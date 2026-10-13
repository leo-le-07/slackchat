CREATE TABLE IF NOT EXISTS runs (
  run_id         TEXT PRIMARY KEY,
  created_at     TEXT NOT NULL,        -- ISO8601 UTC
  client         TEXT NOT NULL,        -- cli | server
  mode           TEXT NOT NULL,        -- correction | translation (always detected)
  input          TEXT NOT NULL,
  output         TEXT NOT NULL,
  provider       TEXT NOT NULL,
  model          TEXT NOT NULL,
  prompt_version TEXT NOT NULL,
  prompt_hash    TEXT NOT NULL,
  input_tokens   INTEGER,
  output_tokens  INTEGER,
  cost_usd       REAL,
  latency_ms     INTEGER,
  changed_ratio  REAL,
  flags          TEXT,                 -- JSON array
  error          TEXT
);

CREATE INDEX IF NOT EXISTS idx_runs_mode_version ON runs(mode, prompt_version);
CREATE INDEX IF NOT EXISTS idx_runs_created ON runs(created_at);
