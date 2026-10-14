from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import random
from threading import RLock
from uuid import uuid4

from .classifier import default_classifier
from .controller import RulePlanner
from .models import FlowKey, FlowSpec, RoutingDecision, TrafficClass, to_dict
from .optimizer import NSGA2RouteOptimizer
from .storage import JsonResultStore
from .topology import Topology, default_topology


class FlowScopeService:
    """Orchestrates classification, optimization, rule planning, and result recording."""

    def __init__(self, results_path: Path | None = None, topology: Topology | None = None):
        self.topology = topology or default_topology()
        self.classifier = default_classifier()
        self.rule_planner = RulePlanner(self.topology)
        self.store = JsonResultStore(results_path or Path("results") / "routing-decisions.jsonl")
        self._lock = RLock()
        self.flows = self._scenario_flows()
        self._simulation_number = 0
        self._last_simulation: dict | None = None

    def baseline(self):
        paths = tuple(self._shortest_path_id() for _ in self.flows)
        optimizer = NSGA2RouteOptimizer(self.topology)
        return optimizer._evaluate(self.flows, paths)

    def optimize(self, seed: int = 20261013) -> dict:
        with self._lock:
            return self._optimize_locked(seed)

    def simulate(self, seed: int | None = None) -> dict:
        """Generate a new synthetic network state, then run the full controller pipeline."""
        with self._lock:
            simulation_seed = seed if seed is not None else random.SystemRandom().randrange(1, 2**31)
            generator = random.Random(simulation_seed)
            self._simulation_number += 1
            profile_name, congested_links = generator.choice(
                [
                    ("Diagonal route", ("s2-s5",)),
                    ("Upper corridor", ("s1-s2", "s2-s4")),
                    ("Lower corridor", ("s3-s5", "s5-s6")),
                    ("Cross link", ("s3-s4",)),
                ]
            )
            for link_id, state in self.topology.link_state.items():
                if link_id in congested_links:
                    state.utilization = generator.uniform(.72, .92)
                else:
                    state.utilization = generator.uniform(.06, .38)
                state.loss_pct = max(0.0, (state.utilization - .72) * 8)
                state.stale = False
            self.flows = self._scenario_flows(generator)
            self._last_simulation = {
                "run_number": self._simulation_number,
                "seed": simulation_seed,
                "profile": profile_name,
                "congested_links": list(congested_links),
                "background_load_pct": {
                    link_id: round(self.topology.link_state[link_id].utilization * 100, 1)
                    for link_id in congested_links
                },
                "started_at": datetime.now(UTC).isoformat(),
            }
            response = self._optimize_locked(simulation_seed)
            response["simulation"] = self._last_simulation
            return response

    def state(self) -> dict:
        baseline = self.baseline()
        return {
            "source": "simulation",
            "controller": "planning-only",
            "simulation": self._last_simulation,
            "flows": [to_dict(flow) for flow in self.flows],
            "links": [
                {
                    "link_id": link_id,
                    "utilization_pct": round(state.utilization * 100, 1),
                    "healthy": state.healthy,
                    "stale": state.stale,
                }
                for link_id, state in self.topology.link_state.items()
            ],
            "baseline": self._evaluation_payload(baseline),
            "recent_decisions": self.store.recent(8),
        }

    def reset(self) -> dict:
        """Return the demonstration to its clean, pre-simulation state."""
        with self._lock:
            self.topology = default_topology()
            self.rule_planner = RulePlanner(self.topology)
            self.flows = self._scenario_flows()
            self._simulation_number = 0
            self._last_simulation = None
            return self.state()

    def _optimize_locked(self, seed: int) -> dict:
        baseline = self.baseline()
        optimizer = NSGA2RouteOptimizer(self.topology, seed=seed)
        selected, pareto_front = optimizer.optimize(self.flows, seed_assignment=baseline.key)
        rules = self.rule_planner.plan(self.flows, selected.assignments)
        decision = RoutingDecision(
            decision_id=str(uuid4()),
            policy="nsga-ii",
            assignments=selected.assignments,
            objectives=selected.objectives,
            rules=rules,
            reason="Selected from the non-dominated route-assignment set using the configured class policy.",
        )
        response = {
            "source": "synthetic-simulation",
            "algorithm": {"name": "NSGA-II", "population_size": optimizer.population_size, "generations": optimizer.generations},
            "baseline": self._evaluation_payload(baseline),
            "selected": self._evaluation_payload(selected),
            "pareto_count": len(pareto_front),
            "pareto_objectives": [list(candidate.objectives) for candidate in pareto_front],
            "decision": to_dict(decision),
            "generated_at": datetime.now(UTC).isoformat(),
        }
        self.store.append(response)
        return response

    def _evaluation_payload(self, evaluation) -> dict:
        assigned_paths = [self.topology.path(assignment.path_id) for assignment in evaluation.assignments]
        assigned_link_ids = {link_id for path in assigned_paths for link_id in path.link_ids}
        return {
            "assignments": [to_dict(assignment) for assignment in evaluation.assignments],
            "objectives": [round(value, 3) for value in evaluation.objectives],
            "flow_metrics": {flow_id: to_dict(metrics) for flow_id, metrics in evaluation.flow_metrics.items()},
            "predicted_utilization_pct": {link_id: round(value * 100, 1) for link_id, value in evaluation.predicted_utilization.items()},
            "peak_utilization_pct": round(max(evaluation.predicted_utilization.values()) * 100, 1),
            "assigned_path_peak_utilization_pct": round(max(evaluation.predicted_utilization[link_id] for link_id in assigned_link_ids) * 100, 1),
        }

    def _shortest_path_id(self) -> str:
        return min(
            self.topology.valid_paths(),
            key=lambda path: sum(self.topology.links[link_id].delay_ms for link_id in path.link_ids),
        ).path_id

    def _scenario_flows(self, generator: random.Random | None = None) -> list[FlowSpec]:
        generator = generator or random.Random(20261013)
        raw = [
            ("voice-01", "Voice / interactive", "10.0.0.1", "10.0.0.6", "udp", 5004, generator.uniform(5, 14)),
            ("video-01", "Video streaming", "10.0.0.2", "10.0.0.6", "udp", 5005, generator.uniform(10, 32)),
            ("bulk-01", "Bulk transfer", "10.0.0.3", "10.0.0.6", "tcp", 5201, generator.uniform(24, 55)),
        ]
        flows = []
        for flow_id, label, source, destination, protocol, destination_port, demand in raw:
            key = FlowKey(source, destination, protocol, 40000 + len(flows), destination_port)
            flows.append(FlowSpec(flow_id, key, self.classifier.classify(key), demand, label))
        return flows
