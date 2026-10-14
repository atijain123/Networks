from __future__ import annotations

import unittest
from pathlib import Path

from flowscope.classifier import default_classifier
from flowscope.models import FlowKey, LinkState, TrafficClass
from flowscope.monitor import CounterSample, LinkMonitor
from flowscope.service import FlowScopeService
from flowscope.optimizer import NSGA2RouteOptimizer


class FlowScopeBackendTests(unittest.TestCase):
    def test_classifier_uses_five_tuple_metadata_not_payload(self):
        classifier = default_classifier()
        voice = FlowKey("10.0.0.1", "10.0.0.6", "udp", 41000, 5004)
        unknown = FlowKey("10.0.0.1", "10.0.0.6", "tcp", 41000, 443)
        self.assertEqual(classifier.classify(voice), TrafficClass.INTERACTIVE)
        self.assertEqual(classifier.classify(unknown), TrafficClass.BULK)

    def test_counter_monitor_smooths_new_utilization_sample(self):
        monitor = LinkMonitor(smoothing=.5)
        link = LinkState("s1-s2", utilization=.2)
        monitor.observe(link, 100, CounterSample(tx_bytes=0, timestamp_s=0))
        monitor.observe(link, 100, CounterSample(tx_bytes=12_500_000, timestamp_s=1))
        self.assertAlmostEqual(link.utilization, .6)
        self.assertFalse(link.stale)

    def test_optimizer_uses_the_documented_class_weights(self):
        self.assertEqual(NSGA2RouteOptimizer.CLASS_WEIGHTS[TrafficClass.INTERACTIVE], (.45, .25, .25, .05))
        self.assertEqual(NSGA2RouteOptimizer.CLASS_WEIGHTS[TrafficClass.STREAMING], (.25, .35, .25, .15))
        self.assertEqual(NSGA2RouteOptimizer.CLASS_WEIGHTS[TrafficClass.BULK], (.10, .60, .10, .20))

    def test_optimizer_returns_assignment_and_controller_rules(self):
        service = FlowScopeService(Path("results") / "test-optimizer-decisions.jsonl")
        result = service.optimize()
        selected_routes = {item["flow_id"]: item["path_id"] for item in result["selected"]["assignments"]}
        self.assertEqual(result["algorithm"]["name"], "NSGA-II")
        self.assertEqual(set(selected_routes), {"voice-01", "video-01", "bulk-01"})
        self.assertNotIn("hot", selected_routes.values())
        self.assertIn("s1", result["decision"]["rules"])
        self.assertGreater(result["selected"]["flow_metrics"]["voice-01"]["goodput_mbps"], 0)

    def test_result_store_records_decision_evidence(self):
        result_path = Path("results") / "test-store-decisions.jsonl"
        service = FlowScopeService(result_path)
        previous_count = len(service.store.recent(100))
        service.optimize()
        self.assertTrue(result_path.exists())
        self.assertEqual(len(service.store.recent(100)), previous_count + 1)

    def test_simulation_generates_a_new_network_run(self):
        service = FlowScopeService(Path("results") / "test-simulation-decisions.jsonl")
        result = service.simulate(seed=8675309)
        self.assertEqual(result["source"], "synthetic-simulation")
        self.assertEqual(result["simulation"]["run_number"], 1)
        self.assertGreater(result["simulation"]["seed"], 0)
        self.assertEqual(set(result["simulation"]["background_load_pct"]), set(result["simulation"]["congested_links"]))
        self.assertEqual(len(result["selected"]["assignments"]), 3)
        service.reset()
        self.assertEqual(service.simulate(seed=8675309)["simulation"]["run_number"], 1)


if __name__ == "__main__":
    unittest.main()
