"""Detached run engine: a council run executes in a background asyncio task
that outlives the HTTP request. Every SSE event is appended to an in-memory
registry and persisted incrementally to Postgres (mra_runs), so viewers can
attach/re-attach by conversation id and replay from any cursor. Client
disconnect no longer aborts a run — Stop is an explicit endpoint."""

import asyncio
import json
import time
import uuid

from . import db
from .extract import ExtractError, extract_file
from .graph import build_council_graph, build_stages, node_sequence
from .lenses import ROUTER_MODEL
from .llm import ConfigError, resolve_model
from .prompts import DEFAULT_AGENTS

RUNS: dict[str, "Run"] = {}  # conversation_id -> latest run
_MAX_KEPT = 60


class Run:
    def __init__(self, conversation_id: str, session_id: str):
        self.id = str(uuid.uuid4())
        self.conversation_id = conversation_id
        self.session_id = session_id
        self.status = "running"  # running | done | error | stopped
        self.events: list[dict] = []
        self.task: asyncio.Task | None = None
        self.cleanup_task: asyncio.Task | None = None
        self._waiters: list[asyncio.Future] = []

    # Single event loop: append+notify runs without an await between check and
    # register in tail(), so no lock is needed.
    def _notify(self):
        for f in self._waiters:
            if not f.done():
                f.set_result(None)
        self._waiters.clear()

    async def wait_change(self, timeout: float) -> bool:
        f = asyncio.get_running_loop().create_future()
        self._waiters.append(f)
        try:
            await asyncio.wait_for(f, timeout)
            return True
        except asyncio.TimeoutError:
            return False
        finally:
            if f in self._waiters:
                self._waiters.remove(f)

    async def emit(self, ev: dict):
        self.events.append(ev)
        self._notify()
        await db.save_run(self)

    async def finish(self, status: str, ev: dict):
        """Terminal status is set BEFORE the closing event so tails drain and exit."""
        self.status = status
        await self.emit(ev)


def register(conversation_id: str, session_id: str) -> Run:
    if len(RUNS) > _MAX_KEPT:
        stale = [c for c, r in RUNS.items() if r.status != "running"]
        for cid in stale[: len(RUNS) - _MAX_KEPT]:
            RUNS.pop(cid, None)
    run = Run(conversation_id, session_id)
    RUNS[conversation_id] = run
    return run


def get(conversation_id: str) -> Run | None:
    return RUNS.get(conversation_id)


def active_for(session_id: str) -> list[dict]:
    return [{"conversation_id": r.conversation_id, "run_id": r.id}
            for r in RUNS.values() if r.status == "running" and r.session_id == session_id]


def sse(obj: dict) -> str:
    return f"data: {json.dumps(obj)}\n\n"


async def tail(run: Run, after: int = 0):
    """Yield SSE frames from cursor `after`, live-tailing until the run is
    terminal. Heartbeat comments every 15s keep proxies from idling out."""
    i = after
    while True:
        if i < len(run.events):
            batch = run.events[i:]
            i = len(run.events)
            for e in batch:
                yield sse(e)
            continue
        if run.status != "running":
            return
        if not await run.wait_change(15.0):
            yield ": ping\n\n"


async def _finish_stopped(run: Run, trace: list[dict], t_run: float):
    steps = [s for s in trace if s.get("node") != "user"]
    partial = (
        "⏹ Stopped by you after: " + " → ".join(f"{s['agent']} ({s['label']})" for s in steps)
        + ". The last completed step is in the Observability tab."
        if steps else "⏹ Stopped by you before any agent finished."
    )
    try:
        await db.add_message(run.conversation_id, "assistant", partial, {"steps": trace} if steps else None)
    except Exception:  # noqa: BLE001
        pass
    await run.finish("stopped", {"type": "stopped", "conversation_id": run.conversation_id,
                                 "message": partial, "trace": steps,
                                 "total_elapsed": round(time.time() - t_run, 1)})


async def execute_run(run: Run, *, message: str, raw_files: list, cfg: dict):
    t_run = time.time()
    cid = run.conversation_id
    trace: list[dict] = []
    try:
        file_texts, file_images, file_names = [], [], []
        for name, data in raw_files:
            try:
                ext = extract_file(name, data)
            except ExtractError as e:
                await run.finish("error", {"type": "error", "message": str(e)})
                return
            file_names.append(name)
            if ext["kind"] == "image":
                file_images.append(ext["data_url"])
            else:
                file_texts.append(ext)

        agents = {**DEFAULT_AGENTS}
        for key, val in (cfg.get("agents") or {}).items():
            if key in agents and isinstance(val, dict):
                agents[key] = {**agents[key], **{k: v for k, v in val.items() if k in ("name", "system_prompt", "model", "expert_mode")}}
        settings = cfg.get("settings") or {}
        stages = build_stages({**cfg, "agents": agents})
        seq = node_sequence(stages)

        history = await db.get_history(cid)
        user_record = message
        if file_names:
            user_record += f"\n[attached: {', '.join(file_names)}]"
        await db.add_message(cid, "user", user_record)

        def node_display(n):
            if n["agent_key"] == "router":
                return "Router", ROUTER_MODEL
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
        await run.emit({"type": "plan", "conversation_id": cid, "nodes": plan_nodes})

        graph = build_council_graph(stages)
        state = {
            "user_input": message or f"(user sent file(s): {', '.join(file_names)})",
            "history": history,
            "file_texts": file_texts,
            "file_images": file_images,
            "agents": agents,
            "settings": settings,
        }

        trace.append({"node": "user", "agent": "You", "label": "User input",
                      "output": user_record, "elapsed": 0})
        final_text = ""
        t_node = time.time()
        async for update in graph.astream(state, stream_mode="updates"):
            for node, delta in update.items():
                if node not in by_node:
                    continue
                out = (delta or {}).get("last_output", "")
                elapsed = round(time.time() - t_node, 1)
                t_node = time.time()
                if (delta or {}).get("analysis"):
                    final_text = delta["analysis"]
                step = {**by_node[node], "output": out, "elapsed": elapsed}
                trace.append(step)
                await run.emit({"type": "node_complete", **step})

        await db.add_message(cid, "assistant", final_text, {"steps": trace})
        await run.finish("done", {"type": "final", "conversation_id": cid, "output": final_text,
                                  "trace": trace, "total_elapsed": round(time.time() - t_run, 1)})
    except asyncio.CancelledError:
        # Stop requested: persist the partial from a fresh task (this one is
        # dying). Ref kept on the run so GC can't collect the cleanup mid-flight.
        run.cleanup_task = asyncio.create_task(_finish_stopped(run, trace, t_run))
        raise
    except ConfigError as e:
        await run.finish("error", {"type": "error", "message": str(e)})
    except Exception as e:  # noqa: BLE001
        msg = str(e)
        if "authentication" in msg.lower() or "api key" in msg.lower() or "401" in msg:
            msg = "The API key was rejected by the provider. Check the key in Settings."
        await run.finish("error", {"type": "error", "message": f"Run failed at the model call: {msg[:500]}"})
