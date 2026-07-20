---
applyTo:
  - "backend/**/*.py"
---
# Backend (FastAPI) review rules

- All endpoints MUST declare `response_model=...` and use Pydantic v2 models
  (never raw dicts) for request/response bodies.
- Business logic MUST NOT live inside route handlers — extract into a helper
  function or a `services/` module once the file grows beyond one endpoint's worth of logic.
- Environment variables MUST be read once at module load (or via a settings
  object), never re-read inside a request handler.
- Any new endpoint MUST raise `HTTPException` with a proper 4xx status code
  on invalid input (do not return `{"error": ...}` dicts with HTTP 200).
- CORS: `allow_origins=["*"]` is acceptable ONLY for this demo. Flag it if
  the endpoint is changed to handle authenticated data.
- LLM calls (Gemini) MUST cap the input length before forwarding user text.
- Use `from google import genai` (google-genai SDK). Flag any import of
  `google.generativeai` (the legacy SDK).
- Default Gemini model MUST be an alias like `gemini-flash-latest`, not a
  pinned version string.
