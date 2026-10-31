from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app.services.ollama_service import OllamaClient, model_matches


def test_health_reports_database_and_workspace(client: TestClient) -> None:
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"
    assert body["workspace_available"] is True


def test_dashboard_is_empty_without_investigations(client: TestClient) -> None:
    body = client.get("/api/dashboard").json()
    assert body["investigations"] == 0
    assert body["average_health_score"] is None
    assert body["recent"] == []


def test_ollama_status_is_honest_when_unreachable(client: TestClient) -> None:
    body = client.get("/api/ollama/status").json()
    assert body["reachable"] is False
    assert body["model_available"] is False


def test_unknown_route_uses_error_schema(client: TestClient) -> None:
    response = client.get("/api/nope")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "http_error"


def test_untrusted_host_header_is_rejected(client: TestClient) -> None:
    assert client.get("/api/health", headers={"host": "evil.example"}).status_code == 400


def test_cors_allows_only_configured_origins(client: TestClient) -> None:
    allowed = client.get("/api/health", headers={"origin": "http://localhost:3000"})
    denied = client.get("/api/health", headers={"origin": "http://evil.example"})
    assert allowed.headers.get("access-control-allow-origin") == "http://localhost:3000"
    assert "access-control-allow-origin" not in denied.headers


def test_cross_site_writes_are_rejected(client: TestClient, workspace: Path) -> None:
    # A page on another site can send this without a preflight.
    response = client.post("/api/repositories/demo", headers={"origin": "http://evil.example"})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden_origin"
    assert not (workspace / "haunted-demo").exists()


def test_same_origin_writes_and_cross_site_reads_are_unaffected(client: TestClient) -> None:
    origin = {"origin": "http://localhost:3000"}
    assert client.post("/api/repositories/demo", headers=origin).status_code == 201
    assert client.post("/api/repositories/demo").status_code == 201
    assert client.get("/api/health", headers={"origin": "http://evil.example"}).status_code == 200


def _settings_body(client: TestClient, **changes) -> dict:
    return {**client.get("/api/settings").json(), **changes}


def test_settings_round_trip(client: TestClient) -> None:
    body = _settings_body(client, ollama_model="qwen3:8b", ai_enabled=False)
    assert client.put("/api/settings", json=body).status_code == 200
    saved = client.get("/api/settings").json()
    assert saved["ollama_model"] == "qwen3:8b"
    assert saved["ai_enabled"] is False


@pytest.mark.parametrize(
    "endpoint",
    ["https://api.example.com", "ftp://localhost:11434", "http://user:pw@localhost:11434"],
)
def test_settings_refuse_non_local_ollama_endpoint(client: TestClient, endpoint: str) -> None:
    response = client.put("/api/settings", json=_settings_body(client, ollama_endpoint=endpoint))
    assert response.status_code == 422


def test_settings_refuse_broad_or_missing_workspace(client: TestClient, tmp_path: Path) -> None:
    for root in [str(Path(tmp_path.anchor)), str(Path.home()), str(tmp_path / "missing")]:
        response = client.put("/api/settings", json=_settings_body(client, workspace_root=root))
        assert response.status_code == 422, root


def test_settings_refuse_path_like_exclusions(client: TestClient) -> None:
    body = _settings_body(client, excluded_dirs=["../secrets"])
    assert client.put("/api/settings", json=body).status_code == 422


def test_model_name_matching_handles_implicit_latest() -> None:
    assert model_matches("qwen3", ["qwen3:latest"])
    assert model_matches("gemma3:4b", ["gemma3:4b"])
    assert not model_matches("qwen3:8b", ["qwen3:latest"])


def test_status_reports_missing_model_with_pull_hint() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/version":
            return httpx.Response(200, json={"version": "0.32.4"})
        return httpx.Response(200, json={"models": [{"name": "other:1b"}]})

    client = OllamaClient(
        endpoint="http://localhost:11434",
        model="qwen3:8b",
        transport=httpx.MockTransport(handler),
    )
    status = client.status()
    assert status.reachable is True
    assert status.model_available is False
    assert "ollama pull qwen3:8b" in status.message
