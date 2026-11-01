import { AlertTriangle, Loader2 } from "lucide-react";
import { type ReactNode, useEffect, useState } from "react";

import { ApiError } from "@/api";
import { AuthPage } from "@/components/auth/AuthPage";
import { ChatView } from "@/components/chat/ChatView";
import { Sidebar } from "@/components/sidebar/Sidebar";
import { Button } from "@/components/ui/Button";
import { useApp } from "@/hooks/useApp";
import { useAuth } from "@/hooks/useAuth";

function Centered({ children }: { children: ReactNode }) {
  return <div className="flex h-full items-center justify-center p-6">{children}</div>;
}

export default function App() {
  const status = useAuth((s) => s.status);
  const restore = useAuth((s) => s.restore);
  const userId = useAuth((s) => s.user?.id);

  useEffect(() => {
    void restore();
  }, [restore]);

  if (status === "loading") {
    return (
      <Centered>
        <Loader2 className="h-6 w-6 animate-spin text-zinc-400" />
      </Centered>
    );
  }
  if (status === "anonymous") return <AuthPage />;
  // Keyed by user, so logging in as someone else starts from a clean state.
  return <Workspace key={userId} />;
}

function Workspace() {
  const boot = useApp((s) => s.boot);
  const newResearch = useApp((s) => s.newResearch);
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");
  const [error, setError] = useState("");

  const load = async () => {
    setState("loading");
    newResearch();
    try {
      await boot();
      setState("ready");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not reach the server.");
      setState("error");
    }
  };

  useEffect(() => {
    void load();
    // Runs once per user session.
  }, []);

  if (state === "loading") {
    return (
      <Centered>
        <Loader2 className="h-6 w-6 animate-spin text-zinc-400" />
      </Centered>
    );
  }
  if (state === "error") {
    return (
      <Centered>
        <div className="max-w-sm text-center">
          <AlertTriangle className="mx-auto h-8 w-8 text-amber-500" />
          <p className="mt-3 font-medium">ResearchOps is unavailable</p>
          <p className="mt-1 text-sm text-zinc-500">{error}</p>
          <Button className="mt-5" onClick={() => void load()}>
            Try again
          </Button>
        </div>
      </Centered>
    );
  }
  return (
    <div className="flex h-full overflow-hidden">
      <Sidebar />
      <ChatView />
    </div>
  );
}
