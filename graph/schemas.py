"""
graph/schemas.py — Pydantic output models for LLM structured outputs.

Used with ChatGoogleGenerativeAI.with_structured_output() so Gemini's API
enforces the schema at the model level — no prompt-based JSON parsing,
no json.loads() fragility.

  StorylineOutput  — Generator agent output
  ReviewOutput     — Reviewer agent output
"""
from __future__ import annotations

from typing import List, Literal
from pydantic import BaseModel, Field


# ── Generator output ──────────────────────────────────────────────────────────

class Scene(BaseModel):
    scene_number: int = Field(
        description="Scene number in the arc, starting from 1"
    )
    title: str = Field(
        description="A short, evocative title for this scene (3-7 words)"
    )
    description: str = Field(
        description="What happens in this scene (2-4 sentences)"
    )


class StorylineOutput(BaseModel):
    character_name: str = Field(
        description="The character's name — should fit the brief description and tone"
    )
    origin: str = Field(
        description="The character's backstory and how they came to be (2-3 sentences)"
    )
    personality_beats: List[str] = Field(
        description="3-5 distinct personality traits or behavioral quirks"
    )
    world: str = Field(
        description="The world/setting the character inhabits (2-3 sentences)"
    )
    scenes: List[Scene] = Field(
        description=(
            "The complete scene-by-scene arc. "
            "MUST contain EXACTLY the number of scenes specified in scene_count — no more, no fewer."
        )
    )
    tagline: str = Field(
        description="A memorable one-liner tagline for the character/show (under 15 words)"
    )


# ── Reviewer output ───────────────────────────────────────────────────────────

class CriteriaScore(BaseModel):
    criterion: str = Field(
        description=(
            "Name of the criterion — must be exactly one of: "
            "'Tone Match', 'Brief Fidelity', 'Audience Appropriateness', "
            "'Scene Count', 'Internal Consistency'"
        )
    )
    score: int = Field(
        description="Score 1-5: 1=completely fails, 2=mostly fails, 3=partially meets, 4=mostly meets, 5=fully meets",
        ge=1,
        le=5,
    )
    rationale: str = Field(
        description=(
            "Specific, evidence-based explanation. "
            "Must cite specific scenes or lines from the draft. No vague generalities."
        )
    )


class ReviewOutput(BaseModel):
    verdict: Literal["APPROVED", "NEEDS_REVISION"] = Field(
        description=(
            "APPROVED if ALL five criteria meet their required thresholds. "
            "NEEDS_REVISION if ANY criterion fails — no exceptions."
        )
    )
    criteria_scores: List[CriteriaScore] = Field(
        description="Scores for all 5 criteria in order: Tone Match, Brief Fidelity, Audience Appropriateness, Scene Count, Internal Consistency"
    )
    feedback_text: str = Field(
        description=(
            "For NEEDS_REVISION: consolidated, actionable notes citing specific scenes. "
            "For APPROVED: confirmation of what each criterion did well."
        )
    )
