"""DuckDB in-process sandbox for testing proposed SQL fixes safely.

Creates an isolated in-memory DuckDB session, loads table snapshots,
applies the proposed fix, then re-runs the failing assertions.
"""
from __future__ import annotations

from typing import Any

import duckdb
import pandas as pd

from datasentinel_shared.logging import get_logger

log = get_logger(__name__)


class SandboxResult:
    def __init__(
        self,
        passed: bool,
        tests_run: int,
        tests_passed: int,
        tests_failed: int,
        details: list[dict[str, Any]],
        error: str = "",
    ) -> None:
        self.passed = passed
        self.tests_run = tests_run
        self.tests_passed = tests_passed
        self.tests_failed = tests_failed
        self.details = details
        self.error = error

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "tests_run": self.tests_run,
            "tests_passed": self.tests_passed,
            "tests_failed": self.tests_failed,
            "details": self.details,
            "error": self.error,
        }


class DuckDBSandbox:
    """Runs SQL fixes in an isolated DuckDB session."""

    def __init__(self) -> None:
        self._conn: duckdb.DuckDBPyConnection | None = None

    def __enter__(self) -> "DuckDBSandbox":
        self._conn = duckdb.connect(":memory:")
        return self

    def __exit__(self, *args: object) -> None:
        if self._conn:
            self._conn.close()

    @property
    def conn(self) -> duckdb.DuckDBPyConnection:
        if self._conn is None:
            raise RuntimeError("Use DuckDBSandbox as a context manager")
        return self._conn

    def load_table(self, table_name: str, df: pd.DataFrame) -> None:
        """Register a pandas DataFrame as a DuckDB table."""
        self.conn.register(table_name, df)
        log.debug("sandbox_table_loaded", table=table_name, rows=len(df))

    def execute_fix(self, fix_sql: str) -> pd.DataFrame:
        """Apply the proposed SQL fix and return the resulting DataFrame."""
        result = self.conn.execute(fix_sql).fetchdf()
        log.info("sandbox_fix_executed", rows=len(result))
        return result

    def run_assertions(
        self,
        table_name: str,
        assertions: list[dict[str, Any]],
    ) -> SandboxResult:
        """Run a list of data assertions against a table in the sandbox.

        Each assertion is a dict with:
          - name: str
          - sql: str  (a SELECT that returns rows only when the assertion FAILS)
          - description: str
        """
        details = []
        passed_count = 0

        for assertion in assertions:
            try:
                result = self.conn.execute(assertion["sql"]).fetchdf()
                failures = len(result)
                passed = failures == 0
                if passed:
                    passed_count += 1
                details.append({
                    "name": assertion["name"],
                    "passed": passed,
                    "failures": failures,
                    "description": assertion.get("description", ""),
                    "sample_failures": result.head(3).to_dict(orient="records") if not passed else [],
                })
            except Exception as exc:
                details.append({
                    "name": assertion["name"],
                    "passed": False,
                    "failures": -1,
                    "description": assertion.get("description", ""),
                    "error": str(exc),
                    "sample_failures": [],
                })

        total = len(assertions)
        return SandboxResult(
            passed=passed_count == total,
            tests_run=total,
            tests_passed=passed_count,
            tests_failed=total - passed_count,
            details=details,
        )

    def run_quick_assertions(self, df: pd.DataFrame, original_failures: list[dict[str, Any]]) -> SandboxResult:
        """Derive assertions from the original dbt test failures and run them on df."""
        self.load_table("_fixed_result", df)

        assertions: list[dict[str, Any]] = []
        for failure in original_failures:
            col = failure.get("column_name", "")
            test_type = failure.get("test_type", "")

            if test_type == "not_null" and col:
                assertions.append({
                    "name": f"not_null_{col}",
                    "sql": f'SELECT * FROM _fixed_result WHERE "{col}" IS NULL',
                    "description": f"Column {col} must have no null values",
                })
            elif test_type == "unique" and col:
                assertions.append({
                    "name": f"unique_{col}",
                    "sql": f'SELECT "{col}", COUNT(*) as cnt FROM _fixed_result GROUP BY "{col}" HAVING COUNT(*) > 1',
                    "description": f"Column {col} must have unique values",
                })
            elif test_type == "accepted_values" and col:
                accepted = failure.get("accepted_values", [])
                if accepted:
                    values_str = ", ".join(f"'{v}'" for v in accepted)
                    assertions.append({
                        "name": f"accepted_values_{col}",
                        "sql": f'SELECT * FROM _fixed_result WHERE "{col}" NOT IN ({values_str})',
                        "description": f"Column {col} must only contain accepted values",
                    })
            elif test_type == "relationships":
                assertions.append({
                    "name": f"row_count_positive",
                    "sql": "SELECT CASE WHEN COUNT(*) = 0 THEN 1 END AS fail FROM _fixed_result HAVING COUNT(*) = 0",
                    "description": "Result must have at least one row",
                })

        if not assertions:
            # Fallback: just check the fixed result has rows
            assertions.append({
                "name": "row_count_positive",
                "sql": "SELECT CASE WHEN COUNT(*) = 0 THEN 1 END AS fail FROM _fixed_result HAVING COUNT(*) = 0",
                "description": "Fixed result must contain data",
            })

        return self.run_assertions("_fixed_result", assertions)
