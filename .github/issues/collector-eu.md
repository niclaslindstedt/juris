# Collector: EU-rätt (EUR-Lex, CJEU, ECHR)

## Description

Add collectors for **EU law sources** relevant to Swedish legal practice:

1. **EU regulations and directives** — directly applicable or transposed into Swedish law
2. **CJEU case law** (EU-domstolen) — binding interpretation of EU law
3. **ECHR** (Europakonventionen) and **ECtHR case law** — incorporated into Swedish law via RF 2:19

## Why it matters

EU law has supremacy over national law and is increasingly central to the Swedish legal method. Many Swedish statutes implement EU directives, and Swedish courts are bound by CJEU interpretations. The ECHR has constitutional status in Sweden since its incorporation.

Any serious application of den juridiska metoden must account for the EU law dimension.

## Known data sources

- **EUR-Lex**: `https://eur-lex.europa.eu` — provides a SPARQL endpoint and REST API for accessing EU legislation
- **CJEU (CURIA)**: `https://curia.europa.eu` — case law database with search API
- **ECtHR (HUDOC)**: `https://hudoc.echr.coe.int` — full-text search API for ECtHR case law
- **CELLAR**: EU's common repository, accessible via SPARQL

## Document types

- `eu_reg` — EU regulations (förordningar)
- `eu_dir` — EU directives (direktiv)
- `cjeu` — CJEU judgments and opinions
- `echr` — ECtHR judgments

## Implementation notes

- This is a larger effort spanning multiple APIs and document types
- Consider starting with CJEU case law citing Swedish cases, then expanding
- EUR-Lex provides structured data in multiple formats (XML, RDF, HTML)
- Language filtering to Swedish versions where available
- The ECHR/ECtHR may warrant its own collector given the different API
