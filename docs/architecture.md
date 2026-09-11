# CharacterForge — System Architecture

```mermaid
flowchart TD
    User(["👤 User\n(Streamlit UI)"])

    subgraph UI ["Streamlit — app.py"]
        Form["Brief Form\n(description · tone · audience\nformat · setting · scene_count)"]
        Results["Results Panel\n(final storyline · revision history)"]
    end

    subgraph Graph ["LangGraph Pipeline — graph/"]
        Validator["input_validator_node\n• validates required fields\n• initialises iteration counter\n• sets max_iterations from env"]
        Generator["generator_node\n• builds prompt from brief + feedback\n• calls LLM with_structured_output(StorylineOutput)\n• retry-once on failure\n• best-effort draft write to DB"]
        Reviewer["reviewer_node\n• scores draft against 5 criteria\n• calls LLM with_structured_output(ReviewOutput)\n• retry-once on failure\n• best-effort review write to DB"]
        Route{"route_after_review\nAPPROVED or\niter ge max?"}
        Finalizer["finalizer_node\n• determines final status\n• critical UPDATE to DB (retry-once)"]
    end

    subgraph DB ["PostgreSQL — Supabase via PgBouncer"]
        Briefs[("briefs\n(1 row per run)")]
        Runs[("storyline_runs\n(status · iteration_count\nfinal_storyline_id)")]
        Drafts[("storyline_drafts\n(1 row per iteration · content_json)")]
        Reviews[("review_feedback\n(1 row per iteration · verdict · scores)")]
    end

    subgraph LangSmith ["LangSmith — smith.langchain.com"]
        Trace["One trace per graph.invoke()\nrun_name + tags + metadata\n─────────────────────\nChild spans:\ninput_validator\ngenerator x N\nreviewer x N\nfinalizer\n─────────────────────\nTokens · latency · cost estimate"]
    end

    User --> Form
    Form -->|"graph.invoke(brief, config)"| Validator
    Validator --> Generator
    Generator --> Reviewer
    Reviewer --> Route
    Route -->|"NEEDS_REVISION\nand iter lt max"| Generator
    Route -->|"APPROVED\nor iter ge max"| Finalizer
    Finalizer --> Results

    Validator -->|"INSERT brief row\nINSERT run (status=running)"| Briefs
    Validator --> Runs
    Generator -->|"INSERT draft row\nbest-effort"| Drafts
    Reviewer  -->|"INSERT review row\nbest-effort"| Reviews
    Finalizer -->|"UPDATE run status\nretry-once + loud warning on fail"| Runs

    Graph -.->|"LANGCHAIN_TRACING_V2=true\nauto-instrumented"| LangSmith
```

## Key Design Decisions

| Decision | Rationale |
|---|---|
| Single `BriefState` TypedDict | One object flows through all nodes; no hidden inter-node contracts |
| Incremental DB writes | Each draft/review committed immediately — partial failures leave a usable record |
| Two-tier DB write policy | Intermediate writes best-effort (`_db_write`); finalizer UPDATE retries once (`_db_write_critical`) |
| LangGraph conditional edge | Loop logic expressed as a pure routing function — no state mutation in the edge |
| `with_structured_output()` for both agents | Enforces schema at the model layer; no `json.loads()` fragility in application code |
| `run_name` in every `graph.invoke()` | Ensures all LangSmith traces are named, not anonymous `LangGraph` runs |
