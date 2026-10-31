import hashlib
import json
import re
import subprocess
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app.agents.readme_generator import NEEDS_CONFIRMATION, build_markdown, generate
from app.analyzers.base import ScanContext
from app.config import Settings
from app.main import create_app
from app.security.path_validation import PathValidationError, validate_patch_path
from app.services.ollama_service import OllamaClient
from app.services.patch_service import (
    ProposedFile,
    check_proposal,
    propose,
    render_patch,
    unified_diff,
)
from tests.helpers import git, init_git, make_repo
from tests.test_investigations import investigate, ollama_handler

AWS_KEY = "AKIA" + "IOSFODNN7EXAMPLE"


def tree_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if path.is_file() and ".git" not in path.relative_to(root).parts:
            digest.update(path.relative_to(root).as_posix().encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()


def profile(**sections) -> dict:
    return {
        "repository": {
            "languages": [{"name": "Python"}],
            "frameworks": [],
            "build_tools": [],
            "entry_points": [],
            "structure": [],
        },
        "dependencies": {"frameworks": [], "dependencies": [], "metadata": {}, "ecosystems": []},
        "configuration": {"env_variables": [], "env_templates": [], "license_files": []},
        "documentation": {"readme": None, "readme_files": [], "contributing_files": []},
        "tests": {"test_file_count": 0, "commands": []},
        **sections,
    }


class TestReadmeGenerator:
    def test_never_fabricates_commands_or_variables_from_nothing(self) -> None:
        content, unverified = build_markdown(profile(), "demo")
        assert "```sh" not in content
        assert "npm" not in content
        assert "pip install" not in content
        assert content.count(NEEDS_CONFIRMATION) >= 5
        assert {"Installation", "Configuration", "Testing", "License"} <= set(unverified)

    def test_commands_match_the_files_present(self) -> None:
        data = profile(
            repository={
                "languages": [],
                "frameworks": [],
                "build_tools": [],
                "entry_points": ["main.py"],
                "structure": [
                    {"path": "requirements.txt", "type": "file"},
                    {"path": "package.json", "type": "file"},
                    {"path": "yarn.lock", "type": "file"},
                ],
            }
        )
        content, _ = build_markdown(data, "demo")
        assert "pip install -r requirements.txt" in content
        assert "yarn install" in content
        assert "npm ci" not in content
        assert "GhostRepo did not run them" in content

    def test_only_declared_scripts_are_listed(self) -> None:
        data = profile(
            dependencies={
                "frameworks": [],
                "dependencies": [],
                "ecosystems": ["npm"],
                "metadata": {
                    "package.json": {"scripts": {"start": "node x", "deploy": "rm -rf /"}}
                },
            }
        )
        content, _ = build_markdown(data, "demo")
        assert "npm run start" in content
        assert "deploy" not in content
        assert "rm -rf" not in content

    def test_structure_leaves_out_secret_file_names(self) -> None:
        repository = {
            **profile()["repository"],
            "structure": [
                {"path": ".env", "type": "file"},
                {"path": "server.pem", "type": "file"},
                {"path": "main.py", "type": "file"},
            ],
        }
        content, _ = build_markdown(profile(repository=repository), "demo")
        assert "main.py" in content
        assert ".env" not in content
        assert "server.pem" not in content

    def test_env_variable_names_only(self) -> None:
        data = profile(
            configuration={"env_variables": ["DB_URL"], "env_templates": [], "license_files": []}
        )
        content, _ = build_markdown(data, "demo")
        assert "`DB_URL`" in content

    def test_repository_text_cannot_inject_html_or_links(self) -> None:
        data = profile(
            dependencies={
                "frameworks": [],
                "dependencies": [],
                "ecosystems": [],
                "metadata": {
                    "package.json": {
                        "description": "<script>alert(1)</script> [click](javascript:alert(1))"
                    }
                },
            }
        )
        content, _ = build_markdown(data, "<img src=x onerror=alert(1)>")
        assert not re.search(r"(?<!\\)<(script|img)", content)
        assert "[click](" not in content

    def test_secrets_are_redacted(self) -> None:
        data = profile(
            dependencies={
                "frameworks": [],
                "dependencies": [],
                "ecosystems": [],
                "metadata": {"package.json": {"description": f"key {AWS_KEY}"}},
            }
        )
        assert AWS_KEY not in build_markdown(data, "demo")[0]

    def _client(self, content: str) -> OllamaClient:
        return OllamaClient(
            endpoint="http://localhost:11434",
            model="gemma3:4b",
            transport=httpx.MockTransport(
                lambda _: httpx.Response(200, json={"message": {"content": content}})
            ),
        )

    def test_ai_overview_is_labeled(self) -> None:
        draft = generate(profile(), "demo", self._client(json.dumps({"overview": "A tracker."})))
        assert draft.origin == "deterministic_and_ai"
        assert "AI-drafted by a local model" in draft.content
        assert "A tracker." in draft.content

    def test_ai_failure_keeps_the_deterministic_draft(self) -> None:
        draft = generate(profile(), "demo", self._client("not json"))
        assert draft.origin == "deterministic"
        assert "AI overview was left out" in draft.warning
        assert "## Installation" in draft.content


class TestPatchDiffs:
    def _apply(self, repo: Path, diff: str) -> None:
        patch = repo.parent / "change.patch"
        patch.write_bytes(diff.encode("utf-8"))
        git(repo, "apply", "--check", str(patch))
        git(repo, "apply", str(patch))

    def _repo(self, tmp_path: Path, files: dict[str, str] | None = None) -> Path:
        repo = make_repo(tmp_path / "repo", files or {"a.py": "x\n"})
        init_git(repo)
        return repo

    def test_new_file_patch_applies(self, tmp_path: Path) -> None:
        repo = self._repo(tmp_path)
        self._apply(repo, unified_diff("docs/new.md", None, "line one\nline two\n"))
        assert (repo / "docs/new.md").read_text() == "line one\nline two\n"

    def test_append_patch_applies(self, tmp_path: Path) -> None:
        repo = self._repo(tmp_path, {".gitignore": "*.log\n"})
        self._apply(repo, unified_diff(".gitignore", "*.log\n", "*.log\n.env\n"))
        assert (repo / ".gitignore").read_text() == "*.log\n.env\n"

    def test_patch_applies_when_file_has_no_trailing_newline(self, tmp_path: Path) -> None:
        repo = self._repo(tmp_path)
        (repo / ".gitignore").write_bytes(b"*.log")
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", "x")
        self._apply(repo, unified_diff(".gitignore", "*.log", "*.log\n.env\n"))
        assert (repo / ".gitignore").read_bytes() == b"*.log\n.env\n"

    def test_patch_preserves_crlf(self, tmp_path: Path) -> None:
        repo = self._repo(tmp_path)
        (repo / ".gitignore").write_bytes(b"*.log\r\n")
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", "x")
        ctx = ScanContext(root=repo)
        files, _ = propose(ctx, profile(configuration={"has_gitignore": True}))
        item = next(file for file in files if file.path == ".gitignore")
        self._apply(repo, render_patch([item]))
        assert (repo / ".gitignore").read_bytes().count(b"\r\n") == 5

    def test_existing_env_rule_means_no_gitignore_change(self, tmp_path: Path) -> None:
        repo = make_repo(tmp_path / "repo", {".gitignore": ".env\n"})
        files, _ = propose(ScanContext(root=repo), profile(configuration={"has_gitignore": True}))
        assert ".gitignore" not in {file.path for file in files}

    def test_gitignore_holding_a_secret_is_left_alone(self, tmp_path: Path) -> None:
        repo = make_repo(tmp_path / "repo", {".gitignore": f"# {AWS_KEY}\n"})
        files, _ = propose(ScanContext(root=repo), profile(configuration={"has_gitignore": True}))
        assert ".gitignore" not in {file.path for file in files}


class TestPatchSafety:
    @pytest.mark.parametrize(
        "path",
        ["../evil", "/etc/cron.d/x", ".git/hooks/pre-commit", ".env", "certs/server.key"],
    )
    def test_unsafe_targets_are_refused(self, tmp_path: Path, path: str) -> None:
        item = ProposedFile(path, "create", "x", None, "x\n")
        assert check_proposal(tmp_path, item) is False
        with pytest.raises(PathValidationError):
            validate_patch_path(tmp_path, path)

    def test_create_never_replaces_an_existing_file(self, tmp_path: Path) -> None:
        make_repo(tmp_path, {"CONTRIBUTING.md": "mine"})
        item = ProposedFile("CONTRIBUTING.md", "create", "x", None, "theirs\n")
        assert check_proposal(tmp_path, item) is False

    def test_existing_readme_is_never_proposed(self, tmp_path: Path) -> None:
        files, _ = propose(
            ScanContext(root=tmp_path),
            profile(documentation={"readme_files": ["README.md"], "contributing_files": []}),
            readme_draft="# Draft\n",
        )
        assert "README.md" not in {file.path for file in files}

    def test_env_example_contains_names_only(self, tmp_path: Path) -> None:
        files, _ = propose(
            ScanContext(root=tmp_path),
            profile(configuration={"env_variables": ["DB_URL"], "env_templates": []}),
        )
        item = next(file for file in files if file.path == ".env.example")
        assert "DB_URL=\n" in item.after


class TestArtifactApi:
    @pytest.fixture
    def repo(self, workspace: Path) -> Path:
        path = make_repo(
            workspace / "demo",
            {
                "app.py": 'import os\nos.environ["DB_URL"]\n',
                "requirements.txt": "flask==2.0\n",
            },
        )
        init_git(path)
        return path

    def test_readme_flow_never_touches_the_repository(self, client: TestClient, repo: Path) -> None:
        before = tree_hash(repo)
        body = investigate(client)
        base = f"/api/investigations/{body['id']}"
        assert client.get(f"{base}/readme").status_code == 404

        draft = client.post(f"{base}/generate-readme", json={}).json()
        assert draft["origin"] == "deterministic"
        assert "pip install -r requirements.txt" in draft["content"]
        assert client.get(f"{base}/readme").json()["id"] == draft["id"]

        saved = client.put(f"{base}/readme", json={"content": "# Edited\n"}).json()
        assert saved["origin"] == "edited"
        assert client.get(f"{base}/readme").json()["content"] == "# Edited\n"
        assert tree_hash(repo) == before
        assert not (repo / "README.md").exists()

    def test_readme_ai_request_is_refused_when_disabled(
        self, client: TestClient, repo: Path
    ) -> None:
        body = investigate(client)
        settings_body = {**client.get("/api/settings").json(), "ai_enabled": False}
        client.put("/api/settings", json=settings_body)
        response = client.post(
            f"/api/investigations/{body['id']}/generate-readme", json={"use_ai": True}
        )
        assert response.status_code == 409

    def test_readme_ai_unavailable_reports_warning(self, client: TestClient, repo: Path) -> None:
        body = investigate(client)
        draft = client.post(
            f"/api/investigations/{body['id']}/generate-readme", json={"use_ai": True}
        ).json()
        assert draft["origin"] == "deterministic"
        assert "AI overview was left out" in draft["warning"]

    def test_patch_requires_explicit_approval_and_is_never_applied(
        self, client: TestClient, repo: Path
    ) -> None:
        before = tree_hash(repo)
        body = investigate(client)
        base = f"/api/investigations/{body['id']}"
        client.post(f"{base}/generate-readme", json={})

        patch = client.post(f"{base}/generate-patch").json()
        assert patch["status"] == "proposed"
        paths = {file["path"] for file in patch["files"]}
        assert paths == {".gitignore", ".env.example", "README.md", "CONTRIBUTING.md"}
        assert all(file["explanation"] for file in patch["files"])
        assert tree_hash(repo) == before

        download = f"{base}/patch/{patch['id']}/download"
        assert client.get(download).status_code == 409

        approve = f"{base}/patch/{patch['id']}/approve"
        assert client.post(approve, json={"confirm": False}).status_code == 400
        assert client.get(download).status_code == 409

        approved = client.post(approve, json={"confirm": True}).json()
        assert approved["status"] == "approved"
        assert approved["approved_at"]
        assert tree_hash(repo) == before

        response = client.get(download)
        assert response.status_code == 200
        assert "attachment" in response.headers["content-disposition"]
        assert tree_hash(repo) == before

        # The download really applies, in a throwaway copy made by the person's own choice.
        patch_file = repo.parent / "change.patch"
        patch_file.write_bytes(response.content)
        subprocess.run(["git", "apply", "--check", str(patch_file)], cwd=repo, check=True)

    def test_empty_proposal_cannot_be_approved(self, client: TestClient, workspace: Path) -> None:
        make_repo(
            workspace / "tidy",
            {
                "README.md": "# Tidy\n",
                ".gitignore": ".env\n",
                "CONTRIBUTING.md": "x",
            },
        )
        body = investigate(client, "tidy")
        base = f"/api/investigations/{body['id']}"
        patch = client.post(f"{base}/generate-patch").json()
        assert patch["files"] == []
        assert "No safe automatic change" in patch["message"]
        response = client.post(f"{base}/patch/{patch['id']}/approve", json={"confirm": True})
        assert response.status_code == 409

    def test_patch_from_another_investigation_is_not_found(
        self, client: TestClient, repo: Path
    ) -> None:
        body = investigate(client)
        patch = client.post(f"/api/investigations/{body['id']}/generate-patch").json()
        response = client.get(f"/api/investigations/other/patch/{patch['id']}/download")
        assert response.status_code == 404


class TestDemoRepository:
    def test_endpoint_creates_labeled_git_repository(
        self, client: TestClient, workspace: Path
    ) -> None:
        response = client.post("/api/repositories/demo")
        assert response.status_code == 201
        candidates = client.get("/api/repositories/candidates").json()["candidates"]
        assert candidates == [
            {
                "name": "haunted-demo",
                "relative_path": "haunted-demo",
                "is_git": True,
                "is_demo": True,
            }
        ]
        # Rebuilding the demo works, including removing Git's read-only objects.
        assert client.post("/api/repositories/demo").status_code == 201

    def test_refuses_to_replace_a_real_folder(self, client: TestClient, workspace: Path) -> None:
        make_repo(workspace / "haunted-demo", {"precious.txt": "keep me"})
        assert client.post("/api/repositories/demo").status_code == 409
        assert (workspace / "haunted-demo/precious.txt").exists()


class TestEndToEnd:
    """The workflow from the product brief, with a stand-in model so it runs anywhere."""

    def test_sample_repository_workflow(self, settings: Settings, workspace: Path) -> None:
        app = create_app(settings)
        with TestClient(app) as client:
            client.post("/api/repositories/demo")
            validated = client.post(
                "/api/repositories/validate", json={"path": "haunted-demo"}
            ).json()
            assert validated["valid"] is True

            # First run: no model, deterministic results only.
            first = investigate(client, "haunted-demo")
            assert first["ai_status"] == "unavailable"
            report = client.get(f"/api/investigations/{first['id']}/report").json()
            titles = {finding["title"] for finding in report["verified_findings"]}
            assert "Secret file is committed: .env" in titles
            assert "Possible hardcoded credentials" in titles
            assert "Dependencies have no version constraint" in titles
            assert "demo-only-not-a-real-credential" not in json.dumps(report)
            assert report["profile"]["git"]["commit_count"] == 3
            assert report["profile"]["tests"]["test_file_count"] == 1

            # Retry with a model, validated against the stored evidence.
            key = report["evidence"][0]["key"]
            app.state.ollama_transport = httpx.MockTransport(
                ollama_handler(
                    json.dumps(
                        {
                            "summary": "s",
                            "health_assessment": "h",
                            "findings": [
                                {
                                    "title": "t",
                                    "description": "d",
                                    "severity": "low",
                                    "category": "maintenance",
                                    "evidence_ids": [key],
                                    "recommendation": "r",
                                    "confidence": 0.5,
                                    "is_hypothesis": True,
                                }
                            ],
                            "recovery_plan": [],
                        }
                    )
                )
            )
            client.post(f"/api/investigations/{first['id']}/reanalyze")
            from tests.test_investigations import wait_until

            wait_until(client, first["id"], lambda item: item["ai_status"] == "completed")

            base = f"/api/investigations/{first['id']}"
            assert client.post(f"{base}/generate-readme", json={}).status_code == 201
            assert client.post(f"{base}/generate-patch").status_code == 201
            exported = client.get(f"{base}/export").text
            assert "Deterministic analyzers and a local AI model" in exported
            assert "demo-only-not-a-real-credential" not in exported
