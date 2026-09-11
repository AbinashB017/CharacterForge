"""
graph/edges.py — Conditional routing logic for the LangGraph state graph.

This module contains ONLY the routing function — no LLM calls, no DB access.
This makes it easily unit-testable (see tests/test_edges.py).

Routing logic:
  After reviewer_node runs, route_after_review() decides:
    - "finalize"  → verdict is APPROVED, or iteration >= max_iterations
    - "generate"  → verdict is NEEDS_REVISION and iteration < max_iterations

  The max_iterations guard ensures the loop can never run forever even if
  the reviewer never approves.
"""
from __future__ import annotations

from graph.state import BriefState


def route_after_review(state: BriefState) -> str:
    """
    Conditional edge function called after reviewer_node.

    Returns:
        "finalize" — send to finalizer_node (approved or iteration cap hit)
        "generate" — send back to generator_node (needs revision, cap not hit)
    """
    verdict = state.get("verdict")
    iteration = state.get("iteration", 0)
    max_iterations = state.get("max_iterations", 3)

    if verdict == "APPROVED" or iteration >= max_iterations:
        return "finalize"
    return "generate"
