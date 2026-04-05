# Collector: Arbetsdomstolen (AD)

## Description

Add a collector for **Arbetsdomstolen** (Labour Court) decisions.

Arbetsdomstolen is the court of last instance for labour law disputes in Sweden. Its decisions are binding precedent for all labour law matters and are frequently cited in both legal practice and doctrine.

## Why it matters

Labour law (arbetsrätt) is a major area of Swedish law. AD decisions interpret key legislation such as LAS (lagen om anställningsskydd), MBL (medbestämmandelagen), and the Discrimination Act (diskrimineringslagen). These are essential prejudikat for anyone working with employment law.

## Known data sources

- **Arbetsdomstolen website**: `https://www.arbetsdomstolen.se` — publishes decisions, possibly scrapeable
- **Domstolsverket rättspraxis API**: may include AD decisions

## Document type

- `ad` — Arbetsdomstolens domar

## Implementation notes

- AD decisions are typically referenced as "AD 2025 nr 19"
- A new collector or extension of the domstol collector may be needed depending on the data source
