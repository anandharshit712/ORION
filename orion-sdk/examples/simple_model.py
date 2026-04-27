"""
ORION SDK — Simple Model Example.

Minimal working example of a ModelInterface implementation.
Use this as a starting point for your own model.

To run this example:
    pip install orion-sdk
    export ORION_API_KEY=sk-orion-...
    python simple_model.py
"""

from orion_sdk import ModelInterface, Action, Observation, upload_model


class FollowSpeedLimitModel(ModelInterface):
    """
    A simple model that tries to match the speed limit.
    Brakes if over the limit, accelerates if under.
    No steering — drives straight.
    """

    def predict(self, observation: Observation) -> Action:
        speed = observation.ego_speed
        limit = observation.speed_limit or 13.89  # default 50 km/h

        if speed > limit * 1.05:
            # Over speed limit — brake proportionally
            brake_amount = min(1.0, (speed - limit) / limit)
            return Action(steering=0.0, throttle=0.0, brake=brake_amount)
        elif speed < limit * 0.95:
            # Under speed limit — accelerate gently
            throttle_amount = min(0.5, (limit - speed) / limit)
            return Action(steering=0.0, throttle=throttle_amount, brake=0.0)
        else:
            # Close enough — coast
            return Action.zero()

    def reset(self) -> None:
        pass   # No internal state to reset


if __name__ == "__main__":
    import os

    api_key = os.environ.get("ORION_API_KEY")
    if not api_key:
        print("Set ORION_API_KEY environment variable first.")
        exit(1)

    print("Uploading FollowSpeedLimitModel...")
    model_id = upload_model(
        FollowSpeedLimitModel(),
        name="follow-speed-limit",
        version="v1.0",
        api_key=api_key,
    )
    print(f"Model uploaded! model_id = {model_id}")
    print(f"Now run: orion runs batch --model {model_id} --scenarios LON")
