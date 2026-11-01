import { AlertCircle, Cpu, Info, Menu, SquarePen } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Logo } from "@/components/ui/Logo";
import { useApp } from "@/hooks/useApp";
import type { ResearchView } from "@/types";

import { Composer } from "./Composer";
import { EmptyState } from "./EmptyState";
import { Claims, Limitations, Sources } from "./Evidence";
import { Markdown } from "./Markdown";
import { ModelPicker } from "./ModelPicker";
import { ReportActions } from "./ReportActions";
import { ResearchTrace } from "./ResearchTrace";

function Answer({ view }: { view: ResearchView }) {
  const [openSource, setOpenSource] = useState<number | null>(null);
  const cite = useCallback((id: number) => {
    setOpenSource(id);
    requestAnimationFrame(() => document.getElementById(`source-${id}`)?.scrollIntoView({ behavior: "smooth", block: "nearest" }));
  }, []);
  const { result } = view;

  return (
    <div className="flex animate-fade-in gap-3 sm:gap-4">
      <Logo className="mt-0.5 h-7 w-7 shrink-0" />
      <div className="min-w-0 flex-1 space-y-4">
        <ResearchTrace steps={view.steps} status={view.status} />

        {result && (
          <>
            <h2 className="text-lg font-semibold tracking-tight">{result.title}</h2>
            <Markdown text={result.answer_markdown} onCite={cite} />
            <Limitations items={result.limitations} />
            <Claims claims={result.claims} onCite={cite} />
            <Sources sources={result.sources} openId={openSource} setOpenId={setOpenSource} />
            {view.runId && view.report && <ReportActions key={view.runId} view={view} runId={view.runId} report={view.report} />}
            {result.models_used.length > 0 && (
              <div className="flex flex-wrap items-center gap-1.5 text-[11px] text-zinc-400">
                <Cpu className="h-3 w-3" />
                {result.models_used.map((model) => (
                  <span key={model} className="rounded-md bg-zinc-100 px-1.5 py-0.5 font-mono dark:bg-zinc-800/80">{model}</span>
                ))}
              </div>
            )}
          </>
        )}

        {view.message && view.status === "error" && (
          <div role="alert" className="flex items-start gap-3 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800 dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-300">
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
            <p className="min-w-0 break-words">{view.message}</p>
          </div>
        )}
        {view.message && (view.status === "rejected" || view.status === "stopped") && (
          <div role="status" className="flex items-start gap-3 rounded-xl border border-zinc-200 bg-zinc-50 px-4 py-3 text-sm text-zinc-700 dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-300">
            <Info className="mt-0.5 h-4 w-4 shrink-0" />
            <p className="min-w-0 break-words">{view.message}</p>
          </div>
        )}
      </div>
    </div>
  );
}

export function ChatView() {
  const view = useApp((s) => s.view);
  const setSidebarOpen = useApp((s) => s.setSidebarOpen);
  const newResearch = useApp((s) => s.newResearch);
  const [draft, setDraft] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);

  // Start at the top whenever a different question is shown.
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: 0 });
  }, [view?.question]);

  return (
    <main className="flex min-w-0 flex-1 flex-col">
      <header className="flex h-14 shrink-0 items-center gap-1 border-b border-zinc-200/70 px-3 sm:px-4 dark:border-zinc-800/70">
        <Button variant="ghost" size="icon" className="lg:hidden" onClick={() => setSidebarOpen(true)} aria-label="Open sidebar">
          <Menu className="h-4 w-4" />
        </Button>
        <ModelPicker />
        {view && (
          <Button variant="ghost" size="icon" className="ml-auto" onClick={newResearch} aria-label="New research" title="New research">
            <SquarePen className="h-4 w-4" />
          </Button>
        )}
      </header>

      <div ref={scrollRef} className="flex min-h-0 flex-1 flex-col overflow-y-auto">
        {view ? (
          <div className="mx-auto w-full max-w-3xl space-y-8 px-4 py-8 sm:px-6">
            <div className="flex animate-fade-in justify-end">
              <div className="max-w-[85%] rounded-2xl rounded-br-md bg-zinc-100 px-4 py-2.5 text-[15px] leading-7 break-words whitespace-pre-wrap dark:bg-zinc-800/80">
                {view.question}
              </div>
            </div>
            <Answer key={view.question} view={view} />
          </div>
        ) : (
          <EmptyState onPick={setDraft} />
        )}
      </div>

      <Composer draft={draft} setDraft={setDraft} />
    </main>
  );
}
