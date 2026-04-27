# ORION — File Structure Guideline
**Version**: 1.0  
**Date**: 2026-04-26  
**Companion to**: `ORION_SAAS_ROADMAP.md`

> Every file listed here has a reason for existing. Files not in this document should not
> be created without updating this document first. Each entry is annotated with its phase
> of introduction — `[EXISTS]` means it is already in the codebase.

---

## Legend

```
[EXISTS]     Already built and working
[EXTEND]     Existing file — new code is added to it in the specified phase
[P1]–[P5]   Phase when this file is first created
```

---

## Monorepo Root Layout

```
ORION/
├── arep_implementation/        # Python backend — FastAPI + simulation core
├── orion-frontend/             # React 18 + Vite + Three.js frontend
├── orion-sdk/                  # [P1] Customer-facing Python SDK (pip install orion-sdk)
├── infrastructure/             # [P1] Docker, docker-compose, nginx, future k8s
├── docs/                       # [P5] Docusaurus documentation site
├── scenarios/                  # [EXISTS] YAML scenario library
├── scripts/                    # [EXISTS] Developer utility scripts
├── .github/                    # [P1] GitHub Actions for CI; [P3] the product Action
├── CLAUDE.md                   # [EXISTS] Claude Code session config
├── ORION_SAAS_ROADMAP.md       # [EXISTS] Product roadmap
├── ORION_FILE_STRUCTURE.md     # [EXISTS] This file
├── ORION_SCENARIO_TAXONOMY.md  # [EXISTS] Scenario naming + taxonomy rules
├── AREP_IMPLEMENTATION_ROADMAP.md  # [EXISTS] Technical simulation roadmap
├── README.md                   # [EXISTS]
├── start.sh                    # [EXISTS] Linux/Mac dev startup
├── start.bat                   # [EXISTS] Windows dev startup
└── start.ps1                   # [EXISTS] PowerShell dev startup
```

**Rule**: Never put application code in the monorepo root. Root is for launcher scripts,
documentation, and configuration only.

---

---

## 1. Backend — `arep_implementation/`

```
arep_implementation/
├── arep/                       # The Python package (import as "from arep.*")
│   └── ... (see full tree below)
├── config/
│   └── default.yaml            # [EXISTS] Master config — never hardcode these values
├── scenarios/
│   └── basic/                  # [EXISTS] v1 format scenarios for unit tests only
├── tests/                      # [EXISTS] pytest test suite
│   ├── __init__.py
│   ├── test_integration.py     # [EXISTS]
│   ├── test_enhanced_physics.py # [EXISTS]
│   ├── test_ws_smoke.py        # [EXISTS]
│   ├── test_multitenancy.py    # [P1] Org isolation tests
│   ├── test_model_submission.py # [P1] SDK + Docker submission
│   ├── test_billing.py         # [P1] Credit deduction + Stripe webhook
│   ├── test_road_topology.py   # [P1] RoadGraph + templates
│   ├── test_failure_clustering.py # [P2]
│   ├── test_adversarial_search.py # [P2]
│   └── fixtures/               # [P4] Test fixture files (.xodr maps, .osc scenarios)
│       ├── TownSimple.xodr
│       └── CutIn.osc
├── scripts/
│   └── ws_smoke.py             # [EXISTS] End-to-end WebSocket smoke test
├── pyproject.toml              # [EXISTS][EXTEND] Add new optional dep groups per phase
├── alembic.ini                 # [P1] Alembic config for DB migrations
└── arep.egg-info/              # Auto-generated, do not edit
```

---

### 1.1 `arep/api/` — FastAPI Application

Owns all HTTP and WebSocket endpoints. No business logic here — routes delegate to
domain modules. Routes validate input, check auth/org, and return responses.

```
arep/api/
├── __init__.py
├── app.py              [EXISTS][EXTEND]  FastAPI app init; mount all routers
│                                         [P1] add org-scoped middleware
├── auth.py             [EXISTS][EXTEND]  JWT auth; [P1] add API key auth + org_id in token
├── routes.py           [EXISTS][EXTEND]  Main router; [P1] extend with models/batch/billing
├── schemas.py          [EXISTS][EXTEND]  Pydantic models; extend as new endpoints are added
├── sim_registry.py     [EXISTS]          In-memory registry of live SimulationEngine runs
├── ws.py               [EXISTS]          WebSocket endpoint for live simulation streaming
├── middleware.py       [P1]              Org-scoped auth middleware (JWT + API key → org_id)
├── model_store.py      [P1]              Upload/fetch model artefacts from object storage
└── billing.py          [P1]              Stripe checkout session + webhook handler
```

**Rule**: All routes are prefixed `/api`. Auth routes are `/api/auth/*`. Live-run routes
are `/api/runs/*`. All other routers follow the same pattern. Never add a route without
a Pydantic request/response schema in `schemas.py`.

---

### 1.2 `arep/core/` — Physics, State & Road

The immutable foundation. Nothing in this package has side effects. Every function
takes inputs and returns outputs — no mutation, no I/O, no randomness outside
`RandomManager`.

```
arep/core/
├── __init__.py
├── action.py           [EXISTS]   Action dataclass (steering, throttle, brake)
├── collision.py        [EXISTS]   OBB collision detection (SAT algorithm)
├── observation.py      [EXISTS]   Observation dataclass (what the model sees)
├── physics.py          [EXISTS]   Bicycle kinematic + Pacejka dynamic tire models
├── random_manager.py   [EXISTS]   Seeded RNG — ALL randomness flows through here
├── state.py            [EXISTS][EXTEND]  WorldState + VehicleState
│                                  [P1] add road_graph: Optional[RoadGraph] field
├── ttc.py              [EXISTS]   Time-to-collision calculations
├── road.py             [P1]       RoadGraph, RoadSegment, Junction dataclasses
└── road_templates.py   [P1]       Factory functions: highway_straight, t_junction,
                                   four_way_intersection, roundabout, highway_onramp
```

**Rule**: Never import from `api`, `database`, `worker`, or `simulation` in this package.
`core` has zero upward dependencies — it is the leaf of the dependency graph.

---

### 1.3 `arep/simulation/` — Simulation Engine & NPC Behavior

Owns the simulation loop and all world dynamics. Reads from `core`, writes new
`WorldState` objects (never mutates existing ones).

```
arep/simulation/
├── __init__.py
├── engine.py           [EXISTS][EXTEND]  SimulationEngine; [P1] extend run_async
│                                          to accept RoadGraph; [P2] performance tuning
├── npc_bt.py           [EXISTS][EXTEND]  NPC behavior trees; [P1] add OncomingDriftBT,
│                                          RedLightRunnerBT, ErraticCyclistBT,
│                                          WrongWayDriverBT, TireBlowoutBT; [P5] AnimalBT
├── world.py            [EXISTS]          WorldManager — spawns and steps all entities
├── termination.py      [EXISTS]          Termination condition checks
└── time_manager.py     [EXISTS]          Fixed 50Hz timestep management
```

**Rule**: `dt = 0.02` always. Never derive `dt` from wall time. Never import `time` or
`datetime` for simulation timing.

---

### 1.4 `arep/scenario/` — YAML Scenario System

Parses YAML files into `ScenarioDefinition` objects. The `ScenarioParameterizer`
creates a per-run modified copy for each seed. Nothing here runs simulations.

```
arep/scenario/
├── __init__.py
├── schema.py           [EXISTS][EXTEND]  ScenarioDefinition dataclass
│                                          [P1] add road_graph field
│                                          [P2] add procedural parameterization support
├── parser.py           [EXISTS][EXTEND]  YAML → ScenarioDefinition
│                                          [P1] handle road.template key
│                                          [P4] handle road.source: xodr
├── parameterizer.py    [EXISTS]          Applies seed-based overrides to a scenario
├── validator.py        [EXISTS]          Schema validation for scenario YAML
├── executor.py         [EXISTS][EXTEND]  Wires ScenarioDefinition into WorldState
│                                          [P1] pass road_graph into WorldState
├── events.py           [EXISTS]          Scripted event parsing and dispatch
├── osc_importer.py     [P4]              OpenSCENARIO 2.0 .osc → ScenarioDefinition
└── osc_exporter.py     [P4]              ScenarioDefinition → OpenSCENARIO 2.0 .osc
```

---

### 1.5 `arep/evaluation/` — Safety Metrics

Four metric modules plus a composite combiner. These run after a simulation completes,
not during. They are pure functions over a list of `WorldState` snapshots.

```
arep/evaluation/
├── __init__.py
├── safety.py           [EXISTS]   SafetyMetrics — collision penalty + TTC scoring
├── compliance.py       [EXISTS]   ComplianceMetrics — speed limit + lane keeping
├── stability.py        [EXISTS]   StabilityMetrics — control smoothness
├── reactivity.py       [EXISTS]   ReactivityMetrics — threat response latency
├── composite.py        [EXISTS]   CompositeEvaluator — weighted combination of all four
└── collector.py        [EXISTS]   Collects per-tick data during a run for post-run eval
```

**Rule**: Metric weights are frozen. Never change `COLLISION_WEIGHT = 0.50`,
`MIN_TTC_WEIGHT = 0.30`, `CRITICAL_TTC_WEIGHT = 0.20` without updating the
specification document and all existing baselines first.

---

### 1.6 `arep/execution/` — Batch Runner

Orchestrates running N simulations for a given scenario + model + seed range.
In Phase 1 this gets wired to the job queue.

```
arep/execution/
├── __init__.py
└── runner.py           [EXISTS][EXTEND]  EvaluationRunner for batch runs
                                           [P1] add headless path (no WebSocket)
                                           [P1] write results to DB after each run
                                           [P1] deduct org credits on completion
```

---

### 1.7 `arep/statistics/` — Statistical Aggregation

Takes a list of per-run metrics and produces aggregate statistics. Extended in Phase 2
to include confidence intervals and distributions.

```
arep/statistics/
├── __init__.py
└── aggregator.py       [EXISTS][EXTEND]  StatisticalAggregator
                                           [P2] add ScoreDistribution dataclass
                                           [P2] add CI calculations (scipy.stats.t)
                                           [P2] add Wilson interval for collision_rate
```

---

### 1.8 `arep/analysis/` — Failure Analysis [Phase 2]

Post-run analysis that runs over completed batch data. Does not touch the simulation
engine — it only reads from the database.

```
arep/analysis/
├── __init__.py                 [P2]
├── failure_clustering.py       [P2]   DBSCAN clustering over failed run parameters
│                                       → FailureReport with FaultCondition objects
└── regression_detector.py      [P2]   Compare model vN vs vN-1 across same scenarios
                                        → flag regressions > 5% composite, > 10% safety
```

---

### 1.9 `arep/search/` — Adversarial Scenario Search [Phase 2]

CMA-ES optimiser that searches the scenario parameterization space to find the
configuration that maximally violates safety properties.

```
arep/search/
├── __init__.py                 [P2]
├── space.py                    [P2]   SearchSpace — extracts {min,max} from YAML
├── objective.py                [P2]   ObjectiveFunction — runs one simulation, returns fitness
└── optimizer.py                [P2]   CMAESOptimizer + RandomSearchOptimizer
```

---

### 1.10 `arep/models/` — Model Interface & Adapters

The `ModelInterface` ABC and all adapters that translate external models into it.

```
arep/models/
├── __init__.py
├── interface.py        [EXISTS]   ModelInterface ABC (predict + reset)
├── local_executor.py   [EXISTS]   Scaffold — to be completed as part of RL work
├── http_adapter.py     [P1]       HttpModelAdapter — calls POST /predict + POST /reset
│                                   on a customer's Docker container
├── sandbox.py          [P1]       SubprocessModelRunner — runs cloudpickle'd model
│                                   in isolated subprocess with resource limits
└── examples/
    ├── __init__.py     [EXISTS]
    └── example_models.py [EXISTS] ConstantAction, EmergencyBrake, SimpleLaneKeep, Random
```

---

### 1.11 `arep/worker/` — Celery Job Queue [Phase 1]

Celery workers consume evaluation tasks from Redis and run them headlessly.
Completely separate from the API server process.

```
arep/worker/
├── __init__.py                 [P1]
├── celery_app.py               [P1]   Celery application init — broker = Redis
└── tasks.py                    [P1]   run_single_simulation task:
                                        fetch model → deserialise/spin-up container
                                        → run simulation → write results → update status
```

---

### 1.12 `arep/reporting/` — PDF & HTML Report Generation [Phase 2]

Generates downloadable evaluation reports using weasyprint (HTML → PDF).

```
arep/reporting/
├── __init__.py                 [P2]
├── pdf_generator.py            [P2]   Renders HTML templates to PDF via weasyprint
└── templates/
    ├── base.html               [P2]   ORION branding, common layout
    ├── batch_report.html       [P2]   Single batch: score distributions, events
    └── comparison_report.html  [P2]   Model A vs B: delta table, regressions, verdict
```

---

### 1.13 `arep/maps/` — OpenDRIVE Map Support [Phase 4]

Parses industry-standard `.xodr` files into AREP `RoadGraph` objects.

```
arep/maps/
├── __init__.py                 [P4]
└── xodr_parser.py              [P4]   OpenDRIVEParser: .xodr → RoadGraph
                                        Supported: straight/arc/cubic roads,
                                        laneSections, junctions, signals
```

---

### 1.14 `arep/cli/` — CI/CD Command-Line Interface [Phase 3]

Entry point for the Docker-based CI evaluation image. Takes a model, runs the full
scenario suite, outputs a JSON/HTML report, exits 0 (pass) or 1 (fail).

```
arep/cli/
├── __init__.py                 [P3]
└── run_suite.py                [P3]   python -m arep.cli.run_suite
                                        --scenarios all|LON|LAT|...
                                        --runs-per-scenario 10
                                        --pass-threshold 0.80
                                        --model <import-path>
                                        --output-dir ./results/
                                        --format json|html
```

---

### 1.15 `arep/database/` — SQLAlchemy Models & Repositories

All DB access goes through repository classes. No raw sessions anywhere.

```
arep/database/
├── __init__.py
├── connection.py       [EXISTS]         session_scope() context manager
├── models.py           [EXISTS][EXTEND] SQLAlchemy ORM models
│                                         [P1] add: organisations, api_keys
│                                         [P1] extend: users (add org_id, role)
│                                         [P1] add: models (submitted models)
│                                         [P1] add: webhook_deliveries
│                                         [P2] add: comparisons, failure_reports
├── repository.py       [EXISTS][EXTEND] Repository classes
│                                         [P1] add OrgRepository, ApiKeyRepository,
│                                              ModelRepository, BillingRepository
│                                         [P2] add ComparisonRepository,
│                                              FailureReportRepository
└── migrations/         [P1]             Alembic migration scripts
    ├── env.py
    ├── script.py.mako
    └── versions/
        ├── 001_initial_schema.py
        ├── 002_add_organisations.py
        ├── 003_add_api_keys.py
        ├── 004_add_models_table.py
        └── 005_add_webhook_deliveries.py
```

**Rule**: Never use `db.execute()` with raw SQL. All queries go through SQLAlchemy ORM
in repository classes. Never instantiate `Session` directly — always use `session_scope()`.

---

### 1.16 `arep/utils/` — Shared Utilities

```
arep/utils/
├── __init__.py
├── exceptions.py       [EXISTS]   Custom exception hierarchy
├── hashing.py          [EXISTS]   Deterministic hashing utilities
├── logging_config.py   [EXISTS]   Structured logging setup
└── validators.py       [EXISTS]   Input validation helpers
```

---

### 1.17 `arep/config/` & `arep/visualization/`

```
arep/config/            [EXISTS]   get_config() → SimulationConfig from default.yaml
arep/visualization/     [EXISTS]   Legacy Plotly dashboard — kept but not extended
                                   Will be removed when frontend replaces all views
```

---

---

## 2. Frontend — `orion-frontend/`

React 18, Vite 5, React Router 6. No TypeScript. CSS co-located with each component.
All HTTP calls go through `src/services/api.js`. Auth lives in `AuthContext`.

```
orion-frontend/
├── src/                # Application source (see full tree below)
├── public/
│   ├── models/         [P5]   GLTF model files (Kenney CC0 assets, checked in)
│   │   ├── car.glb
│   │   ├── truck.glb
│   │   ├── motorcycle.glb
│   │   ├── character-male.glb
│   │   ├── character-female.glb
│   │   ├── tree_default.glb
│   │   ├── streetLight.glb
│   │   ├── dog.glb
│   │   └── deer.glb
│   └── textures/       [P5]   Road surface textures
│       └── asphalt_diffuse.jpg
├── index.html          [EXISTS]
├── vite.config.js      [EXISTS]   Proxy: /api → localhost:8000, /ws → localhost:8000
└── package.json        [EXISTS]
```

---

### 2.1 `src/services/` — API Layer

**Rule**: All HTTP calls go through `api.js`. Never use `fetch()` directly in a component.

```
src/services/
└── api.js              [EXISTS][EXTEND]
                         [EXISTS] auth, runs, scenarios, models (built-in)
                         [P1]     addMethod: submitModel, getBatchStatus, getCredits,
                                  createCheckoutSession, getApiKeys, createApiKey
                         [P2]     addMethod: getFailureReport, startSearch, getComparison
                         [P3]     addMethod: getWebhooks, createWebhook, getModelHistory
```

---

### 2.2 `src/context/` — React Context

```
src/context/
├── AuthContext.jsx      [EXISTS][EXTEND]
│                                [P1] add org_id, role to context value
│                                [P1] add logout-on-401 behaviour
└── OrgContext.jsx       [P1]    Org plan, run_credits, refresh credits after each run
```

---

### 2.3 `src/hooks/` — Custom Hooks

```
src/hooks/
├── useSimulationStream.js  [EXISTS]   WebSocket hook (live simulation)
├── useBatchStatus.js       [P1]       Polls GET /api/runs/batch/{id}/status every 2s
│                                       Returns { total, complete, failed, running }
│                                       Auto-stops polling when complete + failed = total
└── useReplayStream.js      [P5]       Fetches stored tick frames for replay mode
                                        Exposes playback controls (speed, scrub, pause)
```

---

### 2.4 `src/pages/` — Top-Level Route Components

One file pair (`.jsx` + `.css`) per route. Pages own layout and data-fetching.
Components own rendering logic.

```
src/pages/
├── LandingPage.jsx         [EXISTS]
├── LoginPage.jsx           [EXISTS]
├── SignupPage.jsx          [EXISTS]
├── DashboardPage.jsx       [EXISTS][EXTEND]
│                                    [P1] add runs list, credits display, refresh button
│                                    [P2] add ScoreDistribution cards, SmartAlerts panel
├── DashboardPage.css       [EXISTS]
├── ModelsPage.jsx          [P1]     List org models + upload new model (SDK or Docker)
├── ModelsPage.css          [P1]
├── RunPage.jsx             [P1]     Single run detail: scores, event log, link to viewer
├── RunPage.css             [P1]
├── BatchPage.jsx           [P1]     Batch detail: progress, per-run table, aggregate scores
├── BatchPage.css           [P1]
├── ComparePage.jsx         [P2]     Model A vs B comparison table + regression badges
├── ComparePage.css         [P2]
├── SearchPage.jsx          [P2]     Adversarial search: launch + results (Pro tier only)
├── SearchPage.css          [P2]
├── SettingsPage.jsx        [P1]     Org settings, API key management, team members
├── SettingsPage.css        [P1]
├── BillingPage.jsx         [P1]     Current plan, usage, upgrade/downgrade via Stripe
└── BillingPage.css         [P1]
```

---

### 2.5 `src/components/` — Reusable UI Components

```
src/components/
│
├── auth/               [EXISTS]
│   ├── LoginForm.jsx
│   ├── SignupForm.jsx
│   └── AuthForms.css
│
├── common/             [EXISTS][EXTEND]
│   ├── Navbar.jsx      [EXISTS]
│   ├── Navbar.css      [EXISTS]
│   ├── Sidebar.jsx     [P1]     Dashboard sidebar with section nav + credits display
│   ├── Sidebar.css     [P1]
│   └── AlertBanner.jsx [P2]     Dismissible alert for regression warnings
│
├── landing/            [EXISTS]
│   ├── Hero.jsx + Hero.css
│   ├── FeatureCards.jsx + FeatureCards.css
│   ├── StatsSection.jsx + StatsSection.css
│   └── Footer.jsx + Footer.css
│
├── simulation/         [EXISTS][EXTEND]
│   ├── SimulationViewer.jsx    [EXISTS]   R3F scene (road, ego, NPCs, HUD)
│   ├── SimulationViewer.css    [EXISTS]
│   ├── PlaybackControls.jsx    [P5]       Play/pause/speed/scrub timeline bar
│   ├── PlaybackControls.css    [P5]
│   ├── TrajectoryTrace.jsx     [P5]       Rolling 3s position history as fading lines
│   ├── TTCWarningZone.jsx      [P5]       Coloured ellipse around ego, red when TTC < 2s
│   └── NPCIntentOverlay.jsx    [P5]       HTML overlay arrows showing NPC BT state
│
├── dashboard/          [P1]
│   ├── ScoreCard.jsx           [P1]   Single metric score + spark line
│   ├── ScoreCard.css           [P1]
│   ├── ScoreDistribution.jsx   [P2]   Inline spark-histogram (10 bins, 120×40px)
│   ├── RegressionChart.jsx     [P2]   Line chart: composite score over model versions
│   ├── RegressionChart.css     [P2]
│   ├── FailureClusterPanel.jsx [P2]   FaultCondition cards with failure rate bars
│   ├── FailureClusterPanel.css [P2]
│   ├── ComparisonTable.jsx     [P2]   Side-by-side metric table (green=improve, red=regress)
│   ├── ComparisonTable.css     [P2]
│   └── SmartAlerts.jsx         [P2]   Proactive insight cards (regression, suggestions)
│
├── models/             [P1]
│   ├── ModelUploadForm.jsx     [P1]   SDK upload or Docker image registration
│   ├── ModelUploadForm.css     [P1]
│   └── ModelCard.jsx           [P1]   Model name, version, status, last run score
│
└── billing/            [P1]
    ├── PlanCard.jsx            [P1]   Plan name, price, features, upgrade CTA
    ├── PlanCard.css            [P1]
    └── UsageBar.jsx            [P1]   Credits used / total with colour gradient
```

---

### 2.6 `src/utils/` — Frontend Utilities [Phase 1]

```
src/utils/
├── formatting.js       [P1]   formatScore(n), formatDate(ts), formatCredits(n)
└── constants.js        [P1]   PLAN_TIERS, SCORE_THRESHOLDS, METRIC_WEIGHTS
                                These mirror the backend constants — keep in sync.
```

---

---

## 3. Customer SDK — `orion-sdk/`  [Phase 1]

Separate Python package published to PyPI as `orion-sdk`. Customers install it to
submit models and interact with the ORION API from their own code and CI pipelines.

**This package must never import from `arep.*`** — it is a standalone client that
mirrors the relevant interfaces.

```
orion-sdk/
├── orion_sdk/
│   ├── __init__.py             [P1]   Exports: ModelInterface, Action, Observation,
│   │                                   OrionClient, upload_model
│   ├── interface.py            [P1]   ModelInterface ABC (mirrors arep.models.interface)
│   │                                   Action + Observation dataclasses
│   │                                   These must stay in sync with arep counterparts.
│   ├── client.py               [P1]   OrionClient(api_key, base_url)
│   │                                   .submit_model(model, name, version)
│   │                                   .run_batch(model_id, scenario_ids, runs, seed)
│   │                                   .get_batch_results(batch_id)
│   │                                   .compare_models(model_a_id, model_b_id, ...)
│   ├── uploader.py             [P1]   upload_model() — cloudpickle + multipart POST
│   └── cli.py                  [P1]   `orion` CLI entry point
│                                       orion models list
│                                       orion models upload --name x --path y.MyModel
│                                       orion runs batch --model x --scenarios LON
│                                       orion runs status --batch-id abc123
│
├── examples/
│   ├── simple_model.py         [P1]   Minimal ModelInterface example (< 30 lines)
│   └── docker_model/           [P1]   Docker submission example
│       ├── model_server.py             FastAPI server: POST /predict + POST /reset
│       └── Dockerfile                  Python + dependencies, EXPOSE 8080
│
├── pyproject.toml              [P1]   name = "orion-sdk"; minimal deps (requests, click)
└── README.md                   [P1]   Quickstart guide
```

---

---

## 4. Infrastructure — `infrastructure/` [Phase 1]

Everything needed to run ORION in production. All Docker images are built from here.

```
infrastructure/
│
├── docker/
│   ├── Dockerfile.api          [P1]   FastAPI server image
│   │                                   Base: python:3.11-slim
│   │                                   Installs: arep[api]
│   │                                   CMD: python -m uvicorn arep.api.app:app
│   │
│   ├── Dockerfile.worker       [P1]   Celery worker image
│   │                                   Same base as api; additionally installs Docker CLI
│   │                                   for spinning up customer model containers
│   │                                   CMD: celery -A arep.worker.celery_app worker
│   │
│   └── Dockerfile.cli          [P3]   CI/CD evaluation image (used by GitHub Action)
│                                       Base: python:3.11-slim
│                                       Installs: arep[api] + orion-sdk
│                                       ENTRYPOINT: python -m arep.cli.run_suite
│
├── docker-compose.yml          [P1]   Local development: all services in one command
│                                       Services: api, worker, redis, postgres, flower
│
├── docker-compose.prod.yml     [P1]   Production overrides
│                                       (env vars from secrets, no --reload, replicas)
│
└── nginx/
    └── nginx.conf              [P1]   Reverse proxy
                                        / → orion-frontend (static)
                                        /api → api:8000
                                        /ws → api:8000 (WebSocket upgrade headers)
```

**docker-compose.yml services:**

| Service | Image | Port | Purpose |
|---|---|---|---|
| `api` | Dockerfile.api | 8000 | FastAPI backend |
| `worker` | Dockerfile.worker | — | Celery evaluation worker |
| `redis` | redis:7-alpine | 6379 | Celery broker + result backend |
| `postgres` | postgres:15-alpine | 5432 | Primary database |
| `flower` | mher/flower | 5555 | Celery monitoring UI (dev only) |
| `frontend` | node:20-alpine | 5173 | Vite dev server (dev only) |

---

---

## 5. GitHub Actions — `.github/` [Phase 1 + Phase 3]

```
.github/
│
├── workflows/
│   ├── test.yml                [P1]   Run pytest on every push to any branch
│   │                                   Matrix: Python 3.10, 3.11
│   │                                   Installs: arep[dev,api]
│   │                                   Runs: pytest --tb=short
│   │
│   ├── lint.yml                [P1]   black --check + ruff check + mypy
│   │                                   Fails PR if any linter fails
│   │
│   ├── docker-build.yml        [P1]   Build all three Docker images on push to main
│   │                                   Does not push to registry (just verifies buildable)
│   │
│   └── self-eval.yml           [P2]   ORION evaluates ORION's own built-in models
│                                       Runs EmergencyBrake on LON-003 (must PASS)
│                                       Runs ConstantAction on LON-003 (must FAIL)
│                                       Regression gate: EmergencyBrake composite >= 0.80
│
└── actions/
    └── evaluate-model/         [P3]   The product GitHub Action
        ├── action.yml                  Action definition (inputs, outputs, runs)
        └── entrypoint.sh               Shell script: calls orion CLI, writes GITHUB_OUTPUT
```

---

---

## 6. Scenario Library — `scenarios/`

Already well-structured. Rules are unchanged from `ORION_SCENARIO_TAXONOMY.md`.

```
scenarios/
├── lon/    LON-001 through LON-010   [EXISTS: 4] [P1: upgrade to v2] [P4: add to 10]
├── lat/    LAT-001 through LAT-010   [EXISTS: 3] [P1: upgrade to v2] [P4: add to 10]
├── int/    INT-001 through INT-010   [EXISTS: 3] [P1: upgrade to v2] [P4: add to 10]
│                                      Requires road topology (P1.5) to execute
├── vru/    VRU-001 through VRU-010   [EXISTS: 3] [P1: upgrade to v2] [P4: add to 10]
├── emg/    EMG-001 through EMG-010   [EXISTS: 3] [P1: upgrade to v2] [P4: add to 10]
└── mlt/    MLT-001 through MLT-010   [EXISTS: 2] [P1: upgrade to v2] [P4: add to 10]
```

**Naming rule**: `[CATEGORY]-[SEQ3]_description_snake_case.yaml`  
**Version rule**: All new and upgraded scenarios must have `version: "2.0"` and a
`parameterization:` block.  
**Seed rule**: Each scenario has a unique `master_seed`. No two scenarios share a seed.  
**One-behaviour rule**: One scenario = one behavioural requirement. Weather/friction
variants go in `parameterization:`, not as new files.

---

---

## 7. Documentation Site — `docs/` [Phase 5]

Static site built with Docusaurus, deployed at `docs.orion.run`.

```
docs/
├── docusaurus.config.js
├── package.json
├── docs/
│   ├── getting-started/
│   │   ├── quickstart.md       5-minute guide: install SDK, submit model, view report
│   │   └── first-evaluation.md Step-by-step with screenshots
│   │
│   ├── sdk/
│   │   ├── python-sdk.md       Full ModelInterface API reference
│   │   ├── docker-submission.md Guide for containerised models
│   │   └── cli-reference.md    `orion` CLI commands
│   │
│   ├── api/
│   │   └── reference.md        Auto-generated from FastAPI OpenAPI spec
│   │
│   ├── scenarios/
│   │   ├── overview.md         Taxonomy explanation + naming conventions
│   │   ├── lon.md              All LON scenarios with parameters + sample results
│   │   ├── lat.md
│   │   ├── int.md
│   │   ├── vru.md
│   │   ├── emg.md
│   │   └── mlt.md
│   │
│   ├── integrations/
│   │   ├── github-actions.md   Full GitHub Actions integration guide
│   │   ├── gitlab-ci.md        GitLab CI integration guide
│   │   └── webhooks.md         Webhook event reference
│   │
│   └── methodology/
│       ├── how-evaluation-works.md  The most important page — metrics, CI, statistical rigor
│       └── adversarial-search.md   CMA-ES search explanation for non-ML engineers
│
└── static/
    └── img/
        ├── logo.svg
        └── screenshots/        Dashboard, SimulationViewer, comparison report
```

---

---

## 8. Naming Conventions

### Python files

| Pattern | Rule |
|---|---|
| `snake_case.py` | All Python files |
| `test_<module>.py` | Test files mirror the module they test |
| `__init__.py` | Every package directory must have one |
| No `utils.py` at package root | Put utils in `arep/utils/` only |

### React files

| Pattern | Rule |
|---|---|
| `PascalCase.jsx` | All React components |
| `PascalCase.css` | Co-located with its component, same name |
| `camelCase.js` | Non-component JS (hooks, services, utils) |
| No `index.js` barrel files | Import the actual file path |

### Database tables

| Pattern | Rule |
|---|---|
| `snake_case` plural | Table names (e.g. `run_metrics`, `organisations`) |
| `id` | Primary key, UUID type |
| `org_id` | Foreign key to `organisations` in all resource tables |
| `created_at`, `updated_at` | Timestamp columns, always present on entity tables |

### API routes

| Pattern | Rule |
|---|---|
| `/api/<resource>` | All routes prefixed `/api` |
| `POST /api/<resource>` | Create |
| `GET /api/<resource>` | List |
| `GET /api/<resource>/{id}` | Get one |
| `DELETE /api/<resource>/{id}` | Delete |
| `/api/<resource>/{id}/<sub-resource>` | Nested resources |

---

## 9. Hard Rules — What Never Goes Where

| Rule | Reason |
|---|---|
| No business logic in `api/routes.py` | Routes validate and delegate; logic lives in domain modules |
| No DB calls in `core/`, `simulation/`, `evaluation/` | These are pure computation modules |
| No `fetch()` in React components | All HTTP through `src/services/api.js` |
| No simulation timing from wall clock | `dt = 0.02` always, no `time.time()` |
| No `random` module | All randomness through `RandomManager` |
| No mutating `WorldState` in place | Always `.copy()` first |
| No hardcoded config values | Everything from `config/default.yaml` or env vars |
| No JWT in `localStorage` | Managed by `AuthContext` only |
| No raw `Session` in DB code | Always via `session_scope()` |
| No new scenario for a weather variant | Add to `parameterization:` block |
| No importing `arep.*` from `orion-sdk` | SDK is a standalone client package |
| No storing API key plaintext in DB | Store only the SHA-256 hash |

---

_This document must be updated whenever a new file is created, an existing file's
responsibility changes, or a module is moved. Keep it accurate — it is the map
new contributors (and future Claude sessions) use to orient themselves._
