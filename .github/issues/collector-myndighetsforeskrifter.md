# Collector: Myndighetsföreskrifter och allmänna råd

## Description

Add a collector for **myndighetsföreskrifter** (regulatory agency rules) and **allmänna råd** (general guidelines) issued by Swedish government agencies.

These are legally binding rules issued under delegation from the Riksdag or government, and published in each agency's own författningssamling (e.g. SOSFS, SKVFS, FFFS).

## Why it matters

Myndighetsföreskrifter sit below SFS in the normhierarki but are legally binding. In practice, they are often more detailed and directly applicable than the enabling statutes. For example:

- **SOSFS** (Socialstyrelsen) — healthcare regulations
- **SKVFS** (Skatteverket) — tax regulations
- **FFFS** (Finansinspektionen) — financial regulations
- **AFS** (Arbetsmiljöverket) — workplace safety regulations
- **NFS** (Naturvårdsverket) — environmental regulations

Any complete legal analysis frequently requires consulting these.

## Known data sources

- **Lagrummet**: `https://lagrummet.se` — aggregates some myndighetsföreskrifter
- **Individual agency websites** — each agency publishes its own författningssamling
- **Riksarkivet**: maintains a register of Swedish författningssamlingar

## Document type

- `foreskrift` — Myndighetsföreskrifter och allmänna råd

## Implementation notes

- The fragmented nature of these sources (each agency has its own system) makes this challenging
- A phased approach starting with the most commonly cited agencies (Skatteverket, Socialstyrelsen, Finansinspektionen) is recommended
- Lagrummet may provide a unified entry point for discovery
