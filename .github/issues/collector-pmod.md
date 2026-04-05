# Collector: Patent- och marknadsöverdomstolen (PMÖD)

## Description

Add a collector for **Patent- och marknadsöverdomstolen** (Patent and Market Court of Appeal) decisions.

PMÖD handles appeals in intellectual property, marketing law, and competition law. It replaced the former Marknadsdomstolen in 2016 and is part of Svea hovrätt.

## Why it matters

PMÖD decisions are prejudikat for IP law, marknadsrätt, and konkurrensrätt. These are specialized but important areas, particularly for commercial legal practice.

## Known data sources

- **Domstolsverket rättspraxis API**: may include PMÖD decisions
- **Svea hovrätt website**: PMÖD decisions may be published there
- **Konkurrensverket**: may republish relevant competition law decisions

## Document type

- `pmod` — Patent- och marknadsöverdomstolens avgöranden

## Implementation notes

- PMÖD was established in 2016, replacing Marknadsdomstolen (MD)
- Historical MD decisions may also be worth collecting for completeness
- Investigate available data sources before implementation
