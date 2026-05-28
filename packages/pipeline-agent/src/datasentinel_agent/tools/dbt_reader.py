"""Reads dbt run results and manifest to extract failing tests and model SQL."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class DbtReader:
    """Reads dbt artifacts from a project directory.

    Supports dbt Core v1.5+ artifact formats (run_results.json, manifest.json).
    """

    def __init__(self, project_dir: str | Path) -> None:
        self.project_dir = Path(project_dir)
        self._manifest: dict[str, Any] | None = None

    @property
    def target_dir(self) -> Path:
        return self.project_dir / "target"

    @property
    def manifest(self) -> dict[str, Any]:
        if self._manifest is None:
            manifest_path = self.target_dir / "manifest.json"
            if manifest_path.exists():
                self._manifest = json.loads(manifest_path.read_text())
            else:
                self._manifest = {}
        return self._manifest

    def get_failing_tests(self) -> list[dict[str, Any]]:
        """Parse target/run_results.json and return all FAIL / ERROR test results."""
        results_path = self.target_dir / "run_results.json"
        if not results_path.exists():
            return []

        data = json.loads(results_path.read_text())
        failures = []
        for result in data.get("results", []):
            if result.get("status") in ("fail", "error"):
                unique_id = result.get("unique_id", "")
                node = self.manifest.get("nodes", {}).get(unique_id, {})
                failures.append({
                    "unique_id": unique_id,
                    "status": result["status"],
                    "node_name": node.get("name", unique_id),
                    "test_type": node.get("test_metadata", {}).get("name", "generic"),
                    "model": node.get("attached_node", ""),
                    "column_name": node.get("column_name", ""),
                    "failures": result.get("failures", 0),
                    "message": result.get("message", ""),
                    "compiled_code": node.get("compiled_code") or node.get("compiled_sql", ""),
                })
        return failures

    def get_model_sql(self, model_name: str) -> str:
        """Return the compiled SQL for a model by name."""
        for node_id, node in self.manifest.get("nodes", {}).items():
            if node.get("resource_type") == "model" and node.get("name") == model_name:
                return node.get("compiled_code") or node.get("compiled_sql", "")
        # Fallback: read from target/compiled/
        for sql_file in self.target_dir.rglob(f"{model_name}.sql"):
            return sql_file.read_text()
        return ""

    def get_model_schema(self, model_name: str) -> dict[str, Any]:
        """Return column metadata for a model."""
        for node in self.manifest.get("nodes", {}).values():
            if node.get("resource_type") == "model" and node.get("name") == model_name:
                return node.get("columns", {})
        return {}
