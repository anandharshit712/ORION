# ORION — Autonomous Robustness Evaluation Platform

Deterministic, statistically rigorous, CPU-only evaluation platform for autonomous-driving
**planning and control** models. Submit a model, pick a scenario suite, get back a safety
report: composite score, four sub-scores, pass/fail verdict — reproducible from a seed.

**CARLA is a simulator. ORION is a testing laboratory.** No GPU, no rendering, no install —
ORION answers "did my new model version regress on safety?" with confidence intervals.
Today it is **not** a perception testbed (no LiDAR/camera/radar — a structured sensor layer
is Phase 6, after the platform is complete) and **not** a certification tool. See
`docs/ROADMAP.md` § Honest Positioning.

Platform name = **ORION**. Python package = **`arep`** — imports are always `from arep.*`.

---

## Documentation

| Document | What it governs |
| --- | --- |
| [docs/ROADMAP.md](docs/ROADMAP.md) | **What to build next and how.** Phases 0–6, defect register (D-01…D-13), per-phase implementation specs, risks, timeline. |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | **Scenario taxonomy + 4-layer execution architecture** and the integration contract between them. |
| [docs/UI_DESIGN.md](docs/UI_DESIGN.md) | **All frontend visual work.** The "Mission Control" design system — tokens, type, components, theming, page specs. |
| [docs/PROJECT_IDEA.pdf](docs/PROJECT_IDEA.pdf) | The detailed product idea: exec summary, market, status, business model. Start here for context. |
| [docs/MARKET.md](docs/MARKET.md) | 19-competitor analysis, ratings, the four moats. |
| [docs/reference/](docs/reference/) | External research. Background only — constrains nothing. |
| [docs/archive/](docs/archive/) | Superseded originals. Historical; never cite as authority. |
| [CLAUDE.md](CLAUDE.md) | Conventions and hard rules enforced while writing code in this repo. |

---

## Repository Layout

```
ORION/
├── arep_implementation/     # Python backend (the `arep` package)
│   ├── arep/
│   │   ├── core/            # physics, state, collision, observation, action, TTC
│   │   ├── simulation/      # SimulationEngine, WorldManager, NPC behavior trees
│   │   ├── scenario/        # YAML parser, schema, parameterizer, validator
│   │   ├── models/          # ModelInterface + resolver, sandbox, HTTP/Docker adapters
│   │   ├── evaluation/      # safety, compliance, stability, reactivity, composite
│   │   ├── execution/       # EvaluationRunner (batch pipeline)
│   │   ├── statistics/      # StatisticalAggregator (Wilson / t-dist CIs)
│   │   ├── worker/          # Celery tasks + app (async batch queue)
│   │   ├── api/             # FastAPI app, routes, auth, WS, admin, billing
│   │   ├── database/        # SQLAlchemy models, repositories, connection
│   │   └── config/          # config loading + fail-fast secret/DB validation
│   ├── config/default.yaml  # master config — don't hardcode these values in code
│   └── tests/               # pytest suite
├── scenarios/               # 18-scenario library, v2 format: lon/ lat/ int/ vru/ emg/ mlt/
├── orion-frontend/          # React 18 + Vite 5 + R3F dashboard and live viewer
├── orion-sdk/               # `orion` CLI + OrionClient (model upload, runs, keys)
├── infrastructure/          # docker-compose, .env.example
├── design/                  # approved UI sample render
└── docs/                    # all project documentation
```

---

## Quickstart

```bash
# Backend (from arep_implementation/)
python3 -m venv venv && source venv/bin/activate
pip install -e ".[dev,api]"
python -m uvicorn arep.api.app:app --reload --port 8000

# Frontend (from orion-frontend/)
npm install && npm run dev

# Everything at once (from repo root)
./start.sh          # Linux/Mac
start.bat           # Windows cmd
./start.ps1         # Windows PowerShell (-NoReload to disable uvicorn reload)
```

### Run an evaluation

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

Custom models subclass `ModelInterface` (`predict(observation) -> Action`, `reset()`) and are
always invoked through `ModelWrapper`. Built-in models: `EmergencyBrake`, `ConstantAction`,
`SimpleLaneKeep`, `Random`.

### Tests and linting

```bash
pytest                                      # full suite
pytest tests/test_integration.py -v         # one file
pytest --cov=arep --cov-report=term-missing
black arep/ tests/ && ruff check arep/ tests/ && mypy arep/
```

---

## Status

Working: deterministic simulation core (bicycle + Pacejka physics, SAT collision, PCG64
seeding), four evaluation metrics with Wilson/t-distribution CIs, 18 scenarios across all six
categories, live WebSocket streaming to a 3D viewer, multi-tenancy with org-scoped API keys,
model submission (SDK + Docker), async batch queue on Celery + Redis, and a full React
dashboard.

**Current phase: 0 — Security & Score Integrity.** A production-readiness review found 13
defects, four of them critical; all revenue work is blocked until they are closed. 0.1
(secrets hardening) is done, 0.2 (model sandboxing) is next. Full register and ordering:
[docs/ROADMAP.md](docs/ROADMAP.md).

---

## Conventions That Bite

- **Determinism is non-negotiable**: `dt = 0.02` fixed, no `time.time()` / `datetime.now()` /
  `random` inside simulation code, all randomness through `RandomManager`.
- **Never mutate `WorldState` or `VehicleState` in place** — `.copy()` first.
- **Never reorder the simulation step**: validate → physics → NPCs → lights → collision →
  termination → time.
- **Never hardcode secrets or fall back to defaults** — go through `arep/config/validate.py`.
- **Frontend**: all HTTP through `src/services/api.js`, tokens only via `AuthContext`,
  tokens-only styling per `docs/UI_DESIGN.md`.

The complete list lives in [CLAUDE.md](CLAUDE.md) § 12.
