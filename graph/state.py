"""
graph/state.py — Shared LangGraph state definition.

BriefState is the single TypedDict that flows through every node in the graph.
All fields are populated incrementally as the graph executes:
  - Input Validator  → initialises counters + history lists
  - Generator        → populates current_draft, appends to drafts_history, increments iteration
  - Reviewer         → populates latest_feedback + verdict, appends to reviews_history
  - Finalizer        → sets final_storyline, run_id (Phase 3: also writes to DB)

Field name changelog from Phase 1 skeleton:
  brief_description → description  (matches Phase 2 spec)
  show_format       → format       (matches Phase 2 spec)
  drafts            → drafts_history
  feedbacks         → reviews_history
  current_feedback  → latest_feedback
  [new] brief_id    → set by Finalizer in Phase 3
"""
from __future__ import annotations

from typing import Any, Optional
from typing_extensions import TypedDict


class BriefState(TypedDict):
    # ── Raw brief fields (set by caller before graph.invoke()) ───────────────
    brief_id: Optional[int]           # DB briefs.id — set by Finalizer (Phase 3)
    description: str                   # free-text character description
    tone: str                          # e.g. "Funny", "Heroic"
    audience: str                      # e.g. "Kids (6-11)"
    format: str                        # e.g. "Episodic series (11-22 min)"
    setting: str                       # e.g. "Fantasy kingdom"
    core_trait: Optional[str]          # optional quirk/power/flaw
    scene_count: int                   # number of scenes in the arc (default 4)

    # ── Agent loop state (initialised by input_validator_node) ───────────────
    iteration: int                     # how many generator runs have completed (starts 0)
    max_iterations: int                # hard cap from MAX_ITERATIONS env var (default 3)

    # ── Accumulated history (one entry per iteration) ─────────────────────────
    drafts_history: list[dict[str, Any]]    # all StorylineOutput dicts, in order
    reviews_history: list[dict[str, Any]]   # all ReviewOutput dicts, in order

    # ── Current-iteration outputs ─────────────────────────────────────────────
    current_draft: Optional[dict[str, Any]]    # latest StorylineOutput dict
    latest_feedback: Optional[dict[str, Any]]  # latest ReviewOutput dict
    verdict: Optional[str]                     # "APPROVED" | "NEEDS_REVISION"

    # ── Finalizer outputs ────────────────────────────────────────────────────
    run_id: Optional[int]                      # DB storyline_runs.id (Phase 3)
    final_storyline: Optional[dict[str, Any]]  # the approved/capped final draft
    error: Optional[str]                       # set on recoverable node failure
