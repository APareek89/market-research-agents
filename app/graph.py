"""Dynamic LangGraph pipeline for the agent council.

Flow: intake -> analyst draft -> [ordered review stages] -> END
Each stage is a core agent (reviewer/client) or a user-defined custom agent.
Reviewer-mode stages are followed by an analyst revise pass; transformer-mode
stages replace the analysis with their own output. The graph is built per
request from the stage list, so users can insert/reorder agents freely.
"""

import asyncio
import re
from typing import Annotated, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langgraph.graph import END, START, StateGraph

from .lenses import prepare_lens_plans
from .llm import build_llm
from .prompts import EXPERT_AGENTS
from .tools import ANALYST_TOOLS

MAX_TOOL_ITERS = 6
MAX_TOOL_ITERS_REVISE = 3  # revise passes rarely need fresh research; cap the loop for latency
MAX_CUSTOM_AGENTS = 3


def _last_write(a, b):
    """Reducer: analyst and lens_prep run in the same superstep and both write
    last_output — last write wins (the SSE trace reads per-node deltas, not state)."""
    return b


class CouncilState(TypedDict, total=False):
    user_input: str
    history: list
    file_texts: list
    file_images: list
    agents: dict            # core agents {intake, analyst, reviewer, client}
    settings: dict
    brief: str
    analysis: str           # current best analysis
    last_output: Annotated[str, _last_write]  # what the node just produced (for trace/SSE)
    feedback: dict          # stage_id -> feedback text
    lens_plan: dict         # stage_id -> {lenses, questions, text} (expert mode only)


# ---------- helpers ----------

# Deterministic format-contract filter: when the user constrained the output,
# the analyst wraps the deliverable in markers and everything outside them is
# discarded server-side. No markers → text passes through unchanged.
_DELIV_RE = re.compile(r"===\s*DELIVERABLE\s*===\s*(.*?)\s*===\s*END\s*DELIVERABLE\s*===", re.DOTALL)


def _extract_deliverable(text: str) -> str:
    m = _DELIV_RE.search(text or "")
    return m.group(1).strip() if m else text


def _text_of(msg) -> str:
    c = msg.content
    if isinstance(c, str):
        return c
    parts = []
    for b in c:
        if isinstance(b, dict) and b.get("type") == "text":
            parts.append(b.get("text", ""))
        elif isinstance(b, str):
            parts.append(b)
    return "\n".join(parts)


def _history_text(history: list) -> str:
    if not history:
        return "(no prior conversation)"
    lines = []
    for m in history:
        who = "User" if m["role"] == "user" else "Assistant"
        content = m["content"]
        if len(content) > 1500:
            content = content[:1500] + " …[truncated]"
        lines.append(f"{who}: {content}")
    return "\n".join(lines)


def _core(state: CouncilState, key: str) -> dict:
    return (state.get("agents") or {}).get(key) or {}


def _sys_core(state: CouncilState, key: str) -> str:
    a = _core(state, key)
    return f"{a.get('system_prompt', '')}\n\n(Your name is {a.get('name', key)}.)"


async def _run_with_tools(llm, system: str, user_content: str, max_iters: int = MAX_TOOL_ITERS) -> str:
    """Manual tool-calling loop (avoids prebuilt-agent API drift across
    langgraph versions). Tools run in a thread so they don't block the loop."""
    msgs = [SystemMessage(content=system), HumanMessage(content=user_content)]
    llm_t = llm.bind_tools(ANALYST_TOOLS)
    tools_by_name = {t.name: t for t in ANALYST_TOOLS}
    for _ in range(max_iters):
        resp = await llm_t.ainvoke(msgs)
        msgs.append(resp)
        if not getattr(resp, "tool_calls", None):
            return _text_of(resp)
        for tc in resp.tool_calls:
            tool = tools_by_name.get(tc["name"])
            if tool is None:
                result = f"Unknown tool: {tc['name']}"
            else:
                try:
                    result = await asyncio.to_thread(tool.invoke, tc["args"])
                except Exception as e:  # noqa: BLE001
                    result = f"Tool error: {e}"
            msgs.append(ToolMessage(content=str(result) or "(empty)", tool_call_id=tc["id"]))
    msgs.append(HumanMessage(content="Finalize your full analysis now from what you have. Do not call any more tools."))
    resp = await llm.ainvoke(msgs)
    return _text_of(resp)


# ---------- stage plan ----------

def build_stages(cfg: dict) -> list[dict]:
    """Compute the ordered review stages from the request config.

    Returns [{id, key ('reviewer'|'client'|'c_*'), name, system_prompt,
    model, agent_key (for model defaults), revise (bool), custom (bool)}].
    """
    agents = cfg.get("agents") or {}
    customs = {}
    for c in (cfg.get("custom_agents") or [])[:MAX_CUSTOM_AGENTS]:
        if c.get("enabled") and (c.get("system_prompt") or "").strip():
            customs[str(c.get("id"))] = c

    order = [str(k) for k in (cfg.get("stage_order") or [])]
    for default_key in ["reviewer"] + list(customs) + ["client"]:
        if default_key not in order:
            # unknown/new stages: customs slot in before client, client stays last
            if default_key == "client" or "client" not in order:
                order.append(default_key)
            else:
                order.insert(order.index("client"), default_key)

    stages = []
    for key in order:
        if key in ("reviewer", "client") and cfg.get(f"enable_{key}"):
            a = agents.get(key) or {}
            # Expert Mode: the SERVER owns the prompt — any client-sent
            # system_prompt is ignored (enforcement lives here, not in the UI).
            expert = bool(a.get("expert_mode"))
            prompt = EXPERT_AGENTS[key]["system_prompt"] if expert else a.get("system_prompt", "")
            stages.append({"id": key, "key": key,
                           "name": a.get("name", "Reviewer" if key == "reviewer" else "Client"),
                           "system_prompt": prompt, "model": a.get("model"),
                           "agent_key": key, "revise": True, "custom": False,
                           "expert": expert})
        elif key in customs:
            c = customs[key]
            stages.append({"id": f"c_{key}", "key": key, "name": (c.get("name") or "Custom agent").strip() or "Custom agent",
                           "system_prompt": c.get("system_prompt", ""), "model": c.get("model"),
                           "agent_key": "custom", "revise": (c.get("mode") or "reviewer") != "transformer",
                           "custom": True})
    return stages


def expert_stage_ids(stages: list[dict]) -> list[str]:
    return [st["id"] for st in stages if st.get("expert")]


def node_sequence(stages: list[dict]) -> list[dict]:
    """Flat node list for the plan event / trace labels."""
    seq = [
        {"node": "intake", "agent_key": "intake", "label": "Intake brief", "model_agent": ("intake", None)},
        {"node": "analyst", "agent_key": "analyst", "label": "Draft analysis", "model_agent": ("analyst", None)},
    ]
    if expert_stage_ids(stages):
        # Runs in parallel with the draft but finishes first — listed between
        # intake and analyst so the progress UI's done-pointer stays truthful.
        seq.insert(1, {"node": "lens_prep", "agent_key": "router", "label": "Lens selection",
                       "model_agent": ("router", None)})
    for i, st in enumerate(stages):
        label = "Client feedback" if st["id"] == "client" else (
            "Reviewer critique" if st["id"] == "reviewer" else
            ("Transform" if not st["revise"] else "Critique"))
        seq.append({"node": st["id"], "agent_key": st["agent_key"], "label": label,
                    "stage": st, "model_agent": (st["agent_key"], st.get("model"))})
        if st["revise"]:
            last = all(not s["revise"] for s in stages[i + 1:])
            seq.append({"node": f"revise_{st['id']}", "agent_key": "analyst",
                        "label": "Final analysis" if last else "Revised analysis",
                        "model_agent": ("analyst", None)})
    return seq


# ---------- nodes ----------

async def intake_node(state: CouncilState) -> dict:
    a = _core(state, "intake")
    llm = build_llm(state.get("settings"), "intake", a.get("model"))
    file_notes = "\n\n".join(
        f"--- Uploaded file: {f['name']} ---\n{f['text']}" for f in state.get("file_texts") or []
    ) or "(no document files uploaded)"
    text = (
        f"CONVERSATION SO FAR:\n{_history_text(state.get('history') or [])}\n\n"
        f"USER'S NEW MESSAGE:\n{state['user_input']}\n\n"
        f"EXTRACTED FILE CONTENT:\n{file_notes}"
    )
    content: list = [{"type": "text", "text": text}]
    for data_url in state.get("file_images") or []:
        content.append({"type": "image_url", "image_url": {"url": data_url}})
    resp = await llm.ainvoke([SystemMessage(content=_sys_core(state, "intake")),
                              HumanMessage(content=content)])
    brief = _text_of(resp)
    return {"brief": brief, "last_output": brief}


async def analyst_node(state: CouncilState) -> dict:
    a = _core(state, "analyst")
    llm = build_llm(state.get("settings"), "analyst", a.get("model"))
    user = (
        f"RESEARCH BRIEF from the intake agent:\n{state['brief']}\n\n"
        f"CONVERSATION SO FAR (for continuity):\n{_history_text(state.get('history') or [])}\n\n"
        "Produce the full analysis now."
    )
    draft = _extract_deliverable(await _run_with_tools(llm, _sys_core(state, "analyst"), user))
    return {"analysis": draft, "last_output": draft}


def make_lens_prep_node(expert_stages: list[dict]):
    """Blind interrogation-plan prep, parallel with the analyst draft. Only for
    expert-mode core reviewers (never custom agents). Never raises."""
    async def lens_prep_node(state: CouncilState) -> dict:
        lens_plan, summary = await prepare_lens_plans(
            expert_stages, state.get("user_input", ""), state.get("brief", ""),
            state.get("settings") or {})
        return {"lens_plan": lens_plan, "last_output": summary}
    return lens_prep_node


def make_stage_node(st: dict):
    async def stage_node(state: CouncilState) -> dict:
        llm = build_llm(state.get("settings"), st["agent_key"], st.get("model"))
        system = f"{st['system_prompt']}\n\n(Your name is {st['name']}.)"
        if st["revise"]:
            task = "Give your review/feedback now. Do not rewrite the analysis yourself."
        else:
            task = "Produce your full transformed version of the analysis now — your output replaces the current analysis."
        plan = None if st["custom"] else (state.get("lens_plan") or {}).get(st["id"])
        plan_block = f"{plan['text']}\n\n" if plan else ""
        user = (
            f"USER'S ORIGINAL ASK:\n{state.get('user_input', '')}\n\n"
            f"INTAKE BRIEF (user context):\n{state.get('brief', '')}\n\n"
            f"CURRENT ANALYSIS:\n{state.get('analysis', '')}\n\n"
            f"{plan_block}{task}"
        )
        resp = await llm.ainvoke([SystemMessage(content=system), HumanMessage(content=user)])
        out = _text_of(resp)
        if st["revise"]:
            fb = dict(state.get("feedback") or {})
            fb[st["id"]] = out
            return {"feedback": fb, "last_output": out}
        return {"analysis": out, "last_output": out}
    return stage_node


def make_revise_node(st: dict):
    async def revise_node(state: CouncilState) -> dict:
        a = _core(state, "analyst")
        llm = build_llm(state.get("settings"), "analyst", a.get("model"))
        relation = "your boss" if st["id"] == "reviewer" else ("the client" if st["id"] == "client" else "a reviewer on the team")
        user = (
            f"USER'S ORIGINAL ASK (its format/length instructions are binding):\n{state.get('user_input', '')}\n\n"
            f"YOUR CURRENT ANALYSIS:\n{state.get('analysis', '')}\n\n"
            f"FEEDBACK from {st['name']} ({relation}):\n{(state.get('feedback') or {}).get(st['id'], '')}\n\n"
            "Revise the analysis to address every point — strengthen, don't just append. "
            "Search ONLY if the feedback explicitly demands new evidence you don't already have. "
            "If the user's ask specified an output format or length (see the brief's FORMAT "
            "CONTRACT), the revised output must still honor it EXACTLY — apply the feedback's "
            "substance within that constraint, never expand beyond it. "
            "Output the full revised analysis."
        )
        revised = _extract_deliverable(await _run_with_tools(llm, _sys_core(state, "analyst"), user,
                                                             max_iters=MAX_TOOL_ITERS_REVISE))
        return {"analysis": revised, "last_output": revised}
    return revise_node


def build_council_graph(stages: list[dict]):
    g = StateGraph(CouncilState)
    g.add_node("intake", intake_node)
    g.add_node("analyst", analyst_node)
    g.add_edge(START, "intake")
    g.add_edge("intake", "analyst")
    prev = "analyst"
    for st in stages:
        g.add_node(st["id"], make_stage_node(st))
        g.add_edge(prev, st["id"])
        prev = st["id"]
        if st["revise"]:
            rid = f"revise_{st['id']}"
            g.add_node(rid, make_revise_node(st))
            g.add_edge(st["id"], rid)
            prev = rid
    g.add_edge(prev, END)
    experts = [st for st in stages if st.get("expert")]
    if experts:
        # Blind prep runs in parallel with the draft; both edges join at the
        # first stage node (it waits for analyst AND lens_prep).
        g.add_node("lens_prep", make_lens_prep_node(experts))
        g.add_edge("intake", "lens_prep")
        g.add_edge("lens_prep", stages[0]["id"])
    return g.compile()
