# ORION — AREP (Autonomous Robustness Evaluation Platform)

# Claude Code Project Configuration

> This file is read by Claude Code at the start of every session in this project.
> It is project-local and does not affect any other project.

---

## 0. Standing Instructions for Claude Code

After every completed task, feature, or significant code change, update this file:

- Move anything newly completed out of Section 13 and document it in the relevant section
- Add new classes, functions, API endpoints, or conventions that were introduced
- Add new commands if any scripts or entrypoints were created
- Remove anything that is no longer accurate

Keep edits targeted — only update what changed, do not rewrite unrelated sections.

---

## 1. Project Overview

ORION is a deterministic, statistically rigorous evaluation platform for autonomous driving models.
It is NOT a game engine or a 3D simulator. It is a **testing harness**: you feed it a model, it runs
that model through parameterized scenarios hundreds of times, and it returns statistical safety scores.

**Two-part architecture:**

- `arep_implementation/` — Python backend (FastAPI + simulation core + evaluation pipeline)
- `orion-frontend/` — React + Three.js + Vite frontend (dashboard UI, future 3D visualization)

**The platform is called ORION. The Python package is called `arep`.**
Do not confuse the two names in code — imports are always `from arep.*`.

---

## 2. Stack & Versions

| Layer       | Technology                                                                        | Key constraint                  |
| ----------- | --------------------------------------------------------------------------------- | ------------------------------- |
| Python core | Python ≥ 3.10, numpy==1.26.0, scipy==1.11.3, pyyaml==6.0.1                        | Version-locked for determinism  |
| API         | FastAPI + uvicorn, SQLAlchemy 2.0, SQLite (dev) / PostgreSQL (prod)               | Auth via JWT (python-jose)      |
| Frontend    | React 18, Vite 5, React Router 6, Three.js r160, @react-three/fiber 8, Recharts 2 | No TypeScript yet               |
| Testing     | pytest with `--tb=short`, pytest-cov                                              | Run from `arep_implementation/` |
| Linting     | black + ruff + mypy                                                               | All must pass before commit     |

---

## 3. Project Structure

```
ORION/
├── arep_implementation/          # Python package root
│   ├── arep/
│   │   ├── core/                 # Physics, state, collision, observation, action
│   │   ├── simulation/           # SimulationEngine, WorldManager, NPC behavior trees
│   │   ├── scenario/             # YAML parser, schema, parameterizer, validator
│   │   ├── models/               # ModelInterface ABC + example models
│   │   ├── evaluation/           # Safety, compliance, stability, reactivity metrics
│   │   ├── execution/            # EvaluationRunner (batch pipeline)
│   │   ├── statistics/           # StatisticalAggregator
│   │   ├── api/                  # FastAPI app, routes, auth, schemas
│   │   ├── database/             # SQLAlchemy models, repository, connection
│   │   ├── visualization/        # Plotly dashboard (legacy — being replaced by frontend)
│   │   ├── config/               # SimulationConfig, get_config()
│   │   └── utils/                # exceptions, logging_config, validators, hashing
│   ├── config/default.yaml       # Master config (do not hardcode these values in code)
│   ├── scenarios/basic/          # Basic YAML scenarios (v1 format)
│   └── tests/                    # pytest test suite
├── scenarios/                    # Full scenario library (v2 format, categorized)
│   ├── lon/                      # Longitudinal control (LON-*)
│   ├── lat/                      # Lateral control (LAT-*)
│   ├── int/                      # Intersection negotiation (INT-*)
│   ├── vru/                      # Vulnerable road users (VRU-*)
│   ├── emg/                      # Emergency/anomalies (EMG-*)
│   └── mlt/                      # Multi-agent (MLT-*)
└── orion-frontend/               # React frontend
    └── src/
        ├── pages/                # DashboardPage, LandingPage, LoginPage, SignupPage
        ├── components/           # auth/, common/, landing/, simulation/
        ├── hooks/                # useSimulationStream.js
        ├── context/              # AuthContext (JWT token management)
        └── services/api.js       # All fetch calls go through here — do not use fetch() directly
```

---

## 4. Core Design Principles (NON-NEGOTIABLE)

### Determinism first

- Fixed timestep ONLY: `dt = 0.02s` (50 Hz). Never use `time.time()`, `datetime.now()`, or `random` module directly.
- All randomness goes through `RandomManager` — always pass `rng: RandomManager` as a parameter.
- Seeded per-run: `seed = master_seed + run_index`. Never change this pattern.
- Dependency versions are pinned in `pyproject.toml`. Do not upgrade them without explicit instruction.

### Immutable state

- `WorldState` and `VehicleState` are copied before mutation. Use `.copy()` — never mutate in place.
- Every `SimulationEngine.step()` returns a NEW `WorldState`. The input world is never modified.

### Simulation step order (CRITICAL — never reorder)

1. Validate action
2. Apply physics to ego vehicle
3. Update dynamic objects
4. Update traffic lights
5. Check collisions
6. Check other termination conditions
7. Increment time

---

## 5. Key Classes & Interfaces

### Implementing a model

All models MUST subclass `ModelInterface` from `arep.models.interface`:

```python
from arep.models.interface import ModelInterface
from arep.core.observation import Observation
from arep.core.action import Action

class MyModel(ModelInterface):
    def predict(self, observation: Observation) -> Action:
        # Must be deterministic for a given observation + internal state
        ...
    def reset(self) -> None:
        # Called before each new simulation run
        ...
```

Never call `model.predict()` directly in production code — always wrap with `ModelWrapper` which handles timing and error logging.

### Action values

`Action` has three normalized fields, all in `[-1.0, 1.0]`:

- `steering`: negative = left, positive = right (maps to ±`max_steering_angle = 0.5 rad`)
- `throttle`: `[0.0, 1.0]` — maps to `max_acceleration = 3.0 m/s²`
- `brake`: `[0.0, 1.0]` — maps to `max_deceleration = 8.0 m/s²`

Use `Action.zero()` and `Action.emergency_brake()` utility constructors.

### Physics modes

`PhysicsMode.KINEMATIC` — bicycle model, fast, use for batch runs.
`PhysicsMode.DYNAMIC` — Pacejka tire model with surface friction. Use when testing tire/surface behavior.
`SurfaceType` enum: `DRY_ASPHALT (μ=1.0)`, `WET_ASPHALT (μ=0.5)`, `ICE (μ=0.2)`, `GRAVEL (μ=0.6)`.

### Running an evaluation

```python
from arep.execution.runner import EvaluationRunner
runner = EvaluationRunner()
result = runner.run_batch(
    scenario_path="scenarios/lon/LON-003_emergency_stop.yaml",
    model=MyModel(),
    num_runs=100,
    master_seed=42,
)
print(result.aggregated.to_dict())
```

### Streaming a live run (P1.1)

For frontend/3D visualisation — pairs with `WS /ws/simulation/{run_id}`:

```python
from arep.api.sim_registry import start_run, get_registry

run = await start_run(
    scenario_path="scenarios/basic/straight_road_lead_vehicle.yaml",
    model_name="EmergencyBrake",
    master_seed=42,
    tick_interval=0.02,   # 50 Hz wall-clock; pass 0.0 for headless full-speed
)
q = run.subscribe()             # bounded asyncio.Queue, drops oldest on overflow
frame = await q.get()            # dict matching engine.get_tick_frame() schema
run.unsubscribe(q)
```

- `SimulationEngine.run_async(on_tick=...)` drives the loop and calls `on_tick(world, action)` each step. It preserves the synchronous `step()` determinism — wall-clock pacing only affects delivery latency.
- `SimulationEngine.get_tick_frame(world, action, scenario_name, speed_limit)` is the single source of truth for the WebSocket JSON frame schema. Do not duplicate frame construction elsewhere; add fields here when extending the protocol.
- `monitor.metrics_current` in the frame is a per-tick *proxy* (collision flag + speed-limit compliance). Authoritative scores still come from `CompositeEvaluator` after the run ends.
- `LiveRun` (in `api/sim_registry.py`) stores `final_metrics` after run completion, populated from the last tick frame's `monitor.metrics_current`. Composite score is computed inline: `safety×0.5 + compliance×0.2 + stability×0.15 + reactivity×0.15`. These are proxy scores until P1.4 wires `CompositeEvaluator` to live runs.

---

## 6. Scenario System

### File format

All scenarios are YAML. Two versions exist:

- **v1** (`arep_implementation/scenarios/basic/`) — simple, for unit tests
- **v2** (`scenarios/*/`) — production format with full `parameterization:` block

Always write new scenarios in v2 format. Use existing files like `LON-003_emergency_stop.yaml` as the canonical template.

### Naming convention

`[CATEGORY]-[SEQ]_description.yaml` — e.g. `LON-003_emergency_stop.yaml`
Categories: `LON`, `LAT`, `INT`, `VRU`, `EMG`, `MLT`

### The foundational taxonomy rule

**One scenario = one behavioral requirement.** Weather, lighting, and surface friction are
`parameterization` modifiers — NOT separate scenarios. Never create a new scenario file
just to change the weather.

### NPC behavior types (available in `behavior.type`)

Defined in `simulation/npc_bt.py`:

- `constant_velocity` — maintains fixed speed
- `reactive_vehicle` — responds to TTC triggers; supports `bt_type`: `hesitant_brake`, `aggressive_cut_in`
- `follow_lane` — basic lane following
- `scripted` — event-driven via the `events:` block in YAML
- `pedestrian` — VRU movement model

---

## 7. Evaluation Metrics

Four metric modules in `arep/evaluation/`, each returns a typed result dataclass:

| Module          | Class               | Key output field                                                                       |
| --------------- | ------------------- | -------------------------------------------------------------------------------------- |
| `safety.py`     | `SafetyMetrics`     | `safety_score` [0,1] — 50% collision penalty + 30% min TTC + 20% critical TTC fraction |
| `compliance.py` | `ComplianceMetrics` | `compliance_score` — speed limit, lane keeping                                         |
| `stability.py`  | `StabilityMetrics`  | `stability_score` — control smoothness                                                 |
| `reactivity.py` | `ReactivityMetrics` | `reactivity_score` — response latency to threats                                       |

`CompositeEvaluator` (in `evaluation/composite.py`) combines all four into a single `composite_score`.

A test **passes** when: `collision_rate < 0.01` and `intervention_rate < 0.05` across N runs.

TTC thresholds: `TTC_SAFE = 10.0s` (score = 1.0), `TTC_CRITICAL = 2.0s` (flags a critical step).

**Never change metric weights** (`COLLISION_WEIGHT = 0.50`, `MIN_TTC_WEIGHT = 0.30`, `CRITICAL_TTC_WEIGHT = 0.20`) without updating the specification document and all existing baselines.

---

## 8. API

FastAPI backend. All routes are prefixed `/api`. Auth is JWT Bearer token.

```
GET    /health
GET    /models/
GET    /scenarios/
POST   /evaluate/single          body: {scenario_path, model_name, master_seed}
POST   /evaluate/batch           body: {scenario_path, model_name, num_runs, master_seed}
GET    /jobs/
GET    /results/model/{model_name}
GET    /results/batch/{batch_job_id}
POST   /api/runs/                body: {scenario_path, model_name, master_seed, tick_interval}
GET    /api/runs/                list live runs (returns score fields after completion)
GET    /api/runs/{run_id}        live-run status + scores
DELETE /api/runs/{run_id}        cancel a live run
WS     /ws/simulation/{run_id}   live tick frames (auth: ?token=<jwt>)
```

`GET /api/runs/` and `GET /api/runs/{run_id}` return `RunStatusResponse` which includes:
`composite_score`, `safety_score`, `compliance_score`, `stability_score`, `reactivity_score`, `collision_occurred` — populated once `status == "completed"`.

Note: only the auth router (`/api/auth/*`) and the live-run router (`/api/runs/*`) are mounted under `/api`. Other routers are mounted without a prefix — keep this in mind when wiring the frontend proxy.

Available built-in model names (registered in `api/routes.py` `AVAILABLE_MODELS`):
`"ConstantAction"`, `"EmergencyBrake"`, `"SimpleLaneKeep"`, `"Random"`

To add a new model to the API, add it to the `AVAILABLE_MODELS` dict in `api/routes.py`.
Do not instantiate models outside of that dict — the dict is the registry.

All API errors return `{"detail": "..."}` — match this shape in new error handlers.

---

## 9. Frontend

React 18, Vite 5, React Router 6. No TypeScript — plain JSX.

### Rules

- All HTTP calls go through `src/services/api.js` — never use `fetch()` directly in a component.
- Auth token lives in `AuthContext` — use `const { user, token, logout } = useAuth()` everywhere.
- Never store the JWT token in `localStorage` — it is managed in `AuthContext` already.
- Dashboard sections: `overview`, `scenarios`, `runs`, `models`, `settings` — these are string keys used in `Sidebar`.
- Charts use Recharts (`LineChart`, `RadarChart`, `BarChart`) — do not add Chart.js or D3.
- 3D visualization uses `@react-three/fiber` + `@react-three/drei` — do not use raw Three.js imperative API in React components.
- CSS is co-located: `Component.jsx` + `Component.css` in the same folder. No CSS modules, no Tailwind.

### Adding a new API call

Add it to `src/services/api.js` following the existing pattern, then call `api.myNewMethod(token)` in the component.

### Live simulation WebSocket (P1.1 — complete)

Backend streams at `WS /ws/simulation/{run_id}?token=<jwt>`; consumer is wired end-to-end:

- `src/hooks/useSimulationStream.js` — owns the WebSocket. Returns `{ frame, isConnected, status, error, latencyRef }`. Handles exponential-backoff reconnect (max 3 attempts) and cleans up on unmount. Do not open sockets from components directly.
- `src/components/simulation/SimulationViewer.jsx` — R3F scene (road, ego, NPCs) + HTML HUD overlay (sim time, speed, g-force, metric bars, verdict badge). Mounted at `/simulation/:runId`. Has a `← Dashboard` back button (glass style, centered top) for navigation.
- Frame shape is the contract frozen in `SimulationEngine.get_tick_frame()`. To extend the protocol: add fields there, then consume in the hook/viewer.
- Server closes with `{"event": "stream_end", ...}` — hook handles it before deciding whether to reconnect.
- Latency is measured from `frame.emit_ts_ms` against the client's `Date.now()`; the running average and max are exposed via `latencyRef.current` for HUD display.
- Control-plane calls (`POST /api/runs/`, etc.) go through `src/services/api.js` (`api.startRun`, `api.getLiveRun`, `api.cancelLiveRun`) — the hook only owns the WS.

### Dashboard live-run display

- `DashboardPage.jsx` fetches runs via `api.getRuns(token)` → `GET /api/runs/` (NOT `/results/runs` — that endpoint does not exist).
- Has a **↻ Refresh** button that increments `refreshCount` state, triggering a data re-fetch. Use this after completing a run to see scores populate.
- Run score fields (`composite_score`, `safety_score`, etc.) are populated only when `status == "completed"`.
- Expected behavior per model on `straight_road_lead_vehicle.yaml`: `EmergencyBrake` → PASS, `ConstantAction` / `SimpleLaneKeep` / `Random` → FAIL (they do not brake — this is correct evaluation behavior, not a bug).

---

## 10. Database

SQLAlchemy 2.0 with SQLite in development (`sqlite:///arep.db`) and PostgreSQL in production.
Connection URL comes from `config/default.yaml` `database.url` — never hardcode it.

Always use the `session_scope()` context manager from `arep.database.connection`:

```python
with session_scope() as db:
    repo = ScenarioRepository(db)
    scenarios = repo.list_all()
```

Never use a raw `Session` — always go through repository classes in `database/repository.py`.

---

## 11. Common Commands

Run these from `arep_implementation/` unless stated otherwise:

```bash
# Setup (first time)
python3 -m venv venv && source venv/bin/activate
pip install -e ".[dev,api]"

# Start backend API (use python -m uvicorn — bare uvicorn may not be on PATH in all envs)
python -m uvicorn arep.api.app:app --reload --port 8000

# Start frontend (run from orion-frontend/)
npm run dev

# Run all tests
pytest

# Run specific test file
pytest tests/test_integration.py -v

# Run with coverage
pytest --cov=arep --cov-report=term-missing

# End-to-end live-streaming smoke test (spawns in-process uvicorn,
# hits POST /api/runs/, connects to WS, prints frames)
PYTHONPATH=. python scripts/ws_smoke.py

# Lint + format
black arep/ tests/
ruff check arep/ tests/
mypy arep/

# Start everything (from project root)
./start.sh        # Linux/Mac
start.bat         # Windows
```

---

## 12. Hard Rules — Never Do These

- **Never mutate `WorldState` or `VehicleState` in place.** Always `.copy()` first.
- **Never use Python's `random` module.** Use `RandomManager` and pass it explicitly.
- **Never use `time.time()` or `datetime.now()` inside simulation code.** Use `world.sim_time`.
- **Never change the simulation step order** (validate → physics → NPCs → lights → collision → termination → increment time).
- **Never change pinned dependency versions** (`numpy==1.26.0`, `scipy==1.11.3`) without explicit instruction — it breaks determinism tests.
- **Never create a new scenario for a weather/lighting variant.** Add it to the `parameterization:` block.
- **Never call `model.predict()` directly** in runner or API code — always use `ModelWrapper`.
- **Never use `fetch()` directly in React components** — always use `src/services/api.js`.
- **Never hardcode seeds, config values, or API URLs** — they come from `config/default.yaml` and `vite.config.js` proxy.

---

## 13. What Is Not Built Yet (Active Development Areas)

Refer to `AREP_IMPLEMENTATION_ROADMAP.MD` as the source of truth. Current gaps:

1. **Road topology engine (P1.2)** — only flat 2-lane straight road exists; intersections and merge lanes are not implemented. This is the next item after P1.1 acceptance.
2. **Sensor simulation** — no LiDAR, camera, GPS/IMU output; the observation system uses ground-truth world state.
3. **RL model training loop** — `local_executor.py` is a scaffold only.
4. **CompositeEvaluator wired to live runs (P1.4)** — dashboard scores are currently per-tick proxy metrics from `monitor.metrics_current`, not full post-run evaluation.
5. **3D visualization polish (P3.5)** — GLTF vehicle/pedestrian/animal models (Kenney CC0 assets), Sky/Fog/grass environment, instanced roadside trees and street lights, road surface texture. Deferred to Phase 3. Current visualization is flat bird's-eye box geometry.

When working on these areas, check the roadmap document before writing any code.
