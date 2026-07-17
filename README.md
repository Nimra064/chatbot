# Agentic AI Chatbot Demo

A minimal **FastAPI (backend) + Gradio (frontend)** chatbot demo.

- Works out of the box with a **rule-based bot**.
- Optionally uses **Google Gemini** if `GEMINI_API_KEY` is set.

## Project Structure

```
Copilot/
├── backend/
│   └── main.py          # FastAPI app  (/chat, /health)
├── frontend/
│   └── app.py           # Gradio ChatInterface
├── requirements.txt
├── .env.example
├── .gitignore
└── README.md
```

## Setup

```powershell
# From the Copilot folder
cd "C:\Users\RA_Nimra\Documents\Agentic AI Demo\Copilot"

# 1. Create & activate a virtual env
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 2. Install dependencies
pip install -r requirements.txt

# 3. (Optional) enable Gemini
Copy-Item .env.example .env
# edit .env and set GEMINI_API_KEY (get one at https://aistudio.google.com/app/apikey)
```

## Run

Open **two terminals** in the `Copilot` folder:

**Terminal 1 — backend (FastAPI):**
```powershell
uvicorn backend.main:app --reload --port 8000
```
API docs: http://127.0.0.1:8000/docs

**Terminal 2 — frontend (Gradio):**
```powershell
python frontend/app.py
```
UI: http://127.0.0.1:7860

## API

`POST /chat`
```json
{
  "message": "Hello",
  "history": [
    {"role": "user", "content": "hi"},
    {"role": "assistant", "content": "Hello!"}
  ]
}
```

Response:
```json
{
  "reply": "Hi there!",
  "model": "rule-based",
  "timestamp": "2026-07-17T12:00:00"
}
```


<!-- test: trigger auto-PR + Copilot review -->
