import threading
import sys
import json
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, request

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    from flask_cors import CORS
except ImportError:
    def CORS(app: Flask) -> Flask:
        return app

from api.routes import list_files, resolve_output_file
from config import LOG_FILE, OUTPUT_DIR
from pipeline import run_pipeline
from shared_context import SharedContext


app = Flask(__name__)
CORS(app)

current_context: SharedContext | None = None
pipeline_thread: threading.Thread | None = None


def _read_latest_pipeline_logs() -> list[str]:
    log_path = Path(LOG_FILE)
    if not log_path.is_file():
        return []

    lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    start = 0
    for index, line in enumerate(lines):
        if "Pipeline queued from API" in line or "Pipeline started" in line:
            start = index

    latest_run = lines[start:]
    for index in range(len(latest_run) - 1, -1, -1):
        if "Pipeline complete" in latest_run[index]:
            latest_run = latest_run[: index + 1]
            break
    return latest_run[-100:]


def _load_existing_output_context() -> SharedContext:
    output_dir = Path(OUTPUT_DIR)
    context = SharedContext(user_input="")
    context.logs = _read_latest_pipeline_logs()

    spec_path = output_dir / "spec.json"
    if spec_path.is_file():
        try:
            context.spec = json.loads(spec_path.read_text(encoding="utf-8"))
            context.user_input = str(context.spec.get("description", ""))
        except (OSError, json.JSONDecodeError):
            context.spec = {}

    architecture_path = output_dir / "architecture.md"
    if architecture_path.is_file():
        context.architecture = architecture_path.read_text(encoding="utf-8", errors="replace")

    app_dir = output_dir / "app"
    if app_dir.is_dir():
        context.generated_files = {
            str(path.relative_to(app_dir)).replace("\\", "/"): ""
            for path in app_dir.rglob("*")
            if path.is_file()
        }

    quality_report_path = output_dir / "tests" / "quality_report.md"
    if quality_report_path.is_file():
        context.quality_report = quality_report_path.read_text(encoding="utf-8", errors="replace")

    deploy_dir = output_dir / "deploy"
    if deploy_dir.is_dir():
        context.deploy_files = {
            str(path.relative_to(deploy_dir)).replace("\\", "/"): ""
            for path in deploy_dir.rglob("*")
            if path.is_file()
        }

    context.pipeline_status["agent_1"] = (
        "done" if context.spec and context.architecture else "idle"
    )
    context.pipeline_status["agent_2"] = (
        "done" if context.generated_files.get("app.py") else "idle"
    )
    context.pipeline_status["agent_3"] = (
        "done" if context.quality_report else "idle"
    )
    context.pipeline_status["agent_4"] = (
        "done" if context.deploy_files.get("Dockerfile") else "idle"
    )

    log_status: dict[int, str] = {}
    for line in context.logs:
        for agent_num in range(1, 5):
            if f"Agent {agent_num} started" in line:
                log_status[agent_num] = "working"
            if f"Agent {agent_num} done" in line:
                log_status[agent_num] = "done"
            if f"Agent {agent_num} failed" in line:
                log_status[agent_num] = "error"

    for agent_num, status in log_status.items():
        context.pipeline_status[f"agent_{agent_num}"] = status

    failed_agents = [agent_num for agent_num, status in log_status.items() if status == "error"]
    failed_agent = None
    if failed_agents:
        failed_agent = min(failed_agents)
        for agent_num in range(failed_agent + 1, 5):
            context.pipeline_status[f"agent_{agent_num}"] = "idle"

    if any(status == "working" for status in context.pipeline_status.values()):
        context.current_agent = next(
            agent_num
            for agent_num in range(1, 5)
            if context.pipeline_status[f"agent_{agent_num}"] == "working"
        )
    elif failed_agent is not None:
        context.current_agent = failed_agent
    else:
        context.current_agent = 0

    if any(status == "done" for status in context.pipeline_status.values()) and not context.logs:
        context.logs = ["Loaded existing pipeline output from disk."]

    return context


def _run_pipeline_background(context: SharedContext) -> None:
    global current_context
    current_context = context
    run_pipeline(context.user_input, context)


@app.post("/api/run")
def run_endpoint() -> tuple[Any, int]:
    global current_context, pipeline_thread
    payload = request.get_json(silent=True) or {}
    description = str(payload.get("description", "")).strip()
    if not description:
        return jsonify({"error": "description is required"}), 400

    current_context = SharedContext(user_input=description)
    current_context.log("Pipeline queued from API")
    pipeline_thread = threading.Thread(
        target=_run_pipeline_background,
        args=(current_context,),
        daemon=True,
    )
    pipeline_thread.start()
    return jsonify({"status": "started"}), 202


@app.get("/api/status")
def status_endpoint() -> Any:
    if current_context is None:
        return jsonify(_load_existing_output_context().to_json())
    return jsonify(current_context.to_json())


@app.get("/api/files")
def files_endpoint() -> Any:
    return jsonify({"files": list_files(OUTPUT_DIR)})


@app.get("/api/file")
def file_endpoint() -> tuple[Any, int] | Any:
    requested_path = request.args.get("path", "")
    if not requested_path:
        return jsonify({"error": "path is required"}), 400

    try:
        path = resolve_output_file(requested_path, OUTPUT_DIR)
    except PermissionError as exc:
        return jsonify({"error": str(exc)}), 403
    except FileNotFoundError as exc:
        return jsonify({"error": str(exc)}), 404

    return jsonify({"path": requested_path, "content": path.read_text(encoding="utf-8")})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=False, use_reloader=False)
