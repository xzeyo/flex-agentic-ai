# MASTER BUILD PROMPT — FOUR-AGENT AI ENGINEERING TEAM

## 1. Your role and objective

Act as a senior full-stack engineer, AI agent architect, DevOps engineer, and software security engineer.

Your task is to IMPLEMENT, INTEGRATE, TEST, DEBUG, DOCUMENT, AND VERIFY a complete working project titled:

**Deploy Your Own 4-Agent Engineering Team using CrewAI, Coder Agents, and Docker.**

Do not stop after producing a plan, architecture diagram, starter template, or partial implementation. Work directly in the repository, implement the system end to end, run the available checks, resolve failures, and continue until the defined acceptance criteria are satisfied or a genuine environmental blocker prevents progress.

The objective is a functional, reproducible application—not a collection of disconnected AI agents or a UI mockup.

## 2. Project definition — preserve the original topic

Build a multi-agent AI software engineering system in which four specialized agents collaborate to plan, develop, test/debug, and review software applications.

The system must use:

- CrewAI for agent orchestration.
- A coding-capable LLM through a supported provider integration for reasoning and code generation.
- Docker for isolated execution of generated application code.
- Python and FastAPI for the backend.
- Next.js, TypeScript, and a clean responsive UI for the frontend.
- Pydantic for structured input/output validation.
- Persistent storage for task runs, statuses, events, and reports.
- Automated tests for the application, agent workflow, and security-sensitive components.

Begin with Python application development and testing. Design the code so additional programming languages can be added later without redesigning the entire system.

Do not replace this project with a generic chatbot, generic agent builder, unrelated SaaS application, or simple code-generation interface.

## 3. Read the existing project context

Before modifying files:

1. Inspect the repository structure, existing source code, configuration, and Git status.
2. Read the available project specifications in `docs/`, especially the Technical Stack & Architecture and System Workflow & Implementation Plan documents.
3. Identify existing implementation work and preserve useful code.
4. Check the installed Python, Node.js, Docker, and dependency versions.
5. Consult current official CrewAI, Docker, FastAPI, and Next.js documentation when necessary. Verify package APIs and compatibility rather than relying on remembered or outdated examples.
6. Identify missing credentials or unavailable execution capabilities without exposing secrets.
7. Create or update `AGENTS.md` with concise, durable project instructions and establish a milestone checklist.

Use the existing project documents as the source of truth for architecture and scope. If a design detail is missing, choose the simplest safe, maintainable option and document the decision. Do not repeatedly ask for approval for routine implementation decisions.

After this read-only inspection, proceed with implementation. Do not stop after presenting the plan.

## 4. Required four-agent architecture

Implement four distinct CrewAI agents with separate responsibilities and validated structured outputs.

### Agent 1: Project Manager / Requirements Analyst

Responsibilities:
- Interpret the user's software requirement.
- Identify assumptions and ambiguities.
- Break the request into implementation steps.
- Define measurable acceptance criteria.
- Identify expected files, dependencies, and technical risks.
- Produce a structured development plan.

Output:
A validated plan containing the goal, assumptions, ordered tasks, expected files, acceptance criteria, and risks.

### Agent 2: Software Developer / Coder Agent

Responsibilities:
- Consume the approved development plan.
- Inspect the provided project workspace and relevant source files.
- Create or modify code using a controlled file-editing interface.
- Follow the selected language and project conventions.
- Add or update tests when appropriate.
- Return a change summary and a list of modified files.

Output:
A patch or changed files, implementation summary, dependency changes, and known limitations.

The Developer must operate only inside the assigned run workspace. It must not have unrestricted access to the host filesystem or arbitrary shell execution.

### Agent 3: Testing and Debugging Agent

Responsibilities:
- Execute approved test profiles in Docker.
- Capture process exit codes, standard output, standard error, and timeout information.
- Analyze failed tests and runtime errors.
- Produce structured, actionable debugging guidance.
- Request targeted changes from the Developer when appropriate.
- Re-run the required checks after fixes.

Output:
A test report with check names, statuses, failure details, log references, and suggested fixes.

The Testing Agent must not fabricate test results or claim that tests passed without execution evidence.

### Agent 4: Code Reviewer / Quality Assurance Agent

Responsibilities:
- Review the actual code diff against the original requirement and approved plan.
- Evaluate requirement coverage, correctness risks, maintainability, and missing tests.
- Flag suspicious or unsafe code patterns and potential secret exposure.
- Check the recorded test evidence.
- Distinguish verified facts from assumptions.
- Return a structured decision and prioritized findings.

Output:
A review report containing findings, severity, affected files where known, requirement coverage, and unresolved limitations.

The Reviewer must not declare the application fully correct or secure solely because tests pass.

## 5. Workflow controller

Implement an application-owned workflow controller. CrewAI manages agent orchestration, but ordinary application code must enforce state transitions, execution permissions, retry limits, cancellation, and cleanup.

Required workflow:

1. Accept and validate a user task.
2. Create a unique run ID and isolated workspace.
3. Invoke the Requirements Analyst.
4. Validate the plan and acceptance criteria.
5. Invoke the Developer to create a candidate implementation.
6. Validate file paths, file types, and output sizes.
7. Run permitted preflight checks.
8. Execute approved tests in a disposable Docker container.
9. If tests fail, invoke Testing/Debugging and route targeted fix guidance to the Developer.
10. Repeat testing after changes, subject to a bounded retry budget.
11. Invoke the Reviewer using the actual diff, acceptance criteria, and test evidence.
12. Allow a bounded correction cycle for actionable review findings.
13. Generate a final report and artifact manifest.
14. Clean up temporary containers and resources on every exit path.

Use a sensible initial limit of two code-fix iterations after the initial test run and at most one review-fix cycle. Make the limits configurable.

Implement explicit states such as QUEUED, VALIDATING, PLANNING, IMPLEMENTING, TESTING, DEBUGGING, REVIEWING, PACKAGING, SUCCEEDED, FAILED, CANCELLED, and TIMED_OUT.

Prevent invalid transitions and infinite loops. A failed run must not be reported as successful. Record cleanup failures separately from the original run failure.

## 6. Docker execution and security

This is a core requirement, not an optional enhancement.

Implement a Docker runner with a small, known Python runner image and a controlled execution interface.

Requirements:
- Execute generated code in a disposable, per-run container.
- Run as a non-root user and never use privileged mode.
- Apply CPU, memory, process-count, output-size, and wall-clock limits.
- Disable networking by default during generated-code execution.
- Never mount the host home directory, host credentials, SSH agent, or Docker socket into the execution container.
- Never expose provider API keys or application secrets to generated code.
- Use explicit allowlisted command profiles, such as approved pytest and Ruff commands.
- Invoke processes with argument arrays; do not construct shell commands from user or agent text.
- Validate workspace paths to prevent traversal outside the assigned directory.
- Limit file sizes and captured logs.
- Ensure containers are stopped and removed on success, failure, timeout, and cancellation.
- Never execute arbitrary Dockerfiles, privileged commands, or agent-generated deployment instructions in the initial release.
- Fail safely and record a useful error if Docker is unavailable.

If dependencies need to be installed, use a controlled preparation stage or a prebuilt runner image. Do not silently enable unrestricted networking to make a test pass.

Treat user-submitted code, repository content, and model-generated instructions as untrusted inputs. Docker is one layer of defense, not a guarantee of complete isolation.

If the available environment cannot run Docker, still implement the runner and its automated tests where possible. Report the exact unverified integration checks; never claim the sandbox has been successfully tested when it has not.

## 7. Backend implementation

Build a modular FastAPI backend with validated request and response schemas.

Required endpoints:

- `POST /api/runs` — create a software development run.
- `GET /api/runs/{run_id}` — retrieve status, current stage, iteration count, and summary.
- `GET /api/runs/{run_id}/events` — retrieve chronological agent and workflow events.
- `GET /api/runs/{run_id}/artifacts` — list generated files, diffs, test reports, and review reports.
- `POST /api/runs/{run_id}/cancel` — request safe cancellation.
- `GET /health` — health check.

Requirements:
- Use SQLite for a straightforward local MVP; make the persistence layer replaceable with PostgreSQL.
- Use structured logs associated with a run ID and stage.
- Persist task status, agent events, iteration counts, test reports, review findings, and artifact metadata.
- Keep long-running orchestration out of ordinary request-response execution where practical. Use a lightweight local execution approach initially and introduce a background queue only when justified.
- Implement meaningful validation, exception handling, cancellation, and cleanup.
- Never expose API keys, internal secrets, or unsafe absolute filesystem paths in API responses.
- Do not return fabricated results when a provider call or execution stage fails.

## 8. Frontend implementation

Build a functional, polished, responsive Next.js and TypeScript interface.

Include:

1. **Dashboard:** overview of recent runs and their statuses.
2. **New Task:** task description input, supported language selection, and submission.
3. **Run Details:** current workflow stage, progress timeline, four agent roles, iteration count, and timestamps.
4. **Agent Activity:** readable status events and useful error summaries.
5. **Test Results:** executed checks, pass/fail status, exit codes, and failure details.
6. **Code Review:** prioritized findings, recommendations, and requirement coverage.
7. **Artifacts:** generated source files, patch/diff, test report, review report, and final summary.
8. **Cancellation:** a working action to request cancellation of an active run.

Design standards:
- Use a professional developer-tool visual style.
- Provide loading, empty, success, failure, and cancellation states.
- Show real backend data; do not substitute hard-coded demo statuses for actual results.
- Display the difference between running, successful, failed, timed out, and awaiting human review.
- Make error messages understandable and actionable.
- Ensure the interface works at desktop and mobile widths.
- Keep API logic separate from presentational components.
- Do not spend excessive time on animations or decorative effects before core functionality works.

## 9. Final output and artifacts

Each run should produce, where applicable:

- Original task and validated development plan.
- Generated or modified source files.
- A patch/diff for review.
- Preflight and test reports.
- Relevant execution logs.
- Reviewer findings.
- Iteration history.
- A final summary of completed requirements, failed checks, and limitations.
- An artifact manifest with safe relative paths and checksums.

Clearly label unverified requirements. Do not automatically merge changes, deploy to production, or execute destructive external actions.

## 10. Testing requirements

Create a meaningful automated test suite, not just placeholder tests.

Include:

### Unit tests
- Input and output schema validation.
- Workflow state transitions.
- Retry limits.
- Path validation.
- Command allowlist.
- Artifact manifest validation.
- Error and cancellation handling.

### Integration tests
- A successful end-to-end agent workflow using mocked LLM responses where appropriate.
- Docker runner behavior using a small known test fixture when Docker is available.
- Test failure followed by a bounded correction and retest.
- Reviewer rejection and review-fix handling.
- Persistence and API responses.

### Security and failure tests
- Command injection attempts.
- Path traversal attempts.
- Oversized file and log output.
- Execution timeout and resource-limit handling where feasible.
- Container cleanup.
- Invalid or malformed agent outputs.
- Provider timeout and missing-credential behavior.
- Cancellation during execution.

### Frontend checks
- TypeScript type checking.
- Linting.
- Production build.
- Core task-submission and run-status behavior.

Use mocks for expensive or nondeterministic LLM calls in ordinary CI tests. Provide an optional live-model integration test that requires an explicitly configured API key.

Do not require a paid API call for every unit test.

## 11. Configuration and reproducibility

Provide:
- `.env.example` with placeholder values only.
- `.gitignore` that excludes secrets, virtual environments, generated artifacts, and local databases as appropriate.
- Pinned or bounded dependencies with a reproducible installation process.
- Clear setup commands.
- Docker runner build instructions.
- Database initialization instructions.
- Frontend and backend development commands.
- A demo workflow.
- Troubleshooting instructions.
- A README describing architecture, limitations, security boundaries, and known requirements.

Never create a real API key, hard-code a secret, or commit a populated `.env` file. If a required credential is absent, implement the integration and explain how to configure it.

## 12. Repository structure

Use a clear, maintainable layout similar to:

four-agent-engineering-team/
  AGENTS.md
  README.md
  docs/
  backend/
    app/
      api/
      agents/
      orchestration/
      sandbox/
      persistence/
      schemas/
      services/
    tests/
    pyproject.toml
    Dockerfile
  frontend/
    src/
    package.json
  docker/
    python-runner/
      Dockerfile
  scripts/
  docker-compose.yml
  .env.example
  .gitignore

Adapt this structure if the repository already has a sound layout. Avoid needless abstractions and duplicate implementations.

## 13. Implementation strategy

Work in small, verifiable milestones:

1. Repository inspection, decisions, configuration, and schemas.
2. Backend skeleton and persistence.
3. Four-agent CrewAI implementation and validated output contracts.
4. Workflow controller and bounded retry logic.
5. Docker runner and execution security.
6. Test/debug feedback loop and code review.
7. API integration and artifact handling.
8. Frontend and run visualization.
9. Integration, regression, and security tests.
10. Documentation, reproducible setup, and final verification.

For every milestone:
- Implement actual functionality.
- Run the relevant tests and checks.
- Fix failures before moving on.
- Update the checklist and documentation.
- Keep the application runnable.
- Avoid leaving stubs, TODO-only methods, fake integrations, or buttons that do nothing.

Use mocks only at deliberate test boundaries, not as replacements for the actual application workflow.

Do not stop after milestone planning. Continue through all milestones that the environment and available credentials permit.

## 14. Definition of done

The project is complete only when:

- The backend starts using documented commands.
- The frontend starts and can communicate with the backend.
- A user can submit a task through the interface or API.
- All four agent roles are implemented and integrated through the real workflow.
- The planner creates structured acceptance criteria.
- The developer produces actual source changes in the run workspace.
- The Docker runner executes the approved checks when Docker is available.
- Failed tests can trigger a bounded debugging and retesting cycle.
- The reviewer evaluates actual changes and test evidence.
- The system persists statuses, events, reports, and artifact metadata.
- The UI displays actual run progress and results.
- Cancellation, timeouts, failures, and cleanup are handled.
- Unit, integration, and frontend checks have been run.
- Critical failures have been fixed or clearly reported as blocked by the environment.
- Setup and demo instructions work from a clean checkout to the extent the environment permits.
- No credentials are committed, and the final security limitations are documented.

A successful frontend build alone does not satisfy the definition of done.

## 15. Final verification and reporting

Before finishing:

1. Run backend tests and lint/type checks.
2. Run frontend linting, type checking, and production build.
3. Run integration tests, including Docker tests if the environment supports them.
4. Inspect Git diff for accidental changes, secrets, generated clutter, and incomplete implementations.
5. Check that documented commands and configuration match the actual repository.
6. Fix any failures you can resolve.
7. Rerun the relevant checks after fixes.
8. Update README and the implementation checklist.

Do not claim that a command passed unless you actually ran it and observed its result. Clearly distinguish passing checks, failing checks, skipped checks, and environment-blocked checks.

Do not stop merely because one command fails. Diagnose the failure, try a reasonable fix, and continue with independent work where possible.

Do not deploy, publish a package, push to a remote repository, or perform destructive external actions without explicit authorization.

At completion, provide:
- A summary of the implemented system.
- The four agents and their responsibilities.
- The architecture and repository structure.
- Exact setup and run commands.
- Environment variables the user must configure.
- Tests and checks actually executed, with their results.
- Known limitations and any unverified integrations.
- The remaining steps, if any, that genuinely require human action.

**Start by inspecting the repository and its specifications. Then implement the complete project, verify it with real checks, and continue fixing issues until the acceptance criteria are met or a clearly evidenced blocker remains.**