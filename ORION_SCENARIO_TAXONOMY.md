# ORION Scenario Taxonomy

This document defines the strict, behavioral taxonomy for the ORION platform. It discards combinatory enumeration (mixing weather and road types) in favor of one absolute rule: **One Scenario = One Behavioral Requirement**.

## 1. Taxonomy Design Principles

### The Foundational Rule
Every scenario in the taxonomy corresponds to exactly **one behavioral requirement**. If two scenarios require the same behavioral response, they are the same scenario with different parameters.

### Where Weather & Lighting Go
Weather, lighting, and sensor degradation are **NOT** scenario axes. They are **parameterization modifiers**. A pedestrian crossing under rain is the same behavioral challenge as one under a clear sky. Modifiers are defined exclusively in the `Parameterization Profile`.

---

## 2. The Six Behavioral Challenge Categories (60-120 Core Scenarios)

1. **Longitudinal Control (`LON`)**: Management of speed, following distance, and braking. Threat from directly ahead. (e.g., Lead vehicle emergency stop)
2. **Lateral Control (`LAT`)**: Management of lateral position, lane changes, and encroachment responses. (e.g., Adjacent vehicle encroaching)
3. **Intersection Negotiation (`INT`)**: Safe analysis and yielding governed by right-of-way rules at junctions. (e.g., Unprotected left turns)
4. **Vulnerable Road User (`VRU`)**: Interaction with pedestrians, cyclists, child models, and irregular dynamic obstacles.
5. **Emergency/Anomalies (`EMG`)**: Extreme out-of-distribution events requiring irregular traffic deviation. (e.g., Wrong-way driver, scattered debris)
6. **Multi-Agent (`MLT`)**: Orchestration of multiple conflicting agents interacting dynamically simultaneously. 

---

## 3. Strict Scenario Definition Schema

Every scenario adheres rigorously to the following required properties. If a scenario cannot fill out these fields, it is rejected from the taxonomy.

*   `SCN-ID`: Formatted as `[CATEGORY]-[SEQ]`.
*   `Scenario Name`: Threat and response.
*   `Behavioral Category`: One of the six core categories.
*   `Behavioral Requirement`: One sentence test objective.
*   `Threat Agent`: Explicit description of the violating or compliant agent.
*   `Ego Right-of-Way Status`: Does the AV have ROW?
*   `Threat Direction`: Same/Oncoming/Crossing/Rear/Merge.
*   `Trigger Type`: Event, Proximity, Continuous, Time.
*   `Trigger Condition`: Exact numeric boundary conditions.
*   `Occlusion State`: Hidden vs partially visible.
*   `Success Criterion`: Mathematically provable passing margin.
*   `Failure Conditions`: Exhaustive fail states.
*   `Parameterization Profile`: Mappable limits for Weather, Speeds, Modifiers.
*   `Crash Anchor`: Real-life database tie.
*   `Engine Trigger Code`: Identifier for Dynamic Execution NPC Behavior tree.

---

## 4. Master Scenario Templates

### SCN-ID: LON-003
**Scenario Name**: Lead Vehicle Emergency Stop — Rear-End Avoidance with Occluded Cause
**Behavioral Category**: Longitudinal Control
**Behavioral Requirement**: The ego vehicle must detect and respond to a sudden full stop by the lead vehicle with sufficient deceleration to avoid contact.

| Field | Definition |
| :--- | :--- |
| **Threat Agent** | Lead vehicle decelerating at 0.9g from 80 km/h to 0. Compliant (not adversarial). |
| **Ego ROW Status** | N/A (Same-direction following). |
| **Threat Direction** | Same direction (ahead of ego). |
| **Trigger Type** | Proximity-triggered. |
| **Trigger Condition** | Lead vehicle brakes when Ego's TTC reaches 2.5s - 4.0s. |
| **Occlusion State** | Lead vehicle visible. Cause of stop (30m ahead) is fully occluded by the lead vehicle. |
| **Success Criterion** | No contact. Ego decelerates >= 0.3g within 0.8 seconds and stops within bounds. |
| **Failure Conditions** | Collision; lane departure; deceleration onset > 2.0s delay. |
| **Parameterization Profile** | Ego V: 60-100km/h. Distance: 20-60m. Weather Allowed: All. Road: Highway, Rural. |
| **Crash Anchor** | NHTSA Pre-Crash Typology: Type 14. |
| **Engine Trigger Code** | `TRIGGER::LON_EMERGENCY_STOP_V1` |

### SCN-ID: INT-005
**Scenario Name**: Unprotected Left Turn — Yield to Oncoming Traffic Gap Acceptance
**Behavioral Category**: Intersection Negotiation
**Behavioral Requirement**: The ego vehicle must wait for a safe gap in oncoming traffic before completing an unprotected left turn without causing oncoming vehicles to brake.

| Field | Definition |
| :--- | :--- |
| **Threat Agent** | 2-4 oncoming vehicles, road speed. Compliant (not yielding). |
| **Ego ROW Status** | Ego must yield. |
| **Threat Direction** | Oncoming (crossing path during turn). |
| **Trigger Type** | Continuous. |
| **Trigger Condition** | Constant threat until ego acts. |
| **Occlusion State** | Full visibility. *(Occluded variant exists as INT-005b)*. |
| **Success Criterion** | Completes turn without causing oncoming decel >0.1g. Accepts gap >=4.0s TTC. Ego does not block intersection for more than 15 seconds. |
| **Failure Conditions** | Collision; entering turn with TTC <2.5s; >30s timeout blocked. |
| **Parameterization Profile** | Oncoming V: 30-80km/h. Gap: random Poisson 5s mean. Weather Allowed: All. |
| **Crash Anchor** | NHTSA Pre-Crash Typology: Type 2. |
| **Engine Trigger Code** | `TRIGGER::INT_UNPROTECTED_LEFT_V1` |

### SCN-ID: VRU-008
**Scenario Name**: Occluded Pedestrian — Child Entering Road from Between Parked Cars
**Behavioral Category**: VRU Interaction
**Behavioral Requirement**: The ego vehicle must detect and yield to a pedestrian who enters the road from a fully occluded position with minimal TTC.

| Field | Definition |
| :--- | :--- |
| **Threat Agent** | Child profile pedestrian (1.0m height, 1.0 m/s walking speed). Non-compliant (jaywalking). |
| **Ego ROW Status** | Ego has ROW, safety obligation overrides. |
| **Threat Direction** | Crossing lateral. |
| **Trigger Type** | Proximity-triggered. |
| **Trigger Condition** | Pedestrian crossing begins when Ego is 15-25m away from parked vehicle gap. |
| **Occlusion State** | Full occlusion until trigger. |
| **Success Criterion** | No contact. Ego stops or decelerates below 5 km/h before crossing path. |
| **Failure Conditions** | Collision; entering cross line >15 km/h; failure to detect within 0.5s of first visibility. |
| **Parameterization Profile** | Ego V: 20-50 km/h. Walk Speed: 0.8-1.5 m/s. Gap Width: 0.8-1.5m. Weather Allowed: All. |
| **Crash Anchor** | Euro NCAP AEB VRU Test: Child Crossing — Occluded. |
| **Engine Trigger Code** | `TRIGGER::VRU_OCCLUDED_CHILD_V1` |

### SCN-ID: LAT-002
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

### SCN-ID: EMG-004
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

### SCN-ID: MLT-007
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

## Appendix A: Scenario Acceptance Checklist
Before establishing a new scenario class, ensure the following guarantees:
1. Unique behavioral requirement.
2. Threat agent fully specified (compliance behavior + action).
3. Pass/Fail criteria are mathematically measurable.
4. Trigger condition is precise with numeric thresholds.
5. No Weather or Time-of-Day are used as taxonomy classification axes.
6. Physical Plausibility strictly checked.
7. Engine Trigger Code explicitly designated.
8. Crash Anchor explicitly cited.
9. Parameterization Profile bounds rigorously generated.
10. Inconclusive (Timeout) cases gracefully handled.
