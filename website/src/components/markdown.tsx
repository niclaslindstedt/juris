/**
 * Shared markdown renderer used by ManPages and Documentation components.
 *
 * Handles headings, code blocks, tables, lists, paragraphs, and inline
 * formatting (links, code, bold). Internal links are resolved against
 * a provided page list.
 */

import type React from "react";

export interface PageRef {
  slug: string;
}

export function renderMarkdown(
  md: string,
  onNavigate: (slug: string) => void,
  pages: PageRef[],
): React.ReactNode[] {
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
        <h2
          key={key++}
          className="text-xl font-bold text-text-primary mt-8 mb-4 pb-2 border-b border-border"
        >
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
                      {renderInline(cell.trim(), onNavigate, pages)}
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
                          {renderInline(cell.trim(), onNavigate, pages)}
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
              {renderInline(item, onNavigate, pages)}
            </li>
          ))}
        </ul>,
      );
      continue;
    }

    // Numbered list item
    if (/^\d+\.\s/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^\d+\.\s/.test(lines[i])) {
        items.push(lines[i].replace(/^\d+\.\s/, ""));
        i++;
      }
      elements.push(
        <ol key={key++} className="list-decimal list-inside space-y-2 my-4 text-text-secondary">
          {items.map((item, li) => (
            <li key={li} className="leading-relaxed">
              {renderInline(item, onNavigate, pages)}
            </li>
          ))}
        </ol>,
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
      !/^\d+\.\s/.test(lines[i]) &&
      !(lines[i].includes("|") && lines[i].trim().startsWith("|"))
    ) {
      paraLines.push(lines[i]);
      i++;
    }
    if (paraLines.length > 0) {
      elements.push(
        <p key={key++} className="text-text-secondary leading-relaxed my-3">
          {renderInline(paraLines.join(" "), onNavigate, pages)}
        </p>,
      );
    }
  }

  return elements;
}

export function renderInline(
  text: string,
  onNavigate: (slug: string) => void,
  pages: PageRef[],
): React.ReactNode {
  const parts: React.ReactNode[] = [];
  let remaining = text;
  let partKey = 0;

  while (remaining.length > 0) {
    // Markdown link: [text](url)
    const linkMatch = remaining.match(/\[([^\]]+)\]\(([^)]+)\)/);
    // Inline code: `code`
    const codeMatch = remaining.match(/`([^`]+)`/);
    // Bold: **text**
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
      const isInternal = pages.some((p) => p.slug === href);
      if (isInternal) {
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
