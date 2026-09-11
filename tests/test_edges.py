"""
tests/test_edges.py — Unit tests for the conditional routing logic in graph/edges.py.

These tests cover route_after_review() exhaustively:
  - APPROVED verdict → always finalize
  - NEEDS_REVISION + below cap → generate (loop back)
  - NEEDS_REVISION + at cap (iter == max) → finalize (guard)
  - NEEDS_REVISION + above cap (iter > max) → finalize (guard)
  - Missing/None verdict → treated as NEEDS_REVISION

No mocks needed — route_after_review is a pure function with no I/O.
Run with: pytest tests/test_edges.py -v
"""
import pytest
from graph.edges import route_after_review


def make_state(**overrides) -> dict:
    """Helper: base state dict with sensible defaults, overridden by kwargs."""
    base = {
        "verdict": "APPROVED",
        "iteration": 1,
        "max_iterations": 3,
    }
    base.update(overrides)
    return base


# ── APPROVED cases ─────────────────────────────────────────────────────────────

def test_approved_routes_to_finalize():
    state = make_state(verdict="APPROVED", iteration=1, max_iterations=3)
    assert route_after_review(state) == "finalize"


def test_approved_on_first_iteration():
    state = make_state(verdict="APPROVED", iteration=0, max_iterations=3)
    assert route_after_review(state) == "finalize"


# ── NEEDS_REVISION below cap ───────────────────────────────────────────────────

def test_needs_revision_below_cap_routes_to_generate():
    state = make_state(verdict="NEEDS_REVISION", iteration=1, max_iterations=3)
    assert route_after_review(state) == "generate"


def test_needs_revision_first_iteration():
    state = make_state(verdict="NEEDS_REVISION", iteration=0, max_iterations=3)
    assert route_after_review(state) == "generate"


# ── Max-iteration guard ────────────────────────────────────────────────────────

def test_needs_revision_at_cap_routes_to_finalize():
    """Iteration equals max_iterations → cap hit → finalize."""
    state = make_state(verdict="NEEDS_REVISION", iteration=3, max_iterations=3)
    assert route_after_review(state) == "finalize"


def test_needs_revision_above_cap_routes_to_finalize():
    """Iteration exceeds max_iterations (shouldn't happen, but guard covers it)."""
    state = make_state(verdict="NEEDS_REVISION", iteration=5, max_iterations=3)
    assert route_after_review(state) == "finalize"


# ── Edge cases ─────────────────────────────────────────────────────────────────

def test_none_verdict_routes_to_generate():
    """None verdict treated as NEEDS_REVISION (not APPROVED)."""
    state = make_state(verdict=None, iteration=1, max_iterations=3)
    assert route_after_review(state) == "generate"


def test_max_iterations_of_one():
    """With max=1, any NEEDS_REVISION on iteration=1 should finalize."""
    state = make_state(verdict="NEEDS_REVISION", iteration=1, max_iterations=1)
    assert route_after_review(state) == "finalize"
