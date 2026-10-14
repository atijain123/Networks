from __future__ import annotations

from dataclasses import dataclass

from .models import LinkSpec, LinkState, Path


@dataclass
class Topology:
    links: dict[str, LinkSpec]
    paths: dict[str, Path]
    link_state: dict[str, LinkState]

    def path(self, path_id: str) -> Path:
        return self.paths[path_id]

    def valid_paths(self) -> list[Path]:
        return [path for path in self.paths.values() if all(self.link_state[link_id].healthy for link_id in path.link_ids)]


def default_topology() -> Topology:
    # Ports model the exact information the OpenFlow rule planner needs later.
    links = {
        "s1-s2": LinkSpec("s1-s2", "s1", "s2", 100, 4, 2, 1),
        "s2-s4": LinkSpec("s2-s4", "s2", "s4", 100, 4, 2, 1),
        "s4-s6": LinkSpec("s4-s6", "s4", "s6", 100, 5, 2, 1),
        "s1-s3": LinkSpec("s1-s3", "s1", "s3", 100, 7, 3, 1),
        "s3-s5": LinkSpec("s3-s5", "s3", "s5", 100, 7, 2, 1),
        "s5-s6": LinkSpec("s5-s6", "s5", "s6", 100, 8, 2, 2),
        "s3-s4": LinkSpec("s3-s4", "s3", "s4", 100, 6, 3, 3),
        "s2-s5": LinkSpec("s2-s5", "s2", "s5", 70, 3, 3, 3),
    }
    paths = {
        "upper": Path("upper", ("s1", "s2", "s4", "s6"), ("s1-s2", "s2-s4", "s4-s6")),
        "lower": Path("lower", ("s1", "s3", "s5", "s6"), ("s1-s3", "s3-s5", "s5-s6")),
        "cross": Path("cross", ("s1", "s3", "s4", "s6"), ("s1-s3", "s3-s4", "s4-s6")),
        "hot": Path("hot", ("s1", "s2", "s5", "s6"), ("s1-s2", "s2-s5", "s5-s6")),
    }
    # s2-s5 begins congested; each value is a fraction, sampled by the monitor in a live deployment.
    base_utilization = {"s1-s2": .18, "s2-s4": .18, "s4-s6": .18, "s1-s3": .16, "s3-s5": .16, "s5-s6": .16, "s3-s4": .12, "s2-s5": .86}
    state = {link_id: LinkState(link_id, utilization=base_utilization[link_id]) for link_id in links}
    return Topology(links=links, paths=paths, link_state=state)
