import { useParams, useNavigate } from "react-router-dom";
import { useState, useEffect } from "react";
import { MAN_PAGES } from "../data/sourceData";
import { renderMarkdown } from "./markdown";
import { usePageMeta } from "../hooks/usePageMeta";

const PAGE_ORDER = ["juris", "collect", "collect-type", "collect-all", "status", "stats", "man"];

const pages = MAN_PAGES.map((p) => ({ slug: p.command }));

export default function ManualPage() {
  const { command: urlCommand } = useParams();
  const navigate = useNavigate();

  const sorted = PAGE_ORDER.map((cmd) => MAN_PAGES.find((p) => p.command === cmd)).filter(
    (p): p is NonNullable<typeof p> => p != null,
  );

  const [active, setActive] = useState(urlCommand ?? sorted[0]?.command ?? "juris");
  const page = sorted.find((p) => p.command === active) ?? sorted[0];

  const cmdLabel = page.command === "juris" ? "juris" : `juris ${page.command}`;
  usePageMeta(
    `${cmdLabel} — juris manual`,
    `Reference documentation for the \`${cmdLabel}\` command in juris, the Swedish legal data CLI.`,
  );

  // Sync URL param to active state
  useEffect(() => {
    if (urlCommand && sorted.some((p) => p.command === urlCommand)) {
      setActive(urlCommand);
    }
  }, [urlCommand, sorted]);

  function handleNavigate(cmd: string) {
    setActive(cmd);
    navigate(`/manual/${cmd}`, { replace: true });
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  return (
    <div className="pt-24 pb-20 px-6">
      <div className="mx-auto max-w-6xl">
        <div className="mb-10">
          <h1 className="text-3xl md:text-4xl font-bold mb-2">Manual</h1>
          <p className="text-text-secondary">
            Complete reference documentation for every juris command.
          </p>
        </div>

        <div className="flex flex-col lg:flex-row gap-6">
          {/* Sidebar */}
          <nav className="lg:w-48 shrink-0">
            <div className="lg:sticky lg:top-24 flex lg:flex-col gap-2 overflow-x-auto pb-2 lg:pb-0">
              {sorted.map((p) => (
                <button
                  key={p.command}
                  onClick={() => handleNavigate(p.command)}
                  className={`text-left text-sm font-mono px-3 py-2 rounded-lg whitespace-nowrap transition-all ${
                    active === p.command
                      ? "bg-accent/15 text-accent border border-accent/30"
                      : "text-text-secondary hover:text-text-primary hover:bg-surface-200"
                  }`}
                >
                  {p.command === "juris" ? "juris" : `juris ${p.command}`}
                </button>
              ))}
            </div>
          </nav>

          {/* Content */}
          <div className="flex-1 min-w-0 rounded-xl border border-border bg-surface-100/50 p-6 md:p-8">
            <h2 className="text-2xl font-bold font-mono text-accent mb-2">{page.title}</h2>
            {renderMarkdown(page.content, handleNavigate, pages)}
          </div>
        </div>
      </div>
    </div>
  );
}
