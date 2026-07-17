"""Gradio chat frontend that talks to the FastAPI backend."""

from __future__ import annotations

import os
# from typing import Any, Dict, List

import gradio as gr
import requests

BACKEND_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8000")


def chat_fn(message: str, history: List[Any]) -> str:
    """Send the user message + history to the FastAPI backend and return reply.

    Supports both Gradio history formats:
      - "messages":  [{"role": "user"|"assistant", "content": "..."}]
      - "tuples":    [(user_msg, bot_msg), ...]
    """
    api_history: List[Dict[str, str]] = []
    for item in history or []:
        if isinstance(item, dict):
            role = item.get("role")
            content = item.get("content") or ""
            if role in ("user", "assistant") and content:
                api_history.append({"role": role, "content": content})
        elif isinstance(item, (list, tuple)) and len(item) == 2:
            user_msg, bot_msg = item
            if user_msg:
                api_history.append({"role": "user", "content": str(user_msg)})
            if bot_msg:
                api_history.append({"role": "assistant", "content": str(bot_msg)})

    try:
        resp = requests.post(
            f"{BACKEND_URL}/chat",
            json={"message": message, "history": api_history},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("reply", "(no reply)")
    except requests.exceptions.ConnectionError:
        return (
            f"Cannot reach backend at {BACKEND_URL}. "
            "Start it with:  uvicorn backend.main:app --reload"
        )
    except Exception as exc:
        return f"Error: {exc}"


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
