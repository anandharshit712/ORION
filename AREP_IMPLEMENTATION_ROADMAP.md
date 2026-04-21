# AREP / ORION — Full Implementation Roadmap

**Version**: 1.0  
**Date**: 2026-04-20  
**Status**: Active — this document is the single source of truth for all future work.  
**Governing rule**: Nothing is built that is not in this document. Nothing in this document is skipped.

---

## 0. Current State Baseline

### What Is Already Built and Working

| Component                                   | Status      | Location                                                  |
| ------------------------------------------- | ----------- | --------------------------------------------------------- |
| 4-Layer execution architecture (L1–L4)      | ✅ Complete | `arep_implementation/arep/`                               |
| Bicycle kinematic physics (L3)              | ✅ Complete | `core/physics.py` — `PhysicsMode.KINEMATIC`               |
| Pacejka dynamic tire model (L3)             | ✅ Complete | `core/physics.py` — `PhysicsMode.DYNAMIC`                 |
| Surface friction (dry / wet / ice / gravel) | ✅ Complete | `core/physics.py` — `SurfaceType` enum                    |
| OBB collision detection (SAT)               | ✅ Complete | `core/collision.py`                                       |
| WorldState + VehicleState + Vector2D        | ✅ Complete | `core/state.py`                                           |
| RandomManager (seeded, subsystem-isolated)  | ✅ Complete | `core/random_manager.py`                                  |
| ScenarioDefinition schema + YAML parser     | ✅ Complete | `scenario/schema.py`, `parser.py`                         |
| ScenarioParameterizer (L2 engine)           | ✅ Complete | `scenario/parameterizer.py`                               |
| 5 NPC Behavior Tree state machines          | ✅ Complete | `simulation/npc_bt.py`                                    |
| WorldManager + SimulationEngine             | ✅ Complete | `simulation/world.py`, `engine.py`                        |
| 4-metric evaluation monitor                 | ✅ Complete | `evaluation/` (safety, compliance, stability, reactivity) |
| FastAPI backend + auth + routes             | ✅ Complete | `api/app.py`, `auth.py`, `routes.py`                      |
| React + Three.js + Vite frontend scaffold   | ✅ Complete | `orion-frontend/src/`                                     |
| SQLAlchemy models + PostgreSQL config       | ✅ Complete | `database/`, `config/`                                    |
| 18 scenario YAML files (7 upgraded to v2.0) | ✅ Complete | `scenarios/`                                              |
| Batch runner skeleton                       | ✅ Partial  | `execution/runner.py`                                     |
| RL model interface scaffold                 | ✅ Partial  | `models/interface.py`, `local_executor.py`                |
| Dev startup scripts                         | ✅ Complete | `start.sh`, `start.bat`                                   |

### What Is Missing (drives this roadmap)

1. **WebSocket telemetry stream → Three.js 3D visualization** — the frontend renders nothing live
2. **Road topology engine** — only flat 2-lane straight exists; no intersections, no merge lanes
3. **Sensor simulation** — no LiDAR, camera, or GPS/IMU output; no real AV stack can plug in
4. **Adversarial search engine** — the core differentiator vs CARLA; not started
5. **Batch execution wired to API + DB** — runner exists but endpoints are stubs
6. **ROS2 bridge** — no industry AV stack can connect
7. **RL Gym adapter** — scaffold exists but is incomplete
8. **OpenDRIVE map parser** — no real-world road geometry
9. **11 remaining scenario YAMLs** — still on static `scripted` behavior
10. **OpenSCENARIO 2.0 import/export** — no interoperability with industry format
11. **CI/CD Docker image** — no automated regression testing
12. **Reporting dashboard** — DB metrics not visualised

---

## Roadmap Structure

```
Phase 1 — Complete Core Platform        (table-stakes; nothing else matters until done)
Phase 2 — Differentiators               (the features that create a unique position vs CARLA)
Phase 3 — Product Polish                (ecosystem, interoperability, scale)
```

**Execution rule**: Complete Phase 1 entirely before starting Phase 2. Complete Phase 2 entirely before starting Phase 3. Within each phase, items are ordered by dependency — earlier items unblock later ones.

---

---

# PHASE 1 — Complete Core Platform

---

## P1.1 — WebSocket Telemetry Stream + Three.js Live Visualization

**Goal**: The frontend must display a live 3D bird's-eye view of any running simulation. Every 50Hz tick the Python backend emits a JSON frame over WebSocket; the React Three Fiber scene updates vehicle positions in real time.

**SLA (from PROPOSED_IMPLEMENTATION.md)**: sub-100ms perceived latency, p95 < 60ms.

### 1.1.1 Backend — WebSocket Endpoint

**File to create**: `arep_implementation/arep/api/ws.py`

This module adds a WebSocket route to the FastAPI app. The endpoint accepts a `run_id` query parameter, looks up the running simulation from an in-memory registry, and pushes tick frames at 50Hz until the simulation ends or the client disconnects.

```
Endpoint:  WS /ws/simulation/{run_id}
Protocol:  JSON frames, one per tick (20ms interval target)
Auth:      JWT token passed as query param ?token=<jwt>
```

**JSON frame schema** (strict — never deviate):

```json
{
  "tick": 1042,
  "t_ms": 20840.0,
  "ego": {
    "id": "ego",
    "x": 145.3,
    "y": -1.75,
    "z": 0.0,
    "heading": 0.0,
    "speed": 22.1,
    "accel_x": -1.2,
    "accel_y": 0.0,
    "active_sensors": ["lidar_front", "camera_front"]
  },
  "npcs": [
    {
      "id": "lead_vehicle",
      "x": 170.1,
      "y": -1.75,
      "z": 0.0,
      "heading": 0.0,
      "speed": 18.4,
      "type": "car",
      "bt_state": "full_stop"
    }
  ],
  "env": {
    "weather_type": "clear",
    "friction_mu": 1.0,
    "visibility_m": 1000.0,
    "time_of_day": "day"
  },
  "monitor": {
    "active_criteria": ["no_collision", "speed_compliance"],
    "metrics_current": {
      "safety_score": 0.91,
      "compliance_score": 1.0,
      "stability_score": 0.87,
      "reactivity_score": 0.95
    },
    "verdict_so_far": "PASS"
  },
  "events": [
    {
      "t_ms": 20820.0,
      "type": "trigger_fired",
      "npc_id": "lead_vehicle",
      "detail": "hesitant_brake activated"
    }
  ]
}
```

**File to modify**: `arep_implementation/arep/api/app.py`

- Import and register the WebSocket router from `ws.py`
- Add `SimulationRegistry` singleton (dict mapping `run_id → SimulationEngine instance`) accessible by both the REST routes and the WS endpoint

**File to create**: `arep_implementation/arep/api/sim_registry.py`

- `SimulationRegistry`: thread-safe dict with `register(run_id, engine)`, `get(run_id)`, `remove(run_id)`
- Uses `asyncio.Lock` for concurrent access safety

### 1.1.2 Backend — Async Simulation Runner

**File to modify**: `arep_implementation/arep/simulation/engine.py`

The current `SimulationEngine.run()` is synchronous. Add:

- `run_async(on_tick: Callable[[dict], Awaitable[None]])` — runs the simulation loop with `asyncio.sleep(0)` yields between ticks, calling `on_tick` with the JSON frame each step
- `get_tick_frame(world: WorldState, monitor_result: dict) -> dict` — serializes current world to the JSON frame schema above
- The async runner must never block the event loop for more than 5ms per tick

### 1.1.3 Frontend — WebSocket Client Hook

**File to create**: `orion-frontend/src/hooks/useSimulationStream.js`

```javascript
// Returns: { frame, isConnected, error }
// frame is the latest parsed JSON tick frame, updated in real time
export function useSimulationStream(runId, token) { ... }
```

- Opens `ws://localhost:8000/ws/simulation/{runId}?token={token}`
- Parses each incoming message, calls `setFrame(parsed)`
- Handles reconnect on disconnect (exponential backoff, max 3 attempts)
- Cleans up the socket on component unmount

### 1.1.4 Frontend — 3D Scene Renderer

**File to create**: `orion-frontend/src/components/SimulationViewer.jsx`

Uses React Three Fiber (`@react-three/fiber`) and Drei (`@react-three/drei`).

**Scene contents**:

- Road: flat grey `PlaneGeometry` — width = `lanes × lane_width`, length = 300m, lane markings as white `LineSegments`
- Ego vehicle: blue `BoxGeometry` (4.5 × 2.0 × 1.5m) positioned at `frame.ego.{x,y}`, rotated by `frame.ego.heading`
- NPC vehicles: colour-coded by type (red = car, orange = truck, yellow = pedestrian/cyclist)
- All objects receive their position and rotation from the latest WebSocket frame on each React render
- Camera: fixed overhead orthographic view, centered on ego, zoom adjustable via scroll

**HUD overlay** (rendered as HTML over the canvas, not in the 3D scene):

- Top-left: sim time, ego speed (km/h), ego acceleration (g)
- Top-right: live metric bars (Safety / Compliance / Stability / Reactivity) — coloured green/amber/red based on thresholds
- Bottom: event log — last 5 events from `frame.events[]`, auto-scrolling
- Verdict badge: large PASS / FAIL / INCONCLUSIVE badge, colour-coded

**File to modify**: `orion-frontend/src/App.jsx` (or router)

- Add `/simulation/:runId` route that renders `<SimulationViewer />`

### 1.1.5 Acceptance Criteria for P1.1

- [ ] Starting a simulation via the REST API (`POST /api/runs`) returns a `run_id`
- [ ] Opening `http://localhost:5173/simulation/{run_id}` shows a live 3D scene
- [ ] Vehicle positions visibly update each tick
- [ ] HUD shows live metric scores and verdict
- [ ] Measured p95 frame latency (backend emit → browser render) < 100ms on localhost
- [ ] Closing the browser tab cleanly closes the WebSocket and stops simulation streaming

---

## P1.2 — Road Topology Engine

**Goal**: Move from a flat 2-lane straight abstraction to a composable road graph supporting intersections, merge lanes, and roundabouts. This is required by at least 8 of the 18 existing scenarios (all INT-_, EMG-002, MLT-_).

### 1.2.1 Road Graph Data Model

**File to create**: `arep_implementation/arep/core/road.py`

```python
@dataclass
class RoadSegment:
    segment_id: str
    segment_type: Literal["straight", "curve", "intersection_arm", "ramp"]
    centerline: List[Vector2D]   # ordered points defining the segment centre
    lane_count: int
    lane_width: float
    speed_limit: float           # m/s
    surface: SurfaceType
    heading_start: float         # radians
    heading_end: float

@dataclass
class Junction:
    junction_id: str
    junction_type: Literal["t_junction", "4way", "roundabout", "merge"]
    arms: List[str]              # list of segment_ids that connect here
    position: Vector2D
    has_traffic_light: bool
    right_of_way: Dict[str, str] # arm_id → "yield" | "priority"

@dataclass
class RoadGraph:
    segments: Dict[str, RoadSegment]
    junctions: Dict[str, Junction]

    def get_lane_centerline(self, segment_id: str, lane_index: int) -> List[Vector2D]: ...
    def get_ego_segment(self, position: Vector2D) -> Optional[RoadSegment]: ...
    def is_off_road(self, position: Vector2D, margin: float = 0.5) -> bool: ...
    def get_junction_at(self, position: Vector2D) -> Optional[Junction]: ...
```

### 1.2.2 Built-In Road Templates

**File to create**: `arep_implementation/arep/core/road_templates.py`

Provides factory functions that generate `RoadGraph` objects for common layouts. All scenarios use one of these templates rather than raw road graph definitions.

```python
def highway_straight(lanes: int, length: float, lane_width: float, speed_limit: float) -> RoadGraph
def urban_straight(lanes: int, length: float, ...) -> RoadGraph
def t_junction(approach_length: float, cross_length: float, ...) -> RoadGraph
def four_way_intersection(arm_length: float, ...) -> RoadGraph
def highway_onramp(main_length: float, ramp_length: float, merge_point: float, ...) -> RoadGraph
def roundabout(radius: float, arm_count: int, arm_length: float, ...) -> RoadGraph
```

Each function returns a fully-wired `RoadGraph` with correct segment connections, junction right-of-way rules, and lane centerline points at 1m resolution.

### 1.2.3 Scenario YAML — Road Section Extension

**Current YAML `environment.road` section**:

```yaml
road:
  type: highway
  lanes: 2
  lane_width: 3.5
  speed_limit: 27.78
```

**New YAML `environment.road` section** (backward compatible):

```yaml
road:
  template: four_way_intersection # maps to road_templates factory function
  # template-specific parameters:
  arm_length: 80.0
  lanes: 2
  lane_width: 3.5
  speed_limit: 13.89
  # ego spawn is always on arm "south", facing north (heading = π/2)
```

If `template` key is absent, fall back to existing behaviour (straight road derived from `type`).

**File to modify**: `arep_implementation/arep/scenario/parser.py`

- Parse `road.template` and call the appropriate factory function to produce a `RoadGraph`
- Store the `RoadGraph` in `ScenarioDefinition` as a new `road_graph: Optional[RoadGraph]` field

**File to modify**: `arep_implementation/arep/scenario/schema.py`

- Add `road_graph: Optional[Any] = None` to `ScenarioDefinition`

**File to modify**: `arep_implementation/arep/scenario/executor.py`

- Pass `road_graph` into `WorldState.lanes` by converting each segment's lane centerlines to existing `LaneInfo` objects
- Also store `road_graph` directly on `WorldState` for junction-aware queries

**File to modify**: `arep_implementation/arep/core/state.py`

- Add `road_graph: Optional[Any] = None` to `WorldState`

### 1.2.4 Visualization Update for Road Topology

**File to modify**: `orion-frontend/src/components/SimulationViewer.jsx`

- The WebSocket `env` frame is extended with a `road_graph` snapshot (emitted once on connection, not every tick)
- The 3D scene builds road geometry from this snapshot: one `PlaneGeometry` per segment, junction surfaces at intersections
- Lane markings use `LineSegments` generated from the centerline points

### 1.2.5 Acceptance Criteria for P1.2

- [ ] `road_templates.four_way_intersection()` returns a valid `RoadGraph`
- [ ] `road.is_off_road()` returns `True` for positions outside all segments
- [ ] An INT-\* scenario YAML with `template: four_way_intersection` loads and runs without error
- [ ] The Three.js scene correctly renders the intersection geometry
- [ ] Traffic lights at junctions cycle state and are reflected in the HUD

---

## P1.3 — Sensor Simulation Layer

**Goal**: Give the ego vehicle simulated sensor outputs (LiDAR point cloud, forward camera image, GPS + IMU noise). Without this, no real AV stack can consume the simulation output. This is the single highest-leverage item for industry adoption.

### 1.3.1 Sensor Configuration in WorldState

**File to modify**: `arep_implementation/arep/core/state.py`

Add to `WorldState`:

```python
sensor_outputs: Dict[str, Any] = field(default_factory=dict)
# Keys: sensor_id → output object (PointCloud, CameraFrame, GNSSOutput, IMUOutput)
```

### 1.3.2 Sensor Definitions in Scenario YAML

New top-level `sensors:` section (optional — if absent, no sensor output is computed):

```yaml
sensors:
  - id: lidar_front
    type: lidar_2d
    mount_x: 0.0 # metres from ego centre (forward positive)
    mount_y: 0.0
    mount_z: 1.5
    range: 80.0 # metres
    fov_deg: 360.0
    ray_count: 360
    noise_std: 0.02 # metres (Gaussian range noise)

  - id: camera_front
    type: camera_pinhole
    mount_x: 1.8
    mount_y: 0.0
    mount_z: 1.2
    fov_h_deg: 70.0
    resolution: [640, 480]
    max_range: 60.0

  - id: gnss
    type: gnss
    position_noise_std: 0.5 # metres
    heading_noise_std: 0.01 # radians

  - id: imu
    type: imu
    accel_noise_std: 0.05 # m/s²
    gyro_noise_std: 0.002 # rad/s
```

**File to modify**: `arep_implementation/arep/scenario/schema.py`

- Add `sensors: List[Dict[str, Any]] = field(default_factory=list)` to `ScenarioDefinition`

### 1.3.3 Sensor Engine

**File to create**: `arep_implementation/arep/simulation/sensors.py`

```python
class SensorEngine:
    """
    Computes sensor outputs for the ego vehicle each tick.
    All computations are deterministic given the world state and RNG seed.
    """
    def __init__(self, sensor_configs: List[dict]): ...
    def compute(self, world: WorldState, rng: RandomManager) -> Dict[str, Any]:
        """Returns dict of sensor_id → output. Called once per tick."""
        ...
```

**LiDAR (2D raycast)**:

- Cast `ray_count` rays from the sensor mount position in the ego's frame
- For each ray at angle θ: find the first object whose OBB the ray intersects
- If intersection found: range = distance to hit point + `N(0, noise_std)`
- If no intersection within `range`: return max range
- Output: `PointCloud` dataclass with `ranges: np.ndarray` (shape: `[ray_count]`) and `angles: np.ndarray`
- Implementation: use existing `VehicleState.get_bounding_box_corners()` for all objects; ray-OBB intersection via parametric line equation

**Camera (pinhole, top-down 2D projection)**:

- Project all object bounding boxes into the camera image plane using standard pinhole model
- Output: `CameraFrame` dataclass with `width, height, objects: List[ProjectedObject]`
- `ProjectedObject`: `object_id, bbox_pixels: [x1, y1, x2, y2], class_label, confidence: 1.0`
- No pixel rendering — structured object list only (sufficient for AV stack perception input)

**GNSS**:

- Output: `GNSSOutput` with `x, y` = ego position + `N(0, position_noise_std)`, `heading` = ego heading + `N(0, heading_noise_std)`
- Uses `rng.get("noise")` for determinism

**IMU**:

- Output: `IMUOutput` with `accel_x, accel_y` = ego acceleration components + noise, `yaw_rate` = from physics engine + noise

### 1.3.4 Integration into Simulation Engine

**File to modify**: `arep_implementation/arep/simulation/engine.py`

- Instantiate `SensorEngine` from scenario's `sensors` list in `__init__`
- Each tick: call `sensor_engine.compute(world, rng)` and store result in `world.sensor_outputs`
- Include `active_sensors: list(world.sensor_outputs.keys())` in the WebSocket frame's `ego` object

### 1.3.5 Sensor Output in WebSocket Frame

The `ego.active_sensors` field in the JSON frame lists which sensors are active. A separate WebSocket sub-channel (or an extended frame field `sensor_data`) streams sensor outputs:

```json
"sensor_data": {
  "lidar_front": {
    "type": "lidar_2d",
    "ranges": [45.2, 44.8, ...],
    "angles": [0.0, 0.0175, ...]
  },
  "gnss": { "x": 145.8, "y": -1.63, "heading": 0.003 },
  "imu": { "accel_x": -1.18, "accel_y": 0.02, "yaw_rate": 0.001 }
}
```

Camera frames are excluded from the WebSocket stream (too large) but available via a REST endpoint: `GET /api/runs/{run_id}/sensors/camera_front/latest`.

### 1.3.6 Acceptance Criteria for P1.3

- [ ] A scenario with `sensors:` section produces non-null `world.sensor_outputs` each tick
- [ ] LiDAR `ranges` array has correct length (= `ray_count`) and correct units (metres)
- [ ] LiDAR returns max range for directions with no objects; shorter range when an NPC OBB is hit
- [ ] GNSS output has measurable noise (std dev within 20% of configured value over 100 runs)
- [ ] Running with the same seed produces identical sensor outputs; different seeds produce different noise
- [ ] `active_sensors` appears correctly in the WebSocket frame

---

## P1.4 — Batch Execution Wired to API + DB

**Goal**: `POST /api/runs/batch` accepts a scenario ID + run count + seed range; executes all runs headlessly; persists results to PostgreSQL; returns aggregated metrics.

### 1.4.1 Current Gap

`arep_implementation/arep/execution/runner.py` exists but `routes.py` has stub endpoints. The `database/` models exist but `runner.py` never calls them.

### 1.4.2 DB Schema (verify / complete)

**File to verify**: `arep_implementation/arep/database/`

Ensure these tables exist (create migrations if not):

```sql
runs (
  run_id        UUID PRIMARY KEY,
  scenario_id   VARCHAR,
  seed          BIGINT,
  status        VARCHAR,   -- queued / running / complete / failed
  started_at    TIMESTAMP,
  completed_at  TIMESTAMP,
  verdict       VARCHAR,   -- PASS / FAIL / INCONCLUSIVE
  duration_s    FLOAT
)

run_metrics (
  run_id           UUID REFERENCES runs,
  safety_score     FLOAT,
  compliance_score FLOAT,
  stability_score  FLOAT,
  reactivity_score FLOAT,
  composite_score  FLOAT,
  collision        BOOLEAN,
  termination_reason VARCHAR
)

run_events (
  event_id    SERIAL PRIMARY KEY,
  run_id      UUID REFERENCES runs,
  t_ms        FLOAT,
  event_type  VARCHAR,
  detail      JSONB
)
```

### 1.4.3 Batch API Endpoints

**File to modify**: `arep_implementation/arep/api/routes.py`

```
POST   /api/runs/batch
Body:  { scenario_id, run_count, seed_start, seed_step, physics_mode }
Resp:  { batch_id, run_ids: [...] }

GET    /api/runs/batch/{batch_id}/status
Resp:  { total, complete, failed, running }

GET    /api/runs/batch/{batch_id}/results
Resp:  { summary: { pass_rate, mean_composite, std_composite, collision_rate },
         runs: [{ run_id, seed, verdict, composite_score, ... }] }

GET    /api/runs/{run_id}/events
Resp:  [ { t_ms, event_type, detail }, ... ]
```

### 1.4.4 Async Batch Runner

**File to modify**: `arep_implementation/arep/execution/runner.py`

- `BatchRunner.run_batch(batch_config) -> BatchResult`: runs N simulations sequentially (or with `asyncio.gather` for parallel headless runs)
- After each run: writes to `runs` and `run_metrics` tables via SQLAlchemy session
- `BatchRunner` is instantiated per request; the API route calls it inside a `BackgroundTasks` callback so the HTTP response returns immediately
- Progress is stored in `runs.status`; the client polls `GET /api/runs/batch/{batch_id}/status`

### 1.4.5 Acceptance Criteria for P1.4

- [ ] `POST /api/runs/batch` with `run_count=10` returns within 200ms (background execution)
- [ ] Polling status shows `complete: 10` after all runs finish
- [ ] `GET /api/runs/batch/{batch_id}/results` returns correct `pass_rate`, `mean_composite`
- [ ] All 10 run records exist in the `runs` table after completion
- [ ] Same `seed_start` always produces identical `composite_score` for a given scenario

---

## P1.5 — Upgrade Remaining 11 Scenario YAMLs to v2.0

**Goal**: All 18 scenarios use `reactive_vehicle` / `reactive_pedestrian` behavior types with full `parameterization:` blocks. The 7 already upgraded (LON-002, LON-003, LAT-002, VRU-001, VRU-008, MLT-001, MLT-007) are the template.

### Scenarios to Upgrade

| ID      | File                                                 | Required BT Type                  | Notes                              |
| ------- | ---------------------------------------------------- | --------------------------------- | ---------------------------------- |
| LON-001 | `scenarios/lon/LON-001_lead_vehicle_slow.yaml`       | `hesitant_brake`                  | Gentle decel, no full stop         |
| LON-004 | `scenarios/lon/LON-004_highway_merge.yaml`           | `hesitant_cut_in`                 | Merging from on-ramp               |
| LAT-001 | `scenarios/lat/LAT-001_lane_change_conflict.yaml`    | `hesitant_cut_in`                 | Ego changes lane, NPC contests     |
| LAT-003 | `scenarios/lat/LAT-003_oncoming_lane_departure.yaml` | New BT: `oncoming_drift`          | NPC drifts into ego lane           |
| INT-001 | `scenarios/int/INT-001_red_light_runner.yaml`        | New BT: `red_light_runner`        | NPC runs red at random delay       |
| INT-002 | `scenarios/int/INT-002_yield_failure.yaml`           | `hesitant_brake` with abort       | NPC fails to yield at T-junction   |
| INT-005 | `scenarios/int/INT-005_unprotected_left.yaml`        | `hesitant_brake`                  | Oncoming vehicles at gap           |
| VRU-003 | `scenarios/vru/VRU-003_cyclist_dooring.yaml`         | New BT: `erratic_cyclist`         | Cyclist swerves avoiding car door  |
| EMG-001 | `scenarios/emg/EMG-001_wrong_way_driver.yaml`        | New BT: `wrong_way_driver`        | NPC drives toward ego at speed     |
| EMG-002 | `scenarios/emg/EMG-002_debris_field.yaml`            | N/A (static objects + ego swerve) | Multiple static obstacles          |
| EMG-004 | `scenarios/emg/EMG-004_sudden_tire_blowout.yaml`     | New BT: `tire_blowout`            | NPC yaws and decelerates violently |

### New BT Types to Add to `npc_bt.py`

**`OncomingDriftBT`**: `cruising → drifting (gradual lateral move toward ego lane at random speed) → [correction if ego brakes hard] → committed`. Parameters: `drift_speed {min,max}`, `drift_start_distance {min,max}`, `correction_prob`.

**`RedLightRunnerBT`**: `waiting_at_line → [timer expires or gap random] → running (constant velocity through red)`. Parameters: `run_delay {min,max}`, `run_speed {min,max}`.

**`ErraticCyclistBT`**: Extension of `ErraticPedestrianBT` with forward heading bias. Parameters: same as erratic pedestrian plus `swerve_magnitude {min,max}`.

**`WrongWayDriverBT`**: `approaching (constant velocity toward ego, heading = π) → [if ego does not brake] → accelerate`. Parameters: `approach_speed {min,max}`, `acceleration_if_no_ego_brake`.

**`TireBlowoutBT`**: `cruising → blowout_triggered (random yaw torque applied, rapid deceleration) → spinning_out`. Parameters: `trigger_distance {min,max}`, `yaw_impulse {min,max}`, `decel_rate`.

### Parameterization Block Requirements for All Scenarios

Every scenario must have:

- `ego_velocity: { min, max }` — ego initial speed range in m/s
- At minimum one `npc_overrides` block with `initial_x: { min, max }` and at least two randomised behavior parameters
- `master_seed` unique across all scenarios (no two share a seed)

### Acceptance Criteria for P1.5

- [ ] All 18 scenario YAMLs have `version: "2.0"` and a `parameterization:` block
- [ ] All 18 scenarios load without parser errors
- [ ] Running each scenario with 3 different seeds produces 3 different ego velocity values
- [ ] All 5 new BT types are registered in `npc_bt._BT_REGISTRY`

---

---

# PHASE 2 — Differentiators

---

## P2.1 — Adversarial Scenario Search Engine

**Goal**: Given a scenario ID and a safety property, automatically find the parameter configuration that maximally violates the property. This is the single feature that differentiates AREP from CARLA in a way that matters for safety validation.

**Positioning**: CARLA runs scenarios you author. AREP finds the scenarios that break your model before you know to author them.

### 2.1.1 Architecture

The search engine operates at Layer 2 (Parameterization), treating the scenario's `parameterization:` block as a bounded search space and the evaluation monitor's verdict as the objective function.

```
Search Engine
  ├── SearchSpace      — extracts {min,max} ranges from scenario YAML → continuous box
  ├── ObjectiveFunction — runs one simulation, returns scalar fitness (higher = worse for ego)
  ├── Optimizer        — CMA-ES (primary) + random baseline for comparison
  └── FalsificationLog — records all parameter configs that produced FAIL
```

**Fitness function**:

```
f(params) = w_collision · collision_indicator
           + w_ttc · (1 / min_ttc_observed)
           + w_safety · (1 - safety_score)
           + w_compliance · (1 - compliance_score)
```

Weights: `w_collision = 10.0`, `w_ttc = 2.0`, `w_safety = 1.0`, `w_compliance = 0.5`.

### 2.1.2 Files to Create

**`arep_implementation/arep/search/space.py`**

```python
@dataclass
class SearchDimension:
    name: str          # e.g. "lead_vehicle.initial_x"
    low: float
    high: float

class SearchSpace:
    def __init__(self, scenario: ScenarioDefinition): ...
    def dimensions(self) -> List[SearchDimension]: ...
    def to_params_dict(self, x: np.ndarray) -> Dict[str, Any]:
        """Convert optimizer vector to parameterizer-compatible override dict."""
```

**`arep_implementation/arep/search/objective.py`**

```python
class ObjectiveFunction:
    def __init__(self, scenario: ScenarioDefinition, model, physics_mode): ...
    def __call__(self, x: np.ndarray, seed: int = 0) -> float:
        """Run one simulation with params from x, return fitness scalar."""
```

**`arep_implementation/arep/search/optimizer.py`**

```python
class CMAESOptimizer:
    """
    CMA-ES (Covariance Matrix Adaptation Evolution Strategy).
    Uses the `cma` Python package.
    Maximises f(x) by minimising -f(x).
    """
    def __init__(self, space: SearchSpace, sigma0: float = 0.3,
                 popsize: int = 10, max_evals: int = 200): ...
    def run(self, objective: ObjectiveFunction) -> SearchResult: ...

class RandomSearchOptimizer:
    """Baseline: uniform random sampling. Used for comparison and warm start."""
    def __init__(self, space: SearchSpace, n_samples: int = 50): ...
    def run(self, objective: ObjectiveFunction) -> SearchResult: ...

@dataclass
class SearchResult:
    best_params: Dict[str, Any]
    best_fitness: float
    n_evals: int
    falsification_found: bool
    falsification_params: Optional[Dict[str, Any]]
    all_evaluations: List[Tuple[Dict, float]]   # for analysis
```

**`arep_implementation/arep/search/__init__.py`** — package init

### 2.1.3 API Endpoint

**File to modify**: `arep_implementation/arep/api/routes.py`

```
POST /api/search
Body: {
  scenario_id: str,
  max_evals: int,           # default 200
  optimizer: "cma_es" | "random",
  physics_mode: "kinematic" | "dynamic",
  seed: int
}
Resp: {
  search_id: str,
  status: "running"
}

GET /api/search/{search_id}/status
Resp: {
  status: "running" | "complete",
  evals_done: int,
  best_fitness: float,
  falsification_found: bool
}

GET /api/search/{search_id}/result
Resp: {
  best_params: {...},
  best_fitness: float,
  falsification_found: bool,
  falsification_params: {...} | null,
  all_evaluations: [...]
}
```

### 2.1.4 New Python Dependency

Add `cma>=3.3.0` to `arep_implementation/pyproject.toml` under `[project.optional-dependencies] search`.

### 2.1.5 Acceptance Criteria for P2.1

- [ ] `POST /api/search` with LON-003 and `max_evals=50` completes without error
- [ ] Over 50 evaluations, fitness is higher than random search baseline at eval 50 (CMA-ES converges)
- [ ] If the model under test is `ConstantActionModel(accel=0.0)` (no braking), `falsification_found=True` with collision parameters
- [ ] `SearchResult.all_evaluations` has exactly `max_evals` entries
- [ ] Same seed produces identical search trajectory

---

## P2.2 — ROS2 Bridge

**Goal**: Any ROS2-based AV stack (Autoware, Apollo via ROS2 bridge, custom) can subscribe to AREP sensor topics and publish control commands back. AREP becomes a drop-in ROS2 simulation target.

### 2.2.1 Architecture

```
AREP Simulation (Python, 50Hz)
        ↕  ZeroMQ or shared memory IPC
ROS2 Bridge Node (Python, rclpy)
        ↕  ROS2 topics
AV Stack (any)
```

The bridge runs as a separate process alongside the FastAPI server. It subscribes to a ZeroMQ `PUB` socket that the simulation engine publishes to each tick, converts the tick data to ROS2 messages, and subscribes to a ROS2 `cmd_vel` or `autoware_control` topic to receive the ego's action and pushes it back to the simulation via a ZeroMQ `PUSH` socket.

### 2.2.2 Files to Create

**`arep_implementation/arep/bridges/ros2_bridge.py`**

```python
class ROS2Bridge:
    """
    Converts AREP WorldState ↔ ROS2 messages.
    Requires: rclpy, sensor_msgs, geometry_msgs, nav_msgs
    """
    def publish_tick(self, world: WorldState, sensor_outputs: dict) -> None:
        """Publish to: /orion/lidar (PointCloud2), /orion/gnss (NavSatFix),
                       /orion/imu (Imu), /orion/objects (MarkerArray)"""
    def get_latest_control(self) -> Optional[Action]:
        """Read latest from /orion/cmd → AckermannDriveStamped"""
```

**`arep_implementation/arep/bridges/zmq_transport.py`**

- `SimPublisher`: ZeroMQ PUB socket, publishes serialised `WorldState` each tick
- `ControlSubscriber`: ZeroMQ PULL socket, receives `Action` from bridge

**`arep_implementation/ros2_bridge_node.py`** (top-level, not in the `arep` package)

- Entry point: `python ros2_bridge_node.py --scenario-id LON-003 --seed 42`
- Spins the ROS2 node and the ZMQ transport loop

### 2.2.3 ROS2 Topic Mapping

| AREP sensor             | ROS2 topic        | ROS2 message type                      |
| ----------------------- | ----------------- | -------------------------------------- |
| `lidar_front` (360° 2D) | `/orion/scan`     | `sensor_msgs/LaserScan`                |
| `gnss`                  | `/orion/gnss`     | `sensor_msgs/NavSatFix`                |
| `imu`                   | `/orion/imu`      | `sensor_msgs/Imu`                      |
| All NPC bounding boxes  | `/orion/objects`  | `visualization_msgs/MarkerArray`       |
| Ego ground truth        | `/orion/ego/odom` | `nav_msgs/Odometry`                    |
| **Ego control input**   | `/orion/cmd`      | `ackermann_msgs/AckermannDriveStamped` |

### 2.2.4 New Dependencies

Add to `pyproject.toml` under `[project.optional-dependencies] ros2`:

```
pyzmq>=25.0
# rclpy is installed separately via ROS2 environment — not pip
```

### 2.2.5 Acceptance Criteria for P2.2

- [ ] `python ros2_bridge_node.py --scenario-id LON-003 --seed 42` starts without error in a ROS2 Humble environment
- [ ] `ros2 topic echo /orion/scan` shows LaserScan messages at ~50Hz
- [ ] Publishing a constant `AckermannDriveStamped` to `/orion/cmd` causes the ego to follow that command in simulation
- [ ] Disconnecting the ROS2 node causes the simulation to pause (no action = coast at constant velocity, not crash)

---

## P2.3 — RL Gym Adapter (Complete the Scaffold)

**Goal**: A Gymnasium-compatible environment wrapping AREP so that any RL algorithm (PPO, SAC, DQN) can train against AREP scenarios without modification. The existing `models/interface.py` scaffold must be completed.

### 2.3.1 Target Interface

```python
import gymnasium as gym

env = gym.make("AREP-LON003-v0", physics_mode="kinematic", seed=42)
obs, info = env.reset()
action = env.action_space.sample()
obs, reward, terminated, truncated, info = env.step(action)
```

### 2.3.2 Files to Create / Modify

**`arep_implementation/arep/gym_env/arep_env.py`**

```python
class AREPEnv(gymnasium.Env):
    metadata = {"render_modes": ["human", "rgb_array"], "render_fps": 50}

    # Observation space: 1D vector of [ego_v, ego_ax, ego_ay,
    #   lidar_ranges[360], gnss_x, gnss_y, gnss_heading,
    #   npc_0_x, npc_0_y, npc_0_v, ... (up to 4 NPCs, zero-padded)]
    # Action space: Box([-1, -1], [1, 1]) → [normalised_accel, normalised_steering]

    def reset(self, seed=None, options=None) -> Tuple[np.ndarray, dict]: ...
    def step(self, action: np.ndarray) -> Tuple[np.ndarray, float, bool, bool, dict]: ...
    def render(self) -> Optional[np.ndarray]: ...
    def close(self) -> None: ...
```

**Reward function** (internal to `arep_env.py`):

```
R = +1.0  per tick (survival reward)
R += +0.5 · (ego_speed / speed_limit)  (progress reward, capped at 1.0)
R += -10.0  on collision
R += -5.0   on off-road
R += -2.0   on speed_limit violation > 10%
R += +5.0   on scenario SUCCESS (reach end without collision)
```

**`arep_implementation/arep/gym_env/__init__.py`**

- Registers all 18 scenarios as named Gym environments:
  `AREP-LON001-v0` through `AREP-MLT007-v0`

**File to modify**: `arep_implementation/pyproject.toml`

- Add `gymnasium>=0.29.0` to `[project.optional-dependencies] rl`

### 2.3.3 Performance Target

AREP's headless core should achieve **≥ 500 simulation steps/second** in `PhysicsMode.KINEMATIC` with sensors disabled. This is 10× faster than CARLA's typical 30–50 FPS, making it viable for RL training.

Profile and optimise `simulation/engine.py` if needed to hit this target. Key optimisations: avoid deep copy in `WorldState.copy()` where not strictly required; cache OBB computations.

### 2.3.4 Acceptance Criteria for P2.3

- [ ] `gym.make("AREP-LON003-v0")` works in a clean environment
- [ ] `env.reset()` returns an observation of the correct shape
- [ ] `env.step(action)` returns correct types; `terminated=True` when simulation ends
- [ ] 1000 random steps complete in < 2 seconds (≥ 500 steps/sec)
- [ ] Running stable-baselines3 PPO for 10,000 steps against LON-003 does not crash

---

## P2.4 — OpenDRIVE Map Parser (Subset)

**Goal**: Load a standard `.xodr` OpenDRIVE file and convert it to an AREP `RoadGraph`. This unlocks real-world road geometry (exported from HD map tools, CARLA, or public datasets).

**Scope**: Implement a subset sufficient for single-road and simple intersection geometries. Full OpenDRIVE compliance is not required.

### 2.4.1 Supported OpenDRIVE Elements

| Element                                   | Support                   |
| ----------------------------------------- | ------------------------- |
| `<road>` with straight/arc geometry       | ✅ Required               |
| `<road>` with polynomial (cubic) geometry | ✅ Required               |
| `<laneSection>` with driving lanes        | ✅ Required               |
| `<junction>` with connection roads        | ✅ Required               |
| `<signal>` (traffic lights)               | ✅ Required               |
| `<object>` (static obstacles)             | ⚠️ Optional / best-effort |
| Superelevation, banking                   | ❌ Out of scope           |

### 2.4.2 Files to Create

**`arep_implementation/arep/maps/xodr_parser.py`**

```python
class OpenDRIVEParser:
    def parse(self, xodr_path: str) -> RoadGraph:
        """
        Parse a .xodr file and return an AREP RoadGraph.
        Uses Python's xml.etree.ElementTree (no external deps).
        Discretises each road geometry into centerline points at 1m intervals.
        """
```

**`arep_implementation/arep/maps/__init__.py`**

### 2.4.3 Scenario YAML Integration

```yaml
environment:
  road:
    source: xodr
    file: maps/town01_highway.xodr
    ego_start_road_id: "42"
    ego_start_s: 10.0 # s-coordinate along the road
    ego_start_lane_id: "-1"
```

**File to modify**: `arep_implementation/arep/scenario/parser.py`

- If `road.source == "xodr"`, call `OpenDRIVEParser().parse(file)` and use the result as the `RoadGraph`

### 2.4.4 Acceptance Criteria for P2.4

- [ ] Parsing the sample `TownSimple.xodr` from the `tests/fixtures/` directory produces a `RoadGraph` with ≥ 2 segments
- [ ] The resulting `RoadGraph.is_off_road()` returns correct results for known on/off-road positions
- [ ] A scenario using `source: xodr` runs to completion without geometry errors
- [ ] The Three.js scene renders the parsed road geometry correctly

---

---

# PHASE 3 — Product Polish

---

## P3.1 — OpenSCENARIO 2.0 Import / Export

**Goal**: Read standard `.osc` files into AREP `ScenarioDefinition` objects; write AREP YAML scenarios to `.osc` format. Enables interoperability with CARLA, ASAM member tools, and customer scenario libraries.

### 3.1.1 Import

**File to create**: `arep_implementation/arep/scenario/osc_importer.py`

Supports OpenSCENARIO 2.0 DSL `.osc` files (not the older XML 1.x format).

Key mappings:

- `actor` with `Vehicle` or `Pedestrian` → `traffic` NPC entry
- `act` with `trigger` on `TimeCondition` or `EntityCondition` → `trigger_type` / `trigger_value`
- `drive` action → `constant_velocity` behavior
- `brake` action → `hesitant_brake` BT with extracted deceleration
- Unknown actions → `scripted` behavior with raw parameter passthrough

### 3.1.2 Export

**File to create**: `arep_implementation/arep/scenario/osc_exporter.py`

Converts an AREP `ScenarioDefinition` to a valid `.osc` string. Parameterization blocks become OSC2 `parameter` declarations with constraint ranges.

### 3.1.3 API Endpoints

```
POST /api/scenarios/import/osc      — body: .osc file content
GET  /api/scenarios/{id}/export/osc — returns .osc file
```

### 3.1.4 Acceptance Criteria for P3.1

- [ ] Importing the sample `CutIn.osc` from ASAM example library produces a valid `ScenarioDefinition`
- [ ] Exporting LON-003 produces syntactically valid OpenSCENARIO 2.0
- [ ] Round-trip (AREP → OSC → AREP) preserves all trigger conditions and NPC parameters

---

## P3.2 — CI/CD Docker Image + GitHub Action

**Goal**: A single `docker run` command runs the full AREP scenario suite against a provided model and returns a pass/fail report. This is the capability CARLA cannot match (Unreal Engine won't run in a standard CI environment).

### 3.2.1 Dockerfile

**File to create**: `Dockerfile`

```dockerfile
FROM python:3.11-slim
WORKDIR /arep
COPY arep_implementation/ .
RUN pip install -e ".[api]"
COPY scenarios/ /arep/scenarios/
ENTRYPOINT ["python", "-m", "arep.cli.run_suite"]
# Default: run all 18 scenarios, 10 seeds each, with EmergencyBrakeModel
# Returns exit code 0 if pass_rate >= threshold, 1 otherwise
```

### 3.2.2 CLI Entry Point

**File to create**: `arep_implementation/arep/cli/run_suite.py`

```
Usage: python -m arep.cli.run_suite
         --scenarios all|LON|LAT|INT|VRU|EMG|MLT|<id>
         --runs-per-scenario 10
         --pass-threshold 0.8
         --model emergency_brake|constant|<import-path>
         --output-dir ./results/
         --format json|html
```

Exits with code `0` if `pass_rate >= pass_threshold`, `1` otherwise. Writes a JSON/HTML report to `--output-dir`.

### 3.2.3 GitHub Action

**File to create**: `.github/workflows/arep_suite.yml`

```yaml
name: AREP Scenario Suite
on: [push, pull_request]
jobs:
  run-suite:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Build AREP image
        run: docker build -t arep .
      - name: Run scenario suite
        run: docker run --rm -v $PWD/results:/arep/results arep
          --scenarios all --runs-per-scenario 5 --pass-threshold 0.7
      - name: Upload results
        uses: actions/upload-artifact@v4
        with:
          name: arep-results
          path: results/
```

### 3.2.4 Acceptance Criteria for P3.2

- [ ] `docker build -t arep .` succeeds in a clean environment
- [ ] `docker run arep --scenarios LON --runs-per-scenario 3` exits with code 0 or 1 and writes `results/report.json`
- [ ] The GitHub Action runs on every push and uploads the report artifact
- [ ] Total CI runtime for 5 runs × 18 scenarios < 10 minutes

---

## P3.3 — Reporting Dashboard + Regression Tracking

**Goal**: The frontend dashboard shows aggregate results across batch runs, scenario pass rates over time (model versioning), and failure heatmaps over the parameterization space.

### 3.3.1 Dashboard Pages

**File to create**: `orion-frontend/src/pages/Dashboard.jsx`

Views:

1. **Overview**: Total runs, overall pass rate, composite score distribution (histogram), top-5 failing scenarios
2. **Scenario Drill-down**: For a selected scenario — pass rate per seed, metric breakdown (Safety / Compliance / Stability / Reactivity), event timeline for worst run
3. **Failure Heatmap**: For scenarios with 2D parameterization (e.g., ego velocity × NPC initial_x), scatter plot coloured by verdict. Uses `recharts` ScatterChart.
4. **Model Regression**: Line chart of composite score over batch runs (x-axis = batch_id, i.e. time). Detects regressions > 5% and shows a warning badge.

### 3.3.2 API Endpoints Needed

```
GET /api/dashboard/summary
GET /api/dashboard/scenario/{id}/runs
GET /api/dashboard/scenario/{id}/heatmap?x_param=ego_velocity&y_param=lead_vehicle.initial_x
GET /api/dashboard/regression?scenario_id=LON-003
```

### 3.3.3 Acceptance Criteria for P3.3

- [ ] After running 3 batches of 10 runs, the regression chart shows 3 data points
- [ ] The failure heatmap for LON-003 shows correct pass/fail colouring across the parameter space
- [ ] A 5% regression in composite score triggers a visible warning in the UI

---

## P3.4 — Complete Scenario Library (60 Scenarios)

**Goal**: Expand from 18 to 60 core scenarios following the existing 6-category taxonomy. Each new scenario must have a `v2.0` reactive BT, full parameterization block, and a unique `master_seed`.

### Target Count by Category

| Category                   | Current | Target |
| -------------------------- | ------- | ------ |
| LON (Longitudinal)         | 4       | 10     |
| LAT (Lateral)              | 3       | 10     |
| INT (Intersection)         | 3       | 10     |
| VRU (Vulnerable Road User) | 3       | 10     |
| EMG (Emergency / Anomaly)  | 3       | 10     |
| MLT (Multi-Agent)          | 2       | 10     |
| **Total**                  | **18**  | **60** |

### New Scenarios Per Category (IDs reserved)

**LON-005 through LON-010**: following distance violation, stop-and-go traffic, sudden obstacle in lane, low-speed rear approach, speed bump, highway exit deceleration.

**LAT-004 through LAT-010**: parallel lane squeeze, high-speed lane change conflict, sideswipe approach, narrow road oncoming, forced lane change, lane closure merge, wet road lane departure.

**INT-003, INT-004, INT-006 through INT-010**: roundabout entry, stop sign violation, pedestrian crossing at intersection, traffic light amber dilemma, multi-vehicle gap acceptance, blind intersection.

**VRU-002, VRU-004 through VRU-010**: cyclist at crosswalk, child running between cars (non-occluded), pedestrian at night, e-scooter in bike lane, group pedestrian crossing, jaywalker mid-block, pedestrian with stroller.

**EMG-003, EMG-005 through EMG-010**: fallen object on highway, sudden road closure, dust storm (visibility 30m), vehicle fire ahead, emergency vehicle approach, flash flood water on road.

**MLT-002 through MLT-006, MLT-008 through MLT-010**: 3-vehicle chain brake, cut-in + pedestrian, tailgater + lead brake, merge conflict + cyclist, roundabout multi-entry.

---

---

# Execution Rules

## Development Sequence

Work proceeds strictly in phase order, item order:

```
P1.1 → P1.2 → P1.3 → P1.4 → P1.5
       ↓
P2.1 → P2.2 → P2.3 → P2.4
       ↓
P3.1 → P3.2 → P3.3 → P3.4
```

P1.2 and P1.3 can be developed in parallel (no dependency between them). All other items within a phase are sequential.

## Immutable Constraints (inherited from PROPOSED_IMPLEMENTATION.md)

1. **Determinism**: Same `master_seed` always produces identical simulation output. No wall-clock seeding. All randomness flows through `RandomManager`.
2. **No shared mutable state**: `WorldState` is deep-copied between ticks. NPC behavior state lives in `world.npc_behaviors[id]`, never in module-level variables.
3. **Binary verdict separation**: The evaluation monitor returns `PASS / FAIL / INCONCLUSIVE`. Metric scores are recorded separately. Never merge them.
4. **YAML immutability**: `ScenarioDefinition` is never mutated after parsing. `ScenarioParameterizer` creates a modified copy for each run.
5. **50Hz fixed timestep**: The simulation loop never derives `dt` from wall time. `dt = 0.02` always.

## Acceptance Gate

Before moving from Phase N to Phase N+1, **all** acceptance criteria for all items in Phase N must pass. No exceptions.

## Versioning

- Scenario YAMLs: `version: "2.0"` for all reactive BT scenarios. Increment to `"3.0"` only if the schema changes.
- API: All endpoints are under `/api/v1/` prefix (add this if not already present).
- This document: increment version header when any section is materially changed.

---

_This document is the governing specification. All implementation decisions resolve to it._
