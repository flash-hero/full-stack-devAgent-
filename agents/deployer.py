import json
import time
from pathlib import Path
from typing import Any

from config import DEPLOYER_MODEL, OLLAMA_BASE_URL, OUTPUT_DIR
from shared_context import SharedContext


def _load_langchain() -> tuple[Any, Any, Any]:
    from langchain_core.output_parsers import StrOutputParser
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_ollama import ChatOllama

    return ChatOllama, ChatPromptTemplate, StrOutputParser


def _build_llm() -> Any:
    ChatOllama, _, _ = _load_langchain()
    return ChatOllama(model=DEPLOYER_MODEL, base_url=OLLAMA_BASE_URL, temperature=0.1)


def _clean_content(content: str) -> str:
    text = content.strip()
    if text.startswith("```"):
        lines = [line for line in text.splitlines() if not line.strip().startswith("```")]
        text = "\n".join(lines).strip()
    return text + "\n"


def _invoke_with_retries(chain: Any, payload: dict[str, Any], label: str) -> str:
    last_error: Exception | None = None
    for _ in range(3):
        try:
            return _clean_content(chain.invoke(payload))
        except Exception as exc:
            last_error = exc
    raise RuntimeError(f"Failed to generate {label}: {last_error}")


def _generate_dockerfile(context: SharedContext, llm: Any) -> str:
    _, ChatPromptTemplate, StrOutputParser = _load_langchain()
    prompt = ChatPromptTemplate.from_template(
        """You are a DevOps engineer. Generate a production-ready Dockerfile for this Flask application.
Output only the Dockerfile content, nothing else.

Tech stack: {tech_stack}
Dependencies file content: {requirements_txt}
Entry point: app.py
Port: 5000"""
    )
    chain = prompt | llm | StrOutputParser()
    return _invoke_with_retries(
        chain,
        {
            "tech_stack": json.dumps(context.spec.get("tech_stack", {}), indent=2),
            "requirements_txt": context.generated_files.get("requirements.txt", ""),
        },
        "Dockerfile",
    )


def _generate_workflow(context: SharedContext, llm: Any) -> str:
    _, ChatPromptTemplate, StrOutputParser = _load_langchain()
    prompt = ChatPromptTemplate.from_template(
        """Generate a GitHub Actions workflow file (.github/workflows/deploy.yml) that:
- Triggers on push to main
- Installs Python dependencies
- Runs pytest
- Builds Docker image
- Output only valid YAML, nothing else.

App name: {app_name}
Python version: 3.11"""
    )
    chain = prompt | llm | StrOutputParser()
    return _invoke_with_retries(
        chain,
        {"app_name": context.spec.get("app_name", "generated-flask-app")},
        "deploy.yml",
    )


def _verify_with_docker(context: SharedContext, app_name: str) -> None:
    try:
        import docker
        import requests
    except ImportError as exc:
        context.log(f"Docker verification skipped; missing dependency: {exc}")
        return

    client = None
    container = None
    tag = app_name.lower().replace(" ", "-").replace("_", "-")
    try:
        client = docker.from_env()
        context.log("Building Docker image")
        client.images.build(path=str(Path(OUTPUT_DIR) / "app"), tag=tag)
        context.log("Running Docker container")
        container = client.containers.run(tag, ports={"5000/tcp": 5000}, detach=True)
        time.sleep(3)
        response = requests.get("http://localhost:5000", timeout=10)
        if response.status_code == 200:
            context.log("Docker verification responded with HTTP 200")
        else:
            context.log(f"Docker verification returned HTTP {response.status_code}")
    except Exception as exc:
        context.log(f"Docker verification skipped or failed: {exc}")
    finally:
        if container is not None:
            try:
                container.stop()
            except Exception as exc:
                context.log(f"Failed to stop Docker container: {exc}")
        if client is not None:
            try:
                client.close()
            except Exception:
                pass


def run(context: SharedContext) -> None:
    context.pipeline_status["agent_4"] = "working"
    try:
        context.log("Agent 4 started")
        llm = _build_llm()
        dockerfile = _generate_dockerfile(context, llm)
        workflow = _generate_workflow(context, llm)

        deploy_dir = Path(OUTPUT_DIR) / "deploy"
        workflow_dir = deploy_dir / ".github" / "workflows"
        deploy_dir.mkdir(parents=True, exist_ok=True)
        workflow_dir.mkdir(parents=True, exist_ok=True)
        (deploy_dir / "Dockerfile").write_text(dockerfile, encoding="utf-8")
        (workflow_dir / "deploy.yml").write_text(workflow, encoding="utf-8")

        app_dockerfile = Path(OUTPUT_DIR) / "app" / "Dockerfile"
        app_dockerfile.write_text(dockerfile, encoding="utf-8")

        context.deploy_files = {
            "Dockerfile": dockerfile,
            ".github/workflows/deploy.yml": workflow,
        }
        _verify_with_docker(context, str(context.spec.get("app_name", "generated-flask-app")))
        context.pipeline_status["agent_4"] = "done"
        context.log("Agent 4 done")
    except Exception as exc:
        context.pipeline_status["agent_4"] = "error"
        context.log(f"Agent 4 failed: {exc}")
        raise
