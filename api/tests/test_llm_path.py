"""Model path with a fake LiteLLM completion: guards, caching and graceful fallback."""
import types

import litellm
import pytest
from fastapi.testclient import TestClient
from litellm.exceptions import Timeout

from app.main import app


def fake_response(text: str):
    message = types.SimpleNamespace(content=text)
    usage = types.SimpleNamespace(prompt_tokens=120, completion_tokens=30)
    return types.SimpleNamespace(choices=[types.SimpleNamespace(message=message)], usage=usage)


@pytest.fixture()
def model(monkeypatch):
    monkeypatch.setenv("LLM_MODEL", "openai/test-model")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    calls = []

    def install(responder):
        def completion(**kwargs):
            calls.append(kwargs)
            return responder(kwargs)
        monkeypatch.setattr(litellm, "completion", completion)
        return calls
    return install


def test_chat_uses_model_and_rejects_invented_codes(model):
    calls = model(lambda kw: fake_response("Take CS9L999 next term, it is perfect."))
    with TestClient(app) as client:
        r = client.post("/students/P-EE-MS/chat", json={"message": "How do I get better at research?", "session_id": "llm-1"}).json()
        assert calls, "the model was called for an open question"
        assert "CS9L999" not in r["answer"] and r["source"] == "deterministic"
        assert calls[0]["model"] == "openai/test-model" and calls[0]["temperature"] == 0


def test_chat_model_answer_and_cache(model):
    calls = model(lambda kw: fake_response("Read two papers a week with the three-pass method and summarise each."))
    with TestClient(app) as client:
        body = {"message": "Any tips on reading research papers?", "session_id": "llm-2"}
        first = client.post("/students/P-EE-MS/chat", json=body).json()
        assert first["source"] == "model" and "three-pass" in first["answer"]
        usage = client.get("/admin/llm-usage").json()
        assert any(p["purpose"] == "chat" and p["prompt_tokens"] > 0 for p in usage["by_purpose"])


def test_model_timeout_falls_back_without_breaking(model):
    def slow(_kw):
        raise Timeout(message="timed out", model="openai/test-model", llm_provider="openai")
    model(slow)
    with TestClient(app) as client:
        r = client.post("/students/P-ME-UPSC/chat", json={"message": "Explain federalism briefly", "session_id": "llm-3"})
        assert r.status_code == 200 and r.json()["source"] == "deterministic"
        plan = client.post("/students/P-ME-UPSC/plan")
        assert plan.status_code == 200 and plan.json()["constraint_checks"] == []


def test_goal_parsing_by_model_is_validated(model):
    model(lambda kw: fake_response('{"goal_id": "not_a_goal", "confidence": 0.99, "interests": ["hacking"]}'))
    with TestClient(app) as client:
        r = client.post("/goals/parse", json={"goal_text": "I want to crack GATE"}).json()
        assert r["goal_id"] == "gate" and r["parsed_by"] == "keywords"
