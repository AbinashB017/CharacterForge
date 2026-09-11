"""
prompts/generator_prompt.py — Prompt templates for the Storyline Generator Agent.

Design decisions:
  - System message: role + mandatory rules (brief constraints are non-negotiable).
  - User message: assembled from BriefState fields at runtime.
  - On revision iterations (iteration > 0), the reviewer's latest_feedback is
    injected prominently into the user message — formatted with scores and
    per-criterion rationale so the generator has specific things to fix.
  - Prompts live here, not in nodes.py, so they can be versioned independently.
"""
from __future__ import annotations

from typing import Any

from langchain_core.messages import SystemMessage, HumanMessage


GENERATOR_SYSTEM_PROMPT = """You are a creative cartoon character storyline writer for a professional animation studio.

Your job is to write a complete, vivid character storyline based on a creative brief.
You must follow ALL constraints in the brief exactly — no creative liberties that contradict the brief.

MANDATORY RULES — every one of these must be satisfied or the draft will be rejected:
1. Write EXACTLY the number of scenes specified in scene_count. Not one more, not one fewer.
2. Every scene, theme, and implied content must be 100% appropriate for the specified target audience.
   • Toddlers (2-5): zero peril, zero threat, gentle conflict only, simple vocabulary, happy resolution.
   • Kids (6-11): mild adventure allowed, but no violence, scary imagery, or adult concepts.
   • Tweens (12-15): complex emotions OK, but no graphic content or mature themes.
   • All Ages: apply Toddler (2-5) standard — the most restrictive.
3. The character's appearance, personality, and core trait must match the brief precisely.
   Physical details, powers, and quirks from the brief must appear meaningfully — not as footnotes.
4. The tone/mood must be consistent across ALL scenes, not just the first.
5. The setting/world must match the specified setting.
6. If a core trait/power is given, it must be central to the storyline — not an afterthought.

Be imaginative within these constraints. Memorable characters come from specific, vivid details."""


def build_generator_messages(state: dict[str, Any]) -> list:
    """
    Returns [SystemMessage, HumanMessage] for the generator LLM call.
    Chooses the first-generation or revision template based on iteration count.
    """
    return [
        SystemMessage(content=GENERATOR_SYSTEM_PROMPT),
        HumanMessage(content=_build_user_content(state)),
    ]


def _build_user_content(state: dict[str, Any]) -> str:
    description   = state.get("description", "")
    tone          = state.get("tone", "")
    audience      = state.get("audience", "")
    fmt           = state.get("format", "")
    setting       = state.get("setting", "")
    core_trait    = state.get("core_trait") or "None specified"
    scene_count   = state.get("scene_count", 4)
    iteration     = state.get("iteration", 0)
    latest_feedback = state.get("latest_feedback")

    brief_block = f"""CREATIVE BRIEF:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Character Description : {description}
Tone / Mood           : {tone}
Target Audience       : {audience}
Show Format           : {fmt}
Setting / World       : {setting}
Core Trait / Power    : {core_trait}
Number of Scenes      : {scene_count}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"""

    if iteration == 0 or not latest_feedback:
        # ── First generation ─────────────────────────────────────────────────
        return f"""Write a complete cartoon character storyline based on the following brief.

{brief_block}

Produce a rich, imaginative storyline that strictly satisfies every brief constraint above.
Include exactly {scene_count} scenes in the arc — no more, no fewer."""

    else:
        # ── Revision generation ───────────────────────────────────────────────
        feedback_text   = latest_feedback.get("feedback_text", "")
        overall_score   = latest_feedback.get("overall_score", "N/A")
        criteria        = latest_feedback.get("criteria_scores", [])

        criteria_lines = []
        for c in criteria:
            if isinstance(c, dict):
                criteria_lines.append(
                    f"  • {c.get('criterion', '?')} — {c.get('score', '?')}/5\n"
                    f"    {c.get('rationale', '')}"
                )
        criteria_block = (
            "\n".join(criteria_lines)
            if criteria_lines
            else "  (No per-criterion scores available)"
        )

        return f"""Write a REVISED cartoon character storyline based on the following brief.

{brief_block}

⚠️  REVISION REQUIRED — Your previous draft was reviewed and REJECTED.
Overall score: {overall_score}/5

You MUST make concrete, specific changes to address every point in the feedback below.
Do NOT resubmit a similar draft with only cosmetic changes — the reviewer will catch it.

REVIEWER FEEDBACK:
{feedback_text}

CRITERIA SCORES FROM PREVIOUS REVIEW:
{criteria_block}

Now write a corrected storyline that fixes every issue above.
Include exactly {scene_count} scenes in the arc — no more, no fewer."""
