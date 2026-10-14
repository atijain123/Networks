const labels = { "voice-01": ["Voice / interactive", "voice"], "video-01": ["Video streaming", "stream"], "bulk-01": ["Bulk transfer", "bulk"] };
const routePoints = { upper: "126,135 260,54 440,54 574,135", lower: "126,135 260,216 440,216 574,135", cross: "126,135 260,216 440,54 574,135", hot: "126,135 260,54 440,216 574,135" };
let initialState;

function pathText(pathId) { return { upper: "s1 → s2 → s4 → s6", lower: "s1 → s3 → s5 → s6", cross: "s1 → s3 → s4 → s6", hot: "s1 → s2 → s5 → s6" }[pathId]; }
function flowRows(evaluation) {
  const assignments = Object.fromEntries(evaluation.assignments.map(item => [item.flow_id, item.path_id]));
  return Object.entries(evaluation.flow_metrics).map(([flowId, metric]) => {
    const [name, color] = labels[flowId]; const pathId = assignments[flowId];
    const primary = flowId === "voice-01" ? `${metric.delay_ms.toFixed(1)} ms` : flowId === "video-01" ? `${metric.loss_pct.toFixed(1)}% loss` : `${metric.goodput_mbps.toFixed(1)} Mbps`;
    return `<div class="flow-row"><div class="flow-name"><i class="small-dot ${color}"></i><div>${name}<span>${flowId === "bulk-01" ? "TCP" : "UDP"}</span></div></div><div class="flow-path">${pathText(pathId)}</div><div class="flow-stat"><b>${primary}</b>${metric.path_utilization_pct.toFixed(0)}% path load</div></div>`;
  }).join("");
}
function showTopology(evaluation, scenario = null) {
  const scenarioLinks = scenario?.congested_links || [];
  const backgroundLoads = scenario?.background_load_pct || {};
  const details = scenarioLinks.map(link => `${link}: ${backgroundLoads[link].toFixed(0)}%`).join(", ");
  document.querySelector("#bottleneck").textContent = scenarioLinks.length ? `Scenario load: ${details}` : "Scenario link: pending";
  document.querySelectorAll("[data-link]").forEach(link => link.classList.toggle("hot-link", scenarioLinks.includes(link.dataset.link)));
  const routeIds = [...new Set(evaluation.assignments.map(item => item.path_id))];
  document.querySelector("#routeOverlay").innerHTML = routeIds.map(route => `<polyline class="route-line" points="${routePoints[route]}"/>`).join("");
}
function percentageChange(before, after, higherIsBetter) {
  if (before === 0) return "—";
  const change = (after - before) / before * 100;
  const improved = higherIsBetter ? change > 0 : change < 0;
  return `<span class="${improved ? "improved" : change === 0 ? "neutral" : "declined"}">${change > 0 ? "+" : ""}${change.toFixed(0)}%</span>`;
}
function comparisonRows(baseline, selected) {
  const rows = [
    ["Voice delay", `${baseline.flow_metrics["voice-01"].delay_ms.toFixed(1)} ms`, `${selected.flow_metrics["voice-01"].delay_ms.toFixed(1)} ms`, percentageChange(baseline.flow_metrics["voice-01"].delay_ms, selected.flow_metrics["voice-01"].delay_ms, false)],
    ["Video loss", `${baseline.flow_metrics["video-01"].loss_pct.toFixed(1)}%`, `${selected.flow_metrics["video-01"].loss_pct.toFixed(1)}%`, percentageChange(baseline.flow_metrics["video-01"].loss_pct, selected.flow_metrics["video-01"].loss_pct, false)],
    ["Bulk goodput", `${baseline.flow_metrics["bulk-01"].goodput_mbps.toFixed(1)} Mbps`, `${selected.flow_metrics["bulk-01"].goodput_mbps.toFixed(1)} Mbps`, percentageChange(baseline.flow_metrics["bulk-01"].goodput_mbps, selected.flow_metrics["bulk-01"].goodput_mbps, true)],
    ["Assigned-path peak load", `${baseline.assigned_path_peak_utilization_pct.toFixed(0)}%`, `${selected.assigned_path_peak_utilization_pct.toFixed(0)}%`, percentageChange(baseline.assigned_path_peak_utilization_pct, selected.assigned_path_peak_utilization_pct, false)],
  ];
  return `<div class="table-header"><span>Metric</span><span>Baseline</span><span>NSGA-II</span><span>Change</span></div>${rows.map(row => `<div class="comparison-row"><span>${row[0]}</span><span>${row[1]}</span><span>${row[2]}</span><span>${row[3]}</span></div>`).join("")}`;
}
function setInitial(state) {
  document.querySelector("#simulationRun").textContent = "Not started";
  document.querySelector("#scenarioProfile").textContent = "—";
  document.querySelector("#scenarioLinks").textContent = "";
  document.querySelector("#scenarioName").textContent = "Ready for a simulation run";
  document.querySelector("#generation").textContent = "—";
  document.querySelector("#paretoCount").textContent = "—";
  document.querySelector("#comparisonStatus").textContent = "—";
  document.querySelector("#progress").style.width = "0%";
  document.querySelector("#searchCaption").textContent = "Ready to run.";
  document.querySelector("#baselineFlowTable").innerHTML = flowRows(state.baseline);
  document.querySelector("#nsgaFlowTable").innerHTML = `<div class="empty-row">Run a simulation.</div>`;
  document.querySelector("#comparisonTable").innerHTML = `<div class="table-header"><span>Metric</span><span>Baseline</span><span>NSGA-II</span><span>Change</span></div><div class="empty-row">Run a simulation to compare results.</div>`;
  showTopology(state.baseline);
}
function setResult(response) {
  const { baseline, selected, pareto_count, algorithm, simulation } = response;
  document.querySelector("#baselineFlowTable").innerHTML = flowRows(baseline);
  document.querySelector("#nsgaFlowTable").innerHTML = flowRows(selected);
  document.querySelector("#comparisonTable").innerHTML = comparisonRows(baseline, selected);
  document.querySelector("#paretoCount").textContent = `Pareto plans: ${pareto_count}`;
  document.querySelector("#simulationRun").textContent = `Run ${simulation.run_number}`;
  document.querySelector("#scenarioProfile").textContent = simulation.profile;
  const scenarioDetails = simulation.congested_links.map(link => `${link} (${simulation.background_load_pct[link].toFixed(0)}%)`).join(", ");
  document.querySelector("#scenarioLinks").textContent = `High background load: ${scenarioDetails}`;
  document.querySelector("#scenarioName").textContent = `Synthetic scenario · ${simulation.profile}`;
  document.querySelector("#generation").textContent = `${algorithm.generations} / ${algorithm.generations}`;
  document.querySelector("#comparisonStatus").textContent = "Same input conditions";
  document.querySelector("#progress").style.width = "100%";
  document.querySelector("#searchCaption").textContent = "Simulation complete";
  showTopology(selected, simulation);
}
async function runSimulation() {
  const button = document.querySelector("#runButton");
  button.disabled = true; button.textContent = "Running simulation…";
  document.querySelector("#generation").textContent = "0 / 48";
  document.querySelector("#progress").style.width = "12%";
  document.querySelector("#searchCaption").textContent = "Running same-condition comparison";
  try {
    const response = await fetch("/api/simulate", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
    if (!response.ok) throw new Error("Simulation request failed");
    setResult(await response.json());
  } catch {
    document.querySelector("#searchCaption").textContent = "Start the local service";
  } finally {
    button.disabled = false; button.textContent = "Run simulation";
  }
}
async function initialize() {
  try {
    const response = await fetch("/api/reset", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
    if (!response.ok) throw new Error();
    initialState = await response.json(); setInitial(initialState);
  } catch { document.querySelector("#searchCaption").textContent = "Start the local service"; }
}
document.querySelector("#runButton").addEventListener("click", runSimulation);
document.querySelector("#resetButton").addEventListener("click", initialize);
initialize();
