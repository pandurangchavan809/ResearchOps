import { AlertCircle, Download, FileText, Loader2, RefreshCw } from "lucide-react";
import { useState } from "react";

import { api, ApiError } from "@/api";
import { Button } from "@/components/ui/Button";
import { useApp } from "@/hooks/useApp";
import type { ReportInfo, ResearchView } from "@/types";

/** PDF creation stays explicit: a click here, or a question that asks for a PDF. */
export function ReportActions({ view, runId, report }: { view: ResearchView; runId: string; report: ReportInfo }) {
  const generateReport = useApp((s) => s.generateReport);
  const config = useApp((s) => s.config);
  const maxPages = config?.max_report_pages ?? 20;
  const [choice, setChoice] = useState<number | null>(null);
  const [downloadError, setDownloadError] = useState("");
  const pages = choice ?? view.reportPages ?? config?.default_report_pages ?? 5;
  const generating = report.status === "generating";

  const download = async () => {
    setDownloadError("");
    try {
      await api.downloadReport(runId, report.title);
    } catch (err) {
      setDownloadError(err instanceof ApiError ? err.message : "The download failed. Please try again.");
    }
  };

  const ready = report.generations > 0;
  const left = report.generations_limit - report.generations;
  const error = view.reportError || downloadError;
  const shortOfTarget = ready && report.pages !== null && report.requested_pages !== null && report.pages !== report.requested_pages;

  const picker = (
    <label className="flex items-center gap-1.5 text-xs text-zinc-500">
      Pages
      <select
        value={pages}
        disabled={generating}
        onChange={(e) => setChoice(Number(e.target.value))}
        className="h-8 rounded-lg border border-zinc-200 bg-white px-1.5 text-[13px] text-zinc-800 disabled:opacity-50 dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-100"
      >
        {Array.from({ length: maxPages }, (_, i) => i + 1).map((n) => (
          <option key={n} value={n}>{n}</option>
        ))}
      </select>
    </label>
  );

  return (
    <div className="rounded-xl border border-zinc-200/80 p-3 dark:border-zinc-800">
      {ready && report.title && (
        <p className="mb-2.5 flex items-start gap-2 text-sm font-medium">
          <FileText className="mt-0.5 h-4 w-4 shrink-0 text-brand-500" />
          <span className="min-w-0 break-words">
            {report.title}
            {report.pages !== null && (
              <span className="ml-1.5 font-normal text-zinc-500">· {report.pages} {report.pages === 1 ? "page" : "pages"}</span>
            )}
          </span>
        </p>
      )}
      <div className="flex flex-wrap items-center gap-2">
        {ready ? (
          <>
            <Button variant="primary" size="sm" onClick={() => void download()} disabled={generating}>
              <Download className="h-3.5 w-3.5" /> Download PDF
            </Button>
            {picker}
            <Button size="sm" onClick={() => void generateReport(pages)} disabled={generating || left <= 0}>
              {generating ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
              {generating ? "Regenerating…" : "Regenerate"}
            </Button>
            <span className="text-xs text-zinc-500">{left > 0 ? `${left} regeneration${left === 1 ? "" : "s"} left` : "Report limit reached"}</span>
          </>
        ) : (
          <>
            {picker}
            <Button variant="primary" size="sm" onClick={() => void generateReport(pages)} disabled={generating}>
              {generating ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <FileText className="h-3.5 w-3.5" />}
              {generating ? `Writing a ${pages}-page report…` : "Generate report"}
            </Button>
            {!generating && <span className="text-xs text-zinc-500">Uses no credits</span>}
          </>
        )}
      </div>
      {shortOfTarget && (
        <p className="mt-2.5 text-xs leading-5 text-amber-700 dark:text-amber-400">
          You asked for {report.requested_pages} pages. The sources supported {report.pages} without padding or repeating content.
        </p>
      )}
      {error && (
        <p role="alert" className="mt-2.5 flex items-start gap-2 text-sm text-red-600 dark:text-red-400">
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" /> {error}
        </p>
      )}
    </div>
  );
}
