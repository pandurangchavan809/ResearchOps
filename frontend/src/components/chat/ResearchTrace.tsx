import { Check, ChevronDown, Loader2, Sparkles } from "lucide-react";
import { useState } from "react";

import type { Step, ViewStatus } from "@/types";
import { cn, formatDuration } from "@/utils";

/** Shows only progress events the backend actually sent. */
export function ResearchTrace({ steps, status }: { steps: Step[]; status: ViewStatus }) {
  const [open, setOpen] = useState<boolean | null>(null);
  const streaming = status === "streaming";

  if (!steps.length) {
    return streaming ? (
      <div className="flex items-center gap-2 text-sm text-zinc-500">
        <Loader2 className="h-4 w-4 animate-spin text-brand-500" />
        <span className="shimmer-text">Starting research…</span>
      </div>
    ) : null;
  }

  const running = streaming ? steps.find((s) => s.status === "running") : undefined;
  const finished = steps.filter((s) => s.status === "done");
  const total = finished.reduce((sum, s) => sum + (s.duration_ms ?? 0), 0);
  const expanded = open ?? streaming;

  return (
    <div className="rounded-xl border border-zinc-200/80 bg-zinc-50/60 dark:border-zinc-800 dark:bg-zinc-900/40">
      <button
        onClick={() => setOpen(!expanded)}
        className="flex w-full items-center gap-2.5 rounded-xl px-3.5 py-2.5 text-left text-[13px]"
        aria-expanded={expanded}
      >
        {running ? (
          <>
            <Loader2 className="h-4 w-4 shrink-0 animate-spin text-brand-500" />
            <span className="shimmer-text font-medium text-zinc-700 dark:text-zinc-300">{running.label}…</span>
          </>
        ) : (
          <>
            <Sparkles className="h-4 w-4 shrink-0 text-brand-500" />
            <span className="font-medium text-zinc-700 dark:text-zinc-300">
              {status === "done" ? "Researched in" : "Stopped after"} {formatDuration(total)}
            </span>
            <span className="text-zinc-400">·</span>
            <span className="text-zinc-500">{finished.length} {finished.length === 1 ? "step" : "steps"}</span>
          </>
        )}
        <ChevronDown className={cn("ml-auto h-4 w-4 shrink-0 text-zinc-400 transition-transform", expanded && "rotate-180")} />
      </button>

      {expanded && (
        <ol className="space-y-2 border-t border-zinc-200/80 px-3.5 py-3 dark:border-zinc-800">
          {steps.map((step, i) => (
            <li key={`${step.step}-${i}`} className="flex animate-fade-in gap-2.5 text-[13px]">
              {step.status === "running" && streaming ? (
                <Loader2 className="mt-0.5 h-3.5 w-3.5 shrink-0 animate-spin text-brand-500" />
              ) : (
                <Check className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-500" />
              )}
              <div className="min-w-0 flex-1">
                <div className="flex items-baseline gap-2">
                  <span className="font-medium text-zinc-800 dark:text-zinc-200">{step.label}</span>
                  {step.duration_ms !== undefined && (
                    <span className="ml-auto shrink-0 font-mono text-[11px] text-zinc-400">{formatDuration(step.duration_ms)}</span>
                  )}
                </div>
                {step.detail && <p className="mt-0.5 text-xs leading-5 break-words text-zinc-500">{step.detail}</p>}
              </div>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
