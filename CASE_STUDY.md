# DataSentinel — Portfolio Case Study

*Format: LinkedIn article / portfolio write-up. Copy and adapt as needed.*

---

## I Built the Data Quality Tool That Doesn't Exist Yet

Every company running AI in production has the same problem: **they have no idea whether the data their AI is generating is actually correct.**

You might have Great Expectations monitoring that your `ai_description` column is non-null and under 500 characters. But is the content right? Did the model hallucinate a product feature that doesn't exist? Is the tone drifting across runs as the model gets fine-tuned?

No existing tool answers those questions at pipeline scale. So I built one.

---

## The Market Research

Before writing a line of code, I did a full audit of the data reliability landscape:

- **Monte Carlo, Anomalo, Soda** — statistical anomaly detection on structured data. None of them have LLM-based semantic validation.
- **Great Expectations** — schema and statistical checks. Excellent for deterministic rules, no semantic understanding.
- **Collibra, Atlan** — data governance and cataloging. Not validation.
- **Monte Carlo Agent Observability** (launched Mar 2026) — validates AI *chatbot responses*, not AI-generated records in ETL pipelines.
- **Confluent `AI_DETECT_ANOMALIES`** (Q2 2026, TimesFM) — streaming anomaly detection, but Confluent Cloud-only. No open-source equivalent exists.
- **Acceldata, Databricks Genie Code** — pipeline code self-healing. Neither generates SQL fixes for bad *data content*.

Three gaps, confirmed open as of May 2026:
1. Semantic validation of AI-generated structured records
2. Full-loop agentic data incident resolution (detect → diagnose → fix → test → approve)
3. Portable, open-source Flink-native statistical stream quality

---

## What I Built

**DataSentinel** is a three-module platform targeting all three gaps.

### Module 1 — Semantic Validator

A Python library that runs Claude as an LLM judge on every AI-enriched column in your data pipeline. Ships as a Great Expectations-compatible extension.

```python
suite = SemanticExpectationSuite(name="product_quality")
suite.add(FactualConsistencyExpectation(column="ai_description", reference_column="spec_sheet"))
suite.add(HallucinationDetectionExpectation(column="ai_description", source_columns=["sku", "brand"]))
suite.add(SemanticDriftExpectation(column="ai_description", threshold=0.15))
result = suite.run(df)
```

The key insight: existing tools check *structure*, not *meaning*. An AI model can generate a grammatically perfect, non-null, correctly-typed string that is completely wrong. This module catches that.

**Technical decisions:**
- All LLM clients are lazy-initialized so tests run without an API key
- System prompt is sent with `cache_control: ephemeral` — repeated calls in the same pipeline run serve from Anthropic's prompt cache, cutting cost 80%+
- `SemanticDriftExpectation` uses Sentence Transformers (all-MiniLM-L6-v2) for embedding-based cosine similarity, no LLM call per record

### Module 2 — Self-Healing Pipeline Agent

A LangGraph multi-agent system: Observer → Lineage Tracer → Diagnoser → Remediator → DuckDB Sandbox → Human Approval.

When a dbt test fails:
1. Observer reads `run_results.json` and computes column statistics
2. Lineage Tracer walks the OpenMetadata graph upstream to find where the anomaly originated
3. Diagnoser (Claude with tool use) classifies the anomaly type: `null_spike`, `schema_drift`, `logic_error`, `volume_drop`, `distribution_shift`
4. Remediator (Claude) generates a targeted SQL patch
5. Sandbox (DuckDB in-memory) applies the patch and re-runs assertions. If they still fail, the agent iterates up to 3 times before escalating
6. A Streamlit HITL UI presents the incident, lineage, proposed SQL diff, and test results for one-click approval

**Technical decisions:**
- LangGraph `StateGraph` with a `TypedDict` flat state — LangGraph merges partial updates from each node automatically
- DuckDB sandbox is a context manager with a fresh `:memory:` connection per incident — no state leak between runs
- OpenMetadata client degrades to a mock lineage graph when the server is unreachable (standard in local dev)

### Module 3 — Stream Monitor

A portable PyFlink library for statistical anomaly detection on Kafka streams. Rules can be defined in YAML or plain English.

**Key technical design:** The operator chain (SchemaValidator, StatisticalMonitor, IncidentCorrelator) is pure Python — no Flink dependency in the core. PyFlink wraps them as a `ProcessFunction`. This means the library can run standalone, in tests, or in any Python environment, with Flink as an optional deployment target.

**Statistical engine:** Welford's online algorithm for O(1) space streaming mean/variance. After warmup (configurable `min_samples`), switches to an EMA baseline (α=0.05) so long-term legitimate drift doesn't cause permanent alerts — only sharp deviations fire.

**IncidentCorrelator:** Groups violations from the same (topic, column) within a 60-second window into a single `CorrelatedIncident`. A GPS sensor batch producing 30 corrupted records becomes one alert, not 30.

---

## Results

- **67/67 tests passing** across all three modules — zero API key required for any test
- **Standalone demo** runs in under 30 seconds, no Docker needed (Module 3)
- Full `make demo` command runs all three end-to-end demos back-to-back
- Published as installable Python packages (uv workspace monorepo)

---

## What I Learned

**Build for testability from day one.** The biggest architectural lesson was making every LLM client lazy. `LLMJudge()`, `ClaudeClient()`, `OpenMetadataClient()` — all of them defer settings loading until first use. This kept the entire test suite keyless and fast.

**Online algorithms are underappreciated.** Welford's algorithm for streaming mean/variance is a textbook result that most engineers never need — until they're building a stateful Flink operator that can't store historical records. It was the right tool for this problem.

**The gap between "detects a problem" and "fixes a problem" is a product.** Most data quality tools stop at detection. The LangGraph agent loop — diagnose, fix, test, iterate, present for approval — is where the actual value is. Users don't want alerts; they want resolved incidents.

---

## Stack

LangGraph · Claude API (prompt caching) · Welford's algorithm · Flink PyFlink · Apache Kafka · DuckDB · PostgreSQL · Great Expectations · Sentence Transformers · FastAPI · Streamlit · uv workspaces · Docker Compose

**GitHub:** [github.com/Mofasshara/datasentinel](https://github.com/Mofasshara/datasentinel)
