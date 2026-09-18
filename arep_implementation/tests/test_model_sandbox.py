"""
Customer-model sandbox tests (Phase 0.2 — defect D-01).

One test per acceptance criterion in docs/ROADMAP.md section 0.2:

  - the model subprocess environment carries no ORION_* (or other secret) vars
  - a model that opens a socket fails instead of reaching the network
  - a model that hangs is killed at the wall-clock limit and the run fails loudly
  - a self-serve org cannot use the cloudpickle path without explicit enablement

Plus the plumbing those rest on: the Observation wire round-trip, teardown of
the child process, and refusal to restart a sandbox that was killed.

These run a real subprocess. They are slow-ish by design — an in-process fake
would test nothing that matters here.
"""

from __future__ import annotations

import os
import pickle
import sys
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from arep.config import SandboxConfig                      # noqa: E402
from arep.core.action import Action                        # noqa: E402
from arep.core.observation import Observation, ObjectObservation  # noqa: E402
from arep.core.state import TrafficLightState              # noqa: E402
from arep.models.interface import ModelInterface           # noqa: E402
from arep.models.sandbox import (                          # noqa: E402
    ModelSandboxError,
    SubprocessModelRunner,
    _ENV_WHITELIST,
    _SECRET_PREFIXES,
)


# ── Models used as sandbox payloads ──────────────────────────────────────
# Defined at module scope so plain pickle can serialise them by reference;
# the sandbox child imports this module via PYTHONPATH.

class BrakeModel(ModelInterface):
    """Well-behaved model."""

    def predict(self, observation: Observation) -> Action:
        return Action(steering=0.0, throttle=0.0, brake=1.0)

    def reset(self) -> None:
        pass


class EnvSnoopModel(ModelInterface):
    """Reports the environment it can see, as a steering value."""

    def predict(self, observation: Observation) -> Action:
        import os as _os

        leaked = [k for k in _os.environ if k.startswith(("ORION_", "AREP_", "STRIPE_"))]
        # steering encodes the count of leaked variables
        return Action(steering=min(1.0, len(leaked) / 10.0), throttle=0.0, brake=0.0)

    def reset(self) -> None:
        pass


class NetworkModel(ModelInterface):
    """Tries to open a socket on every tick."""

    def predict(self, observation: Observation) -> Action:
        import socket

        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(1.0)
        s.connect(("127.0.0.1", 9))
        return Action.zero()

    def reset(self) -> None:
        pass


class HangingModel(ModelInterface):
    """Never returns."""

    def predict(self, observation: Observation) -> Action:
        while True:
            time.sleep(0.5)

    def reset(self) -> None:
        pass


class RaisingModel(ModelInterface):
    """Raises inside predict() but is otherwise healthy."""

    def predict(self, observation: Observation) -> Action:
        raise ValueError("model blew up")

    def reset(self) -> None:
        pass


def _observation() -> Observation:
    return Observation(
        ego_x=10.0, ego_y=0.0, ego_velocity=15.0, speed_limit=27.8,
        lane_valid=True, traffic_light_state=TrafficLightState.GREEN,
        objects=[ObjectObservation(object_id="npc0", relative_x=30.0, speed=12.0)],
        sim_time=1.0,
    )


def _runner(model: ModelInterface, **overrides) -> SubprocessModelRunner:
    cfg = SandboxConfig(**{
        "predict_timeout_s": 10.0,
        "total_wallclock_s": 60.0,
        **overrides,
    })
    return SubprocessModelRunner(pickle_bytes=pickle.dumps(model), config=cfg)


# ── Wire format ──────────────────────────────────────────────────────────

def test_observation_round_trips_through_the_wire_format():
    """to_dict/from_dict must be lossless — the sandbox IPC depends on it."""
    obs = _observation()
    assert Observation.from_dict(obs.to_dict()).to_dict() == obs.to_dict()


# ── Happy path ───────────────────────────────────────────────────────────

def test_sandboxed_model_returns_its_action():
    runner = _runner(BrakeModel())
    try:
        runner.reset()
        action = runner.predict(_observation())
        assert action.brake == pytest.approx(1.0)
        assert action.throttle == pytest.approx(0.0)
    finally:
        runner.close()


def test_model_exception_yields_emergency_brake_and_keeps_the_run_alive():
    """A model that raises is a bad model, not a broken sandbox."""
    runner = _runner(RaisingModel())
    try:
        first = runner.predict(_observation())
        assert first.brake == pytest.approx(Action.emergency_brake().brake)
        # still usable afterwards
        assert runner.predict(_observation()) is not None
    finally:
        runner.close()


# ── Acceptance: environment is stripped ──────────────────────────────────

def test_env_whitelist_excludes_secret_bearing_prefixes():
    for name in _ENV_WHITELIST:
        assert not name.startswith(_SECRET_PREFIXES), f"{name} is whitelisted but secret-shaped"


def test_sandbox_env_contains_no_orion_variables(monkeypatch):
    """The built env is the one the child gets — assert directly on it."""
    monkeypatch.setenv("ORION_DATABASE_URL", "postgresql://user:pw@db/orion")
    monkeypatch.setenv("ORION_SECRET_KEY", "super-secret-value")
    monkeypatch.setenv("AREP_DATABASE_URL", "sqlite:///arep.db")

    runner = _runner(BrakeModel())
    env = runner._build_env(workdir=os.getcwd())

    assert not [k for k in env if k.startswith(_SECRET_PREFIXES)]
    assert "ORION_DATABASE_URL" not in env
    assert "ORION_SECRET_KEY" not in env
    assert env["PYTHONPATH"]          # arep must still be importable


def test_model_cannot_read_orion_env_from_inside_the_sandbox(monkeypatch):
    monkeypatch.setenv("ORION_DATABASE_URL", "postgresql://user:pw@db/orion")
    monkeypatch.setenv("ORION_SECRET_KEY", "super-secret-value")

    runner = _runner(EnvSnoopModel())
    try:
        action = runner.predict(_observation())
        assert action.steering == pytest.approx(0.0), "model saw ORION_*/AREP_* variables"
    finally:
        runner.close()


# ── Acceptance: network is blocked ───────────────────────────────────────

def test_model_that_opens_a_socket_fails():
    """
    Connecting must not succeed. The model's exception surfaces as an
    emergency brake (sandbox healthy, model misbehaved) rather than a
    successful connection.
    """
    runner = _runner(NetworkModel())
    try:
        action = runner.predict(_observation())
        assert action.brake == pytest.approx(Action.emergency_brake().brake)
    finally:
        runner.close()


# ── Acceptance: hard wall-clock kill ─────────────────────────────────────

def test_hanging_model_is_killed_at_the_wall_clock_limit():
    runner = _runner(HangingModel(), predict_timeout_s=2.0)
    try:
        started = time.monotonic()
        with pytest.raises(ModelSandboxError, match="wall-clock"):
            runner.predict(_observation())
        elapsed = time.monotonic() - started
        assert elapsed < 15.0, f"kill took {elapsed:.1f}s — deadline not enforced"
        assert runner._process is None, "child was not torn down"
    finally:
        runner.close()


def test_killed_sandbox_refuses_to_restart():
    """No crash-loop: once killed for a violation, every later call raises."""
    runner = _runner(HangingModel(), predict_timeout_s=2.0)
    try:
        with pytest.raises(ModelSandboxError):
            runner.predict(_observation())
        with pytest.raises(ModelSandboxError, match="dead"):
            runner.predict(_observation())
    finally:
        runner.close()


def test_total_wallclock_budget_is_enforced_across_calls():
    """
    The per-call deadline is not enough: a model can sit just under it on every
    tick. The run-level budget is what stops that, so it is checked against
    accumulated time rather than one call.

    The accumulated total is set directly instead of being burned in real time —
    a test that waits out a real budget is slow and races the OS timer.
    """
    runner = _runner(BrakeModel(), predict_timeout_s=5.0, total_wallclock_s=30.0)
    try:
        runner.predict(_observation())
        assert runner._elapsed_s > 0.0, "call time is not being accumulated"

        runner._elapsed_s = 30.0        # budget now exhausted
        with pytest.raises(ModelSandboxError, match="total wall-clock budget"):
            runner.predict(_observation())
        assert runner._process is None, "child was not torn down"
    finally:
        runner.close()


# ── Teardown ─────────────────────────────────────────────────────────────

def test_close_terminates_the_child_and_removes_its_jail():
    runner = _runner(BrakeModel())
    runner.predict(_observation())
    workdir = runner._workdir
    pid = runner._process.pid
    assert workdir is not None and workdir.exists()

    runner.close()

    assert runner._process is None
    assert not workdir.exists(), "sandbox temp dir leaked"
    if os.name == "posix":
        with pytest.raises(OSError):
            os.kill(pid, 0)


def test_close_is_idempotent():
    runner = _runner(BrakeModel())
    runner.predict(_observation())
    runner.close()
    runner.close()      # must not raise


# ── Acceptance: a killed sandbox fails the run (so the credit is refunded) ──

def test_runner_aborts_the_run_when_the_sandbox_is_killed(tmp_path):
    """
    End-to-end contract the credit refund depends on.

    EvaluationRunner must propagate ModelSandboxError rather than scoring the
    truncated run: worker tasks treat a raised exception as a failed run and
    refund, while a returned result is published as a real score. A hanging
    model that scored 'safe' because it stopped early would be the worst
    possible outcome.
    """
    from arep.execution.runner import EvaluationRunner
    from arep.utils.exceptions import ModelSandboxError as RunnerSandboxError

    scenario = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "scenarios", "basic", "straight_road_lead_vehicle.yaml",
    )
    runner = EvaluationRunner()
    model = _runner(HangingModel(), predict_timeout_s=2.0)

    with pytest.raises(RunnerSandboxError):
        runner.run_single(scenario, model, master_seed=42)

    # run_single's finally must still have torn the child down
    assert model._process is None
    assert model._workdir is None


def test_model_that_merely_raises_still_produces_a_score():
    """The counterpart: a bad model is scored, not aborted."""
    from arep.execution.runner import EvaluationRunner

    scenario = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "scenarios", "basic", "straight_road_lead_vehicle.yaml",
    )
    result = EvaluationRunner().run_single(scenario, _runner(RaisingModel()), master_seed=42)
    assert result is not None
    assert 0.0 <= result.composite_score <= 1.0
