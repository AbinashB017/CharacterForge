-- db/schema.sql — CharacterForge database schema
-- Run this once in Phase 3 (after DB connection is confirmed in Phase 1).
-- Supabase/Postgres compatible.

-- ── Briefs ────────────────────────────────────────────────────────────────────
-- One row per user form submission.
CREATE TABLE IF NOT EXISTS briefs (
    id            SERIAL PRIMARY KEY,
    description   TEXT        NOT NULL,
    tone          VARCHAR(50) NOT NULL,
    audience      VARCHAR(50) NOT NULL,
    format        VARCHAR(50) NOT NULL,
    setting       TEXT        NOT NULL,
    core_trait    TEXT,
    scene_count   INTEGER     NOT NULL DEFAULT 4,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── Storyline Runs ────────────────────────────────────────────────────────────
-- One row per Generate button click. Tracks overall run status and how many
-- iterations the loop took.
CREATE TABLE IF NOT EXISTS storyline_runs (
    id                  SERIAL PRIMARY KEY,
    brief_id            INTEGER     NOT NULL REFERENCES briefs(id),
    status              VARCHAR(20) NOT NULL DEFAULT 'running',
                        -- 'running' | 'approved' | 'max_iter_reached' | 'error'
    iteration_count     INTEGER     NOT NULL DEFAULT 0,
    final_storyline_id  INTEGER,    -- FK to storyline_drafts.id, set by Finalizer
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── Storyline Drafts ──────────────────────────────────────────────────────────
-- One row per generator call. content_json holds the full StorylineOutput dict.
CREATE TABLE IF NOT EXISTS storyline_drafts (
    id              SERIAL PRIMARY KEY,
    run_id          INTEGER     NOT NULL REFERENCES storyline_runs(id),
    iteration       INTEGER     NOT NULL,
    content_json    JSONB       NOT NULL,
    generated_by    VARCHAR(50) NOT NULL DEFAULT 'gemini-2.5-flash',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── Review Feedback ───────────────────────────────────────────────────────────
-- One row per reviewer call. criteria_scores_json holds the per-criterion scores.
CREATE TABLE IF NOT EXISTS review_feedback (
    id                    SERIAL PRIMARY KEY,
    run_id                INTEGER     NOT NULL REFERENCES storyline_runs(id),
    iteration             INTEGER     NOT NULL,
    verdict               VARCHAR(20) NOT NULL,  -- 'APPROVED' | 'NEEDS_REVISION'
    overall_score         NUMERIC(3,2) NOT NULL, -- Computed in code, not by LLM
    criteria_scores_json  JSONB       NOT NULL,
    feedback_text         TEXT        NOT NULL,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Add FK from storyline_runs to storyline_drafts
-- No DEFERRABLE needed because final_storyline_id allows NULLs. We insert NULL 
-- into storyline_runs first, create drafts later, and UPDATE the run at the end.
ALTER TABLE storyline_runs
    ADD CONSTRAINT fk_final_storyline
    FOREIGN KEY (final_storyline_id)
    REFERENCES storyline_drafts(id);
