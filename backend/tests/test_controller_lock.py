import pytest

from app.controller_lock import ControllerLock
from app.schemas import RunRequest
from app.service import RunService
from tests.conftest import ScriptedAgents, ScriptedRunner


def test_controller_lock_exclusion_and_release(tmp_path):
    first = ControllerLock(tmp_path)
    second = ControllerLock(tmp_path)
    first.acquire()
    with pytest.raises(RuntimeError):
        second.acquire()
    first.release()
    second.acquire()
    second.release()


async def test_second_controller_cannot_recover_active_runs(settings):
    first = RunService(settings, ScriptedAgents(), lambda _: ScriptedRunner())
    second = RunService(settings, ScriptedAgents(), lambda _: ScriptedRunner())
    await first.start(recover_docker=False)
    try:
        run = first.submit(RunRequest(task="Build a calculator"))
        with pytest.raises(RuntimeError):
            await second.start(recover_docker=False)
        assert first.store.get(run["id"])["state"] == "QUEUED"
    finally:
        await first.close()
