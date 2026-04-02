================================================================================
AUTONOMOUS ROBUSTNESS EVALUATION PLATFORM (AREP)
COMPLETE IMPLEMENTATION SPECIFICATION
Version 2.0 - Implementation Grade
================================================================================

Document Purpose:
This document provides COMPLETE implementation-level specifications for every
component, class, method, algorithm, data structure, and system in AREP.

Target Audience:
- Software engineers implementing the system
- DevOps engineers deploying the system
- QA engineers testing the system
- Technical architects reviewing the design

Document Status: IMPLEMENTATION-READY SPECIFICATION

================================================================================
TABLE OF CONTENTS
================================================================================

PART 1: PROJECT STRUCTURE & FOUNDATIONS
    1. Project Directory Structure
    2. Technology Stack & Dependencies
    3. Development Environment Setup
    4. Configuration Management

PART 2: CORE DATA STRUCTURES
    5. State Representations
    6. Observation Types
    7. Action Types
    8. Event Types
    9. Metric Types

PART 3: MATHEMATICAL MODELS & ALGORITHMS
    10. Vehicle Physics Engine
    11. Collision Detection System
    12. Time-To-Collision Calculator
    13. Randomness Management System

PART 4: SIMULATION ENGINE
    14. World State Manager
    15. Simulation Engine Core
    16. Time Management System
    17. Termination Condition Handler

PART 5: SCENARIO SYSTEM
    18. Scenario Definition Format
    19. Scenario Parser & Validator
    20. Scenario Executor
    21. Event System

PART 6: MODEL INTERFACE & EXECUTION
    22. Model Interface Contract
    23. Local Model Executor
    24. Docker Model Sandbox
    25. Model Timeout & Error Handling

PART 7: EVALUATION & METRICS
    26. Metric Collection System
    27. Safety Metrics
    28. Compliance Metrics
    29. Stability Metrics
    30. Reactivity Metrics
    31. Composite Scoring

PART 8: STATISTICAL FRAMEWORK
    32. Batch Execution Engine
    33. Statistical Aggregation
    34. Confidence Interval Calculation
    35. Robustness Curve Generation

PART 9: DATABASE ARCHITECTURE
    36. Database Schema
    37. ORM Models
    38. Migration System
    39. Query Patterns

PART 10: API & WEB INTERFACE
    40. REST API Specification
    41. WebSocket Protocol
    42. Frontend Architecture
    43. Visualization System

PART 11: TESTING & VALIDATION
    44. Unit Test Requirements
    45. Integration Test Suite
    46. Determinism Test Suite
    47. Performance Test Suite

PART 12: DEPLOYMENT & OPERATIONS
    48. Docker Configuration
    49. Kubernetes Architecture
    50. Monitoring & Logging
    51. Security Configuration


================================================================================
PART 1: PROJECT STRUCTURE & FOUNDATIONS
================================================================================

--------------------------------------------------------------------------------
1. PROJECT DIRECTORY STRUCTURE
--------------------------------------------------------------------------------

Complete project structure with all files and directories:

```
arep/
├── README.md
├── LICENSE
├── setup.py
├── requirements.txt
├── requirements-dev.txt
├── docker-compose.yml
├── .env.example
├── .gitignore
├── .dockerignore
│
├── config/
│   ├── __init__.py
│   ├── default.yaml          # Default configuration
│   ├── development.yaml      # Dev overrides
│   ├── production.yaml       # Prod overrides
│   └── test.yaml            # Test overrides
│
├── arep/                     # Main package
│   ├── __init__.py
│   │
│   ├── core/                # Core simulation engine
│   │   ├── __init__.py
│   │   ├── state.py         # WorldState, VehicleState, etc.
│   │   ├── physics.py       # Vehicle physics model
│   │   ├── collision.py     # Collision detection
│   │   ├── time_manager.py  # Deterministic time
│   │   └── random_manager.py # Seeded randomness
│   │
│   ├── simulation/          # Simulation orchestration
│   │   ├── __init__.py
│   │   ├── engine.py        # SimulationEngine
│   │   ├── world.py         # World management
│   │   └── termination.py   # Termination conditions
│   │
│   ├── scenario/            # Scenario system
│   │   ├── __init__.py
│   │   ├── schema.py        # YAML schema definitions
│   │   ├── parser.py        # YAML parser
│   │   ├── validator.py     # Scenario validator
│   │   ├── executor.py      # Scenario executor
│   │   └── events.py        # Event system
│   │
│   ├── models/              # Model interface & execution
│   │   ├── __init__.py
│   │   ├── interface.py     # Abstract model interface
│   │   ├── local_executor.py    # Local model runner
│   │   ├── docker_executor.py   # Docker sandbox runner
│   │   ├── timeout_handler.py   # Timeout management
│   │   └── examples/        # Example models
│   │       ├── pid_controller.py
│   │       ├── pure_pursuit.py
│   │       └── random_agent.py
│   │
│   ├── evaluation/          # Metrics & evaluation
│   │   ├── __init__.py
│   │   ├── collector.py     # MetricCollector
│   │   ├── safety.py        # Safety metrics
│   │   ├── compliance.py    # Compliance metrics
│   │   ├── stability.py     # Stability metrics
│   │   ├── reactivity.py    # Reactivity metrics
│   │   ├── composite.py     # Composite scoring
│   │   └── validator.py     # Metric validation
│   │
│   ├── statistics/          # Statistical analysis
│   │   ├── __init__.py
│   │   ├── aggregator.py    # Statistical aggregation
│   │   ├── confidence.py    # Confidence intervals
│   │   └── curves.py        # Robustness curves
│   │
│   ├── execution/           # Batch execution
│   │   ├── __init__.py
│   │   ├── batch.py         # Batch executor
│   │   ├── worker.py        # Worker process
│   │   ├── pool.py          # Worker pool manager
│   │   └── seed_scheduler.py # Seed generation
│   │
│   ├── database/            # Database layer
│   │   ├── __init__.py
│   │   ├── models.py        # SQLAlchemy ORM models
│   │   ├── schema.sql       # Raw SQL schema
│   │   ├── migrations/      # Alembic migrations
│   │   └── queries.py       # Common queries
│   │
│   ├── api/                 # REST API
│   │   ├── __init__.py
│   │   ├── app.py           # FastAPI application
│   │   ├── routes/
│   │   │   ├── models.py
│   │   │   ├── scenarios.py
│   │   │   ├── evaluations.py
│   │   │   └── results.py
│   │   ├── schemas.py       # Pydantic schemas
│   │   └── websocket.py     # WebSocket handler
│   │
│   ├── visualization/       # Rendering & viz
│   │   ├── __init__.py
│   │   ├── renderer.py      # State renderer
│   │   ├── replay.py        # Replay system
│   │   └── plots.py         # Metric plots
│   │
│   └── utils/               # Utilities
│       ├── __init__.py
│       ├── logging_config.py
│       ├── exceptions.py
│       ├── validators.py
│       └── hashing.py
│
├── scenarios/               # Scenario definitions
│   ├── basic/
│   │   ├── straight_road_empty.yaml
│   │   └── straight_road_lead_vehicle.yaml
│   ├── intermediate/
│   │   ├── highway_merge.yaml
│   │   └── signalized_intersection.yaml
│   └── advanced/
│       ├── unprotected_left_turn.yaml
│       └── pedestrian_dash.yaml
│
├── tests/                   # Test suite
│   ├── __init__.py
│   ├── unit/
│   │   ├── test_physics.py
│   │   ├── test_collision.py
│   │   ├── test_metrics.py
│   │   └── ...
│   ├── integration/
│   │   ├── test_simulation.py
│   │   ├── test_batch.py
│   │   └── ...
│   ├── determinism/
│   │   ├── test_determinism.py
│   │   └── test_reproducibility.py
│   └── performance/
│       ├── test_benchmarks.py
│       └── test_scalability.py
│
├── docker/                  # Docker configs
│   ├── Dockerfile.api
│   ├── Dockerfile.worker
│   ├── Dockerfile.model_sandbox
│   └── nginx.conf
│
├── k8s/                     # Kubernetes configs
│   ├── namespace.yaml
│   ├── api-deployment.yaml
│   ├── worker-deployment.yaml
│   ├── postgres-statefulset.yaml
│   ├── redis-deployment.yaml
│   └── ingress.yaml
│
├── scripts/                 # Utility scripts
│   ├── setup_dev.sh
│   ├── run_tests.sh
│   ├── generate_scenarios.py
│   └── benchmark.py
│
└── docs/                    # Documentation
    ├── architecture.md
    ├── api_reference.md
    ├── scenario_format.md
    └── deployment_guide.md
```

Implementation Notes:
- Use absolute imports: `from arep.core.state import WorldState`
- Each module must have __init__.py for proper package structure
- Configuration follows environment-based overrides
- Tests mirror source structure


--------------------------------------------------------------------------------
2. TECHNOLOGY STACK & DEPENDENCIES
--------------------------------------------------------------------------------

Primary Language: Python 3.11+
Reason: Scientific computing ecosystem, determinism control, broad ML support

Core Dependencies:

```python
# requirements.txt

# Numerical Computing
numpy==1.26.0              # Deterministic arrays, linear algebra
scipy==1.11.0              # Scientific algorithms

# Physics & Geometry
shapely==2.0.2             # Geometric operations (OBB, SAT)
                          # CRITICAL: Pin version for determinism

# Database
sqlalchemy==2.0.23         # ORM
alembic==1.12.1            # Migrations
psycopg2-binary==2.9.9     # PostgreSQL driver

# API
fastapi==0.104.1           # REST API framework
uvicorn==0.24.0            # ASGI server
pydantic==2.5.0            # Data validation
websockets==12.0           # Real-time updates

# Serialization
pyyaml==6.0.1              # Scenario YAML parsing
jsonschema==4.20.0         # Schema validation

# Container Orchestration
docker==6.1.3              # Docker SDK
kubernetes==28.1.0         # K8s SDK (future)

# Job Queue (future distributed mode)
redis==5.0.1               # Task queue
celery==5.3.4              # Distributed tasks

# Monitoring & Logging
prometheus-client==0.19.0  # Metrics export
structlog==23.2.0          # Structured logging

# Testing
pytest==7.4.3              # Test framework
pytest-cov==4.1.0          # Coverage
pytest-benchmark==4.0.0    # Performance tests
hypothesis==6.92.0         # Property-based testing

# Development
black==23.12.0             # Code formatting
ruff==0.1.8                # Linting
mypy==1.7.1                # Type checking
```

Development Dependencies:

```python
# requirements-dev.txt

# Documentation
sphinx==7.2.6
sphinx-rtd-theme==2.0.0

# Profiling
py-spy==0.3.14
memray==1.10.0

# Debugging
ipython==8.18.1
ipdb==0.13.13
```

Version Pinning Strategy:
- ALL dependencies MUST be pinned to exact versions
- Reason: Floating-point determinism requires exact library versions
- Use: `pip freeze > requirements.lock` after testing
- Update: Only after determinism tests pass on new versions


--------------------------------------------------------------------------------
3. DEVELOPMENT ENVIRONMENT SETUP
--------------------------------------------------------------------------------

3.1 System Requirements
```
CPU: 4+ cores (8+ recommended for batch execution)
RAM: 8GB minimum, 16GB recommended
Storage: 20GB for code + data + Docker images
OS: Linux (Ubuntu 22.04+), macOS 12+, Windows 11 with WSL2
Python: 3.11 or 3.12 (NOT 3.13 yet - some deps incompatible)
Docker: 24.0+ (for model sandboxing)
PostgreSQL: 15+ (for database)
```

3.2 Initial Setup Script
```bash
#!/bin/bash
# scripts/setup_dev.sh

set -e  # Exit on error

echo "=== AREP Development Environment Setup ==="

# 1. Check Python version
python_version=$(python3 --version | cut -d' ' -f2)
required_version="3.11"
if [ "$(printf '%s\n' "$required_version" "$python_version" | sort -V | head -n1)" != "$required_version" ]; then
    echo "Error: Python 3.11+ required, found $python_version"
    exit 1
fi

# 2. Create virtual environment
echo "Creating virtual environment..."
python3 -m venv venv
source venv/bin/activate

# 3. Upgrade pip
pip install --upgrade pip setuptools wheel

# 4. Install dependencies
echo "Installing dependencies..."
pip install -r requirements.txt
pip install -r requirements-dev.txt

# 5. Install package in development mode
pip install -e .

# 6. Setup pre-commit hooks
pre-commit install

# 7. Create .env file from template
if [ ! -f .env ]; then
    cp .env.example .env
    echo "Created .env file - please configure"
fi

# 8. Initialize database
echo "Setting up database..."
createdb arep_dev || echo "Database already exists"
alembic upgrade head

# 9. Run determinism validation
echo "Running determinism validation..."
python -m pytest tests/determinism/ -v

echo "=== Setup Complete ==="
echo "Activate environment: source venv/bin/activate"
echo "Run tests: pytest"
echo "Start API: uvicorn arep.api.app:app --reload"
```

3.3 Environment Variables (.env.example)
```bash
# .env.example

# Application
AREP_ENV=development
LOG_LEVEL=INFO
DEBUG=true

# Database
DATABASE_URL=postgresql://localhost:5432/arep_dev
DATABASE_POOL_SIZE=5
DATABASE_MAX_OVERFLOW=10

# Redis (for distributed mode)
REDIS_URL=redis://localhost:6379/0

# API
API_HOST=0.0.0.0
API_PORT=8000
API_WORKERS=1

# Simulation
DEFAULT_TIMESTEP=0.02
MAX_SIMULATION_TIME=60.0
WORKER_POOL_SIZE=4

# Model Execution
MODEL_TIMEOUT_MS=50
DOCKER_MEMORY_LIMIT=512m
DOCKER_CPU_QUOTA=1.0

# Paths
SCENARIOS_DIR=./scenarios
MODELS_DIR=./models
OUTPUT_DIR=./output
LOGS_DIR=./logs

# Security
SECRET_KEY=your-secret-key-change-this
ALLOWED_ORIGINS=http://localhost:3000,http://localhost:8000

# Feature Flags
ENABLE_DOCKER_SANDBOX=false
ENABLE_DISTRIBUTED_MODE=false
ENABLE_VISUALIZATION=true
```

3.4 Docker Compose Setup (Local Development)
```yaml
# docker-compose.yml

version: '3.9'

services:
  postgres:
    image: postgres:15-alpine
    environment:
      POSTGRES_USER: arep
      POSTGRES_PASSWORD: arep_dev
      POSTGRES_DB: arep_dev
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U arep"]
      interval: 5s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 5s
      retries: 5

  api:
    build:
      context: .
      dockerfile: docker/Dockerfile.api
    ports:
      - "8000:8000"
    environment:
      DATABASE_URL: postgresql://arep:arep_dev@postgres:5432/arep_dev
      REDIS_URL: redis://redis:6379/0
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    volumes:
      - ./arep:/app/arep
      - ./scenarios:/app/scenarios
      - ./models:/app/models
    command: uvicorn arep.api.app:app --host 0.0.0.0 --reload

volumes:
  postgres_data:
  redis_data:
```


--------------------------------------------------------------------------------
4. CONFIGURATION MANAGEMENT
--------------------------------------------------------------------------------

4.1 Configuration Schema

```python
# arep/config/__init__.py

from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import yaml
import os


@dataclass
class DatabaseConfig:
    """Database connection configuration."""
    url: str
    pool_size: int = 5
    max_overflow: int = 10
    echo: bool = False  # SQL logging


@dataclass
class SimulationConfig:
    """Core simulation parameters."""
    timestep: float = 0.02  # seconds (50Hz)
    max_duration: float = 60.0  # seconds
    
    # Physics constraints
    max_velocity: float = 35.0  # m/s
    max_acceleration: float = 3.0  # m/s²
    max_deceleration: float = 8.0  # m/s²
    max_steering: float = 0.5  # radians
    
    # Vehicle parameters
    wheelbase: float = 2.7  # meters
    vehicle_width: float = 2.0  # meters
    vehicle_length: float = 4.5  # meters
    
    # Numerical precision
    float_tolerance: float = 1e-9
    collision_tolerance: float = 1e-6


@dataclass
class ExecutionConfig:
    """Batch execution configuration."""
    worker_pool_size: int = 4
    worker_timeout: int = 300  # seconds
    chunk_size: int = 10  # scenarios per chunk
    
    # Model execution
    model_timeout_ms: int = 50
    model_memory_limit_mb: int = 512
    
    # Docker sandbox (if enabled)
    docker_enabled: bool = False
    docker_image: str = "arep-model-sandbox:latest"
    docker_memory_limit: str = "512m"
    docker_cpu_quota: float = 1.0


@dataclass
class PathConfig:
    """File system paths."""
    scenarios_dir: Path
    models_dir: Path
    output_dir: Path
    logs_dir: Path
    cache_dir: Path


@dataclass
class Config:
    """Master configuration object."""
    env: str  # development, production, test
    debug: bool
    
    database: DatabaseConfig
    simulation: SimulationConfig
    execution: ExecutionConfig
    paths: PathConfig
    
    # API config (if running API server)
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_workers: int = 1
    
    # Feature flags
    enable_docker_sandbox: bool = False
    enable_distributed_mode: bool = False
    enable_visualization: bool = True
    
    # Security
    secret_key: str = ""
    allowed_origins: list[str] = None


def load_config(env: Optional[str] = None) -> Config:
    """
    Load configuration with environment-based overrides.
    
    Priority (highest to lowest):
    1. Environment variables
    2. Environment-specific YAML (e.g., production.yaml)
    3. Default YAML (default.yaml)
    """
    if env is None:
        env = os.getenv("AREP_ENV", "development")
    
    # Load default config
    config_dir = Path(__file__).parent
    default_path = config_dir / "default.yaml"
    
    with open(default_path) as f:
        config_dict = yaml.safe_load(f)
    
    # Load environment-specific overrides
    env_path = config_dir / f"{env}.yaml"
    if env_path.exists():
        with open(env_path) as f:
            env_config = yaml.safe_load(f)
            config_dict = merge_dicts(config_dict, env_config)
    
    # Override with environment variables
    config_dict = apply_env_overrides(config_dict)
    
    # Parse into dataclasses
    return parse_config(config_dict, env)


def merge_dicts(base: dict, override: dict) -> dict:
    """Deep merge two dictionaries."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = merge_dicts(result[key], value)
        else:
            result[key] = value
    return result


def apply_env_overrides(config: dict) -> dict:
    """Apply environment variable overrides."""
    # Database
    if db_url := os.getenv("DATABASE_URL"):
        config["database"]["url"] = db_url
    
    # Simulation
    if timestep := os.getenv("DEFAULT_TIMESTEP"):
        config["simulation"]["timestep"] = float(timestep)
    
    # Execution
    if pool_size := os.getenv("WORKER_POOL_SIZE"):
        config["execution"]["worker_pool_size"] = int(pool_size)
    
    # Paths
    if scenarios_dir := os.getenv("SCENARIOS_DIR"):
        config["paths"]["scenarios_dir"] = scenarios_dir
    
    # Feature flags
    if docker_enabled := os.getenv("ENABLE_DOCKER_SANDBOX"):
        config["enable_docker_sandbox"] = docker_enabled.lower() == "true"
    
    return config


def parse_config(config_dict: dict, env: str) -> Config:
    """Parse dictionary into Config dataclass."""
    return Config(
        env=env,
        debug=config_dict.get("debug", False),
        
        database=DatabaseConfig(**config_dict["database"]),
        simulation=SimulationConfig(**config_dict["simulation"]),
        execution=ExecutionConfig(**config_dict["execution"]),
        paths=PathConfig(**{k: Path(v) for k, v in config_dict["paths"].items()}),
        
        api_host=config_dict.get("api", {}).get("host", "0.0.0.0"),
        api_port=config_dict.get("api", {}).get("port", 8000),
        api_workers=config_dict.get("api", {}).get("workers", 1),
        
        enable_docker_sandbox=config_dict.get("enable_docker_sandbox", False),
        enable_distributed_mode=config_dict.get("enable_distributed_mode", False),
        enable_visualization=config_dict.get("enable_visualization", True),
        
        secret_key=config_dict.get("secret_key", ""),
        allowed_origins=config_dict.get("allowed_origins", []),
    )


# Global config instance
_config: Optional[Config] = None


def get_config() -> Config:
    """Get global configuration singleton."""
    global _config
    if _config is None:
        _config = load_config()
    return _config


def reload_config(env: Optional[str] = None):
    """Reload configuration (for testing)."""
    global _config
    _config = load_config(env)
```

4.2 Default Configuration File

```yaml
# config/default.yaml

debug: false

database:
  url: postgresql://localhost:5432/arep_dev
  pool_size: 5
  max_overflow: 10
  echo: false

simulation:
  timestep: 0.02
  max_duration: 60.0
  
  max_velocity: 35.0
  max_acceleration: 3.0
  max_deceleration: 8.0
  max_steering: 0.5
  
  wheelbase: 2.7
  vehicle_width: 2.0
  vehicle_length: 4.5
  
  float_tolerance: 1.0e-9
  collision_tolerance: 1.0e-6

execution:
  worker_pool_size: 4
  worker_timeout: 300
  chunk_size: 10
  
  model_timeout_ms: 50
  model_memory_limit_mb: 512
  
  docker_enabled: false
  docker_image: arep-model-sandbox:latest
  docker_memory_limit: 512m
  docker_cpu_quota: 1.0

paths:
  scenarios_dir: ./scenarios
  models_dir: ./models
  output_dir: ./output
  logs_dir: ./logs
  cache_dir: ./.cache

api:
  host: 0.0.0.0
  port: 8000
  workers: 1

enable_docker_sandbox: false
enable_distributed_mode: false
enable_visualization: true

secret_key: development-secret-key-change-in-production
allowed_origins:
  - http://localhost:3000
  - http://localhost:8000
```

4.3 Production Configuration

```yaml
# config/production.yaml

debug: false

database:
  pool_size: 20
  max_overflow: 40
  echo: false

execution:
  worker_pool_size: 16
  docker_enabled: true

api:
  workers: 4

enable_docker_sandbox: true
enable_distributed_mode: true

# Secret key must be set via environment variable in production
# DATABASE_URL must be set via environment variable
```


================================================================================
PART 2: CORE DATA STRUCTURES
================================================================================

--------------------------------------------------------------------------------
5. STATE REPRESENTATIONS
--------------------------------------------------------------------------------

All state representations must be deterministic, serializable, and
suitable for both simulation and database storage.

```python
# arep/core/state.py

from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any, Tuple
from enum import Enum
import numpy as np
import json


class ObjectType(Enum):
    """Types of dynamic objects in simulation."""
    CAR = "car"
    TRUCK = "truck"
    MOTORCYCLE = "motorcycle"
    BICYCLE = "bicycle"
    PEDESTRIAN = "pedestrian"
    OBSTACLE = "obstacle"  # Static obstacle


class TrafficLightState(Enum):
    """Traffic signal states."""
    RED = "red"
    YELLOW = "yellow"
    GREEN = "green"
    NONE = "none"  # No traffic light


class TerminationReason(Enum):
    """Reasons for simulation termination."""
    NONE = "none"  # Still running
    SUCCESS = "success"  # Completed successfully
    COLLISION = "collision"
    OFF_ROAD = "off_road"
    TIMEOUT = "timeout"
    MODEL_ERROR = "model_error"
    MODEL_TIMEOUT = "model_timeout"
    INVALID_ACTION = "invalid_action"


@dataclass
class Vector2D:
    """2D vector with deterministic operations."""
    x: float
    y: float
    
    def __add__(self, other: 'Vector2D') -> 'Vector2D':
        return Vector2D(self.x + other.x, self.y + other.y)
    
    def __sub__(self, other: 'Vector2D') -> 'Vector2D':
        return Vector2D(self.x - other.x, self.y - other.y)
    
    def __mul__(self, scalar: float) -> 'Vector2D':
        return Vector2D(self.x * scalar, self.y * scalar)
    
    def norm(self) -> float:
        """Euclidean norm."""
        return np.sqrt(self.x**2 + self.y**2)
    
    def normalize(self) -> 'Vector2D':
        """Return unit vector."""
        n = self.norm()
        if n < 1e-10:
            return Vector2D(0.0, 0.0)
        return Vector2D(self.x / n, self.y / n)
    
    def dot(self, other: 'Vector2D') -> float:
        """Dot product."""
        return self.x * other.x + self.y * other.y
    
    def to_array(self) -> np.ndarray:
        """Convert to numpy array."""
        return np.array([self.x, self.y], dtype=np.float64)
    
    @staticmethod
    def from_array(arr: np.ndarray) -> 'Vector2D':
        """Create from numpy array."""
        return Vector2D(float(arr[0]), float(arr[1]))


@dataclass
class VehicleState:
    """
    Complete state of a vehicle in the simulation.
    
    This is the fundamental state representation for all vehicles
    (ego and dynamic objects).
    
    Coordinate System:
    - x: forward (meters)
    - y: lateral (meters, positive = right)
    - theta: heading (radians, 0 = east, counter-clockwise positive)
    """
    # Position and orientation
    position: Vector2D
    heading: float  # radians
    
    # Velocity (scalar speed, not vector)
    velocity: float  # m/s
    
    # Acceleration (for physics updates)
    acceleration: float = 0.0  # m/s²
    
    # Vehicle geometry (for collision detection)
    length: float = 4.5  # meters
    width: float = 2.0   # meters
    wheelbase: float = 2.7  # meters
    
    # Object type
    object_type: ObjectType = ObjectType.CAR
    
    # Unique identifier
    object_id: str = "ego"
    
    def get_velocity_vector(self) -> Vector2D:
        """Get velocity as 2D vector."""
        return Vector2D(
            self.velocity * np.cos(self.heading),
            self.velocity * np.sin(self.heading)
        )
    
    def get_front_center(self) -> Vector2D:
        """Get position of front center of vehicle."""
        offset = self.length / 2.0
        return Vector2D(
            self.position.x + offset * np.cos(self.heading),
            self.position.y + offset * np.sin(self.heading)
        )
    
    def get_rear_center(self) -> Vector2D:
        """Get position of rear center of vehicle."""
        offset = self.length / 2.0
        return Vector2D(
            self.position.x - offset * np.cos(self.heading),
            self.position.y - offset * np.sin(self.heading)
        )
    
    def get_bounding_box_corners(self) -> List[Vector2D]:
        """
        Get 4 corners of oriented bounding box.
        
        Returns corners in deterministic order:
        [front-right, front-left, rear-left, rear-right]
        
        This order is CRITICAL for determinism in collision detection.
        """
        hl = self.length / 2.0  # half length
        hw = self.width / 2.0   # half width
        
        # Local corners (vehicle frame)
        local_corners = [
            (hl, -hw),   # front-right
            (hl, hw),    # front-left
            (-hl, hw),   # rear-left
            (-hl, -hw),  # rear-right
        ]
        
        # Rotation matrix
        cos_h = np.cos(self.heading)
        sin_h = np.sin(self.heading)
        
        # Transform to global frame
        global_corners = []
        for lx, ly in local_corners:
            gx = self.position.x + lx * cos_h - ly * sin_h
            gy = self.position.y + lx * sin_h + ly * cos_h
            global_corners.append(Vector2D(gx, gy))
        
        return global_corners
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "position": {"x": self.position.x, "y": self.position.y},
            "heading": self.heading,
            "velocity": self.velocity,
            "acceleration": self.acceleration,
            "length": self.length,
            "width": self.width,
            "wheelbase": self.wheelbase,
            "object_type": self.object_type.value,
            "object_id": self.object_id,
        }
    
    @staticmethod
    def from_dict(data: Dict[str, Any]) -> 'VehicleState':
        """Deserialize from dictionary."""
        return VehicleState(
            position=Vector2D(**data["position"]),
            heading=data["heading"],
            velocity=data["velocity"],
            acceleration=data.get("acceleration", 0.0),
            length=data.get("length", 4.5),
            width=data.get("width", 2.0),
            wheelbase=data.get("wheelbase", 2.7),
            object_type=ObjectType(data.get("object_type", "car")),
            object_id=data.get("object_id", "unknown"),
        )
    
    def copy(self) -> 'VehicleState':
        """Create deep copy."""
        return VehicleState(
            position=Vector2D(self.position.x, self.position.y),
            heading=self.heading,
            velocity=self.velocity,
            acceleration=self.acceleration,
            length=self.length,
            width=self.width,
            wheelbase=self.wheelbase,
            object_type=self.object_type,
            object_id=self.object_id,
        )


@dataclass
class TrafficLightInfo:
    """Traffic light state and position."""
    state: TrafficLightState
    position: Vector2D
    stop_line_position: Vector2D  # Where vehicles must stop
    light_id: str
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "state": self.state.value,
            "position": {"x": self.position.x, "y": self.position.y},
            "stop_line_position": {
                "x": self.stop_line_position.x,
                "y": self.stop_line_position.y
            },
            "light_id": self.light_id,
        }


@dataclass
class LaneInfo:
    """Lane structure information."""
    lane_id: str
    centerline_points: List[Vector2D]  # Ordered points defining centerline
    width: float  # meters
    speed_limit: float  # m/s
    
    def get_closest_point(self, position: Vector2D) -> Tuple[Vector2D, float]:
        """
        Find closest point on lane centerline to given position.
        
        Returns:
            (closest_point, lateral_offset)
            lateral_offset > 0 means position is to the right of lane
        """
        min_dist = float('inf')
        closest_point = self.centerline_points[0]
        
        for point in self.centerline_points:
            dist = (point - position).norm()
            if dist < min_dist:
                min_dist = dist
                closest_point = point
        
        # Compute lateral offset (simplified - assumes straight segments)
        # For production, use more sophisticated projection
        return closest_point, min_dist
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "lane_id": self.lane_id,
            "centerline_points": [
                {"x": p.x, "y": p.y} for p in self.centerline_points
            ],
            "width": self.width,
            "speed_limit": self.speed_limit,
        }


@dataclass
class WorldState:
    """
    Complete state of the simulation world at a single timestep.
    
    This is the authoritative state object. It contains ALL information
    needed to:
    - Continue simulation
    - Render visualization
    - Compute metrics
    - Store in database
    - Replay simulation
    
    CRITICAL: This object is IMMUTABLE during observation/rendering.
    Only SimulationEngine may mutate it.
    """
    # Simulation time
    sim_time: float  # seconds since start
    timestep_count: int  # number of timesteps elapsed
    
    # Ego vehicle
    ego_vehicle: VehicleState
    
    # Dynamic objects (ordered list for determinism)
    dynamic_objects: List[VehicleState] = field(default_factory=list)
    
    # Traffic lights (ordered list for determinism)
    traffic_lights: List[TrafficLightInfo] = field(default_factory=list)
    
    # Lane graph
    lanes: List[LaneInfo] = field(default_factory=list)
    
    # Environment parameters
    weather_condition: str = "clear"  # clear, rain, fog
    visibility: float = 1000.0  # meters
    
    # Termination status
    is_terminated: bool = False
    termination_reason: TerminationReason = TerminationReason.NONE
    
    # Collision flag
    has_collision: bool = False
    collision_object_id: Optional[str] = None
    collision_time: Optional[float] = None
    
    # Last action applied (for tracking)
    last_action: Optional['Action'] = None
    
    def get_object_by_id(self, object_id: str) -> Optional[VehicleState]:
        """Find dynamic object by ID."""
        for obj in self.dynamic_objects:
            if obj.object_id == object_id:
                return obj
        return None
    
    def get_nearest_traffic_light(self) -> Optional[TrafficLightInfo]:
        """Get traffic light nearest to ego vehicle."""
        if not self.traffic_lights:
            return None
        
        min_dist = float('inf')
        nearest = None
        
        for light in self.traffic_lights:
            dist = (light.position - self.ego_vehicle.position).norm()
            if dist < min_dist:
                min_dist = dist
                nearest = light
        
        return nearest
    
    def get_current_lane(self) -> Optional[LaneInfo]:
        """Get lane ego vehicle is currently in."""
        if not self.lanes:
            return None
        
        # Find lane with smallest lateral offset
        min_offset = float('inf')
        current_lane = None
        
        for lane in self.lanes:
            _, offset = lane.get_closest_point(self.ego_vehicle.position)
            if offset < min_offset:
                min_offset = offset
                current_lane = lane
        
        return current_lane
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize complete state to dictionary."""
        return {
            "sim_time": self.sim_time,
            "timestep_count": self.timestep_count,
            "ego_vehicle": self.ego_vehicle.to_dict(),
            "dynamic_objects": [obj.to_dict() for obj in self.dynamic_objects],
            "traffic_lights": [light.to_dict() for light in self.traffic_lights],
            "lanes": [lane.to_dict() for lane in self.lanes],
            "weather_condition": self.weather_condition,
            "visibility": self.visibility,
            "is_terminated": self.is_terminated,
            "termination_reason": self.termination_reason.value,
            "has_collision": self.has_collision,
            "collision_object_id": self.collision_object_id,
            "collision_time": self.collision_time,
            "last_action": self.last_action.to_dict() if self.last_action else None,
        }
    
    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), indent=2)
    
    def copy(self) -> 'WorldState':
        """Create deep copy of world state."""
        return WorldState(
            sim_time=self.sim_time,
            timestep_count=self.timestep_count,
            ego_vehicle=self.ego_vehicle.copy(),
            dynamic_objects=[obj.copy() for obj in self.dynamic_objects],
            traffic_lights=[
                TrafficLightInfo(
                    state=light.state,
                    position=Vector2D(light.position.x, light.position.y),
                    stop_line_position=Vector2D(
                        light.stop_line_position.x,
                        light.stop_line_position.y
                    ),
                    light_id=light.light_id
                )
                for light in self.traffic_lights
            ],
            lanes=[  # Lanes are immutable, can share reference
                lane for lane in self.lanes
            ],
            weather_condition=self.weather_condition,
            visibility=self.visibility,
            is_terminated=self.is_terminated,
            termination_reason=self.termination_reason,
            has_collision=self.has_collision,
            collision_object_id=self.collision_object_id,
            collision_time=self.collision_time,
            last_action=self.last_action.copy() if self.last_action else None,
        )
```

Implementation Notes:
- All floats are Python float (IEEE 754 double precision)
- Vector2D uses explicit float64 for numpy conversions
- Bounding box corners MUST be in fixed order for determinism
- WorldState.copy() creates deep copies to prevent mutation bugs
- Serialization must be deterministic (dicts maintain insertion order in Python 3.7+)


--------------------------------------------------------------------------------
6. OBSERVATION TYPES
--------------------------------------------------------------------------------

Models receive observations in standardized formats.

```python
# arep/core/observation.py

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
import numpy as np
from arep.core.state import (
    WorldState, VehicleState, TrafficLightState,
    Vector2D, ObjectType
)


@dataclass
class ObjectObservation:
    """
    Observation of a single dynamic object relative to ego vehicle.
    
    All positions and velocities are in ego vehicle's reference frame:
    - x: forward from ego (positive = ahead)
    - y: lateral from ego (positive = right)
    """
    # Relative position
    relative_x: float  # meters (positive = ahead)
    relative_y: float  # meters (positive = right)
    
    # Relative velocity
    relative_vx: float  # m/s (positive = approaching if ahead)
    relative_vy: float  # m/s (positive = moving right)
    
    # Object properties
    object_type: ObjectType
    length: float  # meters
    width: float   # meters
    
    # Distance metrics
    distance: float  # Euclidean distance to ego
    
    # Unique ID (for tracking across timesteps)
    object_id: str
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "relative_x": self.relative_x,
            "relative_y": self.relative_y,
            "relative_vx": self.relative_vx,
            "relative_vy": self.relative_vy,
            "object_type": self.object_type.value,
            "length": self.length,
            "width": self.width,
            "distance": self.distance,
            "object_id": self.object_id,
        }
    
    def to_array(self) -> np.ndarray:
        """
        Convert to fixed-size numpy array for ML models.
        
        Format: [rel_x, rel_y, rel_vx, rel_vy, length, width, distance, type_encoding]
        type_encoding: car=0, truck=1, motorcycle=2, bicycle=3, pedestrian=4
        """
        type_encoding = {
            ObjectType.CAR: 0.0,
            ObjectType.TRUCK: 1.0,
            ObjectType.MOTORCYCLE: 2.0,
            ObjectType.BICYCLE: 3.0,
            ObjectType.PEDESTRIAN: 4.0,
            ObjectType.OBSTACLE: 5.0,
        }
        
        return np.array([
            self.relative_x,
            self.relative_y,
            self.relative_vx,
            self.relative_vy,
            self.length,
            self.width,
            self.distance,
            type_encoding[self.object_type],
        ], dtype=np.float32)


@dataclass
class Observation:
    """
    Complete observation provided to model for decision-making.
    
    This is the standardized interface between simulation and model.
    Models receive this observation and must return an Action.
    
    Design Principles:
    - Complete: Contains all information model needs
    - Standardized: Fixed schema across all scenarios
    - Efficient: Compact representation for fast inference
    - Interpretable: Human-readable structure
    """
    # === EGO STATE ===
    ego_speed: float  # m/s
    ego_acceleration: float  # m/s²
    ego_heading_rate: float  # rad/s (rate of change of heading)
    
    # === LANE INFORMATION ===
    lane_offset: float  # meters from lane center (positive = right)
    lane_heading_error: float  # radians from lane heading
    lane_width: float  # meters
    distance_to_lane_end: float  # meters
    
    # === NEARBY OBJECTS ===
    # Sorted by distance, up to MAX_OBJECTS
    objects: List[ObjectObservation] = field(default_factory=list)
    
    # === TRAFFIC SIGNALS ===
    nearest_traffic_light_state: TrafficLightState = TrafficLightState.NONE
    distance_to_traffic_light: float = float('inf')  # meters
    distance_to_stop_line: float = float('inf')  # meters
    
    # === SPEED LIMITS ===
    current_speed_limit: float = 30.0  # m/s (default)
    
    # === TIME ===
    sim_time: float = 0.0  # seconds since start
    
    # Configuration
    MAX_OBJECTS: int = 10  # Maximum number of objects in observation
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "ego_speed": self.ego_speed,
            "ego_acceleration": self.ego_acceleration,
            "ego_heading_rate": self.ego_heading_rate,
            "lane_offset": self.lane_offset,
            "lane_heading_error": self.lane_heading_error,
            "lane_width": self.lane_width,
            "distance_to_lane_end": self.distance_to_lane_end,
            "objects": [obj.to_dict() for obj in self.objects],
            "nearest_traffic_light_state": self.nearest_traffic_light_state.value,
            "distance_to_traffic_light": self.distance_to_traffic_light,
            "distance_to_stop_line": self.distance_to_stop_line,
            "current_speed_limit": self.current_speed_limit,
            "sim_time": self.sim_time,
        }
    
    def to_vector(self) -> np.ndarray:
        """
        Convert to flat numpy vector for ML models.
        
        This is a FIXED-SIZE representation suitable for neural networks.
        
        Vector structure (total size: 13 + MAX_OBJECTS * 8):
        [0:13] - Ego and environment features
        [13:13+MAX_OBJECTS*8] - Object features (padded with zeros)
        
        Returns:
            numpy array of shape (93,) for MAX_OBJECTS=10
        """
        # Ego features (13 values)
        ego_features = np.array([
            self.ego_speed,
            self.ego_acceleration,
            self.ego_heading_rate,
            self.lane_offset,
            self.lane_heading_error,
            self.lane_width,
            self.distance_to_lane_end,
            self._encode_traffic_light_state(),
            self.distance_to_traffic_light,
            self.distance_to_stop_line,
            self.current_speed_limit,
            self.sim_time,
            float(len(self.objects)),  # number of objects present
        ], dtype=np.float32)
        
        # Object features (8 values per object, padded to MAX_OBJECTS)
        object_features = np.zeros(self.MAX_OBJECTS * 8, dtype=np.float32)
        for i, obj in enumerate(self.objects[:self.MAX_OBJECTS]):
            object_features[i*8:(i+1)*8] = obj.to_array()
        
        return np.concatenate([ego_features, object_features])
    
    def _encode_traffic_light_state(self) -> float:
        """Encode traffic light state as float."""
        encoding = {
            TrafficLightState.NONE: 0.0,
            TrafficLightState.GREEN: 1.0,
            TrafficLightState.YELLOW: 2.0,
            TrafficLightState.RED: 3.0,
        }
        return encoding[self.nearest_traffic_light_state]
    
    @staticmethod
    def from_world_state(
        world: WorldState,
        previous_world: Optional[WorldState] = None
    ) -> 'Observation':
        """
        Convert WorldState to Observation.
        
        This is the main observation generation function used by simulation.
        
        Args:
            world: Current world state
            previous_world: Previous world state (for computing derivatives)
        
        Returns:
            Observation object
        """
        ego = world.ego_vehicle
        
        # Compute heading rate (derivative of heading)
        heading_rate = 0.0
        if previous_world is not None:
            dt = world.sim_time - previous_world.sim_time
            if dt > 1e-6:
                dheading = ego.heading - previous_world.ego_vehicle.heading
                # Wrap angle difference to [-pi, pi]
                dheading = np.arctan2(np.sin(dheading), np.cos(dheading))
                heading_rate = dheading / dt
        
        # Get current lane information
        current_lane = world.get_current_lane()
        if current_lane is not None:
            closest_point, lane_offset = current_lane.get_closest_point(ego.position)
            # Compute heading error (simplified)
            # For production: use tangent vector at closest point
            lane_heading_error = 0.0  # Placeholder
            lane_width = current_lane.width
            speed_limit = current_lane.speed_limit
            distance_to_lane_end = 1000.0  # Placeholder - compute from centerline
        else:
            lane_offset = 0.0
            lane_heading_error = 0.0
            lane_width = 3.5  # default
            speed_limit = 30.0  # default
            distance_to_lane_end = 1000.0
        
        # Get traffic light information
        nearest_light = world.get_nearest_traffic_light()
        if nearest_light is not None:
            traffic_light_state = nearest_light.state
            distance_to_light = (nearest_light.position - ego.position).norm()
            distance_to_stop_line = (
                nearest_light.stop_line_position - ego.position
            ).norm()
        else:
            traffic_light_state = TrafficLightState.NONE
            distance_to_light = float('inf')
            distance_to_stop_line = float('inf')
        
        # Convert dynamic objects to relative observations
        object_observations = []
        for obj in world.dynamic_objects:
            obj_obs = _convert_to_relative_observation(ego, obj)
            object_observations.append(obj_obs)
        
        # Sort by distance and limit to MAX_OBJECTS
        object_observations.sort(key=lambda o: o.distance)
        object_observations = object_observations[:Observation.MAX_OBJECTS]
        
        return Observation(
            ego_speed=ego.velocity,
            ego_acceleration=ego.acceleration,
            ego_heading_rate=heading_rate,
            lane_offset=lane_offset,
            lane_heading_error=lane_heading_error,
            lane_width=lane_width,
            distance_to_lane_end=distance_to_lane_end,
            objects=object_observations,
            nearest_traffic_light_state=traffic_light_state,
            distance_to_traffic_light=distance_to_light,
            distance_to_stop_line=distance_to_stop_line,
            current_speed_limit=speed_limit,
            sim_time=world.sim_time,
        )


def _convert_to_relative_observation(
    ego: VehicleState,
    obj: VehicleState
) -> ObjectObservation:
    """
    Convert object to ego-relative observation.
    
    Transforms object position and velocity from global frame to
    ego vehicle's reference frame.
    """
    # Global position difference
    dx_global = obj.position.x - ego.position.x
    dy_global = obj.position.y - ego.position.y
    
    # Rotate to ego frame
    cos_ego = np.cos(-ego.heading)  # Negative for inverse rotation
    sin_ego = np.sin(-ego.heading)
    
    relative_x = dx_global * cos_ego - dy_global * sin_ego
    relative_y = dx_global * sin_ego + dy_global * cos_ego
    
    # Velocity in global frame
    obj_vx_global = obj.velocity * np.cos(obj.heading)
    obj_vy_global = obj.velocity * np.sin(obj.heading)
    ego_vx_global = ego.velocity * np.cos(ego.heading)
    ego_vy_global = ego.velocity * np.sin(ego.heading)
    
    # Relative velocity in global frame
    dvx_global = obj_vx_global - ego_vx_global
    dvy_global = obj_vy_global - ego_vy_global
    
    # Rotate relative velocity to ego frame
    relative_vx = dvx_global * cos_ego - dvy_global * sin_ego
    relative_vy = dvx_global * sin_ego + dvy_global * cos_ego
    
    # Distance
    distance = np.sqrt(relative_x**2 + relative_y**2)
    
    return ObjectObservation(
        relative_x=relative_x,
        relative_y=relative_y,
        relative_vx=relative_vx,
        relative_vy=relative_vy,
        object_type=obj.object_type,
        length=obj.length,
        width=obj.width,
        distance=distance,
        object_id=obj.object_id,
    )
```

Implementation Notes:
- Observation.to_vector() produces FIXED-SIZE arrays for ML models
- Object observations are sorted by distance for consistency
- MAX_OBJECTS=10 is configurable but must be consistent across system
- Missing objects are zero-padded in vector representation
- All angles wrapped to [-π, π] for consistency


--------------------------------------------------------------------------------
7. ACTION TYPES
--------------------------------------------------------------------------------

Models output actions in standardized format.

```python
# arep/core/action.py

from dataclasses import dataclass
from typing import Dict, Any
import numpy as np


@dataclass
class Action:
    """
    Control action from model to simulation.
    
    This is the standardized output interface for all models.
    
    Control Semantics:
    - steering: Normalized steering angle [-1, 1]
        -1 = maximum left turn
         0 = straight
        +1 = maximum right turn
        Maps to actual steering angle via: delta = steering * max_steering
    
    - throttle: Normalized throttle [0, 1]
        0 = no throttle
        1 = maximum throttle
        Maps to acceleration via: a = throttle * max_acceleration
    
    - brake: Normalized brake [0, 1]
        0 = no brake
        1 = maximum brake
        Maps to deceleration via: a = -brake * max_deceleration
    
    Conflict Resolution:
    - If both throttle and brake are nonzero, brake takes precedence
    - Actual acceleration = throttle * max_accel - brake * max_decel
    """
    steering: float  # [-1, 1]
    throttle: float  # [0, 1]
    brake: float     # [0, 1]
    
    def __post_init__(self):
        """Validate action values."""
        self._validate()
    
    def _validate(self):
        """Check action values are in valid ranges."""
        if not (-1.0 <= self.steering <= 1.0):
            raise ValueError(
                f"Steering must be in [-1, 1], got {self.steering}"
            )
        if not (0.0 <= self.throttle <= 1.0):
            raise ValueError(
                f"Throttle must be in [0, 1], got {self.throttle}"
            )
        if not (0.0 <= self.brake <= 1.0):
            raise ValueError(
                f"Brake must be in [0, 1], got {self.brake}"
            )
    
    def clamp(self) -> 'Action':
        """
        Clamp values to valid range (for safety).
        Use this when model might produce slightly out-of-range values.
        """
        return Action(
            steering=np.clip(self.steering, -1.0, 1.0),
            throttle=np.clip(self.throttle, 0.0, 1.0),
            brake=np.clip(self.brake, 0.0, 1.0),
        )
    
    def get_acceleration(
        self,
        max_acceleration: float,
        max_deceleration: float
    ) -> float:
        """
        Convert throttle/brake to actual acceleration.
        
        Args:
            max_acceleration: Maximum acceleration (m/s²)
            max_deceleration: Maximum deceleration (m/s², positive value)
        
        Returns:
            Actual acceleration in m/s² (negative for braking)
        """
        accel_from_throttle = self.throttle * max_acceleration
        accel_from_brake = -self.brake * max_deceleration
        
        # Brake takes precedence if both are active
        if self.brake > 0.01:  # Small threshold to avoid floating point issues
            return accel_from_brake
        else:
            return accel_from_throttle
    
    def get_steering_angle(self, max_steering: float) -> float:
        """
        Convert normalized steering to actual angle.
        
        Args:
            max_steering: Maximum steering angle (radians)
        
        Returns:
            Actual steering angle in radians
        """
        return self.steering * max_steering
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "steering": self.steering,
            "throttle": self.throttle,
            "brake": self.brake,
        }
    
    def to_array(self) -> np.ndarray:
        """Convert to numpy array."""
        return np.array([self.steering, self.throttle, self.brake], dtype=np.float32)
    
    @staticmethod
    def from_dict(data: Dict[str, Any]) -> 'Action':
        """Deserialize from dictionary."""
        return Action(
            steering=data["steering"],
            throttle=data.get("throttle", 0.0),
            brake=data.get("brake", 0.0),
        )
    
    @staticmethod
    def from_array(arr: np.ndarray) -> 'Action':
        """Create from numpy array."""
        return Action(
            steering=float(arr[0]),
            throttle=float(arr[1]) if len(arr) > 1 else 0.0,
            brake=float(arr[2]) if len(arr) > 2 else 0.0,
        )
    
    @staticmethod
    def zero() -> 'Action':
        """Create zero action (no steering, no throttle, no brake)."""
        return Action(steering=0.0, throttle=0.0, brake=0.0)
    
    @staticmethod
    def emergency_brake() -> 'Action':
        """Create emergency brake action."""
        return Action(steering=0.0, throttle=0.0, brake=1.0)
    
    def copy(self) -> 'Action':
        """Create copy of action."""
        return Action(
            steering=self.steering,
            throttle=self.throttle,
            brake=self.brake,
        )
    
    def __repr__(self) -> str:
        return (
            f"Action(steering={self.steering:.3f}, "
            f"throttle={self.throttle:.3f}, "
            f"brake={self.brake:.3f})"
        )


# Alternative Action Format (for models that prefer different representation)

@dataclass
class ActionAlternative:
    """
    Alternative action format: steering + acceleration.
    
    Some models prefer direct acceleration control instead of
    separate throttle/brake.
    
    This can be converted to/from standard Action format.
    """
    steering: float      # [-1, 1]
    acceleration: float  # [-1, 1], negative = braking
    
    def to_standard_action(self) -> Action:
        """Convert to standard Action format."""
        if self.acceleration >= 0:
            return Action(
                steering=self.steering,
                throttle=self.acceleration,
                brake=0.0,
            )
        else:
            return Action(
                steering=self.steering,
                throttle=0.0,
                brake=-self.acceleration,
            )
    
    @staticmethod
    def from_standard_action(action: Action) -> 'ActionAlternative':
        """Convert from standard Action format."""
        if action.brake > action.throttle:
            acceleration = -action.brake
        else:
            acceleration = action.throttle
        
        return ActionAlternative(
            steering=action.steering,
            acceleration=acceleration,
        )
```

Implementation Notes:
- Action validation happens in __post_init__ (dataclass feature)
- clamp() provides safety net for minor numerical issues
- Zero action and emergency brake provided as utilities
- Alternative action format supported for model flexibility
- All conversions are deterministic and reversible


================================================================================
PART 3: MATHEMATICAL MODELS & ALGORITHMS
================================================================================

--------------------------------------------------------------------------------
10. VEHICLE PHYSICS ENGINE
--------------------------------------------------------------------------------

The vehicle physics engine implements the bicycle model with discrete-time
integration. This is the CORE of simulation determinism.

```python
# arep/core/physics.py

import numpy as np
from typing import Tuple
from arep.core.state import VehicleState, Vector2D
from arep.core.action import Action
from arep.config import SimulationConfig


class VehiclePhysics:
    """
    Deterministic vehicle physics using bicycle model.
    
    State Equations:
        x_{n+1} = x_n + v_n * cos(θ_n) * dt
        y_{n+1} = y_n + v_n * sin(θ_n) * dt
        θ_{n+1} = θ_n + (v_n / L) * tan(δ_n) * dt
        v_{n+1} = clamp(v_n + a_n * dt, 0, v_max)
    
    where:
        (x, y) = position
        θ = heading
        v = velocity
        δ = steering angle
        a = acceleration
        L = wheelbase
        dt = timestep
    
    Constraints:
        |δ| ≤ δ_max
        |a| ≤ a_max (acceleration) or a_max_brake (braking)
        0 ≤ v ≤ v_max
    """
    
    def __init__(self, config: SimulationConfig):
        """
        Initialize physics engine with configuration.
        
        Args:
            config: Simulation configuration with vehicle parameters
        """
        self.dt = config.timestep
        self.wheelbase = config.wheelbase
        
        # Constraints
        self.max_velocity = config.max_velocity
        self.max_acceleration = config.max_acceleration
        self.max_deceleration = config.max_deceleration
        self.max_steering = config.max_steering
        
        # Numerical tolerance
        self.epsilon = config.float_tolerance
    
    def update(
        self,
        state: VehicleState,
        action: Action
    ) -> VehicleState:
        """
        Update vehicle state by one timestep using bicycle model.
        
        This is the PRIMARY physics update function used in simulation.
        It MUST be deterministic - same inputs always produce same outputs.
        
        Args:
            state: Current vehicle state
            action: Control action from model
        
        Returns:
            New vehicle state after dt seconds
        
        Implementation Notes:
        - Uses explicit Euler integration (first-order)
        - Constraints enforced BEFORE physics update
        - Velocity clamped AFTER integration
        - All trigonometric functions use numpy for consistency
        """
        # Convert normalized action to physical values
        steering_angle = action.get_steering_angle(self.max_steering)
        acceleration = action.get_acceleration(
            self.max_acceleration,
            self.max_deceleration
        )
        
        # Enforce steering constraint
        steering_angle = np.clip(steering_angle, -self.max_steering, self.max_steering)
        
        # Get current state values
        x = state.position.x
        y = state.position.y
        theta = state.heading
        v = state.velocity
        
        # Compute velocity change
        v_next = v + acceleration * self.dt
        
        # Enforce velocity constraints
        v_next = np.clip(v_next, 0.0, self.max_velocity)
        
        # Compute position update (using current velocity)
        # NOTE: We use current velocity v, not v_next, for position update
        # This is standard Euler integration
        x_next = x + v * np.cos(theta) * self.dt
        y_next = y + v * np.sin(theta) * self.dt
        
        # Compute heading update (bicycle model)
        # Avoid division by zero when velocity is very small
        if abs(v) > self.epsilon:
            # Standard bicycle model
            theta_dot = (v / self.wheelbase) * np.tan(steering_angle)
            theta_next = theta + theta_dot * self.dt
        else:
            # Vehicle is stopped, heading doesn't change
            theta_next = theta
        
        # Wrap heading to [-π, π]
        theta_next = self._wrap_angle(theta_next)
        
        # Create new state
        new_state = state.copy()
        new_state.position = Vector2D(x_next, y_next)
        new_state.heading = theta_next
        new_state.velocity = v_next
        new_state.acceleration = acceleration
        
        return new_state
    
    def predict_future_position(
        self,
        state: VehicleState,
        action: Action,
        time_horizon: float
    ) -> Tuple[float, float]:
        """
        Predict where vehicle will be after time_horizon seconds.
        
        Used for: lookahead planning, TTC calculation
        
        Args:
            state: Current state
            action: Assumed constant action
            time_horizon: Prediction time (seconds)
        
        Returns:
            (x, y) position after time_horizon
        """
        # Number of timesteps to simulate
        n_steps = int(time_horizon / self.dt)
        
        # Simulate forward
        current = state.copy()
        for _ in range(n_steps):
            current = self.update(current, action)
        
        return current.position.x, current.position.y
    
    def compute_stopping_distance(self, velocity: float) -> float:
        """
        Compute distance needed to stop from given velocity.
        
        Uses kinematic equation: d = v² / (2 * a)
        
        Args:
            velocity: Current velocity (m/s)
        
        Returns:
            Stopping distance (meters)
        """
        if velocity < self.epsilon:
            return 0.0
        
        return (velocity ** 2) / (2 * self.max_deceleration)
    
    def compute_time_to_stop(self, velocity: float) -> float:
        """
        Compute time needed to stop from given velocity.
        
        Uses kinematic equation: t = v / a
        
        Args:
            velocity: Current velocity (m/s)
        
        Returns:
            Stopping time (seconds)
        """
        if velocity < self.epsilon:
            return 0.0
        
        return velocity / self.max_deceleration
    
    @staticmethod
    def _wrap_angle(angle: float) -> float:
        """
        Wrap angle to [-π, π].
        
        This is CRITICAL for determinism - must use consistent wrapping.
        
        Args:
            angle: Input angle (radians)
        
        Returns:
            Wrapped angle in [-π, π]
        """
        # Use numpy's arctan2 for consistent wrapping
        return np.arctan2(np.sin(angle), np.cos(angle))
    
    def validate_action(self, action: Action) -> bool:
        """
        Check if action is physically valid.
        
        Args:
            action: Action to validate
        
        Returns:
            True if valid, False otherwise
        """
        try:
            action._validate()
            return True
        except ValueError:
            return False


# Utility functions for physics calculations

def compute_turning_radius(velocity: float, steering_angle: float, wheelbase: float) -> float:
    """
    Compute instantaneous turning radius.
    
    Formula: R = L / tan(δ)
    
    Args:
        velocity: Current velocity (m/s)
        steering_angle: Steering angle (radians)
        wheelbase: Vehicle wheelbase (meters)
    
    Returns:
        Turning radius (meters), inf if going straight
    """
    if abs(steering_angle) < 1e-6:
        return float('inf')
    
    return wheelbase / np.tan(steering_angle)


def compute_lateral_acceleration(velocity: float, steering_angle: float, wheelbase: float) -> float:
    """
    Compute lateral (centripetal) acceleration during turn.
    
    Formula: a_lat = v² / R = v² * tan(δ) / L
    
    Args:
        velocity: Current velocity (m/s)
        steering_angle: Steering angle (radians)
        wheelbase: Vehicle wheelbase (meters)
    
    Returns:
        Lateral acceleration (m/s²)
    """
    if abs(steering_angle) < 1e-6:
        return 0.0
    
    return (velocity ** 2) * np.tan(steering_angle) / wheelbase
```


--------------------------------------------------------------------------------
11. COLLISION DETECTION SYSTEM
--------------------------------------------------------------------------------

Collision detection uses Oriented Bounding Boxes (OBB) with Separating
Axis Theorem (SAT). This must be deterministic and order-independent.

```python
# arep/core/collision.py

import numpy as np
from typing import List, Optional, Tuple
from dataclasses import dataclass
from arep.core.state import VehicleState, Vector2D, WorldState
from arep.config import SimulationConfig


@dataclass
class CollisionEvent:
    """Record of a collision event."""
    ego_id: str
    object_id: str
    sim_time: float
    impact_speed: float  # m/s
    impact_angle: float  # radians
    
    # Position of collision
    collision_point: Vector2D
    
    def to_dict(self) -> dict:
        return {
            "ego_id": self.ego_id,
            "object_id": self.object_id,
            "sim_time": self.sim_time,
            "impact_speed": self.impact_speed,
            "impact_angle": self.impact_angle,
            "collision_point": {
                "x": self.collision_point.x,
                "y": self.collision_point.y
            }
        }


class CollisionDetector:
    """
    Deterministic collision detection using OBB and SAT.
    
    Algorithm:
    1. For each pair of vehicles:
       a. Compute oriented bounding box (OBB) vertices
       b. Apply Separating Axis Theorem (SAT)
       c. If no separating axis exists, collision detected
    
    Determinism Requirements:
    - Object pairs must be iterated in sorted order (by ID)
    - Vertices must be computed in fixed order
    - Axes must be tested in fixed order
    - Floating-point comparisons use consistent tolerance
    """
    
    def __init__(self, config: SimulationConfig):
        """
        Initialize collision detector.
        
        Args:
            config: Simulation configuration
        """
        self.tolerance = config.collision_tolerance
    
    def check_collision(
        self,
        vehicle_a: VehicleState,
        vehicle_b: VehicleState
    ) -> bool:
        """
        Check if two vehicles are colliding.
        
        Uses Separating Axis Theorem (SAT) on oriented bounding boxes.
        
        Args:
            vehicle_a: First vehicle
            vehicle_b: Second vehicle
        
        Returns:
            True if collision detected, False otherwise
        """
        # Get OBB corners for both vehicles
        corners_a = vehicle_a.get_bounding_box_corners()
        corners_b = vehicle_b.get_bounding_box_corners()
        
        # Get edge normals (potential separating axes)
        axes_a = self._get_edge_normals(corners_a)
        axes_b = self._get_edge_normals(corners_b)
        
        # Test all axes
        all_axes = axes_a + axes_b
        
        for axis in all_axes:
            # Project both polygons onto axis
            proj_a = self._project_polygon(corners_a, axis)
            proj_b = self._project_polygon(corners_b, axis)
            
            # Check for overlap
            if not self._projections_overlap(proj_a, proj_b):
                # Found separating axis -> no collision
                return False
        
        # No separating axis found -> collision
        return True
    
    def detect_all_collisions(self, world: WorldState) -> List[CollisionEvent]:
        """
        Detect all collisions in world state.
        
        Checks:
        - Ego vs. all dynamic objects
        - (Optionally) Dynamic objects vs. each other
        
        Args:
            world: Current world state
        
        Returns:
            List of collision events (empty if none)
        """
        collisions = []
        
        # Check ego vs. all dynamic objects
        # Objects must be processed in deterministic order (by ID)
        sorted_objects = sorted(world.dynamic_objects, key=lambda o: o.object_id)
        
        for obj in sorted_objects:
            if self.check_collision(world.ego_vehicle, obj):
                # Compute collision details
                event = self._create_collision_event(
                    world.ego_vehicle,
                    obj,
                    world.sim_time
                )
                collisions.append(event)
        
        return collisions
    
    def _get_edge_normals(self, corners: List[Vector2D]) -> List[Vector2D]:
        """
        Get perpendicular normals to each edge of polygon.
        
        For a rectangle, this gives us 2 unique axes (opposing edges have same normal).
        But we compute all 4 for generality.
        
        Args:
            corners: List of corner vertices in order
        
        Returns:
            List of unit normal vectors
        """
        normals = []
        n = len(corners)
        
        for i in range(n):
            # Edge from corner i to corner (i+1) % n
            edge = corners[(i + 1) % n] - corners[i]
            
            # Perpendicular normal (rotate 90 degrees)
            # For edge (dx, dy), normal is (-dy, dx)
            normal = Vector2D(-edge.y, edge.x)
            
            # Normalize
            normal = normal.normalize()
            
            normals.append(normal)
        
        return normals
    
    def _project_polygon(
        self,
        corners: List[Vector2D],
        axis: Vector2D
    ) -> Tuple[float, float]:
        """
        Project polygon onto axis and return min/max projections.
        
        Args:
            corners: Polygon vertices
            axis: Unit vector to project onto
        
        Returns:
            (min_projection, max_projection)
        """
        projections = [corner.dot(axis) for corner in corners]
        return min(projections), max(projections)
    
    def _projections_overlap(
        self,
        proj_a: Tuple[float, float],
        proj_b: Tuple[float, float]
    ) -> bool:
        """
        Check if two projection intervals overlap.
        
        Args:
            proj_a: (min, max) for polygon A
            proj_b: (min, max) for polygon B
        
        Returns:
            True if intervals overlap, False if separated
        """
        min_a, max_a = proj_a
        min_b, max_b = proj_b
        
        # Check for separation (with tolerance)
        if max_a < min_b - self.tolerance:
            return False
        if max_b < min_a - self.tolerance:
            return False
        
        return True
    
    def _create_collision_event(
        self,
        vehicle_a: VehicleState,
        vehicle_b: VehicleState,
        sim_time: float
    ) -> CollisionEvent:
        """
        Create collision event with computed details.
        
        Args:
            vehicle_a: First vehicle (typically ego)
            vehicle_b: Second vehicle (typically object)
            sim_time: Current simulation time
        
        Returns:
            CollisionEvent with computed metrics
        """
        # Compute relative velocity
        vel_a = vehicle_a.get_velocity_vector()
        vel_b = vehicle_b.get_velocity_vector()
        relative_vel = vel_a - vel_b
        impact_speed = relative_vel.norm()
        
        # Compute impact angle (angle between velocity vectors)
        if impact_speed > 1e-6:
            # Angle between relative velocity and vehicle A's heading
            impact_angle = np.arctan2(relative_vel.y, relative_vel.x) - vehicle_a.heading
            impact_angle = np.arctan2(np.sin(impact_angle), np.cos(impact_angle))
        else:
            impact_angle = 0.0
        
        # Approximate collision point (midpoint between centers)
        collision_point = Vector2D(
            (vehicle_a.position.x + vehicle_b.position.x) / 2.0,
            (vehicle_a.position.y + vehicle_b.position.y) / 2.0
        )
        
        return CollisionEvent(
            ego_id=vehicle_a.object_id,
            object_id=vehicle_b.object_id,
            sim_time=sim_time,
            impact_speed=impact_speed,
            impact_angle=impact_angle,
            collision_point=collision_point
        )
    
    def check_off_road(
        self,
        vehicle: VehicleState,
        world: WorldState,
        max_lane_offset: float = 2.0
    ) -> bool:
        """
        Check if vehicle has gone off road.
        
        Simple implementation: checks if lateral offset exceeds threshold.
        For production: use proper lane boundary geometry.
        
        Args:
            vehicle: Vehicle to check
            world: World state (for lane information)
            max_lane_offset: Maximum allowed lateral offset (meters)
        
        Returns:
            True if off road, False otherwise
        """
        current_lane = world.get_current_lane()
        if current_lane is None:
            # No lane defined, cannot determine off-road
            return False
        
        _, lateral_offset = current_lane.get_closest_point(vehicle.position)
        
        # Off road if offset exceeds half lane width + tolerance
        lane_boundary = current_lane.width / 2.0 + max_lane_offset
        
        return abs(lateral_offset) > lane_boundary
```


--------------------------------------------------------------------------------
12. TIME-TO-COLLISION CALCULATOR
--------------------------------------------------------------------------------

TTC is a critical safety metric. It must be computed accurately and
deterministically.

```python
# arep/core/ttc.py

import numpy as np
from typing import Optional
from arep.core.state import VehicleState, Vector2D


class TTCCalculator:
    """
    Time-To-Collision (TTC) calculator.
    
    TTC Definition:
    Time until collision if both vehicles maintain current velocity.
    
    Algorithm:
    1. Compute relative position and velocity
    2. Check if vehicles are approaching (closing speed > 0)
    3. Estimate collision time using linear approximation
    4. Validate using angular check (object must be in forward cone)
    
    Assumptions:
    - Constant velocity motion
    - Point-mass approximation (vehicles as points)
    - Linear trajectory
    
    Limitations:
    - Does not account for vehicle size (conservative)
    - Does not account for acceleration
    - Assumes straight-line motion
    """
    
    def __init__(
        self,
        forward_cone_angle: float = np.pi / 3,  # 60 degrees
        lateral_threshold: float = 5.0  # meters
    ):
        """
        Initialize TTC calculator.
        
        Args:
            forward_cone_angle: Half-angle of forward cone (radians)
            lateral_threshold: Maximum lateral distance to consider (meters)
        """
        self.forward_cone_angle = forward_cone_angle
        self.lateral_threshold = lateral_threshold
    
    def compute_ttc(
        self,
        ego: VehicleState,
        obj: VehicleState
    ) -> Optional[float]:
        """
        Compute Time-To-Collision between ego and object.
        
        Args:
            ego: Ego vehicle state
            obj: Object vehicle state
        
        Returns:
            TTC in seconds if collision possible, None if not approaching
        """
        # Relative position
        rel_pos = obj.position - ego.position
        distance = rel_pos.norm()
        
        if distance < 1e-6:
            # Already colliding
            return 0.0
        
        # Relative velocity (in global frame)
        ego_vel = ego.get_velocity_vector()
        obj_vel = obj.get_velocity_vector()
        rel_vel = obj_vel - ego_vel
        
        # Closing speed (projection of relative velocity onto relative position)
        closing_speed = -rel_pos.dot(rel_vel) / distance
        
        # If closing_speed <= 0, vehicles are moving apart or parallel
        if closing_speed <= 0.0:
            return None
        
        # Check if object is in forward cone
        if not self._is_in_forward_cone(ego, obj):
            return None
        
        # Check lateral distance threshold
        if not self._is_within_lateral_threshold(ego, obj):
            return None
        
        # Linear TTC approximation
        ttc = distance / closing_speed
        
        return ttc
    
    def compute_min_ttc(
        self,
        ego: VehicleState,
        objects: list[VehicleState]
    ) -> float:
        """
        Compute minimum TTC across all objects.
        
        Args:
            ego: Ego vehicle
            objects: List of dynamic objects
        
        Returns:
            Minimum TTC (inf if no collision possible)
        """
        min_ttc = float('inf')
        
        for obj in objects:
            ttc = self.compute_ttc(ego, obj)
            if ttc is not None and ttc < min_ttc:
                min_ttc = ttc
        
        return min_ttc
    
    def _is_in_forward_cone(self, ego: VehicleState, obj: VehicleState) -> bool:
        """
        Check if object is in ego's forward cone.
        
        Args:
            ego: Ego vehicle
            obj: Object
        
        Returns:
            True if object is in forward cone
        """
        # Vector from ego to object
        to_obj = obj.position - ego.position
        
        # Ego's forward direction
        ego_forward = Vector2D(np.cos(ego.heading), np.sin(ego.heading))
        
        # Angle between ego forward and vector to object
        dot = to_obj.normalize().dot(ego_forward)
        angle = np.arccos(np.clip(dot, -1.0, 1.0))
        
        return angle <= self.forward_cone_angle
    
    def _is_within_lateral_threshold(
        self,
        ego: VehicleState,
        obj: VehicleState
    ) -> bool:
        """
        Check if object is within lateral threshold.
        
        Computes lateral distance in ego's reference frame.
        
        Args:
            ego: Ego vehicle
            obj: Object
        
        Returns:
            True if within threshold
        """
        # Transform object position to ego frame
        dx = obj.position.x - ego.position.x
        dy = obj.position.y - ego.position.y
        
        # Rotate to ego frame
        cos_ego = np.cos(-ego.heading)
        sin_ego = np.sin(-ego.heading)
        
        lateral = dx * sin_ego + dy * cos_ego
        
        return abs(lateral) <= self.lateral_threshold
```


--------------------------------------------------------------------------------
13. RANDOMNESS MANAGEMENT SYSTEM
--------------------------------------------------------------------------------

All randomness must be seeded and reproducible. The RandomManager provides
hierarchical seeding for different simulation subsystems.

```python
# arep/core/random_manager.py

import numpy as np
import hashlib
from typing import Dict, Optional
from dataclasses import dataclass, field


@dataclass
class RandomState:
    """
    State of a random number generator.
    Can be saved and restored for replay.
    """
    seed: int
    state: dict  # NumPy generator state
    
    def to_dict(self) -> dict:
        """Serialize state."""
        return {
            "seed": self.seed,
            "state": self.state,
        }
    
    @staticmethod
    def from_dict(data: dict) -> 'RandomState':
        """Deserialize state."""
        return RandomState(
            seed=data["seed"],
            state=data["state"],
        )


class RandomManager:
    """
    Centralized randomness management for deterministic simulation.
    
    Design:
    - Master seed is provided at initialization
    - Subsystem seeds are derived deterministically from master seed
    - Each subsystem gets independent numpy.random.Generator
    - All randomness goes through this manager
    
    Subsystems:
    - scenario: Initial conditions
    - traffic: Dynamic object behavior
    - pedestrian: Pedestrian behavior
    - weather: Weather events
    - noise: Sensor/actuation noise
    
    Usage:
        rng = RandomManager(master_seed=42)
        
        # Get random value for specific subsystem
        noise = rng.get("noise").normal(0, 0.1)
        
        # Sample from distribution
        position = rng.get("scenario").uniform(0, 100)
    """
    
    def __init__(self, master_seed: int):
        """
        Initialize random manager with master seed.
        
        Args:
            master_seed: Master seed for all randomness
        """
        self.master_seed = master_seed
        
        # Subsystem generators
        self._generators: Dict[str, np.random.Generator] = {}
        
        # Initialize default subsystems
        self._initialize_subsystems()
    
    def _initialize_subsystems(self):
        """Create generators for each subsystem."""
        subsystems = [
            "scenario",
            "traffic",
            "pedestrian",
            "weather",
            "noise",
        ]
        
        for subsystem in subsystems:
            seed = self._derive_seed(self.master_seed, subsystem)
            self._generators[subsystem] = np.random.Generator(
                np.random.PCG64(seed)
            )
    
    def get(self, subsystem: str) -> np.random.Generator:
        """
        Get random generator for specific subsystem.
        
        Args:
            subsystem: Name of subsystem
        
        Returns:
            NumPy random generator for this subsystem
        
        Example:
            rng.get("noise").normal(0, 1)
            rng.get("traffic").choice([0, 1, 2])
        """
        if subsystem not in self._generators:
            # Create generator on-demand
            seed = self._derive_seed(self.master_seed, subsystem)
            self._generators[subsystem] = np.random.Generator(
                np.random.PCG64(seed)
            )
        
        return self._generators[subsystem]
    
    @staticmethod
    def _derive_seed(master_seed: int, subsystem: str) -> int:
        """
        Derive subsystem seed from master seed.
        
        Uses SHA256 hashing for deterministic derivation.
        
        Args:
            master_seed: Master seed
            subsystem: Subsystem name
        
        Returns:
            Derived seed (32-bit integer)
        """
        # Create deterministic hash
        data = f"{master_seed}:{subsystem}".encode('utf-8')
        hash_digest = hashlib.sha256(data).digest()
        
        # Convert first 4 bytes to integer
        seed = int.from_bytes(hash_digest[:4], byteorder='big')
        
        return seed
    
    def save_state(self) -> Dict[str, RandomState]:
        """
        Save state of all generators.
        
        Used for replay and debugging.
        
        Returns:
            Dictionary mapping subsystem to RandomState
        """
        states = {}
        for subsystem, generator in self._generators.items():
            states[subsystem] = RandomState(
                seed=self._derive_seed(self.master_seed, subsystem),
                state=generator.bit_generator.state,
            )
        return states
    
    def restore_state(self, states: Dict[str, RandomState]):
        """
        Restore generator states.
        
        Args:
            states: Dictionary of saved states
        """
        for subsystem, state in states.items():
            if subsystem in self._generators:
                self._generators[subsystem].bit_generator.state = state.state
    
    def reset(self):
        """Reset all generators to initial state."""
        self._generators.clear()
        self._initialize_subsystems()


# Utility functions for common random operations

def add_gaussian_noise(
    value: float,
    rng: np.random.Generator,
    std_dev: float
) -> float:
    """
    Add Gaussian noise to value.
    
    Args:
        value: Base value
        rng: Random generator
        std_dev: Standard deviation of noise
    
    Returns:
        Noisy value
    """
    noise = rng.normal(0, std_dev)
    return value + noise


def sample_uniform_position(
    rng: np.random.Generator,
    x_range: tuple[float, float],
    y_range: tuple[float, float]
) -> tuple[float, float]:
    """
    Sample random position uniformly.
    
    Args:
        rng: Random generator
        x_range: (min_x, max_x)
        y_range: (min_y, max_y)
    
    Returns:
        (x, y) position
    """
    x = rng.uniform(x_range[0], x_range[1])
    y = rng.uniform(y_range[0], y_range[1])
    return x, y


def sample_velocity(
    rng: np.random.Generator,
    mean: float,
    std: float,
    min_vel: float = 0.0,
    max_vel: float = 35.0
) -> float:
    """
    Sample velocity from truncated normal distribution.
    
    Args:
        rng: Random generator
        mean: Mean velocity
        std: Standard deviation
        min_vel: Minimum velocity
        max_vel: Maximum velocity
    
    Returns:
        Sampled velocity
    """
    velocity = rng.normal(mean, std)
    return np.clip(velocity, min_vel, max_vel)
```

Implementation Notes:
- Uses numpy.random.Generator (modern API, not legacy RandomState)
- PCG64 is the bit generator (fast and high quality)
- Subsystem seeds derived via SHA256 hash (cryptographically secure)
- All generators independent - changing one subsystem doesn't affect others
- State can be saved/restored for exact replay


[DOCUMENT CONTINUES - Part 3 Complete]


================================================================================
PART 4: SIMULATION ENGINE
================================================================================

--------------------------------------------------------------------------------
14. WORLD STATE MANAGER
--------------------------------------------------------------------------------

The World State Manager handles world initialization, updates, and queries.

```python
# arep/simulation/world.py

from typing import List, Optional
from arep.core.state import (
    WorldState, VehicleState, TrafficLightInfo, LaneInfo,
    Vector2D, ObjectType, TerminationReason
)
from arep.core.random_manager import RandomManager
from arep.config import SimulationConfig


class WorldManager:
    """
    Manages world state initialization and queries.
    
    Responsibilities:
    - Initialize world from scenario definition
    - Provide query methods for state information
    - Update traffic lights based on time
    - Track termination conditions
    
    Does NOT:
    - Mutate vehicle states (that's SimulationEngine's job)
    - Handle physics (that's VehiclePhysics's job)
    """
    
    def __init__(self, config: SimulationConfig):
        """
        Initialize world manager.
        
        Args:
            config: Simulation configuration
        """
        self.config = config
    
    def create_initial_world(
        self,
        ego_initial: VehicleState,
        dynamic_objects: List[VehicleState],
        traffic_lights: List[TrafficLightInfo],
        lanes: List[LaneInfo],
        weather_condition: str = "clear",
        visibility: float = 1000.0
    ) -> WorldState:
        """
        Create initial world state from components.
        
        Args:
            ego_initial: Initial ego vehicle state
            dynamic_objects: Initial dynamic object states
            traffic_lights: Traffic light configurations
            lanes: Lane graph
            weather_condition: Weather condition
            visibility: Visibility distance
        
        Returns:
            Initial WorldState
        """
        return WorldState(
            sim_time=0.0,
            timestep_count=0,
            ego_vehicle=ego_initial,
            dynamic_objects=dynamic_objects,
            traffic_lights=traffic_lights,
            lanes=lanes,
            weather_condition=weather_condition,
            visibility=visibility,
            is_terminated=False,
            termination_reason=TerminationReason.NONE,
            has_collision=False,
            collision_object_id=None,
            collision_time=None,
            last_action=None,
        )
    
    def update_traffic_lights(
        self,
        world: WorldState,
        rng: RandomManager
    ) -> WorldState:
        """
        Update traffic light states based on time.
        
        This is a simplified implementation. Production version should
        implement proper traffic signal timing plans.
        
        Args:
            world: Current world state
            rng: Random manager
        
        Returns:
            Updated world state
        """
        # For now, traffic lights are static
        # In production, implement signal timing logic here
        return world
    
    def update_dynamic_objects(
        self,
        world: WorldState,
        dt: float,
        rng: RandomManager
    ) -> WorldState:
        """
        Update dynamic object states according to their behavior models.
        
        Args:
            world: Current world state
            dt: Timestep
            rng: Random manager
        
        Returns:
            Updated world state with new object positions
        """
        updated_objects = []
        
        for obj in world.dynamic_objects:
            # Update based on object behavior type
            # For now, implement simple constant velocity
            updated_obj = self._update_constant_velocity_object(obj, dt)
            updated_objects.append(updated_obj)
        
        new_world = world.copy()
        new_world.dynamic_objects = updated_objects
        return new_world
    
    @staticmethod
    def _update_constant_velocity_object(
        obj: VehicleState,
        dt: float
    ) -> VehicleState:
        """
        Update object with constant velocity motion.
        
        Args:
            obj: Object state
            dt: Timestep
        
        Returns:
            Updated object state
        """
        new_obj = obj.copy()
        
        # Update position
        new_obj.position = Vector2D(
            obj.position.x + obj.velocity * np.cos(obj.heading) * dt,
            obj.position.y + obj.velocity * np.sin(obj.heading) * dt
        )
        
        return new_obj
    
    def get_objects_in_range(
        self,
        world: WorldState,
        center: Vector2D,
        radius: float
    ) -> List[VehicleState]:
        """
        Get all objects within radius of center point.
        
        Args:
            world: World state
            center: Center position
            radius: Search radius
        
        Returns:
            List of objects within radius
        """
        objects_in_range = []
        
        for obj in world.dynamic_objects:
            distance = (obj.position - center).norm()
            if distance <= radius:
                objects_in_range.append(obj)
        
        return objects_in_range
    
    def get_objects_ahead(
        self,
        world: WorldState,
        max_distance: float = 100.0,
        max_lateral: float = 5.0
    ) -> List[VehicleState]:
        """
        Get objects ahead of ego vehicle.
        
        Args:
            world: World state
            max_distance: Maximum forward distance
            max_lateral: Maximum lateral distance
        
        Returns:
            List of objects ahead, sorted by distance
        """
        ego = world.ego_vehicle
        objects_ahead = []
        
        for obj in world.dynamic_objects:
            # Transform to ego frame
            dx = obj.position.x - ego.position.x
            dy = obj.position.y - ego.position.y
            
            cos_ego = np.cos(-ego.heading)
            sin_ego = np.sin(-ego.heading)
            
            forward = dx * cos_ego - dy * sin_ego
            lateral = dx * sin_ego + dy * cos_ego
            
            # Check if ahead and within thresholds
            if (forward > 0 and 
                forward <= max_distance and 
                abs(lateral) <= max_lateral):
                objects_ahead.append(obj)
        
        # Sort by forward distance
        objects_ahead.sort(
            key=lambda o: (o.position - ego.position).norm()
        )
        
        return objects_ahead


--------------------------------------------------------------------------------
15. SIMULATION ENGINE CORE
--------------------------------------------------------------------------------

The SimulationEngine is the main orchestrator of simulation execution.

```python
# arep/simulation/engine.py

from typing import Optional
import numpy as np

from arep.core.state import WorldState, VehicleState, TerminationReason
from arep.core.action import Action
from arep.core.physics import VehiclePhysics
from arep.core.collision import CollisionDetector
from arep.core.random_manager import RandomManager
from arep.simulation.world import WorldManager
from arep.simulation.termination import TerminationChecker
from arep.config import SimulationConfig


class SimulationEngine:
    """
    Core simulation engine orchestrating all simulation components.
    
    Responsibilities:
    - Execute one simulation timestep
    - Coordinate physics, collision detection, world updates
    - Check termination conditions
    - Maintain determinism guarantees
    
    Usage:
        engine = SimulationEngine(config)
        world = engine.initialize(scenario, seed)
        
        for step in range(max_steps):
            action = model.predict(observation)
            world = engine.step(world, action)
            
            if world.is_terminated:
                break
    """
    
    def __init__(self, config: SimulationConfig):
        """
        Initialize simulation engine.
        
        Args:
            config: Simulation configuration
        """
        self.config = config
        self.dt = config.timestep
        
        # Initialize subsystems
        self.physics = VehiclePhysics(config)
        self.collision_detector = CollisionDetector(config)
        self.world_manager = WorldManager(config)
        self.termination_checker = TerminationChecker(config)
    
    def step(
        self,
        world: WorldState,
        action: Action,
        rng: RandomManager
    ) -> WorldState:
        """
        Execute one simulation timestep.
        
        This is the MAIN simulation loop function.
        It must be deterministic - same inputs always produce same output.
        
        Execution Order (CRITICAL for determinism):
        1. Validate action
        2. Apply action to ego vehicle (physics update)
        3. Update dynamic objects
        4. Update traffic lights
        5. Check collisions
        6. Check other termination conditions
        7. Increment time
        
        Args:
            world: Current world state
            action: Control action from model
            rng: Random manager for any stochastic updates
        
        Returns:
            New world state after timestep
        """
        # 0. Check if already terminated
        if world.is_terminated:
            return world
        
        # 1. Validate action
        if not self.physics.validate_action(action):
            # Invalid action -> terminate with error
            new_world = world.copy()
            new_world.is_terminated = True
            new_world.termination_reason = TerminationReason.INVALID_ACTION
            return new_world
        
        # 2. Apply physics to ego vehicle
        new_ego = self.physics.update(world.ego_vehicle, action)
        
        # 3. Update dynamic objects
        new_world = world.copy()
        new_world.ego_vehicle = new_ego
        new_world = self.world_manager.update_dynamic_objects(new_world, self.dt, rng)
        
        # 4. Update traffic lights
        new_world = self.world_manager.update_traffic_lights(new_world, rng)
        
        # 5. Check collisions
        collisions = self.collision_detector.detect_all_collisions(new_world)
        if collisions:
            new_world.has_collision = True
            new_world.collision_object_id = collisions[0].object_id
            new_world.collision_time = new_world.sim_time
            new_world.is_terminated = True
            new_world.termination_reason = TerminationReason.COLLISION
        
        # 6. Check other termination conditions
        if not new_world.is_terminated:
            termination = self.termination_checker.check(new_world)
            if termination is not None:
                new_world.is_terminated = True
                new_world.termination_reason = termination
        
        # 7. Increment time
        new_world.sim_time += self.dt
        new_world.timestep_count += 1
        new_world.last_action = action.copy()
        
        return new_world
    
    def run_simulation(
        self,
        initial_world: WorldState,
        model: 'ModelInterface',
        rng: RandomManager,
        max_steps: int = 3000  # 60 seconds at 50Hz
    ) -> WorldState:
        """
        Run complete simulation until termination or max_steps.
        
        Args:
            initial_world: Initial world state
            model: Model to control ego vehicle
            rng: Random manager
            max_steps: Maximum number of timesteps
        
        Returns:
            Final world state
        """
        world = initial_world.copy()
        previous_world = None
        
        for step in range(max_steps):
            # Generate observation
            observation = Observation.from_world_state(world, previous_world)
            
            # Get action from model
            try:
                action = model.predict(observation)
            except Exception as e:
                # Model error -> terminate
                world.is_terminated = True
                world.termination_reason = TerminationReason.MODEL_ERROR
                break
            
            # Execute timestep
            previous_world = world
            world = self.step(world, action, rng)
            
            # Check termination
            if world.is_terminated:
                break
        
        # If max_steps reached without other termination
        if not world.is_terminated:
            world.is_terminated = True
            world.termination_reason = TerminationReason.TIMEOUT
        
        return world


--------------------------------------------------------------------------------
16. TIME MANAGEMENT SYSTEM
--------------------------------------------------------------------------------

Strict deterministic time management.

```python
# arep/simulation/time_manager.py

import time
from typing import Optional
from dataclasses import dataclass


@dataclass
class TimeMetrics:
    """Metrics about simulation timing."""
    sim_time: float  # Simulation time (seconds)
    wall_time: float  # Wall clock time (seconds)
    timesteps: int  # Number of timesteps executed
    real_time_factor: float  # sim_time / wall_time


class TimeManager:
    """
    Deterministic time management for simulation.
    
    CRITICAL RULES:
    1. Simulation time is NEVER derived from wall clock
    2. Timestep is FIXED at initialization
    3. Time advances by exactly dt each step
    4. Wall clock is used ONLY for performance metrics
    """
    
    def __init__(self, dt: float):
        """
        Initialize time manager.
        
        Args:
            dt: Fixed timestep (seconds)
        """
        self.dt = dt
        self.sim_time = 0.0
        self.timesteps = 0
        self.start_wall_time: Optional[float] = None
    
    def start(self):
        """Start wall clock timer."""
        self.start_wall_time = time.perf_counter()
    
    def step(self):
        """Advance simulation time by one timestep."""
        self.sim_time += self.dt
        self.timesteps += 1
    
    def reset(self):
        """Reset time to zero."""
        self.sim_time = 0.0
        self.timesteps = 0
        self.start_wall_time = None
    
    def get_metrics(self) -> TimeMetrics:
        """
        Get timing metrics.
        
        Returns:
            TimeMetrics with simulation and wall clock times
        """
        if self.start_wall_time is not None:
            wall_time = time.perf_counter() - self.start_wall_time
        else:
            wall_time = 0.0
        
        rtf = self.sim_time / wall_time if wall_time > 0 else 0.0
        
        return TimeMetrics(
            sim_time=self.sim_time,
            wall_time=wall_time,
            timesteps=self.timesteps,
            real_time_factor=rtf
        )


--------------------------------------------------------------------------------
17. TERMINATION CONDITION HANDLER
--------------------------------------------------------------------------------

Checks for simulation termination conditions.

```python
# arep/simulation/termination.py

from typing import Optional
from arep.core.state import WorldState, TerminationReason
from arep.core.collision import CollisionDetector
from arep.config import SimulationConfig


class TerminationChecker:
    """
    Checks for simulation termination conditions.
    
    Termination Conditions:
    1. Collision (checked separately in engine)
    2. Off-road
    3. Timeout (checked in run loop)
    4. Goal reached (scenario-specific)
    5. Model error (checked in run loop)
    """
    
    def __init__(self, config: SimulationConfig):
        """
        Initialize termination checker.
        
        Args:
            config: Simulation configuration
        """
        self.config = config
        self.collision_detector = CollisionDetector(config)
        self.max_simulation_time = config.max_duration
    
    def check(self, world: WorldState) -> Optional[TerminationReason]:
        """
        Check all termination conditions.
        
        Args:
            world: Current world state
        
        Returns:
            TerminationReason if should terminate, None otherwise
        """
        # Check timeout
        if world.sim_time >= self.max_simulation_time:
            return TerminationReason.TIMEOUT
        
        # Check off-road
        if self.collision_detector.check_off_road(world.ego_vehicle, world):
            return TerminationReason.OFF_ROAD
        
        # Check goal reached (scenario-specific, not implemented yet)
        # if self._check_goal_reached(world):
        #     return TerminationReason.SUCCESS
        
        return None
    
    def _check_goal_reached(self, world: WorldState) -> bool:
        """
        Check if scenario goal has been reached.
        
        This is scenario-specific and should be implemented per scenario.
        For now, returns False.
        
        Args:
            world: World state
        
        Returns:
            True if goal reached
        """
        # Placeholder - implement scenario-specific goals
        return False


[DOCUMENT CONTINUES - Part 4 Complete]


================================================================================
PART 5: SCENARIO SYSTEM
================================================================================

--------------------------------------------------------------------------------
18. SCENARIO DEFINITION FORMAT
--------------------------------------------------------------------------------

Scenarios are defined in YAML format with strict schema validation.

```python
# arep/scenario/schema.py

from dataclasses import dataclass
from typing import List, Dict, Any, Optional
from enum import Enum


class RoadType(Enum):
    """Types of road environments."""
    HIGHWAY = "highway"
    URBAN = "urban"
    RESIDENTIAL = "residential"
    RURAL = "rural"


class WeatherCondition(Enum):
    """Weather conditions."""
    CLEAR = "clear"
    RAIN = "rain"
    FOG = "fog"
    SNOW = "snow"


class EventType(Enum):
    """Types of scenario events."""
    SPAWN_VEHICLE = "spawn_vehicle"
    SPAWN_PEDESTRIAN = "spawn_pedestrian"
    CHANGE_TRAFFIC_LIGHT = "change_traffic_light"
    CHANGE_WEATHER = "change_weather"
    OBJECT_BEHAVIOR_CHANGE = "object_behavior_change"


@dataclass
class VehicleInitialCondition:
    """Initial conditions for a vehicle."""
    x: float
    y: float
    heading: float
    velocity: float
    object_type: str = "car"
    object_id: Optional[str] = None


@dataclass
class VehicleConstraints:
    """Physical constraints for ego vehicle."""
    max_velocity: float = 30.0
    max_acceleration: float = 3.0
    max_deceleration: float = 8.0
    max_steering: float = 0.5


@dataclass
class RoadConfiguration:
    """Road environment configuration."""
    road_type: str
    lanes: int
    lane_width: float
    speed_limit: float


@dataclass
class WeatherConfiguration:
    """Weather and visibility configuration."""
    condition: str
    visibility: float


@dataclass
class TrafficObjectBehavior:
    """Behavior specification for traffic objects."""
    type: str  # "constant_velocity", "scripted", "follow_lane"
    parameters: Dict[str, Any]


@dataclass
class TrafficObjectDefinition:
    """Complete definition of a traffic object."""
    id: str
    type: str
    initial: VehicleInitialCondition
    behavior: TrafficObjectBehavior


@dataclass
class ScenarioEvent:
    """Timed event in scenario."""
    type: str
    trigger_time: float
    parameters: Dict[str, Any]


@dataclass
class ScenarioTermination:
    """Termination conditions for scenario."""
    conditions: List[str]
    timeout: float


@dataclass
class ScenarioDefinition:
    """
    Complete scenario definition.
    
    This is the master data structure representing a scenario.
    It can be loaded from YAML and validated.
    """
    # Metadata
    name: str
    version: str
    description: str
    duration: float
    
    # Ego vehicle
    ego_initial: VehicleInitialCondition
    ego_constraints: VehicleConstraints
    
    # Environment
    road: RoadConfiguration
    weather: WeatherConfiguration
    
    # Traffic
    traffic_objects: List[TrafficObjectDefinition]
    
    # Events
    events: List[ScenarioEvent]
    
    # Termination
    termination: ScenarioTermination
    
    # Seeds (optional, can be overridden)
    master_seed: Optional[int] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        # Implementation omitted for brevity
        pass
    
    @staticmethod
    def from_dict(data: Dict[str, Any]) -> 'ScenarioDefinition':
        """Parse from dictionary."""
        # Implementation omitted for brevity
        pass


# Example YAML schema

SCENARIO_YAML_EXAMPLE = """
scenario:
  name: "highway_merge_aggressive"
  version: "1.0"
  description: "Ego must merge into highway with aggressive traffic"
  duration: 30.0

ego:
  initial:
    x: 0.0
    y: -3.5
    heading: 0.0
    velocity: 15.0
  
  constraints:
    max_velocity: 30.0
    max_acceleration: 3.0
    max_deceleration: 6.0
    max_steering: 0.5

environment:
  road:
    type: "highway"
    lanes: 3
    lane_width: 3.5
    speed_limit: 27.8
  
  weather:
    condition: "clear"
    visibility: 1000.0

traffic:
  - id: "lead_vehicle"
    type: "car"
    initial:
      x: 50.0
      y: 0.0
      heading: 0.0
      velocity: 25.0
    behavior:
      type: "constant_velocity"
      parameters: {}
  
  - id: "aggressive_merger"
    type: "truck"
    initial:
      x: 30.0
      y: -3.5
      heading: 0.0
      velocity: 20.0
    behavior:
      type: "scripted"
      parameters:
        waypoints:
          - {time: 2.0, action: "lane_change_left"}
          - {time: 5.0, action: "accelerate", value: 2.0}

events:
  - type: "spawn_pedestrian"
    trigger_time: 10.0
    parameters:
      x: 100.0
      y: 3.5
      crossing_speed: 1.5

termination:
  conditions:
    - collision
    - off_road
    - timeout
  timeout: 30.0
"""


--------------------------------------------------------------------------------
19. SCENARIO PARSER & VALIDATOR
--------------------------------------------------------------------------------

Parse and validate YAML scenario definitions.

```python
# arep/scenario/parser.py

import yaml
from pathlib import Path
from typing import Union
import hashlib

from arep.scenario.schema import ScenarioDefinition
from arep.scenario.validator import ScenarioValidator
from arep.utils.exceptions import ScenarioParseError, ScenarioValidationError


class ScenarioParser:
    """
    Parse scenario YAML files into ScenarioDefinition objects.
    
    Features:
    - YAML parsing with error handling
    - Schema validation
    - Hash computation for versioning
    """
    
    def __init__(self):
        """Initialize parser with validator."""
        self.validator = ScenarioValidator()
    
    def parse_file(self, filepath: Union[str, Path]) -> ScenarioDefinition:
        """
        Parse scenario from YAML file.
        
        Args:
            filepath: Path to YAML file
        
        Returns:
            ScenarioDefinition object
        
        Raises:
            ScenarioParseError: If YAML parsing fails
            ScenarioValidationError: If validation fails
        """
        filepath = Path(filepath)
        
        if not filepath.exists():
            raise ScenarioParseError(f"File not found: {filepath}")
        
        # Read YAML
        try:
            with open(filepath, 'r') as f:
                yaml_content = f.read()
                data = yaml.safe_load(yaml_content)
        except yaml.YAMLError as e:
            raise ScenarioParseError(f"YAML parsing error: {e}")
        
        # Parse into ScenarioDefinition
        try:
            scenario = self._parse_scenario_dict(data)
        except (KeyError, ValueError, TypeError) as e:
            raise ScenarioParseError(f"Schema parsing error: {e}")
        
        # Validate
        validation_errors = self.validator.validate(scenario)
        if validation_errors:
            raise ScenarioValidationError(
                f"Validation failed: {validation_errors}"
            )
        
        # Compute hash for versioning
        scenario_hash = self.compute_hash(yaml_content)
        
        return scenario, scenario_hash
    
    def parse_string(self, yaml_string: str) -> ScenarioDefinition:
        """
        Parse scenario from YAML string.
        
        Args:
            yaml_string: YAML content as string
        
        Returns:
            ScenarioDefinition object
        """
        try:
            data = yaml.safe_load(yaml_string)
        except yaml.YAMLError as e:
            raise ScenarioParseError(f"YAML parsing error: {e}")
        
        scenario = self._parse_scenario_dict(data)
        
        validation_errors = self.validator.validate(scenario)
        if validation_errors:
            raise ScenarioValidationError(
                f"Validation failed: {validation_errors}"
            )
        
        scenario_hash = self.compute_hash(yaml_string)
        
        return scenario, scenario_hash
    
    def _parse_scenario_dict(self, data: dict) -> ScenarioDefinition:
        """
        Parse dictionary into ScenarioDefinition.
        
        Args:
            data: Parsed YAML dictionary
        
        Returns:
            ScenarioDefinition object
        """
        # Parse metadata
        metadata = data["scenario"]
        
        # Parse ego vehicle
        ego_data = data["ego"]
        ego_initial = VehicleInitialCondition(
            x=ego_data["initial"]["x"],
            y=ego_data["initial"]["y"],
            heading=ego_data["initial"]["heading"],
            velocity=ego_data["initial"]["velocity"],
        )
        
        ego_constraints = VehicleConstraints(
            max_velocity=ego_data["constraints"]["max_velocity"],
            max_acceleration=ego_data["constraints"]["max_acceleration"],
            max_deceleration=ego_data["constraints"]["max_deceleration"],
            max_steering=ego_data["constraints"]["max_steering"],
        )
        
        # Parse environment
        env_data = data["environment"]
        road = RoadConfiguration(
            road_type=env_data["road"]["type"],
            lanes=env_data["road"]["lanes"],
            lane_width=env_data["road"]["lane_width"],
            speed_limit=env_data["road"]["speed_limit"],
        )
        
        weather = WeatherConfiguration(
            condition=env_data["weather"]["condition"],
            visibility=env_data["weather"]["visibility"],
        )
        
        # Parse traffic objects
        traffic_objects = []
        for obj_data in data.get("traffic", []):
            obj_initial = VehicleInitialCondition(
                x=obj_data["initial"]["x"],
                y=obj_data["initial"]["y"],
                heading=obj_data["initial"]["heading"],
                velocity=obj_data["initial"]["velocity"],
            )
            
            obj_behavior = TrafficObjectBehavior(
                type=obj_data["behavior"]["type"],
                parameters=obj_data["behavior"].get("parameters", {}),
            )
            
            traffic_obj = TrafficObjectDefinition(
                id=obj_data["id"],
                type=obj_data["type"],
                initial=obj_initial,
                behavior=obj_behavior,
            )
            traffic_objects.append(traffic_obj)
        
        # Parse events
        events = []
        for event_data in data.get("events", []):
            event = ScenarioEvent(
                type=event_data["type"],
                trigger_time=event_data["trigger_time"],
                parameters=event_data.get("parameters", {}),
            )
            events.append(event)
        
        # Parse termination
        term_data = data["termination"]
        termination = ScenarioTermination(
            conditions=term_data["conditions"],
            timeout=term_data["timeout"],
        )
        
        # Create ScenarioDefinition
        return ScenarioDefinition(
            name=metadata["name"],
            version=metadata["version"],
            description=metadata["description"],
            duration=metadata["duration"],
            ego_initial=ego_initial,
            ego_constraints=ego_constraints,
            road=road,
            weather=weather,
            traffic_objects=traffic_objects,
            events=events,
            termination=termination,
            master_seed=data.get("master_seed"),
        )
    
    @staticmethod
    def compute_hash(yaml_string: str) -> str:
        """
        Compute SHA256 hash of YAML content.
        
        Used for scenario versioning and reproducibility.
        
        Args:
            yaml_string: YAML content
        
        Returns:
            Hex digest of SHA256 hash
        """
        return hashlib.sha256(yaml_string.encode('utf-8')).hexdigest()


--------------------------------------------------------------------------------
20. SCENARIO EXECUTOR
--------------------------------------------------------------------------------

Execute scenarios by creating initial world states.

```python
# arep/scenario/executor.py

from typing import List
import numpy as np

from arep.scenario.schema import ScenarioDefinition
from arep.core.state import (
    WorldState, VehicleState, TrafficLightInfo, LaneInfo,
    Vector2D, ObjectType, TrafficLightState
)
from arep.core.random_manager import RandomManager
from arep.simulation.world import WorldManager
from arep.config import SimulationConfig


class ScenarioExecutor:
    """
    Execute scenario definitions to create world states.
    
    Responsibilities:
    - Convert ScenarioDefinition to initial WorldState
    - Handle randomization based on seed
    - Create lane graphs
    - Initialize traffic objects
    """
    
    def __init__(self, config: SimulationConfig):
        """
        Initialize scenario executor.
        
        Args:
            config: Simulation configuration
        """
        self.config = config
        self.world_manager = WorldManager(config)
    
    def create_initial_world(
        self,
        scenario: ScenarioDefinition,
        rng: RandomManager
    ) -> WorldState:
        """
        Create initial world state from scenario definition.
        
        Args:
            scenario: Scenario definition
            rng: Random manager
        
        Returns:
            Initial WorldState
        """
        # Create ego vehicle
        ego = self._create_ego_vehicle(scenario, rng)
        
        # Create dynamic objects
        objects = self._create_traffic_objects(scenario, rng)
        
        # Create traffic lights (if any)
        traffic_lights = self._create_traffic_lights(scenario, rng)
        
        # Create lane graph
        lanes = self._create_lanes(scenario, rng)
        
        # Create world
        world = self.world_manager.create_initial_world(
            ego_initial=ego,
            dynamic_objects=objects,
            traffic_lights=traffic_lights,
            lanes=lanes,
            weather_condition=scenario.weather.condition,
            visibility=scenario.weather.visibility,
        )
        
        return world
    
    def _create_ego_vehicle(
        self,
        scenario: ScenarioDefinition,
        rng: RandomManager
    ) -> VehicleState:
        """
        Create ego vehicle from scenario definition.
        
        Args:
            scenario: Scenario definition
            rng: Random manager
        
        Returns:
            Initial ego vehicle state
        """
        init = scenario.ego_initial
        
        return VehicleState(
            position=Vector2D(init.x, init.y),
            heading=init.heading,
            velocity=init.velocity,
            acceleration=0.0,
            length=self.config.vehicle_length,
            width=self.config.vehicle_width,
            wheelbase=self.config.wheelbase,
            object_type=ObjectType.CAR,
            object_id="ego",
        )
    
    def _create_traffic_objects(
        self,
        scenario: ScenarioDefinition,
        rng: RandomManager
    ) -> List[VehicleState]:
        """
        Create traffic objects from scenario definition.
        
        Args:
            scenario: Scenario definition
            rng: Random manager
        
        Returns:
            List of initial traffic object states
        """
        objects = []
        
        for obj_def in scenario.traffic_objects:
            init = obj_def.initial
            
            # Map type string to ObjectType enum
            obj_type_map = {
                "car": ObjectType.CAR,
                "truck": ObjectType.TRUCK,
                "motorcycle": ObjectType.MOTORCYCLE,
                "pedestrian": ObjectType.PEDESTRIAN,
            }
            obj_type = obj_type_map.get(obj_def.type, ObjectType.CAR)
            
            # Set dimensions based on type
            if obj_type == ObjectType.TRUCK:
                length, width = 8.0, 2.5
            elif obj_type == ObjectType.PEDESTRIAN:
                length, width = 0.5, 0.5
            else:
                length, width = 4.5, 2.0
            
            obj = VehicleState(
                position=Vector2D(init.x, init.y),
                heading=init.heading,
                velocity=init.velocity,
                acceleration=0.0,
                length=length,
                width=width,
                wheelbase=2.7,
                object_type=obj_type,
                object_id=obj_def.id,
            )
            objects.append(obj)
        
        return objects
    
    def _create_traffic_lights(
        self,
        scenario: ScenarioDefinition,
        rng: RandomManager
    ) -> List[TrafficLightInfo]:
        """
        Create traffic lights from scenario.
        
        For now, this is a placeholder. Production version should
        parse traffic light definitions from scenario.
        
        Args:
            scenario: Scenario definition
            rng: Random manager
        
        Returns:
            List of traffic lights
        """
        # Placeholder - implement based on scenario definition
        return []
    
    def _create_lanes(
        self,
        scenario: ScenarioDefinition,
        rng: RandomManager
    ) -> List[LaneInfo]:
        """
        Create lane graph from road configuration.
        
        This is a simplified implementation. Production version should
        support complex road geometries.
        
        Args:
            scenario: Scenario definition
            rng: Random manager
        
        Returns:
            List of lanes
        """
        road = scenario.road
        lanes = []
        
        # Create simple straight lanes
        for lane_idx in range(road.lanes):
            # Lane center y-coordinate
            lane_y = (lane_idx - road.lanes / 2.0 + 0.5) * road.lane_width
            
            # Create centerline points (straight road for now)
            centerline = [
                Vector2D(x, lane_y)
                for x in np.linspace(0, 1000, 100)  # 1km road
            ]
            
            lane = LaneInfo(
                lane_id=f"lane_{lane_idx}",
                centerline_points=centerline,
                width=road.lane_width,
                speed_limit=road.speed_limit,
            )
            lanes.append(lane)
        
        return lanes


--------------------------------------------------------------------------------
21. EVENT SYSTEM
--------------------------------------------------------------------------------

Handle timed events during simulation.

```python
# arep/scenario/events.py

from typing import List, Optional
from dataclasses import dataclass

from arep.scenario.schema import ScenarioEvent, EventType
from arep.core.state import WorldState, VehicleState, Vector2D, ObjectType
from arep.core.random_manager import RandomManager


class EventExecutor:
    """
    Execute scenario events at specified times.
    
    Events can:
    - Spawn new objects
    - Change object behaviors
    - Modify traffic light states
    - Change weather conditions
    """
    
    def __init__(self):
        """Initialize event executor."""
        self.executed_events: List[str] = []
    
    def check_and_execute_events(
        self,
        world: WorldState,
        events: List[ScenarioEvent],
        rng: RandomManager
    ) -> WorldState:
        """
        Check if any events should trigger and execute them.
        
        Args:
            world: Current world state
            events: List of all scenario events
            rng: Random manager
        
        Returns:
            Updated world state
        """
        new_world = world
        
        for event in events:
            event_id = f"{event.type}_{event.trigger_time}"
            
            # Check if event should trigger
            if (world.sim_time >= event.trigger_time and
                event_id not in self.executed_events):
                
                # Execute event
                new_world = self._execute_event(new_world, event, rng)
                
                # Mark as executed
                self.executed_events.append(event_id)
        
        return new_world
    
    def _execute_event(
        self,
        world: WorldState,
        event: ScenarioEvent,
        rng: RandomManager
    ) -> WorldState:
        """
        Execute a single event.
        
        Args:
            world: Current world state
            event: Event to execute
            rng: Random manager
        
        Returns:
            Updated world state
        """
        if event.type == "spawn_vehicle":
            return self._spawn_vehicle(world, event, rng)
        elif event.type == "spawn_pedestrian":
            return self._spawn_pedestrian(world, event, rng)
        elif event.type == "change_traffic_light":
            return self._change_traffic_light(world, event)
        else:
            # Unknown event type, ignore
            return world
    
    def _spawn_vehicle(
        self,
        world: WorldState,
        event: ScenarioEvent,
        rng: RandomManager
    ) -> WorldState:
        """Spawn a new vehicle."""
        params = event.parameters
        
        new_vehicle = VehicleState(
            position=Vector2D(params["x"], params["y"]),
            heading=params.get("heading", 0.0),
            velocity=params.get("velocity", 0.0),
            acceleration=0.0,
            length=params.get("length", 4.5),
            width=params.get("width", 2.0),
            wheelbase=2.7,
            object_type=ObjectType.CAR,
            object_id=params.get("id", f"spawned_{world.sim_time}"),
        )
        
        new_world = world.copy()
        new_world.dynamic_objects.append(new_vehicle)
        return new_world
    
    def _spawn_pedestrian(
        self,
        world: WorldState,
        event: ScenarioEvent,
        rng: RandomManager
    ) -> WorldState:
        """Spawn a new pedestrian."""
        params = event.parameters
        
        pedestrian = VehicleState(
            position=Vector2D(params["x"], params["y"]),
            heading=params.get("heading", 0.0),
            velocity=params.get("crossing_speed", 1.5),
            acceleration=0.0,
            length=0.5,
            width=0.5,
            wheelbase=0.5,
            object_type=ObjectType.PEDESTRIAN,
            object_id=params.get("id", f"pedestrian_{world.sim_time}"),
        )
        
        new_world = world.copy()
        new_world.dynamic_objects.append(pedestrian)
        return new_world
    
    def _change_traffic_light(
        self,
        world: WorldState,
        event: ScenarioEvent
    ) -> WorldState:
        """Change traffic light state."""
        # Implementation for traffic light changes
        return world
    
    def reset(self):
        """Reset executed events tracker."""
        self.executed_events.clear()


================================================================================
PART 6: MODEL INTERFACE & EXECUTION
================================================================================

--------------------------------------------------------------------------------
22. MODEL INTERFACE CONTRACT
--------------------------------------------------------------------------------

All models must implement this interface.

```python
# arep/models/interface.py

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
import numpy as np

from arep.core.observation import Observation
from arep.core.action import Action


class ModelInterface(ABC):
    """
    Abstract interface that all models must implement.
    
    This is the CONTRACT between the simulation and models.
    All submitted models must inherit from this class.
    
    Key Requirements:
    1. Models must be deterministic (given same observation, return same action)
    2. predict() must complete within timeout (default 50ms)
    3. Models must not maintain state across simulations (or reset() it)
    4. Models must not use global variables or shared state
    5. Models must handle any valid Observation
    
    Thread Safety:
    - Models may be called from multiple processes (in batch mode)
    - Each process gets its own model instance
    - No shared state across processes
    """
    
    @abstractmethod
    def reset(self) -> None:
        """
        Reset model to initial state.
        
        Called once at the start of each simulation run.
        Models with internal state (LSTM, history buffers) must reset here.
        
        Must complete in: <10ms
        """
        pass
    
    @abstractmethod
    def predict(self, observation: Observation) -> Action:
        """
        Predict action from observation.
        
        This is called every timestep (50Hz = every 20ms).
        
        Args:
            observation: Current state observation
        
        Returns:
            Action to take
        
        Requirements:
        - Must complete in <50ms (configurable timeout)
        - Must be deterministic
        - Must return valid Action (will be validated)
        - Must not make network calls
        - Must not read/write files
        - Must not use unseeded randomness
        
        Raises:
            Any exception will terminate simulation with MODEL_ERROR
        """
        pass
    
    @abstractmethod
    def get_internal_state(self) -> Dict[str, Any]:
        """
        Get model's internal state.
        
        Used for:
        - Replay debugging
        - Determinism verification
        - State visualization
        
        Returns:
            Dictionary of internal state (must be JSON-serializable)
        
        Example:
            {
                "lstm_hidden": [0.1, 0.2, ...],
                "history_buffer": [[...], [...]],
                "step_count": 42
            }
        """
        pass
    
    @abstractmethod
    def restore_internal_state(self, state: Dict[str, Any]) -> None:
        """
        Restore model's internal state.
        
        Used for replay and determinism testing.
        
        Args:
            state: State dictionary from get_internal_state()
        """
        pass
    
    def get_metadata(self) -> Dict[str, Any]:
        """
        Get model metadata (optional).
        
        Returns metadata about the model for display/logging.
        
        Returns:
            Dictionary with metadata
        
        Example:
            {
                "name": "My Model",
                "version": "1.0",
                "author": "Team Name",
                "description": "Rule-based controller with...",
                "parameters": {...}
            }
        """
        return {
            "name": "Unknown Model",
            "version": "1.0",
        }


# Utility function for validation

def validate_model_interface(model: ModelInterface) -> List[str]:
    """
    Validate that model correctly implements interface.
    
    Checks:
    - All required methods exist
    - Methods have correct signatures
    - reset() and predict() can be called
    - Internal state can be saved/restored
    
    Args:
        model: Model to validate
    
    Returns:
        List of validation errors (empty if valid)
    """
    errors = []
    
    # Check methods exist
    required_methods = ["reset", "predict", "get_internal_state", "restore_internal_state"]
    for method_name in required_methods:
        if not hasattr(model, method_name):
            errors.append(f"Missing required method: {method_name}")
    
    # Try calling reset()
    try:
        model.reset()
    except Exception as e:
        errors.append(f"reset() failed: {e}")
    
    # Try calling get_internal_state()
    try:
        state = model.get_internal_state()
        if not isinstance(state, dict):
            errors.append("get_internal_state() must return dict")
    except Exception as e:
        errors.append(f"get_internal_state() failed: {e}")
    
    return errors


--------------------------------------------------------------------------------
23. LOCAL MODEL EXECUTOR
--------------------------------------------------------------------------------

Execute models in the same process (for development/testing).

```python
# arep/models/local_executor.py

import time
from typing import Optional
from arep.models.interface import ModelInterface
from arep.core.observation import Observation
from arep.core.action import Action
from arep.utils.exceptions import ModelTimeoutError, ModelExecutionError


class LocalModelExecutor:
    """
    Execute models locally (same process).
    
    Features:
    - Timeout enforcement
    - Error handling
    - Performance monitoring
    
    Usage:
        executor = LocalModelExecutor(model, timeout_ms=50)
        action = executor.predict(observation)
    """
    
    def __init__(
        self,
        model: ModelInterface,
        timeout_ms: int = 50
    ):
        """
        Initialize local executor.
        
        Args:
            model: Model instance to execute
            timeout_ms: Timeout in milliseconds
        """
        self.model = model
        self.timeout_s = timeout_ms / 1000.0
        
        # Statistics
        self.total_calls = 0
        self.total_time = 0.0
        self.max_time = 0.0
    
    def reset(self):
        """Reset model."""
        try:
            self.model.reset()
        except Exception as e:
            raise ModelExecutionError(f"Model reset failed: {e}")
    
    def predict(self, observation: Observation) -> Action:
        """
        Execute model prediction with timeout.
        
        Args:
            observation: Current observation
        
        Returns:
            Predicted action
        
        Raises:
            ModelTimeoutError: If execution exceeds timeout
            ModelExecutionError: If model raises exception
        """
        start_time = time.perf_counter()
        
        try:
            # Call model (no actual timeout enforcement in Python without threads)
            # For production, use multiprocessing with timeout
            action = self.model.predict(observation)
            
            elapsed = time.perf_counter() - start_time
            
            # Check if exceeded timeout
            if elapsed > self.timeout_s:
                raise ModelTimeoutError(
                    f"Model execution took {elapsed*1000:.1f}ms, "
                    f"exceeds timeout of {self.timeout_s*1000:.1f}ms"
                )
            
            # Update statistics
            self.total_calls += 1
            self.total_time += elapsed
            self.max_time = max(self.max_time, elapsed)
            
            # Validate action
            if not isinstance(action, Action):
                raise ModelExecutionError(
                    f"Model must return Action, got {type(action)}"
                )
            
            return action
            
        except ModelTimeoutError:
            raise
        except Exception as e:
            raise ModelExecutionError(f"Model prediction failed: {e}")
    
    def get_statistics(self) -> Dict[str, float]:
        """
        Get execution statistics.
        
        Returns:
            Dictionary with performance metrics
        """
        avg_time = self.total_time / self.total_calls if self.total_calls > 0 else 0
        
        return {
            "total_calls": self.total_calls,
            "total_time_ms": self.total_time * 1000,
            "avg_time_ms": avg_time * 1000,
            "max_time_ms": self.max_time * 1000,
        }


[DOCUMENT CONTINUES - Parts 5-6 Complete]
