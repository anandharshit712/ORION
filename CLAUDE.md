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

All project documentation lives in `docs/`. Three documents govern; each owns one domain, and they do not overlap:

- **`docs/ROADMAP.md`** (v3.0) — governs **what to build next and how**. Phase 0–6 scope, the known-defect register (D-01…D-13), per-phase implementation specs (data structures, file names, acceptance criteria), honest positioning, risks, timeline. When two tasks compete, this doc decides. It replaces the old `ORION_SAAS_ROADMAP.md` + `AREP_IMPLEMENTATION_ROADMAP.md` pair.
- **`docs/ARCHITECTURE.md`** — governs **the scenario taxonomy and the 4-layer execution architecture**: the "one scenario = one behavioral requirement" rule, the six categories, the strict scenario schema, L1–L4 layer contracts, the integration contract. Read before touching `scenario/`, `simulation/`, or adding scenarios.
- **`docs/UI_DESIGN.md`** (v1.0) — governs **ALL frontend/UI visual work**. The binding design system ("Mission Control"): tokens, typography, components, theming, page-by-page specs. Any change under `orion-frontend/` must conform. Approved sample = `design/sample-mission-control.html`. See Section 9.

Supporting, non-governing: `docs/PROJECT_IDEA.pdf` (the detailed product idea — exec summary, positioning, status, business model), `docs/MARKET.md` (19-competitor analysis, the four moats), `docs/reference/` (external research), `docs/archive/` (superseded originals — historical only, never cite as authority).

**Phase 0 (Security & Score Integrity) is complete** — see Section 13 for what each defect became. Current priority: Phase 1.4 (Stripe billing) and 1.5 (road topology). `docs/METHODOLOGY.md` now documents scoring and must be updated alongside any scoring change.

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
| Testing     | pytest with `--tb=short`, pytest-cov                                              | Run from `arep_implementation/`; CI gate at 70% coverage |
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
        ├── pages/                # DashboardPage, LandingPage, LoginPage, SignupPage, ResetPasswordPage, VerifyEmailPage, BillingPage
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

### Running a customer model (sandbox)

Customer artefacts are hostile input. `SubprocessModelRunner` (`models/sandbox.py`) runs them
in a locked-down child: env whitelist (no `ORION_*`), network namespace when the host allows
it plus an in-process socket block, fresh tmpdir as cwd/`TMPDIR`/`HOME`, POSIX rlimits, and a
hard wall-clock kill per call and per run.

- Limits come from `get_config().sandbox` (`config/default.yaml` → `sandbox:`, env
  `ORION_SANDBOX_*`). Never hardcode them at a call site.
- `ModelSandboxError` (in `utils/exceptions.py`) means the run is **void** — resource
  violation, hang, or crash. `ModelWrapper` and `EvaluationRunner` re-raise it on purpose so
  the worker fails the run and refunds the credit. Never catch it to "keep the run going": a
  truncated run scored as safe is worse than no score.
- A model that merely raises inside `predict()` is different — that yields
  `Action.emergency_brake()` for the tick and the run continues.
- Always `close()` an out-of-process model. `EvaluationRunner._release_model()` does this in
  a `finally`; if you add a new execution path, do the same or you leak a child process —
  or, on the Docker path, a container.
- **The Docker path starts a real container (Phase 2, D-01 step 2).** `ContainerModelRunner`
  (`models/container.py`) runs the customer image with `--cap-drop=ALL`,
  `no-new-privileges`, `--read-only` plus a noexec tmpfs, memory/CPU/PID limits, the port
  published on `127.0.0.1` only, and an empty `--env-file` so no `ORION_*` credential is
  inherited. Set `ORION_CONTAINER_RUNTIME=runsc` for gVisor, and
  `ORION_REQUIRE_HARDENED_RUNTIME=true` in production so the API refuses to run customer code
  under plain runc. Before this, `resolve_model` returned an `HttpModelAdapter` aimed at
  `localhost:<port>` and assumed something else had started a container — nothing had, so the
  path the pickle gate recommends had no boundary at all.
  **Not yet exercised against a live Docker daemon**: the command construction is unit-tested,
  the execution path is not.
- `Observation.to_dict()`/`from_dict()` is the wire format for out-of-process models. Extend
  both sides together, or the sandbox and HTTP adapters silently drop fields.

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
- **The frame is canonical (Phase 0.5, D-06)**: its content is a pure function of
  `(seed, scenario, tick)`. Anything you add to `get_tick_frame()` must be deterministic —
  no wall-clock, no host state, no run ids. Non-deterministic transport fields go at the
  WebSocket send site instead, which is where `emit_ts_ms` is now stamped. `FrameHasher`
  (`utils/hashing.py`) folds the canonical frames into a per-run digest stored on
  `RunRecord.frame_hash` and `LiveRun.frame_hash`, and sent in the `stream_end` message.
  Same `(model, scenario, seed)` → same digest; `tests/test_frame_determinism.py` enforces it.
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

### Road topology (Phase 1.5)

A scenario declares its shape with `environment.road.template` plus optional
`template_params`, naming a factory in `arep/core/road_templates.py`:
`highway_straight`, `urban_straight`, `t_junction`, `four_way_intersection`,
`highway_onramp`, `roundabout`.

```yaml
environment:
  road:
    type: urban
    lanes: 2
    lane_width: 3.5
    speed_limit: 11.11
    template: four_way_intersection      # omit for a flat straight road
    template_params:
      arm_length: 80.0
      has_traffic_light: false
```

- **Omitting `template` is supported and means the flat straight road.** Every scenario written
  before 1.5 keeps the geometry it was scored on, so stored results stay comparable.
- `lanes`, `lane_width` and `speed_limit` from the road block are passed to the factory;
  `template_params` overrides them. An unknown template or an unknown parameter raises
  `ScenarioParseError` at build time — never a silent fallback to a straight road, which would
  score a model on geometry it was never shown.
- `WorldState.road_graph` carries the graph **alongside** `lanes`, not instead of it. Lanes
  answer "where is the centreline" for observations and scoring; the graph answers "am I on the
  road at all" and "is there a junction here", which parallel lines cannot. `check_off_road()`
  and `get_speed_limit()` prefer the graph when present.
- Topology is declared, not inferred from `road_type`: "urban" describes a speed limit and a
  feel, not a shape — INT-001 is a four-way stop and LAT-001 is a straight road, and both are
  urban.

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

**Scoring methodology is documented in `docs/METHODOLOGY.md`** — every weight, threshold
and stated approximation, written for a customer's safety reviewer. Update it in the same
change as any scoring change, and add a row to its change log: scores are only comparable
within a scoring version.

**Metric defect status (Phase 0.5):**

- ~~D-05 lane compliance stub~~ — **closed.** `EgoSnapshot` records signed `lane_offset`,
  `lane_width` and `vehicle_half_width`; in-lane means the *body* is inside the line
  (`|offset| + half_width <= lane_width/2`), because a centre-point test against the nearest
  lane is tautological. Lane 0 is now centred on y=0 to match what scenarios mean by y=0.
- ~~D-12 weight transfer off-by-one~~ — **closed.** Uses the current step's commanded
  acceleration; the achieved-value residual is documented in `docs/METHODOLOGY.md`.
- ~~D-11 TTC constant-velocity~~ — **closed (Phase 2.1).** `core/ttc.py` solves
  `0.5·a·t² + v·t − d = 0` along the closing line, so braking is accounted for and a hard
  enough stop reports no collision rather than a number. Two approximations remain and are
  documented: acceleration is held constant over the projection, and steering is not projected
  at all. TTC still ranks models on a scenario; it is not a calibrated time to impact.
- **Pacejka coefficients are uncalibrated** — plausible defaults, not fitted to a measured
  tire. Don't publish absolute handling claims from them, and don't tune them to make a
  scenario pass.

---

## 8. API

FastAPI backend. All routes prefixed `/api`. Auth = JWT Bearer token.

```
PUT    /api/admin/orgs/{org_id}/pickle-models  body: {enabled, note?} — superadmin: allow/deny this org the cloudpickle model path (D-01 gate, default deny)
POST   /api/auth/forgot-password    body: {email} — request password reset link (public, no auth)
POST   /api/auth/reset-password     body: {token, new_password} — consume token, set new password (public, no auth)
GET    /api/billing/plans           plan catalogue: name, monthly_usd, run_credits, self_serve (PUBLIC — the pricing page needs it)
GET    /api/billing/usage           current plan, credits, renewal date, subscription status
POST   /api/billing/checkout        body: {plan, success_url, cancel_url} — Stripe hosted Checkout
POST   /api/billing/topup           body: {quantity, success_url, cancel_url} — one-off credit packs
GET    /api/billing/portal          ?return_url= — Stripe Customer Portal
POST   /api/auth/verify-email       body: {token} — consume verification token, mark address verified (public, single-use)
POST   /api/auth/resend-verification body: {email} — new verification link; always same reply, per-IP + per-user throttled
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
POST   /api/runs/{run_id}/ws-ticket  mint a single-use 60s WebSocket ticket (auth required, run must be yours)
WS     /ws/simulation/{run_id}   live tick frames (auth: ?ticket=<single-use ticket>; 4401 close if refused)
POST   /api/runs/batch           async batch — body: {scenario_path, model_name, num_runs, master_seed}; returns 202 {batch_id, status, num_runs, enqueued, credits_remaining}
GET    /api/runs/batch/{id}/status   live progress {status, total, queued, running, completed, failed, composite_mean, collision_rate, error_message}
```

POST `/api/auth/logout` clears both cookies (public — clearing cookies you may not have is a no-op).

**Two authentication paths, both first-class**: the browser uses the `orion_session` httpOnly
cookie plus the `X-CSRF-Token` double-submit header on writes; SDK, CLI and API-key clients use
`Authorization: Bearer` and are exempt from CSRF (the browser never attaches that header, so
there is nothing to forge). The header wins when both are present. `get_current_user` and
`OrgAuthMiddleware` both read header-then-cookie — keep them in step.

`GET /api/runs/` and `GET /api/runs/{run_id}` return `RunStatusResponse` with:
`composite_score`, `safety_score`, `compliance_score`, `stability_score`, `reactivity_score`, `collision_occurred` — populated once `status == "completed"`.

**Path split — read before adding a frontend call.** Only the auth router (`/api/auth/*`) and the live-run router (`/api/runs/*`) are mounted under `/api`. `/scenarios/`, `/jobs/`, `/results/*`, `/evaluate/*`, `/models/` and `/health` are mounted at the **root**. `src/services/api.js` therefore spells out each full path rather than prefixing everything, and `vite.config.js` proxies every one of those root prefixes. Getting this wrong is quiet: the dev server answers with `index.html` and the call fails as a JSON parse error rather than a 404. Four methods shipped broken this way and went unnoticed because the sections that would call them are not wired up yet.

Built-in model names (registered in `api/routes.py` `AVAILABLE_MODELS`):
`"ConstantAction"`, `"EmergencyBrake"`, `"SimpleLaneKeep"`, `"Random"`

To add new model to API, add to `AVAILABLE_MODELS` dict in `api/routes.py`.
Don't instantiate models outside that dict — dict is registry.

All API errors return `{"detail": "..."}` — match this shape in new error handlers.
Rate-limit 429s go through `rate_limit_exceeded_handler` to keep that shape (slowapi's
default body is `{"error": ...}`).

### API edge behaviour (Phase 0.3 — DONE)

- **CORS** is an explicit whitelist from `api.cors_origins` (env `ORION_ALLOWED_ORIGINS`,
  comma-separated). `resolve_cors_origins()` in `config/validate.py` refuses `*` or an empty
  list outside dev and runs inside `validate_startup()`. Never reintroduce `allow_origins=["*"]`.
- **Rate limiting** is slowapi through the single shared limiter in `api/ratelimit.py`
  (`login 5/min`, `signup 3/hour`, `120/min` default, all from `api.rate_limit_*`). Add a
  per-route limit with `@limiter.limit(...)` and a `request: Request` parameter — slowapi needs
  it, and a route without it fails at call time. Import the shared `limiter`; a second `Limiter`
  instance is silently never consulted. `/health` is `@limiter.exempt`.
- **Auth is declared per router**, not per handler: `dependencies=_AUTHENTICATED` in
  `api/routes.py`. A new data route is gated by default. `/health`, `/docs`, `/openapi.json`
  and the auth routes are the only public surface.
- **Security headers** come from `SecurityHeadersMiddleware` in `api/middleware.py`
  (nosniff, DENY, no-referrer, `default-src 'none'` CSP; relaxed CSP for `/docs` and `/redoc`,
  HSTS only over TLS).
- **Webhooks**: `POST /api/billing/webhook` verifies the Stripe signature and claims the event
  id in `webhook_events` before doing anything. Any new webhook handler follows the same order —
  verify, claim, handle, `mark_processed` in the same transaction as the side effect.
- **Billing (Phase 1.4)**: plan allocations live in `PLAN_CREDITS` / `PLAN_MONTHLY_USD` in
  `api/billing.py` and are served by `GET /api/billing/plans`. **The frontend must never
  hardcode a credit number** — `BillingPage` shipped advertising 100/2,500/15,000 against a
  backend granting 50/500/3,000. Credits are granted **only** on `invoice.paid`;
  `customer.subscription.updated` changes the plan and never the balance, or every card update
  would hand out a free month. Cancellation drops the plan to `free` and leaves paid-for
  credits alone. `run_credits == -1` means unlimited — `OrganisationRepository.UNLIMITED_CREDITS`;
  don't compare it with `<`.
- **Stripe objects are not dicts.** `StripeObject` has no `.get()` in stripe >= 15, and a
  `hasattr(x, "get")` guard silently evaluates False rather than raising — so a metadata lookup
  returns `None` and the caller takes the wrong branch. Use `_metadata_value()` in `billing.py`.
- **Email verification (Phase 0.4, D-04)**: signup creates the user with `email_verified=false`
  and one hashed token on the user row (no side table — a resend replaces it). An unverified
  account can log in and read, but `Depends(require_verified_email)` blocks the routes that
  spend credits or run submitted code: `/evaluate/*`, `POST /api/runs/`, `POST /api/runs/batch`,
  `POST /api/keys/`, `POST /api/models/upload|register`. Superadmin bypasses. Put the dependency
  on any new route of that kind. In tests, call `verify_email_for(email)` from `tests/conftest.py`
  right after signing up.

---

## 9. Frontend

React 18, Vite 5, React Router 6. No TypeScript — plain JSX.

### Design system — `docs/UI_DESIGN.md` is BINDING (read before ANY frontend work)

**Every visual change under `orion-frontend/` MUST conform to `docs/UI_DESIGN.md`** (the "Mission Control" design system, approved 2026-06-25). Read it before writing any page, component, or style. It is the source of truth for colors, typography, spacing, radius, components, theming, and per-page layout — the approved render is `design/sample-mission-control.html`.

- **Use tokens only.** Never hardcode a hex, font size, radius, or one-off color — use the CSS variables defined in `index.css` per the design doc. Old purple/glass tokens (`#6c63ff`, `--accent-primary` gradient, `.glass-card` glow) are retired.
- **Fonts:** Chakra Petch (display) / Saira (UI) / JetBrains Mono (all numerals, tabular). No Inter/Roboto/system body.
- **Theme:** dark-default, light available; `data-theme` on `<html>`, persisted to `localStorage` key `orion-theme`. This is the **only** sanctioned localStorage UI-pref key — it does NOT relax the D-04 auth-token rule below.
- **No emoji as UI icons** — use the inline-SVG set in `src/components/common/Icon.jsx`.
- **Banned aesthetics (permanent):** glassmorphism-as-primary-surface, purple/violet gradients, glow-pulse/float animations, rounded-2xl, generic AI-startup hero. See design doc §1.
- **Out of scope = don't.** Don't add visual features, routes, libraries, or styles not described in the design doc unless the user explicitly asks. New pattern needed → add it to `docs/UI_DESIGN.md` in the same change, then implement.
- The redesign migration is complete; its sequencing plan is archived at `docs/archive/ORION_UI_REDESIGN_PLAN.md` (historical, not binding).

**Implementation status: DONE** (redesign Phases A–I complete). The code now matches the design doc. Key infrastructure:
- Tokens + global utilities (`.panel`/`.panel--live`, `.btn*`, `.field`, `.chip*`, `.data-table`, `.mono-label`, `.num`, `.spec-strip`, grid backdrop, `.skeleton`, `.skip-link`) live in `src/index.css`. Legacy purple/`glass-card` aliases were removed — use canonical tokens only.
- Theme: `src/theme/ThemeContext.jsx` (`useTheme()` → `{theme, toggleTheme, setTheme}`), control = `src/components/common/ThemeToggle.jsx`, no-FOUC inline script in `index.html`, key `orion-theme`. Dark default.
- Icons: `src/components/common/Icon.jsx` (`<Icon name=.. size=.. />`). No emoji. Add new icons there + list in design doc §7.
- Shell: `src/components/common/HudBar.jsx` (sticky status strip) + real `src/components/common/Sidebar.jsx` (numbered nav). `src/components/common/ErrorBoundary.jsx` wraps the app in `main.jsx`; `src/pages/NotFoundPage.jsx` is the `*` route.
- Recharts theming: recompute palette from CSS vars keyed on `useTheme().theme` (see `useChartPalette` in `DashboardPage.jsx`). Never hardcode chart hex.

### Rules

- All HTTP calls through `src/services/api.js` — never use `fetch()` directly in component.
- Auth token lives in `AuthContext` — use `const { user, token, logout } = useAuth()` everywhere.
- **Token storage (D-04 — CLOSED in Phase 0.4)**: the JWT lives in an `httpOnly` cookie
  (`orion_session`) that JavaScript cannot read. `AuthContext` holds no token at all and derives
  auth state from `GET /api/auth/me` on mount, so a refresh stays logged in. **`useAuth()` returns
  `{ user, loading, login, register, logout, isAuthenticated, isVerified }` — there is no `token`.**
  Never reintroduce one, and never put a credential in `localStorage` (the only sanctioned key
  stays `orion-theme`).
- **CSRF**: cookies ride along automatically, so `src/services/api.js` echoes the readable
  `orion_csrf` cookie in an `X-CSRF-Token` header on POST/PUT/PATCH/DELETE. Every call must go
  through `request()` in that file or it will 403. API methods take **no token argument** —
  `api.getRuns(50)`, not `api.getRuns(token, 50)`.
- `OrgContext.jsx` was **deleted** in Phase 0.6. It was never mounted, never consumed, its body was two TODOs, and it imported `api` as a default export that does not exist — it would have thrown on first use. When the billing UI needs org state, `GET /api/orgs/me` through `api.js` is a few lines.
- Dashboard sections: `overview`, `scenarios`, `runs`, `models`, `batches`, `compare`, `settings` — string keys used in `Sidebar` (numbered nav). Only `overview` renders real data; the rest show the `ComingSoon` panel. `NAV_ITEMS` in `Sidebar.jsx` carries a `ready` flag: unready entries stay visible with a `soon` marker but are **disabled**, so nobody lands on an empty page and reads it as a fault. **Flip `ready: true` in the same change that wires a section up.**
- Charts use Recharts (`LineChart`, `RadarChart`, `BarChart`) — don't add Chart.js or D3.
- 3D visualization uses `@react-three/fiber` + `@react-three/drei` — don't use raw Three.js imperative API in React components.
- CSS co-located: `Component.jsx` + `Component.css` same folder. No CSS modules, no Tailwind.

### Frontend tests (Phase 2)

Vitest + Testing Library + jsdom. `npm test` from `orion-frontend/`, and it runs in CI
alongside the production build.

There were none before, so the rule is: **test what fails silently, not what looks wrong.**
A broken layout is visible the moment anyone opens the page; a `credentials: 'include'` that
stops being sent, a CSRF header that stops going out on writes, or an auth bootstrap that
stops running all look like backend faults and cost hours. Those are covered
(`src/services/api.test.js`, `src/context/AuthContext.test.jsx`), including a guard that
`useAuth()` never grows a `token` field again.

### Adding a new API call

Add to `src/services/api.js` following existing pattern, then call `api.myNewMethod(token)` in component.

### Live simulation WebSocket (P1.1 — complete)

Backend streams at `WS /ws/simulation/{run_id}?token=<jwt>`; consumer wired end-to-end:

- `src/hooks/useSimulationStream.js` — owns WebSocket. Returns `{ frame, isConnected, status, error, latencyRef }`. Handles exponential-backoff reconnect (max 3 attempts), cleans up on unmount. Don't open sockets from components directly.
- `src/components/simulation/SimulationViewer.jsx` — R3F scene (road, ego, NPCs) + HTML HUD overlay (sim time, speed, g-force, metric bars, verdict badge). Mounted at `/simulation/:runId`. Has `← Dashboard` back button (`.btn-ghost`, top). Scene + overlay restyled to Mission Control palette; HUD = glassless instrument panels.
- Frame shape frozen in `SimulationEngine.get_tick_frame()`. To extend protocol: add fields there, consume in hook/viewer.
- **Auth is a ticket, never the JWT (Phase 0.4, D-04).** The hook calls `api.createWsTicket()` per
  connection attempt, then connects with `?ticket=`. Tickets are single-use and expire in 60 s
  (`arep/api/ws_tickets.py`, in-memory alongside `sim_registry`). A refused credential closes
  with **4401** (not 1008) so the client knows to mint a new ticket rather than give up. Never
  put a JWT in a WebSocket URL — URLs reach access logs, proxy logs and browser history.
- Server closes with `{"event": "stream_end", ...}` — hook handles before deciding reconnect.
- Latency measured from `frame.emit_ts_ms` against client `Date.now()`; running average and max exposed via `latencyRef.current` for HUD display.
- Control-plane calls (`POST /api/runs/`, etc.) go through `src/services/api.js` (`api.startRun`, `api.getLiveRun`, `api.cancelLiveRun`) — hook only owns WS.

### Auth pages

- `LoginPage.jsx` — wraps `LoginForm`. `LoginForm` includes an inline forgot-password panel (shown on "Forgot password?" click): email input → calls `api.forgotPassword(email)` → `POST /api/auth/forgot-password`. Always shows success message regardless of outcome (avoids email enumeration). Panel fades in below the form within the same card.
- `ResetPasswordPage.jsx` — public route at `/reset-password`. Reads `?token=` from URL query string. No token → shows error immediately. Valid token → form with new + confirm password fields (min 6 chars, must match) → calls `api.resetPassword(token, newPassword)` → `POST /api/auth/reset-password`. Success state hides the form and shows a "Go to Login" button.

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

Migrations live in `arep/database/migrations/versions/` (latest: `009_subscription_state`).
Note: `alembic upgrade head` does **not** run on SQLite — migration `002` uses an `ALTER`
with a constraint, which SQLite cannot do. Dev uses `init_database()` (`create_all`); the
migration chain is only exercised against Postgres. Tracked as D-13 (Phase 0.6).
`OrganisationRepository.allows_pickle_models(org_id)` is the single read of the D-01 gate —
check it there, never by reading the column directly.

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

# Frontend tests (from orion-frontend/)
npm test

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

# Hard-rule check (no wall-clock / unseeded randomness in the simulation
# packages). AST-based, same check CI runs.
python scripts/check_hard_rules.py

# End-to-end smoke tests against a real uvicorn server. Both use throwaway
# databases; run them for anything touching middleware, headers or the ASGI
# stack, where TestClient and production diverge.
PYTHONPATH=. python scripts/api_smoke.py
PYTHONPATH=. python scripts/ws_smoke.py

# Coverage with the CI gate
pytest --cov=arep --cov-report=term-missing --cov-fail-under=70

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
  `time.monotonic()` in `run_async` is the one sanctioned exception: it paces live *delivery*
  and never reaches frame content. `tests/test_frame_determinism.py` greps for violations.
- **Never change simulation step order** (validate → physics → NPCs → lights → collision → termination → increment time).
- **Never change pinned dependency versions** (`numpy==1.26.0`, `scipy==1.11.3`) without explicit instruction — breaks determinism tests.
- **Never create new scenario for weather/lighting variant.** Add to `parameterization:` block.
- **Never call `model.predict()` directly** in runner or API code — always use `ModelWrapper`.
- **Never use `fetch()` directly in React components** — always use `src/services/api.js`.
- **Never hardcode seeds, config values, or API URLs** — from `config/default.yaml` and `vite.config.js` proxy.
- **Never hardcode secrets or credential fallbacks** — no default JWT secrets, no default DB passwords. Fail fast if env var missing (Phase 0.1 pattern).
- **Never deserialise untrusted pickle/cloudpickle outside the sandboxed model path** — customer artefacts are hostile input (D-01).

**Secret/config resolution (Phase 0.1 — DONE, D-02 closed)**: never read `ORION_SECRET_KEY` / `ORION_DATABASE_URL` directly with a fallback default. Go through `arep/config/validate.py`: `resolve_secret_key()`, `resolve_database_url()`, `validate_startup()`. Non-dev (`ORION_ENV` not in dev/test/local) refuses to boot on missing/weak/placeholder secret or SQLite URL; dev gets an ephemeral secret + `sqlite:///arep.db`. `validate_startup()` runs in `app.py` lifespan. docker-compose pulls all secrets from git-ignored `infrastructure/.env` (`env_file:` + `${VAR}`); see `infrastructure/.env.example`.

**Known violations of these rules in existing code** (tracked in the `docs/ROADMAP.md` defect register, fixed in Phase 0): JWT in `localStorage` in `AuthContext.jsx` (D-04). ~~fallback secrets (D-02)~~ — closed in 0.1. ~~`time.time()` in the tick frame (D-06)~~ — closed in 0.5. ~~CORS `*` / no rate limiting (D-03)~~ and ~~unauthenticated catalogue routes (D-07)~~ — closed in 0.3. Don't copy these patterns; Phase 0.6 adds CI checks that mechanically enforce the simulation-purity rules.

**API hardening rules (Phase 0.3 — DONE, D-03 + D-07 closed)**: never set `allow_origins=["*"]`
or read origins anywhere but `resolve_cors_origins()`. Never hardcode a rate limit at a call
site — they live in `api.rate_limit_*`. Never add a data route without router-level auth
(`dependencies=_AUTHENTICATED`); `/health`, `/docs`, `/openapi.json` and `/api/auth/*` are the
whole public surface. Never act on a webhook before verifying its signature and claiming its
event id. See Section 8.

---

## 13. What Is Not Built Yet (Active Development Areas)

**Authority**: `docs/ROADMAP.md` v3.0 — priority *and* implementation detail. Read the relevant phase section before writing code in these areas.

### Phase 0 — Security & Score Integrity (COMPLETE)

Full spec + defect register (D-01…D-13): `docs/ROADMAP.md` § Phase 0. Order:

1. ~~**0.1 Secrets hardening (D-02)**~~ — **DONE.** Fallbacks removed; `arep/config/validate.py` is the single resolver (`resolve_secret_key`, `resolve_database_url`, `validate_startup`); fail-fast in non-dev, ephemeral secret + sqlite in dev; `validate_startup()` wired into `app.py` lifespan; docker-compose secrets moved to git-ignored `infrastructure/.env` (`infrastructure/.env.example` documents them). `git grep "Harshit:Harshit\|change-in-production"` in `arep/` → 0 hits. See Section 12.
2. ~~**0.2 Model sandboxing (D-01)**~~ — **STEP 1 DONE.** `arep/models/sandbox.py` rewritten: env whitelist (no `ORION_*` reaches the child), `unshare --net` when available + in-process socket block installed before unpickling, fresh tmpdir as cwd/`TMPDIR`/`HOME`, rlimits actually applied via `preexec_fn` + `os.setsid()`, hard per-call and per-run wall-clock kill via `killpg(SIGKILL)`. Limits in `config/default.yaml` `sandbox:` (`SandboxConfig`, `ORION_SANDBOX_*`). Cloudpickle path gated per-org: `organisations.allow_pickle_models` (migration `005`, default FALSE), enforced at upload and at resolve, toggled by `PUT /api/admin/orgs/{id}/pickle-models`. `ModelSandboxError` aborts the run (never scored) so the worker refunds. **Step 2 still open**: gVisor/Firecracker before open self-serve signup.
3. ~~**0.3 API hardening (D-03, D-07)**~~ — **DONE.** CORS is an explicit whitelist
   (`ORION_ALLOWED_ORIGINS`, wildcard refused outside dev by `resolve_cors_origins()`);
   slowapi rate limiting via `api/ratelimit.py` (login 5/min, signup 3/hour, 120/min default,
   bucketed org → credential hash → IP, `X-Forwarded-For` only when trusted);
   `SecurityHeadersMiddleware`; router-level auth on `/models/` `/scenarios/` `/evaluate/`
   `/jobs/` `/results/*` `/api/runs/`; Stripe webhook signature verification + a
   `webhook_events` idempotency ledger (migration `006`). Tests: `test_api_hardening.py` (21),
   `test_route_auth.py` (13), `test_webhook_security.py` (15); suite 147 passed.
   **Correction to the register**: D-07 claimed four unauthenticated routers; only `/models/`
   and `/scenarios/*` actually were — `/jobs/` and `/results/*` already called
   `get_request_principal`. Neither open route carried org-scoped rows, so there was no tenancy
   leak. Both are gated regardless.
4. ~~**0.4 Auth flow (D-04)**~~ — **DONE.** Email verification (token hashed on the user row,
   `require_verified_email` gates runs/keys/model upload); JWT moved to an `httpOnly` cookie with
   a double-submit CSRF partner and a `GET /api/auth/me` bootstrap, `localStorage` token gone;
   WS auth is a 60-second single-use ticket (`POST /api/runs/{id}/ws-ticket`, 4401 on refusal),
   JWT never in a socket URL; superadmin tokens expire in 4 h. Migration `007`. Tests:
   `test_email_verification.py` (18), `test_ws_ticket_auth.py` (13), `test_cookie_auth.py` (19).
5. ~~**0.5 Score integrity (D-05, D-06, D-11, D-12)**~~ — **DONE.** Real lane compliance
   (body-edge test against recorded signed `lane_offset`; lane 0 recentred on the travel line);
   canonical frames with `emit_ts_ms` moved to the WS send site; per-run `FrameHasher` digest
   on `RunRecord.frame_hash` (migration `008`); TTC approximation documented everywhere it
   surfaces; weight transfer uses the current step; `docs/METHODOLOGY.md` written.
6. ~~**0.6 Reliability + test gates (D-08, D-09, D-10, D-13)**~~ — **DONE.** Celery
   `max_retries=3` with 5/15/60s backoff for transient errors only, refund once, idempotent on
   `(batch_id, seed)`; CI coverage gate at 70% (currently 71.3%) plus a Postgres job with an
   Alembic upgrade → downgrade → upgrade round trip; scenario-library, cross-org denial,
   partial-refund, NPC behaviour-tree and admin suites; `scripts/check_hard_rules.py` enforces
   the simulation-purity rules in CI; frontend `OrgContext` deleted and unready nav disabled.

**Phase 0 is complete** apart from 0.2 Step 2 (gVisor/Firecracker), which is gated on opening
self-serve signup rather than on this phase. Next: Phase 1.4 (Stripe billing, on the verified
webhook base) and 1.5 (road topology, which unblocks ~35% of the scenario library).

### Phase 1 remainder (after Phase 0 exits)

1. ~~**Stripe billing (Phase 1.4)**~~ — **DONE.** Checkout, top-up, portal, webhook handlers,
   `GET /api/billing/plans`, and a live `BillingPage`. See Section 8. Still needs real Stripe
   price IDs and a test-mode round trip against the live API.
2. **Road topology engine (Phase 1.5)** — only flat 2-lane straight road exists. Blocks ~35% of scenario library (all INT-*, EMG-002, MLT-*). `core/road.py` and `core/road_templates.py` do not exist. Spec: `docs/ROADMAP.md` § 1.5.

### Done (P1.1 + P1.2 + P1.3)

- **Multi-tenancy (P1.1)** — `organisations`, `api_keys` tables. JWT carries `org_id`+`role`. `OrgAuthMiddleware` resolves both JWT and API keys. `/api/orgs/me`, `/api/orgs/invite`, `/api/keys/` CRUD. All eval/batch/jobs/results/live-run routes scoped by `org_id`.
- **Model submission (P1.2)** — `models` table + `ModelRepository`. `/api/models/upload` (multipart cloudpickle), `/api/models/register` (Docker), `/api/models/`, `/api/models/{id}` GET/DELETE. `models/resolver.py` dispatches built-in name → instance, UUID → `SubprocessModelRunner` or `HttpModelAdapter`. Org isolation enforced. **Cloudpickle path is gated per-org** — `organisations.allow_pickle_models` defaults FALSE; upload returns 403 and `resolve_model()` raises `PermissionError` until a superadmin enables it. `orion-sdk/` package: `OrionClient`, `upload_model()`, `orion` CLI (`models`, `runs`, `keys` commands).
- **Async batch queue (P1.3)** — Celery + Redis. `arep/worker/celery_app.py` + `arep/worker/tasks.py` (`run_single_simulation`, `run_batch_simulations`). `POST /api/runs/batch` atomically deducts `num_runs` credits via `OrganisationRepository.deduct_credits()` (FOR UPDATE row lock), creates a `BatchJobRecord` (`status=queued`), fans out N tasks on the `simulation` queue, and returns 202 in <300 ms. Workers write `RunRecord` rows + bump `runs_completed`/`runs_failed`; the last task to finish triggers `BatchJobRepository.finalise_if_done()` which aggregates from per-run rows and flips status to `completed`. Failed tasks refund 1 credit via `OrganisationRepository.add_credits()`. `GET /api/runs/batch/{id}/status` exposes live progress. Tests run Celery in `task_always_eager` mode (no broker required) — see `tests/test_batch_queue.py`. Worker container + Flower UI defined in `infrastructure/docker-compose.yml` (`worker`, `flower` services). Broker URL via `ORION_REDIS_URL` env var (default `redis://localhost:6379/0`).

### Deferred (Phase 2+, see `docs/ROADMAP.md`)

- **Statistical CIs surfaced to API/dashboard (2.1)** — aggregator computes Wilson/t-dist CIs internally; batch results API and dashboard show point estimates only.
- **Failure clustering (2.2)**, **adversarial search (2.3)**, **model comparison + PDF (2.4)**.
- **Deterministic replay (2.5)** — promoted from Phase 5; depends on Phase 0.5 frame hash. Closes `RunPage` stub.
- **CompositeEvaluator wired to live runs** — dashboard scores are per-tick proxy metrics from `monitor.metrics_current`, not full post-run evaluation.
- **Sensor simulation** — no LiDAR, camera, GPS/IMU today; observation = ground-truth state. Scheduled as **Phase 6** (`docs/ROADMAP.md`), which starts only after Phase 5 exits — structured sensor output (object lists, ranges), never rendered pixels. Until it ships, ORION = planning/control eval: don't promise perception testing anywhere, and don't build sensor code early.
- **Standards alignment (Phase 4.5)** — no ISO 26262/21448 story today; traceability matrix + ODD declarations planned, certification never claimed.
- **3D visualization polish + frontend debt (Phase 5)** — GLTF assets, trajectory traces, progressive TypeScript migration, frontend tests (currently zero), `DashboardPage.jsx` decomposition.

---

## 14. Git Workflow & Branching

GitHub Flow. `main` is the production branch and is **always deployable** — every commit on it
should have a green CI run. All work happens on short-lived branches off `main`.

### When to cut a branch

Size a branch by **what gets reviewed and merged as one unit** — days of work, not weeks. A
roadmap item bigger than that gets split into slices that each leave `main` working; if the
feature isn't user-ready, land the slices behind a flag (as `billing_enabled` does) rather
than letting a branch live for weeks and rot against `main`.

| Stay on the current branch | Cut a new branch |
| -------------------------- | ---------------- |
| Fixing review comments      | Unrelated work (different defect, different roadmap item) |
| Repairing tests you broke   | Anything that should merge independently of what's in flight |
| Refactors the change needs  | A bug found in passing, unrelated to the current change |
| Docs for that change        | The current branch is merged (never reuse a merged branch) |

Deciding question: *if the branch I'm on were rejected, should this change die with it?*
No → new branch.

### Naming

`<type>/<scope>-<what>`, type matching the Conventional Commit prefix:
`fix/d03-cors-whitelist`, `feat/road-topology`, `chore/ci-postgres`, `docs/branching-convention`.

For Phase 0 work, one branch per defect or per separable part of a sub-phase — e.g. 0.3 splits
into `fix/d03-cors-and-ratelimit` and `fix/d07-route-auth`, each its own PR.

### Rules

- **Attribution: never credit Claude, in anything.** No `Co-Authored-By: Claude ...` trailer,
  no "Generated with Claude Code" line in a commit message, PR description, issue or release
  note. Nothing in this repository should show Claude as an author or collaborator. The commit
  author is the repository owner; that is the whole authorship story. This rule overrides any
  default attribution behaviour the tooling suggests.
- **Never commit directly to `main`.** Branch, PR, merge.
- **Rebase onto `main` before opening the PR** — don't merge `main` into the branch. Keeps
  history linear and the diff honest.
- **Squash-merge** small branches (one commit per landed change, easy `git revert`). Keep a
  real merge commit only when a branch's individual steps are worth preserving.
- **Delete the branch after merge**, local and remote.
- CI (`.github/workflows/`) must be green before merge. Lint baseline is dirty (see Section 12
  notes) — don't reformat untouched files inside a feature commit to make it pass.

### Not used

No Git Flow (`develop` / `release/*` / `hotfix/*`). It exists for versioned releases shipped by
multiple teams; for this repo it is four branches of ceremony for a problem we don't have.
Revisit only if a staging environment starts lagging production.
