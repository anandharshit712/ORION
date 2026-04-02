"""
AREP Configuration Management.

Three-tier priority: environment variables → env-specific YAML → default YAML.
Configuration is immutable after loading.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import os

import yaml

from arep.utils.exceptions import ConfigurationError


# ── Dataclasses ──────────────────────────────────────────────────────────

@dataclass(frozen=True)
class SimulationConfig:
    """Core simulation parameters."""
    timestep: float = 0.02               # seconds (50 Hz)
    max_duration: float = 60.0           # seconds
    max_steps: int = 3000                # max_duration / timestep
    vehicle_length: float = 4.5          # meters
    vehicle_width: float = 2.0           # meters
    wheelbase: float = 2.7              # meters
    max_velocity: float = 35.0           # m/s (~126 km/h)
    max_acceleration: float = 3.0        # m/s²
    max_deceleration: float = 8.0        # m/s²
    max_steering_angle: float = 0.5      # radians
    collision_tolerance: float = 1e-6    # metres overlap threshold


@dataclass(frozen=True)
class ExecutionConfig:
    """Batch execution parameters."""
    num_workers: int = 4
    model_timeout_ms: int = 50
    default_num_runs: int = 100
    default_master_seed: int = 42


@dataclass(frozen=True)
class DatabaseConfig:
    """Database connection parameters."""
    url: str = "postgresql://Harshit:Harshit@localhost:5432/orion"
    echo: bool = False
    pool_size: int = 5


@dataclass(frozen=True)
class PathConfig:
    """File system paths."""
    scenarios_dir: str = "scenarios"
    results_dir: str = "results"
    logs_dir: str = "logs"
    models_dir: str = "models"


@dataclass(frozen=True)
class APIConfig:
    """REST API parameters."""
    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: tuple = ("*",)
    debug: bool = False


@dataclass(frozen=True)
class PhysicsConfig:
    """Enhanced physics parameters (Level 3)."""
    mode: str = "kinematic"              # "kinematic" or "dynamic"
    vehicle_mass: float = 1500.0         # kg
    yaw_inertia: float = 2500.0          # kg·m²
    cg_height: float = 0.5              # meters (center of gravity)
    track_width: float = 1.6            # meters
    front_weight_ratio: float = 0.55    # fraction on front axle
    drag_coefficient: float = 0.3       # aerodynamic Cd
    frontal_area: float = 2.2           # m²
    rolling_resistance: float = 0.015   # Crr
    surface_friction: float = 1.0       # 1.0=dry, 0.5=wet, 0.2=ice


@dataclass(frozen=True)
class RLConfig:
    """Reinforcement learning environment parameters (Level 3)."""
    max_episode_steps: int = 3000
    reward_preset: str = "balanced"      # balanced, safety_first, speed_demon
    curriculum_enabled: bool = False
    guardian_enabled: bool = False
    guardian_ttc_threshold: float = 0.5  # seconds
    domain_randomization: bool = False
    render_mode: str = ""                # "", "human", "rgb_array"


@dataclass(frozen=True)
class Config:
    """Root configuration for the entire AREP platform."""
    env: str = "development"
    debug: bool = False
    simulation: SimulationConfig = field(default_factory=SimulationConfig)
    execution: ExecutionConfig = field(default_factory=ExecutionConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    paths: PathConfig = field(default_factory=PathConfig)
    api: APIConfig = field(default_factory=APIConfig)
    physics: PhysicsConfig = field(default_factory=PhysicsConfig)
    rl: RLConfig = field(default_factory=RLConfig)
    enable_visualization: bool = True


# ── Singleton ────────────────────────────────────────────────────────────

_config: Optional[Config] = None


def load_config(
    env: Optional[str] = None,
    config_dir: Optional[str] = None,
) -> Config:
    """
    Load configuration with 3-tier priority.

    Priority (highest to lowest):
      1. Environment variables (AREP_*)
      2. Environment-specific YAML ({config_dir}/{env}.yaml)
      3. Default YAML ({config_dir}/default.yaml)
      4. Hardcoded dataclass defaults

    Args:
        env: Environment name. Defaults to AREP_ENV or "development".
        config_dir: Directory containing YAML config files.

    Returns:
        Immutable Config instance.
    """
    global _config

    env = env or os.environ.get("AREP_ENV", "development")

    # Start with defaults
    sim_kwargs = {}
    exec_kwargs = {}
    db_kwargs = {}
    path_kwargs = {}
    api_kwargs = {}
    phys_kwargs = {}
    rl_kwargs = {}
    root_kwargs = {"env": env}

    # --- Tier 3: default.yaml ---
    if config_dir:
        _apply_yaml(Path(config_dir) / "default.yaml",
                     sim_kwargs, exec_kwargs, db_kwargs,
                     path_kwargs, api_kwargs, phys_kwargs,
                     rl_kwargs, root_kwargs)

        # --- Tier 2: env-specific YAML ---
        _apply_yaml(Path(config_dir) / f"{env}.yaml",
                     sim_kwargs, exec_kwargs, db_kwargs,
                     path_kwargs, api_kwargs, phys_kwargs,
                     rl_kwargs, root_kwargs)

    # --- Tier 1: environment variables ---
    _apply_env_vars(sim_kwargs, exec_kwargs, db_kwargs,
                    path_kwargs, api_kwargs, phys_kwargs,
                    rl_kwargs, root_kwargs)

    _config = Config(
        simulation=SimulationConfig(**sim_kwargs),
        execution=ExecutionConfig(**exec_kwargs),
        database=DatabaseConfig(**db_kwargs),
        paths=PathConfig(**path_kwargs),
        api=APIConfig(**api_kwargs),
        physics=PhysicsConfig(**phys_kwargs),
        rl=RLConfig(**rl_kwargs),
        **root_kwargs,
    )
    return _config


def get_config() -> Config:
    """
    Get the current configuration singleton.

    Returns:
        The loaded Config. Loads defaults if not yet loaded.
    """
    global _config
    if _config is None:
        _config = load_config()
    return _config


def reload_config(**kwargs) -> Config:
    """Reset and reload config. Useful for testing."""
    global _config
    _config = None
    return load_config(**kwargs)


# ── Private helpers ──────────────────────────────────────────────────────

def _apply_yaml(
    filepath: Path,
    sim: dict, exe: dict, db: dict,
    paths: dict, api: dict, phys: dict,
    rl: dict, root: dict,
) -> None:
    """Merge values from a YAML file into kwargs dicts."""
    if not filepath.exists():
        return

    try:
        with open(filepath, "r") as f:
            data = yaml.safe_load(f) or {}
    except yaml.YAMLError as e:
        raise ConfigurationError(f"Invalid YAML in {filepath}: {e}")

    if "simulation" in data and isinstance(data["simulation"], dict):
        sim.update(data["simulation"])
    if "execution" in data and isinstance(data["execution"], dict):
        exe.update(data["execution"])
    if "database" in data and isinstance(data["database"], dict):
        db.update(data["database"])
    if "paths" in data and isinstance(data["paths"], dict):
        paths.update(data["paths"])
    if "api" in data and isinstance(data["api"], dict):
        api.update(data["api"])
    if "physics" in data and isinstance(data["physics"], dict):
        phys.update(data["physics"])
    if "rl" in data and isinstance(data["rl"], dict):
        rl.update(data["rl"])
    for key in ("env", "debug", "enable_visualization"):
        if key in data:
            root[key] = data[key]


_ENV_MAP = {
    # AREP_TIMESTEP → simulation.timestep (float)
    "AREP_TIMESTEP": ("sim", "timestep", float),
    "AREP_MAX_DURATION": ("sim", "max_duration", float),
    "AREP_MAX_VELOCITY": ("sim", "max_velocity", float),
    "AREP_NUM_WORKERS": ("exe", "num_workers", int),
    "AREP_MODEL_TIMEOUT_MS": ("exe", "model_timeout_ms", int),
    "AREP_DATABASE_URL": ("db", "url", str),
    "AREP_API_HOST": ("api", "host", str),
    "AREP_API_PORT": ("api", "port", int),
    "AREP_DEBUG": ("root", "debug", lambda v: v.lower() in ("1", "true", "yes")),
    # Physics
    "AREP_PHYSICS_MODE": ("phys", "mode", str),
    "AREP_SURFACE_FRICTION": ("phys", "surface_friction", float),
    "AREP_VEHICLE_MASS": ("phys", "vehicle_mass", float),
}


def _apply_env_vars(
    sim: dict, exe: dict, db: dict,
    paths: dict, api: dict, phys: dict,
    rl: dict, root: dict,
) -> None:
    """Override config values from environment variables."""
    buckets = {"sim": sim, "exe": exe, "db": db,
               "paths": paths, "api": api, "phys": phys,
               "rl": rl, "root": root}

    for env_var, (bucket, key, converter) in _ENV_MAP.items():
        value = os.environ.get(env_var)
        if value is not None:
            try:
                buckets[bucket][key] = converter(value)
            except (ValueError, TypeError) as e:
                raise ConfigurationError(
                    f"Invalid value for {env_var}={value!r}: {e}"
                )
