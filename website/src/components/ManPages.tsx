import { useState } from "react";
import { MAN_PAGES } from "../data/sourceData";

const PAGE_ORDER = ["juris", "collect", "collect-type", "collect-all", "status", "stats", "man"];

function renderMarkdown(md: string, onNavigate: (cmd: string) => void): React.ReactNode[] {
  const lines = md.split("\n");
  const elements: React.ReactNode[] = [];
  let i = 0;
  let key = 0;

  while (i < lines.length) {
    const line = lines[i];

    // Skip the top-level h1 title (rendered separately)
    if (line.startsWith("# ") && key === 0) {
      i++;
      continue;
    }

    // h2
    if (line.startsWith("## ")) {
      elements.push(
        <h2 key={key++} className="text-xl font-bold text-text-primary mt-8 mb-4 pb-2 border-b border-border">
          {line.slice(3)}
        </h2>,
      );
      i++;
      continue;
    }

    // h3
    if (line.startsWith("### ")) {
      elements.push(
        <h3 key={key++} className="text-lg font-semibold text-text-primary mt-6 mb-3">
          {line.slice(4)}
        </h3>,
      );
      i++;
      continue;
    }

    // Fenced code block
    if (line.startsWith("```")) {
      const codeLines: string[] = [];
      i++;
      while (i < lines.length && !lines[i].startsWith("```")) {
        codeLines.push(lines[i]);
        i++;
      }
      i++; // skip closing ```
      elements.push(
        <pre
          key={key++}
          className="bg-surface rounded-xl border border-border p-4 overflow-x-auto font-mono text-sm text-text-secondary leading-relaxed my-4"
        >
          <code>{codeLines.join("\n")}</code>
        </pre>,
      );
      continue;
    }

    // Table
    if (line.includes("|") && line.trim().startsWith("|")) {
      const tableLines: string[] = [];
      while (i < lines.length && lines[i].includes("|") && lines[i].trim().startsWith("|")) {
        tableLines.push(lines[i]);
        i++;
      }
      if (tableLines.length >= 2) {
        const headerCells = tableLines[0].split("|").filter((c) => c.trim());
        const bodyRows = tableLines.slice(2); // skip header + separator
        elements.push(
          <div key={key++} className="overflow-x-auto my-4">
            <table className="w-full text-sm border-collapse">
              <thead>
                <tr>
                  {headerCells.map((cell, ci) => (
                    <th
                      key={ci}
                      className="text-left px-3 py-2 border-b border-border text-text-primary font-semibold"
                    >
                      {renderInline(cell.trim(), onNavigate)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {bodyRows.map((row, ri) => {
                  const cells = row.split("|").filter((c) => c.trim());
                  return (
                    <tr key={ri} className="border-b border-border/50">
                      {cells.map((cell, ci) => (
                        <td key={ci} className="px-3 py-2 text-text-secondary">
                          {renderInline(cell.trim(), onNavigate)}
                        </td>
                      ))}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>,
        );
      }
      continue;
    }

    // List item
    if (line.startsWith("- ")) {
      const items: string[] = [];
      while (i < lines.length && lines[i].startsWith("- ")) {
        items.push(lines[i].slice(2));
        i++;
      }
      elements.push(
        <ul key={key++} className="list-disc list-inside space-y-2 my-4 text-text-secondary">
          {items.map((item, li) => (
            <li key={li} className="leading-relaxed">
              {renderInline(item, onNavigate)}
            </li>
          ))}
        </ul>,
      );
      continue;
    }

    // Empty line
    if (line.trim() === "") {
      i++;
      continue;
    }

    // Paragraph — collect consecutive non-empty, non-special lines
    const paraLines: string[] = [];
    while (
      i < lines.length &&
      lines[i].trim() !== "" &&
      !lines[i].startsWith("#") &&
      !lines[i].startsWith("```") &&
      !lines[i].startsWith("- ") &&
      !(lines[i].includes("|") && lines[i].trim().startsWith("|"))
    ) {
      paraLines.push(lines[i]);
      i++;
    }
    if (paraLines.length > 0) {
      elements.push(
        <p key={key++} className="text-text-secondary leading-relaxed my-3">
          {renderInline(paraLines.join(" "), onNavigate)}
        </p>,
      );
    }
  }

  return elements;
}

function renderInline(text: string, onNavigate: (cmd: string) => void): React.ReactNode {
  // Split on inline code, bold, and links
  const parts: React.ReactNode[] = [];
  let remaining = text;
  let partKey = 0;

  while (remaining.length > 0) {
    // Markdown link: [text](url)
    const linkMatch = remaining.match(/\[([^\]]+)\]\(([^)]+)\)/);
    // Inline code: `code`
    const codeMatch = remaining.match(/`([^`]+)`/);
    // Bold: **text** or *text*
    const boldMatch = remaining.match(/\*\*([^*]+)\*\*/);

    // Find earliest match
    const matches = [
      linkMatch ? { type: "link", match: linkMatch } : null,
      codeMatch ? { type: "code", match: codeMatch } : null,
      boldMatch ? { type: "bold", match: boldMatch } : null,
    ]
      .filter((m): m is NonNullable<typeof m> => m !== null)
      .sort((a, b) => (a.match.index ?? 0) - (b.match.index ?? 0));

    if (matches.length === 0) {
      parts.push(remaining);
      break;
    }

    const first = matches[0];
    const idx = first.match.index ?? 0;

    if (idx > 0) {
      parts.push(remaining.slice(0, idx));
    }

    if (first.type === "code") {
      parts.push(
        <code
          key={partKey++}
          className="bg-surface-200 text-accent px-1.5 py-0.5 rounded text-[0.85em] font-mono"
        >
          {first.match[1]}
        </code>,
      );
    } else if (first.type === "link") {
      const href = first.match[2];
      const linkText = first.match[1];
      // Internal man page links are bare command names
      const manPage = MAN_PAGES.find((p) => p.command === href);
      if (manPage) {
        parts.push(
          <button
            key={partKey++}
            onClick={() => onNavigate(href)}
            className="text-accent hover:underline cursor-pointer"
          >
            {linkText}
          </button>,
        );
      } else {
        parts.push(
          <a
            key={partKey++}
            href={href}
            className="text-accent hover:underline"
            target="_blank"
            rel="noopener noreferrer"
          >
            {linkText}
          </a>,
        );
      }
    } else if (first.type === "bold") {
      parts.push(
        <strong key={partKey++} className="font-semibold text-text-primary">
          {first.match[1]}
        </strong>,
      );
    }

    remaining = remaining.slice(idx + first.match[0].length);
  }

  return parts.length === 1 ? parts[0] : <>{parts}</>;
}

export default function ManPages() {
  const sorted = PAGE_ORDER.map((cmd) => MAN_PAGES.find((p) => p.command === cmd)).filter(
    (p): p is NonNullable<typeof p> => p != null,
  );

  const [active, setActive] = useState(sorted[0]?.command ?? "juris");
  const page = sorted.find((p) => p.command === active) ?? sorted[0];

  return (
    <section id="manual" className="py-20 px-6">
      <div className="mx-auto max-w-6xl">
        <h2 className="text-3xl md:text-4xl font-bold text-center mb-4">Manual</h2>
        <p className="text-text-secondary text-center mb-12 max-w-2xl mx-auto">
          Complete reference documentation for every juris command.
        </p>

        <div className="flex flex-col lg:flex-row gap-6">
          {/* Sidebar */}
          <nav className="lg:w-48 shrink-0">
            <div className="lg:sticky lg:top-24 flex lg:flex-col gap-2 overflow-x-auto pb-2 lg:pb-0">
              {sorted.map((p) => (
                <button
                  key={p.command}
                  onClick={() => setActive(p.command)}
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
            <h1 className="text-2xl font-bold font-mono text-accent mb-2">{page.title}</h1>
            {renderMarkdown(page.content, setActive)}
          </div>
        </div>
      </div>
    </section>
  );
}
