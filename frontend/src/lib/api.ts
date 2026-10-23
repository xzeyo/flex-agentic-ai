export type Check = { profile: string; exit_code: number | null; duration_seconds: number; output: string; timed_out: boolean; output_limited: boolean; oom_killed: boolean };
export type Review = { decision: string; findings: { severity: string; title: string; detail: string; file: string | null }[]; requirement_coverage: {criterion: string; met: boolean; evidence: string}[]; limitations: string[] };
export type Run = { id: string; task: string; state: string; created_at: string; updated_at: string; iteration: number; review_iteration: number; cancelled: boolean; summary: string; report: {checks?: Check[]; review?: Review | null; duration_seconds?: number; model_calls?: number; limitations?: string[]; cleanup_errors?: string[]} };
export type Event = { seq: number; timestamp: string; kind: string; stage: string; message: string; data: Record<string, unknown> };
export type Artifact = { path: string; size: number; sha256: string };

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {...init, cache: "no-store", headers: {"Content-Type": "application/json", ...init?.headers}});
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(typeof body?.detail === "string" ? body.detail : `Request failed (${response.status}). Check that the API is running.`);
  }
  return response.json() as Promise<T>;
}
export const api = {
  list: () => request<Run[]>("/api/runs"),
  get: (id: string) => request<Run>(`/api/runs/${id}`),
  events: (id: string) => request<Event[]>(`/api/runs/${id}/events`),
  artifacts: (id: string) => request<Artifact[]>(`/api/runs/${id}/artifacts`),
  create: (task: string) => request<Run>("/api/runs", {method: "POST", body: JSON.stringify({task, language: "python"})}),
  cancel: (id: string) => request<Run>(`/api/runs/${id}/cancel`, {method: "POST"}),
};
export const terminal = (state: string) => ["SUCCEEDED", "FAILED", "CANCELLED", "TIMED_OUT"].includes(state);
export const checkPassed = (check: Check) => check.exit_code === 0 && !check.timed_out && !check.output_limited && !check.oom_killed;
