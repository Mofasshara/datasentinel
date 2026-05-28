# DataSentinel

**Agentic data reliability platform** — semantic validation for AI-generated records, self-healing pipeline agents, and real-time streaming data quality.

[![Tests](https://img.shields.io/badge/tests-67%2F67%20passing-brightgreen)](https://github.com/Mofasshara/datasentinel/actions)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

---

## The Problem

Modern data pipelines have three blind spots that no existing tool addresses together:

| Gap | What happens today | What DataSentinel does |
|-----|--------------------|------------------------|
| **AI-generated records contain silent errors** | No tool validates whether AI-enriched columns are factually correct, hallucination-free, or semantically consistent over time | LLM-as-judge validation on every AI-generated column, every pipeline run |
| **Data incidents take 15+ hours to resolve manually** | Engineers trace root cause, write fixes, and test in staging — all by hand | LangGraph agent does it end-to-end in under 2 minutes, presents a one-click approval |
| **Streaming quality tools are batch-oriented or vendor-locked** | Confluent's anomaly detection works only in Confluent Cloud; no open-source Flink alternative | Portable, Flink-native statistical baseline engine — runs anywhere |

**Market timing:** Acceldata (Aug 2025), Databricks Genie Code (Mar 2026), and Monte Carlo Agent Observability (Mar 2026) all launched pipeline-adjacent AI products. None close all three gaps. Confluent's `AI_DETECT_ANOMALIES` (Q2 2026, powered by TimesFM) is the closest on streaming — but it's cloud-locked. All three gaps remain open in open source.

---

## Modules

### Module 1 — Semantic Validator (`datasentinel-semantic`)
> *"Is the data your AI systems are generating actually correct?"*

An installable Python library (Great Expectations-compatible) that runs LLM-as-judge checks on AI-enriched pipeline columns. Designed for teams running Claude, GPT-4, or any LLM to generate structured records in an ETL pipeline.

```bash
pip install datasentinel-semantic
```

```python
from datasentinel_semantic import SemanticExpectationSuite
from datasentinel_semantic.expectations import (
    FactualConsistencyExpectation,
    HallucinationDetectionExpectation,
    SemanticDriftExpectation,
    LabelAccuracyExpectation,
)

suite = SemanticExpectationSuite(name="product_catalog_quality")
suite.add(FactualConsistencyExpectation(column="ai_description", reference_column="spec_sheet"))
suite.add(HallucinationDetectionExpectation(column="ai_description", source_columns=["sku", "brand"]))
suite.add(SemanticDriftExpectation(column="ai_description", threshold=0.15, lookback_days=7))
suite.add(LabelAccuracyExpectation(column="ai_sentiment_label", content_column="review_text"))

result = suite.run(df)
print(result.summary())
# pass_rate=0.94  failed=340  drift_detected=True  drift_delta=0.18
```

**Four built-in expectations:**
- `FactualConsistencyExpectation` — LLM checks AI text against a reference column in the same row
- `HallucinationDetectionExpectation` — extracts named entities and verifies they appear in source data
- `SemanticDriftExpectation` — cosine similarity of embedding centroid vs. 7-day historical baseline
- `LabelAccuracyExpectation` — LLM verifies AI-assigned labels match record content

---

### Module 2 — Pipeline Agent (`datasentinel-agent`)
> *"When your data pipeline breaks, fix it automatically."*

A LangGraph multi-agent system that detects dbt test failures, traces root cause through OpenMetadata lineage, generates a SQL fix, validates it in a DuckDB sandbox, and presents a one-click human approval.

```
dbt failure detected
        │
        ▼
[ Observer ] → reads dbt run_results.json, computes column stats
        │
        ▼
[ Lineage Tracer ] → walks OpenMetadata graph upstream to find root-cause table
        │
        ▼
[ Diagnoser ] → Claude classifies anomaly: null_spike / schema_drift / logic_error
        │
        ▼
[ Remediator ] → Claude generates targeted SQL patch with explanation
        │
        ▼
[ DuckDB Sandbox ] → applies patch, re-runs assertions, iterates up to 3×
        │
        ▼
[ Streamlit HITL ] → approve / reject button → PR created on approval
```

FastAPI backend exposes `/incidents` CRUD. The Streamlit approval UI shows: incident summary, lineage trace, proposed SQL diff, sandbox test results.

---

### Module 3 — Stream Monitor (`datasentinel-stream`)
> *"Know the moment your live data feeds go wrong — not hours later."*

A portable, open-source PyFlink library for statistical data quality on Kafka streams. Define rules in YAML or plain English — no code required for standard checks.

```yaml
# gps_rules.yaml
topic: gps-events
rules:
  - name: valid_latitude
    type: range
    column: latitude
    min: -90.0
    max: 90.0
    severity: critical

  - name: speed_anomaly
    type: statistical
    column: speed
    z_score_threshold: 3.5
    min_samples: 100
```

```python
from datasentinel_stream import QualityRuleSet
from datasentinel_stream.rules.compiler import RuleCompiler

rule_set = QualityRuleSet.from_yaml("gps_rules.yaml")
validator, monitor = RuleCompiler.compile(rule_set)

for record in stream:
    violations = validator.check(record) + monitor.check(record)
```

Or describe rules in plain English:

```python
from datasentinel_stream.nlp_rules import NLPRuleGenerator

rules = NLPRuleGenerator().generate(
    topic="gps-events",
    description="GPS latitude must be between -90 and 90. Speed anomalies "
                "more than 3 standard deviations from normal should alert.",
)
```

**Five rule types:** `range` · `not_null` · `regex` · `null_rate` · `statistical`  
**Statistical engine:** Welford's online algorithm + EMA baseline blending — no historical data storage required  
**Correlator:** Groups violation bursts from the same column into a single `CorrelatedIncident` (reduces alert noise)

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          DataSentinel Platform                           │
│                                                                          │
│  Kafka Stream ──► [ Stream Monitor ]  ◄── learned baselines             │
│                   YAML/NLP rules │ z-score alerts │ incident correlation │
│                         │ dq-violations topic                           │
│                         ▼                                                │
│  Data Warehouse ─► [ Pipeline Agent ]  ◄── OpenMetadata lineage graph   │
│                    observe │ trace │ diagnose │ fix │ sandbox │ approve  │
│                         │                                                │
│  AI Enrichment ──► [ Semantic Validator ]  ◄── LLM-as-judge (Claude)   │
│                    factual │ hallucination │ drift │ label               │
│                         │                                                │
│                    Postgres ── Streamlit dashboards                      │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Quickstart

**Requirements:** Python 3.11+, Docker, [`uv`](https://docs.astral.sh/uv/)

```bash
git clone https://github.com/Mofasshara/datasentinel
cd datasentinel

# Install all packages
make dev

# Set your Anthropic API key
cp .env.example .env
# Edit .env → set ANTHROPIC_API_KEY=sk-ant-...

# Start infrastructure (Postgres + Kafka + Flink)
make infra

# Run all three demos back-to-back
make demo

# Or run individually
make demo-stream      # No API key needed — standalone GPS anomaly demo
make demo-semantic    # AI output validation (API key required)
make demo-agent       # Self-healing pipeline (API key required)

# Launch dashboards
make dashboard        # Unified platform home
make dashboard-semantic
make dashboard-agent
make dashboard-stream
```

---

## Repository Layout

```
DataSentinel/
├── packages/
│   ├── semantic-validator/     # Module 1 — pip install datasentinel-semantic
│   │   └── src/datasentinel_semantic/
│   │       ├── core/           # SemanticExpectation base + LLMJudge
│   │       ├── expectations/   # 4 built-in expectation types
│   │       ├── suite.py        # SemanticExpectationSuite runner
│   │       ├── storage/        # Postgres: pass rate history
│   │       ├── dbt_integration/# YAML-driven dbt hook
│   │       └── dashboard/      # Streamlit UI
│   │
│   ├── pipeline-agent/         # Module 2 — LangGraph self-healing agent
│   │   └── src/datasentinel_agent/
│   │       ├── state.py        # IncidentState TypedDict
│   │       ├── graph.py        # build_graph() + run_incident()
│   │       ├── agents/         # observer, lineage_tracer, diagnoser, remediator, sandbox
│   │       ├── tools/          # dbt_reader, openmetadata, duckdb_sandbox
│   │       ├── storage/        # Postgres incident repository
│   │       ├── api/            # FastAPI /incidents CRUD
│   │       └── ui/             # Streamlit HITL approval UI
│   │
│   └── stream-monitor/         # Module 3 — Flink stream quality
│       └── src/datasentinel_stream/
│           ├── rules/          # dsl.py (Pydantic YAML schema) + compiler.py
│           ├── operators/      # validator, anomaly_detector, correlator
│           ├── nlp_rules.py    # plain-English → YAML via Claude
│           ├── flink_job.py    # PyFlink job template
│           ├── storage/        # Postgres violations repository
│           └── dashboard/      # Streamlit live violation feed
│
├── shared/                     # Claude client, config, logging (shared)
├── infra/                      # Docker Compose — Kafka, Flink, Postgres, OpenMetadata
├── demo/
│   ├── app.py                  # Unified platform home dashboard
│   ├── run_all.py              # make demo entry point
│   └── scenarios/              # semantic_demo.py, agent_demo.py, stream_demo.py
├── .github/workflows/          # CI (lint, type check, tests) + PyPI publish
├── Makefile                    # make dev / infra / demo / dashboard
├── DEVELOPMENT.md              # Architecture decisions, gotchas, setup guide
└── ROADMAP.md                  # Full build plan with task tracking
```

---

## Stack

| Layer | Technology |
|-------|-----------|
| Language | Python 3.11+ |
| Agent orchestration | LangGraph |
| LLM | Claude API (claude-sonnet-4-6) with prompt caching |
| Data layer | DuckDB + PostgreSQL |
| Streaming | Apache Kafka + Apache Flink (PyFlink) |
| Pipeline integration | dbt Core |
| Metadata / Lineage | OpenMetadata |
| Validation framework | Great Expectations (Module 1 ships as GX extension) |
| Embeddings | Sentence Transformers (all-MiniLM-L6-v2) |
| API | FastAPI |
| UI | Streamlit |
| Packaging | uv workspaces |
| Infra | Docker Compose |

---

## Status

| Module | Status | Tests |
|--------|--------|-------|
| `datasentinel-semantic` | ✅ Built | 16/16 |
| `datasentinel-agent` | ✅ Built | 19/19 |
| `datasentinel-stream` | ✅ Built | 32/32 |
| Phase 4 — Platform integration | ✅ Built | — |

**Total: 67/67 tests passing across all modules. No API key required for tests.**

See [DEVELOPMENT.md](DEVELOPMENT.md) for architecture decisions, setup guide, and known gotchas.
