import time
from collections import defaultdict, deque


class SlidingWindowLimiter:
    """Per-user request limit over a sliding window.

    State lives in the process, so with several API instances each enforces its own budget;
    move it to Redis if a strict global limit is needed.
    """

    def __init__(self, limit: int, window_seconds: float = 60.0) -> None:
        self._limit = limit
        self._window = window_seconds
        self._calls: defaultdict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str) -> float | None:
        """Record a call. Returns None if allowed, else the seconds until the next slot."""
        now = time.monotonic()
        calls = self._calls[key]
        while calls and now - calls[0] >= self._window:
            calls.popleft()
        if len(calls) >= self._limit:
            return self._window - (now - calls[0])
        calls.append(now)
        return None
