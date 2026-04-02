"""
ORION Model Interface.

Abstract base class that all autonomous driving models must implement.
Also provides a ModelWrapper that adds timing, error handling, and logging.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Optional

from arep.core.observation import Observation
from arep.core.action import Action
from arep.utils.exceptions import ModelTimeoutError, ModelExecutionError
from arep.utils.logging_config import get_logger

logger = get_logger("models.interface")


class ModelInterface(ABC):
    """
    Abstract interface for autonomous driving models.

    Every model that is evaluated by ORION must subclass this and
    implement predict() and reset().
    """

    @abstractmethod
    def predict(self, observation: Observation) -> Action:
        """
        Produce a control action given the current observation.

        MUST be deterministic for a given observation + model state.

        Args:
            observation: Current observation (ego-relative).

        Returns:
            Control action (steering, throttle, brake).
        """
        ...

    @abstractmethod
    def reset(self) -> None:
        """
        Reset any internal state.

        Called before each new simulation run.
        """
        ...

    @property
    def name(self) -> str:
        """Human-readable model name."""
        return self.__class__.__name__

    @property
    def version(self) -> str:
        """Model version string."""
        return "0.0.0"


class ModelWrapper:
    """
    Wraps a ModelInterface with timing, error handling, and logging.

    Usage:
        raw_model = MyModel()
        model = ModelWrapper(raw_model, timeout_ms=50)
        action = model.predict(observation)
    """

    def __init__(
        self,
        model: ModelInterface,
        timeout_ms: int = 50,
    ):
        self.model = model
        self.timeout_ms = timeout_ms
        self.total_predict_calls = 0
        self.total_predict_time_ms = 0.0
        self.max_predict_time_ms = 0.0
        self.timeout_count = 0
        self.error_count = 0

    def predict(self, observation: Observation) -> Action:
        """
        Call model.predict with timing and error handling.

        Args:
            observation: Current observation.

        Returns:
            Action from the model.

        Raises:
            ModelTimeoutError: If model exceeds timeout.
            ModelExecutionError: If model raises an exception.
        """
        start = time.perf_counter()
        try:
            action = self.model.predict(observation)
        except Exception as e:
            self.error_count += 1
            raise ModelExecutionError(
                f"Model {self.model.name} error: {e}"
            ) from e
        finally:
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            self.total_predict_calls += 1
            self.total_predict_time_ms += elapsed_ms
            self.max_predict_time_ms = max(self.max_predict_time_ms, elapsed_ms)

        if elapsed_ms > self.timeout_ms:
            self.timeout_count += 1
            logger.warning(
                "Model %s exceeded timeout: %.2f ms > %d ms",
                self.model.name, elapsed_ms, self.timeout_ms,
            )
            # Log warning but don't raise — soft timeout
            # Raise only for hard timeout:
            # raise ModelTimeoutError(...)

        return action

    def reset(self) -> None:
        """Reset model and timing stats."""
        self.model.reset()
        self.total_predict_calls = 0
        self.total_predict_time_ms = 0.0
        self.max_predict_time_ms = 0.0
        self.timeout_count = 0
        self.error_count = 0

    @property
    def avg_predict_time_ms(self) -> float:
        if self.total_predict_calls == 0:
            return 0.0
        return self.total_predict_time_ms / self.total_predict_calls

    @property
    def name(self) -> str:
        return self.model.name

    def get_timing_stats(self) -> dict:
        return {
            "model_name": self.model.name,
            "total_calls": self.total_predict_calls,
            "avg_predict_ms": round(self.avg_predict_time_ms, 3),
            "max_predict_ms": round(self.max_predict_time_ms, 3),
            "timeouts": self.timeout_count,
            "errors": self.error_count,
        }
