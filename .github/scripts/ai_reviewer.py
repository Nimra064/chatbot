"""Agentic code reviewer using Google Gemini with tool-calling.

The agent is given the review policy (`.github/copilot-instructions.md`), the
diff of the current change, and a set of tools with which it can investigate
the repository *and* probe the running app. It then emits a structured JSON
verdict.

Outputs written to the workflow workspace:
    review.md            - human-readable report for the PR / commit comment
    review_blocking.txt  - "1" if the change should be blocked, "0" otherwise
    verdict.json         - the raw structured verdict from the agent
"""

from __future__ import annotations

import json
import logging
import os
import pathlib
import re
import subprocess
import sys
import textwrap
import traceback
from typing import Any, Callable

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("ai_reviewer")

REPO_ROOT = pathlib.Path.cwd().resolve()
MAX_TURNS = 12
MAX_TOOL_OUTPUT = 8000
BACKEND_URL = os.environ.get("BACKEND_URL", "http://127.0.0.1:8000")
FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://127.0.0.1:7860")


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

def _safe_path(rel: str) -> pathlib.Path | None:
    """Resolve rel inside REPO_ROOT. Return None if it escapes the repo."""
    try:
        candidate = (REPO_ROOT / rel).resolve()
        candidate.relative_to(REPO_ROOT)
    except (ValueError, OSError):
        return None
    return candidate


def tool_read_file(path: str, max_bytes: int = 20000) -> str:
    """Read a UTF-8 text file inside the repo."""
    p = _safe_path(path)
    if p is None or not p.is_file():
        return f"ERROR: not a file inside repo: {path}"
    data = p.read_bytes()[:max_bytes]
    return data.decode("utf-8", errors="replace")


def tool_list_dir(path: str = ".") -> str:
    """List directory entries inside the repo."""
    p = _safe_path(path)
    if p is None or not p.is_dir():
        return f"ERROR: not a directory inside repo: {path}"
    entries = []
    for child in sorted(p.iterdir()):
        entries.append(child.name + ("/" if child.is_dir() else ""))
    return "\n".join(entries) or "(empty)"


def tool_grep(pattern: str, path: str = ".") -> str:
    """Case-insensitive extended regex search across the repo."""
    p = _safe_path(path)
    if p is None:
        return f"ERROR: path escapes repo: {path}"
    try:
        out = subprocess.run(
            [
                "grep", "-rniE",
                "--exclude-dir=.git",
                "--exclude-dir=.venv",
                "--exclude-dir=node_modules",
                pattern, str(p),
            ],
            capture_output=True, text=True, timeout=15,
        )
    except subprocess.TimeoutExpired:
        return "ERROR: grep timed out"
    text = (out.stdout or "").strip()
    return text or "(no matches)"


def tool_call_endpoint(method: str, url: str, body: str = "") -> str:
    """Probe the running backend or frontend. Restricted to the local URLs."""
    method = (method or "").upper()
    if method not in ("GET", "POST"):
        return f"ERROR: method {method} not allowed"
    if not (url.startswith(BACKEND_URL) or url.startswith(FRONTEND_URL)):
        return f"ERROR: url must start with {BACKEND_URL} or {FRONTEND_URL}"
    resp_path = pathlib.Path("/tmp/agent_resp.txt")
    cmd = [
        "curl", "-sS",
        "-o", str(resp_path),
        "-w", "HTTP %{http_code}",
        "-X", method,
    ]
    if method == "POST":
        cmd += ["-H", "Content-Type: application/json", "--data", body or "{}"]
    cmd.append(url)
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
    except subprocess.TimeoutExpired:
        return "ERROR: curl timed out"
    status = (out.stdout or "").strip()
    body_text = resp_path.read_text(encoding="utf-8", errors="replace") if resp_path.exists() else ""
    return f"{status}\n---BODY (first 4KB)---\n{body_text[:4000]}"


TOOL_IMPL: dict[str, Callable[[dict[str, Any]], str]] = {
    "read_file":     lambda args: tool_read_file(str(args.get("path", ""))),
    "list_dir":      lambda args: tool_list_dir(str(args.get("path", "."))),
    "grep":          lambda args: tool_grep(str(args.get("pattern", "")), str(args.get("path", "."))),
    "call_endpoint": lambda args: tool_call_endpoint(
        str(args.get("method", "GET")),
        str(args.get("url", "")),
        str(args.get("body", "")),
    ),
}


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def write_outputs(review_md: str, blocking: bool, verdict: dict[str, Any]) -> None:
    """Write the three output files consumed by the workflow."""
    pathlib.Path("review.md").write_text(review_md, encoding="utf-8")
    pathlib.Path("review_blocking.txt").write_text("1" if blocking else "0")
    pathlib.Path("verdict.json").write_text(json.dumps(verdict, indent=2), encoding="utf-8")


def render_markdown(verdict: dict[str, Any], final_verdict: str) -> str:
    """Turn the verdict JSON into a compact Markdown report."""
    findings = verdict.get("findings") or []
    summary = (verdict.get("summary") or "").strip()

    lines: list[str] = [f"**Verdict:** `{final_verdict}`"]
    if summary:
        lines.extend(["", summary])

    buckets: dict[str, list[dict[str, Any]]] = {"security": [], "bug": [], "style": [], "nit": []}
    for f in findings:
        sev = str(f.get("severity", "nit")).lower()
        buckets.setdefault(sev, []).append(f)

    for sev in ("security", "bug", "style", "nit"):
        items = buckets.get(sev) or []
        if not items:
            continue
        lines.extend(["", f"### [{sev}]"])
        for f in items:
            loc = str(f.get("file", "?"))
            ln = f.get("line")
            if ln:
                loc = f"{loc}:{ln}"
            bullet = f"- **{loc}** — {f.get('message', '').strip()}"
            sug = (f.get("suggestion") or "").strip()
            if sug:
                bullet += f"\n  - _Fix:_ {sug}"
            lines.append(bullet)

    if not findings:
        lines.extend(["", "_No findings — LGTM._"])

    return "\n".join(lines)


def parse_verdict_json(text: str) -> dict[str, Any]:
    """Tolerant JSON parser: strip fences / prose, extract first object."""
    text = (text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if match:
        text = match.group(0)
    return json.loads(text)


# ---------------------------------------------------------------------------
# Agent loop
# ---------------------------------------------------------------------------

def build_tools(types_mod: Any) -> Any:
    """Declare the tool schema for the Gemini SDK."""
    return types_mod.Tool(function_declarations=[
        types_mod.FunctionDeclaration(
            name="read_file",
            description="Read a UTF-8 text file from the repository (max 20 KB).",
            parameters=types_mod.Schema(
                type=types_mod.Type.OBJECT,
                properties={"path": types_mod.Schema(type=types_mod.Type.STRING, description="Repo-relative file path")},
                required=["path"],
            ),
        ),
        types_mod.FunctionDeclaration(
            name="list_dir",
            description="List entries in a repository directory.",
            parameters=types_mod.Schema(
                type=types_mod.Type.OBJECT,
                properties={"path": types_mod.Schema(type=types_mod.Type.STRING, description="Repo-relative directory path")},
                required=["path"],
            ),
        ),
        types_mod.FunctionDeclaration(
            name="grep",
            description="Case-insensitive regex search across the repository.",
            parameters=types_mod.Schema(
                type=types_mod.Type.OBJECT,
                properties={
                    "pattern": types_mod.Schema(type=types_mod.Type.STRING, description="Extended regex to search for"),
                    "path":    types_mod.Schema(type=types_mod.Type.STRING, description="Repo-relative directory (default '.')"),
                },
                required=["pattern"],
            ),
        ),
        types_mod.FunctionDeclaration(
            name="call_endpoint",
            description=(
                f"Probe the running app. The url MUST start with "
                f"{BACKEND_URL} (backend) or {FRONTEND_URL} (frontend). "
                "Use to verify runtime behaviour of an endpoint the diff touched."
            ),
            parameters=types_mod.Schema(
                type=types_mod.Type.OBJECT,
                properties={
                    "method": types_mod.Schema(type=types_mod.Type.STRING, description="GET or POST"),
                    "url":    types_mod.Schema(type=types_mod.Type.STRING, description="Full URL to probe"),
                    "body":   types_mod.Schema(type=types_mod.Type.STRING, description="Optional JSON body for POST"),
                },
                required=["method", "url"],
            ),
        ),
    ])


def run_agent(api_key: str, model: str, rules: str, diff: str) -> dict[str, Any]:
    """Run the multi-turn tool-calling loop and return the parsed verdict."""
    from google import genai
    from google.genai import types

    tools = build_tools(types)

    system_instruction = textwrap.dedent(f"""
        You are an autonomous senior code reviewer for a FastAPI + Gradio + Gemini demo.
        You have tools to investigate the repository AND to probe the running
        app at {BACKEND_URL} (backend) and {FRONTEND_URL} (frontend). Use them
        whenever the diff alone is insufficient — e.g. read the full function
        around a changed line, grep for other call sites, or POST to /chat to
        confirm the runtime behaviour of an endpoint you just reviewed.

        Follow the REVIEW POLICY strictly. Only flag issues the policy tells
        you to flag. Do NOT flag [style] or [nit] as blocking.

        When you have enough information, respond with a SINGLE JSON object and
        NOTHING else — no code fences, no prose, no Markdown. Schema:

        {{
          "verdict": "block" | "allow",
          "summary": "one or two sentences",
          "findings": [
            {{
              "severity": "security" | "bug" | "style" | "nit",
              "file": "path/to/file",
              "line": 123,
              "message": "what is wrong",
              "suggestion": "what to change (optional)"
            }}
          ]
        }}

        Rules for verdict:
          * "block" if ANY finding has severity in ("security", "bug").
          * "allow" otherwise (style / nit only, or empty findings).
    """).strip()

    user_prompt = textwrap.dedent(f"""
        ===== REVIEW POLICY =====
        {rules}

        ===== DIFF =====
        {diff}

        Investigate as needed with the tools, then return the JSON verdict.
    """).strip()

    client = genai.Client(api_key=api_key)
    contents: list[Any] = [types.Content(role="user", parts=[types.Part.from_text(text=user_prompt)])]
    config = types.GenerateContentConfig(
        system_instruction=system_instruction,
        tools=[tools],
        temperature=0.2,
    )

    final_text = ""
    for turn in range(MAX_TURNS):
        resp = client.models.generate_content(model=model, contents=contents, config=config)
        candidate = (resp.candidates or [None])[0]
        if candidate is None or candidate.content is None:
            final_text = (resp.text or "").strip()
            break

        parts = candidate.content.parts or []
        fn_calls = [p.function_call for p in parts if getattr(p, "function_call", None)]

        if fn_calls:
            contents.append(candidate.content)
            for fc in fn_calls:
                name = fc.name
                args = dict(fc.args or {})
                impl = TOOL_IMPL.get(name)
                try:
                    result = impl(args) if impl else f"ERROR: unknown tool {name}"
                except Exception as exc:  # noqa: BLE001 - tool crashes must not kill the agent
                    result = f"ERROR: {exc}"
                snippet = result[:200].replace("\n", " ")
                logger.info("[turn %d] %s(%s) -> %s...", turn, name, args, snippet)
                contents.append(types.Content(
                    role="user",
                    parts=[types.Part.from_function_response(
                        name=name,
                        response={"result": result[:MAX_TOOL_OUTPUT]},
                    )],
                ))
            continue

        final_text = (resp.text or "").strip()
        break
    else:
        final_text = final_text or "(agent exceeded max turns without a final answer)"

    return parse_verdict_json(final_text)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    """Run the agent and write review outputs. Never raises."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        write_outputs(
            "> ❌ **Change blocked** — `GEMINI_API_KEY` secret is not set.\n"
            "> The agentic reviewer is mandatory. Add the secret at "
            "**Settings → Secrets and variables → Actions → New repository secret** "
            "and re-run this workflow.",
            blocking=True,
            verdict={"verdict": "block", "reason": "missing_api_key", "findings": []},
        )
        return 0

    diff_path = pathlib.Path("diff.patch")
    rules_path = pathlib.Path(".github/copilot-instructions.md")

    diff = diff_path.read_text(encoding="utf-8", errors="replace") if diff_path.exists() else ""
    rules = rules_path.read_text(encoding="utf-8") if rules_path.exists() else "(no policy file)"

    if not diff.strip():
        write_outputs(
            "_No diff to review._",
            blocking=False,
            verdict={"verdict": "allow", "findings": []},
        )
        return 0

    model = os.environ.get("GEMINI_MODEL", "gemini-flash-latest")

    try:
        verdict = run_agent(api_key, model, rules, diff)
    except Exception as exc:  # noqa: BLE001 - agent crash must not kill the workflow
        tb = traceback.format_exc()
        write_outputs(
            f"> ❌ **Agent crashed** — treating as block.\n\n"
            f"```\n{exc}\n```\n\n<details><summary>Traceback</summary>\n\n```\n{tb}\n```\n</details>",
            blocking=True,
            verdict={"verdict": "block", "error": str(exc)},
        )
        return 0

    findings = verdict.get("findings") or []
    has_blocking = any(str(f.get("severity", "")).lower() in ("security", "bug") for f in findings)
    final_verdict = "block" if has_blocking or verdict.get("verdict") == "block" else "allow"

    write_outputs(
        render_markdown(verdict, final_verdict),
        blocking=(final_verdict == "block"),
        verdict=verdict,
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        tb = traceback.format_exc()
        write_outputs(
            f"> ❌ **Reviewer script crashed**\n\n```\n{tb}\n```",
            blocking=True,
            verdict={"verdict": "block", "error": "reviewer crash"},
        )
        sys.exit(0)  # Gate step decides pass/fail from review_blocking.txt
