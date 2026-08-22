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
from .extract import extract_file, ExtractError
from .graph import GRAPH, NODE_AGENT, NODE_LABEL, NODE_OUTPUT_KEY, plan_for
from .llm import ConfigError
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
        "models": {"claude": CLAUDE_MODELS, "openai": OPENAI_MODELS},
        "default_model": DEFAULT_MODEL,
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
                    agents[key] = {**agents[key], **{k: v for k, v in val.items() if k in ("name", "system_prompt")}}
            enable_reviewer = bool(cfg.get("enable_reviewer"))
            enable_client = bool(cfg.get("enable_client"))
            settings = cfg.get("settings") or {}

            cid = await db.ensure_conversation(session_id, conversation_id or None, message.strip() or (file_names and file_names[0]) or "New research")
            history = await db.get_history(cid)
            user_record = message.strip()
            if file_names:
                user_record += f"\n[attached: {', '.join(file_names)}]"
            await db.add_message(cid, "user", user_record)

            plan = plan_for(enable_reviewer, enable_client)
            yield sse({"type": "plan", "conversation_id": cid,
                       "nodes": [{"node": n, "agent": agents[NODE_AGENT[n]]["name"], "label": NODE_LABEL[n]} for n in plan]})

            state = {
                "user_input": message.strip() or f"(user sent file(s): {', '.join(file_names)})",
                "history": history,
                "file_texts": file_texts,
                "file_images": file_images,
                "agents": agents,
                "settings": settings,
                "enable_reviewer": enable_reviewer,
                "enable_client": enable_client,
            }

            trace = [{"node": "user", "agent": "You", "label": "User input",
                      "output": user_record, "elapsed": 0}]
            final_text = ""
            t_node = time.time()
            async for update in GRAPH.astream(state, stream_mode="updates"):
                for node, delta in update.items():
                    if node not in NODE_OUTPUT_KEY:
                        continue
                    if await request.is_disconnected():
                        return
                    out = (delta or {}).get(NODE_OUTPUT_KEY[node], "")
                    elapsed = round(time.time() - t_node, 1)
                    t_node = time.time()
                    if (delta or {}).get("final"):
                        final_text = delta["final"]
                    step = {"node": node, "agent": agents[NODE_AGENT[node]]["name"],
                            "label": NODE_LABEL[node], "output": out, "elapsed": elapsed}
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


# ---- static frontend (built React app) ----
DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if DIST.exists():
    app.mount("/", StaticFiles(directory=str(DIST), html=True), name="static")
else:
    @app.get("/")
    async def root():
        return JSONResponse({"status": "API up. Frontend not built — run `npm run build` in frontend/."})
