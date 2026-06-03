from pathlib import Path

import api.server as server
from shared_context import SharedContext


def test_status_returns_current_context(monkeypatch):
    context = SharedContext(user_input="Build a CRM")
    context.pipeline_status["agent_1"] = "working"
    monkeypatch.setattr(server, "current_context", context)

    client = server.app.test_client()
    response = client.get("/api/status")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["user_input"] == "Build a CRM"
    assert payload["pipeline_status"]["agent_1"] == "working"


def test_status_allows_frontend_cors_origin():
    client = server.app.test_client()

    response = client.get("/api/status", headers={"Origin": "http://127.0.0.1:5173"})

    assert response.status_code == 200
    assert response.headers["Access-Control-Allow-Origin"] in {
        "*",
        "http://127.0.0.1:5173",
    }


def test_files_lists_output_files(tmp_path, monkeypatch):
    output_dir = tmp_path / "output"
    nested = output_dir / "app"
    nested.mkdir(parents=True)
    file_path = nested / "app.py"
    file_path.write_text("print('hello')", encoding="utf-8")
    monkeypatch.setattr(server, "OUTPUT_DIR", str(output_dir))

    client = server.app.test_client()
    response = client.get("/api/files")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["files"] == [{"path": "output/app/app.py", "size": file_path.stat().st_size}]


def test_file_endpoint_rejects_path_traversal(tmp_path, monkeypatch):
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    monkeypatch.setattr(server, "OUTPUT_DIR", str(output_dir))

    client = server.app.test_client()
    response = client.get("/api/file?path=../secret.txt")

    assert response.status_code == 403


def test_file_endpoint_returns_generated_file(tmp_path, monkeypatch):
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    file_path = output_dir / "spec.json"
    file_path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(server, "OUTPUT_DIR", str(output_dir))

    client = server.app.test_client()
    response = client.get("/api/file?path=output/spec.json")

    assert response.status_code == 200
    assert response.get_json()["content"] == "{}"
