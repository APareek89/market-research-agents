# Agent Council — Market Research

A 4-agent LangGraph council that sharpens market research through review rounds:
**Scout** (intake) → **Astra** (analyst, web tools) → **Vera** (boss critique, toggleable) → **Cleo** (client feedback, toggleable).

FastAPI + LangGraph/LangChain backend · React (Vite) frontend · Postgres (Supabase) conversational memory with in-memory fallback · deployed on Render.

## Run locally

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env   # add ANTHROPIC_API_KEY (+ optional DATABASE_URL)
set -a && source .env && set +a
.venv/bin/uvicorn app.main:app --port 8600
```

Frontend dev: `cd frontend && npm install && npm run dev` (proxies /api to :8600).
Production: `npm run build` — FastAPI serves `frontend/dist/` statically.

## Env vars
- `ANTHROPIC_API_KEY` — default Claude key (users can bring their own in the UI)
- `DATABASE_URL` — optional Postgres URL; omit to run on in-memory conversation storage
