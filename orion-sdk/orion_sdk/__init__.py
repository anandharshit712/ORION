"""
orion-sdk — ORION Evaluation Platform Customer SDK.

Provides a clean interface for submitting models, running evaluations,
and fetching results from the ORION SaaS platform.

This package is completely standalone — it does NOT import from the
arep.* backend package. All shared data structures (ModelInterface,
Action, Observation) are re-implemented here to match the AREP protocol.

Quick start:
    pip install orion-sdk

    from orion_sdk import ModelInterface, Action, Observation, OrionClient

    class MyModel(ModelInterface):
        def predict(self, observation: Observation) -> Action:
            return Action(steering=0.0, throttle=0.5, brake=0.0)
        def reset(self) -> None:
            pass

    client = OrionClient(api_key="sk-orion-...")
    model_id = client.submit_model(MyModel(), name="my-model", version="v1.0")
    batch = client.run_batch(model_id, scenarios=["LON-003"], runs_per_scenario=10)
    results = client.get_batch_results(batch.batch_id)
    print(results.summary())
"""

from orion_sdk.interface import ModelInterface, Action, Observation
from orion_sdk.client import OrionClient
from orion_sdk.uploader import upload_model

__all__ = [
    "ModelInterface",
    "Action",
    "Observation",
    "OrionClient",
    "upload_model",
]

__version__ = "0.1.0"
