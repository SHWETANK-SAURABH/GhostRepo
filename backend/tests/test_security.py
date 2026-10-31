import os
import sys
from pathlib import Path

import pytest

from app.security.path_validation import (
    PathValidationError,
    resolve_repository_path,
    validate_patch_path,
)
from app.security.process_safety import ProcessError, run_command
from app.security.secret_redaction import find_secrets, is_secret_file, redact, redact_data
from tests.helpers import make_junction, make_repo, scan

# Built by concatenation so these fake values never look like real tokens in the source.
AWS_KEY = "AKIA" + "IOSFODNN7EXAMPLE"
GITHUB_TOKEN = "ghp_" + "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8"


def _symlink(link: Path, target: Path) -> None:
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip("Creating symlinks needs extra privileges here")


class TestRepositoryPath:
    def test_accepts_child_by_relative_and_absolute_path(self, workspace: Path) -> None:
        repo = workspace / "repo"
        repo.mkdir()
        assert resolve_repository_path("repo", workspace) == repo.resolve()
        assert resolve_repository_path(str(repo), workspace) == repo.resolve()

    @pytest.mark.parametrize(
        "raw", ["../outside", "repo/../../outside", "..", ".", "..\\outside", "repo/../.."]
    )
    def test_rejects_traversal(self, workspace: Path, raw: str) -> None:
        (workspace / "repo").mkdir()
        (workspace.parent / "outside").mkdir(exist_ok=True)
        with pytest.raises(PathValidationError) as error:
            resolve_repository_path(raw, workspace)
        assert error.value.code == "outside_workspace"

    def test_rejects_absolute_path_outside_workspace(self, workspace: Path, tmp_path: Path) -> None:
        with pytest.raises(PathValidationError) as error:
            resolve_repository_path(str(tmp_path), workspace)
        assert error.value.code == "outside_workspace"

    def test_rejects_symlink_escaping_workspace(self, workspace: Path, tmp_path: Path) -> None:
        outside = tmp_path / "secret-place"
        outside.mkdir()
        _symlink(workspace / "link", outside)
        with pytest.raises(PathValidationError) as error:
            resolve_repository_path("link", workspace)
        assert error.value.code == "outside_workspace"

    @pytest.mark.parametrize("raw", ["", "   ", "bad\x00name"])
    def test_rejects_empty_or_nul(self, workspace: Path, raw: str) -> None:
        with pytest.raises(PathValidationError):
            resolve_repository_path(raw, workspace)

    def test_rejects_missing_and_file_paths(self, workspace: Path) -> None:
        (workspace / "file.txt").write_text("x")
        with pytest.raises(PathValidationError) as missing:
            resolve_repository_path("nope", workspace)
        with pytest.raises(PathValidationError) as not_dir:
            resolve_repository_path("file.txt", workspace)
        assert missing.value.code == "not_found"
        assert not_dir.value.code == "not_a_directory"

    def test_errors_do_not_reveal_server_paths(self, workspace: Path, tmp_path: Path) -> None:
        with pytest.raises(PathValidationError) as error:
            resolve_repository_path(str(tmp_path), workspace)
        assert str(tmp_path) not in error.value.message


@pytest.mark.skipif(sys.platform != "win32", reason="Junctions exist only on Windows")
class TestJunctions:
    def test_repository_path_rejects_junction_escape(self, workspace: Path, tmp_path: Path) -> None:
        outside = tmp_path / "secret-place"
        outside.mkdir()
        make_junction(workspace / "link", outside)
        with pytest.raises(PathValidationError) as error:
            resolve_repository_path("link", workspace)
        assert error.value.code == "outside_workspace"

    def test_patch_path_rejects_write_through_junction(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        repo.mkdir()
        outside = tmp_path / "outside"
        outside.mkdir()
        make_junction(repo / "out", outside)
        with pytest.raises(PathValidationError):
            validate_patch_path(repo, "out/file.txt")

    def test_walker_does_not_enter_junctions(self, tmp_path: Path) -> None:
        repo = make_repo(tmp_path / "repo", {"a.py": "x"})
        outside = make_repo(tmp_path / "outside", {"secret.txt": "top secret"})
        make_junction(repo / "link", outside)
        _, inventory = scan(repo)
        assert inventory.paths() == {"a.py"}
        assert inventory.skipped_symlinks == 1


class TestPatchPath:
    def test_accepts_normal_paths(self, tmp_path: Path) -> None:
        assert validate_patch_path(tmp_path, "docs/guide.md") == "docs/guide.md"
        assert validate_patch_path(tmp_path, "docs\\guide.md") == "docs/guide.md"
        assert validate_patch_path(tmp_path, ".env.example") == ".env.example"

    @pytest.mark.parametrize(
        "path",
        [
            "../evil",
            "a/../../evil",
            "/etc/passwd",
            "C:/Windows/evil",
            "C:evil",
            "//server/share/x",
            "..\\evil",
            ".git/config",
            ".GIT/hooks/pre-commit",
            "sub/.git/config",
            ".git./config",
            ".git /config",
            "git~1/config",
            ".env",
            "config/.env.production",
            "keys/server.pem",
            "NUL",
            "con.txt",
            "file.txt:stream",
            "",
            "a\x00b",
        ],
    )
    def test_rejects_unsafe_paths(self, tmp_path: Path, path: str) -> None:
        with pytest.raises(PathValidationError):
            validate_patch_path(tmp_path, path)

    def test_rejects_write_through_symlink(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        repo.mkdir()
        outside = tmp_path / "outside"
        outside.mkdir()
        _symlink(repo / "out", outside)
        with pytest.raises(PathValidationError):
            validate_patch_path(repo, "out/file.txt")


class TestSecretRedaction:
    @pytest.mark.parametrize(
        ("text", "secret"),
        [
            (f"key = {AWS_KEY}", AWS_KEY),
            (f"token: {GITHUB_TOKEN}", GITHUB_TOKEN),
            ('password = "hunter2hunter2"', "hunter2hunter2"),
            ("API_KEY=abcd1234efgh", "abcd1234efgh"),
            ("postgres://admin:s3cretpw@db.internal/app", "s3cretpw"),
            ('{"client_secret": "very-private-value"}', "very-private-value"),
        ],
    )
    def test_redacts(self, text: str, secret: str) -> None:
        assert secret not in redact(text)
        assert "[REDACTED]" in redact(text)

    def test_redacts_private_key_block(self) -> None:
        block = "-----BEGIN RSA PRIVATE KEY-----\nabc\ndef\n-----END RSA PRIVATE KEY-----"
        assert "abc" not in redact(f"before\n{block}\nafter")

    def test_leaves_normal_text_alone(self) -> None:
        text = "Install dependencies, then run the server on port 8000."
        assert redact(text) == text

    def test_redacts_nested_data_including_keys(self) -> None:
        data = {"a": [f"x {AWS_KEY}"], AWS_KEY: 1, "n": 5}
        result = str(redact_data(data))
        assert AWS_KEY not in result
        assert "'n': 5" in result

    def test_find_secrets_reports_rule_and_line_only(self) -> None:
        hits = find_secrets(f"line one\nkey = {AWS_KEY}\n")
        assert [(hit.rule, hit.line) for hit in hits] == [("aws-access-key", 2)]
        assert AWS_KEY not in str(hits)

    @pytest.mark.parametrize(
        "text",
        [
            'password = "change-me-please"',
            'api_key = "your_api_key_here"',
            'token = "${TOKEN_VALUE}"',
        ],
    )
    def test_find_secrets_ignores_placeholders(self, text: str) -> None:
        assert find_secrets(text) == []

    @pytest.mark.parametrize(
        ("path", "expected"),
        [
            (".env", True),
            ("config/.env.production", True),
            (".env.example", False),
            ("id_rsa", True),
            ("certs/server.key", True),
            ("credentials.json", True),
            ("src/main.py", False),
        ],
    )
    def test_is_secret_file(self, path: str, expected: bool) -> None:
        assert is_secret_file(path) is expected


class TestProcessSafety:
    def test_rejects_shell_strings(self, tmp_path: Path) -> None:
        with pytest.raises(ProcessError):
            run_command("git status", tmp_path, 5)  # type: ignore[arg-type]

    def test_rejects_programs_outside_the_allowlist(self, tmp_path: Path) -> None:
        with pytest.raises(ProcessError):
            run_command(["python", "-c", "print(1)"], tmp_path, 5)

    def test_truncates_large_output(self, tmp_path: Path) -> None:
        result = run_command(["git", "--version"], tmp_path, 10, max_output_bytes=3)
        assert len(result.stdout) == 3
        assert result.truncated is True

    def test_shell_metacharacters_are_plain_arguments(self, tmp_path: Path) -> None:
        marker = tmp_path / "pwned"
        command = f"--version; echo x > {marker}"
        run_command(["git", command], tmp_path, 10)
        assert not marker.exists()
        assert os.listdir(tmp_path) == []
