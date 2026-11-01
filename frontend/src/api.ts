import type { AppConfig, ReportInfo, ResearchEvent, RunDetail, RunSummary, TokenResponse, User } from "@/types";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

// The access token lives only in memory. The long-lived refresh token is an HttpOnly cookie.
let accessToken: string | null = null;
let refreshing: Promise<TokenResponse> | null = null;
let onSessionLost: () => void = () => {};

export function setSessionLostHandler(handler: () => void) {
  onSessionLost = handler;
}

async function toApiError(response: Response): Promise<ApiError> {
  let message = "Something went wrong. Please try again.";
  try {
    const body = await response.json();
    if (typeof body.detail === "string") message = body.detail;
  } catch {
    /* Non-JSON error body: keep the generic message. */
  }
  return new ApiError(response.status, message);
}

/** Only one refresh runs at a time, since each call rotates the token. */
export function refreshSession(): Promise<TokenResponse> {
  refreshing ??= (async () => {
    try {
      const response = await fetch("/api/auth/refresh", { method: "POST", credentials: "same-origin" });
      if (!response.ok) throw await toApiError(response);
      const session = (await response.json()) as TokenResponse;
      accessToken = session.access_token;
      return session;
    } finally {
      refreshing = null;
    }
  })();
  return refreshing;
}

/** Sends a request, renewing an expired access token once before giving up. */
async function send(path: string, init: RequestInit = {}): Promise<Response> {
  const attempt = () =>
    fetch(path, {
      ...init,
      credentials: "same-origin",
      headers: {
        ...(init.body ? { "Content-Type": "application/json" } : {}),
        ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
        ...init.headers,
      },
    });
  let response = await attempt();
  if (response.status === 401) {
    try {
      await refreshSession();
    } catch {
      accessToken = null;
      onSessionLost();
      throw await toApiError(response);
    }
    response = await attempt();
  }
  if (!response.ok) throw await toApiError(response);
  return response;
}

async function json<T>(path: string, init?: RequestInit): Promise<T> {
  return (await send(path, init)).json() as Promise<T>;
}

async function authenticate(path: string, body: object): Promise<TokenResponse> {
  const response = await fetch(path, {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw await toApiError(response);
  const session = (await response.json()) as TokenResponse;
  accessToken = session.access_token;
  return session;
}

export const api = {
  login: (email: string, password: string) => authenticate("/api/auth/login", { email, password }),
  register: (email: string, newPassword: string, confirmPassword: string) =>
    authenticate("/api/auth/register", { email, new_password: newPassword, confirm_password: confirmPassword }),
  logout: async () => {
    await fetch("/api/auth/logout", { method: "POST", credentials: "same-origin" });
    accessToken = null;
  },
  me: () => json<User>("/api/auth/me"),
  config: () => json<AppConfig>("/api/config"),
  runs: () => json<RunSummary[]>("/api/research"),
  run: (id: string) => json<RunDetail>(`/api/research/${id}`),
  deleteRun: async (id: string) => {
    await send(`/api/research/${id}`, { method: "DELETE" });
  },
  deleteAllRuns: () => json<{ deleted: number }>("/api/research", { method: "DELETE" }),
  generateReport: (id: string, pages: number) =>
    json<ReportInfo>(`/api/research/${id}/report`, { method: "POST", body: JSON.stringify({ pages }) }),

  downloadReport: async (id: string, title: string | null) => {
    const response = await send(`/api/research/${id}/report/download`);
    const url = URL.createObjectURL(await response.blob());
    const name = /filename="?([^";]+)"?/.exec(response.headers.get("content-disposition") ?? "")?.[1];
    const link = document.createElement("a");
    link.href = url;
    link.download = name ?? `${title ?? "report"}.pdf`;
    link.click();
    URL.revokeObjectURL(url);
  },

  /** Streams real workflow events until the run ends or the signal aborts. */
  research: async (question: string, model: string, onEvent: (event: ResearchEvent) => void, signal: AbortSignal) => {
    const response = await send("/api/research", {
      method: "POST",
      body: JSON.stringify({ question, model }),
      signal,
    });
    const reader = response.body!.pipeThrough(new TextDecoderStream()).getReader();
    let buffer = "";
    for (;;) {
      const { done, value } = await reader.read();
      if (done) return;
      buffer += value.replace(/\r\n/g, "\n");
      let boundary: number;
      while ((boundary = buffer.indexOf("\n\n")) >= 0) {
        const frame = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        const event = /^event: (.+)$/m.exec(frame)?.[1];
        const data = /^data: (.+)$/m.exec(frame)?.[1];
        if (event && data) onEvent({ event, data: JSON.parse(data) } as ResearchEvent);
      }
    }
  },
};
