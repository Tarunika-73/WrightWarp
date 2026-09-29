import pytest

from app.collection.rate_limiter import RateLimiter


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class RecordingSleeper:
    def __init__(self, clock: FakeClock) -> None:
        self.clock = clock
        self.calls: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)
        self.clock.advance(seconds)


@pytest.mark.asyncio
async def test_first_call_never_waits():
    clock = FakeClock()
    sleeper = RecordingSleeper(clock)
    limiter = RateLimiter(clock=clock, sleep=sleeper)

    waited = await limiter.acquire("MOCK", requests_per_minute=60)

    assert waited == 0.0
    assert sleeper.calls == []


@pytest.mark.asyncio
async def test_second_call_waits_for_min_interval():
    clock = FakeClock()
    sleeper = RecordingSleeper(clock)
    limiter = RateLimiter(clock=clock, sleep=sleeper)

    await limiter.acquire("MOCK", requests_per_minute=60)  # min interval = 1s
    waited = await limiter.acquire("MOCK", requests_per_minute=60)

    assert waited == pytest.approx(1.0)
    assert sleeper.calls == [pytest.approx(1.0)]


@pytest.mark.asyncio
async def test_no_wait_if_enough_time_already_elapsed():
    clock = FakeClock()
    sleeper = RecordingSleeper(clock)
    limiter = RateLimiter(clock=clock, sleep=sleeper)

    await limiter.acquire("MOCK", requests_per_minute=60)  # min interval = 1s
    clock.advance(5.0)
    waited = await limiter.acquire("MOCK", requests_per_minute=60)

    assert waited == 0.0
    assert sleeper.calls == []


@pytest.mark.asyncio
async def test_sources_are_rate_limited_independently():
    clock = FakeClock()
    sleeper = RecordingSleeper(clock)
    limiter = RateLimiter(clock=clock, sleep=sleeper)

    await limiter.acquire("MOCK", requests_per_minute=60)
    waited = await limiter.acquire("OTHER", requests_per_minute=60)

    assert waited == 0.0


@pytest.mark.asyncio
async def test_zero_or_negative_rate_rejected():
    limiter = RateLimiter()
    with pytest.raises(ValueError):
        await limiter.acquire("MOCK", requests_per_minute=0)
