# CharacterForge

AI-powered cartoon character storyline generator using an agentic Generator→Reviewer loop built with LangGraph, Groq (or Gemini), PostgreSQL, and LangSmith.

---

## What it does

Given a character brief (description, tone, target audience, format, setting), CharacterForge:

1. **Validates** the brief and initialises a database run record.
2. **Generates** a full structured storyline — origin, personality, world, scene arc, tagline.
3. **Reviews** the draft against 5 scored criteria (Tone Match, Brief Fidelity, Audience Appropriateness, Scene Count, Internal Consistency).
4. **Loops** — if the reviewer returns `NEEDS_REVISION`, the generator receives the feedback and produces a revised draft. This continues up to `MAX_ITERATIONS`.
5. **Finalises** — persists the approved (or best-effort) storyline to Postgres and returns the result to the UI.

Every run produces a named trace in LangSmith showing the full node-by-node execution with token counts, latency, and cost estimates.

---

## Project Structure

```
app.py                  # Streamlit entry point
graph/
  state.py              # BriefState TypedDict
  nodes.py              # All node functions + DB write helpers
  edges.py              # route_after_review() conditional edge
  build_graph.py        # StateGraph assembly + compile()
  schemas.py            # StorylineOutput, ReviewOutput Pydantic models
prompts/
  generator_prompt.py   # Generator system + user message builders
  reviewer_prompt.py    # Reviewer system + user message builders
db/
  connection.py         # SQLAlchemy engine (PgBouncer-compatible)
  schema.sql            # Table definitions
observability/
  tracing.py            # LangSmith env-var verification helper
tests/
  test_edges.py         # 8 unit tests for route_after_review()
docs/
  architecture.md       # Mermaid architecture diagram
  CODING_STANDARDS.md   # Design decisions and patterns
test1_matched.py        # Integration test — matched brief (expect APPROVED)
test2_mismatched.py     # Integration test — mismatched brief (expect revision loop)
requirements.txt
.env.example
```

---

## Setup

### 1. Clone and install dependencies

```bash
git clone <repo-url>
cd CharacterForge
pip install -r requirements.txt
```

### 2. Configure environment variables

Copy `.env.example` to `.env` and fill in your values:

```bash
cp .env.example .env
```

| Variable | Required | Description |
|---|---|---|
| `LLM_PROVIDER` | Yes | `groq` (default) or `gemini` |
| `GROQ_API_KEY` | If provider=groq | Groq API key |
| `GROQ_MODEL` | No | Defaults to `openai/gpt-oss-120b` |
| `GEMINI_API_KEY` | If provider=gemini | Google AI API key |
| `GEMINI_MODEL` | No | Defaults to `gemini-2.5-flash` |
| `DATABASE_URL` | Yes | PostgreSQL connection string (see note below) |
| `LANGCHAIN_TRACING_V2` | No | Set to `true` to enable LangSmith tracing |
| `LANGCHAIN_API_KEY` | If tracing=true | LangSmith API key |
| `LANGCHAIN_PROJECT` | No | LangSmith project name (default: `characterforge`) |
| `MAX_ITERATIONS` | No | Max generator/reviewer cycles (default: `3`) |

> **Supabase / PgBouncer note:** If using Supabase's Transaction Pooler, your `DATABASE_URL` should use port `6543`. The SQLAlchemy engine is pre-configured with `plan_cache_mode=force_custom_plan` to disable prepared statements, which are incompatible with PgBouncer transaction mode.

### 3. Set up the database

Run the schema against your PostgreSQL instance:

```bash
psql $DATABASE_URL -f db/schema.sql
```

Or copy-paste `db/schema.sql` into the Supabase SQL editor.

### 4. Run the Streamlit UI

```bash
streamlit run app.py
```

Open [http://localhost:8501](http://localhost:8501) in your browser.

---

## Provider selection

Switch between Groq and Gemini without touching source code:

```bash
# Use Groq (default — higher quota, recommended for iterative testing)
LLM_PROVIDER=groq

# Use Gemini (fallback — 20 RPD free tier, use for spot checks only)
LLM_PROVIDER=gemini
```

> **Why `openai/gpt-oss-120b`?** The 20B variant of this model inconsistently completes complex tool-call JSON for the reviewer schema (nested `criteria_scores` array + long `feedback_text`), resulting in `tool_use_failed` errors. The 120B model is reliable. See `CODING_STANDARDS.md §8` for full detail.

---

## Running tests

```bash
# Unit tests (no LLM/DB required)
pytest tests/ -v

# Integration tests (requires LLM API key + DB)
python test1_matched.py     # Expect: APPROVED within max_iterations
python test2_mismatched.py  # Expect: revision loop; may hit max_iterations
```

---

## LangSmith Observability

With `LANGCHAIN_TRACING_V2=true` set, every `graph.invoke()` call automatically produces a named trace in your LangSmith project. To view:

1. Log in at [smith.langchain.com](https://smith.langchain.com/)
2. Open **Projects → characterforge**
3. Each run appears by its `run_name` (e.g. `Test1-Matched-Jellyfish`, `UI-Funny-Kids-…`)
4. Click a trace to expand the child spans: `input_validator → generator → reviewer → … → finalizer`
5. Click any span to see the prompt, completion, token counts, latency, and cost estimate

> **Cost figures:** LangSmith detects the `openai/` prefix in the Groq model ID and estimates cost using OpenAI token rates as a proxy. The figure is directionally correct but is not Groq's actual billing rate.

---

## Assumptions made during the build

1. **Audience Appropriateness is a hard gate.** Any scene with violence, peril, or adult content for a toddler/child audience scores 1/5 and fails the iteration regardless of other criteria. This was an explicit design decision, not an LLM default.
2. **`overall_score` is computed in code**, not by the LLM. It is `min(criteria_scores)` — a single bad criterion fails the whole review. The LLM never outputs an `overall_score` field directly.
3. **The reviewer never silently approves** a draft it could not evaluate. If the reviewer LLM call fails after retry, it defaults to `NEEDS_REVISION` with a descriptive `feedback_text`.
4. **DB writes are best-effort for intermediate rows** (drafts, reviews) but retry-once for the finalizer's status UPDATE. A failed intermediate write is logged as `[DB WARNING]`; a failed finalizer UPDATE is logged as `[FINALIZER DB CRITICAL]`.
5. **Supabase Transaction Pooler** requires `plan_cache_mode=force_custom_plan` in the SQLAlchemy engine. This is set in `db/connection.py`.
6. **`brief_id` is set by the input_validator node** (not the caller). The `run_id` returned in state is the `storyline_runs.id`, not `briefs.id`.
