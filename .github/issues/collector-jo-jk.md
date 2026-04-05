# Collector: JO- och JK-beslut

## Description

Add a collector for decisions from **Justitieombudsmannen (JO)** and **Justitiekanslern (JK)**.

JO (the Parliamentary Ombudsman) supervises public authorities' compliance with laws. JK (the Chancellor of Justice) serves a similar function under the government and also handles state liability claims.

## Why it matters

While JO and JK decisions are not formally binding as prejudikat, they carry significant interpretive weight in Swedish law, particularly regarding:

- **Förvaltningsrätt** — how public authorities should apply the law
- **Offentlighetsprincipen** — public access to documents
- **Mänskliga rättigheter** — fundamental rights in practice
- **Myndighetsutövning** — exercise of public authority

JO decisions are frequently cited in legal argumentation and by courts when assessing whether an authority has acted correctly.

## Known data sources

- **JO**: `https://www.jo.se` — publishes decisions, searchable archive
- **JK**: `https://www.jk.se` — publishes decisions and opinions

## Document types

- `jo` — Justitieombudsmannens beslut
- `jk` — Justitiekanslerns beslut

## Implementation notes

- JO and JK have separate websites with different structures
- JO publishes an annual report (ämbetsberättelse) that compiles key decisions
- Both sources likely require web scraping rather than API access
- Consider starting with JO as it has the larger and more frequently cited body of decisions
