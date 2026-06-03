from pathlib import Path

from shared_context import SharedContext


def test_log_appends_timestamped_message_and_writes_file(tmp_path, monkeypatch):
    log_file = tmp_path / "logs" / "pipeline.log"
    monkeypatch.setattr("shared_context.LOG_FILE", str(log_file))

    context = SharedContext(user_input="Build a task tracker")
    context.log("Pipeline started")

    assert len(context.logs) == 1
    assert "Pipeline started" in context.logs[0]
    assert log_file.exists()
    assert "Pipeline started" in log_file.read_text(encoding="utf-8")


def test_to_json_returns_serializable_pipeline_state():
    context = SharedContext(user_input="Build a blog")
    context.spec = {"app_name": "Blog"}
    context.generated_files["app.py"] = "from flask import Flask"
    context.pipeline_status["agent_1"] = "done"
    context.current_agent = 2

    payload = context.to_json()

    assert payload["user_input"] == "Build a blog"
    assert payload["spec"] == {"app_name": "Blog"}
    assert payload["generated_files"] == ["app.py"]
    assert payload["pipeline_status"]["agent_1"] == "done"
    assert payload["current_agent"] == 2
