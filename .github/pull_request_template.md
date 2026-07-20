## What changed
<!-- One or two sentences describing the change. -->

## Why
<!-- Motivation / linked issue. -->

## Checklist
- [ ] No secrets or API keys committed
- [ ] Backend still starts: `uvicorn backend.main:app --reload --port 8000`
- [ ] Frontend still starts: `python frontend/app.py`
- [ ] Manual smoke test: sent a message via Gradio and got a reply

---
> **Review flow:**
> 1. Layer 1 — Lint & static checks (ruff / mypy / bandit) run in Actions.
> 2. Layer 2 — GitHub Copilot code review posts inline comments using
>    `.github/copilot-instructions.md` + path-specific files in
>    `.github/instructions/`.
