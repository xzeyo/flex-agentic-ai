import asyncio
import json

from pydantic import ValidationError

from app.agents.client import AgentError, CrewAgents
from app.errors import SandboxError
from app.schemas import Plan, RunRequest
from app.store import Store
from app.workflow import Workflow
from tests.conftest import ScriptedAgents, ScriptedRunner, make_review


async def execute(settings, agents=None, runner=None):
    store = Store(settings.root)
    run = store.create(RunRequest(task="Build a calculator with addition"))
    await Workflow(settings, store, agents or ScriptedAgents(), runner or ScriptedRunner()).execute(run["id"])
    return store, store.get(run["id"])


async def test_four_roles_success_and_artifacts(settings):
    agents = ScriptedAgents()
    store, result = await execute(settings, agents)
    assert result["state"] == "SUCCEEDED"
    assert [role for role, _ in agents.calls] == ["planner", "developer", "debugger", "reviewer"]
    root = settings.root / "runs" / result["id"]
    assert json.loads((root / "manifest.json").read_text())
    assert (root / "source" / "calculator.py").exists()
    reviewer_context = agents.calls[-1][1]
    assert "+def add" in reviewer_context["actual_diff"]
    assert all(c["exit_code"] == 0 for c in reviewer_context["checks"])
    assert store.events(result["id"])[-1]["kind"] == "run.completed"


async def test_failure_correction_and_retest(settings):
    agents = ScriptedAgents()
    _, result = await execute(settings, agents, ScriptedRunner(failures=1))
    assert result["state"] == "SUCCEEDED"
    assert result["iteration"] == 1
    assert agents.counts["developer"] == 2
    assert agents.counts["debugger"] == 2
    assert result["report"]["history"][0]["checks"][0]["exit_code"] == 1


async def test_retry_budget_exhausted_is_failure(settings):
    agents = ScriptedAgents()
    _, result = await execute(settings, agents, ScriptedRunner(failures=100))
    assert result["state"] == "FAILED"
    assert result["iteration"] == 2
    assert agents.counts["developer"] == 3
    assert agents.counts["reviewer"] == 1


async def test_review_fix_then_approve(settings):
    agents = ScriptedAgents(reviews=[make_review(False), make_review()])
    _, result = await execute(settings, agents)
    assert result["state"] == "SUCCEEDED"
    assert result["review_iteration"] == 1
    assert agents.counts["developer"] == 2


async def test_review_budget_exhausted_and_critical_blocks(settings):
    agents = ScriptedAgents(reviews=[make_review(severity="critical")])
    _, result = await execute(settings, agents)
    assert result["state"] == "FAILED"
    assert result["review_iteration"] == 1
    assert agents.counts["reviewer"] == 2


async def test_cancel_during_execution(settings):
    store = Store(settings.root)
    run = store.create(RunRequest(task="Build a calculator"))
    runner = ScriptedRunner(hook=lambda: store.cancel(run["id"]))
    await Workflow(settings, store, ScriptedAgents(), runner).execute(run["id"])
    assert store.get(run["id"])["state"] == "CANCELLED"
    assert store.events(run["id"])[-2]["kind"] == "cleanup.completed"


async def test_packaging_error_cannot_be_success(settings, monkeypatch):
    from app.artifacts import Artifacts
    def broken_manifest(self):
        raise OSError("Disk full")
    monkeypatch.setattr(Artifacts, "manifest", broken_manifest)
    _, result = await execute(settings)
    assert result["state"] == "FAILED"
    assert "packaging failed" in result["summary"]
    final = settings.root / "runs" / result["id"] / "final-report.json"
    assert json.loads(final.read_text())["state"] == "FAILED"


async def test_timeout_evidence_is_not_success(settings):
    _, result = await execute(settings, runner=ScriptedRunner(timed_out=True))
    assert result["state"] == "TIMED_OUT"


async def test_run_deadline(settings):
    settings.run_timeout = 0.01
    class SlowAgents(ScriptedAgents):
        async def invoke(self, role, context, schema, abort):
            await asyncio.sleep(.02)
            return await super().invoke(role, context, schema, abort)
    _, result = await execute(settings, SlowAgents())
    assert result["state"] == "TIMED_OUT"


async def test_missing_credentials_fail_cleanly(settings):
    _, result = await execute(settings, CrewAgents(settings))
    assert result["state"] == "FAILED"
    assert "TEAM_API_KEY" in result["summary"]


async def test_provider_failure_bounded(settings):
    agents = ScriptedAgents(fail=AgentError("Provider unavailable"))
    _, result = await execute(settings, agents)
    assert result["state"] == "FAILED"
    assert agents.counts["planner"] == 2
    assert result["report"]["agent_retries"] == 1


async def test_provider_timeout_is_retried_once_then_terminal(settings):
    agents = ScriptedAgents(fail=TimeoutError())
    _, result = await execute(settings, agents)
    assert result["state"] == "TIMED_OUT"
    assert agents.counts["planner"] == 2
    assert result["report"]["agent_retries"] == 1


async def test_schema_repair_bounded(settings):
    error = None
    try:
        Plan.model_validate({"goal": "broken"})
    except ValidationError as exc:
        error = exc
    agents = ScriptedAgents(fail=error)
    _, result = await execute(settings, agents)
    assert result["state"] == "FAILED"
    assert agents.counts["planner"] == 2
    assert "validation twice" in result["summary"]


async def test_cleanup_failure_does_not_erase_original_failure(settings):
    class BrokenRunner(ScriptedRunner):
        def run(self, *args):
            self.cleanup_errors.append("Container removal failed")
            raise SandboxError("Docker unavailable")
    _, result = await execute(settings, runner=BrokenRunner())
    assert result["state"] == "FAILED"
    assert result["summary"] == "Docker unavailable"
    assert result["report"]["cleanup_errors"] == ["Container removal failed"]


async def test_model_call_budget(settings):
    settings.max_model_calls = 4
    _, result = await execute(settings, runner=ScriptedRunner(failures=1))
    assert result["state"] == "FAILED"
    assert result["report"]["model_calls"] == 4
