import { AlertTriangle, ChevronDown, CircleCheck, CircleDashed, CircleHelp, ExternalLink, GitCompare } from "lucide-react";
import type { ComponentType } from "react";
import { useState } from "react";

import type { Claim, ClaimStatus, Source } from "@/types";
import { cn } from "@/utils";

const STATUS: Record<ClaimStatus, { label: string; icon: ComponentType<{ className?: string }>; className: string }> = {
  supported: { label: "Supported", icon: CircleCheck, className: "text-emerald-600 dark:text-emerald-400" },
  partially_supported: { label: "Partially supported", icon: CircleDashed, className: "text-amber-600 dark:text-amber-400" },
  conflicting: { label: "Conflicting", icon: GitCompare, className: "text-orange-600 dark:text-orange-400" },
  unsupported: { label: "Unsupported", icon: CircleHelp, className: "text-red-600 dark:text-red-400" },
};

const LABEL = "text-[11px] font-medium tracking-wide text-zinc-400 uppercase";

export function Limitations({ items }: { items: string[] }) {
  if (!items.length) return null;
  return (
    <div className="rounded-xl border border-amber-200 bg-amber-50/60 px-4 py-3 dark:border-amber-500/25 dark:bg-amber-500/5">
      <p className="flex items-center gap-2 text-sm font-medium text-amber-800 dark:text-amber-300">
        <AlertTriangle className="h-4 w-4 shrink-0" /> Limitations
      </p>
      <ul className="mt-1.5 list-disc space-y-1 pl-6 text-sm leading-6 text-zinc-700 dark:text-zinc-300">
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </div>
  );
}

export function Claims({ claims, onCite }: { claims: Claim[]; onCite: (id: number) => void }) {
  const [open, setOpen] = useState(false);
  if (!claims.length) return null;
  const supported = claims.filter((c) => c.status === "supported").length;
  return (
    <div className="rounded-xl border border-zinc-200/80 dark:border-zinc-800">
      <button
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-center gap-2 rounded-xl px-3.5 py-2.5 text-left text-[13px] font-medium text-zinc-700 dark:text-zinc-300"
      >
        <CircleCheck className="h-4 w-4 shrink-0 text-emerald-500" />
        Claim verification
        <span className="font-normal text-zinc-500">{supported} of {claims.length} supported</span>
        <ChevronDown className={cn("ml-auto h-4 w-4 text-zinc-400 transition-transform", open && "rotate-180")} />
      </button>
      {open && (
        <ul className="divide-y divide-zinc-200/80 border-t border-zinc-200/80 dark:divide-zinc-800 dark:border-zinc-800">
          {claims.map((claim) => {
            const { label, icon: Icon, className } = STATUS[claim.status];
            return (
              <li key={claim.text} className="px-3.5 py-3 text-sm">
                <p className={cn("flex items-center gap-1.5 text-xs font-medium", className)}>
                  <Icon className="h-3.5 w-3.5" /> {label}
                </p>
                <p className="mt-1 leading-6">{claim.text}</p>
                <p className="mt-0.5 text-xs leading-5 text-zinc-500">
                  {claim.rationale}
                  {claim.citations.map((id) => (
                    <button
                      key={id}
                      onClick={() => onCite(id)}
                      aria-label={`Show source ${id}`}
                      className="ml-1 rounded bg-brand-50 px-1 font-mono text-[11px] font-medium text-brand-600 dark:bg-brand-500/15 dark:text-brand-400"
                    >
                      {id}
                    </button>
                  ))}
                </p>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

export function Sources({ sources, openId, setOpenId }: { sources: Source[]; openId: number | null; setOpenId: (id: number | null) => void }) {
  if (!sources.length) return null;
  return (
    <section aria-label="Sources">
      <p className={cn(LABEL, "mb-2")}>Sources</p>
      <ul className="space-y-1.5">
        {sources.map((source) => {
          const open = openId === source.id;
          return (
            <li key={source.id} id={`source-${source.id}`} className="scroll-mt-4 rounded-xl border border-zinc-200/80 dark:border-zinc-800">
              <button
                onClick={() => setOpenId(open ? null : source.id)}
                aria-expanded={open}
                className="flex w-full items-center gap-2.5 rounded-xl px-3 py-2 text-left"
              >
                <span className="flex h-5 min-w-5 shrink-0 items-center justify-center rounded-md bg-brand-50 px-1 font-mono text-[11px] font-medium text-brand-600 dark:bg-brand-500/15 dark:text-brand-400">
                  {source.id}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[13px] font-medium">{source.title}</span>
                  <span className="block truncate text-xs text-zinc-500">
                    {source.domain}
                    {source.published_date ? ` · ${source.published_date}` : ""}
                  </span>
                </span>
                <ChevronDown className={cn("h-4 w-4 shrink-0 text-zinc-400 transition-transform", open && "rotate-180")} />
              </button>
              {open && (
                <div className="animate-fade-in border-t border-zinc-200/80 px-3 py-2.5 dark:border-zinc-800">
                  {source.excerpts.length > 0 && (
                    <>
                      <p className={cn(LABEL, "mb-1.5")}>Supporting excerpts</p>
                      <div className="space-y-2">
                        {source.excerpts.map((excerpt) => (
                          <blockquote key={excerpt} className="border-l-2 border-brand-500 pl-3 text-[13px] leading-6 text-zinc-600 dark:text-zinc-400">
                            {excerpt}
                          </blockquote>
                        ))}
                      </div>
                    </>
                  )}
                  <a
                    href={source.url}
                    target="_blank"
                    rel="noreferrer noopener"
                    className="mt-2.5 inline-flex max-w-full items-center gap-1.5 text-xs text-brand-600 hover:underline dark:text-brand-400"
                  >
                    <ExternalLink className="h-3 w-3 shrink-0" />
                    <span className="truncate">{source.url}</span>
                  </a>
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
