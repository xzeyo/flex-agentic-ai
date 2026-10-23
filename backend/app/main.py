import logging
from contextlib import asynccontextmanager
from typing import Annotated
from uuid import UUID

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import Response

from app.artifacts import Artifacts
from app.config import Settings
from app.schemas import Artifact, EventRecord, RunRecord, RunRequest
from app.service import QueueFull, RunService


def create_app(settings: Settings | None = None, service: RunService | None = None) -> FastAPI:
    settings = settings or Settings()
    service = service or RunService(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        logging.basicConfig(level=logging.INFO, format="%(message)s")
        await service.start(recover_docker=not getattr(service, "test_mode", False))
        try:
            yield
        finally:
            await service.close()

    app = FastAPI(title="Four Agent Engineering Team", version="0.1.0", lifespan=lifespan)
    app.state.service = service

    def find(run_id: UUID) -> dict:
        try:
            return service.store.get(str(run_id))
        except KeyError as exc:
            raise HTTPException(404, "Run not found") from exc

    @app.get("/health")
    async def health():
        return {"status": "ok", "model_configured": bool(settings.api_key.get_secret_value()),
                "language": "python", "recovery_warning": service.recovery_warning}

    @app.get("/api/runs", response_model=list[RunRecord])
    async def list_runs():
        return service.store.recent()

    @app.post("/api/runs", status_code=202, response_model=RunRecord)
    async def submit(request: RunRequest):
        try:
            return service.submit(request)
        except QueueFull as exc:
            raise HTTPException(429, "Run queue is full or shutting down. Try again later.") from exc

    @app.get("/api/runs/{run_id}", response_model=RunRecord)
    async def get_run(run_id: UUID):
        return find(run_id)

    @app.get("/api/runs/{run_id}/events", response_model=list[EventRecord])
    async def get_events(run_id: UUID, after: Annotated[int, Query(ge=0)] = 0):
        find(run_id)
        return service.store.events(str(run_id), after)

    @app.post("/api/runs/{run_id}/cancel", status_code=202, response_model=RunRecord)
    async def cancel(run_id: UUID):
        find(run_id)
        return service.store.cancel(str(run_id))

    @app.get("/api/runs/{run_id}/artifacts", response_model=list[Artifact])
    async def get_artifacts(run_id: UUID):
        find(run_id)
        artifacts = Artifacts(settings.root / "runs" / str(run_id))
        try:
            import json
            return json.loads(artifacts.read("manifest.json"))
        except FileNotFoundError:
            return []

    @app.get("/api/runs/{run_id}/artifacts/{path:path}")
    async def get_artifact(run_id: UUID, path: str):
        find(run_id)
        try:
            data = Artifacts(settings.root / "runs" / str(run_id)).read(path)
        except (ValueError, FileNotFoundError, IsADirectoryError) as exc:
            raise HTTPException(404, "Artifact not found") from exc
        # Never serve submitted HTML or source as executable content.
        return Response(data, media_type="text/plain", headers={"X-Content-Type-Options": "nosniff",
                                                                "Content-Security-Policy": "default-src 'none'"})

    return app


app = create_app()
