"""
ORION SDK — CLI entry point.

Provides the `orion` command for interacting with the platform from terminal.

Usage:
    orion models list
    orion models upload --name my-model --path myproject.model.MyModel
    orion runs batch --model <model-id> --scenarios LON --runs 10
    orion runs status --batch-id <batch-id>
    orion keys create --label "CI pipeline"
"""

from __future__ import annotations

import os
import sys

try:
    import click
except ImportError:
    raise ImportError("click is required for the CLI. Install with: pip install orion-sdk")


def _get_api_key() -> str:
    """Read API key from ORION_API_KEY env var."""
    key = os.environ.get("ORION_API_KEY", "")
    if not key:
        click.echo("Error: ORION_API_KEY environment variable not set.", err=True)
        sys.exit(1)
    return key


@click.group()
@click.version_option("0.1.0", prog_name="orion")
def main():
    """ORION Evaluation Platform CLI."""
    pass


@main.group()
def models():
    """Manage submitted models."""
    pass


@models.command("list")
def models_list():
    """List all models in your organisation."""
    # TODO [P1]: OrionClient(_get_api_key()).list_models()
    click.echo("models list — not yet implemented [P1]")


@models.command("upload")
@click.option("--name", required=True, help="Model name")
@click.option("--path", required=True, help="Python import path, e.g. mymodule.MyModel")
@click.option("--version", default="v1.0", help="Version string")
def models_upload(name, path, version):
    """Upload a model from a Python import path."""
    # TODO [P1]: Dynamic import from path, upload_model()
    click.echo(f"models upload {name} from {path} — not yet implemented [P1]")


@main.group()
def runs():
    """Manage evaluation runs."""
    pass


@runs.command("batch")
@click.option("--model", required=True, help="Model ID")
@click.option("--scenarios", default="all", help="Scenarios: all, LON, LAT, or specific ID")
@click.option("--runs", default=10, type=int, help="Runs per scenario")
@click.option("--seed", default=42, type=int, help="Master seed")
def runs_batch(model, scenarios, runs, seed):
    """Submit a batch evaluation."""
    # TODO [P1]: OrionClient(_get_api_key()).run_batch(model, ...)
    click.echo(f"runs batch {model} {scenarios} n={runs} — not yet implemented [P1]")


@runs.command("status")
@click.option("--batch-id", required=True, help="Batch job ID")
def runs_status(batch_id):
    """Check the status of a batch job."""
    # TODO [P1]: OrionClient(_get_api_key()).get_batch_results(batch_id)
    click.echo(f"runs status {batch_id} — not yet implemented [P1]")


@main.group()
def keys():
    """Manage API keys."""
    pass


@keys.command("create")
@click.option("--label", default="", help="Human-readable label for this key")
def keys_create(label):
    """Create a new API key."""
    # TODO [P1]: POST /api/keys, print key once
    click.echo(f"keys create '{label}' — not yet implemented [P1]")


@keys.command("list")
def keys_list():
    """List all API keys in your organisation."""
    # TODO [P1]: GET /api/keys
    click.echo("keys list — not yet implemented [P1]")


if __name__ == "__main__":
    main()
