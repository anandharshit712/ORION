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

    def __init__(self, require_pdf: bool = True):
        """
        Args:
            require_pdf: check the PDF toolchain up front. Pass False to render
                HTML on a machine without WeasyPrint's native GTK libraries —
                the content is identical, and that is what the tests assert.
        """
        self._check_dependencies(require_pdf=require_pdf)

    @staticmethod
    def _check_dependencies(require_pdf: bool = True) -> None:
        if require_pdf:
            try:
                import weasyprint  # noqa: F401
            except ImportError:
                raise ImportError(
                    "weasyprint is not installed. "
                    "Install with: pip install arep[reporting]"
                )
            except OSError as exc:
                # Installed, but its GTK/Pango libraries are missing — the
                # usual state on Windows. Say which of the two it is, because
                # "pip install" does not fix the second one.
                raise ImportError(
                    f"weasyprint is installed but cannot load its native "
                    f"libraries ({exc}). On Windows install the GTK3 runtime; "
                    f"on Debian/Ubuntu install libpango-1.0-0 and "
                    f"libpangoft2-1.0-0. HTML rendering works without them: "
                    f"PDFGenerator(require_pdf=False).render_html(...)"
                ) from exc
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

        This is the artefact a customer forwards to their safety reviewer, so
        it carries the caveats as well as the numbers — a report that lists
        only strengths is marketing, and a reviewer who finds the omission
        stops trusting the rest of it.
        """
        return self._render("batch_report.html", {"batch": batch_data}, output_path)

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

        """
        return self._render(
            "comparison_report.html", {"comparison": comparison_data}, output_path,
        )

    # ── Internals ────────────────────────────────────────────────────

    def render_html(self, template_name: str, context: dict) -> str:
        """Render a report template to HTML.

        Split from the PDF step on purpose. Every content bug lives here — a
        missing figure, a mislabelled column, a caveat that did not make it
        into the page — while the PDF step is one library call. Separating them
        means the content is testable on any machine, including this one, where
        WeasyPrint cannot load its GTK native libraries at all.
        """
        from jinja2 import (
            Environment, FileSystemLoader, StrictUndefined, select_autoescape,
        )

        environment = Environment(
            loader=FileSystemLoader(str(TEMPLATES_DIR)),
            autoescape=select_autoescape(["html"]),
            # StrictUndefined: a typo in a template key would otherwise render
            # as a blank cell, and a safety report with a silently empty number
            # is worse than one that fails to build.
            undefined=StrictUndefined,
        )
        environment.globals["generated_at"] = _now_iso()
        # base.html puts an organisation in the header. Defaulted rather than
        # required, so a caller who omits it still gets a report; anything in
        # the context wins.
        environment.globals.setdefault("org_name", "ORION")

        return environment.get_template(template_name).render(**context)

    def _render(self, template_name: str, context: dict, output_path) -> bytes:
        """Render a template to PDF bytes, optionally writing it out."""
        import weasyprint

        html = self.render_html(template_name, context)
        pdf_bytes = weasyprint.HTML(string=html, base_url=str(TEMPLATES_DIR)).write_pdf()

        if output_path is not None:
            path = Path(output_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(pdf_bytes)
            logger.info("Wrote report to %s (%d bytes)", path, len(pdf_bytes))

        return pdf_bytes

    def _load_template(self, template_name: str) -> str:
        """Load and return a Jinja2 template string."""
        template_path = TEMPLATES_DIR / template_name
        if not template_path.exists():
            raise FileNotFoundError(f"Report template not found: {template_path}")
        return template_path.read_text(encoding="utf-8")


def _now_iso() -> str:
    """Timestamp for the report footer.

    Wall-clock is fine here and nowhere near the simulation: a report records
    when it was produced, which is not part of any run.
    """
    import datetime

    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
