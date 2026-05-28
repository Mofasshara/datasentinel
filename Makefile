.PHONY: install dev lint test test-semantic test-agent test-stream infra infra-full infra-down demo demo-semantic demo-agent demo-stream dashboard dashboard-semantic dashboard-agent dashboard-stream clean help

## ── Setup ────────────────────────────────────────────────────────────────────

install:           ## Install all workspace packages
	uv sync --all-packages

dev: install       ## Install with all dev extras
	uv sync --all-packages --all-extras
	uv pip install --python .venv/bin/python3 -e "packages/pipeline-agent" -e "packages/semantic-validator" -e "packages/stream-monitor" -e "shared"
	cp -n .env.example .env || true

## ── Quality ──────────────────────────────────────────────────────────────────

lint:              ## Run ruff lint + format check + mypy
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy shared/src packages/semantic-validator/src

fmt:               ## Auto-fix formatting
	uv run ruff check --fix .
	uv run ruff format .

test: test-semantic test-agent test-stream  ## Run all tests

test-semantic:     ## Run semantic-validator tests
	uv run pytest packages/semantic-validator/tests -v --tb=short

test-agent:        ## Run pipeline-agent tests
	uv run pytest packages/pipeline-agent/tests -v --tb=short

test-stream:       ## Run stream-monitor tests
	uv run pytest packages/stream-monitor/tests -v --tb=short

## ── Infrastructure ───────────────────────────────────────────────────────────

infra:             ## Start core services: Postgres + Kafka + Flink + Kafka UI
	docker compose -f infra/docker-compose.yml up -d postgres zookeeper kafka kafka-ui flink-jobmanager flink-taskmanager

infra-full:        ## Start all services including OpenMetadata (slow first start)
	docker compose -f infra/docker-compose.yml --profile full up -d

infra-down:        ## Stop all services
	docker compose -f infra/docker-compose.yml down

infra-clean:       ## Stop all services and delete volumes
	docker compose -f infra/docker-compose.yml down -v

infra-logs:        ## Tail all service logs
	docker compose -f infra/docker-compose.yml logs -f

## ── Demo ─────────────────────────────────────────────────────────────────────

demo:              ## Run all three module demos end-to-end
	uv run python demo/run_all.py

demo-semantic:     ## Run the semantic validator demo (API key required)
	uv run python demo/scenarios/semantic_demo.py

demo-agent:        ## Run the pipeline agent demo (API key required)
	uv run python demo/scenarios/agent_demo.py

demo-stream:       ## Run the stream monitor demo (standalone, no Kafka required)
	uv run python demo/scenarios/stream_demo.py --standalone

## ── Dashboard ─────────────────────────────────────────────────────────────────

dashboard-semantic:  ## Launch the semantic validator Streamlit dashboard
	uv run streamlit run packages/semantic-validator/src/datasentinel_semantic/dashboard/app.py

dashboard-agent:     ## Launch the pipeline agent approval UI
	uv run streamlit run packages/pipeline-agent/src/datasentinel_agent/ui/app.py

dashboard-stream:    ## Launch the stream monitor dashboard
	uv run streamlit run packages/stream-monitor/src/datasentinel_stream/dashboard/app.py

dashboard:           ## Launch the unified platform home dashboard
	uv run streamlit run demo/app.py

## ── Utility ──────────────────────────────────────────────────────────────────

clean:             ## Remove .venv, __pycache__, build artifacts
	rm -rf .venv
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +

help:              ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'
