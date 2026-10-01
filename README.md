# Market Research — Agent Council

Scout turns a question and uploaded sources into a brief. Astra drafts the analysis, Vera challenges it, and Cleo reviews it from the client’s perspective. Each enabled review feeds back into Astra. You can change prompts, reorder stages, add up to three custom reviewers or transformers, and inspect the complete trace.

**Live app:** [Market Research](https://market-research.3-6-183-210.sslip.io). On 1 October 2026, authenticated live checks and the prepared-example browser flow passed. One limited paid report completed after correcting the temporary proof guard. Independent paid SQL/hash verification and the final browser smoke passed after restoration of ordinary live mode. Live acceptance is complete.

## Try it in three steps

1. Open the app and create an account with an email and a password of at least 12 characters.
2. Choose **Try with an example**, then one of the three prepared questions below. These authored, illustrative replies run through the normal council without provider requests.
3. Expand the agent steps, open **Observability**, and export the report as PDF or PPTX. Reload to return to the saved conversation. A new question uses the selected provider and is a separate live research request.

The three examples are:

- **Size an AI editing opportunity:** “Should a small team test an AI image-editing service for Indian ecommerce sellers?”
- **Compare competitor pricing:** “Compare fictional editing plans: Basic $20 for 100 images, Growth $60 for 500 images, Team $150 for 1500 images. What should a 400-image/month team test?”
- **Evaluate a watermark-removal idea:** “How should a team validate a video watermark-removal feature for customers editing videos they own or are authorized to modify?”

Their reports mark assumptions and fictional figures explicitly. They are examples of the workflow, not current market research.

## Run a free local fixture

Python 3.11 and Node 22 or later are required. From the repository root:

```bash
python3.11 -m venv .venv
.venv/bin/pip install -r requirements-lock.txt
(cd frontend && npm ci && npm run build)
env -i PATH="$PATH" HOME="$HOME" \
  MRA_MOCK_MODE=1 MRA_STORAGE_MODE=fixture PORTFOLIO_STORAGE_MODE=fixture \
  PORTFOLIO_AUTH_ENABLED=0 PUBLIC_BASE_URL=http://127.0.0.1:8600 \
  .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8600
```

Open [localhost:8600](http://127.0.0.1:8600). This explicit development mode uses temporary memory, skips accounts, and produces synthetic output. Provider keys are absent; research tools are disabled. Restarting clears the fixture. For real accounts, use PostgreSQL and the settings in [deployment notes](docs/PORTFOLIO-DEPLOYMENT.md).

## What is preserved

- Independent conversations and detached runs; disconnecting or changing tabs does not stop a run. Use **Stop** to cancel it, or reload to replay its events.
- Optional Vera/Cleo review, expert framework lenses, dynamic custom stages, per-agent prompts and model choices.
- PDF, DOCX, spreadsheet, CSV, text and image uploads; server limits include eight files, 15 MiB per file and 30 MiB combined.
- Markdown tables, Mermaid diagrams, PDF via Typst with fpdf fallback, and PPTX exports.
- OpenAI, Anthropic and Hugging Face options. The hosted default is supplied by the API; launch configuration is OpenAI `gpt-5-mini`.

## Privacy and practical limits

Accounts use password hashes and revocable server sessions. Conversations, traces, runs and original uploads are checked against the signed-in owner. Upload originals use a private versioned S3 object with hash verification. API keys entered in the browser stay in the current page’s memory, disappear on reload/signout/provider change, and are never saved in browser preferences or run records. Preferences are scoped to the account; late responses from another account are discarded.

The included live-research budget is bounded and can be exhausted; prepared examples remain free. Provider support and budgets do not guarantee answer accuracy. Search may return no results, expert lenses may degrade to ordinary review, and exports are generated from the report rather than a bespoke slide template. Email verification, Google sign-in and email password recovery are not configured. There is one server worker; unfinished runs are marked interrupted after a process restart, rather than resumed across machines. No image-generation pipeline is part of this app.

## Verified scope

There are 36 backend contracts and 13 frontend checks, plus the separate 35-check original baseline. Live verification covered two-account ownership, session revocation, six cached stages and replay, a private 89-byte upload with exact S3 version/hash and anonymous denial, and readable PDF/PPTX exports. The browser flow passed sign-in/out, saved traces, both themes and 390px layout.

The paid check used a prepared Scout brief, disabled reviewers and one live GPT-5-mini analyst response. It completed a report recommending Growth at $0.15 per image, but also assumed four Basic plans could be purchased—an unsupported condition in the fictional dataset. This proves the limited execution/persistence path, not a fully paid council, current web research or factual accuracy.

There were **two actual paid dispatches**, totaling an estimated **$0.0034410**: the first returned provider usage but failed in the temporary guard before a report; the corrected attempt completed. These are token-price estimates, not invoices. Both attempts and their separate outcomes are retained in [Loop.MD](Loop.MD).

## Checks and architecture

```bash
(cd frontend && npm test && npm run build)
.venv/bin/python -m compileall -q app
```

See [Loop.MD](Loop.MD) for test receipts and verification scope, [the council diagram](docs/mermaid/01-agent-flow.mmd), and [the architecture viewer](docs/architecture-flow.html). Development checks must use mock/fixture contexts. A normal council invokes multiple models; do not use it as an unapproved one-call smoke test.
