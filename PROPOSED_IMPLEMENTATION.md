# ORION Implementation Architecture

This document governs the physical pipeline, execution standards, and integration thresholds for the ORION platform. The architecture is defined by four rigid layers with explicitly defined inputs, outputs, and separations to guarantee deterministic reproducibility.

## 1. The 4-Layer Execution Architecture

### L1: Scenario Registry
A read-only structured database storing all scenario definitions defined in the ORION taxonomy. The registry evaluates all initial requests and provides the architectural base.
*   **Input**: Scenario Schema (Taxonomy mapping parameters).
*   **Output**: `ScenarioTemplate` data object.

### L2: Parameterization Engine
Takes the base template and generates the mathematically configured boundaries bounding a test, locking variables *prior* to simulation.
*   **Input**: `ScenarioTemplate` + Random Seed + Config limits.
*   **Output**: `ScenarioInstance` (Concrete positional, environmental, and agent definitions including fully resolved Trigger Thresholds).

### L3: Dynamic Execution Engine
The real-time execution brain. The engine loads physics at 50Hz, handles dynamically reactive NPCs via Behavior Trees, and runs the continuous evaluation monitor.
*   **Input**: `ScenarioInstance`
*   **Output**: `SimulationResult` object encompassing pass/fail grading and fully logged metric traces.

### L4: Evaluation and Reporting Layers
Aggregates the trace streams over large batch runs to expose system biases (e.g. Failure categorizations across Weather gradients, Sub-system category collapses). Dashboard visualizer endpoint bounds.
*   **Input**: `SimulationResult[]` Array
*   **Output**: Dashboard Visualizer / Analytical HTML Reports

---

## 2. Dynamic Execution Sub-Systems (L3 Deep Dive)

The core execution environment (L3) manages three distinct physics operations without overlap:
1. **Physics & World Simulation (50hz 20ms Tick):** Ensures rapid collision detection necessary for high-speed urban dynamics. Dynamically updates road surface friction metrics continuously (preventing global scalar static limits).
2. **NPC Behavior Tree (BT) System:** NPCs run decoupled Behavior Trees referenced via the scenario `TRIGGER::` codes. BTs manage "Reactive Conditions" vs "Terminal States" natively resolving Ego positioning in real time. **Important Restriction**: BTs must be deterministic; chaos stems from parameterization, not BT code.
3. **Real-time Evaluation Monitor:** Continually analyzes conditions matching `success_criteria_resolved`. When failure triggers, execution halts immediately mapping exactly what failed; it does not await standard timeout padding unless the timeout itself flags "INCONCLUSIVE".

---

## 3. The 3 Immutable Integration Contracts

### Definition vs. Parameterization
Scenario Definition sets the fixed architectural rules. Parameterization uniquely modifies one instance of a run. **Never mutate a ScenarioTemplate with run-specific values**.

### Scripted Initialization vs. Reactive Triggers
Every adversarial NPC is split explicitly between two phases: Phase 1 follows a defined initialization trajectory to set up a threat angle. Phase 2 (post-trigger) acts *purely* reactively off the base behavior tree. NPCs *must not* execute reactive BT logic prior to their explicit activation trigger or bounds logic breaks.

### Binary Verdits vs. Metric Output Trace
The Evaluation monitor returns a strict Binary Verdict (PASS / FAIL / INCONCLUSIVE). However, it uniquely saves the continuous output metric trace. This strict separation guarantees we analyze "passing edge-cases" safely while cleanly tracking mass safety thresholds.

---

## 4. 3D WebGL Visualization (Headed Simulation Interface)

For "headed" GUI simulations, the backend does not produce 3D pixel output (which is intensive for scalable workloads). We utilize a decoupled WebGL WebSocket architecture streaming raw JSON metrics.

**SLA**: The rendering pipeline must target a **sub-100ms perceived latency** limit natively across modern browsers featuring a p95 latency threshold below 60ms.

1. **Headless Python Core**: Generates `t_ms` timing and updates the 50Hz physics vector states in a background binary calculation.
2. **Telemetry Socket JSON Stream**: Streams decoupled X/Y/Z points mapped natively through WebSocket layers per 20ms tick.
3. **In-Browser WebGL Target Engine**: Intercepts telemetry metrics via `Three.js` / `React Three Fiber` overlay mapping pre-cached 3D models atop vector nodes efficiently on the client machine.
4. **Interactive Scrubbing / HUD Canvas**: Handles standard HUD elements via React states parsing `monitor.metrics_current` for time, velocity, and dynamic evaluation grading in real time.
