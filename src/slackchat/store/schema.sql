CREATE TABLE IF NOT EXISTS runs (
  run_id         TEXT PRIMARY KEY,
  created_at     TEXT NOT NULL,        -- ISO8601 UTC
  client         TEXT NOT NULL,        -- cli | server | eval
  mode           TEXT NOT NULL,        -- correction | translation
  forced         INTEGER NOT NULL,
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

CREATE TABLE IF NOT EXISTS reviews (
  run_id     TEXT NOT NULL REFERENCES runs(run_id),
  dimension  TEXT NOT NULL,
  score      INTEGER NOT NULL CHECK (score IN (0,1,2)),
  reviewer   TEXT NOT NULL,            -- 'human' or a model id
  note       TEXT,
  created_at TEXT NOT NULL,
  PRIMARY KEY (run_id, dimension, reviewer)
);

-- Not in the design spec. Added because pass rate is not derivable from
-- `runs` alone, and spec section 8.1 requires `--compare A B` to be a query.
CREATE TABLE IF NOT EXISTS eval_results (
  run_id     TEXT NOT NULL REFERENCES runs(run_id),
  case_id    TEXT NOT NULL,
  check_name TEXT NOT NULL,
  passed     INTEGER NOT NULL,
  PRIMARY KEY (run_id, check_name)
);

CREATE INDEX IF NOT EXISTS idx_eval_results_case ON eval_results(case_id);
