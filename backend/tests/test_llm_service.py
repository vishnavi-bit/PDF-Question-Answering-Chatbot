"""
Gemini service tests. The google-genai client is replaced by a fake object,
so these tests check what we SEND and how we handle replies, without any network call.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.core.config import get_settings
from app.services import llm_service
from app.services.llm_service import LLMError


class _RecordingModels:
    def __init__(self, reply_text):
        self.reply_text = reply_text
        self.kwargs = None

    def generate_content(self, **kwargs):
        self.kwargs = kwargs
        return SimpleNamespace(text=self.reply_text)


@pytest.fixture
def fake_models(monkeypatch):
    monkeypatch.setattr(get_settings(), "gemini_api_key", "test-key-not-real")
    monkeypatch.setattr(get_settings(), "gemini_model", "gemini-test-model")
    models = _RecordingModels('{"answer": "ok", "source_ids": []}')
    monkeypatch.setattr(llm_service, "_client", SimpleNamespace(models=models))
    return models


def test_request_uses_configured_model_and_system_instruction(fake_models):
    llm_service.complete("Be careful.", [{"role": "user", "content": "Hi"}], json_output=True)

    assert fake_models.kwargs["model"] == "gemini-test-model"
    config = fake_models.kwargs["config"]
    assert config.system_instruction == "Be careful."
    assert config.response_mime_type == "application/json"


def test_plain_text_mode_when_json_not_requested(fake_models):
    llm_service.complete("Sys", [{"role": "user", "content": "Summarise"}])
    assert fake_models.kwargs["config"].response_mime_type == "text/plain"


def test_assistant_messages_become_model_role(fake_models):
    llm_service.complete(
        "Sys",
        [
            {"role": "user", "content": "Q1"},
            {"role": "assistant", "content": "A1"},
            {"role": "user", "content": "Q2"},
        ],
    )
    roles = [content.role for content in fake_models.kwargs["contents"]]
    texts = [content.parts[0].text for content in fake_models.kwargs["contents"]]
    assert roles == ["user", "model", "user"]
    assert texts == ["Q1", "A1", "Q2"]


def test_missing_key_gives_503_before_any_request(monkeypatch):
    monkeypatch.setattr(get_settings(), "gemini_api_key", "")
    monkeypatch.setattr(llm_service, "_client", None)

    with pytest.raises(LLMError) as info:
        llm_service.complete("Sys", [{"role": "user", "content": "Hi"}])

    assert info.value.status_code == 503
    assert info.value.code == "not_configured"
    assert "GEMINI_API_KEY" in info.value.message


def test_empty_reply_is_reported_as_an_error(monkeypatch):
    monkeypatch.setattr(get_settings(), "gemini_api_key", "test-key-not-real")
    monkeypatch.setattr(llm_service, "_client", SimpleNamespace(models=_RecordingModels(None)))

    with pytest.raises(LLMError) as info:
        llm_service.complete("Sys", [{"role": "user", "content": "Hi"}])

    assert info.value.code == "empty_response"


def test_is_configured_reflects_the_key(monkeypatch):
    monkeypatch.setattr(get_settings(), "gemini_api_key", "")
    assert llm_service.is_configured() is False
    monkeypatch.setattr(get_settings(), "gemini_api_key", "x")
    assert llm_service.is_configured() is True
