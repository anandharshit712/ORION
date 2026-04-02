"""
ORION Visualization - Plot Generation.

Creates matplotlib charts for evaluation results:
  - Radar chart (composite breakdown)
  - Score distribution histogram
  - TTC timeline
  - Comparison bar chart
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

try:
    import matplotlib
    matplotlib.use("Agg")  # Non-interactive backend
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False

from arep.evaluation.composite import EvaluationResult
from arep.statistics.aggregator import AggregatedMetrics


def _check_matplotlib():
    if not HAS_MATPLOTLIB:
        raise ImportError(
            "matplotlib is required for visualization. "
            "Install with: pip install matplotlib"
        )


def create_radar_chart(
    result: EvaluationResult,
    output_path: Optional[str] = None,
) -> Optional[bytes]:
    """
    Create a radar chart showing the four metric categories.

    Args:
        result: Single evaluation result.
        output_path: If provided, save to file.

    Returns:
        PNG bytes if output_path is None, else None.
    """
    _check_matplotlib()

    categories = ["Safety", "Compliance", "Stability", "Reactivity"]
    values = [
        result.safety.safety_score,
        result.compliance.compliance_score,
        result.stability.stability_score,
        result.reactivity.reactivity_score,
    ]

    # Close the polygon
    angles = np.linspace(0, 2 * np.pi, len(categories), endpoint=False).tolist()
    values += values[:1]
    angles += angles[:1]

    fig, ax = plt.subplots(figsize=(6, 6), subplot_kw=dict(polar=True))

    ax.fill(angles, values, color="#4fc3f7", alpha=0.25)
    ax.plot(angles, values, color="#0288d1", linewidth=2)
    ax.scatter(angles[:-1], values[:-1], color="#01579b", s=60, zorder=5)

    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(categories, fontsize=12)
    ax.set_ylim(0, 1.0)
    ax.set_yticks([0.2, 0.4, 0.6, 0.8, 1.0])
    ax.set_yticklabels(["0.2", "0.4", "0.6", "0.8", "1.0"], fontsize=8)

    ax.set_title(
        f"{result.model_name} - {result.scenario_name}\n"
        f"Composite: {result.composite_score:.3f}",
        fontsize=14, fontweight="bold", pad=20,
    )

    plt.tight_layout()

    if output_path:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        plt.savefig(output_path, dpi=150, bbox_inches="tight")
        plt.close(fig)
        return None
    else:
        buf = BytesIO()
        plt.savefig(buf, format="png", dpi=150, bbox_inches="tight")
        plt.close(fig)
        buf.seek(0)
        return buf.read()


def create_score_distribution(
    results: List[EvaluationResult],
    output_path: Optional[str] = None,
) -> Optional[bytes]:
    """
    Create histogram of composite score distribution.

    Args:
        results: List of evaluation results.
        output_path: If provided, save to file.

    Returns:
        PNG bytes if output_path is None, else None.
    """
    _check_matplotlib()

    scores = [r.composite_score for r in results]

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.hist(scores, bins=20, color="#4fc3f7", edgecolor="#0288d1", alpha=0.8)
    ax.axvline(np.mean(scores), color="#e53935", linestyle="--",
               linewidth=2, label=f"Mean: {np.mean(scores):.3f}")
    ax.set_xlabel("Composite Score", fontsize=12)
    ax.set_ylabel("Frequency", fontsize=12)
    ax.set_title("Score Distribution", fontsize=14, fontweight="bold")
    ax.legend(fontsize=11)
    ax.set_xlim(0, 1)

    plt.tight_layout()

    if output_path:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        plt.savefig(output_path, dpi=150, bbox_inches="tight")
        plt.close(fig)
        return None
    else:
        buf = BytesIO()
        plt.savefig(buf, format="png", dpi=150, bbox_inches="tight")
        plt.close(fig)
        buf.seek(0)
        return buf.read()


def create_comparison_chart(
    model_metrics: Dict[str, AggregatedMetrics],
    output_path: Optional[str] = None,
) -> Optional[bytes]:
    """
    Create grouped bar chart comparing multiple models.

    Args:
        model_metrics: {model_name: AggregatedMetrics}.
        output_path: If provided, save to file.

    Returns:
        PNG bytes if output_path is None, else None.
    """
    _check_matplotlib()

    model_names = list(model_metrics.keys())
    categories = ["Safety", "Compliance", "Stability", "Reactivity", "Composite"]
    colors = ["#e53935", "#43a047", "#1e88e5", "#fb8c00", "#8e24aa"]

    x = np.arange(len(model_names))
    width = 0.15

    fig, ax = plt.subplots(figsize=(10, 6))

    for i, (cat, color) in enumerate(zip(categories, colors)):
        if cat == "Composite":
            vals = [model_metrics[m].composite_mean for m in model_names]
        elif cat == "Safety":
            vals = [model_metrics[m].safety_mean for m in model_names]
        elif cat == "Compliance":
            vals = [model_metrics[m].compliance_mean for m in model_names]
        elif cat == "Stability":
            vals = [model_metrics[m].stability_mean for m in model_names]
        else:
            vals = [model_metrics[m].reactivity_mean for m in model_names]

        ax.bar(x + i * width, vals, width, label=cat, color=color, alpha=0.85)

    ax.set_xlabel("Model", fontsize=12)
    ax.set_ylabel("Score", fontsize=12)
    ax.set_title("Model Comparison", fontsize=14, fontweight="bold")
    ax.set_xticks(x + width * 2)
    ax.set_xticklabels(model_names, fontsize=10)
    ax.set_ylim(0, 1.1)
    ax.legend(fontsize=10, loc="upper right")

    plt.tight_layout()

    if output_path:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        plt.savefig(output_path, dpi=150, bbox_inches="tight")
        plt.close(fig)
        return None
    else:
        buf = BytesIO()
        plt.savefig(buf, format="png", dpi=150, bbox_inches="tight")
        plt.close(fig)
        buf.seek(0)
        return buf.read()
