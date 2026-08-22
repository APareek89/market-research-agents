"""Ingest kb/frameworks/*.md into mra_frameworks (idempotent upsert by id).

Usage: .venv/bin/python scripts/ingest_kb.py   (reads DATABASE_URL from env or .env)
kb/ is the source of truth; this overwrites the DB mirror, never the reverse.
"""

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import asyncpg  # noqa: E402

from app import kb  # noqa: E402


def _load_dotenv():
    env = ROOT / ".env"
    if not env.exists():
        return
    for line in env.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


async def main():
    _load_dotenv()
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        sys.exit("DATABASE_URL not set (env or .env)")
    con = await asyncpg.connect(url, statement_cache_size=0)
    try:
        n = await kb.ingest(con)
        count = await con.fetchval("SELECT count(*) FROM mra_frameworks")
        ids = [r["id"] for r in await con.fetch("SELECT id FROM mra_frameworks ORDER BY id")]
    finally:
        await con.close()
    print(f"ingested {n} files; mra_frameworks now has {count} rows:")
    for i in ids:
        print(f"  - {i}")


if __name__ == "__main__":
    asyncio.run(main())
