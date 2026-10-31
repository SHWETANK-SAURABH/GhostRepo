import json
import time
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.services.findings_engine import DraftFinding, build_findings, health_score
from tests.helpers import init_git, make_repo

AWS_KEY = "AKIA" + "IOSFODNN7EXAMPLE"

FILES = {
    "main.py": 'import os\nKEY = "' + AWS_KEY + '"\nos.environ["DB_URL"]\n',
    "requirements.txt": "flask==2.0\nnumpy\n",
    "tests/test_main.py": "raise SystemExit('this must never run')\n",
    "README.md": "# Demo\n\nShort.\n",
}


def wait_until(client: TestClient, investigation_id: str, predicate, timeout: float = 30) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        body = client.get(f"/api/investigations/{investigation_id}").json()
        if predicate(body):
            return body
        time.sleep(0.05)
    raise AssertionError(f"Timed out; last state: {body}")


def finished(body: dict) -> bool:
    return body["status"] in {"completed", "failed", "interrupted"}


def investigate(client: TestClient, path: str = "demo") -> dict:
    response = client.post("/api/investigations", json={"path": path})
    assert response.status_code == 202, response.text
    return wait_until(client, response.json()["id"], finished)


@pytest.fixture
def demo_repo(workspace: Path) -> Path:
    repo = make_repo(workspace / "demo", FILES)
    init_git(repo)
    return repo


def ollama_handler(content: str, model: str = "gemma3:4b"):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/version":
            return httpx.Response(200, json={"version": "test"})
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": model}]})
        return httpx.Response(200, json={"message": {"content": content}})

    return handler


def ai_reply(key: str, invented: bool = False) -> str:
    return json.dumps(
        {
            "summary": "Needs documentation work.",
            "health_assessment": "Based on the evidence, hygiene is mixed.",
            "findings": [
                {
                    "title": "Setup is unclear",
                    "description": "The README has no setup steps.",
                    "severity": "medium",
                    "category": "documentation",
                    "evidence_ids": [key],
                    "recommendation": "Document setup.",
                    "confidence": 0.8,
                    "is_hypothesis": True,
                },
                {
                    "title": "Invented",
                    "description": "Cites evidence that does not exist.",
                    "severity": "high",
                    "category": "maintenance",
                    "evidence_ids": ["ev-fake-999"] if invented else [key],
                    "recommendation": "Nothing.",
                    "confidence": 0.9,
                    "is_hypothesis": False,
                },
            ],
            "recovery_plan": [
                {
                    "title": "Write setup docs",
                    "description": "Add install steps.",
                    "priority": "high",
                    "related_evidence_ids": [key],
                }
            ],
        }
    )


class TestLifecycle:
    def test_full_deterministic_run_without_ollama(
        self, client: TestClient, demo_repo: Path
    ) -> None:
        body = investigate(client)
        assert body["status"] == "completed"
        assert body["ai_status"] == "unavailable"
        assert body["verified_finding_count"] > 0
        assert body["ai_finding_count"] == 0
        assert all(stage["status"] != "running" for stage in body["stages"])
        assert body["repository"]["relative_path"] == "demo"
        assert "Python" in body["repository"]["detected_languages"]
        assert "Flask" in body["repository"]["detected_frameworks"]

        ai_stage = next(stage for stage in body["stages"] if stage["key"] == "ai")
        assert ai_stage["status"] == "failed"
        assert "not reachable" in ai_stage["message"]

    def test_tests_in_repository_are_not_executed(
        self, client: TestClient, demo_repo: Path
    ) -> None:
        marker = demo_repo / "executed"
        (demo_repo / "tests/test_main.py").write_text(f"open(r'{marker}', 'w')\n")
        (demo_repo / "conftest.py").write_text(f"open(r'{marker}', 'w')\n")
        (demo_repo / "setup.py").write_text(f"open(r'{marker}', 'w')\n")
        investigate(client)
        assert not marker.exists()

    def test_report_contains_evidence_and_never_the_secret(
        self, client: TestClient, demo_repo: Path, workspace: Path
    ) -> None:
        body = investigate(client)
        response = client.get(f"/api/investigations/{body['id']}/report")
        report = response.json()

        assert AWS_KEY not in response.text
        assert str(workspace) not in response.text
        assert report["provenance"] == "deterministic"
        assert report["evidence"]
        assert report["profile"]["git"]["commit_count"] == 1
        assert report["profile"]["tests"]["executed"] is False

        keys = {item["key"] for item in report["evidence"]}
        for finding in report["verified_findings"]:
            assert finding["origin"] == "deterministic"
            assert finding["is_hypothesis"] is False
            assert finding["detection_method"]
            assert set(finding["evidence_references"]) <= keys
            assert finding["evidence_references"]
        titles = {finding["title"] for finding in report["verified_findings"]}
        assert "Credentials appear to be in the source" in titles

    def test_evidence_is_persisted_and_plan_is_prioritized(
        self, client: TestClient, demo_repo: Path
    ) -> None:
        body = investigate(client)
        report = client.get(f"/api/investigations/{body['id']}/report").json()
        priorities = [task["priority"] for task in report["recovery_tasks"]]
        rank = {"high": 0, "medium": 1, "low": 2}
        assert priorities == sorted(priorities, key=rank.get)
        first = report["recovery_tasks"][0]
        assert first["why_it_matters"]
        assert first["effort_estimate"]
        assert first["verification_steps"]

    def test_empty_repository(self, client: TestClient, workspace: Path) -> None:
        (workspace / "empty").mkdir()
        body = investigate(client, "empty")
        assert body["status"] == "completed"
        assert body["health_score"] is None

    def test_repository_without_git_or_manifest(self, client: TestClient, workspace: Path) -> None:
        make_repo(workspace / "plain", {"notes.txt": "hello"})
        body = investigate(client, "plain")
        assert body["status"] == "completed"
        report = client.get(f"/api/investigations/{body['id']}/report").json()
        assert report["profile"]["git"]["available"] is False

    def test_malformed_manifest_does_not_stop_the_investigation(
        self, client: TestClient, workspace: Path
    ) -> None:
        make_repo(workspace / "bad", {"package.json": "{oops", "pom.xml": "<a><b>"})
        body = investigate(client, "bad")
        assert body["status"] == "completed"
        report = client.get(f"/api/investigations/{body['id']}/report").json()
        assert "Dependency manifest is malformed" in {
            finding["title"] for finding in report["verified_findings"]
        }

    def test_analyzer_crash_is_reported_and_other_stages_continue(
        self, client: TestClient, demo_repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.analyzers import dependency_analyzer

        def explode(*_):
            raise RuntimeError("boom")

        monkeypatch.setattr(dependency_analyzer, "analyze", explode)
        body = investigate(client)
        assert body["status"] == "completed"
        assert "Dependency inspection" in body["error_message"]
        stage = next(s for s in body["stages"] if s["key"] == "dependencies")
        assert stage["status"] == "failed"
        assert "boom" not in json.dumps(body)

    def test_timeout_fails_with_a_clear_message(
        self, client: TestClient, demo_repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.analyzers import git_historian
        from app.analyzers.base import ScanTimeout

        def slow(*_):
            raise ScanTimeout("limit")

        monkeypatch.setattr(git_historian, "analyze", slow)
        body = investigate(client)
        assert body["status"] == "failed"
        assert "time limit" in body["error_message"]

    def test_interrupted_runs_are_marked_on_restart(self, settings: Settings) -> None:
        app = create_app(settings)
        with TestClient(app) as first:
            from app.database.models import Investigation, Repository

            with app.state.database.scope() as db:
                repository = Repository(name="r", local_path=str(settings.workspace_root / "r"))
                row = Investigation(repository=repository, status="running", stages=[])
                db.add(row)
                db.flush()
                investigation_id = row.id
            assert first.get(f"/api/investigations/{investigation_id}").status_code == 200
        with TestClient(create_app(settings)) as second:
            body = second.get(f"/api/investigations/{investigation_id}").json()
        assert body["status"] == "interrupted"
        assert "restarted" in body["error_message"]


class TestApiErrors:
    def test_rejects_paths_outside_workspace(self, client: TestClient) -> None:
        response = client.post("/api/investigations", json={"path": "../.."})
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "outside_workspace"

    def test_missing_repository_is_404(self, client: TestClient) -> None:
        assert client.post("/api/investigations", json={"path": "nope"}).status_code == 404

    def test_unknown_investigation_is_404(self, client: TestClient) -> None:
        for suffix in ["", "/progress", "/report", "/export"]:
            assert client.get(f"/api/investigations/unknown{suffix}").status_code == 404

    def test_invalid_export_format(self, client: TestClient, demo_repo: Path) -> None:
        body = investigate(client)
        response = client.get(f"/api/investigations/{body['id']}/export?format=exe")
        assert response.status_code == 422

    def test_sql_metacharacters_in_ids_are_harmless(self, client: TestClient) -> None:
        response = client.get("/api/investigations/x' OR '1'='1")
        assert response.status_code == 404


class TestProgressAndHistory:
    def test_progress_has_all_stages_in_order(self, client: TestClient, demo_repo: Path) -> None:
        body = investigate(client)
        progress = client.get(f"/api/investigations/{body['id']}/progress").json()
        assert [stage["key"] for stage in progress["stages"]] == [
            "discovery",
            "git",
            "dependencies",
            "configuration",
            "documentation",
            "tests",
            "ai",
            "report",
        ]
        assert progress["percent"] == 100

    def test_history_is_listed(self, client: TestClient, demo_repo: Path) -> None:
        investigate(client)
        investigate(client)
        body = client.get("/api/investigations").json()
        assert body["total"] == 2
        dashboard = client.get("/api/dashboard").json()
        assert dashboard["investigations"] == 2
        assert dashboard["verified_findings"] > 0
        assert dashboard["pending_recovery_tasks"] > 0
        assert dashboard["average_health_score"] is not None

    def test_recovery_task_status_updates(self, client: TestClient, demo_repo: Path) -> None:
        body = investigate(client)
        report = client.get(f"/api/investigations/{body['id']}/report").json()
        task = report["recovery_tasks"][0]
        url = f"/api/investigations/{body['id']}/recovery-tasks/{task['id']}"
        assert client.patch(url, json={"status": "done"}).json()["status"] == "done"
        assert client.patch(url, json={"status": "bogus"}).status_code == 422
        other = f"/api/investigations/other/recovery-tasks/{task['id']}"
        assert client.patch(other, json={"status": "done"}).status_code == 404


class TestAiIntegration:
    @pytest.fixture
    def ai_app(self, settings: Settings):
        app = create_app(settings)
        with TestClient(app) as test_client:
            yield app, test_client

    def _key(self, client: TestClient, investigation_id: str) -> str:
        report = client.get(f"/api/investigations/{investigation_id}/report").json()
        return report["evidence"][0]["key"]

    def test_valid_output_is_stored_and_invented_references_rejected(
        self, ai_app, demo_repo: Path
    ) -> None:
        app, client = ai_app
        first = investigate(client)
        key = self._key(client, first["id"])

        app.state.ollama_transport = httpx.MockTransport(
            ollama_handler(ai_reply(key, invented=True))
        )
        body = investigate(client)
        report = client.get(f"/api/investigations/{body['id']}/report").json()

        assert report["provenance"] == "deterministic_and_ai"
        assert report["ai"]["status"] == "completed"
        assert report["ai"]["summary"] == "Needs documentation work."
        assert [finding["title"] for finding in report["ai"]["findings"]] == ["Setup is unclear"]
        assert report["ai"]["findings"][0]["is_hypothesis"] is True
        assert report["ai"]["findings"][0]["detection_method"] == "local-ai:gemma3:4b"
        assert report["ai"]["rejected"][0]["title"] == "Invented"
        assert "Setup is unclear" not in {f["title"] for f in report["verified_findings"]}
        ai_tasks = [task for task in report["recovery_tasks"] if task["origin"] == "ai"]
        assert ai_tasks[0]["title"] == "Write setup docs"

    def test_retry_uses_stored_evidence_without_rescanning(
        self, ai_app, demo_repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        app, client = ai_app
        body = investigate(client)
        assert body["ai_status"] == "unavailable"
        before = client.get(f"/api/investigations/{body['id']}/report").json()

        from app.analyzers import repository_scout

        def must_not_run(*_):
            raise AssertionError("Deterministic analysis must not repeat")

        monkeypatch.setattr(repository_scout, "analyze", must_not_run)
        app.state.ollama_transport = httpx.MockTransport(
            ollama_handler(ai_reply(before["evidence"][0]["key"]))
        )
        response = client.post(f"/api/investigations/{body['id']}/reanalyze")
        assert response.status_code == 202
        done = wait_until(client, body["id"], lambda item: item["ai_status"] == "completed")
        after = client.get(f"/api/investigations/{body['id']}/report").json()
        assert done["ai_finding_count"] == 2
        assert after["verified_findings"] == before["verified_findings"]

    def test_retry_replaces_earlier_ai_results(self, ai_app, demo_repo: Path) -> None:
        app, client = ai_app
        body = investigate(client)
        key = self._key(client, body["id"])
        app.state.ollama_transport = httpx.MockTransport(ollama_handler(ai_reply(key)))
        for _ in range(2):
            client.post(f"/api/investigations/{body['id']}/reanalyze")
            wait_until(client, body["id"], lambda item: item["ai_status"] == "completed")
            time.sleep(0.05)
        report = client.get(f"/api/investigations/{body['id']}/report").json()
        assert len(report["ai"]["findings"]) == 2

    def test_invalid_model_output_keeps_deterministic_results(
        self, ai_app, demo_repo: Path
    ) -> None:
        app, client = ai_app
        app.state.ollama_transport = httpx.MockTransport(ollama_handler("definitely not json"))
        body = investigate(client)
        report = client.get(f"/api/investigations/{body['id']}/report").json()
        assert body["status"] == "completed"
        assert body["ai_status"] == "failed"
        assert report["provenance"] == "deterministic"
        assert report["ai"]["summary"] is None
        assert "could not be validated" in report["ai"]["error"]
        assert report["verified_findings"]

    def test_missing_model_is_reported(self, ai_app, demo_repo: Path) -> None:
        app, client = ai_app
        app.state.ollama_transport = httpx.MockTransport(ollama_handler("{}", model="other:1b"))
        body = investigate(client)
        assert body["ai_status"] == "unavailable"
        assert "ollama pull" in body["ai_error"]

    def test_disabled_ai_is_skipped_honestly(self, ai_app, demo_repo: Path) -> None:
        app, client = ai_app
        settings_body = {**client.get("/api/settings").json(), "ai_enabled": False}
        client.put("/api/settings", json=settings_body)
        body = investigate(client)
        assert body["ai_status"] == "disabled"
        stage = next(s for s in body["stages"] if s["key"] == "ai")
        assert stage["status"] == "skipped"

    def test_reanalyze_requires_a_finished_investigation(self, ai_app) -> None:
        _, client = ai_app
        assert client.post("/api/investigations/unknown/reanalyze").status_code == 404

    def test_secrets_are_not_sent_to_the_model(self, ai_app, demo_repo: Path) -> None:
        app, client = ai_app
        bodies = []
        base = ollama_handler("not json")

        def recording(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/chat":
                bodies.append(request.content.decode())
            return base(request)

        (demo_repo / ".env").write_text(f"KEY={AWS_KEY}\n")
        app.state.ollama_transport = httpx.MockTransport(recording)
        investigate(client)
        assert bodies
        assert all(AWS_KEY not in body for body in bodies)

    def test_source_code_is_not_sent_to_the_model(self, ai_app, demo_repo: Path) -> None:
        app, client = ai_app
        bodies = []
        base = ollama_handler("not json")

        def recording(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/chat":
                bodies.append(request.content.decode())
            return base(request)

        (demo_repo / "engine.py").write_text("PROPRIETARY_ALGORITHM_MARKER = 1\n")
        app.state.ollama_transport = httpx.MockTransport(recording)
        investigate(client)
        assert all("PROPRIETARY_ALGORITHM_MARKER" not in body for body in bodies)


class TestExport:
    def test_markdown_export(self, client: TestClient, demo_repo: Path, workspace: Path) -> None:
        body = investigate(client)
        response = client.get(f"/api/investigations/{body['id']}/export")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/markdown")
        assert "attachment" in response.headers["content-disposition"]
        assert "ghostrepo-demo-" in response.headers["content-disposition"]
        text = response.text
        assert "# GhostRepo report: demo" in text
        assert "Deterministic analyzers only" in text
        assert "not a measurement" in text
        assert AWS_KEY not in text
        assert str(workspace) not in text

    def test_json_export(self, client: TestClient, demo_repo: Path, workspace: Path) -> None:
        body = investigate(client)
        response = client.get(f"/api/investigations/{body['id']}/export?format=json")
        data = response.json()
        assert data["investigation"]["id"] == body["id"]
        assert AWS_KEY not in response.text
        assert str(workspace) not in response.text


class TestFindingsEngine:
    def test_fixture_credentials_rank_below_production_ones(self) -> None:
        def hit(key: str, path: str, in_fixture: bool) -> dict:
            return {
                "key": key,
                "kind": "configuration.secret_pattern",
                "description": "x",
                "source_file": path,
                "structured_data": {"rule": "aws-access-key", "in_test_or_example": in_fixture},
                "detection_method": "m",
            }

        found = build_findings([hit("a", "app.py", False), hit("b", "tests/t.py", True)])
        assert {f.title: f.severity for f in found} == {
            "Credentials appear to be in the source": "critical",
            "Possible credentials in test or example files": "low",
        }

    def test_committed_secret_is_critical_and_ignored_one_is_low(self) -> None:
        evidence = [
            {
                "key": "ev-cfg-001",
                "kind": "configuration.secret_file",
                "description": "x",
                "source_file": ".env",
                "structured_data": {"tracked": True},
                "detection_method": "m",
            },
            {
                "key": "ev-cfg-002",
                "kind": "configuration.secret_file",
                "description": "x",
                "source_file": "a.pem",
                "structured_data": {"tracked": False},
                "detection_method": "m",
            },
        ]
        severity = {f.source_file: f.severity for f in build_findings(evidence)}
        assert severity == {".env": "critical", "a.pem": "low"}

    def test_old_commits_are_never_called_abandoned(self) -> None:
        evidence = [
            {
                "key": "ev-git-001",
                "kind": "git.no_recent_commits",
                "description": "No commits in the last 2000 day(s).",
                "source_file": None,
                "structured_data": {},
                "detection_method": "m",
            }
        ]
        finding = build_findings(evidence)[0]
        assert finding.severity == "info"
        assert "abandon" not in f"{finding.title} {finding.recommendation}".lower()

    def test_health_score_floor_and_empty_case(self) -> None:
        finding = DraftFinding("r", "t", "d", "critical", "configuration", 1, "x", "m")
        assert health_score([finding] * 10, [{"kind": "x"}]) == 0
        assert health_score([], [{"kind": "x"}]) == 100
        assert health_score([], []) is None
        assert health_score([], [{"kind": "repository.empty"}]) is None
