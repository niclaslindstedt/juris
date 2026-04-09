import { SOURCES, DOC_TYPES } from "../data/sourceData";

const features = [
  {
    title: `${SOURCES.length} Official Sources`,
    description:
      `Collects from ${SOURCES.map((s) => s.description.split(" ")[0]).slice(0, 4).join(", ")}, and more. Each source has a dedicated async collector with rate limiting and incremental state.`,
    icon: "\uD83C\uDDF8\uD83C\uDDEA",
  },
  {
    title: `${DOC_TYPES.length} Document Types`,
    description:
      "Government bills, court decisions, EU regulations, ombudsman rulings, and more \u2014 all normalized into a unified schema with Pydantic validation.",
    icon: "\uD83D\uDCDC",
  },
  {
    title: "AI-Powered via zag",
    description:
      "Built on zag\u2019s agent orchestration layer. AI agents parse complex legal documents, extract structured data, and handle edge cases intelligently.",
    icon: "\u26A1",
  },
  {
    title: "Git-Friendly Output",
    description:
      "Every document is stored as JSON (machine-readable) + Markdown with YAML frontmatter (human-readable). Clean diffs, easy version control.",
    icon: "\uD83D\uDCC1",
  },
  {
    title: "Incremental Collection",
    description:
      "State tracking per source and document type. Only fetches new and updated documents. Resume interrupted collections seamlessly.",
    icon: "\uD83D\uDD04",
  },
  {
    title: "PDF Text Extraction",
    description:
      "Automatic text extraction from PDF attachments via pymupdf. Handles scanned documents and complex legal formatting.",
    icon: "\uD83D\uDCC4",
  },
  {
    title: "Async & Rate-Limited",
    description:
      "Fully async I/O with httpx. Built-in rate limiting respects each source\u2019s API constraints. Parallel collection across sources.",
    icon: "\uD83D\uDE80",
  },
  {
    title: "Coverage Reports",
    description:
      "Track collection completeness over time. Diff reports show what\u2019s new, what\u2019s changed, and what\u2019s missing across all sources.",
    icon: "\uD83D\uDCCA",
  },
];

export default function Features() {
  return (
    <section id="features" className="border-t border-border py-20 md:py-28">
      <div className="mx-auto max-w-6xl px-6">
        <h2 className="text-center text-3xl font-bold text-text-primary md:text-4xl">
          Everything you need for Swedish legal data
        </h2>
        <p className="mx-auto mt-4 max-w-2xl text-center text-text-secondary">
          A unified pipeline that collects, parses, normalizes, and stores legal documents from
          official Swedish and EU sources.
        </p>

        <div className="mt-14 grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
          {features.map((f) => (
            <div
              key={f.title}
              className="group rounded-xl border border-border bg-surface-alt p-6 transition-all hover:border-accent/40 hover:bg-surface-hover"
            >
              <div className="mb-4 text-2xl">{f.icon}</div>
              <h3 className="mb-2 text-lg font-semibold text-text-primary">{f.title}</h3>
              <p className="text-sm leading-relaxed text-text-secondary">{f.description}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
