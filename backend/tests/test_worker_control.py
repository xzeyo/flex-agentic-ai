import asyncio
from unittest.mock import AsyncMock

import pytest
from pydantic import SecretStr

from app.agents.client import CrewAgents
from app.agents.worker import safe_worker_error
from app.errors import RunCancelled
from app.schemas import Plan


def test_worker_reports_invalid_provider_key_without_echoing_secret():
    secret = "gsk_private-test-value"
    error = RuntimeError(f'GroqException - {{"message":"Invalid API Key","code":"invalid_api_key","token":"{secret}"}}')

    message = safe_worker_error(error, "groq")

    assert "Groq rejected TEAM_API_KEY" in message
    assert "active" in message
    assert secret not in message


def test_worker_reports_provider_rate_limit():
    error = RuntimeError("rate_limit_exceeded")

    assert "rate limit or quota" in safe_worker_error(error, "groq")


@pytest.mark.parametrize("reason", ["timeout", "cancel"])
async def test_model_worker_is_killed(settings, monkeypatch, reason):
    settings.api_key = SecretStr("test-key")
    settings.agent_timeout = .01
    process = AsyncMock()
    process.returncode = None
    process.stdin.write = lambda _: None
    process.stdin.close = lambda: None
    killed = []
    def kill():
        killed.append(True)
        process.returncode = -9
    process.kill = kill
    async def read(_):
        await asyncio.sleep(10)
        return b""
    process.stdout.read = read
    monkeypatch.setattr(asyncio, "create_subprocess_exec", AsyncMock(return_value=process))
    def abort():
        if reason == "cancel":
            raise RunCancelled()
    with pytest.raises(TimeoutError if reason == "timeout" else RunCancelled):
        await CrewAgents(settings).invoke("planner", {}, Plan, abort)
    assert killed
