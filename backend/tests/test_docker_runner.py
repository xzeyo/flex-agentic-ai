import os
import time
from unittest.mock import MagicMock
from uuid import uuid4

import docker
import pytest

from app.artifacts import Artifacts
from app.errors import RunCancelled, SandboxError
from app.sandbox.docker_runner import DockerRunner
from tests.conftest import make_candidate


def fake_client(monkeypatch):
    client = MagicMock()
    image = client.images.get.return_value
    image.id = "sha256:trusted"
    stage, check = MagicMock(), MagicMock()
    check.status = "exited"
    check.attrs = {"State": {"ExitCode": 0, "OOMKilled": False}}
    check.logs.return_value = b"passed"
    client.containers.create.side_effect = [stage, check]
    monkeypatch.setattr(docker, "from_env", lambda **_: client)
    return client, stage, check


def test_docker_restrictions_and_cleanup(settings, tmp_path, monkeypatch):
    client, stage, check = fake_client(monkeypatch)
    artifacts = Artifacts(tmp_path / "input")
    artifacts.candidate(make_candidate())
    runner = DockerRunner(settings, str(uuid4()))
    result = runner.run(artifacts.source, "test", lambda: None)
    assert result.passed
    for call in client.containers.create.call_args_list:
        config = call.kwargs
        assert config["user"] == "10001:10001"
        assert config["network_mode"] == "none"
        assert config["read_only"] is True
        assert config["privileged"] is False
        assert config["cap_drop"] == ["ALL"]
        assert config["pids_limit"] == 64
        assert config["nano_cpus"] == 1_000_000_000
        assert not any("KEY" in key or "TOKEN" in key for key in config["environment"])
        assert all(mount["Type"] == "volume" for mount in config["mounts"])
    assert client.containers.create.call_args_list[-1].kwargs["mounts"][0]["ReadOnly"]
    stage.remove.assert_called_once_with(force=True)
    check.remove.assert_called_once_with(force=True)
    client.volumes.create.return_value.remove.assert_called_once_with(force=True)
    assert not runner.cleanup_errors


def test_container_removed_on_cancellation(settings, tmp_path, monkeypatch):
    client, stage, check = fake_client(monkeypatch)
    check.status = "running"
    artifacts = Artifacts(tmp_path / "input")
    artifacts.candidate(make_candidate())
    calls = 0
    def abort():
        nonlocal calls
        calls += 1
        if calls > 3:
            raise RunCancelled()
    with pytest.raises(RunCancelled):
        DockerRunner(settings, str(uuid4())).run(artifacts.source, "test", abort)
    check.remove.assert_called_once_with(force=True)
    client.volumes.create.return_value.remove.assert_called_once_with(force=True)


def test_docker_unavailable_is_safe(settings, tmp_path, monkeypatch):
    def unavailable(**kwargs):
        raise docker.errors.DockerException("unavailable")
    monkeypatch.setattr(docker, "from_env", unavailable)
    source = tmp_path / "source"
    source.mkdir()
    with pytest.raises(SandboxError, match="Docker execution unavailable"):
        DockerRunner(settings, str(uuid4())).run(source, "test", lambda: None)


def test_capped_logs(settings, tmp_path, monkeypatch):
    _, _, check = fake_client(monkeypatch)
    check.logs.return_value = b"a" * 100_000
    source = tmp_path / "source"
    source.mkdir()
    result = DockerRunner(settings, str(uuid4())).run(source, "test", lambda: None)
    assert len(result.output.encode()) <= 64_000
    assert result.output_limited and not result.passed


def require_docker(settings):
    if os.getenv("TEAM_TEST_DOCKER") != "1":
        pytest.skip("Set TEAM_TEST_DOCKER=1 to execute real disposable containers")
    client = docker.from_env(timeout=30)
    client.ping()
    client.images.get(settings.runner_image)
    return client


def real_source(tmp_path, code):
    source = tmp_path / "source"
    (source / "tests").mkdir(parents=True)
    (source / "tests" / "test_isolation.py").write_text(code, encoding="utf-8")
    return source


@pytest.mark.docker
def test_real_container_isolation_checks_and_cleanup(settings, tmp_path):
    client = require_docker(settings)
    run_id = str(uuid4())
    source = real_source(tmp_path, '''import os
import socket


def test_restrictions():
    assert os.getuid() == 10001
    assert not any("API_KEY" in key for key in os.environ)
    assert not os.path.exists("/var/run/docker.sock")
    assert not os.path.exists("/root/.ssh")
    for path in ("/input/tampered.py", "/runner/tampered.py"):
        try:
            with open(path, "w") as stream:
                stream.write("bad")
        except OSError:
            pass
        else:
            raise AssertionError("read-only path was writable")
    sock = socket.socket()
    sock.settimeout(0.2)
    try:
        assert sock.connect_ex(("1.1.1.1", 443)) != 0
    finally:
        sock.close()
''')
    runner = DockerRunner(settings, run_id)
    try:
        for profile in ("lint", "test"):
            result = runner.run(source, profile, lambda: None)
            assert result.passed, result.model_dump()
        assert not runner.cleanup_errors
        assert not client.containers.list(all=True, filters={"label": f"four-agent.run_id={run_id}"})
        assert not client.volumes.list(filters={"label": f"four-agent.run_id={run_id}"})
    finally:
        client.close()


@pytest.mark.docker
@pytest.mark.parametrize("scenario", ["timeout", "output", "cancel", "disk"])
def test_real_container_limits(settings, tmp_path, scenario):
    client = require_docker(settings)
    run_id = str(uuid4())
    codes = {
        "timeout": "import time\n\ndef test_slow():\n    time.sleep(30)\n",
        "cancel": "import time\n\ndef test_slow():\n    time.sleep(30)\n",
        "output": "def test_output():\n    print('a' * 200_000)\n    assert False\n",
        "disk": "import pytest\n\ndef test_disk():\n    with pytest.raises(OSError):\n        with open('/workspace/huge', 'wb') as stream:\n            stream.write(b'a' * 20_000_000)\n",
    }
    source = real_source(tmp_path, codes[scenario])
    runner = DockerRunner(settings, run_id)
    settings.check_timeout = 5 if scenario == "timeout" else 30
    started = time.monotonic()
    def abort():
        if scenario == "cancel" and time.monotonic() - started > 3:
            raise RunCancelled()
    try:
        if scenario == "cancel":
            with pytest.raises(RunCancelled):
                runner.run(source, "test", abort)
        else:
            result = runner.run(source, "test", abort)
            if scenario == "timeout":
                assert result.timed_out and not result.passed
            elif scenario == "output":
                assert result.output_limited and not result.passed
            else:
                assert result.passed, result.output
        assert not runner.cleanup_errors
        assert not client.containers.list(all=True, filters={"label": f"four-agent.run_id={run_id}"})
        assert not client.volumes.list(filters={"label": f"four-agent.run_id={run_id}"})
    finally:
        client.close()
