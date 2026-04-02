# AREP - Autonomous Robustness Evaluation Platform

Complete implementation of deterministic, statistically rigorous evaluation framework for autonomous driving systems.

## Project Structure

This project is separated into two main parts:

### 1. Implementation Specification Document
**File**: `AREP_IMPLEMENTATION_SPECIFICATION.md`

This document provides complete specifications for what to build:
- Architecture and design decisions
- Algorithms and mathematical models
- Data structures and schemas
- Requirements and constraints
- **Does NOT contain code implementations**

### 2. Code Implementation
**Directory**: `arep_implementation/`

Python implementation of all modules:

```
arep_implementation/
├── arep/                       # Main package
│   ├── core/                  # Core simulation components
│   │   ├── state.py          ✓ Complete implementation
│   │   ├── physics.py        ✓ Complete implementation
│   │   ├── action.py         ✓ Complete implementation
│   │   ├── collision.py      # To be implemented
│   │   ├── observation.py    # To be implemented
│   │   └── ttc.py           # To be implemented
│   │
│   ├── simulation/           # Simulation engine
│   │   ├── engine.py        # To be implemented
│   │   ├── world.py         # To be implemented
│   │   └── termination.py   # To be implemented
│   │
│   ├── scenario/            # Scenario system
│   │   ├── schema.py       # To be implemented
│   │   ├── parser.py       # To be implemented
│   │   └── validator.py    # To be implemented
│   │
│   ├── models/             # Model interface
│   │   ├── interface.py   ✓ Complete implementation (with example)
│   │   └── local_executor.py  # To be implemented
│   │
│   └── evaluation/         # Metrics and scoring
│       ├── collector.py    # To be implemented
│       └── safety.py       # To be implemented
│
├── tests/                  # Test suite
│   ├── unit/              # Unit tests
│   └── integration/       # Integration tests
│
└── scenarios/             # Example scenario definitions
    └── basic/            # Basic scenarios (YAML)
```

## Completed Implementations

### ✓ core/state.py
Complete state representation system:
- `Vector2D`: 2D vector with deterministic operations
- `VehicleState`: Complete vehicle state with physics properties
- `WorldState`: Full simulation world state
- Enums: `ObjectType`, `TrafficLightState`, `TerminationReason`

**Key Features**:
- Bounding box computation for collision detection
- Serialization to/from dictionaries and JSON
- Deep copying for immutability
- Velocity vector computations

### ✓ core/physics.py
Deterministic bicycle model physics engine:
- Fixed timestep integration (dt = 0.02s)
- Bicycle model kinematics
- Constraint enforcement
- Stopping distance/time calculations

**Key Features**:
- Explicit Euler integration
- Angle wrapping to [-π, π]
- Numerical stability with epsilon tolerance
- Action validation

### ✓ core/action.py
Control action representation:
- Normalized control inputs (steering, throttle, brake)
- Validation and clamping
- Conversion to physical values
- Serialization support

**Key Features**:
- Range validation in __post_init__
- Utility constructors (zero, emergency_brake)
- Array conversion for ML models

### ✓ models/interface.py
Abstract model interface with example:
- `ModelInterface`: Abstract base class defining contract
- `PIDController`: Complete example implementation

**Key Features**:
- Clear interface contract
- State save/restore for replay
- Metadata for documentation
- Working PID controller example

## How to Use

### 1. Read the Specification
Start with `AREP_IMPLEMENTATION_SPECIFICATION.md` to understand:
- System architecture
- Design decisions
- Requirements and constraints

### 2. Implement Remaining Modules
Follow the specification to implement:
- Collision detection (core/collision.py)
- Observation generation (core/observation.py)
- Simulation engine (simulation/engine.py)
- Scenario system (scenario/*.py)
- Metrics (evaluation/*.py)

### 3. Follow the Patterns
Use completed modules as reference:
- Dataclasses for data structures
- Type hints throughout
- Docstrings with Args/Returns
- Deterministic operations
- Comprehensive validation

## Development Workflow

### Setup
```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install numpy>=1.26.0

# Install package in development mode
cd arep_implementation
pip install -e .
```

### Testing
```bash
# Run unit tests
pytest tests/unit/

# Run determinism tests
pytest tests/determinism/

# Run specific test
pytest tests/unit/test_physics.py -v
```

### Adding a New Module

1. **Read specification** for that module in the spec document
2. **Create file** in appropriate directory
3. **Implement** following patterns from completed modules
4. **Add tests** in tests/ directory
5. **Validate** determinism and correctness

## Key Design Principles

### Determinism First
- Fixed timestep only
- No wall clock dependency
- Seeded randomness only
- Stable iteration orders
- Version-locked dependencies

### Clean Architecture
- Pure functions where possible
- Immutable data structures (copy for mutation)
- Clear separation of concerns
- No circular dependencies

### Complete Documentation
- Every public function has docstring
- Complex algorithms explained
- Type hints throughout
- Examples in docstrings

## Next Steps

Priority order for implementation:

1. **core/collision.py** - OBB + SAT collision detection
2. **core/observation.py** - Observation generation from WorldState
3. **simulation/engine.py** - Main simulation loop
4. **scenario/parser.py** - YAML scenario parsing
5. **evaluation/safety.py** - Safety metrics computation
6. **execution/batch.py** - Batch execution for statistics

Each module specification is in the Implementation Specification Document.

## Example Usage (Future)

```python
from arep.simulation.engine import SimulationEngine
from arep.models.interface import PIDController
from arep.scenario.parser import ScenarioParser

# Load scenario
parser = ScenarioParser()
scenario = parser.parse_file("scenarios/basic/highway_merge.yaml")

# Create model
model = PIDController(kp=1.0, ki=0.1, kd=0.5)

# Run simulation
engine = SimulationEngine()
world = engine.initialize(scenario, seed=42)
world = engine.run_simulation(world, model, max_steps=3000)

# Check results
print(f"Collision: {world.has_collision}")
print(f"Final time: {world.sim_time}s")
```

## Contributing

1. Follow PEP 8 style guide
2. Add type hints to all functions
3. Write docstrings for public APIs
4. Include unit tests
5. Verify determinism tests pass

## License

[To be determined]

## Contact

[To be determined]
