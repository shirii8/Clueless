"""Single gateway for every model call. All calls go through LiteLLM.

- Model, key and endpoint come only from LLM_MODEL / LLM_API_KEY / LLM_API_BASE.
- Responses are cached by a hash of (model, messages, temperature) so re-runs are consistent and
  repeated prompts cost no tokens.
- Each call is logged (purpose, tokens, latency, errors) for the admin usage report.
- Timeouts and rate limits are retried with backoff; callers always have a deterministic fallback.
"""
import hashlib
import json
import logging
import os
import threading
import time
from typing import Any

# LiteLLM would otherwise download its model price map at import time (an outbound call that is not
# to the configured provider). Use the bundled copy instead.
os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")

logger = logging.getLogger(__name__)


class ModelConfigurationError(RuntimeError):
    pass


class ModelUnavailableError(RuntimeError):
    pass


def model_enabled() -> bool:
    return bool(os.getenv("LLM_MODEL", "").strip() and os.getenv("LLM_API_KEY", "").strip())


def model_name() -> str:
    return os.getenv("LLM_MODEL", "").strip()


def _provider_arguments() -> dict[str, Any]:
    model = os.getenv("LLM_MODEL", "").strip()
    key = os.getenv("LLM_API_KEY", "").strip()
    if not model or not key:
        raise ModelConfigurationError("Set LLM_MODEL and LLM_API_KEY to enable model features.")
    arguments: dict[str, Any] = {"model": model, "api_key": key}
    api_base = os.getenv("LLM_API_BASE", "").strip()
    if api_base:
        arguments["api_base"] = api_base
    return arguments


def _cache_key(messages: list[dict[str, str]], temperature: float, purpose: str) -> str:
    payload = json.dumps({"m": model_name(), "msgs": messages, "t": temperature, "p": purpose}, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


_pending_calls: list[dict] = []
_pending_cache: dict[str, str] = {}
_memory_cache: dict[str, str] = {}
_lock = threading.Lock()


def _record(purpose: str, prompt_tokens: int, completion_tokens: int, latency_ms: int, cached: bool, ok: bool, error: str = "") -> None:
    with _lock:
        _pending_calls.append(dict(purpose=purpose, model=model_name(), prompt_tokens=prompt_tokens, completion_tokens=completion_tokens,
                                   latency_ms=latency_ms, cached=cached, ok=ok, error=error[:500]))


def _cache_get(key: str) -> str | None:
    if key in _memory_cache:
        return _memory_cache[key]
    try:
        from app.db import SessionLocal
        from app.models import LLMCache

        with SessionLocal() as session:
            row = session.get(LLMCache, key)
            if row:
                _memory_cache[key] = row.response
            return row.response if row else None
    except Exception:
        return None


def _cache_put(key: str, response: str) -> None:
    with _lock:
        _memory_cache[key] = response
        _pending_cache[key] = response


def flush_bookkeeping() -> None:
    """Persist call logs and cached responses. Called after each request (outside the request's
    transaction, so SQLite never sees two writers) and safe to call any time."""
    with _lock:
        calls, cache = list(_pending_calls), dict(_pending_cache)
        _pending_calls.clear()
        _pending_cache.clear()
    if not calls and not cache:
        return
    try:
        from app.db import SessionLocal
        from app.models import LLMCache, LLMCall

        with SessionLocal() as session:
            session.add_all(LLMCall(**c) for c in calls)
            for key, response in cache.items():
                session.merge(LLMCache(key=key, response=response))
            session.commit()
    except Exception:  # bookkeeping must never break a request
        logger.debug("Could not persist model bookkeeping", exc_info=True)


def complete(messages: list[dict[str, str]], temperature: float = 0, purpose: str = "general",
             max_tokens: int = 700, use_cache: bool = True) -> str:
    arguments = _provider_arguments()
    key = _cache_key(messages, temperature, purpose)
    if use_cache and temperature == 0:
        cached = _cache_get(key)
        if cached is not None:
            _record(purpose, 0, 0, 0, True, True)
            return cached

    import litellm
    from litellm import completion
    from litellm.exceptions import APIConnectionError, InternalServerError, RateLimitError, ServiceUnavailableError, Timeout

    try:
        litellm.telemetry = False
    except Exception:
        pass
    timeout = float(os.getenv("LLM_TIMEOUT_S", "25"))
    last_error: Exception | None = None
    for attempt in range(3):
        started = time.monotonic()
        try:
            response = completion(**arguments, messages=messages, temperature=temperature, timeout=timeout,
                                  max_tokens=max_tokens, num_retries=0)
            content = response.choices[0].message.content
            if not isinstance(content, str) or not content.strip():
                raise ValueError("The configured model returned an empty response.")
            usage = getattr(response, "usage", None)
            _record(purpose, getattr(usage, "prompt_tokens", 0) or 0, getattr(usage, "completion_tokens", 0) or 0,
                    int((time.monotonic() - started) * 1000), False, True)
            content = content.strip()
            if use_cache and temperature == 0:
                _cache_put(key, content)
            return content
        except (Timeout, RateLimitError, APIConnectionError, InternalServerError, ServiceUnavailableError) as error:
            last_error = error
            _record(purpose, 0, 0, int((time.monotonic() - started) * 1000), False, False, type(error).__name__)
            if attempt < 2:
                time.sleep(0.6 * (2 ** attempt))
        except Exception as error:  # authentication, bad request, malformed output
            _record(purpose, 0, 0, int((time.monotonic() - started) * 1000), False, False, f"{type(error).__name__}: {error}")
            raise ModelUnavailableError(f"The model call failed: {type(error).__name__}") from error
    raise ModelUnavailableError("The configured model is temporarily unavailable; retry shortly.") from last_error


def complete_json(messages: list[dict[str, str]], temperature: float = 0, purpose: str = "general", max_tokens: int = 700) -> Any:
    content = complete(messages, temperature, purpose, max_tokens)
    start, end = content.find("{"), content.rfind("}")
    if start < 0 or end < start:
        raise ValueError("The configured model did not return a JSON object.")
    return json.loads(content[start : end + 1])


def try_complete(messages: list[dict[str, str]], purpose: str, max_tokens: int = 500) -> str | None:
    """Best-effort call: returns None (never raises) so callers can fall back deterministically."""
    if not model_enabled():
        return None
    try:
        return complete(messages, 0, purpose, max_tokens)
    except Exception:
        logger.warning("Model call for %s failed; using deterministic fallback", purpose, exc_info=True)
        return None


def try_complete_json(messages: list[dict[str, str]], purpose: str, max_tokens: int = 500) -> Any | None:
    if not model_enabled():
        return None
    try:
        return complete_json(messages, 0, purpose, max_tokens)
    except Exception:
        logger.warning("Model JSON call for %s failed; using deterministic fallback", purpose, exc_info=True)
        return None
