from __future__ import annotations

from dataclasses import dataclass

from .models import FlowKey, TrafficClass


@dataclass(frozen=True)
class ClassificationRule:
    traffic_class: TrafficClass
    protocol: str | None = None
    destination_port: int | None = None

    def matches(self, flow: FlowKey) -> bool:
        return (
            (self.protocol is None or flow.protocol.lower() == self.protocol.lower())
            and (self.destination_port is None or flow.dst_port == self.destination_port)
        )


class FlowClassifier:
    """Classifies five-tuples without reading application payload bytes."""

    def __init__(self, rules: list[ClassificationRule], default: TrafficClass = TrafficClass.BULK):
        self._rules = rules
        self._default = default

    def classify(self, flow: FlowKey) -> TrafficClass:
        for rule in self._rules:
            if rule.matches(flow):
                return rule.traffic_class
        return self._default


def default_classifier() -> FlowClassifier:
    return FlowClassifier(
        [
            ClassificationRule(TrafficClass.INTERACTIVE, protocol="udp", destination_port=5004),
            ClassificationRule(TrafficClass.STREAMING, protocol="udp", destination_port=5005),
            ClassificationRule(TrafficClass.BULK, protocol="tcp", destination_port=5201),
        ]
    )
