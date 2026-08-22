# PRD — Market Research Agent Council

## What we're building
A web app where a council of 4 AI agents produces sharp market-research analysis. Agent 0 (Scout) digests the user's ask + uploaded files; Agent 1 (Astra) researches with web tools and drafts the analysis; Agent 2 (Vera, "the boss") critiques it from first principles; Agent 3 (Cleo, "the client") gives final stakeholder feedback. Each review round feeds back into Agent 1 so the final output is much sharper than a single-shot answer.

## Who uses it, and for what
Anand (PM at PixelBin) and anyone he shares the Render URL with — for market research questions, competitor analysis, and document-grounded research. No sign-up; anonymous browser sessions.

## Core requirements
- **Tab 1 Chat**: Claude-style chat with file upload (PDF, DOCX, XLSX, CSV, images, ≤15 MB/file) + URL support; toggles for Agent 2 and Agent 3 that change the workflow.
- **Tab 2 Prompts**: modular editor for each agent's name + system prompt (sub-tab per agent, full-screen editing). Edits immediately change chat behavior (stored in browser, sent per request).
- **Tab 3 Observability**: full flow per run — user input, Scout brief, Astra draft, Vera critique, refined draft, Cleo feedback, final output, with timings.
- **Tab 4 Settings**: BYO API key (Claude or OpenAI) + model picker; server's default Claude key used when blank.
- Tools for Agent 1: web search, web fetch. Files are extracted server-side and fed via Scout.
- Stack: FastAPI + Python LangGraph/LangChain, React (Vite) frontend served as static files, Supabase Postgres (ALS prod) for conversational memory with in-memory fallback.
- Deploy: GitHub (APareek89) + Render (free tier).

## What must NEVER break
- The server's default Anthropic key and DB URL must never reach the client or the repo (env vars only).
- User-supplied API keys are never persisted server-side.
- A mid-run LLM failure must show a per-node error, not a blank screen or lost conversation.

## Done for v1
A deployed Render URL where: a message with a PDF attached runs the full 4-agent flow with both toggles on, streams per-agent progress, shows the trace in Observability, remembers the conversation on refresh, and works with an OpenAI key entered in Settings.

## Out of scope (v1)
Auth/sign-up, payment, multi-user workspaces, PPTX/export, agent parallelism, streaming tokens (node-level streaming only).
