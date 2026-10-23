import re
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MAX_FILE_BYTES = 100_000
MAX_SOURCE_BYTES = 500_000
MAX_LOG_BYTES = 64_000


def now() -> str:
    return datetime.now(UTC).isoformat()


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", str_max_length=100_000)


def safe_path(value: str) -> str:
    # A portable subset avoids Windows ADS, device names, separators and normalization collisions.
    if len(value) > 180 or not re.fullmatch(r"[A-Za-z0-9_./-]+", value):
        raise ValueError("Use a portable relative file path")
    parts = value.split("/")
    if any(p in {"", ".", ".."} or p.startswith(".") or p.endswith(".") for p in parts):
        raise ValueError("Unsafe file path")
    reserved = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(10)), *(f"LPT{i}" for i in range(10))}
    if any(p.split(".")[0].upper() in reserved for p in parts):
        raise ValueError("Reserved file name")
    if PurePosixPath(value).is_absolute():
        raise ValueError("Absolute paths are forbidden")
    return value


class RunRequest(Contract):
    task: str = Field(min_length=10, max_length=12_000)
    language: Literal["python"] = "python"

    @field_validator("task")
    @classmethod
    def meaningful_task(cls, value: str) -> str:
        if len(value.strip()) < 10:
            raise ValueError("Describe a task in at least 10 characters")
        return value.strip()


class Plan(Contract):
    goal: str = Field(min_length=1, max_length=2000)
    assumptions: list[str] = Field(max_length=20)
    steps: list[str] = Field(min_length=1, max_length=20)
    files_expected: list[str] = Field(min_length=1, max_length=50)
    acceptance_criteria: list[str] = Field(min_length=1, max_length=20)
    risks: list[str] = Field(max_length=20)


class SourceFile(Contract):
    path: str
    content: str

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        safe_path(value)
        if PurePosixPath(value).suffix not in {".py", ".md", ".txt"}:
            raise ValueError("v1 accepts Python, Markdown and text files only")
        if value.lower().endswith("requirements.txt"):
            raise ValueError("v1 uses preinstalled pytest/Ruff and Python standard library only")
        return value

    @field_validator("content")
    @classmethod
    def validate_size(cls, value: str) -> str:
        if len(value.encode()) > MAX_FILE_BYTES or "\x00" in value:
            raise ValueError("File is oversized or contains NUL")
        return value


class Implementation(Contract):
    summary: str = Field(min_length=1, max_length=3000)
    # Each response is a COMPLETE candidate snapshot. Missing files are removed.
    files: list[SourceFile] = Field(min_length=1, max_length=50)
    dependencies: list[str] = Field(max_length=20)
    known_limitations: list[str] = Field(max_length=20)

    @model_validator(mode="after")
    def validate_snapshot(self) -> "Implementation":
        paths = [f.path.lower() for f in self.files]
        if len(set(paths)) != len(paths):
            raise ValueError("Duplicate file paths")
        if any(any(p.startswith(q + "/") for q in paths) for p in paths):
            raise ValueError("File and directory path collision")
        if sum(len(f.content.encode()) for f in self.files) > MAX_SOURCE_BYTES:
            raise ValueError("Candidate source exceeds size limit")
        if self.dependencies:
            raise ValueError("Additional dependencies are unsupported in v1")
        if not any(f.path.startswith("tests/test_") and f.path.endswith(".py") for f in self.files):
            raise ValueError("Candidate must include tests/test_*.py")
        return self


class DebugReport(Contract):
    analysis: str = Field(min_length=1, max_length=4000)
    fix_guidance: list[str] = Field(max_length=20)
    limitations: list[str] = Field(max_length=20)


class Finding(Contract):
    severity: Literal["critical", "high", "medium", "low"]
    title: str = Field(min_length=1, max_length=300)
    detail: str = Field(min_length=1, max_length=3000)
    file: str | None = None


class Coverage(Contract):
    criterion: str = Field(min_length=1)
    met: bool
    evidence: str


class Review(Contract):
    decision: Literal["approve", "changes_requested"]
    findings: list[Finding] = Field(max_length=30)
    requirement_coverage: list[Coverage] = Field(min_length=1, max_length=20)
    limitations: list[str] = Field(max_length=20)

    def accepts(self, plan: Plan) -> bool:
        coverage = {c.criterion: c.met for c in self.requirement_coverage}
        return (
            self.decision == "approve"
            and not any(f.severity in {"critical", "high"} for f in self.findings)
            and all(coverage.get(c, False) for c in plan.acceptance_criteria)
        )


class CheckResult(Contract):
    profile: Literal["lint", "test"]
    exit_code: int | None
    duration_seconds: float = Field(ge=0)
    output: str = Field(max_length=MAX_LOG_BYTES)
    timed_out: bool = False
    output_limited: bool = False
    oom_killed: bool = False
    log_ref: str | None = None

    @property
    def passed(self) -> bool:
        return self.exit_code == 0 and not (self.timed_out or self.output_limited or self.oom_killed)


class State(StrEnum):
    QUEUED = "QUEUED"
    VALIDATING = "VALIDATING"
    PLANNING = "PLANNING"
    IMPLEMENTING = "IMPLEMENTING"
    PRECHECKING = "PRECHECKING"
    TESTING = "TESTING"
    DEBUGGING = "DEBUGGING"
    REVIEWING = "REVIEWING"
    PACKAGING = "PACKAGING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    TIMED_OUT = "TIMED_OUT"


TERMINAL = {State.SUCCEEDED, State.FAILED, State.CANCELLED, State.TIMED_OUT}
TRANSITIONS = {
    State.QUEUED: {State.VALIDATING}, State.VALIDATING: {State.PLANNING},
    State.PLANNING: {State.IMPLEMENTING}, State.IMPLEMENTING: {State.PRECHECKING},
    State.PRECHECKING: {State.TESTING}, State.TESTING: {State.DEBUGGING, State.REVIEWING},
    State.DEBUGGING: {State.IMPLEMENTING},
    State.REVIEWING: {State.IMPLEMENTING, State.PACKAGING},
    State.PACKAGING: {State.SUCCEEDED},
}


class Artifact(Contract):
    path: str
    size: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("path")
    @classmethod
    def relative_path(cls, value: str) -> str:
        return safe_path(value)


class RunReport(Contract):
    verified: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    history: list[dict] = Field(default_factory=list)
    checks: list[CheckResult] = Field(default_factory=list)
    review: Review | None = None
    duration_seconds: float | None = None
    model_calls: int = 0
    agent_retries: int = 0
    cleanup_errors: list[str] = Field(default_factory=list)


class RunRecord(Contract):
    id: str
    task: str
    state: State
    created_at: str
    updated_at: str
    cancelled: bool
    iteration: int = Field(ge=0)
    review_iteration: int = Field(ge=0)
    summary: str
    report: RunReport


class EventRecord(Contract):
    seq: int
    run_id: str
    timestamp: str
    kind: str
    stage: State
    message: str
    data: dict
