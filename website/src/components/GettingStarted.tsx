import { useState } from "react";

const STEPS = [
  {
    title: "Install",
    code: `pip install juris`,
  },
  {
    title: "Collect",
    code: `# Collect government bills from the current session
juris collect riksdagen --type prop --session 2024/25

# Or use the best provider automatically
juris collect-type sou --since 2024-01-01

# Collect everything
juris collect-all`,
  },
  {
    title: "Browse",
    code: `data/
├── prop/
│   └── 2024-25/
│       ├── prop-2024-25_208.json
│       └── prop-2024-25_208.md
├── sou/
│   └── 2024/
│       ├── sou-2024_12.json
│       └── sou-2024_12.md
└── ...`,
  },
];

export default function GettingStarted() {
  const [copied, setCopied] = useState<number | null>(null);

  function copyToClipboard(text: string, index: number) {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(index);
      setTimeout(() => setCopied(null), 2000);
    });
  }

  return (
    <section id="getting-started" className="py-20 px-6 bg-surface-100/50">
      <div className="mx-auto max-w-3xl">
        <h2 className="text-3xl md:text-4xl font-bold text-center mb-4">
          Getting Started
        </h2>
        <p className="text-text-secondary text-center mb-12">
          Three steps to start building your Swedish law database.
        </p>

        <div className="space-y-6">
          {STEPS.map((step, i) => (
            <div key={step.title}>
              <div className="flex items-center gap-3 mb-3">
                <span className="w-7 h-7 rounded-full bg-accent/15 text-accent text-sm font-bold flex items-center justify-center">
                  {i + 1}
                </span>
                <h3 className="font-semibold text-lg">{step.title}</h3>
              </div>
              <div className="relative group">
                <pre className="bg-surface rounded-xl border border-border p-4 overflow-x-auto font-mono text-sm text-text-secondary leading-relaxed">
                  <code>{step.code}</code>
                </pre>
                <button
                  onClick={() => copyToClipboard(step.code, i)}
                  className="absolute top-3 right-3 p-1.5 rounded-md bg-surface-200 border border-border text-text-dim hover:text-text-primary opacity-0 group-hover:opacity-100 transition-opacity"
                  aria-label="Copy to clipboard"
                >
                  {copied === i ? (
                    <svg className="w-4 h-4 text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                    </svg>
                  ) : (
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                    </svg>
                  )}
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
