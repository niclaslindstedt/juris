"""Collector package with auto-discovery.

Concrete ``BaseCollector`` subclasses register themselves automatically
via ``__init_subclass__``.  All public modules in this package are
discovered lazily on first registry access, so adding a new collector
only requires creating a new ``.py`` file — no manual registration needed.
"""

from __future__ import annotations

from juris.collectors.base import (  # noqa: F401  — re-export registry API
    BaseCollector,
    get_collector_class,
    get_doc_type_providers,
    get_preferred_providers,
    get_registry,
)

# Backward-compatible re-exports — existing code that does
# ``from juris.collectors import RiksdagenCollector`` keeps working.
from juris.collectors.curia import CjeuCollector as CjeuCollector
from juris.collectors.domstol import DomstolCollector as DomstolCollector
from juris.collectors.eurlex import EurLexCollector as EurLexCollector
from juris.collectors.hudoc import HudocCollector as HudocCollector
from juris.collectors.jo_jk import JoJkCollector as JoJkCollector
from juris.collectors.lagrummet import LagrummetCollector as LagrummetCollector
from juris.collectors.regeringen import RegeringenCollector as RegeringenCollector
from juris.collectors.riksdagen import RiksdagenCollector as RiksdagenCollector

__all__ = [
    "BaseCollector",
    "CjeuCollector",
    "DomstolCollector",
    "EurLexCollector",
    "HudocCollector",
    "JoJkCollector",
    "LagrummetCollector",
    "RegeringenCollector",
    "RiksdagenCollector",
    "get_collector_class",
    "get_doc_type_providers",
    "get_preferred_providers",
    "get_registry",
]
