"""OpenMetadata REST API client for data lineage traversal.

Gracefully degrades to a mock lineage graph when the server is unreachable,
so the agent pipeline works in local development without full infrastructure.
"""
from __future__ import annotations

from typing import Any

import httpx

from datasentinel_shared.config import get_settings
from datasentinel_shared.logging import get_logger

log = get_logger(__name__)


class LineageNode:
    def __init__(self, name: str, fqn: str, node_type: str = "table") -> None:
        self.name = name
        self.fqn = fqn                   # fully qualified name: schema.table
        self.node_type = node_type       # table | view | model
        self.upstream: list["LineageNode"] = []

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "fqn": self.fqn,
            "node_type": self.node_type,
            "upstream": [u.to_dict() for u in self.upstream],
        }


class OpenMetadataClient:
    """Fetches data lineage from the OpenMetadata API (v1.5+)."""

    def __init__(
        self,
        host: str | None = None,
        token: str | None = None,
    ) -> None:
        self._host_override = host
        self._token_override = token

    def _get_headers(self) -> dict[str, str]:
        token = self._token_override
        if token is None:
            try:
                token = get_settings().openmetadata_token
            except Exception:
                token = ""
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    def _get_base(self) -> str:
        if self._host_override:
            return self._host_override.rstrip("/")
        try:
            return get_settings().openmetadata_host.rstrip("/")
        except Exception:
            return "http://localhost:8585"

    def get_lineage(self, table_fqn: str, depth: int = 3) -> dict[str, Any]:
        """Fetch upstream lineage for a table up to `depth` hops.

        Returns a dict representation of the lineage tree, or a mock
        if the server is unreachable.
        """
        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.get(
                    f"{self._get_base()}/api/v1/lineage/table/name/{table_fqn}",
                    headers=self._get_headers(),
                    params={"upstreamDepth": depth, "downstreamDepth": 0},
                )
                resp.raise_for_status()
                return self._parse_lineage(resp.json(), table_fqn)
        except Exception as exc:
            log.warning("openmetadata_unavailable", error=str(exc), table=table_fqn)
            return self._mock_lineage(table_fqn)

    def _parse_lineage(self, data: dict[str, Any], root_fqn: str) -> dict[str, Any]:
        """Convert OpenMetadata lineage response to a simplified dict."""
        nodes: dict[str, dict[str, Any]] = {}
        edges: list[dict[str, str]] = []

        for node in data.get("nodes", []):
            fqn = node.get("fullyQualifiedName", "")
            nodes[fqn] = {
                "fqn": fqn,
                "name": node.get("name", fqn.split(".")[-1]),
                "node_type": node.get("type", "table").lower(),
            }

        for edge in data.get("upstreamEdges", []):
            edges.append({
                "from": edge.get("fromEntity", {}).get("fullyQualifiedName", ""),
                "to": edge.get("toEntity", {}).get("fullyQualifiedName", ""),
            })

        return {"root": root_fqn, "nodes": nodes, "edges": edges}

    def _mock_lineage(self, table_fqn: str) -> dict[str, Any]:
        """Return a plausible mock lineage graph for local dev / demo."""
        parts = table_fqn.split(".")
        schema = parts[0] if len(parts) > 1 else "analytics"
        table = parts[-1]

        source_table = f"raw.{table}_raw"
        staging_table = f"staging.stg_{table}"

        nodes = {
            table_fqn: {"fqn": table_fqn, "name": table, "node_type": "model"},
            staging_table: {"fqn": staging_table, "name": f"stg_{table}", "node_type": "model"},
            source_table: {"fqn": source_table, "name": f"{table}_raw", "node_type": "table"},
        }
        edges = [
            {"from": source_table, "to": staging_table},
            {"from": staging_table, "to": table_fqn},
        ]
        return {"root": table_fqn, "nodes": nodes, "edges": edges, "_mock": True}

    def get_upstream_tables(self, lineage: dict[str, Any]) -> list[str]:
        """Return list of upstream table FQNs in topological order (furthest first)."""
        root = lineage["root"]
        edges = lineage.get("edges", [])

        # Build adjacency: to → [froms] (reversed for upstream traversal)
        upstream_map: dict[str, list[str]] = {}
        for edge in edges:
            upstream_map.setdefault(edge["to"], []).append(edge["from"])

        visited: list[str] = []

        def dfs(node: str) -> None:
            for parent in upstream_map.get(node, []):
                if parent not in visited:
                    dfs(parent)
                    visited.append(parent)

        dfs(root)
        return visited  # furthest ancestors first
