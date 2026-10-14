from __future__ import annotations

from dataclasses import dataclass

from .models import LinkState


@dataclass
class CounterSample:
    tx_bytes: int
    timestamp_s: float


class LinkMonitor:
    """Converts OpenFlow port-counter samples into smoothed link utilization."""

    def __init__(self, smoothing: float = .4):
        self._smoothing = smoothing
        self._previous: dict[str, CounterSample] = {}

    def observe(self, link: LinkState, capacity_mbps: float, sample: CounterSample) -> LinkState:
        previous = self._previous.get(link.link_id)
        self._previous[link.link_id] = sample
        if previous is None or sample.timestamp_s <= previous.timestamp_s or sample.tx_bytes < previous.tx_bytes:
            link.stale = previous is not None
            return link
        bits_per_second = 8 * (sample.tx_bytes - previous.tx_bytes) / (sample.timestamp_s - previous.timestamp_s)
        raw = max(0.0, min(1.0, bits_per_second / (capacity_mbps * 1_000_000)))
        link.utilization = self._smoothing * raw + (1 - self._smoothing) * link.utilization
        link.stale = False
        return link
