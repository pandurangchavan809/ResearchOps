import { LogOut, Moon, SquarePen, Sun, Trash2, X } from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/Button";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { Logo } from "@/components/ui/Logo";
import { useApp } from "@/hooks/useApp";
import { useAuth } from "@/hooks/useAuth";
import type { RunSummary } from "@/types";
import { cn, displayName, initials } from "@/utils";

type PendingDelete = { kind: "one"; run: RunSummary } | { kind: "all" };

function useTheme() {
  const [dark, setDark] = useState(() => document.documentElement.classList.contains("dark"));
  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
    try {
      localStorage.setItem("ro-theme", dark ? "dark" : "light");
    } catch {
      /* Storage unavailable: the theme just lasts for this session. */
    }
  }, [dark]);
  return { dark, toggle: () => setDark((d) => !d) };
}

function UserCard() {
  const user = useAuth((s) => s.user);
  const logout = useAuth((s) => s.logout);
  if (!user) return null;
  const { limit, remaining } = user.credits;
  return (
    <div className="mx-3 mt-3 rounded-xl border border-zinc-200 bg-white p-3 dark:border-zinc-800 dark:bg-zinc-900">
      <div className="flex items-center gap-2.5">
        <span
          className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-brand-500 to-accent-500 text-xs font-semibold text-white"
          aria-hidden
        >
          {initials(user.email)}
        </span>
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium" title={user.email}>{displayName(user.email)}</p>
          <p className="truncate text-xs text-zinc-500">{user.email}</p>
        </div>
        <Button variant="ghost" size="icon" onClick={() => void logout()} aria-label="Log out" title="Log out">
          <LogOut className="h-4 w-4" />
        </Button>
      </div>
      <div className="mt-3">
        <div className="flex items-baseline justify-between text-xs">
          <span className="text-zinc-500">Research credits</span>
          <span className="font-medium tabular-nums">{remaining} of {limit} left</span>
        </div>
        <div
          className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-zinc-100 dark:bg-zinc-800"
          role="progressbar"
          aria-label="Research credits left"
          aria-valuenow={remaining}
          aria-valuemin={0}
          aria-valuemax={limit}
        >
          <div
            className="h-full rounded-full bg-brand-500 transition-[width]"
            style={{ width: `${limit ? (remaining / limit) * 100 : 0}%` }}
          />
        </div>
      </div>
    </div>
  );
}

export function Sidebar() {
  const open = useApp((s) => s.sidebarOpen);
  const setOpen = useApp((s) => s.setSidebarOpen);
  const runs = useApp((s) => s.runs);
  const activeId = useApp((s) => s.view?.runId);
  const newResearch = useApp((s) => s.newResearch);
  const openRun = useApp((s) => s.openRun);
  const deleteRun = useApp((s) => s.deleteRun);
  const deleteAllRuns = useApp((s) => s.deleteAllRuns);
  const { dark, toggle } = useTheme();
  const [pendingDelete, setPendingDelete] = useState<PendingDelete | null>(null);

  return (
    <>
      {open && <div className="fixed inset-0 z-30 bg-zinc-950/40 lg:hidden" onClick={() => setOpen(false)} />}
      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-40 flex w-[280px] flex-col border-r border-zinc-200 bg-zinc-50 transition-transform duration-200 lg:static lg:translate-x-0 dark:border-zinc-800/80 dark:bg-zinc-900",
          open ? "translate-x-0" : "-translate-x-full",
        )}
      >
        <div className="flex items-center gap-2.5 px-4 pt-4 pb-3">
          <Logo />
          <span className="text-[15px] font-semibold tracking-tight">ResearchOps</span>
          <Button variant="ghost" size="icon" className="ml-auto lg:hidden" onClick={() => setOpen(false)} aria-label="Close sidebar">
            <X className="h-4 w-4" />
          </Button>
        </div>

        <div className="px-3">
          <Button className="w-full justify-start" onClick={newResearch}>
            <SquarePen className="h-4 w-4" /> New research
          </Button>
        </div>

        <UserCard />

        <div className="mt-4 min-h-0 flex-1 overflow-y-auto px-3 pb-3">
          <div className="flex h-7 items-center justify-between pr-0.5 pb-1 pl-2">
            <p className="text-[11px] font-medium tracking-wide text-zinc-400 uppercase">History</p>
            {runs.length > 0 && (
              <button
                onClick={() => setPendingDelete({ kind: "all" })}
                className="rounded-md px-1.5 py-0.5 text-[11px] font-medium text-zinc-500 transition-colors hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-500/10 dark:hover:text-red-400"
              >
                Delete all
              </button>
            )}
          </div>
          {runs.length === 0 ? (
            <p className="px-2 text-xs leading-5 text-zinc-500">Your finished research will appear here.</p>
          ) : (
            <ul className="space-y-0.5">
              {runs.map((run) => (
                <li
                  key={run.id}
                  className={cn(
                    "group flex items-center rounded-lg transition-colors hover:bg-zinc-200/60 dark:hover:bg-zinc-800",
                    run.id === activeId && "bg-zinc-200/70 dark:bg-zinc-800",
                  )}
                >
                  <button
                    onClick={() => void openRun(run.id)}
                    title={run.title}
                    aria-current={run.id === activeId}
                    className={cn(
                      "min-w-0 flex-1 truncate rounded-lg py-1.5 pl-2 text-left text-[13px]",
                      run.id === activeId && "font-medium",
                      run.status !== "completed" && "text-zinc-500",
                    )}
                  >
                    {run.title}
                  </button>
                  {/* Always visible on touch screens, which have no hover. */}
                  <button
                    onClick={() => setPendingDelete({ kind: "one", run })}
                    aria-label={`Delete ${run.title}`}
                    title="Delete"
                    className="mx-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-md text-zinc-400 transition-colors group-hover:opacity-100 hover:bg-red-50 hover:text-red-600 focus-visible:opacity-100 lg:opacity-0 dark:hover:bg-red-500/10 dark:hover:text-red-400"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="flex items-center justify-between border-t border-zinc-200 px-4 py-3 text-xs text-zinc-500 dark:border-zinc-800">
          <span>Evidence first</span>
          <Button variant="ghost" size="icon" onClick={toggle} aria-label={dark ? "Use light theme" : "Use dark theme"}>
            {dark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
          </Button>
        </div>
      </aside>

      {pendingDelete && (
        <ConfirmDialog
          title={pendingDelete.kind === "all" ? "Delete all research?" : "Delete this research?"}
          description={
            pendingDelete.kind === "all"
              ? `This permanently deletes ${runs.length} saved ${runs.length === 1 ? "item" : "items"} and their PDF reports. Used credits are not returned.`
              : `"${pendingDelete.run.title}" and its PDF report will be permanently deleted. The credit it used is not returned.`
          }
          confirmLabel={pendingDelete.kind === "all" ? "Delete all" : "Delete"}
          onCancel={() => setPendingDelete(null)}
          onConfirm={async () => {
            await (pendingDelete.kind === "all" ? deleteAllRuns() : deleteRun(pendingDelete.run.id));
            setPendingDelete(null);
          }}
        />
      )}
    </>
  );
}
