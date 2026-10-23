import asyncio
import json
import os
import sys
import time
from typing import TypeVar

from pydantic import BaseModel

from app.config import Settings

T = TypeVar("T", bound=BaseModel)


class AgentError(RuntimeError):
    pass


class CrewAgents:
    """An interruptible process per role keeps synchronous provider code off the event loop."""

    def __init__(self, settings: Settings):
        self.settings = settings

    async def invoke(self, role: str, context: dict, schema: type[T], abort) -> T:
        if not self.settings.api_key.get_secret_value():
            raise AgentError("Configure TEAM_API_KEY for the selected model provider.")
        payload = json.dumps({"role": role, "context": context, "model": self.settings.model,
                              "base_url": self.settings.base_url or None,
                              "timeout": self.settings.agent_timeout}).encode()
        if len(payload) > 1_500_000:
            raise AgentError("Model context quota exceeded")
        env = {**os.environ, "TEAM_API_KEY": self.settings.api_key.get_secret_value(),
               "OTEL_SDK_DISABLED": "true", "CREWAI_TRACING_ENABLED": "false"}
        process = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "app.agents.worker", stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL, env=env,
        )

        async def exchange() -> bytes:
            assert process.stdin and process.stdout
            process.stdin.write(payload)
            await process.stdin.drain()
            process.stdin.close()
            output = bytearray()
            while chunk := await process.stdout.read(16_384):
                output.extend(chunk)
                if len(output) > 1_000_000:
                    raise AgentError("Model output quota exceeded")
            await process.wait()
            return bytes(output)

        task = asyncio.create_task(exchange())
        started = time.monotonic()
        try:
            while not task.done():
                abort()
                if time.monotonic() - started > self.settings.agent_timeout:
                    raise TimeoutError("Model stage timed out")
                await asyncio.wait({task}, timeout=0.1)
            output = await task
            if process.returncode:
                try:
                    failure = json.loads(output).get("worker_error")
                except (json.JSONDecodeError, AttributeError, UnicodeDecodeError):
                    failure = None
                message = failure if isinstance(failure, str) and len(failure) <= 300 else (
                    "Model worker failed before returning a valid response. Check local diagnostics.")
                raise AgentError(message)
            return schema.model_validate_json(output)
        finally:
            if process.returncode is None:
                process.kill()
                await process.wait()
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)
