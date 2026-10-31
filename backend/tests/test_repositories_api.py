from pathlib import Path

from fastapi.testclient import TestClient

from tests.helpers import init_git, make_repo


def test_validate_accepts_workspace_repository(client: TestClient, workspace: Path) -> None:
    repo = make_repo(workspace / "demo", {"README.md": "# Demo", "package.json": "{}"})
    init_git(repo)
    body = client.post("/api/repositories/validate", json={"path": "demo"}).json()
    assert body["valid"] is True
    assert body["name"] == "demo"
    assert body["relative_path"] == "demo"
    assert body["is_git"] is True
    assert body["manifests"] == ["package.json"]
    assert body["has_readme"] is True


def test_validate_rejects_traversal_without_revealing_paths(
    client: TestClient, tmp_path: Path
) -> None:
    response = client.post("/api/repositories/validate", json={"path": "../.."})
    body = response.json()
    assert response.status_code == 200
    assert body["valid"] is False
    assert body["code"] == "outside_workspace"
    assert str(tmp_path) not in response.text


def test_validate_rejects_absolute_system_path(client: TestClient, tmp_path: Path) -> None:
    body = client.post("/api/repositories/validate", json={"path": str(tmp_path)}).json()
    assert body["valid"] is False


def test_validate_requires_path_field(client: TestClient) -> None:
    response = client.post("/api/repositories/validate", json={})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_candidates_lists_only_direct_child_directories(
    client: TestClient, workspace: Path
) -> None:
    make_repo(workspace / "one/nested", {"a.py": "x"})
    (workspace / "file.txt").write_text("x")
    (workspace / ".hidden").mkdir()
    body = client.get("/api/repositories/candidates").json()
    assert [item["name"] for item in body["candidates"]] == ["one"]
    assert body["workspace_available"] is True
