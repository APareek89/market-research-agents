CREATE TABLE IF NOT EXISTS mra_users(
 id UUID PRIMARY KEY, email TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(), disabled BOOLEAN NOT NULL DEFAULT false
);
CREATE UNIQUE INDEX IF NOT EXISTS mra_users_email_lower ON mra_users(lower(email));
CREATE TABLE IF NOT EXISTS mra_sessions(
 token_hash TEXT PRIMARY KEY, owner_id UUID NOT NULL REFERENCES mra_users(id),
 expires_at TIMESTAMPTZ NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS mra_rates(key TEXT PRIMARY KEY, window_start TIMESTAMPTZ NOT NULL, count INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS mra_conversations(
 id UUID PRIMARY KEY, owner_id UUID NOT NULL REFERENCES mra_users(id), title TEXT NOT NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(), UNIQUE(id,owner_id)
);
CREATE INDEX IF NOT EXISTS mra_conversations_owner ON mra_conversations(owner_id,created_at DESC);
CREATE TABLE IF NOT EXISTS mra_messages(
 id UUID PRIMARY KEY, conversation_id UUID NOT NULL, owner_id UUID NOT NULL,
 role TEXT NOT NULL CHECK(role IN ('user','assistant')), content TEXT NOT NULL, trace JSONB,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 FOREIGN KEY(conversation_id,owner_id) REFERENCES mra_conversations(id,owner_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS mra_messages_owner_conv ON mra_messages(owner_id,conversation_id,created_at);
CREATE TABLE IF NOT EXISTS mra_runs(
 id UUID PRIMARY KEY, conversation_id UUID NOT NULL, owner_id UUID NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('running','done','error','stopped')), events JSONB NOT NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 FOREIGN KEY(conversation_id,owner_id) REFERENCES mra_conversations(id,owner_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS mra_runs_owner_conv ON mra_runs(owner_id,conversation_id,created_at DESC);
CREATE TABLE IF NOT EXISTS mra_uploads(
 id UUID PRIMARY KEY, owner_id UUID NOT NULL REFERENCES mra_users(id), conversation_id UUID,
 bytes BIGINT NOT NULL CHECK(bytes>=0), storage_ref JSONB NOT NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 FOREIGN KEY(conversation_id,owner_id) REFERENCES mra_conversations(id,owner_id)
);
CREATE TABLE IF NOT EXISTS mra_usage(
 id UUID PRIMARY KEY, owner_id UUID NOT NULL REFERENCES mra_users(id), run_id UUID NOT NULL,
 provider TEXT NOT NULL, model TEXT NOT NULL, shared BOOLEAN NOT NULL,
 reserved_usd NUMERIC NOT NULL, actual_usd NUMERIC, input_tokens INTEGER, output_tokens INTEGER,
 status TEXT NOT NULL, cached_input_tokens INTEGER, reasoning_output_tokens INTEGER, created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE mra_usage ADD COLUMN IF NOT EXISTS cached_input_tokens INTEGER;
ALTER TABLE mra_usage ADD COLUMN IF NOT EXISTS reasoning_output_tokens INTEGER;
