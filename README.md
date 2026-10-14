# FlowScope — Application-Aware SDN Traffic Engineering

FlowScope is a backend-first prototype for application-aware traffic engineering in Software-Defined Networks. The browser dashboard is intentionally thin: the Python backend owns classification, telemetry processing, NSGA-II optimization, route-rule planning, and decision recording.

## Evaluation scope

This version is a **synthetic-network controller prototype**. Each simulation run generates new background link load and flow demand, then produces controller-ready forwarding-rule intents. It does not claim that rules have been installed on Mininet or that the displayed values are physical measurements.

## Backend architecture

```text
five-tuple flow metadata
        │
        ▼
classifier.py ──► traffic class
        │
telemetry / port counters ──► monitor.py ──► link state
        │                                      │
        └──────────────────────────────────────▼
                                optimizer.py (NSGA-II)
                                           │
                                           ▼
                         controller.py (OpenFlow rule intents)
                                           │
                             storage.py (JSONL decision evidence)
                                           │
                                           ▼
                         api.py ──► minimal dashboard
```

## Implemented backend modules

| Module | Responsibility |
| --- | --- |
| `flowscope/classifier.py` | Payload-independent classification from protocol and destination-port rules. |
| `flowscope/topology.py` | Six-switch topology, paths, capacities, delays, ports, and current link state. |
| `flowscope/monitor.py` | Counter-delta utilization calculation with EWMA smoothing and stale-sample detection. |
| `flowscope/optimizer.py` | NSGA-II route-assignment optimizer. It uses the documented per-class weights for delay, utilization, loss, and hop count, then applies dominance sorting, crowding distance, tournament selection, crossover, mutation, and elitist survivor selection. |
| `flowscope/controller.py` | Controller-ready per-switch OpenFlow forwarding-rule intents. |
| `flowscope/service.py` | The orchestration layer that connects every component and records decisions. |
| `flowscope/api.py` | Dependency-free REST API and static-file server. |
| `flowscope/storage.py` | Append-only JSONL experiment-decision storage. |

## Run the backend demo

No third-party Python packages are required.

```powershell
python -m flowscope.cli demo
```

This starts one deterministic synthetic run and prints the baseline, selected NSGA-II plan, Pareto-front count, predicted metrics, and controller-ready flow rules.

## Run the dashboard

```powershell
python -m flowscope.cli serve
```

Open `http://127.0.0.1:8000`. The dashboard calls:

- `GET /api/health`
- `GET /api/state`
- `POST /api/simulate`

The simulation endpoint generates a fresh synthetic network state, runs the Python NSGA-II backend, and records the generated decision under `results/routing-decisions.jsonl`.

## Automated checks

```powershell
python -m unittest discover -v
```

The tests cover five-tuple classification, telemetry smoothing, optimizer output, forwarding-rule generation, and result persistence.

## Tomorrow's code walkthrough

1. Start with `flowscope/service.py`: it shows the complete request-to-decision pipeline.
2. Open `flowscope/optimizer.py`: explain individuals, the three class objectives, non-dominated sorting, crowding distance, mutation, and survivor selection.
3. Show `flowscope/controller.py`: the selected route becomes concrete per-switch rule intents.
4. Run `python -m flowscope.cli demo` and point to the generated JSON decision and rule plan.
5. Open the dashboard only as a lightweight operator view of the backend response.

## Final integration work

The next phase is deliberately reserved for real controller integration: connect `LinkMonitor` to OpenFlow port statistics, translate `FlowRule` intents into Ryu flow-mod messages, run the topology in Mininet, collect measured latency/jitter/loss/goodput, and compare repeated baseline and NSGA-II trials.
"# Flowscope" 
