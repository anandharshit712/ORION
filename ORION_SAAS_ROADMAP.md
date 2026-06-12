# ORION — SaaS Product Roadmap

**Version**: 2.0
**Date**: 2026-06-12
**Authors**: Harshit Anand + Claude
**Status**: Active — governing product direction document

> This roadmap supersedes `AREP_IMPLEMENTATION_ROADMAP.md` for product prioritisation.
> Technical implementation detail in that document remains valid where referenced.
> When the two conflict on priority ordering, this document wins.

---

## What Changed in v2.0

v1.0 was written before a full production-readiness review (2026-06-12). The review
confirmed the core simulation engine is solid (deterministic PCG64 seeding, correct
bicycle + Pacejka physics, SAT collision, Wilson/t-distribution statistics) but found
**four ship-blocking security defects and one score-integrity defect** in the SaaS layer.

v2.0 changes, in order of importance:

1. **New Phase 0 — Security & Score Integrity** inserted before any revenue work.
   Stripe billing (formerly next up) is pointless on a platform with a known RCE path
   and forgeable JWTs. Nothing customer-facing ships until Phase 0 exits.
2. **Score integrity treated as product-critical, not tech debt.** The lane-compliance
   metric currently returns a hardcoded `1.0` — the product sells scores, so a fake
   score component is an existential credibility risk, fixed in Phase 0.
3. **Deterministic replay promoted** from Phase 5 polish to Phase 2 (2.5). "Re-run the
   exact failure from its seed" is the demo that proves the determinism claim — it was
   buried under GLTF assets.
4. **Honest positioning section added.** ORION has no sensor simulation and no
   ISO 26262/21448 story. That defines the addressable niche; pretending otherwise
   loses enterprise deals in the first meeting.
5. **Status snapshot + known-defect register added** so this document reflects what is
   actually built, not only what is planned.

---

## Vision

ORION is a **cloud-native, subscription-based safety evaluation platform** for autonomous
driving models. Teams submit their model, choose a scenario suite, and receive
statistically rigorous safety reports — without installing anything, without owning a GPU
cluster, and without writing a single test case.

**The core bet**: CARLA is a simulator. ORION is a testing laboratory. CARLA requires a
GPU workstation and gives you a pretty scene. ORION runs on CPU-only cloud instances and
gives you answers about your model's safety profile with confidence intervals, failure
clustering, and regression tracking.

**What ORION sells**: Certainty, not screenshots.

---

## Honest Positioning — What ORION Is and Is Not

### Is

- A deterministic, statistically rigorous, CI-friendly **evaluation harness for
  planning and control stacks** that consume ground-truth state.
- The cheapest path to "did my new model version regress on safety?" answered with
  confidence intervals, on every pull request.
- Reproducible by construction: same seed → same run, every time, auditable.

### Is Not (and must not pretend to be)

- **Not a perception testbed.** No LiDAR, camera, or radar simulation. Models that need
  sensor input cannot be evaluated here (deferred — see Phase 4 note). Target customers:
  planning/control teams, RL researchers, motion-prediction teams, education.
- **Not a certification tool.** No ISO 26262 ASIL mapping, no ISO 21448 (SOTIF) ODD
  coverage argument, no HARA traceability. Enterprise AV safety teams will ask in the
  first meeting; the answer today is "no — we are an engineering regression tool, not a
  homologation tool." Phase 4.5 starts the standards-alignment story.
- **Not photorealistic.** Bloomberg Terminal, not Unreal Engine. Never compete with
  CARLA/DRIVE Sim on rendering.

| Dimension         | CARLA                                   | ORION                               |
| ----------------- | --------------------------------------- | ----------------------------------- |
| Primary value     | Photorealistic sensor data for training | Rigorous safety evaluation + scores |
| Infrastructure    | GPU workstation, local install          | Browser-based SaaS, CPU cloud       |
| Evaluation rigor  | Manual, no statistical framework        | Automated, statistically rigorous   |
| CI/CD integration | Not possible (Unreal Engine)            | First-class feature                 |
| Target user       | Perception ML engineers                 | Planning/control + safety engineers |
| Pricing model     | Free/open-source, self-hosted           | Subscription (run credits per tier) |

---

## Status Snapshot (2026-06-12)

### Built and working

| Item                                                                                           | Status                                     |
| ---------------------------------------------------------------------------------------------- | ------------------------------------------ |
| Sim core: kinematic + Pacejka dynamic physics, SAT collision, deterministic seeding            | ✅ Solid (review-verified)                 |
| Evaluation metrics: safety / stability / reactivity + Wilson & t-dist CIs in aggregator        | ✅ (lane compliance defective — see below) |
| Live streaming: `WS /ws/simulation/{run_id}` + R3F viewer (P1.1)                               | ✅                                         |
| Multi-tenancy: orgs, roles, API keys, org-scoped routes (SaaS P1.1)                            | ✅                                         |
| Model submission: cloudpickle SDK path + Docker path (SaaS P1.2)                               | ✅ functional, ❌ unsafe (RCE — Phase 0.2) |
| Async batch queue: Celery + Redis, atomic credit deduction (SaaS P1.3)                         | ✅                                         |
| Auth: bcrypt, hashed single-use reset tokens, superadmin role                                  | ✅                                         |
| 18-scenario library across all 6 categories, CI (test+lint+docker), Alembic, clean git hygiene | ✅                                         |

### Known defects (review 2026-06-12) — register

| ID   | Defect                                                                                                                                                                   | Severity | Fixed in                          |
| ---- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | -------- | --------------------------------- |
| D-01 | Cloudpickle model upload = arbitrary code execution in worker; subprocess inherits `ORION_DATABASE_URL` (`api/models_routes.py`, `models/sandbox.py`)                    | CRITICAL | 0.2                               |
| D-02 | JWT secret falls back to hardcoded string if env unset (`api/auth.py:40`); hardcoded DB creds in config defaults; plaintext creds in `infrastructure/docker-compose.yml` | CRITICAL | 0.1                               |
| D-03 | CORS `allow_origins=["*"]` + zero rate limiting on login/signup (`api/app.py`)                                                                                           | CRITICAL | 0.3                               |
| D-04 | JWT stored in `localStorage` (`AuthContext.jsx`) — violates own CLAUDE.md rule; signup auto-activates with no email verification                                         | CRITICAL | 0.4                               |
| D-05 | Lane compliance hardcoded `lane_frac = 1.0` (`evaluation/compliance.py:88`) — lane-keeping score is fake                                                                 | HIGH     | 0.5                               |
| D-06 | `time.time()` in tick frame (`simulation/engine.py:323`) — violates determinism hard rule, breaks frame hashing/replay                                                   | HIGH     | 0.5                               |
| D-07 | `/models/`, `/scenarios/` routes unauthenticated — cross-org info disclosure                                                                                             | HIGH     | 0.3                               |
| D-08 | Celery `max_retries=0` — transient failure kills run, customer eats it                                                                                                   | HIGH     | 0.6                               |
| D-09 | No coverage gate in CI; WS layer, admin routes, billing routes, partial-batch-refund untested                                                                            | HIGH     | 0.6                               |
| D-10 | Frontend: no error boundaries, no 404, `OrgProvider` written but never mounted, 5 stub pages advertised in sidebar                                                       | MED      | 0.6 / with features               |
| D-11 | TTC uses constant-velocity approximation — optimistic in critical scenarios; Pacejka coefficients uncited                                                                | MED      | 0.5 (document), Phase 2 (improve) |
| D-12 | Weight transfer uses previous-step acceleration (`core/physics.py:312`) — off-by-one                                                                                     | LOW      | 0.5                               |
| D-13 | SQLite dev vs Postgres prod — `FOR UPDATE` is a no-op on SQLite, race bugs invisible in dev                                                                              | MED      | 0.6                               |

---

# The Phases

| Phase | Name                              | Duration (2-person team) | Outcome                                         |
| ----- | --------------------------------- | ------------------------ | ----------------------------------------------- |
| **0** | Security & Score Integrity        | ~1 month                 | Platform is safe to put a customer on           |
| **1** | SaaS Foundation (remainder)       | ~1.5 months              | Real paying customers can use it                |
| **2** | Evaluation Depth                  | ~2.5 months              | Genuinely better than CARLA for evaluation      |
| **3** | CI/CD Integration                 | ~1.5 months              | The killer feature that closes enterprise deals |
| **4** | Ecosystem Expansion               | ~2.5 months              | Broad compatibility, real-world scenarios       |
| **5** | Visualization, Frontend Debt & DX | ~1.5 months              | Professional, polished, demo-worthy             |

**Total to full platform: ~10.5 months from Phase 0 start.**

---

---

# PHASE 0 — Security & Score Integrity (NEW — blocks all revenue work)

**Duration**: ~1 month
**Goal**: Close the four critical security holes and make every published score honest.
**Hard rule**: No Stripe integration, no marketing, no external beta users until every
item in 0.1–0.5 is done. Billing a customer on a platform with a known RCE is worse than
having no billing.

---

## 0.1 — Secrets & Configuration Hardening (D-02)

**Effort**: days, not weeks. Do first.

- `api/auth.py`: remove the `"orion-dev-secret-change-in-production"` fallback.
  On startup, if `ORION_SECRET_KEY` is unset **and** `ORION_ENV != "dev"`, raise and
  refuse to boot. In dev, generate an ephemeral random secret and log a warning.
- `config/__init__.py` + `database/connection.py`: remove hardcoded
  `postgresql://Harshit:Harshit@...` default. Same fail-fast pattern.
- `infrastructure/docker-compose.yml`: move `POSTGRES_PASSWORD`, `ORION_JWT_SECRET`,
  Redis URL into a git-ignored `.env` file consumed via `env_file:`. Update
  `.env.example` with placeholder values and document every required variable.
- Add a startup config validator (`arep/config/validate.py`) that runs in `app.py`
  lifespan: checks secret strength (≥32 chars), refuses SQLite when `ORION_ENV=prod`
  (also closes D-13's prod half).

### Acceptance Criteria

- [ ] API refuses to start in prod mode without `ORION_SECRET_KEY` set
- [ ] `git grep -i "Harshit:Harshit\|change-in-production"` returns zero hits in `arep/`
- [ ] docker-compose boots with secrets from `.env` only; `.env` is git-ignored

---

## 0.2 — Customer Model Sandboxing (D-01)

**The single most dangerous defect in the codebase.** A customer-uploaded cloudpickle
deserialises with full Python in a worker subprocess that inherits DB credentials.
One malicious upload = every org's data.

### Decision: interim lockdown now, real isolation before open signup

**Step 1 — Interim (this phase, mandatory):**

- Strip the worker subprocess environment: spawn model subprocess with an explicit
  whitelist env (`PATH`, `PYTHONPATH` to a read-only venv) — **no** `ORION_DATABASE_URL`,
  no Redis URL, no secrets. Model I/O happens over the existing pipe protocol only.
- Drop network: run model subprocess under an unprivileged user with no outbound network
  (Linux: `unshare --net` / network namespace; document Windows-dev limitation).
- Filesystem: subprocess working dir = empty tmpdir, read-only mount of the model
  artefact, nothing else.
- Keep existing CPU/memory rlimits; add hard wall-clock kill (model `predict()` that
  hangs gets SIGKILL, run marked failed, credit refunded) — closes the soft-timeout gap
  in `models/interface.py`.
- Gate Path A (cloudpickle) behind an org-level flag defaulting to OFF for self-serve
  signups; Docker path (already process-isolated by container boundary) is the default
  public path. Enable Path A per-org manually for trusted design partners.

**Step 2 — Before open/self-serve launch (tracked, can land in Phase 1):**

- gVisor (`runsc`) or Firecracker microVM for the model process. Container-per-run with
  no network, read-only rootfs, seccomp default profile.

### Acceptance Criteria

- [ ] Model subprocess env contains no `ORION_*` variables (test asserts this)
- [ ] A model that calls `socket.connect()` fails; run marked failed, credit refunded
- [ ] A model that sleeps forever is killed at the wall-clock limit; credit refunded
- [ ] Self-serve org cannot use cloudpickle path without manual enablement

---

## 0.3 — API Surface Hardening (D-03, D-07)

- **CORS**: replace `allow_origins=["*"]` with `ORION_ALLOWED_ORIGINS` env var
  (comma-separated whitelist). Note: `allow_credentials=True` with `*` is invalid per
  spec anyway — current config is both insecure and broken.
- **Rate limiting**: add `slowapi` (or equivalent). Limits: login 5/min/IP with
  lockout-style backoff, signup 3/hour/IP, forgot-password already rate-limited (keep),
  global default 120/min/key on API routes.
- **Auth on public routes**: `/models/`, `/scenarios/`, `/jobs/`, `/results/*` require
  auth and org-scoping like everything else. Decide deliberately if built-in model list
  stays public (marketing value) — but org-uploaded resources never leak.
- **Security headers middleware**: `Strict-Transport-Security`,
  `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, basic CSP on API responses.
- **Webhook stub**: `api/billing.py` webhook handler gets Stripe signature verification
  - event-id idempotency table NOW, even as a stub — so Phase 1.4 builds on a safe base.

### Acceptance Criteria

- [ ] Request from non-whitelisted origin gets no CORS grant
- [ ] 6th login attempt in a minute from one IP → 429
- [ ] Unauthenticated `GET /scenarios/` → 401
- [ ] Replayed webhook event id is a no-op

---

## 0.4 — Auth Flow Integrity (D-04)

- **Email verification**: signup creates user with `email_verified=false`; verification
  token emailed (reuse the hashed-token machinery from password reset). Unverified users
  can log in but cannot create runs/keys/models. Resend endpoint, rate-limited.
- **Token storage redesign**: backend sets JWT in an `httpOnly; Secure; SameSite=Lax`
  cookie on login. `AuthContext` drops `localStorage` entirely; auth state derived from a
  `GET /api/auth/me` call on mount. Keep `Authorization: Bearer` support for API-key/SDK
  clients — cookie is for the browser app only. Add CSRF protection for cookie-auth
  state-changing routes (double-submit token or `SameSite=Strict` + origin check).
- **WebSocket auth**: replace `?token=<jwt>` query param with a short-lived (60 s,
  single-use) ticket: `POST /api/runs/{id}/ws-ticket` → opaque ticket → WS connects with
  `?ticket=...`. Long-lived JWT never appears in access logs / proxy logs / browser
  history.
- Superadmin tokens: shorten expiry to 4 h (regular stays 24 h).

### Acceptance Criteria

- [ ] JWT absent from `localStorage`, present only as httpOnly cookie
- [ ] Unverified account → `POST /api/runs/` returns 403 with clear message
- [ ] WS connect with an expired/reused ticket → 4401 close; JWT never in WS URL
- [ ] Page refresh keeps the user logged in (cookie + `/me` bootstrap)

---

## 0.5 — Score Integrity (D-05, D-06, D-11, D-12)

The product is the score. Every component of every published score must be computed,
documented, and reproducible.

- **Lane compliance — real implementation**: add `lane_offset` (signed lateral distance
  to lane centerline) to `EgoSnapshot` at recording time; `ComplianceMetrics` computes
  per-step in-lane fraction + mean/max offset. Delete the `lane_frac = 1.0` stub.
  Re-baseline all stored expected scores after this lands (scores will move — that is
  the point).
- **Determinism leak**: remove `emit_ts_ms` from `get_tick_frame()` core payload; if the
  frontend needs wall-clock for latency HUD, inject it at the WebSocket send site,
  outside the canonical frame, so frame content is pure `f(seed, scenario)`.
- **Frame hash**: add a per-run rolling hash of canonical frames, stored on the run
  record. Two runs with the same seed must produce identical hashes — this becomes the
  enforceable determinism guarantee and a CI test.
- **TTC honesty**: document the constant-velocity approximation in the methodology page
  and metric docstrings ("TTC is optimistic under braking"); constant-acceleration TTC
  upgrade tracked for Phase 2.1.
- **Physics correctness pass**: weight transfer uses current-step `ax` (D-12); cite or
  flag Pacejka coefficients as empirical defaults in `DynamicVehicleParams` docstrings.
- **Methodology doc**: one page per metric — formula, weights, thresholds, known
  approximations. This becomes the "How ORION evaluates your model" page (Phase 5.3)
  and the artifact a customer's safety reviewer reads.

### Acceptance Criteria

- [ ] Lane-keeping scenario where ego drifts out of lane scores < 1.0 on compliance
- [ ] Same seed → identical frame hash across two runs and two machines (CI-enforced)
- [ ] `git grep "time.time" arep/simulation arep/core arep/evaluation` → zero hits
- [ ] Methodology doc covers all four metrics incl. stated TTC approximation

---

## 0.6 — Reliability & Test Gates (D-08, D-09, D-10, D-13)

- **Celery retry policy**: `max_retries=3`, exponential backoff (5 s/15 s/60 s),
  `autoretry_for` transient exceptions (DB disconnect, Redis hiccup). Credit refund only
  after final failure. Make tasks idempotent on `run_id` (re-execution must not
  double-write `RunRecord` or double-bump counters).
- **CI coverage gate**: `pytest --cov=arep --cov-fail-under=70` (raise later). Coverage
  uploaded as artifact.
- **Missing test suites**:
  - WebSocket integration test in CI (async client against in-process app)
  - Cross-org denial tests for every authenticated route group (admin, models, runs,
    batch, keys, billing)
  - Partial batch failure: 5 runs / 3 fail → exactly 3 credits refunded, batch
    finalises once (assert no double-finalise race)
  - Parameterized parse+validate test over all 18 scenario YAMLs
  - Alembic upgrade→downgrade→upgrade on a fresh Postgres in CI
- **Dev/prod parity (D-13)**: CI test job runs against Postgres service container, not
  SQLite, so `FOR UPDATE` paths are actually exercised.
- **Frontend minimum reliability (D-10)**: top-level `ErrorBoundary` with fallback UI;
  404 route; mount `OrgProvider` (it is needed by upcoming billing UI) or delete it —
  decide, don't leave dead; sidebar hides sections whose pages are stubs.
- **Hard-rule lint enforcement**: add a CI grep/AST check forbidding `time.time()`,
  `datetime.now()`, `import random` inside `arep/core`, `arep/simulation`,
  `arep/evaluation` — the rules in CLAUDE.md become mechanically enforced.

### Acceptance Criteria

- [ ] Transient DB error during a run → task retries and succeeds; no refund
- [ ] CI fails below 70% coverage; CI runs on Postgres
- [ ] All listed test suites green in CI
- [ ] Throwing inside any dashboard component shows fallback UI, not blank page

---

## Phase 0 Exit Checklist

- [ ] All D-01…D-09 closed (D-10 may carry stub-page items into their feature phases)
- [ ] External-facing pen-test-style pass: org A cannot read/write/infer org B data via
      any route, WS, or uploaded model
- [ ] CLAUDE.md hard-rules section matches reality again (no known violations)

---

---

# PHASE 1 — SaaS Foundation (remainder)

**Duration**: ~1.5 months
**Goal**: A real user signs up, submits a model, runs evaluations, pays.
**Already done**: 1.1 Multi-tenancy ✅ · 1.2 Model submission ✅ (hardened in 0.2) ·
1.3 Async batch queue ✅. Sections below are what remains.

---

## 1.4 — Stripe Billing Integration

**Why now and not earlier**: deferred behind Phase 0 deliberately — billing on an
insecure platform is liability, not revenue.

### Subscription Tiers

| Tier           | Monthly Price | Run Credits/mo | Concurrent Runs | Scenario Access              |
| -------------- | ------------- | -------------- | --------------- | ---------------------------- |
| **Free**       | $0            | 50             | 1               | LON category only            |
| **Starter**    | $49           | 500            | 3               | All categories               |
| **Pro**        | $199          | 3,000          | 10              | All + adversarial search     |
| **Enterprise** | Custom        | Unlimited      | Custom          | All + priority support + SLA |

Run credits roll over 3 months. Top-up at $0.10/run.

### Implementation

Stripe hosted checkout (Stripe Billing) — no custom payment UI, minimal PCI scope.

```
POST /api/billing/checkout         # create Checkout session → return URL
GET  /api/billing/portal           # Stripe Customer Portal
POST /api/billing/webhook          # subscription.updated, invoice.paid, ... (signature-verified + idempotent — built in 0.3)
GET  /api/billing/usage            # current credits, next renewal date
```

On `invoice.paid`: top up `organisations.run_credits` by tier allocation.
On `subscription.updated`: update `organisations.plan`.
Existing admin top-up/plan-change routes remain the manual fallback.
Add `stripe>=7.0.0` to pyproject.

**Frontend**: implement `BillingPage` (currently a stub) — plan card, usage meter,
checkout + portal buttons. This closes one D-10 stub.

### Acceptance Criteria

- [ ] Free-tier org with 0 credits gets 402 on `POST /api/runs/batch`
- [ ] Starter upgrade via checkout grants 500 credits within 60 s of payment
- [ ] Replayed webhook event does not double credits (idempotency from 0.3)
- [ ] BillingPage shows live plan + credits; checkout round-trip works in test mode

---

## 1.5 — Road Topology Engine

**Unchanged from v1.0 — required for ~35% of the scenario library (all INT-_, EMG-002,
MLT-_) to execute.** Full technical spec: `AREP_IMPLEMENTATION_ROADMAP.md § P1.2`.

Delivers: `RoadGraph` (`RoadSegment` + `Junction`), six templates (`highway_straight`,
`urban_straight`, `t_junction`, `four_way_intersection`, `highway_onramp`, `roundabout`),
YAML `road.template` key wired into `WorldState`, Three.js renders road geometry.

### Acceptance Criteria

- [ ] `road_templates.four_way_intersection()` returns a valid `RoadGraph`
- [ ] An INT-\* scenario with `template: four_way_intersection` loads and runs
- [ ] Three.js renders intersection geometry; junction traffic lights cycle in HUD
- [ ] Lane-offset computation (from 0.5) works on curved/junction segments, not just
      straight roads

---

## Phase 1 — Launch Checklist

Before charging the first customer:

- [ ] Phase 0 exit checklist fully green (non-negotiable)
- [ ] Sign-up → email verify → org → first run → results: whole flow works in production
- [ ] Stripe live mode; model submission works via Docker path (cloudpickle gated per 0.2)
- [ ] All 18 scenarios runnable (INT needs 1.5)
- [ ] HTTPS everywhere; secrets from env/secret store only
- [ ] Basic admin view: orgs, usage, error rates
- [ ] Step-2 sandboxing (gVisor/Firecracker) done **or** cloudpickle path still gated off

---

---

# PHASE 2 — Evaluation Depth

**Duration**: ~2.5 months
**Goal**: Make evaluation output so much richer than competitors that it becomes the
primary reason customers choose ORION.

---

## 2.1 — Statistical Rigor: Confidence Intervals & Distribution Analysis

**Currently**: aggregator already computes Wilson + t-distribution CIs internally; they
are not surfaced through batch results API or dashboard.
**After**: `safety_score: 0.73 ± 0.04 (95% CI, n=100)` with full distribution shown.

### Changes

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

Per-metric distributions + `collision_rate_ci_95` (Wilson) + `worst_run_id` /
`best_run_id`. scipy/numpy already pinned — no new deps.

Also in this work package (from review):

- **Constant-acceleration TTC** option (closes D-11 properly): TTC computed from relative
  velocity _and_ relative acceleration; constant-velocity kept as documented fallback.
- Document small-n behavior (ddof=1, wide CIs at n<5) in methodology page.

### API + Frontend

`GET /api/runs/batch/{batch_id}/results` includes full `ScoreDistribution` objects
(additive change). Dashboard score cards: mean + ±CI annotation + inline 10-bin
spark-histogram (Recharts).

### Acceptance Criteria

- [ ] CI widens as n decreases (verified n=5/20/100)
- [ ] Same seed → identical distribution statistics
- [ ] Frontend shows CI on all score cards
- [ ] TTC-with-acceleration flagged scenarios show earlier threat detection than CV-TTC

---

## 2.2 — Failure Clustering & Root Cause Analysis

**Currently**: you know a model failed; not why.
**After**: "42% of failures occurred when NPC initial distance < 25 m AND ego speed > 15 m/s."

**File**: `arep/analysis/failure_clustering.py` — `FailureClusterer.analyse(batch_id)`:
pull FAIL runs → extract parameter vector per run (seed + parameterizer) → DBSCAN
clustering → per-cluster mean params, failure rate, dominant event → top-3
human-readable `FaultCondition`s + `safe_region_description`.
Add `scikit-learn>=1.3.0` optional dep.

```
GET /api/runs/batch/{batch_id}/failure-report     # lazy-computed, DB-cached
```

**Frontend**: "Failure Analysis" panel in scenario drill-down — condition cards, failure
rate bars, "See example run →" link into SimulationViewer.

### Acceptance Criteria

- [ ] 50-run LON-003 batch with `ConstantAction` produces non-empty `FailureReport`
- [ ] Descriptions reference actual parameter names; `example_run_id` is a real FAIL run

---

## 2.3 — Adversarial Scenario Search

**The single biggest technical differentiator.** Full spec:
`AREP_IMPLEMENTATION_ROADMAP.md § P2.1`. CMA-ES searches the parameterization space for
the configuration that maximally violates safety properties. `POST /api/search` → async
job → worst-case parameters.

**SaaS wrapping**: Pro-tier-only (402 below Pro); consumes `max_evals` credits.

### Acceptance Criteria

- [ ] CMA-ES finds a collision for `ConstantAction` on LON-003 within 50 evals
- [ ] `falsification_params` re-run with same seed reproduces the collision exactly
      (frame-hash equal — uses 0.5 infrastructure)
- [ ] Tier gate + credit accounting correct

---

## 2.4 — Model Comparison & Regression Reports

**After**: "Model v2.1 vs v2.0: safety improved 0.08, compliance regressed 0.03."

```
POST /api/compare        { model_a_id, model_b_id, scenario_ids|"all", runs_per_scenario, seed }
GET  /api/compare/{id}/results
GET  /api/compare/{id}/report.pdf
```

Regression flagged when composite delta < −0.05, OR safety delta < −0.10, OR
collision_rate +0.01. Regressions badge the dashboard and can fire a webhook (Phase 3).

**Frontend**: "Compare Models" dashboard section (closes the `ComparePage` stub) —
side-by-side table, green/red delta cells, verdict badge.

**PDF**: `arep/reporting/pdf_generator.py` via `weasyprint>=60.0`; HTML template at
`arep/reporting/templates/comparison_report.html`. Executive summary, score tables,
failure highlights, **methodology section from 0.5** (the part a safety reviewer reads).

### Acceptance Criteria

- [ ] `EmergencyBrake` vs `ConstantAction` on LON-003 → EmergencyBrake wins
- [ ] Regression correctly flagged; PDF downloads with all sections
- [ ] Cost = `2 × runs_per_scenario × len(scenario_ids)` credits

---

## 2.5 — Deterministic Replay (promoted from Phase 5)

**Why promoted**: replay is the proof of the determinism claim and the best demo in the
product — "click the failure, watch it re-run, frame-identical." It also closes the
debugging gap: a deterministic platform where you cannot re-step a failed run wastes its
own guarantee.

### Two modes

1. **Re-simulate from seed** (cheap, exact): store `(scenario_path, model_id, seed,
engine_version)` per run — re-running reproduces the run bit-for-bit (guaranteed by
   the 0.5 frame hash). `POST /api/runs/{run_id}/replay` spins a live run with stored
   params; viewer connects over the normal WS path.
2. **Stored-frame playback** (no compute): persist tick frames for failed/flagged runs
   (compressed JSON per run; retention by tier). `GET /api/runs/{run_id}/frames` →
   chunked array; viewer plays back client-side.

**Frontend** (closes the `RunPage` stub + `PlaybackControls`): playback bar —
play/pause/step, 0.1×–5× speed, scrub timeline, jump-to-event markers from `run_events`.

### Acceptance Criteria

- [ ] Replay-from-seed of any completed run produces identical frame hash
- [ ] Failed batch run is watchable via stored frames without re-computation
- [ ] Scrub + jump-to-collision works in viewer

---

## Phase 2 Exit Criteria

- [ ] Demo flow in one session: submit model → adversarial search → failure cluster →
      replay the worst run → download comparison PDF
- [ ] ≥1 external beta user has run their actual model through the platform
- [ ] Statistical methodology reviewed by someone with a safety-engineering background

---

---

# PHASE 3 — CI/CD Integration

**Duration**: ~1.5 months
**Goal**: ORION becomes a native part of the model development workflow: push a model
version, ORION evaluates it, the pipeline fails if safety regresses. "GitHub Actions for
autonomous driving safety." Large AV companies build this internally for millions;
ORION hosts it.

## 3.1 — Webhook System

```
POST   /api/webhooks      { url, events: ["run.completed","batch.completed","regression.detected","search.completed"], secret }
GET    /api/webhooks
DELETE /api/webhooks/{id}
```

HMAC-SHA256 signature in `X-ORION-Signature`; 3× retry with exponential backoff;
deliveries logged in `webhook_deliveries` table.

## 3.2 — GitHub Actions Integration

Published action `orioneval/evaluate-model@v1` (skeleton already exists at
`.github/actions/evaluate-model/`). Docker image runs `orion evaluate`: package model →
upload → batch evaluate → poll → regression-check vs previous suite run → write
`$GITHUB_OUTPUT` → exit 0/1. Inputs: `api_key`, `model_path`, `scenarios`,
`runs_per_scenario`, `pass_threshold`, `fail_on_regression`.

Red check on every PR = the product's viral loop.

## 3.3 — GitLab CI Integration

Same pattern, GitLab CI component at `gitlab.com/orioneval/evaluate-model`.

## 3.4 — Model Versioning & History

Same model name resubmitted → versions tracked; dashboard timeline of composite score
per version; auto regression compare vN vs vN−1; flags in dashboard + webhook.
(Closes the `ModelsPage` stub.)

```
GET /api/models/{name}/history
```

### Acceptance Criteria for Phase 3

- [ ] GitHub Action fails a PR when threshold missed or regression detected
- [ ] Webhook fires < 30 s after batch completion; signature verifies
- [ ] Version history shows correct trend across 3 submissions

---

---

# PHASE 4 — Ecosystem Expansion

**Duration**: ~2.5 months
**Goal**: Remove reasons not to use ORION.

## 4.1 — HTTP Model Bridge (Non-Python Models)

Extend Docker path docs + adapters for **C++**, **ROS2** (ZMQ bridge —
`AREP_IMPLEMENTATION_ROADMAP.md § P2.2`), **MATLAB/Simulink**. ORION side
(`HttpModelAdapter`) already built — this is documentation, example repos, client
adapters.

## 4.2 — OpenDRIVE Map Support

Full spec: `AREP_IMPLEMENTATION_ROADMAP.md § P2.4`. Customers test on real-world road
geometry. SaaS addition: `POST /api/maps/upload` for org-scoped `.xodr` files.

## 4.3 — Scenario Library Expansion (18 → 60)

Full target list: `AREP_IMPLEMENTATION_ROADMAP.md § P3.4`. SaaS packaging into suites:
Core (18, all paid plans) · Intersection (10, Starter+) · VRU (10, Starter+) ·
Emergency (10, Pro+) · Full (60, Enterprise).

**Sampling upgrade (from review)**: parameterization today is uniform sampling only.
Add importance sampling / failure-region oversampling (seeded, deterministic) so large
suites spend runs where failures live. Competitors' headline is "find the failure
automatically" — 2.3 finds it, this exploits it at suite scale.

## 4.4 — OpenSCENARIO Import

Full spec: `AREP_IMPLEMENTATION_ROADMAP.md § P3.1`. Migration path from CARLA:
`POST /api/scenarios/import/osc`.

## 4.5 — Safety-Standards Alignment (NEW — enterprise prerequisite)

Not certification — alignment documentation that lets an enterprise safety team slot
ORION into their process:

- Map each scenario to a hazard/behavioral-requirement statement (ISO 21448 SOTIF
  vocabulary); export a traceability matrix (scenario ↔ requirement ↔ latest result).
- Document ORION's position in an ISO 26262 toolchain (tool confidence level argument:
  deterministic, frame-hashed, version-pinned).
- ODD declaration per scenario suite (road types, speed ranges, actor types covered —
  and explicitly NOT covered).

This is a documentation + metadata work package, not an engine change, and it converts
"no ISO story" from a first-meeting deal-killer into a credible answer.

### Acceptance Criteria

- [ ] Traceability matrix exportable (CSV/PDF) for any suite
- [ ] ODD coverage statement auto-generated from scenario metadata

---

---

# PHASE 5 — Visualization, Frontend Debt & Developer Experience

**Duration**: ~1.5 months
**Goal**: Premium professional instrument — Bloomberg Terminal, not Unreal Engine.
**Critical principle**: no photorealism, no server-side rendering.

## 5.1 — Visualization Overhaul (Information Density, Not Eye Candy)

Playback/replay landed in 2.5; this phase is display depth:

- **Trajectory traces**: last 3 s of ego + NPC paths as fading lines (`drei` `Line`,
  rolling buffer in hook).
- **TTC warning zones**: ellipse around ego scaling with speed, red when TTC < 2 s.
- **NPC intent indicators**: `<Html>` overlay arrows per BT state (braking/accelerating/
  cutting-in).
- **GLTF assets**: Kenney CC0 models replace boxes (`AREP_IMPLEMENTATION_ROADMAP.md
§ P3.5`); static assets from Vite only.
- **R3F perf pass** (from review): memoize `Scene`, share materials across vehicles,
  cap re-renders — target 60 fps with 30 NPCs.

## 5.2 — Dashboard Polish

- **Smart alerts panel**: rules engine after each batch ("LON-003 safety −12% since last
  run", "best model: my-model-v3", "3 failing INT scenarios — run adversarial search").
- **Onboarding flow**: upload model → run Core Suite → view first report; skippable,
  shown until completed.
- **Table hygiene** (from review): pagination + sorting + status/model/date filters on
  runs table (currently fixed 50, no sort).

## 5.3 — Documentation & Developer Experience

**docs.orion.run** (Docusaurus/Astro): Getting Started (5 min to first eval), SDK
reference (autogen), API reference (OpenAPI autogen), scenario catalogue, CI/CD guides,
model submission guide, and **"How ORION evaluates your model"** — the methodology page
seeded in 0.5.

## 5.4 — Frontend Type Safety & Tests (NEW — debt from review)

- **Progressive TypeScript migration**: `allowJs` Vite/TS config; new files in TS;
  convert `services/api.js`, contexts, hooks first (highest prop-shape risk). Full JSX
  conversion not required to get 80% of the safety.
- **Test floor**: Vitest + Testing Library — api service, AuthContext, useSimulationStream
  (mock WS), DashboardPage render. Playwright smoke: login → start run → see viewer.
- Component decomposition: split `DashboardPage.jsx` (357 lines, 6 inline components).

### Acceptance Criteria for Phase 5

- [ ] Viewer: traces + TTC zone + intent arrows at 60 fps with 30 NPCs
- [ ] New org completes onboarding to first report unassisted
- [ ] docs site live; methodology page published
- [ ] Frontend CI: typecheck + unit tests + Playwright smoke green

---

---

# Risk Register

| Risk                                                  | Likelihood                              | Impact   | Mitigation                                                                                       |
| ----------------------------------------------------- | --------------------------------------- | -------- | ------------------------------------------------------------------------------------------------ |
| Customer model executes malicious code in our infra   | **High** (currently trivially possible) | Critical | Phase 0.2 interim lockdown now; gVisor/Firecracker before open signup; cloudpickle gated         |
| A customer discovers a fake/incorrect score component | Medium                                  | Critical | Phase 0.5 closes lane stub; methodology doc; external statistical review before enterprise sales |
| Secrets misconfiguration in a real deployment         | Medium                                  | Critical | Phase 0.1 fail-fast startup validation; no defaults anywhere                                     |
| CARLA releases a hosted SaaS version                  | Low                                     | High     | Accelerate Phase 3 CI/CD — not feasible on Unreal Engine                                         |
| 2-person team runs out of runway before Phase 3       | Medium                                  | High     | Phase 1 must be revenue-generating; no Phase 4 without paying customers                          |
| Statistical methodology challenged by a safety expert | Low                                     | High     | External review of CI approach before enterprise sales (Phase 2 exit criterion)                  |
| Enterprise deals blocked on "no ISO story"            | High                                    | Medium   | Honest positioning now; Phase 4.5 alignment documentation                                        |
| Docker model submission infra complexity              | High                                    | Medium   | Docker is default path (safer than pickle); Firecracker deferred until needed                    |
| Dev (SQLite) vs prod (Postgres) behavioral drift      | Medium                                  | Medium   | Phase 0.6 CI on Postgres; prod refuses SQLite                                                    |

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
Month 9-11     Phase 4: Ecosystem (HTTP bridge, OpenDRIVE, 60 scenarios,
                 OpenSCENARIO, standards alignment)
Month 12       Phase 5: Visualization, frontend debt, docs
                 → Conference-demo-worthy
```

**First revenue target**: end of month 3 (Phase 0 + 1 complete)
**Competitive parity target**: end of month 6 (Phase 2 complete)
**Enterprise-ready target**: end of month 8 (Phase 3 complete)

---

_This document governs product direction. Technical specification for simulation
components lives in `AREP_IMPLEMENTATION_ROADMAP.md`. When both documents address the
same feature, this document's priority ordering and SaaS framing take precedence._
