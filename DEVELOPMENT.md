# DataSentinel — Development Guide

Everything a new session needs to continue building without re-deriving context.

---

## Current State (as of 2026-05-29)

**Built and tested:**
- Phase 0 — Monorepo foundation (uv workspaces, Docker Compose, shared module, CI)
- Phase 1 — `datasentinel-semantic` (Module 1: AI Output Validator) — 16/16 tests
- Phase 2 — `datasentinel-agent` (Module 2: Self-Healing Pipeline Agent) — 19/19 tests
- Phase 3 — `datasentinel-stream` (Module 3: Real-Time Stream Monitor) — 32/32 tests

**Not yet built:**
- Phase 4 — Platform Integration & End-to-End Demo

**Total tests: 67/67 passing (no API key needed — all LLM calls mocked in tests)**

---

## Repository Layout

```
DataSentinel/
├── packages/
│   ├── semantic-validator/          # Module 1 — pip install datasentinel-semantic
│   │   └── src/datasentinel_semantic/
│   │       ├── core/
│   │       │   ├── expectation.py   # SemanticExpectation base class + Verdict + ExpectationResult
│   │       │   └── judge.py         # LLMJudge (Claude API, lazy-init, prompt caching)
│   │       ├── expectations/
│   │       │   ├── factual_consistency.py   # LLM-per-row: AI text vs reference column
│   │       │   ├── hallucination.py         # LLM-per-row: entities traceable to source
│   │       │   ├── semantic_drift.py        # Embedding-based: cosine distance vs baseline
│   │       │   └── label_accuracy.py        # LLM-per-row: AI label vs content column
│   │       ├── suite.py             # SemanticExpectationSuite runner
│   │       ├── storage/repository.py  # Postgres: save results + pass rate history
│   │       ├── dbt_integration/     # YAML-driven dbt hook integration
│   │       └── dashboard/app.py     # Streamlit UI (make dashboard-semantic)
│   │
│   ├── pipeline-agent/              # Module 2 — LangGraph self-healing pipeline agent
│   │   └── src/datasentinel_agent/
│   │       ├── state.py             # IncidentState TypedDict (LangGraph state)
│   │       ├── graph.py             # build_graph() + run_incident() entry point
│   │       ├── agents/
│   │       │   ├── observer.py      # Reads dbt failures, computes column stats
│   │       │   ├── lineage_tracer.py  # Walks OpenMetadata lineage upstream
│   │       │   ├── diagnoser.py     # Claude: classifies anomaly type
│   │       │   ├── remediator.py    # Claude: generates SQL fix
│   │       │   └── sandbox.py       # DuckDB: applies fix, reruns assertions
│   │       ├── tools/
│   │       │   ├── dbt_reader.py        # Reads dbt manifest.json + run_results.json
│   │       │   ├── openmetadata.py      # OpenMetadata REST client (lazy settings, mock fallback)
│   │       │   └── duckdb_sandbox.py    # Isolated DuckDB session + assertion runner
│   │       ├── storage/incident_repository.py  # Postgres: upsert/list/resolve incidents
│   │       ├── api/server.py        # FastAPI: /incidents CRUD + approve/reject
│   │       └── ui/app.py            # Streamlit HITL approval dashboard
│   │
│   └── stream-monitor/              # Module 3 — NOT YET BUILT
│       └── src/datasentinel_stream/
│           ├── rules/               # EMPTY — placeholder
│           └── operators/           # EMPTY — placeholder
│
├── shared/src/datasentinel_shared/
│   ├── claude_client.py    # Anthropic SDK wrapper: prompt caching, retry, judge() + complete()
│   ├── config.py           # Pydantic Settings (lazy — no API key needed until first use)
│   └── logging.py          # structlog (PrintLoggerFactory, no add_logger_name processor)
│
├── infra/
│   ├── docker-compose.yml  # Kafka, Flink, Postgres, OpenMetadata, Kafka UI
│   └── configs/postgres/init.sql   # Full DB schema for all 3 modules
│
├── demo/scenarios/
│   ├── semantic_demo.py    # 10 product records with injected AI errors
│   └── agent_demo.py       # Simulated dbt incident: column rename → null spike
│
├── Makefile                # make dev / make infra / make demo-* / make dashboard-*
├── .env.example            # Copy to .env and set ANTHROPIC_API_KEY
├── pyproject.toml          # uv workspace root + pytest importlib mode
├── ROADMAP.md              # Task tracking (66% complete)
└── CUSTOMER_OVERVIEW.md    # Plain-English product explanation for all 3 modules
```

---

## Setup

```bash
# 1. Clone and install
git clone ... && cd DataSentinel
make dev                      # uv sync + copy .env.example

# 2. Set your API key
echo "ANTHROPIC_API_KEY=sk-ant-..." >> .env

# 3. Start infrastructure (Postgres + Kafka + Flink)
make infra

# 4. Run tests (no API key needed)
make test

# 5. Run demo (API key required)
make demo-semantic            # Module 1 demo
make demo-agent               # Module 2 demo

# 6. Launch dashboards
make dashboard-semantic       # Module 1 Streamlit UI
make dashboard-agent          # Module 2 HITL approval UI
```

---

## Known Gotchas & Fixes Applied

### 1. LLM clients must be lazy-initialized
**Problem:** `LLMJudge()` and `OpenMetadataClient()` called `get_settings()` eagerly in `__init__`, which required `ANTHROPIC_API_KEY` at import time — breaking all tests.

**Fix:** All three expectation classes (`FactualConsistencyExpectation`, `HallucinationDetectionExpectation`, `LabelAccuracyExpectation`) and `OpenMetadataClient` now use a `_judge: LLMJudge | None = None` pattern with a `@property` that instantiates lazily. Tests pre-set `exp._judge = mock_judge` before calling `evaluate()`.

`SemanticDriftExpectation` was also fixed — removed the `get_settings()` call from `__init__`, defaulting `model_name="all-MiniLM-L6-v2"` directly.

### 2. structlog `add_logger_name` incompatible with `PrintLoggerFactory`
**Problem:** `structlog.stdlib.add_logger_name` requires a stdlib logger (has `.name` attribute). `PrintLoggerFactory` produces `PrintLogger` which has no `.name`. Caused `AttributeError` in all tests that triggered logging.

**Fix:** Removed `add_logger_name` from the processor chain in `shared/src/datasentinel_shared/logging.py`.

### 3. PyFlink package name
**Problem:** `pyflink>=1.20` does not exist on PyPI. The actual package is `apache-flink`.

**Fix:** `stream-monitor/pyproject.toml` declares `apache-flink` under `[project.optional-dependencies] flink = [...]` (not in core deps) so it doesn't block workspace install. Install with `uv pip install "datasentinel-stream[flink]"` when building Module 3.

### 4. Running tests across packages simultaneously
**Problem:** Both `packages/*/tests/__init__.py` create a `tests` namespace that collides when pytest collects them together.

**Fix:** Added `addopts = "--import-mode=importlib"` to root `pyproject.toml` `[tool.pytest.ini_options]`.

### 5. editable package install in uv workspace
**Problem:** `uv run pytest` couldn't find `datasentinel_agent` module even after `uv sync`, because workspace editable installs weren't linking into the venv's site-packages.

**Fix:** Run `uv pip install --python .venv/bin/python3 -e "packages/pipeline-agent" -e "packages/semantic-validator" -e "shared"` once after first `uv sync`. `make dev` should be updated to include this. (TODO: wire into Makefile `dev` target.)

---

## Architecture Decisions

### Lazy settings everywhere
All classes that need `Settings` (API key, DB URL, etc.) load them on first use, not in `__init__`. This keeps tests fast and keyless. Pattern: `if self._thing is None: self._thing = Thing()`.

### LLM calls use prompt caching
`ClaudeClient` sends the system prompt with `"cache_control": {"type": "ephemeral"}`. On repeated calls (same session), Claude serves from cache — critical for reducing cost when running expectations across large DataFrames.

### LangGraph state is a flat TypedDict
`IncidentState` in `state.py` is a flat dict — no nested objects. LangGraph handles deep merging of partial updates from each node. Each node returns only the keys it sets; unchanged keys are preserved automatically.

### OpenMetadata client degrades to mock
If the OpenMetadata server is unreachable (usual in local dev), the client falls back to `_mock_lineage()` which generates a plausible upstream chain based on the table name. The graph has `"_mock": True` so the UI can display an info banner. Phase 3 won't need OpenMetadata.

### DuckDB sandbox is stateless and always in-memory
`DuckDBSandbox` is used as a context manager (`with DuckDBSandbox() as sb:`). Each incident gets a fresh `:memory:` connection — no state leaks between runs.

---

## Phase 3 — Real-Time Stream Monitor (BUILT ✅)

**32/32 tests passing. Standalone demo: `make demo-stream`**

**Architecture (as built):**
```
Kafka topic (or standalone mode)
    │
    ▼
[QualityRuleSet] ← compiled from YAML or NLP
    │
    ├── SchemaValidator (deterministic: RangeRule, NotNullRule, RegexRule, NullRateRule)
    │
    └── StatisticalMonitor (stateful: Welford online mean/variance → z-score alert)
                │
                ▼
        IncidentCorrelator (groups violations within 60s window → CorrelatedIncident)
                │
                ▼
        Postgres (stream_violations table) + Streamlit dashboard
```

**Key files (all created):**
- `rules/dsl.py` — Pydantic models for 5 rule types; discriminated union; `QualityRuleSet.from_yaml()`
- `rules/compiler.py` — `RuleCompiler.compile(rule_set)` → `(SchemaValidator, StatisticalMonitor)`
- `operators/validator.py` — `SchemaValidator.check(record)` → `list[dict]` violations; stateful NullRateWindow per column
- `operators/anomaly_detector.py` — `StatisticalMonitor.check(record)`; Welford's online algorithm; EMA baseline blending (alpha=0.05) after warmup; no violations until `min_samples` reached
- `operators/correlator.py` — `IncidentCorrelator.push(violation)` → `CorrelatedIncident | None`; groups by (topic, column) key; time-window expiry
- `nlp_rules.py` — `NLPRuleGenerator.generate(topic, description)` → `QualityRuleSet`; lazy Claude client; validated against DSL schema
- `storage/violations_repository.py` — Postgres persist with graceful degradation
- `dashboard/app.py` — Streamlit: KPI row, violation timeline, per-topic bar, live feed
- `flink_job.py` — PyFlink job template (optional dep); wraps operators as Flink ProcessFunction
- `demo/scenarios/stream_demo.py` — standalone demo: 120-record warmup → GPS lat anomaly injection → violation + correlator output

**Design decisions:**
- **Operators are pure Python** — no Flink dependency in the core. PyFlink wraps them. This makes tests trivial (no cluster needed) and lets the library be used in non-Flink contexts (batch, testing, standalone).
- **Welford's online algorithm** — computes running mean/variance in O(1) space per column, suitable for unbounded streams. No need to store historical records.
- **EMA blending for baseline adaptation** — after warmup, the baseline itself drifts slowly (alpha=0.05) so long-term legitimate changes don't cause permanent alerts. Only sharp deviations exceed the threshold.
- **Correlator time-window grouping** — a burst of 30 GPS anomalies from one batch is reported as one incident, not 30 alerts. Reduces operational noise.
- **Cold-start protection** — no statistical violations fire until `min_samples` records are seen. Prevents false alerts on new topics.

**Confluence with market:** Confluent's `AI_DETECT_ANOMALIES` (Q2 2026, powered by TimesFM) proves the concept works commercially, but it's Confluent Cloud locked. This module is the portable, open-source equivalent.

---

## Phase 4 Plan — Platform Integration

**Goal:** All three modules run together from `make demo`. A unified Streamlit home dashboard shows health across all three layers.

**Key tasks:**
- Unified home dashboard (`demo/app.py`)
- `make demo` script: start infra + generate synthetic errors across all layers simultaneously
- Architecture diagram (Excalidraw/draw.io)
- PyPI publish: `pip install datasentinel-semantic`
- Root README demo GIFs
- LinkedIn case study write-up

---

## Database Schema (Postgres)

All tables created by `infra/configs/postgres/init.sql` on first `make infra`.

| Table | Module | Purpose |
|-------|--------|---------|
| `semantic_expectation_results` | 1 | Per-run pass rates by suite/column/expectation |
| `semantic_verdicts` | 1 | Per-record LLM verdicts (failures only, sampled) |
| `pipeline_incidents` | 2 | Incident lifecycle: open → pending_approval → resolved |
| `stream_violations` | 3 | Per-violation events from Flink jobs |
| `stream_baselines` | 3 | Rolling statistical baselines per topic/column/metric |

---

## Environment Variables

| Variable | Required | Default | Used by |
|----------|----------|---------|---------|
| `ANTHROPIC_API_KEY` | Yes (runtime) | — | All modules (Claude API) |
| `CLAUDE_MODEL` | No | `claude-sonnet-4-6` | All modules |
| `POSTGRES_*` | No (local dev) | `localhost/datasentinel` | Storage layer |
| `KAFKA_BOOTSTRAP_SERVERS` | No (Module 3) | `localhost:9092` | Stream monitor |
| `OPENMETADATA_HOST` | No (Module 2) | `http://localhost:8585` | Lineage tracer |
| `MAX_FIX_ITERATIONS` | No | `3` | Sandbox retry loop |
| `SEMANTIC_BATCH_SIZE` | No | `50` | Semantic validator |
