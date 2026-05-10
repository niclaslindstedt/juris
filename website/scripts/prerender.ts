/**
 * prerender.ts — Generates static HTML for each docs/manual route after vite build.
 *
 * Why: the SPA's `noscript` fallback only fires on the homepage. Without
 * prerendered HTML, crawlers and AI agents that don't run JavaScript see an
 * empty `<div id="root">` for /docs/* and /manual/* routes, and even Googlebot
 * indexes JS-rendered SPAs slower and less reliably than static pages.
 *
 * Each output file:
 *   - reuses the same JS bundle so users with JS still get the SPA
 *   - bakes a per-route <title>, meta description, canonical, OG tags
 *   - injects Article + BreadcrumbList JSON-LD
 *   - replaces the homepage <noscript> body with the rendered markdown so
 *     crawlers see real content
 *
 * Also emits:
 *   - llms.txt        — short LLM-friendly project summary with key links
 *   - llms-full.txt   — full markdown corpus (docs + man pages) for LLM ingestion
 */

import { readFileSync, writeFileSync, readdirSync, mkdirSync } from "fs";
import { resolve, join } from "path";

const ROOT = resolve(import.meta.dirname, "../..");
const DIST = resolve(import.meta.dirname, "../dist");
const DOCS_DIR = join(ROOT, "docs");
const MAN_DIR = join(ROOT, "man");
const PYPROJECT_PATH = join(ROOT, "pyproject.toml");
const SITE_URL = "https://juris.niclaslindstedt.se";

// --- Read source ---

function getVersion(): string {
  const content = readFileSync(PYPROJECT_PATH, "utf-8");
  return content.match(/^version\s*=\s*"([^"]+)"/m)?.[1] ?? "0.0.0";
}

interface Page {
  slug: string;
  title: string;
  content: string;
}

function readMarkdownDir(dir: string): Page[] {
  let files: string[];
  try {
    files = readdirSync(dir).filter((f) => f.endsWith(".md")).sort();
  } catch {
    return [];
  }
  return files.map((f) => {
    const slug = f.replace(/\.md$/, "");
    const content = readFileSync(join(dir, f), "utf-8");
    const title = content.match(/^#\s+(.+)/m)?.[1]?.trim() ?? slug;
    return { slug, title, content };
  });
}

const docPages = readMarkdownDir(DOCS_DIR);
const manPages = readMarkdownDir(MAN_DIR);
const VERSION = getVersion();

// --- Markdown → HTML (semantic, no styling — Tailwind hydrates over it) ---

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function renderInline(text: string): string {
  let out = escapeHtml(text);
  // Inline code first so its contents aren't re-processed
  out = out.replace(/`([^`]+)`/g, (_, c) => `<code>${c}</code>`);
  // Bold
  out = out.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  // Links — restore href value (we already escaped quotes; & in URLs is acceptable as &amp;)
  out = out.replace(/\[([^\]]+)\]\(([^)]+)\)/g, (_, label, href) => {
    const isExternal = /^https?:\/\//.test(href);
    const rel = isExternal ? ' rel="noopener noreferrer"' : "";
    const target = isExternal ? ' target="_blank"' : "";
    return `<a href="${href}"${target}${rel}>${label}</a>`;
  });
  return out;
}

function renderMarkdownToHtml(md: string, skipFirstH1 = true): string {
  const lines = md.split("\n");
  const out: string[] = [];
  let i = 0;
  let seenH1 = false;

  while (i < lines.length) {
    const line = lines[i];

    if (line.startsWith("# ")) {
      if (!seenH1 && skipFirstH1) {
        seenH1 = true;
        i++;
        continue;
      }
      out.push(`<h1>${renderInline(line.slice(2))}</h1>`);
      i++;
      continue;
    }
    if (line.startsWith("## ")) {
      out.push(`<h2>${renderInline(line.slice(3))}</h2>`);
      i++;
      continue;
    }
    if (line.startsWith("### ")) {
      out.push(`<h3>${renderInline(line.slice(4))}</h3>`);
      i++;
      continue;
    }
    if (line.startsWith("#### ")) {
      out.push(`<h4>${renderInline(line.slice(5))}</h4>`);
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
      i++;
      out.push(`<pre><code>${escapeHtml(codeLines.join("\n"))}</code></pre>`);
      continue;
    }

    // Table
    if (line.includes("|") && line.trim().startsWith("|")) {
      const tableLines: string[] = [];
      while (
        i < lines.length &&
        lines[i].includes("|") &&
        lines[i].trim().startsWith("|")
      ) {
        tableLines.push(lines[i]);
        i++;
      }
      if (tableLines.length >= 2) {
        const header = tableLines[0].split("|").filter((c) => c.trim());
        const body = tableLines.slice(2);
        let html = "<table><thead><tr>";
        for (const h of header) html += `<th>${renderInline(h.trim())}</th>`;
        html += "</tr></thead><tbody>";
        for (const row of body) {
          const cells = row.split("|").filter((c) => c.trim());
          html += "<tr>";
          for (const c of cells) html += `<td>${renderInline(c.trim())}</td>`;
          html += "</tr>";
        }
        html += "</tbody></table>";
        out.push(html);
      }
      continue;
    }

    // Bullet list
    if (line.startsWith("- ")) {
      const items: string[] = [];
      while (i < lines.length && lines[i].startsWith("- ")) {
        items.push(lines[i].slice(2));
        i++;
      }
      out.push(
        `<ul>${items.map((it) => `<li>${renderInline(it)}</li>`).join("")}</ul>`,
      );
      continue;
    }

    // Numbered list
    if (/^\d+\.\s/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^\d+\.\s/.test(lines[i])) {
        items.push(lines[i].replace(/^\d+\.\s/, ""));
        i++;
      }
      out.push(
        `<ol>${items.map((it) => `<li>${renderInline(it)}</li>`).join("")}</ol>`,
      );
      continue;
    }

    if (line.trim() === "") {
      i++;
      continue;
    }

    // Paragraph
    const para: string[] = [];
    while (
      i < lines.length &&
      lines[i].trim() !== "" &&
      !lines[i].startsWith("#") &&
      !lines[i].startsWith("```") &&
      !lines[i].startsWith("- ") &&
      !/^\d+\.\s/.test(lines[i]) &&
      !(lines[i].includes("|") && lines[i].trim().startsWith("|"))
    ) {
      para.push(lines[i]);
      i++;
    }
    if (para.length > 0) {
      out.push(`<p>${renderInline(para.join(" "))}</p>`);
    }
  }

  return out.join("\n");
}

function firstParagraph(md: string): string {
  const lines = md.split("\n");
  let i = 0;
  // Skip h1 + blank lines
  while (i < lines.length && (lines[i].startsWith("#") || lines[i].trim() === "")) i++;
  const para: string[] = [];
  while (i < lines.length && lines[i].trim() !== "" && !lines[i].startsWith("#")) {
    para.push(lines[i]);
    i++;
  }
  // Strip markdown-ish syntax for meta description
  return para
    .join(" ")
    .replace(/`([^`]+)`/g, "$1")
    .replace(/\*\*([^*]+)\*\*/g, "$1")
    .replace(/\[([^\]]+)\]\(([^)]+)\)/g, "$1")
    .replace(/\s+/g, " ")
    .trim();
}

// --- Per-route HTML rendering ---

const indexHtmlPath = join(DIST, "index.html");
const indexHtml = readFileSync(indexHtmlPath, "utf-8");

interface Route {
  url: string;        // e.g. /docs/architecture
  outFile: string;    // dist/docs/architecture/index.html
  title: string;      // <title> content
  description: string; // meta description
  bodyHtml: string;   // content for <noscript>
  jsonLd: object[];   // additional JSON-LD blocks
}

function buildRoute(opts: Route): string {
  const canonical = `${SITE_URL}${opts.url}`;
  let html = indexHtml;

  // Replace <title>
  html = html.replace(
    /<title>[^<]*<\/title>/,
    `<title>${escapeHtml(opts.title)}</title>`,
  );

  // Replace <meta name="description">
  html = html.replace(
    /<meta\s+name="description"[\s\S]*?\/>/,
    `<meta name="description" content="${escapeHtml(opts.description)}" />`,
  );

  // Replace canonical link
  html = html.replace(
    /<link rel="canonical"[^>]*\/>/,
    `<link rel="canonical" href="${canonical}" />`,
  );

  // Update OG/Twitter URL + title + description
  html = html.replace(
    /<meta property="og:url"[^>]*\/>/,
    `<meta property="og:url" content="${canonical}" />`,
  );
  html = html.replace(
    /<meta property="og:title"[^>]*\/>/,
    `<meta property="og:title" content="${escapeHtml(opts.title)}" />`,
  );
  html = html.replace(
    /<meta\s+property="og:description"[\s\S]*?\/>/,
    `<meta property="og:description" content="${escapeHtml(opts.description)}" />`,
  );
  html = html.replace(
    /<meta name="twitter:title"[^>]*\/>/,
    `<meta name="twitter:title" content="${escapeHtml(opts.title)}" />`,
  );
  html = html.replace(
    /<meta\s+name="twitter:description"[\s\S]*?\/>/,
    `<meta name="twitter:description" content="${escapeHtml(opts.description)}" />`,
  );

  // Inject route-specific JSON-LD before </head>
  const ldScripts = opts.jsonLd
    .map(
      (ld) =>
        `<script type="application/ld+json">${JSON.stringify(ld)}</script>`,
    )
    .join("\n    ");
  html = html.replace("</head>", `    ${ldScripts}\n  </head>`);

  // Replace <noscript>...</noscript> body with route content
  html = html.replace(
    /<noscript>[\s\S]*?<\/noscript>/,
    `<noscript>${opts.bodyHtml}</noscript>`,
  );

  return html;
}

function ensureDir(p: string): void {
  mkdirSync(p, { recursive: true });
}

function writePage(outFile: string, html: string): void {
  ensureDir(outFile.replace(/\/[^/]+$/, ""));
  writeFileSync(outFile, html, "utf-8");
}

// --- Render docs pages ---

for (const p of docPages) {
  const title = `${p.title} — juris docs`;
  const desc = firstParagraph(p.content) ||
    `${p.title}: documentation for juris, the Swedish and EU legal data CLI.`;
  const article = {
    "@context": "https://schema.org",
    "@type": "TechArticle",
    headline: p.title,
    description: desc,
    url: `${SITE_URL}/docs/${p.slug}`,
    inLanguage: "en",
    isPartOf: {
      "@type": "WebSite",
      name: "juris",
      url: SITE_URL,
    },
    author: { "@type": "Person", name: "Niclas Lindstedt" },
    keywords:
      "juris, swedish law, legal data, python cli, documentation, " + p.title,
  };
  const breadcrumb = {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: [
      { "@type": "ListItem", position: 1, name: "Home", item: SITE_URL + "/" },
      {
        "@type": "ListItem",
        position: 2,
        name: "Documentation",
        item: SITE_URL + "/docs",
      },
      {
        "@type": "ListItem",
        position: 3,
        name: p.title,
        item: `${SITE_URL}/docs/${p.slug}`,
      },
    ],
  };
  const bodyHtml =
    `<header><h1>${escapeHtml(p.title)}</h1>` +
    `<p><a href="/">juris</a> &rsaquo; <a href="/docs">Documentation</a> &rsaquo; ${escapeHtml(p.title)}</p></header>` +
    `<article>${renderMarkdownToHtml(p.content)}</article>` +
    `<footer><p>Source: <a href="https://github.com/niclaslindstedt/juris/blob/main/docs/${p.slug}.md">docs/${p.slug}.md</a> &middot; <a href="/">juris home</a> &middot; <a href="/manual">CLI manual</a></p></footer>`;
  const html = buildRoute({
    url: `/docs/${p.slug}`,
    outFile: join(DIST, "docs", p.slug, "index.html"),
    title,
    description: desc.slice(0, 300),
    bodyHtml,
    jsonLd: [article, breadcrumb],
  });
  writePage(join(DIST, "docs", p.slug, "index.html"), html);
}

// /docs index
{
  const title = "juris documentation — Swedish legal data CLI";
  const desc =
    "Concept and architecture documentation for juris: a Python CLI that collects and normalizes Swedish + EU legal documents (propositioner, SOU, SFS, NJA, EUR-Lex, ECHR…) into JSON + Markdown.";
  const items = docPages.map((p, i) => ({
    "@type": "ListItem",
    position: i + 1,
    name: p.title,
    url: `${SITE_URL}/docs/${p.slug}`,
  }));
  const itemList = {
    "@context": "https://schema.org",
    "@type": "ItemList",
    name: "juris documentation",
    itemListElement: items,
  };
  const bodyHtml =
    `<header><h1>juris — Documentation</h1>` +
    `<p>Concepts, architecture, and guides for the juris CLI.</p></header>` +
    `<nav><ul>` +
    docPages
      .map(
        (p) =>
          `<li><a href="/docs/${p.slug}">${escapeHtml(p.title)}</a> — ${escapeHtml(firstParagraph(p.content).slice(0, 160))}</li>`,
      )
      .join("") +
    `</ul></nav>` +
    `<p>See also the <a href="/manual">CLI manual</a> and the <a href="https://github.com/niclaslindstedt/juris">GitHub repository</a>.</p>`;
  const html = buildRoute({
    url: "/docs",
    outFile: join(DIST, "docs", "index.html"),
    title,
    description: desc,
    bodyHtml,
    jsonLd: [itemList],
  });
  writePage(join(DIST, "docs", "index.html"), html);
}

// --- Render manual pages ---

for (const p of manPages) {
  const cmdLabel = p.slug === "juris" ? "juris" : `juris ${p.slug}`;
  const title = `${cmdLabel} — juris manual`;
  const desc = firstParagraph(p.content) ||
    `Reference documentation for the \`${cmdLabel}\` command in juris, the Swedish legal data CLI.`;
  const article = {
    "@context": "https://schema.org",
    "@type": "TechArticle",
    headline: cmdLabel,
    description: desc,
    url: `${SITE_URL}/manual/${p.slug}`,
    inLanguage: "en",
    isPartOf: { "@type": "WebSite", name: "juris", url: SITE_URL },
    author: { "@type": "Person", name: "Niclas Lindstedt" },
    keywords: `juris, ${cmdLabel}, cli, manual, swedish law, legal data, python`,
    proficiencyLevel: "Beginner",
  };
  const breadcrumb = {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: [
      { "@type": "ListItem", position: 1, name: "Home", item: SITE_URL + "/" },
      {
        "@type": "ListItem",
        position: 2,
        name: "Manual",
        item: SITE_URL + "/manual",
      },
      {
        "@type": "ListItem",
        position: 3,
        name: cmdLabel,
        item: `${SITE_URL}/manual/${p.slug}`,
      },
    ],
  };
  const bodyHtml =
    `<header><h1>${escapeHtml(cmdLabel)}</h1>` +
    `<p><a href="/">juris</a> &rsaquo; <a href="/manual">Manual</a> &rsaquo; ${escapeHtml(cmdLabel)}</p></header>` +
    `<article>${renderMarkdownToHtml(p.content)}</article>` +
    `<footer><p>Source: <a href="https://github.com/niclaslindstedt/juris/blob/main/man/${p.slug}.md">man/${p.slug}.md</a> &middot; <a href="/">juris home</a> &middot; <a href="/docs">Documentation</a></p></footer>`;
  const html = buildRoute({
    url: `/manual/${p.slug}`,
    outFile: join(DIST, "manual", p.slug, "index.html"),
    title,
    description: desc.slice(0, 300),
    bodyHtml,
    jsonLd: [article, breadcrumb],
  });
  writePage(join(DIST, "manual", p.slug, "index.html"), html);
}

// /manual index
{
  const title = "juris CLI manual — every command, flag, and option";
  const desc =
    "Reference documentation for every juris CLI command: collect, collect-type, collect-all, update, status, stats, search, validate, report, logs, man.";
  const items = manPages.map((p, i) => ({
    "@type": "ListItem",
    position: i + 1,
    name: p.slug === "juris" ? "juris" : `juris ${p.slug}`,
    url: `${SITE_URL}/manual/${p.slug}`,
  }));
  const itemList = {
    "@context": "https://schema.org",
    "@type": "ItemList",
    name: "juris CLI commands",
    itemListElement: items,
  };
  const bodyHtml =
    `<header><h1>juris — CLI Manual</h1>` +
    `<p>Complete reference documentation for every juris command.</p></header>` +
    `<nav><ul>` +
    manPages
      .map((p) => {
        const label = p.slug === "juris" ? "juris" : `juris ${p.slug}`;
        return `<li><a href="/manual/${p.slug}"><code>${escapeHtml(label)}</code></a> — ${escapeHtml(firstParagraph(p.content).slice(0, 160))}</li>`;
      })
      .join("") +
    `</ul></nav>` +
    `<p>See also the <a href="/docs">documentation</a> and the <a href="https://github.com/niclaslindstedt/juris">GitHub repository</a>.</p>`;
  const html = buildRoute({
    url: "/manual",
    outFile: join(DIST, "manual", "index.html"),
    title,
    description: desc,
    bodyHtml,
    jsonLd: [itemList],
  });
  writePage(join(DIST, "manual", "index.html"), html);
}

// --- llms.txt — short, link-rich project summary for LLM crawlers ---
//     See: https://llmstxt.org/

const llmsTxt = `# juris

> Open-source Python CLI that collects and normalizes Swedish and EU legal documents — propositioner, SOU, betänkanden, SFS, NJA, AD, HFD, AFS, JO, JK, EU regulations, CJEU and ECHR rulings — into a git-friendly database of JSON + Markdown. ${manPages.length} CLI commands, 21 document types, 8 official sources.

Version: ${VERSION}
Repository: https://github.com/niclaslindstedt/juris
Package: https://pypi.org/project/juris/
License: MIT
Language: Python 3.11+

## Quick start

\`\`\`bash
pip install juris
juris collect-all
\`\`\`

## Documentation

${docPages.map((p) => `- [${p.title}](${SITE_URL}/docs/${p.slug}): ${firstParagraph(p.content).slice(0, 200)}`).join("\n")}

## CLI manual

${manPages.map((p) => `- [${p.slug === "juris" ? "juris" : `juris ${p.slug}`}](${SITE_URL}/manual/${p.slug}): ${firstParagraph(p.content).slice(0, 200)}`).join("\n")}

## Optional

- [Full corpus for LLM ingestion](${SITE_URL}/llms-full.txt): every doc and man page concatenated as plain markdown.
- [Sitemap](${SITE_URL}/sitemap.xml)
- [robots.txt](${SITE_URL}/robots.txt)
`;

writeFileSync(join(DIST, "llms.txt"), llmsTxt, "utf-8");

// --- llms-full.txt — full corpus, plain markdown ---

const llmsFullParts: string[] = [
  `# juris ${VERSION}`,
  ``,
  `Open-source Python CLI that collects Swedish + EU legal documents into JSON + Markdown.`,
  `Repository: https://github.com/niclaslindstedt/juris`,
  `PyPI: https://pypi.org/project/juris/`,
  ``,
  `---`,
  `## Documentation`,
  `---`,
];

for (const p of docPages) {
  llmsFullParts.push("");
  llmsFullParts.push(`### docs/${p.slug}.md`);
  llmsFullParts.push("");
  llmsFullParts.push(p.content.trim());
  llmsFullParts.push("");
}

llmsFullParts.push("---");
llmsFullParts.push("## CLI manual");
llmsFullParts.push("---");

for (const p of manPages) {
  llmsFullParts.push("");
  llmsFullParts.push(`### man/${p.slug}.md`);
  llmsFullParts.push("");
  llmsFullParts.push(p.content.trim());
  llmsFullParts.push("");
}

writeFileSync(join(DIST, "llms-full.txt"), llmsFullParts.join("\n"), "utf-8");

console.log(`Prerendered:`);
console.log(`  docs pages: ${docPages.length} (+ /docs index)`);
console.log(`  manual pages: ${manPages.length} (+ /manual index)`);
console.log(`  llms.txt`);
console.log(`  llms-full.txt`);
