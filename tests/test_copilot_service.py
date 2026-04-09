"""Tests for the Reader3 Copilot summary service."""

from __future__ import annotations

import base64
from types import SimpleNamespace

import pytest

import copilot_service
from copilot_service import CopilotSummaryService


class _FakeSession:
    def __init__(self, content: str):
        self.content = content
        self.calls: list[dict[str, object]] = []
        self.disconnected = False

    async def send_and_wait(self, prompt, *, attachments=None, timeout=60.0):
        self.calls.append(
            {
                "prompt": prompt,
                "attachments": attachments,
                "timeout": timeout,
            }
        )
        return SimpleNamespace(data=SimpleNamespace(content=self.content))

    async def disconnect(self):
        self.disconnected = True


class _FakeClient:
    def __init__(self, session: _FakeSession, models=None):
        self.session = session
        self.models = models or []
        self.start_calls = 0
        self.stop_calls = 0
        self.create_session_calls: list[dict[str, object]] = []

    async def start(self):
        self.start_calls += 1

    async def stop(self):
        self.stop_calls += 1

    async def create_session(self, **kwargs):
        self.create_session_calls.append(kwargs)
        return self.session

    async def list_models(self):
        return self.models


@pytest.mark.asyncio
async def test_summarize_text_creates_toolless_summary_session(monkeypatch):
    fake_session = _FakeSession("Short summary")
    fake_client = _FakeClient(fake_session)
    monkeypatch.setattr(
        copilot_service,
        "PermissionHandler",
        SimpleNamespace(approve_all="approve-all"),
    )

    service = CopilotSummaryService(client=fake_client, model="gpt-4.1")

    result = await service.summarize_text(
        "Important passage",
        scope="selection",
        book_title="Test Book",
        chapter_title="Chapter 1",
    )

    assert result == "Short summary"
    assert fake_client.start_calls == 1
    assert fake_client.create_session_calls[0]["available_tools"] == []
    assert fake_client.create_session_calls[0]["model"] == "gpt-4.1"
    assert (
        fake_client.create_session_calls[0]["system_message"]["mode"]
        == "replace"
    )
    assert "Important passage" in fake_session.calls[0]["prompt"]
    assert fake_session.disconnected is True


@pytest.mark.asyncio
async def test_summarize_image_blob_base64_encodes_attachment(monkeypatch):
    fake_session = _FakeSession("Image summary")
    fake_client = _FakeClient(fake_session)
    monkeypatch.setattr(
        copilot_service,
        "PermissionHandler",
        SimpleNamespace(approve_all="approve-all"),
    )

    service = CopilotSummaryService(client=fake_client, model="gpt-4.1")

    await service.summarize_image_blob(
        b"png-bytes",
        mime_type="image/png",
        display_name="page-1.png",
        book_title="Test Book",
        chapter_title="Page 1",
    )

    attachment = fake_session.calls[0]["attachments"][0]
    assert attachment["type"] == "blob"
    assert attachment["mimeType"] == "image/png"
    assert attachment["displayName"] == "page-1.png"
    assert attachment["data"] == base64.b64encode(b"png-bytes").decode("ascii")


@pytest.mark.asyncio
async def test_get_status_reports_model_availability_and_vision_support():
    fake_session = _FakeSession("unused")
    model = SimpleNamespace(
        id="gpt-4.1",
        capabilities=SimpleNamespace(
            supports=SimpleNamespace(vision=True),
        ),
    )
    fake_client = _FakeClient(fake_session, models=[model])
    service = CopilotSummaryService(client=fake_client, model="gpt-4.1")

    status = await service.get_status()

    assert status["available"] is True
    assert status["authenticated"] is True
    assert status["supports_vision"] is True
    assert status["error"] is None


@pytest.mark.asyncio
async def test_get_status_reports_missing_configured_model():
    fake_session = _FakeSession("unused")
    fake_client = _FakeClient(
        fake_session,
        models=[SimpleNamespace(id="claude-haiku-4.5")],
    )
    service = CopilotSummaryService(client=fake_client, model="gpt-4.1")

    status = await service.get_status()

    assert status["available"] is False
    assert status["authenticated"] is True
    assert "not available" in status["error"].lower()


@pytest.mark.asyncio
async def test_start_reports_missing_sdk_when_not_installed(monkeypatch):
    monkeypatch.setattr(copilot_service, "CopilotClient", None)
    service = CopilotSummaryService()

    error = await service.start()

    assert "github-copilot-sdk is not installed" in error.lower()
