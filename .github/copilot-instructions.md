# Copilot Code Review Instructions

This repo is a small **FastAPI (backend) + Gradio (frontend)** chatbot that
optionally calls **Google Gemini** via the `google-genai` SDK. Use the
guidance below when reviewing pull requests.

## Project layout
- `backend/main.py` — FastAPI app exposing `/chat` and `/health`.
- `frontend/app.py` — Gradio ChatInterface that calls the FastAPI backend.
- `requirements.txt` — pinned minimum versions.
- `.env` — local secrets (never committed).

---

## Security — block the PR if any of these appear
- NEVER approve a PR that adds a hard-coded API key, token, or password.
  Keys MUST be loaded via `os.getenv(...)` from `.env`.
- Flag any commit that adds or modifies `.env`, `*.pem`, `*.key`, or `secrets.json`.
- Flag `eval(`, `exec(`, `pickle.load(`, `subprocess.*(shell=True)`, and SQL string concatenation.
- Flag `allow_origins=["*"]` on any route that handles authenticated data.
- Flag any LLM call that forwards `request.body` or user input without a length cap.

## Style
- All public functions MUST have type hints and a one-line docstring.
- PREFER `pathlib.Path` over `os.path`.
- NEVER use `print()` for logging — use the `logging` module.
- Files > 300 lines SHOULD be split.
- No unused imports or dead code.
- Match existing formatting; do not reformat unrelated code.

## FastAPI
- All request/response bodies MUST use Pydantic v2 models — not raw dicts.
- Endpoints MUST declare `response_model=...`.
- SHOULD raise `HTTPException` with a proper status code on error paths.

## Gradio
- `chat_fn` MUST accept both the "messages" (list of dicts) and legacy tuple history formats.
- NEVER call `demo.launch(share=True)` in committed code.

## Gemini
- Use `from google import genai` (google-genai SDK). Flag any import of `google.generativeai`.
- Default model MUST be an alias like `gemini-flash-latest`, not a pinned version.

## Tests
- Any change to `backend/main.py` SHOULD add or update a test under `tests/`.
- New endpoints MUST have at least one test hitting a happy path and one 4xx path.

---

## Review style
- Group related issues into a single comment; do not repeat the same fix on every occurrence.
- If a change is only formatting, approve without comments.
- Prefix each comment with one of: `[security]`, `[bug]`, `[style]`, `[nit]`.

## Do NOT comment on
- Line-length / whitespace inside unchanged code.
- Missing docstrings on trivial one-line helpers.
- The rule-based fallback bot in `backend/main.py` — that phrasing is intentional demo content.

---

## Test / run commands
- Backend: `uvicorn backend.main:app --reload --port 8000`
- Frontend: `python frontend/app.py`
- Install: `pip install -r requirements.txt`
