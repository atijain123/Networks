from __future__ import annotations

from .models import FlowRule, FlowSpec, PathAssignment
from .topology import Topology


class RulePlanner:
    """Builds controller-ready OpenFlow rule intents without touching a switch."""

    def __init__(self, topology: Topology):
        self.topology = topology

    def plan(self, flows: list[FlowSpec], assignments: tuple[PathAssignment, ...]) -> dict[str, list[FlowRule]]:
        rules: dict[str, list[FlowRule]] = {}
        flow_by_id = {flow.flow_id: flow for flow in flows}
        for assignment in assignments:
            flow = flow_by_id[assignment.flow_id]
            path = self.topology.path(assignment.path_id)
            match = {
                "ipv4_src": flow.key.src_ip,
                "ipv4_dst": flow.key.dst_ip,
                "ip_proto": flow.key.protocol.lower(),
                "tp_src": flow.key.src_port,
                "tp_dst": flow.key.dst_port,
            }
            # Host ports are deliberately explicit; Ryu integration only needs to translate these intents.
            for index, switch in enumerate(path.switches):
                if index == 0:
                    in_port = 1
                    out_port = self.topology.links[path.link_ids[index]].source_port
                elif index == len(path.switches) - 1:
                    previous = self.topology.links[path.link_ids[index - 1]]
                    in_port, out_port = previous.target_port, 1
                else:
                    previous = self.topology.links[path.link_ids[index - 1]]
                    following = self.topology.links[path.link_ids[index]]
                    in_port, out_port = previous.target_port, following.source_port
                rules.setdefault(switch, []).append(FlowRule(switch, in_port, out_port, match))
        return rules
