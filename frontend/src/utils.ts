export { clsx as cn } from "clsx";

export function formatDuration(ms: number): string {
  return ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)} s`;
}

export function initials(email: string): string {
  const parts = email.split("@")[0].split(/[._-]+/).filter(Boolean);
  return ((parts[0]?.[0] ?? "?") + (parts[1]?.[0] ?? "")).toUpperCase();
}

export function displayName(email: string): string {
  return email.split("@")[0];
}

/** Turns [3] into a link the Markdown renderer shows as a citation chip, leaving code untouched. */
export function linkCitations(markdown: string): string {
  return markdown
    .split(/(```[\s\S]*?```|`[^`\n]*`)/g)
    .map((part, i) => (i % 2 ? part : part.replace(/\[(\d{1,3})\](?!\()/g, "[$1](#source-$1)")))
    .join("");
}
