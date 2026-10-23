from collections import defaultdict

import pytest

from app.config import Settings
from app.schemas import CheckResult, DebugReport, Implementation, Plan, Review, SourceFile


@pytest.fixture
def settings(tmp_path):
    return Settings(data_dir=tmp_path / "data", _env_file=None)


def make_plan():
    return Plan(goal="Build a calculator", assumptions=[], steps=["Implement addition and tests"],
                files_expected=["calculator.py", "tests/test_calculator.py"],
                acceptance_criteria=["Adds two integers"], risks=[])


def make_candidate():
    return Implementation(summary="Calculator and tests", files=[
        SourceFile(path="calculator.py", content="def add(a, b):\n    return a + b\n"),
        SourceFile(path="tests/test_calculator.py", content="from calculator import add\n\n\ndef test_add():\n    assert add(2, 3) == 5\n"),
    ], dependencies=[], known_limitations=[])


def make_review(approve=True, severity=None):
    return Review(decision="approve" if approve else "changes_requested",
                  findings=[] if not severity else [{"severity": severity, "title": "Issue", "detail": "Fix this", "file": "calculator.py"}],
                  requirement_coverage=[{"criterion": "Adds two integers", "met": approve, "evidence": "Executed addition test"}],
                  limitations=["Only addition is covered"])


class ScriptedAgents:
    def __init__(self, reviews=None, fail=None):
        self.calls = []
        self.reviews = list(reviews or [make_review()])
        self.counts = defaultdict(int)
        self.fail = fail

    async def invoke(self, role, context, schema, abort):
        abort()
        self.calls.append((role, context))
        self.counts[role] += 1
        if self.fail:
            raise self.fail
        if role == "planner":
            return make_plan()
        if role == "developer":
            return make_candidate()
        if role == "debugger":
            return DebugReport(analysis="Inspection of captured evidence", fix_guidance=["Fix the failing assertion"], limitations=[])
        if len(self.reviews) > 1:
            return self.reviews.pop(0)
        return self.reviews[0]


class ScriptedRunner:
    def __init__(self, failures=0, timed_out=False, hook=None):
        self.cleanup_errors = []
        self.failures = failures
        self.round = 0
        self.hook = hook
        self.timed_out = timed_out

    def run(self, source, profile, abort):
        if self.hook:
            self.hook()
        abort()
        code = 1 if self.round < self.failures else 0
        if profile == "test":
            self.round += 1
        return CheckResult(profile=profile, exit_code=code, duration_seconds=.1,
                           output="FAILED assertion" if code else "passed", timed_out=self.timed_out)
