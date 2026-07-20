"""FastAPI backend for the AI Chatbot demo.

Exposes a simple /chat endpoint. Uses Google Gemini if GEMINI_API_KEY is set,
otherwise falls back to a lightweight rule-based bot so the demo
works out of the box.
"""

from __future__ import annotations

import os
import random
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# Load .env from the project root (parent of backend/)
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

app = FastAPI(
    title="Agentic AI Chatbot API",
    description="Simple chatbot backend for the Gradio demo.",
    version="1.0.0",
)

# Allow the Gradio frontend (running on a different port) to call this API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class Message(BaseModel):
    role: str = Field(..., description="'user' or 'assistant'")
    content: str


class ChatRequest(BaseModel):
    message: str = Field(..., description="Latest user message")
    history: list[Message] = Field(default_factory=list)


class ChatResponse(BaseModel):
    reply: str
    model: str
    timestamp: str


# ---------------------------------------------------------------------------
# Rule-based fallback bot
# ---------------------------------------------------------------------------

RULES = [
    (
        ("hi", "hello", "hey", "salam", "assalam"),
        [
            "Hello! How can I help you today?",
            "Hi there! What would you like to talk about?",
            "Hey! I'm your demo assistant. Ask me anything.",
        ],
    ),
    (("how are you", "how r u"), ["I'm just code, but I'm running smoothly! How about you?"]),
    (("your name", "who are you"), ["I'm the Agentic AI Demo Bot, powered by FastAPI + Gradio."]),
    (("time",), [f"Server time is {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"]),
    (("bye", "goodbye", "exit"), ["Goodbye! Have a great day.", "See you later!"]),
    (("thanks", "thank you"), ["You're welcome!", "Anytime!"]),
    (("help",), ["I can chat with you. Try asking about the time, my name, or just say hi!"]),
]


def rule_based_reply(message: str) -> str:
    msg = message.lower().strip()
    if not msg:
        return "Please type something so I can respond."
    for keywords, replies in RULES:
        if any(k in msg for k in keywords):
            return random.choice(replies)
    return (
        f'You said: "{message}". '
        "I'm a simple demo bot — set OPENAI_API_KEY to enable smarter replies."
    )


# ---------------------------------------------------------------------------
# Optional Gemini-powered reply
# ---------------------------------------------------------------------------


def gemini_reply(message: str, history: list[Message]) -> str | None:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return None
    try:
        from google import genai  # type: ignore
        from google.genai import types  # type: ignore

        client = genai.Client(api_key=api_key)

        # Gemini expects roles 'user' and 'model'.
        contents = []
        for m in history:
            role = "user" if m.role == "user" else "model"
            contents.append(types.Content(role=role, parts=[types.Part.from_text(text=m.content)]))
        contents.append(types.Content(role="user", parts=[types.Part.from_text(text=message)]))

        response = client.models.generate_content(
            model=os.getenv("GEMINI_MODEL", "gemini-flash-latest"),
            contents=contents,  # type: ignore[arg-type]
            config=types.GenerateContentConfig(
                system_instruction="You are a helpful assistant.",
                temperature=0.7,
            ),
        )
        return (response.text or "").strip()
    except Exception as exc:  # pragma: no cover - demo fallback
        return f"(Gemini error, falling back) {exc}"


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/")
def root():
    return {
        "app": "Agentic AI Chatbot API",
        "status": "ok",
        "endpoints": ["/health", "/chat"],
    }


@app.get("/health")
def health():
    return {"status": "healthy", "time": datetime.utcnow().isoformat()}


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    ai_reply = gemini_reply(req.message, req.history)
    if ai_reply:
        model_name = os.getenv("GEMINI_MODEL", "gemini-flash-latest")
        reply = ai_reply
    else:
        model_name = "rule-based"
        reply = rule_based_reply(req.message)

    return ChatResponse(
        reply=reply,
        model=model_name,
        timestamp=datetime.utcnow().isoformat(),
    )
