"""FastAPI app: SSE chat endpoint driving the LangGraph council, defaults API,
conversation history, and static serving of the built React frontend."""

import json
import time
import os
from pathlib import Path

from fastapi import FastAPI, Request, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import db
from .export import to_pdf, to_pptx
from .extract import extract_file, ExtractError
from .graph import MAX_CUSTOM_AGENTS, build_council_graph, build_stages, node_sequence
from .llm import ConfigError, build_llm, resolve_model, DEFAULT_AGENT_MODELS, HF_MODELS
from .prompts import CLAUDE_MODELS, DEFAULT_AGENTS, DEFAULT_MODEL, OPENAI_MODELS, PROMPTS_VERSION

app = FastAPI(title="Market Research Agent Council")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.on_event("startup")
async def startup():
    app.state.db_mode = await db.init_db()


def sse(obj: dict) -> str:
    return f"data: {json.dumps(obj)}\n\n"


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
    request: Request,
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

    # Read uploads before streaming starts (request body is only valid here)
    raw_files = []
    for f in files:
        data = await f.read()
        raw_files.append((f.filename or "file", data))

    async def stream():
        t_run = time.time()
        try:
            file_texts, file_images, file_names = [], [], []
            for name, data in raw_files:
                try:
                    ext = extract_file(name, data)
                except ExtractError as e:
                    yield sse({"type": "error", "message": str(e)})
                    return
                file_names.append(name)
                if ext["kind"] == "image":
                    file_images.append(ext["data_url"])
                else:
                    file_texts.append(ext)

            if not message.strip() and not raw_files:
                yield sse({"type": "error", "message": "Type a message or attach a file."})
                return

            agents = {**DEFAULT_AGENTS}
            for key, val in (cfg.get("agents") or {}).items():
                if key in agents and isinstance(val, dict):
                    agents[key] = {**agents[key], **{k: v for k, v in val.items() if k in ("name", "system_prompt", "model")}}
            settings = cfg.get("settings") or {}
            stages = build_stages({**cfg, "agents": agents})
            seq = node_sequence(stages)

            cid = await db.ensure_conversation(session_id, conversation_id or None, message.strip() or (file_names and file_names[0]) or "New research")
            history = await db.get_history(cid)
            user_record = message.strip()
            if file_names:
                user_record += f"\n[attached: {', '.join(file_names)}]"
            await db.add_message(cid, "user", user_record)

            def node_display(n):
                if n.get("stage"):
                    name = n["stage"]["name"]
                else:
                    name = agents[n["agent_key"]]["name"]
                mk, mm = n["model_agent"]
                if mk == "analyst":
                    mm = agents["analyst"].get("model")
                elif mk == "intake":
                    mm = agents["intake"].get("model")
                return name, resolve_model(settings, mk, mm)

            plan_nodes = []
            by_node = {}
            for n in seq:
                name, model = node_display(n)
                info = {"node": n["node"], "agent": name, "label": n["label"], "model": model}
                plan_nodes.append(info)
                by_node[n["node"]] = info
            yield sse({"type": "plan", "conversation_id": cid, "nodes": plan_nodes})

            graph = build_council_graph(stages)
            state = {
                "user_input": message.strip() or f"(user sent file(s): {', '.join(file_names)})",
                "history": history,
                "file_texts": file_texts,
                "file_images": file_images,
                "agents": agents,
                "settings": settings,
            }

            trace = [{"node": "user", "agent": "You", "label": "User input",
                      "output": user_record, "elapsed": 0}]
            final_text = ""
            t_node = time.time()
            async for update in graph.astream(state, stream_mode="updates"):
                for node, delta in update.items():
                    if node not in by_node:
                        continue
                    if await request.is_disconnected():
                        return
                    out = (delta or {}).get("last_output", "")
                    elapsed = round(time.time() - t_node, 1)
                    t_node = time.time()
                    if (delta or {}).get("analysis"):
                        final_text = delta["analysis"]
                    step = {**by_node[node], "output": out, "elapsed": elapsed}
                    trace.append(step)
                    yield sse({"type": "node_complete", **step})

            await db.add_message(cid, "assistant", final_text, {"steps": trace})
            yield sse({"type": "final", "conversation_id": cid, "output": final_text,
                       "trace": trace, "total_elapsed": round(time.time() - t_run, 1)})
        except ConfigError as e:
            yield sse({"type": "error", "message": str(e)})
        except Exception as e:  # noqa: BLE001
            msg = str(e)
            if "authentication" in msg.lower() or "api key" in msg.lower() or "401" in msg:
                msg = "The API key was rejected by the provider. Check the key in Settings."
            yield sse({"type": "error", "message": f"Run failed at the model call: {msg[:500]}"})

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


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
