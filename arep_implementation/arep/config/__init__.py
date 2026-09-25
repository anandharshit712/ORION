"""
AREP Configuration Management.

Three-tier priority: environment variables → env-specific YAML → default YAML.
Configuration is immutable after loading.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional
import os

import yaml

from arep.utils.exceptions import ConfigurationError

# ── Dataclasses ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class SimulationConfig:
    """Core simulation parameters."""

    timestep: float = 0.02  # seconds (50 Hz)
    max_duration: float = 60.0  # seconds
    max_steps: int = 3000  # max_duration / timestep
    vehicle_length: float = 4.5  # meters
    vehicle_width: float = 2.0  # meters
    wheelbase: float = 2.7  # meters
    max_velocity: float = 35.0  # m/s (~126 km/h)
    max_acceleration: float = 3.0  # m/s²
    max_deceleration: float = 8.0  # m/s²
    max_steering_angle: float = 0.5  # radians
    collision_tolerance: float = 1e-6  # metres overlap threshold


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

    url: str = "sqlite:///arep.db"
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
    """REST API parameters.

    The rate-limit and CORS fields are security controls (Phase 0.3, defect
    D-03), not performance tuning. ``cors_origins`` must be an explicit
    whitelist outside dev — ``validate_startup()`` refuses to boot on ``*``.
    """

    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: tuple = ("http://localhost:5173", "http://localhost:3000")
    debug: bool = False

    # Rate limiting (slowapi). Empty string disables a specific limit.
    rate_limit_enabled: bool = True
    rate_limit_login: str = "5/minute"  # per IP — credential stuffing
    rate_limit_signup: str = "3/hour"  # per IP — account-farm abuse
    rate_limit_default: str = "120/minute"  # per principal — global API budget
    # "memory://" is per-process: with >1 uvicorn worker each worker keeps its
    # own counters, so the effective limit is N x the configured one. Point this
    # at the Redis the worker queue already uses to make limits global.
    rate_limit_storage_uri: str = "memory://"
    # Only honour X-Forwarded-For when a trusted proxy sets it. Off by default:
    # if it were on and the API were exposed directly, any client could spoof
    # the header and get a fresh rate-limit bucket per request.
    trust_proxy_headers: bool = False


@dataclass(frozen=True)
class PhysicsConfig:
    """Enhanced physics parameters (Level 3)."""

    mode: str = "kinematic"  # "kinematic" or "dynamic"
    vehicle_mass: float = 1500.0  # kg
    yaw_inertia: float = 2500.0  # kg·m²
    cg_height: float = 0.5  # meters (center of gravity)
    track_width: float = 1.6  # meters
    front_weight_ratio: float = 0.55  # fraction on front axle
    drag_coefficient: float = 0.3  # aerodynamic Cd
    frontal_area: float = 2.2  # m²
    rolling_resistance: float = 0.015  # Crr
    surface_friction: float = 1.0  # 1.0=dry, 0.5=wet, 0.2=ice


@dataclass(frozen=True)
class RLConfig:
    """Reinforcement learning environment parameters (Level 3)."""

    max_episode_steps: int = 3000
    reward_preset: str = "balanced"  # balanced, safety_first, speed_demon
    curriculum_enabled: bool = False
    guardian_enabled: bool = False
    guardian_ttc_threshold: float = 0.5  # seconds
    domain_randomization: bool = False
    render_mode: str = ""  # "", "human", "rgb_array"


@dataclass(frozen=True)
class BillingConfig:
    """
    Billing and credit configuration.

    When billing_enabled is False (beta/testing mode):
      - Stripe routes return a friendly "not active in beta" message
      - New orgs receive beta_credits instead of the free-tier 50
      - Credit deduction/refund still work — the system is tested end-to-end
      - An admin top-up endpoint lets you manually replenish beta testers

    To go live: set billing_enabled: true in config and fill in Stripe credentials.
    """

    billing_enabled: bool = False  # flip to True when Stripe is ready
    beta_credits: int = 1000  # credits granted to new orgs in beta mode
    stripe_secret_key: str = ""  # STRIPE_SECRET_KEY env var preferred
    stripe_webhook_secret: str = ""  # STRIPE_WEBHOOK_SECRET env var preferred
    stripe_publishable_key: str = ""  # sent to frontend


@dataclass(frozen=True)
class SandboxConfig:
    """
    Customer-model subprocess sandbox limits (Phase 0.2, defect D-01).

    These are security limits, not performance tuning. Raising them widens the
    blast radius of a hostile model artefact. See docs/ROADMAP.md section 0.2.
    """

    predict_timeout_s: float = 5.0  # hard wall-clock per predict()/reset() call
    total_wallclock_s: float = 300.0  # hard wall-clock budget for a whole run
    cpu_seconds: int = 60  # RLIMIT_CPU for the model process (POSIX)
    memory_bytes: int = 512 * 1024 * 1024  # RLIMIT_AS
    max_file_bytes: int = (
        64 * 1024 * 1024
    )  # RLIMIT_FSIZE - model may write to its tmpdir only
    max_open_files: int = 64  # RLIMIT_NOFILE
    require_network_namespace: bool = (
        False  # True = refuse to run without kernel net isolation
    )

    # ── Docker submission path (Phase 2, D-01 step 2) ────────────────
    # The container runtime to run customer images under. "" uses Docker's
    # default (runc). Set to "runsc" for gVisor, which puts a user-space kernel
    # between the model and the host — the isolation step D-01 was waiting for.
    # Firecracker is reached the same way via a Docker runtime shim.
    container_runtime: str = ""
    container_memory: str = "512m"  # --memory
    container_cpus: str = "1.0"  # --cpus
    container_pids_limit: int = 128  # --pids-limit, caps fork bombs
    container_start_timeout_s: float = 30.0  # wait for the model to answer /health
    # Refuse to run a customer image at all unless a hardened runtime is
    # configured. Off in dev (no gVisor on a laptop); turn it on in production
    # and the API fails loudly rather than running customer code under runc.
    require_hardened_runtime: bool = False

    # The Docker network customer containers join. Empty means Docker's default
    # bridge, which has **unrestricted outbound access** — a customer image can
    # reach the cloud metadata endpoint (169.254.169.254), the database and
    # Redis directly. Measured, not theorised: a container on the default bridge
    # reaches the public internet today.
    #
    # Docker's own `--internal` network blocks egress but also breaks
    # `--publish`, and ORION talks to the model over that published port — so
    # the answer is a named bridge whose egress the operator filters at the
    # host. infrastructure/ documents the rules.
    container_network: str = ""
    # Refuse to run a customer image on the default bridge. Off in dev, on in
    # production: the code cannot install firewall rules, but it can decline to
    # run customer code until someone has.
    require_restricted_network: bool = False


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
    billing: BillingConfig = field(default_factory=BillingConfig)
    sandbox: SandboxConfig = field(default_factory=SandboxConfig)
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
    sim_kwargs: dict[str, Any] = {}
    exec_kwargs: dict[str, Any] = {}
    db_kwargs: dict[str, Any] = {}
    path_kwargs: dict[str, Any] = {}
    api_kwargs: dict[str, Any] = {}
    phys_kwargs: dict[str, Any] = {}
    rl_kwargs: dict[str, Any] = {}
    billing_kwargs: dict[str, Any] = {}
    sandbox_kwargs: dict[str, Any] = {}
    root_kwargs: dict[str, Any] = {"env": env}

    # --- Tier 3: default.yaml ---
    if config_dir:
        _apply_yaml(
            Path(config_dir) / "default.yaml",
            sim_kwargs,
            exec_kwargs,
            db_kwargs,
            path_kwargs,
            api_kwargs,
            phys_kwargs,
            rl_kwargs,
            billing_kwargs,
            sandbox_kwargs,
            root_kwargs,
        )

        # --- Tier 2: env-specific YAML ---
        _apply_yaml(
            Path(config_dir) / f"{env}.yaml",
            sim_kwargs,
            exec_kwargs,
            db_kwargs,
            path_kwargs,
            api_kwargs,
            phys_kwargs,
            rl_kwargs,
            billing_kwargs,
            sandbox_kwargs,
            root_kwargs,
        )

    # --- Tier 1: environment variables ---
    _apply_env_vars(
        sim_kwargs,
        exec_kwargs,
        db_kwargs,
        path_kwargs,
        api_kwargs,
        phys_kwargs,
        rl_kwargs,
        billing_kwargs,
        sandbox_kwargs,
        root_kwargs,
    )

    _config = Config(
        simulation=SimulationConfig(**sim_kwargs),
        execution=ExecutionConfig(**exec_kwargs),
        database=DatabaseConfig(**db_kwargs),
        paths=PathConfig(**path_kwargs),
        api=APIConfig(**api_kwargs),
        physics=PhysicsConfig(**phys_kwargs),
        rl=RLConfig(**rl_kwargs),
        billing=BillingConfig(**billing_kwargs),
        sandbox=SandboxConfig(**sandbox_kwargs),
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
    sim: dict,
    exe: dict,
    db: dict,
    paths: dict,
    api: dict,
    phys: dict,
    rl: dict,
    billing: dict,
    sandbox: dict,
    root: dict,
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
    if "billing" in data and isinstance(data["billing"], dict):
        billing.update(data["billing"])
    if "sandbox" in data and isinstance(data["sandbox"], dict):
        sandbox.update(data["sandbox"])
    for key in ("env", "debug", "enable_visualization"):
        if key in data:
            root[key] = data[key]


def _bool(v: str) -> bool:
    """Parse a truthy env var value."""
    return v.strip().lower() in ("1", "true", "yes", "on")


def _csv_tuple(v: str) -> tuple:
    """Parse a comma-separated env var into a tuple, dropping blanks.

    Used for ORION_ALLOWED_ORIGINS. An empty string yields an empty tuple,
    which means "no cross-origin browser access" — not "allow everything".
    """
    return tuple(item.strip() for item in v.split(",") if item.strip())


_ENV_MAP: dict[str, tuple[str, str, Callable[[str], Any]]] = {
    # AREP_TIMESTEP → simulation.timestep (float)
    "AREP_TIMESTEP": ("sim", "timestep", float),
    "AREP_MAX_DURATION": ("sim", "max_duration", float),
    "AREP_MAX_VELOCITY": ("sim", "max_velocity", float),
    "AREP_NUM_WORKERS": ("exe", "num_workers", int),
    "AREP_MODEL_TIMEOUT_MS": ("exe", "model_timeout_ms", int),
    "AREP_DATABASE_URL": ("db", "url", str),
    "AREP_API_HOST": ("api", "host", str),
    "AREP_API_PORT": ("api", "port", int),
    # API surface hardening (Phase 0.3, D-03) — ops tunables, never secrets
    "ORION_ALLOWED_ORIGINS": ("api", "cors_origins", _csv_tuple),
    "ORION_RATE_LIMIT_ENABLED": ("api", "rate_limit_enabled", _bool),
    "ORION_RATE_LIMIT_LOGIN": ("api", "rate_limit_login", str),
    "ORION_RATE_LIMIT_SIGNUP": ("api", "rate_limit_signup", str),
    "ORION_RATE_LIMIT_DEFAULT": ("api", "rate_limit_default", str),
    "ORION_RATE_LIMIT_STORAGE_URI": ("api", "rate_limit_storage_uri", str),
    "ORION_TRUST_PROXY_HEADERS": ("api", "trust_proxy_headers", _bool),
    "AREP_DEBUG": ("root", "debug", lambda v: v.lower() in ("1", "true", "yes")),
    # Physics
    "AREP_PHYSICS_MODE": ("phys", "mode", str),
    "AREP_SURFACE_FRICTION": ("phys", "surface_friction", float),
    "AREP_VEHICLE_MASS": ("phys", "vehicle_mass", float),
    # Billing — Stripe keys always come from env vars, never YAML
    "STRIPE_SECRET_KEY": ("billing", "stripe_secret_key", str),
    "STRIPE_WEBHOOK_SECRET": ("billing", "stripe_webhook_secret", str),
    "STRIPE_PUBLISHABLE_KEY": ("billing", "stripe_publishable_key", str),
    "AREP_BILLING_ENABLED": (
        "billing",
        "billing_enabled",
        lambda v: v.lower() in ("1", "true", "yes"),
    ),
    "AREP_BETA_CREDITS": ("billing", "beta_credits", int),
    # Sandbox limits (Phase 0.2) — ops tunables, never secrets
    "ORION_SANDBOX_PREDICT_TIMEOUT_S": ("sandbox", "predict_timeout_s", float),
    "ORION_SANDBOX_TOTAL_WALLCLOCK_S": ("sandbox", "total_wallclock_s", float),
    "ORION_SANDBOX_CPU_SECONDS": ("sandbox", "cpu_seconds", int),
    "ORION_SANDBOX_MEMORY_BYTES": ("sandbox", "memory_bytes", int),
    "ORION_SANDBOX_REQUIRE_NETNS": (
        "sandbox",
        "require_network_namespace",
        lambda v: v.lower() in ("1", "true", "yes"),
    ),
    "ORION_CONTAINER_RUNTIME": ("sandbox", "container_runtime", str),
    "ORION_CONTAINER_NETWORK": ("sandbox", "container_network", str),
    "ORION_REQUIRE_RESTRICTED_NETWORK": (
        "sandbox",
        "require_restricted_network",
        lambda v: v.lower() in ("1", "true", "yes"),
    ),
    "ORION_CONTAINER_MEMORY": ("sandbox", "container_memory", str),
    "ORION_CONTAINER_CPUS": ("sandbox", "container_cpus", str),
    "ORION_CONTAINER_PIDS_LIMIT": ("sandbox", "container_pids_limit", int),
    "ORION_REQUIRE_HARDENED_RUNTIME": (
        "sandbox",
        "require_hardened_runtime",
        _bool,
    ),
}


def _apply_env_vars(
    sim: dict,
    exe: dict,
    db: dict,
    paths: dict,
    api: dict,
    phys: dict,
    rl: dict,
    billing: dict,
    sandbox: dict,
    root: dict,
) -> None:
    """Override config values from environment variables."""
    buckets = {
        "sim": sim,
        "exe": exe,
        "db": db,
        "paths": paths,
        "api": api,
        "phys": phys,
        "rl": rl,
        "billing": billing,
        "sandbox": sandbox,
        "root": root,
    }

    for env_var, (bucket, key, converter) in _ENV_MAP.items():
        value = os.environ.get(env_var)
        if value is not None:
            try:
                buckets[bucket][key] = converter(value)
            except (ValueError, TypeError) as e:
                raise ConfigurationError(f"Invalid value for {env_var}={value!r}: {e}")
