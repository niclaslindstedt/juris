const FEATURES = [
  {
    icon: "🏛",
    title: "8 Data Sources",
    description:
      "Parliament, government, courts, ombudsmen, agencies, and EU institutions. JSON APIs, REST endpoints, SPARQL, and web scraping.",
  },
  {
    icon: "📜",
    title: "21 Document Types",
    description:
      "Bills, motions, inquiries, court decisions, regulations, EU directives, and more. Every type of Swedish legal document.",
  },
  {
    icon: "📄",
    title: "Dual Output Format",
    description:
      "JSON for machines, Markdown with YAML frontmatter for humans. Browse documents directly on GitHub.",
  },
  {
    icon: "⏩",
    title: "Incremental Collection",
    description:
      "State tracking resumes where you left off. Skip already-collected documents automatically.",
  },
  {
    icon: "⚡",
    title: "Async I/O & Rate Limiting",
    description:
      "Built on httpx with configurable rate limits. Respects source servers with exponential backoff and retry.",
  },
  {
    icon: "📎",
    title: "PDF Text Extraction",
    description:
      "Automatically downloads PDF attachments and extracts full text via pymupdf. Falls back gracefully.",
  },
];

export default function Features() {
  return (
    <section id="features" className="py-20 px-6">
      <div className="mx-auto max-w-6xl">
        <h2 className="text-3xl md:text-4xl font-bold text-center mb-4">Features</h2>
        <p className="text-text-secondary text-center mb-12 max-w-2xl mx-auto">
          Everything you need to build a comprehensive, version-controlled database of Swedish law.
        </p>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {FEATURES.map((feature) => (
            <div
              key={feature.title}
              className="p-6 rounded-xl border border-border hover:border-border-visible bg-surface-100 hover:bg-surface-200 transition-all"
            >
              <div className="text-2xl mb-3">{feature.icon}</div>
              <h3 className="text-lg font-semibold mb-2">{feature.title}</h3>
              <p className="text-text-secondary text-sm leading-relaxed">
                {feature.description}
              </p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
