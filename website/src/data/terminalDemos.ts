import type { TerminalTab } from "./logStyles";

export const terminalDemos: TerminalTab[] = [
  {
    label: "Collect",
    sequence: [
      { type: "comment", text: "# Collect government bills from Riksdagen" },
      {
        type: "command",
        text: "zig collect prop --limit 5",
      },
      { type: "pause", duration: 400 },
      {
        type: "output",
        delay: 200,
        lines: [
          { text: "\u26a1 zag agent initialized (claude/sonnet)", style: "zag" },
          { text: "\u2713 Connected to riksdagen API", style: "success" },
        ],
      },
      { type: "pause", duration: 300 },
      {
        type: "output",
        delay: 80,
        lines: [
          { text: "  Collecting prop from riksdagen...", style: "info" },
          { text: "  \u23fa Parsing prop-2024/25:208 \u2014 Ny budgetlag", style: "agent" },
          { text: "  \u2190 extracted 47 pages, 3 attachments", style: "result" },
          { text: "  \u23fa Parsing prop-2024/25:195 \u2014 \u00c4ndring i milj\u00f6balken", style: "agent" },
          { text: "  \u2190 extracted 23 pages, 1 attachment", style: "result" },
          { text: "  \u23fa Parsing prop-2024/25:182 \u2014 Dataskyddsreform", style: "agent" },
          { text: "  \u2190 extracted 91 pages, 5 attachments", style: "result" },
        ],
      },
      { type: "pause", duration: 300 },
      {
        type: "output",
        lines: [
          "",
          { text: "\u2713 Collected 5 documents", style: "success" },
          { text: "  data/prop/2024-25/ | 5 new files (JSON + MD)", style: "stat" },
          "",
          "Duration: 4.2s \u00b7 Pages extracted: 284 \u00b7 Attachments: 12",
        ],
      },
      { type: "pause", duration: 2500 },
    ],
  },
  {
    label: "Search",
    sequence: [
      { type: "comment", text: "# Search across all collected documents" },
      {
        type: "command",
        text: 'zig search "dataskydd" --doc-type prop,sou',
      },
      { type: "pause", duration: 300 },
      {
        type: "output",
        delay: 150,
        lines: [
          { text: "\u26a1 zag agent analyzing query...", style: "zag" },
          { text: "  \u23fa Searching local index (2,847 documents)...", style: "agent" },
        ],
      },
      { type: "pause", duration: 500 },
      {
        type: "output",
        delay: 60,
        lines: [
          "",
          { text: "  prop-2024/25:182  Dataskyddsreform              2025-01-15", style: "result" },
          { text: '    "...st\u00e4rkt dataskydd f\u00f6r enskilda vid behandling av..."', style: "dim" },
          "",
          { text: "  sou-2024:39       Dataskydd i praktiken          2024-09-20", style: "result" },
          { text: '    "...utredningen f\u00f6resl\u00e5r nya regler f\u00f6r dataskydd..."', style: "dim" },
          "",
          { text: "  prop-2023/24:144  Kompletterande dataskyddslag   2024-03-12", style: "result" },
          { text: '    "...\u00e4ndringar i den kompletterande dataskyddslagen..."', style: "dim" },
          "",
          { text: "\u2713 Found 3 results in 0.8s", style: "success" },
        ],
      },
      { type: "pause", duration: 2500 },
    ],
  },
  {
    label: "Multi-Source",
    sequence: [
      { type: "comment", text: "# Collect from multiple sources in parallel" },
      {
        type: "command",
        text: "zig collect-all --since 2025-01-01",
        typingSpeed: 40,
      },
      { type: "pause", duration: 300 },
      {
        type: "output",
        delay: 150,
        lines: [
          { text: "\u26a1 zag orchestrating 8 collection agents...", style: "zag" },
          "",
          { text: "  riksdagen  \u23fa collecting prop, mot, bet, skr...", style: "agent" },
          { text: "  regeringen \u23fa collecting sou, ds, dir, lagr...", style: "agent" },
          { text: "  domstol    \u23fa collecting nja, ad, hfd...", style: "agent" },
          { text: "  eur_lex    \u23fa collecting eu_reg, eu_dir...", style: "agent" },
        ],
      },
      { type: "pause", duration: 800 },
      {
        type: "output",
        delay: 100,
        lines: [
          "",
          { text: "  \u2713 riksdagen   47 documents collected", style: "success" },
          { text: "  \u2713 regeringen  23 documents collected", style: "success" },
          { text: "  \u2713 domstol     31 documents collected", style: "success" },
          { text: "  \u2713 eur_lex     15 documents collected", style: "success" },
          { text: "  \u2713 curia        8 documents collected", style: "success" },
          { text: "  \u2713 hudoc        5 documents collected", style: "success" },
          { text: "  \u2713 jo_jk       12 documents collected", style: "success" },
          { text: "  \u2713 lagrummet    9 documents collected", style: "success" },
        ],
      },
      { type: "pause", duration: 300 },
      {
        type: "output",
        lines: [
          "",
          { text: "\u2713 All 8 sources completed \u2014 150 documents total", style: "success" },
          "Duration: 28.4s \u00b7 New: 150 \u00b7 Updated: 0 \u00b7 Skipped: 0",
        ],
      },
      { type: "pause", duration: 2500 },
    ],
  },
  {
    label: "Agent Report",
    sequence: [
      { type: "comment", text: "# Generate an AI-powered coverage report" },
      {
        type: "command",
        text: "zig report --diff",
      },
      { type: "pause", duration: 400 },
      {
        type: "output",
        delay: 200,
        lines: [
          { text: "\u26a1 zag agent analyzing collection coverage...", style: "zag" },
        ],
      },
      { type: "pause", duration: 600 },
      {
        type: "output",
        delay: 80,
        lines: [
          "",
          { text: "Coverage Report \u2014 2025-04-09", style: "info" },
          "",
          { text: "  Source        Types  Documents  Coverage", style: "stat" },
          { text: "  \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500", style: "stat" },
          { text: "  riksdagen    4      2,341      94%", style: "result" },
          { text: "  regeringen   4      1,208      87%", style: "result" },
          { text: "  domstol      5        892      76%", style: "result" },
          { text: "  eur_lex      2        634      91%", style: "result" },
          { text: "  curia        1        287      82%", style: "result" },
          { text: "  hudoc        1        156      79%", style: "result" },
          { text: "  jo_jk        2        445      88%", style: "result" },
          { text: "  lagrummet    2        198      71%", style: "result" },
          "",
          { text: "  \u0394 Since last report: +150 new, 12 updated", style: "info" },
          { text: "\u2713 Report saved to .reports/2025-04-09.json", style: "success" },
        ],
      },
      { type: "pause", duration: 2500 },
    ],
  },
];
