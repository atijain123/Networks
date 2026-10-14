from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class TrafficClass(StrEnum):
    INTERACTIVE = "interactive"
    STREAMING = "streaming"
    BULK = "bulk"


@dataclass(frozen=True)
class FlowKey:
    src_ip: str
    dst_ip: str
    protocol: str
    src_port: int
    dst_port: int

    @property
    def value(self) -> str:
        return f"{self.src_ip}:{self.src_port}>{self.dst_ip}:{self.dst_port}/{self.protocol.lower()}"


@dataclass(frozen=True)
class FlowSpec:
    flow_id: str
    key: FlowKey
    traffic_class: TrafficClass
    demand_mbps: float
    label: str


@dataclass(frozen=True)
class LinkSpec:
    link_id: str
    source: str
    target: str
    capacity_mbps: float
    delay_ms: float
    source_port: int
    target_port: int


@dataclass
class LinkState:
    link_id: str
    utilization: float = 0.0
    loss_pct: float = 0.0
    healthy: bool = True
    stale: bool = False


@dataclass(frozen=True)
class Path:
    path_id: str
    switches: tuple[str, ...]
    link_ids: tuple[str, ...]


@dataclass(frozen=True)
class PathAssignment:
    flow_id: str
    path_id: str


@dataclass
class FlowMetrics:
    delay_ms: float
    jitter_ms: float
    loss_pct: float
    goodput_mbps: float
    path_utilization_pct: float


@dataclass
class CandidateEvaluation:
    assignments: tuple[PathAssignment, ...]
    objectives: tuple[float, float, float]
    flow_metrics: dict[str, FlowMetrics]
    predicted_utilization: dict[str, float]
    rank: int = 0
    crowding_distance: float = 0.0

    @property
    def key(self) -> tuple[str, ...]:
        return tuple(assignment.path_id for assignment in self.assignments)


@dataclass(frozen=True)
class FlowRule:
    switch: str
    in_port: int
    out_port: int
    match: dict[str, Any]
    priority: int = 200


@dataclass
class RoutingDecision:
    decision_id: str
    policy: str
    assignments: tuple[PathAssignment, ...]
    objectives: tuple[float, float, float]
    rules: dict[str, list[FlowRule]]
    reason: str


def to_dict(value: Any) -> Any:
    """Convert FlowScope records into JSON-safe primitives."""
    if isinstance(value, StrEnum):
        return value.value
    if hasattr(value, "__dataclass_fields__"):
        return {key: to_dict(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): to_dict(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [to_dict(item) for item in value]
    return value
