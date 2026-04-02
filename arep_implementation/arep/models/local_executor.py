"""
ORION Local Model Executor.

Executes model predictions in the same process.
Provides timing measurement and error handling wrapper.
"""

from __future__ import annotations

from typing import List, Optional

from arep.core.observation import Observation
from arep.core.action import Action
from arep.models.interface import ModelInterface, ModelWrapper
from arep.utils.logging_config import get_logger

logger = get_logger("models.executor")


class LocalModelExecutor:
    """
    Execute models locally in the same Python process.

    Wraps models in ModelWrapper for timing and error handling.
    """

    def __init__(
        self,
        model: ModelInterface,
        timeout_ms: int = 50,
    ):
        self.wrapper = ModelWrapper(model, timeout_ms=timeout_ms)

    def predict(self, observation: Observation) -> Action:
        """Get model prediction."""
        return self.wrapper.predict(observation)

    def reset(self) -> None:
        """Reset model state."""
        self.wrapper.reset()

    def get_stats(self) -> dict:
        """Get timing statistics."""
        return self.wrapper.get_timing_stats()

    @property
    def name(self) -> str:
        return self.wrapper.name
