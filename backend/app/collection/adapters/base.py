"""The one interface every source (airline or OTA) must implement.

Kept deliberately small: an adapter's only job is "given a
``CollectionRequest``, go find fares and hand back raw findings." It must
never touch the database directly - persistence is ``CollectionRepository``'s
job, and coordination (compliance checks, rate limiting, retries) is
``CollectionService``'s job. This separation is what lets Phase 2 add a
second, third, tenth source without rewriting anything above this layer.
"""
from abc import ABC, abstractmethod

from app.schemas.collection import AdapterSearchOutcome, CollectionRequest


class SourceAdapter(ABC):
    @property
    @abstractmethod
    def source_id(self) -> str:
        """The registry ``source_id`` (app.core.sources) this adapter serves."""

    @abstractmethod
    async def search(self, request: CollectionRequest) -> AdapterSearchOutcome:
        """Search this source for the given request and return raw findings.

        Implementations should raise ``app.collection.errors.CollectionException``
        (never a bare/unstructured exception) for anything that should be
        classified into a ``CollectionErrorType`` by the caller.
        """

    async def startup(self) -> None:
        """Optional one-time setup (e.g. warm a browser context). No-op by default."""

    async def shutdown(self) -> None:
        """Optional teardown (e.g. close a browser context). No-op by default."""
