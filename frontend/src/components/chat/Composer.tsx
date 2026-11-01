import { ArrowUp, Square } from "lucide-react";
import { useEffect, useRef } from "react";

import { useApp } from "@/hooks/useApp";
import { useAuth } from "@/hooks/useAuth";
import { cn } from "@/utils";

export function Composer({ draft, setDraft }: { draft: string; setDraft: (text: string) => void }) {
  const ask = useApp((s) => s.ask);
  const stop = useApp((s) => s.stop);
  const busy = useApp((s) => s.view?.status === "streaming");
  const config = useApp((s) => s.config);
  const credits = useAuth((s) => s.user?.credits.remaining ?? 0);
  const ref = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 220)}px`;
  }, [draft]);

  const configured = !!config && config.search_configured && config.models.length > 0;
  const maxChars = config?.max_question_chars ?? 2000;
  const tooLong = draft.length > maxChars;
  const blocked = !configured || credits <= 0;
  const canSend = !blocked && !busy && draft.trim().length > 0 && !tooLong;

  const submit = () => {
    if (!canSend) return;
    void ask(draft.trim());
    setDraft("");
  };

  const placeholder = !configured
    ? "Research is unavailable until the server is configured"
    : credits <= 0
      ? "You have used all your research credits"
      : "Ask a technical research question…";

  return (
    <div className="mx-auto w-full max-w-3xl px-4 pb-4 sm:px-6">
      <div
        className={cn(
          "rounded-2xl border bg-white shadow-[0_2px_16px_-6px_rgb(0_0_0/0.12)] transition-colors focus-within:border-zinc-400 dark:bg-zinc-900 dark:focus-within:border-zinc-600",
          tooLong ? "border-red-400" : "border-zinc-200 dark:border-zinc-800",
        )}
      >
        <textarea
          ref={ref}
          rows={1}
          value={draft}
          disabled={blocked}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
              e.preventDefault();
              submit();
            }
          }}
          placeholder={placeholder}
          className="block max-h-[220px] w-full resize-none rounded-t-2xl bg-transparent px-4 pt-3.5 pb-1 text-[15px] leading-6 outline-none placeholder:text-zinc-400 disabled:cursor-not-allowed"
          aria-label="Research question"
        />
        <div className="flex items-center gap-2 px-3 pb-2.5">
          <span className="text-[11px] text-zinc-400">Each question is researched on its own and uses a credit</span>
          {draft.length > maxChars * 0.8 && (
            <span className={cn("text-[11px] tabular-nums", tooLong ? "text-red-500" : "text-zinc-400")}>
              {draft.length}/{maxChars}
            </span>
          )}
          {busy ? (
            <button
              onClick={stop}
              className="ml-auto flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-zinc-900 text-white hover:bg-zinc-700 dark:bg-white dark:text-zinc-900"
              aria-label="Stop research"
            >
              <Square className="h-3 w-3 fill-current" />
            </button>
          ) : (
            <button
              onClick={submit}
              disabled={!canSend}
              className="ml-auto flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-zinc-900 text-white transition hover:bg-zinc-700 disabled:bg-zinc-200 disabled:text-zinc-400 dark:bg-white dark:text-zinc-900 dark:hover:bg-zinc-200 dark:disabled:bg-zinc-800 dark:disabled:text-zinc-600"
              aria-label="Start research"
            >
              <ArrowUp className="h-4 w-4" strokeWidth={2.5} />
            </button>
          )}
        </div>
      </div>
      <p className="mt-2 text-center text-[11px] text-zinc-400">
        ResearchOps can make mistakes. Check answers against the sources for important decisions.
      </p>
    </div>
  );
}
