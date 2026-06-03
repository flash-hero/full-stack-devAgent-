import json
from pathlib import Path
from typing import Any

from config import ARCHITECT_MODEL, OLLAMA_BASE_URL, OUTPUT_DIR
from shared_context import SharedContext


SYSTEM_MESSAGE = """You are a senior software architect. When given a description of a web application,
you produce a complete, structured specification in valid JSON format only.
Output nothing except the JSON object. No markdown, no explanation, no backticks."""

HUMAN_MESSAGE = """Analyze this application request and produce a JSON specification:

REQUEST: {user_input}

The JSON must follow this exact schema:
{{
  "app_name": "string",
  "description": "string",
  "features": ["list of functional features"],
  "tech_stack": {{
    "frontend": "string (e.g. HTML/CSS/JS or React)",
    "backend": "string (e.g. Flask)",
    "database": "string (e.g. SQLite)"
  }},
  "routes": [
    {{ "method": "GET|POST", "path": "/path", "description": "what it does" }}
  ],
  "db_schema": [
    {{ "table": "table_name", "fields": ["field1:type", "field2:type"] }}
  ],
  "pages": ["list of HTML pages needed"],
  "dependencies": ["list of pip packages needed"]
}}"""


def _load_langchain() -> tuple[Any, Any, Any]:
    from langchain_core.output_parsers import StrOutputParser
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_ollama import ChatOllama

    return ChatOllama, ChatPromptTemplate, StrOutputParser


def _strip_json_fences(raw_output: str) -> str:
    text = raw_output.strip()
    if text.startswith("```"):
        lines = [line for line in text.splitlines() if not line.strip().startswith("```")]
        text = "\n".join(lines).strip()
    return text


def _write_text(path: Path, content: str, context: SharedContext) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    except OSError as exc:
        context.log(f"Failed to write {path}: {exc}")


def _build_llm() -> Any:
    ChatOllama, _, _ = _load_langchain()
    return ChatOllama(model=ARCHITECT_MODEL, base_url=OLLAMA_BASE_URL, temperature=0.1)


def _generate_spec(context: SharedContext, llm: Any) -> tuple[dict[str, Any], str]:
    _, ChatPromptTemplate, StrOutputParser = _load_langchain()
    parser = StrOutputParser()
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", SYSTEM_MESSAGE),
            ("human", HUMAN_MESSAGE),
        ]
    )
    chain = prompt | llm | parser

    user_input = context.user_input
    last_error: Exception | None = None
    for attempt in range(1, 4):
        try:
            context.log(f"Agent 1 generating JSON spec (attempt {attempt})")
            raw_output = chain.invoke({"user_input": user_input})
            cleaned = _strip_json_fences(raw_output)
            spec = json.loads(cleaned)
            return spec, cleaned
        except json.JSONDecodeError as exc:
            last_error = exc
            context.log(f"Agent 1 JSON parse failed on attempt {attempt}: {exc}")
            user_input = (
                f"{context.user_input}\n\nYour previous response was not valid JSON. "
                "Return only the JSON object."
            )
        except Exception as exc:
            last_error = exc
            context.log(f"Agent 1 LLM call failed on attempt {attempt}: {exc}")

    raise RuntimeError(f"Agent 1 failed to produce valid JSON: {last_error}")


def _generate_architecture(context: SharedContext, spec: dict[str, Any], llm: Any) -> str:
    _, ChatPromptTemplate, StrOutputParser = _load_langchain()
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "You are a senior software architect. Produce concise markdown describing folder structure and component responsibilities.",
            ),
            (
                "human",
                "Create architecture.md for this generated Flask application.\n\n"
                "User request: {user_input}\n\nSpecification:\n{spec}",
            ),
        ]
    )
    chain = prompt | llm | StrOutputParser()
    last_error: Exception | None = None

    for attempt in range(1, 4):
        try:
            context.log(f"Agent 1 generating architecture.md (attempt {attempt})")
            return chain.invoke(
                {
                    "user_input": context.user_input,
                    "spec": json.dumps(spec, indent=2),
                }
            ).strip()
        except Exception as exc:
            last_error = exc
            context.log(f"Agent 1 architecture generation failed on attempt {attempt}: {exc}")

    raise RuntimeError(f"Agent 1 failed to generate architecture.md: {last_error}")


def run(context: SharedContext) -> None:
    context.pipeline_status["agent_1"] = "working"
    try:
        context.log("Agent 1 started")
        llm = _build_llm()
        spec, spec_text = _generate_spec(context, llm)
        architecture = _generate_architecture(context, spec, llm)

        output_dir = Path(OUTPUT_DIR)
        _write_text(output_dir / "spec.json", json.dumps(spec, indent=2), context)
        _write_text(output_dir / "architecture.md", architecture + "\n", context)

        context.spec = spec
        context.architecture = architecture
        context.pipeline_status["agent_1"] = "done"
        context.log("Agent 1 done")
    except Exception as exc:
        context.pipeline_status["agent_1"] = "error"
        context.log(f"Agent 1 failed: {exc}")
        raise
