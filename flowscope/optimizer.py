from __future__ import annotations

import random
from collections import defaultdict

from .models import CandidateEvaluation, FlowMetrics, FlowSpec, PathAssignment, TrafficClass
from .topology import Topology


class NSGA2RouteOptimizer:
    """Dependency-free NSGA-II implementation for simultaneous flow-route assignment."""

    # Exact class-specific design weights: delay, utilization, loss, hop count.
    CLASS_WEIGHTS: dict[TrafficClass, tuple[float, float, float, float]] = {
        TrafficClass.INTERACTIVE: (.45, .25, .25, .05),
        TrafficClass.STREAMING: (.25, .35, .25, .15),
        TrafficClass.BULK: (.10, .60, .10, .20),
    }
    UTILIZATION_EPSILON = .01
    UTILIZATION_SAFETY_CEILING = .95
    INFEASIBLE_PENALTY = 1_000.0

    def __init__(self, topology: Topology, population_size: int = 42, generations: int = 48, seed: int = 20261013):
        if population_size < 4:
            raise ValueError("NSGA-II needs a population of at least four")
        self.topology = topology
        self.population_size = population_size
        self.generations = generations
        self.random = random.Random(seed)
        self._max_link_delay_ms = max(link.delay_ms for link in topology.links.values())

    def optimize(self, flows: list[FlowSpec], seed_assignment: tuple[str, ...] | None = None) -> tuple[CandidateEvaluation, list[CandidateEvaluation]]:
        options = [path.path_id for path in self.topology.valid_paths()]
        if not options:
            raise RuntimeError("No valid paths are available")
        population = [self._evaluate(flows, seed_assignment)] if seed_assignment else []
        while len(population) < self.population_size:
            population.append(self._evaluate(flows, tuple(self.random.choice(options) for _ in flows)))
        for _ in range(self.generations):
            fronts = self._rank(population)
            offspring: list[CandidateEvaluation] = []
            while len(offspring) < self.population_size:
                first = self._tournament(population).key
                second = self._tournament(population).key
                child = tuple(first[index] if self.random.random() < .5 else second[index] for index in range(len(flows)))
                if self.random.random() < .28:
                    changed = self.random.randrange(len(flows))
                    child = child[:changed] + (self.random.choice(options),) + child[changed + 1:]
                offspring.append(self._evaluate(flows, child))
            population = self._survive(population + offspring)
        front = self._unique(self._rank(population)[0])
        # Each objective is already a class-specific weighted path cost from the design document.
        selected = min(front, key=lambda candidate: sum(candidate.objectives))
        return selected, front

    def _evaluate(self, flows: list[FlowSpec], genome: tuple[str, ...] | None) -> CandidateEvaluation:
        if genome is None:
            raise ValueError("A candidate must include a path for every flow")
        assignments = tuple(PathAssignment(flow.flow_id, path_id) for flow, path_id in zip(flows, genome, strict=True))
        demand_by_link: dict[str, float] = defaultdict(float)
        for flow, path_id in zip(flows, genome, strict=True):
            for link_id in self.topology.path(path_id).link_ids:
                demand_by_link[link_id] += flow.demand_mbps
        utilization = {
            link_id: self.topology.link_state[link_id].utilization + demand_by_link[link_id] / spec.capacity_mbps
            for link_id, spec in self.topology.links.items()
        }
        metrics: dict[str, FlowMetrics] = {}
        for flow, path_id in zip(flows, genome, strict=True):
            path = self.topology.path(path_id)
            link_utilization = max(utilization[link_id] for link_id in path.link_ids)
            base_delay = sum(self.topology.links[link_id].delay_ms for link_id in path.link_ids)
            queue_delay = sum(max(0.0, utilization[link_id] - .70) * 28 for link_id in path.link_ids)
            loss = max(self._link_loss_pct(link_id, utilization[link_id]) for link_id in path.link_ids)
            delivery = max(.12, 1 - max(0.0, link_utilization - .65) * .90)
            metrics[flow.flow_id] = FlowMetrics(
                delay_ms=base_delay + queue_delay,
                jitter_ms=max(0.2, queue_delay * .18),
                loss_pct=loss,
                goodput_mbps=flow.demand_mbps * delivery,
                path_utilization_pct=link_utilization * 100,
            )
        objectives = tuple(
            self._path_cost(flow, self.topology.path(path_id), utilization)
            for flow, path_id in zip(flows, genome, strict=True)
        )
        # This is the design's hard feasibility filter expressed as a constraint penalty:
        # a plan that overloads any link cannot compete with a safe alternative.
        if any(value > self.UTILIZATION_SAFETY_CEILING for value in utilization.values()):
            objectives = tuple(value + self.INFEASIBLE_PENALTY for value in objectives)
        return CandidateEvaluation(assignments, objectives, metrics, utilization)

    def _path_cost(self, flow: FlowSpec, path, utilization: dict[str, float]) -> float:
        """C_c(P) from the design document, summed once for every edge in the path."""
        delay_weight, utilization_weight, loss_weight, hop_weight = self.CLASS_WEIGHTS[flow.traffic_class]
        cost = 0.0
        for link_id in path.link_ids:
            link = self.topology.links[link_id]
            normalized_delay = link.delay_ms / self._max_link_delay_ms
            normalized_utilization = min(1.0, max(0.0, utilization[link_id]))
            congestion_penalty = normalized_utilization / (1 - normalized_utilization + self.UTILIZATION_EPSILON)
            normalized_loss = min(1.0, self._link_loss_pct(link_id, utilization[link_id]) / 100)
            cost += (
                delay_weight * normalized_delay
                + utilization_weight * congestion_penalty
                + loss_weight * normalized_loss
                + hop_weight
            )
        return cost

    def _link_loss_pct(self, link_id: str, predicted_utilization: float) -> float:
        measured_loss = self.topology.link_state[link_id].loss_pct
        congestion_loss = max(0.0, predicted_utilization - .75) * 12
        return max(measured_loss, congestion_loss)

    @staticmethod
    def _dominates(left: CandidateEvaluation, right: CandidateEvaluation) -> bool:
        return all(a <= b for a, b in zip(left.objectives, right.objectives, strict=True)) and any(a < b for a, b in zip(left.objectives, right.objectives, strict=True))

    def _rank(self, population: list[CandidateEvaluation]) -> list[list[CandidateEvaluation]]:
        dominance: dict[int, list[CandidateEvaluation]] = {}
        domination_count: dict[int, int] = {}
        first: list[CandidateEvaluation] = []
        for candidate in population:
            dominance[id(candidate)] = []
            domination_count[id(candidate)] = 0
            for other in population:
                if candidate is other:
                    continue
                if self._dominates(candidate, other):
                    dominance[id(candidate)].append(other)
                elif self._dominates(other, candidate):
                    domination_count[id(candidate)] += 1
            if domination_count[id(candidate)] == 0:
                candidate.rank = 0
                first.append(candidate)
        fronts = [first]
        rank = 0
        while fronts[rank]:
            next_front: list[CandidateEvaluation] = []
            for candidate in fronts[rank]:
                for dominated in dominance[id(candidate)]:
                    domination_count[id(dominated)] -= 1
                    if domination_count[id(dominated)] == 0:
                        dominated.rank = rank + 1
                        next_front.append(dominated)
            if next_front:
                fronts.append(next_front)
            rank += 1
            if not next_front:
                break
        for front in fronts:
            self._crowding_distance(front)
        return fronts

    @staticmethod
    def _crowding_distance(front: list[CandidateEvaluation]) -> None:
        for candidate in front:
            candidate.crowding_distance = 0.0
        for objective_index in range(3):
            front.sort(key=lambda candidate: candidate.objectives[objective_index])
            if not front:
                continue
            front[0].crowding_distance = float("inf")
            front[-1].crowding_distance = float("inf")
            low, high = front[0].objectives[objective_index], front[-1].objectives[objective_index]
            for index in range(1, len(front) - 1):
                front[index].crowding_distance += (front[index + 1].objectives[objective_index] - front[index - 1].objectives[objective_index]) / (high - low or 1)

    def _tournament(self, population: list[CandidateEvaluation]) -> CandidateEvaluation:
        first, second = self.random.sample(population, 2)
        return first if (first.rank, -first.crowding_distance) < (second.rank, -second.crowding_distance) else second

    def _survive(self, combined: list[CandidateEvaluation]) -> list[CandidateEvaluation]:
        next_generation: list[CandidateEvaluation] = []
        for front in self._rank(combined):
            if len(next_generation) + len(front) <= self.population_size:
                next_generation.extend(front)
            else:
                next_generation.extend(sorted(front, key=lambda candidate: candidate.crowding_distance, reverse=True)[: self.population_size - len(next_generation)])
                break
        return next_generation

    @staticmethod
    def _unique(front: list[CandidateEvaluation]) -> list[CandidateEvaluation]:
        unique: dict[tuple[str, ...], CandidateEvaluation] = {}
        for candidate in front:
            unique.setdefault(candidate.key, candidate)
        return list(unique.values())
