---
description: "Sync the zig website with the Python source. Run when models, collectors, CLI commands, man pages, or docs change. Extracts data, updates components if needed, builds, and verifies."
---

# Syncing the Website

The zig website (`website/src/`) sources its data from the Python codebase. When the Python source changes (models, collectors, CLI, docs, man pages), the website needs to be re-synced.

## What Gets Synced

The `extract-data.ts` script parses the Python source and generates `website/src/data/sourceData.ts`, which contains:

- **Version** from `pyproject.toml`
- **DocType enum** members + descriptions from `src/juris/models.py`
- **Source enum** members from `src/juris/models.py`
- **Collector metadata** (supported doc types, preferred_for) from `src/juris/collectors/*.py`
- **Doc type categories** (Parliament, Government, Courts, Authorities, EU Law)
- **Man pages** from `man/*.md`
- **Doc pages** from `docs/*.md`

Additionally, docs and man pages are imported directly via Vite's `?raw` suffix in:
- `website/src/data/docs.ts` — imports `docs/*.md`
- `website/src/data/manpages.ts` — imports `man/*.md`

## Sync Process

### Step 1: Run the extraction

```sh
cd website && npm run extract
```

This regenerates `website/src/data/sourceData.ts`. Review the output counts:
```
Generated website/src/data/sourceData.ts
  Version: X.Y.Z
  DocTypes: 21
  Sources: 8
  Collectors: 8
  Man pages: 7
  Doc pages: 7
```

### Step 2: Check if component updates are needed

If the changes include:

| Change | Files to check |
|--------|---------------|
| New Source enum member | `Sources.tsx` — add source metadata to `SOURCE_META` in `extract-data.ts` |
| New DocType enum member | `DocTypes.tsx` — verify it appears in a category in `DOC_TYPE_CATEGORIES` |
| New collector file | Automatic — collectors are auto-discovered by `extract-data.ts` |
| New man page | `manpages.ts` — add the import and entry to `manPageGroups` |
| New doc page | `docs.ts` — add the import and entry to `docs` array |
| Version bump | Automatic — version is extracted from `pyproject.toml` |
| New CLI command | Verify `man/` has a page; `GettingStarted.tsx` may need updating |
| New feature | `Features.tsx` — consider adding a feature card |
| Terminal demos stale | `terminalDemos.ts` — update demo sequences |

### Step 3: Build and verify

```sh
cd website && npm run build
```

The build must complete without errors. Optionally start the dev server:

```sh
cd website && npm run dev
```

Then open http://localhost:5173/ and verify:
1. Hero shows correct version and source/doc-type counts
2. Sources section shows all 8 sources with correct doc types
3. Doc Types section shows all 21 types in correct categories
4. Terminal demos play correctly
5. Docs and Manual pages render properly

### Step 4: Update tracking

Record the current commit as the sync baseline:

```sh
git rev-parse HEAD > .claude/skills/sync-website/.last-synced
```

## Component Mapping

| Component | File | Data source |
|-----------|------|-------------|
| Hero | `Hero.tsx` | `VERSION`, `SOURCES`, `DOC_TYPES` from sourceData.ts |
| Features | `Features.tsx` | `SOURCES`, `DOC_TYPES` counts from sourceData.ts |
| Sources | `Sources.tsx` | `SOURCES` from sourceData.ts |
| DocTypes | `DocTypes.tsx` | `DOC_TYPES`, `DOC_TYPE_CATEGORIES` from sourceData.ts |
| ZagRelationship | `ZagRelationship.tsx` | Static content (update when architecture changes) |
| CodeExamples | `CodeExamples.tsx` | Static CLI examples (update when CLI syntax changes) |
| GettingStarted | `GettingStarted.tsx` | Static install instructions |
| Terminal | `terminalDemos.ts` | Static demo sequences |
| Docs sidebar | `docs.ts` | Imports from `docs/*.md` |
| Manual sidebar | `manpages.ts` | Imports from `man/*.md` |

## Adding a New Source

1. Add the Source enum member in `src/juris/models.py`
2. Create the collector in `src/juris/collectors/`
3. Add metadata to `SOURCE_META` in `website/scripts/extract-data.ts`
4. Run `npm run extract` — the source appears automatically
5. Verify in `Sources.tsx` that it renders correctly

## Adding a New Doc Type

1. Add the DocType enum member in `src/juris/models.py`
2. Add it to the appropriate category in `DOC_TYPE_CATEGORIES` in `extract-data.ts`
3. Run `npm run extract` — it appears in the categories
4. Verify in `DocTypes.tsx`

## Adding a New Man Page

1. Create `man/new-command.md`
2. Add the import and entry in `website/src/data/manpages.ts`:
   ```ts
   import newCommand from "../../../man/new-command.md?raw";
   // Add to appropriate group in manPageGroups
   ```
3. Build to verify

## Adding a New Doc Page

1. Create `docs/new-topic.md`
2. Add the import and entry in `website/src/data/docs.ts`:
   ```ts
   import newTopic from "../../../docs/new-topic.md?raw";
   // Add to docs array
   ```
3. Build to verify

## Verification Checklist

- [ ] `npm run extract` succeeds with correct counts
- [ ] `npm run build` succeeds without TypeScript or Vite errors
- [ ] All data-driven sections show correct, up-to-date information
- [ ] No broken imports or missing pages
- [ ] Update `.claude/skills/sync-website/.last-synced` with current HEAD
