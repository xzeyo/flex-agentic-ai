# Technical stack and architecture

Quartet implements Project 5: a user submits a software task and four specialized agents plan, implement, test/debug and review a Python application. Generated source executes only in disposable restricted Docker containers.

| Layer | Implementation |
|---|---|
| Frontend | Next.js App Router, React, TypeScript, Tailwind CSS |
| API | Python 3.12, FastAPI, Pydantic request/response contracts |
| Agent orchestration | Four CrewAI task/agent roles with typed outputs |
| Models | Configurable CrewAI LLM adapter; provider secrets stay in trusted workers |
| Execution | Docker SDK, locally built Python runner, fixed pytest/Ruff profiles |
| Controller | Application-owned state machine, deadlines, admission limits and correction budgets |
| Persistence | SQLite runs, chronological structured events and final reports |
| Artifacts | Per-run source snapshots, actual unified diff, revision evidence and SHA256 manifest |
| Background work | Bounded asyncio workers; interruptible model subprocesses and monitored container checks |
| Packaging | Locked Python/npm dependencies, Docker Compose, GitHub Actions |

Request → FastAPI validation → unique run ID and SQLite record → local queue → application controller → Planner → Developer → Docker Ruff/pytest → Test/Debug → bounded corrections → Reviewer → bounded review corrections → artifact packaging → terminal status.

CrewAI supplies reasoning and validated outputs. It does not control transitions, filesystem permissions, execution profiles, acceptance, cancellation, retries or resource lifetimes. The Developer returns a full candidate snapshot through a controlled application interface. Only the application writes validated paths. The test agent analyzes captured evidence; the controller invokes the execution boundary.

The sandbox runs as UID/GID 10001 with networking off, read-only root/source, all capabilities dropped, no-new-privileges, resource limits and bounded logs. The trusted controller alone accesses Docker. No sandbox receives a host directory mount, Docker socket, provider key or production secret.

v1 supports Python standard-library applications and supplied tests using the preinstalled pytest/Ruff toolchain. It does not install dependencies or deploy applications. Authentication, public multi-tenancy, a durable distributed queue, PostgreSQL and stronger isolation remain future work. Current verification and external prerequisites are recorded separately in verification.md.
