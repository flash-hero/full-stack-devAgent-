import ast
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from config import OUTPUT_DIR, TESTER_MODEL, OLLAMA_BASE_URL
from shared_context import SharedContext


def _load_langchain() -> tuple[Any, Any, Any]:
    from langchain_core.output_parsers import StrOutputParser
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_ollama import ChatOllama

    return ChatOllama, ChatPromptTemplate, StrOutputParser


def _build_llm() -> Any:
    ChatOllama, _, _ = _load_langchain()
    return ChatOllama(model=TESTER_MODEL, base_url=OLLAMA_BASE_URL, temperature=0.1)


def _clean_code(content: str) -> str:
    text = content.strip()
    if text.startswith("```"):
        lines = [line for line in text.splitlines() if not line.strip().startswith("```")]
        text = "\n".join(lines).strip()
    return text


def _extract_safe_test_functions(raw_output: str, route_index: int) -> list[str]:
    try:
        tree = ast.parse(_clean_code(raw_output))
    except SyntaxError:
        return []

    xfail_decorator = ast.parse(
        "@pytest.mark.xfail(reason='LLM-generated exploratory test', strict=False)\n"
        "def placeholder():\n"
        "    pass\n"
    ).body[0].decorator_list[0]

    functions: list[str] = []
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef):
            continue
        if not node.name.startswith("test_"):
            continue
        args = [arg.arg for arg in node.args.args]
        if args != ["client"]:
            continue

        node.name = f"llm_{route_index}_{node.name}"
        node.decorator_list = [xfail_decorator]
        functions.append(ast.unparse(ast.fix_missing_locations(node)))

    return functions


def _safe_test_slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", value.strip("/").lower()).strip("_")
    return slug or "root"


def _fallback_route_test(route: dict[str, Any], route_index: int) -> str:
    method = str(route.get("method", "GET")).upper()
    path = str(route.get("path", "/"))
    slug = _safe_test_slug(path)
    function_name = f"test_route_{route_index}_{method.lower()}_{slug}_smoke"
    if method == "POST":
        request_line = f"response = client.post({path!r}, data={{}})"
    else:
        request_line = f"response = client.open({path!r}, method={method!r})"

    return (
        f"def {function_name}(client):\n"
        f"    {request_line}\n"
        "    assert response.status_code < 500\n"
    )


def _route_code_snippet(route_path: str, app_code: str) -> str:
    if not app_code:
        return ""
    escaped = re.escape(route_path)
    pattern = rf"@app\.route\(['\"]{escaped}['\"].*?(?=\n@app\.route|\nif __name__|$)"
    match = re.search(pattern, app_code, re.DOTALL)
    return match.group(0) if match else app_code[:4000]


def _generate_route_tests(route: dict[str, Any], code_snippet: str, spec: dict[str, Any], llm: Any) -> str:
    _, ChatPromptTemplate, StrOutputParser = _load_langchain()
    prompt = ChatPromptTemplate.from_template(
        """You are a senior QA engineer. Given this Flask route code, write pytest test functions.
Use Flask's test client. Output only valid Python code, no markdown fences.

Route: {route_method} {route_path} - {route_description}
Relevant code: {code_snippet}
App spec context: {spec_summary}

Write pytest functions for this route now:"""
    )
    chain = prompt | llm | StrOutputParser()
    last_error: Exception | None = None

    for _ in range(3):
        try:
            return _clean_code(
                chain.invoke(
                    {
                        "route_method": route.get("method", "GET"),
                        "route_path": route.get("path", "/"),
                        "route_description": route.get("description", ""),
                        "code_snippet": code_snippet,
                        "spec_summary": json.dumps(spec, indent=2),
                    }
                )
            )
        except Exception as exc:
            last_error = exc

    raise RuntimeError(f"Failed to generate tests for {route.get('path')}: {last_error}")


def _parse_pytest_output(result: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    output = (result.stdout or "") + "\n" + (result.stderr or "")
    passed = 0
    failed = 0

    passed_match = re.search(r"(\d+)\s+passed", output)
    failed_match = re.search(r"(\d+)\s+failed", output)
    if passed_match:
        passed = int(passed_match.group(1))
    if failed_match:
        failed = int(failed_match.group(1))

    failures: list[str] = []
    failure_blocks = re.findall(r"FAILED\s+(.+)", output)
    failures.extend(block.strip() for block in failure_blocks)

    return {
        "passed": passed,
        "failed": failed,
        "returncode": result.returncode,
        "failures": failures,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def _generate_quality_report(context: SharedContext, test_results: dict[str, Any], llm: Any) -> str:
    _, ChatPromptTemplate, StrOutputParser = _load_langchain()
    prompt = ChatPromptTemplate.from_template(
        """You are a senior QA engineer. Write a concise markdown quality report.

Test results:
{test_results}

App spec:
{spec_summary}

app.py:
{app_py}

models.py:
{models_py}

Include:
- Test results with pass/fail counts
- Code quality observations
- Detected issues
- Suggested fixes for each issue"""
    )
    chain = prompt | llm | StrOutputParser()
    last_error: Exception | None = None

    for _ in range(3):
        try:
            return chain.invoke(
                {
                    "test_results": json.dumps(test_results, indent=2),
                    "spec_summary": json.dumps(context.spec, indent=2),
                    "app_py": context.generated_files.get("app.py", ""),
                    "models_py": context.generated_files.get("models.py", ""),
                }
            ).strip()
        except Exception as exc:
            last_error = exc

    raise RuntimeError(f"Failed to generate quality report: {last_error}")


def run(context: SharedContext) -> None:
    context.pipeline_status["agent_3"] = "working"
    try:
        context.log("Agent 3 started")
        llm = _build_llm()
        app_code = context.generated_files.get("app.py", "")
        test_chunks = [
            "import os",
            "import sys",
            "from pathlib import Path",
            "",
            "APP_DIR = Path(__file__).resolve().parents[1] / 'app'",
            "sys.path.insert(0, str(APP_DIR))",
            "",
            "from app import app",
            "try:",
            "    from app import db",
            "except ImportError:",
            "    db = None",
            "",
            "",
            "@pytest.fixture",
            "def client(tmp_path):",
            "    app.config.update(TESTING=True, SECRET_KEY='test-secret')",
            "    with app.app_context():",
            "        if db is not None:",
            "            db.create_all()",
            "        with app.test_client() as client:",
            "            yield client",
            "        if db is not None:",
            "            db.session.remove()",
            "            db.drop_all()",
            "",
        ]

        for route_index, route in enumerate(context.spec.get("routes", []), start=1):
            context.log(f"Generating tests for {route.get('method', 'GET')} {route.get('path', '/')}")
            snippet = _route_code_snippet(str(route.get("path", "/")), app_code)
            generated = _generate_route_tests(route, snippet, context.spec, llm)
            test_chunks.extend(_extract_safe_test_functions(generated, route_index))
            test_chunks.append(_fallback_route_test(route, route_index))
            test_chunks.append("")

        test_file = Path(OUTPUT_DIR) / "tests" / "test_routes.py"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        content = "import pytest\n" + "\n".join(test_chunks)
        test_file.write_text(content, encoding="utf-8")

        context.log("Running generated pytest suite")
        result = subprocess.run(
            [sys.executable, "-m", "pytest", str(Path(OUTPUT_DIR) / "tests"), "--tb=short", "-q"],
            capture_output=True,
            text=True,
            check=False,
        )
        test_results = _parse_pytest_output(result)
        quality_report = _generate_quality_report(context, test_results, llm)
        quality_path = Path(OUTPUT_DIR) / "tests" / "quality_report.md"
        quality_path.write_text(quality_report + "\n", encoding="utf-8")

        context.test_results = test_results
        context.quality_report = quality_report
        context.pipeline_status["agent_3"] = "done"
        context.log("Agent 3 done")
    except Exception as exc:
        context.pipeline_status["agent_3"] = "error"
        context.log(f"Agent 3 failed: {exc}")
        raise
