-- DataSentinel schema bootstrap

CREATE DATABASE openmetadata_db;

-- Module 1: semantic validator results
CREATE TABLE IF NOT EXISTS semantic_expectation_results (
    id              BIGSERIAL PRIMARY KEY,
    run_id          UUID NOT NULL,
    suite_name      TEXT NOT NULL,
    expectation     TEXT NOT NULL,
    column_name     TEXT NOT NULL,
    dataset_name    TEXT,
    total_records   INTEGER NOT NULL,
    passed_records  INTEGER NOT NULL,
    failed_records  INTEGER NOT NULL,
    pass_rate       FLOAT NOT NULL,
    run_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata        JSONB
);

CREATE INDEX idx_ser_suite_column ON semantic_expectation_results (suite_name, column_name, run_at);

-- Module 1: per-record verdicts (sampled failures stored for dashboard)
CREATE TABLE IF NOT EXISTS semantic_verdicts (
    id              BIGSERIAL PRIMARY KEY,
    run_id          UUID NOT NULL,
    expectation     TEXT NOT NULL,
    column_name     TEXT NOT NULL,
    record_index    INTEGER,
    passed          BOOLEAN NOT NULL,
    confidence      FLOAT,
    reason          TEXT,
    evidence        JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_sv_run_expectation ON semantic_verdicts (run_id, expectation);

-- Module 2: pipeline incidents
CREATE TABLE IF NOT EXISTS pipeline_incidents (
    id              BIGSERIAL PRIMARY KEY,
    incident_id     UUID NOT NULL UNIQUE,
    table_name      TEXT NOT NULL,
    anomaly_type    TEXT NOT NULL,
    root_cause      TEXT,
    root_cause_table TEXT,
    status          TEXT NOT NULL DEFAULT 'open',  -- open | pending_approval | resolved | escalated
    proposed_fix    TEXT,
    sandbox_result  JSONB,
    resolved_at     TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Module 3: stream quality events
CREATE TABLE IF NOT EXISTS stream_violations (
    id              BIGSERIAL PRIMARY KEY,
    topic           TEXT NOT NULL,
    rule_name       TEXT NOT NULL,
    column_name     TEXT,
    violation_type  TEXT NOT NULL,
    sample_value    TEXT,
    window_start    TIMESTAMPTZ,
    window_end      TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_sv_topic_time ON stream_violations (topic, created_at);

CREATE TABLE IF NOT EXISTS stream_baselines (
    id              BIGSERIAL PRIMARY KEY,
    topic           TEXT NOT NULL,
    column_name     TEXT NOT NULL,
    metric          TEXT NOT NULL,
    mean            FLOAT,
    std_dev         FLOAT,
    window_count    INTEGER,
    last_updated    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (topic, column_name, metric)
);
