"""
Phase 2/4 — Test 1: Well-matched brief. Traces to LangSmith.
Run from project root: python test1_matched.py
"""
import os
import sys
import json
from dotenv import load_dotenv
load_dotenv()  # MUST be before any langchain import so LANGCHAIN_TRACING_V2 is set

# Force UTF-8 output in Windows terminal
sys.stdout.reconfigure(encoding='utf-8')

from graph.build_graph import build_graph


def print_trace(result: dict) -> None:
    drafts  = result.get("drafts_history", [])
    reviews = result.get("reviews_history", [])

    print("\n" + "-" * 70)
    print("FINAL OUTCOME")
    print(f"  Total iterations : {result.get('iteration', 0)}")
    print(f"  Final verdict    : {result.get('verdict', 'UNKNOWN')}")
    if result.get("error"):
        print(f"  Error            : {result['error']}")

    for i in range(max(len(drafts), len(reviews))):
        print("\n" + "=" * 70)
        print(f"  ITERATION {i + 1}")
        print("=" * 70)

        if i < len(drafts):
            d = drafts[i]
            print(f"\n  DRAFT:")
            print(f"    Character  : {d.get('character_name', 'N/A')}")
            print(f"    Origin     : {d.get('origin', '')[:200]}")
            print(f"    World      : {d.get('world', '')[:150]}")
            print(f"    Tagline    : {d.get('tagline', 'N/A')}")
            scenes = d.get("scenes", [])
            print(f"    Scene count: {len(scenes)}")
            for s in scenes:
                if isinstance(s, dict):
                    print(f"      Scene {s.get('scene_number','?')}: {s.get('title','N/A')}")
                    desc = s.get("description", "")
                    print(f"        {desc[:220]}{'...' if len(desc)>220 else ''}")

        if i < len(reviews):
            r = reviews[i]
            print(f"\n  REVIEW:")
            print(f"    Verdict       : {r.get('verdict', 'N/A')}")
            print(f"    Overall score : {r.get('overall_score', 'N/A')}/5")
            print(f"    Criteria scores:")
            for c in r.get("criteria_scores", []):
                if isinstance(c, dict):
                    rat = c.get("rationale", "")
                    print(f"      {c.get('criterion','?')}: {c.get('score','?')}/5")
                    print(f"        {rat[:220]}{'...' if len(rat)>220 else ''}")
            fb = r.get("feedback_text", "")
            print(f"\n    Feedback:")
            print(f"      {fb[:600]}{'...' if len(fb)>600 else ''}")


brief = {
    "description": (
        "A small, round, glowing blue jellyfish with six wiggly tentacles that light up "
        "different neon colors whenever she laughs — which she does a lot, even at her own jokes"
    ),
    "tone": "Funny",
    "audience": "Kids (6-11)",
    "format": "Short-form (2-5 min)",
    "setting": "Underwater world",
    "core_trait": (
        "Her laugh is contagious — when she giggles, her tentacles flash random colors "
        "and every fish nearby starts laughing too, even if they don't know why"
    ),
    "scene_count": 3,
}

print("=" * 70)
print("TEST 1 — MATCHED BRIEF (funny jellyfish, Kids 6-11, 3 scenes)")
print("=" * 70)
print(json.dumps(brief, indent=2))
print()

graph = build_graph()

# Pass run_name + metadata so this trace is labelled clearly in LangSmith.
# LangGraph creates ONE parent trace per invoke(), with each node as a child
# span. Multiple loop iterations produce multiple generator/reviewer spans
# nested under the same trace automatically.
result = graph.invoke(
    brief,
    config={
        "run_name": "Test1-Matched-Jellyfish",
        "tags": ["phase4", "test1", "matched"],
        "metadata": {
            "test": "test1_matched",
            "model": os.environ.get("GROQ_MODEL", "unknown"),
            "provider": os.environ.get("LLM_PROVIDER", "gemini"),
        },
    },
)
print_trace(result)
print(f"\nLangSmith run_id : {result.get('run_id', 'N/A')}  (cross-ref with DB)")
print("Test 1 complete.")
