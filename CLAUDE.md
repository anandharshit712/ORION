# ORION — AREP (Autonomous Robustness Evaluation Platform)

# Claude Code Project Configuration

> Claude Code reads file each session start. Project-local, no other project affected.

---

## 0. Standing Instructions for Claude Code

After every completed task, feature, or significant code change, update this file:

- Move completed items out of Section 13, document in relevant section
- Add new classes, functions, API endpoints, conventions introduced
- Add new commands if scripts or entrypoints created
- Remove anything no longer accurate

Edits targeted — only update what changed, don't rewrite unrelated sections.

### Governing Documents

Two roadmap documents exist. Know the difference:

- **`ORION_SAAS_ROADMAP.md`** — governs **priority ordering**. What to build next. When two tasks compete, this doc wins. Source of truth for Phase 1–5 scope.
- **`AREP_IMPLEMENTATION_ROADMAP.md`** — governs **technical implementation detail**. How to build it. Specific data structures, acceptance criteria, file names.

When they conflict on priority: SaaS roadmap wins. When you need implementation depth: read the technical roadmap.

---

## 1. Project Overview

ORION = deterministic, statistically rigorous eval platform for autonomous driving models.
NOT game engine or 3D simulator. **Testing harness**: feed model, runs through parameterized scenarios hundreds of times, returns statistical safety scores.

**Two-part architecture:**

- `arep_implementation/` — Python backend (FastAPI + simulation core + evaluation pipeline)
- `orion-frontend/` — React + Three.js + Vite frontend (dashboard UI, future 3D visualization)

**Platform = ORION. Python package = `arep`.**
Don't confuse names in code — imports always `from arep.*`.

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
- All randomness through `RandomManager` — always pass `rng: RandomManager` as parameter.
- Seeded per-run: `seed = master_seed + run_index`. Never change this pattern.
- Dependency versions pinned in `pyproject.toml`. Don't upgrade without explicit instruction.

### Immutable state

- `WorldState` and `VehicleState` copied before mutation. Use `.copy()` — never mutate in place.
- Every `SimulationEngine.step()` returns NEW `WorldState`. Input world never modified.

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

Never call `model.predict()` directly in production code — always wrap with `ModelWrapper` for timing and error logging.

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

- `SimulationEngine.run_async(on_tick=...)` drives loop, calls `on_tick(world, action)` each step. Preserves synchronous `step()` determinism — wall-clock pacing only affects delivery latency.
- `SimulationEngine.get_tick_frame(world, action, scenario_name, speed_limit)` = single source of truth for WebSocket JSON frame schema. Don't duplicate frame construction elsewhere; add fields here when extending protocol.
- `monitor.metrics_current` in frame = per-tick *proxy* (collision flag + speed-limit compliance). Authoritative scores still come from `CompositeEvaluator` after run ends.
- `LiveRun` (in `api/sim_registry.py`) stores `final_metrics` after run completion, populated from last tick frame's `monitor.metrics_current`. Composite score computed inline: `safety×0.5 + compliance×0.2 + stability×0.15 + reactivity×0.15`. Proxy scores until P1.4 wires `CompositeEvaluator` to live runs.

---

## 6. Scenario System

### File format

All scenarios YAML. Two versions:

- **v1** (`arep_implementation/scenarios/basic/`) — simple, for unit tests
- **v2** (`scenarios/*/`) — production format with full `parameterization:` block

Always write new scenarios in v2 format. Use `LON-003_emergency_stop.yaml` as canonical template.

### Naming convention

`[CATEGORY]-[SEQ]_description.yaml` — e.g. `LON-003_emergency_stop.yaml`
Categories: `LON`, `LAT`, `INT`, `VRU`, `EMG`, `MLT`

### The foundational taxonomy rule

**One scenario = one behavioral requirement.** Weather, lighting, surface friction = `parameterization` modifiers — NOT separate scenarios. Never create new scenario file just to change weather.

### NPC behavior types (available in `behavior.type`)

Defined in `simulation/npc_bt.py`:

- `constant_velocity` — maintains fixed speed
- `reactive_vehicle` — responds to TTC triggers; supports `bt_type`: `hesitant_brake`, `aggressive_cut_in`
- `follow_lane` — basic lane following
- `scripted` — event-driven via `events:` block in YAML
- `pedestrian` — VRU movement model

---

## 7. Evaluation Metrics

Four metric modules in `arep/evaluation/`, each returns typed result dataclass:

| Module          | Class               | Key output field                                                                       |
| --------------- | ------------------- | -------------------------------------------------------------------------------------- |
| `safety.py`     | `SafetyMetrics`     | `safety_score` [0,1] — 50% collision penalty + 30% min TTC + 20% critical TTC fraction |
| `compliance.py` | `ComplianceMetrics` | `compliance_score` — speed limit, lane keeping                                         |
| `stability.py`  | `StabilityMetrics`  | `stability_score` — control smoothness                                                 |
| `reactivity.py` | `ReactivityMetrics` | `reactivity_score` — response latency to threats                                       |

`CompositeEvaluator` (in `evaluation/composite.py`) combines all four into single `composite_score`.

Test **passes** when: `collision_rate < 0.01` and `intervention_rate < 0.05` across N runs.

TTC thresholds: `TTC_SAFE = 10.0s` (score = 1.0), `TTC_CRITICAL = 2.0s` (flags critical step).

**Never change metric weights** (`COLLISION_WEIGHT = 0.50`, `MIN_TTC_WEIGHT = 0.30`, `CRITICAL_TTC_WEIGHT = 0.20`) without updating specification document and all existing baselines.

---

## 8. API

FastAPI backend. All routes prefixed `/api`. Auth = JWT Bearer token.

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
POST   /api/runs/batch           async batch — body: {scenario_path, model_name, num_runs, master_seed}; returns 202 {batch_id, status, num_runs, enqueued, credits_remaining}
GET    /api/runs/batch/{id}/status   live progress {status, total, queued, running, completed, failed, composite_mean, collision_rate, error_message}
```

`GET /api/runs/` and `GET /api/runs/{run_id}` return `RunStatusResponse` with:
`composite_score`, `safety_score`, `compliance_score`, `stability_score`, `reactivity_score`, `collision_occurred` — populated once `status == "completed"`.

Note: only auth router (`/api/auth/*`) and live-run router (`/api/runs/*`) mounted under `/api`. Other routers mounted without prefix — keep in mind when wiring frontend proxy.

Built-in model names (registered in `api/routes.py` `AVAILABLE_MODELS`):
`"ConstantAction"`, `"EmergencyBrake"`, `"SimpleLaneKeep"`, `"Random"`

To add new model to API, add to `AVAILABLE_MODELS` dict in `api/routes.py`.
Don't instantiate models outside that dict — dict is registry.

All API errors return `{"detail": "..."}` — match this shape in new error handlers.

---

## 9. Frontend

React 18, Vite 5, React Router 6. No TypeScript — plain JSX.

### Rules

- All HTTP calls through `src/services/api.js` — never use `fetch()` directly in component.
- Auth token lives in `AuthContext` — use `const { user, token, logout } = useAuth()` everywhere.
- Never store JWT token in `localStorage` — managed in `AuthContext` already.
- Dashboard sections: `overview`, `scenarios`, `runs`, `models`, `settings` — string keys used in `Sidebar`.
- Charts use Recharts (`LineChart`, `RadarChart`, `BarChart`) — don't add Chart.js or D3.
- 3D visualization uses `@react-three/fiber` + `@react-three/drei` — don't use raw Three.js imperative API in React components.
- CSS co-located: `Component.jsx` + `Component.css` same folder. No CSS modules, no Tailwind.

### Adding a new API call

Add to `src/services/api.js` following existing pattern, then call `api.myNewMethod(token)` in component.

### Live simulation WebSocket (P1.1 — complete)

Backend streams at `WS /ws/simulation/{run_id}?token=<jwt>`; consumer wired end-to-end:

- `src/hooks/useSimulationStream.js` — owns WebSocket. Returns `{ frame, isConnected, status, error, latencyRef }`. Handles exponential-backoff reconnect (max 3 attempts), cleans up on unmount. Don't open sockets from components directly.
- `src/components/simulation/SimulationViewer.jsx` — R3F scene (road, ego, NPCs) + HTML HUD overlay (sim time, speed, g-force, metric bars, verdict badge). Mounted at `/simulation/:runId`. Has `← Dashboard` back button (glass style, centered top).
- Frame shape frozen in `SimulationEngine.get_tick_frame()`. To extend protocol: add fields there, consume in hook/viewer.
- Server closes with `{"event": "stream_end", ...}` — hook handles before deciding reconnect.
- Latency measured from `frame.emit_ts_ms` against client `Date.now()`; running average and max exposed via `latencyRef.current` for HUD display.
- Control-plane calls (`POST /api/runs/`, etc.) go through `src/services/api.js` (`api.startRun`, `api.getLiveRun`, `api.cancelLiveRun`) — hook only owns WS.

### Dashboard live-run display

- `DashboardPage.jsx` fetches runs via `api.getRuns(token)` → `GET /api/runs/` (NOT `/results/runs` — that endpoint doesn't exist).
- Has **↻ Refresh** button incrementing `refreshCount` state, triggering data re-fetch. Use after completing run to see scores populate.
- Run score fields (`composite_score`, `safety_score`, etc.) populated only when `status == "completed"`.
- Expected behavior per model on `straight_road_lead_vehicle.yaml`: `EmergencyBrake` → PASS, `ConstantAction` / `SimpleLaneKeep` / `Random` → FAIL (don't brake — correct evaluation behavior, not bug).

---

## 10. Database

SQLAlchemy 2.0 with SQLite in dev (`sqlite:///arep.db`), PostgreSQL in prod.
Connection URL from `config/default.yaml` `database.url` — never hardcode it.

Always use `session_scope()` context manager from `arep.database.connection`:

```python
with session_scope() as db:
    repo = ScenarioRepository(db)
    scenarios = repo.list_all()
```

Never use raw `Session` — always go through repository classes in `database/repository.py`.

---

## 11. Common Commands

Run from `arep_implementation/` unless stated otherwise:

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
./start.sh        # Linux/Mac (bash)
start.bat         # Windows (cmd.exe)
./start.ps1       # Windows (PowerShell) — pass -NoReload to disable uvicorn --reload
```

---

## 12. Hard Rules — Never Do These

- **Never mutate `WorldState` or `VehicleState` in place.** Always `.copy()` first.
- **Never use Python's `random` module.** Use `RandomManager`, pass explicitly.
- **Never use `time.time()` or `datetime.now()` inside simulation code.** Use `world.sim_time`.
- **Never change simulation step order** (validate → physics → NPCs → lights → collision → termination → increment time).
- **Never change pinned dependency versions** (`numpy==1.26.0`, `scipy==1.11.3`) without explicit instruction — breaks determinism tests.
- **Never create new scenario for weather/lighting variant.** Add to `parameterization:` block.
- **Never call `model.predict()` directly** in runner or API code — always use `ModelWrapper`.
- **Never use `fetch()` directly in React components** — always use `src/services/api.js`.
- **Never hardcode seeds, config values, or API URLs** — from `config/default.yaml` and `vite.config.js` proxy.

---

## 13. What Is Not Built Yet (Active Development Areas)

**Priority authority**: `ORION_SAAS_ROADMAP.md`. **Implementation detail**: `AREP_IMPLEMENTATION_ROADMAP.md`. Read both before writing code in these areas.

### Phase 1 — SaaS Platform Foundation (current phase, P1.1–P1.3 complete)

1. **Stripe billing (P1.4 SaaS)** — no payment, no tiers, no credit top-ups. `api/billing.py` scaffold only. Credits are deducted/refunded by P1.3 but never replenished beyond signup grant. **Start here.**
2. **Road topology engine (P1.5 SaaS)** — only flat 2-lane straight road. No intersections, merge lanes, roundabouts. Blocks ~35% of scenario library (all INT-*, EMG-002, MLT-*). `core/road.py` and `core/road_templates.py` do not exist.

### Done (P1.1 + P1.2 + P1.3)

- **Multi-tenancy (P1.1)** — `organisations`, `api_keys` tables. JWT carries `org_id`+`role`. `OrgAuthMiddleware` resolves both JWT and API keys. `/api/orgs/me`, `/api/orgs/invite`, `/api/keys/` CRUD. All eval/batch/jobs/results/live-run routes scoped by `org_id`.
- **Model submission (P1.2)** — `models` table + `ModelRepository`. `/api/models/upload` (multipart cloudpickle), `/api/models/register` (Docker), `/api/models/`, `/api/models/{id}` GET/DELETE. `models/resolver.py` dispatches built-in name → instance, UUID → `SubprocessModelRunner` or `HttpModelAdapter`. Org isolation enforced. `orion-sdk/` package: `OrionClient`, `upload_model()`, `orion` CLI (`models`, `runs`, `keys` commands).
- **Async batch queue (P1.3)** — Celery + Redis. `arep/worker/celery_app.py` + `arep/worker/tasks.py` (`run_single_simulation`, `run_batch_simulations`). `POST /api/runs/batch` atomically deducts `num_runs` credits via `OrganisationRepository.deduct_credits()` (FOR UPDATE row lock), creates a `BatchJobRecord` (`status=queued`), fans out N tasks on the `simulation` queue, and returns 202 in <300 ms. Workers write `RunRecord` rows + bump `runs_completed`/`runs_failed`; the last task to finish triggers `BatchJobRepository.finalise_if_done()` which aggregates from per-run rows and flips status to `completed`. Failed tasks refund 1 credit via `OrganisationRepository.add_credits()`. `GET /api/runs/batch/{id}/status` exposes live progress. Tests run Celery in `task_always_eager` mode (no broker required) — see `tests/test_batch_queue.py`. Worker container + Flower UI defined in `infrastructure/docker-compose.yml` (`worker`, `flower` services). Broker URL via `ORION_REDIS_URL` env var (default `redis://localhost:6379/0`).

### Deferred (Phase 2+)

- **Sensor simulation** — no LiDAR, camera, GPS/IMU; observation = ground-truth state. Explicitly deprioritised from Phase 1 in `ORION_SAAS_ROADMAP.md`.
- **CompositeEvaluator wired to live runs** — dashboard scores are per-tick proxy metrics from `monitor.metrics_current`, not full post-run evaluation.
- **Statistical confidence intervals (P2.1)** — scores are point estimates, no CI or distribution analysis yet.
- **3D visualization polish (P3.5)** — current viz = flat bird's-eye box geometry. GLTF assets, Sky/Fog, road textures deferred to Phase 3.