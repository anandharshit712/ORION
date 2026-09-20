# How ORION Evaluates Your Model

**Status**: current as of Phase 0.5. Every formula, weight and threshold below is
taken from the code, and the file paths are given so you can check.

This document exists so that a safety reviewer can decide how much weight to put on
an ORION score without reading the source. It states what each number measures, how
it is computed, and — the part most eval tools leave out — where the model of the
world is approximate and which way the approximation biases the result.

---

## 1. What a score is, and what it is not

ORION runs your model through a parameterised scenario a fixed number of times with
seeded randomness, and reduces each run to four metrics and one composite. The
scores are **comparative**: two models driven through the same scenarios on the same
tire and surface model are ranked on equal terms. They are **not** calibrated
absolute measures of road safety, and nothing here is a certification.

What is genuinely guaranteed:

- **Determinism.** The same `(model, scenario, master_seed)` produces byte-identical
  simulation frames. Every run stores a rolling SHA256 over its frames
  (`runs.frame_hash`), so you can re-run and compare digests rather than trusting
  the claim. See `arep/utils/hashing.py` and `tests/test_frame_determinism.py`.
- **Isolation.** Your model runs in a locked-down subprocess with no network, a
  fresh temporary directory, resource limits and a hard wall-clock kill. A run that
  hits a limit is voided, never scored.
- **No hidden state between runs.** `reset()` is called before each run and the
  world is rebuilt from the scenario definition.

---

## 2. The composite score

`arep/evaluation/composite.py`

```
composite = 0.35 · safety
          + 0.25 · compliance
          + 0.20 · stability
          + 0.20 · reactivity
```

All four components are in `[0, 1]`, 1 being best, so the composite is too.

A test **passes** when, across N runs, `collision_rate < 0.01` and
`intervention_rate < 0.05`. The composite is a summary for ranking; the pass/fail
gate is the collision and intervention rate, not the composite.

These weights are also what the live dashboard uses. Until `CompositeEvaluator` is
wired to live runs, the dashboard's *inputs* are per-tick proxies rather than the
full post-run evaluation — the weighting is shared, the underlying measurements are
not yet. Treat a dashboard composite as indicative and the batch result as
authoritative.

---

## 3. Safety — 35% of the composite

`arep/evaluation/safety.py`

```
safety = 0.50 · collision_penalty
       + 0.30 · min_ttc_score
       + 0.20 · (1 − critical_ttc_fraction)
```

| Term | Meaning |
| --- | --- |
| `collision_penalty` | 0.0 if the run collided, 1.0 otherwise |
| `min_ttc_score` | `min(1.0, min_ttc / 10.0)` — TTC at or above 10 s scores 1.0 |
| `critical_ttc_fraction` | fraction of timesteps with TTC ≤ 2.0 s |

### Known approximation: TTC is optimistic under braking

Time-to-collision (`arep/core/ttc.py`) is a **constant-velocity projection**. Both
vehicles are extrapolated forward at their current speed, ignoring acceleration.

This matters because braking is exactly when TTC is consulted. A decelerating ego is
credited with closing speed it will not actually carry, so the reported TTC is an
upper bound and `min_ttc` is **biased high** during any braking manoeuvre. Two
consequences worth stating to a reviewer:

- A model that brakes early and one that brakes late look more similar than they
  are, until the late one actually collides — at which point the collision term
  dominates anyway.
- TTC figures are comparable between models on the same scenario. They are not
  calibrated times to impact and must not be quoted as absolute safety margins.

The constant-acceleration upgrade is scheduled for Phase 2.1. The bias is toward
*flattering* a model, never toward failing a safe one.

TTC also assumes straight-line motion and treats vehicles as points; physical
overlap is handled separately by the collision detector, which does use vehicle
dimensions.

---

## 4. Compliance — 25% of the composite

`arep/evaluation/compliance.py`

```
compliance = 0.60 · speed_compliance_fraction
           + 0.40 · lane_compliance_fraction
```

**Speed compliance** is the fraction of timesteps within the posted limit plus a
1.0 m/s tolerance. The result also reports mean and maximum excess over the limit.

**Lane compliance** is the fraction of timesteps where the *whole vehicle body* is
inside the lane:

```
|lane_offset| + vehicle_width / 2  ≤  lane_width / 2
```

`lane_offset` is the signed lateral distance from the centreline of the nearest
lane, recorded at each step against the live road geometry — negative is left of
the direction of travel. The result also reports the mean offset (which exposes a
persistent bias) and the worst absolute offset (which exposes the single worst
excursion); a model that weaves and one that hugs a line can have the same in-lane
fraction and very different means.

Two details a reviewer should know:

- The test is against the **body edge**, not the centre point. Measuring the centre
  against the nearest lane is very nearly tautological on a road of equal-width
  adjacent lanes, and would make this term decorative.
- Timesteps where the vehicle is not over any lane are **excluded** from the
  fraction rather than counted as compliant. A scenario with no lane geometry at all
  scores 1.0, because it cannot fail a lane-keeping check.
- Terminating `off_road` overrides the fraction with a duration-based penalty:
  leaving the road is worse than any in-lane drift, and the run stops there, so the
  unrecorded remainder counts against the model rather than being ignored.

Before Phase 0.5 this term was hardcoded to 1.0. Scores published before that date
are not comparable with scores after it.

---

## 5. Stability — 20% of the composite

`arep/evaluation/stability.py`

```
stability = 0.40 · accel_score + 0.40 · jerk_score + 0.20 · steering_score
```

Each term is a normalised measure of control smoothness, scoring 0 at or above its
threshold: acceleration standard deviation 3.0 m/s², jerk 10.0 m/s³, steering
standard deviation 0.5.

This measures ride quality and control discipline, not safety. A model can brake
hard and correctly and lose stability points for it; that is intended, and it is why
stability carries a fifth of the weight rather than a third.

---

## 6. Reactivity — 20% of the composite

`arep/evaluation/reactivity.py`

```
reactivity = 0.40 · brake_latency_score
           + 0.20 · steering_latency_score
           + 0.40 · response_adequacy_score
```

Latency is measured from the first timestep at which a threat is present to the
first timestep at which the model responds — braking counts as a brake command of
0.1 or more. Adequacy measures whether the response was proportionate to the threat
rather than merely present.

---

## 7. The physical model, and where it is approximate

`arep/core/physics.py`

Two modes. `KINEMATIC` is a bicycle model, used for batch runs. `DYNAMIC` adds a
Pacejka tire model with load transfer and surface friction, used when tire or
surface behaviour is under test.

Stated limitations:

- **Tire coefficients are uncalibrated.** The Pacejka parameters are plausible
  passenger-car defaults in the range the Magic Formula literature uses for dry
  asphalt. They are not fitted to any measured tire, and no vehicle in ORION
  corresponds to a real make or model. Absolute lateral forces are indicative;
  relative comparison between models is sound.
- **Longitudinal load transfer uses the commanded acceleration** for the current
  step rather than the achieved one. Resolving the achieved value exactly requires
  iterating against the tire forces it feeds into. The approximation is correct to
  first order and exact whenever the tires are not saturated; residual error appears
  only while sliding. (Before Phase 0.5 it used the *previous* step's acceleration,
  which lagged axle loads by 20 ms and understated front grip at the start of every
  emergency stop.)
- **Surface friction** is a single coefficient per surface type: dry asphalt 1.0,
  wet 0.5, ice 0.2, gravel 0.6.
- **Fixed 50 Hz timestep.** Everything is integrated at dt = 0.02 s.

---

## 8. What ORION does not test

Stated so that nobody infers coverage that is not there:

- **No perception.** Observations are ground-truth object states. There is no
  LiDAR, camera, radar, GPS or IMU model, and no sensor noise, occlusion or
  detection failure. ORION evaluates planning and control. A model that would fail
  because its perception stack missed an object will score well here.
- **No road topology beyond a flat straight road.** Intersections, curves, merges
  and gradients are not yet modelled, which is why the intersection and multi-agent
  scenario categories are not yet executable.
- **No certification claim.** ORION is not an ISO 26262 or ISO 21448 tool and
  produces no evidence package for either.

---

## 9. Reproducing a score

```bash
# From arep_implementation/
python -c "
from arep.execution.runner import EvaluationRunner
from arep.models.examples.example_models import EmergencyBrakeModel
r = EvaluationRunner().run_batch(
    scenario_path='scenarios/basic/straight_road_lead_vehicle.yaml',
    model=EmergencyBrakeModel(), num_runs=100, master_seed=42)
print(r.aggregated.to_dict())
"
```

Same seed, same scenario, same model version → same numbers, on any machine running
the pinned dependency set (`numpy==1.26.0`, `scipy==1.11.3`). If they differ, the run
was not reproducible and the score should not be relied on — compare `frame_hash`
values to find where the two runs diverged.

---

## 10. Change log for scoring

Scores are only comparable within a scoring version. Changes that moved numbers:

| Phase | Change | Effect |
| --- | --- | --- |
| 0.5 | Lane compliance computed for real (was hardcoded 1.0) | Compliance scores fall for any model that drifts |
| 0.5 | Lane 0 centred on the travel line | Previously every vehicle straddled a lane boundary |
| 0.5 | Load transfer uses current-step acceleration | Small changes in `DYNAMIC` mode only |
| 0.5 | Live dashboard adopts the `CompositeEvaluator` weights | Dashboard composites shift; batch results unchanged |
