# Collector: Högsta förvaltningsdomstolen (HFD)

## Description

Add a collector for **Högsta förvaltningsdomstolen** (Supreme Administrative Court) decisions.

HFD is the supreme court for administrative law in Sweden, covering areas such as tax law, social insurance, migration, and public procurement. Together with HD, it forms the two pillars of Swedish case law.

## Why it matters

Without HFD, roughly half of all prejudikat in Swedish law are missing. Administrative law is one of the most active areas of Swedish legal practice, and HFD decisions are binding precedent for all lower administrative courts (förvaltningsrätter and kammarrätter).

In the rättskällehierarki, HFD decisions carry the same weight as HD (NJA) decisions.

## Known data sources

- **Domstolsverket rättspraxis API**: `https://rattspraxis.etjanst.domstol.se` — the same API used for HD/NJA likely provides HFD decisions as well
- **Lagrummet**: `https://lagrummet.se` — may provide additional structured metadata

## Document type

- `hfd` — Högsta förvaltningsdomstolens årsbok (previously RÅ — Regeringsrättens årsbok)

## Implementation notes

- The existing `domstol.py` collector likely needs to be extended to support HFD as an additional court
- The Document model already supports adding new `DocType` enum values
- HFD references follow the pattern "HFD 2025 ref. 19" (post-2011) or "RÅ 2010 ref. 19" (pre-2011)
