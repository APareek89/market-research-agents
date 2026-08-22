"""Conversational memory: Supabase Postgres (mra_ tables) with a transparent
in-memory fallback so the app never hard-fails when the DB is unreachable."""

import json
import os
import uuid
import datetime

import asyncpg

_pool: asyncpg.Pool | None = None
_mem: dict[str, dict] = {}  # conversation_id -> {session_id, title, created_at, messages: []}

SCHEMA = """
CREATE TABLE IF NOT EXISTS mra_conversations (
    id UUID PRIMARY KEY,
    session_id TEXT NOT NULL,
    title TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS mra_conversations_session_idx ON mra_conversations (session_id);
CREATE TABLE IF NOT EXISTS mra_messages (
    id UUID PRIMARY KEY,
    conversation_id UUID REFERENCES mra_conversations(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    trace JSONB,
    created_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS mra_messages_conv_idx ON mra_messages (conversation_id);
"""


async def init_db() -> str:
    global _pool
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        return "memory (no DATABASE_URL)"
    try:
        # statement_cache_size=0: required behind pgbouncer/Supabase pooler
        _pool = await asyncpg.create_pool(url, min_size=0, max_size=4,
                                          statement_cache_size=0, timeout=10)
        async with _pool.acquire() as con:
            await con.execute(SCHEMA)
        return "postgres"
    except Exception as e:  # noqa: BLE001
        _pool = None
        return f"memory (db unreachable: {type(e).__name__})"


async def ensure_conversation(session_id: str, conversation_id: str | None, title_hint: str) -> str:
    if conversation_id:
        return conversation_id
    cid = str(uuid.uuid4())
    title = (title_hint or "New research")[:80]
    if _pool:
        try:
            async with _pool.acquire() as con:
                await con.execute(
                    "INSERT INTO mra_conversations (id, session_id, title) VALUES ($1,$2,$3)",
                    uuid.UUID(cid), session_id, title)
            return cid
        except Exception:  # noqa: BLE001
            pass
    _mem[cid] = {"session_id": session_id, "title": title,
                 "created_at": datetime.datetime.utcnow().isoformat(), "messages": []}
    return cid


async def add_message(conversation_id: str, role: str, content: str, trace: dict | None = None):
    mid = str(uuid.uuid4())
    if _pool:
        try:
            async with _pool.acquire() as con:
                await con.execute(
                    "INSERT INTO mra_messages (id, conversation_id, role, content, trace) VALUES ($1,$2,$3,$4,$5)",
                    uuid.UUID(mid), uuid.UUID(conversation_id), role, content,
                    json.dumps(trace) if trace else None)
            return
        except Exception:  # noqa: BLE001
            pass
    conv = _mem.setdefault(conversation_id, {"session_id": "?", "title": "", "messages": []})
    conv["messages"].append({"id": mid, "role": role, "content": content, "trace": trace,
                             "created_at": datetime.datetime.utcnow().isoformat()})


async def get_history(conversation_id: str, limit: int = 12) -> list[dict]:
    """Last N user/assistant messages (content only) for model context."""
    msgs = await get_messages(conversation_id)
    return [{"role": m["role"], "content": m["content"]} for m in msgs][-limit:]


async def get_messages(conversation_id: str) -> list[dict]:
    if _pool:
        try:
            async with _pool.acquire() as con:
                rows = await con.fetch(
                    "SELECT id, role, content, trace, created_at FROM mra_messages "
                    "WHERE conversation_id=$1 ORDER BY created_at", uuid.UUID(conversation_id))
            return [{"id": str(r["id"]), "role": r["role"], "content": r["content"],
                     "trace": json.loads(r["trace"]) if r["trace"] else None,
                     "created_at": r["created_at"].isoformat()} for r in rows]
        except Exception:  # noqa: BLE001
            pass
    conv = _mem.get(conversation_id)
    return list(conv["messages"]) if conv else []


async def list_conversations(session_id: str) -> list[dict]:
    if _pool:
        try:
            async with _pool.acquire() as con:
                rows = await con.fetch(
                    "SELECT id, title, created_at FROM mra_conversations "
                    "WHERE session_id=$1 ORDER BY created_at DESC LIMIT 30", session_id)
            return [{"id": str(r["id"]), "title": r["title"],
                     "created_at": r["created_at"].isoformat()} for r in rows]
        except Exception:  # noqa: BLE001
            pass
    return [{"id": cid, "title": c.get("title", ""), "created_at": c.get("created_at", "")}
            for cid, c in _mem.items() if c.get("session_id") == session_id]
