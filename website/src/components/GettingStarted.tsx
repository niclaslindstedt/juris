const methods = [
  {
    title: "From PyPI",
    command: "pip install juris",
    note: "Requires Python 3.11+",
  },
  {
    title: "From source",
    command: "git clone https://github.com/niclaslindstedt/juris\ncd juris && pip install -e '.[dev]'",
    note: "Build from latest source",
  },
  {
    title: "With uv",
    command: "uv pip install juris",
    note: "Fast install with uv",
  },
];

export default function GettingStarted() {
  return (
    <section id="get-started" className="border-t border-border bg-surface-alt py-20 md:py-28">
      <div className="mx-auto max-w-5xl px-6">
        <h2 className="text-center text-3xl font-bold text-text-primary md:text-4xl">
          Get started in seconds
        </h2>
        <p className="mx-auto mt-4 max-w-xl text-center text-text-secondary">
          Install zig, then start collecting Swedish legal documents.
        </p>

        {/* Install methods */}
        <div className="mt-12 grid gap-6 md:grid-cols-3">
          {methods.map((m) => (
            <div key={m.title} className="rounded-xl border border-border bg-surface p-5">
              <h3 className="mb-1 text-sm font-semibold text-text-primary">{m.title}</h3>
              <p className="mb-3 text-xs text-text-dim">{m.note}</p>
              <pre className="overflow-x-auto rounded-lg bg-surface-alt p-3 text-xs leading-relaxed text-accent">
                <code>{m.command}</code>
              </pre>
            </div>
          ))}
        </div>

        {/* Prerequisites */}
        <div className="mt-12">
          <h3 className="mb-4 text-center text-lg font-semibold text-text-primary">
            Prerequisites
          </h3>
          <div className="mx-auto max-w-2xl space-y-2">
            {[
              { name: "Python 3.11+", cmd: "python3 --version" },
              { name: "zag CLI", cmd: "cargo install zag-cli" },
              { name: "pymupdf (optional)", cmd: "pip install pymupdf" },
            ].map((p) => (
              <div key={p.name} className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between rounded-lg border border-border bg-surface px-4 py-2.5">
                <span className="text-sm font-medium text-text-secondary">{p.name}</span>
                <code className="text-xs text-text-dim">{p.cmd}</code>
              </div>
            ))}
          </div>
        </div>

        {/* Quick verify */}
        <div className="mx-auto mt-12 max-w-lg rounded-xl border border-border bg-surface p-5">
          <p className="mb-3 text-center text-sm text-text-secondary">Verify your installation:</p>
          <pre className="overflow-x-auto text-sm text-text-secondary">
            <code>
              <span className="text-accent">$</span> zig collect prop --limit 1{"\n"}
              <span className="text-[#4ade80]">{"\u2713"}</span> Collected 1 document to data/prop/
            </code>
          </pre>
        </div>
      </div>
    </section>
  );
}
