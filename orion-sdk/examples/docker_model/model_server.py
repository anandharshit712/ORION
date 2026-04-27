"""
ORION SDK — Docker Model Server Example.

Exposes a ModelInterface via a FastAPI HTTP server.
ORION will call POST /predict and POST /reset on this server during evaluation.

To build and register:
    docker build -t registry.orion.run/YOUR_ORG/my-model:v1.0 .
    docker push registry.orion.run/YOUR_ORG/my-model:v1.0
    orion models register --name my-model --image registry.orion.run/YOUR_ORG/my-model:v1.0 --port 8080

Required endpoints:
    POST /predict  body: Observation JSON → returns Action JSON
    POST /reset    body: {} → returns {}
    GET  /health   → returns {"status": "ok"}
"""

from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel
from typing import Any, Dict, List, Optional

app = FastAPI(title="ORION Model Server", version="1.0.0")


# ── Replace this with your actual model ──────────────────────────────────

class MyActualModel:
    """
    Placeholder — replace with your real autonomous driving model.
    This could load a PyTorch/TensorFlow checkpoint, connect to ROS, etc.
    """

    def predict(self, observation: dict) -> dict:
        # TODO: implement your model's predict logic
        return {"steering": 0.0, "throttle": 0.3, "brake": 0.0}

    def reset(self) -> None:
        # TODO: reset any internal state
        pass


_model = MyActualModel()


# ── Request/response schemas ──────────────────────────────────────────────

class NearbyObjectSchema(BaseModel):
    object_id: str
    relative_x: float
    relative_y: float
    relative_speed: float
    object_type: str
    ttc: float


class ObservationSchema(BaseModel):
    ego_speed: float = 0.0
    ego_heading: float = 0.0
    ego_acceleration: float = 0.0
    ego_x: float = 0.0
    ego_y: float = 0.0
    speed_limit: float = 0.0
    nearby_objects: List[NearbyObjectSchema] = []
    traffic_light_state: Optional[str] = None
    lane_lateral_offset: float = 0.0
    sim_time: float = 0.0


class ActionSchema(BaseModel):
    steering: float
    throttle: float
    brake: float


# ── Endpoints ─────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/predict", response_model=ActionSchema)
def predict(observation: ObservationSchema):
    action_dict = _model.predict(observation.model_dump())
    return ActionSchema(**action_dict)


@app.post("/reset")
def reset():
    _model.reset()
    return {}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
