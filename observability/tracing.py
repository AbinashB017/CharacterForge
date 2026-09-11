"""
observability/tracing.py — LangSmith tracing setup.

LangSmith auto-traces all LangChain/LangGraph calls when these env vars are set:
    LANGCHAIN_TRACING_V2=true
    LANGCHAIN_API_KEY=<your key>
    LANGCHAIN_PROJECT=<your project>

These are already in .env and loaded by load_dotenv() in app.py — no manual
callback wiring needed for basic node-level tracing.

This module exists as a central place to:
  1. Confirm tracing is active at startup (verify_tracing_config).
  2. Provide a run_name helper so each generation run appears in LangSmith
     with a meaningful name (e.g. "CharacterForge-run-42") rather than a UUID.

Phase 2 will call configure_run_metadata() when invoking the compiled graph
so each LangSmith trace is labeled with the brief's key fields.
"""
from __future__ import annotations

import os


def verify_tracing_config() -> None:
    """
    Logs a warning if LangSmith env vars are missing.
    Called once at app startup.
    """
    required = ["LANGCHAIN_TRACING_V2", "LANGCHAIN_API_KEY", "LANGCHAIN_PROJECT"]
    missing = [k for k in required if not os.getenv(k)]
    if missing:
        print(f"[Tracing] WARNING: missing env vars: {missing}. Tracing disabled.")
    else:
        project = os.getenv("LANGCHAIN_PROJECT")
        print(f"[Tracing] LangSmith tracing active — project: '{project}'")


def get_run_config(run_name: str) -> dict:
    """
    Returns a LangGraph invoke config dict with a human-readable run name.
    Pass this as the 'config' argument to graph.invoke(state, config=...).

    Example:
        config = get_run_config("CharacterForge-run-1")
        result = graph.invoke(initial_state, config=config)
    """
    return {
        "run_name": run_name,
        "tags": ["characterforge"],
    }
