"""End-to-end DataSentinel platform demo.

Runs all three module demos back-to-back and prints a unified summary.
Invoked by `make demo`.

Module 1 (semantic) and Module 2 (agent) require ANTHROPIC_API_KEY.
Module 3 (stream) runs standalone — no API key or Kafka needed.

If ANTHROPIC_API_KEY is not set, modules 1 and 2 are skipped with a clear
message explaining how to enable them.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from datetime import datetime

BOLD = "\033[1m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
CYAN = "\033[36m"
RESET = "\033[0m"


def _header(text: str) -> None:
    width = 62
    print(f"\n{BOLD}{CYAN}{'=' * width}{RESET}")
    print(f"{BOLD}{CYAN}  {text}{RESET}")
    print(f"{BOLD}{CYAN}{'=' * width}{RESET}\n")


def _section(text: str) -> None:
    print(f"\n{BOLD}── {text} {'─' * (54 - len(text))}{RESET}")


def _ok(text: str) -> None:
    print(f"{GREEN}  ✓ {text}{RESET}")


def _skip(text: str) -> None:
    print(f"{YELLOW}  ⚠ {text}{RESET}")


def _fail(text: str) -> None:
    print(f"{RED}  ✗ {text}{RESET}")


_SKIPPED = "skipped"


def _run_module(
    label: str,
    script: str,
    extra_args: list[str] | None = None,
    requires_api_key: bool = False,
    timeout: int = 120,
) -> tuple[bool | str, float]:
    """Run a demo script as a subprocess. Returns (True|False|'skipped', elapsed)."""
    if requires_api_key and not os.environ.get("ANTHROPIC_API_KEY"):
        _skip(f"{label} skipped — set ANTHROPIC_API_KEY to enable")
        return _SKIPPED, 0.0

    args = [sys.executable, script] + (extra_args or [])
    start = time.time()
    try:
        result = subprocess.run(
            args,
            capture_output=False,
            timeout=timeout,
            check=False,
        )
        elapsed = time.time() - start
        if result.returncode == 0:
            _ok(f"{label} completed in {elapsed:.1f}s")
            return True, elapsed
        else:
            _fail(f"{label} exited with code {result.returncode}")
            return False, elapsed
    except subprocess.TimeoutExpired:
        elapsed = time.time() - start
        _fail(f"{label} timed out after {timeout}s")
        return False, elapsed
    except Exception as exc:
        elapsed = time.time() - start
        _fail(f"{label} failed: {exc}")
        return False, elapsed


def main() -> None:
    _header("DataSentinel — End-to-End Platform Demo")
    print(f"  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    has_key = bool(os.environ.get("ANTHROPIC_API_KEY"))
    if has_key:
        _ok("ANTHROPIC_API_KEY detected — all modules will run")
    else:
        _skip("ANTHROPIC_API_KEY not set — Module 1 and 2 demos will be skipped")
        print("  Set it with: export ANTHROPIC_API_KEY=sk-ant-...")

    results: list[tuple[str, bool | str, float]] = []

    # ── Module 1 — Semantic Validator ─────────────────────────────────────────
    _section("Module 1 — Semantic Validator")
    print("  Validates AI-generated product descriptions for factual consistency,")
    print("  hallucinations, semantic drift, and label accuracy.\n")
    ok, t = _run_module(
        label="Semantic validator demo",
        script="demo/scenarios/semantic_demo.py",
        requires_api_key=True,
        timeout=180,
    )
    results.append(("Module 1 — Semantic Validator", ok, t))

    # ── Module 2 — Pipeline Agent ─────────────────────────────────────────────
    _section("Module 2 — Self-Healing Pipeline Agent")
    print("  Detects a simulated dbt failure, traces root cause through lineage,")
    print("  generates a SQL fix, validates in DuckDB, awaits approval.\n")
    ok, t = _run_module(
        label="Pipeline agent demo",
        script="demo/scenarios/agent_demo.py",
        requires_api_key=True,
        timeout=180,
    )
    results.append(("Module 2 — Pipeline Agent", ok, t))

    # ── Module 3 — Stream Monitor ─────────────────────────────────────────────
    _section("Module 3 — Real-Time Stream Monitor")
    print("  Processes 250 synthetic GPS events. After 120-record warmup,")
    print("  injects impossible latitude values. Violations detected in real time.\n")
    ok, t = _run_module(
        label="Stream monitor demo (standalone)",
        script="demo/scenarios/stream_demo.py",
        extra_args=["--standalone", "--records", "250", "--warmup", "120"],
        requires_api_key=False,
        timeout=60,
    )
    results.append(("Module 3 — Stream Monitor", ok, t))

    # ── Summary ───────────────────────────────────────────────────────────────
    _header("Demo Summary")

    passed = sum(1 for _, ok, _ in results if ok is True)
    skipped = sum(1 for _, ok, _ in results if ok == _SKIPPED)
    failed = sum(1 for _, ok, _ in results if ok is False)

    for label, ok, elapsed in results:
        if ok is True:
            print(f"  {GREEN}✓{RESET} {label:<40} {elapsed:.1f}s")
        elif ok == _SKIPPED:
            print(f"  {YELLOW}⚠{RESET} {label:<40} skipped (no API key)")
        else:
            print(f"  {RED}✗{RESET} {label:<40} failed")

    print()
    total = len(results)
    if failed == 0 and skipped == 0:
        print(f"{GREEN}{BOLD}  All {total} modules completed successfully.{RESET}")
    elif failed == 0:
        print(f"  {passed} passed · {skipped} skipped · {failed} failed")
    else:
        print(f"  {passed} passed · {skipped} skipped · {failed} failed")

    if not has_key:
        print(f"\n  {YELLOW}Tip: Set ANTHROPIC_API_KEY to see the LLM-powered demos.{RESET}")

    print(f"\n  Dashboards:")
    print(f"    make dashboard-semantic   # Module 1 Streamlit UI")
    print(f"    make dashboard-agent      # Module 2 HITL approval UI")
    print(f"    make dashboard-stream     # Module 3 live violation feed")
    print(f"    make dashboard            # Unified platform home\n")


if __name__ == "__main__":
    main()
