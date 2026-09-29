"""Can the scenario be passed at all? (Phase 4.3 follow-up)

A scenario that no behaviour can pass is not a hard scenario, it is a broken
one: it scores a model on the geometry it was handed rather than on how it
responded, and it sits in the suite as a permanent false negative. LON-002 was
exactly this and went unnoticed for months because a 10% failure rate against a
brake-only model reads like a demanding scenario.

The check is a braking-feasibility bound, deliberately generous to the scenario:
the ego is assumed to brake at its full declared ``max_deceleration`` from tick
zero, with no reaction delay, against the worst corner of the declared parameter
ranges. A scenario that fails *this* cannot be passed by any braking behaviour
whatsoever.

Two cases, because they have different answers:

* **braking lead** -- worst case it stops, so the ego must fit its own stopping
  distance into the gap plus however far the lead still travels::

      v_e^2/2a_e - v_l^2/2a_l  <=  gap

* **coasting lead** -- a ``constant_velocity`` lead never stops, so the ego only
  has to shed the speed difference before the gap closes::

      (v_e^2 - v_l^2)/2a_e  <=  gap

Only same-lane objects count. A cut-in vehicle starting ten metres ahead in the
next lane at matched speed is a lateral problem, not a braking one, and by the
time it is in the lane the speeds agree. This module asks one question and does
not pretend to ask the other.

``EVASION_SCENARIOS`` is the allowlist: scenarios whose stated requirement is to
*not* solve the problem by braking. Adding to it is a deliberate act -- it says
"braking is supposed to be insufficient here", which is a claim about the
scenario's purpose, not a way to silence the check.
"""

from __future__ import annotations

import math
import pathlib

import pytest
import yaml

REPO = pathlib.Path(__file__).resolve().parent.parent.parent
SCENARIOS = sorted((REPO / "scenarios").glob("*/*.yaml"))

# Body separation counted against the gap: roughly one vehicle length across
# both bumpers. Centre-to-centre distance overstates the available room by half
# of both vehicles, which at highway speed is most of a car length of margin
# that does not exist.
BODY = 5.0

# Same lane if the lateral centres are within this, in metres.
LANE_TOL = 2.0

# Required slack beyond the bare physical minimum, in metres. The bound already
# assumes instantaneous maximum braking, which nothing real does; this leaves
# roughly a third of a second of reaction at highway speed. It is a floor for
# being *answerable*, not a comfortable following distance.
MIN_MARGIN = 5.0

# Scenarios where braking is intentionally not the answer. Each needs evasive
# steering or a lateral decision, and a negative braking margin is the point.
# Oncoming scenarios (EMG-002, LAT-003, LAT-007) do not appear here: an
# oncoming vehicle is skipped above, so those scenarios have no same-lane lead
# and the check does not apply to them at all.
EVASION_SCENARIOS = {
    "EMG-001_road_debris_avoidance",
}


def _worst_case_margin(doc: dict) -> tuple[float, str] | None:
    """Metres of slack at the worst corner, and which object produced it.

    None when no object is ever in front of the ego in its own lane, which is
    every lateral, intersection and VRU-from-the-side scenario.
    """
    ego = doc.get("ego") or {}
    init = ego.get("initial") or {}
    cons = ego.get("constraints") or {}
    a_e = float(cons.get("max_deceleration", 8.0))
    ego_y = float(init.get("y", 0.0))
    ego_x = float(init.get("x", 0.0))

    par = doc.get("parameterization") or {}
    ev = par.get("ego_velocity")
    v_e = float(ev["max"]) if isinstance(ev, dict) else float(init.get("velocity", 0.0))
    jitter = par.get("ego_x_jitter")
    if isinstance(jitter, dict):
        ego_x += float(jitter["max"])

    overrides = par.get("npc_overrides") or {}
    worst: tuple[float, str] | None = None

    for npc in doc.get("traffic") or []:
        npc_id = npc.get("id")
        npc_init = npc.get("initial") or {}
        override = overrides.get(npc_id) or {}

        # Oncoming traffic is not a lead. A head-on vehicle closes at the sum
        # of both speeds and cannot be solved by braking at all -- stopping dead
        # still leaves it arriving -- so it is an evasion problem by
        # construction and this bound has nothing useful to say about it.
        npc_heading = float(npc_init.get("heading", 0.0))
        ego_heading = float(init.get("heading", 0.0))
        relative_heading = abs(
            math.atan2(
                math.sin(npc_heading - ego_heading),
                math.cos(npc_heading - ego_heading),
            )
        )
        if relative_heading > math.pi / 2:
            continue

        npc_y = float(npc_init.get("y", 0.0))
        if isinstance(override.get("initial_y"), dict):
            npc_y = float(override["initial_y"]["min"])
        if abs(npc_y - ego_y) > LANE_TOL:
            continue

        npc_x = float(npc_init.get("x", 0.0))
        if isinstance(override.get("initial_x"), dict):
            npc_x = float(override["initial_x"]["min"])
        gap = npc_x - ego_x - BODY
        if gap <= -BODY:
            continue  # starts level with or behind the ego

        v_l = float(npc_init.get("velocity", 0.0))
        if isinstance(override.get("initial_velocity"), dict):
            v_l = float(override["initial_velocity"]["min"])

        params = (npc.get("behavior") or {}).get("parameters") or {}
        param_overrides = override.get("parameters") or {}

        def lowest(key: str) -> float | None:
            spec = param_overrides.get(key, params.get(key))
            if isinstance(spec, dict):
                value = spec.get("min", spec.get("max"))
                return float(value) if value is not None else None
            return float(spec) if isinstance(spec, (int, float)) else None

        coasting = (npc.get("behavior") or {}).get("type") == "constant_velocity"
        decels = [
            d
            for d in (lowest("final_decel"), lowest("initial_decel"), lowest("decel"))
            if d
        ]
        a_l = abs(min(decels)) if (not coasting and decels) else None

        if a_l:
            needed = v_e**2 / (2 * a_e) - v_l**2 / (2 * a_l)
        elif v_l <= 0.0:
            needed = v_e**2 / (2 * a_e)
        else:
            needed = max(0.0, (v_e**2 - v_l**2) / (2 * a_e))

        margin = gap - needed
        if worst is None or margin < worst[0]:
            worst = (margin, str(npc_id))

    return worst


@pytest.mark.parametrize("path", SCENARIOS, ids=lambda p: p.stem)
def test_worst_corner_is_survivable_by_braking(path: pathlib.Path):
    """No scenario may contain a corner that braking cannot answer.

    The failure this prevents is quiet. A scenario with an impossible corner
    still runs, still produces a score, and still looks like a demanding test --
    it just fails every model for a reason that has nothing to do with the model.
    """
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    worst = _worst_case_margin(doc)
    if worst is None:
        pytest.skip("no same-lane lead; braking feasibility does not apply")

    margin, npc_id = worst
    if path.stem in EVASION_SCENARIOS:
        assert margin < MIN_MARGIN, (
            f"{path.stem} is listed in EVASION_SCENARIOS, which claims braking is "
            f"deliberately insufficient, but it has {margin:.1f} m of braking margin "
            f"against {npc_id}. Remove it from the list."
        )
        return

    assert margin >= MIN_MARGIN, (
        f"{path.stem}: at the worst corner of its declared ranges the ego needs "
        f"{-margin + MIN_MARGIN:.1f} m more room than it has against {npc_id} "
        f"(margin {margin:.1f} m, required {MIN_MARGIN:.1f} m). Braking at the full "
        f"declared max_deceleration from tick zero does not avoid contact, so no "
        f"model can pass those draws and the scenario is scoring geometry rather "
        f"than response. Raise the NPC's initial_x floor or lower the ego_velocity "
        f"ceiling. If braking is *meant* to be insufficient, this is an evasion "
        f"scenario -- add it to EVASION_SCENARIOS and say so in its description."
    )


def test_the_evasion_allowlist_has_no_stale_entries():
    """A name left behind after a rename silently stops checking that scenario."""
    names = {p.stem for p in SCENARIOS}
    stale = EVASION_SCENARIOS - names
    assert (
        not stale
    ), f"EVASION_SCENARIOS names scenarios that do not exist: {sorted(stale)}"
