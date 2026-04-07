/**
 * extract-data.ts — Parses Python source files to generate sourceData.ts
 *
 * Keeps the website in sync with the juris codebase by extracting:
 * - DocType and Source enums from models.py
 * - Collector metadata (supported doc types, preferred_for) from collectors/*.py
 * - Man page content from man/*.1
 * - Version from pyproject.toml
 */

import { readFileSync, writeFileSync, readdirSync, mkdirSync } from "fs";
import { resolve, join, dirname } from "path";

const ROOT = resolve(import.meta.dirname, "../..");
const MODELS_PATH = join(ROOT, "src/juris/models.py");
const COLLECTORS_DIR = join(ROOT, "src/juris/collectors");
const MAN_DIR = join(ROOT, "man");
const PYPROJECT_PATH = join(ROOT, "pyproject.toml");
const OUTPUT_PATH = resolve(import.meta.dirname, "../src/data/sourceData.ts");

// --- Manual metadata not reliably parseable from code ---

const SOURCE_META: Record<string, { url: string; method: string; description: string }> = {
  riksdagen: {
    url: "data.riksdagen.se",
    method: "JSON API",
    description: "Swedish Parliament open data",
  },
  regeringen: {
    url: "regeringen.se",
    method: "Web Scraping",
    description: "Swedish Government publications",
  },
  domstol: {
    url: "domstol.se",
    method: "REST API",
    description: "Swedish courts decisions",
  },
  jo_jk: {
    url: "jo.se / jk.se",
    method: "Web Scraping",
    description: "Parliamentary & Chancellor of Justice ombudsmen",
  },
  lagrummet: {
    url: "lagrummet.se",
    method: "Web Scraping",
    description: "Agency regulations and guidelines",
  },
  eur_lex: {
    url: "eur-lex.europa.eu",
    method: "SPARQL",
    description: "EU regulations and directives",
  },
  curia: {
    url: "curia.europa.eu",
    method: "SPARQL",
    description: "Court of Justice of the EU",
  },
  hudoc: {
    url: "hudoc.echr.coe.int",
    method: "JSON API",
    description: "European Court of Human Rights",
  },
};

// --- Parsing helpers ---

function extractVersion(): string {
  const content = readFileSync(PYPROJECT_PATH, "utf-8");
  const match = content.match(/^version\s*=\s*"([^"]+)"/m);
  return match?.[1] ?? "0.0.0";
}

interface EnumMember {
  name: string;
  value: string;
  description: string;
}

function extractEnum(content: string, enumName: string): EnumMember[] {
  const members: EnumMember[] = [];
  const classPattern = new RegExp(`^class ${enumName}\\(`, "m");
  const classMatch = content.match(classPattern);
  if (!classMatch || classMatch.index === undefined) return members;

  const after = content.slice(classMatch.index);
  const lines = after.split("\n").slice(1); // skip class line

  for (const line of lines) {
    // Stop at next class or top-level definition
    if (/^\S/.test(line) && line.trim() !== "") break;

    const m = line.match(/^\s+(\w+)\s*=\s*"([^"]+)"(?:\s*#\s*(.+))?/);
    if (m) {
      members.push({
        name: m[1],
        value: m[2],
        description: (m[3] ?? "").trim(),
      });
    }
  }
  return members;
}

/**
 * Parse a dict like `_COURT_MAP: dict[DocType, str] = { DocType.NJA: "HDO", ... }`
 * and return the DocType values referenced as keys.
 */
function extractDictDocTypeKeys(content: string, dictName: string): string[] {
  const keys: string[] = [];
  const pattern = new RegExp(`^${dictName}\\b.*?=\\s*\\{`, "m");
  const match = content.match(pattern);
  if (!match || match.index === undefined) return keys;

  const after = content.slice(match.index);
  const lines = after.split("\n");

  for (let i = 1; i < lines.length; i++) {
    const line = lines[i];
    if (line.match(/^\s*\}/)) break;
    const m = line.match(/DocType\.(\w+)/);
    if (m) keys.push(m[1]);
  }
  return keys;
}

interface CollectorInfo {
  sourceValue: string;
  supportedDocTypes: string[];
  preferredFor: string[];
}

function extractCollector(filePath: string, docTypesByName: Map<string, string>): CollectorInfo | null {
  const content = readFileSync(filePath, "utf-8");

  // Find source = Source.XXX
  const sourceMatch = content.match(/^\s+source\s*=\s*Source\.(\w+)/m);
  if (!sourceMatch) return null;
  const sourceValue = sourceMatch[1].toLowerCase();

  // Find supported_doc_types
  let supportedDocTypes: string[] = [];
  const supportedMatch = content.match(/^\s+supported_doc_types\s*=\s*(.+)/m);
  if (supportedMatch) {
    const rhs = supportedMatch[1].trim();

    if (rhs.startsWith("list(")) {
      // list(_DICT_NAME.keys())
      const dictRef = rhs.match(/list\((\w+)\.keys\(\)\)/);
      if (dictRef) {
        const dictKeys = extractDictDocTypeKeys(content, dictRef[1]);
        supportedDocTypes = dictKeys.map((k) => docTypesByName.get(k) ?? k.toLowerCase());
      }
    } else {
      // [DocType.X, DocType.Y, ...]
      const matches = rhs.matchAll(/DocType\.(\w+)/g);
      for (const m of matches) {
        supportedDocTypes.push(docTypesByName.get(m[1]) ?? m[1].toLowerCase());
      }
    }
  }

  // Find preferred_for
  const preferredFor: string[] = [];
  const preferredMatch = content.match(/^\s+preferred_for\s*=\s*\[(.+)\]/m);
  if (preferredMatch) {
    const matches = preferredMatch[1].matchAll(/DocType\.(\w+)/g);
    for (const m of matches) {
      preferredFor.push(docTypesByName.get(m[1]) ?? m[1].toLowerCase());
    }
  }

  return { sourceValue, supportedDocTypes, preferredFor };
}

interface ManPage {
  command: string;
  title: string;
  content: string;
}

function extractManPages(): ManPage[] {
  const pages: ManPage[] = [];
  try {
    const files = readdirSync(MAN_DIR).filter((f) => f.endsWith(".md")).sort();
    for (const file of files) {
      const command = file.replace(/\.md$/, "");
      const content = readFileSync(join(MAN_DIR, file), "utf-8");
      const titleMatch = content.match(/^#\s+(.+)/m);
      const title = titleMatch?.[1] ?? command;
      pages.push({ command, title, content });
    }
  } catch {
    // man dir may not exist
  }
  return pages;
}

// --- Main ---

const modelsContent = readFileSync(MODELS_PATH, "utf-8");
const docTypes = extractEnum(modelsContent, "DocType");
const sources = extractEnum(modelsContent, "Source");
const version = extractVersion();
const manPages = extractManPages();

// Build name -> value lookup for DocType
const docTypesByName = new Map(docTypes.map((dt) => [dt.name, dt.value]));

// Parse all collectors
const collectorFiles = readdirSync(COLLECTORS_DIR)
  .filter((f) => f.endsWith(".py") && !f.startsWith("_") && f !== "base.py")
  .sort();

const collectors: CollectorInfo[] = [];
for (const file of collectorFiles) {
  const info = extractCollector(join(COLLECTORS_DIR, file), docTypesByName);
  if (info) collectors.push(info);
}

// Build source data combining enums + collector info
const sourceData = sources.map((s) => {
  const collector = collectors.find((c) => c.sourceValue === s.value);
  const meta = SOURCE_META[s.value] ?? { url: "", method: "Unknown", description: "" };
  return {
    value: s.value,
    name: s.name,
    supportedDocTypes: collector?.supportedDocTypes ?? [],
    preferredFor: collector?.preferredFor ?? [],
    method: meta.method,
    url: meta.url,
    description: meta.description,
  };
});

// Doc type categories
const categories: Record<string, string[]> = {
  "Swedish Parliament": ["prop", "mot", "bet", "skr"],
  "Swedish Government": ["sou", "ds", "dir", "lagr", "sfs"],
  Courts: ["nja", "ad", "hfd", "mod", "pmod"],
  Authorities: ["jo", "jk", "foreskrift"],
  "EU Law": ["eu_reg", "eu_dir", "cjeu", "echr"],
};

// --- Generate output ---

const output = `// AUTO-GENERATED by scripts/extract-data.ts — do not edit manually

export const VERSION = ${JSON.stringify(version)};

export interface DocTypeInfo {
  value: string;
  name: string;
  description: string;
}

export interface SourceInfo {
  value: string;
  name: string;
  supportedDocTypes: string[];
  preferredFor: string[];
  method: string;
  url: string;
  description: string;
}

export interface ManPage {
  command: string;
  title: string;
  content: string;
}

export const DOC_TYPES: DocTypeInfo[] = ${JSON.stringify(docTypes, null, 2)};

export const SOURCES: SourceInfo[] = ${JSON.stringify(sourceData, null, 2)};

export const DOC_TYPE_CATEGORIES: Record<string, string[]> = ${JSON.stringify(categories, null, 2)};

export const MAN_PAGES: ManPage[] = ${JSON.stringify(manPages, null, 2)};
`;

mkdirSync(dirname(OUTPUT_PATH), { recursive: true });
writeFileSync(OUTPUT_PATH, output, "utf-8");
console.log(`Generated ${OUTPUT_PATH}`);
console.log(`  Version: ${version}`);
console.log(`  DocTypes: ${docTypes.length}`);
console.log(`  Sources: ${sourceData.length}`);
console.log(`  Collectors: ${collectors.length}`);
console.log(`  Man pages: ${manPages.length}`);
