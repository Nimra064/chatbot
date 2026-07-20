---
applyTo:
  - "frontend/**/*.py"
---
# Frontend (Gradio) review rules

- `chat_fn` MUST accept both the "messages" (list of dicts with role/content)
  and the legacy tuple history formats.
- NEVER call `demo.launch(share=True)` in committed code.
- The backend URL MUST come from `os.getenv("BACKEND_URL", ...)` — never
  hard-code `http://127.0.0.1:8000` inside the request call.
- HTTP calls to the backend MUST set an explicit `timeout=` on `requests.post`.
- Catch `requests.exceptions.ConnectionError` separately from generic
  `Exception` so the user sees a helpful "backend not running" message.
- NEVER use `print()` for logging — use the `logging` module.
