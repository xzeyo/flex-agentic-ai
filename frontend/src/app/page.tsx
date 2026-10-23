"use client";

import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { api, Artifact, Check, checkPassed, Event, Run, terminal } from "@/lib/api";

const roles = [
  {name: "Planner", mark: "01", detail: "Requirements & acceptance", stages: ["PLANNING"]},
  {name: "Developer", mark: "02", detail: "Source & targeted fixes", stages: ["IMPLEMENTING", "PRECHECKING"]},
  {name: "Test / Debug", mark: "03", detail: "Checks & failure analysis", stages: ["TESTING", "DEBUGGING"]},
  {name: "Reviewer", mark: "04", detail: "Diff & evidence review", stages: ["REVIEWING", "PACKAGING"]},
];
const date = (value: string) => new Date(value).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
const label = (value: string) => value.toLowerCase().replaceAll("_", " ");
async function readArtifact(runId: string, path: string) {
  const response = await fetch(`/api/runs/${runId}/artifacts/${path.split("/").map(encodeURIComponent).join("/")}`);
  if (!response.ok) throw new Error("Artifact could not be opened.");
  return response.text();
}

function Badge({state}: {state: string}) {
  return <span className={`badge ${state.toLowerCase()}`}><i />{label(state)}</span>;
}

function CheckCard({check}: {check: Check}) {
  return <article className="check-card"><div className="row"><h3>{check.profile === "lint" ? "Ruff · static checks" : "pytest · test suite"}</h3><span className={checkPassed(check) ? "positive" : "negative"}>{checkPassed(check) ? "Passed" : "Failed"}</span></div><p className="muted">Exit {check.exit_code ?? "—"} · {check.duration_seconds.toFixed(2)}s{check.timed_out && " · timed out"}{check.output_limited && " · output capped"}{check.oom_killed && " · memory limit"}</p><pre>{check.output || "No output captured."}</pre></article>;
}

export default function Home() {
  const [runs, setRuns] = useState<Run[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [run, setRun] = useState<Run | null>(null);
  const [events, setEvents] = useState<Event[]>([]);
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [tab, setTab] = useState("Activity");
  const [task, setTask] = useState("");
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [error, setError] = useState("");
  const [artifactText, setArtifactText] = useState<{path: string; text: string} | null>(null);
  const artifactRequest = useRef(0);
  const autoOpenedRun = useRef<string | null>(null);
  const tabChosen = useRef(false);
  const [selectionVersion, setSelectionVersion] = useState(0);
  const taskInput = useRef<HTMLTextAreaElement>(null);

  const refresh = useCallback(async (signal?: AbortSignal) => {
    try {
      const recent = await api.list();
      const id = selected || recent.find(item => item.state === "SUCCEEDED")?.id || recent[0]?.id;
      if (id) {
        const [current, activity, outputs] = await Promise.all([api.get(id), api.events(id), api.artifacts(id)]);
        if (signal?.aborted) return;
        setRun(current); setEvents(activity); setArtifacts(outputs);
        if (current.state === "SUCCEEDED" && !tabChosen.current) setTab("Artifacts");
      }
      if (signal?.aborted) return;
      setRuns(recent); setError("");
    } catch (err) {
      if (!signal?.aborted) setError(err instanceof Error ? err.message : "Could not load runs.");
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }, [selected]);

  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => { await refresh(controller.signal); if (!controller.signal.aborted) timer = setTimeout(poll, 2500); };
    void poll();
    return () => { controller.abort(); clearTimeout(timer); };
  }, [refresh]);

  useEffect(() => {
    const selectedRun = selected ?? run?.id;
    if (!run || selectedRun !== run.id || run.state !== "SUCCEEDED") return;
    const openKey = `${run.id}:${selectionVersion}`;
    if (autoOpenedRun.current === openKey) return;
    const source = artifacts.find(item => item.path.startsWith("source/") && /\.(py|md|txt)$/i.test(item.path));
    if (!source) return;

    autoOpenedRun.current = openKey;
    const sequence = ++artifactRequest.current;
    void readArtifact(run.id, source.path).then(text => {
      if (sequence === artifactRequest.current) setArtifactText({path: source.path, text});
    }).catch(err => {
      if (sequence === artifactRequest.current) setError(err instanceof Error ? err.message : "Artifact could not be opened.");
    });
  }, [selected, run, artifacts, selectionVersion]);

  async function submit(event: FormEvent) {
    event.preventDefault(); setSubmitting(true); setError("");
    try {
      const created = await api.create(task.trim());
      artifactRequest.current++;
      tabChosen.current = false;
      setRun(created); setSelected(created.id); setEvents([]); setArtifacts([]); setArtifactText(null); setTab("Activity");
      setRuns(previous => [created, ...previous.filter(item => item.id !== created.id)]);
      setTask("");
    } catch (err) { setError(err instanceof Error ? err.message : "Task submission failed."); }
    finally { setSubmitting(false); }
  }

  async function cancel() {
    if (!run) return;
    setCancelling(true);
    try { setRun(await api.cancel(run.id)); }
    catch (err) { setError(err instanceof Error ? err.message : "Cancellation failed."); }
    finally { setCancelling(false); }
  }

  async function inspect(item: Artifact) {
    if (!run) return;
    const sequence = ++artifactRequest.current;
    try {
      const text = await readArtifact(run.id, item.path);
      if (sequence === artifactRequest.current) setArtifactText({path: item.path, text});
    } catch (err) { setError(err instanceof Error ? err.message : "Artifact could not be opened."); }
  }

  const active = runs.filter(item => !terminal(item.state)).length;
  const successful = runs.filter(item => item.state === "SUCCEEDED").length;
  const review = run?.report.review;

  return <div className="shell">
    <aside className="sidebar">
      <Link className="brand" href="/"><span className="brand-icon">q<span>·</span></span><span>quartet<small>ENGINEERING CONSOLE</small></span></Link>
      <div className="workspace-label"><span className="workspace-icon">W</span>Local workspace<span className="muted">⌄</span></div>
      <nav aria-label="Main navigation"><a href="#overview" className="nav-active"><span>▦</span> Overview <small>{runs.length}</small></a><button onClick={() => taskInput.current?.focus()}><span>＋</span> New task</button></nav>
      <div className="sidebar-heading">YOUR TEAM <span>4 AGENTS</span></div>
      <div className="team-list">{roles.map(role => <div key={role.name}><span className="role-icon">{role.mark}</span><div>{role.name}<small>{role.detail}</small></div><i className={run && role.stages.includes(run.state) ? "agent-dot busy" : "agent-dot"} /></div>)}</div>
      <div className="sidebar-footer"><span className="sandbox-icon">◇</span><div>Isolated by design<small>Python 3.12 · Docker sandbox</small></div><span className="positive">●</span></div>
    </aside>

    <main id="overview">
      <header className="topbar"><span>Workspace <span className="slash">/</span> <strong>Overview</strong></span><span className="local"><i />LOCAL ENVIRONMENT</span></header>
      <div className="content">
        <div className="page-heading"><div><div className="eyebrow">YOUR IDEAS, ENGINEERED.</div><h1>A small team. A complete workflow.</h1><p>From a software task to tested code, with every decision in view.</p></div><span className="version">v0.1 <span>PYTHON EDITION</span></span></div>
        <section className="stats" aria-label="Run statistics"><div><span>Total runs</span><strong>{runs.length}<small>in this workspace</small></strong></div><div><span>In progress</span><strong>{active}<small><i className="amber-dot" />agents at work</small></strong></div><div><span>Verified runs</span><strong>{successful}<small>checks + review accepted</small></strong></div></section>

        {error && <div className="error" role="alert"><span>{error}</span><button onClick={() => void refresh()}>Retry</button></div>}

        <section className="composer panel"><div className="section-title"><span className="square-plus">＋</span><div><h2>What should we build?</h2><p>Give your team a clear task. They’ll handle the workflow.</p></div><span className="subtle-tag">NEW TASK</span></div><form onSubmit={submit}><label htmlFor="task" className="sr-only">Software task</label><textarea id="task" ref={taskInput} value={task} onChange={event => setTask(event.target.value)} minLength={10} maxLength={12000} required placeholder="Create a Python calculator with add, subtract, multiply, divide, and pytest tests…" /><div className="composer-bottom"><div className="composer-options"><label><span className="muted">Language</span> <select aria-label="Language" defaultValue="python"><option value="python">Python 3.12</option></select></label><span className="separator" /><span>◇ <span className="muted">Network off · standard library</span></span></div><button className="primary" type="submit" disabled={submitting || task.trim().length < 10}>{submitting ? "Submitting…" : "Start engineering"}<span>↗</span></button></div></form></section>

        <div className="work-grid">
          <section className="runs-panel panel"><div className="panel-heading"><h2>Recent runs <span>{runs.length}</span></h2><span className="muted">↻ Live</span></div>{loading ? <div className="empty">Connecting to your workspace…</div> : runs.length === 0 ? <div className="empty"><span className="empty-icon">⌘</span><h3>Your first run starts here</h3><p>Submit a task above to bring your team together.</p></div> : <div className="run-list">{runs.map(item => <button key={item.id} className={`run-item ${run?.id === item.id ? "selected" : ""}`} onClick={() => {tabChosen.current = false; setSelected(item.id); setSelectionVersion(value => value + 1); setTab(item.state === "SUCCEEDED" ? "Artifacts" : "Activity"); setArtifactText(null); artifactRequest.current++;}}><div className="row"><span className="run-short">{item.id.slice(0, 8)}</span><span className="run-time">{date(item.created_at)}</span></div><h3>{item.task}</h3><div className="row"><Badge state={item.state} /><span className="muted">{item.iteration + item.review_iteration} fixes <span>↗</span></span></div></button>)}</div>}<div className="list-footer">Last {runs.length} runs · stored locally</div></section>

          <section className="detail-panel panel" aria-label="Run details">
            {!run ? <div className="empty detail-empty"><div className="orbit">q<span>·</span></div><h2>One task. Four perspectives.</h2><p>Your team’s plan, source, test evidence, and review will appear here.</p><div className="empty-steps">Plan <span>→</span> Build <span>→</span> Test <span>→</span> Review</div></div> : <>
              <div className="detail-heading"><div className="row"><span className="eyebrow">RUN / {run.id.slice(0, 8)}</span><Badge state={run.state} /></div><h2>{run.task}</h2><div className="row detail-meta"><span>Updated {date(run.updated_at)} · {run.iteration} test fixes · {run.review_iteration} review fixes{run.report.duration_seconds !== undefined && ` · ${run.report.duration_seconds}s`}</span>{!terminal(run.state) && <button className="cancel" disabled={cancelling || run.cancelled} onClick={() => void cancel()}>{cancelling || run.cancelled ? "Cancelling…" : "Cancel run"}</button>}</div></div>
              <div className="workflow-roles">{roles.map(role => {const started = events.some(event => event.kind === "agent.started" && event.data.agent === ({Planner: "planner", Developer: "developer", "Test / Debug": "debugger", Reviewer: "reviewer"}[role.name])); const current = role.stages.includes(run.state); return <div key={role.name} className={current ? "current" : started ? "visited" : ""}><span>{role.mark}</span><strong>{role.name}</strong><small>{current && !terminal(run.state) ? "Working…" : started ? "Invoked" : "Pending"}</small></div>;})}</div>
              {run.summary && <p className={`run-summary ${run.state === "SUCCEEDED" ? "success-summary" : ""}`}>{run.summary}</p>}
              <div className="tabs" role="tablist" aria-label="Run outputs">{["Activity", "Tests", "Review", "Artifacts"].map(name => <button role="tab" aria-selected={tab === name} aria-controls={`panel-${name}`} id={`tab-${name}`} className={tab === name ? "active-tab" : ""} key={name} onClick={() => {tabChosen.current = true; setTab(name);}}>{name}{name === "Artifacts" && artifacts.length > 0 && <small>{artifacts.length}</small>}</button>)}</div>
              <div className="tab-content" id={`panel-${tab}`} role="tabpanel" aria-labelledby={`tab-${tab}`}>
                {tab === "Activity" && <>{events.length === 0 ? <p className="empty-inline">Waiting for the first workflow event…</p> : <ol className="timeline">{events.map(event => <li key={event.seq}><span className={`timeline-dot ${event.kind.includes("failed") ? "failure" : ""}`} /><div><div className="row"><strong>{event.message}</strong><time>{date(event.timestamp)}</time></div><small>{label(event.stage)} <span>·</span> {event.kind}</small></div></li>)}</ol>}</>}
                {tab === "Tests" && <>{run.report.checks?.length ? run.report.checks.map(check => <CheckCard key={check.profile} check={check} />) : <p className="empty-inline">Executed check evidence will appear here when available.</p>}<p className="evidence-note">Results reflect executed checks. Passing tests do not prove complete correctness.</p></>}
                {tab === "Review" && <>{review ? <><div className="review-decision">Review decision <strong>{label(review.decision)}</strong></div>{review.findings.map((finding, index) => <article className="finding" key={index}><span className={`severity ${finding.severity}`}>{finding.severity}</span><h3>{finding.title}</h3><p>{finding.detail}</p>{finding.file && <code>{finding.file}</code>}</article>)}<h3 className="coverage-title">Requirement coverage</h3>{review.requirement_coverage.map((criterion, index) => <div className="coverage" key={index}><span className={criterion.met ? "positive" : "negative"}>{criterion.met ? "✓" : "!"}</span><div><strong>{criterion.criterion}</strong><p>{criterion.evidence}</p></div></div>)}{review.limitations.map((text, index) => <p className="evidence-note" key={index}>{text}</p>)}</> : <p className="empty-inline">The reviewer will inspect the actual diff and recorded test evidence.</p>}</>}
                {tab === "Artifacts" && <>{artifacts.length ? artifacts.map(item => <button className="artifact" key={item.path} onClick={() => void inspect(item)}><span>▤</span><div><strong>{item.path}</strong><small>{item.size.toLocaleString()} bytes · SHA256 {item.sha256.slice(0, 12)}…</small></div><span>↗</span></button>) : <p className="empty-inline">Source and reports are packaged at the end of the run.</p>}{artifactText && <div className="artifact-preview"><div className="row"><strong>{artifactText.path}</strong><button onClick={() => setArtifactText(null)}>Close</button></div><pre>{artifactText.text}</pre></div>}</>}
              </div>
              {run.report.limitations && <div className="limitations">{run.report.limitations.map((text, index) => <p key={index}>{text}</p>)}</div>}
            </>}
          </section>
        </div>
        <footer className="page-footer"><span>Built to make the work visible.</span><span>Application-controlled workflow <i>·</i> Disposable execution <i>·</i> Evidence first</span></footer>
      </div>
    </main>
  </div>;
}
