import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from config import LOG_FILE


def _default_pipeline_status() -> dict[str, str]:
    return {f"agent_{agent_num}": "idle" for agent_num in range(1, 5)}


@dataclass
class SharedContext:
    user_input: str
    spec: dict[str, Any] = field(default_factory=dict)
    architecture: str = ""
    generated_files: dict[str, str] = field(default_factory=dict)
    test_results: dict[str, Any] = field(default_factory=dict)
    quality_report: str = ""
    deploy_files: dict[str, str] = field(default_factory=dict)
    pipeline_status: dict[str, str] = field(default_factory=_default_pipeline_status)
    current_agent: int = 0
    logs: list[str] = field(default_factory=list)

    def log(self, message: str) -> None:
        timestamped = f"[{datetime.now().isoformat(timespec='seconds')}] {message}"
        self.logs.append(timestamped)

        log_path = Path(LOG_FILE)
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with log_path.open("a", encoding="utf-8") as log_file:
                log_file.write(timestamped + "\n")
        except OSError:
            self.logs.append(
                f"[{datetime.now().isoformat(timespec='seconds')}] Failed to write log file: {LOG_FILE}"
            )

    def to_json(self) -> dict[str, Any]:
        return {
            "user_input": self.user_input,
            "spec": self.spec,
            "architecture": self.architecture,
            "generated_files": sorted(self.generated_files.keys()),
            "test_results": self.test_results,
            "quality_report": self.quality_report,
            "deploy_files": sorted(self.deploy_files.keys()),
            "pipeline_status": dict(self.pipeline_status),
            "current_agent": self.current_agent,
            "logs": list(self.logs),
        }

    def to_json_string(self) -> str:
        return json.dumps(self.to_json(), indent=2)
