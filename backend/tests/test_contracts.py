import hashlib

import pytest
from pydantic import ValidationError

from app.artifacts import Artifacts
from app.sandbox.policy import command
from app.schemas import Artifact, Implementation, RunRequest, SourceFile, State
from app.store import Store
from tests.conftest import make_candidate, make_plan, make_review


@pytest.mark.parametrize("path", ["../escape.py", "/etc/passwd.py", "C:/x.py", "a\\x.py", "a//x.py", "a/./x.py", "CON.py", "a/x.py:ads", ".env", "a/../x.py", "a/NUL.txt", "a./x.py", "é.py"])
def test_reject_unsafe_paths(path):
    with pytest.raises(ValidationError):
        SourceFile(path=path, content="x")


@pytest.mark.parametrize("profile", ["pytest; whoami", "python", "test && echo secret", "test\n", "--privileged"])
def test_command_injection_rejected(profile):
    with pytest.raises(ValueError):
        command(profile)


def test_profiles_are_not_mutable():
    command("test").append("arbitrary")
    assert "arbitrary" not in command("test")


def test_output_schema_and_size():
    with pytest.raises(ValidationError):
        SourceFile(path="huge.py", content="é" * 60_000)
    with pytest.raises(ValidationError):
        SourceFile(path="Dockerfile", content="FROM evil")
    with pytest.raises(ValidationError):
        RunRequest(task=" " * 50)
    with pytest.raises(ValidationError):
        RunRequest(task="Build code please", language="javascript")
    value = make_candidate().model_dump()
    value["files"].append(value["files"][0])
    with pytest.raises(ValidationError):
        Implementation.model_validate(value)
    value = make_candidate().model_dump()
    value["dependencies"] = ["requests"]
    with pytest.raises(ValidationError):
        Implementation.model_validate(value)


def test_file_directory_collision():
    value = make_candidate().model_dump()
    value["files"] += [{"path": "calculator.py/child.py", "content": ""}]
    with pytest.raises(ValidationError):
        Implementation.model_validate(value)


def test_review_cannot_approve_missing_coverage_or_high_findings():
    review = make_review()
    assert review.accepts(make_plan())
    review.requirement_coverage[0].criterion = "Unrelated criterion"
    assert not review.accepts(make_plan())
    assert not make_review(severity="high").accepts(make_plan())


def test_manifest_checksums_and_safe_reads(tmp_path):
    artifacts = Artifacts(tmp_path / "run")
    artifacts.candidate(make_candidate())
    manifest = artifacts.manifest()
    for item in manifest:
        Artifact.model_validate(item)
        assert item["sha256"] == hashlib.sha256(artifacts.read(item["path"])).hexdigest()
    with pytest.raises(ValueError):
        artifacts.read("../escape")
    assert "--- /dev/null" in artifacts.read("changes.patch").decode()


def test_snapshot_removes_obsolete_files(tmp_path):
    artifacts = Artifacts(tmp_path / "run")
    artifacts.candidate(make_candidate())
    (artifacts.source / "obsolete.py").write_text("x")
    artifacts.candidate(make_candidate())
    assert not (artifacts.source / "obsolete.py").exists()


def test_state_transitions_and_persistence(settings):
    store = Store(settings.root)
    run = store.create(RunRequest(task="Build a calculator"))
    with pytest.raises(ValueError):
        store.transition(run["id"], State.SUCCEEDED)
    store.transition(run["id"], State.VALIDATING)
    store.transition(run["id"], State.FAILED)
    with pytest.raises(ValueError):
        store.transition(run["id"], State.PLANNING)
    assert Store(settings.root).get(run["id"])["state"] == "FAILED"
    assert [e["seq"] for e in store.events(run["id"])] == sorted(e["seq"] for e in store.events(run["id"]))


def test_restart_recovers_incomplete_runs(settings):
    store = Store(settings.root)
    run = store.create(RunRequest(task="Build a calculator"))
    store.recover()
    assert store.get(run["id"])["state"] == "FAILED"


def test_queued_cancel_is_immediate_and_idempotent(settings):
    store = Store(settings.root)
    run = store.create(RunRequest(task="Build a calculator"))
    assert store.cancel(run["id"])["state"] == "CANCELLED"
    assert store.cancel(run["id"])["state"] == "CANCELLED"


def test_sandbox_owner_is_persisted_and_separate_per_data_volume(tmp_path):
    from app.config import Settings
    first = Settings(data_dir=tmp_path / "one", _env_file=None)
    second = Settings(data_dir=tmp_path / "two", _env_file=None)
    assert first.instance_id != second.instance_id
    assert Settings(data_dir=tmp_path / "one", _env_file=None).instance_id == first.instance_id
