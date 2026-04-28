# ORION — SaaS Product Roadmap

**Version**: 1.0  
**Date**: 2026-04-26  
**Authors**: Harshit Anand + Claude  
**Status**: Active — governing product direction document

> This roadmap supersedes the original `AREP_IMPLEMENTATION_ROADMAP.md` for product
> prioritisation decisions. The technical implementation details in that document remain
> valid and are referenced where applicable. When the two documents conflict on priority
> ordering, this document wins.

---

## Vision

ORION is a **cloud-native, subscription-based safety evaluation platform** for autonomous
driving models. Teams submit their model, choose a scenario suite, and receive statistically
rigorous safety reports — without installing anything, without owning a GPU cluster, and
without writing a single test case.

**The core bet**: CARLA is a simulator. ORION is a testing laboratory. CARLA requires a
powerful GPU workstation and gives you a pretty scene. ORION runs on CPU-only cloud
instances, costs a fraction of the price, and gives you answers about your model's safety
profile with confidence intervals, failure clustering, and regression tracking.

**What ORION sells**: Certainty, not screenshots.

---

## Positioning Summary

| Dimension         | CARLA                                   | ORION                                 |
| ----------------- | --------------------------------------- | ------------------------------------- |
| Primary value     | Photorealistic sensor data for training | Rigorous safety evaluation + scores   |
| Infrastructure    | GPU workstation, local install          | Browser-based SaaS, CPU cloud         |
| Evaluation rigor  | Manual, no statistical framework        | Automated, statistically rigorous     |
| CI/CD integration | Not possible (Unreal Engine)            | First-class feature                   |
| Target user       | Perception ML engineers                 | Safety validation engineers, AV teams |
| Pricing model     | Free/open-source, self-hosted           | Subscription (run credits per tier)   |

---

## The Five Phases

| Phase | Name                       | Duration (2-person team) | Outcome                                               |
| ----- | -------------------------- | ------------------------ | ----------------------------------------------------- |
| **1** | SaaS Platform Foundation   | ~3 months                | Real paying customers can use it                      |
| **2** | Evaluation Depth           | ~2.5 months              | Product is genuinely better than CARLA for evaluation |
| **3** | CI/CD Integration          | ~1.5 months              | The killer feature that closes enterprise deals       |
| **4** | Ecosystem Expansion        | ~2.5 months              | Broad compatibility, real-world scenarios             |
| **5** | Visualization & Experience | ~1.5 months              | Professional, polished, demo-worthy                   |

**Total to full platform: ~11 months**

---

---

# PHASE 1 — SaaS Platform Foundation

**Duration**: ~3 months  
**Goal**: A real user can sign up, submit their model, run evaluations, and pay for it.
Nothing else matters until this works end-to-end.

**What changes from the existing roadmap**: Road topology (P1.2) is pulled into this phase
because one-third of the existing scenario library currently cannot execute. Sensor
simulation (P1.3 in the original roadmap) is deprioritised — it is a large engineering
investment that does not directly serve evaluation customers yet. Batch execution (P1.4) is
also pulled into this phase because it is required for the billing model to make sense.

---

## 1.1 — Multi-Tenancy & Organisation Model

**Why first**: Every subsequent feature (billing, model submission, run history, API keys)
builds on the data model established here. Build this wrong and you re-do everything.

### Data Model

Add the following tables to the database (SQLAlchemy models + Alembic migration):

```
organisations
  id            UUID PK
  name          VARCHAR
  slug          VARCHAR UNIQUE        # used in URLs, e.g. orion.run/acme
  plan          VARCHAR               # free | starter | pro | enterprise
  run_credits   INT                   # remaining evaluation run credits
  created_at    TIMESTAMP

users
  id            UUID PK
  org_id        UUID FK organisations
  email         VARCHAR UNIQUE
  role          VARCHAR               # owner | admin | member | viewer
  created_at    TIMESTAMP

api_keys
  id            UUID PK
  org_id        UUID FK organisations
  user_id       UUID FK users
  key_hash      VARCHAR               # store only the hash, never the plaintext
  label         VARCHAR               # "CI pipeline" or "dev laptop"
  last_used_at  TIMESTAMP
  created_at    TIMESTAMP
  revoked_at    TIMESTAMP NULLABLE
```

Modify the existing `users` table if one exists — add `org_id` and `role`. Existing JWT
auth (`api/auth.py`) must be updated to include `org_id` and `role` in the token payload.

### API Changes

All existing routes must enforce org-scoped access: a user can only read/write resources
belonging to their `org_id`. Add middleware in `api/app.py` that extracts `org_id` from
the JWT and attaches it to the request state.

```
POST   /api/auth/signup         # creates user + org in one call (first user = owner)
POST   /api/auth/login          # returns JWT with org_id + role
POST   /api/orgs/invite         # owner/admin: invite user by email
GET    /api/orgs/me             # org details + current plan + credits remaining
POST   /api/keys                # create API key, returns plaintext once
GET    /api/keys                # list API keys (label, last_used, never the key)
DELETE /api/keys/{id}           # revoke API key
```

API key auth: accept `Authorization: Bearer <api_key>` in addition to JWT. The middleware
resolves both to `(org_id, user_id, role)` on the request state.

### Acceptance Criteria

- [ ] Two orgs can exist; user from org A cannot read runs belonging to org B
- [ ] API key created by org A is rejected when org B's endpoints are called
- [ ] JWT and API key auth both work on all protected routes
- [ ] `GET /api/orgs/me` returns correct `run_credits` value

---

## 1.2 — Model Submission System

**Why second**: This is the core value exchange. Without it, ORION only tests the four
built-in toy models, which is useless as a product.

### Two Submission Paths

**Path A — Python SDK** (for teams whose model is a Python object):

Create a Python package: `pip install orion-sdk`

```python
# What the customer writes
from orion_sdk import ModelInterface, upload_model

class MyADModel(ModelInterface):
    def predict(self, observation) -> Action:
        ...
    def reset(self) -> None:
        ...

upload_model(
    model=MyADModel(),
    name="my-model-v2.1",
    api_key="sk-orion-..."
)
```

`upload_model` serialises the model class definition and its dependencies using `cloudpickle`,
uploads it to `POST /api/models/upload` as a multipart form, and returns a `model_id`.

The backend stores the serialised model in object storage (S3-compatible). When a run is
submitted, the worker deserialises it in an isolated subprocess using `subprocess` + a
restricted Python environment (no network access from within the model process).

**Path B — Docker Container** (for teams with complex runtimes — ROS2, CUDA, etc.):

```bash
# What the customer runs
docker push registry.orion.run/acme/my-model:v2.1
orion models register \
  --image registry.orion.run/acme/my-model:v2.1 \
  --interface http \
  --port 8080 \
  --name "my-model-v2.1"
```

ORION spins up the container per-run alongside the simulation engine. The container exposes
a simple HTTP interface:

- `POST /predict` — receives `Observation` JSON, returns `Action` JSON
- `POST /reset` — called before each run

The simulation engine's `ModelWrapper` is extended with an `HttpModelAdapter` that
translates the existing Python `ModelInterface` protocol to HTTP calls.

### Files to Create

```
orion-sdk/                        # new Python package (separate repo or monorepo subfolder)
  orion_sdk/
    interface.py                  # ModelInterface + Action + Observation (mirrors arep.*)
    uploader.py                   # upload_model() implementation
    cli.py                        # `orion` CLI (models, runs, keys subcommands)

arep_implementation/arep/
  models/
    http_adapter.py               # HttpModelAdapter: ModelInterface → HTTP calls
    sandbox.py                    # SubprocessModelRunner: runs pickled model in isolation
  api/
    model_store.py                # upload, list, fetch model artefacts from object storage
```

### Database Addition

```
models
  id            UUID PK
  org_id        UUID FK organisations
  name          VARCHAR
  version       VARCHAR
  submission_type  VARCHAR         # python_sdk | docker
  artefact_uri  VARCHAR            # s3://... or registry.orion.run/...
  created_at    TIMESTAMP
  status        VARCHAR            # uploading | ready | error
```

### New API Endpoints

```
POST   /api/models/upload         # multipart: cloudpickle blob
POST   /api/models/register       # body: { name, version, image, port }
GET    /api/models                # list org's models
DELETE /api/models/{id}
```

### Security Note

Sandboxing customer model code is a security-critical concern. For the initial SaaS launch,
use `subprocess` isolation with `resource` limits (CPU time, memory) and no network access
from the model process. For scale, move to Firecracker microVMs — defer this until you
have paying customers who need it.

### Acceptance Criteria

- [ ] `upload_model(MyModel(), ...)` successfully serialises and uploads via the SDK
- [ ] A run started with a Python SDK model executes and returns real scores
- [ ] A run started with a Docker model executes and returns real scores (requires Docker on the worker)
- [ ] Two different customers' models cannot see each other's artefacts

---

## 1.3 — Job Queue & Async Batch Execution

**Why here**: The billing model is per-run-credit. Credits must be consumed reliably. If
a batch of 100 runs is requested, it must complete even if the HTTP connection drops.
Synchronous execution cannot provide this.

### Stack

**Celery + Redis**: Celery for task queue, Redis as the broker and result backend. This is
the simplest production-proven option for Python async work queues.

Add to `pyproject.toml`:

```
celery>=5.3.0
redis>=5.0.0
flower>=2.0.0      # Celery monitoring UI, optional but useful in dev
```

### Architecture

```
API Server (FastAPI)
  POST /api/runs/batch
    → deduct run_credits from org (fail fast if insufficient)
    → create BatchJob record (status=queued)
    → enqueue N Celery tasks (one per run)
    → return { batch_id, estimated_start }

Celery Workers (1 or more processes)
  Task: run_single_simulation(run_id, scenario_id, model_id, seed, org_id)
    → fetch model artefact from object storage
    → deserialise / spin up container
    → run SimulationEngine headlessly (no WebSocket streaming)
    → write results to run_metrics table
    → update run status → "completed"
    → publish progress event to Redis pubsub

API: GET /api/runs/batch/{batch_id}/status
  → reads from DB, returns { total, queued, running, complete, failed }
```

### Files to Create / Modify

```
arep_implementation/arep/
  worker/
    celery_app.py               # Celery application init
    tasks.py                    # run_single_simulation task
  execution/
    runner.py                   # add headless batch path (existing file, extend)
  api/
    routes.py                   # wire POST /api/runs/batch to enqueue tasks
```

### Credit Deduction Logic

Credit deduction must be atomic:

```python
# In routes.py, before enqueuing:
with session_scope() as db:
    org = db.query(Organisation).with_for_update().get(org_id)
    if org.run_credits < num_runs:
        raise HTTPException(402, "Insufficient run credits")
    org.run_credits -= num_runs
    db.commit()
# Then enqueue tasks
```

If tasks fail, credits are refunded via a Celery failure callback.

### Acceptance Criteria

- [ ] `POST /api/runs/batch` returns immediately (< 300ms) regardless of `num_runs`
- [ ] Closing the HTTP connection does not stop background execution
- [ ] Credits are deducted before execution and refunded on failure
- [ ] `GET /api/runs/batch/{batch_id}/status` correctly reflects real-time progress
- [ ] Worker can process ≥ 10 concurrent headless runs without OOM on a 2-core/4GB instance

---

## 1.4 — Stripe Billing Integration

**Why here**: Without billing, you have a demo, not a product.

### Subscription Tiers

| Tier           | Monthly Price | Run Credits/mo | Concurrent Runs | Scenario Access              |
| -------------- | ------------- | -------------- | --------------- | ---------------------------- |
| **Free**       | $0            | 50             | 1               | LON category only            |
| **Starter**    | $49           | 500            | 3               | All categories               |
| **Pro**        | $199          | 3,000          | 10              | All + adversarial search     |
| **Enterprise** | Custom        | Unlimited      | Custom          | All + priority support + SLA |

Run credits roll over for 3 months. Top-up credits available at $0.10/run.

### Implementation

Use Stripe's hosted checkout (Stripe Billing) — do not implement a custom payment UI.
This minimises PCI compliance scope.

```
POST /api/billing/checkout         # create Stripe Checkout session → return URL
GET  /api/billing/portal           # Stripe Customer Portal for self-service
POST /api/billing/webhook          # Stripe webhook: subscription.updated, invoice.paid, etc.
GET  /api/billing/usage            # current credits, next renewal date
```

On `invoice.paid` webhook: top up `organisations.run_credits` by the tier's monthly
allocation. On `subscription.updated`: update `organisations.plan`.

Add to `pyproject.toml`: `stripe>=7.0.0`

### Acceptance Criteria

- [ ] New user on Free tier has 50 credits and cannot run more than 50 simulations
- [ ] Upgrading to Starter via Stripe checkout gives 500 credits within 60 seconds of payment
- [ ] Top-up purchase of 100 credits at $10 adds exactly 100 credits
- [ ] Webhook is idempotent (replaying the same event twice does not double credits)

---

## 1.5 — Road Topology Engine

**Pulled from original P1.2 — required for one-third of the scenario library to execute.**

The existing `AREP_IMPLEMENTATION_ROADMAP.md` section P1.2 contains the complete technical
specification for this. Follow it exactly. Summary of what it delivers:

- `RoadGraph` data model with `RoadSegment` and `Junction`
- Six road templates: `highway_straight`, `urban_straight`, `t_junction`,
  `four_way_intersection`, `highway_onramp`, `roundabout`
- YAML `road.template` key parsed and wired into `WorldState`
- Three.js scene renders the road graph geometry

**This unlocks**: All INT-_, EMG-002, and MLT-_ scenarios. Without it you are selling
a platform that cannot run roughly 35% of its advertised scenario library.

Refer to `AREP_IMPLEMENTATION_ROADMAP.md § P1.2` for full implementation detail.

### Acceptance Criteria (same as original P1.2, reproduced here for completeness)

- [ ] `road_templates.four_way_intersection()` returns a valid `RoadGraph`
- [ ] An INT-\* scenario with `template: four_way_intersection` loads and runs
- [ ] Three.js scene renders intersection geometry correctly
- [ ] Traffic lights at junctions cycle and appear in the HUD

---

## Phase 1 — Launch Checklist

Before calling Phase 1 complete and charging the first customer:

- [ ] Sign-up → org creation → first run → view results: entire flow works in production
- [ ] Stripe billing live (not test mode)
- [ ] Model submission works via Python SDK (Docker path can follow in Phase 2)
- [ ] At minimum 18 scenarios runnable (all LON, LAT, VRU; INT needs road topology)
- [ ] Org isolation verified: penetration test that org A cannot access org B data
- [ ] HTTPS everywhere, JWT secrets rotated from defaults
- [ ] Basic admin view: list of orgs, usage, error rates

---

---

# PHASE 2 — Evaluation Depth

**Duration**: ~2.5 months  
**Goal**: Make the evaluation output so much richer than competitors that it becomes the
primary reason customers choose ORION. CARLA gives you a simulator. ORION gives you
answers. This is where that claim gets earned.

---

## 2.1 — Statistical Rigor: Confidence Intervals & Distribution Analysis

**Currently**: Scores are single point estimates (e.g. `safety_score: 0.73`).  
**After this**: `safety_score: 0.73 ± 0.04 (95% CI, n=100)` with full distribution shown.

### Changes to `StatisticalAggregator`

File: `arep_implementation/arep/statistics/aggregator.py`

Add to `AggregatedResult`:

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

@dataclass
class AggregatedResult:
    # existing fields...
    composite_distribution: ScoreDistribution
    safety_distribution: ScoreDistribution
    compliance_distribution: ScoreDistribution
    stability_distribution: ScoreDistribution
    reactivity_distribution: ScoreDistribution
    collision_rate: float
    collision_rate_ci_95: Tuple[float, float]  # Wilson interval
    worst_run_id: str
    best_run_id: str
```

Use `scipy.stats.t.interval` for mean CI and Wilson interval for collision rate CI.
Both scipy and numpy are already pinned dependencies — no new deps required.

### API Changes

`GET /api/runs/batch/{batch_id}/results` response must include the full
`ScoreDistribution` objects for each metric. Existing clients are unaffected (additive).

### Frontend: Distribution Display

In `DashboardPage.jsx`, the score cards for a completed batch show:

- The mean score as the primary number
- The 95% CI as a ± annotation in smaller text
- A small inline spark-histogram of the score distribution using Recharts `BarChart`
  (10 bins, renders inline at ~120×40px)

### Acceptance Criteria

- [ ] `AggregatedResult` includes `composite_distribution.ci_95_low/high` values
- [ ] CI widens as `n` decreases (verified at n=5, n=20, n=100)
- [ ] Same seed always produces identical distribution statistics
- [ ] Frontend shows CI annotation on all score cards

---

## 2.2 — Failure Clustering & Root Cause Analysis

**Currently**: You know a model failed. You don't know why.  
**After this**: "42% of failures occurred when NPC initial distance was < 25m AND
ego initial speed was > 15 m/s."

### Architecture

After a batch completes, run a clustering pass over the `run_events` and `run_metrics`
data for all FAIL runs. The goal is to find which parameter combinations are associated
with failures.

**File to create**: `arep_implementation/arep/analysis/failure_clustering.py`

```python
class FailureClusterer:
    def analyse(self, batch_id: str) -> FailureReport:
        """
        For a completed batch:
        1. Pull all FAIL runs from DB
        2. Extract parameter vector for each run (from run.seed + scenario parameterizer)
        3. Run DBSCAN clustering on parameter vectors
        4. For each cluster: compute mean parameters, failure rate, dominant event type
        5. Identify the top 3 "fault conditions" as human-readable strings
        """

@dataclass
class FaultCondition:
    description: str              # e.g. "NPC initial_x < 28m with ego_speed > 14 m/s"
    failure_rate: float           # fraction of runs in this cluster that FAIL
    run_count: int
    dominant_event: str           # e.g. "collision" | "speed_violation" | "off_road"
    example_run_id: str           # the worst run in this cluster

@dataclass
class FailureReport:
    batch_id: str
    total_runs: int
    fail_runs: int
    fault_conditions: List[FaultCondition]  # ordered by failure_rate desc
    safe_region_description: str  # e.g. "Model is safe when NPC initial_x > 35m"
```

Use `sklearn.cluster.DBSCAN` — add `scikit-learn>=1.3.0` to pyproject.toml optional deps.

### API Endpoint

```
GET /api/runs/batch/{batch_id}/failure-report
Resp: FailureReport JSON
```

This is computed lazily on first request and cached in the DB.

### Frontend Display

In `DashboardPage.jsx` scenario drill-down view, add a "Failure Analysis" panel below the
score distribution. It shows each `FaultCondition` as a card with:

- The description in bold
- A horizontal bar showing failure rate (red fill)
- "See example run →" link that opens the SimulationViewer for `example_run_id`

### Acceptance Criteria

- [ ] A batch of 50 runs on LON-003 with `ConstantAction` model produces a `FailureReport`
- [ ] `fault_conditions` is non-empty and descriptions reference actual parameter names
- [ ] `example_run_id` links to a real run that is actually a FAIL
- [ ] `safe_region_description` is a valid string (even if generic)

---

## 2.3 — Adversarial Scenario Search

**Pulled from original P2.1 — this is the single biggest technical differentiator.**

The existing `AREP_IMPLEMENTATION_ROADMAP.md` section P2.1 contains the complete
technical specification. Follow it. Summary:

- CMA-ES optimiser searches the parameterization space to find the configuration that
  maximally violates safety properties
- `POST /api/search` → async search job → results with worst-case parameters
- The key customer value: "Here is the exact scenario that breaks your model"

**Why it matters for SaaS**: This feature is the reason a safety engineer pays $199/month
instead of running their own batch scripts. Nobody else offers this in a hosted, zero-setup
product.

Refer to `AREP_IMPLEMENTATION_ROADMAP.md § P2.1` for full implementation detail.

### Additional SaaS Wrapping (beyond original spec)

The adversarial search is a Pro-tier-only feature. Add a tier check in the API route:

```python
if org.plan not in ("pro", "enterprise"):
    raise HTTPException(402, "Adversarial search requires Pro or Enterprise plan")
```

Each adversarial search consumes `max_evals` run credits (same as running `max_evals`
individual simulations).

### Acceptance Criteria (same as P2.1 in original roadmap)

- [ ] CMA-ES finds a falsification (collision) for `ConstantAction` on LON-003 within 50 evals
- [ ] Search result includes `falsification_params` that, when re-run with that exact seed, reproduces the collision
- [ ] Pro-tier gate enforced (Free/Starter gets 402)
- [ ] Credits deducted = `max_evals` regardless of when falsification is found

---

## 2.4 — Model Comparison & Regression Reports

**Currently**: Runs belong to one model. There is no side-by-side comparison.  
**After this**: "Model v2.1 vs v2.0: safety improved by 0.08, compliance regressed by 0.03."

### Comparison API

```
POST /api/compare
Body: {
  model_a_id: str,
  model_b_id: str,
  scenario_ids: ["LON-003", "LAT-002", ...],  # or "all"
  runs_per_scenario: int,
  seed: int
}
Resp: { comparison_id: str }

GET /api/compare/{comparison_id}/results
Resp: {
  model_a: { name, version },
  model_b: { name, version },
  scenarios: [
    {
      scenario_id: str,
      a_composite: ScoreDistribution,
      b_composite: ScoreDistribution,
      delta: float,           # b - a, positive = b is better
      regression: bool,       # True if delta < -0.05
      winner: "a" | "b" | "tie"
    }
  ],
  overall_winner: "a" | "b" | "tie",
  regressions: [{ scenario_id, metric, delta }]
}
```

### Regression Detection Logic

A regression is flagged when:
`delta < -0.05` on composite score, OR
`delta < -0.10` on safety score specifically, OR
collision_rate increases by more than 0.01

Regressions trigger a warning badge in the dashboard and can optionally trigger a webhook
(used by CI/CD in Phase 3).

### Frontend: Comparison View

New dashboard section: **"Compare Models"**. Renders a side-by-side table with scenarios
as rows and metrics as columns. Delta cells coloured green (improvement) or red (regression).
An overall verdict badge at the top: "Model B is safer" / "Regression detected — do not deploy".

### PDF Report Generation

A comparison result can be exported as a PDF report suitable for presenting to a safety board
or regulatory reviewer.

**File to create**: `arep_implementation/arep/reporting/pdf_generator.py`

Use `weasyprint` to render an HTML template to PDF. The HTML template lives at
`arep_implementation/arep/reporting/templates/comparison_report.html`.

```
GET /api/compare/{comparison_id}/report.pdf
```

Add `weasyprint>=60.0` to pyproject.toml optional deps.

The PDF includes: executive summary, per-scenario score table, failure analysis highlights,
methodology section (scenario count, seeds, confidence intervals), ORION platform branding.

### Acceptance Criteria

- [ ] Comparison of `EmergencyBrake` vs `ConstantAction` on LON-003 correctly shows `EmergencyBrake` winning
- [ ] Regression flagged when a model with worse safety scores is model B
- [ ] PDF report downloads correctly and includes all sections
- [ ] Comparison costs `2 × runs_per_scenario × len(scenario_ids)` credits

---

## Phase 2 Exit Criteria

Before starting Phase 3, verify:

- [ ] A prospective customer demo shows: submit model → run adversarial search → view failure cluster → download comparison PDF — all in one session
- [ ] At least one external beta user has run their actual model (not a toy baseline) through the platform
- [ ] Statistical reports are reviewed by at least one person with a safety engineering background for sanity

---

---

# PHASE 3 — CI/CD Integration

**Duration**: ~1.5 months  
**Goal**: Make ORION a native part of the model development workflow. A model developer
pushes a new version, ORION automatically evaluates it, and the pipeline fails if safety
regresses. This is the feature that locks in enterprise customers.

**Why this wins deals**: Large AV companies spend millions building this internally. ORION
offers it as a hosted service. This is the "GitHub Actions for autonomous driving safety."

---

## 3.1 — Webhook System

**Foundation for everything else in this phase.**

```
POST /api/webhooks
Body: {
  url: str,               # customer's endpoint
  events: ["run.completed", "batch.completed", "regression.detected", "search.completed"],
  secret: str             # for HMAC signature verification
}

GET    /api/webhooks        # list
DELETE /api/webhooks/{id}   # remove
```

On each event, POST to the customer's URL with:

```json
{
  "event": "regression.detected",
  "timestamp": "2026-05-01T12:34:56Z",
  "org_id": "...",
  "data": { ... event-specific payload ... }
}
```

Sign with `HMAC-SHA256(secret, payload)` in `X-ORION-Signature` header. Retry 3× with
exponential backoff on failure. Log all deliveries in a `webhook_deliveries` table.

---

## 3.2 — GitHub Actions Integration

**File to create**: `orion-sdk/orion_sdk/github_action/action.yml`
(Published as a GitHub Action at `orioneval/evaluate-model@v1`)

```yaml
name: ORION Safety Evaluation
description: Evaluate your autonomous driving model against ORION safety scenarios

inputs:
  api_key:
    required: true
    description: ORION API key (store as a GitHub Secret)
  model_path:
    required: true
    description: Python import path to your ModelInterface class
  scenarios:
    required: false
    default: all
    description: Comma-separated scenario IDs or category names (LON,LAT,etc.)
  runs_per_scenario:
    required: false
    default: "10"
  pass_threshold:
    required: false
    default: "0.80"
  fail_on_regression:
    required: false
    default: "true"

outputs:
  composite_score:
    description: Overall composite safety score (0-1)
  passed:
    description: true if all scenarios passed the threshold
  report_url:
    description: URL to the full evaluation report in ORION dashboard

runs:
  using: docker
  image: docker://ghcr.io/orioneval/cli:latest
```

The Docker image runs `orion evaluate` CLI command which:

1. Packages the model from `model_path` using cloudpickle
2. Submits to `POST /api/models/upload`
3. Submits batch evaluation job
4. Polls until complete
5. Compares against previous run of the same scenario suite (regression check)
6. Writes `$GITHUB_OUTPUT` with results
7. Exits with code 0 (pass) or 1 (fail)

### Example Customer Workflow

```yaml
# .github/workflows/safety.yml
name: Safety Evaluation
on: [push, pull_request]

jobs:
  evaluate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - run: pip install -r requirements.txt
      - uses: orioneval/evaluate-model@v1
        with:
          api_key: ${{ secrets.ORION_API_KEY }}
          model_path: myproject.model.ADModel
          scenarios: LON,LAT,VRU
          runs_per_scenario: 20
          fail_on_regression: true
```

A red check block labeled "ORION Safety Evaluation" appears on every PR. Engineers cannot
merge if safety regresses. This is the product's viral loop — every customer's engineers
see ORION on every PR.

---

## 3.3 — GitLab CI Integration

Same pattern as GitHub Actions. Provide a GitLab CI component at
`gitlab.com/orioneval/evaluate-model`.

```yaml
# .gitlab-ci.yml
include:
  - component: gitlab.com/orioneval/evaluate-model@v1
    inputs:
      api_key: $ORION_API_KEY
      model_path: myproject.model.ADModel
```

---

## 3.4 — Model Versioning & History

When the same model name is submitted multiple times, ORION tracks versions
(e.g. `my-model` → v1, v2, v3). The dashboard shows a timeline chart of composite
score per version across the same scenario suite.

```
GET /api/models/{name}/history
Resp: [
  { version: "v1", submitted_at, composite_score, collision_rate, batch_id },
  { version: "v2", ... },
  ...
]
```

Regression tracking then compares vN vs vN-1 automatically and flags changes in the
dashboard and via webhook.

### Acceptance Criteria for Phase 3

- [ ] Pushing to a GitHub repo with the Action configured runs evaluation and fails the PR if threshold is missed
- [ ] Webhook fires within 30 seconds of a batch completing
- [ ] Model version history shows correct score trend across 3 submitted versions
- [ ] `fail_on_regression: true` fails the CI step even if absolute scores pass threshold

---

---

# PHASE 4 — Ecosystem Expansion

**Duration**: ~2.5 months  
**Goal**: Broaden what models can connect to ORION and what scenarios they can be tested
against. This is about removing reasons not to use ORION.

---

## 4.1 — HTTP Model Bridge (Non-Python Models)

Extend the Docker submission path to support any language/runtime that can expose an HTTP
server. Customer documentation provides adapters for:

- **C++** (common in production AV stacks)
- **ROS2** (see original roadmap P2.2 — implement the ZMQ bridge)
- **MATLAB/Simulink** (common in automotive OEMs — expose via MATLAB Production Server)

The ORION side is already built (HttpModelAdapter from Phase 1). This work is documentation,
example repos, and client adapters in each language.

---

## 4.2 — OpenDRIVE Map Support

**Pulled from original P2.4.** Allows customers to test their model on real-world road
geometry exported from HD map tools (Mobileye, HERE HD Maps, etc.) or CARLA's own maps.

This is a strong enterprise feature — "test on your actual operational domain, not a
synthetic road template."

Refer to `AREP_IMPLEMENTATION_ROADMAP.md § P2.4` for full implementation detail.

**SaaS addition**: customers can upload their own `.xodr` files to
`POST /api/maps/upload`. Maps are org-scoped (not shared between customers).

---

## 4.3 — Scenario Library Expansion (18 → 60)

**Pulled from original P3.4.** Expand to 60 scenarios following the existing taxonomy.

Refer to `AREP_IMPLEMENTATION_ROADMAP.md § P3.4` for the full target list.

**SaaS packaging**: scenarios are grouped into "test suites" that customers can subscribe
to as named packages:

- **Core Suite** (18 scenarios) — included in all paid plans
- **Intersection Suite** (10 INT scenarios) — included in Starter+
- **Vulnerable Road User Suite** (10 VRU scenarios) — included in Starter+
- **Emergency Suite** (10 EMG scenarios) — included in Pro+
- **Full Suite** (60 scenarios) — Enterprise

---

## 4.4 — OpenSCENARIO Import

**Pulled from original P3.1.** Allows customers to import their existing CARLA scenario
libraries (.osc files) directly into ORION.

This is the migration path for teams moving from CARLA. Make it as frictionless as possible.

Refer to `AREP_IMPLEMENTATION_ROADMAP.md § P3.1` for full implementation detail.

**New API endpoint**:

```
POST /api/scenarios/import/osc     # upload .osc → returns new scenario_id in org library
GET  /api/scenarios                # list: shared (built-in) + org-owned (imported)
```

---

---

# PHASE 5 — Visualization & Experience Polish

**Duration**: ~1.5 months  
**Goal**: The product should look and feel like a premium professional tool. Not a game.
Not a research prototype. The kind of thing you are proud to put in a sales demo or a
safety board presentation.

**Critical principle**: DO NOT pursue photorealism. Photorealism is CARLA's territory and
requires GPU rendering on the server. ORION's visualization should look like a high-end
professional instrument — think Bloomberg Terminal, not Unreal Engine.

---

## 5.1 — Visualization Overhaul (Information Density, Not Eye Candy)

**What the current viewer lacks**: trajectory history, TTC warning zones, NPC intent
indicators, slow-motion replay, fast-forward, scrubbing.

### Additions to `SimulationViewer.jsx`

**Trajectory traces**: render the last 3 seconds of ego and NPC paths as fading line
segments. Use a rolling buffer of positions in the hook, rendered as `Line` from
`@react-three/drei`.

**TTC warning zones**: render a coloured ellipse around the ego vehicle that scales with
speed and turns red when TTC < 2s (critical threshold). Uses a `CircleGeometry` with
opacity driven by the `monitor.metrics_current.safety_score`.

**NPC intent indicators**: small arrow above each NPC showing its current BT state
direction (braking = red down-arrow, accelerating = green up-arrow, cutting-in = yellow
diagonal arrow). These are HTML overlays using R3F's `<Html>` component.

**Playback controls**: the SimulationViewer should work in two modes — live (streaming)
and replay (from stored run data). Add a playback bar at the bottom:

- Play / Pause / Step-forward
- Speed: 0.1× / 0.5× / 1× / 2× / 5×
- Scrub timeline
- Jump-to-event buttons (each event in `run_events` is a clickable marker on the timeline)

**Replay mode**: `GET /api/runs/{run_id}/replay` returns all tick frames stored in DB,
delivered as a chunked JSON array. The hook plays them back at the selected speed.

### GLTF Asset Integration

**Pulled from original P3.5.** Replace box geometries with Kenney CC0 GLTF models.

Refer to `AREP_IMPLEMENTATION_ROADMAP.md § P3.5` for the full asset list and implementation.

**Key constraint from our direction**: No server-side rendering of any kind. All GLTF
models are served as static assets from the Vite server. The backend never touches them.

---

## 5.2 — Dashboard Polish

The dashboard should surface insights proactively, not just display data.

**Smart alerts panel** (top of dashboard):

- "⚠ LON-003: safety score dropped 12% since last run — possible regression"
- "✓ Your best-performing model is my-model-v3 (composite: 0.89)"
- "💡 You have 3 failing scenarios in the INT category — run adversarial search to find worst-case parameters"

Each alert is generated by a lightweight rules engine that runs after each batch completes.

**Onboarding flow** for new users:

- Step 1: Upload your first model (SDK or Docker) → guided UI
- Step 2: Run the Core Suite (18 scenarios, 10 runs each) → one-click
- Step 3: View your first safety report → interactive walkthrough

This flow should be skippable but present for every new org until they complete it.

---

## 5.3 — Documentation & Developer Experience

A great SaaS product has documentation that matches its product quality.

**docs.orion.run** (static site, built with Docusaurus or Astro):

- Getting Started (5 minutes to first evaluation)
- Python SDK reference (auto-generated from docstrings)
- API reference (auto-generated from FastAPI OpenAPI spec)
- Scenario library catalogue (each scenario with description, parameters, sample results)
- CI/CD integration guides (GitHub Actions, GitLab CI, Jenkins)
- "How ORION evaluates your model" — the methodology page that explains metrics,
  statistical rigor, and why this matters for safety validation
- Model submission guide (Python SDK, Docker, HTTP bridge)

---

---

# Risk Register

| Risk                                                      | Likelihood | Impact   | Mitigation                                                                        |
| --------------------------------------------------------- | ---------- | -------- | --------------------------------------------------------------------------------- |
| Customer model code executes malicious code in our infra  | Medium     | Critical | Subprocess isolation in Phase 1; Firecracker microVMs before enterprise launch    |
| CARLA releases a hosted SaaS version                      | Low        | High     | Accelerate CI/CD integration (Phase 3) — they cannot do this with Unreal Engine   |
| 2-person team runs out of runway before Phase 3           | Medium     | High     | Phase 1 must be revenue-generating; do not start Phase 4 without paying customers |
| Statistical methodology is challenged by a safety expert  | Low        | High     | Get an external review of confidence interval approach before enterprise sales    |
| Docker model submission creates infrastructure complexity | High       | Medium   | Ship Python SDK first; Docker in Phase 2; defer Firecracker until needed          |

---

# Timeline Summary (2-Person Team)

```
Month 1-3    Phase 1: SaaS Platform Foundation
               → First paying customers possible at end of this phase

Month 4-6    Phase 2: Evaluation Depth
               → Product becomes defensibly better than CARLA for evaluation use cases
               → Target: 10+ paying customers before starting Phase 3

Month 7-8    Phase 3: CI/CD Integration
               → Enterprise sales conversations become realistic
               → GitHub Action is the primary acquisition channel from here on

Month 9-11   Phase 4: Ecosystem Expansion
               → OpenDRIVE + 60 scenarios + OpenSCENARIO import
               → Removes "we can't use it because..." objections

Month 12     Phase 5: Visualization & Experience
               → Product is demo-worthy at an industry conference
               → Kenney GLTF assets, trajectory traces, replay, polish
```

**First revenue target**: End of month 3 (Phase 1 complete)  
**Competitive parity target**: End of month 6 (Phase 2 complete)  
**Enterprise-ready target**: End of month 8 (Phase 3 complete)

---

_This document governs product direction. The technical specification for simulation
components lives in `AREP_IMPLEMENTATION_ROADMAP.md`. When both documents address the
same feature, this document's priority ordering and SaaS framing take precedence._
