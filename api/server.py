import threading
import sys
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
from config import OUTPUT_DIR
from pipeline import run_pipeline
from shared_context import SharedContext


app = Flask(__name__)
CORS(app)

current_context: SharedContext | None = None
pipeline_thread: threading.Thread | None = None


def _run_pipeline_background(description: str) -> None:
    global current_context
    current_context = run_pipeline(description)


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
        args=(description,),
        daemon=True,
    )
    pipeline_thread.start()
    return jsonify({"status": "started"}), 202


@app.get("/api/status")
def status_endpoint() -> Any:
    if current_context is None:
        return jsonify(
            SharedContext(user_input="").to_json()
            | {"pipeline_status": {f"agent_{agent_num}": "idle" for agent_num in range(1, 5)}}
        )
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
    app.run(host="0.0.0.0", port=8000, debug=True)
