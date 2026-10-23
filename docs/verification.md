# Verification — 23 October 2026 (Asia/Kolkata)

The local MVP is implemented and its backend, Docker sandbox and frontend checks have passed. A live end-to-end calculator workflow also succeeded through OpenRouter using GLM 5.3 Flash. This verifies the configured key and model for this run; broader provider availability and model behavior remain unverified.

## Observed checks

| Check | Observed result |
|---|---|
| Backend core, API, persistence, contracts, workflow/failure handling and controller locking | **54 passed** in the final core suite |
| Real Docker integration cases, including actual CrewAI + local mock provider + Docker, seeded defect correction, isolation, timeout, cancellation, output/disk limits and cleanup | **7 passed** in the expanded integration regression |
| Actual CrewAI worker processes for all four roles against a localhost mock OpenAI-compatible provider, including UTF-8 structured output | **1 passed** |
| Optional live paid-model planner | **1 skipped**; requires explicit `TEAM_TEST_LIVE=1` and a configured key |
| Ruff backend lint | **Passed** |
| mypy backend | **Passed**, 17 source modules |
| Frontend interaction tests, Vitest 4.1.12 | **5 passed**, including automatic source preview for selected verified runs |
| Frontend ESLint and TypeScript | **Passed** |
| Next.js production build and standalone asset packaging | **Passed** locally and in the clean Linux image build |
| Complete npm dependency audit, including development tools | **0 findings** |
| Fixed Python sandbox image build | **Passed** |
| API and frontend Compose image builds from lockfiles | **Passed** |
| Compose startup on isolated localhost ports 18000/13000 | **Passed** |
| Compose frontend → API proxy, task submission, retry evidence, safe missing-key failure and artifact manifest | **Passed** |
| CrewAI 1.15.28 import in Linux API image | **Passed** |
| Running Linux API controller rejects a second controller lock | **Passed** |
| Sandbox launched through the containerized API's Docker SDK | **Ruff and pytest exit 0** |
| Actual sandbox cgroup configuration | **1 CPU, 256 MiB memory, 64 PIDs**, UID 10001 and no provider key in the container |
| Compose sandbox cleanup | **No cleanup errors; zero leaked test containers/volumes** |
| Browser smoke test | Submission, actual persisted failure state, event timeline and report viewing verified |
| Responsive layout | Desktop and mobile breakpoint inspected; no horizontal overflow observed |
| Final localhost preview | API health `ok`; production frontend HTTP 200 |
| Source credential-pattern inspection | No matching private keys or provider tokens in deliverable source |
| Backend regression after provider dependency repair | **64 passed, 1 live test deselected**; Docker cases included |
| Live OpenRouter GLM 5.3 Flash calculator workflow | **Succeeded**; all four roles completed, Ruff passed, 9 pytest checks passed, reviewer approved with no findings, cleanup succeeded |
| Focused real CrewAI worker protocol after provider dependency repair | **1 passed** against a localhost mock provider; paid model test deselected |
| Ruff and mypy after provider dependency repair | **Passed** |
| Groq chat-completions authentication | **Failed with `invalid_api_key`**; the key value is not logged or shown |
| Previous Groq model configuration | `groq/openai/gpt-oss-120b`; a historical Groq attempt failed authentication and is retained as evidence |
| Current local model configuration | `openrouter/z-ai/glm-5.3-flash-20260826`; verified in the successful live run without recording the credential |
| Worker diagnostic safety | Invalid-key and rate-limit messages are classified and never include provider response text or credentials |

The original backend counts represent **62 unique passing cases across separate suites**. After the provider dependency and safe-diagnostic changes, the complete non-live backend command passed **64 cases**, including Docker tests; the optional paid test was deselected. The earlier seeded fixture issue was corrected before the original final core run. There are no known outstanding assertion failures in the automated non-live suite.

## Live OpenRouter run — 23 October 2026

The local `.env` selects `openrouter/z-ai/glm-5.3-flash-20260826` and stores the OpenRouter key outside version control. Calculator run `3055737e-1083-4397-8cfa-c81183c72324` completed successfully in 111.109 seconds with four model calls and no retries. Planner, Developer, Test/Debug and Reviewer all completed. The sandbox reported Ruff exit 0 and pytest exit 0 (**9 passed**); the Reviewer approved with no findings, and sandbox cleanup reported no errors. Generated files and the final report are available in the run artifacts. The key and provider response bodies are not recorded here.

The first GLM implementation response violated two application-owned constraints by listing a dependency and omitting the required `tests/test_*.py` path. The application safely rejected that candidate before sandbox execution. Developer instructions now state both rules explicitly, with examples. A focused live structured-output check passed, followed by the successful full workflow. No source was executed on the host.

## Live Groq attempt — 23 October 2026

The browser submitted the calculator task. The first attempt initially exposed two issues: the saved model ID was not present in the current Groq model listing, and the locked LiteLLM 1.106.1 attempted to import `mcp.types.CacheableResult`, which is absent from the locked MCP 1.28.1 package. The project now selects `groq/openai/gpt-oss-120b` and pins LiteLLM to 1.105.3, resolving that dependency conflict. The real CrewAI worker mock-provider check and the complete backend regression suite pass with this change.

After those fixes, Groq chat completion returned `invalid_api_key`. A replacement value was saved and the calculator task retried; Groq returned the same authentication error. Its local formatting was checked without displaying it: the value is nonempty, has the `gsk_` prefix, and contains no whitespace or quotes. The application now shows a safe, actionable credential error without exposing the provider response or key. A successful live run still requires an active Groq key accepted by the chat-completions endpoint. The existing failed calculator runs are retained as evidence and are not retried automatically.

The backend test transport emits a non-failing Starlette/httpx deprecation warning. Expensive/non-deterministic paid calls are excluded from normal CI.

## Reproduce

From `backend/`, using the locked environment:

```powershell
uv run --frozen --extra dev ruff check .
uv run --frozen --extra dev mypy app
uv run --frozen --extra dev pytest -q -m "not docker and not live"
$env:TEAM_TEST_DOCKER = '1'
uv run --frozen --extra dev pytest -q -m docker
```

Build the sandbox first: `docker build -t four-agent-python:1 docker/python-runner`. Docker Desktop must use Linux containers. When needed on Windows, set `DOCKER_HOST=npipe:////./pipe/dockerDesktopLinuxEngine`. A restricted temporary directory can be avoided with `--basetemp=../.cache/pytest-local`.

From `frontend/`: `npm ci`, `npm test`, `npm run lint`, `npm run typecheck`, `npm run build`, and `npm audit`. Use Node.js 22.22 or newer. Final native frontend checks used the bundled Node.js 24.19 runtime; clean container builds used Node.js 22.22 and successfully consumed the same npm lockfile.

## Remaining external verification and limits

- The ignored root `.env` currently contains the OpenRouter credential and GLM 5.3 Flash model used by the successful run. Provider quotas, billing and future model availability can still affect later runs.
- A mock provider verifies the real CrewAI protocol and workflow; it does not verify a paid provider's credentials, availability, billing, model quality or future API behavior.
- GitHub Actions is configured but has not run remotely. This folder now has its own local Git repository on `codex/four-agent-team`; no remote, commit, push, PR or external deployment was created. The selected Code Review plugin exposes PR CI diagnostics, so it was not applicable without a PR. The GitHub plugin was used to inspect the official CrewAI task contract.
- Python application scope is standard library plus the preinstalled pytest/Ruff toolchain. Dependency installation, arbitrary repositories and other languages are unsupported in v1.
- Authentication, distributed workers, automatic retention deletion and public multi-tenant hardening remain outside this local MVP. Lifetime artifact storage is operator-managed.
- Passing generated tests and model review is evidence of the recorded checks, not proof of complete correctness or security. Docker shares a kernel and requires stronger isolation for untrusted public workloads.

The temporary Compose verification deployment is removed after testing; its images remain available. The native localhost console and API are left running for inspection. Selecting a successful run now opens its generated source preview automatically; on page load, the latest successful run is selected ahead of newer failed attempts. The latest calculator preview is a real successful run with persisted source, check and review artifacts.
