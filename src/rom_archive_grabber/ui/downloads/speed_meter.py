from collections import deque

# Long enough to smooth out bursty progress, short enough to follow a change.
WINDOW_SECONDS = 2.0


class SpeedMeter:
    """Download speed in bytes per second over the last `WINDOW_SECONDS`."""

    def __init__(self) -> None:
        self._samples: deque[tuple[float, int]] = deque()

    def add(self, now: float, bytes_done: int) -> None:
        # Fewer bytes than before means the download started over.
        if self._samples and bytes_done < self._samples[-1][1]:
            self._samples.clear()
        self._samples.append((now, bytes_done))
        while now - self._samples[0][0] > WINDOW_SECONDS:
            self._samples.popleft()

    def reset(self) -> None:
        self._samples.clear()

    def rate(self) -> float | None:
        """Bytes per second, or None until two samples apart in time exist."""
        if len(self._samples) < 2:  # noqa: PLR2004 - a rate needs two points
            return None
        (start, first), (end, last) = self._samples[0], self._samples[-1]
        return None if end <= start else (last - first) / (end - start)
