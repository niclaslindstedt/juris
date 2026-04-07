"""Tests for the collector auto-discovery registry."""

from __future__ import annotations

import pytest

from juris.collectors import (
    BaseCollector,
    get_collector_class,
    get_doc_type_providers,
    get_preferred_providers,
    get_registry,
)
from juris.models import DocType, Source


class TestAutoDiscovery:
    """Verify that all collectors are discovered and registered."""

    def test_all_sources_registered(self) -> None:
        registry = get_registry()
        for src in Source:
            assert src.value in registry, f"Source {src} not in registry"

    def test_registry_count(self) -> None:
        assert len(get_registry()) == len(Source)

    def test_registry_values_are_collector_subclasses(self) -> None:
        for name, cls in get_registry().items():
            assert issubclass(cls, BaseCollector), (
                f"{name} -> {cls} is not a BaseCollector subclass"
            )

    def test_get_collector_class(self) -> None:
        cls = get_collector_class("riksdagen")
        assert cls.source == Source.RIKSDAGEN

    def test_get_collector_class_unknown_raises(self) -> None:
        with pytest.raises(KeyError):
            get_collector_class("nonexistent")


class TestDocTypeProviders:
    """Verify the doc-type -> provider mapping."""

    def test_every_doc_type_has_provider(self) -> None:
        providers = get_doc_type_providers()
        for dt in DocType:
            assert dt.value in providers, f"No provider for {dt}"

    def test_providers_are_valid_sources(self) -> None:
        registry = get_registry()
        for dt, source_names in get_doc_type_providers().items():
            for name in source_names:
                assert name in registry, (
                    f"Provider '{name}' for {dt} not in registry"
                )


class TestPreferredProviders:
    """Verify the preferred-provider map."""

    def test_every_doc_type_has_preferred(self) -> None:
        preferred = get_preferred_providers()
        for dt in DocType:
            assert dt.value in preferred, f"No preferred provider for {dt}"

    def test_riksdagen_preferred_for_overlap_types(self) -> None:
        preferred = get_preferred_providers()
        for dt in (DocType.PROP, DocType.SOU, DocType.DIR, DocType.SKR):
            assert preferred[dt.value] == "riksdagen", (
                f"Expected riksdagen as preferred for {dt}, got {preferred[dt.value]}"
            )

    def test_sole_provider_auto_preferred(self) -> None:
        """Doc types with only one provider should be auto-preferred."""
        providers = get_doc_type_providers()
        preferred = get_preferred_providers()
        for dt, sources in providers.items():
            if len(sources) == 1:
                assert preferred[dt] == sources[0], (
                    f"Sole provider {sources[0]} for {dt} not preferred"
                )


class TestCollectorAttributes:
    """Verify collectors have required class attributes."""

    def test_all_have_supported_doc_types(self) -> None:
        for name, cls in get_registry().items():
            assert len(cls.supported_doc_types) > 0, (
                f"Collector {name} has no supported_doc_types"
            )

    def test_preferred_for_is_subset_of_supported(self) -> None:
        for name, cls in get_registry().items():
            for dt in cls.preferred_for:
                assert dt in cls.supported_doc_types, (
                    f"{name} declares preferred_for={dt} but "
                    f"does not list it in supported_doc_types"
                )
