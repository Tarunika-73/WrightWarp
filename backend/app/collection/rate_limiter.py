"""Conservative, per-source async rate limiting.

Goal is responsible collection, not throughput: each source gets its own
minimum spacing between requests, derived from
``SourceDefinition.rate_limit_per_minute``. There is no burst allowance
and no cross-source sharing - a slow source cannot be sped up by borrowing
another source's budget, and a fast one cannot starve others since each
has an independent lock.
"""
import asyncio
import time
from collections.abc import Awaitable, Callable


class RateLimiter:
    """Enforces a minimum delay between consecutive requests to the same source.

    ``clock`` and ``sleep`` are injectable so tests can assert on the
    computed delay without actually waiting real wall-clock time.
    """

    def __init__(
        self,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._clock = clock
        self._sleep = sleep
        self._locks: dict[str, asyncio.Lock] = {}
        self._last_call_at: dict[str, float] = {}

    def _lock_for(self, source_id: str) -> asyncio.Lock:
        lock = self._locks.get(source_id)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[source_id] = lock
        return lock

    async def acquire(self, source_id: str, requests_per_minute: float) -> float:
        """Block until it is safe to issue the next request for ``source_id``.

        Returns the number of seconds actually waited (0.0 if no wait was
        needed), which is what tests assert against.
        """
        if requests_per_minute <= 0:
            raise ValueError("requests_per_minute must be positive")
        min_interval = 60.0 / requests_per_minute

        async with self._lock_for(source_id):
            now = self._clock()
            last = self._last_call_at.get(source_id)
            waited = 0.0
            if last is not None:
                elapsed = now - last
                remaining = min_interval - elapsed
                if remaining > 0:
                    await self._sleep(remaining)
                    waited = remaining
            self._last_call_at[source_id] = self._clock()
            return waited
