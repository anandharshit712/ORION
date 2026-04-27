"""
ORION Celery Application.  [Phase 1]

Initialises the Celery application used for async evaluation task execution.
Workers consuming from this app run simulation jobs headlessly and write
results directly to the database.

Configuration is read from environment variables:
  ORION_REDIS_URL  — Celery broker + result backend (default: redis://localhost:6379/0)

Start a worker:
  celery -A arep.worker.celery_app worker --loglevel=info --concurrency=4

Monitor with Flower:
  celery -A arep.worker.celery_app flower --port=5555
"""

from __future__ import annotations

import os

try:
    from celery import Celery
except ImportError:
    raise ImportError(
        "Celery is not installed. Install with: pip install arep[worker]"
    )

from arep.utils.logging_config import get_logger

logger = get_logger("worker.celery_app")

REDIS_URL = os.environ.get("ORION_REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "orion",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["arep.worker.tasks"],
)

celery_app.conf.update(
    # Task serialisation
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",

    # Timezone
    timezone="UTC",
    enable_utc=True,

    # Reliability
    task_acks_late=True,              # re-queue on worker crash
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,     # one task at a time per worker process

    # Result expiry (keep results for 24 hours)
    result_expires=86400,

    # Route all simulation tasks to the 'simulation' queue
    task_routes={
        "arep.worker.tasks.run_single_simulation": {"queue": "simulation"},
        "arep.worker.tasks.run_batch_simulations": {"queue": "simulation"},
    },
)

logger.info(f"Celery app initialised (broker: {REDIS_URL})")
