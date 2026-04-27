"""
ORION PDF Report Generator.  [Phase 2]

Generates downloadable evaluation reports using weasyprint (HTML → PDF).
Reports are suitable for presenting to safety boards and regulatory reviewers.

Two report types:
  BatchReport      — single batch: score distributions, event log, verdict
  ComparisonReport — model A vs B: delta table, regressions, recommendation

Requires: weasyprint>=60.0 (install with: pip install arep[reporting])
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from arep.utils.logging_config import get_logger

logger = get_logger("reporting.pdf_generator")

TEMPLATES_DIR = Path(__file__).parent / "templates"


class PDFGenerator:
    """
    Renders HTML report templates to PDF using weasyprint.

    Templates use Jinja2 for variable substitution.
    Requires: weasyprint, jinja2
    """

    def __init__(self):
        self._check_dependencies()

    @staticmethod
    def _check_dependencies() -> None:
        try:
            import weasyprint  # noqa: F401
        except ImportError:
            raise ImportError(
                "weasyprint is not installed. "
                "Install with: pip install arep[reporting]"
            )
        try:
            import jinja2  # noqa: F401
        except ImportError:
            raise ImportError(
                "jinja2 is not installed. "
                "Install with: pip install arep[reporting]"
            )

    def render_batch_report(
        self,
        batch_data: Dict[str, Any],
        output_path: Optional[Path] = None,
    ) -> bytes:
        """
        Render a batch evaluation report to PDF.

        Args:
            batch_data:  Dict containing batch results (scenario_id, model_name,
                         num_runs, aggregated scores, failure report, etc.)
            output_path: If provided, write PDF to this path in addition to returning bytes.

        Returns:
            PDF file contents as bytes.

        TODO [P2]: Load batch_report.html template with Jinja2.
        TODO [P2]: Render template with batch_data.
        TODO [P2]: Convert rendered HTML to PDF with weasyprint.HTML(string=html).write_pdf().
        TODO [P2]: Optionally write to output_path.
        TODO [P2]: Return PDF bytes.
        """
        raise NotImplementedError("PDFGenerator.render_batch_report not yet implemented [P2]")

    def render_comparison_report(
        self,
        comparison_data: Dict[str, Any],
        output_path: Optional[Path] = None,
    ) -> bytes:
        """
        Render a model comparison report to PDF.

        Args:
            comparison_data: Dict containing ComparisonReport data
                             (model_a, model_b, scenario comparisons, regressions, verdict).
            output_path:     If provided, write PDF to this path.

        Returns:
            PDF file contents as bytes.

        TODO [P2]: Load comparison_report.html template with Jinja2.
        TODO [P2]: Render and convert to PDF.
        """
        raise NotImplementedError("PDFGenerator.render_comparison_report not yet implemented [P2]")

    def _load_template(self, template_name: str) -> str:
        """Load and return a Jinja2 template string."""
        template_path = TEMPLATES_DIR / template_name
        if not template_path.exists():
            raise FileNotFoundError(f"Report template not found: {template_path}")
        return template_path.read_text(encoding="utf-8")
