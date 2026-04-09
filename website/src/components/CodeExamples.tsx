import { useState } from "react";

const tabs = [
  {
    label: "Basic Collection",
    code: `# Collect government bills from the current session
$ zig collect prop

# Collect with date range
$ zig collect sou --since 2025-01-01 --until 2025-03-31

# Collect specific document types from a single source
$ zig collect-type riksdagen mot --limit 100

# Collect everything (all sources, all types)
$ zig collect-all`,
  },
  {
    label: "Search & Inspect",
    code: `# Search across all collected documents
$ zig search "personuppgiftsbehandling"

# Search specific document types
$ zig search "dataskydd" --doc-type prop,sou

# Check collection status
$ zig status

# View collection statistics
$ zig stats

# View recent collection logs
$ zig logs`,
  },
  {
    label: "Reports & Updates",
    code: `# Generate a coverage report
$ zig report

# Compare with previous report
$ zig report --diff

# Update remote document indexes
$ zig update

# Update specific source
$ zig update --source riksdagen`,
  },
  {
    label: "Output Format",
    code: `# Documents stored as dual format:
$ ls data/prop/2024-25/
prop-2024_25-208.json    # Machine-readable
prop-2024_25-208.md      # Human-readable (YAML frontmatter)

# JSON contains full structured data
$ cat data/prop/2024-25/prop-2024_25-208.json
{
  "doc_id": "prop-2024/25:208",
  "doc_type": "prop",
  "title": "Ny budgetlag",
  "date": "2025-01-15",
  "source": "riksdagen",
  ...
}`,
  },
];

export default function CodeExamples() {
  const [active, setActive] = useState(0);

  return (
    <section className="border-t border-border bg-surface-alt py-20 md:py-28">
      <div className="mx-auto max-w-4xl px-6">
        <h2 className="text-center text-3xl font-bold text-text-primary md:text-4xl">
          See it in action
        </h2>
        <p className="mx-auto mt-4 max-w-2xl text-center text-text-secondary">
          From simple one-liners to full collection runs — zig keeps the interface clean and consistent.
        </p>

        <div className="mt-12 overflow-hidden rounded-xl border border-border bg-surface shadow-2xl">
          {/* Tab bar */}
          <div className="flex overflow-x-auto border-b border-border">
            {tabs.map((t, i) => (
              <button
                key={t.label}
                onClick={() => setActive(i)}
                className={`shrink-0 whitespace-nowrap px-5 py-3 text-sm font-medium transition-colors ${
                  i === active
                    ? "border-b-2 border-accent text-accent bg-surface-alt"
                    : "text-text-dim hover:text-text-secondary"
                }`}
              >
                {t.label}
              </button>
            ))}
          </div>
          {/* Code */}
          <pre className="overflow-x-auto p-6 text-sm leading-relaxed text-text-secondary">
            <code>{tabs[active].code}</code>
          </pre>
        </div>
      </div>
    </section>
  );
}
