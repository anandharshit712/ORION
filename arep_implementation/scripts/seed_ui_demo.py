"""
Seed a throwaway database so the UI walkthrough has something to render.

Every section is driven by a real endpoint, so an empty database would produce
eight screenshots of the empty state — technically correct and useless for
looking at the thing. This writes rows directly rather than driving the API:
the point here is the UI, and a batch through the real queue needs a broker.

Deliberately includes the states that are easy to get wrong visually:
  - a run that collided and one that did not, so PASS and FAIL chips both show;
  - a run still going, which must render "—" rather than 0.0;
  - a revoked API key beside a live one;
  - a comparison that found a regression, since that is the interesting report;
  - a completed search that falsified the model, with real parameter sets.
"""

from __future__ import annotations

import datetime
import json
import os
import sys

# The package root, two levels up from scripts/.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DB_PATH = sys.argv[1] if len(sys.argv) > 1 else "ui_demo.db"
os.environ["ORION_DATABASE_URL"] = f"sqlite:///{DB_PATH}"
os.environ.setdefault("ORION_ENV", "dev")

from arep.database import connection as conn  # noqa: E402

conn._engine = None
conn._SessionFactory = None
conn.init_database(url=f"sqlite:///{DB_PATH}")

from arep.api.auth import hash_password  # noqa: E402
from arep.database.models import (  # noqa: E402
    ApiKeyRecord,
    BatchJobRecord,
    ComparisonJobRecord,
    ModelRecord,
    OrganisationRecord,
    RunRecord,
    SearchJobRecord,
    UserRecord,
)

EMAIL = "demo@orion.test"
PASSWORD = "orion-demo-1234"
NOW = datetime.datetime.utcnow()

SCENARIO = "../scenarios/lon/LON-003_emergency_stop.yaml"


def main() -> None:
    with conn.session_scope() as db:
        org = OrganisationRecord(
            id="org-ui-demo",
            name="Beamhash Autonomy",
            slug="beamhash",
            plan="pro",
            run_credits=2450,
            created_at=NOW,
        )
        db.add(org)

        db.add(
            UserRecord(
                org_id=org.id,
                role="owner",
                email=EMAIL,
                username="demo",
                hashed_password=hash_password(PASSWORD),
                full_name="Demo Operator",
                is_active=True,
                email_verified=True,
                email_verified_at=NOW,
            )
        )
        db.flush()

        # ── Batch + its runs ────────────────────────────────────────────
        batch = BatchJobRecord(
            org_id=org.id,
            scenario_name="LON-003 Emergency Stop",
            scenario_path=SCENARIO,
            model_name="EmergencyBrake",
            num_runs=24,
            master_seed=42,
            status="completed",
            runs_completed=24,
            runs_failed=0,
            composite_mean=0.8741,
            composite_std=0.0412,
            safety_mean=0.9213,
            compliance_mean=0.8902,
            stability_mean=0.8115,
            reactivity_mean=0.8408,
            collision_rate=0.0417,
            started_at=NOW - datetime.timedelta(minutes=18),
            completed_at=NOW - datetime.timedelta(minutes=4),
            created_at=NOW - datetime.timedelta(minutes=18),
        )
        db.add(batch)

        db.add(
            BatchJobRecord(
                org_id=org.id,
                scenario_name="VRU-001 Pedestrian Crosswalk",
                scenario_path="../scenarios/vru/VRU-001_pedestrian_crosswalk.yaml",
                model_name="SimpleLaneKeep",
                num_runs=50,
                master_seed=7,
                status="running",
                runs_completed=31,
                runs_failed=2,
                created_at=NOW - datetime.timedelta(minutes=3),
            )
        )
        db.flush()

        for i in range(24):
            collided = i in (5, 17)
            db.add(
                RunRecord(
                    org_id=org.id,
                    scenario_id=SCENARIO,
                    batch_job_id=batch.id,
                    model_name="EmergencyBrake",
                    master_seed=42 + i,
                    duration=12.4,
                    termination_reason="collision" if collided else "completed",
                    num_timesteps=620,
                    frame_hash=f"{i:064x}",
                    composite_score=0.41 if collided else 0.86 + (i % 7) * 0.012,
                    safety_score=0.22 if collided else 0.93,
                    collision_occurred=collided,
                    min_ttc=0.4 if collided else 4.8,
                    compliance_score=0.89,
                    speed_compliance=0.97,
                    stability_score=0.81,
                    mean_jerk=1.8,
                    reactivity_score=0.84,
                    brake_response_time=0.42,
                    created_at=NOW - datetime.timedelta(minutes=17 - (i // 3)),
                )
            )

        # ── Models ──────────────────────────────────────────────────────
        db.add(
            ModelRecord(
                id="8f2c1a94-0d3b-4f77-9a10-2b6e5c4d1e88",
                org_id=org.id,
                user_id=1,
                name="lane-follower",
                version="v2.1",
                submission_type="cloudpickle",
                artefact_uri="file://models/lane-follower-v2.1.pkl",
                content_hash="9a3f" + "0" * 60,
                size_bytes=248_320,
                status="ready",
                created_at=NOW - datetime.timedelta(days=1),
            )
        )
        db.add(
            ModelRecord(
                id="1c7d4e02-55aa-4b31-8f60-7d9e0a2b4c15",
                org_id=org.id,
                user_id=1,
                name="lane-follower",
                version="v2.0",
                submission_type="docker",
                artefact_uri="registry.example.com/lane-follower:2.0",
                status="ready",
                created_at=NOW - datetime.timedelta(days=6),
            )
        )

        # ── API keys: one live, one revoked ─────────────────────────────
        db.add(
            ApiKeyRecord(
                id="key-live-001",
                org_id=org.id,
                user_id=1,
                key_hash="hash-live",
                key_prefix="orion_9fA2",
                label="ci-pipeline",
                last_used_at=NOW - datetime.timedelta(hours=2),
                created_at=NOW - datetime.timedelta(days=12),
            )
        )
        db.add(
            ApiKeyRecord(
                id="key-dead-002",
                org_id=org.id,
                user_id=1,
                key_hash="hash-dead",
                key_prefix="orion_3bC7",
                label="laptop (rotated)",
                created_at=NOW - datetime.timedelta(days=40),
                revoked_at=NOW - datetime.timedelta(days=3),
            )
        )

        # ── A comparison that found a regression ────────────────────────
        db.add(
            ComparisonJobRecord(
                org_id=org.id,
                user_id=1,
                model_a_id="EmergencyBrake",
                model_b_id="lane-follower",
                scenario_ids=SCENARIO,
                runs_per_scenario=10,
                seed=42,
                credits_charged=20,
                status="completed",
                overall_winner="a",
                has_regression=True,
                report_json={
                    "model_a_id": "EmergencyBrake",
                    "model_a_name": "EmergencyBrake",
                    "model_b_id": "lane-follower",
                    "model_b_name": "lane-follower v2.1",
                    "overall_winner": "a",
                    "recommendation": (
                        "Regression detected - do not deploy. 2 metric(s) regressed, "
                        "worst: safety_score 0.921 to 0.734 against a threshold of 0.10."
                    ),
                    "regressions": [
                        {
                            "metric": "safety_score",
                            "value_a": 0.9213,
                            "value_b": 0.7340,
                            "delta": -0.1873,
                            "is_regression": True,
                            "threshold_used": 0.10,
                            "scenario_id": "LON-003_emergency_stop",
                        },
                        {
                            "metric": "composite_score",
                            "value_a": 0.8741,
                            "value_b": 0.7902,
                            "delta": -0.0839,
                            "is_regression": True,
                            "threshold_used": 0.05,
                            "scenario_id": "LON-003_emergency_stop",
                        },
                    ],
                    "scenario_comparisons": [
                        {
                            "scenario_id": "LON-003_emergency_stop",
                            "model_a_name": "EmergencyBrake",
                            "model_b_name": "lane-follower v2.1",
                            "metric_deltas": [
                                {
                                    "metric": "composite_score",
                                    "value_a": 0.8741,
                                    "value_b": 0.7902,
                                    "delta": -0.0839,
                                    "is_regression": True,
                                    "threshold_used": 0.05,
                                    "scenario_id": None,
                                },
                                {
                                    "metric": "safety_score",
                                    "value_a": 0.9213,
                                    "value_b": 0.7340,
                                    "delta": -0.1873,
                                    "is_regression": True,
                                    "threshold_used": 0.10,
                                    "scenario_id": None,
                                },
                            ],
                            "has_regression": True,
                            "winner": "a",
                            "runs_per_model": 10,
                            "baseline_composite": 0.8741,
                            "candidate_composite": 0.7902,
                            "delta": -0.0839,
                        }
                    ],
                },
                created_at=NOW - datetime.timedelta(hours=1),
                completed_at=NOW - datetime.timedelta(minutes=41),
            )
        )

        # ── A search that broke the model ───────────────────────────────
        db.add(
            SearchJobRecord(
                org_id=org.id,
                user_id=1,
                scenario_id=SCENARIO,
                model_id="lane-follower",
                optimizer="cma_es",
                physics_mode="kinematic",
                max_evals=80,
                seed=42,
                n_dims=8,
                credits_charged=80,
                status="completed",
                evals_done=80,
                best_fitness=24.0261,
                falsification_found=True,
                result_json={
                    "optimizer_used": "cma-es",
                    "best_params": {
                        "npc.initial_speed": 18.42,
                        "npc.brake_intensity": 0.91,
                    },
                    "best_fitness": 24.0261,
                    "n_evals": 80,
                    "converged": False,
                    "falsification_found": True,
                    "falsification_params": {
                        "npc.initial_speed": 18.42,
                        "npc.initial_gap": 21.07,
                        "npc.brake_intensity": 0.91,
                        "ego.initial_speed": 27.65,
                    },
                    "falsifications": [
                        {
                            "npc.initial_speed": 18.42,
                            "npc.initial_gap": 21.07,
                            "npc.brake_intensity": 0.91,
                            "ego.initial_speed": 27.65,
                        },
                        {
                            "npc.initial_speed": 12.10,
                            "npc.initial_gap": 18.33,
                            "npc.brake_intensity": 0.78,
                            "ego.initial_speed": 29.90,
                        },
                        {
                            "npc.initial_speed": 22.05,
                            "npc.initial_gap": 30.12,
                            "npc.brake_intensity": 0.99,
                            "ego.initial_speed": 24.41,
                        },
                    ],
                    "falsification_count": 27,
                    "distinct_failure_count": 3,
                    "failure_rate": 0.3375,
                    "all_evaluations": [],
                    "evaluations_truncated": False,
                },
                created_at=NOW - datetime.timedelta(hours=2),
                completed_at=NOW - datetime.timedelta(hours=1, minutes=48),
            )
        )

        db.add(
            SearchJobRecord(
                org_id=org.id,
                user_id=1,
                scenario_id="../scenarios/vru/VRU-001_pedestrian_crosswalk.yaml",
                model_id="EmergencyBrake",
                optimizer="random",
                physics_mode="kinematic",
                max_evals=30,
                seed=7,
                n_dims=3,
                credits_charged=30,
                status="running",
                evals_done=11,
                created_at=NOW - datetime.timedelta(minutes=6),
            )
        )

    _store_real_frames()
    print(json.dumps({"db": DB_PATH, "email": EMAIL, "password": PASSWORD}))


def _store_real_frames() -> None:
    """Attach genuine tick frames to the run the UI links to for replay.

    Generated by actually driving the engine rather than fabricated: the
    viewer reads positions, headings and TTC out of these, and hand-written
    frames would produce a picture that cannot happen.
    """
    import asyncio

    from arep.config import get_config
    from arep.core.random_manager import RandomManager
    from arep.execution.frame_store import compress
    from arep.models.examples.example_models import ConstantActionModel
    from arep.scenario.executor import ScenarioExecutor
    from arep.scenario.parser import ScenarioParser
    from arep.simulation.engine import SimulationEngine
    from arep.database.models import RunFrameRecord

    cfg = get_config().simulation
    engine = SimulationEngine(cfg)
    scenario_def, _ = ScenarioParser().parse_file(SCENARIO)
    rng = RandomManager(47)
    world = ScenarioExecutor(cfg).create_initial_world(scenario_def, rng)

    frames = []

    def on_canonical(w, action):
        frames.append(
            engine.get_tick_frame(
                w,
                action=action,
                scenario_name=scenario_def.name,
                speed_limit=w.get_speed_limit(),
            )
        )

    async def on_tick(w, action):
        return None

    async def drive():
        await engine.run_async(
            initial_world=world,
            model=ConstantActionModel(),
            rng=rng,
            on_tick=on_tick,
            on_canonical=on_canonical,
            max_steps=int(scenario_def.duration / cfg.timestep),
            tick_interval=0.0,
        )

    asyncio.run(drive())

    with conn.session_scope() as db:
        # Run 6 is one of the two seeded collisions, so frames are the mode the
        # backend would actually have kept for it.
        collided = (
            db.query(RunRecord)
            .filter(RunRecord.collision_occurred.is_(True))
            .order_by(RunRecord.id)
            .first()
        )
        if collided is None:
            return
        db.add(
            RunFrameRecord(
                run_id=collided.id,
                frame_count=len(frames),
                frames_gzip=compress(frames),
                reason="collision",
                stored_at=NOW,
            )
        )
        print(f"stored {len(frames)} frames on run {collided.id}", file=sys.stderr)


if __name__ == "__main__":
    main()
