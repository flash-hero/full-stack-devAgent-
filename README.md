# Multi-Agent Web App Development Pipeline

This project runs a local four-agent pipeline that turns a natural language web app request into a generated Flask application, tests, a quality report, and deployment artifacts.

## Agents

1. **Architect** uses `mistral:7b` through Ollama to write `output/spec.json` and `output/architecture.md`.
2. **Developer** uses `qwen2.5-coder:7b` to generate the Flask app one file at a time under `output/app/`.
3. **Tester** uses `qwen2.5-coder:7b` to generate pytest route tests, runs them, and writes `output/tests/quality_report.md`.
4. **Deployer** uses `mistral:7b` to create `output/deploy/Dockerfile` and `output/deploy/.github/workflows/deploy.yml`, then tries Docker verification if Docker is available.

## Requirements

- Python 3.11+
- Ollama running locally on `http://localhost:11434`
- Local models:
  - `mistral:7b`
  - `qwen2.5-coder:7b`
- Docker Desktop, optional for deploy verification

Install Python dependencies:

```bash
pip install -r requirements.txt
```

Start Ollama:

```bash
ollama serve
```

Pull the required models if needed:

```bash
ollama pull mistral:7b
ollama pull qwen2.5-coder:7b
```

## Run The Pipeline

```bash
python pipeline.py
```

Enter the app description when prompted. Generated artifacts are written to `output/`.

## Run The API

```bash
python api/server.py
```

The API runs on port `8000`.

Endpoints:

- `POST /api/run` with `{ "description": "..." }`
- `GET /api/status`
- `GET /api/files`
- `GET /api/file?path=output/app/app.py`

## Verify This Project

```bash
python -m pytest tests -q
```

These tests cover the shared context and status/file API behavior without requiring Ollama.
