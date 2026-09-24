# ORION — Architecture & Scenario Taxonomy

**Version**: 1.0 (Markdown consolidation)
**Status**: Active — the design authority for the scenario taxonomy, the 4-layer execution
architecture, and the contract between them.

> **Provenance.** This document is the Markdown consolidation of `ORION_Design_Guide.docx`,
> which itself superseded the original `ORION_SCENARIO_TAXONOMY.md` and
> `PROPOSED_IMPLEMENTATION.md`. The three scenario templates that existed only in the old
> taxonomy file (LAT-002, EMG-004, MLT-007) are preserved in **Appendix D**. Both source
> files are archived under `docs/archive/`.
>
> **Scope.** This document defines *what the system is*. Build order and priorities live in
> [ROADMAP.md](ROADMAP.md); the rules Claude Code enforces while writing code live in
> `CLAUDE.md`; frontend visuals live in [UI_DESIGN.md](UI_DESIGN.md).
>
> **One known divergence.** Section 2.6 and the telemetry schema below predate the shipped
> implementation. The live frame schema is now frozen in
> `SimulationEngine.get_tick_frame()` — where the two differ, the code wins and this
> document is the intent behind it.

---

ORION Platform

Complete Design Guide

Scenario Taxonomy · Implementation Architecture · Integration Contract

This document replaces the original ORION_SCENARIO_TAXONOMY.md and PROPOSED_IMPLEMENTATION.md.

It defines what to build, how to build it, and how every piece connects.

# PART 0 — DIAGNOSIS: WHAT THE ORIGINAL DOCUMENTS GOT WRONG

## 0. Why the Originals Must Be Rebuilt, Not Patched

Before defining what ORION should be, you need to understand precisely why the original documents fail. Two separate, serious errors are present — one in each document — and a third error ties them together.

### 0.1 The Taxonomy Error: Combinatoric Enumeration Is Not a Taxonomy

The original taxonomy took four axes — Road Topology (5 values), Weather (5), Ego Maneuver (4), Adversary Type (5) — and randomly sampled ~200 of the 500 possible combinations. Each combination was assigned a scenario ID and called a distinct scenario.

> **CRITICAL** — A scenario is not a combination of labels. A scenario is a specific behavioral challenge with a defined threat, a required response, and a measurable success criterion. SCN-001 ('Highway / Right Turn / Emergency Vehicle / Sun Glare') tells you nothing about what the ego vehicle must do, what the adversary will do, whether the ego has right of way, or what constitutes a pass or fail. It is a label, not a scenario.

The proof that the taxonomy is hollow: pick any three rows and ask 'what is the AV being tested for?' The answer is always the same vague thing: 'handle an adversary in bad weather.' That is not a test. That is a situation description without a test objective.

Additionally, the axes themselves are wrong for the purpose of scenario differentiation:

- Weather/Lighting: is a modulator, not a scenario axis. Changing weather does not change the behavioral challenge. A pedestrian crossing under rain is the same behavioral problem as one under clear sky. Weather belongs in the parameterization layer, not the taxonomy.
- Adversary Type: is insufficient without Adversary Action. A 'Hesitant Pedestrian' on a highway versus at a crosswalk requires completely different responses. The adversary's action is what defines the scenario, not its type label.
- Ego Maneuver: is a result of the scenario, not a definition of it. The scenario should define the situation the ego faces; the maneuver the ego chooses is what is being evaluated. Listing 'Evasive Stop' as an axis pre-decides the response.

### 0.2 The Implementation Error: Two Architectures Described as One

The implementation document describes a Tick-Level Dynamic Trigger System where NPC behavior reacts to the ego vehicle in real time. This is a generative reactive architecture — the scenario unfolds based on what the ego does.

But the taxonomy document describes a static catalog of 200 pre-enumerated scenarios — a scripted scenario library architecture where scenarios have fixed definitions and predetermined IDs.

> **CRITICAL** — These two models are not the same thing and cannot share the same execution pipeline without a deliberate architectural bridge. The implementation document implies Model B (generative); the taxonomy implies Model A (scripted). Neither document acknowledges the other's model exists, let alone explains how they connect.

### 0.3 The Missing Connection: The Integration Contract

There is no document — and no section in either document — that answers the most important question: HOW does a scenario from the taxonomy get loaded into the dynamic execution engine? Specifically:

- What data structure does a scenario produce that the engine consumes?
- Which parts of a scenario are fixed at load time vs. allowed to mutate at runtime?
- How does the engine know when a scenario has been passed, failed, or is inconclusive?
- How does parameterization interact with dynamic mid-run mutation — which parameters are set before the run starts, and which can change during the run?

This guide answers all of these questions. The three parts that follow are: (1) how to build a proper taxonomy, (2) how to build a connected implementation, (3) the explicit integration contract between them.

# PART 1 — HOW TO BUILD THE ORION SCENARIO TAXONOMY

## 1. Taxonomy Design Principles

A scenario taxonomy for AV testing has one job: ensure that when you run the full catalog against a model, you have tested every behaviorally distinct challenge the vehicle will face in the real world. This section defines the principles that make that possible.

### 1.1 The Foundational Rule: One Scenario = One Behavioral Requirement

> **RULE** — Every scenario in the taxonomy must correspond to exactly one behavioral requirement — a specific thing the AV must be able to do. If two scenarios require the same behavioral response from the AV, they are the same scenario with different parameters, not two different scenarios.

Examples of behavioral requirements:

- The AV must yield to oncoming traffic before completing an unprotected left turn.
- The AV must brake hard enough to avoid collision when a lead vehicle stops unexpectedly.
- The AV must pull over and stop when an emergency vehicle approaches from behind.
- The AV must remain in its lane when an adjacent vehicle encroaches laterally on a bend.

Notice that each of these statements contains: who is the threat, what action the threat takes, and what the AV must do in response. That is the minimum content of a scenario definition. If your scenario definition does not contain all three, it is not a scenario — it is a situation label.

### 1.2 The Six Mandatory Behavioral Challenge Categories

All AV scenarios can be grouped into six categories based on the class of challenge they present. A complete taxonomy must have meaningful coverage in all six. These categories are not arbitrary — they map directly to the dominant crash types in real-world accident databases (NHTSA, GIDAS, UK STATS19).

#### Category 1: Longitudinal Control Challenges

Tests whether the AV correctly manages speed, following distance, and braking. The threat comes from ahead of the ego vehicle, in the same direction of travel.

- Core question: Can the AV detect and respond to a change in the motion state of objects directly ahead of it?
- What varies: Speed of the lead vehicle, rate of deceleration, warning time available to ego, presence of a follow-on vehicle behind ego
- Examples: Lead vehicle emergency stop; lead vehicle decelerating for unseen obstacle; multi-vehicle chain braking event; speed bump or road surface change

#### Category 2: Lateral Control and Lane Management

Tests whether the AV correctly manages lateral position, lane changes, and responses to encroachment. Threats come from adjacent lanes or from road edges.

- Core question: Can the AV maintain appropriate lateral positioning and respond correctly when that positioning is threatened?
- What varies: Direction of encroachment (from left vs right), whether ego is initiating the lane change or responding to another's, speed differential, available lane width
- Examples: Adjacent vehicle merging into ego's lane; ego performing a voluntary lane change into moving traffic; oncoming vehicle crossing centreline on a bend; narrow road requiring precise lateral positioning

#### Category 3: Intersection and Right-of-Way Negotiation

Tests whether the AV correctly interprets and acts on right-of-way rules at junctions. This is the most complex category and the source of the highest proportion of fatal crashes globally.

- Core question: Does the AV correctly determine who has right of way and act on that determination safely?
- What varies: Type of traffic control (signal, stop sign, yield, bare), ego's maneuver (straight, left turn, right turn), whether the conflict agent is compliant or violating
- Critical sub-types: Protected left turn; unprotected left turn (must yield to oncoming); right turn with crossing pedestrian/cyclist; crossing negotiation at unsignalized junction; red light violation by cross traffic

#### Category 4: Vulnerable Road User (VRU) Interaction

Tests whether the AV detects, predicts, and appropriately yields to pedestrians, cyclists, and other non-vehicle road users. VRU crashes are disproportionately fatal.

- Core question: Does the AV detect VRUs accurately and give them appropriate priority even when their behavior is unpredictable?
- What varies: VRU type (pedestrian, cyclist, e-scooter), location (crosswalk vs jaywalking), trajectory (predictable vs sudden direction change), occlusion level
- Critical sub-types: Pedestrian crossing at marked crosswalk; jaywalking pedestrian mid-block; cyclist cutting across at intersection; child running from between parked cars (occlusion); cyclist in door zone

#### Category 5: Emergency and Anomalous Situations

Tests whether the AV handles rare but high-stakes situations that fall outside normal traffic flow. These are the 'long tail' scenarios.

- Core question: Does the AV behave safely when the environment presents something outside its expected nominal operating domain?
- What varies: Type of emergency (vehicle, ambulance, police, fire), type of anomaly (debris, wrong-way driver, broken-down vehicle, road surface failure), visibility of the anomaly
- Critical sub-types: Emergency vehicle approaching from behind (pull over required); wrong-way driver on divided road; stationary vehicle blocking lane on high-speed road; debris field requiring slalom; vehicle control loss (ice/blowout)

#### Category 6: Multi-Agent and Complex Interaction

Tests whether the AV handles situations where multiple threats are active simultaneously. Single-threat scenarios are necessary but not sufficient — real driving involves constant multi-agent coordination.

- Core question: Does the AV correctly prioritize and sequence its responses when multiple conflicting demands are present at the same time?
- What varies: Number of active agents (2, 3, 4+), whether conflicts are simultaneous vs sequential, whether agents behave cooperatively or adversarially toward each other
- Examples: Pedestrian crossing at same time as vehicle cuts in; merging while emergency vehicle approaches; construction zone with both a lane restriction and a pedestrian worker

### 1.3 The Correct Axis Structure for Scenario Differentiation

Within each category, scenarios are differentiated by axes. But these axes must be behavioral, not cosmetic. Here is the correct set of axes, and why each one is included.

> **RULE** — The test for whether an axis belongs in the taxonomy (vs. the parameterization layer): does changing this axis value require the AV to execute a DIFFERENT BEHAVIOR? If yes, it is a taxonomy axis. If no — if the AV does the same thing but under harder sensory conditions — it belongs in parameterization.

| Axis | Values | Why It Is a Taxonomy Axis | Why Weather Is NOT Here |
|---|---|---|---|
| Right-of-way status | Ego has ROW / Ego must yield / Ambiguous / Violated by other | Changes the correct response entirely — ego that has ROW accelerates; ego that must yield stops/waits | Weather does not change who has right of way |
| Threat direction | Same direction / Oncoming / Crossing (lateral) / Rear / Merging | Response differs: same-direction = brake; oncoming = lateral avoidance; crossing = time-gap judgment | Weather does not change the geometry of the threat |
| Adversary compliance | Fully compliant / Violating traffic law / Unpredictable / Non-participant (debris) | Ego must predict adversary intent — compliant agents are predictable; violators are not | Weather does not change whether an agent is compliant |
| Occlusion state | Full visibility / Partially occluded / Fully hidden until trigger | Changes perception task fundamentally — hidden threats require anticipatory behavior, not reactive | Weather reduces range, but occlusion changes the task type |
| Ego's positional state | In lane / Lane-changing / In intersection / Merging / Parking | Ego's current maneuver determines which responses are physically available | Weather does not change which maneuvers are geometrically possible |
| Trigger mechanism | Continuous / Event-triggered / Time-triggered / Proximity-triggered | Determines the warning time available to ego — same threat at different trigger timings is a different challenge | Weather affects perception of the trigger, not the trigger type itself |

### 1.4 Where Weather, Lighting, and Sensor Degradation Go

These are NOT scenario axes. They are parameterization modifiers. Here is the correct treatment:

> **NOTE** — A 'Pedestrian Crossing' scenario at a signalized crosswalk is one scenario. Running it under 5 different weather conditions produces 5 parameterized instances of the same scenario. The weather condition should be logged as a test parameter, and performance should be disaggregated by weather in the results dashboard — but it does not create 5 different scenarios in the taxonomy.

The parameterization layer handles:

- Environmental conditions: Clear / Rain / Fog / Night / Glare / Snow / Mixed (transition mid-run)
- Sensor degradation profile: 0% noise, 10%, 25%, 50% loss across camera / LiDAR / radar independently
- Road surface friction: 0.9 (dry) → 0.2 (ice) — affects AV dynamics, not behavioral challenge category
- Time of day: Noon / Sunset / Dusk / Night — affects sensor performance, not right-of-way logic
- Traffic density background: Sparse / Moderate / Dense — background traffic, not the threat agent
- Adversary speed: Range in km/h appropriate to road class
- Adversary spawn distance: How far from ego the threat begins — controls time available
- Ego initial speed: At or below posted limit at scenario start

Each scenario in the taxonomy receives a defined Parameterization Profile — the ranges that are valid to apply to that scenario. A highway scenario does not get parking lot speed ranges. A night-only scenario does not get daytime runs. This profiles the parameterization layer to the scenario, rather than applying global ranges blindly.

### 1.5 What Must Be Absent from the Taxonomy

The following must not appear in the scenario taxonomy:

> **WARNING** — Do not include any of the following in scenario definitions. Each one is either a parameterization concern or a non-scenario that tests nothing specific.

- Duplicate behavioral requirements: If two scenarios have the same required AV response, they are one scenario with different parameters. Remove duplicates ruthlessly. Scenario count is not a quality signal.
- Weather-differentiated variants of the same scenario: SCN-001 and SCN-004 from the original taxonomy differ only in weather. This is one scenario with two parameterization instances. One ID, not two.
- Scenarios without a measurable pass/fail condition: 'Highway / Straight / Emergency Vehicle / Fog' has no defined success criterion. If you cannot state what the AV must do to pass, it is not a scenario.
- Physically implausible combinations: 'Merging from On-Ramp' in a Parking Lot (SCN-162). On-ramps do not exist in parking lots. This is a combinatoric artifact, not a real scenario.
- Redundant Road Topology categories without behavioral justification: If the AV's required behavior at a 'Suburban Intersection' is identical to its behavior at an 'Urban Intersection' in all your scenarios, merge the categories. Topology is a parameterization modifier (speed limit, lane width) unless it creates a categorically different behavioral challenge.
- Scenarios where the 'adversary' is passive: A Stationary Debris scenario is a perception test, not an adversarial interaction. Label it correctly or it will corrupt your analysis of adversarial behavior results.

### 1.6 The Correct Schema for a Single Scenario Definition

Every scenario in the ORION taxonomy must be defined with this schema — no exceptions. An ID and a three-column table row is not a scenario definition.

> **RULE** — If a scenario cannot be fully described using this schema, it is not ready for the taxonomy. Do not add it until all fields can be populated.

| Field | Description and Requirements |
|---|---|
| SCN-ID | Format: [CATEGORY_CODE]-[SEQUENCE]. E.g., LON-003, INT-012, VRU-007. Category code ensures scenario IDs carry behavioral meaning. |
| Scenario Name | Plain English name that describes the behavioral challenge. Must contain the threat and the required response. E.g., 'Lead Vehicle Emergency Stop — Rear-End Avoidance'. |
| Behavioral Category | One of the six: Longitudinal / Lateral / Intersection / VRU / Emergency / Multi-Agent. |
| Behavioral Requirement | One sentence: what the AV must be able to do to pass this scenario. This is the test objective. E.g., 'The ego vehicle must come to a complete stop without contact within the available distance.' |
| Threat Agent | Who/what creates the challenge. Include type, action, and compliance status. E.g., 'Lead vehicle: decelerates from 80 km/h to 0 in under 2 seconds (emergency stop).' |
| Ego Right-of-Way Status | Ego has ROW / Ego must yield / Ambiguous / Ego's ROW is violated by adversary. |
| Threat Direction | Same direction / Oncoming / Crossing lateral / Rear / Merging. |
| Trigger Type | How the critical event is initiated: Proximity-triggered / Event-triggered / Time-triggered / Continuous. |
| Trigger Condition | Specific condition. E.g., 'Emergency stop triggers when ego TTC to lead vehicle crosses below 3.5 seconds.' |
| Occlusion State | Full visibility / Partial occlusion (describe what blocks view) / Full occlusion until trigger. |
| Success Criterion | Measurable condition the ego must meet to pass. E.g., 'No collision; deceleration between 0.3g and 0.8g; ego comes to stop within 1.5x the available braking distance.' |
| Failure Conditions | What constitutes a fail: collision, lane departure, wrong-way maneuver, etc. Must be exhaustive. |
| Parameterization Profile | What ranges are valid: adversary speed, ego initial speed, spawn distance, applicable weather conditions, applicable road types. |
| Real-World Crash Anchor | If this scenario maps to a documented crash type, cite it (NHTSA typology code, Euro NCAP test code, etc.). If it does not map to any real crash type, justify its inclusion. |
| Engine Trigger Code | The identifier used by the Dynamic Execution Engine to instantiate this scenario's NPC behavior tree. This is the integration link to the implementation. E.g., TRIGGER::LON_EMERGENCY_STOP_V1. |

#### 1.6.1 Parameterization is mandatory (RULE)

> **RULE** — Every scenario MUST declare a `parameterization:` block with at least one
> `{min, max}` range. A scenario with no ranges is a single fixed situation, not a test.

The schema above has always listed a "Parameterization Profile" as required. It was not
enforced, and by 2026-09-24 **eleven of twenty-one production scenarios had no
`parameterization:` block at all**. Those scenarios could be run, but they could not be
*searched*: adversarial search varies declared ranges, so with none declared it has nothing
to explore and returns immediately. Half the library was invisible to the feature meant to
find its hardest cases.

All twenty-one now declare ranges (1–11 dimensions). The rule is enforced by
`tests/test_scenario_library.py`, so a new scenario without ranges fails the suite rather
than silently opting out of search.

**What to vary, and what not to.** Ranges vary the *difficulty* of the behavioural
requirement, never the requirement itself:

- **Vary**: ego approach speed, adversary speed, spawn distance, trigger distance,
  deceleration strength, hesitation probability, pedestrian walk speed.
- **Do not vary**: anything that changes what the scenario *is*. A stationary-obstacle
  scenario keeps a stationary obstacle in every draw. A head-on scenario stays head-on. If a
  range would turn the scenario into a different behavioural requirement, it belongs in a
  different scenario — see §1.1.
- **Do not vary the thing under test.** EMG-004 tests black-ice recovery, so surface
  friction is fixed and *entry speed* is the range. Varying the friction would be varying
  the question.

**Make the range wide enough to include failures.** A range where every draw is comfortably
survivable tests nothing. LON-004's sighting distance deliberately reaches inside the
braking distance for its highest speed, so some draws are genuinely unavoidable — a model
should be measured on those too.

**Watch the axis on rotated geometry.** `ego_x_jitter` shifts x, which is *longitudinal* on
an eastbound scenario and *lateral* on a northbound arm. INT-003 once applied ±4 m of it
while climbing a north-facing arm, which is wider than the lane: every run started in
oncoming traffic. MLT-003 documents avoiding the same trap on its 15° ramp.

---

### 1.7 The Full Taxonomy Structure: How Many Scenarios and How to Count Them

The number of scenarios should emerge from coverage analysis, not be decided in advance. Here is how to arrive at the right number:

- Step 1: Map the six categories to real crash data — Pull the top 10–15 crash types by frequency and severity from NHTSA pre-crash typology (or equivalent). These are your mandatory scenarios. You cannot have a credible AV test suite without them.
- Step 2: For each crash type, identify the minimum behavioral requirement variants — Some crash types branch into 2–3 distinct behavioral requirements. An intersection crash can require either 'yield to oncoming' (unprotected left turn) or 'yield to cross-traffic' (right turn at crossing) or 'handle violating agent' (red light runner). Each distinct behavioral requirement = one scenario.
- Step 3: Add scenarios for known AV-specific failure modes — Real-world crash data was generated mostly by human drivers. AVs have specific failure patterns not well-represented in crash data: phantom braking, lane-merge timing errors, adversarial sensor attacks, map-reality mismatch at construction zones. Add scenarios targeting these.
- Step 4: Add multi-agent compositions — Take the 2–3 most dangerous single-agent scenarios from each category and create composed versions with 2+ simultaneous agents. These test prioritization logic.
- Step 5: Count what you have and verify coverage — You should end up with 60–120 distinct scenarios if done rigorously. If you have fewer than 40, you've under-covered the problem space. If you have more than 150, you likely have duplicates — run the behavioral requirement uniqueness test on every pair.

> ◆ KEY INSIGHT60 rigorous scenarios with defined behavioral requirements, trigger conditions, and pass/fail criteria will expose more AV model weaknesses than 200 combinatoric label combinations. Depth beats breadth in test taxonomy design.

### 1.8 Sample Correct Scenario Definitions (Three Examples)

The following three examples show what a properly defined scenario looks like. Use these as templates.

#### Example 1 — Longitudinal Category

| SCN-ID | LON-003 |
|---|---|
| Scenario Name | Lead Vehicle Emergency Stop — Rear-End Avoidance with Occluded Cause |
| Behavioral Category | Longitudinal Control |
| Behavioral Requirement | The ego vehicle must detect and respond to a sudden full stop by the lead vehicle with sufficient deceleration to avoid contact, without prior visible cause for the stop. |
| Threat Agent | Lead vehicle: decelerating at 0.9g (emergency stop) from 80 km/h to 0 km/h. Cause of stop (obstacle) is not visible to ego. Compliant behavior — not adversarial. |
| Ego ROW Status | Not applicable (same-direction following, no right-of-way conflict). |
| Threat Direction | Same direction (ahead of ego). |
| Trigger Type | Proximity-triggered. |
| Trigger Condition | Lead vehicle begins emergency deceleration when ego's TTC to lead vehicle is between 2.5s and 4.0s (randomized per run). |
| Occlusion State | Lead vehicle is fully visible. Cause of stop (obstacle 30m ahead of lead) is fully occluded by the lead vehicle. |
| Success Criterion | No contact. Ego decelerates at or above 0.3g within 0.8 seconds of lead vehicle stop onset. Ego comes to full stop within road lane boundaries. |
| Failure Conditions | Collision with lead vehicle; departure from lane during stop maneuver; deceleration onset delay exceeding 2.0 seconds. |
| Parameterization Profile | Ego initial speed: 60–100 km/h. Lead vehicle speed: same as ego ±5 km/h. Initial following distance: 20–60m. Weather: all. Road type: Highway, Rural. |
| Real-World Crash Anchor | NHTSA Pre-Crash Typology: Type 14 — Lead vehicle decelerating. |
| Engine Trigger Code | TRIGGER::LON_EMERGENCY_STOP_V1 |

#### Example 2 — Intersection Category

| SCN-ID | INT-005 |
|---|---|
| Scenario Name | Unprotected Left Turn — Yield to Oncoming Traffic Gap Acceptance |
| Behavioral Category | Intersection Negotiation |
| Behavioral Requirement | The ego vehicle must wait for a safe gap in oncoming traffic before completing an unprotected left turn at a signalized or unsignalized junction, without causing oncoming vehicles to brake. |
| Threat Agent | 2–4 oncoming vehicles traveling at road speed in the lane ego must cross. Compliant behavior — they will not yield. |
| Ego ROW Status | Ego must yield. Oncoming vehicles have right of way. |
| Threat Direction | Oncoming (crossing path during ego's left turn). |
| Trigger Type | Continuous (oncoming traffic flows throughout; ego must find safe gap). |
| Trigger Condition | N/A — threat is constant. Scenario ends when ego completes turn or times out. |
| Occlusion State | Full visibility of oncoming vehicles. No occlusion variant in this base scenario (see INT-005b for occluded variant). |
| Success Criterion | Ego completes left turn without causing any oncoming vehicle to decelerate more than 0.1g. Ego accepts a gap >= 4.0 seconds TTC before entering. Ego does not block intersection for more than 15 seconds. |
| Failure Conditions | Collision; causes oncoming vehicle emergency brake (>0.3g decel); enters turn with TTC < 2.5 seconds to nearest oncoming vehicle; does not complete turn within 30-second timeout. |
| Parameterization Profile | Oncoming vehicle speed: 30–80 km/h depending on road class. Gap distribution: random Poisson process with mean 5s. Number of oncoming vehicles: 2–6. Traffic control: signalized (with protected phase absent) or unsignalized. |
| Real-World Crash Anchor | NHTSA Pre-Crash Typology: Type 2 — Unprotected left turn, oncoming traffic. #1 cause of fatal intersection crashes. |
| Engine Trigger Code | TRIGGER::INT_UNPROTECTED_LEFT_V1 |

#### Example 3 — VRU Category

| SCN-ID | VRU-008 |
|---|---|
| Scenario Name | Occluded Pedestrian — Child Entering Road from Between Parked Vehicles |
| Behavioral Category | VRU Interaction |
| Behavioral Requirement | The ego vehicle must detect and yield to a pedestrian who enters the road from a fully occluded position between parked vehicles, with an initial TTC that does not allow for comfortable stop without anticipatory speed reduction. |
| Threat Agent | Pedestrian (child profile: 1.0m height, 1.0 m/s walking speed) entering road laterally from gap between parked cars. Non-compliant with traffic (jaywalking). |
| Ego ROW Status | Ego has ROW on the road. However, safety obligation requires yielding regardless. |
| Threat Direction | Crossing lateral (pedestrian path is perpendicular to ego's path). |
| Trigger Type | Proximity-triggered. |
| Trigger Condition | Pedestrian begins crossing when ego is 15–25m from parked vehicle gap (randomized per run). Pedestrian is invisible until they step beyond the parked vehicle edge. |
| Occlusion State | Full occlusion until trigger (parked vehicle blocks view). First visibility: ego has 1.0–2.5 seconds TTC to pedestrian at point of visual acquisition. |
| Success Criterion | No contact with pedestrian. Ego decelerates to full stop or below 5 km/h before pedestrian's path. Anticipatory speed reduction (below posted limit) is rewarded as a secondary metric. |
| Failure Conditions | Contact with pedestrian; ego speed at pedestrian crossing line exceeds 15 km/h; ego fails to detect pedestrian within 0.5 seconds of first visibility. |
| Parameterization Profile | Ego initial speed: 20–50 km/h. Pedestrian speed: 0.8–1.5 m/s. Gap width: 0.8–1.5m. Available sight distance: 5–20m before gap. Weather: all. Road type: Urban, Suburban. |
| Real-World Crash Anchor | Euro NCAP AEB VRU Test: Child Crossing — Occluded by Parked Vehicle. |
| Engine Trigger Code | TRIGGER::VRU_OCCLUDED_CHILD_V1 |

# PART 2 — HOW TO BUILD THE ORION IMPLEMENTATION ARCHITECTURE

## 2. Implementation Architecture: Full Specification

The original implementation document had the right high-level ideas — headless physics, WebSocket telemetry, client-side rendering, reactive NPCs. This section takes those ideas and makes them specific enough to actually build. Every component is defined with its data contract so that the taxonomy and execution engine can be connected.

### 2.1 The Architecture in One Diagram

ORION has four layers. Each layer has a single, clear responsibility. Nothing crosses layer boundaries except through the defined interface.

| Layer | Name | Responsibility | Input | Output |
|---|---|---|---|---|
| L1 | Scenario Registry | Stores all scenario definitions from the taxonomy. Serves scenario templates to the engine. | Scenario schema (from taxonomy) | ScenarioTemplate object |
| L2 | Parameterization Engine | Takes a ScenarioTemplate and produces a fully initialized ScenarioInstance with concrete values for all variable parameters. | ScenarioTemplate + seed/config | ScenarioInstance object |
| L3 | Dynamic Execution Engine | Runs the physics simulation, manages NPC behavior trees, evaluates pass/fail criteria at 50Hz. The 'real-time brain'. | ScenarioInstance | SimulationResult object |
| L4 | Evaluation and Reporting | Aggregates SimulationResults across runs, computes pass rates by scenario/category/weather/seed, produces dashboards. | SimulationResult[] | Report / Dashboard |

> ◆ KEY INSIGHTThis four-layer structure is the explicit connection between the taxonomy and the implementation. The taxonomy lives entirely in L1. The parameterization section of the taxonomy defines what L2 does. The Engine Trigger Code field in each scenario definition is the bridge to L3. L4 is what turns test results into useful information.

### 2.2 Layer 1: Scenario Registry

The Scenario Registry is a structured database (or structured YAML/JSON files) containing all scenarios defined in the taxonomy. It is read-only during simulation — the engine never modifies it. It is the source of truth.

#### Data Schema: ScenarioTemplate Object

This is the exact data structure a ScenarioTemplate must contain. It maps directly from the taxonomy schema defined in Section 1.6.

| Field | Type | Description |
|---|---|---|
| scenario_id | string | Unique ID following [CATEGORY]-[SEQ] format. E.g., LON-003. |
| name | string | Full plain-English scenario name. |
| category | enum | One of: LONGITUDINAL \| LATERAL \| INTERSECTION \| VRU \| EMERGENCY \| MULTI_AGENT |
| behavioral_requirement | string | The one-sentence test objective. |
| right_of_way | enum | EGO_HAS_ROW \| EGO_MUST_YIELD \| AMBIGUOUS \| EGO_ROW_VIOLATED |
| threat_direction | enum | SAME_DIRECTION \| ONCOMING \| CROSSING \| REAR \| MERGING |
| trigger_code | string | Engine trigger identifier. E.g., TRIGGER::LON_EMERGENCY_STOP_V1 |
| trigger_type | enum | PROXIMITY \| EVENT \| TIME \| CONTINUOUS |
| trigger_condition | object | Structured trigger: { type, threshold, threshold_unit, randomize_range } |
| occlusion_state | enum | FULL_VISIBILITY \| PARTIAL \| FULLY_HIDDEN_UNTIL_TRIGGER |
| success_criteria | Criterion[] | Array of measurable conditions, each with: metric, operator, threshold, unit. |
| failure_conditions | string[] | List of explicit failure states. |
| param_profile | ParamProfile | Structured object defining valid ranges for all parameterizable variables. |
| crash_anchor | string \| null | Citation to real-world crash type, or null. |
| version | semver string | Schema version. Enables registry migration without breaking running simulations. |

### 2.3 Layer 2: Parameterization Engine

The Parameterization Engine takes a ScenarioTemplate from the Registry and produces a ScenarioInstance — a fully resolved, concrete set of initial conditions ready to run. It runs before the simulation starts.

#### What Parameterization Does (and Does Not Do)

> **RULE** — Parameterization sets the initial state of the world. It does NOT define what happens during the simulation. The boundary is: everything that is known before the run starts = parameterization. Everything that changes in response to the ego vehicle's actions during the run = dynamic execution (Layer 3).

Parameterization resolves:

- Actor initial positions and velocities: Sampled from the ranges in the scenario's param_profile.
- Environmental conditions: Weather state (e.g., fog density = 0.6), road surface friction (e.g., mu = 0.45), time of day (e.g., sunset at 18:22).
- Sensor degradation profile: Which sensors are degraded, and by how much, at run start. Can be set to 'progressive' (degrades during run) — but the degradation schedule is fixed at parameterization time.
- Trigger thresholds: If the trigger_condition has a randomize_range, the specific threshold is resolved at this step. E.g., emergency stop triggers at TTC = 3.2s (drawn from uniform[2.5, 4.0]).
- Background traffic: Density and routing of non-scenario vehicles placed to create realistic traffic context around the scenario actors.

#### The ScenarioInstance Object

This is what parameterization produces and what the execution engine consumes:

| run_id | Unique identifier for this specific run. Links results back to scenario_id + seed. |
|---|---|
| scenario_id | Reference to the ScenarioTemplate this instance was generated from. |
| seed | The random seed used. Required for deterministic replay. |
| world_state_t0 | Complete initial world state: all actor positions, velocities, headings at t=0. |
| environment_config | Resolved weather, friction, time of day, visibility range. |
| sensor_config | Which sensors are active, their noise profiles, and degradation schedule. |
| resolved_triggers | All trigger thresholds resolved to concrete values. |
| npc_behavior_trees | References to the Behavior Tree programs each NPC will run. NOT the full BT — just the reference. The BT is loaded by the engine from the Trigger Registry. |
| success_criteria_resolved | The success criteria from the template with any parameterized thresholds resolved. |
| timeout_seconds | Maximum run duration before the scenario is marked inconclusive. |

### 2.4 Layer 3: Dynamic Execution Engine

This is the runtime core. It takes a ScenarioInstance and runs it. The execution engine has three sub-systems that the original document described but did not specify with enough precision:

#### Sub-system A: Physics and World Simulation

The physics simulation runs at 50Hz. This rate was mentioned in the original document without justification. Here is the justification and the implications:

> **NOTE** — 50Hz (20ms tick) is chosen because: (1) it is above the Nyquist frequency for detecting collision events at urban speeds (two vehicles approaching at 60 km/h close at ~33m/s, meaning even a 10ms tick would detect the collision within 0.3m accuracy); (2) it matches typical AV sensor fusion rates; (3) it provides 5 physics ticks per AV planning cycle if the model under test plans at 10Hz. The AV model interface must be designed to handle this mismatch explicitly — the engine buffers the AV's most recent control output and applies it until a new one arrives.

Physics simulation must handle these dynamic state changes natively:

- Road surface friction mutation: Friction coefficient is a per-tile property in the physics world, not a global parameter. This means the engine must support per-tile friction updates at runtime. The Continuous Weather Evolution feature requires this — you cannot just apply a global friction scalar and call it done.
- Visibility range updates: As fog density increases, the engine updates the visibility range parameter that the sensor simulation layer uses to determine what is and is not detectable. This is not just a visual effect — it affects whether the AV's sensor outputs include certain objects.
- Actor state updates from NPC behavior trees: Every NPC tick produces a new (position, velocity, heading) state. The physics engine applies these after collision resolution, not before. This prevents NPCs from teleporting through the ego vehicle.

#### Sub-system B: NPC Behavior Tree System

The original document mentioned Behavior Trees but did not specify them. Here is the required specification.

> **RULE** — Every NPC in a scenario has exactly one Behavior Tree program loaded at run start, referenced by the trigger_code from the scenario definition. Behavior Trees are stored in a Trigger Registry, versioned separately from scenarios. A scenario references a BT by its TRIGGER:: code, not by embedding the BT inline. This means BTs can be improved without changing scenario definitions.

A Behavior Tree for an NPC must define:

- Root selector: The priority order of all behaviors the NPC can execute.
- Reactive conditions: Which ego vehicle states trigger which NPC behaviors. These are the 'if ego does X, NPC does Y' rules from the original document. Every condition must be specified with a threshold, not described qualitatively. E.g., not 'if ego follows too closely' but 'if (ego_TTC_to_this_NPC < 2.0s AND ego_speed > 20 km/h), trigger emergency_brake_action'.
- Action library: The set of physically executable actions available to this NPC. Each action has a duration, max acceleration/deceleration, and termination condition. Actions must be physically realizable given the current NPC state — the BT executor must check this before initiating any action.
- Priority override rules: When two conditions trigger simultaneously, which takes precedence. This is where the original document was vague. Define it explicitly: e.g., collision_avoidance_action always preempts scenario_trigger_action.
- Terminal states: Conditions under which the NPC stops executing its BT and enters a passive state (e.g., NPC has reached its route end, scenario has ended, NPC has been involved in a collision).

#### Sub-system C: Real-Time Evaluation Monitor

The evaluation monitor runs in parallel with the physics simulation at every tick. It is the component that connects the taxonomy directly to runtime — it reads the success_criteria_resolved and failure_conditions from the ScenarioInstance and evaluates them continuously.

The monitor must:

- Track all metrics continuously: Not just at the end. If the success criterion requires 'deceleration onset within 0.8 seconds,' the monitor must timestamp the moment the lead vehicle begins decelerating and the moment ego begins decelerating, and compute the delta in real time.
- Emit verdict immediately on failure: When a failure condition is met, the run is terminated immediately and marked as FAIL with the specific condition that triggered failure. Do not run to timeout if a failure has already occurred.
- Produce a partial trace on pass: When a run completes, the monitor emits the full metric trace — not just pass/fail, but the values of every tracked metric across the run. This is what allows the evaluation layer (L4) to produce graded performance curves, not just binary results.
- Handle the inconclusive case explicitly: If the scenario timeout is reached without any success or failure condition being met, the result is INCONCLUSIVE, not PASS. An AV that does nothing technically avoids all failures. Do not allow this to count as a pass.

### 2.5 Layer 4: Evaluation and Reporting

The evaluation layer receives SimulationResult objects from completed runs and produces useful analysis. This layer is what distinguishes a test platform from a test oracle — it answers not just 'did the AV pass?' but 'where specifically does it break down, and under what conditions?'

#### Required Metrics Aggregations

- Pass rate by scenario: Per scenario_id across N parameterization instances. If LON-003 passes 94/100 runs, that is the pass rate for that behavioral requirement.
- Pass rate by category: Aggregate across all scenarios in each of the six behavioral categories. This tells you if the AV is systematically weak in Intersection scenarios vs VRU scenarios.
- Pass rate by weather condition: Disaggregate any scenario's pass rate by the weather parameterization value. If a scenario passes 96% in clear conditions but only 61% in fog, the fog degradation is meaningful.
- Pass rate by trigger timing: Disaggregate by how much warning time the ego had (i.e., the resolved trigger threshold). Performance should degrade gracefully — not collapse — at shorter warning times.
- Metric distributions, not just pass rates: For every run, the monitor produced metric traces. Plot distributions of key metrics: TTC at intervention, deceleration onset time, lateral deviation during maneuver. These distributions reveal systematic biases that pass/fail rates hide.
- Failure mode taxonomy: Categorize failures: collision, lane departure, timeout, wrong maneuver. A model that fails by collision is different from one that fails by being too conservative. Both are failures but in opposite directions.

### 2.6 The 3D Visualization Layer

The original document's WebGL streaming architecture is correct in concept. The following specification makes it precise:

> **WARNING** — The phrase 'zero-lag' must be removed from all technical documentation. It is not an engineering claim. Replace it with: 'sub-100ms perceived latency in standard browser conditions, with a target p95 latency below 60ms.' This is a measurable SLA that can be tested. 'Zero-lag' cannot.

#### Telemetry Stream Schema

The WebSocket stream emits one telemetry frame per physics tick (20ms). Each frame is a compact JSON object:

| tick | Integer. Physics tick counter since run start. |
|---|---|
| t_ms | Float. Simulation time in milliseconds since run start. |
| ego | Object: { id, x, y, z, heading, speed, accel_x, accel_y, active_sensors[] } |
| npcs | Array of objects: { id, x, y, z, heading, speed, type, bt_state } |
| env | Object: { weather_type, friction_mu, visibility_m, time_of_day } |
| monitor | Object: { active_criteria[], metrics_current{}, verdict_so_far } |
| events | Array of timestamped events this tick: trigger fires, metric threshold crossings, NPC state transitions. |

> **NOTE** — Keep the telemetry frame minimal. The client reconstructs 3D state from these values — it does not need raw physics data. The monitor.metrics_current field is what drives the live HUD in the React dashboard (showing TTC, speed, distance to threat). The events array is what drives the timeline scrubber for post-run replay.

#### Client-Side Rendering Responsibilities

- Three.js scene graph: One persistent scene graph per simulation session. Actor meshes are spawned once and updated in position/rotation each frame — not destroyed and recreated.
- Camera modes: Bird's-Eye, Chase Camera, and Free Camera must be switchable without interrupting the telemetry stream. Camera state is purely client-side — never sent to the backend.
- Timeline scrubber: The client stores the full telemetry history in a circular buffer (max 300 seconds at 50Hz = 15,000 frames). The scrubber rewinds by replaying historical frames into the scene graph.
- HUD overlay: Renders the active metrics from monitor.metrics_current. Specifically: current TTC, ego speed, distance to nearest threat, active weather condition, and the current verdict.

# PART 3 — THE INTEGRATION CONTRACT: HOW TAXONOMY AND IMPLEMENTATION CONNECT

## 3. The Integration Contract

This is the section that was entirely missing from the original documents. The integration contract defines exactly how a scenario from the taxonomy becomes a running simulation in the engine. Every field in the taxonomy schema maps to exactly one component in the implementation.

### 3.1 End-to-End Flow for a Single Scenario Run

The following describes precisely what happens when a user selects a scenario and clicks 'Run':

- Scenario Registry lookup (L1) — The system loads the ScenarioTemplate for the requested scenario_id from the Registry. This is a read-only operation. The template is validated against the registry schema — if any required field is missing, the run is rejected before it starts.
- Parameterization (L2) — The Parameterization Engine receives the ScenarioTemplate and a run configuration (seed, weather override if any, sensor degradation profile). It samples all variable parameters from the param_profile ranges using the seed for reproducibility. It loads the NPC behavior tree references from the Trigger Registry using the trigger_codes in the template. Output: a complete ScenarioInstance.
- World initialization (L3 entry) — The physics world is initialized from world_state_t0 in the ScenarioInstance. All actors are spawned at their resolved initial positions. The environment is configured. The evaluation monitor is initialized with the resolved success criteria and failure conditions.
- Run execution (L3 loop) — The physics engine begins ticking at 50Hz. Each tick: (a) physics step; (b) NPC behavior trees evaluated against current world state; (c) AV model queried for control output; (d) evaluation monitor checks all criteria; (e) telemetry frame emitted if headed mode is active. Loop continues until success, failure, or timeout.
- Result collection (L3 exit) — When the run terminates (any verdict), the engine emits a SimulationResult containing: run_id, scenario_id, seed, verdict, failure_reason if applicable, full metric trace, and the complete telemetry log.
- Evaluation aggregation (L4) — The SimulationResult is stored and the aggregation layer updates all relevant dashboards: per-scenario pass rate, per-category pass rate, metric distributions. If this was part of a batch job (e.g., 1,000 parameterized runs of LON-003), the aggregation waits for all runs before computing distributions.

### 3.2 The Taxonomy-to-Engine Field Mapping

Every field in the taxonomy schema from Section 1.6 maps to a specific engine component. This table is the authoritative reference for anyone implementing either side of the system:

| Taxonomy Field | Consumed By | How It Is Used |
|---|---|---|
| scenario_id | Registry + L4 | Primary key for all lookup and aggregation operations. |
| behavioral_requirement | Human documentation only | Not consumed by the engine. Guides test design and result interpretation. |
| category | L4 aggregation | Groups results for category-level pass rate analysis. |
| right_of_way | L3 Evaluation Monitor | Monitor uses this to validate that the ego vehicle's behavior was legally and situationally appropriate. |
| threat_direction | L3 NPC BT System | Informs which spatial coordinate frame the NPC's behavior tree operates in. |
| trigger_code | L2 + L3 NPC BT System | L2 looks up the BT from the Trigger Registry. L3 loads and executes it. |
| trigger_type + trigger_condition | L3 NPC BT System | The BT's root condition. Defines when the scenario's critical event is activated. |
| occlusion_state | L2 World Initialization | L2 places occluding objects (parked vehicles, walls) in the world at positions that produce the specified occlusion geometry. |
| success_criteria | L3 Evaluation Monitor | Monitor evaluates these at every tick. Run terminates with PASS when all are satisfied. |
| failure_conditions | L3 Evaluation Monitor | Monitor evaluates these at every tick. Run terminates immediately with FAIL when any is met. |
| param_profile | L2 Parameterization Engine | Defines the sampling ranges for all variable parameters. |
| crash_anchor | L4 Reporting | Used to group results by real-world crash type for safety case documentation. |
| version | L1 Registry | Used for schema migration. The engine rejects ScenarioTemplates with incompatible versions. |

### 3.3 The Three Things That Must Stay Separate

The most common architecture mistake when building a system like ORION is conflating things that must remain separate. These three separations are non-negotiable:

> **CRITICAL** — Violation of any of these separations will create a system that is difficult to maintain, impossible to reproduce, and unreliable as a test oracle.

#### Separation 1: Scenario Definition vs. Scenario Parameterization

The scenario definition (what the scenario is) lives in the Registry and never changes for a given version. The parameterization (what the specific run looks like) is generated fresh for each run. These must be separate data structures (ScenarioTemplate vs. ScenarioInstance). Never mutate a ScenarioTemplate with run-specific values.

#### Separation 2: NPC Scripted Initial Behavior vs. NPC Reactive Runtime Behavior

Every NPC has two behavioral phases. Phase 1 (pre-trigger): the NPC follows a scripted initial trajectory set up by parameterization. Phase 2 (post-trigger): the NPC executes its Behavior Tree reactively. These phases must be clearly defined in the BT. The mistake to avoid: making Phase 1 reactive (NPC reacts before the trigger fires). If the NPC starts reacting to ego before the trigger condition is met, the scenario's trigger_condition threshold becomes meaningless.

#### Separation 3: Pass/Fail Evaluation vs. Performance Grading

A run has a binary verdict: PASS or FAIL (or INCONCLUSIVE). But within a passing run, the AV may have performed better or worse. A scenario passed with a 3.5-second TTC at intervention is better than one passed with a 2.6-second TTC. These are different things: the verdict tells you if the AV is safe enough; the metric trace tells you how much safety margin it had. The evaluation layer must maintain both and never collapse graded performance into a binary verdict.

### 3.4 The Feature That the Original Implementation Got Right (and How to Keep It)

The Continuous Weather Evolution and Adversarial NPC micro-logic from the original implementation document are good ideas. They must simply be implemented in the right layer:

- Continuous Weather Evolution: This is a parameterization-time decision (the degradation schedule is fixed before the run starts) but a runtime effect (the physics world and sensor model update every tick). The schedule is part of environment_config in the ScenarioInstance. The execution engine reads the schedule and applies it. The taxonomy's param_profile for each scenario should specify whether weather evolution is allowed (some scenarios require stable conditions by definition — e.g., sensor calibration tests).
- Adversarial NPC micro-logic: This is a Behavior Tree feature, not a scenario definition feature. The Behavior Trees in the Trigger Registry can be as sophisticated as needed. The key constraint is: the BT must be deterministic given the same world state. Stochastic BTs break reproducibility. If you want variability in NPC behavior, introduce it through parameterization (e.g., randomize the pedestrian's panic probability), not through non-deterministic BT execution.

### 3.5 The Correct Interpretation of 'Infinite Scenarios'

The original taxonomy claimed ORION generates 'infinite scenarios' through parameterization. This claim is correct but needs to be understood precisely.

> ◆ KEY INSIGHTThe taxonomy defines a finite set of distinct behavioral requirements. Parameterization generates infinite instances of each. The correct claim is: ORION has N distinct behavioral test scenarios (where N is the size of your taxonomy) and each scenario can be instantiated in M different parameterized configurations (where M is effectively infinite due to continuous parameter ranges). The '200 scenarios' in the original document was counting parameterization instances as if they were distinct scenarios. The actual number of distinct behavioral requirements in a rigorous taxonomy is closer to 60–120.

This distinction matters for safety case documentation. A regulator or safety auditor will ask: 'What distinct behavioral requirements have you tested?' Not: 'How many random parameter combinations have you tried?' The answer to the first question is your taxonomy size. The answer to the second is your test run count.

> APPENDIX — REFERENCE CHECKLISTS

## Appendix A: Scenario Acceptance Checklist

Before adding any scenario to the ORION taxonomy, it must pass all of the following checks. If any check fails, the scenario is not ready.

| # | Check | Pass Condition |
|---|---|---|
| 1 | Unique behavioral requirement | No existing scenario in the registry requires the same behavioral response from the ego vehicle under the same conditions. |
| 2 | Threat agent fully specified | Threat agent has: type, action, compliance status, and trajectory description. 'Aggressive Driver' alone does not pass. |
| 3 | Pass/fail criteria are measurable | Every success criterion and failure condition can be evaluated by software with no human judgment required. |
| 4 | Trigger condition is precise | Trigger uses a numeric threshold with a unit. 'When ego is close' does not pass. 'When ego TTC < 3.2s' passes. |
| 5 | No weather as taxonomy axis | The scenario does not create variants by changing weather. Weather is in param_profile, not in the scenario definition. |
| 6 | Physical plausibility | All actor combinations can coexist in the road topology. No on-ramp merges in parking lots. |
| 7 | Engine trigger code assigned | A TRIGGER:: code has been assigned and the corresponding BT exists in the Trigger Registry. |
| 8 | Crash anchor or explicit justification | Scenario maps to a real crash type, or there is explicit written justification for including it. |
| 9 | Parameterization profile complete | All variable parameters have defined ranges appropriate to the road class and scenario type. |
| 10 | Inconclusive case handled | The scenario definition specifies what a timeout/inconclusive result means for this scenario specifically. |

## Appendix B: What the Final Taxonomy Will Look Like

When the ORION taxonomy is correctly built using this guide, it will have these structural properties:

- Scenario count: Between 60 and 120 entries. If it is fewer than 60, coverage is insufficient. If it is more than 120, there are likely duplicates.
- ID format: All IDs follow [CATEGORY_CODE]-[SEQUENCE]. Six category codes: LON, LAT, INT, VRU, EMG, MLT.
- Distribution across categories: No category should have fewer than 8 scenarios or more than 30. If Intersection has 45 and Lateral has 3, the taxonomy is unbalanced.
- Weather: Not present as a taxonomy column. Present only in param_profile for each scenario.
- Every scenario has a TRIGGER:: code: This is the visible contract with the implementation. No scenario without a trigger code is in the taxonomy.
- Every scenario has a crash anchor or justification: No scenario is included just because it seems like a good idea.
- The table format: Each scenario occupies multiple lines in the source document (because the full schema requires it). A three-column table with ID, maneuver, and weather is not a taxonomy. It is a spreadsheet.

## Appendix C: What the Final Implementation Will Look Like

When the ORION implementation is correctly built using this guide, it will have these structural properties:

- Four distinct layers: L1 Registry, L2 Parameterization Engine, L3 Dynamic Execution Engine, L4 Evaluation. Each layer has a single responsibility and communicates with adjacent layers only through defined data schemas.
- Three data schemas as layer interfaces: ScenarioTemplate (L1→L2), ScenarioInstance (L2→L3), SimulationResult (L3→L4). These three schemas are the architecture's skeleton.
- Deterministic replay by seed: Any SimulationResult can be re-run by providing its run_id + seed to the Parameterization Engine, which will reproduce the exact same ScenarioInstance.
- Binary verdict + metric trace: Every completed run produces both. The verdict is for pass/fail tracking. The metric trace is for performance analysis. Neither replaces the other.
- Behavior Trees in a versioned Trigger Registry: NPC programs are not embedded in scenario definitions. They live separately and are referenced by TRIGGER:: codes. Updating a BT does not require modifying the taxonomy.
- Weather evolution as a scheduled, deterministic effect: Not random. The degradation schedule is set at parameterization time and applied deterministically by the engine.
- Sub-100ms p95 render latency: Not 'zero lag'. A measurable, testable target.

End of ORION Design Guide
---

# Appendix D: Additional Master Scenario Templates

Section 1.8 above gives three worked templates (LON-003, INT-005, VRU-008). These three
covered the remaining categories in the original taxonomy document and are preserved here in
the same schema. Together the six cover all six behavioral categories.

## SCN-ID: LAT-002
**Scenario Name**: Adjacent Vehicle Cut-in on Highway
**Behavioral Category**: Lateral Control
**Behavioral Requirement**: The ego vehicle must maintain its lane and respond to a sudden cut-in from an adjacent lane by adjusting speed or position to avoid collision.

| Field | Definition |
| :--- | :--- |
| **Threat Agent** | Adjacent vehicle traveling at +5 km/h relative to ego. Non-compliant (cutting in without safe gap). |
| **Ego ROW Status** | Ego has ROW in its lane. |
| **Threat Direction** | Merging (Lateral cut-in from side). |
| **Trigger Type** | Proximity-triggered. |
| **Trigger Condition** | Adjacent vehicle initiates lane change when ego's longitudinal gap to it is < 10m. |
| **Occlusion State** | Full visibility. |
| **Success Criterion** | No contact. Ego restores >= 2.0s headway within 5 seconds of the cut-in completion. |
| **Failure Conditions** | Collision; lane departure to avoid collision; heavy emergency braking > 0.6g. |
| **Parameterization Profile** | Ego V: 80-120 km/h. Initial Lateral distance: 3.5m. Weather Allowed: All. |
| **Crash Anchor** | NHTSA Pre-Crash Typology: Type 45 (Changing lanes, same direction). |
| **Engine Trigger Code** | `TRIGGER::LAT_ADJACENT_CUT_IN_V1` |

## SCN-ID: EMG-004
**Scenario Name**: Vehicle Control Loss — Sudden Black Ice Event
**Behavioral Category**: Emergency/Anomalies
**Behavioral Requirement**: The ego vehicle must detect severe friction loss during a maneuver and adjust its steering and speed rapidly to prevent a total spinout and remain within road boundaries.

| Field | Definition |
| :--- | :--- |
| **Threat Agent** | The environment itself (Black Ice). Non-adversarial. |
| **Ego ROW Status** | N/A. |
| **Threat Direction** | N/A. |
| **Trigger Type** | Event-triggered (Geofenced area). |
| **Trigger Condition** | Ego enters a predefined 50m road segment where friction drops instantly. |
| **Occlusion State** | Black ice is visually occluded (invisible to cameras, must be inferred via physics/slip). |
| **Success Criterion** | Ego survives the patch without leaving the designated lane or exceeding 15 degrees of yaw slip angle. |
| **Failure Conditions** | Departure from lane; complete spinout (>30 degrees yaw divergence); collision with barrier. |
| **Parameterization Profile** | Ego V: 40-80 km/h. Road Curvature: Straight to mild curve. **Weather Required: Freezing/Ice conditions.** |
| **Crash Anchor** | NHTSA Pre-Crash Typology: Type 01 (Control loss without prior action). |
| **Engine Trigger Code** | `TRIGGER::EMG_ICE_LOSS_V1` |

## SCN-ID: MLT-007
**Scenario Name**: Complex Multi-Agent — Construction Zone Stop with Tailgating Follower
**Behavioral Category**: Multi-Agent
**Behavioral Requirement**: The ego vehicle must brake for a static construction obstacle while maintaining a sufficient deceleration curve to prevent being rear-ended by an aggressive tailgater.

| Field | Definition |
| :--- | :--- |
| **Threat Agent** | Agent 1: Static construction barrier (compliant). Agent 2: Following vehicle close behind ego (non-compliant / aggressive). |
| **Ego ROW Status** | N/A (Yielding to obstacle). |
| **Threat Direction** | Agent 1: Same direction (ahead). Agent 2: Rear. |
| **Trigger Type** | Continuous (Agent 2) + Proximity (Agent 1). |
| **Trigger Condition** | Barrier becomes visible at 60m. Tailgater maintains 0.8s TTC continuously. |
| **Occlusion State** | Full visibility. |
| **Success Criterion** | Ego stops before the barrier without being hit from behind. Deceleration does not exceed 0.4g (forcing smooth braking to prevent rear-end). |
| **Failure Conditions** | Collision with barrier; rear-ended by tailgater; sudden panic braking > 0.6g. |
| **Parameterization Profile** | Ego V: 60-80 km/h. Tailgater TTC: 0.5s-1.2s. Weather Allowed: Clear/Rain. |
| **Crash Anchor** | Derived (Multi-Agent composition of Type 11 & Type 14). |
| **Engine Trigger Code** | `TRIGGER::MLT_TAILGATE_AND_STOP_V1` |

---
