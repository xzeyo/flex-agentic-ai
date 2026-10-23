import asyncio
import logging

from app.agents.client import CrewAgents
from app.config import Settings
from app.controller_lock import ControllerLock
from app.sandbox.docker_runner import DockerRunner
from app.schemas import TERMINAL, RunRequest, State
from app.store import Store
from app.workflow import Workflow


class QueueFull(Exception):
    pass


class RunService:
    def __init__(self, settings: Settings, agents=None, runner_factory=None):
        self.settings = settings
        self.store = Store(settings.root)
        self.agents = agents or CrewAgents(settings)
        self.runner_factory = runner_factory or (lambda run_id: DockerRunner(settings, run_id))
        self.queue: asyncio.Queue[str | None] = asyncio.Queue(settings.max_queued)
        self.workers: list[asyncio.Task] = []
        self.active: set[str] = set()
        self.accepting = False
        self.recovery_warning: str | None = None
        self.controller_lock = ControllerLock(settings.root)

    async def start(self, recover_docker: bool = True) -> None:
        self.controller_lock.acquire()
        try:
            _ = self.settings.instance_id
            self.store.recover()
            if recover_docker:
                try:
                    await asyncio.to_thread(DockerRunner.recover, self.settings)
                except Exception:
                    self.recovery_warning = "Docker resource recovery unavailable; check Docker before submitting runs."
                    logging.getLogger("team").warning(self.recovery_warning)
            self.accepting = True
            self.workers = [asyncio.create_task(self.worker()) for _ in range(self.settings.max_active)]
        except BaseException:
            self.controller_lock.release()
            raise

    def submit(self, request: RunRequest) -> dict:
        # No await between admission and enqueue: atomic within this application's event loop.
        if not self.accepting or self.queue.full():
            raise QueueFull()
        run = self.store.create(request)
        self.queue.put_nowait(run["id"])
        return run

    async def worker(self) -> None:
        while True:
            run_id = await self.queue.get()
            try:
                if run_id is None:
                    return
                if State(self.store.get(run_id)["state"]) in TERMINAL:
                    continue
                self.active.add(run_id)
                workflow = Workflow(self.settings, self.store, self.agents, self.runner_factory(run_id))
                await workflow.execute(run_id)
            finally:
                if run_id:
                    self.active.discard(run_id)
                self.queue.task_done()

    async def close(self) -> None:
        try:
            await self._close_workers()
        finally:
            self.controller_lock.release()

    async def _close_workers(self) -> None:
        self.accepting = False
        for run_id in list(self.active):
            self.store.cancel(run_id)
        while not self.queue.empty():
            queued_id = self.queue.get_nowait()
            if queued_id:
                self.store.cancel(queued_id)
                if State(self.store.get(queued_id)["state"]) not in TERMINAL:
                    self.store.transition(queued_id, State.CANCELLED)
                    self.store.update(queued_id, summary="Cancelled during server shutdown before execution.")
            self.queue.task_done()
        # Running workers observe cancellation; do not abandon a thread holding a container.
        await self.queue.join()
        for _ in self.workers:
            await self.queue.put(None)
        await asyncio.gather(*self.workers)
