import asyncio
import time
from typing import Protocol, TypeVar

from pydantic import BaseModel, ValidationError

from app.agents.client import AgentError
from app.artifacts import Artifacts
from app.config import Settings
from app.errors import RunCancelled, RunTimedOut, SandboxError
from app.schemas import CheckResult, DebugReport, Implementation, Plan, Review, State
from app.store import Store

T = TypeVar("T", bound=BaseModel)


class Agents(Protocol):
    async def invoke(self, role: str, context: dict, schema: type[T], abort) -> T: ...


class Runner(Protocol):
    cleanup_errors: list[str]

    def run(self, source, profile: str, abort) -> CheckResult: ...


class Workflow:
    def __init__(self, settings: Settings, store: Store, agents: Agents, runner: Runner):
        self.settings, self.store, self.agents, self.runner = settings, store, agents, runner

    async def execute(self, run_id: str) -> None:
        started = time.monotonic()
        artifacts = Artifacts(self.settings.root / "runs" / run_id)
        checks: list[CheckResult] = []
        review: Review | None = None
        candidate: Implementation | None = None
        plan: Plan | None = None
        model_calls = 0
        agent_retries = 0
        diagnostics: DebugReport | None = None
        outcome = State.FAILED
        report: dict = {"verified": [], "limitations": [], "history": []}

        def abort() -> None:
            if self.store.get(run_id)["cancelled"]:
                raise RunCancelled()
            if time.monotonic() - started > self.settings.run_timeout:
                raise RunTimedOut()

        def stage(state: State) -> None:
            abort()
            self.store.transition(run_id, state)

        async def ask(role: str, context: dict, schema: type[T]) -> T:
            nonlocal model_calls, agent_retries
            self.store.event(run_id, "agent.started", f"{role} started", agent=role)
            call_started = time.monotonic()
            # One repair/retry attempt. The total model-call budget bounds both mechanisms.
            for attempt in range(2):
                abort()
                if model_calls >= self.settings.max_model_calls:
                    raise AgentError("Model call budget exhausted")
                model_calls += 1
                try:
                    output = await self.agents.invoke(role, context, schema, abort)
                    output = schema.model_validate(output)
                    abort()
                    self.store.event(run_id, "agent.completed", f"{role} completed", agent=role,
                                     duration_seconds=round(time.monotonic() - call_started, 3))
                    return output
                except ValidationError as exc:
                    context = {**context, "repair": "Previous output violated the schema. Return a fresh valid object.",
                               "validation_errors": [{"loc": list(e["loc"]), "type": e["type"]} for e in exc.errors()]}
                    if attempt:
                        raise AgentError("Model output failed schema validation twice") from exc
                    agent_retries += 1
                    self.store.event(run_id, "agent.retry", "Repairing invalid structured output", agent=role)
                except AgentError:
                    if attempt:
                        raise
                    agent_retries += 1
                    self.store.event(run_id, "agent.retry", "Retrying provider request", agent=role)
                    await asyncio.sleep(0.25)
                except TimeoutError:
                    if attempt:
                        raise
                    agent_retries += 1
                    self.store.event(run_id, "agent.retry", "Retrying timed-out model stage", agent=role)
                    await asyncio.sleep(0.25)
            raise AgentError("No validated model output")

        async def implement(feedback: dict) -> str:
            nonlocal candidate, diagnostics
            stage(State.IMPLEMENTING)
            candidate = await ask("developer", {"request": request, "plan": plan.model_dump() if plan else {},
                                                "previous_candidate": candidate.model_dump() if candidate else None,
                                                "feedback": feedback}, Implementation)
            patch = artifacts.candidate(candidate)
            round_id = len(report["history"])
            artifacts.write(f"history/candidate-{round_id}.json", candidate.model_dump())
            stage(State.PRECHECKING)
            checks.clear()
            for profile in ("lint", "test"):
                if profile == "test":
                    stage(State.TESTING)
                abort()
                self.store.event(run_id, "sandbox.started", f"Running {profile}", profile=profile)
                result = await asyncio.to_thread(self.runner.run, artifacts.source, profile, abort)
                result.log_ref = f"history/check-{round_id}-{profile}.json"
                checks.append(result)
                artifacts.write(f"history/check-{round_id}-{profile}.json", result.model_dump())
                self.store.event(run_id, "sandbox.completed", f"{profile}: {'passed' if result.passed else 'failed'}",
                                 **result.model_dump(exclude={"output"}))
                if result.timed_out:
                    raise RunTimedOut()
            report["history"].append({"round": round_id, "checks": [c.model_dump() for c in checks]})
            self.store.update(run_id, report={**report, "checks": [c.model_dump() for c in checks]})
            diagnostics = await ask("debugger", {"request": request, "candidate": candidate.model_dump(),
                                                   "checks": [c.model_dump() for c in checks]}, DebugReport)
            artifacts.write(f"history/diagnostics-{round_id}.json", diagnostics.model_dump())
            return patch

        async def test_fixes(patch: str) -> str:
            while not all(c.passed for c in checks):
                self.store.event(run_id, "test.failed", "Check evidence requires correction")
                if self.store.get(run_id)["iteration"] >= self.settings.max_fixes:
                    return patch
                stage(State.DEBUGGING)
                assert diagnostics is not None
                guidance = diagnostics
                iteration = self.store.get(run_id)["iteration"] + 1
                self.store.update(run_id, iteration=iteration)
                self.store.event(run_id, "iteration.started", "Applying test correction", iteration=iteration)
                artifacts.write(f"history/debug-{iteration}.json", guidance.model_dump())
                patch = await implement(guidance.model_dump())
            return patch

        request = self.store.get(run_id)["task"]
        try:
            stage(State.VALIDATING)
            artifacts.write("request.json", {"task": request, "language": "python"})
            stage(State.PLANNING)
            plan = await ask("planner", {"request": request, "constraints": "Python 3.12 standard library only; pytest and Ruff preinstalled. Include tests. No install/deployment/network."}, Plan)
            artifacts.write("plan.json", plan.model_dump())
            patch = await test_fixes(await implement({}))
            while True:
                stage(State.REVIEWING)
                review = await ask("reviewer", {"request": request, "plan": plan.model_dump(),
                                                "actual_diff": patch, "checks": [c.model_dump() for c in checks]}, Review)
                artifacts.write(f"history/review-{self.store.get(run_id)['review_iteration']}.json", review.model_dump())
                self.store.event(run_id, "review.completed", review.decision)
                if review.accepts(plan) or not all(c.passed for c in checks):
                    break
                if self.store.get(run_id)["review_iteration"] >= self.settings.max_review_fixes:
                    break
                self.store.update(run_id, review_iteration=self.store.get(run_id)["review_iteration"] + 1)
                patch = await test_fixes(await implement({"review": review.model_dump()}))
            stage(State.PACKAGING)
            accepted = all(c.passed for c in checks) and review.accepts(plan)
            report["verified"] = [f"{c.profile}: exit {c.exit_code}" for c in checks if c.passed]
            report["limitations"] = ["Generated tests and model review do not prove correctness or security.",
                                     *(candidate.known_limitations if candidate else []), *review.limitations]
            summary = "All required checks passed and review accepted." if accepted else "Run requires changes: failed checks or unresolved review requirements."
            self.store.update(run_id, summary=summary)
            outcome = State.SUCCEEDED if accepted else State.FAILED
        except RunCancelled:
            outcome = State.CANCELLED
            self.store.update(run_id, summary="Cancelled; incomplete results remain unverified.")
        except (RunTimedOut, TimeoutError):
            outcome = State.TIMED_OUT
            self.store.update(run_id, summary="Execution exceeded its time limit; incomplete results remain unverified.")
        except (AgentError, SandboxError, ValueError) as exc:
            outcome = State.FAILED
            self.store.update(run_id, summary=str(exc)[:500])
        except Exception:
            outcome = State.FAILED
            self.store.update(run_id, summary="Internal workflow error. Inspect server diagnostics and submit a new run.")
        finally:
            report.update({"checks": [c.model_dump() for c in checks],
                           "review": review.model_dump() if review else None,
                           "duration_seconds": round(time.monotonic() - started, 3),
                           "model_calls": model_calls, "agent_retries": agent_retries,
                           "cleanup_errors": self.runner.cleanup_errors})
            if self.runner.cleanup_errors:
                report["limitations"].extend(self.runner.cleanup_errors)
            if outcome == State.SUCCEEDED:
                try:
                    abort()
                except RunCancelled:
                    outcome = State.CANCELLED
                    self.store.update(run_id, summary="Cancelled before finalization.")
                except RunTimedOut:
                    outcome = State.TIMED_OUT
                    self.store.update(run_id, summary="Run deadline exceeded before finalization.")
            self.store.update(run_id, report=report)
            try:
                artifacts.write("test-report.json", [c.model_dump() for c in checks])
                if review:
                    artifacts.write("review-report.json", review.model_dump())
                artifacts.write("final-report.json", {**self.store.get(run_id), "state": outcome.value})
                artifacts.manifest()
            except Exception:
                if outcome == State.SUCCEEDED:
                    outcome = State.FAILED
                    self.store.update(run_id, summary="Artifact packaging failed; source may be incomplete.")
                try:
                    artifacts.write("final-report.json", {**self.store.get(run_id), "state": outcome.value})
                except Exception:
                    pass  # The durable run record retains the outcome even when storage is full.
                self.store.event(run_id, "packaging.failed", "Some artifacts could not be packaged")
            self.store.transition(run_id, outcome)
            self.store.event(run_id, "cleanup.failed" if self.runner.cleanup_errors else "cleanup.completed",
                             "Resource cleanup completed" if not self.runner.cleanup_errors else "Operator resource cleanup required")
            self.store.event(run_id, "run.completed" if outcome == State.SUCCEEDED else f"run.{outcome.value.lower()}", self.store.get(run_id)["state"],
                             duration_seconds=report["duration_seconds"])
