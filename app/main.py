"""FastAPI app: SSE chat endpoint driving the LangGraph council (as detached
background runs — see runs.py), defaults API, conversation history, run
re-attach/stop endpoints, and static serving of the built React frontend."""

import asyncio
import json
import os
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import db, runs
from .export import to_pdf, to_pptx
from .extract import extract_file, ExtractError
from .graph import MAX_CUSTOM_AGENTS
from .llm import ConfigError, build_llm, DEFAULT_AGENT_MODELS, HF_MODELS
from .prompts import CLAUDE_MODELS, DEFAULT_AGENTS, OPENAI_MODELS, PROMPTS_VERSION

app = FastAPI(title="Market Research Agent Council")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.on_event("startup")
async def startup():
    app.state.db_mode = await db.init_db()


def sse(obj: dict) -> str:
    return f"data: {json.dumps(obj)}\n\n"


SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


def error_stream(message: str) -> StreamingResponse:
    async def gen():
        yield sse({"type": "error", "message": message})
    return StreamingResponse(gen(), media_type="text/event-stream", headers=SSE_HEADERS)


@app.get("/api/defaults")
async def defaults():
    return {
        "agents": DEFAULT_AGENTS,
        "prompts_version": PROMPTS_VERSION,
        "models": {"claude": CLAUDE_MODELS, "openai": OPENAI_MODELS, "hf": HF_MODELS},
        "default_model": "auto",
        "agent_model_defaults": DEFAULT_AGENT_MODELS,
        "max_custom_agents": MAX_CUSTOM_AGENTS,
        "default_provider": "claude",
        "server_key_available": bool(os.environ.get("ANTHROPIC_API_KEY")),
        "db": getattr(app.state, "db_mode", "unknown"),
    }


@app.get("/api/conversations")
async def conversations(session_id: str):
    return await db.list_conversations(session_id)


@app.get("/api/conversations/{conversation_id}/messages")
async def conversation_messages(conversation_id: str):
    return await db.get_messages(conversation_id)


@app.post("/api/chat")
async def chat(
    message: str = Form(""),
    session_id: str = Form(...),
    conversation_id: str = Form(""),
    config: str = Form("{}"),
    files: list[UploadFile] = File(default=[]),
):
    try:
        cfg = json.loads(config or "{}")
    except json.JSONDecodeError:
        cfg = {}

    # Read uploads before the request body is gone (the run outlives the request)
    raw_files = []
    for f in files:
        data = await f.read()
        raw_files.append((f.filename or "file", data))

    if not message.strip() and not raw_files:
        return error_stream("Type a message or attach a file.")
    existing = runs.get(conversation_id) if conversation_id else None
    if existing and existing.status == "running":
        return error_stream("A run is already in progress in this thread. Stop it or wait for it to finish.")

    title_hint = message.strip() or (raw_files and raw_files[0][0]) or "New research"
    cid = await db.ensure_conversation(session_id, conversation_id or None, title_hint)
    run = runs.register(cid, session_id)
    # First event tells the client its real conversation id immediately
    # (needed to Stop or re-attach before the plan is ready).
    await run.emit({"type": "conversation", "conversation_id": cid, "run_id": run.id})
    run.task = asyncio.create_task(
        runs.execute_run(run, message=message.strip(), raw_files=raw_files, cfg=cfg))

    return StreamingResponse(runs.tail(run, 0), media_type="text/event-stream", headers=SSE_HEADERS)


@app.get("/api/runs/active")
async def active_runs(session_id: str):
    return runs.active_for(session_id)


@app.get("/api/runs/{conversation_id}/stream")
async def run_stream(conversation_id: str, after: int = 0):
    run = runs.get(conversation_id)
    if run:
        return StreamingResponse(runs.tail(run, after), media_type="text/event-stream", headers=SSE_HEADERS)
    stored = await db.get_run(conversation_id)
    if stored:
        async def replay():
            for ev in stored["events"][after:]:
                yield sse(ev)
        return StreamingResponse(replay(), media_type="text/event-stream", headers=SSE_HEADERS)
    return error_stream("No run found for this conversation.")


@app.post("/api/runs/{conversation_id}/stop")
async def stop_run(conversation_id: str):
    run = runs.get(conversation_id)
    if not run or run.status != "running" or not run.task:
        return {"ok": False, "status": run.status if run else "none"}
    run.task.cancel()
    return {"ok": True}


SYNTH_SYSTEM = """You are an expert prompt engineer for a multi-agent market-research review pipeline.
Your job: rewrite ONE agent's system prompt so the agent emulates a real person the user describes (their boss, client, a domain expert) — from the user's notes and any uploaded documents (reviews they wrote, emails, feedback threads).

Rules:
- Extract the person's priorities, evaluation style, tone, recurring pet peeves, favorite frameworks, and standards of evidence from the material. Quote-worthy phrases they actually use are gold — work them in.
- PRESERVE the pipeline mechanics of the current prompt: what the agent receives, whether it gives feedback vs rewrites, and any output-format contract. The agent must stay compatible with its slot in the pipeline.
- Keep it under 450 words, imperative voice, structured (role, focus areas, concrete instructions, output format).
- If the material is thin, still produce the best prompt you can from what's there plus the current prompt.
- Output ONLY the new system prompt text. No preamble, no commentary, no code fences."""


@app.post("/api/synthesize-prompt")
async def synthesize_prompt(
    agent_name: str = Form(""),
    agent_role: str = Form(""),
    current_prompt: str = Form(""),
    notes: str = Form(""),
    settings: str = Form("{}"),
    files: list[UploadFile] = File(default=[]),
):
    try:
        cfg_settings = json.loads(settings or "{}")
    except json.JSONDecodeError:
        cfg_settings = {}
    file_parts, image_urls = [], []
    for f in files:
        data = await f.read()
        try:
            ext = extract_file(f.filename or "file", data)
        except ExtractError as e:
            return JSONResponse({"error": str(e)}, status_code=400)
        if ext["kind"] == "image":
            image_urls.append(ext["data_url"])
        else:
            file_parts.append(f"--- {ext['name']} ---\n{ext['text']}")
    if not notes.strip() and not file_parts and not image_urls:
        return JSONResponse({"error": "Add some notes or upload a document first."}, status_code=400)

    text = (
        f"AGENT TO CONFIGURE: {agent_name} — {agent_role}\n\n"
        f"CURRENT SYSTEM PROMPT:\n{current_prompt}\n\n"
        f"USER'S NOTES ABOUT THE PERSON THIS AGENT SHOULD EMULATE:\n{notes.strip() or '(none — rely on documents)'}\n\n"
        f"UPLOADED MATERIAL:\n{chr(10).join(file_parts) or '(none)'}\n\n"
        "Write the new system prompt now."
    )
    content: list = [{"type": "text", "text": text}]
    for url in image_urls:
        content.append({"type": "image_url", "image_url": {"url": url}})
    try:
        llm = build_llm(cfg_settings, "analyst")
        from langchain_core.messages import HumanMessage, SystemMessage
        resp = await llm.ainvoke([SystemMessage(content=SYNTH_SYSTEM), HumanMessage(content=content)])
        out = resp.content if isinstance(resp.content, str) else "\n".join(
            b.get("text", "") for b in resp.content if isinstance(b, dict) and b.get("type") == "text")
        return {"prompt": out.strip()}
    except ConfigError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"error": f"Synthesis failed: {str(e)[:300]}"}, status_code=500)


@app.post("/api/export")
async def export_report(payload: dict):
    fmt = (payload.get("format") or "pdf").lower()
    title = (payload.get("title") or "Market research report").strip()[:160]
    markdown = payload.get("markdown") or ""
    diagrams = payload.get("diagrams") or []
    if not markdown.strip():
        return JSONResponse({"error": "Nothing to export."}, status_code=400)
    try:
        if fmt == "pptx":
            data = to_pptx(title, markdown, diagrams)
            media = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
            fname = "agent-council-report.pptx"
        else:
            data = to_pdf(title, markdown, diagrams)
            media = "application/pdf"
            fname = "agent-council-report.pdf"
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"error": f"Export failed: {e}"}, status_code=500)
    from fastapi.responses import Response
    return Response(content=data, media_type=media,
                    headers={"Content-Disposition": f'attachment; filename="{fname}"'})


# ---- static frontend (built React app) ----
DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if DIST.exists():
    app.mount("/", StaticFiles(directory=str(DIST), html=True), name="static")
else:
    @app.get("/")
    async def root():
        return JSONResponse({"status": "API up. Frontend not built — run `npm run build` in frontend/."})
