import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.analyzers import (
    configuration_analyzer,
    dependency_analyzer,
    documentation_analyzer,
    git_historian,
    repository_scout,
    test_discovery,
)
from app.analyzers.base import read_text
from app.analyzers.dependency_analyzer import (
    ManifestError,
    parse_cargo,
    parse_go_mod,
    parse_package_json,
    parse_pom,
    parse_pyproject,
    parse_requirements,
)
from app.services.evidence_service import build_model_context, normalize
from tests.helpers import git, init_git, kinds, make_repo, scan

AWS_KEY = "AKIA" + "IOSFODNN7EXAMPLE"


class TestWalker:
    def test_excludes_generated_directories(self, tmp_path: Path) -> None:
        make_repo(tmp_path, {"src/a.py": "x", "node_modules/b.js": "x", ".venv/c.py": "x"})
        _, inventory = scan(tmp_path)
        assert inventory.paths() == {"src/a.py"}

    def test_stops_at_file_limit(self, tmp_path: Path) -> None:
        make_repo(tmp_path, {f"f{i}.py": "x" for i in range(5)})
        _, inventory = scan(tmp_path, max_files=2)
        assert inventory.truncated is True
        assert len(inventory.files) == 2

    def test_stops_at_depth_limit(self, tmp_path: Path) -> None:
        make_repo(tmp_path, {"a/b/c/d.py": "x", "top.py": "x"})
        _, inventory = scan(tmp_path, max_depth=1)
        assert inventory.depth_limited is True
        assert "a/b/c/d.py" not in inventory.paths()

    def test_does_not_follow_symlinks(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        make_repo(repo, {"a.py": "x"})
        outside = tmp_path / "outside"
        make_repo(outside, {"secret.txt": "top secret"})
        try:
            (repo / "link").symlink_to(outside, target_is_directory=True)
            (repo / "file-link").symlink_to(outside / "secret.txt")
        except OSError:
            pytest.skip("Creating symlinks needs extra privileges here")
        ctx, inventory = scan(repo)
        assert inventory.paths() == {"a.py"}
        assert inventory.skipped_symlinks == 2
        assert read_text(ctx, "file-link") is None

    def test_read_text_refuses_oversized_binary_and_secret_files(self, tmp_path: Path) -> None:
        make_repo(tmp_path, {"big.txt": "x" * 100, ".env": "A=1"})
        (tmp_path / "bin.dat").write_bytes(b"\x00\x01")
        ctx, _ = scan(tmp_path, max_file_size=10)
        assert read_text(ctx, "big.txt") is None
        assert read_text(ctx, "bin.dat") is None
        assert read_text(ctx, ".env") is None


class TestRepositoryScout:
    def test_detects_languages_tools_and_entry_points(self, tmp_path: Path) -> None:
        make_repo(
            tmp_path,
            {
                "main.py": "print('x')" * 100,
                "web/app.ts": "let a = 1",
                "styles.css": "a{}" * 2000,
                "Dockerfile": "FROM scratch",
                "manage.py": "x",
                "pyproject.toml": "",
            },
        )
        ctx, inventory = scan(tmp_path)
        facts = repository_scout.analyze(ctx, inventory).facts
        assert facts["primary_language"] == "Python"
        assert "TypeScript" in facts["secondary_languages"]
        assert "Django" in facts["frameworks"]
        assert "Docker" in facts["build_tools"]
        assert "main.py" in facts["entry_points"]

    def test_marks_unsupported_languages(self, tmp_path: Path) -> None:
        make_repo(tmp_path, {"a.rb": "puts 1", "b.go": "package b"})
        ctx, inventory = scan(tmp_path)
        languages = {
            item["name"]: item["deep_support"]
            for item in repository_scout.analyze(ctx, inventory).facts["languages"]
        }
        assert languages == {"Ruby": False, "Go": True}

    def test_empty_repository(self, tmp_path: Path) -> None:
        ctx, inventory = scan(tmp_path)
        result = repository_scout.analyze(ctx, inventory)
        assert "repository.empty" in kinds(result)
        assert result.facts["primary_language"] is None


class TestGitHistorian:
    def test_reads_history(self, tmp_path: Path) -> None:
        make_repo(tmp_path, {"a.py": "x"})
        init_git(tmp_path)
        (tmp_path / "b.py").write_text("y")
        git(tmp_path, "add", "-A")
        git(tmp_path, "commit", "-q", "-m", "fix: second", date="2024-03-01T12:00:00+00:00")
        ctx, _ = scan(tmp_path)

        now = datetime(2024, 3, 11, 12, tzinfo=UTC)
        facts = git_historian.analyze(ctx, now=now).facts

        assert facts["available"] is True
        assert facts["branch"] == "main"
        assert facts["commit_count"] == 2
        assert facts["latest_commit"]["subject"] == "fix: second"
        assert facts["days_since_last_commit"] == 10
        assert facts["activity"]["last_30_days"] == 1
        assert facts["activity"]["last_90_days"] == 2
        assert facts["contributor_count"] == 1
        assert facts["message_patterns"]["conventional_commit_share"] == 100.0

    def test_author_email_is_not_collected(self, tmp_path: Path) -> None:
        make_repo(tmp_path, {"a.py": "x"})
        init_git(tmp_path)
        ctx, _ = scan(tmp_path)
        assert "ada@example.com" not in json.dumps(git_historian.analyze(ctx).facts)

    def test_old_repository_is_an_observation_not_abandonment(self, tmp_path: Path) -> None:
        make_repo(tmp_path, {"a.py": "x"})
        init_git(tmp_path)
        ctx, _ = scan(tmp_path)
        result = git_historian.analyze(ctx, now=datetime(2030, 1, 1, tzinfo=UTC))
        item = next(e for e in result.evidence if e.kind == "git.no_recent_commits")
        assert "not abandoned" in item.description

    def test_no_git_metadata(self, tmp_path: Path) -> None:
        make_repo(tmp_path, {"a.py": "x"})
        ctx, _ = scan(tmp_path)
        result = git_historian.analyze(ctx)
        assert result.facts["available"] is False
        assert "git.absent" in kinds(result)

    def test_does_not_report_a_parent_repository(self, tmp_path: Path) -> None:
        make_repo(tmp_path, {"inner/a.py": "x"})
        init_git(tmp_path)
        ctx, _ = scan(tmp_path / "inner")
        assert git_historian.analyze(ctx).facts["available"] is False

    def test_repository_without_commits(self, tmp_path: Path) -> None:
        make_repo(tmp_path, {"a.py": "x"})
        git(tmp_path, "init", "-q", "-b", "main")
        ctx, _ = scan(tmp_path)
        result = git_historian.analyze(ctx)
        assert result.facts["commit_count"] == 0
        assert "git.no_commits" in kinds(result)

    def test_git_pointer_file_is_not_followed(self, tmp_path: Path) -> None:
        make_repo(tmp_path, {"a.py": "x", ".git": "gitdir: /somewhere/else\n"})
        ctx, _ = scan(tmp_path)
        result = git_historian.analyze(ctx)
        assert result.facts["reason"] == "unsafe_git_metadata"

    def test_hostile_git_config_cannot_run_programs(self, tmp_path: Path) -> None:
        make_repo(tmp_path, {"a.py": "x"})
        init_git(tmp_path)
        marker = tmp_path / "pwned"
        script = tmp_path / "evil.sh"
        script.write_text(f"#!/bin/sh\ntouch '{marker.as_posix()}'\n")
        script.chmod(0o755)
        program = script.as_posix()
        with (tmp_path / ".git" / "config").open("a") as config:
            config.write(
                f"[core]\n\tfsmonitor = {program}\n\tpager = {program}\n"
                f"[log]\n\tshowSignature = true\n[gpg]\n\tprogram = {program}\n"
            )
        ctx, _ = scan(tmp_path)
        git_historian.analyze(ctx)
        git_historian.tracked_paths(ctx, ["a.py"])
        assert not marker.exists()

    def test_commit_subject_secrets_are_redacted(self, tmp_path: Path) -> None:
        make_repo(tmp_path, {"a.py": "x"})
        init_git(tmp_path, message=f"add key {AWS_KEY}")
        ctx, _ = scan(tmp_path)
        assert AWS_KEY not in json.dumps(git_historian.analyze(ctx).facts)


class TestManifestParsers:
    def test_requirements(self) -> None:
        text = (
            "# comment\nflask==2.0.1\nrequests>=2,<3\nnumpy\n-r other.txt\n"
            "pkg @ https://example.com/pkg.tar.gz\n!!invalid!!\n"
        )
        deps, invalid = parse_requirements(text, "requirements.txt")
        by_name = {dep.name: dep for dep in deps}
        assert by_name["flask"].pinning == "exact"
        assert by_name["requests"].pinning == "range"
        assert by_name["numpy"].pinning == "unbounded"
        assert by_name["pkg"].pinning == "external"
        assert invalid == ["line 7"]

    def test_pyproject_pep621_and_poetry(self) -> None:
        text = """
[project]
name = "demo"
requires-python = ">=3.10"
dependencies = ["httpx>=0.27", "rich"]
[project.optional-dependencies]
dev = ["pytest==8.0"]
[tool.poetry.dependencies]
python = "^3.10"
django = "^4.2"
[tool.pytest.ini_options]
addopts = "-q"
"""
        deps, invalid, meta = parse_pyproject(text, "pyproject.toml")
        by_name = {dep.name: dep for dep in deps}
        assert set(by_name) == {"httpx", "rich", "pytest", "django"}
        assert by_name["pytest"].dev is True
        assert by_name["rich"].pinning == "unbounded"
        assert meta["requires_python"] == ">=3.10"
        assert invalid == []

    def test_package_json(self) -> None:
        text = json.dumps(
            {
                "name": "demo",
                "dependencies": {
                    "react": "^18.0.0",
                    "left": "1.2.3",
                    "any": "*",
                    "g": "github:a/b",
                },
                "devDependencies": {"vitest": "~1.0.0"},
                "scripts": {"test": "vitest"},
            }
        )
        deps, meta = parse_package_json(text, "package.json")
        by_name = {dep.name: dep for dep in deps}
        assert by_name["react"].pinning == "range"
        assert by_name["left"].pinning == "exact"
        assert by_name["any"].pinning == "unbounded"
        assert by_name["g"].pinning == "external"
        assert by_name["vitest"].dev is True
        assert meta["scripts"] == {"test": "vitest"}

    def test_cargo(self) -> None:
        text = """
[package]
name = "demo"
[dependencies]
serde = "1.0"
tokio = { version = "=1.2.3" }
local = { path = "../local" }
any = "*"
[dev-dependencies]
proptest = "1"
"""
        deps, meta = parse_cargo(text, "Cargo.toml")
        by_name = {dep.name: dep for dep in deps}
        assert by_name["serde"].pinning == "range"
        assert by_name["tokio"].pinning == "exact"
        assert by_name["local"].pinning == "external"
        assert by_name["any"].pinning == "unbounded"
        assert by_name["proptest"].dev is True
        assert meta["name"] == "demo"

    def test_go_mod(self) -> None:
        text = (
            "module example.com/demo\n\ngo 1.21\n\nrequire (\n"
            "\tgithub.com/gin-gonic/gin v1.9.0\n\tgolang.org/x/net v0.1.0 // indirect\n)\n"
            "require github.com/x/y v1.0.0\n"
        )
        deps, meta = parse_go_mod(text, "go.mod")
        assert [dep.name for dep in deps] == [
            "github.com/gin-gonic/gin", "golang.org/x/net", "github.com/x/y",
        ]  # fmt: skip
        assert deps[1].dev is True
        assert meta == {"name": "example.com/demo", "go_version": "1.21"}

    def test_pom(self) -> None:
        text = """<project xmlns="http://maven.apache.org/POM/4.0.0">
  <artifactId>demo</artifactId>
  <dependencies>
    <dependency><groupId>a</groupId><artifactId>b</artifactId><version>1.0</version></dependency>
    <dependency><groupId>c</groupId><artifactId>d</artifactId><version>${v}</version></dependency>
    <dependency><groupId>e</groupId><artifactId>f</artifactId><scope>test</scope></dependency>
  </dependencies>
</project>"""
        deps, meta = parse_pom(text, "pom.xml")
        assert [(d.name, d.pinning, d.dev) for d in deps] == [
            ("a:b", "exact", False), ("c:d", "range", False), ("e:f", "unbounded", True),
        ]  # fmt: skip
        assert meta["name"] == "demo"

    @pytest.mark.parametrize(
        "payload",
        [
            '<!DOCTYPE x [<!ENTITY e SYSTEM "file:///etc/passwd">]><project>&e;</project>',
            '<!DOCTYPE x [<!ENTITY a "aaaa"><!ENTITY b "&a;&a;">]><project>&b;</project>',
        ],
    )
    def test_pom_refuses_xml_entity_attacks(self, payload: str) -> None:
        with pytest.raises(ManifestError):
            parse_pom(payload, "pom.xml")


class TestDependencyAnalyzer:
    def test_summarizes_and_states_freshness_is_unverified(self, tmp_path: Path) -> None:
        make_repo(
            tmp_path,
            {
                "requirements.txt": "flask==2.0\nnumpy\n",
                "web/package.json": json.dumps({"dependencies": {"react": "^18"}}),
            },
        )
        ctx, inventory = scan(tmp_path)
        result = dependency_analyzer.analyze(ctx, inventory)
        assert result.facts["dependency_count"] == 3
        assert result.facts["freshness_verified"] is False
        assert result.facts["ecosystems"] == ["npm", "pypi"]
        assert {"Flask", "React"} == set(result.facts["frameworks"])
        assert {"dependency.unbounded", "dependency.freshness_unverified"} <= kinds(result)
        assert "dependency.no_lockfile" in kinds(result)

    def test_recognizes_lockfile(self, tmp_path: Path) -> None:
        make_repo(
            tmp_path,
            {"package.json": json.dumps({"dependencies": {"a": "1.0.0"}}), "yarn.lock": ""},
        )
        ctx, inventory = scan(tmp_path)
        assert "dependency.no_lockfile" not in kinds(dependency_analyzer.analyze(ctx, inventory))

    @pytest.mark.parametrize(
        ("name", "content"),
        [
            ("package.json", "{not json"),
            ("package.json", "[1,2]"),
            ("pyproject.toml", "= broken"),
            ("Cargo.toml", "[[["),
            ("pom.xml", "<project><unclosed>"),
            ("package.json", "[" * 200_000),
        ],
    )
    def test_malformed_manifests_are_reported_not_fatal(
        self, tmp_path: Path, name: str, content: str
    ) -> None:
        make_repo(tmp_path, {name: content})
        ctx, inventory = scan(tmp_path)
        result = dependency_analyzer.analyze(ctx, inventory)
        assert "dependency.manifest_malformed" in kinds(result)
        assert result.facts["malformed_manifests"] == [name]

    def test_no_manifest(self, tmp_path: Path) -> None:
        make_repo(tmp_path, {"a.py": "x"})
        ctx, inventory = scan(tmp_path)
        assert "dependency.no_manifest" in kinds(dependency_analyzer.analyze(ctx, inventory))


class TestConfigurationAnalyzer:
    def test_secret_values_never_reach_evidence(self, tmp_path: Path) -> None:
        make_repo(
            tmp_path,
            {"settings.py": f'KEY = "{AWS_KEY}"\nDEBUG = True\nALLOWED_HOSTS = ["*"]\n'},
        )
        ctx, inventory = scan(tmp_path)
        result = configuration_analyzer.analyze(ctx, inventory)
        assert AWS_KEY not in json.dumps([vars(item) for item in result.evidence])
        secret = next(e for e in result.evidence if e.kind == "configuration.secret_pattern")
        assert secret.data == {"rule": "aws-access-key", "file": "settings.py", "line": 1}
        rules = {e.data["rule"] for e in result.evidence if e.kind == "configuration.risky_setting"}
        assert rules == {"debug-enabled", "wildcard-allowed-hosts"}

    def test_env_file_contents_are_not_read(self, tmp_path: Path) -> None:
        make_repo(tmp_path, {".env": f"KEY={AWS_KEY}\n"})
        ctx, inventory = scan(tmp_path)
        result = configuration_analyzer.analyze(ctx, inventory)
        assert "configuration.secret_file" in kinds(result)
        assert "configuration.secret_pattern" not in kinds(result)

    def test_committed_env_file_is_flagged_as_tracked(self, tmp_path: Path) -> None:
        make_repo(tmp_path, {".env": "A=1\n", "a.py": "x"})
        init_git(tmp_path)
        ctx, inventory = scan(tmp_path)
        item = next(
            e
            for e in configuration_analyzer.analyze(ctx, inventory).evidence
            if e.kind == "configuration.secret_file"
        )
        assert item.data["tracked"] is True

    def test_finds_env_references_license_and_missing_config(self, tmp_path: Path) -> None:
        make_repo(
            tmp_path,
            {
                "app.py": 'import os\nos.environ["DB_URL"]\nos.getenv("PORT")\n',
                "web.js": "process.env.API_HOST",
            },
        )
        ctx, inventory = scan(tmp_path)
        result = configuration_analyzer.analyze(ctx, inventory)
        assert result.facts["env_variables"] == ["API_HOST", "DB_URL", "PORT"]
        assert {
            "configuration.env_template_missing",
            "configuration.license_missing",
            "configuration.gitignore_missing",
            "configuration.ci_missing",
        } <= kinds(result)

    def test_recognizes_existing_configuration(self, tmp_path: Path) -> None:
        make_repo(
            tmp_path,
            {
                "LICENSE": "MIT License\n\nCopyright",
                ".env.example": "PORT=\n",
                ".gitignore": ".env\n",
                "Dockerfile": "FROM x",
                ".github/workflows/ci.yml": "on: push",
            },
        )
        ctx, inventory = scan(tmp_path)
        result = configuration_analyzer.analyze(ctx, inventory)
        assert result.facts["license"] == "MIT"
        assert result.facts["deployment"] == ["Docker"]
        assert result.facts["ci_files"] == [".github/workflows/ci.yml"]
        assert {"configuration.license", "configuration.env_template", "configuration.ci"} <= kinds(
            result
        )


class TestDocumentationAnalyzer:
    def test_complete_readme_scores_higher(self, tmp_path: Path) -> None:
        readme = (
            "# Demo\n\nThis project collects weather data from stations and stores the "
            "readings so analysts can compare them over long periods of time.\n\n"
            "## Installation\n\n```\nx\n```\n\n## Usage\n\ntext\n\n## Testing\n\n## Configuration\n"
        )
        make_repo(
            tmp_path,
            {
                "README.md": readme,
                "LICENSE": "x",
                "CONTRIBUTING.md": "x",
                "docs/ARCHITECTURE.md": "x",
                "docs/api.md": "x",
            },
        )
        ctx, inventory = scan(tmp_path)
        facts = documentation_analyzer.analyze(ctx, inventory).facts
        assert facts["completeness_score"] == 100
        assert facts["api_docs"] == ["docs/api.md"]
        assert facts["readme"]["sections"]["installation"] is True

    def test_missing_docs(self, tmp_path: Path) -> None:
        make_repo(tmp_path, {"a.py": "x"})
        ctx, inventory = scan(tmp_path)
        result = documentation_analyzer.analyze(ctx, inventory)
        assert result.facts["completeness_score"] == 0
        assert {"documentation.readme_missing", "documentation.contributing_missing"} <= kinds(
            result
        )

    def test_thin_readme_reports_gaps(self, tmp_path: Path) -> None:
        make_repo(tmp_path, {"README.md": "# Demo\n\nShort.\n"})
        ctx, inventory = scan(tmp_path)
        result = documentation_analyzer.analyze(ctx, inventory)
        item = next(e for e in result.evidence if e.kind == "documentation.readme_gaps")
        assert item.data["missing_sections"] == ["installation", "usage"]
        assert result.facts["criteria"]["README has an overview"] is False


class TestTestDiscovery:
    def test_finds_python_tests_without_running(self, tmp_path: Path) -> None:
        make_repo(
            tmp_path,
            {
                "tests/test_a.py": "raise SystemExit('executed!')",
                "pytest.ini": "",
                "src/a.py": "x",
            },
        )
        ctx, inventory = scan(tmp_path)
        result = test_discovery.analyze(ctx, inventory)
        assert result.facts["executed"] is False
        assert result.facts["test_file_count"] == 1
        assert result.facts["frameworks"] == ["pytest"]
        assert result.facts["commands"] == [
            {"command": "pytest", "source": "inferred", "file": None}
        ]

    def test_detects_other_ecosystems(self, tmp_path: Path) -> None:
        make_repo(
            tmp_path,
            {
                "a_test.go": "package a",
                "web/x.spec.ts": "x",
                "src/test/java/FooTest.java": "x",
                "vitest.config.ts": "x",
            },
        )
        ctx, inventory = scan(tmp_path)
        facts = test_discovery.analyze(ctx, inventory).facts
        assert facts["test_file_count"] == 3
        assert {"go test", "Vitest"} <= set(facts["frameworks"])

    def test_declared_and_placeholder_scripts(self, tmp_path: Path) -> None:
        make_repo(
            tmp_path,
            {"package.json": json.dumps({"scripts": {"test": 'echo "Error: no test specified"'}})},
        )
        ctx, inventory = scan(tmp_path)
        result = test_discovery.analyze(ctx, inventory)
        assert "testing.placeholder_script" in kinds(result)
        assert result.facts["commands"] == []

    def test_no_tests(self, tmp_path: Path) -> None:
        make_repo(tmp_path, {"a.py": "x"})
        ctx, inventory = scan(tmp_path)
        assert "testing.no_tests" in kinds(test_discovery.analyze(ctx, inventory))


class TestEvidenceNormalization:
    def _results(self, root: Path) -> list:
        ctx, inventory = scan(root)
        return [
            repository_scout.analyze(ctx, inventory),
            git_historian.analyze(ctx),
            dependency_analyzer.analyze(ctx, inventory),
            configuration_analyzer.analyze(ctx, inventory),
            documentation_analyzer.analyze(ctx, inventory),
            test_discovery.analyze(ctx, inventory),
        ]

    def test_keys_are_unique_and_prefixed(self, tmp_path: Path) -> None:
        make_repo(tmp_path, {"a.py": "x", "requirements.txt": "numpy\n"})
        evidence = normalize(self._results(tmp_path))
        keys = [item.key for item in evidence]
        assert len(keys) == len(set(keys))
        assert {key.split("-")[1] for key in keys} == {"repo", "git", "dep", "cfg", "doc", "tst"}
        assert all(item.detection_method for item in evidence)

    def test_normalization_redacts_and_bounds(self, tmp_path: Path) -> None:
        from app.analyzers.base import AnalyzerResult, RawEvidence

        raw = RawEvidence(
            "repository.x", "repository", f"has {AWS_KEY}", "m",
            data={"v": f"{AWS_KEY} " + "x" * 5000, "items": list(range(500))},
        )  # fmt: skip
        item = normalize([AnalyzerResult("n", {}, [raw])])[0]
        assert AWS_KEY not in item.description
        assert AWS_KEY not in str(item.structured_data)
        assert len(item.structured_data["v"]) <= 400
        assert len(item.structured_data["items"]) == 50

    def test_model_context_excludes_secret_values_and_respects_budget(self, tmp_path: Path) -> None:
        make_repo(
            tmp_path,
            {".env": f"KEY={AWS_KEY}", "a.py": f'token = "{AWS_KEY}"', "requirements.txt": "numpy"},
        )
        evidence = [
            {
                "key": item.key,
                "kind": item.kind,
                "category": item.category,
                "description": item.description,
                "source_file": item.source_file,
                "structured_data": item.structured_data,
            }
            for item in normalize(self._results(tmp_path))
        ]
        context = build_model_context(evidence)
        assert AWS_KEY not in context
        assert "configuration" in context
        assert len(build_model_context(evidence, limit=500)) <= 500
