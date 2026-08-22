"""Framework KB: kb/frameworks/*.md is the source of truth; mra_frameworks in
Postgres is a mirror (re-ingest overwrites DB, never the reverse). Files are
parsed whole — a framework is a unit of interrogation, never chunked."""

from pathlib import Path

KB_DIR = Path(__file__).resolve().parent.parent / "kb" / "frameworks"
SKIP_FILES = {"INDEX.md", "README.md"}

# embedding vector(1024) ships NULLABLE and unused — the pgvector retrieval
# path only becomes worth building past ~50 frameworks (user uploads).
# TODO(>50 frameworks): embed when_to_use + trigger_signals ONLY, never body_md.
DDL_VECTOR_EXT = "CREATE EXTENSION IF NOT EXISTS vector"
DDL = """
CREATE TABLE IF NOT EXISTS mra_frameworks (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    cluster TEXT NOT NULL,
    origin TEXT,
    strength TEXT,
    when_to_use TEXT NOT NULL,
    trigger_signals TEXT[] DEFAULT '{}',
    reviewer TEXT[] NOT NULL,
    pairs_well_with TEXT[] DEFAULT '{}',
    failure_modes TEXT[] DEFAULT '{}',
    body_md TEXT NOT NULL,
    embedding vector(1024),
    updated_at TIMESTAMPTZ DEFAULT now()
);
"""
DDL_NO_VECTOR = DDL.replace("    embedding vector(1024),\n", "")

UPSERT = """
INSERT INTO mra_frameworks
    (id, name, cluster, origin, strength, when_to_use, trigger_signals,
     reviewer, pairs_well_with, failure_modes, body_md, updated_at)
VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11, now())
ON CONFLICT (id) DO UPDATE SET
    name=EXCLUDED.name, cluster=EXCLUDED.cluster, origin=EXCLUDED.origin,
    strength=EXCLUDED.strength, when_to_use=EXCLUDED.when_to_use,
    trigger_signals=EXCLUDED.trigger_signals, reviewer=EXCLUDED.reviewer,
    pairs_well_with=EXCLUDED.pairs_well_with, failure_modes=EXCLUDED.failure_modes,
    body_md=EXCLUDED.body_md, updated_at=now()
"""


def _parse_frontmatter(fm: str) -> dict:
    """Tolerant one-key-per-line parser: KB values legally contain colons and
    quotes that strict YAML rejects (e.g. origin: Helmer, "7 Powers: ...").
    Lists are inline [a, b, c]; no multi-line values exist in the KB schema."""
    meta = {}
    for line in fm.splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        key, _, val = line.partition(":")
        val = val.strip()
        if val.startswith("[") and val.endswith("]"):
            items = [x.strip().strip('"').strip("'") for x in val[1:-1].split(",")]
            meta[key.strip()] = [x for x in items if x]
        else:
            meta[key.strip()] = val.strip('"').strip("'")
    return meta


def parse_framework(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        raise ValueError(f"{path.name}: missing frontmatter")
    _, fm, body = text.split("---", 2)
    meta = _parse_frontmatter(fm)

    def strs(key):
        v = meta.get(key) or []
        return [str(x) for x in v] if isinstance(v, list) else [str(v)]

    return {
        "id": str(meta["id"]),
        "name": str(meta["name"]),
        "cluster": str(meta["cluster"]),
        "origin": str(meta.get("origin") or ""),
        "strength": str(meta.get("strength") or ""),
        "when_to_use": str(meta["when_to_use"]),
        "trigger_signals": strs("trigger_signals"),
        "reviewer": strs("reviewer"),
        "pairs_well_with": strs("pairs_well_with"),
        "failure_modes": strs("failure_modes_caught"),
        "body_md": body.strip(),
    }


def load_all() -> list[dict]:
    rows = []
    for path in sorted(KB_DIR.glob("*.md")):
        if path.name in SKIP_FILES:
            continue
        rows.append(parse_framework(path))
    return rows


async def ensure_table(con) -> None:
    """Create mra_frameworks; vector column is best-effort (pgvector optional)."""
    try:
        await con.execute(DDL_VECTOR_EXT)
        await con.execute(DDL)
    except Exception:  # noqa: BLE001 — no pgvector: same table minus embedding
        await con.execute(DDL_NO_VECTOR)


async def ingest(con) -> int:
    await ensure_table(con)
    rows = load_all()
    for r in rows:
        await con.execute(UPSERT, r["id"], r["name"], r["cluster"], r["origin"],
                          r["strength"], r["when_to_use"], r["trigger_signals"],
                          r["reviewer"], r["pairs_well_with"], r["failure_modes"],
                          r["body_md"])
    return len(rows)
