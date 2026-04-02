"""
Tests for AREP Enhanced Physics Engine.

Tests both KINEMATIC (original) and DYNAMIC (new) modes:
  - Backward compatibility (kinematic unchanged)
  - Pacejka tire model correctness
  - Friction effects (dry/wet/ice)
  - Weight transfer under acceleration
  - Aerodynamic drag
  - Determinism (same inputs → same outputs)
  - Constraint enforcement (velocity, steering)
  - Stopping distance calculations
"""

import math
import unittest

from arep.config import SimulationConfig
from arep.core.physics import (
    VehiclePhysics,
    PhysicsMode,
    SurfaceType,
    PacejkaParams,
    DynamicVehicleParams,
    GRAVITY,
)
from arep.core.state import VehicleState, Vector2D
from arep.core.action import Action


class TestKinematicBackwardCompatibility(unittest.TestCase):
    """Verify KINEMATIC mode produces identical results to the original."""

    def setUp(self):
        self.config = SimulationConfig()
        self.physics = VehiclePhysics(self.config, mode=PhysicsMode.KINEMATIC)

    def test_straight_line_motion(self):
        """Driving straight should increase x, not change y or heading."""
        state = VehicleState(
            position=Vector2D(0., 0.), heading=0., velocity=10.
        )
        action = Action(steering=0., throttle=0.5, brake=0.)
        new = self.physics.update(state, action)

        self.assertGreater(new.position.x, 0.)
        self.assertAlmostEqual(new.position.y, 0., places=10)
        self.assertAlmostEqual(new.heading, 0., places=10)

    def test_velocity_update(self):
        """Velocity should change by acceleration × dt."""
        state = VehicleState(position=Vector2D(0., 0.), heading=0., velocity=10.)
        action = Action(steering=0., throttle=1.0, brake=0.)
        new = self.physics.update(state, action)

        expected_accel = action.get_acceleration(
            self.config.max_acceleration, self.config.max_deceleration
        )
        expected_v = 10. + expected_accel * self.config.timestep
        self.assertAlmostEqual(new.velocity, expected_v, places=10)

    def test_braking(self):
        """Braking should reduce velocity."""
        state = VehicleState(position=Vector2D(0., 0.), heading=0., velocity=10.)
        action = Action(steering=0., throttle=0., brake=1.0)
        new = self.physics.update(state, action)
        self.assertLess(new.velocity, 10.)

    def test_velocity_never_negative(self):
        """Velocity should be clamped at zero, not go negative."""
        state = VehicleState(position=Vector2D(0., 0.), heading=0., velocity=0.1)
        action = Action(steering=0., throttle=0., brake=1.0)
        new = self.physics.update(state, action)
        self.assertGreaterEqual(new.velocity, 0.)

    def test_max_velocity_clamped(self):
        """Velocity should not exceed max_velocity."""
        state = VehicleState(
            position=Vector2D(0., 0.), heading=0.,
            velocity=self.config.max_velocity - 0.01
        )
        action = Action(steering=0., throttle=1.0, brake=0.)

        # Step many times
        for _ in range(100):
            state = self.physics.update(state, action)

        self.assertLessEqual(state.velocity, self.config.max_velocity)

    def test_steering_changes_heading(self):
        """Non-zero steering with velocity should change heading."""
        state = VehicleState(position=Vector2D(0., 0.), heading=0., velocity=10.)
        action = Action(steering=0.5, throttle=0.5, brake=0.)
        new = self.physics.update(state, action)
        self.assertNotAlmostEqual(new.heading, 0.)

    def test_heading_wrapping(self):
        """Heading should stay in [-π, π]."""
        state = VehicleState(
            position=Vector2D(0., 0.), heading=math.pi - 0.01, velocity=10.
        )
        action = Action(steering=1.0, throttle=0.5, brake=0.)

        for _ in range(50):
            state = self.physics.update(state, action)

        self.assertGreaterEqual(state.heading, -math.pi)
        self.assertLessEqual(state.heading, math.pi)

    def test_determinism(self):
        """Same inputs must always produce same outputs."""
        state = VehicleState(position=Vector2D(10., 5.), heading=0.3, velocity=15.)
        action = Action(steering=0.3, throttle=0.6, brake=0.1)

        r1 = self.physics.update(state, action)
        r2 = self.physics.update(state, action)

        self.assertEqual(r1.position.x, r2.position.x)
        self.assertEqual(r1.position.y, r2.position.y)
        self.assertEqual(r1.heading, r2.heading)
        self.assertEqual(r1.velocity, r2.velocity)


class TestPacejkaTireModel(unittest.TestCase):
    """Test the Pacejka Magic Formula implementation."""

    def setUp(self):
        self.tire = PacejkaParams(B=10., C=1.9, D=1.0, E=0.97)

    def test_zero_slip_zero_force(self):
        """Zero slip angle should produce zero force."""
        F = self.tire.compute_force(0., 5000., 1.0)
        self.assertAlmostEqual(F, 0., places=5)

    def test_force_increases_with_slip(self):
        """Small slip increase should increase force."""
        F1 = self.tire.compute_force(0.01, 5000., 1.0)
        F2 = self.tire.compute_force(0.05, 5000., 1.0)
        self.assertGreater(abs(F2), abs(F1))

    def test_force_saturates(self):
        """Force should saturate (not grow indefinitely) at large slip."""
        F_small = abs(self.tire.compute_force(0.05, 5000., 1.0))
        F_large = abs(self.tire.compute_force(0.5, 5000., 1.0))
        F_very_large = abs(self.tire.compute_force(1.0, 5000., 1.0))

        # Force should grow then flatten — not linear
        growth_1 = F_large - F_small
        growth_2 = F_very_large - F_large
        self.assertGreater(growth_1, growth_2)  # Diminishing returns

    def test_friction_scales_force(self):
        """Lower friction should reduce peak force proportionally."""
        F_dry = abs(self.tire.compute_force(0.1, 5000., 1.0))
        F_wet = abs(self.tire.compute_force(0.1, 5000., 0.5))

        # Wet should be approximately half of dry
        ratio = F_wet / F_dry
        self.assertAlmostEqual(ratio, 0.5, places=2)

    def test_normal_load_scales_force(self):
        """Higher normal load should increase force."""
        F_light = abs(self.tire.compute_force(0.1, 3000., 1.0))
        F_heavy = abs(self.tire.compute_force(0.1, 6000., 1.0))
        self.assertGreater(F_heavy, F_light)

    def test_sign_of_force(self):
        """Force direction should match slip direction."""
        F_pos = self.tire.compute_force(0.1, 5000., 1.0)
        F_neg = self.tire.compute_force(-0.1, 5000., 1.0)
        self.assertGreater(F_pos, 0.)
        self.assertLess(F_neg, 0.)


class TestDynamicMode(unittest.TestCase):
    """Test the enhanced dynamic physics model."""

    def setUp(self):
        self.config = SimulationConfig()
        self.physics = VehiclePhysics(
            self.config, mode=PhysicsMode.DYNAMIC
        )

    def test_straight_line_dynamic(self):
        """Dynamic mode should also move forward when driving straight."""
        state = VehicleState(
            position=Vector2D(0., 0.), heading=0., velocity=10.
        )
        action = Action(steering=0., throttle=0.5, brake=0.)
        new = self.physics.update(state, action)

        self.assertGreater(new.position.x, 0.)
        # Small lateral deviation is acceptable due to dynamics
        self.assertAlmostEqual(new.position.y, 0., places=3)

    def test_braking_on_ice_longer_distance(self):
        """Braking on ice should take longer than on dry asphalt."""
        state_dry = VehicleState(position=Vector2D(0., 0.), heading=0., velocity=20.)
        state_ice = VehicleState(position=Vector2D(0., 0.), heading=0., velocity=20.)

        phys_dry = VehiclePhysics(
            self.config, mode=PhysicsMode.DYNAMIC
        )
        phys_dry.set_surface(SurfaceType.DRY_ASPHALT)

        phys_ice = VehiclePhysics(
            self.config, mode=PhysicsMode.DYNAMIC
        )
        phys_ice.set_surface(SurfaceType.ICE)

        d_dry = phys_dry.compute_stopping_distance(20.)
        d_ice = phys_ice.compute_stopping_distance(20.)

        self.assertGreater(d_ice, d_dry)

    def test_aerodynamic_drag_at_high_speed(self):
        """At high speed, drag should reduce acceleration vs low speed."""
        state_slow = VehicleState(
            position=Vector2D(0., 0.), heading=0., velocity=5.
        )
        state_fast = VehicleState(
            position=Vector2D(0., 0.), heading=0., velocity=30.
        )
        action = Action(steering=0., throttle=1.0, brake=0.)

        new_slow = self.physics.update(state_slow, action)
        new_fast = self.physics.update(state_fast, action)

        accel_slow = new_slow.velocity - 5.
        accel_fast = new_fast.velocity - 30.

        # Fast car should have less acceleration due to drag
        self.assertGreater(accel_slow, accel_fast)

    def test_velocity_clamped_dynamic(self):
        """Velocity should not exceed max in dynamic mode."""
        state = VehicleState(
            position=Vector2D(0., 0.), heading=0.,
            velocity=self.config.max_velocity - 0.01
        )
        action = Action(steering=0., throttle=1.0, brake=0.)

        for _ in range(100):
            state = self.physics.update(state, action)

        self.assertLessEqual(state.velocity, self.config.max_velocity)

    def test_determinism_dynamic(self):
        """Dynamic mode must also be deterministic."""
        state = VehicleState(
            position=Vector2D(10., 5.), heading=0.3, velocity=15.
        )
        action = Action(steering=0.3, throttle=0.6, brake=0.1)

        phys1 = VehiclePhysics(self.config, mode=PhysicsMode.DYNAMIC)
        phys2 = VehiclePhysics(self.config, mode=PhysicsMode.DYNAMIC)

        r1 = phys1.update(state, action)
        r2 = phys2.update(state, action)

        self.assertEqual(r1.position.x, r2.position.x)
        self.assertEqual(r1.position.y, r2.position.y)
        self.assertEqual(r1.heading, r2.heading)
        self.assertEqual(r1.velocity, r2.velocity)

    def test_steering_causes_heading_change_dynamic(self):
        """Steering in dynamic mode should induce yaw change."""
        state = VehicleState(
            position=Vector2D(0., 0.), heading=0., velocity=15.
        )
        action = Action(steering=0.5, throttle=0.5, brake=0.)

        # Run several steps to build up yaw rate
        for _ in range(10):
            state = self.physics.update(state, action)

        self.assertNotAlmostEqual(state.heading, 0.)

    def test_heading_wrapping_dynamic(self):
        """Heading should stay in [-π, π] in dynamic mode."""
        state = VehicleState(
            position=Vector2D(0., 0.), heading=math.pi - 0.01, velocity=10.
        )
        action = Action(steering=1.0, throttle=0.5, brake=0.)

        for _ in range(100):
            state = self.physics.update(state, action)

        self.assertGreaterEqual(state.heading, -math.pi)
        self.assertLessEqual(state.heading, math.pi)

    def test_reset_dynamic_state(self):
        """Resetting dynamic state should clear yaw rate."""
        state = VehicleState(
            position=Vector2D(0., 0.), heading=0., velocity=15.
        )
        action = Action(steering=0.8, throttle=0.5, brake=0.)

        # Build up yaw rate
        for _ in range(20):
            state = self.physics.update(state, action)

        self.assertNotEqual(self.physics._yaw_rate, 0.)

        # Reset
        self.physics.reset_dynamic_state()
        self.assertEqual(self.physics._yaw_rate, 0.)


class TestSurfaceTypes(unittest.TestCase):
    """Test surface friction system."""

    def test_dry_friction(self):
        self.assertAlmostEqual(SurfaceType.DRY_ASPHALT.get_friction(), 1.0)

    def test_wet_friction(self):
        self.assertAlmostEqual(SurfaceType.WET_ASPHALT.get_friction(), 0.5)

    def test_ice_friction(self):
        self.assertAlmostEqual(SurfaceType.ICE.get_friction(), 0.2)

    def test_gravel_friction(self):
        self.assertAlmostEqual(SurfaceType.GRAVEL.get_friction(), 0.6)

    def test_set_surface_updates_friction(self):
        config = SimulationConfig()
        physics = VehiclePhysics(config, mode=PhysicsMode.DYNAMIC)

        physics.set_surface(SurfaceType.WET_ASPHALT)
        self.assertAlmostEqual(physics.surface_friction, 0.5)

        physics.set_surface(SurfaceType.ICE)
        self.assertAlmostEqual(physics.surface_friction, 0.2)

    def test_custom_friction(self):
        config = SimulationConfig()
        physics = VehiclePhysics(config, mode=PhysicsMode.DYNAMIC)
        physics.set_surface_friction(0.75)
        self.assertAlmostEqual(physics.surface_friction, 0.75)


class TestTireForceDiagnostics(unittest.TestCase):
    """Test the diagnostic get_tire_forces method."""

    def test_kinematic_returns_no_forces(self):
        config = SimulationConfig()
        physics = VehiclePhysics(config, mode=PhysicsMode.KINEMATIC)
        state = VehicleState(position=Vector2D(0., 0.), heading=0., velocity=10.)
        action = Action(steering=0., throttle=0.5, brake=0.)

        forces = physics.get_tire_forces(state, action)
        self.assertEqual(forces["mode"], "kinematic")
        self.assertFalse(forces["forces_available"])

    def test_dynamic_returns_forces(self):
        config = SimulationConfig()
        physics = VehiclePhysics(config, mode=PhysicsMode.DYNAMIC)
        state = VehicleState(position=Vector2D(0., 0.), heading=0., velocity=10.)
        action = Action(steering=0.1, throttle=0.5, brake=0.)

        forces = physics.get_tire_forces(state, action)
        self.assertEqual(forces["mode"], "dynamic")
        self.assertIn("front_slip_angle_deg", forces)
        self.assertIn("front_lateral_force_N", forces)
        self.assertIn("front_grip_ratio", forces)
        self.assertIn("surface_friction", forces)


class TestStoppingDistanceComparison(unittest.TestCase):
    """Verify stopping distance calculations for both modes."""

    def test_kinematic_stopping_distance_formula(self):
        """d = v² / (2·a_max)."""
        config = SimulationConfig()
        physics = VehiclePhysics(config, mode=PhysicsMode.KINEMATIC)

        v = 20.
        expected = v * v / (2. * config.max_deceleration)
        actual = physics.compute_stopping_distance(v)
        self.assertAlmostEqual(actual, expected, places=5)

    def test_dynamic_stopping_shorter_on_dry(self):
        """Dynamic on dry should stop shorter due to drag helping."""
        config = SimulationConfig()
        phys_k = VehiclePhysics(config, mode=PhysicsMode.KINEMATIC)
        phys_d = VehiclePhysics(config, mode=PhysicsMode.DYNAMIC)
        phys_d.set_surface(SurfaceType.DRY_ASPHALT)

        d_k = phys_k.compute_stopping_distance(20.)
        d_d = phys_d.compute_stopping_distance(20.)

        # Dynamic with drag should be shorter or comparable
        self.assertLess(d_d, d_k * 1.1)  # Within 10% or less

    def test_zero_velocity_zero_distance(self):
        config = SimulationConfig()
        for mode in (PhysicsMode.KINEMATIC, PhysicsMode.DYNAMIC):
            physics = VehiclePhysics(config, mode=mode)
            self.assertEqual(physics.compute_stopping_distance(0.), 0.)
            self.assertEqual(physics.compute_time_to_stop(0.), 0.)


class TestMultiStepConsistency(unittest.TestCase):
    """Run longer simulations and verify physical plausibility."""

    def test_coast_to_stop_dynamic(self):
        """With no throttle, drag and rolling should eventually stop the car."""
        config = SimulationConfig()
        physics = VehiclePhysics(config, mode=PhysicsMode.DYNAMIC)
        state = VehicleState(
            position=Vector2D(0., 0.), heading=0., velocity=10.
        )
        action = Action(steering=0., throttle=0., brake=0.)

        # Coast for 30 seconds (1500 steps)
        for _ in range(1500):
            state = physics.update(state, action)

        # Should have slowed significantly (drag + rolling)
        self.assertLess(state.velocity, 5.)

    def test_100_step_trajectory_forward_progress(self):
        """Driving forward for 100 steps should make significant distance."""
        config = SimulationConfig()
        for mode in (PhysicsMode.KINEMATIC, PhysicsMode.DYNAMIC):
            physics = VehiclePhysics(config, mode=mode)
            if mode == PhysicsMode.DYNAMIC:
                physics.reset_dynamic_state()

            state = VehicleState(
                position=Vector2D(0., 0.), heading=0., velocity=15.
            )
            action = Action(steering=0., throttle=0.5, brake=0.)

            for _ in range(100):
                state = physics.update(state, action)

            # 100 steps × 0.02s = 2 seconds at ~15 m/s = ~30m
            self.assertGreater(
                state.position.x, 20.,
                f"Mode {mode.value}: insufficient forward progress"
            )


if __name__ == "__main__":
    unittest.main()
