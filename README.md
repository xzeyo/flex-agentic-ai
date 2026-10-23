# Quartet — Four Agent Engineering Team

A local engineering console that turns a Python task into source files, isolated check evidence and a structured review. FastAPI owns the workflow; four CrewAI roles reason about requirements, implementation, debugging and review. Next.js displays real progress and artifacts.

## Quick start

Install Docker Desktop (Linux containers), Python 3.12, [uv](https://docs.astral.sh/uv/) and Node.js 22.22 or newer. Run commands from the repository root unless specified.

```powershell
Copy-Item .env.example .env
# Edit .env: set TEAM_API_KEY and a model your provider supports.
docker build -t four-agent-python:1 docker/python-runner
cd backend
uv sync --frozen --extra dev
cd ..
uv run --project backend --env-file .env uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
```

On Windows, if the SDK cannot reach the active Docker Desktop context, set this in the backend terminal before starting it:

```powershell
$env:DOCKER_HOST = 'npipe:////./pipe/dockerDesktopLinuxEngine'
```

In a second terminal:

```powershell
cd frontend
npm ci
npm run dev
```

Open [the console](http://127.0.0.1:3000) or [API documentation](http://127.0.0.1:8000/docs). SQLite and run folders initialize automatically under `data/` in the backend's current working directory. Starting from the repository root keeps this at `<repository>/data`. An OS lock enforces one API/CLI controller per data directory; stop the API before using offline `four-agent run`, or select a separate `TEAM_DATA_DIR`. Read-only CLI status queries can run alongside the API.

The frontend development proxy defaults to port 8000. `API_URL` is a **server/build-time** variable; set it when building if the API lives elsewhere. It is not a browser API key. The frontend does not need provider credentials.

## Docker Compose

After creating `.env` and building the runner image:

```powershell
docker compose up --build
```

Compose serves the console on localhost:3000 and API on localhost:8000, with a named data volume. The trusted API controller mounts the Docker socket to create sandboxes. **The controller therefore has Docker daemon authority.** Generated code runs in separate non-root containers without that socket, credentials, host mounts or network access. Do not expose this local MVP publicly.

Optional `TEAM_API_PORT` and `TEAM_WEB_PORT` change the two loopback host ports for parallel local testing. The frontend still uses the internal `api:8000` service address in Compose. The default setup does not require either variable.

## Configure model access

`TEAM_API_KEY` is required for live generation. `TEAM_MODEL` is passed to CrewAI as `provider/model`. The default is `openai/gpt-4.1`; select a model available to your account. `TEAM_BASE_URL` optionally configures a compatible gateway. OpenAI and LiteLLM integrations are installed; some providers require additional SDKs or environment configuration. Check the provider's CrewAI documentation before switching.

No real credentials are included. Missing credentials produce a failed run with an actionable message, never fabricated code or test results. Model calls are processed outside the HTTP request in disposable subprocesses.

Other settings in `.env.example`: `TEAM_RUN_TIMEOUT`, `TEAM_AGENT_TIMEOUT`, `TEAM_CHECK_TIMEOUT`, `TEAM_MAX_FIXES` (default 2), `TEAM_MAX_REVIEW_FIXES` (default 1), `TEAM_MAX_ACTIVE` (2), `TEAM_MAX_QUEUED` (20), `TEAM_MAX_MODEL_CALLS` (16), `TEAM_DATA_DIR`, and `TEAM_RUNNER_IMAGE`. The configured image must already exist locally. v1 supports standard-library Python projects with preinstalled pytest/Ruff; it rejects additional dependency installation.

## Workflow and acceptance

```text
submit → validate → plan → implement → precheck → Docker Ruff + pytest
                                              ↓ failed checks
                                  debug → bounded correction → retest
                                              ↓
                               review → bounded correction → retest/review
                                              ↓
                                     package → terminal status
```

1. Planner returns assumptions, ordered steps, expected files, measurable acceptance criteria and risks.
2. Developer returns a complete validated file snapshot, summary and limitations. The application writes it to that run's directory and generates a unified patch against an empty project.
3. Test/Debug analyzes actual Docker check evidence. It supplies targeted feedback for at most two test corrections in total, including any review cycle.
4. Reviewer receives the actual diff, original task, plan and recorded checks. High/critical findings or missing/unmet criteria block success. At most one review correction is allowed by default.

Every role runs on the successful path. Invalid role output gets one repair attempt; provider failures get one retry. Framework/provider retries are also limited. The model-call budget counts role invocations, not individual HTTP requests. Token output is bounded; strict monetary quotas must be configured with the provider.

States: `QUEUED`, `VALIDATING`, `PLANNING`, `IMPLEMENTING`, `PRECHECKING`, `TESTING`, `DEBUGGING`, `REVIEWING`, `PACKAGING`, then `SUCCEEDED`, `FAILED`, `CANCELLED` or `TIMED_OUT`. Invalid transitions are rejected. Check and run timeouts stop work; cancellation kills the model worker or removes the active sandbox. Docker API requests have a separate 15-second timeout, so cancellation can wait for an in-flight API call. Cleanup errors are recorded separately from the primary outcome.

## API and CLI

| Method | Route | Result |
|---|---|---|
| POST | `/api/runs` | `{"task":"...","language":"python"}` → accepted run ID |
| GET | `/api/runs` | 50 most recent runs |
| GET | `/api/runs/{id}` | state, iterations, summary and reports |
| GET | `/api/runs/{id}/events?after=0` | chronological events, paginated by sequence |
| GET | `/api/runs/{id}/artifacts` | manifest with relative paths and SHA256 |
| GET | `/api/runs/{id}/artifacts/{path}` | plain-text artifact contents |
| POST | `/api/runs/{id}/cancel` | cancellation request |
| GET | `/health` | API availability and model configuration state |

```powershell
uv run --project backend --env-file .env four-agent run "Create a Python calculator with add, subtract, multiply, divide, and pytest tests."
uv run --project backend --env-file .env four-agent status <run-id>
```

Artifacts include the original task, validated plan, source, `changes.patch`, each candidate/check/debug/review revision, test and review reports, final report and checksum manifest. Raw model chain-of-thought is not retained. Check logs are combined stdout/stderr with a 64 KB capture cap. Run events contain stage, role, durations and safe evidence references.

## Verify and demonstrate

From `backend/`:

```powershell
uv run --frozen --extra dev ruff check .
uv run --frozen --extra dev mypy app
uv run --frozen --extra dev pytest -q -m "not docker and not live"
$env:TEAM_TEST_DOCKER = '1'
uv run --frozen --extra dev pytest -q -m docker
# Optional paid provider check (requires your configured key):
$env:TEAM_TEST_LIVE = '1'
uv run --env-file ../.env --frozen --extra dev pytest -q -m live
```

The ordinary suite uses scripted roles and a localhost mock provider; the latter exercises actual CrewAI workers without paid calls. Docker tests use real disposable containers. The seeded failure regression demonstrates a failed first round, a targeted correction and successful retest; the reviewer rejection regression demonstrates the separate review budget. To inspect them directly, run `pytest -v tests/test_workflow.py -k "correction or review_fix"` through `uv run --extra dev`.

From `frontend/`: `npm test`, `npm run lint`, `npm run typecheck`, `npm run build`. CI runs these plus real Docker tests on Linux. See [observed verification results](docs/verification.md), [milestones](docs/milestones.md), and [architecture decisions](docs/decisions.md).

## Security boundaries and limitations

Sandbox checks use a locally built Python image resolved to an immutable image ID, non-root UID/GID 10001, no network, dropped capabilities, no-new-privileges, a read-only root/source, 1 CPU, 256 MiB memory with no extra swap, 64 PIDs, 32 MiB workspace tmpfs, 16 MiB temporary tmpfs, 8 MiB per-file limit, bounded logs and wall time. Input size is capped at 500 KB across at most 50 files; paths reject traversal, symlinks, Windows devices/ADS and collisions. Reports and source are capped per run. Sandbox containers and input volumes are removed on every handled path; restart recovery targets labels scoped to this data directory.

Docker shares the host kernel and is only one defense layer. This MVP has no authentication, billing, production deployment, arbitrary repositories, network dependency installs or public multi-tenant hardening. Generated tests may be incomplete or adversarial. Passing checks and model review do not guarantee correctness or safety. Independently review a patch before applying it to an important project.

Runs/artifacts are retained locally until the operator deletes them while the backend is stopped; no automatic retention deletion is enabled. Per-run quotas do not cap lifetime disk use. Back up the SQLite database and run folders together. Production use requires authentication, user quotas, a durable queue, stricter isolation and operational monitoring.

## Troubleshooting

- **Missing key/model error:** set `TEAM_API_KEY` and confirm `TEAM_MODEL`/`TEAM_BASE_URL` with your provider. The UI accepts tasks even when a provider is unavailable, then records the precise failed stage.
- **Docker unavailable:** start Docker Desktop in Linux-container mode, build the fixed image and check `docker version`. On Windows use the `DOCKER_HOST` setting above when needed. There is no host-execution fallback.
- **Runner checks fail:** inspect the recorded exit code, logs, resource flags and bounded correction history. v1 does not install requested third-party dependencies.
- **API unreachable:** start the backend on port 8000; restart/rebuild Next.js if you change `API_URL`.
- **Restarted server:** interrupted runs become failed; submit a fresh task. Resource-recovery failures appear in `/health` and server logs. Do not run multiple API processes against one data directory.
- **Restricted test temp directory:** pass `--basetemp=../.cache/pytest-local` when running tests from `backend/`.
- **Cleanup failure:** inspect Docker resources with the reported `four-agent.run_id` label and remove only those resources after stopping the affected run.

Repository layout: `backend/app/` (API, store, schemas, role workers, workflow, artifacts, sandbox), `backend/tests/`, `frontend/src/`, `docker/python-runner/`, `docs/`, `.github/workflows/ci.yml`, and `docker-compose.yml`.
