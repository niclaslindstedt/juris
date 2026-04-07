import { SOURCES } from "../data/sourceData";

const METHOD_COLORS: Record<string, string> = {
  "JSON API": "bg-blue-500/15 text-blue-400 border-blue-500/30",
  "REST API": "bg-emerald-500/15 text-emerald-400 border-emerald-500/30",
  "Web Scraping": "bg-orange-500/15 text-orange-400 border-orange-500/30",
  SPARQL: "bg-purple-500/15 text-purple-400 border-purple-500/30",
};

export default function Sources() {
  return (
    <section id="sources" className="py-20 px-6 bg-surface-100/50">
      <div className="mx-auto max-w-6xl">
        <h2 className="text-3xl md:text-4xl font-bold text-center mb-4">Data Sources</h2>
        <p className="text-text-secondary text-center mb-12 max-w-2xl mx-auto">
          juris collects from {SOURCES.length} official Swedish and European legal data sources.
        </p>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-5">
          {SOURCES.map((source) => (
            <div
              key={source.value}
              className="p-5 rounded-xl border border-border hover:border-border-visible bg-surface hover:bg-surface-200 transition-all"
            >
              <div className="flex items-start justify-between mb-3">
                <h3 className="font-semibold font-mono text-accent">{source.value}</h3>
                <span
                  className={`text-xs px-2 py-0.5 rounded-full border ${METHOD_COLORS[source.method] ?? "bg-surface-200 text-text-dim border-border"}`}
                >
                  {source.method}
                </span>
              </div>
              <p className="text-xs text-text-dim mb-1">{source.url}</p>
              <p className="text-sm text-text-secondary mb-3">{source.description}</p>
              <div className="flex flex-wrap gap-1.5">
                {source.supportedDocTypes.map((dt) => (
                  <span
                    key={dt}
                    className={`text-xs font-mono px-1.5 py-0.5 rounded ${
                      source.preferredFor.includes(dt)
                        ? "bg-accent/15 text-accent border border-accent/30"
                        : "bg-surface-200 text-text-dim"
                    }`}
                  >
                    {dt}
                  </span>
                ))}
              </div>
            </div>
          ))}
        </div>

        <p className="text-xs text-text-dim text-center mt-6">
          <span className="inline-block px-1.5 py-0.5 rounded bg-accent/15 text-accent border border-accent/30 font-mono mr-1">highlighted</span>
          = preferred provider for that document type
        </p>
      </div>
    </section>
  );
}
