"""
CharacterForge — Streamlit UI entry point.

Usage:
    streamlit run app.py

The Generate button is disabled until all required brief fields are filled.
Each run passes a run_name + metadata config to graph.invoke() so LangSmith
traces are named rather than appearing as anonymous "LangGraph" runs.
"""
import os
import time

import streamlit as st
from dotenv import load_dotenv

load_dotenv()  # Must precede any langchain/langgraph import

from graph.build_graph import build_graph  # noqa: E402 (after load_dotenv)

# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="CharacterForge",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Custom CSS ────────────────────────────────────────────────────────────────

st.markdown("""
<style>
    /* Typography */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

    /* Header gradient */
    .cf-header {
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
        border-radius: 16px;
        padding: 2rem 2.5rem;
        margin-bottom: 1.5rem;
        color: white;
    }
    .cf-header h1 { font-size: 2.4rem; font-weight: 700; margin: 0; }
    .cf-header p  { font-size: 1rem; opacity: 0.75; margin: 0.3rem 0 0; }

    /* Section cards */
    .cf-card {
        background: #f8f9fb;
        border: 1px solid #e4e6ea;
        border-radius: 12px;
        padding: 1.25rem 1.5rem;
        margin-bottom: 1rem;
    }
    .cf-card-dark {
        background: #1a1a2e;
        border: 1px solid #2d2d4e;
        border-radius: 12px;
        padding: 1.25rem 1.5rem;
        margin-bottom: 1rem;
        color: white;
    }

    /* Badge */
    .cf-badge-approved {
        display: inline-block;
        background: #16a34a;
        color: white;
        padding: 2px 12px;
        border-radius: 20px;
        font-size: 0.8rem;
        font-weight: 600;
    }
    .cf-badge-revision {
        display: inline-block;
        background: #d97706;
        color: white;
        padding: 2px 12px;
        border-radius: 20px;
        font-size: 0.8rem;
        font-weight: 600;
    }
    .cf-badge-maxiter {
        display: inline-block;
        background: #6b7280;
        color: white;
        padding: 2px 12px;
        border-radius: 20px;
        font-size: 0.8rem;
        font-weight: 600;
    }

    /* Tagline callout */
    .cf-tagline {
        font-size: 1.25rem;
        font-style: italic;
        color: #4338ca;
        border-left: 4px solid #4338ca;
        padding-left: 1rem;
        margin: 0.75rem 0;
    }

    /* Scene card */
    .cf-scene {
        border-left: 3px solid #0f3460;
        padding: 0.5rem 0 0.5rem 1rem;
        margin-bottom: 0.75rem;
    }
    .cf-scene-title { font-weight: 600; color: #0f3460; }

    /* Score bar */
    .cf-score { font-weight: 600; color: #16a34a; }
    .cf-score-low { font-weight: 600; color: #dc2626; }

    /* Divider */
    hr { border: none; border-top: 1px solid #e4e6ea; margin: 1.25rem 0; }
</style>
""", unsafe_allow_html=True)

# ── Header ────────────────────────────────────────────────────────────────────

st.markdown("""
<div class="cf-header">
    <h1>🎬 CharacterForge</h1>
    <p>AI-powered cartoon character storyline generator · Agentic review loop · LangGraph + Groq</p>
</div>
""", unsafe_allow_html=True)

# ── Brief form ────────────────────────────────────────────────────────────────

TONES     = ["Funny", "Heroic", "Dramatic", "Mysterious", "Heartwarming", "Action-Adventure"]
AUDIENCES = ["Toddlers (2-5)", "Kids (6-11)", "Teens (12-17)", "Family (all ages)"]
FORMATS   = ["Short-form (2-5 min)", "Long-form (10+ min)", "Episodic series (11-22 min)", "Feature length (45+ min)"]
SETTINGS  = [
    "Underwater world", "Space / sci-fi", "Fantasy kingdom", "Urban city",
    "Enchanted forest", "Post-apocalyptic", "School / academy", "Prehistoric world",
]

col_form, col_result = st.columns([1, 1], gap="large")

with col_form:
    st.subheader("✍️ Character Brief")

    description = st.text_area(
        "Character description *",
        placeholder="Describe your character's look, powers, and personality…",
        height=110,
        help="Required. Be specific — the more detail, the better the output.",
    )

    col1, col2 = st.columns(2)
    with col1:
        tone     = st.selectbox("Tone *",     ["— select —"] + TONES)
        audience = st.selectbox("Audience *", ["— select —"] + AUDIENCES)
    with col2:
        fmt     = st.selectbox("Format *",  ["— select —"] + FORMATS)
        setting = st.selectbox("Setting *", ["— select —"] + SETTINGS)

    core_trait = st.text_input(
        "Core trait / power / flaw (optional)",
        placeholder="e.g. 'Her laugh is contagious — nearby creatures laugh too'",
    )

    scene_count = st.slider("Number of scenes", min_value=2, max_value=6, value=4)

    # ── Validation — disable Generate until all required fields are set ────────
    required_ok = (
        description.strip() != ""
        and tone != "— select —"
        and audience != "— select —"
        and fmt != "— select —"
        and setting != "— select —"
    )

    if not required_ok:
        st.caption("⚠️ Fill in all required fields (*) to enable generation.")

    provider = os.environ.get("LLM_PROVIDER", "gemini").upper()
    if provider == "GROQ":
        gen_model = os.environ.get("GROQ_GENERATOR_MODEL", "unknown")
        rev_model = os.environ.get("GROQ_REVIEWER_MODEL", "unknown")
        model = f"Gen: {gen_model} | Rev: {rev_model}"
    else:
        model = os.environ.get("GEMINI_MODEL", "unknown")

    generate_clicked = st.button(
        "⚡ Generate Storyline",
        disabled=not required_ok,
        use_container_width=True,
        type="primary",
    )

    st.caption(f"Provider: **{provider}** · Model: `{model}` · Max iterations: {os.environ.get('MAX_ITERATIONS', 3)}")

# ── Generation ────────────────────────────────────────────────────────────────

if generate_clicked and required_ok:
    brief = {
        "description": description.strip(),
        "tone":        tone,
        "audience":    audience,
        "format":      fmt,
        "setting":     setting,
        "scene_count": scene_count,
    }
    if core_trait.strip():
        brief["core_trait"] = core_trait.strip()

    # Run name mirrors the test script convention for LangSmith
    char_slug = description.strip()[:30].replace(" ", "-").replace("/", "-")
    run_name  = f"UI-{tone[:6]}-{audience.split()[0]}-{char_slug}"

    with col_result:
        progress_bar = st.progress(0, text="Initialising pipeline…")
        status_box   = st.empty()

        def _update(msg: str, pct: int) -> None:
            progress_bar.progress(pct, text=msg)
            status_box.info(msg)

        _update("Validating brief…", 5)
        graph = build_graph()

        _update("Generating storyline draft…", 20)
        t0 = time.time()

        try:
            result = graph.invoke(
                brief,
                config={
                    "run_name": run_name,
                    "tags":     ["ui", tone.lower(), audience.split()[0].lower()],
                    "metadata": {
                        "source":   "streamlit_ui",
                        "model":    model,
                        "provider": provider,
                        "tone":     tone,
                        "audience": audience,
                    },
                },
            )
        except Exception as exc:
            progress_bar.empty()
            status_box.empty()
            st.error(f"Pipeline error: {exc}")
            st.stop()

        elapsed = time.time() - t0
        progress_bar.progress(100, text="Done!")
        status_box.empty()

        # Store result in session so it survives reruns
        st.session_state["last_result"] = result
        st.session_state["last_elapsed"] = elapsed

# ── Results panel ─────────────────────────────────────────────────────────────

result  = st.session_state.get("last_result")
elapsed = st.session_state.get("last_elapsed", 0)

with col_result:
    if result is None:
        st.markdown("""
        <div style="text-align:center; padding: 4rem 1rem; color: #9ca3af;">
            <div style="font-size: 3rem;">🎭</div>
            <p style="margin-top:0.5rem">Fill in the brief and click <strong>Generate Storyline</strong> to begin.</p>
        </div>
        """, unsafe_allow_html=True)
    else:
        verdict   = result.get("verdict", "UNKNOWN")
        iteration = result.get("iteration", 0)
        draft     = result.get("final_storyline") or result.get("current_draft")
        run_id    = result.get("run_id")
        error     = result.get("error")

        # ── Status bar ────────────────────────────────────────────────────────
        if verdict == "APPROVED":
            badge = '<span class="cf-badge-approved">✅ APPROVED</span>'
        elif iteration >= int(os.environ.get("MAX_ITERATIONS", 3)):
            badge = '<span class="cf-badge-maxiter">⏹ MAX ITERATIONS</span>'
        else:
            badge = '<span class="cf-badge-revision">🔄 NEEDS REVISION</span>'

        st.markdown(
            f"{badge} &nbsp; **{iteration} iteration{'s' if iteration != 1 else ''}** · "
            f"{elapsed:.1f}s · DB run #{run_id or 'N/A'}",
            unsafe_allow_html=True,
        )

        if error:
            st.warning(f"⚠️ {error}")

        if draft:
            # ── Character header ───────────────────────────────────────────────
            st.markdown(f"## {draft.get('character_name', 'Character')}")
            st.markdown(
                f'<div class="cf-tagline">"{draft.get("tagline", "")}"</div>',
                unsafe_allow_html=True,
            )

            # ── Core details ──────────────────────────────────────────────────
            tab_story, tab_world, tab_personality = st.tabs(["📖 Story", "🌍 World", "🧠 Personality"])

            with tab_story:
                st.markdown("**Origin**")
                st.write(draft.get("origin", ""))
                st.markdown("---")
                st.markdown("**Scene Arc**")
                for scene in draft.get("scenes", []):
                    st.markdown(
                        f'<div class="cf-scene">'
                        f'<div class="cf-scene-title">Scene {scene.get("scene_number","?")} — {scene.get("title","")}</div>'
                        f'<div style="margin-top:0.25rem">{scene.get("description","")}</div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

            with tab_world:
                st.write(draft.get("world", ""))

            with tab_personality:
                beats = draft.get("personality_beats", [])
                if beats:
                    for beat in beats:
                        st.markdown(f"- {beat}")
                else:
                    st.write("No personality beats recorded.")
        else:
            st.error("No draft was produced — the generator failed on all iterations.")

        # ── Revision History expander ─────────────────────────────────────────
        drafts  = result.get("drafts_history", [])
        reviews = result.get("reviews_history", [])

        if drafts or reviews:
            with st.expander(
                f"🔍 Revision History ({max(len(drafts), len(reviews))} iteration{'s' if max(len(drafts), len(reviews)) != 1 else ''})",
                expanded=False,
            ):
                for i in range(max(len(drafts), len(reviews))):
                    st.markdown(f"### Iteration {i + 1}")

                    if i < len(drafts):
                        d = drafts[i]
                        st.markdown(
                            f"**Draft — {d.get('character_name', 'N/A')}** · "
                            f"{len(d.get('scenes', []))} scenes · tagline: *{d.get('tagline', '')}*"
                        )

                    if i < len(reviews):
                        r = reviews[i]
                        v = r.get("verdict", "N/A")
                        badge_cls = "cf-badge-approved" if v == "APPROVED" else "cf-badge-revision"
                        st.markdown(
                            f'<span class="{badge_cls}">{v}</span> &nbsp; '
                            f'Overall: **{r.get("overall_score", "N/A")}/5**',
                            unsafe_allow_html=True,
                        )

                        criteria = r.get("criteria_scores", [])
                        if criteria:
                            cols = st.columns(len(criteria))
                            for ci, c in enumerate(criteria):
                                score = c.get("score", 0)
                                color = "#16a34a" if score >= 4 else ("#d97706" if score == 3 else "#dc2626")
                                cols[ci].markdown(
                                    f"<div style='text-align:center'>"
                                    f"<div style='font-size:0.7rem;color:#6b7280'>{c.get('criterion','')}</div>"
                                    f"<div style='font-size:1.4rem;font-weight:700;color:{color}'>{score}/5</div>"
                                    f"</div>",
                                    unsafe_allow_html=True,
                                )
                            show_detail = st.toggle(
                                "Show rationale & feedback",
                                key=f"detail_{i}",
                            )
                            if show_detail:
                                for c in criteria:
                                    st.markdown(f"**{c.get('criterion')}** ({c.get('score')}/5)")
                                    st.caption(c.get("rationale", ""))
                                st.markdown("**Overall Feedback**")
                                st.info(r.get("feedback_text", ""))

                    if i < max(len(drafts), len(reviews)) - 1:
                        st.markdown("---")

        # ── Footer meta ───────────────────────────────────────────────────────
        if run_id:
            st.caption(
                f"🔗 LangSmith trace: run name `{run_name if 'run_name' in dir() else 'UI run'}` · "
                f"Project: `characterforge` · DB run_id: {run_id}"
            )
