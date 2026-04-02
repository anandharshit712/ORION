"""
ORION Database Repository.

CRUD operations for scenarios, runs, and batch jobs.
Provides a clean interface between the evaluation pipeline
and the persistence layer.
"""

from __future__ import annotations

import datetime
from typing import List, Optional

from sqlalchemy.orm import Session

from arep.database.models import ScenarioRecord, RunRecord, BatchJobRecord
from arep.evaluation.composite import EvaluationResult
from arep.statistics.aggregator import AggregatedMetrics
from arep.utils.logging_config import get_logger

logger = get_logger("database.repository")


class ScenarioRepository:
    """CRUD for scenario records."""

    def __init__(self, session: Session):
        self.session = session

    def upsert(
        self,
        name: str,
        version: str,
        content_hash: str,
        yaml_content: str,
        duration: float,
        description: str = "",
        road_type: str = "",
        num_traffic_objects: int = 0,
    ) -> ScenarioRecord:
        """Insert or return existing scenario (by content_hash)."""
        existing = (
            self.session.query(ScenarioRecord)
            .filter_by(content_hash=content_hash)
            .first()
        )
        if existing:
            return existing

        record = ScenarioRecord(
            name=name,
            version=version,
            description=description,
            content_hash=content_hash,
            yaml_content=yaml_content,
            duration=duration,
            road_type=road_type,
            num_traffic_objects=num_traffic_objects,
        )
        self.session.add(record)
        self.session.flush()
        return record

    def get_by_name(self, name: str) -> Optional[ScenarioRecord]:
        return (
            self.session.query(ScenarioRecord)
            .filter_by(name=name)
            .order_by(ScenarioRecord.created_at.desc())
            .first()
        )

    def get_all(self) -> List[ScenarioRecord]:
        return self.session.query(ScenarioRecord).all()


class RunRepository:
    """CRUD for individual simulation run records."""

    def __init__(self, session: Session):
        self.session = session

    def save_result(
        self,
        scenario_id: int,
        result: EvaluationResult,
        batch_job_id: Optional[int] = None,
    ) -> RunRecord:
        """Save an EvaluationResult as a RunRecord."""
        record = RunRecord(
            scenario_id=scenario_id,
            batch_job_id=batch_job_id,
            model_name=result.model_name,
            master_seed=result.master_seed,
            duration=result.duration,
            termination_reason=result.termination_reason,
            composite_score=result.composite_score,
            safety_score=result.safety.safety_score,
            collision_occurred=result.safety.collision_occurred,
            min_ttc=result.safety.min_ttc,
            compliance_score=result.compliance.compliance_score,
            speed_compliance=result.compliance.speed_compliance_fraction,
            stability_score=result.stability.stability_score,
            mean_jerk=result.stability.mean_jerk,
            reactivity_score=result.reactivity.reactivity_score,
            brake_response_time=(
                result.reactivity.brake_response_time
                if result.reactivity.brake_response_time != float("inf")
                else None
            ),
        )
        self.session.add(record)
        self.session.flush()
        return record

    def get_runs_for_model(
        self, model_name: str, limit: int = 100,
    ) -> List[RunRecord]:
        return (
            self.session.query(RunRecord)
            .filter_by(model_name=model_name)
            .order_by(RunRecord.created_at.desc())
            .limit(limit)
            .all()
        )

    def get_runs_for_scenario(
        self, scenario_id: int, limit: int = 100,
    ) -> List[RunRecord]:
        return (
            self.session.query(RunRecord)
            .filter_by(scenario_id=scenario_id)
            .order_by(RunRecord.created_at.desc())
            .limit(limit)
            .all()
        )

    def get_runs_for_batch(self, batch_job_id: int) -> List[RunRecord]:
        return (
            self.session.query(RunRecord)
            .filter_by(batch_job_id=batch_job_id)
            .all()
        )


class BatchJobRepository:
    """CRUD for batch job records."""

    def __init__(self, session: Session):
        self.session = session

    def create(
        self,
        scenario_name: str,
        model_name: str,
        num_runs: int,
        master_seed: int,
    ) -> BatchJobRecord:
        record = BatchJobRecord(
            scenario_name=scenario_name,
            model_name=model_name,
            num_runs=num_runs,
            master_seed=master_seed,
            status="pending",
        )
        self.session.add(record)
        self.session.flush()
        return record

    def mark_running(self, job_id: int) -> None:
        job = self.session.query(BatchJobRecord).get(job_id)
        if job:
            job.status = "running"
            job.started_at = datetime.datetime.utcnow()

    def mark_completed(
        self, job_id: int, aggregated: AggregatedMetrics,
    ) -> None:
        job = self.session.query(BatchJobRecord).get(job_id)
        if job:
            job.status = "completed"
            job.completed_at = datetime.datetime.utcnow()
            job.composite_mean = aggregated.composite_mean
            job.composite_std = aggregated.composite_std
            job.safety_mean = aggregated.safety_mean
            job.compliance_mean = aggregated.compliance_mean
            job.stability_mean = aggregated.stability_mean
            job.reactivity_mean = aggregated.reactivity_mean
            job.collision_rate = aggregated.collision_rate

    def mark_failed(self, job_id: int) -> None:
        job = self.session.query(BatchJobRecord).get(job_id)
        if job:
            job.status = "failed"
            job.completed_at = datetime.datetime.utcnow()

    def get_recent(self, limit: int = 20) -> List[BatchJobRecord]:
        return (
            self.session.query(BatchJobRecord)
            .order_by(BatchJobRecord.created_at.desc())
            .limit(limit)
            .all()
        )

    def get_by_id(self, job_id: int) -> Optional[BatchJobRecord]:
        return self.session.query(BatchJobRecord).get(job_id)
