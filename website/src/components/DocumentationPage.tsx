import { useParams, useNavigate } from "react-router-dom";
import { useState, useEffect } from "react";
import { DOC_PAGES } from "../data/sourceData";
import { renderMarkdown } from "./markdown";

const PAGE_ORDER = [
  "overview",
  "architecture",
  "collectors",
  "document-model",
  "storage-format",
  "data-sources",
  "parsing-rules",
];

const PAGE_LABELS: Record<string, string> = {
  overview: "Overview",
  architecture: "Architecture",
  collectors: "Collectors",
  "document-model": "Document Model",
  "storage-format": "Storage Format",
  "data-sources": "Data Sources",
  "parsing-rules": "Parsing Rules",
};

const pages = DOC_PAGES.map((p) => ({ slug: p.slug }));

export default function DocumentationPage() {
  const { slug: urlSlug } = useParams();
  const navigate = useNavigate();

  const sorted = PAGE_ORDER.map((slug) => DOC_PAGES.find((p) => p.slug === slug)).filter(
    (p): p is NonNullable<typeof p> => p != null,
  );

  const [active, setActive] = useState(urlSlug ?? sorted[0]?.slug ?? "overview");
  const page = sorted.find((p) => p.slug === active) ?? sorted[0];

  // Sync URL param to active state
  useEffect(() => {
    if (urlSlug && sorted.some((p) => p.slug === urlSlug)) {
      setActive(urlSlug);
    }
  }, [urlSlug, sorted]);

  function handleNavigate(slug: string) {
    setActive(slug);
    navigate(`/docs/${slug}`, { replace: true });
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  return (
    <div className="pt-24 pb-20 px-6">
      <div className="mx-auto max-w-6xl">
        <div className="mb-10">
          <h1 className="text-3xl md:text-4xl font-bold mb-2">Documentation</h1>
          <p className="text-text-secondary">
            Concepts, architecture, and guides for understanding how juris works.
          </p>
        </div>

        <div className="flex flex-col lg:flex-row gap-6">
          {/* Sidebar */}
          <nav className="lg:w-48 shrink-0">
            <div className="lg:sticky lg:top-24 flex lg:flex-col gap-2 overflow-x-auto pb-2 lg:pb-0">
              {sorted.map((p) => (
                <button
                  key={p.slug}
                  onClick={() => handleNavigate(p.slug)}
                  className={`text-left text-sm font-mono px-3 py-2 rounded-lg whitespace-nowrap transition-all ${
                    active === p.slug
                      ? "bg-accent/15 text-accent border border-accent/30"
                      : "text-text-secondary hover:text-text-primary hover:bg-surface-200"
                  }`}
                >
                  {PAGE_LABELS[p.slug] ?? p.title}
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
