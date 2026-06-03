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


def test_background_pipeline_updates_visible_context(monkeypatch):
    context = SharedContext(user_input="Build a restaurant site")
    context.log = lambda message: context.logs.append(f"[test] {message}")

    def fake_run_pipeline(user_input, live_context):
        assert user_input == "Build a restaurant site"
        assert live_context is context
        live_context.pipeline_status["agent_1"] = "working"
        live_context.log("Agent 1 started")
        return live_context

    monkeypatch.setattr(server, "run_pipeline", fake_run_pipeline)

    server._run_pipeline_background(context)

    assert server.current_context is context
    assert context.pipeline_status["agent_1"] == "working"
    assert "Agent 1 started" in context.logs[-1]


def test_status_hydrates_latest_output_failure_from_disk(tmp_path, monkeypatch):
    output_dir = tmp_path / "output"
    (output_dir / "app").mkdir(parents=True)
    (output_dir / "tests").mkdir()
    (output_dir / "deploy").mkdir()
    (output_dir / "spec.json").write_text(
        '{"description": "A restaurant website"}',
        encoding="utf-8",
    )
    (output_dir / "architecture.md").write_text("Architecture", encoding="utf-8")
    (output_dir / "app" / "app.py").write_text("from flask import Flask", encoding="utf-8")
    (output_dir / "tests" / "quality_report.md").write_text("Report", encoding="utf-8")
    (output_dir / "deploy" / "Dockerfile").write_text("FROM python", encoding="utf-8")

    log_file = tmp_path / "logs" / "pipeline.log"
    log_file.parent.mkdir()
    log_file.write_text(
        "\n".join(
            [
                "[2026-06-03T17:28:47] Pipeline started",
                "[2026-06-03T17:32:36] Agent 1 done",
                "[2026-06-03T17:42:31] Agent 2 done",
                "[2026-06-03T17:48:55] Agent 3 failed: pytest missing",
                "[2026-06-03T17:48:55] Pipeline complete",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(server, "OUTPUT_DIR", str(output_dir))
    monkeypatch.setattr(server, "LOG_FILE", str(log_file))
    monkeypatch.setattr(server, "current_context", None)

    client = server.app.test_client()
    response = client.get("/api/status")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["pipeline_status"] == {
        "agent_1": "done",
        "agent_2": "done",
        "agent_3": "error",
        "agent_4": "idle",
    }
    assert payload["generated_files"] == ["app.py"]


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
