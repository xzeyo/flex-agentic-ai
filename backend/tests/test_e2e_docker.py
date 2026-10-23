
import pytest
from pydantic import SecretStr

from app.agents.client import CrewAgents
from app.sandbox.docker_runner import DockerRunner
from app.schemas import RunRequest
from app.store import Store
from app.workflow import Workflow
from tests.conftest import ScriptedAgents
from tests.test_docker_runner import require_docker
from tests.test_provider import provider  # noqa: F401 - registers the local provider fixture


@pytest.mark.docker
async def test_real_crewai_and_docker_workflow(settings, request):
    client = require_docker(settings)
    client.close()
    url, calls = request.getfixturevalue("provider")
    settings.api_key = SecretStr("local-test-key")
    settings.base_url = url
    store = Store(settings.root)
    run_id = store.create(RunRequest(task="Build a calculator with addition"))["id"]
    runner = DockerRunner(settings, run_id)
    await Workflow(settings, store, CrewAgents(settings), runner).execute(run_id)
    result = store.get(run_id)
    assert result["state"] == "SUCCEEDED", result
    assert result["report"]["model_calls"] == 4
    assert len(calls) >= 4
    assert all(c["exit_code"] == 0 for c in result["report"]["checks"])
    assert not runner.cleanup_errors


@pytest.mark.docker
async def test_seeded_defect_is_corrected_against_real_pytest(settings):
    client = require_docker(settings)
    client.close()
    class SeededDefect(ScriptedAgents):
        async def invoke(self, role, context, schema, abort):
            result = await super().invoke(role, context, schema, abort)
            if role == "developer" and self.counts[role] == 1:
                result.files[0].content = result.files[0].content.replace("a + b", "a - b")
            return result
    store = Store(settings.root)
    run_id = store.create(RunRequest(task="Build a calculator with addition"))["id"]
    runner = DockerRunner(settings, run_id)
    await Workflow(settings, store, SeededDefect(), runner).execute(run_id)
    result = store.get(run_id)
    assert result["state"] == "SUCCEEDED", result
    assert result["iteration"] == 1
    history = result["report"]["history"]
    assert history[0]["checks"][1]["exit_code"] != 0
    assert history[1]["checks"][1]["exit_code"] == 0
