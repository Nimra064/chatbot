"""Gradio chat frontend that talks to the FastAPI backend."""

from __future__ import annotations

import logging
import os
from typing import Any

import gradio as gr
import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("chatbot.frontend")

BACKEND_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8000")
logger.info("Frontend will call backend at %s", BACKEND_URL)


def _content_to_text(content: Any) -> str:
    """Normalize Gradio's `content` field to a plain string.

    Gradio may send content as:
      - a plain string:   "Hello!"
      - a list of parts:  [{"type": "text", "text": "Hello!"}, ...]
      - a dict part:      {"type": "text", "text": "Hello!"}
    Anything else is coerced with str().
    """
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, dict):
                parts.append(str(part.get("text") or part.get("content") or ""))
            elif isinstance(part, str):
                parts.append(part)
            else:
                parts.append(str(part))
        return "".join(p for p in parts if p)
    if isinstance(content, dict):
        return str(content.get("text") or content.get("content") or "")
    return str(content)


def chat_fn(message: str, history: list[Any]) -> str:
    """Send the user message + history to the FastAPI backend and return reply.

    Supports both Gradio history formats:
      - "messages":  [{"role": "user"|"assistant", "content": "..."}]
      - "tuples":    [(user_msg, bot_msg), ...]
    """
    api_history: list[dict[str, str]] = []
    for item in history or []:
        if isinstance(item, dict):
            role = item.get("role")
            content = _content_to_text(item.get("content"))
            if role in ("user", "assistant") and content:
                api_history.append({"role": role, "content": content})
        elif isinstance(item, list | tuple) and len(item) == 2:
            user_msg, bot_msg = item
            if user_msg:
                api_history.append({"role": "user", "content": _content_to_text(user_msg)})
            if bot_msg:
                api_history.append({"role": "assistant", "content": _content_to_text(bot_msg)})

    try:
        resp = requests.post(
            f"{BACKEND_URL}/chat",
            json={"message": message, "history": api_history},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("reply", "(no reply)")
    except requests.exceptions.ConnectionError as exc:
        logger.error("Cannot reach backend at %s: %s", BACKEND_URL, exc)
        return (
            f"Cannot reach backend at {BACKEND_URL}. "
            "Start it with:  uvicorn backend.main:app --reload"
        )
    except requests.exceptions.Timeout as exc:
        logger.error("Backend request timed out after 30s: %s", exc)
        return "Backend timed out after 30 seconds. Try again or check backend logs."
    except requests.exceptions.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else "?"
        body = exc.response.text[:300] if exc.response is not None else ""
        logger.error("Backend returned HTTP %s: %s", status, body)
        return f"Backend returned HTTP {status}. Details: {body}"
    except ValueError as exc:  # invalid JSON in response
        logger.exception("Backend response was not valid JSON")
        return f"Backend returned invalid JSON: {exc}"
    except Exception as exc:
        logger.exception("Unexpected error calling backend (%s)", type(exc).__name__)
        return f"Unexpected error ({type(exc).__name__}): {exc}"


with gr.Blocks(title="Agentic AI Chatbot Demo", theme=gr.themes.Soft()) as demo:
    gr.Markdown(
        """
        # Agentic AI Chatbot Demo
        A simple **FastAPI + Gradio** demo.
        Type a message below to chat with the bot.
        """
    )

    gr.ChatInterface(
        fn=chat_fn,
        examples=[
            "Hello!",
            "What is your name?",
            "What time is it?",
            "Tell me a joke",
        ],
        cache_examples=False,
    )

    gr.Markdown(
        f"**Backend:** `{BACKEND_URL}`  -  "
        "Set `OPENAI_API_KEY` in the backend env for smarter replies."
    )


if __name__ == "__main__":
    demo.launch(server_name="127.0.0.1", server_port=7860)
