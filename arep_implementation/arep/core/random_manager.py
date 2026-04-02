"""
ORION Randomness Management System.

Hierarchical seeding via SHA256 derivation. Each subsystem gets an
independent numpy.random.Generator(PCG64) so that changes to one
subsystem's random usage don't affect others.

    Master Seed (σ)
        ├─→ scenario
        ├─→ traffic
        ├─→ pedestrian
        ├─→ weather
        └─→ noise
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import numpy as np

from arep.utils.hashing import derive_seed


# Standard subsystem names
SUBSYSTEMS = ("scenario", "traffic", "pedestrian", "weather", "noise")


class RandomManager:
    """
    Deterministic random number management.

    Usage:
        rng = RandomManager(master_seed=42)
        noise = rng.get("noise").normal(0, 0.1)
        spawn_x = rng.get("scenario").uniform(0, 100)

    Guarantees:
        - Same master_seed → same generator states
        - Subsystems are independent (using one doesn't affect others)
        - State can be saved/restored for replay
    """

    def __init__(self, master_seed: int):
        self.master_seed = master_seed
        self._generators: Dict[str, np.random.Generator] = {}
        self._seeds: Dict[str, int] = {}

        # Initialize standard subsystems
        for subsystem in SUBSYSTEMS:
            self._init_subsystem(subsystem)

    def _init_subsystem(self, subsystem: str) -> None:
        """Create a generator for a subsystem."""
        seed = derive_seed(self.master_seed, subsystem)
        self._seeds[subsystem] = seed
        self._generators[subsystem] = np.random.Generator(
            np.random.PCG64(seed)
        )

    def get(self, subsystem: str) -> np.random.Generator:
        """
        Get the random generator for a subsystem.

        Creates on-demand if the subsystem wasn't pre-registered.

        Args:
            subsystem: Subsystem identifier.

        Returns:
            numpy Generator for that subsystem.
        """
        if subsystem not in self._generators:
            self._init_subsystem(subsystem)
        return self._generators[subsystem]

    def save_state(self) -> Dict[str, Any]:
        """
        Save all generator states for replay/debugging.

        Returns:
            Dict mapping subsystem name → (seed, generator bit_generator state).
        """
        state = {}
        for name, gen in self._generators.items():
            state[name] = {
                "seed": self._seeds[name],
                "bit_generator_state": gen.bit_generator.state,
            }
        return state

    def restore_state(self, state: Dict[str, Any]) -> None:
        """
        Restore generator states from a saved snapshot.

        After restoration, generators will produce the same
        sequence as if they'd been used from the saved point.
        """
        for name, sub_state in state.items():
            seed = sub_state["seed"]
            self._seeds[name] = seed
            gen = np.random.Generator(np.random.PCG64(seed))
            gen.bit_generator.state = sub_state["bit_generator_state"]
            self._generators[name] = gen

    def reset(self) -> None:
        """
        Reset all generators to their initial state (as if just constructed).
        """
        self._generators.clear()
        self._seeds.clear()
        for subsystem in SUBSYSTEMS:
            self._init_subsystem(subsystem)


# ── Utility functions ────────────────────────────────────────────────────

def add_gaussian_noise(
    value: float,
    std: float,
    rng: np.random.Generator,
) -> float:
    """
    Add Gaussian noise to a value.

    Args:
        value: Base value.
        std: Standard deviation of noise.
        rng: Random generator to use.

    Returns:
        value + noise
    """
    return value + float(rng.normal(0.0, std))


def sample_uniform_position(
    x_range: tuple[float, float],
    y_range: tuple[float, float],
    rng: np.random.Generator,
) -> tuple[float, float]:
    """
    Sample a uniform random (x, y) position.

    Args:
        x_range: (min_x, max_x).
        y_range: (min_y, max_y).
        rng: Random generator.

    Returns:
        (x, y) tuple.
    """
    x = float(rng.uniform(x_range[0], x_range[1]))
    y = float(rng.uniform(y_range[0], y_range[1]))
    return x, y


def sample_velocity(
    min_v: float,
    max_v: float,
    rng: np.random.Generator,
) -> float:
    """
    Sample a uniform random velocity.

    Args:
        min_v: Minimum velocity.
        max_v: Maximum velocity.
        rng: Random generator.

    Returns:
        Sampled velocity.
    """
    return float(rng.uniform(min_v, max_v))
