import json
from pathlib import Path
from typing import Any

from config import DEVELOPER_MODEL, OLLAMA_BASE_URL, OUTPUT_DIR
from shared_context import SharedContext


FILE_DESCRIPTIONS = {
    "app.py": "Flask app with all routes from the spec, SQLite with SQLAlchemy, app factory support, and error handlers.",
    "models.py": "SQLAlchemy models derived from db_schema in the spec.",
    "requirements.txt": "All pip dependencies needed to run the generated Flask app and tests.",
    "templates/base.html": "Base HTML template with navigation, flash messages, content block, and static CSS link.",
    "static/style.css": "Clean responsive CSS for the generated HTML templates.",
}


def _load_langchain() -> tuple[Any, Any, Any]:
    from langchain_core.output_parsers import StrOutputParser
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_ollama import ChatOllama

    return ChatOllama, ChatPromptTemplate, StrOutputParser


def _build_llm() -> Any:
    ChatOllama, _, _ = _load_langchain()
    return ChatOllama(model=DEVELOPER_MODEL, base_url=OLLAMA_BASE_URL, temperature=0.1)


def _clean_file_content(content: str) -> str:
    text = content.strip()
    if text.startswith("```"):
        lines = [line for line in text.splitlines() if not line.strip().startswith("```")]
        text = "\n".join(lines).strip()
    return text + "\n"


def _page_to_template(page: str) -> str:
    normalized = page.strip().replace("\\", "/")
    if not normalized:
        normalized = "index.html"
    if normalized.startswith("templates/"):
        return normalized
    if not normalized.endswith(".html"):
        normalized = f"{normalized}.html"
    return f"templates/{normalized}"


def _required_files(spec: dict[str, Any]) -> list[tuple[str, str]]:
    files = [
        ("app.py", FILE_DESCRIPTIONS["app.py"]),
        ("models.py", FILE_DESCRIPTIONS["models.py"]),
        ("requirements.txt", FILE_DESCRIPTIONS["requirements.txt"]),
        ("templates/base.html", FILE_DESCRIPTIONS["templates/base.html"]),
    ]

    seen = {filename for filename, _ in files}
    for page in spec.get("pages", []):
        filename = _page_to_template(str(page))
        if filename not in seen:
            files.append((filename, f"HTML template for the {Path(filename).stem} page."))
            seen.add(filename)

    files.append(("static/style.css", FILE_DESCRIPTIONS["static/style.css"]))
    return files


def generate_file(
    filename: str,
    description: str,
    spec: dict[str, Any],
    existing_files: dict[str, str],
    llm: Any,
) -> str:
    _, ChatPromptTemplate, StrOutputParser = _load_langchain()
    prompt = ChatPromptTemplate.from_template(
        """You are a senior full-stack developer. Generate ONLY the complete file content for {filename}.
No explanation, no markdown fences, no comments outside the code.

App spec: {spec_summary}
File purpose: {description}
Already generated files: {existing_file_list}

Write the complete {filename} content now:"""
    )
    chain = prompt | llm | StrOutputParser()
    existing_file_list = "\n".join(sorted(existing_files.keys())) or "None"
    last_error: Exception | None = None

    for attempt in range(1, 4):
        try:
            output = chain.invoke(
                {
                    "filename": filename,
                    "description": description,
                    "spec_summary": json.dumps(spec, indent=2),
                    "existing_file_list": existing_file_list,
                }
            )
            return _clean_file_content(output)
        except Exception as exc:
            last_error = exc

    raise RuntimeError(f"Failed to generate {filename}: {last_error}")


def _write_generated_file(filename: str, content: str, context: SharedContext) -> None:
    path = Path(OUTPUT_DIR) / "app" / filename
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    except OSError as exc:
        context.log(f"Failed to write {path}: {exc}")


def run(context: SharedContext) -> None:
    context.pipeline_status["agent_2"] = "working"
    try:
        context.log("Agent 2 started")
        if not context.spec:
            raise ValueError("Agent 2 requires context.spec from Agent 1")

        llm = _build_llm()
        generated_files: dict[str, str] = {}
        for filename, description in _required_files(context.spec):
            context.log(f"Generating {filename}...")
            content = generate_file(filename, description, context.spec, generated_files, llm)
            _write_generated_file(filename, content, context)
            generated_files[filename] = content
            context.log(f"Generating {filename}... done")

        context.generated_files = generated_files
        context.pipeline_status["agent_2"] = "done"
        context.log("Agent 2 done")
    except Exception as exc:
        context.pipeline_status["agent_2"] = "error"
        context.log(f"Agent 2 failed: {exc}")
        raise
