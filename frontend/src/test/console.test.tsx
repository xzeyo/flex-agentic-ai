import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import Home from "@/app/page";
import { api, Artifact, checkPassed, Run } from "@/lib/api";

vi.mock("@/lib/api", async (original) => ({...await original<typeof import("@/lib/api")>(), api: {list: vi.fn(), get: vi.fn(), events: vi.fn(), artifacts: vi.fn(), create: vi.fn(), cancel: vi.fn()}}));
const sample: Run = {id: "d6621efa-18e2-422c-a197-6136340835cd", task: "Create a calculator with tests", state: "QUEUED", created_at: new Date().toISOString(), updated_at: new Date().toISOString(), iteration: 0, review_iteration: 0, cancelled: false, summary: "", report: {}};
const verifiedRun = (id: string, task: string): Run => ({...sample, id, task, state: "SUCCEEDED", report: {checks: [], review: {decision: "approve", findings: [], requirement_coverage: [], limitations: []}}});
const artifact = (path: string): Artifact => ({path, size: 40, sha256: "a".repeat(64)});

beforeEach(() => {vi.mocked(api.list).mockResolvedValue([]); vi.mocked(api.events).mockResolvedValue([]); vi.mocked(api.artifacts).mockResolvedValue([]); vi.mocked(api.get).mockResolvedValue(sample);});
afterEach(() => {cleanup(); vi.clearAllMocks(); vi.unstubAllGlobals();});
describe("engineering console", () => {
  it("submits a real task and displays the accepted run", async () => {
    vi.mocked(api.create).mockResolvedValue(sample);
    render(<Home />);
    await screen.findByText("Your first run starts here");
    fireEvent.change(screen.getByLabelText("Software task"), {target: {value: sample.task}});
    fireEvent.click(screen.getByRole("button", {name: /Start engineering/}));
    await waitFor(() => expect(api.create).toHaveBeenCalledWith(sample.task));
    expect(await screen.findByText(/RUN \/ d6621efa/)).toBeInTheDocument();
  });
  it("shows server failures without fabricated runs", async () => {
    vi.mocked(api.list).mockRejectedValue(new Error("API unavailable"));
    render(<Home />);
    expect(await screen.findByRole("alert")).toHaveTextContent("API unavailable");
    expect(screen.getByText("Your first run starts here")).toBeInTheDocument();
  });
  it("requests cancellation and displays it as pending", async () => {
    vi.mocked(api.list).mockResolvedValue([sample]);
    vi.mocked(api.cancel).mockResolvedValue({...sample, cancelled: true});
    render(<Home />);
    fireEvent.click(await screen.findByRole("button", {name: "Cancel run"}));
    await waitFor(() => expect(api.cancel).toHaveBeenCalledWith(sample.id));
    expect(await screen.findByRole("button", {name: "Cancelling…"})).toBeDisabled();
  });
  it("opens generated source automatically for each selected verified run", async () => {
    const first = verifiedRun("11111111-1111-4111-8111-111111111111", "Build the first mini task");
    const second = verifiedRun("22222222-2222-4222-8222-222222222222", "Build the second mini task");
    const newerFailure = {...sample, id: "33333333-3333-4333-8333-333333333333", task: "A newer failed run", state: "FAILED"};
    vi.mocked(api.list).mockResolvedValue([newerFailure, first, second]);
    vi.mocked(api.get).mockImplementation(async id => id === second.id ? second : first);
    vi.mocked(api.artifacts).mockImplementation(async id => [artifact(id === second.id ? "source/second.py" : "source/first.py")]);
    vi.stubGlobal("fetch", vi.fn(async input => ({
      ok: true,
      text: async () => String(input).includes(second.id) ? "def second_task(): pass" : "def first_task(): pass",
    } as Response)));

    render(<Home />);
    expect(await screen.findByText("def first_task(): pass")).toBeInTheDocument();
    expect(screen.getByRole("tab", {name: /Artifacts/})).toHaveAttribute("aria-selected", "true");

    fireEvent.click(screen.getByRole("button", {name: /Build the second mini task/}));
    expect(await screen.findByText("def second_task(): pass")).toBeInTheDocument();
    expect(screen.getAllByText("source/second.py")).toHaveLength(2);
  });
  it("does not display resource-limited execution as passing", () => {
    expect(checkPassed({profile: "test", exit_code: 0, output: "", duration_seconds: 1, timed_out: true, oom_killed: false, output_limited: false})).toBe(false);
  });
});
