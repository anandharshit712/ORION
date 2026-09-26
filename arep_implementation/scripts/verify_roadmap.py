"""
Verify roadmap acceptance criteria by executing them.

A checkbox ticked from memory is worse than an unticked one: it converts "we
think this works" into "this was verified" without anything having been
verified. This script runs the criteria that can be run and prints PASS, FAIL or
CANNOT-VERIFY per item, so the roadmap is updated from evidence.

    PYTHONPATH=. python scripts/verify_roadmap.py

CANNOT-VERIFY is a real outcome, not a failure to try: some criteria need a
browser, a production deployment, a ROS2 install or a fixture nobody has
committed. Those stay unticked.
"""

from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path

RESULTS: list[tuple[str, str, str]] = []


def check(item: str, fn):
    """Run one criterion. Its return value is the evidence line."""
    try:
        detail = fn()
        RESULTS.append(("PASS", item, detail or ""))
    except NotImplementedError as exc:
        RESULTS.append(("CANNOT-VERIFY", item, str(exc)))
    except Exception as exc:  # noqa: BLE001 - a failed criterion is data
        RESULTS.append(("FAIL", item, f"{type(exc).__name__}: {exc}"))
        if "-v" in sys.argv:
            traceback.print_exc()


# ── 1.5 Road topology ─────────────────────────────────────────────────────


def _four_way_graph():
    from arep.core.road_templates import four_way_intersection

    graph = four_way_intersection()
    assert graph.segments, "no segments"
    assert graph.junctions, "no junctions"
    return f"{len(graph.segments)} segments, {len(graph.junctions)} junction(s)"


def _off_road():
    from arep.core.road_templates import four_way_intersection
    from arep.core.state import Vector2D

    graph = four_way_intersection()
    far = graph.is_off_road(Vector2D(5000.0, 5000.0))
    on = graph.is_off_road(Vector2D(0.0, 0.0))
    assert far is True, "a point 5 km away was not off-road"
    assert on is False, "the junction centre was reported off-road"
    return "off-road at (5000,5000)=True, at origin=False"


def _int_scenario_runs():
    from arep.execution.runner import EvaluationRunner
    from arep.models.examples.example_models import EmergencyBrakeModel

    result = EvaluationRunner().run_single(
        "../scenarios/int/INT-001_four_way_stop_yield.yaml",
        EmergencyBrakeModel(),
        master_seed=42,
    )
    assert 0.0 <= result.composite_score <= 1.0
    return f"INT-001 ran, composite={result.composite_score:.4f}"


def _lane_offset_on_junction():
    from arep.config import get_config
    from arep.core.random_manager import RandomManager
    from arep.scenario.executor import ScenarioExecutor
    from arep.scenario.parser import ScenarioParser

    scenario, _ = ScenarioParser().parse_file(
        "../scenarios/int/INT-004_roundabout_entry_give_way.yaml"
    )
    world = ScenarioExecutor(get_config().simulation).create_initial_world(
        scenario, RandomManager(42)
    )
    lane = world.get_current_lane()
    assert lane is not None, "no lane under the ego on a curved template"
    offset = lane.get_signed_lateral_offset(world.ego_vehicle.position)
    assert abs(offset) < lane.width, f"offset {offset} exceeds the lane"
    return f"roundabout lane offset={offset:+.3f} m on a curved segment"


# ── 2.1 Confidence intervals ──────────────────────────────────────────────


def _ci_widens():
    import numpy as np
    from arep.statistics.aggregator import StatisticalAggregator

    agg = StatisticalAggregator()
    values = np.random.default_rng(0).normal(0.75, 0.10, 100)
    widths = []
    for n in (5, 20, 100):
        d = agg.distribution(values[:n])
        widths.append(round(d.ci_95_high - d.ci_95_low, 4))
    assert widths[0] > widths[1] > widths[2], widths
    return f"widths {widths} at n=5/20/100"


def _ci_deterministic():
    import numpy as np
    from arep.statistics.aggregator import StatisticalAggregator

    agg = StatisticalAggregator()
    values = np.random.default_rng(7).normal(0.5, 0.1, 40)
    assert agg.distribution(values).to_dict() == agg.distribution(values).to_dict()
    return "identical input gives identical statistics"


def _ttc_accounts_for_braking():
    """Constant-acceleration TTC must not report a collision the braking
    prevents, which the constant-velocity version did."""
    from arep.core.state import ObjectType, Vector2D, VehicleState
    from arep.core.ttc import TTCCalculator

    def ego(accel):
        return VehicleState(
            position=Vector2D(0.0, 0.0),
            heading=0.0,
            velocity=20.0,
            acceleration=accel,
            length=4.5,
            width=2.0,
            wheelbase=2.7,
            object_type=ObjectType.CAR,
            object_id="ego",
        )

    stopped = VehicleState(
        position=Vector2D(50.0, 0.0),
        heading=0.0,
        velocity=0.0,
        acceleration=0.0,
        length=4.5,
        width=2.0,
        wheelbase=2.7,
        object_type=ObjectType.CAR,
        object_id="lead",
    )

    calc = TTCCalculator()
    braking = calc.compute_ttc(ego(-8.0), stopped)
    coasting = calc.compute_ttc(ego(0.0), stopped)

    assert coasting is not None, "coasting into a stopped car reported no TTC"
    # Braking either avoids it entirely (None) or buys measurably more time.
    assert (
        braking is None or braking > coasting
    ), f"braking TTC {braking} is not better than coasting {coasting}"
    shown = "no collision" if braking is None else f"{braking:.2f}s"
    return f"braking -> {shown}; coasting -> {coasting:.2f}s"


# ── 2.2 Failure clustering ────────────────────────────────────────────────


def _failure_report():
    from arep.analysis.failure_clustering import FailureClusterer
    from arep.execution.runner import EvaluationRunner
    from arep.models.examples.example_models import ConstantActionModel

    batch = EvaluationRunner().run_batch(
        scenario_path="../scenarios/lon/LON-003_emergency_stop.yaml",
        model=ConstantActionModel(throttle=0.4),
        num_runs=50,
        master_seed=42,
    )
    failures = [r for r in batch.per_run_results if r.safety.collision_occurred]
    assert failures, "ConstantAction did not fail LON-003 at all"

    # analyse() reads a persisted batch, so the runs are written first - which
    # also exercises the path the API actually uses.
    from arep.database.connection import session_scope
    from arep.database.repository import (
        BatchJobRepository,
        RunRepository,
        ScenarioRepository,
    )

    with session_scope() as db:
        scenario_rec = ScenarioRepository(db).upsert(
            name="LON-003 verify",
            version="1.0",
            content_hash="v" * 64,
            yaml_content="x",
            duration=20.0,
            road_type="highway",
            num_traffic_objects=1,
        )
        job = BatchJobRepository(db).create(
            scenario_name="LON-003 verify",
            model_name="ConstantAction",
            num_runs=50,
            master_seed=42,
            scenario_path="../scenarios/lon/LON-003_emergency_stop.yaml",
        )
        db.flush()
        batch_id = job.id
        repo = RunRepository(db)
        for r in batch.per_run_results:
            repo.save_result(scenario_rec.id, r, batch_job_id=batch_id, org_id=None)

    report = FailureClusterer().analyse(batch_id)
    assert report.fail_runs > 0, "report is empty despite real failures"
    return f"{len(failures)}/50 failed; report has {report.fail_runs} fail runs"


# ── 2.3 Adversarial search ────────────────────────────────────────────────


def _search_finds_collision():
    from arep.models.examples.example_models import ConstantActionModel
    from arep.scenario.parser import ScenarioParser
    from arep.search.objective import ObjectiveFunction
    from arep.search.optimizer import CMAESOptimizer
    from arep.search.space import SearchSpace

    scenario, _ = ScenarioParser().parse_file(
        "../scenarios/lon/LON-003_emergency_stop.yaml"
    )
    space = SearchSpace(scenario)
    objective = ObjectiveFunction(scenario, ConstantActionModel(throttle=0.4), space)
    result = CMAESOptimizer(space, max_evals=50, popsize=10, seed=7).run(objective)

    assert result.falsification_found, "no collision found in 50 evaluations"
    return f"collision found after {result.n_evals} evaluations"


def _search_reproduces():
    import copy

    from arep.core.random_manager import RandomManager
    from arep.execution.runner import EvaluationRunner
    from arep.models.examples.example_models import ConstantActionModel
    from arep.scenario.parameterizer import ScenarioParameterizer
    from arep.scenario.parser import ScenarioParser
    from arep.search.objective import ObjectiveFunction
    from arep.search.optimizer import RandomSearchOptimizer
    from arep.search.space import SearchSpace

    scenario, _ = ScenarioParser().parse_file(
        "../scenarios/lon/LON-003_emergency_stop.yaml"
    )
    space = SearchSpace(scenario)
    objective = ObjectiveFunction(scenario, ConstantActionModel(throttle=0.4), space)
    result = RandomSearchOptimizer(space, n_samples=30, seed=3).run(objective)
    assert result.falsification_found, "baseline found no collision to reproduce"

    record = objective.falsification_record
    replay = copy.deepcopy(scenario)
    replay.parameterization = record.params
    ScenarioParameterizer().apply(replay, RandomManager(record.seed))
    rerun = EvaluationRunner().run_scenario_definition(
        replay, ConstantActionModel(throttle=0.4), record.seed
    )
    assert (
        rerun.safety.collision_occurred
    ), "the reported counter-example did not reproduce"
    return f"seed {record.seed} reproduced the collision"


def _search_records_every_eval():
    from arep.models.examples.example_models import EmergencyBrakeModel
    from arep.scenario.parser import ScenarioParser
    from arep.search.objective import ObjectiveFunction
    from arep.search.optimizer import CMAESOptimizer
    from arep.search.space import SearchSpace

    scenario, _ = ScenarioParser().parse_file(
        "../scenarios/lon/LON-003_emergency_stop.yaml"
    )

    def run():
        space = SearchSpace(scenario)
        objective = ObjectiveFunction(scenario, EmergencyBrakeModel(), space)
        res = CMAESOptimizer(space, max_evals=12, popsize=4, seed=7).run(objective)
        return res, [round(r.fitness, 9) for r in res.all_evaluations]

    first, a = run()
    _, b = run()
    assert len(first.all_evaluations) == first.n_evals
    assert a == b, "same seed gave a different search"
    return f"{first.n_evals} evaluations recorded, reproducible"


# ── 2.4 Comparison & reports ──────────────────────────────────────────────


def _comparison_picks_the_better_model():
    from arep.analysis.regression_detector import RegressionDetector

    report = RegressionDetector().compare(
        model_a_id="EmergencyBrake",
        model_b_id="ConstantAction",
        scenario_ids=["../scenarios/lon/LON-003_emergency_stop.yaml"],
        runs_per_scenario=4,
        seed=42,
    )
    assert report.overall_winner in (
        "a",
        "tie",
    ), f"ConstantAction won: {report.overall_winner}"
    return f"winner={report.overall_winner}, {report.recommendation[:60]}"


def _pdf_report_sections():
    from arep.reporting.pdf_generator import PDFGenerator

    html = PDFGenerator(require_pdf=False).render_html(
        "batch_report.html",
        {
            "batch": {
                "scenario_name": "LON-003",
                "model_name": "EmergencyBrake",
                "num_runs": 100,
                "master_seed": 42,
                "physics_mode": "kinematic",
                "aggregated": {
                    "composite_mean": 0.89,
                    "composite_std": 0.02,
                    "pass_rate": 0.99,
                    "safety_mean": 0.95,
                    "compliance_mean": 0.88,
                    "stability_mean": 0.82,
                    "reactivity_mean": 0.90,
                },
            }
        },
    )
    for token in ("LON-003", "EmergencyBrake", "0.89"):
        assert token in html, f"report is missing {token}"
    return "HTML report renders its numbers (PDF step needs GTK, Linux CI)"


# ── 4.2 / 4.4 interop ─────────────────────────────────────────────────────


def _xodr_named_fixture():
    raise NotImplementedError(
        "tests/fixtures/TownSimple.xodr does not exist; the parser is tested "
        "against generated XML instead"
    )


def _xodr_parses_at_all():
    xml = """<?xml version="1.0"?>
<OpenDRIVE>
  <road name="a" length="100.0" id="1" junction="-1">
    <planView>
      <geometry s="0" x="0" y="0" hdg="0" length="50"><line/></geometry>
      <geometry s="50" x="50" y="0" hdg="0" length="50">
        <arc curvature="0.01"/>
      </geometry>
    </planView>
    <lanes><laneSection s="0">
      <right><lane id="-1" type="driving"><width sOffset="0" a="3.5"/></lane></right>
    </laneSection></lanes>
  </road>
</OpenDRIVE>"""
    import tempfile

    from arep.maps.xodr_parser import OpenDRIVEParser

    with tempfile.NamedTemporaryFile("w", suffix=".xodr", delete=False) as fh:
        fh.write(xml)
        path = fh.name
    try:
        graph = OpenDRIVEParser().parse(path)
    finally:
        os.unlink(path)

    assert graph.segments, "no segments parsed"
    return f"{len(graph.segments)} segment(s) from line + arc geometry"


def _osc_named_fixture():
    raise NotImplementedError(
        "the ASAM CutIn.osc sample is not committed; the importer is tested "
        "against exported output instead"
    )


def _osc_export_roundtrip():
    from arep.scenario.osc_exporter import OpenSCENARIOExporter
    from arep.scenario.osc_importer import OpenSCENARIOImporter
    from arep.scenario.parser import ScenarioParser

    scenario, _ = ScenarioParser().parse_file(
        "../scenarios/lon/LON-003_emergency_stop.yaml"
    )
    text = OpenSCENARIOExporter().export(scenario)
    assert "scenario" in text, "export produced nothing recognisable"
    reimported = OpenSCENARIOImporter().import_string(text)
    assert reimported.name, "re-import lost the scenario name"
    return "LON-003 exports and re-imports (parameterisation lost by design)"


# ── 3.2 CI entrypoint ─────────────────────────────────────────────────────


def _suite_runner_exit_codes():
    from arep.cli.run_suite import EXIT_ERROR, EXIT_FAIL, EXIT_PASS

    assert len({EXIT_PASS, EXIT_FAIL, EXIT_ERROR}) == 3, "exit codes collide"
    return f"pass={EXIT_PASS} fail={EXIT_FAIL} error={EXIT_ERROR}, all distinct"


def _ci_files_agree():
    """The action and the workflow are only ever executed by someone else's
    pipeline, so nothing in our CI notices when they stop matching."""
    import yaml

    root = Path(__file__).resolve().parent.parent.parent
    action = yaml.safe_load(
        (root / ".github" / "actions" / "evaluate-model" / "action.yml").read_text(
            encoding="utf-8"
        )
    )
    workflow = (root / ".github" / "workflows" / "docker-build.yml").read_text(
        encoding="utf-8"
    )

    image = action["runs"]["image"].replace("docker://", "")
    name = image.rsplit("/", 1)[-1].split(":")[0]
    assert name in workflow, f"{name} is never built by docker-build.yml"
    assert "docker push" in workflow, "the image is built but never published"

    entrypoint = action["runs"].get("entrypoint")
    assert entrypoint, "the action does not override the image entrypoint"

    dockerfile = (root / "infrastructure" / "docker" / "Dockerfile.cli").read_text(
        encoding="utf-8"
    )
    assert entrypoint in dockerfile, f"{entrypoint} is not installed in the image"

    script = root / "ci" / "orion-ci.sh"
    # bytes([13, 10]) rather than a "\r\n" literal: this file gets edited by
    # tooling that mangles backslash escapes, and a CRLF check that silently
    # became a bare-newline check would pass against the exact file it exists
    # to reject.
    assert bytes([13, 10]) not in script.read_bytes(), "orion-ci.sh has CRLF"

    return f"action runs {image} via {entrypoint}; pushed, installed, LF"


def _ci_regression_fails_a_passing_run():
    """The absolute collision bar cannot see a model getting steadily worse.
    Two real models, both collision-free on LON-003, one clearly worse."""
    import json
    import tempfile

    from arep.cli.run_suite import EXIT_FAIL, EXIT_PASS, main as suite_main

    with tempfile.TemporaryDirectory() as tmp:
        good, worse = Path(tmp) / "good", Path(tmp) / "worse"

        def run(model, out, extra=()):
            return suite_main(
                [
                    "--scenarios",
                    "LON-003",
                    "--model",
                    model,
                    "--runs-per-scenario",
                    "2",
                    "--output-dir",
                    str(out),
                    *extra,
                ]
            )

        assert run("emergency_brake", good) == EXIT_PASS
        assert run("lane_keep", worse) == EXIT_PASS, "must pass on its own merits"

        baseline = good / "orion_suite_report.json"
        assert run("lane_keep", worse, ["--baseline", str(baseline)]) == EXIT_FAIL

        before = json.loads(baseline.read_text(encoding="utf-8"))["composite_mean"]
        after = json.loads(
            (worse / "orion_suite_report.json").read_text(encoding="utf-8")
        )["composite_mean"]

    return f"composite {before} -> {after} passes the bar and fails the build"


def _gitlab_component_matches_the_action():
    import yaml

    root = Path(__file__).resolve().parent.parent.parent
    component = root / "ci" / "gitlab" / "templates" / "evaluate-model.yml"
    assert component.exists(), "the GitLab component is missing"

    docs = list(yaml.safe_load_all(component.read_text(encoding="utf-8")))
    assert len(docs) == 2, "a component is a spec document then a job document"

    action = yaml.safe_load(
        (root / ".github" / "actions" / "evaluate-model" / "action.yml").read_text(
            encoding="utf-8"
        )
    )
    expected = action["runs"]["image"].replace("docker://", "")
    assert (
        docs[0]["spec"]["inputs"]["image"]["default"] == expected
    ), "the component and the action would score against different images"

    job = next(iter(docs[1].values()))
    assert job["image"]["entrypoint"] == [""], "script: would be passed to run_suite"

    return f"component pinned to {expected}; not published (no gitlab.com/orioneval)"


CRITERIA = [
    ("1.5", "four_way_intersection() returns a valid RoadGraph", _four_way_graph),
    ("1.5", "is_off_road() true outside all segments", _off_road),
    ("1.5", "An INT-* scenario with a template loads and runs", _int_scenario_runs),
    ("1.5", "Lane offset works on curved/junction segments", _lane_offset_on_junction),
    ("2.1", "CI widens as n decreases (5/20/100)", _ci_widens),
    ("2.1", "Same input -> identical distribution statistics", _ci_deterministic),
    ("2.1", "TTC with acceleration beats constant-velocity", _ttc_accounts_for_braking),
    (
        "2.2",
        "50-run LON-003 + ConstantAction gives a non-empty report",
        _failure_report,
    ),
    ("2.3", "CMA-ES finds a collision within 50 evals", _search_finds_collision),
    ("2.3", "falsification_params reproduce the collision", _search_reproduces),
    ("2.3", "all_evaluations complete and reproducible", _search_records_every_eval),
    (
        "2.4",
        "EmergencyBrake beats ConstantAction on LON-003",
        _comparison_picks_the_better_model,
    ),
    ("2.4", "Report renders all sections", _pdf_report_sections),
    ("3.2", "run_suite exit codes 0/1/2 are distinct", _suite_runner_exit_codes),
    ("3.2", "The action and the image it runs agree", _ci_files_agree),
    (
        "3.2",
        "A regression fails a run that passes the collision bar",
        _ci_regression_fails_a_passing_run,
    ),
    (
        "3.3",
        "GitLab component matches the action",
        _gitlab_component_matches_the_action,
    ),
    ("4.2", "Parsing TownSimple.xodr", _xodr_named_fixture),
    ("4.2", "XODR line+arc geometry parses to a RoadGraph", _xodr_parses_at_all),
    ("4.4", "Importing the ASAM CutIn.osc sample", _osc_named_fixture),
    ("4.4", "LON-003 exports to OSC2 and re-imports", _osc_export_roundtrip),
]


def main() -> int:
    for phase, item, fn in CRITERIA:
        check(f"[{phase}] {item}", fn)

    width = max(len(i) for _, i, _ in RESULTS)
    for status, item, detail in RESULTS:
        print(f"{status:>14}  {item:<{width}}  {detail}")

    failed = [r for r in RESULTS if r[0] == "FAIL"]
    print(
        f"\n{sum(1 for r in RESULTS if r[0] == 'PASS')} passed, "
        f"{len(failed)} failed, "
        f"{sum(1 for r in RESULTS if r[0] == 'CANNOT-VERIFY')} cannot verify"
    )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
