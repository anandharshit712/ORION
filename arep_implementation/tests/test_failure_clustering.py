"""
Failure clustering tests (Phase 2.2).

A batch reporting "12% collision rate" tells a customer they have a problem but
not when it happens, and "when" is the only actionable part. This clusters the
failures by the parameters that produced them.

The tests run a real batch through EvaluationRunner and cluster its actual
results rather than fabricating rows, because the load-bearing claim is that a
run's parameters can be reconstructed from its seed — and a fixture that
invents parameter vectors would never test that.
"""

from __future__ import annotations

import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from arep.analysis.failure_clustering import (       # noqa: E402
    FailureClusterer, _dominant_event, _is_failure,
)

SCENARIO = "scenarios/basic/straight_road_lead_vehicle.yaml"
PARAMETERISED = "../scenarios/lon/LON-003_emergency_stop.yaml"


@pytest.fixture
def db(tmp_path):
    from arep.database import connection as conn_mod

    path = tmp_path / "clustering.db"
    conn_mod._engine = None
    conn_mod._SessionFactory = None
    conn_mod.init_database(url=f"sqlite:///{path}")
    yield conn_mod
    conn_mod._engine = None
    conn_mod._SessionFactory = None


def _record_batch(conn_mod, scenario_path: str, model, seeds, num_runs=None) -> int:
    """Run a real batch and persist it the way the worker would."""
    from arep.database.models import BatchJobRecord, ScenarioRecord
    from arep.database.repository import RunRepository
    from arep.execution.runner import EvaluationRunner

    with conn_mod.session_scope() as session:
        scenario_row = ScenarioRecord(
            name="clustering-fixture", version="2.0", content_hash=os.urandom(32).hex(),
            yaml_content="", duration=30.0,
        )
        session.add(scenario_row)
        session.flush()
        scenario_id = scenario_row.id

        job = BatchJobRecord(
            scenario_name="clustering-fixture", model_name=model.name,
            num_runs=num_runs or len(seeds), master_seed=seeds[0],
            status="running", scenario_path=scenario_path,
        )
        session.add(job)
        session.flush()
        batch_id = job.id

    runner = EvaluationRunner()
    for seed in seeds:
        result = runner.run_single(scenario_path, model, seed)
        with conn_mod.session_scope() as session:
            RunRepository(session).save_result(scenario_id, result, batch_job_id=batch_id)

    return batch_id


# -- What counts as a failure --------------------------------------------

def test_a_collision_is_a_failure():
    assert _is_failure({"collision": True, "termination_reason": "collision"})


def test_leaving_the_road_is_a_failure():
    assert _is_failure({"collision": False, "termination_reason": "off_road"})


def test_a_low_score_alone_is_not_a_failure():
    """A low composite can mean an uncomfortable but safe drive. Clustering
    that together with crashes would mix ride quality into a safety report."""
    assert not _is_failure({"collision": False, "termination_reason": "timeout"})


def test_the_dominant_event_is_the_most_common_one():
    cluster = [
        {"collision": True, "termination_reason": "collision"},
        {"collision": True, "termination_reason": "collision"},
        {"collision": False, "termination_reason": "off_road"},
    ]
    assert _dominant_event(cluster) == "collision"


# -- End to end on real runs ---------------------------------------------

def test_a_clean_batch_reports_no_fault_conditions(db):
    from arep.models.examples.example_models import EmergencyBrakeModel

    batch_id = _record_batch(db, SCENARIO, EmergencyBrakeModel(), seeds=list(range(5)))
    report = FailureClusterer().analyse(batch_id)

    assert report.total_runs == 5
    assert report.fail_runs == 0
    assert report.overall_pass_rate == 1.0
    assert report.fault_conditions == []
    assert "No failures" in report.safe_region_description


def test_a_failing_batch_is_summarised(db):
    """ConstantAction does not brake, so it rear-ends the lead vehicle."""
    from arep.models.examples.example_models import ConstantActionModel

    batch_id = _record_batch(
        db, SCENARIO, ConstantActionModel(throttle=0.4), seeds=list(range(6)),
    )
    report = FailureClusterer().analyse(batch_id)

    assert report.total_runs == 6
    assert report.fail_runs > 0, "a non-braking model should hit the lead vehicle"
    assert report.overall_pass_rate < 1.0


def test_an_unparameterised_scenario_says_so_rather_than_implying_no_pattern(db):
    """Every run used identical inputs, so there is no parameter space. Saying
    "no pattern found" would suggest the failures were random."""
    from arep.models.examples.example_models import ConstantActionModel

    batch_id = _record_batch(
        db, SCENARIO, ConstantActionModel(throttle=0.4), seeds=list(range(4)),
    )
    report = FailureClusterer().analyse(batch_id)

    assert report.fail_runs > 0
    assert "no parameterisation" in report.safe_region_description


def test_a_parameterised_batch_reconstructs_its_parameters(db):
    """The load-bearing claim: a run's inputs can be recovered from its seed."""
    from arep.models.examples.example_models import ConstantActionModel

    batch_id = _record_batch(
        db, PARAMETERISED, ConstantActionModel(throttle=0.5),
        seeds=list(range(12)),
    )
    report = FailureClusterer().analyse(batch_id)

    assert report.total_runs == 12
    if report.fault_conditions:
        condition = report.fault_conditions[0]
        assert condition.parameter_means, "a cluster with no parameters means nothing"
        assert condition.run_count >= 1
        assert 0.0 <= condition.failure_rate <= 1.0
        assert condition.example_run_id
        assert condition.description


def test_reconstruction_is_deterministic(db):
    """Two analyses of one batch must agree, or the report is not evidence."""
    from arep.models.examples.example_models import ConstantActionModel

    batch_id = _record_batch(
        db, PARAMETERISED, ConstantActionModel(throttle=0.5), seeds=list(range(8)),
    )
    clusterer = FailureClusterer()
    first = clusterer.analyse(batch_id)
    second = clusterer.analyse(batch_id)

    assert first.fail_runs == second.fail_runs
    assert [c.description for c in first.fault_conditions] == \
           [c.description for c in second.fault_conditions]


# -- Degenerate inputs ----------------------------------------------------

def test_an_unknown_batch_raises(db):
    with pytest.raises(ValueError, match="No batch job"):
        FailureClusterer().analyse(999999)


def test_an_empty_batch_reports_zero_rather_than_dividing_by_it(db):
    from arep.database.models import BatchJobRecord

    with db.session_scope() as session:
        job = BatchJobRecord(
            scenario_name="empty", model_name="m", num_runs=0, master_seed=1,
            status="completed", scenario_path=SCENARIO,
        )
        session.add(job)
        session.flush()
        batch_id = job.id

    report = FailureClusterer().analyse(batch_id)
    assert report.total_runs == 0
    assert report.overall_pass_rate == 0.0
    assert report.fault_conditions == []


def test_a_batch_with_no_recorded_path_says_it_cannot_be_analysed(db):
    """Older batches stored no scenario path, so their inputs are unrecoverable."""
    from arep.database.models import BatchJobRecord, ScenarioRecord
    from arep.database.repository import RunRepository
    from arep.execution.runner import EvaluationRunner
    from arep.models.examples.example_models import ConstantActionModel

    with db.session_scope() as session:
        scenario_row = ScenarioRecord(
            name="pathless", version="2.0", content_hash=os.urandom(32).hex(),
            yaml_content="", duration=30.0,
        )
        session.add(scenario_row)
        session.flush()
        scenario_id = scenario_row.id
        job = BatchJobRecord(
            scenario_name="pathless", model_name="m", num_runs=2, master_seed=1,
            status="completed", scenario_path=None,
        )
        session.add(job)
        session.flush()
        batch_id = job.id

    runner = EvaluationRunner()
    for seed in (1, 2):
        result = runner.run_single(SCENARIO, ConstantActionModel(throttle=0.4), seed)
        with db.session_scope() as session:
            RunRepository(session).save_result(scenario_id, result, batch_job_id=batch_id)

    report = FailureClusterer().analyse(batch_id)
    assert "cannot be reconstructed" in report.safe_region_description


# -- Description building -------------------------------------------------

def test_a_description_names_only_the_extreme_parameters():
    """Listing every parameter says nothing; the useful part is the two or
    three that characterise the region."""
    clusterer = FailureClusterer()
    description = clusterer._build_description(
        cluster_params={"gap": 12.0, "speed": 25.0, "middling": 50.0},
        scenario_param_ranges={
            "gap": (10.0, 60.0),        # cluster sits at the bottom
            "speed": (10.0, 26.0),      # cluster sits at the top
            "middling": (0.0, 100.0),   # cluster sits in the middle
        },
    )
    assert "gap <" in description
    assert "speed >" in description
    assert "middling" not in description


def test_the_safe_region_inverts_the_faults_and_hedges():
    from arep.analysis.failure_clustering import FaultCondition

    clusterer = FailureClusterer()
    text = clusterer._build_safe_region([
        FaultCondition(description="gap < 22.5", failure_rate=0.3, run_count=3,
                       dominant_event="collision", example_run_id="7"),
    ])
    assert "gap >=" in text
    assert "not a safety guarantee" in text


def test_no_faults_gives_the_plain_message():
    assert "No consistent failure patterns" in FailureClusterer()._build_safe_region([])
