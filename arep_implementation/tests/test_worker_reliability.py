"""
Worker retry and idempotency tests (Phase 0.6, defect D-08).

Covers the roadmap acceptance criterion "transient DB error during a run → task
retries and succeeds; no refund", plus the two ways the previous behaviour lost
or duplicated customer work:

  - max_retries=0 meant a dropped database connection killed a run the customer
    had already paid for
  - acks_late redelivery could write a second RunRecord for the same seed,
    inflating the batch aggregate

Celery runs eagerly here (task_always_eager), so `.retry()` raises rather than
re-queueing. The tests therefore drive the task function directly with a stub
`self`, which is also the only way to observe the retry decision rather than
just its outcome.
"""

from __future__ import annotations

import os
import sys
from types import SimpleNamespace

import pytest
from sqlalchemy.exc import OperationalError

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from arep.worker import tasks  # noqa: E402


class _Retry(Exception):
    """Stands in for celery.exceptions.Retry."""


class _StubTask:
    """Minimal bound-task double: records retries instead of re-queueing."""

    def __init__(self, retries: int = 0):
        self.request = SimpleNamespace(retries=retries)
        self.retry_calls: list[dict] = []

    def retry(self, exc=None, countdown=None):
        self.retry_calls.append({"exc": exc, "countdown": countdown})
        return _Retry(str(exc))


@pytest.fixture
def spy(monkeypatch):
    """Capture refunds and failure bookkeeping instead of touching a database."""
    calls = {"refunds": [], "failures": [], "saved": []}

    monkeypatch.setattr(tasks, "_refund_credit",
                        lambda org_id: calls["refunds"].append(org_id))
    monkeypatch.setattr(tasks, "_fail_run",
                        lambda batch_id, org_id, exc: calls["failures"].append(
                            (batch_id, org_id, str(exc))))
    return calls


@pytest.fixture
def no_existing_run(monkeypatch):
    """Idempotency guard finds nothing, so the task proceeds."""
    class _Session:
        def __enter__(self): return self
        def __exit__(self, *a): return False

    class _Repo:
        def __init__(self, _db): pass
        def get_by_batch_and_seed(self, batch_id, seed): return None
        def save_result(self, *a, **k): return None

    monkeypatch.setattr(tasks, "session_scope", lambda: _Session())
    monkeypatch.setattr(tasks, "RunRepository", _Repo)
    return _Repo


# The Celery decorator binds `self`, so a stub cannot be passed to the task
# object. execute_single_run is the same logic as a plain function.
_run_single = tasks.execute_single_run


def _run(task_self, **overrides):
    kwargs = dict(
        batch_id=1, scenario_id=1,
        scenario_path="scenarios/basic/straight_road_lead_vehicle.yaml",
        model_name="EmergencyBrake", seed=42, org_id="org-a",
    )
    kwargs.update(overrides)
    return _run_single(task_self, **kwargs)


# -- Retry policy ---------------------------------------------------------

def test_retry_policy_matches_the_spec():
    """5s / 15s / 60s, three attempts after the first."""
    assert tasks.MAX_RETRIES == 3
    assert tasks.RETRY_BACKOFF_SECONDS == (5, 15, 60)


def test_a_transient_database_error_is_retried_without_refunding(
    monkeypatch, spy, no_existing_run,
):
    """The acceptance criterion: a dropped connection must not lose the run.

    A refund here would hand back a credit for a run that is still going to
    happen — and again on the next attempt.
    """
    def explode(*a, **k):
        raise OperationalError("SELECT 1", {}, Exception("server closed the connection"))

    monkeypatch.setattr(tasks, "resolve_model", explode)
    task = _StubTask(retries=0)

    with pytest.raises(_Retry):
        _run(task)

    assert len(task.retry_calls) == 1
    assert task.retry_calls[0]["countdown"] == 5
    assert spy["refunds"] == [], "a retryable failure must not refund"
    assert spy["failures"] == [], "a retryable failure must not count as failed"


def test_backoff_grows_with_the_attempt_number(monkeypatch, spy, no_existing_run):
    def explode(*a, **k):
        raise OperationalError("SELECT 1", {}, Exception("gone"))

    monkeypatch.setattr(tasks, "resolve_model", explode)

    for attempt, expected in enumerate(tasks.RETRY_BACKOFF_SECONDS):
        task = _StubTask(retries=attempt)
        with pytest.raises(_Retry):
            _run(task)
        assert task.retry_calls[0]["countdown"] == expected


def test_the_final_transient_failure_refunds_exactly_once(
    monkeypatch, spy, no_existing_run,
):
    """Retries exhausted: now the customer gets their credit back, once."""
    def explode(*a, **k):
        raise OperationalError("SELECT 1", {}, Exception("still gone"))

    monkeypatch.setattr(tasks, "resolve_model", explode)
    task = _StubTask(retries=tasks.MAX_RETRIES)

    with pytest.raises(OperationalError):
        _run(task)

    assert task.retry_calls == [], "no retry left to make"
    assert len(spy["failures"]) == 1
    assert spy["failures"][0][0] == 1


def test_a_deterministic_failure_is_not_retried(monkeypatch, spy, no_existing_run):
    """A bad model fails the same way three more times and bills for each."""
    def explode(*a, **k):
        raise ValueError("unknown model 'NotAModel'")

    monkeypatch.setattr(tasks, "resolve_model", explode)
    task = _StubTask(retries=0)

    with pytest.raises(ValueError):
        _run(task)

    assert task.retry_calls == []
    assert len(spy["failures"]) == 1


def test_a_sandbox_violation_is_not_retried(monkeypatch, spy, no_existing_run):
    """ModelSandboxError means the run is void — repeating it proves nothing."""
    from arep.utils.exceptions import ModelSandboxError

    def explode(*a, **k):
        raise ModelSandboxError("model exceeded its memory limit")

    monkeypatch.setattr(tasks, "resolve_model", explode)
    task = _StubTask(retries=0)

    with pytest.raises(ModelSandboxError):
        _run(task)

    assert task.retry_calls == []
    assert len(spy["failures"]) == 1


# -- Idempotency ----------------------------------------------------------

def test_a_redelivered_task_does_not_run_twice(monkeypatch, spy):
    """acks_late redelivers whenever a worker dies mid-task.

    A second RunRecord for the same (batch, seed) would inflate the batch
    aggregate and report more completed runs than were paid for.
    """
    ran = []

    class _Session:
        def __enter__(self): return self
        def __exit__(self, *a): return False

    class _RepoWithExistingRow:
        def __init__(self, _db): pass
        def get_by_batch_and_seed(self, batch_id, seed):
            return object()          # already recorded
        def save_result(self, *a, **k):
            ran.append("saved")

    monkeypatch.setattr(tasks, "session_scope", lambda: _Session())
    monkeypatch.setattr(tasks, "RunRepository", _RepoWithExistingRow)
    monkeypatch.setattr(tasks, "resolve_model",
                        lambda *a, **k: ran.append("resolved"))

    result = _run(_StubTask())

    assert result["skipped"] == "already_recorded"
    assert ran == [], "the run must not execute or write a second time"
    assert spy["refunds"] == []


def test_the_idempotency_key_is_batch_plus_seed():
    """Two runs of one batch differ only by seed, so both parts are needed."""
    import inspect

    source = inspect.getsource(tasks.execute_single_run)
    assert "get_by_batch_and_seed(batch_id, seed)" in source


def test_repository_lookup_distinguishes_seeds(tmp_path):
    """The guard is only as good as the query behind it."""
    from arep.database import connection as conn_mod
    from arep.database.models import RunRecord
    from arep.database.repository import RunRepository

    db_path = tmp_path / "runs.db"
    conn_mod._engine = None
    conn_mod._SessionFactory = None
    conn_mod.init_database(url=f"sqlite:///{db_path}")

    try:
        with conn_mod.session_scope() as db:
            db.add(RunRecord(
                scenario_id=1, batch_job_id=7, model_name="m", master_seed=1,
                duration=1.0, composite_score=0.5, safety_score=0.5,
                compliance_score=0.5, stability_score=0.5, reactivity_score=0.5,
            ))

        with conn_mod.session_scope() as db:
            repo = RunRepository(db)
            assert repo.get_by_batch_and_seed(7, 1) is not None
            assert repo.get_by_batch_and_seed(7, 2) is None      # other seed
            assert repo.get_by_batch_and_seed(8, 1) is None      # other batch
    finally:
        conn_mod._engine = None
        conn_mod._SessionFactory = None
