"""Dynamic lens retrieval for Expert Mode review stages.

lens_prep runs in parallel with the analyst draft and composes a BLIND,
task-contextualized interrogation plan per expert-mode reviewer — questions
derive from the brief, not the draft's frame. LLM router (haiku) selects
frameworks from the compact index; one sonnet call contextualizes them.
Every failure path degrades silently to no-plan (= today's behavior)."""

import asyncio
import os

from .llm import build_llm, resolve_model
from langchain_core.messages import HumanMessage, SystemMessage

from . import db

ROUTER_MODEL = "claude-haiku-4-5"
COMPOSER_MODEL = "claude-sonnet-5"

def model_label(settings: dict) -> str:
    router = resolve_model(settings, "router", ROUTER_MODEL)
    composer = resolve_model(settings, "composer", COMPOSER_MODEL)
    return router if router == composer else f"{router} / {composer}"

# stage id -> KB reviewer role + hard caps (attention budget, spec §2/§3)
LENS_ROLES = {"reviewer": "vera", "client": "cleo"}
LENS_CAPS = {"reviewer": {"lenses": 3, "questions": 9}, "client": {"lenses": 2, "questions": 5}}

APPLY_INSTRUCTION = (
    "TASK-SPECIFIC INTERROGATION PLAN (prepared blind from the brief, before the draft existed). "
    "Apply it two-phase: (1) sort the questions — which does the draft answer, dodge, or never "
    "consider; (2) fold the material misses into your findings. Cite the lens tag on each "
    "question you use."
)

ROUTER_SCHEMA = {
    "name": "lens_selection",
    "description": "Frameworks selected as interrogation lenses for this task",
    "schema": {
        "title": "lens_selection",
        "description": "Frameworks selected as interrogation lenses for this task",
        "type": "object",
        "properties": {
            "lenses": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "why": {"type": "string"},
                        "weight": {"type": "string", "enum": ["primary", "secondary"]},
                    },
                    "required": ["id", "why", "weight"],
                    "additionalProperties": False,
                },
            },
            "no_fit": {"type": "boolean"},
        },
        "required": ["lenses", "no_fit"],
        "additionalProperties": False,
    },
}

COMPOSER_SCHEMA = {
    "name": "interrogation_plans",
    "description": "Contextualized interrogation plan per reviewer",
    "schema": {
        "title": "interrogation_plans",
        "description": "Contextualized interrogation plan per reviewer",
        "type": "object",
        "properties": {
            "plans": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "agent": {"type": "string", "enum": ["reviewer", "client"]},
                        "questions": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "question": {"type": "string"},
                                    "via": {"type": "string"},
                                },
                                "required": ["question", "via"],
                                "additionalProperties": False,
                            },
                        },
                    },
                    "required": ["agent", "questions"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["plans"],
        "additionalProperties": False,
    },
}


def _llm(model: str, settings: dict, max_tokens: int):
    role="router" if model==ROUTER_MODEL else "composer"
    # Uses the selected provider and the same budget/mock context as the council.
    return build_llm(settings,role,model,max_tokens=max_tokens)

async def _route_for(stage_id: str, index: list[dict], ask: str, brief: str, key: dict) -> list[dict]:
    """One haiku call: select up to cap lenses for one expert reviewer."""
    role = LENS_ROLES[stage_id]
    cap = LENS_CAPS[stage_id]["lenses"]
    rows = [r for r in index if role in (r.get("reviewer") or [])]
    if not rows:
        return []
    catalog = "\n".join(
        f"- {r['id']}: {r['when_to_use']} (signals: {', '.join(r['trigger_signals'] or [])})"
        for r in rows)
    system = (
        "You route market-research review tasks to interrogation frameworks. "
        f"Select the frameworks (max {cap}) whose lens would most sharpen a critique of THIS task. "
        "Match the task against each framework's when-to-use line and trigger signals. "
        "Fewer, sharper lenses beat coverage. Set no_fit=true only if none genuinely applies.")
    user = (
        f"AVAILABLE FRAMEWORKS:\n{catalog}\n\n"
        f"USER'S ASK:\n{ask}\n\n"
        f"INTAKE BRIEF:\n{brief}\n\n"
        f"Select up to {cap} lens(es) by id.")
    llm = _llm(ROUTER_MODEL, key, 1000).with_structured_output(ROUTER_SCHEMA["schema"], method="json_schema")
    out = await llm.ainvoke([SystemMessage(content=system), HumanMessage(content=user)])
    if not isinstance(out, dict) or out.get("no_fit"):
        return []
    valid = {r["id"] for r in rows}
    return [l for l in out.get("lenses", []) if l.get("id") in valid][:cap]


async def _compose(selection: dict, frameworks: dict, ask: str, brief: str, key: dict) -> dict:
    """One sonnet call: contextualize the selected frameworks' interrogation
    sets into per-reviewer plans (deduped, capped, lens-tagged)."""
    sections = []
    for stage_id, lenses in selection.items():
        cap = LENS_CAPS[stage_id]["questions"]
        bodies = "\n\n".join(
            f"### {frameworks[l['id']]['name']} [{l['weight']}]\n{frameworks[l['id']]['body_md']}"
            for l in lenses if l["id"] in frameworks)
        sections.append(
            f"## Plan for agent '{stage_id}' (max {cap} questions TOTAL)\n"
            f"Selected frameworks:\n{bodies}")
    system = (
        "You prepare interrogation plans for market-research reviewers. You see the task brief "
        "but NOT the draft (blind preparation — questions must derive from the problem, not any "
        "draft's framing). For each requested agent: take the selected frameworks' Interrogation "
        "sets, keep only the questions material to THIS task, contextualize each to the task's "
        "specifics (name the actual market/product/decision), dedupe overlapping questions across "
        "frameworks, order critical-first, and respect the per-agent TOTAL question cap — the cap "
        "is a hard attention budget, cut the least material questions to fit. In `via`, put the "
        "framework's short name (e.g. 'Wardley Evolution').")
    user = (
        f"USER'S ASK:\n{ask}\n\n"
        f"INTAKE BRIEF:\n{brief}\n\n"
        f"{chr(10).join(sections)}\n\n"
        "Produce the plan(s) now.")
    llm = _llm(COMPOSER_MODEL, key, 5000).with_structured_output(COMPOSER_SCHEMA["schema"], method="json_schema")
    out = await llm.ainvoke([SystemMessage(content=system), HumanMessage(content=user)])
    plans = {}
    for p in (out.get("plans", []) if isinstance(out, dict) else []):
        sid = p.get("agent")
        if sid in selection:
            cap = LENS_CAPS[sid]["questions"]
            qs = [q for q in (p.get("questions") or []) if isinstance(q, dict) and q.get("question")]
            plans[sid] = [{"question": q["question"], "via": q.get("via") or "Framework"}
                          for q in qs][:cap]
    return plans


def _plan_text(questions: list[dict]) -> str:
    lines = [f"{i}. {q['question']} [via {q['via']}]" for i, q in enumerate(questions, 1)]
    return f"{APPLY_INSTRUCTION}\n\n" + "\n".join(lines)


def _summary(selection: dict, plans: dict, names: dict) -> str:
    out = []
    for sid, lenses in selection.items():
        who = names.get(sid, sid)
        out.append(f"**{who} — lenses:** " + "; ".join(
            f"{l['id']} ({l['weight']}) — {l['why']}" for l in lenses))
        qs = plans.get(sid) or []
        if qs:
            out.append(f"**{who} — interrogation plan ({len(qs)} questions):**")
            out.extend(f"{i}. {q['question']} [via {q['via']}]" for i, q in enumerate(qs, 1))
    return "\n".join(out)


async def prepare_lens_plans(expert_stages: list[dict], ask: str, brief: str, settings: dict) -> tuple[dict, str]:
    """Returns (lens_plan {stage_id: {lenses, questions, text}}, trace summary).
    NEVER raises — any KB/DB/router failure returns ({}, reason) and the run
    proceeds exactly as today."""
    try:
        key = settings
        stage_ids = [st["id"] for st in expert_stages if st["id"] in LENS_ROLES]
        roles = [LENS_ROLES[s] for s in stage_ids]
        index = await db.fetch_framework_index(roles)
        if not index:
            return {}, "(lens selection skipped: framework KB unavailable — running with built-in lenses)"

        routed = await asyncio.gather(
            *(_route_for(sid, index, ask, brief, key) for sid in stage_ids),
            return_exceptions=True)
        selection = {}
        for sid, res in zip(stage_ids, routed):
            if isinstance(res, Exception):
                print("[lens_prep] router unavailable; continuing with built-in lenses", flush=True)
            elif res:
                selection[sid] = res
        if not selection:
            return {}, "(lens selection: no framework fit — running with built-in lenses)"

        ids = sorted({l["id"] for lenses in selection.values() for l in lenses})
        frameworks = {f["id"]: f for f in await db.fetch_frameworks(ids)}
        if not frameworks:
            return {}, "(lens selection skipped: framework fetch failed — running with built-in lenses)"

        plans = await _compose(selection, frameworks, ask, brief, key)
        lens_plan = {}
        for sid, lenses in selection.items():
            qs = plans.get(sid) or []
            if qs:
                lens_plan[sid] = {"lenses": lenses, "questions": qs, "text": _plan_text(qs)}
        if not lens_plan:
            return {}, "(lens selection: plan composition failed — running with built-in lenses)"
        names = {st["id"]: st["name"] for st in expert_stages}
        return lens_plan, _summary({s: selection[s] for s in lens_plan}, plans, names)
    except Exception as e:  # noqa: BLE001 — non-negotiable: never block the run
        print("[lens_prep] optional plan unavailable; continuing with built-in lenses", flush=True)
        return {}, f"(lens selection skipped: {type(e).__name__} — running with built-in lenses)"
