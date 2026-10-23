System Workflow & Implementation Plan
1. Objective
Define how a request moves through the four-agent engineering team. The application owns state transitions, permissions, retry limits, timeouts, and cleanup; agents provide task-specific reasoning and outputs.
2. End-to-End Workflow
SUBMIT
 -> VALIDATE REQUEST
 -> CREATE RUN + WORKSPACE
 -> PLANNER: plan + acceptance criteria
 -> VALIDATE PLAN
 -> DEVELOPER: code/patch
 -> STATIC CHECKS
 -> DOCKER SANDBOX: approved tests
 -> if tests fail and budget remains:
      TEST/DEBUG analyzes logs
      -> DEVELOPER applies targeted fix
      -> rerun checks and tests
 -> REVIEWER checks diff + evidence + requirements
 -> optional bounded review-fix cycle
 -> PACKAGE ARTIFACTS
 -> FINALIZE RUN
 -> CLEAN UP
Suggested initial limits: two code-fix iterations after the first test run, one review-fix cycle, maximum run duration, and token/cost limits.
3. Stages
1. Validate: check task size, language, framework, paths, and policy settings.
2. Create workspace: unique run ID and isolated per-run workspace.
3. Plan: planner returns steps, expected files, acceptance criteria, dependencies, and risks.
4. Implement: developer returns a patch/changed files and summary.
5. Preflight: run approved syntax/lint checks.
6. Test: execute approved commands in disposable Docker container.
7. Debug loop: test/debug agent interprets failures; developer makes a bounded fix; tests rerun.
8. Review: reviewer checks diff and evidence; critical findings block success or require a controlled fix cycle.
9. Package: produce source/patch, test report, review report, and artifact manifest.
10. Cleanup: stop/remove container and apply workspace-retention policy on every path.
4. State Machine
QUEUED -> VALIDATING -> PLANNING -> IMPLEMENTING -> PRECHECKING -> TESTING
TESTING -> DEBUGGING -> IMPLEMENTING (bounded)
TESTING -> REVIEWING -> PACKAGING -> SUCCEEDED

Any active state -> FAILED / CANCELLED / TIMED_OUT
Every terminal path performs cleanup and finalizes the record.
Keep the primary run result separate from cleanup status, so cleanup errors do not erase the original failure.
5. Agent Output Contracts
- Planner: goal, assumptions, steps[], files_expected[], acceptance_criteria[], risks[]
- Developer: changed_files[], patch_ref, summary, dependencies[], known_limitations[]
- Test/Debug: status, checks[], failures[], log_refs[], fix_guidance[], limitations
- Reviewer: decision, findings[], requirement_coverage[], limitations[]
Validate outputs against typed schemas before using them. Malformed outputs must never trigger execution.
6. Failure Handling
Failure	Handling
Model/API timeout	Bounded retry with backoff, then fail cleanly
Invalid agent output	One schema-repair attempt, then fail stage
Compile/test failure	Capture logs and route through bounded debug loop
Container timeout/resource limit	Terminate container and record the limit event
Unsafe command	Reject through command policy
Path traversal/oversized output	Reject output and stop or quarantine run
Cancellation	Stop worker/container and finalize as cancelled
Critical review finding	Do not mark success; bounded fix cycle or human review
Cleanup failure	Record separately and alert operator


7. Sandbox Rules
- Use pinned runner images; do not build arbitrary agent-provided Dockerfiles in v1.
- Non-root user, no privileged mode, drop capabilities, read-only root filesystem where practical.
- Per-run workspace only; no Docker socket, broad host mounts, credentials, or SSH agent.
- Network off by default; controlled dependency preparation if required.
- Resource/time/log limits.
- Use explicit allowlisted commands such as python -m pytest and ruff check; avoid shell=True.
- Always clean up containers and temporary files.
- For untrusted public workloads, consider stronger isolation than a shared Docker daemon.
8. Events
Record run.created, stage.started, agent.started, agent.completed, sandbox.started, sandbox.completed, test.failed, iteration.started, review.completed, run.completed, run.failed, and cleanup.completed. Include run_id, timestamps, stage/agent, duration, status, and safe references to logs/artifacts.
9. Milestones
Milestone	Deliverable	Done when
M1 Skeleton	Python package, CLI, schemas	Request validates; unit tests pass
M2 Agent workflow	Planner + Developer	Plan and patch produced
M3 Sandbox	Docker runner + command policy	Approved test runs with limits and cleanup
M4 Debug loop	Test/Debug + retry controller	Seeded failure captured and corrected within budget
M5 Review/report	Reviewer + artifact manifest	Final report includes evidence and limitations
M6 API	FastAPI + persistence	Create/query/cancel/inspect runs
M7 UI	Task form and run timeline	User can inspect outputs in browser
M8 Hardening	CI, security/integration tests, quotas	Failure paths and restrictions are tested


10. Testing Strategy
- Unit tests: schemas, state transitions, retry limits, command allowlist, path validation, artifact manifest.
- Integration tests: fake model responses and disposable test container.
- Security tests: command injection, path traversal, output caps, timeout, cancellation, no-network, cleanup.
- Regression suite: fixed benchmark tasks run after prompt/model changes.
11. Demonstration Scenario
1. Submit: “Create a Python calculator with add, subtract, multiply, divide, and pytest tests.”
2. Planner creates acceptance criteria.
3. Developer creates source and tests.
4. Docker runs approved pytest command.
5. Demonstrate a controlled seeded defect and a single correction cycle.
6. Reviewer checks the diff, evidence, and coverage.
7. Show patch, test summary, review findings, iteration count, and limitations.
12. Overall Definition of Done
- Four distinct roles with validated structured outputs.
- Workflow controller enforces states and bounded retries.
- Code runs only via the restricted sandbox.
- Logs, exit codes, and artifacts are retained according to policy.
- Failure, timeout, cancellation, and cleanup are observable.
- Final report accurately states what passed and what remains unverified.
- Demo and automated tests work from a clean checkout.