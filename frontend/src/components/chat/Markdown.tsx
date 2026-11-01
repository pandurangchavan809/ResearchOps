import { memo } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { linkCitations } from "@/utils";

interface MarkdownProps {
  text: string;
  onCite: (id: number) => void;
}

export const Markdown = memo(function Markdown({ text, onCite }: MarkdownProps) {
  return (
    <div className="markdown">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          table: ({ node: _node, ...props }) => (
            <div className="table-wrap">
              <table {...props} />
            </div>
          ),
          a: ({ node: _node, href, children, ...props }) => {
            const citation = /^#source-(\d+)$/.exec(href ?? "");
            if (citation) {
              const id = Number(citation[1]);
              return (
                <button
                  onClick={() => onCite(id)}
                  aria-label={`Show source ${id}`}
                  className="mx-0.5 inline-flex h-[18px] min-w-[18px] -translate-y-px items-center justify-center rounded-md bg-brand-50 px-1 align-middle font-mono text-[11px] font-medium text-brand-600 hover:bg-brand-100 dark:bg-brand-500/15 dark:text-brand-400 dark:hover:bg-brand-500/25"
                >
                  {id}
                </button>
              );
            }
            return (
              <a {...props} href={href} target="_blank" rel="noreferrer noopener">
                {children}
              </a>
            );
          },
        }}
      >
        {linkCitations(text)}
      </ReactMarkdown>
    </div>
  );
});
