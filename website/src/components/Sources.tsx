import { SOURCES } from "../data/sourceData";

export default function Sources() {
  return (
    <section id="sources" className="border-t border-border bg-surface-alt py-20 md:py-28">
      <div className="mx-auto max-w-6xl px-6">
        <h2 className="text-center text-3xl font-bold text-text-primary md:text-4xl">
          {SOURCES.length} sources, one unified format
        </h2>
        <p className="mx-auto mt-4 max-w-2xl text-center text-text-secondary">
          Each source has a dedicated async collector with auto-discovery, rate limiting, and
          incremental state tracking. Collectors are registered automatically via{" "}
          <code className="rounded bg-surface px-1.5 py-0.5 text-xs text-accent">BaseCollector.__init_subclass__</code>.
        </p>

        <div className="mt-14 grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
          {SOURCES.map((s) => (
            <div key={s.value} className="rounded-xl border border-border bg-surface p-6">
              <div className="mb-1 text-xs font-medium uppercase tracking-wider text-text-dim">
                {s.method}
              </div>
              <h3 className="mb-2 text-lg font-bold text-text-primary">{s.name}</h3>
              <p className="mb-3 text-sm text-text-secondary">{s.description}</p>
              <div className="mb-3 text-xs text-text-dim">{s.url}</div>

              {/* Supported doc types */}
              <div className="flex flex-wrap gap-1.5">
                {s.supportedDocTypes.map((dt) => (
                  <span
                    key={dt}
                    className={`rounded-full px-2 py-0.5 text-xs ${
                      s.preferredFor.includes(dt)
                        ? "bg-accent/15 text-accent font-medium"
                        : "bg-surface-alt text-text-dim"
                    }`}
                  >
                    {dt}
                  </span>
                ))}
              </div>
            </div>
          ))}
        </div>

        <p className="text-xs text-text-dim text-center mt-8">
          <span className="inline-block px-1.5 py-0.5 rounded bg-accent/15 text-accent font-mono mr-1">highlighted</span>
          = preferred provider for that document type
        </p>
      </div>
    </section>
  );
}
