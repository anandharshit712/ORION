"""
ORION Database Models.

SQLAlchemy ORM models for persistent storage of:
  - Scenarios (parsed scenario metadata)
  - Runs (individual simulation runs)
  - BatchJobs (batch evaluation jobs)
  - Results (evaluation results per run)
"""

from __future__ import annotations

import datetime
from typing import Optional

from sqlalchemy import (
    Column, Integer, Float, String, Boolean, Text, DateTime,
    ForeignKey, JSON, Index, create_engine,
)
from sqlalchemy.orm import (
    DeclarativeBase, relationship, Mapped, mapped_column,
)


class Base(DeclarativeBase):
    """Base class for all ORM models."""
    pass


class ScenarioRecord(Base):
    """Stored scenario definition."""
    __tablename__ = "scenarios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    yaml_content: Mapped[str] = mapped_column(Text, nullable=False)
    duration: Mapped[float] = mapped_column(Float, nullable=False)
    road_type: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    num_traffic_objects: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow
    )

    # Relationships
    runs: Mapped[list["RunRecord"]] = relationship(back_populates="scenario")

    def __repr__(self) -> str:
        return f"<Scenario {self.name} v{self.version}>"


class BatchJobRecord(Base):
    """A batch evaluation job (N runs of one model × one scenario)."""
    __tablename__ = "batch_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scenario_name: Mapped[str] = mapped_column(String(256), nullable=False)
    model_name: Mapped[str] = mapped_column(String(256), nullable=False)
    num_runs: Mapped[int] = mapped_column(Integer, nullable=False)
    master_seed: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending"
    )  # pending, running, completed, failed

    # Aggregated results (populated on completion)
    composite_mean: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    composite_std: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    safety_mean: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    compliance_mean: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    stability_mean: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    reactivity_mean: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    collision_rate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    started_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime, nullable=True
    )
    completed_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime, nullable=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow
    )

    # Relationships
    runs: Mapped[list["RunRecord"]] = relationship(back_populates="batch_job")

    def __repr__(self) -> str:
        return f"<BatchJob {self.model_name}@{self.scenario_name} ({self.status})>"


class RunRecord(Base):
    """Single simulation run with its evaluation result."""
    __tablename__ = "runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scenario_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("scenarios.id"), nullable=False
    )
    batch_job_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("batch_jobs.id"), nullable=True
    )
    model_name: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    master_seed: Mapped[int] = mapped_column(Integer, nullable=False)

    # Termination
    duration: Mapped[float] = mapped_column(Float, nullable=False)
    termination_reason: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    num_timesteps: Mapped[int] = mapped_column(Integer, default=0)

    # Composite score
    composite_score: Mapped[float] = mapped_column(Float, nullable=False)

    # Safety
    safety_score: Mapped[float] = mapped_column(Float, nullable=False)
    collision_occurred: Mapped[bool] = mapped_column(Boolean, default=False)
    min_ttc: Mapped[float] = mapped_column(Float, default=30.0)

    # Compliance
    compliance_score: Mapped[float] = mapped_column(Float, nullable=False)
    speed_compliance: Mapped[float] = mapped_column(Float, default=1.0)

    # Stability
    stability_score: Mapped[float] = mapped_column(Float, nullable=False)
    mean_jerk: Mapped[float] = mapped_column(Float, default=0.0)

    # Reactivity
    reactivity_score: Mapped[float] = mapped_column(Float, nullable=False)
    brake_response_time: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow
    )

    # Relationships
    scenario: Mapped["ScenarioRecord"] = relationship(back_populates="runs")
    batch_job: Mapped[Optional["BatchJobRecord"]] = relationship(back_populates="runs")

    # Indexes for common queries
    __table_args__ = (
        Index("ix_runs_model_scenario", "model_name", "scenario_id"),
        Index("ix_runs_composite", "composite_score"),
    )

    def __repr__(self) -> str:
        return f"<Run {self.model_name} seed={self.master_seed} score={self.composite_score:.3f}>"


class UserRecord(Base):
    """User account for authentication."""
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(256), nullable=False, unique=True, index=True)
    username: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(512), nullable=False)
    full_name: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow
    )
    last_login: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime, nullable=True
    )

    def __repr__(self) -> str:
        return f"<User {self.username} ({self.email})>"
