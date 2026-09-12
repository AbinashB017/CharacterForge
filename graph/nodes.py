"""
graph/nodes.py — All LangGraph node functions.

Nodes:
  input_validator_node  — validates brief fields, initialises loop counters,
                          inserts briefs + storyline_runs rows (incremental write)
  generator_node        — calls Gemini to draft a structured storyline,
                          inserts storyline_drafts row immediately after each draft
  reviewer_node         — calls Gemini to score the draft against the brief,
                          inserts review_feedback row immediately after each review
  finalizer_node        — updates storyline_runs.status/iteration_count/final_storyline_id

Error handling (applies to both LLM nodes):
  - Each call is attempted twice via _invoke_with_retry().
  - On generator failure after retry: treat as automatic NEEDS_REVISION with
    a descriptive feedback_text, so the loop terminates naturally via the cap.
  - On reviewer failure after retry: default to NEEDS_REVISION — never silently
    approve a draft that was not actually reviewed.

DB write policy — two tiers:
  BEST-EFFORT (intermediate writes: drafts, reviews):
    _db_write() — one attempt, silently swallowed on failure. A network blip
    is logged as [DB WARNING] but never crashes the graph. Data already lives
    in LangGraph state so the run terminates cleanly regardless.

  CRITICAL (finalizer status UPDATE only):
    _db_write_critical() — retries once after a 1 s pause. If both attempts
    fail, logs a loud [FINALIZER DB CRITICAL] warning so the failure is
    impossible to overlook. The graph does not crash but the operator knows
    the run's final status was not persisted.
"""
from __future__ import annotations

import os
import json
import time
from typing import Any

from dotenv import load_dotenv
from graph.llm_client import invoke_with_fallback
from sqlalchemy import text

from db.connection import SessionLocal
from graph.state import BriefState
from graph.schemas import StorylineOutput, ReviewOutput
from prompts.generator_prompt import build_generator_messages
from prompts.reviewer_prompt import build_reviewer_messages

load_dotenv()


# ── DB helpers ────────────────────────────────────────────────────────────────

def _db_write(sql: str, params: dict, label: str) -> Any:
    """
    Best-effort DB write — one attempt, silently swallowed on failure.
    Used for intermediate draft/review rows. Returns scalar result or None.
    """
    try:
        with SessionLocal() as db:
            result = db.execute(text(sql), params)
            db.commit()
            try:
                return result.scalar()
            except Exception:
                return None
    except Exception as exc:  # noqa: BLE001
        print(f"[DB WARNING] {label} write failed (non-fatal): {exc}", flush=True)
        return None


def _db_write_critical(sql: str, params: dict, label: str) -> Any:
    """
    Critical DB write — retries once after 1 s on failure.
    Used exclusively for the finalizer's storyline_runs UPDATE.
    On total failure: logs a loud [FINALIZER DB CRITICAL] warning so the
    operator cannot miss it. Does NOT crash the graph.
    Returns scalar result or None.
    """
    for attempt in range(2):
        try:
            with SessionLocal() as db:
                result = db.execute(text(sql), params)
                db.commit()
                try:
                    return result.scalar()
                except Exception:
                    return None
        except Exception as exc:  # noqa: BLE001
            if attempt == 0:
                print(
                    f"[DB WARNING] {label} write failed on attempt 1, retrying in 1s: {exc}",
                    flush=True,
                )
                time.sleep(1)
            else:
                print(
                    f"\n[FINALIZER DB CRITICAL] {label} failed after 2 attempts — "
                    f"run status NOT persisted to DB. Manual check required.\n"
                    f"Error: {exc}",
                    flush=True,
                )
    return None


# ── LLM invocation is handled by graph/llm_client.py ────────────────────────
# invoke_with_fallback(schema, messages, node_type, label) provides:
#   - Groq key rotation on 429 (Key1 → Key2 → Key3)
#   - Gemini as final fallback
#   - Retry-once on same key for non-429 parse/output errors


# ── Input Validator ────────────────────────────────────────────────────────────

def input_validator_node(state: BriefState) -> dict[str, Any]:
    """
    Validates that all required brief fields are present and non-empty.
    Initialises iteration counters and clears history lists.
    Writes one row to briefs and one placeholder row to storyline_runs.
    Does NOT call any LLM.
    """
    required = ["description", "tone", "audience", "format", "setting", "scene_count"]
    missing = [f for f in required if not state.get(f)]
    if missing:
        raise ValueError(f"Missing required brief fields: {missing}")

    max_iterations = int(os.environ.get("MAX_ITERATIONS", "3"))
    scene_count = int(state.get("scene_count", 4))
    core_trait = state.get("core_trait") or None

    # Insert brief — non-fatal if DB is unavailable
    brief_id = _db_write(
        """
        INSERT INTO briefs (description, tone, audience, format, setting, core_trait, scene_count)
        VALUES (:desc, :tone, :aud, :fmt, :setting, :trait, :sc)
        RETURNING id
        """,
        {
            "desc": state.get("description"), "tone": state.get("tone"),
            "aud": state.get("audience"), "fmt": state.get("format"),
            "setting": state.get("setting"), "trait": core_trait, "sc": scene_count
        },
        label="briefs INSERT",
    )

    # Insert placeholder run (status='running', final_storyline_id=NULL)
    run_id = _db_write(
        "INSERT INTO storyline_runs (brief_id, status) VALUES (:bid, 'running') RETURNING id",
        {"bid": brief_id},
        label="storyline_runs INSERT",
    )

    return {
        "brief_id": brief_id,
        "iteration": 0,
        "max_iterations": max_iterations,
        "drafts_history": [],
        "reviews_history": [],
        "current_draft": None,
        "latest_feedback": None,
        "verdict": None,
        "run_id": run_id,
        "final_storyline": None,
        "error": None,
        "scene_count": scene_count,
        "core_trait": core_trait,
    }


# ── Storyline Generator ────────────────────────────────────────────────────────

def generator_node(state: BriefState) -> dict[str, Any]:
    """
    Calls the LLM (with_structured_output → StorylineOutput) to draft a storyline.
    Uses invoke_with_fallback: Groq Key1 → Key2 → Key3 → Gemini on 429s;
    retries once on the same key for non-429 parse errors.

    On first call: generates from the brief alone.
    On revision calls (iteration > 0): injects latest_feedback into the prompt
      so the generator has specific, actionable targets.

    Increments state.iteration on every call (regardless of success/failure).
    On unrecoverable failure: writes a fallback review_feedback row and returns
      NEEDS_REVISION so the loop terminates naturally via the max_iterations cap.
    """
    messages = build_generator_messages(state)
    new_iteration = state.get("iteration", 0) + 1

    try:
        result: StorylineOutput = invoke_with_fallback(
            StorylineOutput, messages, "generator", "Generator"
        )
    except RuntimeError as exc:
        # Unrecoverable: write a fallback review row for the audit trail, then
        # surface as NEEDS_REVISION so the iteration cap handles termination.
        fb_text = (
            "Generator response was malformed and could not be parsed after retry. "
            "No draft was produced."
        )
        _db_write(
            """
            INSERT INTO review_feedback
                (run_id, iteration, verdict, overall_score, criteria_scores_json, feedback_text)
            VALUES (:run_id, :iter, 'NEEDS_REVISION', 1.0, :criteria, :fb)
            """,
            {
                "run_id": state.get("run_id"),
                "iter": new_iteration,
                "criteria": json.dumps([]),
                "fb": fb_text,
            },
            label="review_feedback fallback INSERT (generator failure)",
        )
        fallback_feedback: dict[str, Any] = {
            "verdict": "NEEDS_REVISION",
            "criteria_scores": [],
            "feedback_text": fb_text,
            "overall_score": 1.0,
        }
        return {
            "iteration": new_iteration,
            "current_draft": None,
            "drafts_history": list(state.get("drafts_history", [])),
            "verdict": "NEEDS_REVISION",
            "latest_feedback": fallback_feedback,
            "reviews_history": list(state.get("reviews_history", [])) + [fallback_feedback],
            "error": str(exc),
        }

    draft_dict = result.model_dump()

    _db_write(
        """
        INSERT INTO storyline_drafts (run_id, iteration, content_json)
        VALUES (:run_id, :iter, :content)
        """,
        {
            "run_id": state.get("run_id"),
            "iter": new_iteration,
            "content": json.dumps(draft_dict),
        },
        label="storyline_drafts INSERT",
    )

    # Brief sleep to avoid back-to-back free-tier rate limit hits between Generator
    # and Reviewer LLM calls. 2 seconds is enough for per-minute quota headroom.
    time.sleep(2)

    return {
        "iteration": new_iteration,
        "current_draft": draft_dict,
        "drafts_history": list(state.get("drafts_history", [])) + [draft_dict],
        "verdict": None,       # reset so reviewer sets it fresh
        "latest_feedback": None,
        "error": None,
    }


# ── Review / Critic Agent ──────────────────────────────────────────────────────

def reviewer_node(state: BriefState) -> dict[str, Any]:
    """
    Calls the LLM (with_structured_output → ReviewOutput) to score current_draft
    against the ORIGINAL brief on 5 concrete criteria.
    Uses invoke_with_fallback: Groq Key1 → Key2 → Key3 → Gemini on 429s;
    retries once on the same key for non-429 parse errors.

    If current_draft is None (generator failed), skips the LLM call and
    passes through the existing verdict/feedback from the generator failure.

    On unrecoverable failure: defaults to NEEDS_REVISION — never silently approves.
    """
    # Generator failed this iteration — no draft to review; pass through state
    if state.get("current_draft") is None:
        return {}

    messages = build_reviewer_messages(state)

    try:
        result: ReviewOutput = invoke_with_fallback(
            ReviewOutput, messages, "reviewer", "Reviewer"
        )
    except RuntimeError as exc:
        # Never silently approve — default to NEEDS_REVISION on parse failure.
        # Write a fallback row to review_feedback so the audit trail is complete.
        fb_text = (
            "Reviewer could not parse a response after retry. "
            "Defaulting to NEEDS_REVISION to prevent silent approval."
        )
        _db_write(
            """
            INSERT INTO review_feedback
                (run_id, iteration, verdict, overall_score, criteria_scores_json, feedback_text)
            VALUES (:run_id, :iter, 'NEEDS_REVISION', 1.0, :criteria, :fb)
            """,
            {
                "run_id": state.get("run_id"),
                "iter": state["iteration"],
                "criteria": json.dumps([]),
                "fb": fb_text,
            },
            label="review_feedback fallback INSERT (reviewer failure)",
        )
        fallback_feedback: dict[str, Any] = {
            "verdict": "NEEDS_REVISION",
            "criteria_scores": [],
            "feedback_text": fb_text,
            "overall_score": 1.0,
        }
        return {
            "verdict": "NEEDS_REVISION",
            "latest_feedback": fallback_feedback,
            "reviews_history": list(state.get("reviews_history", [])) + [fallback_feedback],
            "error": str(exc),
        }

    feedback_dict = result.model_dump()

    # Calculate overall_score deterministically in code — NOT by the LLM.
    # We use a simple mean of the 5 criteria scores. This is consistent with the
    # strict reviewer design: the score is a reflection of the criteria, not a
    # separate LLM opinion that could contradict them.
    scores = [c.score for c in result.criteria_scores]
    overall_score = sum(scores) / len(scores) if scores else 1.0
    feedback_dict["overall_score"] = overall_score

    _db_write(
        """
        INSERT INTO review_feedback
            (run_id, iteration, verdict, overall_score, criteria_scores_json, feedback_text)
        VALUES (:run_id, :iter, :verdict, :score, :criteria, :fb)
        """,
        {
            "run_id": state.get("run_id"),
            "iter": state["iteration"],
            "verdict": feedback_dict["verdict"],
            "score": overall_score,
            "criteria": json.dumps(feedback_dict.get("criteria_scores", [])),
            "fb": feedback_dict["feedback_text"],
        },
        label="review_feedback INSERT",
    )

    return {
        "verdict": result.verdict,
        "latest_feedback": feedback_dict,
        "reviews_history": list(state.get("reviews_history", [])) + [feedback_dict],
        "error": None,
    }


# ── Finalizer ─────────────────────────────────────────────────────────────────

def finalizer_node(state: BriefState) -> dict[str, Any]:
    """
    Updates storyline_runs with the final status, iteration count, and
    final_storyline_id (the DB id of the last draft produced).

    The heavy lifting (draft + review rows) was already done incrementally by
    generator_node and reviewer_node — this is a lightweight single UPDATE.
    """
    iteration = state.get("iteration", 0)
    verdict = state.get("verdict")
    run_id = state.get("run_id")

    # Determine final status
    if state.get("error"):
        status = "error"
    elif verdict == "APPROVED":
        status = "approved"
    elif iteration >= state.get("max_iterations", 3):
        status = "max_iter_reached"
    else:
        status = "needs_revision"

    # Find the DB id of the most recent draft (may be None if generator always failed)
    final_draft_id: int | None = None
    if run_id:
        final_draft_id = _db_write(
            "SELECT id FROM storyline_drafts WHERE run_id = :run_id ORDER BY iteration DESC LIMIT 1",
            {"run_id": run_id},
            label="storyline_drafts SELECT (finalizer)",
        )
        # Critical write — retries once, distinct loud warning on failure.
        _db_write_critical(
            """
            UPDATE storyline_runs
            SET status = :status, iteration_count = :iter, final_storyline_id = :draft_id
            WHERE id = :run_id
            """,
            {
                "status": status,
                "iter": iteration,
                "draft_id": final_draft_id,
                "run_id": run_id,
            },
            label="storyline_runs UPDATE",
        )

    print(f"\n{'=' * 70}")
    print(f"FINALIZER  (Phase 3 - Run {run_id} updated)")
    print(f"{'=' * 70}")
    print(f"Total iterations : {iteration}")
    print(f"Final status     : {status}")

    draft = state.get("current_draft")
    if draft:
        print(f"Character        : {draft.get('character_name', 'N/A')}")
        print(f"Tagline          : {draft.get('tagline', 'N/A')}")
        print(f"Scene count      : {len(draft.get('scenes', []))}")
    else:
        print("No final draft   : generator failed on all iterations")

    if state.get("error"):
        print(f"\nError recorded   : {state['error']}")
    print("=" * 70 + "\n")

    return {
        "final_storyline": state.get("current_draft"),
    }
