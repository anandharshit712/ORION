# Autonomous Driving Simulation Platforms — Technical Survey

**Compiled**: 2025 · **Status**: Reference material, not a governing document

> Markdown consolidation of `autonomous_driving_simulation_platforms.docx` (archived under
> `docs/archive/`). Ten platforms surveyed for scenario taxonomy, counts and differentiation
> basis. Background research for the scenario taxonomy in [../ARCHITECTURE.md](../ARCHITECTURE.md)
> and the ratings in [../MARKET.md](../MARKET.md). Nothing here constrains implementation.

---

Autonomous Driving

Simulation Platforms

Scenario Taxonomy, Counts & Differentiation Basis

Platforms Covered

1. CARLA + ScenarioRunner

2. nuPlan (Motional)

3. Waymax (Waymo)

4. LGSVL Simulator + Apollo Dreamland

5. Eclipse SUMO

6. Microsoft AirSim

7. MetaDrive

8. Highway-Env (Farama Foundation)

9. PTV VISSIM

10. IPG CarMaker

Document compiled for platform design reference | 2025

## 1. CARLA + ScenarioRunner

CARLA (Car Learning to Act) is the most widely used open-source autonomous driving simulator for research. Built on Unreal Engine 4, it is developed by the Computer Vision Center (CVC) at the Universitat Autonoma de Barcelona. ScenarioRunner is the companion module for defining, loading, and executing traffic scenarios within CARLA.

### 1.1 Platform Overview

| Maintainer | Computer Vision Center (CVC), UAB — open-source community |
|---|---|
| Engine | Unreal Engine 4 (photorealistic rendering) |
| License | MIT (CARLA) / MIT (ScenarioRunner) |
| Primary Use | Full-stack AV research: perception, planning, control, end-to-end |
| Scenario Type | Synthetic, rule-based — hand-crafted Python classes or OpenSCENARIO XML |
| Scenario Count | ~30 named types in ScenarioRunner; 17 standardized in the CARLA Leaderboard (from NHTSA pre-crash typology); infinite parameterized variants possible |
| Rendering | Full Unreal Engine — high-fidelity photorealistic visuals, day/night, weather |
| Sensor Suite | RGB camera, depth, semantic segmentation, instance segmentation, LiDAR, Radar, GNSS, IMU, collision/lane-invasion detectors |
| Standards Support | OpenSCENARIO 1.x and 2.0, OpenDRIVE maps, ASAM standards |
| Key Integrations | ROS/ROS2 bridge, SUMO co-simulation, Scenic probabilistic DSL, Apollo/Autoware |
| Available Maps | Town01–Town15 (procedural + manual), custom maps via RoadRunner + OpenDRIVE import |

### 1.2 Scenario Design Philosophy

CARLA scenarios are explicitly scripted behavioral programs. Each scenario is a Python class (inheriting from BasicScenario) or an OpenSCENARIO XML file. A scenario defines: (1) initial world state — vehicle positions, pedestrian positions, weather; (2) behavioral tree of all non-ego actors; (3) success/failure criteria. Scenarios are run by ScenarioRunner against a live CARLA server.

The 17 CARLA Leaderboard scenarios were derived directly from the NHTSA Pre-Crash Typology — a classification of real crash types from U.S. crash databases. This means every leaderboard scenario maps to a documented real-world crash pattern.

### 1.3 Complete Scenario List

| # | Scenario Name | Description & Differentiating Factor |
|---|---|---|
| 01 | Control loss (no prior action) | Ego loses control due to bad road conditions. Differentiator: no precipitating event — control loss is spontaneous, testing recovery behavior from an unexpected slide. |
| 02 | Unprotected left turn | Ego turns left at intersection while oncoming traffic approaches. Differentiator: yielding obligation is on ego — tests gap acceptance under oncoming flow. Occurs at both signalized and unsignalized junctions. |
| 03 | Right turn with crossing traffic | Ego turns right while a vehicle crosses from the left. Differentiator: conflict comes from crossing direction (lateral), not from oncoming flow. |
| 04 | Crossing negotiation (unsignalized) | Ego and another vehicle reach an unsignalized intersection simultaneously. Differentiator: no traffic control — tests negotiation and right-of-way inference between two vehicles. |
| 05 | Red light runner | Ego proceeds on green but crossing vehicle runs red. Differentiator: the conflicting agent is in violation — ego has right of way but must still avoid the collision. |
| 06 | Crossing with oncoming bicycles | Ego turns at intersection while bicycles cross. Differentiator: conflicting actor is a vulnerable road user (bicycle), not a motor vehicle — smaller profile, different speed/behavior. |
| 07 | Highway merge from on-ramp | Ego enters highway from on-ramp into moving traffic. Differentiator: ego is the merging agent, must find a gap in high-speed traffic. |
| 08 | Highway cut-in from on-ramp | Another vehicle merges into ego's lane from on-ramp. Differentiator: ego is on the main road and must react to an agent merging into its path — opposite role from Scenario 07. |
| 09 | Static cut-in | Vehicle merges into ego's lane from a lane of stopped traffic. Differentiator: cut-in comes from a static traffic queue, not from an on-ramp. |
| 10 | Slow moving hazard (same direction) | Slow vehicle partially blocks lane, ego must maneuver next to same-direction traffic. Differentiator: traffic adjacent to maneuver moves in the same direction as ego. |
| 10a | Slow moving hazard (opposite direction) | Slow hazard at lane edge, adjacent traffic moves opposite to ego. Differentiator: oncoming traffic during maneuver increases risk. |
| 11 | Yield to emergency vehicle | Emergency vehicle approaches from behind. Ego must clear a path. Differentiator: actor is an emergency vehicle with right-of-way override — legal and safety behavior tested. |
| 12 | Obstacle in lane (same-direction lane change) | Blocked lane requires change into same-direction traffic. Differentiator: ego lane change is into traffic flowing same way — lower speed differential. |
| 12a | Obstacle in lane (opposite-direction lane change) | Blocked lane requires change into oncoming traffic lane. Differentiator: lane change is into oncoming flow — much higher risk scenario. |
| 13 | Door obstacle | Parked vehicle opens door into ego's lane. Differentiator: obstacle appears suddenly at very short range from a stationary vehicle — reaction time is extremely limited. |
| 14 | Vehicle invading lane on bend | Oncoming vehicle crosses into ego's lane due to its own obstacle. Differentiator: conflict occurs on a curved road where visibility is reduced. |
| 15 | Emergency brake due to leading vehicle | Leading vehicle decelerates suddenly. Differentiator: longitudinal-only challenge — pure braking or avoidance required, no lateral threat. |
| 16 | Obstacle avoidance (no prior action) | Unexpected entity (debris, animal, fallen object) appears in road. Differentiator: no warning, no other vehicles — pure perception-and-react test. |
| 17 | Follow leading vehicle (stops ahead) | Ego follows a leader that eventually stops. Differentiator: baseline longitudinal following behavior — simplest scenario, used as foundation for more complex variants. |
| 18 | Follow leading vehicle (hidden obstacle) | Ego follows a leader that stops due to a hidden obstacle further ahead. Differentiator: ego cannot see reason for stop; must infer hazard from leader behavior alone. |
| 19 | Stationary object crossing | Stationary cyclist/pedestrian in road blocks path. Differentiator: blocking agent is static — ego must stop and wait rather than avoid a moving threat. |
| 20 | Dynamic object crossing | Cyclist/pedestrian dynamically crosses ego's path. Differentiator: crossing agent is moving — timing and trajectory prediction critical. Agent clears road after crossing. |
| 21 | Signalized intersection right turn | Ego turns right at a signalized intersection while another vehicle crosses straight from a lateral direction. Differentiator: both ego and conflicting vehicle have green light on different approaches. |
| 22 | Lane change with obstacle ahead | Adversary in adjacent lane accelerates, then cuts left in front of a stationary obstacle. Differentiator: three-actor coordination — ego, active lane-changer, and static obstacle all interact. |

### 1.4 Dimensions of Differentiation

Scenarios within CARLA differ along these axes. Understanding these dimensions is critical for designing your own scenario taxonomy:

| Dimension | How Scenarios Differ |
|---|---|
| Road geometry | Intersection vs highway vs residential vs rural bend vs parking area. Road type determines which maneuvers are relevant and which conflicts can arise. |
| Conflicting actor type | Motor vehicle vs cyclist vs pedestrian vs emergency vehicle. Actor type changes size, speed, trajectory predictability, and legal right-of-way rules. |
| Actor behavior | Stationary vs moving; compliant vs non-compliant (e.g., red-light running). Non-compliant actors test robustness to rule violations. |
| Ego maneuver | Straight, left turn, right turn, lane change, merge, parking. Each maneuver creates a different set of potential conflicts. |
| Traffic control | Signalized vs unsignalized; green/yellow/red; stop sign vs yield vs bare intersection. Control type changes right-of-way and negotiation requirements. |
| Conflict direction | Oncoming (head-on) vs crossing (lateral) vs rear-end vs merging. The geometric relationship between ego and the conflicting agent determines the type of response needed. |
| Environment | Weather (clear/rain/fog/wet), time of day (noon/sunset/night/dawn), road surface condition. Same behavioral scenario under different conditions tests perception and decision-making robustness. |
| Triggering condition | Event-based (actor appears at distance X) vs time-based vs velocity-based. Controls when the critical moment occurs in the scenario. |
| Obstacle state | Static obstacle (construction site, parked car) vs dynamic (moving vehicle, pedestrian). Dynamic obstacles require trajectory prediction; static ones require detection and avoidance planning. |

The key insight for building a new platform: each new scenario is created by changing one or more of these dimensions while holding others constant. For example, Scenarios 07 and 08 both involve a highway on-ramp but differ in ego role (merging vs. receiving). Scenarios 12 and 12a both involve an obstacle-forced lane change but differ in conflict direction (same-direction vs. oncoming traffic).

## 2. nuPlan (Motional)

nuPlan is the world's first closed-loop ML-based planning benchmark for autonomous vehicles, developed by Motional. Unlike synthetic simulators, nuPlan's scenarios are mined from real-world driving data collected across four cities. It is designed specifically for benchmarking motion planning algorithms, not perception or full-stack systems.

### 2.1 Platform Overview

| Maintainer | Motional (joint venture: Aptiv + Hyundai) |
|---|---|
| License | CC BY-NC-SA 4.0 (non-commercial research) |
| Primary Use | ML-based motion planning evaluation; open-loop and closed-loop benchmarking |
| Scenario Type | Real-world data-driven — scenarios mined and auto-labeled from logged driving data |
| Scenario Count | 73 unique scenario types; 15,910 log files; 1,282 hours total; nuPlan mini: 67 types in 7h |
| Cities | Las Vegas (NV), Boston (MA), Pittsburgh (PA), Singapore |
| Data Volume | 1,282 hours in full dataset; 128 hours with raw sensor data |
| Scenario Origin | Auto-labeled using vehicle speed, state transitions, and traffic light status from logs |
| Simulation Mode | Open-loop (ego follows ground truth) and closed-loop (ego follows planner; reactive IDM agents) |
| Key Metrics | ADE, FDE, collision rate, comfort metrics, traffic compliance, route completion |
| Framework | Python-based devkit with Hydra config; nuBoard for visualization; Pytorch Lightning for training |

### 2.2 How Scenarios Are Created

nuPlan does not hand-craft scenarios. Instead, a scenario taxonomy is defined with rules, and mining algorithms scan all 15,910 logs to find instances matching each rule. Rules are based on low-level attributes:

- Vehicle speed thresholds: e.g., high jerk = jerk > X m/s³ for > Y seconds
- State transitions: e.g., stopped-to-moving, moving-to-stopped, lane-change indicator on then off
- Traffic light status: encoded into lane connectors on the semantic map
- Map context: presence of intersection polygon, PUDO zone, construction area, speed bump in map layer
- Agent interactions: number of agents within radius, presence of pedestrians, relative velocities

This means every scenario instance is a real, human-driven event extracted from logs — not a simulation. This makes coverage realistic but makes it impossible to guarantee coverage of specific rare events without collecting more data.

### 2.3 Selected Scenario Types (of 73 total)

| # | Scenario Name | Description & Differentiating Factor |
|---|---|---|
| 01 | Lane change | Ego changes lanes on a multi-lane road. Differentiated by: presence/absence of adjacent traffic, gap size, speed differential, triggered by lane blockage vs. voluntary. |
| 02 | Unprotected left turn | Ego turns left without a dedicated green arrow. Differentiated by: oncoming traffic density, gap size, intersection geometry. |
| 03 | Tailgating | Ego follows a vehicle at a dangerously short headway. Differentiated from normal following by abnormally small time-to-collision values. |
| 04 | High-velocity overtake | Ego overtakes another vehicle at high speed. Differentiated by speed differential and lateral clearance. |
| 05 | Double-parked car | A parked vehicle blocks part of ego's lane. Differentiated by available gap in adjacent lane and speed of adjacent traffic. |
| 06 | Jaywalking pedestrian | Pedestrian crosses outside of designated crossing. Differentiated by trajectory angle, prediction difficulty, and ego speed at encounter. |
| 07 | Stop-controlled intersection | Ego must stop and yield at a stop sign. Differentiated by cross-traffic density and visibility. |
| 08 | Traffic light intersection | Ego navigates a signalized intersection. Differentiated by phase state (green/yellow/red) and crossing traffic behavior. |
| 09 | Pickup/dropoff zone (PUDO) | Ego handles a vehicle stopped in a PUDO zone. Differentiated by available space for passing and duration of blockage. |
| 10 | Construction zone | Road narrowing or detour due to construction. Differentiated by taper length, presence of workers, and speed limit change. |
| 11 | Abrupt braking | Ego or a lead vehicle brakes hard. Differentiated by headway at event onset and ego's following distance. |
| 12 | Speed bump | Ego traverses a speed bump. Differentiated by approach speed and bump height/profile. |
| 13 | High-jerk maneuver | Ego executes a sudden lateral or longitudinal move. Differentiated from normal driving by jerk metric exceeding threshold. |
| 14 | On intersection | Ego is within intersection boundaries. A broad label capturing all intersection-crossing events regardless of type. |
| 15 | Yielding | Ego yields to another road user. Differentiated by who/what is being yielded to: pedestrian, cyclist, cross-traffic. |
| 16 | Vehicle following | Ego follows a leading vehicle at normal headway. The baseline scenario; differentiated from tailgating by headway value. |
| 17 | Lane merging | Two lanes merge into one. Differentiated by which vehicle has right of way and relative speeds. |
| 18 | Crossing on green | Ego proceeds through a green light. Differentiated by presence/absence of vehicles entering against the signal. |
| 19 | Mixed speed profile | Ego experiences varied stop-and-go speeds within a scenario. Differentiated by frequency of speed changes. |
| 20 | Roundabout navigation | Ego enters, traverses, and exits a roundabout. Differentiated by roundabout size and density of circulating traffic. |

### 2.4 Dimensions of Differentiation

| Dimension | How Scenarios Differ |
|---|---|
| Ego behavior type | What the ego vehicle is doing: following, yielding, turning, merging, stopping. Scenarios are classified primarily by ego action. |
| Agent interaction type | What other agents are doing: parked (double-park), crossing (jaywalking), stopping (emergency stop), following closely (tailgating). |
| Map context | Whether ego is in an intersection, PUDO zone, construction area, or open road at the time of the event. |
| Traffic control state | Traffic light phase, stop sign presence. Captures compliance situations and signal-related decisions. |
| Speed dynamics | Speed profile characteristics: abrupt braking (high decel), high-velocity overtake (high relative speed), speed bump (low speed over obstacle). |
| City | Las Vegas, Boston, Pittsburgh, Singapore have different traffic patterns, road layouts, and agent behavior norms. Same scenario type in different cities is effectively a different distribution. |
| Jerk / comfort metrics | High-jerk maneuvers form their own scenario class, capturing scenarios where smooth driving is violated regardless of conflict type. |

## 3. Waymax (Waymo)

Waymax is a lightweight, hardware-accelerated, data-driven simulator developed by Waymo for multi-agent autonomous driving research. It is written entirely in JAX, enabling GPU/TPU-based simulation at scale. Unlike CARLA or nuPlan, Waymax has no fixed scenario taxonomy — its diversity comes from the sheer scale of the Waymo Open Motion Dataset (WOMD).

### 3.1 Platform Overview

| Maintainer | Waymo Research |
|---|---|
| License | Waymax License Agreement (non-commercial use) |
| Framework | JAX — full GPU/TPU acceleration; JIT compilation; vectorized parallel environments |
| Primary Use | Behavior research: planning, prediction, sim agents, RL at scale |
| Scenario Type | Data-driven — real-world driving logs from WOMD; no fixed taxonomy |
| Scenario Count | 100,000+ trajectory snippets (WOMD training set); 7.64M unique object instances; 250h+ of data |
| Scenario Duration | 9 seconds per snippet (recorded at 10 Hz = 91 frames) |
| Cities | Multiple dense urban environments (Waymo's operational cities) |
| Objects per Scenario | Up to 128 per scene (vehicles, pedestrians, cyclists) |
| Agent Models | Log playback (replay logs exactly) or IDM route-following (reactive) |
| Metrics | Log divergence, collision, offroad, wrong-way, kinematic infeasibility |

### 3.2 How Scenarios Are Created

Waymax does not create scenarios manually or via mining rules. Scenarios are the raw driving logs from the Waymo Open Motion Dataset. Each scenario is initialized with:

- Static information: road graph (lanes, stop signs, crosswalks, speed limits) from the real-world HD map
- Dynamic initialization: first 1 second of logged trajectory for all objects in scene
- Ground truth logs: remaining 8 seconds of all object trajectories, used for log playback or IDM model initialization

Diversity is entirely a function of where and when Waymo's sensor vehicles drove. No scenario is deliberately crafted. This is both a strength (naturalistic, uncurated realism) and a limitation (no guarantee of specific edge case coverage).

### 3.3 Scenario Differentiation Dimensions

Since Waymax has no named scenario types, differentiation must be described in terms of the properties that vary across the 100,000+ snippets:

| Dimension | How Scenarios Differ |
|---|---|
| Road graph topology | Each scenario has a unique real-world road graph. May include multi-way intersections, highway merges, roundabouts, urban grids, or suburban streets. |
| Object population | Agent count (up to 128), type mix (vehicles/pedestrians/cyclists), and spatial distribution vary per snippet. |
| Interaction density | Some snippets are sparse (highway, few agents); others are extremely dense (urban intersection, 30+ interacting agents). No explicit labeling. |
| Agent behavior (logged) | Each snippet captures real human driving behaviors including aggressive lane changes, hard braking, yielding, and non-compliant maneuvers. |
| Simulation mode | Log playback reproduces original behavior exactly. IDM mode makes agents reactive — they adjust speed based on ego's actions. Mode choice changes how the scenario unfolds. |
| Controlled agent identity | Any subset of agents can be designated as controlled (ego or multi-agent). The same snippet produces different research problems depending on which agent is controlled. |

Important note for platform design: Waymax's scenario granularity is the individual 9-second snippet, not a named type. Researchers typically filter snippets by custom criteria (e.g., 'contains a lane change event', 'involves a pedestrian') to construct task-specific training sets.

## 4. LGSVL Simulator + Apollo Dreamland

LGSVL Simulator is a high-fidelity simulator developed by LG Electronics built on Unity. It is designed specifically as an end-to-end testbed for autonomous driving stacks, with first-class integration with Baidu Apollo and Autoware. Apollo Dreamland is Baidu's web-based simulation platform built on top of the Apollo ADS stack.

### 4.1 Platform Overview

| Maintainer | LG Electronics (LGSVL) + Baidu (Apollo Dreamland) |
|---|---|
| Engine | Unity (LGSVL) — High Definition Render Pipeline (HDRP) |
| License | Apache 2.0 (LGSVL); Baidu Apollo license (Dreamland) |
| Primary Use | Full ADS stack testing (Apollo/Autoware integration), HIL/SIL/MIL, sensor simulation |
| Scenario Types | Two fundamental types: WorldSim (synthetic) and LogSim (log-replay from real sensors) |
| Scenario Count | ~200 pre-built scenario cases in Apollo Dreamland; unlimited via Python API scripting |
| Sensor Suite | RGB camera, fisheye camera, LiDAR, RADAR, ultrasonic, depth camera, semantic segmentation, ground truth 3D bounding boxes, IMU, GPS |
| Map Support | Apollo HD Map 5.0, Lanelet2, OpenDRIVE 1.4 (import and export) |
| ADS Interfaces | Apollo (CyberRT), Autoware (ROS/ROS2); custom bridges via plugin |
| Evaluation Metrics | 12 automatic grading metrics: traffic safety, road safety, rider comfort, traffic compliance |
| Cloud Support | Dreamland supports parallel cloud execution of millions of simulation miles per day |

### 4.2 Two Fundamental Scenario Types

#### WorldSim — Synthetic Scenarios

WorldSim scenarios are manually created with fully specified and deterministic obstacle behavior and traffic light state. They are designed to test specific, well-defined ADS behaviors in a controlled environment. Each WorldSim scenario specifies: road geometry, obstacle types and trajectories, traffic light phase sequences, and ego start/end conditions.

Strengths: Completely reproducible; obstacle behavior is exactly as specified; easy to create targeted regression tests. Weaknesses: Lack the complexity and unpredictability of real-world traffic.

#### LogSim — Log-Based Scenarios

LogSim scenarios replay real-world sensor data collected from Baidu's Apollo test vehicles. The sensor data (camera, LiDAR, radar) is replayed into the ADS stack exactly as it was recorded. Obstacles are perceived from the real sensor data, so perception results are realistic but non-deterministic.

Strengths: Captures genuine real-world complexity including partial occlusions, sensor noise, and unusual traffic behaviors. Weaknesses: Cannot change obstacle behavior; harder to create targeted tests; perceived obstacles may be fuzzy or missed.

### 4.3 Scenario Categories in Apollo Dreamland

| # | Scenario Name | Description & Differentiating Factor |
|---|---|---|
| 1 | Intersection w/ traffic light | Ego navigates a signalized intersection. Differentiated by: phase state at ego arrival, conflicting traffic on cross-street. |
| 2 | Stop sign intersection | Ego stops at stop sign, waits for clear gap, proceeds. Differentiated from signalized: no timing guarantee, must judge gap independently. |
| 3 | U-turn lane | Ego performs a U-turn in a dedicated turn lane. Differentiated by: oncoming traffic density, lane width. |
| 4 | Through lane (straight) | Ego drives straight through intersection or along arterial. Baseline scenario used to verify basic lane keeping and signal compliance. |
| 5 | T-junction | Three-way intersection. Ego turns left or right into main road. Differentiated from 4-way: only two approach directions for crossing traffic. |
| 6 | Curved lane | Ego navigates a significant road curve. Differentiated by: curvature radius, bank angle, presence of opposing traffic. |
| 7 | Pedestrian crossing | Pedestrian crosses at a marked crossing, with or without signal. Differentiated by: pedestrian speed, timing relative to ego, signal state. |
| 8 | Motor vehicle obstacle | Stopped or slow motor vehicle in ego's path. Differentiated from pedestrian: larger object, different stopping distance requirement. |
| 9 | Bicycle obstacle | Cyclist in or crossing ego's path. Differentiated: smaller than motor vehicle, less predictable trajectory, often in bike lane edge cases. |
| 10 | Narrow road passage | Road narrows, requiring careful lateral positioning or yielding to oncoming vehicles. Differentiated by: which direction has priority, width of gap. |
| 11 | Bare intersection | Unsignalized, unmarked intersection. Ego must infer right-of-way from road geometry alone. Tests rule-based inference in ambiguous situations. |
| 12 | Pull-over maneuver | Ego must pull over to the side of the road on instruction. Tests precise lateral control and situational awareness of road shoulder. |

### 4.4 Dimensions of Differentiation

| Dimension | How Scenarios Differ |
|---|---|
| WorldSim vs LogSim | The most fundamental split. WorldSim is deterministic and targeted; LogSim is realistic but fixed. No mid-ground is possible within a single scenario. |
| Road type | Intersection, U-turn lane, T-junction, curved lane, through lane, narrow road. Defines the spatial challenge. |
| Obstacle type | Pedestrian, bicycle, motor vehicle. Each has different size, speed, trajectory predictability, and legal status. |
| Traffic control state | Signal phase, stop sign, bare intersection. Determines how right-of-way is established. |
| Sensor configuration | LGSVL allows full sensor suite customization per scenario. Same behavior scenario with different sensors (e.g., camera-only vs LiDAR+camera) is effectively a different test. |
| ADS stack under test | Same scenario with Apollo vs Autoware produces different results due to algorithm differences. The scenario itself is the same; the SUT changes. |

## 5. Eclipse SUMO (Simulation of Urban MObility)

SUMO is an open-source, microscopic, continuous, multi-modal traffic simulation package developed by the German Aerospace Center (DLR). Unlike the other platforms, SUMO is a traffic flow simulator rather than an AV testing simulator — it models individual vehicle behavior based on car-following and lane-changing models. However, it is widely used for AV testing via its TraCI (Traffic Control Interface) API and co-simulation with CARLA.

### 5.1 Platform Overview

| Maintainer | German Aerospace Center (DLR) + Eclipse Foundation community |
|---|---|
| License | Eclipse Public License v2.0 (EPL-2.0) |
| Primary Use | Traffic flow simulation, V2X research, AV platoon testing, signal optimization, co-simulation |
| Simulation Model | Microscopic — every vehicle individually modeled with car-following (IDM, Krauss, etc.) and lane-change (LC2013, SL2015) models |
| Scenario Type | Parametric network + demand — scenarios defined by road network + vehicle demand; no pre-built named scenario library |
| Network Sources | OpenStreetMap import, synthetic random networks, manual NETEDIT construction |
| Object Types | Cars, trucks, buses, trams, trains, bicycles, pedestrians, motorcycles |
| Standards | OpenDRIVE export, GTFS import (public transport), OSM import |
| Key APIs | TraCI (Python/C++/Java real-time control), libsumo (embedded), SUMO-GUI, netedit |
| Key Integrations | CARLA co-simulation, NS2/NS3 (V2X), OMNET++, VISSIM import, Flow framework |
| Co-simulation | SUMO handles traffic flow; CARLA handles sensor rendering. Tasks split between simulators. |

### 5.2 How Scenarios Are Defined

SUMO does not have a library of pre-defined named scenarios. Instead, a scenario is composed from:

- Network file (.net.xml): road geometry, junctions, traffic lights, lane connections
- Route file (.rou.xml): vehicle types, departure times, routes or OD demands
- Additional file (.add.xml): detectors, signal programs, parking areas, public transport stops
- Configuration file (.sumocfg): ties all inputs together with simulation parameters

Scenario complexity emerges from the interaction of these inputs. A simple intersection + high vehicle demand = congestion scenario. The same intersection + low demand + a single pedestrian = yielding scenario. Scenarios are defined by parameters, not by scripted agent behaviors.

### 5.3 Scenario Types

| # | Scenario Name | Description & Differentiating Factor |
|---|---|---|
| 1 | Signalized intersection | Junction with traffic lights controlling flow. Differentiated by: phase timing, number of approaches, protected vs permissive turns. |
| 2 | Unsignalized intersection | Junction with yield/priority rules only. Differentiated by: who has priority (main road vs side road), traffic density on each approach. |
| 3 | Roundabout | Circular junction. Differentiated by: number of entry/exit lanes, circulating traffic density, entry speed. |
| 4 | Highway (motorway) | Multi-lane high-speed road. Differentiated by: lane count, speed limit, on-ramp merges, truck/car ratio. |
| 5 | Urban grid | City block network from OpenStreetMap import. Differentiated by: network density, signal coordination plans, pedestrian crossing demand. |
| 6 | On-ramp merge | Vehicle enters main road from acceleration lane. Differentiated by: merge lane length, main road speed, gap acceptance model parameters. |
| 7 | Bus/tram corridor | Public transport running in mixed or dedicated lanes. Differentiated by: headway, stop placement, interaction with general traffic. |
| 8 | Pedestrian crossing | Pedestrian-triggered or scheduled crossings. Differentiated by: pedestrian demand rate, crossing speed distribution, signal priority. |
| 9 | Parking generation | Vehicles searching for and occupying parking spaces. Differentiated by: supply/demand ratio, search radius, parking time distribution. |
| 10 | Emergency vehicle response | Emergency vehicle moves through network with priority signal preemption. Differentiated by: preemption strategy, network congestion level. |
| 11 | AV platoon | Vehicles traveling in coordinated close-following formation. Differentiated by: platoon size, headway, penetration rate of connected vehicles. |
| 12 | V2X cooperative scenario | Vehicles exchange information via V2X comms. Differentiated by: penetration rate, communication range, use case (green wave, hazard warning, cooperative merge). |

### 5.4 Dimensions of Differentiation

| Dimension | How Scenarios Differ |
|---|---|
| Network topology | Grid, arterial, freeway, mixed urban network. Imported from OSM or built manually. Topology determines which traffic phenomena can emerge. |
| Traffic demand | Vehicle count per hour per lane. Low demand = free-flow; moderate = stable queue; high = breakdown/congestion. Can be from OD matrices, random trips, or real counts. |
| Vehicle type mix | Ratio of cars, trucks, buses, bicycles, pedestrians. Heavy vehicles change capacity; mixed modes create complex interactions. |
| Car-following model | Krauss (default), IDM, Wiedemann, CACC. Changes how vehicles maintain headway. CACC enables platoon simulation. |
| Lane-change model | LC2013 (default), SL2015 (strategic). Different aggressiveness and cooperative behavior. |
| Signal plan | Fixed timing, actuated, adaptive (via TraCI). Signal plan change with same demand produces different congestion patterns. |
| V2X penetration rate | Fraction of vehicles with communication capability. Enables cooperative scenarios (green wave, hazard warning, cooperative merge). |
| AV penetration rate | Fraction of vehicles under SUMO control vs TraCI control (external AV algorithm). Used to study mixed autonomy traffic effects. |

## 6. Microsoft AirSim

AirSim is a simulation platform developed by Microsoft Research, built as a plugin for Unreal Engine (with experimental Unity support). Originally designed for drone simulation, it was extended to ground vehicles and became widely used for autonomous driving research, especially for end-to-end deep learning and computer vision. As of 2022, Microsoft has archived the original AirSim and is redirecting efforts to Project AirSim (aerial-focused commercial platform).

### 6.1 Platform Overview

| Maintainer | Microsoft Research (original; now archived). Community forks active. |
|---|---|
| Engine | Unreal Engine 4 (primary) / Unity (experimental) |
| License | MIT |
| Status | Original archived (2022). Community-maintained forks exist. Project AirSim (aerial) is the commercial successor. |
| Primary Use | Computer vision dataset generation, end-to-end deep learning, sensor simulation, RL research |
| Scenario Type | Environment-based — no pre-defined scenario library; scenarios built from environment + API scripts |
| Environments | Neighborhood, Mountain/Landscape, Modular Building, City, custom Unreal environments |
| Sensor Suite | RGB camera, depth camera, surface normals, optical flow, semantic segmentation (by object ID), LiDAR, IMU, GPS |
| Physics | PhysX (Unreal Engine) — realistic vehicle dynamics; also 'simple_flight' model |
| APIs | Python, C++, C#, Java; RPC-based; supports async operations |
| Special Modes | Computer Vision mode (no physics, free camera for dataset collection), Car mode, Drone mode |

### 6.2 How Scenarios Are Created

AirSim does not have a named scenario library. Scenarios are created by:

- Selecting or building a 3D environment in Unreal Engine
- Writing a Python/C++ script using the AirSim API to position vehicles, set weather, and control agents
- Optionally using the Computer Vision mode to capture labeled datasets without running a vehicle

The primary differentiator between AirSim scenarios is the environment (3D world). Unlike CARLA's behavioral scenarios, AirSim scenarios are fundamentally about the visual and physical fidelity of the environment rather than a specific behavioral challenge.

### 6.3 Scenario Types

| # | Scenario Name | Description & Differentiating Factor |
|---|---|---|
| 1 | Mountain / Landscape highway | Winding mountain road for end-to-end steering control. Differentiated by: curve sharpness, elevation change, lighting conditions (day/night). |
| 2 | Neighborhood streets | Suburban road network for urban driving. Differentiated by: pedestrian presence, parked vehicle density, traffic signs. |
| 3 | Modular building environment | Industrial/modular environment for structural variety. Differentiated by: road width variations, building proximity, shadow patterns. |
| 4 | AutonomousDrivingCookbook: single-camera steering | E2E deep learning scenario using a single front-facing camera. Differentiated from full-stack: no HD map, no LiDAR — pure vision to steering. |
| 5 | Computer Vision mode (no physics) | Free-camera mode for dataset generation. No vehicle physics active. Differentiated: used for perception dataset collection, not driving policy testing. |
| 6 | Custom Unreal Engine environment | User-imported Unreal world. Differentiated: fully custom; scenario type depends entirely on the environment imported. |

### 6.4 Dimensions of Differentiation

| Dimension | How Scenarios Differ |
|---|---|
| Environment type | Mountain road vs neighborhood vs modular industrial. Each environment has a different visual domain, road structure, and level of complexity. |
| Lighting condition | Time of day (sun position), artificial lighting, fog/rain/snow. Primary differentiator for perception research — same road, different visual appearance. |
| Weather | Rain, fog, snow, dust. Changes visual appearance and, in physics mode, road friction coefficient. |
| Sensor configuration | Which sensors are active, their placement, resolution, and noise models. Same scenario with camera-only vs LiDAR+camera is a different test. |
| Task type | End-to-end steering (one camera, one output) vs full-stack (multi-sensor, full planning) vs dataset collection (static camera, labeled frames). |
| Physics mode | Full PhysX vs kinematic vs Computer Vision (no physics). Affects what aspects of driving can be tested. |

## 7. MetaDrive

MetaDrive is a driving simulation platform developed at UCLA (Bolei Zhou's lab) designed specifically for generalizable reinforcement learning research. Its defining feature is compositionality — it can generate an infinite number of diverse driving scenarios from elementary building blocks. It supports both procedurally generated synthetic maps and real-world data import (Waymo, Argoverse datasets).

### 7.1 Platform Overview

| Maintainer | Bolei Zhou's group, UCLA — open source community |
|---|---|
| Engine | Panda3D with Bullet Physics — lightweight, high-throughput, not photorealistic |
| License | Apache 2.0 |
| Primary Use | Generalizable RL for autonomous driving, safe RL, multi-agent RL, policy transfer research |
| Scenario Type | Procedural generation (infinite) + real-world data import (Waymo, Argoverse) |
| Scenario Count (synthetic) | 3,000 standard benchmark scenarios; infinite via seed variation |
| Scenario Count (real-world) | 1,165 scenarios from Waymo Open Motion Dataset |
| Road Block Types | Straight, Curve, T-intersection, 4-way intersection, Roundabout, Ramp (merge), Ramp (diverge), Bottleneck (merge/diverge) |
| Observations | LiDAR-like point cloud, RGB camera, depth camera, bird-view semantic map, scalar vehicle state |
| Physics | Bullet engine with chassis, wheel, and joint constraints — more accurate than simple kinematic models |
| Multi-agent | Supports multiple simultaneously controlled AV agents in same scene |
| Safe RL | Explicit cost functions for constraint violations (overspeed, near-collision) alongside reward |

### 7.2 Scenario Architecture

MetaDrive builds scenarios from road block primitives. A road map is a sequence of blocks: e.g., Straight → Curve → T-intersection → Straight → Ramp. Each block type has parameterizable properties (lane width, curve radius, number of lanes). Traffic flow is generated by spawning vehicles into the network and controlling them with rule-based or IDM models.

This procedural approach means scenario diversity is theoretically infinite — each random seed generates a different road topology. The critical insight is that the network topology, not the specific behavior of individual agents, is the primary differentiator between MetaDrive scenarios.

### 7.3 Scenario Types

| # | Scenario Name | Description & Differentiating Factor |
|---|---|---|
| PG | Procedural Generation (Synthetic) | Maps built from elementary road blocks. 3,000 default scenarios. Block distribution: Straight (33%), Curve (16%), Ramp merge/diverge (8% each), Intersection (8%), T-intersection (7%), Roundabout (8%), Bottleneck merge/diverge (7% each). Average 8.9 traffic vehicles per scene. |
| RW | Real-world Waymo Import | 1,165 scenarios reconstructed from the Waymo Open Motion Dataset. Average 26.1 traffic vehicles per scene (3x denser than synthetic). Maps and surrounding vehicle trajectories are real-world recorded. Used for generalization benchmarking. |
| SA | Single-agent generalization | Agent trained on N procedurally generated maps and evaluated on held-out maps. Scenario count varies; standard benchmark uses 200 training, 200 test. Differentiator: no multi-agent interaction; pure environment generalization test. |
| MA | Multi-agent interaction | Multiple AV agents coexist in same scene. Scenarios identical to PG/RW but with multiple controlled agents. Differentiator: cooperative and competitive behaviors emerge; reward functions become more complex. |
| SR | Safe RL scenarios | Scenarios with explicit cost functions measuring dangerous events (e.g. overspeed, near-collision). Same map structures as PG but with added safety constraints. Differentiator: tests constrained optimization, not just task completion. |

### 7.4 Road Block Distribution in Default 3,000-Scenario Benchmark

| Straight | 33.1% of all blocks — highway-like sections |
|---|---|
| Curve | 15.6% — turns and bends |
| Ramp (merge) | 8.1% — on-ramp merge points |
| Ramp (diverge) | 7.6% — off-ramp diverge points |
| Intersection (4-way) | 7.7% — full 4-way crossroads |
| T-intersection | 7.4% — 3-way junctions |
| Roundabout | 7.7% — circular junctions |
| Bottleneck (merge) | 6.5% — lane narrowing merges |
| Bottleneck (diverge) | 6.8% — lane widening diverges |

### 7.5 Dimensions of Differentiation

| Dimension | How Scenarios Differ |
|---|---|
| Road block sequence | The ordered sequence of road block types defines the scenario's spatial challenge. Changing the sequence (e.g., adding a roundabout after a straight) changes the test. |
| Random seed | Each seed produces a different road topology with different block parameters. The same block types but different seed = different scenario. |
| Traffic density | Number of vehicles spawned per unit road length. Low density = sparse; high density = congested interaction. |
| Data source (PG vs real) | Procedurally generated (synthetic, variable) vs Waymo-imported (real, fixed maps and trajectories). Real scenarios have 3x more agents on average. |
| Agent type (single vs multi) | Single-agent RL vs multi-agent (multiple AV agents simultaneously). Multi-agent changes the reward structure and interaction complexity. |
| Constraint type (Safe RL) | Which safety constraints are active: speed limit, minimum gap, off-road. Different constraints produce different risk landscapes. |

## 8. Highway-Env (Farama Foundation)

Highway-Env is a minimalist Python library of autonomous driving environments for reinforcement learning research, originally developed by Edouard Leurent at Inria and now maintained by the Farama Foundation (the same organization that maintains Gymnasium). It is the most widely cited RL simulator for highway and urban driving decision-making research, with hundreds of published papers using it.

### 8.1 Platform Overview

| Maintainer | Farama Foundation (Edouard Leurent, original author) |
|---|---|
| License | MIT |
| Interface | Gymnasium (OpenAI Gym) compatible — standard step(), reset(), render() |
| Primary Use | RL algorithm development and benchmarking for decision-making; fast training throughput |
| Scenario Type | Named discrete environment types — each is a distinct configurable environment class |
| Scenario Count | 9 named environment types (plus variants like highway-fast-v0) |
| Rendering | 2D bird's-eye view — not photorealistic; intentionally minimal for speed |
| Physics | Simple kinematic model (not physics engine) — prioritizes speed over realism |
| Agent Model | IDM/MOBIL rule-based NPC vehicles — intelligent but scripted behavior |
| Configuration | Each environment is fully parameterizable via config dict (lane count, vehicle density, speed limits, etc.) |
| Observation Spaces | Kinematics (vehicle state), occupancy grid, grayscale image, time-to-collision matrix |
| Action Spaces | Discrete (lane change + speed), continuous (steering + acceleration), meta-action (high-level) |

### 8.2 Complete Environment List

| # | Scenario Name | Description & Differentiating Factor |
|---|---|---|
| 1 | highway-v0 | Multi-lane highway with surrounding vehicles. Ego must reach high speed while avoiding collisions. Differentiated by: number of lanes, vehicle density, speed variance. |
| 2 | highway-fast-v0 | Identical to highway-v0 but with degraded simulation accuracy for faster RL training throughput. Used when data volume matters more than physical precision. |
| 3 | merge-v0 | Ego starts on highway and reaches an on-ramp with incoming vehicles. Must make room while maintaining speed. Differentiated from highway: a fixed merge conflict point is introduced. |
| 4 | roundabout-v0 | Ego approaches a roundabout with flowing traffic. Must handle lane changes and longitudinal control to exit efficiently. Differentiated from merge: circular topology with multiple exit paths. |
| 5 | parking-v0 | Goal-conditioned continuous control task. Ego must reach a target parking spot with correct heading. Differentiated from all others: no high-speed traffic; task is positional precision. |
| 6 | intersection-v0 | Dense traffic intersection negotiation. Ego must cross without collision. Differentiated from roundabout: 4-way junction with conflicting straight-through traffic rather than circular flow. |
| 7 | racetrack-v0 | Ego drives on a closed racetrack. Objective is speed maximization on a fixed curve-heavy track. Differentiated: no other vehicles; challenge is lateral control on bends. |
| 8 | u-turn-v0 | Ego must execute a U-turn, reversing direction on a two-lane road. Differentiated: requires spatial awareness of narrow road width; no other scenarios test full direction reversal. |
| 9 | ComplexRoads | Composes multiple sub-scenarios (highway, merge, intersection segments) into a single compound network. Ego must navigate across sub-networks. Differentiated: no other env chains multiple scenario types into one episode. |

### 8.3 Dimensions of Differentiation

| Dimension | How Scenarios Differ |
|---|---|
| Road topology | Linear highway vs branching merge vs circular roundabout vs grid intersection vs racetrack. The fundamental spatial structure defines the challenge type. |
| Objective type | Speed maximization (highway, merge) vs goal-conditioned positioning (parking) vs collision avoidance (intersection) vs lap time (racetrack). |
| Traffic density | Configurable vehicles_count and road_density parameters. Same environment at different densities is effectively a different difficulty level. |
| Agent count | Single ego vs multiple controlled agents. Multi-agent variants test cooperative/competitive behaviors. |
| Ego role | Merging agent (must yield/find gap) vs main-road agent (must accommodate merger). Same spatial scenario but different responsibility. |
| Observation type | Kinematics vs image vs TTC matrix. Same environment with different observations tests different aspects of the perception-action loop. |
| Configuration parameters | Lane count, speed limits, vehicle count, simulation frequency, reward weights — every environment is parameterizable, producing infinite variants from each named type. |

## 9. PTV VISSIM

PTV VISSIM is a commercial microscopic traffic simulation software developed by PTV Group. It is the industry standard tool used by transportation engineers, urban planners, and government agencies worldwide for evaluating road design, signal optimization, and traffic flow. It is also used for ADAS and AV system testing, though this is secondary to its traffic planning use case.

### 9.1 Platform Overview

| Maintainer | PTV Group (commercial, headquartered in Germany) |
|---|---|
| License | Commercial (per-seat license) |
| Primary Use | Transportation planning, intersection design, signal timing, AV/ADAS integration testing |
| Scenario Type | Parametric — scenarios defined by network design + vehicle inputs; rich library of templates |
| Simulation Model | Microscopic (Wiedemann car-following model) — calibrated against real-world measured data |
| Vehicle Types | Cars, HGVs, buses, trams, light rail, bicycles, pedestrians, e-scooters |
| Signal Control | Fixed timing, actuated, SCATS/SCOOT integration, VAP (scripted adaptive), VisVAP |
| AV Integration | COM API (VBA/Python/C++) allows external AV algorithm to control ego vehicle |
| Key Feature | Wiedemann model is the most empirically validated car-following model; calibrated to real traffic data |
| Output | Queue lengths, delay, throughput, emissions, safety surrogate measures (TTC, PET) |

### 9.2 Scenario Types

| # | Scenario Name | Description & Differentiating Factor |
|---|---|---|
| 1 | Signalized intersection | Detailed signal timing with pedestrian phases. Differentiated by: detector placement, adaptive signal control algorithm. |
| 2 | Roundabout | Micro-level entry/circulate/exit behavior. Differentiated by: number of lanes, entry gap acceptance parameters per lane. |
| 3 | Highway weave | On-ramp and off-ramp in close proximity. Differentiated by: weave length, volume ratio between main road and ramps. |
| 4 | Urban arterial | Multi-block corridor with coordinated signals. Differentiated by: green wave bandwidth, driveway interference, bus stops. |
| 5 | ADAS/AV evaluation | Customized scenario for testing ADAS functions via COM API. Differentiated by: specific sensor model, connected vehicle penetration rate. |

### 9.3 Dimensions of Differentiation

| Dimension | How Scenarios Differ |
|---|---|
| Network design | Intersection geometry, turning lanes, channelization, pedestrian crossing placement. Primary differentiator in transportation planning use case. |
| Vehicle input volume | Traffic counts per approach per time period. Same network at different demands produces fundamentally different congestion patterns. |
| Driving behavior parameters | Wiedemann model parameters (desired speed, standstill distance, acceleration, deceleration). Calibrated per road class or region. |
| Signal control strategy | Fixed vs actuated vs adaptive. Same demand with different signal strategies is a different scenario for both traffic flow and AV testing. |
| Mode mix | Proportion of cars, HGVs, buses, cyclists, pedestrians. Mixed-mode scenarios create more complex interactions. |
| AV penetration rate | When using COM API, fraction of vehicles under AV control vs VISSIM-controlled. Used to study traffic effects of mixed autonomy. |

## 10. IPG CarMaker

IPG CarMaker is a commercial simulation software developed by IPG Automotive GmbH (Karlsruhe, Germany), specifically designed for vehicle dynamics and ADAS/AV validation. It is the dominant tool in the automotive OEM/Tier-1 industry for virtual test drives. Unlike research-focused simulators, CarMaker is calibrated to match real vehicle behavior with high fidelity, supporting SIL, MIL, and HIL testing workflows.

### 10.1 Platform Overview

| Maintainer | IPG Automotive GmbH (commercial) |
|---|---|
| License | Commercial (subscription/perpetual) |
| Primary Use | ADAS validation, vehicle dynamics testing, ECU/controller-in-the-loop, OEM production sign-off |
| Simulation Model | Vehicle dynamics (multi-body system), tire models (MF-Tyre, FTire), road surface models |
| Scenario Type | Parametric test runs — scenarios defined by road geometry + maneuver parameters; TestRun configuration files |
| Testing Modes | SIL (Software-in-Loop), MIL (Model-in-Loop), HIL (Hardware-in-Loop), Vehicle-in-Loop (ViL) |
| Road Library | OpenDRIVE, custom road geometry; built-in standard road profiles (highway, rural, urban) |
| Traffic | IPG Traffic module — scripted other vehicles and pedestrians with behavior trees |
| Sensor Models | Camera, LiDAR, RADAR, ultrasonic — with physical noise models; integrates with PreScan |
| Key Integrations | MATLAB/Simulink (co-simulation), PreScan (sensor simulation), dSpace, Vector CANalyzer, AUTOSAR |
| Industry Standards | ISO 26262, SOTIF (ISO 21448), UN ECE regulations; safety case support |

### 10.2 Scenario Types

| # | Scenario Name | Description & Differentiating Factor |
|---|---|---|
| 1 | Lane following (highway) | Basic longitudinal and lateral control on straight/curved highway. Differentiator: foundational scenario; validates steering and speed control before more complex tests. |
| 2 | Lane change (adjacent traffic) | Ego changes lane with controlled adjacent traffic. Differentiator: trigger is rule-based (slower lead vehicle), adjacent vehicle speed/gap is parameterized. |
| 3 | Overtaking on rural road | Ego overtakes in daylight, clear weather, on a non-junction rural road. Differentiator: involves crossing into oncoming lane — highest-risk maneuver class. |
| 4 | Intersection (stop sign) | Ego stops at stop sign and proceeds when clear. Differentiator: no signal control — right-of-way by position and speed. |
| 5 | Emergency braking (AEB) | Static or moving obstacle triggers automatic emergency braking. Differentiator: tests AEB activation threshold — obstacle type (pedestrian, car, wall) varies. |
| 6 | Driver drowsiness / distraction | Simulated driver inattention triggers ADAS warning/intervention. Differentiator: ego wanders within lane before system correction — tests LDWS/DMS. |
| 7 | Bad weather (rain/fog/ice) | Adverse weather conditions applied to any base scenario. Differentiator: environmental variables change road friction, visibility, and sensor performance. |
| 8 | Co-simulation with Simulink | CarMaker delegates control to external Simulink model. Differentiator: used for HIL/SIL validation of specific ECUs — scenario is host for external controller under test. |

### 10.3 Dimensions of Differentiation

| Dimension | How Scenarios Differ |
|---|---|
| Road class | Highway vs rural road vs urban street. Defines speed range, lane width, and applicable traffic rules. |
| Weather / road surface | Dry/wet/icy/snowy road, fog, rain. Directly affects tire-road friction and sensor performance. The same behavioral scenario under different weather is a different test. |
| Vehicle under test (VUT) configuration | Different vehicle mass, center of gravity, tire compound, suspension setup. CarMaker is designed to test how the vehicle itself behaves, not just the algorithm. |
| Testing mode (SIL/MIL/HIL) | Same scenario run in different testing modes validates different layers of the development chain. HIL includes real hardware ECUs; SIL uses software models only. |
| ADAS function under test | AEB, LKA, ACC, LDW, DMS — each function defines which aspects of the scenario matter. AEB test focuses on time-to-collision; LKA test focuses on lateral deviation. |
| Parameterization | Trigger distance, approach speed, obstacle type/size, driver model parameters. Standard ADAS tests (Euro NCAP, UNECE) specify exact parameter values for regulatory compliance. |

## Summary: Platform Comparison

The following table provides a concise side-by-side overview of all ten platforms for quick reference when designing your simulation platform.

| Platform | Scenario Count | Type | Primary Use | Scenario Creation Method |
|---|---|---|---|---|
| CARLA + ScenarioRunner | ~30 types (+ variants) | Synthetic | Full-stack AV research | Hand-crafted Python classes / OpenSCENARIO XML; NHTSA pre-crash typology as basis |
| nuPlan (Motional) | 73 types / 1,282h data | Real-world logged | ML planning benchmark | Auto-mined from 15,910 real driving logs using speed/state/map rules |
| Waymax (Waymo) | 100,000+ snippets | Real-world logged | Behavior/planning RL at scale | Raw Waymo driving logs; no taxonomy — diversity from data volume |
| LGSVL + Dreamland | ~200 cases (+ custom) | Hybrid (WorldSim + LogSim) | Full ADS stack testing | WorldSim: hand-crafted. LogSim: extracted from sensor logs. |
| SUMO | Infinite (parametric) | Parametric traffic | Traffic flow, V2X, co-sim | Network + demand files; behavior emerges from IDM/Krauss models |
| Microsoft AirSim | ~6 environments | Environment-based | Computer vision, E2E DL | Unreal Engine environments + Python API scripts; no named scenario library |
| MetaDrive | 3,000+ (PG) + 1,165 (real) | Procedural + real-world | Generalizable RL | Procedural composition of road block primitives; real import from Waymo/Argoverse |
| Highway-Env | 9 named environment types | Named discrete envs | RL algorithm development | Fixed env classes with configurable parameters (lanes, density, speed) |
| PTV VISSIM | Unlimited (parametric) | Parametric traffic | Transportation planning, ADAS | Network design + vehicle input volumes; Wiedemann car-following model |
| IPG CarMaker | Unlimited (parametric) | Parametric ADAS/dynamics | OEM ADAS validation, HIL | TestRun files with road + maneuver parameters; ADAS function-specific standard tests |

### Key Design Principles for Your Platform

Based on the analysis of all ten platforms, the following principles emerge for building a robust scenario library:

#### 1. Define your differentiation axes first

Every platform differentiates scenarios along a consistent set of axes. Before creating individual scenarios, define your taxonomy dimensions: road type, actor type, ego maneuver, traffic control, weather, etc. Then each scenario becomes a specific combination of values across those axes.

#### 2. Anchor to real-world crash data where possible

CARLA's leaderboard scenarios are derived from NHTSA pre-crash data. This approach ensures that scenarios correspond to real hazard types rather than arbitrary invented situations. Similar datasets exist globally (GIDAS in Germany, STATS19 in the UK, etc.).

#### 3. Use parameterization to multiply scenario coverage

A single behavioral scenario class (e.g., 'pedestrian crossing') can produce thousands of test instances by varying: pedestrian speed, crossing angle, ego approach speed, time of day, weather, presence of other vehicles. Build scenarios as classes with parameters, not as fixed scripts.

#### 4. Balance synthetic and data-driven scenarios

Synthetic scenarios give you control and reproducibility. Data-driven scenarios give you realism and naturalistic diversity. The best platforms (like Dreamland's WorldSim/LogSim split) support both. Synthetic scenarios are best for regression testing; data-driven for generalization evaluation.

#### 5. Cover all six maneuver/interaction types

A complete scenario library should include at minimum: (1) longitudinal control challenges (following, braking), (2) lateral control challenges (lane change, merge), (3) intersection negotiation, (4) vulnerable road user interaction (pedestrian, cyclist), (5) emergency situations (sudden obstacle, control loss), (6) adverse conditions (weather, poor visibility). These six categories together cover the majority of real-world crash types.