import { AlertTriangle, ArrowRight, BarChart3, Database, FileText, Layers, Quote, Scale, ShieldCheck } from "lucide-react";

import { Logo } from "@/components/ui/Logo";
import { useApp } from "@/hooks/useApp";

const SUGGESTIONS = [
  { icon: Scale, text: "Compare vLLM and SGLang for production inference" },
  { icon: Database, text: "How do PostgreSQL and ClickHouse differ for analytics?" },
  { icon: BarChart3, text: "Evaluate current approaches to RAG evaluation" },
  { icon: Layers, text: "What should I consider when choosing a vector database?" },
];

export function EmptyState({ onPick }: { onPick: (text: string) => void }) {
  const config = useApp((s) => s.config);
  const missing = [
    config && config.models.length === 0 && "an AI model key (OpenAI, Gemini, or Nebius)",
    config && !config.search_configured && "TAVILY_API_KEY",
  ].filter(Boolean);

  return (
    <div className="mx-auto flex w-full max-w-3xl flex-1 flex-col items-center justify-center px-4 py-10 sm:px-6">
      <div className="relative mb-6">
        <div className="absolute inset-0 -z-10 scale-150 rounded-full bg-gradient-to-br from-brand-500/25 to-accent-500/25 blur-2xl" />
        <Logo className="h-12 w-12" />
      </div>
      <h1 className="text-center text-2xl font-semibold tracking-tight sm:text-3xl">
        Make your next technical decision <span className="text-gradient">clearer</span>
      </h1>
      <p className="mt-3 max-w-lg text-center text-sm leading-6 text-zinc-500 dark:text-zinc-400">
        Ask a question. ResearchOps gathers evidence from the web, checks claims against sources, and shows you what its answer rests on.
      </p>

      {missing.length > 0 && (
        <div role="status" className="mt-6 flex w-full items-start gap-3 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-200">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <p>Research is unavailable until {missing.join(" and ")} is added to the server's .env file.</p>
        </div>
      )}

      <div className="mt-8 grid w-full gap-2.5 sm:grid-cols-2">
        {SUGGESTIONS.map(({ icon: Icon, text }) => (
          <button
            key={text}
            onClick={() => onPick(text)}
            className="group flex items-start gap-3 rounded-2xl border border-zinc-200 bg-white p-4 text-left text-sm transition hover:border-zinc-300 hover:shadow-sm dark:border-zinc-800 dark:bg-zinc-900/50 dark:hover:border-zinc-700"
          >
            <Icon className="mt-0.5 h-4 w-4 shrink-0 text-brand-500" />
            <span className="flex-1 text-zinc-700 dark:text-zinc-300">{text}</span>
            <ArrowRight className="mt-0.5 h-4 w-4 shrink-0 text-zinc-300 transition group-hover:translate-x-0.5 group-hover:text-zinc-500" />
          </button>
        ))}
      </div>

      <div className="mt-10 flex flex-wrap items-center justify-center gap-x-5 gap-y-2 text-xs text-zinc-400">
        <span className="flex items-center gap-1.5"><Quote className="h-3.5 w-3.5" /> Citations you can inspect</span>
        <span className="flex items-center gap-1.5"><ShieldCheck className="h-3.5 w-3.5" /> Claims checked against sources</span>
        <span className="flex items-center gap-1.5"><FileText className="h-3.5 w-3.5" /> PDF reports on request</span>
      </div>
    </div>
  );
}
