"""
ORION SDK — CLI entry point.

Provides the `orion` command for interacting with the platform from the
terminal.

Usage:
    orion models list
    orion models upload --name my-model --module myproject.model:MyModel
    orion models register --name my-model --image registry/x:v1 --port 8080
    orion runs batch --model <model-id> --scenario <path> --runs 10
    orion runs status --run-id <run-id>
    orion keys create --label "CI pipeline"
    orion keys list
"""

from __future__ import annotations

import importlib
import json
import os
import sys

try:
    import click
except ImportError as e:
    raise ImportError(
        "click is required for the CLI. Install with: pip install 'orion-sdk[cli]'"
    ) from e


def _api_key() -> str:
    key = os.environ.get("ORION_API_KEY", "").strip()
    if not key:
        click.echo("Error: ORION_API_KEY environment variable not set.", err=True)
        sys.exit(1)
    return key


def _base_url() -> str:
    return os.environ.get("ORION_API_URL", "http://localhost:8000")


def _client():
    from orion_sdk.client import OrionClient
    return OrionClient(api_key=_api_key(), base_url=_base_url())


def _import_callable(spec: str):
    """Import a `module.path:ClassName` spec and return the callable."""
    if ":" not in spec:
        raise click.ClickException(
            f"Invalid module spec {spec!r}. Use 'module.path:ClassName'."
        )
    mod_path, attr = spec.split(":", 1)
    module = importlib.import_module(mod_path)
    if not hasattr(module, attr):
        raise click.ClickException(f"{mod_path} has no attribute {attr!r}.")
    return getattr(module, attr)


@click.group()
@click.version_option("0.1.0", prog_name="orion")
def main():
    """ORION Evaluation Platform CLI."""


# ── models ───────────────────────────────────────────────────────────

@main.group()
def models():
    """Manage submitted models."""


@models.command("list")
def models_list():
    """List all models in your organisation."""
    rows = _client().list_models()
    if not rows:
        click.echo("(no models)")
        return
    for r in rows:
        click.echo(
            f"{r['id']}  {r['name']}@{r['version']:<8}  "
            f"{r['submission_type']:<10}  {r['status']}"
        )


@models.command("upload")
@click.option("--name", required=True, help="Model name")
@click.option("--module", "module_spec", required=True,
              help="Python import spec, e.g. 'mymodule:MyModel'")
@click.option("--version", default="v1.0", help="Version string")
def models_upload(name, module_spec, version):
    """Upload a Python model from an import spec."""
    cls = _import_callable(module_spec)
    instance = cls() if isinstance(cls, type) else cls
    model_id = _client().submit_model(instance, name=name, version=version)
    click.echo(f"Uploaded {name}@{version} → {model_id}")


@models.command("register")
@click.option("--name", required=True, help="Model name")
@click.option("--image", required=True, help="Docker image reference")
@click.option("--port", default=8080, type=int, help="Container port")
@click.option("--version", default="v1.0", help="Version string")
def models_register(name, image, port, version):
    """Register a Docker container image as a model."""
    model_id = _client().register_docker_model(
        image=image, port=port, name=name, version=version,
    )
    click.echo(f"Registered {name}@{version} → {model_id}")


@models.command("delete")
@click.argument("model_id")
def models_delete(model_id):
    _client().delete_model(model_id)
    click.echo(f"Deleted {model_id}")


# ── runs ─────────────────────────────────────────────────────────────

@main.group()
def runs():
    """Manage evaluation runs."""


@runs.command("batch")
@click.option("--model", "model_id", required=True, help="Model ID")
@click.option("--scenario", required=True, help="Scenario path")
@click.option("--runs", "num_runs", default=10, type=int, help="Runs per scenario")
@click.option("--seed", default=42, type=int, help="Master seed")
def runs_batch(model_id, scenario, num_runs, seed):
    """Submit a batch evaluation."""
    result = _client().run_batch(
        model_id=model_id, scenario_path=scenario,
        num_runs=num_runs, seed=seed,
    )
    click.echo(result.summary())


@runs.command("status")
@click.option("--run-id", required=True, help="Run ID")
def runs_status(run_id):
    """Check the status of a single run."""
    click.echo(json.dumps(_client().get_run_status(run_id), indent=2))


# ── keys ─────────────────────────────────────────────────────────────

@main.group()
def keys():
    """Manage API keys."""


@keys.command("create")
@click.option("--label", required=True, help="Human-readable label for this key")
def keys_create(label):
    body = _client().create_key(label)
    click.echo(body["plaintext"])
    click.echo("(this key will not be shown again — store it securely)", err=True)


@keys.command("list")
def keys_list():
    rows = _client().list_keys()
    if not rows:
        click.echo("(no keys)")
        return
    for r in rows:
        revoked = " [revoked]" if r.get("revoked_at") else ""
        click.echo(f"{r['id']}  {r['key_prefix']}...  {r['label']}{revoked}")


@keys.command("revoke")
@click.argument("key_id")
def keys_revoke(key_id):
    _client().revoke_key(key_id)
    click.echo(f"Revoked {key_id}")


if __name__ == "__main__":
    main()
