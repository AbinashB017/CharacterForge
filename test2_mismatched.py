"""
Phase 2/4 -- Test 2: Deliberately mismatched brief. Traces to LangSmith.
Audience = Toddlers (2-5) but description/setting implies dark/violent themes.
This should naturally trigger at least one NEEDS_REVISION cycle.
Run from project root: python test2_mismatched.py
"""
import os
import sys
import json

# Force UTF-8 output in Windows terminal
sys.stdout.reconfigure(encoding='utf-8')

from dotenv import load_dotenv
load_dotenv()  # MUST be before any langchain import so LANGCHAIN_TRACING_V2 is set

from graph.build_graph import build_graph



def print_trace(result: dict) -> None:
    drafts  = result.get("drafts_history", [])
    reviews = result.get("reviews_history", [])

    print()
    print("-" * 70)
    print("FINAL OUTCOME")
    print(f"  Total iterations : {result.get('iteration', 0)}")
    print(f"  Final verdict    : {result.get('verdict', 'UNKNOWN')}")
    if result.get("error"):
        print(f"  Error            : {result['error']}")

    for i in range(max(len(drafts), len(reviews))):
        print()
        print("=" * 70)
        print(f"  ITERATION {i + 1}")
        print("=" * 70)

        if i < len(drafts):
            d = drafts[i]
            print()
            print("  DRAFT:")
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
                    print(f"        {desc[:220]}{'...' if len(desc) > 220 else ''}")

        if i < len(reviews):
            r = reviews[i]
            print()
            print("  REVIEW:")
            print(f"    Verdict       : {r.get('verdict', 'N/A')}")
            print(f"    Overall score : {r.get('overall_score', 'N/A')}/5")
            print("    Criteria scores:")
            for c in r.get("criteria_scores", []):
                if isinstance(c, dict):
                    rat = c.get("rationale", "")
                    print(f"      {c.get('criterion','?')}: {c.get('score','?')}/5")
                    print(f"        {rat[:220]}{'...' if len(rat) > 220 else ''}")
            fb = r.get("feedback_text", "")
            print()
            print("    Feedback:")
            print(f"      {fb[:600]}{'...' if len(fb) > 600 else ''}")


# Deliberately mismatched: toddler audience + dark revenge/war themes
brief = {
    "description": (
        "A battle-scarred wolf warrior with glowing red eyes, jagged armour forged from "
        "enemy bones, and a broadsword called 'Grimfang' — driven by a burning thirst "
        "for revenge against the shadow demon army that massacred his pack"
    ),
    "tone": "Heroic",
    "audience": "Toddlers (2-5)",
    "format": "Short-form (2-5 min)",
    "setting": "Post-apocalyptic",
    "core_trait": "Rage-fuelled berserker strength that doubles when he witnesses destruction",
    "scene_count": 4,
}

print("=" * 70)
print("TEST 2 -- MISMATCHED BRIEF (dark warrior + Toddlers 2-5 audience)")
print("Expect: at least 1 NEEDS_REVISION due to audience mismatch")
print("=" * 70)
print(json.dumps(brief, indent=2))
print()

graph = build_graph()
result = graph.invoke(
    brief,
    config={
        "run_name": "Test2-Mismatched-Wolf-Warrior",
        "tags": ["phase4", "test2", "mismatched"],
        "metadata": {
            "test": "test2_mismatched",
            "model": os.environ.get("GROQ_MODEL", "unknown"),
            "provider": os.environ.get("LLM_PROVIDER", "gemini"),
            "expected_outcome": "needs_revision_or_max_iter",
        },
    },
)
print_trace(result)
print()
print(f"LangSmith run_id : {result.get('run_id', 'N/A')}  (cross-ref with DB)")
print("Test 2 complete.")
