import time
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import create_app
from app.service import RunService
from tests.conftest import ScriptedAgents, ScriptedRunner


def client_for(settings):
    service = RunService(settings, ScriptedAgents(), lambda _: ScriptedRunner())
    service.test_mode = True
    return TestClient(create_app(settings, service))


def test_submit_query_events_artifacts_and_restart(settings):
    with client_for(settings) as client:
        assert client.get("/health").json()["model_configured"] is False
        assert client.post("/api/runs", json={"task": "tiny"}).status_code == 422
        response = client.post("/api/runs", json={"task": "Build a calculator with tests"})
        assert response.status_code == 202
        run_id = response.json()["id"]
        for _ in range(100):
            result = client.get(f"/api/runs/{run_id}").json()
            if result["state"] == "SUCCEEDED":
                break
            time.sleep(.02)
        assert result["state"] == "SUCCEEDED"
        assert client.get("/api/runs").json()[0]["id"] == run_id
        events = client.get(f"/api/runs/{run_id}/events").json()
        assert events[0]["kind"] == "run.created"
        assert client.get(f"/api/runs/{run_id}/events?after={events[-1]['seq']}").json() == []
        artifacts = client.get(f"/api/runs/{run_id}/artifacts").json()
        assert any(item["path"] == "changes.patch" for item in artifacts)
        source = client.get(f"/api/runs/{run_id}/artifacts/source/calculator.py")
        assert source.headers["content-type"].startswith("text/plain")
        assert source.headers["x-content-type-options"] == "nosniff"
        assert "def add" in source.text
        assert client.post(f"/api/runs/{run_id}/cancel").json()["state"] == "SUCCEEDED"
    with client_for(settings) as client:
        assert client.get(f"/api/runs/{run_id}").json()["state"] == "SUCCEEDED"


def test_unknown_and_unsafe_paths(settings):
    with client_for(settings) as client:
        assert client.get("/api/runs/bad-id").status_code == 422
        assert client.get(f"/api/runs/{uuid4()}").status_code == 404
        run = client.post("/api/runs", json={"task": "Build calculator code"}).json()
        assert client.get(f"/api/runs/{run['id']}/artifacts/source%5C..%5Csecret.py").status_code == 404


async def test_queue_admission_and_shutdown(settings):
    import pytest

    from app.schemas import RunRequest
    from app.service import QueueFull

    settings.max_queued = 1
    service = RunService(settings, ScriptedAgents(), lambda _: ScriptedRunner())
    await service.start(recover_docker=False)
    first = service.submit(RunRequest(task="Build calculator code"))
    with pytest.raises(QueueFull):
        service.submit(RunRequest(task="Build another calculator"))
    await service.close()
    assert service.store.get(first["id"])["state"] == "CANCELLED"
