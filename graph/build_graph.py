"""
graph/build_graph.py — Assembles and compiles the LangGraph StateGraph.

Graph topology:
    START
      ↓
    input_validator        ← validates brief fields, initialises counters
      ↓
    generator              ← drafts storyline from brief (+ feedback on revisions)
      ↓
    reviewer               ← scores draft; sets verdict + latest_feedback
      ↓
    [route_after_review]   ← conditional edge (graph/edges.py)
      │
      ├─ "generate" ───────────────────────────────────► generator  (NEEDS_REVISION + iter < max)
      │
      └─ "finalize" ───────────────────────────────────► finalizer ──► END
                                                          (APPROVED or iter >= max_iterations)

latest_feedback flows back into the generator prompt automatically via BriefState —
no special wiring needed; the generator_node reads state.latest_feedback directly.
"""
from __future__ import annotations

from langgraph.graph import StateGraph, START, END

from graph.state import BriefState
from graph.edges import route_after_review
from graph.nodes import (
    input_validator_node,
    generator_node,
    reviewer_node,
    finalizer_node,
)


def build_graph():
    """
    Builds and compiles the CharacterForge StateGraph.
    Returns a compiled LangGraph runnable (callable with .invoke(state)).
    """
    builder = StateGraph(BriefState)

    # ── Register nodes ────────────────────────────────────────────────────────
    builder.add_node("input_validator", input_validator_node)
    builder.add_node("generator",       generator_node)
    builder.add_node("reviewer",        reviewer_node)
    builder.add_node("finalizer",       finalizer_node)

    # ── Linear edges ─────────────────────────────────────────────────────────
    builder.add_edge(START,             "input_validator")
    builder.add_edge("input_validator", "generator")
    builder.add_edge("generator",       "reviewer")

    # ── Conditional edge: reviewer → generate | finalize ─────────────────────
    builder.add_conditional_edges(
        "reviewer",
        route_after_review,          # pure routing fn in graph/edges.py
        {
            "generate": "generator",  # loop back for revision
            "finalize": "finalizer",  # proceed to end
        },
    )

    # ── Finalizer → END ───────────────────────────────────────────────────────
    builder.add_edge("finalizer", END)

    return builder.compile()
