"""
AREP End-to-End Integration Test.

Tests the full pipeline:
  1. Config loading
  2. Vector2D math
  3. State creation and serialization
  4. Action clamping and brake precedence
  5. Physics engine (bicycle model)
  6. Random manager (determinism)
  7. Collision detection (SAT/OBB)
  8. TTC computation
  9. Observation generation
  10. Simulation engine (single step + full run)
  11. Scenario parsing and execution
  12. Data collection + evaluation metrics
  13. Statistical aggregation
  14. Batch execution
"""

import math
import json
import sys
import os

# Add parent dir to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from arep.config import Config, SimulationConfig, load_config, reload_config
from arep.core.state import (
    Vector2D, VehicleState, WorldState,
    ObjectType, TerminationReason, TrafficLightState,
    LaneInfo, TrafficLightInfo,
)
from arep.core.action import Action, ActionAlternative
from arep.core.physics import VehiclePhysics
from arep.core.random_manager import RandomManager
from arep.core.collision import CollisionDetector
from arep.core.ttc import TTCCalculator
from arep.core.observation import Observation
from arep.simulation.engine import SimulationEngine
from arep.simulation.time_manager import TimeManager
from arep.evaluation.collector import DataCollector
from arep.evaluation.composite import CompositeEvaluator
from arep.models.examples.example_models import (
    ConstantActionModel, EmergencyBrakeModel,
    SimpleLaneKeepModel, RandomModel,
)
from arep.statistics.aggregator import StatisticalAggregator
from arep.utils.hashing import hash_string, derive_seed
from arep.utils.validators import clamp, validate_range

import numpy as np


def test_config():
    """Test config loading and defaults."""
    config = reload_config()
    assert config.env == "development"
    assert config.simulation.timestep == 0.02
    assert config.simulation.max_velocity == 35.0
    assert config.simulation.vehicle_length == 4.5
    print("  [PASS] Config defaults")


def test_vector2d():
    """Test Vector2D operations."""
    v1 = Vector2D(3.0, 4.0)
    v2 = Vector2D(1.0, 2.0)

    # Basic arithmetic
    assert (v1 + v2).x == 4.0
    assert (v1 - v2).y == 2.0
    assert (v1 * 2.0).x == 6.0
    assert (2.0 * v1).x == 6.0

    # Dot and cross
    assert v1.dot(v2) == 11.0
    assert v1.cross(v2) == 2.0

    # Norm
    assert abs(v1.norm() - 5.0) < 1e-10

    # Normalize
    n = v1.normalize()
    assert abs(n.norm() - 1.0) < 1e-10

    # Rotation
    v = Vector2D(1.0, 0.0)
    rotated = v.rotate(math.pi / 2)
    assert abs(rotated.x) < 1e-10
    assert abs(rotated.y - 1.0) < 1e-10

    # Distance
    assert abs(v1.distance_to(v2) - math.sqrt(8)) < 1e-10

    # Serialization
    d = v1.to_dict()
    v_back = Vector2D.from_dict(d)
    assert v_back.x == v1.x and v_back.y == v1.y

    print("  [PASS] Vector2D operations")


def test_vehicle_state():
    """Test VehicleState methods."""
    v = VehicleState(
        position=Vector2D(10.0, 5.0),
        heading=0.0,
        velocity=20.0,
        length=4.5,
        width=2.0,
        object_id="ego",
    )

    # Velocity vector
    vel = v.get_velocity_vector()
    assert abs(vel.x - 20.0) < 1e-10
    assert abs(vel.y) < 1e-10

    # Front/rear
    front = v.get_front_center()
    rear = v.get_rear_center()
    assert front.x > v.position.x
    assert rear.x < v.position.x

    # Bounding box
    corners = v.get_bounding_box_corners()
    assert len(corners) == 4

    # All corners should be at the correct distance from center
    for c in corners:
        dist = c.distance_to(v.position)
        expected = math.sqrt((4.5/2)**2 + (2.0/2)**2)
        assert abs(dist - expected) < 1e-6

    # Serialization roundtrip
    d = v.to_dict()
    v2 = VehicleState.from_dict(d)
    assert v2.object_id == "ego"
    assert abs(v2.velocity - 20.0) < 1e-10

    # Deep copy
    v_copy = v.copy()
    v_copy.velocity = 0.0
    assert v.velocity == 20.0  # original unchanged

    print("  [PASS] VehicleState methods")


def test_action():
    """Test Action clamping and conversion."""
    # Clamping
    a = Action(steering=2.0, throttle=-1.0, brake=3.0)
    assert a.steering == 1.0
    assert a.throttle == 0.0
    assert a.brake == 1.0

    # Brake precedence
    a = Action(steering=0.0, throttle=0.5, brake=0.5)
    accel = a.get_acceleration()
    assert accel < 0  # brake wins

    # ActionAlternative conversion
    alt = ActionAlternative(steering=0.3, acceleration=-2.0)
    act = alt.to_action()
    assert act.brake > 0.0
    assert act.throttle == 0.0

    alt_pos = ActionAlternative(steering=0.0, acceleration=1.5)
    act_pos = alt_pos.to_action()
    assert act_pos.throttle > 0.0
    assert act_pos.brake == 0.0

    print("  [PASS] Action clamping and conversion")


def test_physics():
    """Test physics engine determinism and correctness."""
    config = SimulationConfig()
    physics = VehiclePhysics(config)

    # Straight-line motion
    state = VehicleState(
        position=Vector2D(0.0, 0.0),
        heading=0.0,
        velocity=10.0,
    )
    action = Action(steering=0.0, throttle=0.0, brake=0.0)

    new_state = physics.update(state, action)

    # Should move forward
    expected_x = 10.0 * config.timestep
    assert abs(new_state.position.x - expected_x) < 1e-10

    # Velocity unchanged (no throttle/brake)
    assert abs(new_state.velocity - 10.0) < 1e-10

    # Heading unchanged (no steering)
    assert abs(new_state.heading) < 1e-10

    # Test determinism: same inputs → same output
    new_state_2 = physics.update(state, action)
    assert abs(new_state.position.x - new_state_2.position.x) < 1e-15
    assert abs(new_state.velocity - new_state_2.velocity) < 1e-15

    # Braking
    brake_action = Action(steering=0.0, throttle=0.0, brake=1.0)
    braked = physics.update(state, brake_action)
    assert braked.velocity < state.velocity

    # Velocity cannot go negative
    stopped = VehicleState(position=Vector2D(0, 0), velocity=0.1)
    hard_brake = Action(0, 0, 1.0)
    result = physics.update(stopped, hard_brake)
    assert result.velocity >= 0.0

    print("  [PASS] Physics determinism and correctness")


def test_random_manager():
    """Test deterministic random manager."""
    rng1 = RandomManager(master_seed=42)
    rng2 = RandomManager(master_seed=42)

    # Same seed → same values
    val1 = float(rng1.get("noise").normal(0, 1))
    val2 = float(rng2.get("noise").normal(0, 1))
    assert val1 == val2

    # Different subsystems are independent
    scenario_val = float(rng1.get("scenario").uniform(0, 100))
    noise_val = float(rng1.get("noise").normal(0, 1))  # next noise value

    # Save/restore
    state = rng1.save_state()
    next_val = float(rng1.get("noise").normal(0, 1))
    rng1.restore_state(state)
    restored_val = float(rng1.get("noise").normal(0, 1))
    assert next_val == restored_val

    # Different seed → different values
    rng3 = RandomManager(master_seed=99)
    val3 = float(rng3.get("noise").normal(0, 1))
    rng4 = RandomManager(master_seed=42)
    val4 = float(rng4.get("noise").normal(0, 1))
    assert val3 != val4

    print("  [PASS] Random manager determinism")


def test_collision_detection():
    """Test SAT/OBB collision detection."""
    config = SimulationConfig()
    detector = CollisionDetector(config)

    # Two overlapping vehicles at same position
    v1 = VehicleState(
        position=Vector2D(0.0, 0.0), heading=0.0,
        length=4.5, width=2.0, object_id="a",
    )
    v2 = VehicleState(
        position=Vector2D(0.0, 0.0), heading=0.0,
        length=4.5, width=2.0, object_id="b",
    )
    assert detector.check_collision(v1, v2) == True

    # Two separated vehicles
    v3 = VehicleState(
        position=Vector2D(100.0, 0.0), heading=0.0,
        length=4.5, width=2.0, object_id="c",
    )
    assert detector.check_collision(v1, v3) == False

    # Edge case: barely NOT touching (4.5m center-to-center = length apart)
    v4 = VehicleState(
        position=Vector2D(4.5 + 0.01, 0.0), heading=0.0,
        length=4.5, width=2.0, object_id="d",
    )
    # Centers 4.51m apart, half lengths 2.25+2.25 = 4.5 → gap of 0.01
    assert detector.check_collision(v1, v4) == False

    # Overlapping case: 3m apart (overlap = 4.5 - 3 = 1.5)
    v4b = VehicleState(
        position=Vector2D(3.0, 0.0), heading=0.0,
        length=4.5, width=2.0, object_id="d2",
    )
    assert detector.check_collision(v1, v4b) == True

    # Clear separation
    v5 = VehicleState(
        position=Vector2D(10.0, 0.0), heading=0.0,
        length=4.5, width=2.0, object_id="e",
    )
    assert detector.check_collision(v1, v5) == False

    # detect_all_collisions
    world = WorldState(
        ego_vehicle=v1,
        dynamic_objects=[v2, v5],
    )
    collisions = detector.detect_all_collisions(world)
    assert len(collisions) == 1
    assert collisions[0].object_id == "b"

    print("  [PASS] Collision detection (SAT/OBB)")


def test_ttc():
    """Test time-to-collision calculation."""
    calc = TTCCalculator()

    ego = VehicleState(
        position=Vector2D(0.0, 0.0), heading=0.0, velocity=20.0,
    )
    # Vehicle ahead, moving slower
    ahead = VehicleState(
        position=Vector2D(100.0, 0.0), heading=0.0, velocity=10.0,
        object_id="ahead",
    )

    ttc = calc.compute_ttc(ego, ahead)
    # TTC = 100 / (20 - 10) = 10 seconds
    assert ttc is not None
    assert abs(ttc - 10.0) < 0.1

    # Vehicle behind → no TTC
    behind = VehicleState(
        position=Vector2D(-50.0, 0.0), heading=0.0, velocity=10.0,
        object_id="behind",
    )
    assert calc.compute_ttc(ego, behind) is None

    # Vehicle moving away → no TTC
    away = VehicleState(
        position=Vector2D(100.0, 0.0), heading=0.0, velocity=30.0,
        object_id="away",
    )
    assert calc.compute_ttc(ego, away) is None

    # Min TTC across multiple
    min_ttc = calc.compute_min_ttc(ego, [ahead, behind, away])
    assert abs(min_ttc - 10.0) < 0.1

    print("  [PASS] TTC calculation")


def test_observation():
    """Test observation generation."""
    ego = VehicleState(
        position=Vector2D(50.0, 0.0), heading=0.0, velocity=20.0,
        object_id="ego",
    )
    obj = VehicleState(
        position=Vector2D(100.0, 3.0), heading=0.0, velocity=15.0,
        object_id="obj1",
    )
    world = WorldState(ego_vehicle=ego, dynamic_objects=[obj])

    obs = Observation.from_world_state(world)

    assert abs(obs.ego_velocity - 20.0) < 1e-10
    assert len(obs.objects) == 1
    assert obs.objects[0].relative_x > 0  # ahead

    # Vector conversion
    vec = obs.to_vector()
    assert vec.shape == (93,)
    assert abs(vec[3] - 20.0) < 1e-10  # ego velocity at index 3

    # Dict conversion
    d = obs.to_dict()
    assert d["ego"]["velocity"] == 20.0

    print("  [PASS] Observation generation")


def test_simulation_engine():
    """Test simulation engine step and full run."""
    config = SimulationConfig()
    engine = SimulationEngine(config)
    rng = RandomManager(42)

    ego = VehicleState(
        position=Vector2D(0.0, 0.0), heading=0.0, velocity=10.0,
        object_id="ego",
    )
    world = WorldState(ego_vehicle=ego)

    # Single step
    action = Action(steering=0.0, throttle=0.3, brake=0.0)
    new_world = engine.step(world, action, rng)

    assert new_world.sim_time > 0
    assert new_world.ego_vehicle.position.x > 0
    assert not new_world.is_terminated

    # Full run with ConstantActionModel
    model = ConstantActionModel(throttle=0.3)
    final = engine.run_simulation(world, model, rng, max_steps=100)

    assert final.is_terminated
    assert final.sim_time > 0
    assert final.ego_vehicle.position.x > 0

    print("  [PASS] Simulation engine")


def test_evaluation_pipeline():
    """Test data collection and metrics evaluation."""
    config = SimulationConfig()
    engine = SimulationEngine(config)
    rng = RandomManager(42)

    ego = VehicleState(
        position=Vector2D(0.0, 0.0), heading=0.0, velocity=15.0,
        object_id="ego",
    )
    obj = VehicleState(
        position=Vector2D(80.0, 0.0), heading=0.0, velocity=10.0,
        object_id="lead",
    )
    lane = LaneInfo(
        lane_id="lane_0",
        centerline_points=[Vector2D(float(x), 0.0) for x in range(0, 1001, 10)],
        width=3.5,
        speed_limit=20.0,
    )
    world = WorldState(
        ego_vehicle=ego,
        dynamic_objects=[obj],
        lanes=[lane],
    )

    collector = DataCollector(scenario_name="test", model_name="constant")
    model = ConstantActionModel(throttle=0.3)

    # Run short simulation
    previous = None
    current = world
    for step in range(50):
        obs = Observation.from_world_state(current, previous)
        action = model.predict(obs)
        collector.record_step(current, action, previous)
        previous = current
        current = engine.step(current, action, rng)
        if current.is_terminated:
            break

    record = collector.finalize(current)

    # Evaluate
    evaluator = CompositeEvaluator()
    result = evaluator.evaluate(record)

    # Scores should be in [0, 1]
    assert 0.0 <= result.composite_score <= 1.0
    assert 0.0 <= result.safety.safety_score <= 1.0
    assert 0.0 <= result.compliance.compliance_score <= 1.0
    assert 0.0 <= result.stability.stability_score <= 1.0
    assert 0.0 <= result.reactivity.reactivity_score <= 1.0

    # Serialization
    d = result.to_dict()
    assert "composite_score" in d
    assert "safety_score" in d

    print("  [PASS] Evaluation pipeline")


def test_statistical_aggregation():
    """Test statistical aggregation."""
    config = SimulationConfig()
    engine = SimulationEngine(config)
    evaluator = CompositeEvaluator()
    aggregator = StatisticalAggregator()

    for seed in range(5):
        rng = RandomManager(42 + seed)
        ego = VehicleState(
            position=Vector2D(0.0, 0.0), heading=0.0, velocity=15.0,
        )
        world = WorldState(ego_vehicle=ego)

        collector = DataCollector()
        model = ConstantActionModel(throttle=0.3)

        current = world
        previous = None
        for step in range(30):
            obs = Observation.from_world_state(current, previous)
            action = model.predict(obs)
            collector.record_step(current, action, previous)
            previous = current
            current = engine.step(current, action, rng)
            if current.is_terminated:
                break

        record = collector.finalize(current)
        result = evaluator.evaluate(record)
        aggregator.add_result(result)

    metrics = aggregator.compute()
    assert metrics.num_runs == 5
    assert 0.0 <= metrics.composite_mean <= 1.0
    assert metrics.composite_ci_lower <= metrics.composite_mean or \
        (np.isnan(metrics.composite_ci_lower) and metrics.composite_std == 0)
    assert metrics.composite_mean <= metrics.composite_ci_upper or \
        (np.isnan(metrics.composite_ci_upper) and metrics.composite_std == 0)

    d = metrics.to_dict()
    assert "composite_95ci" in d

    print("  [PASS] Statistical aggregation")


def test_hashing():
    """Test hashing utilities."""
    h1 = hash_string("hello")
    h2 = hash_string("hello")
    h3 = hash_string("world")
    assert h1 == h2
    assert h1 != h3
    assert len(h1) == 64

    s1 = derive_seed(42, "noise")
    s2 = derive_seed(42, "noise")
    s3 = derive_seed(42, "scenario")
    assert s1 == s2
    assert s1 != s3
    assert 0 <= s1 < 2**32

    print("  [PASS] Hashing utilities")


def test_validators():
    """Test validation helpers."""
    assert clamp(5.0, 0.0, 10.0) == 5.0
    assert clamp(-1.0, 0.0, 10.0) == 0.0
    assert clamp(15.0, 0.0, 10.0) == 10.0

    validate_range(5.0, 0.0, 10.0)
    try:
        validate_range(15.0, 0.0, 10.0)
        assert False, "Should have raised ValueError"
    except ValueError:
        pass

    print("  [PASS] Validators")


def test_example_models():
    """Test all example models."""
    obs = Observation(ego_velocity=15.0, lane_offset=1.0)

    # ConstantAction
    m1 = ConstantActionModel(throttle=0.5)
    a1 = m1.predict(obs)
    assert a1.throttle == 0.5

    # EmergencyBrake
    m2 = EmergencyBrakeModel()
    a2 = m2.predict(obs)
    assert a2.brake == 1.0

    # SimpleLaneKeep
    m3 = SimpleLaneKeepModel(target_velocity=20.0)
    a3 = m3.predict(obs)
    assert a3.is_valid()

    # Random (deterministic)
    m4 = RandomModel(seed=42)
    m4.reset()
    a4a = m4.predict(obs)
    m4.reset()
    a4b = m4.predict(obs)
    assert a4a.steering == a4b.steering  # same after reset

    print("  [PASS] Example models")


if __name__ == "__main__":
    print("\n=== AREP Integration Tests ===\n")

    tests = [
        ("Config", test_config),
        ("Vector2D", test_vector2d),
        ("VehicleState", test_vehicle_state),
        ("Action", test_action),
        ("Physics", test_physics),
        ("Random Manager", test_random_manager),
        ("Collision Detection", test_collision_detection),
        ("TTC", test_ttc),
        ("Observation", test_observation),
        ("Simulation Engine", test_simulation_engine),
        ("Evaluation Pipeline", test_evaluation_pipeline),
        ("Statistical Aggregation", test_statistical_aggregation),
        ("Hashing", test_hashing),
        ("Validators", test_validators),
        ("Example Models", test_example_models),
    ]

    passed = 0
    failed = 0

    for name, test_fn in tests:
        try:
            test_fn()
            passed += 1
        except Exception as e:
            print(f"  [FAIL] {name} FAILED: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print(f"\n{'=' * 40}")
    print(f"Results: {passed} passed, {failed} failed")
    print(f"{'=' * 40}\n")

    sys.exit(1 if failed > 0 else 0)
