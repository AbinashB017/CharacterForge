# CODING_STANDARDS.md — CharacterForge

## 1. Project / Module Layout

```
app.py              # Streamlit entry point only — no business logic
graph/              # LangGraph state, nodes, edges, graph assembly
prompts/            # Prompt strings and builder functions (no LLM calls)
db/                 # SQLAlchemy engine, session, schema SQL
observability/      # LangSmith config helpers
tests/              # Pytest unit tests
docs/               # Architecture diagram + this file
```

**Why this split:** Each layer has one responsibility. `prompts/` can be
reviewed and iterated without touching graph execution. `graph/edges.py` is
unit-testable without any LLM or DB setup. `db/` is the only place that
knows about PostgreSQL.

---

## 2. LangGraph State Typing

State is defined as a single `TypedDict` (`BriefState` in `graph/state.py`).

**Why TypedDict over Pydantic BaseModel for state:**
LangGraph's `StateGraph` accepts TypedDict natively. Using TypedDict keeps the
state definition simple and avoids double-validation (Pydantic models are used
for LLM *output* schemas via `with_structured_output`, not for state).

**Why all fields are Optional where applicable:**
Nodes populate fields incrementally. `current_draft` is `None` before the
generator runs, `run_id` is `None` before the finalizer runs, etc. This is
explicit rather than relying on `.get()` with implicit defaults.

**`brief_id` vs `run_id` — two distinct DB identifiers:**
`BriefState.brief_id` holds `briefs.id` — the primary key of the brief record
inserted into the `briefs` table. `BriefState.run_id` holds `storyline_runs.id`
— the primary key of the generation run. Both are set by `input_validator_node`
(not the Finalizer) immediately after the two INSERT statements, and both are
carried in state for the remainder of the graph. Downstream nodes use `run_id`
to attach draft/review rows; `brief_id` is stored in `storyline_runs` as a
foreign key but is not otherwise consumed by any downstream node.

---

## 3. Prompt Management

- **Location:** All prompt strings and builder functions live in `prompts/`.
  Nodes import and call builder functions — they never construct strings inline.
- **System vs user messages:** Generator and Reviewer use a two-message pattern:
  a fixed system message (role + output format) and a dynamically built user
  message (brief fields + optional prior feedback).
- **Structured output:** `with_structured_output(PydanticModel, method="json_schema")`
  is used for both agents. This enforces schema at the Gemini API level —
  no prompt-level JSON parsing, no `json.loads()` fragility.

---

## 4. Error Handling

| Failure type | Strategy |
|---|---|
| LLM network / timeout | Retry once (try/except around `invoke()`), then set `state["error"]` and route to finalizer with error status |
| Malformed / incomplete structured output | **Provider-dependent** — see Section 8 for detail. Gemini enforces the JSON schema natively at the API level, so malformed output is effectively impossible. Groq uses tool-calling, where the model generates tool arguments as free-form JSON; truncated or invalid arguments surface as `tool_use_failed`. Both cases are caught by the same retry-once-then-fallback path in `generator_node` and `reviewer_node`. |
| Max iteration cap | `route_after_review()` returns `"finalize"` when `iteration >= max_iterations` |
| DB write failure | Two-tier policy — **intermediate writes** (drafts, reviews) use `_db_write()`: one attempt, best-effort, `[DB WARNING]` on failure, graph never crashes. **Finalizer UPDATE** uses `_db_write_critical()`: retries once after 1 s; on total failure logs a distinct `[FINALIZER DB CRITICAL]` warning so the failure cannot be overlooked. Graph still does not crash, but operator is clearly alerted. |
| Missing env vars | `observability/tracing.py:verify_tracing_config()` warns at startup; `db/connection.py` raises `KeyError` on missing `DATABASE_URL` |

---

## 5. Testing Approach

- **`tests/test_edges.py`:** 8 unit tests for `route_after_review()`.
  Pure function, no mocks, covers all branches including the max-iteration guard.
- **Integration testing:** Run the graph end-to-end twice in Phase 2 —
  once with a matched brief (expect APPROVED on first pass) and once with a
  deliberately mismatched brief (expect ≥1 NEEDS_REVISION cycle).
- No DB mocks needed for unit tests — the routing logic has no DB dependency.
- **Scope note:** Unit tests are deliberately limited to routing/conditional-edge
  logic, which is the minimum testing standard explicitly stated in the assignment
  specification (Section 3.2). Node-function unit tests were not added; this is
  a documented scope decision, not an oversight.

---

## 6. Secrets / Config Handling

- All secrets in `.env` (gitignored). `.env.example` committed as a template.
- `python-dotenv` loads `.env` at startup via `load_dotenv()` in `app.py`.
- No hard-coded keys anywhere in source code.
- Configurable values (`MAX_ITERATIONS`, `GEMINI_MODEL`) in `.env` so they
  can be changed without touching source code.
- LangSmith is activated purely via env vars (`LANGCHAIN_TRACING_V2`,
  `LANGCHAIN_API_KEY`, `LANGCHAIN_PROJECT`) — no SDK initialization call needed.
- `observability/tracing.py` provides two helpers: `verify_tracing_config()`
  checks for the three required env vars at startup and prints either a
  confirmation or a `[Tracing] WARNING` listing any missing vars; `get_run_config()`
  returns a minimal `{"run_name": ..., "tags": [...]}` dict. Note: `app.py` and
  the test scripts build their own richer config dicts inline (adding `metadata`
  and additional `tags`) rather than calling `get_run_config()` — both approaches
  are valid since LangSmith reads the config at invoke time.

---

## 7. LangSmith Observability

**Trace structure per run:**
- `graph.invoke()` → **one parent trace** in LangSmith, named via `config["run_name"]`.
- Each node execution (`input_validator`, `generator`, `reviewer`, `finalizer`) → a **distinct child span**.
- Loop iterations (NEEDS_REVISION cycles) produce multiple `generator` and `reviewer` spans
  nested chronologically under the same parent trace — not a flat trace, not separate traces.

**What is visible per span:**
- Full prompt and completion text.
- Token counts (input / output).
- Latency.
- Cost estimate (see note below).

**Cost tracking:**
Cost figures **do appear** in LangSmith (e.g., `$0.0033` for ~10K tokens on `openai/gpt-oss-120b`).
LangSmith derives this by recognising the `openai/` prefix in the model ID and applying
OpenAI's published token rates as a proxy. This means the figure is a reasonable approximation
but is **not** Groq's actual billing rate for the model — Groq's pricing will differ.
Treat the cost column as directionally correct for comparison purposes, not as an exact invoice figure.

**Run naming convention:**
Every `graph.invoke()` call must pass a `config` dict with at minimum:
```python
config={
    "run_name": "<descriptive-name>",   # shows in LangSmith trace list
    "tags": ["phase", "test-id"],
    "metadata": {"model": ..., "provider": ...},
}
```
This ensures traces are distinguishable from anonymous `LangGraph` runs.

**Demo / recording note:**
The `characterforge` LangSmith project may contain unnamed `LangGraph` traces from earlier
debugging runs (including some with red error icons from Gemini rate-limit failures).
These are benign. When demonstrating or recording, filter by run name or scroll to the two
named traces: `Test1-Matched-Jellyfish` and `Test2-Mismatched-Wolf-Warrior`.

---

## 8. Multi-Provider Architecture

The active LLM provider is controlled by `LLM_PROVIDER` in `.env`:

| `LLM_PROVIDER` | Model | Notes |
|---|---|---|
| `groq` (default) | `openai/gpt-oss-120b` | Primary. Sufficient free-tier quota for iterative testing. |
| `gemini` | `gemini-2.5-flash` | Fallback. 20 RPD free-tier limit — use only for spot checks. |

**Why 120b over 20b:** The `openai/gpt-oss-20b` model inconsistently completes complex
tool-call responses (truncating the JSON mid-generation on the `ReviewOutput` schema).
The 120b model handles the nested `criteria_scores` array reliably.

**Structured output mode:** Both providers use `with_structured_output(PydanticModel)`.
Groq implements this via tool-calling (model generates tool arguments as free-form JSON;
Groq parses it). This is less strictly enforced than Gemini's native JSON schema mode —
malformed tool-call arguments surface as `tool_use_failed` and trigger the retry-once-then-fallback
path in `generator_node` and `reviewer_node`.
