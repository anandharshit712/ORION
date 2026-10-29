# ORION and the Safety Standards

**Status**: Phase 4.5, written 2026-10-29. Every claim below names the code, test or
document that backs it, so you can check it rather than take it on trust.

**Audience**: the safety engineer deciding whether, and how, ORION results can enter a
safety case under ISO 26262 or ISO 21448.

**ORION is not certified, not qualified and not a certification tool.** Nothing in this
document is a claim of conformance with ISO 26262, ISO 21448 or any other standard. It
explains where ORION can sit in your process, what evidence it can produce, and the limits
you have to argue around. It is written to help you reach your own tool-confidence
decision, not to make that decision for you.

---

## 1. What ORION is, in standards terms

ORION is a **simulation-based verification tool** for the planning and control software of
an automated driving function. It runs a model through parameterised traffic scenarios many
times with seeded randomness and reports, per scenario, a collision rate, an off-road rate
and four behaviour scores (`docs/METHODOLOGY.md`).

| What it evaluates | What it does not evaluate |
| --- | --- |
| Planning and control decisions given ground-truth object states | Perception: no camera, LiDAR, radar, GPS or IMU model, no noise and no occlusion (`arep/core/observation.py`, `docs/METHODOLOGY.md` §8) |
| Behaviour against a declared, parameterised hazard | Hardware, timing on a target ECU, or the vehicle's actuators |
| Ranking two models on equal terms | A calibrated absolute measure of road safety |

In ISO 26262 vocabulary, ORION is a **software tool used in verification** of an element
(ISO 26262-8, Clause 11). In ISO 21448 (SOTIF) vocabulary, its scenario library is a set of
**known hazardous scenarios**, each with a **triggering condition**, used to evaluate the
function's behaviour against them. Where ORION fits in each standard is set out in §3 and §4.

---

## 2. The artefacts

Three artefacts are generated from the scenario files, so they cannot drift from the library
they describe. Run from `arep_implementation/`:

```bash
# 1. A result to trace against. Any suite: core, intersection, vru, emergency,
#    multi-agent, full (SUITES in arep/cli/run_suite.py).
PYTHONPATH=. python -m arep.cli.run_suite --scenarios core --model <your.module.Model> \
    --runs-per-scenario 100 --output-dir ./results

# 2. Traceability matrix: CSV + HTML, and PDF where WeasyPrint's GTK libraries load.
PYTHONPATH=. python -m arep.cli.standards traceability --suite core \
    --report ./results/orion_suite_report.json --output-dir ./standards

# 3. ODD coverage statement: JSON + HTML (+ PDF).
PYTHONPATH=. python -m arep.cli.standards odd --suite core --output-dir ./standards
```

### 2.1 Per-scenario requirement metadata

Every scenario under `scenarios/` declares, in its `scenario:` block:

- **`behavioral_requirement`**: one sentence stating what the ego must do to pass. This
  follows the taxonomy rule that one scenario is one behavioural requirement
  (`docs/ARCHITECTURE.md` §1.1, §1.6).
- **`hazard`**: in ISO 21448 vocabulary, the *triggering condition* and the *hazardous
  event*, in a fixed two-part shape.
- **`verification_gap`**, where one applies: what the pass criterion does **not** check for
  that scenario. Read this column before reading the result beside it.

These are documentation. The engine never reads them (`docs/ARCHITECTURE.md` §3.2). They are
parsed into `ScenarioDefinition` (`arep/scenario/schema.py`, `parser.py`) as optional fields.
`tests/test_standards_alignment.py` asserts every production scenario has a non-empty
requirement and hazard and that no two scenarios share a requirement. **The test checks that
the text exists and is distinct, not that it is correct.** The statements were written by
reading each scenario's setup, and a reviewer should read them the same way.

### 2.2 Traceability matrix

Columns: scenario ↔ hazard ↔ behavioural requirement ↔ verification gap ↔ latest result
(collision rate, off-road rate, composite mean, run count, model, seed).

- **The latest result comes only from the report you pass with `--report`.** A scenario that
  report does not cover reads `not run`. A result is never inferred, defaulted or carried
  over from anywhere else. Without `--report`, every row reads `not run`.
- A scenario the report could not load reads `NOT RUN: refused at load`.
- **A PASS means the pass gate held, and nothing more**: collision rate < 0.01 and off-road
  rate < 0.01 across the runs (`COLLISION_RATE_LIMIT`, `OFF_ROAD_RATE_LIMIT` in
  `arep/cli/run_suite.py`). Where a scenario's requirement asks for more — a stop at a red
  light, a minimum overtaking clearance, a deceleration limit — the verification-gap column
  says what was not checked. The ODD statement lists every scenario that carries such a gap;
  for **INT-002 and INT-005 the requirement is not verified at all** (see §6).

### 2.3 ODD coverage statement

Generated per suite from the scenario YAML (`odd_statement()` in `arep/cli/standards.py`):
road types and topologies, lane counts and widths, speed limits, the ego's initial speed range
(the union of each scenario's parameterised `ego_velocity`), actor types and behaviours, and
the weather labels the suite declares. Coverage counts only scenarios that load: a scenario
refused at load exercises nothing, so it appears under "not covered" instead of widening a
range.

The "not covered" list combines what the data shows (scenarios refused at load, weather
labels that reach nothing) with what the code shows is absent from every scenario: weather
and friction effects, sensors and perception, lighting, road grade, routes and goals, a
progress term, traffic-rule compliance beyond speed and lane position, and reversing. Each
entry names its evidence.

This statement describes what **the test suite exercises in simulation**. It is not the ODD
of your vehicle, and it does not follow the ISO 34503 / BSI PAS 1883 ODD taxonomy. Use it to
check whether your function's ODD is inside what the suite covers, not as an ODD definition.

---

## 3. ISO 26262-8 Clause 11: tool confidence

Clause 11 asks for a **tool confidence level** (TCL) from two judgements about each use case
of a tool: its **tool impact** (TI) and the **tool error detection** (TD) your process
provides. That classification belongs to your use case, not to ORION, so what follows is the
argument you would make and the evidence ORION contributes to it.

### 3.1 Tool impact

- **TI1** applies where ORION results are **not credited** as verification evidence — for
  example, ORION is a development aid and the claim rests on other verification. A tool
  malfunction then cannot introduce or hide an error in the item. TI1 gives TCL1, which needs
  no qualification.
- **TI2** applies wherever an ORION PASS is **credited** as evidence that a requirement is
  met. A malfunction that produced a false pass could then let an error in the function go
  undetected. This is the case the rest of this section is about.

### 3.2 Tool error detection: what ORION provides

The question is how likely an ORION malfunction — above all a false PASS — is to be detected
or prevented. ORION has the following mechanisms, each with its limits:

| Mechanism | What it detects or prevents | What it does not | Evidence |
| --- | --- | --- | --- |
| **Determinism**: fixed 20 ms step, all randomness from a seeded `RandomManager`, `seed = master_seed + run_index` | A run that cannot be reproduced. Same `(model, scenario, seed)` gives byte-identical frames | A *consistently* wrong result: a reproducible error reproduces | `CLAUDE.md` §4; `tests/test_frame_determinism.py` |
| **Frame hash**: `FrameHasher` folds every canonical tick frame into a SHA-256 chain stored per run (`RunRecord.frame_hash`) | Divergence between two runs that should be identical, including frame order | Anything both runs share | `arep/utils/hashing.py`; `tests/test_frame_determinism.py` (two runs, live vs batch path) |
| **Hard-rule check**: no wall clock, no unseeded randomness in the simulation packages | A determinism leak entering the code | Logic errors | `scripts/check_hard_rules.py` (runs in CI) |
| **Version pinning**: `numpy==1.26.0`, `scipy==1.11.3`, `pyyaml==6.0.1` | Numerical drift from a dependency upgrade | Drift from the Python interpreter, the OS or the CPU (see §5.1) | `arep_implementation/pyproject.toml` |
| **Refusal of unsupported input**: an unimplemented event type is refused at load, never silently dropped | A scenario that loads, runs and scores while its hazard never happens | YAML keys that parse but are ignored (see §5.4) | `IMPLEMENTED_EVENT_TYPES` in `arep/scenario/events.py`; `docs/DISCUSSIONS.md` DI-02 |
| **Void runs**: a sandbox violation, hang or crash aborts the run and refunds it rather than scoring it | A truncated run scored as safe | — | `ModelSandboxError` in `arep/utils/exceptions.py`; `arep/execution/runner.py` |
| **Feasibility check**: every scenario has a corner of its ranges a braking response survives | Scenarios that fail every model (false FAIL) | False PASS | `tests/test_scenario_feasibility.py` |
| **Reference model**: a non-degenerate driver (IDM + lane keeping + evasion) | Scenarios that cannot be told apart from impossible ones | — | `ReferenceDriverModel`; `tests/test_reference_model.py` |
| **Executed acceptance criteria** | Roadmap claims that are no longer true | — | `scripts/verify_roadmap.py` |

What is **not** in place, and matters most for a false PASS:

- **No automated check that each scenario's hazard actually threatens a model.** During
  Phase 4.3 every new scenario was checked by hand to discriminate a braking model from a
  non-braking one, with the tables in the commit messages (`docs/ROADMAP.md` 4.3), but no
  test re-runs that check. A scenario edited so that its hazard no longer reaches the ego
  would keep passing.
- **No independent reference** against which the physics or the scoring has been validated.
- **No qualification kit**: no tool safety manual, no tool requirements specification, no
  tool validation report against those requirements.

### 3.3 The resulting position

For a TI2 use, the honest default is **TD3 → TCL3**: the mechanisms above detect
*non-reproducibility* well and *systematically wrong results* poorly. Two consequences:

1. **ORION does not currently supply the evidence a TCL3 or TCL2 qualification requires.**
   Clause 11's qualification methods — increased confidence from use, evaluation of the tool
   development process, validation of the software tool, development to a safety standard —
   would all need work on your side or ours. ORION's test suite and `verify_roadmap.py` are
   inputs to a tool-validation argument, not that argument.
2. **You can lower TD by process.** Common ways: cross-check a sample of ORION verdicts against
   an independent simulator or test track; re-run a sample of credited runs and compare
   frame hashes; review the verification-gap column for every scenario you credit; and inject
   known faults into a model to confirm the scenarios you rely on detect them. ORION's
   determinism makes the second and fourth cheap.

---

## 4. ISO 21448 (SOTIF)

The scenario library maps onto the SOTIF activities as follows:

- **Triggering conditions.** Each scenario's `hazard` names the triggering condition that
  initiates the hazardous behaviour and the hazardous event that would follow. These are a
  starting list for your own triggering-condition analysis, not a complete one: they come
  from a 60-scenario library, not from an analysis of your function.
- **Evaluation of known scenarios.** Running a suite and reading the traceability matrix is
  evidence about behaviour in these known hazardous scenarios, within the gaps the matrix
  states.
- **Unknown scenarios.** ORION explores the declared parameter ranges of known scenarios —
  uniform sampling, importance sampling (`arep/scenario/importance.py`) and adversarial search
  (`arep/search/`). That searches for failures *inside* a scenario's ranges. It does not
  discover new kinds of scenario, so it is weak evidence about the unknown-unsafe area.
- **Perception-related triggering conditions** — sensor limitations, occlusion, weather — are
  outside ORION entirely today (§5.2).

---

## 5. Limits you have to argue around

### 5.1 Determinism has a boundary

- **ROS2 bridge runs are real time and not seed-reproducible.** `Ros2BridgeModel` paces to
  the 20 ms step and uses the newest command, so the trajectory and frame hash depend on the
  stack's timing. Never present a ROS2 run as a deterministic result, and never compare its
  frame hash (`arep/bridges/ros2_bridge.py`; `CLAUDE.md` §5).
- **Reproducibility is tested within one environment.** `tests/test_frame_determinism.py`
  runs the same seed twice in one process and checks the live and batch paths agree. No
  golden hash is checked across machines, operating systems or Python versions, and the
  interpreter is not pinned: CI runs Python 3.10 and 3.11, development 3.12. Floating-point
  accumulation order is known to differ between interpreter versions (`CLAUDE.md` §12). Treat
  cross-environment hash equality as a check you perform, not a property ORION guarantees.
- **Only the simulation core's dependencies are pinned.** API, database and reporting
  dependencies use minimum versions.

### 5.2 The world model

- **Ground-truth observations.** No sensor model, noise, field of view or occlusion. Scenarios
  that describe an occluded hazard (VRU-008, MLT-009) do not occlude it; their verification
  gap says so. A model that would fail because its perception missed an object scores well
  here (`docs/METHODOLOGY.md` §8). Sensor simulation is Phase 6.
- **Weather, visibility and friction are labels** that neither physics nor the Observation
  reads; friction is one global value, and the default kinematic physics ignores it.
  EMG-004 (black ice) is refused at load for this reason (`docs/DISCUSSIONS.md` DI-01,
  DI-02). Five scenarios substitute for themes that need this physics, and each says so:
  LON-010 (speed bump, needs road grade), LAT-010 (wet-road lane departure), VRU-006
  (pedestrian at night), EMG-008 (dust storm), EMG-009 (flash-flood water).
- **Pacejka tyre coefficients are uncalibrated**: plausible passenger-car defaults, not
  fitted to a measured tyre. Relative comparison between models is sound; absolute handling
  claims are not (`docs/METHODOLOGY.md` §7).
- **No route, no goal, no lane assignment.** Nothing tells a model which way to go, so a
  turn or a merge cannot be required. Junction results measure reaction inside a junction,
  not negotiation of one (`docs/PENDING.md`, "No lane assignment reaches the model").

### 5.3 The scoring

- **Nothing in the composite rewards making progress.** A model that brakes to a standstill
  scores 0.988 composite on LON-001, and the pass gate inherits this: refusing to move
  passes most of the library. A high score is evidence of not crashing, not evidence of
  driving (`docs/METHODOLOGY.md` §8; pinned by `tests/test_reference_model.py`).
- **The pass gate is collision and off-road only.** Signals, stop lines, give-way, right of
  way, clearances and deceleration limits are not checked; a violation fails a run only if
  it causes contact (`arep/evaluation/compliance.py`, `arep/cli/run_suite.py`).
- **TTC is an approximation.** It projects under constant acceleration along the closing
  line and does not project steering. It ranks models on a scenario; it is not a calibrated
  time to impact (`arep/core/ttc.py`; `docs/METHODOLOGY.md` §3).
- **Scores are comparable only within a scoring version.** Several corrections in Phases 0.5
  to 4.3 moved scores (`docs/METHODOLOGY.md` §10).

### 5.4 The library

- **Six scenarios are unproven**: EMG-002, EMG-008, LAT-003, LAT-007, MLT-005 and MLT-007.
  No model in the repository passes them (measured 2026-10-01, 10 runs per scenario), so it
  has not been shown that they can be passed. A FAIL there is not yet evidence against your
  model. Their verification gap says so.
- **Silently ignored YAML keys are still possible.** DI-02 closed the event-type hole but its
  audit of keys the parser accepts and ignores is open. One instance was found writing this
  document: LON-001 parameterises `initial_decel`, which its scripted lead vehicle never
  reads, so its deceleration is the same on every run.
- **Some scenarios are close to duplicates as executed**, because the detail that separates
  them is not modelled: VRU-001 and VRU-006 differ by crossing markings that do not exist in
  the road model; VRU-008 is VRU-004 plus a parked car that does not occlude. Both are
  recorded in their verification gaps.

---

## 6. Scenarios whose requirement is not verified by the pass gate

The verification-gap column is the full list. The two where a PASS says nothing about the
requirement:

- **INT-002** (red light): there is no cross traffic and red-light running is not detected,
  so a model that drives through the red passes.
- **INT-005** (unprotected left turn): nothing tells the model to turn, and an ego that drives
  straight never enters the oncoming lane.

And two where the requirement can only be met by not attempting it: **INT-003** (joining from
a T-junction needs a turn; stopping short passes) and **MLT-003** (on-ramp merge; stopping on
the ramp passes).

---

## 7. Keeping this document true

- A scenario added or changed must keep its `behavioral_requirement`, `hazard` and, where one
  applies, `verification_gap` accurate. The library test enforces presence and uniqueness
  only.
- When a limit in §5 is fixed, update the relevant `verification_gap` entries, the
  `_engine_limits()` list in `arep/cli/standards.py`, and this document in the same change.
- The HTML and PDF artefacts carry their generation time in the header; the CSV and JSON do
  not. Regenerate them for each release you rely on, and never edit one by hand.
