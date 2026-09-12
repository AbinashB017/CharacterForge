"""
graph/llm_client.py — Central LLM invocation with Groq key rotation and Gemini fallback.

Fallback architecture:
  GROQ_API_KEY_1 → GROQ_API_KEY_2 → GROQ_API_KEY_3 → Gemini (final fallback)

Two independent retry tracks:
  - 429 Rate Limit  : rotate to next key/provider (no retry on current key)
  - Non-429 (e.g. tool_use_failed / malformed JSON) : retry once on the SAME key,
    then raise RuntimeError — key rotation does NOT apply to parse errors.
"""
import os
from langchain_groq import ChatGroq
from langchain_google_genai import ChatGoogleGenerativeAI


def is_rate_limit(exc: Exception) -> bool:
    """Return True if the exception indicates a 429 / rate-limit response."""
    msg = str(exc).lower()
    return "429" in msg or "rate limit" in msg or "rate_limit" in msg or "too many requests" in msg


def invoke_with_fallback(schema_class, messages: list, node_type: str, label: str):
    """
    Invoke an LLM with structured output, rotating across Groq keys on 429s,
    and falling back to Gemini if all Groq keys are exhausted.

    Args:
        schema_class : Pydantic model to use with with_structured_output()
        messages     : prompt messages list
        node_type    : "generator" or "reviewer" — selects the correct model env var
                       and temperature (generator=0.7 for creative variance, reviewer=0)
        label        : human-readable name for log messages (e.g. "Generator")

    Raises:
        RuntimeError : if all keys/providers are exhausted, OR if a non-429 error
                       fails twice on the same key.
    """
    provider = os.environ.get("LLM_PROVIDER", "groq").lower()  # default: groq (not gemini)
    configs = []

    # ── Build Groq configs from up to 3 independent API keys ─────────────────
    if provider == "groq":
        model_env  = "GROQ_GENERATOR_MODEL" if node_type == "generator" else "GROQ_REVIEWER_MODEL"
        model_name = os.environ.get(model_env, "openai/gpt-oss-120b")
        # Generator: temperature=0.7 so revision iterations explore different directions
        # Reviewer : temperature=0  for deterministic, reproducible scoring
        temperature = 0.7 if node_type == "generator" else 0.0

        for i in range(1, 4):
            key = os.environ.get(f"GROQ_API_KEY_{i}", "").strip()
            if key and not key.startswith("your"):
                configs.append({
                    "provider": "groq",
                    "model":    model_name,
                    "key":      key,
                    "temp":     temperature,
                    "name":     f"Groq Key {i}",
                })

    # ── Always append Gemini as final fallback ────────────────────────────────
    gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if gemini_key and not gemini_key.startswith("your"):
        configs.append({
            "provider": "gemini",
            "model":    os.environ.get("GEMINI_MODEL", "gemini-2.5-flash"),
            "key":      gemini_key,
            "temp":     0.7 if node_type == "generator" else 0.0,
            "name":     "Gemini Fallback",
        })

    if not configs:
        raise RuntimeError(f"[{label}] No valid LLM API keys found in environment.")

    last_exc: Exception | None = None

    for idx, config in enumerate(configs):
        # ── Instantiate LLM ──────────────────────────────────────────────────
        if config["provider"] == "groq":
            llm = ChatGroq(
                model=config["model"],
                api_key=config["key"],
                temperature=config["temp"],
            )
        else:
            llm = ChatGoogleGenerativeAI(
                model=config["model"],
                google_api_key=config["key"],
                temperature=config["temp"],
            )

        structured_llm = llm.with_structured_output(schema_class)

        # ── Inner loop: retry once on the same key for non-429 errors ────────
        for attempt in range(2):
            try:
                return structured_llm.invoke(messages)
            except Exception as exc:  # noqa: BLE001
                last_exc = exc

                if is_rate_limit(exc):
                    # 429 — move on to the next key/provider immediately
                    next_idx = idx + 1
                    if next_idx < len(configs):
                        print(
                            f"[{label}] {config['name']} rate-limited — "
                            f"switching to {configs[next_idx]['name']}",
                            flush=True,
                        )
                    else:
                        print(
                            f"[{label}] {config['name']} rate-limited — "
                            f"no more fallbacks available.",
                            flush=True,
                        )
                    break  # exit inner loop, advance to next config

                else:
                    # Non-429 (e.g. malformed JSON / tool_use_failed)
                    if attempt == 0:
                        print(
                            f"[{label}] Parse/output error on {config['name']} "
                            f"(attempt 1) — retrying once on same key…",
                            flush=True,
                        )
                        # continue inner loop for attempt 1
                    else:
                        # Failed twice on same key with a non-429 error.
                        # Do NOT rotate keys — raise immediately so the node's
                        # error-handling path (audit-trail DB write) takes over.
                        raise RuntimeError(
                            f"{label} failed after 2 attempts (non-429). "
                            f"Last error: {last_exc}"
                        ) from last_exc

    # All configs exhausted via 429 rotation
    raise RuntimeError(
        f"{label} failed — all {len(configs)} key(s)/provider(s) returned rate-limit "
        f"errors. Last error: {last_exc}"
    )
