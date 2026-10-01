# Portfolio deployment

Status as of 1 October 2026: 36 backend contracts, 13 frontend checks, live free acceptance and root browser checks passed. The corrected limited paid core flow completed. Independent paid SQL/hash verification, ordinary-live restoration and the final browser smoke passed. Live acceptance is complete.

The live URL is https://market-research.3-6-183-210.sslip.io. Service configuration uses the `market-research` slug, SSM prefix `/portfolio/market-research/`, and PostgreSQL database `market_research`. FastAPI listens on internal port 8600 behind HTTPS. One worker owns the detached run registry. The container uses Python 3.11, Node 22 at build time, a non-root runtime and a database-aware `/healthz`.

Required hosted settings:

- `PORTFOLIO_AUTH_ENABLED=1`, `PUBLIC_BASE_URL` set to the exact HTTPS origin, and a private `AUTH_SECRET` of at least 32 characters.
- `DATABASE_URL` plus `DATABASE_SSL_CA_FILE`; certificate-verified PostgreSQL is required. `DATABASE_SSL=disable` is a loopback-only test exception.
- `MRA_DEFAULT_PROVIDER=openai`, `MRA_DEFAULT_MODEL=gpt-5-mini`, with `OPENAI_API_KEY` supplied privately. `MRA_MOCK_MODE=0` is the verified ordinary live configuration. Use `1` for deployment smoke; change back only after the controlled release checks.
- `PORTFOLIO_STORAGE_MODE=s3`, the private versioned `PORTFOLIO_STORAGE_BUCKET=portfolio-market-research-uploads-511833557379`, scoped AWS credentials and `AWS_REGION=ap-south-1`.
- `MRA_OWNER_BUDGET_USD` and `MRA_SHARED_BUDGET_USD` bound included provider spend. Reservations are conservative; unknown shared-model prices fail closed. Provider retries are disabled.

Do not place env files, credentials, operator receipts or account fixtures in the repository. The app migration creates its own `mra_` tables in the dedicated database. It does not connect to the previous ALS Supabase database. Browser account identity governs all private routes; a caller-supplied `session_id` is retained only for old client compatibility.

Prepared examples are authored replies executed by the normal graph and explicitly marked cached. They do not retrieve fresh web facts or spend provider tokens. Hosted research/upload/export limits preserve the core workflow while bounding shared resources. Original uploads are immutable private S3 versions referenced by owner and SHA-256; generated reports and run traces live in PostgreSQL. Image uploads are inputs, not a generated-media pipeline.

The client uses shared Inter/Roboto Mono tokens, Lucide icons, semantic light/dark surfaces and narrow-screen layouts. Late JSON, SSE and download responses are fenced by account generation. This client guard is usability protection; server owner checks are the security boundary.

Live free acceptance on image `portfolio/market-research:c089e8e8463d4534` verified two-account auth/isolation, six cached stages/replay, an 89-byte original upload with exact S3 version and SHA, anonymous S3 denial, readable PDF/PPTX, session revocation, TLS 1.3, preservation of existing rows and zero provider-usage change. The root independently checked the browser flow and served frontend asset.

Paid accounting for the same unchanged app image:

- Attempt 1: one OpenAI HTTP200 response, 858 input / 499 output tokens, including 384 reasoning and 0 cached input; estimated $0.0012125. A temporary operator guard reconstructed decoded gzip bytes with the old encoding headers, so the application stored an error run and no assistant report. The conservative reservation was subsequently reconciled from retained provider evidence; the failed run remains unchanged.
- Corrected attempt: after offline reproduction and full-SDK compressed-response regression, a separately authorized dispatch completed the normal report path. GPT-5-mini used 858 input / 1007 output tokens, including 896 reasoning and 0 cached input; estimated $0.0022285.
- Total: two actual dispatches, estimated $0.0034410, one completed report. Reasoning tokens are included in output totals, not added again. Estimates use token prices and are not invoices. No automatic retry occurred.

Only the temporary proof guard changed between attempts. The proof used prepared intake and reviewers off to constrain paid calls; it did not validate a fully paid council or fresh research. The final answer correctly recommended Growth at $0.15/image but assumed four Basic plans could be purchased, which the supplied fictional terms did not establish. Retain that quality limitation.

Ordinary live runtime is verified on the same `c089e8e8463d4534` image: healthy, non-root, read-only root filesystem, authentication enabled, mock disabled, PostgreSQL TLS 1.3 and awslogs. The temporary proof command and mounts are removed; prior applications remain unchanged. The final browser check reopened the actual paid report/trace and completed a new free example without console errors or warnings. Corrected evidence seal SHA256: `bfe935a2b6d795e9016688872d74a752ec0c3fd454bccfbcef2eaf7a33d9f6af`.

Temporary proof scripts, capabilities, private responses and sealed receipts remain outside this repository. Source publication uses a separately reviewed exact index and redacted scans.
