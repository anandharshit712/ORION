"""
ORION custom exception hierarchy.

All ORION exceptions inherit from AREPError for easy catching.
"""


class AREPError(Exception):
    """Base exception for all ORION errors."""
    pass


# ── Configuration ────────────────────────────────────────────────────────

class ConfigurationError(AREPError):
    """Raised when configuration is invalid or missing."""
    pass


# ── Scenario ─────────────────────────────────────────────────────────────

class ScenarioParseError(AREPError):
    """Raised when a scenario YAML file cannot be parsed."""
    pass


class ScenarioValidationError(AREPError):
    """Raised when a parsed scenario fails validation checks."""
    pass


# ── Model Execution ─────────────────────────────────────────────────────

class ModelTimeoutError(AREPError):
    """Raised when a model's predict() exceeds the allowed timeout."""
    pass


class ModelExecutionError(AREPError):
    """Raised when a model raises an unexpected exception."""
    pass


# ── Simulation ───────────────────────────────────────────────────────────

class SimulationError(AREPError):
    """Raised when the simulation encounters an unrecoverable error."""
    pass


class DeterminismError(AREPError):
    """Raised when a determinism violation is detected."""
    pass


# ── Database ─────────────────────────────────────────────────────────────

class DatabaseError(AREPError):
    """Raised for database connection or query failures."""
    pass
