# ORION — Roadmap

**Version**: 3.0
**Date**: 2026-09-18
**Author**: Harshit Anand
**Status**: Active — the single governing roadmap for ORION.

> **This document replaces `ORION_SAAS_ROADMAP.md` v2.0 and `AREP_IMPLEMENTATION_ROADMAP.md` v1.1.**
> Both are archived under `docs/archive/`. Priority ordering came from the SaaS roadmap;
> implementation specs (data structures, file names, acceptance criteria) came from the
> technical roadmap and are inlined into the phase that owns them. Where the two disagreed,
> the SaaS roadmap won and the stale text was dropped — see *What Changed in v3.0*.

---

## What Changed in v3.0

1. **One roadmap instead of two.** Priorities and implementation detail now live in the same
   phase section. No more "see the other document § P1.2" indirection, and no more two
   competing phase numberings for the same work.
2. **Sensor simulation rescheduled, not deleted.** The old technical roadmap carried a
   full LiDAR / camera / GPS-IMU specification as "P1.3 — the single highest-leverage item
   for industry adoption", scheduled ahead of revenue work and contradicting the stated
   positioning. It is now **Phase 6**: the full spec is retained, moved behind every phase on
   the revenue path, and constrained to structured (non-rendered) sensor output so the
   CPU-only guarantee survives.
3. **Completed work collapsed.** WebSocket telemetry, batch-execution-wired-to-API and the
   scenario v2.0 upgrade were still written as future work in the technical roadmap. They
   are done; only their frozen contracts survive, in the status snapshot.
4. **RL Gym adapter demoted** from a Phase 2 differentiator to *Deferred — unscheduled*. It
   was never referenced by the product roadmap and is not on the path to revenue.

Carried forward unchanged from SaaS roadmap v2.0: Phase 0 exists and blocks all revenue
work; score integrity is product-critical, not tech debt; deterministic replay sits in
Phase 2; positioning is stated honestly.

---

## Vision

ORION is a **cloud-native, subscription-based safety evaluation platform** for autonomous
driving models. Teams submit their model, choose a scenario suite, and receive statistically
rigorous safety reports — without installing anything, without owning a GPU cluster, and
without writing a single test case.

**The core bet**: CARLA is a simulator. ORION is a testing laboratory. CARLA requires a GPU
workstation and gives you a pretty scene. ORION runs on CPU-only cloud instances and gives
you answers about your model's safety profile with confidence intervals, failure clustering,
and regression tracking.

**What ORION sells**: certainty, not screenshots.

---

## Honest Positioning — What ORION Is and Is Not

### Is

- A deterministic, statistically rigorous, CI-friendly **evaluation harness for planning and
  control stacks** that consume ground-truth state.
- The cheapest path to "did my new model version regress on safety?" answered with
  confidence intervals, on every pull request.
- Reproducible by construction: same seed → same run, every time, auditable.

### Is Not (and must not pretend to be)

- **Not a perception testbed — today.** No LiDAR, camera, or radar simulation; models that
  need sensor input cannot be evaluated here yet. Target customers: planning/control teams,
  RL researchers, motion-prediction teams, education. **Phase 6** adds a structured sensor
  layer (object lists and ranges, never rendered pixels) after the platform is complete —
  until it ships, claim nothing about perception testing.
- **Not a certification tool.** No ISO 26262 ASIL mapping, no ISO 21448 (SOTIF) ODD coverage
  argument, no HARA traceability. Enterprise AV safety teams ask in the first meeting; the
  answer today is "no — we are an engineering regression tool, not a homologation tool."
  Phase 4.5 starts the standards-alignment story.
- **Not photorealistic.** Bloomberg Terminal, not Unreal Engine. Never compete with
  CARLA / DRIVE Sim on rendering.

| Dimension         | CARLA                                   | ORION                               |
| ----------------- | --------------------------------------- | ----------------------------------- |
| Primary value     | Photorealistic sensor data for training | Rigorous safety evaluation + scores |
| Infrastructure    | GPU workstation, local install          | Browser-based SaaS, CPU cloud       |
| Evaluation rigor  | Manual, no statistical framework        | Automated, statistically rigorous   |
| CI/CD integration | Not possible (Unreal Engine)            | First-class feature                 |
| Target user       | Perception ML engineers                 | Planning/control + safety engineers |
| Pricing model     | Free/open-source, self-hosted           | Subscription (run credits per tier) |

Full competitor scoring and the four moats: [MARKET.md](MARKET.md).

---

## Status Snapshot

### Built and working

| Component | Status | Location |
| --- | --- | --- |
| 4-layer execution architecture (L1–L4) | ✅ | `arep_implementation/arep/` |
| Bicycle kinematic physics | ✅ | `core/physics.py` — `PhysicsMode.KINEMATIC` |
| Pacejka dynamic tire model + surface friction | ✅ | `core/physics.py` — `PhysicsMode.DYNAMIC`, `SurfaceType` |
| OBB collision detection (SAT) | ✅ | `core/collision.py` |
| `WorldState` / `VehicleState` / `Vector2D` | ✅ | `core/state.py` |
| `RandomManager` (seeded, subsystem-isolated) | ✅ | `core/random_manager.py` |
| Scenario schema + YAML parser + parameterizer | ✅ | `scenario/` |
| 5 NPC behavior trees | ✅ | `simulation/npc_bt.py` — `hesitant_brake`, `hesitant_cut_in`, `adaptive_tailgate`, `cautious_pedestrian`, `erratic_pedestrian` |
| `WorldManager` + `SimulationEngine` | ✅ | `simulation/world.py`, `engine.py` |
| 4-metric evaluation + Wilson / t-dist CIs in aggregator | ⚠ | `evaluation/`, `statistics/` — lane compliance is a stub (D-05), TTC is constant-velocity (D-11) |
| FastAPI backend + auth + routes | ⚠ | `api/` — CORS `*` and no rate limiting (D-03), unauth `/models/` `/scenarios/` (D-07) |
| React + Three.js + Vite frontend ("Mission Control" design system) | ⚠ | `orion-frontend/src/` — JWT in `localStorage` (D-04) |
| SQLAlchemy models + Postgres config + Alembic | ✅ | `database/`, `config/` |
| 18 scenario YAMLs, all v2.0, across all 6 categories | ✅ | `scenarios/` |
| WebSocket telemetry + R3F live viewer | ⚠ | `api/ws.py`, `sim_registry.py`, `SimulationViewer.jsx` — `time.time()` in frame (D-06) |
| Multi-tenancy: orgs, roles, API keys, org-scoped routes | ✅ | `OrgAuthMiddleware`, `/api/orgs/*`, `/api/keys/*` |
| Model submission (cloudpickle SDK + Docker) | ⚠ | `api/models_routes.py`, `models/resolver.py`, `orion-sdk/` — cloudpickle path is an RCE vector (D-01) |
| Async batch queue (Celery + Redis, atomic credit deduction) | ⚠ | `worker/` — `max_retries=0` (D-08) |
| Auth: bcrypt, hashed single-use reset tokens, superadmin | ✅ | `api/auth.py`, `api/admin.py` |
| Secret / DB resolution with fail-fast startup validation | ✅ | `config/validate.py` — closes D-02 |
| CI: test + lint + docker-build | ⚠ | `.github/workflows/` — no coverage gate, SQLite not Postgres (D-09, D-13) |
| Dev startup scripts | ✅ | `start.sh`, `start.bat`, `start.ps1` |

**Frozen contracts** (do not redefine elsewhere): `SimulationEngine.get_tick_frame()` is the
single source of truth for the WebSocket frame schema. `ModelInterface.predict()` /
`reset()` is the only model entry point, always invoked through `ModelWrapper`. Metric
weights are frozen — see `CLAUDE.md` § 7.

### Known-defect register (production-readiness review, 2026-06-12)

| ID | Defect | Severity | Fixed in |
| --- | --- | --- | --- |
| D-01 | ~~Cloudpickle model upload = arbitrary code execution in worker; subprocess inherits `ORION_DATABASE_URL`~~ | CRITICAL | 0.2 Step 1 — **done**; Step 2 (gVisor/Firecracker) before open signup |
| D-02 | ~~JWT secret falls back to a hardcoded string; hardcoded DB creds; plaintext creds in docker-compose~~ | CRITICAL | 0.1 — **done** |
| D-03 | CORS `allow_origins=["*"]` + zero rate limiting on login/signup (`api/app.py`) | CRITICAL | 0.3 |
| D-04 | JWT stored in `localStorage` (`AuthContext.jsx`); signup auto-activates with no email verification | CRITICAL | 0.4 |
| D-05 | Lane compliance hardcoded `lane_frac = 1.0` (`evaluation/compliance.py`) — lane-keeping score is fake | HIGH | 0.5 |
| D-06 | `time.time()` in tick frame (`simulation/engine.py`) — breaks the determinism rule and frame hashing | HIGH | 0.5 |
| D-07 | `/models/`, `/scenarios/`, `/jobs/`, `/results/*` unauthenticated — cross-org info disclosure | HIGH | 0.3 |
| D-08 | Celery `max_retries=0` — a transient failure kills the run and the customer eats it | HIGH | 0.6 |
| D-09 | No coverage gate in CI; WS layer, admin routes, billing routes, partial-batch-refund untested | HIGH | 0.6 |
| D-10 | Frontend: no error boundaries, no 404, `OrgProvider` written but never mounted, stub pages in sidebar | MED | 0.6 / with features |
| D-11 | TTC uses a constant-velocity approximation — optimistic in critical scenarios; Pacejka coefficients uncited | MED | 0.5 (document), 2.1 (fix) |
| D-12 | Weight transfer uses previous-step acceleration (`core/physics.py`) — off-by-one | LOW | 0.5 |
| D-13 | SQLite dev vs Postgres prod — `FOR UPDATE` is a no-op on SQLite, race bugs invisible in dev | MED | 0.6 |

**Current position**: Phase 0. 0.1 and 0.2 Step 1 are done; 0.3 (API surface hardening) is the active task.

---

## The Phases

| Phase | Name | Duration (2-person team) | Outcome |
| ----- | --- | --- | --- |
| **0** | Security & Score Integrity | ~1 month | Platform is safe to put a customer on |
| **1** | SaaS Foundation (remainder) | ~1.5 months | Real paying customers can use it |
| **2** | Evaluation Depth | ~2.5 months | Genuinely better than CARLA for evaluation |
| **3** | CI/CD Integration | ~1.5 months | The killer feature that closes enterprise deals |
| **4** | Ecosystem Expansion | ~2.5 months | Broad compatibility, real-world scenarios |
| **5** | Visualization, Frontend Debt & DX | ~1.5 months | Professional, polished, demo-worthy |
| **6** | Sensor Simulation Layer (future) | ~2 months | Sensor-consuming AV stacks can be evaluated |

**Total to full platform: ~10.5 months from Phase 0 start** (Phases 0–5). Phase 6 is the
first post-platform expansion: it starts only once Phase 5 exits, and nothing above it waits
on it.

**Execution rule**: a phase finishes entirely before the next begins. Within a phase, items
are ordered by dependency. Before moving from phase N to phase N+1, every acceptance
criterion in phase N must pass. No exceptions.

---

# PHASE 0 — Security & Score Integrity

**Duration**: ~1 month
**Goal**: close the four critical security holes and make every published score honest.
**Hard rule**: no Stripe integration, no marketing, no external beta users until every item
in 0.1–0.5 is done. Billing a customer on a platform with a known RCE is worse than having
no billing.

---

## 0.1 — Secrets & Configuration Hardening (D-02) — ✅ DONE

`arep/config/validate.py` is the single resolver: `resolve_secret_key()`,
`resolve_database_url()`, `validate_startup()` (wired into the `app.py` lifespan).

- Non-dev (`ORION_ENV` not in dev/test/local) refuses to boot on a missing, weak
  (< 32 chars) or placeholder secret, and refuses a SQLite URL — which also closes D-13's
  production half.
- Dev gets an ephemeral random secret plus `sqlite:///arep.db`, with a warning.
- Fallbacks removed from `api/auth.py`, `database/connection.py`, `config/__init__.py`.
- docker-compose secrets moved to a git-ignored `infrastructure/.env` (`env_file:` +
  `${VAR}`); `infrastructure/.env.example` documents every required variable.

### Acceptance Criteria

- [x] API refuses to start in prod mode without `ORION_SECRET_KEY` set
- [x] `git grep -i "Harshit:Harshit\|change-in-production"` returns zero hits in `arep/`
- [x] docker-compose boots with secrets from `.env` only; `.env` is git-ignored

---

## 0.2 — Customer Model Sandboxing (D-01) — ✅ STEP 1 DONE

**The single most dangerous defect in the codebase.** A customer-uploaded cloudpickle
deserialises with full Python in a worker subprocess that inherits DB credentials. One
malicious upload = every org's data.

### Decision: interim lockdown now, real isolation before open signup

**Step 1 — interim (this phase, mandatory):**

- Strip the worker subprocess environment: spawn the model subprocess with an explicit
  whitelist env (`PATH`, `PYTHONPATH` to a read-only venv) — **no** `ORION_DATABASE_URL`, no
  Redis URL, no secrets. Model I/O happens over the existing pipe protocol only.
- Drop network: run the model subprocess as an unprivileged user with no outbound network
  (Linux: `unshare --net` / network namespace; document the Windows-dev limitation).
- Filesystem: subprocess working directory = empty tmpdir, read-only mount of the model
  artefact, nothing else.
- Keep the existing CPU/memory rlimits; add a hard wall-clock kill (a `predict()` that hangs
  gets SIGKILL, run marked failed, credit refunded) — closes the soft-timeout gap in
  `models/interface.py`.
- Gate the cloudpickle path behind an org-level flag defaulting to OFF for self-serve
  signups. The Docker path (already process-isolated by the container boundary) is the
  default public path; enable cloudpickle per-org manually for trusted design partners.

**Step 2 — before open/self-serve launch (still open, may land in Phase 1):**

- gVisor (`runsc`) or a Firecracker microVM for the model process: container-per-run, no
  network, read-only rootfs, seccomp default profile.

### What Step 1 shipped (2026-09-18)

`arep/models/sandbox.py` rewritten. Limits live in `config/default.yaml` under `sandbox:`
(`SandboxConfig`, `ORION_SANDBOX_*` env overrides) — they are security limits, not perf
tuning.

- **Env stripped** to an explicit whitelist (`PATH`, `SYSTEMROOT`, `COMSPEC`, `WINDIR`,
  `LANG`, `LC_ALL`, `TZ`) plus a computed `PYTHONPATH`; `_build_env()` asserts nothing
  matching `ORION_/AREP_/STRIPE_/AWS_/POSTGRES_/REDIS_` survives.
- **Network**: `unshare --net --map-root-user` when the host supports it (probed once at
  runtime, not assumed), plus a Python-level socket block installed *before* the artefact
  is unpickled. The in-process block is defence in depth, not a boundary.
- **Filesystem**: fresh temp dir as cwd, `TMPDIR`, `TEMP`, `TMP`, `HOME` and `USERPROFILE`;
  the artefact file is deleted as soon as the child reports READY.
- **rlimits actually applied** via `preexec_fn` + `os.setsid()` — CPU, address space, file
  size, open files, core dumps. They were previously declared as constants and never used.
- **Hard wall-clock kill**: per-call deadline *and* a run-level budget, enforced by a reader
  thread and `killpg(SIGKILL)` on the child's session. Raises `ModelSandboxError`, which
  `ModelWrapper` and `EvaluationRunner` deliberately do **not** swallow, so the worker
  fails the run and refunds the credit instead of publishing a truncated score.
- **Per-org gate**: `organisations.allow_pickle_models` (migration `005`), default FALSE,
  enforced at upload *and* at resolve (keyed on the artefact's owning org, so an unscoped
  caller cannot bypass it). Flipped by `PUT /api/admin/orgs/{id}/pickle-models`.
- **Lifecycle**: `EvaluationRunner` now tears down out-of-process models in a `finally`.
  Nothing did before — every customer-model run leaked a child process.

Two defects found while doing the work: `Observation` had no `from_dict`, so the sandboxed
path could never have decoded an observation (added, round-trip tested); and the declared
CPU/memory limits were dead constants.

Platform note: rlimits and namespaces are POSIX-only. On Windows only the env strip, the
tmpdir jail and the wall-clock kill apply, and the sandbox logs a warning — Windows is a
dev-only target for this path.

### Acceptance Criteria

- [x] Model subprocess env contains no `ORION_*` variables (test asserts this)
- [x] A model that calls `socket.connect()` fails; run marked failed, credit refunded
- [x] A model that sleeps forever is killed at the wall-clock limit; credit refunded
- [x] A self-serve org cannot use the cloudpickle path without manual enablement
- [ ] Step 2: model process runs under gVisor/Firecracker (before open signup)

---

## 0.3 — API Surface Hardening (D-03, D-07)

- **CORS**: replace `allow_origins=["*"]` with an `ORION_ALLOWED_ORIGINS` env var
  (comma-separated whitelist). Note `allow_credentials=True` with `*` is invalid per spec
  anyway — the current config is both insecure and broken.
- **Rate limiting**: add `slowapi` (or equivalent). Login 5/min/IP with lockout-style
  backoff, signup 3/hour/IP, forgot-password already limited (keep), global default
  120/min/key on API routes.
- **Auth on public routes**: `/models/`, `/scenarios/`, `/jobs/`, `/results/*` require auth
  and org scoping like everything else. Decide deliberately whether the built-in model list
  stays public (marketing value) — but org-uploaded resources never leak.
- **Security headers middleware**: `Strict-Transport-Security`,
  `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, basic CSP on API responses.
- **Webhook stub**: the `api/billing.py` webhook handler gets Stripe signature verification
  and an event-id idempotency table NOW, even as a stub, so Phase 1.4 builds on a safe base.

### Acceptance Criteria

- [ ] Request from a non-whitelisted origin gets no CORS grant
- [ ] 6th login attempt in a minute from one IP → 429
- [ ] Unauthenticated `GET /scenarios/` → 401
- [ ] A replayed webhook event id is a no-op

---

## 0.4 — Auth Flow Integrity (D-04)

- **Email verification**: signup creates the user with `email_verified=false`; the
  verification token is emailed (reuse the hashed-token machinery from password reset).
  Unverified users can log in but cannot create runs, keys or models. Resend endpoint,
  rate-limited.
- **Token storage redesign**: the backend sets the JWT in an `httpOnly; Secure;
  SameSite=Lax` cookie on login. `AuthContext` drops `localStorage` entirely; auth state is
  derived from a `GET /api/auth/me` call on mount. Keep `Authorization: Bearer` support for
  API-key / SDK clients — the cookie is for the browser app only. Add CSRF protection for
  cookie-auth state-changing routes (double-submit token, or `SameSite=Strict` + origin
  check).
- **WebSocket auth**: replace the `?token=<jwt>` query param with a short-lived (60 s,
  single-use) ticket: `POST /api/runs/{id}/ws-ticket` → opaque ticket → WS connects with
  `?ticket=...`. The long-lived JWT never appears in access logs, proxy logs or browser
  history.
- Superadmin tokens: shorten expiry to 4 h (regular stays 24 h).

### Acceptance Criteria

- [ ] JWT absent from `localStorage`, present only as an httpOnly cookie
- [ ] Unverified account → `POST /api/runs/` returns 403 with a clear message
- [ ] WS connect with an expired or reused ticket → 4401 close; JWT never in the WS URL
- [ ] Page refresh keeps the user logged in (cookie + `/me` bootstrap)

---

## 0.5 — Score Integrity (D-05, D-06, D-11, D-12)

The product is the score. Every component of every published score must be computed,
documented and reproducible.

- **Lane compliance — real implementation**: add `lane_offset` (signed lateral distance to
  the lane centerline) to `EgoSnapshot` at recording time; `ComplianceMetrics` computes the
  per-step in-lane fraction plus mean/max offset. Delete the `lane_frac = 1.0` stub.
  Re-baseline all stored expected scores after this lands — scores will move, and that is
  the point.
- **Determinism leak**: remove `emit_ts_ms` from the `get_tick_frame()` core payload. If the
  frontend needs wall-clock for the latency HUD, inject it at the WebSocket send site,
  outside the canonical frame, so frame content is pure `f(seed, scenario)`.
- **Frame hash**: add a per-run rolling hash of canonical frames, stored on the run record.
  Two runs with the same seed must produce identical hashes — this becomes the enforceable
  determinism guarantee, and a CI test.
- **TTC honesty**: document the constant-velocity approximation in the methodology page and
  in metric docstrings ("TTC is optimistic under braking"); the constant-acceleration
  upgrade is tracked in 2.1.
- **Physics correctness pass**: weight transfer uses current-step `ax` (D-12); cite or flag
  the Pacejka coefficients as empirical defaults in the `DynamicVehicleParams` docstrings.
- **Methodology doc**: one page per metric — formula, weights, thresholds, known
  approximations. This becomes the "How ORION evaluates your model" page (5.3) and the
  artifact a customer's safety reviewer reads.

### Acceptance Criteria

- [ ] A lane-keeping scenario where the ego drifts out of lane scores < 1.0 on compliance
- [ ] Same seed → identical frame hash across two runs and two machines (CI-enforced)
- [ ] `git grep "time.time" arep/simulation arep/core arep/evaluation` → zero hits
- [ ] Methodology doc covers all four metrics, including the stated TTC approximation

---

## 0.6 — Reliability & Test Gates (D-08, D-09, D-10, D-13)

- **Celery retry policy**: `max_retries=3`, exponential backoff (5 s / 15 s / 60 s),
  `autoretry_for` transient exceptions (DB disconnect, Redis hiccup). Credit refund only
  after final failure. Make tasks idempotent on `run_id` — re-execution must not double-write
  `RunRecord` or double-bump counters.
- **CI coverage gate**: `pytest --cov=arep --cov-fail-under=70` (raise later); coverage
  uploaded as an artifact.
- **Missing test suites**:
  - WebSocket integration test in CI (async client against the in-process app)
  - Cross-org denial tests for every authenticated route group (admin, models, runs, batch,
    keys, billing)
  - Partial batch failure: 5 runs / 3 fail → exactly 3 credits refunded, batch finalises
    once (assert no double-finalise race)
  - Parameterized parse + validate test over all 18 scenario YAMLs
  - Alembic upgrade → downgrade → upgrade on a fresh Postgres in CI
- **Dev/prod parity (D-13)**: the CI test job runs against a Postgres service container, not
  SQLite, so `FOR UPDATE` paths are actually exercised.
- **Frontend minimum reliability (D-10)**: top-level `ErrorBoundary` with fallback UI and a
  404 route (both now shipped with the Mission Control redesign — verify, don't rebuild);
  mount `OrgProvider` (the billing UI needs it) or delete it — decide, don't leave it dead;
  the sidebar hides sections whose pages are stubs.
- **Hard-rule lint enforcement**: add a CI grep/AST check forbidding `time.time()`,
  `datetime.now()` and `import random` inside `arep/core`, `arep/simulation`,
  `arep/evaluation` — the rules in `CLAUDE.md` become mechanically enforced.

### Acceptance Criteria

- [ ] Transient DB error during a run → task retries and succeeds; no refund
- [ ] CI fails below 70% coverage; CI runs on Postgres
- [ ] All listed test suites green in CI
- [ ] Throwing inside any dashboard component shows the fallback UI, not a blank page

---

## Phase 0 Exit Checklist

- [ ] D-01…D-09 all closed (D-10 may carry stub-page items into their feature phases)
- [ ] External-facing pen-test-style pass: org A cannot read, write or infer org B data via
      any route, WS, or uploaded model
- [ ] The `CLAUDE.md` hard-rules section matches reality again (no known violations)

---
# PHASE 1 — SaaS Foundation (remainder)

**Duration**: ~1.5 months
**Goal**: a real user signs up, submits a model, runs evaluations, and pays.
**Already done**: multi-tenancy ✅ · model submission ✅ (hardened in 0.2) · async batch
queue ✅. The sections below are what remains.

---

## 1.4 — Stripe Billing Integration

**Why now and not earlier**: deferred behind Phase 0 deliberately — billing on an insecure
platform is liability, not revenue.

### Subscription Tiers

| Tier | Monthly Price | Run Credits/mo | Concurrent Runs | Scenario Access |
| --- | --- | --- | --- | --- |
| **Free** | $0 | 50 | 1 | LON category only |
| **Starter** | $49 | 500 | 3 | All categories |
| **Pro** | $199 | 3,000 | 10 | All + adversarial search |
| **Enterprise** | Custom | Unlimited | Custom | All + priority support + SLA |

Run credits roll over 3 months. Top-up at $0.10/run.

### Implementation

Stripe hosted checkout (Stripe Billing) — no custom payment UI, minimal PCI scope.

```
POST /api/billing/checkout    # create Checkout session → return URL
GET  /api/billing/portal      # Stripe Customer Portal
POST /api/billing/webhook     # subscription.updated, invoice.paid, ... (signature-verified + idempotent — built in 0.3)
GET  /api/billing/usage       # current credits, next renewal date
```

On `invoice.paid`: top up `organisations.run_credits` by the tier allocation.
On `subscription.updated`: update `organisations.plan`.
The existing admin top-up / plan-change routes remain the manual fallback.
Add `stripe>=7.0.0` to `pyproject.toml`.

**Frontend**: implement `BillingPage` (currently a stub) — plan card, usage meter, checkout
and portal buttons. Closes one D-10 stub.

### Acceptance Criteria

- [ ] A free-tier org with 0 credits gets 402 on `POST /api/runs/batch`
- [ ] A Starter upgrade via checkout grants 500 credits within 60 s of payment
- [ ] A replayed webhook event does not double credits (idempotency from 0.3)
- [ ] `BillingPage` shows live plan + credits; the checkout round-trip works in test mode

---

## 1.5 — Road Topology Engine

**Required for ~35% of the scenario library to execute** (all INT-\*, EMG-002, MLT-\*). Only
a flat 2-lane straight road exists today.

### 1.5.1 Road Graph Data Model

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
    arms: List[str]              # segment_ids that connect here
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

### 1.5.2 Built-In Road Templates

**File to create**: `arep_implementation/arep/core/road_templates.py`

Factory functions that generate `RoadGraph` objects for common layouts. Scenarios use a
template rather than a raw road-graph definition.

```python
def highway_straight(lanes: int, length: float, lane_width: float, speed_limit: float) -> RoadGraph
def urban_straight(lanes: int, length: float, ...) -> RoadGraph
def t_junction(approach_length: float, cross_length: float, ...) -> RoadGraph
def four_way_intersection(arm_length: float, ...) -> RoadGraph
def highway_onramp(main_length: float, ramp_length: float, merge_point: float, ...) -> RoadGraph
def roundabout(radius: float, arm_count: int, arm_length: float, ...) -> RoadGraph
```

Each returns a fully-wired `RoadGraph` with correct segment connections, junction
right-of-way rules, and lane centerline points at 1 m resolution.

### 1.5.3 Scenario YAML — Road Section Extension

New `environment.road` section (backward compatible — absent `template` falls back to the
existing straight road derived from `type`):

```yaml
road:
  template: four_way_intersection   # maps to a road_templates factory function
  arm_length: 80.0
  lanes: 2
  lane_width: 3.5
  speed_limit: 13.89
  # ego spawn is always on arm "south", facing north (heading = π/2)
```

- `scenario/parser.py` — parse `road.template`, call the factory, store the result in
  `ScenarioDefinition.road_graph`
- `scenario/schema.py` — add `road_graph: Optional[Any] = None` to `ScenarioDefinition`
- `scenario/executor.py` — convert each segment's lane centerlines into existing `LaneInfo`
  objects for `WorldState.lanes`, and store the `RoadGraph` on `WorldState` for
  junction-aware queries
- `core/state.py` — add `road_graph: Optional[Any] = None` to `WorldState`

### 1.5.4 Visualization Update

`orion-frontend/src/components/simulation/SimulationViewer.jsx`: the WS `env` frame carries
a `road_graph` snapshot, emitted once on connection (not per tick). The scene builds road
geometry from it — one `PlaneGeometry` per segment, junction surfaces at intersections, lane
markings as `LineSegments` from the centerline points.

### Acceptance Criteria

- [ ] `road_templates.four_way_intersection()` returns a valid `RoadGraph`
- [ ] `RoadGraph.is_off_road()` returns `True` for positions outside all segments
- [ ] An INT-\* scenario with `template: four_way_intersection` loads and runs
- [ ] Three.js renders the intersection geometry; junction traffic lights cycle in the HUD
- [ ] Lane-offset computation (from 0.5) works on curved and junction segments, not just
      straight roads

---

## Phase 1 — Launch Checklist

Before charging the first customer:

- [ ] Phase 0 exit checklist fully green (non-negotiable)
- [ ] Sign-up → email verify → org → first run → results: the whole flow works in production
- [ ] Stripe live mode; model submission works via the Docker path (cloudpickle gated per 0.2)
- [ ] All 18 scenarios runnable (INT needs 1.5)
- [ ] HTTPS everywhere; secrets from env or a secret store only
- [ ] Basic admin view: orgs, usage, error rates
- [ ] Step-2 sandboxing (gVisor / Firecracker) done **or** the cloudpickle path still gated off

---

# PHASE 2 — Evaluation Depth

**Duration**: ~2.5 months
**Goal**: make the evaluation output so much richer than competitors' that it becomes the
primary reason customers choose ORION.

---

## 2.1 — Statistical Rigor: Confidence Intervals & Distribution Analysis

**Currently**: the aggregator already computes Wilson + t-distribution CIs internally; they
are not surfaced through the batch-results API or the dashboard.
**After**: `safety_score: 0.73 ± 0.04 (95% CI, n=100)` with the full distribution shown.

`statistics/aggregator.py` — extend `AggregatedResult`:

```python
@dataclass
class ScoreDistribution:
    mean: float
    std: float
    ci_95_low: float
    ci_95_high: float
    percentile_5: float
    percentile_25: float
    percentile_75: float
    percentile_95: float
    n: int
```

Per-metric distributions, plus `collision_rate_ci_95` (Wilson) and `worst_run_id` /
`best_run_id`. scipy and numpy are already pinned — no new dependencies.

Also in this work package:

- **Constant-acceleration TTC** (properly closes D-11): TTC computed from relative velocity
  *and* relative acceleration; constant-velocity kept as a documented fallback.
- Document small-n behavior (ddof=1, wide CIs at n < 5) on the methodology page.

**API + frontend**: `GET /api/runs/batch/{batch_id}/results` includes full
`ScoreDistribution` objects (additive change). Dashboard score cards show mean ± CI plus an
inline 10-bin spark-histogram (Recharts).

### Acceptance Criteria

- [ ] CI widens as n decreases (verified at n = 5 / 20 / 100)
- [ ] Same seed → identical distribution statistics
- [ ] Frontend shows the CI on all score cards
- [ ] TTC-with-acceleration flags earlier threat detection than constant-velocity TTC

---

## 2.2 — Failure Clustering & Root Cause Analysis

**Currently**: you know a model failed, not why.
**After**: "42% of failures occurred when NPC initial distance < 25 m AND ego speed > 15 m/s."

**File**: `arep/analysis/failure_clustering.py` — `FailureClusterer.analyse(batch_id)`: pull
FAIL runs → extract the parameter vector per run (seed + parameterizer) → DBSCAN clustering →
per-cluster mean params, failure rate, dominant event → top-3 human-readable
`FaultCondition`s plus a `safe_region_description`. Add `scikit-learn>=1.3.0` as an optional
dependency.

```
GET /api/runs/batch/{batch_id}/failure-report   # lazy-computed, DB-cached
```

**Frontend**: a "Failure Analysis" panel in the scenario drill-down — condition cards,
failure-rate bars, "See example run →" links into `SimulationViewer`.

### Acceptance Criteria

- [ ] A 50-run LON-003 batch with `ConstantAction` produces a non-empty `FailureReport`
- [ ] Descriptions reference actual parameter names; `example_run_id` is a real FAIL run

---

## 2.3 — Adversarial Scenario Search

**The single biggest technical differentiator.** CARLA runs the scenarios you author; ORION
finds the scenarios that break your model before you know to author them.

### 2.3.1 Architecture

The search engine operates at Layer 2 (parameterization), treating the scenario's
`parameterization:` block as a bounded search space and the evaluation monitor's verdict as
the objective function.

```
Search Engine
  ├── SearchSpace       — extracts {min,max} ranges from scenario YAML → continuous box
  ├── ObjectiveFunction — runs one simulation, returns scalar fitness (higher = worse for ego)
  ├── Optimizer         — CMA-ES (primary) + random baseline for comparison
  └── FalsificationLog  — records all parameter configs that produced FAIL
```

Fitness function:

```
f(params) = w_collision · collision_indicator
          + w_ttc · (1 / min_ttc_observed)
          + w_safety · (1 - safety_score)
          + w_compliance · (1 - compliance_score)
```

Weights: `w_collision = 10.0`, `w_ttc = 2.0`, `w_safety = 1.0`, `w_compliance = 0.5`.

### 2.3.2 Files to Create

**`arep/search/space.py`**

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
        """Convert optimizer vector to a parameterizer-compatible override dict."""
```

**`arep/search/objective.py`**

```python
class ObjectiveFunction:
    def __init__(self, scenario: ScenarioDefinition, model, physics_mode): ...
    def __call__(self, x: np.ndarray, seed: int = 0) -> float:
        """Run one simulation with params from x, return the fitness scalar."""
```

**`arep/search/optimizer.py`**

```python
class CMAESOptimizer:
    """CMA-ES via the `cma` package. Maximises f(x) by minimising -f(x)."""
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
    all_evaluations: List[Tuple[Dict, float]]
```

Add `cma>=3.3.0` to `pyproject.toml` under `[project.optional-dependencies] search`.

### 2.3.3 API

```
POST /api/search                  { scenario_id, max_evals=200, optimizer: "cma_es"|"random", physics_mode, seed }
GET  /api/search/{search_id}/status    { status, evals_done, best_fitness, falsification_found }
GET  /api/search/{search_id}/result    { best_params, best_fitness, falsification_found, falsification_params, all_evaluations }
```

**SaaS wrapping**: Pro tier and above (402 below Pro); consumes `max_evals` credits.

### Acceptance Criteria

- [ ] CMA-ES finds a collision for `ConstantAction` on LON-003 within 50 evals
- [ ] Over 50 evaluations, CMA-ES fitness beats the random-search baseline
- [ ] `falsification_params` re-run with the same seed reproduces the collision exactly
      (frame-hash equal — uses the 0.5 infrastructure)
- [ ] `SearchResult.all_evaluations` has exactly `max_evals` entries; same seed → identical
      search trajectory
- [ ] Tier gate and credit accounting correct

---

## 2.4 — Model Comparison & Regression Reports

**After**: "Model v2.1 vs v2.0: safety improved 0.08, compliance regressed 0.03."

```
POST /api/compare        { model_a_id, model_b_id, scenario_ids|"all", runs_per_scenario, seed }
GET  /api/compare/{id}/results
GET  /api/compare/{id}/report.pdf
```

A regression is flagged when composite delta < −0.05, OR safety delta < −0.10, OR
collision_rate rises by 0.01. Regressions badge the dashboard and can fire a webhook
(Phase 3).

**Frontend**: a "Compare Models" dashboard section (closes the `ComparePage` stub) —
side-by-side table, green/red delta cells, verdict badge.

**PDF**: `arep/reporting/pdf_generator.py` via `weasyprint>=60.0`; HTML template at
`arep/reporting/templates/comparison_report.html`. Executive summary, score tables, failure
highlights, and the **methodology section from 0.5** — the part a safety reviewer reads.

### Acceptance Criteria

- [ ] `EmergencyBrake` vs `ConstantAction` on LON-003 → EmergencyBrake wins
- [ ] Regression correctly flagged; PDF downloads with all sections
- [ ] Cost = `2 × runs_per_scenario × len(scenario_ids)` credits

---

## 2.5 — Deterministic Replay

**Why it sits here and not in polish**: replay is the proof of the determinism claim and the
best demo in the product — click the failure, watch it re-run, frame-identical. It also
closes the debugging gap: a deterministic platform where you cannot re-step a failed run
wastes its own guarantee.

### Two modes

1. **Re-simulate from seed** (cheap, exact): store `(scenario_path, model_id, seed,
   engine_version)` per run; re-running reproduces it bit-for-bit, guaranteed by the 0.5
   frame hash. `POST /api/runs/{run_id}/replay` spins a live run with the stored params; the
   viewer connects over the normal WS path.
2. **Stored-frame playback** (no compute): persist tick frames for failed or flagged runs
   (compressed JSON per run, retention by tier). `GET /api/runs/{run_id}/frames` → chunked
   array; the viewer plays it back client-side.

**Frontend** (closes the `RunPage` stub + `PlaybackControls`): playback bar — play/pause/step,
0.1×–5× speed, scrub timeline, jump-to-event markers from `run_events`.

### Acceptance Criteria

- [ ] Replay-from-seed of any completed run produces an identical frame hash
- [ ] A failed batch run is watchable via stored frames without re-computation
- [ ] Scrub and jump-to-collision work in the viewer

---

## Phase 2 Exit Criteria

- [ ] Demo flow in one session: submit model → adversarial search → failure cluster → replay
      the worst run → download comparison PDF
- [ ] ≥ 1 external beta user has run their actual model through the platform
- [ ] Statistical methodology reviewed by someone with a safety-engineering background

---
# PHASE 3 — CI/CD Integration

**Duration**: ~1.5 months
**Goal**: ORION becomes a native part of the model development workflow — push a model
version, ORION evaluates it, the pipeline fails if safety regresses. "GitHub Actions for
autonomous driving safety." Large AV companies build this internally for millions; ORION
hosts it.

## 3.1 — Webhook System

```
POST   /api/webhooks   { url, events: ["run.completed","batch.completed","regression.detected","search.completed"], secret }
GET    /api/webhooks
DELETE /api/webhooks/{id}
```

HMAC-SHA256 signature in `X-ORION-Signature`; 3× retry with exponential backoff; deliveries
logged in a `webhook_deliveries` table.

## 3.2 — GitHub Actions Integration

Published action `orioneval/evaluate-model@v1` (skeleton already exists at
`.github/actions/evaluate-model/`). The Docker image runs `orion evaluate`: package model →
upload → batch evaluate → poll → regression-check against the previous suite run → write
`$GITHUB_OUTPUT` → exit 0/1. Inputs: `api_key`, `model_path`, `scenarios`,
`runs_per_scenario`, `pass_threshold`, `fail_on_regression`.

A red check on every PR is the product's viral loop.

### Self-hosted suite runner (the same capability, offline)

For customers who want the suite in their own CI without hitting the hosted API:

**`arep/cli/run_suite.py`**

```
python -m arep.cli.run_suite
  --scenarios all|LON|LAT|INT|VRU|EMG|MLT|<id>
  --runs-per-scenario 10
  --pass-threshold 0.8
  --model emergency_brake|constant|<import-path>
  --output-dir ./results/
  --format json|html
```

Exits `0` if `pass_rate >= pass_threshold`, `1` otherwise, and writes a JSON/HTML report to
`--output-dir`. Shipped as a slim image (`python:3.11-slim`, `pip install -e ".[api]"`,
scenarios copied in) with `run_suite` as the entrypoint.

## 3.3 — GitLab CI Integration

Same pattern, as a GitLab CI component at `gitlab.com/orioneval/evaluate-model`.

## 3.4 — Model Versioning & History

The same model name resubmitted creates a tracked version; the dashboard shows a timeline of
composite score per version, auto-compares vN against vN−1, and flags regressions in the
dashboard and via webhook. Closes the `ModelsPage` stub.

```
GET /api/models/{name}/history
```

### Acceptance Criteria for Phase 3

- [ ] The GitHub Action fails a PR when the threshold is missed or a regression is detected
- [ ] Webhook fires < 30 s after batch completion; signature verifies
- [ ] Version history shows the correct trend across 3 submissions
- [ ] `run_suite` on 5 runs × 18 scenarios completes in < 10 minutes

---

# PHASE 4 — Ecosystem Expansion

**Duration**: ~2.5 months
**Goal**: remove reasons not to use ORION.

## 4.1 — HTTP Model Bridge & ROS2 Connector (Non-Python Models)

The ORION side (`HttpModelAdapter`) is already built. This work package is documentation,
example repositories and client adapters for **C++**, **MATLAB/Simulink**, and **ROS2**.

### ROS2 bridge

```
ORION simulation (Python, 50 Hz)
        ↕  ZeroMQ IPC
ROS2 bridge node (Python, rclpy)
        ↕  ROS2 topics
AV stack (any)
```

The bridge runs as a separate process alongside the API server: it subscribes to a ZeroMQ
`PUB` socket the engine publishes to each tick, converts ticks to ROS2 messages, and reads
the ego action back from a ROS2 control topic via a ZeroMQ `PUSH` socket.

- **`arep/bridges/ros2_bridge.py`** — `publish_tick(world, outputs)` / `get_latest_control()`
- **`arep/bridges/zmq_transport.py`** — `SimPublisher` (PUB, serialised `WorldState` per
  tick), `ControlSubscriber` (PULL, receives `Action`)
- **`ros2_bridge_node.py`** (top level, outside the `arep` package) — entry point:
  `python ros2_bridge_node.py --scenario-id LON-003 --seed 42`

| ORION output | ROS2 topic | Message type |
| --- | --- | --- |
| Ego ground truth | `/orion/ego/odom` | `nav_msgs/Odometry` |
| NPC bounding boxes | `/orion/objects` | `visualization_msgs/MarkerArray` |
| **Ego control input** | `/orion/cmd` | `ackermann_msgs/AckermannDriveStamped` |

> The original spec also mapped `sensor_msgs/LaserScan`, `NavSatFix` and `Imu` topics. Those
> depend on the sensor simulation layer and arrive with **Phase 6** — until then the bridge
> publishes ground-truth state only.

Dependencies: `pyzmq>=25.0` under `[project.optional-dependencies] ros2` (`rclpy` comes from
the ROS2 environment, not pip).

### Acceptance Criteria

- [ ] `python ros2_bridge_node.py --scenario-id LON-003 --seed 42` starts in a ROS2 Humble
      environment
- [ ] `ros2 topic echo /orion/ego/odom` shows messages at ~50 Hz
- [ ] Publishing a constant `AckermannDriveStamped` to `/orion/cmd` drives the ego
- [ ] Disconnecting the ROS2 node pauses the simulation (no action = coast, not crash)

## 4.2 — OpenDRIVE Map Support

Load a standard `.xodr` file and convert it to an ORION `RoadGraph`, unlocking real-world
road geometry exported from HD map tools, CARLA, or public datasets. A subset is enough —
full OpenDRIVE compliance is not required.

| Element | Support |
| --- | --- |
| `<road>` with straight/arc geometry | ✅ Required |
| `<road>` with polynomial (cubic) geometry | ✅ Required |
| `<laneSection>` with driving lanes | ✅ Required |
| `<junction>` with connection roads | ✅ Required |
| `<signal>` (traffic lights) | ✅ Required |
| `<object>` (static obstacles) | ⚠ Best-effort |
| Superelevation, banking | ❌ Out of scope |

**`arep/maps/xodr_parser.py`** — `OpenDRIVEParser.parse(xodr_path) -> RoadGraph`, using
`xml.etree.ElementTree` (no external dependency), discretising each road geometry into
centerline points at 1 m intervals. `scenario/parser.py` routes `road.source == "xodr"` to
it. SaaS addition: `POST /api/maps/upload` for org-scoped `.xodr` files.

```yaml
environment:
  road:
    source: xodr
    file: maps/town01_highway.xodr
    ego_start_road_id: "42"
    ego_start_s: 10.0
    ego_start_lane_id: "-1"
```

### Acceptance Criteria

- [ ] Parsing `tests/fixtures/TownSimple.xodr` produces a `RoadGraph` with ≥ 2 segments
- [ ] `is_off_road()` is correct for known on/off-road positions
- [ ] A scenario using `source: xodr` runs to completion; Three.js renders the geometry

## 4.3 — Scenario Library Expansion (18 → 60)

Ten scenarios per category, following the existing taxonomy. Each new scenario needs a
reactive BT, a full parameterization block, and a unique `master_seed`.

| Category | Current | Target |
| --- | --- | --- |
| LON (Longitudinal) | 4 | 10 |
| LAT (Lateral) | 3 | 10 |
| INT (Intersection) | 3 | 10 |
| VRU (Vulnerable Road User) | 3 | 10 |
| EMG (Emergency / Anomaly) | 3 | 10 |
| MLT (Multi-Agent) | 2 | 10 |
| **Total** | **18** | **60** |

Reserved IDs and themes:

- **LON-005…LON-010**: following-distance violation, stop-and-go traffic, sudden obstacle in
  lane, low-speed rear approach, speed bump, highway exit deceleration.
- **LAT-004…LAT-010**: parallel lane squeeze, high-speed lane-change conflict, sideswipe
  approach, narrow road oncoming, forced lane change, lane-closure merge, wet-road lane
  departure.
- **INT-003, INT-004, INT-006…INT-010**: roundabout entry, stop-sign violation, pedestrian
  crossing at an intersection, amber-light dilemma, multi-vehicle gap acceptance, blind
  intersection.
- **VRU-002, VRU-004…VRU-010**: cyclist at crosswalk, child running between cars
  (non-occluded), pedestrian at night, e-scooter in bike lane, group pedestrian crossing,
  mid-block jaywalker, pedestrian with stroller.
- **EMG-003, EMG-005…EMG-010**: fallen object on highway, sudden road closure, dust storm
  (visibility 30 m), vehicle fire ahead, emergency vehicle approach, flash-flood water.
- **MLT-002…MLT-006, MLT-008…MLT-010**: 3-vehicle chain brake, cut-in + pedestrian,
  tailgater + lead brake, merge conflict + cyclist, roundabout multi-entry.

**New behavior trees needed.** The current registry has five BTs (`hesitant_brake`,
`hesitant_cut_in`, `adaptive_tailgate`, `cautious_pedestrian`, `erratic_pedestrian`). The
expansion needs at least: `oncoming_drift` (gradual lateral move into the ego lane, with a
correction probability), `red_light_runner` (waits at line, then runs at a randomised delay),
`erratic_cyclist` (erratic pedestrian with forward heading bias plus `swerve_magnitude`),
`wrong_way_driver` (approaches head-on, accelerates if the ego does not brake), and
`tire_blowout` (random yaw impulse plus rapid deceleration). Register each in
`npc_bt._BT_REGISTRY`.

**Sampling upgrade**: parameterization today is uniform sampling only. Add importance
sampling / failure-region oversampling (seeded, deterministic) so that large suites spend
runs where failures live. 2.3 finds the failure; this exploits it at suite scale.

**SaaS packaging into suites**: Core (18, all paid plans) · Intersection (10, Starter+) ·
VRU (10, Starter+) · Emergency (10, Pro+) · Full (60, Enterprise).

## 4.4 — OpenSCENARIO 2.0 Import / Export

Read standard `.osc` files into `ScenarioDefinition` objects and write ORION scenarios back
out — the migration path from CARLA and ASAM member tools.

- **`arep/scenario/osc_importer.py`** — OpenSCENARIO 2.0 DSL (not the older XML 1.x).
  Mappings: `actor`/`Vehicle`/`Pedestrian` → `traffic` NPC entry; `act` with a
  `TimeCondition` or `EntityCondition` trigger → `trigger_type` / `trigger_value`; `drive` →
  `constant_velocity`; `brake` → `hesitant_brake` with the extracted deceleration; unknown
  actions → `scripted` with raw parameter passthrough.
- **`arep/scenario/osc_exporter.py`** — `ScenarioDefinition` → valid `.osc`;
  parameterization blocks become OSC2 `parameter` declarations with constraint ranges.

```
POST /api/scenarios/import/osc        # body: .osc file content
GET  /api/scenarios/{id}/export/osc   # returns .osc file
```

### Acceptance Criteria

- [ ] Importing the ASAM sample `CutIn.osc` produces a valid `ScenarioDefinition`
- [ ] Exporting LON-003 produces syntactically valid OpenSCENARIO 2.0
- [ ] Round-trip (ORION → OSC → ORION) preserves triggers and NPC parameters

## 4.5 — Safety-Standards Alignment

Not certification — alignment documentation that lets an enterprise safety team slot ORION
into their process:

- Map each scenario to a hazard / behavioral-requirement statement (ISO 21448 SOTIF
  vocabulary); export a traceability matrix (scenario ↔ requirement ↔ latest result).
- Document ORION's position in an ISO 26262 toolchain — the tool-confidence-level argument:
  deterministic, frame-hashed, version-pinned.
- ODD declaration per scenario suite: road types, speed ranges, actor types covered, and
  explicitly not covered.

This is a documentation and metadata work package, not an engine change, and it converts "no
ISO story" from a first-meeting deal-killer into a credible answer.

### Acceptance Criteria

- [ ] Traceability matrix exportable (CSV/PDF) for any suite
- [ ] ODD coverage statement auto-generated from scenario metadata

---

# PHASE 5 — Visualization, Frontend Debt & Developer Experience

**Duration**: ~1.5 months
**Goal**: a premium professional instrument — Bloomberg Terminal, not Unreal Engine.
**Critical principle**: no photorealism, no server-side rendering. All visual work conforms
to [UI_DESIGN.md](UI_DESIGN.md).

## 5.1 — Visualization Overhaul (Information Density, Not Eye Candy)

Playback and replay landed in 2.5; this phase is display depth.

- **Trajectory traces**: the last 3 s of ego and NPC paths as fading lines (`drei` `Line`,
  rolling buffer in the hook).
- **TTC warning zones**: an ellipse around the ego that scales with speed, red when TTC < 2 s.
- **NPC intent indicators**: `<Html>` overlay arrows per BT state (braking / accelerating /
  cutting in).
- **GLTF assets**: Kenney CC0 models replace the placeholder boxes. Packs go in
  `orion-frontend/public/models/` as static Vite assets (never imported as JS modules):
  `car.glb`, `truck.glb`, `suv.glb`, `motorcycle.glb`, `character-male.glb`,
  `character-female.glb`, `tree_default.glb`, `bush.glb`, `streetLight.glb`, `dog.glb`,
  `deer.glb`. Replace `<Vehicle>`'s `BoxGeometry` with a `useGLTF`-backed component driven by
  an NPC-type → model-path map; preload every model at app start to avoid pop-in. Roadside
  trees and street lights render through `InstancedMesh` (one draw call each). Backend side:
  add an `AnimalBT` (wanders at low speed, freezes when the ego is close) to
  `npc_bt._BT_REGISTRY` and allow `animal` as an NPC type in `scenario/schema.py`.
- **R3F performance pass**: memoize `Scene`, share materials across vehicles, cap re-renders
  — target 60 fps with 30 NPCs.

### Acceptance Criteria

- [ ] Viewer shows GLTF models, traces, TTC zone and intent arrows at 60 fps with 30 NPCs
- [ ] Trees and street lights confirmed as single instanced draw calls in devtools
- [ ] First-load increase < 3 s on a 10 Mbps connection (models total < 3 MB), no pop-in

## 5.2 — Dashboard Polish

- **Smart alerts panel**: a rules engine that runs after each batch — "LON-003 safety −12%
  since last run", "best model: my-model-v3", "3 failing INT scenarios — run adversarial
  search".
- **Onboarding flow**: upload model → run the Core Suite → view the first report; skippable,
  shown until completed.
- **Table hygiene**: pagination, sorting, and status/model/date filters on the runs table
  (currently a fixed 50 rows with no sort).

## 5.3 — Documentation & Developer Experience

**docs.orion.run** (Docusaurus or Astro): Getting Started (5 minutes to first eval), SDK
reference (autogenerated), API reference (OpenAPI autogenerated), scenario catalogue, CI/CD
guides, model submission guide, and **"How ORION evaluates your model"** — the methodology
page seeded in 0.5.

## 5.4 — Frontend Type Safety & Tests

- **Progressive TypeScript migration**: `allowJs` Vite/TS config; new files in TS; convert
  `services/api.js`, contexts and hooks first (highest prop-shape risk). A full JSX
  conversion is not required to get 80% of the benefit.
- **Test floor**: Vitest + Testing Library — api service, `AuthContext`,
  `useSimulationStream` (mock WS), `DashboardPage` render. Playwright smoke: login → start
  run → see viewer.
- Component decomposition: split `DashboardPage.jsx`.

### Acceptance Criteria for Phase 5

- [ ] A new org completes onboarding to its first report unassisted
- [ ] Docs site live; methodology page published
- [ ] Frontend CI: typecheck + unit tests + Playwright smoke green

---

# PHASE 6 — Sensor Simulation Layer (future)

**Duration**: ~2 months
**Status**: Planned, not started. **Starts only after Phase 5 exits** — every phase above it
is on the revenue path; this one widens the market after the platform is finished.
**Goal**: give the ego vehicle simulated sensor outputs (2D LiDAR point cloud, forward
camera object projections, GPS + IMU noise) so that AV stacks which consume sensor input —
not just ground-truth state — can be evaluated on ORION.

### Why it sits last, and what it changes when it lands

Until this phase ships, ORION is a planning/control evaluation harness and nothing else. That
is deliberate: the CPU-only architecture, the cents-per-suite run cost, and the "testing
laboratory, not simulator" position all depend on there being no rendering in the loop. Every
statement of positioning in this document, in `README.md` and in `docs/PROJECT_IDEA.pdf`
describes ORION *today* — a perception customer cannot use it yet.

Phase 6 changes that carefully. It does **not** add photorealism, and it never will: the
camera model emits a structured object list (bounding boxes, class labels), not rendered
pixels. That keeps the CPU-only guarantee intact while giving a real AV stack something to
consume. ORION still does not compete with CARLA or NVIDIA DRIVE Sim on rendering.

When this phase completes, update the Honest Positioning section above — the "not a
perception testbed" claim becomes "no photorealistic sensor rendering; structured sensor
output only".

## 6.1 — Sensor Configuration

**`core/state.py`** — add to `WorldState`:

```python
sensor_outputs: Dict[str, Any] = field(default_factory=dict)
# Keys: sensor_id → output object (PointCloud, CameraFrame, GNSSOutput, IMUOutput)
```

**Scenario YAML** — new optional top-level `sensors:` section. If absent, no sensor output is
computed and the run costs exactly what it costs today:

```yaml
sensors:
  - id: lidar_front
    type: lidar_2d
    mount_x: 0.0        # metres from ego centre (forward positive)
    mount_y: 0.0
    mount_z: 1.5
    range: 80.0         # metres
    fov_deg: 360.0
    ray_count: 360
    noise_std: 0.02     # metres (Gaussian range noise)

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
    position_noise_std: 0.5    # metres
    heading_noise_std: 0.01    # radians

  - id: imu
    type: imu
    accel_noise_std: 0.05      # m/s²
    gyro_noise_std: 0.002      # rad/s
```

**`scenario/schema.py`** — add `sensors: List[Dict[str, Any]] = field(default_factory=list)`
to `ScenarioDefinition`.

## 6.2 — Sensor Engine

**File to create**: `arep/simulation/sensors.py`

```python
class SensorEngine:
    """
    Computes sensor outputs for the ego vehicle each tick.
    All computations are deterministic given the world state and RNG seed.
    """
    def __init__(self, sensor_configs: List[dict]): ...
    def compute(self, world: WorldState, rng: RandomManager) -> Dict[str, Any]:
        """Returns dict of sensor_id → output. Called once per tick."""
```

**LiDAR (2D raycast)** — cast `ray_count` rays from the mount position in the ego frame; for
each ray, find the first object whose OBB it intersects; range = distance to the hit point
plus `N(0, noise_std)`, or max range if nothing is hit within `range`. Output: a `PointCloud`
dataclass with `ranges: np.ndarray` (shape `[ray_count]`) and `angles: np.ndarray`. Reuse
`VehicleState.get_bounding_box_corners()`; ray-OBB intersection via the parametric line
equation.

**Camera (pinhole, structured output only)** — project all object bounding boxes into the
image plane with a standard pinhole model. Output: a `CameraFrame` dataclass with `width`,
`height`, and `objects: List[ProjectedObject]`, where `ProjectedObject` carries `object_id`,
`bbox_pixels: [x1, y1, x2, y2]`, `class_label`, `confidence: 1.0`. **No pixel rendering** —
this is the constraint that keeps ORION CPU-only.

**GNSS** — `GNSSOutput` with `x, y` = ego position + `N(0, position_noise_std)`, `heading` =
ego heading + `N(0, heading_noise_std)`. Noise draws from `rng.get("noise")`.

**IMU** — `IMUOutput` with `accel_x, accel_y` = ego acceleration components + noise,
`yaw_rate` from the physics engine + noise.

## 6.3 — Engine Integration

**`simulation/engine.py`** — instantiate `SensorEngine` from the scenario's `sensors` list in
`__init__`; each tick, call `sensor_engine.compute(world, rng)` and store the result in
`world.sensor_outputs`.

**Determinism is not negotiable here.** Sensor noise flows through `RandomManager` like
everything else, and sensor output is part of the canonical frame — the Phase 0.5 frame hash
must stay stable for a given seed once sensors are active. A sensor that introduces
wall-clock or unseeded randomness breaks the platform's central guarantee.

## 6.4 — Sensor Output in the Stream

`ego.active_sensors` in the tick frame lists the active sensor ids. Sensor payloads ride an
extended frame field (or a WS sub-channel):

```json
"sensor_data": {
  "lidar_front": { "type": "lidar_2d", "ranges": [45.2, 44.8], "angles": [0.0, 0.0175] },
  "gnss": { "x": 145.8, "y": -1.63, "heading": 0.003 },
  "imu": { "accel_x": -1.18, "accel_y": 0.02, "yaw_rate": 0.001 }
}
```

Camera frames are excluded from the WebSocket stream (too large) and served via
`GET /api/runs/{run_id}/sensors/camera_front/latest`.

Extend the frame schema in `SimulationEngine.get_tick_frame()` — never construct frames
elsewhere.

## 6.5 — Downstream Unblocking

Two things already specified become fully useful only here:

- **ROS2 bridge (4.1)** gains its sensor topics: `/orion/scan` (`sensor_msgs/LaserScan`),
  `/orion/gnss` (`sensor_msgs/NavSatFix`), `/orion/imu` (`sensor_msgs/Imu`). Until then the
  bridge publishes ground-truth state only.
- **RL Gym adapter** (see *Deferred* below) gets the observation vector its original spec
  assumed (`lidar_ranges[360]`, GNSS, IMU).

### Acceptance Criteria

- [ ] A scenario with a `sensors:` section produces non-null `world.sensor_outputs` each tick
- [ ] LiDAR `ranges` has length `ray_count`, in metres; max range where nothing is hit,
      shorter where an NPC OBB is hit
- [ ] GNSS noise std is within 20% of the configured value over 100 runs
- [ ] Same seed → identical sensor outputs and identical frame hash; different seeds →
      different noise
- [ ] `active_sensors` appears correctly in the WebSocket frame
- [ ] A scenario with no `sensors:` section runs at the same speed as before this phase
- [ ] Positioning updated in this document, `README.md` and `CLAUDE.md`

---

# Deferred — Unscheduled

Not out of scope, not on the plan either. Pick up when there is a reason to.

### RL Gym adapter

A Gymnasium-compatible `AREPEnv` wrapper (`gym.make("AREP-LON003-v0")`, Box action space,
survival + progress reward, ≥ 500 steps/sec headless target) was specified as a Phase 2
differentiator in the old technical roadmap and never referenced by the product roadmap. It
is not on the path to revenue: RL researchers are a target *user* but not a paying segment,
and the headless throughput work it implies belongs with a performance pass rather than with
evaluation depth. Its observation vector also assumes the sensor layer, which is Phase 6.
Spec retained in `docs/archive/AREP_IMPLEMENTATION_ROADMAP.md § P2.3`.

---

# Risk Register

| Risk | Likelihood | Impact | Mitigation |
| --- | --- | --- | --- |
| Customer model executes malicious code in our infra | **High** (currently trivially possible) | Critical | Phase 0.2 interim lockdown now; gVisor/Firecracker before open signup; cloudpickle gated |
| A customer discovers a fake or incorrect score component | Medium | Critical | Phase 0.5 closes the lane stub; methodology doc; external statistical review before enterprise sales |
| Secrets misconfiguration in a real deployment | Medium | Critical | Phase 0.1 fail-fast startup validation; no defaults anywhere |
| CARLA releases a hosted SaaS version | Low | High | Accelerate Phase 3 CI/CD — not feasible on Unreal Engine |
| 2-person team runs out of runway before Phase 3 | Medium | High | Phase 1 must be revenue-generating; no Phase 4 without paying customers |
| Statistical methodology challenged by a safety expert | Low | High | External review of the CI approach before enterprise sales (Phase 2 exit criterion) |
| Enterprise deals blocked on "no ISO story" | High | Medium | Honest positioning now; Phase 4.5 alignment documentation |
| Docker model submission infra complexity | High | Medium | Docker is the default path (safer than pickle); Firecracker deferred until needed |
| Dev (SQLite) vs prod (Postgres) behavioral drift | Medium | Medium | Phase 0.6 CI on Postgres; prod refuses SQLite |
| Applied Intuition launches a mid-market tier | Medium | High | Win the mid-market first; watch their pricing page and PLG job postings (see `MARKET.md`) |

---

# Timeline Summary (2-Person Team)

```
Month 1        Phase 0: Security & Score Integrity
                 → Platform safe to put a customer on; scores honest
Month 2-3      Phase 1 remainder: Stripe billing + road topology
                 → First paying customers possible at end of month 3
Month 4-6      Phase 2: Evaluation depth (CIs, clustering, adversarial search,
                 comparison, deterministic replay)
                 → Defensibly better than CARLA for evaluation; target 10+ paying customers
Month 7-8      Phase 3: CI/CD integration
                 → Enterprise conversations realistic; GitHub Action = acquisition channel
Month 9-11     Phase 4: Ecosystem (HTTP/ROS2 bridge, OpenDRIVE, 60 scenarios,
                 OpenSCENARIO, standards alignment)
Month 12       Phase 5: Visualization, frontend debt, docs
                 → Conference-demo-worthy
Month 13-14    Phase 6: Sensor simulation layer (post-platform expansion)
                 → Sensor-consuming AV stacks become addressable
```

**First revenue target**: end of month 3 (Phases 0 + 1 complete)
**Competitive parity target**: end of month 6 (Phase 2 complete)
**Enterprise-ready target**: end of month 8 (Phase 3 complete)

---

# Immutable Constraints

These hold in every phase. `CLAUDE.md` § 4 and § 12 are the enforcement copy; this is the
rationale.

1. **Determinism** — the same `master_seed` always produces identical simulation output. No
   wall-clock seeding; all randomness flows through `RandomManager`.
2. **No shared mutable state** — `WorldState` is copied between ticks. NPC behavior state
   lives in `world.npc_behaviors[id]`, never in module-level variables.
3. **Binary verdict separation** — the evaluation monitor returns PASS / FAIL / INCONCLUSIVE.
   Metric scores are recorded separately. Never merge them.
4. **YAML immutability** — `ScenarioDefinition` is never mutated after parsing;
   `ScenarioParameterizer` creates a modified copy per run.
5. **50 Hz fixed timestep** — the loop never derives `dt` from wall time. `dt = 0.02` always.
6. **Versioning** — scenario YAMLs stay at `version: "2.0"`; increment only on a schema
   change. Increment this document's version header when any section materially changes.

---

_This document governs both product priority and technical implementation. For the system
architecture and scenario taxonomy behind it, see [ARCHITECTURE.md](ARCHITECTURE.md); for
competitive positioning, [MARKET.md](MARKET.md); for all frontend work,
[UI_DESIGN.md](UI_DESIGN.md)._
