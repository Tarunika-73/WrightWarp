"""Maps a ``source_id`` to an actual adapter instance.

Separate from ``app.core.sources`` (the static compliance/config registry):
that module answers "what sources do we know about and are they cleared
to run", this module answers "if one is cleared, which Python object
actually implements it". A source can exist in ``app.core.sources`` with
no entry here at all (e.g. every ``PENDING_REVIEW`` airline/OTA) - the
absence is exactly what keeps them from running.
"""
from app.collection.adapters.base import SourceAdapter
from app.collection.adapters.mock import MockSourceAdapter


class AdapterRegistry:
    def __init__(self) -> None:
        self._adapters: dict[str, SourceAdapter] = {}

    def register(self, adapter: SourceAdapter) -> None:
        self._adapters[adapter.source_id] = adapter

    def get(self, source_id: str) -> SourceAdapter | None:
        return self._adapters.get(source_id)

    def is_registered(self, source_id: str) -> bool:
        return source_id in self._adapters


adapter_registry = AdapterRegistry()
adapter_registry.register(MockSourceAdapter())
