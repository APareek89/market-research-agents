"""LangGraph StateGraph wiring the 4-agent council.

Flow (conditional on toggles):
  intake -> analyst -> [reviewer -> analyst_refine] -> [client -> analyst_final] -> END
"""

import asyncio
from typing import TypedDict

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langgraph.graph import END, START, StateGraph

from .llm import build_llm
from .tools import ANALYST_TOOLS

MAX_TOOL_ITERS = 6


class CouncilState(TypedDict, total=False):
    user_input: str
    history: list
    file_texts: list
    file_images: list
    agents: dict
    settings: dict
    enable_reviewer: bool
    enable_client: bool
    brief: str
    draft: str
    critique: str
    refined: str
    client_feedback: str
    final: str


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


def _agent(state: CouncilState, key: str) -> dict:
    return (state.get("agents") or {}).get(key) or {}


def _sys(state: CouncilState, key: str) -> str:
    a = _agent(state, key)
    return f"{a.get('system_prompt', '')}\n\n(Your name is {a.get('name', key)}.)"


def _current_analysis(state: CouncilState) -> str:
    return state.get("refined") or state.get("draft") or ""


async def _run_with_tools(llm, system: str, user_content: str) -> str:
    """Manual tool-calling loop (avoids prebuilt-agent API drift across
    langgraph versions). Tools run in a thread so they don't block the loop."""
    msgs = [SystemMessage(content=system), HumanMessage(content=user_content)]
    llm_t = llm.bind_tools(ANALYST_TOOLS)
    tools_by_name = {t.name: t for t in ANALYST_TOOLS}
    for _ in range(MAX_TOOL_ITERS):
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


async def intake_node(state: CouncilState) -> dict:
    llm = build_llm(state.get("settings"), "intake")
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
    resp = await llm.ainvoke([SystemMessage(content=_sys(state, "intake")),
                              HumanMessage(content=content)])
    return {"brief": _text_of(resp)}


async def analyst_node(state: CouncilState) -> dict:
    llm = build_llm(state.get("settings"), "analyst")
    user = (
        f"RESEARCH BRIEF from the intake agent:\n{state['brief']}\n\n"
        f"CONVERSATION SO FAR (for continuity):\n{_history_text(state.get('history') or [])}\n\n"
        "Produce the full analysis now."
    )
    draft = await _run_with_tools(llm, _sys(state, "analyst"), user)
    return {"draft": draft, "final": draft}


async def reviewer_node(state: CouncilState) -> dict:
    llm = build_llm(state.get("settings"), "reviewer")
    user = (
        f"USER'S ORIGINAL ASK:\n{state.get('user_input', '')}\n\n"
        f"INTAKE BRIEF (user context):\n{state.get('brief', '')}\n\n"
        f"ANALYST'S DRAFT:\n{state.get('draft', '')}\n\n"
        "Review it now — contextualize the framework to this task first."
    )
    resp = await llm.ainvoke([SystemMessage(content=_sys(state, "reviewer")),
                              HumanMessage(content=user)])
    return {"critique": _text_of(resp)}


async def analyst_refine_node(state: CouncilState) -> dict:
    llm = build_llm(state.get("settings"), "analyst")
    reviewer_name = _agent(state, "reviewer").get("name", "the reviewer")
    user = (
        f"YOUR PREVIOUS DRAFT:\n{state.get('draft', '')}\n\n"
        f"REVIEW FEEDBACK from {reviewer_name} (your boss):\n{state.get('critique', '')}\n\n"
        "Revise the analysis to address every point. Use tools if you need more evidence. Output the full revised analysis."
    )
    refined = await _run_with_tools(llm, _sys(state, "analyst"), user)
    return {"refined": refined, "final": refined}


async def client_node(state: CouncilState) -> dict:
    llm = build_llm(state.get("settings"), "client")
    user = (
        f"THE RESEARCH I COMMISSIONED (brief):\n{state.get('brief', '')}\n\n"
        f"THE ANALYSIS DELIVERED TO ME:\n{_current_analysis(state)}\n\n"
        "Give your stakeholder feedback now."
    )
    resp = await llm.ainvoke([SystemMessage(content=_sys(state, "client")),
                              HumanMessage(content=user)])
    return {"client_feedback": _text_of(resp)}


async def analyst_final_node(state: CouncilState) -> dict:
    llm = build_llm(state.get("settings"), "analyst")
    client_name = _agent(state, "client").get("name", "the client")
    user = (
        f"YOUR CURRENT ANALYSIS:\n{_current_analysis(state)}\n\n"
        f"FINAL FEEDBACK from {client_name} (the client):\n{state.get('client_feedback', '')}\n\n"
        "Produce the final polished version addressing the client's asks. Use tools only if strictly necessary. Output the full final analysis."
    )
    final = await _run_with_tools(llm, _sys(state, "analyst"), user)
    return {"final": final}


def _after_analyst(state: CouncilState) -> str:
    if state.get("enable_reviewer"):
        return "reviewer"
    if state.get("enable_client"):
        return "client"
    return END


def _after_refine(state: CouncilState) -> str:
    return "client" if state.get("enable_client") else END


def build_graph():
    g = StateGraph(CouncilState)
    g.add_node("intake", intake_node)
    g.add_node("analyst", analyst_node)
    g.add_node("reviewer", reviewer_node)
    g.add_node("analyst_refine", analyst_refine_node)
    g.add_node("client", client_node)
    g.add_node("analyst_final", analyst_final_node)
    g.add_edge(START, "intake")
    g.add_edge("intake", "analyst")
    g.add_conditional_edges("analyst", _after_analyst, ["reviewer", "client", END])
    g.add_edge("reviewer", "analyst_refine")
    g.add_conditional_edges("analyst_refine", _after_refine, ["client", END])
    g.add_edge("client", "analyst_final")
    g.add_edge("analyst_final", END)
    return g.compile()


GRAPH = build_graph()


def plan_for(enable_reviewer: bool, enable_client: bool) -> list[str]:
    plan = ["intake", "analyst"]
    if enable_reviewer:
        plan += ["reviewer", "analyst_refine"]
    if enable_client:
        plan += ["client", "analyst_final"]
    return plan


NODE_AGENT = {
    "intake": "intake", "analyst": "analyst", "reviewer": "reviewer",
    "analyst_refine": "analyst", "client": "client", "analyst_final": "analyst",
}

NODE_LABEL = {
    "intake": "Intake brief", "analyst": "Draft analysis", "reviewer": "Reviewer critique",
    "analyst_refine": "Refined analysis", "client": "Client feedback", "analyst_final": "Final analysis",
}

NODE_OUTPUT_KEY = {
    "intake": "brief", "analyst": "draft", "reviewer": "critique",
    "analyst_refine": "refined", "client": "client_feedback", "analyst_final": "final",
}
