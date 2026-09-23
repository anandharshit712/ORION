"""
AREP API Pydantic Schemas.

Request/response models for the FastAPI endpoints.
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

# ── Request Models ───────────────────────────────────────────────────────


class RunSingleRequest(BaseModel):
    """Request to run a single simulation."""

    scenario_path: str = Field(..., description="Path to scenario YAML file")
    model_name: str = Field(
        "SimpleLaneKeep", description="Name of built-in model to use"
    )
    master_seed: int = Field(42, description="Random seed")


class RunBatchRequest(BaseModel):
    """Request to run a batch evaluation."""

    scenario_path: str = Field(..., description="Path to scenario YAML file")
    model_name: str = Field(
        "SimpleLaneKeep", description="Name of built-in model to use"
    )
    num_runs: int = Field(100, ge=1, le=10000, description="Number of runs")
    master_seed: int = Field(42, description="Base random seed")


# ── Response Models ──────────────────────────────────────────────────────


class MetricsResponse(BaseModel):
    """Individual evaluation metrics."""

    composite_score: float
    safety_score: float
    compliance_score: float
    stability_score: float
    reactivity_score: float
    collision_occurred: bool
    min_ttc: float
    duration: float
    termination_reason: str
    scenario_name: str
    model_name: str


class AggregatedResponse(BaseModel):
    """Aggregated batch results."""

    num_runs: int
    composite_mean: float
    composite_std: float
    composite_95ci: List[float]
    safety_mean: float
    compliance_mean: float
    stability_mean: float
    reactivity_mean: float
    collision_rate: float
    collision_rate_95ci: List[float]
    min_ttc_mean: float
    mean_duration: float


class BatchResultResponse(BaseModel):
    """Full batch result response."""

    scenario_name: str
    model_name: str
    num_runs: int
    aggregated: AggregatedResponse
    per_run: Optional[List[MetricsResponse]] = None


class ScenarioResponse(BaseModel):
    """Scenario metadata response."""

    id: int
    name: str
    version: str
    description: Optional[str]
    duration: float
    road_type: Optional[str]
    num_traffic_objects: int
    content_hash: str
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class BatchJobResponse(BaseModel):
    """Batch job status response."""

    id: int
    scenario_name: str
    model_name: str
    num_runs: int
    status: str
    composite_mean: Optional[float]
    collision_rate: Optional[float]
    runs_completed: int = 0
    runs_failed: int = 0
    error_message: Optional[str] = None
    created_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class BatchEnqueueResponse(BaseModel):
    """Returned by POST /api/runs/batch — accepted, fan-out happens in worker."""

    batch_id: int
    status: str
    num_runs: int
    enqueued: int
    credits_remaining: int


class BatchProgressResponse(BaseModel):
    """Returned by GET /api/runs/batch/{batch_id}/status — live progress."""

    batch_id: int
    status: str
    total: int
    queued: int
    running: int
    completed: int
    failed: int
    composite_mean: Optional[float] = None
    collision_rate: Optional[float] = None
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class HistogramBin(BaseModel):
    """One bin of the composite-score histogram."""

    lower: float
    upper: float
    count: int


class ScoreDistributionResponse(BaseModel):
    """One metric's distribution across a batch (Phase 2.1).

    The interval and the percentiles answer different questions. The interval
    says how well the mean is pinned down by this sample; the percentiles say
    what the spread actually looks like, which is where a rare catastrophic run
    shows up. A mean alone hides both.
    """

    mean: float
    std: float
    ci_95_low: float
    ci_95_high: float
    percentile_5: float
    percentile_25: float
    percentile_75: float
    percentile_95: float
    minimum: float
    maximum: float
    n: int


class BatchResultsResponse(BaseModel):
    """Returned by GET /api/runs/batch/{batch_id}/results.

    `histogram` is a pre-binned composite histogram so the dashboard does not
    have to pull every run row to draw one.
    """

    batch_id: int
    status: str
    scenario_name: str
    model_name: str
    num_runs: int
    scored_runs: int
    master_seed: int

    distributions: Dict[str, ScoreDistributionResponse]

    collision_rate: float
    collision_rate_ci_95_low: float
    collision_rate_ci_95_high: float

    # Seeds, not row ids: a seed can be re-run, which is the only reason to
    # name the worst run.
    worst_run_seed: Optional[int] = None
    best_run_seed: Optional[int] = None

    histogram: List[HistogramBin] = []

    # True when the sample is too small for the interval to say much. The
    # dashboard shows a caveat rather than a confident-looking number.
    low_confidence: bool = False


class RunRecordResponse(BaseModel):
    """Individual run record response."""

    id: int
    model_name: str
    master_seed: int
    duration: float
    termination_reason: Optional[str]
    composite_score: float
    safety_score: float
    compliance_score: float
    stability_score: float
    reactivity_score: float
    collision_occurred: bool
    min_ttc: float
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class HealthResponse(BaseModel):
    """Health check response."""

    status: str = "healthy"
    version: str = "1.0.0"
    components: dict = {}


class ModelListResponse(BaseModel):
    """Available models response."""

    models: List[str]
