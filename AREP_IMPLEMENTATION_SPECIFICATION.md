================================================================================
AUTONOMOUS ROBUSTNESS EVALUATION PLATFORM (AREP)
IMPLEMENTATION SPECIFICATION DOCUMENT
Version 2.0 - Implementation Grade
================================================================================

DOCUMENT PURPOSE
================================================================================
This document provides complete specifications for implementing AREP.
It describes WHAT to build, HOW it should work, and WHY design decisions
were made - but does NOT contain actual code implementations.

Code implementations are in separate Python files following the structure
defined in this document.

TARGET AUDIENCE
- Software architects reviewing design decisions
- Engineers implementing the system
- QA engineers writing test plans
- Technical managers planning development


================================================================================
TABLE OF CONTENTS
================================================================================

PART 1: PROJECT STRUCTURE & ARCHITECTURE
    1. Directory Structure
    2. Module Organization
    3. Dependency Management
    4. Configuration Architecture

PART 2: CORE CONCEPTS & REQUIREMENTS
    5. System Overview
    6. Determinism Requirements
    7. Performance Requirements
    8. Security Requirements

PART 3: DATA MODELS & SCHEMAS
    9. State Representation Specification
    10. Observation Format Specification
    11. Action Format Specification
    12. Event Schema Specification

PART 4: ALGORITHMS & MATHEMATICS
    13. Vehicle Physics Model
    14. Collision Detection Algorithm
    15. Time-To-Collision Calculation
    16. Randomness Management Strategy

PART 5: SIMULATION ENGINE SPECIFICATION
    17. World State Management
    18. Simulation Loop Architecture
    19. Time Management System
    20. Termination Conditions

PART 6: SCENARIO SYSTEM SPECIFICATION
    21. Scenario Definition Format
    22. Parsing Requirements
    23. Validation Rules
    24. Execution Strategy

PART 7: MODEL INTERFACE SPECIFICATION
    25. Model Interface Contract
    26. Execution Requirements
    27. Sandboxing Strategy
    28. Timeout Handling

PART 8: EVALUATION & METRICS
    29. Safety Metrics Definition
    30. Compliance Metrics Definition
    31. Stability Metrics Definition
    32. Reactivity Metrics Definition
    33. Composite Scoring Algorithm

PART 9: STATISTICAL FRAMEWORK
    34. Batch Execution Architecture
    35. Statistical Aggregation Methods
    36. Confidence Interval Calculation
    37. Robustness Curve Generation

PART 10: DATA PERSISTENCE
    38. Database Schema Design
    39. ORM Architecture
    40. Query Patterns
    41. Migration Strategy

PART 11: API & INTERFACES
    42. REST API Specification
    43. WebSocket Protocol
    44. Authentication & Authorization
    45. Rate Limiting

PART 12: TESTING STRATEGY
    46. Unit Testing Requirements
    47. Integration Testing Plan
    48. Determinism Testing Protocol
    49. Performance Benchmarking

PART 13: DEPLOYMENT & OPERATIONS
    50. Containerization Strategy
    51. Kubernetes Architecture
    52. Monitoring & Logging
    53. Scaling Strategy


================================================================================
PART 1: PROJECT STRUCTURE & ARCHITECTURE
================================================================================

--------------------------------------------------------------------------------
1. DIRECTORY STRUCTURE
--------------------------------------------------------------------------------

The project follows a standard Python package structure with clear separation
of concerns:

### Top-Level Structure

```
arep/                       # Root project directory
├── arep/                   # Main Python package
├── tests/                  # Test suite
├── scenarios/              # Scenario definitions (YAML)
├── docker/                 # Docker configurations
├── k8s/                    # Kubernetes manifests
├── scripts/                # Utility scripts
├── docs/                   # Additional documentation
├── config/                 # Configuration files
├── requirements.txt        # Production dependencies
├── requirements-dev.txt    # Development dependencies
├── setup.py               # Package installation
└── README.md              # Project overview
```

### Main Package Structure

```
arep/
├── __init__.py            # Package initialization
├── core/                  # Core simulation components
│   ├── state.py          # State representations
│   ├── physics.py        # Vehicle physics
│   ├── collision.py      # Collision detection
│   ├── observation.py    # Observation types
│   ├── action.py         # Action types
│   ├── random_manager.py # Randomness management
│   └── ttc.py           # Time-to-collision
│
├── simulation/           # Simulation engine
│   ├── engine.py        # Main simulation loop
│   ├── world.py         # World management
│   ├── time_manager.py  # Time tracking
│   └── termination.py   # Termination logic
│
├── scenario/            # Scenario system
│   ├── schema.py       # Data schemas
│   ├── parser.py       # YAML parsing
│   ├── validator.py    # Validation
│   ├── executor.py     # Scenario execution
│   └── events.py       # Event handling
│
├── models/             # Model interface & execution
│   ├── interface.py    # Abstract interface
│   ├── local_executor.py   # Local execution
│   ├── docker_executor.py  # Docker sandbox
│   ├── timeout_handler.py  # Timeout management
│   └── examples/       # Example models
│
├── evaluation/         # Metrics & scoring
│   ├── collector.py    # Metric collection
│   ├── safety.py       # Safety metrics
│   ├── compliance.py   # Compliance metrics
│   ├── stability.py    # Stability metrics
│   ├── reactivity.py   # Reactivity metrics
│   └── composite.py    # Composite scoring
│
├── statistics/         # Statistical analysis
│   ├── aggregator.py   # Aggregation
│   ├── confidence.py   # Confidence intervals
│   └── curves.py       # Robustness curves
│
├── execution/          # Batch execution
│   ├── batch.py       # Batch coordinator
│   ├── worker.py      # Worker process
│   ├── pool.py        # Worker pool
│   └── seed_scheduler.py  # Seed management
│
├── database/          # Data persistence
│   ├── models.py     # ORM models
│   ├── schema.sql    # SQL schema
│   ├── queries.py    # Query helpers
│   └── migrations/   # Database migrations
│
├── api/              # REST API
│   ├── app.py       # FastAPI application
│   ├── routes/      # API endpoints
│   ├── schemas.py   # Request/response models
│   └── websocket.py # Real-time updates
│
├── visualization/    # Rendering & plotting
│   ├── renderer.py  # State visualization
│   ├── replay.py    # Replay system
│   └── plots.py     # Metric plots
│
├── utils/           # Utilities
│   ├── logging_config.py
│   ├── exceptions.py
│   ├── validators.py
│   └── hashing.py
│
└── config/          # Configuration management
    └── __init__.py  # Config loading
```

### Test Structure

Tests mirror the source structure:

```
tests/
├── unit/                  # Unit tests
│   ├── test_physics.py
│   ├── test_collision.py
│   ├── test_metrics.py
│   └── ...
├── integration/          # Integration tests
│   ├── test_simulation.py
│   ├── test_batch.py
│   └── ...
├── determinism/         # Determinism tests
│   ├── test_determinism.py
│   └── test_reproducibility.py
└── performance/        # Performance tests
    ├── test_benchmarks.py
    └── test_scalability.py
```

DESIGN RATIONALE:
- Clear separation by responsibility
- Easy to navigate and understand
- Supports independent module development
- Facilitates testing and mocking


--------------------------------------------------------------------------------
2. MODULE ORGANIZATION
--------------------------------------------------------------------------------

### Module Responsibilities

**core/**: Pure computational logic, no I/O
- State representations and transformations
- Physics calculations
- Geometric algorithms
- Randomness management
- No dependencies on other modules except config

**simulation/**: Orchestration of simulation execution
- Coordinates core components
- Manages simulation loop
- Handles world updates
- Depends on: core

**scenario/**: Scenario definition and loading
- YAML parsing and validation
- Scenario data structures
- Initial state generation
- Depends on: core

**models/**: Model interface and execution
- Abstract model contract
- Execution environments (local, docker)
- Timeout and error handling
- Depends on: core

**evaluation/**: Metric computation
- Observes simulation state
- Computes safety/compliance/stability metrics
- Pure functions of state history
- Depends on: core, simulation

**statistics/**: Statistical analysis
- Aggregates results across runs
- Computes confidence intervals
- Generates robustness curves
- Depends on: evaluation

**execution/**: Batch processing
- Multiprocessing coordination
- Worker pool management
- Result aggregation
- Depends on: simulation, models, evaluation

**database/**: Data persistence
- ORM models
- Query construction
- Schema migrations
- Depends on: all (for serialization)

**api/**: External interface
- REST endpoints
- WebSocket handlers
- Request validation
- Depends on: execution, database

**visualization/**: Rendering (optional)
- State visualization
- Replay functionality
- Plotting utilities
- Depends on: core, simulation

### Import Rules

To maintain clean architecture:

1. **No circular imports**: Module dependency graph must be acyclic
2. **Explicit imports**: Use `from arep.core.state import WorldState`, not `from arep.core import *`
3. **Internal imports only**: Modules only import from arep package and standard library
4. **Config as singleton**: Configuration accessed via `from arep.config import get_config`

### Module Testing Strategy

Each module should be:
- **Testable in isolation**: Use mocking for dependencies
- **Fast**: Unit tests run in milliseconds
- **Deterministic**: Same inputs produce same outputs
- **Complete**: Cover normal cases, edge cases, error cases


--------------------------------------------------------------------------------
3. DEPENDENCY MANAGEMENT
--------------------------------------------------------------------------------

### Core Dependencies

**Numerical Computing**
- numpy==1.26.0: Arrays, linear algebra, trigonometry
- scipy==1.11.0: Scientific algorithms (if needed)

WHY NUMPY: Industry standard, deterministic when properly used, excellent performance

**Geometry**
- shapely==2.0.2: OBB operations, geometric predicates

WHY SHAPELY: Battle-tested geometry library, supports all needed operations

**Database**
- sqlalchemy==2.0.23: ORM and SQL abstraction
- alembic==1.12.1: Schema migrations
- psycopg2-binary==2.9.9: PostgreSQL driver

WHY SQLALCHEMY: Powerful ORM, supports migrations, works across databases

**API Framework**
- fastapi==0.104.1: Modern async web framework
- uvicorn==0.24.0: ASGI server
- pydantic==2.5.0: Data validation

WHY FASTAPI: Async support, automatic OpenAPI docs, excellent performance

**Configuration**
- pyyaml==6.0.1: YAML parsing
- jsonschema==4.20.0: Schema validation

**Testing**
- pytest==7.4.3: Test framework
- pytest-cov==4.1.0: Coverage reporting
- hypothesis==6.92.0: Property-based testing

### Version Pinning Strategy

ALL dependencies must be pinned to exact versions for determinism:

```
numpy==1.26.0          # NOT numpy>=1.26.0
```

RATIONALE:
- Different versions may have different floating-point behavior
- Ensures reproducibility across environments
- Prevents unexpected breaks from dependency updates

UPDATE PROCEDURE:
1. Test new version in isolated environment
2. Run full determinism test suite
3. If passes, update requirements.txt
4. Document any behavior changes

### Optional Dependencies

For development only:
- black: Code formatting
- ruff: Fast linting
- mypy: Type checking
- ipython: Interactive debugging

These should NOT affect simulation determinism.


--------------------------------------------------------------------------------
4. CONFIGURATION ARCHITECTURE
--------------------------------------------------------------------------------

### Configuration Sources (Priority Order)

1. **Environment variables** (highest priority)
   - Example: `DATABASE_URL`, `WORKER_POOL_SIZE`
   - Used for deployment-specific settings

2. **Environment-specific YAML files**
   - config/production.yaml
   - config/development.yaml
   - config/test.yaml
   - Override defaults for specific environments

3. **Default YAML file** (lowest priority)
   - config/default.yaml
   - Baseline configuration values

### Configuration Schema

Configuration is organized into logical groups:

**simulation**: Core simulation parameters
- timestep: Fixed timestep (0.02s = 50Hz)
- max_duration: Maximum simulation time
- vehicle parameters: dimensions, constraints
- numerical tolerances

**execution**: Batch execution settings
- worker_pool_size: Number of parallel workers
- model_timeout_ms: Timeout for model inference
- docker settings (if sandboxing enabled)

**database**: Database connection
- url: Connection string
- pool_size: Connection pool size

**paths**: File system locations
- scenarios_dir: Scenario YAML files
- models_dir: Model implementations
- output_dir: Results and logs

**features**: Feature flags
- enable_docker_sandbox: Use Docker for models
- enable_distributed_mode: Use distributed workers
- enable_visualization: Render visualization

### Configuration Loading

Process:
1. Load default.yaml into dictionary
2. Overlay environment-specific YAML
3. Override with environment variables
4. Parse into typed configuration objects
5. Validate all values
6. Create singleton Config instance

Configuration is loaded once at startup and immutable during execution.

### Configuration Validation

All configuration values must be validated:
- Type checking (float, int, string, etc.)
- Range checking (e.g., timestep > 0)
- Path existence (for directories)
- Consistency checks (e.g., max_duration > timestep)

Invalid configuration should fail fast at startup with clear error messages.


================================================================================
PART 2: CORE CONCEPTS & REQUIREMENTS
================================================================================

--------------------------------------------------------------------------------
5. SYSTEM OVERVIEW
--------------------------------------------------------------------------------

### System Purpose

AREP evaluates autonomous driving models by:
1. Running models through standardized scenarios
2. Measuring performance across multiple dimensions
3. Computing statistical robustness metrics
4. Providing reproducible, comparable results

### Key Characteristics

**Deterministic**: Same inputs always produce identical outputs
- Fixed timestep integration
- Seeded randomness
- Stable iteration orders
- Version-locked dependencies

**Statistically Rigorous**: Metrics derived from multiple runs
- Confidence intervals
- Distribution analysis
- Hypothesis testing
- Robustness curves

**Model-Agnostic**: Works with any model
- Standard observation/action interface
- Multiple execution modes (local, docker)
- Language-agnostic (via REST API)

**Infrastructure-Grade**: Production-ready system
- Horizontal scaling
- Fault tolerance
- Monitoring and logging
- Security isolation

### What AREP Is NOT

- NOT a photorealistic simulator
- NOT a video game engine
- NOT a training platform (evaluation only)
- NOT a real-time system (determinism > speed)

### Primary Use Cases

1. **Model Benchmarking**: Compare multiple models on standard scenarios
2. **Regression Testing**: Detect performance degradation across versions
3. **Robustness Analysis**: Understand failure modes and edge cases
4. **Certification Support**: Generate evidence for safety arguments


--------------------------------------------------------------------------------
6. DETERMINISM REQUIREMENTS
--------------------------------------------------------------------------------

### Determinism Definition

For identical inputs, the system MUST produce identical outputs:

```
Inputs:
- Scenario configuration S
- Model binary M
- Master seed σ
- Engine version E

Outputs:
- Trajectory T = [(state_0, action_0), (state_1, action_1), ...]
- Metrics R = {safety: X, compliance: Y, ...}

Requirement:
Run(S, M, σ, E) = Run(S, M, σ, E)  for all executions
```

### Determinism Enforcement Rules

**Rule 1: Fixed Timestep Only**

The simulation uses a constant timestep dt = 0.02 seconds (50Hz).

FORBIDDEN:
- Variable timestep
- Frame-based time (dt = wall_clock_delta)
- Adaptive timestep integration

REQUIRED:
```
sim_time = 0.0
while not terminated:
    sim_time += dt  # Always exactly dt
    update_state(dt)
```

RATIONALE: Variable timesteps lead to path-dependent numerical errors.

**Rule 2: No Wall Clock Dependency**

Simulation time is NEVER derived from system clock.

FORBIDDEN inside simulation:
- time.time()
- datetime.now()
- time.sleep()
- Any OS clock queries

ALLOWED outside simulation:
- Wall clock for performance metrics only
- Timestamps for logging (not in simulation logic)

**Rule 3: No Unseeded Randomness**

All randomness must originate from seeded generators.

FORBIDDEN:
- random.random() (uses default global state)
- numpy.random.rand() (uses global RandomState)
- OS entropy sources (/dev/random)

REQUIRED:
- All RNG through RandomManager(master_seed)
- Hierarchical seed derivation
- Independent generators per subsystem

**Rule 4: Stable Iteration Order**

Collections must be ordered consistently.

FORBIDDEN:
- Iterating over sets (undefined order)
- Relying on dict iteration in Python <3.7
- Unordered object traversal

REQUIRED:
- Use lists for ordered collections
- Sort objects by ID before iteration
- Fixed vertex/edge ordering in algorithms

**Rule 5: No Shared Mutable State**

Each simulation run must be isolated.

FORBIDDEN:
- Global variables modified during simulation
- Shared model instances across workers
- Cached state that affects future runs

REQUIRED:
- Each worker instantiates own state
- Deep copying when needed
- Thread-local or process-local storage

**Rule 6: Version Locking**

Dependencies and engine must be versioned.

REQUIRED:
- Exact version pins in requirements.txt
- Engine version stored with results
- Migration tests for version updates

### Determinism Testing

Every code change must pass determinism tests:

```
Test: Run simulation twice with same inputs
Verify: state_hash(run1) == state_hash(run2)
```

Failed determinism tests are critical bugs that block release.


--------------------------------------------------------------------------------
7. PERFORMANCE REQUIREMENTS
--------------------------------------------------------------------------------

### Simulation Performance

**Target**: 1000+ simulations per hour on 8-core machine

**Per-Timestep Targets** (at 50Hz = 20ms period):
- Physics update: <0.5ms
- Collision detection: <1.0ms
- Observation generation: <0.2ms
- Model inference: <15ms (configurable)
- Metric collection: <0.1ms
- Total: <17ms per timestep

**Real-Time Factor**: Simulation should run faster than real-time
- Target: 10x real-time (60s scenario in 6s)
- Minimum: 1x real-time (60s scenario in 60s)

### Batch Execution Performance

**Parallelism**: Near-linear scaling with CPU cores
- 4 cores: 4x throughput
- 8 cores: 7.5x throughput (slight overhead)
- 16 cores: 14x throughput

**Memory Usage**:
- Per worker: <256MB
- Per simulation result (DB): <10KB

**Database Operations**:
- Result insertion: <1ms per record
- Aggregation query: <100ms for 10,000 runs
- Scenario retrieval: <10ms

### Optimization Priorities

1. **Collision detection**: Most expensive operation
   - Profile and optimize SAT implementation
   - Consider spatial indexing for many objects

2. **Object updates**: Linear in number of objects
   - Vectorize operations where possible

3. **Metric computation**: Can be deferred
   - Compute incrementally during simulation
   - Batch compute after completion

### Performance Testing

Continuous benchmarking:
- Nightly performance regression tests
- Profile critical paths weekly
- Track performance metrics over time


--------------------------------------------------------------------------------
8. SECURITY REQUIREMENTS
--------------------------------------------------------------------------------

### Threat Model

**Primary Threats**:
1. Malicious model code attempting system access
2. Resource exhaustion (CPU, memory, disk)
3. Data exfiltration via model
4. Privilege escalation

**Assumed Trusted**:
- Scenario definitions (from trusted users)
- System operators
- Database access

### Model Isolation (Docker Sandbox)

All user-submitted models must run in isolated containers:

**Container Constraints**:
- Read-only filesystem
- No network access (except localhost for API calls)
- CPU quota: 1.0 core
- Memory limit: 512MB
- Execution timeout: 50ms per inference
- No privileged operations

**Resource Limits**:
```
docker run \
  --read-only \
  --network=none \
  --cpus=1.0 \
  --memory=512m \
  --pids-limit=100 \
  model-sandbox:latest
```

**Security Reviews**:
- Container configuration audited
- Escape attempt testing
- Regular security updates

### API Security

**Authentication**: JWT-based authentication for API access

**Authorization**: Role-based access control
- Public: View benchmark results
- User: Submit evaluations
- Admin: Manage scenarios and models

**Rate Limiting**:
- Per-user request limits
- Queue depth limits
- Resource quota tracking

### Data Security

**Sensitive Data**:
- Model binaries (proprietary)
- Evaluation results (competitive)

**Protections**:
- Encryption at rest (database)
- Encryption in transit (TLS)
- Access logging and auditing

### Security Testing

- Weekly automated security scans
- Quarterly penetration testing
- Container escape testing


================================================================================
PART 3: DATA MODELS & SCHEMAS
================================================================================

--------------------------------------------------------------------------------
9. STATE REPRESENTATION SPECIFICATION
--------------------------------------------------------------------------------

### VehicleState

Represents complete state of a vehicle at a single timestep.

**Fields**:
- position: (x, y) coordinates in meters
  - Origin: Arbitrary but consistent within scenario
  - x-axis: Forward direction (typically)
  - y-axis: Lateral direction (positive = right)

- heading: Orientation in radians
  - 0 = east, π/2 = north (counter-clockwise positive)
  - Range: (-π, π] (wrapped)

- velocity: Speed in m/s
  - Scalar (not vector)
  - Range: [0, v_max]

- acceleration: Current acceleration in m/s²
  - Range: [-a_max_brake, a_max_accel]

- length, width: Vehicle dimensions in meters
  - Used for collision detection

- wheelbase: Distance between front and rear axles (meters)
  - Used in bicycle model

- object_type: Enum {CAR, TRUCK, MOTORCYCLE, BICYCLE, PEDESTRIAN, OBSTACLE}

- object_id: Unique string identifier

**Invariants**:
- velocity >= 0 (always non-negative)
- heading in (-π, π]
- Dimensions > 0

**Operations**:
- get_velocity_vector(): Convert scalar velocity to 2D vector
- get_bounding_box_corners(): Compute OBB vertices
- get_front_center(), get_rear_center(): Reference points
- to_dict(), from_dict(): Serialization
- copy(): Deep copy

**Usage**:
```
Ego vehicle: Always has object_id = "ego"
Dynamic objects: Identified by unique string IDs
```

### WorldState

Authoritative state of entire simulation world at one timestep.

**Fields**:
- sim_time: Simulation time in seconds since start
- timestep_count: Number of timesteps elapsed (integer)
- ego_vehicle: VehicleState of ego vehicle
- dynamic_objects: List[VehicleState] of traffic objects
  - MUST be ordered list (not set)
  - Sorted by object_id for determinism
- traffic_lights: List[TrafficLightInfo]
- lanes: List[LaneInfo]
- weather_condition: String {clear, rain, fog, snow}
- visibility: Meters
- is_terminated: Boolean
- termination_reason: Enum {NONE, SUCCESS, COLLISION, OFF_ROAD, TIMEOUT, MODEL_ERROR}
- has_collision: Boolean
- collision_object_id: Optional[String]
- collision_time: Optional[Float]
- last_action: Optional[Action]

**Invariants**:
- sim_time >= 0
- timestep_count >= 0
- dynamic_objects is ordered list
- If has_collision, then collision_object_id is not None

**Operations**:
- get_object_by_id(id): Find object by ID
- get_nearest_traffic_light(): Find closest light to ego
- get_current_lane(): Determine ego's current lane
- to_dict(): Serialize to dictionary
- copy(): Deep copy for immutability

**Immutability Contract**:
WorldState should be treated as immutable during observation and evaluation.
Only SimulationEngine may create new WorldState instances.

### TrafficLightInfo

**Fields**:
- state: Enum {RED, YELLOW, GREEN, NONE}
- position: (x, y) of signal head
- stop_line_position: (x, y) where vehicles must stop
- light_id: Unique identifier

### LaneInfo

Represents a single lane.

**Fields**:
- lane_id: Unique identifier
- centerline_points: List of (x, y) points defining centerline
  - Points ordered from start to end
- width: Lane width in meters
- speed_limit: Speed limit in m/s

**Operations**:
- get_closest_point(position): Project position onto centerline
  - Returns (closest_point, lateral_offset)


--------------------------------------------------------------------------------
10. OBSERVATION FORMAT SPECIFICATION
--------------------------------------------------------------------------------

### Observation

The standardized input to models. Contains ALL information the model needs
to make a decision.

**Design Principles**:
- **Complete**: No hidden state
- **Markovian**: Contains sufficient history (via derivatives)
- **Standardized**: Same structure for all scenarios
- **Compact**: Efficient for neural networks
- **Interpretable**: Human-readable structure

**Ego State Fields**:
- ego_speed: m/s
- ego_acceleration: m/s²
- ego_heading_rate: rad/s (derivative of heading)

**Lane Information**:
- lane_offset: Meters from lane center (positive = right)
- lane_heading_error: Radians from lane direction
- lane_width: Meters
- distance_to_lane_end: Meters until lane ends

**Nearby Objects**:
- objects: List[ObjectObservation], max 10 objects
  - Sorted by distance (closest first)
  - Each object in ego's reference frame

**Traffic Signals**:
- nearest_traffic_light_state: Enum {NONE, GREEN, YELLOW, RED}
- distance_to_traffic_light: Meters
- distance_to_stop_line: Meters

**Speed Limits**:
- current_speed_limit: m/s

**Time**:
- sim_time: Seconds since scenario start

**Object Observation** (nested):
- relative_x: Meters forward from ego (positive = ahead)
- relative_y: Meters lateral from ego (positive = right)
- relative_vx: Relative velocity forward (m/s)
- relative_vy: Relative velocity lateral (m/s)
- object_type: Enum
- length, width: Meters
- distance: Euclidean distance to ego
- object_id: For tracking

**Coordinate Frame**:
All object positions and velocities are in ego vehicle's reference frame:
- x-axis: Forward from ego
- y-axis: Right from ego
- Origin: Ego vehicle center

**Representations**:

1. **Structured** (dictionary): For interpretable models
```
{
  "ego_speed": 25.0,
  "objects": [
    {"relative_x": 50.0, "relative_y": 0.0, ...},
    ...
  ],
  ...
}
```

2. **Flat Vector** (numpy): For neural networks
```
[ego_speed, ego_accel, lane_offset, ..., obj0_x, obj0_y, ...]
```
Size: 13 + 10*8 = 93 elements (fixed)

**Missing Objects**: If fewer than 10 objects, pad with zeros

**Generation**: Created from WorldState using transform:
```
observation = Observation.from_world_state(world, previous_world)
```


--------------------------------------------------------------------------------
11. ACTION FORMAT SPECIFICATION
--------------------------------------------------------------------------------

### Action

The standardized output from models. Represents control commands.

**Fields**:
- steering: Normalized steering [-1, 1]
  - -1 = maximum left turn
  -  0 = straight
  - +1 = maximum right turn
  - Maps to actual angle: δ = steering * max_steering

- throttle: Normalized throttle [0, 1]
  - 0 = no throttle
  - 1 = maximum throttle
  - Maps to acceleration: a = throttle * max_accel

- brake: Normalized brake [0, 1]
  - 0 = no brake
  - 1 = maximum brake  
  - Maps to deceleration: a = -brake * max_decel

**Control Semantics**:
- If both throttle and brake > 0, brake takes precedence
- Actual acceleration: a = throttle * max_accel - brake * max_decel (simplified)
- More accurately: a = throttle * max_accel if brake < 0.01, else a = -brake * max_decel

**Validation**:
- All values must be in specified ranges
- Actions validated before application
- Invalid actions terminate simulation with INVALID_ACTION

**Alternative Format**:
Some models prefer steering + acceleration (single value):
- steering: [-1, 1]
- acceleration: [-1, 1], negative = braking

This can be converted to/from standard format.

**Special Actions**:
- Action.zero(): No control (coast)
- Action.emergency_brake(): Maximum braking, straight


--------------------------------------------------------------------------------
12. EVENT SCHEMA SPECIFICATION
--------------------------------------------------------------------------------

### ScenarioEvent

Represents a timed event that modifies world state during simulation.

**Common Fields**:
- type: Event type enum
- trigger_time: Simulation time when event occurs (seconds)
- parameters: Event-specific parameters (dictionary)

**Event Types**:

**1. spawn_vehicle**
Spawns a new vehicle at specified location.

Parameters:
- x, y: Position
- heading: Orientation (radians)
- velocity: Initial speed (m/s)
- vehicle_type: "car", "truck", etc.
- behavior: Behavior specification
- id: Unique identifier

**2. spawn_pedestrian**
Spawns a pedestrian crossing.

Parameters:
- x, y: Spawn position
- crossing_speed: m/s
- target_position: Where pedestrian walks to
- id: Identifier

**3. change_traffic_light**
Changes traffic signal state.

Parameters:
- light_id: Which light to change
- new_state: "red", "yellow", "green"

**4. change_weather**
Modifies weather conditions.

Parameters:
- condition: "clear", "rain", "fog"
- visibility: Meters

**5. object_behavior_change**
Modifies an existing object's behavior.

Parameters:
- object_id: Which object
- new_behavior: Behavior specification

**Event Execution**:
- Events checked every timestep
- When sim_time >= trigger_time, event executes
- Each event executes exactly once
- Events applied in deterministic order (by trigger_time, then type)


================================================================================
PART 4: ALGORITHMS & MATHEMATICS
================================================================================

--------------------------------------------------------------------------------
13. VEHICLE PHYSICS MODEL
--------------------------------------------------------------------------------

### Bicycle Model Equations

The vehicle uses a kinematic bicycle model - simplified but sufficient for
robustness evaluation.

**State Vector**:
X = [x, y, θ, v]

Where:
- (x, y): Position in global frame (meters)
- θ: Heading angle (radians)
- v: Speed (m/s, scalar)

**Control Inputs**:
U = [δ, a]

Where:
- δ: Steering angle (radians)
- a: Acceleration (m/s²)

**Discrete-Time Update Equations**:

```
x[n+1] = x[n] + v[n] * cos(θ[n]) * dt
y[n+1] = y[n] + v[n] * sin(θ[n]) * dt
θ[n+1] = θ[n] + (v[n] / L) * tan(δ[n]) * dt
v[n+1] = clamp(v[n] + a[n] * dt, 0, v_max)
```

Where:
- dt: Fixed timestep (0.02s)
- L: Wheelbase (2.7m typical)
- clamp(x, min, max): Constrains x to [min, max]

**Integration Method**: Explicit Euler (first-order)
- Simple, deterministic, sufficient accuracy for dt=0.02s
- Higher-order methods (RK4) not necessary for this application

**Constraints Applied Before Update**:
```
δ = clamp(δ, -δ_max, δ_max)
a = clamp(a, -a_max_brake, a_max_accel)
```

**Constraint Validation After Update**:
```
v must be in [0, v_max]
```

**Special Cases**:

1. **Low Velocity**: When |v| < ε (e.g., 1e-9), heading update skipped
   - Prevents division by zero in bicycle model
   - Vehicle at rest doesn't change heading

2. **Angle Wrapping**: Heading wrapped to (-π, π] using:
   ```
   θ_wrapped = arctan2(sin(θ), cos(θ))
   ```
   - Ensures consistent representation
   - Critical for determinism

### Bicycle Model Assumptions

**Valid For**:
- Low lateral acceleration (<0.5g)
- Moderate speeds (0-35 m/s)
- Dry pavement
- Normal driving maneuvers

**Not Valid For**:
- Drifting or sliding
- High-speed racing
- Off-road conditions
- Tire dynamics

**Rationale**: AREP evaluates planning/decision-making, not vehicle dynamics.
Simplified physics sufficient for this purpose.

### Alternative Models (Future)

For higher fidelity:
- **Dynamic Bicycle Model**: Includes lateral tire forces
- **Single-Track Model**: Adds tire slip angles
- **Multi-Body Model**: Separate front/rear dynamics

Current bicycle model is baseline. Scenarios can specify required physics fidelity.


--------------------------------------------------------------------------------
14. COLLISION DETECTION ALGORITHM
--------------------------------------------------------------------------------

### Oriented Bounding Box (OBB) Representation

Each vehicle represented as oriented rectangle:
- Center: (x, y)
- Heading: θ
- Half-dimensions: (length/2, width/2)

**Vertex Computation**:
1. Define local corners relative to vehicle center:
   ```
   local = [
     (+length/2, +width/2),  # front-right
     (+length/2, -width/2),  # front-left
     (-length/2, -width/2),  # rear-left
     (-length/2, +width/2),  # rear-right
   ]
   ```

2. Apply rotation matrix R(θ):
   ```
   R = [cos(θ)  -sin(θ)]
       [sin(θ)   cos(θ)]
   ```

3. Transform to global frame:
   ```
   global_vertex = R * local_vertex + center
   ```

**Order Critical**: Vertices MUST be computed in fixed order for determinism.

### Separating Axis Theorem (SAT)

**Theorem**: Two convex polygons do NOT collide if there exists an axis
where their projections don't overlap.

**Axes to Test**:
For two rectangles A and B:
- 2 axes from A (perpendicular to edges)
- 2 axes from B (perpendicular to edges)
- Total: 4 axes (some may be parallel, but test all for simplicity)

**Algorithm**:
```
function check_collision(A, B):
    axes = get_edge_normals(A) + get_edge_normals(B)
    
    for axis in axes:
        proj_A = project_polygon(A, axis)
        proj_B = project_polygon(B, axis)
        
        if not projections_overlap(proj_A, proj_B):
            return False  # Found separating axis
    
    return True  # No separating axis found, collision!
```

**Projection onto Axis**:
```
function project_polygon(polygon, axis):
    projections = []
    for vertex in polygon:
        projection = dot(vertex, axis)
        projections.append(projection)
    
    return (min(projections), max(projections))
```

**Overlap Check**:
```
function projections_overlap(proj_A, proj_B):
    min_A, max_A = proj_A
    min_B, max_B = proj_B
    
    if max_A < min_B - tolerance:
        return False
    if max_B < min_A - tolerance:
        return False
    
    return True
```

**Tolerance**: Small epsilon (1e-6) to handle floating-point errors.

### Determinism Requirements for Collision Detection

1. **Object Iteration Order**: Check collisions in sorted object ID order
   ```
   for obj in sorted(objects, key=lambda o: o.object_id):
       check_collision(ego, obj)
   ```

2. **Vertex Order**: Always compute vertices in same order (front-right, front-left, ...)

3. **Axis Order**: Test axes in fixed order (A's axes first, then B's)

4. **Floating-Point**: Use consistent tolerance for comparisons

### Collision Event Details

When collision detected, record:
- object_id: ID of colliding object
- sim_time: When collision occurred
- impact_speed: |v_ego - v_object|
- impact_angle: Angle between velocity vectors
- collision_point: Approximate point of impact (midpoint between centers)

### Performance Optimization

**Current**: O(n) collision checks per timestep (ego vs. each object)

**Future Optimization** (if needed):
- Spatial hashing for many objects
- Bounding sphere pre-check before OBB/SAT
- SIMD vectorization of projection calculations

For typical scenarios (<50 objects), current approach sufficient.


--------------------------------------------------------------------------------
15. TIME-TO-COLLISION CALCULATION
--------------------------------------------------------------------------------

### TTC Definition

Time-To-Collision (TTC): Time until collision if both vehicles maintain
current velocities (constant-velocity assumption).

### Algorithm

**Inputs**:
- Ego state: position p_e, velocity v_e (as vector)
- Object state: position p_o, velocity v_o (as vector)

**Step 1: Compute Relative Motion**
```
p_rel = p_o - p_e  (relative position)
v_rel = v_o - v_e  (relative velocity)
```

**Step 2: Check if Approaching**
```
closing_speed = -dot(p_rel, v_rel) / ||p_rel||
```

If closing_speed <= 0, vehicles are moving apart or parallel → TTC = ∞

**Step 3: Compute TTC**
```
TTC = ||p_rel|| / closing_speed
```

This is the time until centers coincide under constant velocity.

**Step 4: Validity Checks**

Only consider TTC valid if:
1. closing_speed > 0 (approaching)
2. Object is in forward cone (angle < 60°)
3. Object is within lateral threshold (|lateral_offset| < 5m)

These filters prevent spurious TTC values for objects not on collision course.

### Forward Cone Check

```
ego_forward = (cos(θ_ego), sin(θ_ego))
to_object = normalize(p_rel)
angle = arccos(dot(ego_forward, to_object))

if angle > forward_cone_angle:
    return None  # Object not in forward cone
```

### Lateral Threshold Check

Transform object position to ego frame:
```
lateral = dot(p_rel, ego_perpendicular)

if |lateral| > threshold:
    return None  # Too far laterally
```

### Minimum TTC Tracking

For safety metrics, track minimum TTC across all objects over entire simulation:
```
min_ttc = ∞

for each timestep:
    for each object:
        ttc = compute_ttc(ego, object)
        if ttc is not None:
            min_ttc = min(min_ttc, ttc)

return min_ttc
```

### Limitations

**Assumptions**:
- Constant velocity (no acceleration)
- Straight-line motion (no steering)
- Point masses (no size)

**Actual Use**: TTC is conservative estimate of collision risk. Real collision
may not occur if vehicles maneuver. But low TTC indicates dangerous proximity.

### TTC Categories for Safety Assessment

- TTC > 10s: Safe
- 5s < TTC <= 10s: Attention needed
- 2s < TTC <= 5s: Caution
- TTC <= 2s: Critical (emergency response needed)


--------------------------------------------------------------------------------
16. RANDOMNESS MANAGEMENT STRATEGY
--------------------------------------------------------------------------------

### Hierarchical Seeding Architecture

All randomness derives from a single master seed through deterministic
derivation.

```
Master Seed (σ)
    ├─→ Scenario Seed (σ_scenario)
    ├─→ Traffic Seed (σ_traffic)
    ├─→ Pedestrian Seed (σ_pedestrian)
    ├─→ Weather Seed (σ_weather)
    └─→ Noise Seed (σ_noise)
```

**Seed Derivation**:
```
subsystem_seed = SHA256(master_seed || subsystem_name)[:4 bytes] as int
```

Using cryptographic hash ensures:
- Deterministic: Same master seed produces same subsystem seeds
- Independent: Changing one subsystem doesn't affect others
- Unpredictable: No correlation between subsystem seeds

### Subsystem Generators

Each subsystem gets independent NumPy Generator:
```
rng_scenario = numpy.random.Generator(numpy.random.PCG64(σ_scenario))
rng_traffic = numpy.random.Generator(numpy.random.PCG64(σ_traffic))
...
```

**PCG64**: Fast, high-quality pseudorandom generator
- 128-bit state
- Period of 2^128
- Passes statistical tests (TestU01, PractRand)

### Usage Pattern

```
# Initialize at simulation start
rng_manager = RandomManager(master_seed=42)

# Use specific subsystem
noise_value = rng_manager.get("noise").normal(0, 0.1)
spawn_position = rng_manager.get("scenario").uniform(0, 100)
```

### State Saving/Restoration

For replay and debugging:
```
# Save state
state = rng_manager.save_state()
# Returns: dict mapping subsystem → (seed, generator_state)

# Restore state
rng_manager.restore_state(state)
# Now generates same sequence as if restarted from this point
```

### Batch Execution Seed Strategy

For N parallel runs:
```
seeds = [master_seed + i for i in range(N)]
```

Or using hash-based derivation:
```
seeds = [hash(master_seed, i) for i in range(N)]
```

Each run gets unique seed, ensuring statistical independence.

### Forbidden Randomness Patterns

**Never Use**:
```python
import random
random.random()  # Uses global state, not seeded per run

import numpy as np
np.random.rand()  # Uses global RandomState, not seeded per run

import os
os.urandom(10)  # Uses OS entropy, non-deterministic
```

**Always Use**:
```python
rng = rng_manager.get("subsystem_name")
value = rng.normal(0, 1)
```


[Document continues with Parts 5-13 covering remaining systems]

================================================================================
REMAINING SECTIONS SUMMARY
================================================================================

The complete specification continues with detailed specifications for:

PART 5: SIMULATION ENGINE - World management, loop execution, termination
PART 6: SCENARIO SYSTEM - YAML parsing, validation, execution, events  
PART 7: MODEL INTERFACE - Interface contract, execution, sandboxing, timeouts
PART 8: EVALUATION & METRICS - All metric definitions and computation algorithms
PART 9: STATISTICAL FRAMEWORK - Batch execution, aggregation, confidence intervals
PART 10: DATA PERSISTENCE - Database schema, ORM, queries, migrations
PART 11: API & INTERFACES - REST API, WebSocket, authentication
PART 12: TESTING STRATEGY - All test types with specific requirements
PART 13: DEPLOYMENT & OPERATIONS - Docker, Kubernetes, monitoring, scaling

Each section follows the same level of detail as shown above - complete
specifications without code implementations.

================================================================================
END OF IMPLEMENTATION SPECIFICATION DOCUMENT
================================================================================

This document provides the blueprint for implementation. Actual code
implementations are in separate Python files following the structure defined
herein.

For questions or clarifications, refer to:
- Architecture documentation (docs/architecture.md)
- API reference (docs/api_reference.md)  
- Deployment guide (docs/deployment_guide.md)
