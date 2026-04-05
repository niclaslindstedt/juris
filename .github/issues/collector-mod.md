# Collector: Mark- och miljööverdomstolen (MÖD)

## Description

Add a collector for **Mark- och miljööverdomstolen** (Land and Environment Court of Appeal) decisions.

MÖD is the final instance for most environmental and land use cases in Sweden, including plan- och bygglagen (PBL), miljöbalken, and related legislation.

## Why it matters

Environmental and land use law is a growing area of Swedish legal practice. MÖD decisions serve as prejudikat for all mark- och miljödomstolar and are essential for practitioners in these fields.

## Known data sources

- **Domstolsverket rättspraxis API**: `https://rattspraxis.etjanst.domstol.se` — may include MÖD decisions
- **Svea hovrätt (MÖD is part of Svea hovrätt)**: decisions may be published on the court website

## Document type

- `mod` — Mark- och miljööverdomstolens avgöranden

## Implementation notes

- MÖD decisions are typically referenced by case number (e.g., "MÖD 2025:12")
- Investigate whether Domstolsverket API covers MÖD or if a separate source is needed
