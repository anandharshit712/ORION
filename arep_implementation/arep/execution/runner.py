"""
ORION Batch Execution Runner.

Orchestrates running multiple simulations with the full pipeline:
  1. Parse scenario
  2. Create initial world
  3. Run simulation with model
  4. Collect data
  5. Evaluate metrics
  6. Aggregate statistics
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from arep.config import SimulationConfig, get_config
from arep.core.observation import Observation
from arep.core.random_manager import RandomManager
from arep.evaluation.collector import DataCollector
from arep.evaluation.composite import CompositeEvaluator, EvaluationResult
from arep.models.interface import ModelInterface, ModelWrapper
from arep.scenario.executor import ScenarioExecutor
from arep.scenario.parser import ScenarioParser
from arep.simulation.engine import SimulationEngine
from arep.statistics.aggregator import StatisticalAggregator, AggregatedMetrics
from arep.utils.logging_config import get_logger

logger = get_logger("execution.runner")


@dataclass
class BatchResult:
    """Result of a batch evaluation run."""
    scenario_name: str
    model_name: str
    num_runs: int
    aggregated: AggregatedMetrics
    per_run_results: List[EvaluationResult]


class EvaluationRunner:
    """
    High-level evaluation runner.

    Full pipeline: scenario → simulate × N → evaluate → aggregate.

    Usage:
        runner = EvaluationRunner()
        result = runner.run_batch(
            scenario_path="scenarios/basic/straight_road_lead_vehicle.yaml",
            model=SimpleLaneKeepModel(),
            num_runs=100,
            master_seed=42,
        )
        print(result.aggregated.to_dict())
    """

    def __init__(self, config: Optional[SimulationConfig] = None):
        cfg = config or get_config().simulation
        self.sim_config = cfg
        self.engine = SimulationEngine(cfg)
        self.evaluator = CompositeEvaluator()
        self.parser = ScenarioParser()
        self.scenario_executor = ScenarioExecutor(cfg)

    def run_single(
        self,
        scenario_path: str,
        model: ModelInterface,
        master_seed: int = 42,
    ) -> EvaluationResult:
        """
        Run a single simulation and evaluate.

        Args:
            scenario_path: Path to scenario YAML.
            model: Model to evaluate.
            master_seed: Random seed.

        Returns:
            EvaluationResult for this run.
        """
        scenario, _ = self.parser.parse_file(scenario_path)
        rng = RandomManager(master_seed)

        initial_world = self.scenario_executor.create_initial_world(scenario, rng)

        # Wrap model
        wrapper = ModelWrapper(
            model, timeout_ms=get_config().execution.model_timeout_ms
        )

        # Collect data
        collector = DataCollector(
            scenario_name=scenario.name,
            model_name=model.name,
        )

        # Run simulation with data collection
        world = initial_world.copy()
        previous_world = None
        wrapper.reset()

        max_steps = int(scenario.duration / self.sim_config.timestep)

        for step in range(max_steps):
            observation = Observation.from_world_state(world, previous_world)

            try:
                action = wrapper.predict(observation)
            except Exception as e:
                logger.error("Model error at step %d: %s", step, e)
                break

            collector.record_step(world, action, previous_world)

            previous_world = world
            world = self.engine.step(world, action, rng)

            if world.is_terminated:
                break

        record = collector.finalize(world)
        record.master_seed = master_seed

        return self.evaluator.evaluate(record)

    def run_batch(
        self,
        scenario_path: str,
        model: ModelInterface,
        num_runs: int = 100,
        master_seed: int = 42,
    ) -> BatchResult:
        """
        Run N simulations with different seeds and aggregate results.

        Each run uses a unique seed: master_seed + run_index.

        Args:
            scenario_path: Path to scenario YAML.
            model: Model to evaluate.
            num_runs: Number of runs.
            master_seed: Base seed (each run uses master_seed + i).

        Returns:
            BatchResult with aggregated statistics.
        """
        scenario, _ = self.parser.parse_file(scenario_path)
        aggregator = StatisticalAggregator()
        per_run: List[EvaluationResult] = []

        logger.info(
            "Starting batch: scenario=%s, model=%s, runs=%d",
            scenario.name, model.name, num_runs,
        )

        for i in range(num_runs):
            seed = master_seed + i
            result = self.run_single(scenario_path, model, seed)
            aggregator.add_result(result)
            per_run.append(result)

            if (i + 1) % 10 == 0 or i == 0:
                logger.info(
                    "Run %d/%d complete (composite=%.3f)",
                    i + 1, num_runs, result.composite_score,
                )

        aggregated = aggregator.compute()

        logger.info(
            "Batch complete: composite=%.4f±%.4f, collision_rate=%.2f%%",
            aggregated.composite_mean,
            aggregated.composite_std,
            aggregated.collision_rate * 100,
        )

        return BatchResult(
            scenario_name=scenario.name,
            model_name=model.name,
            num_runs=num_runs,
            aggregated=aggregated,
            per_run_results=per_run,
        )

    def save_results(
        self,
        result: BatchResult,
        output_path: str,
    ) -> None:
        """Save batch results to JSON."""
        output = {
            "scenario": result.scenario_name,
            "model": result.model_name,
            "num_runs": result.num_runs,
            "aggregated": result.aggregated.to_dict(),
            "per_run": [r.to_dict() for r in result.per_run_results],
        }
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(output, indent=2))
        logger.info("Results saved to %s", output_path)
