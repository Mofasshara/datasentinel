# DataSentinel — Project Roadmap

## Status Overview
| Phase | Status | Tasks | Done |
|-------|--------|-------|------|
| Phase 0 — Foundation & Monorepo Setup | ✅ Done | 6 | 6/6 |
| Phase 1 — Module 1: AI Output Validator | ✅ Done | 11 | 11/11 |
| Phase 2 — Module 2: Self-Healing Pipeline Agent | ✅ Done | 10 | 10/10 |
| Phase 3 — Module 3: Real-Time Stream Monitor | ✅ Done | 8 | 8/8 |
| Phase 4 — Platform Integration & Demo | ✅ Done | 6 | 6/6 |

**Total Progress:** 41 / 41 tasks complete (100%)
**Estimated Remaining:** 0 — project complete

---

## Stack

| Layer | Technology | Reason |
|-------|-----------|--------|
| Language | Python 3.11+ | Ecosystem dominance in data/ML |
| Agent Orchestration | LangGraph | Stateful multi-agent graphs, HITL support |
| LLM | Claude API (claude-sonnet-4-6) | Tool use, structured output, cost efficiency |
| Data Layer | DuckDB + PostgreSQL | DuckDB for local analytics, Postgres for production state |
| Streaming | Apache Kafka + Apache Flink (PyFlink) | Industry standard; matches Grab Coban architecture |
| Pipeline Integration | dbt Core | Most widely adopted transformation layer |
| Metadata / Lineage | OpenMetadata | Open source, well-documented API, schema registry |
| Validation Framework | Great Expectations (extension) | Module 1 ships as a GX-compatible extension |
| Embeddings | Sentence Transformers (all-MiniLM-L6-v2) | Lightweight, local, semantic similarity |
| Backend API | FastAPI | Async, typed, OpenAPI spec auto-generation |
| Frontend | Streamlit (prototype) → React (polish) | Fast to demo; React for portfolio-quality UI |
| Packaging | Python monorepo with `uv` workspaces | Each module independently installable |
| Infra | Docker Compose | Local development; all services one command |

---

## Phase 0 — Foundation & Monorepo Setup
**Goal:** One repository, shared infrastructure, every developer tool wired up.
**Estimate:** 1 week

| # | Task | Status | Estimate | Started | Completed |
|---|------|--------|----------|---------|-----------|
| 0.1 | Initialize monorepo structure: `packages/semantic-validator`, `packages/pipeline-agent`, `packages/stream-monitor`, `shared/`, `infra/`, `demo/` | ⏳ Pending | 2h | — | — |
| 0.2 | Set up `uv` workspaces so each package is independently pip-installable | ⏳ Pending | 1h | — | — |
| 0.3 | Docker Compose stack: Kafka, Flink, Postgres, OpenMetadata, dbt test project with sample data | ⏳ Pending | 4h | — | — |
| 0.4 | Shared logging, config, and Claude API client in `shared/` | ⏳ Pending | 2h | — | — |
| 0.5 | GitHub Actions CI: lint (ruff), type check (mypy), unit tests on each package | ⏳ Pending | 2h | — | — |
| 0.6 | Root README with architecture diagram, quickstart, and module descriptions | ⏳ Pending | 2h | — | — |

---

## Phase 1 — Module 1: AI Output Validator (`datasентinel-semantic`)
**Goal:** Installable Python library that validates semantic correctness of AI-generated data in pipelines. Ships as open-source with Great Expectations compatibility.
**Estimate:** 5–6 weeks

### Phase 1A — Core Engine (2 weeks)
| # | Task | Status | Estimate | Started | Completed |
|---|------|--------|----------|---------|-----------|
| 1.1 | Design the `SemanticExpectation` base class API — mirrors GX `Expectation` interface so the library is a drop-in extension | ⏳ Pending | 1 day | — | — |
| 1.2 | Implement `LLMJudge` engine: takes a record + prompt template + pass/fail criteria → calls Claude API → returns structured verdict with confidence score | ⏳ Pending | 2 days | — | — |
| 1.3 | Implement `SemanticExpectationSuite`: runs multiple expectations against a dataset, aggregates results, produces a quality report | ⏳ Pending | 1 day | — | — |
| 1.4 | Persist expectation results to Postgres: per-column pass rates, verdict history, timestamps — this powers the drift dashboard | ⏳ Pending | 1 day | — | — |

### Phase 1B — Built-In Expectations (2 weeks)
| # | Task | Status | Estimate | Started | Completed |
|---|------|--------|----------|---------|-----------|
| 1.5 | `expect_column_to_be_factually_consistent_with(reference_column)` — LLM checks if AI-generated text is consistent with a reference field in the same row | ⏳ Pending | 2 days | — | — |
| 1.6 | `expect_column_to_not_hallucinate_entities()` — extracts named entities (names, dates, numbers, SKUs) from AI-generated text and checks they exist in source data | ⏳ Pending | 2 days | — | — |
| 1.7 | `expect_semantic_drift_below(threshold, lookback_days)` — computes cosine similarity of embedding centroid vs. historical baseline; alerts when drift exceeds threshold | ⏳ Pending | 2 days | — | — |
| 1.8 | `expect_label_to_match_content(label_column, content_column)` — LLM verifies that classification labels assigned by an AI model genuinely match the content of the record | ⏳ Pending | 1 day | — | — |

### Phase 1C — Integration & Demo (1–2 weeks)
| # | Task | Status | Estimate | Started | Completed |
|---|------|--------|----------|---------|-----------|
| 1.9 | dbt test macro wrapper: `semantic_validator_test` — runs Module 1 checks as a dbt test on any model column, surfaces results in dbt test output | ⏳ Pending | 2 days | — | — |
| 1.10 | Streamlit dashboard: per-column pass rate time series, semantic drift chart, example failing records with LLM verdict explanations | ⏳ Pending | 2 days | — | — |
| 1.11 | Demo dataset: synthetic e-commerce dataset where an AI enrichment step introduces ~5% hallucinations, factual inconsistencies, and semantic drift — used in README and demo | ⏳ Pending | 1 day | — | — |

---

## Phase 2 — Module 2: Self-Healing Pipeline Agent (`datasентinel-agent`)
**Goal:** LangGraph multi-agent system that detects dbt test failures, traces root cause through data lineage, generates a SQL fix, tests it in a sandbox, and presents a one-click approval for deployment.
**Estimate:** 7–8 weeks

### Phase 2A — Observer + Lineage Tracer (2 weeks)
| # | Task | Status | Estimate | Started | Completed |
|---|------|--------|----------|---------|-----------|
| 2.1 | Observer Agent: polls dbt test results (dbt `run_results.json`) and Great Expectations validation results; fires incident events on failures | ⏳ Pending | 2 days | — | — |
| 2.2 | OpenMetadata integration: fetch lineage graph for any table — upstream tables, column-level lineage, owning pipeline jobs | ⏳ Pending | 3 days | — | — |
| 2.3 | Lineage Tracer Agent: given a failing table, walks the lineage graph upstream, queries row counts and null rates at each hop to locate where the anomaly first appeared | ⏳ Pending | 3 days | — | — |

### Phase 2B — Diagnoser Agent (2 weeks)
| # | Task | Status | Estimate | Started | Completed |
|---|------|--------|----------|---------|-----------|
| 2.4 | Anomaly classifier: LLM tool use — agent queries DuckDB to compute column statistics at the failing table and at the root-cause table; classifies issue type (schema drift, volume drop, null spike, distribution shift, logic error) | ⏳ Pending | 3 days | — | — |
| 2.5 | Root cause report generation: structured JSON report summarising affected tables, likely cause, confidence, and supporting evidence (stats, sample rows) | ⏳ Pending | 2 days | — | — |

### Phase 2C — Remediator Agent (2 weeks)
| # | Task | Status | Estimate | Started | Completed |
|---|------|--------|----------|---------|-----------|
| 2.6 | SQL fix generation: LLM agent reads the failing dbt model SQL + the root cause report, generates a targeted SQL patch with explanation | ⏳ Pending | 3 days | — | — |
| 2.7 | Sandbox executor: spins up a DuckDB in-process environment, runs the patched SQL against a snapshot of the data, re-runs the failing dbt tests, returns pass/fail result | ⏳ Pending | 2 days | — | — |
| 2.8 | Sandbox iteration loop: if tests still fail after the first fix attempt, the agent reads the remaining failures and iterates up to 3 times before escalating to human | ⏳ Pending | 2 days | — | — |

### Phase 2D — HITL Approval UI (1–2 weeks)
| # | Task | Status | Estimate | Started | Completed |
|---|------|--------|----------|---------|-----------|
| 2.9 | FastAPI + Streamlit approval interface: shows incident summary, lineage trace, proposed SQL diff, sandbox test results, approve/reject buttons; approved fixes are written to the dbt project as a PR | ⏳ Pending | 3 days | — | — |
| 2.10 | Demo scenario: sample dbt project with a broken transformation (upstream schema change introduces a new column that a downstream model does not handle); agent traces, fixes, and presents approval in under 2 minutes | ⏳ Pending | 1 day | — | — |

---

## Phase 3 — Module 3: Real-Time Stream Monitor (`datasентinel-stream`)
**Goal:** Portable, open-source Flink-native data quality library with statistical baseline learning and near-real-time anomaly detection — the "Deequ for Flink" that does not exist yet.
**Estimate:** 8–10 weeks

### Phase 3A — Flink Job Framework (2 weeks)
| # | Task | Status | Estimate | Started | Completed |
|---|------|--------|----------|---------|-----------|
| 3.1 | PyFlink job template: consumes from a Kafka topic, deserializes records (JSON/Avro), applies a chain of quality check operators, publishes violation events to a `dq-violations` Kafka topic | ✅ Done | 3 days | 2026-05-29 | 2026-05-29 |
| 3.2 | Declarative quality rule DSL in YAML: define schema rules, value range rules, null rate thresholds, and regex patterns per Kafka topic — no code required for basic checks | ✅ Done | 2 days | 2026-05-29 | 2026-05-29 |
| 3.3 | Rule-to-Flink compiler: YAML rules are compiled to operator chain at job startup | ✅ Done | 2 days | 2026-05-29 | 2026-05-29 |

### Phase 3B — Statistical Baseline Engine (3 weeks)
| # | Task | Status | Estimate | Started | Completed |
|---|------|--------|----------|---------|-----------|
| 3.4 | Stateful operator: Welford online mean/variance tracker per metric; EMA blending after warmup | ✅ Done | 3 days | 2026-05-29 | 2026-05-29 |
| 3.5 | Anomaly detector: fires when metric deviates more than z_score_threshold std from rolling baseline; N configurable per rule | ✅ Done | 2 days | 2026-05-29 | 2026-05-29 |
| 3.6 | Cross-stream correlator: groups violation events from same (topic, column) within 60s window into a single CorrelatedIncident | ✅ Done | 3 days | 2026-05-29 | 2026-05-29 |
| 3.7 | Baseline cold-start: no statistical violations emitted until min_samples reached; EMA takes over after warmup | ✅ Done | 1 day | 2026-05-29 | 2026-05-29 |

### Phase 3C — LLM Semantic Rule Generation (2 weeks)
| # | Task | Status | Estimate | Started | Completed |
|---|------|--------|----------|---------|-----------|
| 3.8 | Natural language rule intake: NLPRuleGenerator accepts plain-English description → Claude → validated QualityRuleSet | ✅ Done | 2 days | 2026-05-29 | 2026-05-29 |
| 3.9 | Rule validation: LLM-generated YAML validated against DSL Pydantic schema before activation | ✅ Done | 1 day | 2026-05-29 | 2026-05-29 |

### Phase 3D — Dashboard & Demo (1–2 weeks)
| # | Task | Status | Estimate | Started | Completed |
|---|------|--------|----------|---------|-----------|
| 3.10 | Streamlit dashboard: per-topic quality score timeline, live violation feed, KPI row, violation timeline chart | ✅ Done | 3 days | 2026-05-29 | 2026-05-29 |
| 3.11 | Demo scenario: standalone GPS producer with 120-record warmup → anomaly injection → violation + correlator output; `make demo-stream` | ✅ Done | 1 day | 2026-05-29 | 2026-05-29 |

---

## Phase 4 — Platform Integration & Portfolio Polish
**Goal:** All three modules work together in a single demo. README, docs, and portfolio presentation are production-quality.
**Estimate:** 2–3 weeks

| # | Task | Status | Estimate | Started | Completed |
|---|------|--------|----------|---------|-----------|
| 4.1 | Unified Streamlit home dashboard (`demo/app.py`): three-column module cards, platform KPI row, architecture diagram, quickstart commands | ✅ Done | 2 days | 2026-05-29 | 2026-05-29 |
| 4.2 | End-to-end demo script (`demo/run_all.py`): `make demo` runs all three modules; skips LLM demos gracefully when no API key set; color-coded summary | ✅ Done | 3 days | 2026-05-29 | 2026-05-29 |
| 4.3 | Architecture diagram: ASCII art in README (platform overview + per-module flows) | ✅ Done | 1 day | 2026-05-29 | 2026-05-29 |
| 4.4 | Root README: market gap table, module descriptions with code examples, architecture diagram, quickstart, repo layout, stack table | ✅ Done | 1 day | 2026-05-29 | 2026-05-29 |
| 4.5 | PyPI publish: `publish.yml` GitHub Actions workflow with OIDC trusted publishing for `datasentinel-semantic` and `datasentinel-stream`; triggered on release tag | ✅ Done | 1 day | 2026-05-29 | 2026-05-29 |
| 4.6 | LinkedIn / portfolio write-up (`CASE_STUDY.md`): market research section, three-module technical breakdown, learnings — ready to copy to LinkedIn | ✅ Done | 1 day | 2026-05-29 | 2026-05-29 |

---

## Build Order Rationale

Build Phase 1 first because:
- Widest-open market gap with zero direct competitors
- Ships as an open-source Python library — gives you a PyPI package on your CV
- Completely self-contained (no Kafka, no Flink infra needed to demo)
- Easiest to demo to a non-technical audience in an interview

Build Phase 2 second because:
- Builds on Phase 1's dbt integration
- Requires the OpenMetadata Docker service already in the Compose stack from Phase 0
- The HITL approval UI is the best interview demo of the three

Build Phase 3 last because:
- Most infrastructure-heavy (Kafka + Flink Docker setup)
- Most technically differentiated — leave the hardest for when you have momentum
- References Confluent's TimesFM work as market validation in the README

---

## Change Log

| Date | Change | Reason | Impact | Original Plan |
|------|--------|--------|--------|---------------|
| 2026-05-28 | Initial roadmap created | Project inception | All phases defined | N/A |
| 2026-05-29 | Phase 0 + Phase 1 completed | Build session | Monorepo scaffolded, all 4 expectations + suite + Postgres storage + Streamlit dashboard + demo dataset built; 16/16 tests passing | N/A (new build) |
| 2026-05-29 | Phase 2 completed | Build session | All 5 LangGraph agent nodes (Observer, Lineage Tracer, Diagnoser, Remediator, Sandbox) + graph wiring + FastAPI server + Streamlit HITL UI + demo + incident repository; 35/35 tests passing | N/A (new build) |
| 2026-05-29 | Phase 3 completed | Build session | QualityRuleSet DSL (5 rule types), SchemaValidator, StatisticalMonitor (Welford online + EMA baseline), IncidentCorrelator, NLPRuleGenerator, ViolationsRepository, Streamlit dashboard, standalone GPS demo; 67/67 total tests passing | N/A (new build) |
| 2026-05-29 | Phase 4 completed — project 100% done | Build session | Unified home dashboard (demo/app.py), end-to-end demo runner (demo/run_all.py, make demo), PyPI publish workflow (OIDC trusted publishing), polished README with market gap table and code examples, LinkedIn case study (CASE_STUDY.md) | N/A (new build) |
