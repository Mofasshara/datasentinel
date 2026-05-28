"""Sandbox Agent — applies the proposed SQL fix in DuckDB and re-runs assertions."""
from __future__ import annotations

from typing import Any

import pandas as pd

from datasentinel_agent.state import IncidentState
from datasentinel_agent.tools.duckdb_sandbox import DuckDBSandbox
from datasentinel_shared.config import get_settings
from datasentinel_shared.logging import get_logger

log = get_logger(__name__)


def sandbox_node(state: IncidentState) -> dict[str, Any]:
    """Execute the proposed fix in an isolated DuckDB session and validate results."""
    fix_sql = state.get("proposed_fix_sql", "")
    failing_tests = state.get("failing_tests", [])
    iteration = state.get("iteration_count", 0)

    log.info("sandbox_started", iteration=iteration, fix_length=len(fix_sql))

    if not fix_sql:
        return {
            "sandbox_passed": False,
            "sandbox_output": {"error": "No fix SQL provided"},
            "status": "escalated",
        }

    try:
        sandbox_result = _run_sandbox(fix_sql, failing_tests, state)
        log.info(
            "sandbox_complete",
            passed=sandbox_result["passed"],
            tests_run=sandbox_result["tests_run"],
            tests_passed=sandbox_result["tests_passed"],
        )

        if sandbox_result["passed"]:
            return {
                "sandbox_passed": True,
                "sandbox_output": sandbox_result,
                "status": "pending_approval",
            }
        else:
            new_iteration = iteration + 1
            settings = get_settings()
            max_iter = settings.max_fix_iterations
            if new_iteration >= max_iter:
                log.warning("sandbox_max_iterations_reached", iterations=new_iteration)
                return {
                    "sandbox_passed": False,
                    "sandbox_output": sandbox_result,
                    "iteration_count": new_iteration,
                    "status": "escalated",
                }
            return {
                "sandbox_passed": False,
                "sandbox_output": sandbox_result,
                "iteration_count": new_iteration,
                "status": "fixing",   # will loop back to remediator
            }
    except Exception as exc:
        log.error("sandbox_error", error=str(exc))
        return {
            "sandbox_passed": False,
            "sandbox_output": {"error": str(exc)},
            "status": "escalated",
        }


def _run_sandbox(
    fix_sql: str,
    failing_tests: list[dict[str, Any]],
    state: IncidentState,
) -> dict[str, Any]:
    """Run the fix in DuckDB and return a sandbox result dict."""
    with DuckDBSandbox() as sandbox:
        # Load any available upstream data snapshots
        _load_demo_data(sandbox, state)

        # Execute the fix SQL to produce the corrected table
        try:
            fixed_df = sandbox.execute_fix(fix_sql)
        except Exception as exc:
            return {
                "passed": False,
                "tests_run": 1,
                "tests_passed": 0,
                "tests_failed": 1,
                "details": [{"name": "sql_execution", "passed": False, "error": str(exc), "failures": -1, "sample_failures": []}],
                "error": str(exc),
            }

        # Run assertions derived from the original failing tests
        result = sandbox.run_quick_assertions(fixed_df, failing_tests)
        return result.to_dict()


def _load_demo_data(sandbox: DuckDBSandbox, state: IncidentState) -> None:
    """Load demo parquet snapshots into the sandbox if they exist."""
    import os
    table_name = state.get("table_name", "")
    root_cause_table = (state.get("root_cause_table") or "").split(".")[-1]

    for name in {table_name, root_cause_table}:
        if not name:
            continue
        for path_template in [f"demo/synthetic_data/{name}.parquet", f"demo/synthetic_data/{name}_raw.parquet"]:
            if os.path.exists(path_template):
                try:
                    df = pd.read_parquet(path_template)
                    sandbox.load_table(name, df)
                except Exception as exc:
                    log.debug("demo_data_load_skipped", path=path_template, error=str(exc))
