import { create } from "zustand";

import { api, ApiError } from "@/api";
import { useAuth } from "@/hooks/useAuth";
import type { AppConfig, ReportInfo, ResearchView, RunSummary, Step } from "@/types";

const MODEL_KEY = "ro-model";

function storedModel(): string {
  try {
    return localStorage.getItem(MODEL_KEY) ?? "auto";
  } catch {
    return "auto";
  }
}

interface AppState {
  config: AppConfig | null;
  runs: RunSummary[];
  model: string;
  view: ResearchView | null;
  sidebarOpen: boolean;
  controller: AbortController | null;
  boot: () => Promise<void>;
  setModel: (model: string) => void;
  setSidebarOpen: (open: boolean) => void;
  newResearch: () => void;
  openRun: (id: string) => Promise<void>;
  ask: (question: string) => Promise<void>;
  stop: () => void;
  generateReport: (pages: number) => Promise<void>;
  deleteRun: (id: string) => Promise<void>;
  deleteAllRuns: () => Promise<void>;
}

function applyStep(steps: Step[], step: Step): Step[] {
  const index = steps.findLastIndex((item) => item.step === step.step && item.status === "running");
  if (index < 0) return [...steps, step];
  return steps.map((item, i) => (i === index ? step : item));
}

export const useApp = create<AppState>((set, get) => {
  const refreshRuns = async () => set({ runs: await api.runs() });
  const updateView = (patch: Partial<ResearchView>) =>
    set((state) => (state.view ? { view: { ...state.view, ...patch } } : state));

  return {
    config: null,
    runs: [],
    model: storedModel(),
    view: null,
    sidebarOpen: false,
    controller: null,

    boot: async () => {
      const [config, runs] = await Promise.all([api.config(), api.runs()]);
      const { model } = get();
      const stale = model !== "auto" && !config.models.some((m) => m.id === model);
      set({ config, runs, model: stale ? "auto" : model });
    },
    setModel: (model) => {
      try {
        localStorage.setItem(MODEL_KEY, model);
      } catch {
        /* Storage unavailable: the choice just lasts for this session. */
      }
      set({ model });
    },
    setSidebarOpen: (sidebarOpen) => set({ sidebarOpen }),
    newResearch: () => {
      get().controller?.abort();
      set({ view: null, sidebarOpen: false });
    },
    openRun: async (id) => {
      get().controller?.abort();
      set({ sidebarOpen: false });
      const run = await api.run(id);
      const failed = run.status !== "completed";
      set({
        view: {
          runId: run.id,
          question: run.question,
          status: failed ? (run.status === "failed" ? "error" : "rejected") : "done",
          steps: run.result?.steps ?? [],
          result: run.result,
          message: run.error,
          report: run.report,
          reportError: null,
          reportPages: run.report.requested_pages,
        },
      });
    },
    ask: async (question) => {
      get().controller?.abort();
      const controller = new AbortController();
      const limit = get().config?.max_reports_per_run ?? 0;
      set({
        controller,
        view: {
          runId: null,
          question,
          status: "streaming",
          steps: [],
          result: null,
          message: null,
          report: null,
          reportError: null,
          reportPages: null,
        },
      });
      const setCredits = useAuth.getState().setCredits;
      try {
        await api.research(
          question,
          get().model,
          ({ event, data }) => {
            if (controller.signal.aborted) return;
            if (event === "started") {
              setCredits(data.credits);
              updateView({ runId: data.run_id });
            } else if (event === "step") {
              set((state) => (state.view ? { view: { ...state.view, steps: applyStep(state.view.steps, data) } } : state));
            } else if (event === "result") {
              setCredits(data.credits);
              updateView({
                status: "done",
                result: data.result,
                report: { status: "none", title: null, pages: null, requested_pages: null, generations: 0, generations_limit: limit },
              });
              // The question itself asked for a PDF, so that counts as the explicit request.
              if (data.report_request) void get().generateReport(data.report_request.pages);
            } else {
              setCredits(data.credits);
              updateView({ status: event === "rejected" ? "rejected" : "error", message: data.message });
            }
          },
          controller.signal,
        );
        if (!controller.signal.aborted && get().view?.status === "streaming") {
          updateView({ status: "error", message: "The connection ended before the research finished." });
        }
      } catch (err) {
        if (controller.signal.aborted) return;
        updateView({
          status: "error",
          message: err instanceof ApiError ? err.message : "Could not reach the server. Please try again.",
        });
      } finally {
        if (get().controller === controller) set({ controller: null });
        // The server settles any refund, so read the true balance and history afterwards.
        void refreshRuns().catch(() => undefined);
        void api.me().then((user) => setCredits(user.credits)).catch(() => undefined);
      }
    },
    stop: () => {
      get().controller?.abort();
      updateView({ status: "stopped", message: "Research stopped. Your credit was returned." });
      set({ controller: null });
    },
    deleteRun: async (id) => {
      await api.deleteRun(id);
      set((state) => ({
        runs: state.runs.filter((run) => run.id !== id),
        view: state.view?.runId === id ? null : state.view,
      }));
    },
    deleteAllRuns: async () => {
      await api.deleteAllRuns();
      const runs = await api.runs();
      // Research still in progress is kept on the server, so it stays on screen too.
      set((state) => {
        const busy = state.view?.status === "streaming" || state.view?.report?.status === "generating";
        return { runs, view: busy ? state.view : null };
      });
    },
    generateReport: async (pages) => {
      const { view } = get();
      if (!view?.runId || !view.report) return;
      const runId = view.runId;
      const isCurrent = () => get().view?.runId === runId;
      updateView({ report: { ...view.report, status: "generating" }, reportError: null, reportPages: pages });
      try {
        const report = await api.generateReport(runId, pages);
        if (isCurrent()) updateView({ report });
      } catch (err) {
        if (!isCurrent()) return;
        const message = err instanceof ApiError ? err.message : "Could not reach the server. Please try again.";
        updateView({ report: { ...view.report, status: view.report.generations ? "ready" : "failed" }, reportError: message });
      }
    },
  };
});
