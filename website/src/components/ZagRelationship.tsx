export default function ZagRelationship() {
  return (
    <section id="how-it-works" className="border-t border-border py-20 md:py-28">
      <div className="mx-auto max-w-5xl px-6">
        <h2 className="text-center text-3xl font-bold text-text-primary md:text-4xl">
          Built on <span className="text-zag">zag</span>, purpose-built for law
        </h2>
        <p className="mx-auto mt-4 max-w-2xl text-center text-text-secondary">
          zig is a domain-specific layer on top of{" "}
          <a href="https://github.com/niclaslindstedt/zag" target="_blank" rel="noopener noreferrer" className="text-zag hover:underline font-medium">zag</a>'s
          agent orchestration. zag handles multi-provider AI coordination.
          zig applies it to Swedish legal data collection.
        </p>

        {/* Architecture diagram */}
        <div className="mx-auto mt-14 max-w-lg">
          <div className="space-y-0">
            {/* zig layer */}
            <div className="rounded-t-xl border border-accent/40 bg-accent/5 p-6 text-center">
              <div className="text-xs font-medium uppercase tracking-wider text-accent mb-2">Domain Layer</div>
              <div className="text-xl font-bold text-text-primary mb-1">{"\u2696\uFE0F"} zig</div>
              <p className="text-sm text-text-secondary">
                Swedish legal data collection &mdash; 8 sources, 21 doc types, Pydantic models,
                incremental state, PDF extraction
              </p>
            </div>

            {/* zag layer */}
            <div className="border-x border-zag/30 bg-zag/5 p-6 text-center">
              <div className="text-xs font-medium uppercase tracking-wider text-zag mb-2">Agent Layer</div>
              <div className="text-xl font-bold text-text-primary mb-1">{"\u26A1"} zag</div>
              <p className="text-sm text-text-secondary">
                Multi-agent orchestration &mdash; spawn, wait, pipe, collect.
                Provider-agnostic sessions, JSON output, isolation modes.
              </p>
            </div>

            {/* Provider layer */}
            <div className="rounded-b-xl border border-border bg-surface-alt p-6 text-center">
              <div className="text-xs font-medium uppercase tracking-wider text-text-dim mb-2">Provider Layer</div>
              <div className="flex items-center justify-center gap-4 text-sm text-text-secondary">
                <span className="text-[#d4a27f]">Claude</span>
                <span className="text-text-dim">&middot;</span>
                <span className="text-[#4ade80]">Codex</span>
                <span className="text-text-dim">&middot;</span>
                <span className="text-[#60a5fa]">Gemini</span>
                <span className="text-text-dim">&middot;</span>
                <span className="text-[#c084fc]">Copilot</span>
                <span className="text-text-dim">&middot;</span>
                <span className="text-[#f472b6]">Ollama</span>
              </div>
            </div>
          </div>
        </div>

        {/* How it works bullets */}
        <div className="mt-14 grid gap-8 md:grid-cols-3">
          <div className="text-center">
            <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-accent/10 text-xl text-accent">1</div>
            <h3 className="mb-2 text-lg font-semibold text-text-primary">Collect</h3>
            <p className="text-sm text-text-secondary">
              zig dispatches async collectors to each source. Rate-limited, incremental,
              with automatic retry and state tracking.
            </p>
          </div>
          <div className="text-center">
            <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-zag/10 text-xl text-zag">2</div>
            <h3 className="mb-2 text-lg font-semibold text-text-primary">Parse</h3>
            <p className="text-sm text-text-secondary">
              zag agents analyze raw documents, extract text from PDFs, parse HTML/XML,
              and normalize into the unified Document schema.
            </p>
          </div>
          <div className="text-center">
            <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-accent/10 text-xl text-accent">3</div>
            <h3 className="mb-2 text-lg font-semibold text-text-primary">Store</h3>
            <p className="text-sm text-text-secondary">
              Documents are written as dual-format files (JSON + Markdown) into a
              git-friendly directory structure. Ready for version control.
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}
