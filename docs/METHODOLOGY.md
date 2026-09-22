# How ORION Evaluates Your Model

**Status**: current as of the Phase 1.5 lane-geometry correction. Every formula, weight and
threshold below is taken from the code, and the file paths are given so you can check.

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

### How TTC is computed, and what it still approximates

Time-to-collision (`arep/core/ttc.py`) projects both vehicles forward using their
current velocity **and** their current acceleration, solving

```
0.5 · a · t²  +  v · t  −  d  =  0
```

along the line between them, where `v` is the closing speed and `a` the closing
acceleration. Where the closing rate eases off enough that relative motion reverses
before the gap is covered, the result is "no collision on this trajectory" rather
than a number.

Until Phase 2.1 this was a constant-velocity projection, `d / v`, which credited a
braking ego with closing speed it was never going to carry. A 20 m/s approach to an
obstacle 50 m away reported 2.5 s whether the ego was braking at 8 m/s² or not
accelerating at all. Scores produced before that change are not comparable with
scores after it.

Two approximations remain, and a reviewer should know both:

- **Acceleration is held constant over the projection.** A vehicle that brakes
  harder a moment later closes sooner than predicted, so TTC still leans optimistic
  during a developing manoeuvre — much less than before, but not zero.
- **Steering is not projected.** A vehicle turning into or out of the path is
  mispredicted; TTC is a straight-line measure.

Vehicles are treated as points here. Physical overlap is the collision detector's
job, and that one does use vehicle dimensions.

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
| 2.1 | TTC projects under constant acceleration instead of constant velocity | `min_ttc` rises for braking models and falls for accelerating ones; safety scores move for any scenario with acceleration |
| 1.5-fix | One lane-centre formula for the flat road and the road graph | Lane compliance rises from 0.0 to 1.0 on the 15 scenarios that start the ego at y=-1.75; composite rises by exactly +0.100 for each. INT-003 rises +0.050 from dropping a lateral `ego_x_jitter` wider than its lane. The 5 templated scenarios are unchanged. |

### The 1.5 lane-geometry correction

Worth stating plainly, because it moved more scores than anything since 0.5.

Two pieces of code computed lane centres and disagreed. The flat straight road put lane 0 on
`y = 0`; the road graph introduced in Phase 1.5 put it on `y = -1.75`, the carriageway being
centred on the origin. A scenario therefore sat on different geometry depending on whether it
happened to declare a `template`.

15 of the 21 production scenarios start the ego at `y = -1.75` and do not declare a template.
On a 3.5 m lane whose centre was taken to be `y = 0`, the in-lane test
`|offset| + half_width <= lane_width / 2` evaluates to `1.75 + 1.0 <= 1.75` — false at every
timestep, for every model, in every run. Those scenarios scored a lane-compliance fraction of
exactly **0.0** for reasons that had nothing to do with how the model drove.

Measured against `emergency_brake` over the whole library, the correction raises composite by
exactly **+0.100** on each of the 15, leaves the 5 correctly-templated scenarios untouched, and
raises INT-003 by +0.050. Mean across the library: +0.0736.

It survived because the test suite runs on the two v1 fixtures in `scenarios/basic/`, and those
are the only scenarios in the repository that drive along `y = 0` — the exact case the 0.5
change was written against.

Fixed by giving both builders the same formula, `(i - (n-1)/2) * lane_width`, moving the two
fixtures into lane 0, and adding two invariants to `tests/test_scenario_library.py`: the
builders must agree, and every scenario in the library must start the ego inside its lane. The
second caught a separate defect in INT-003, which applied a ±4 m `ego_x_jitter` on an arm the
ego climbs heading north — lateral jitter wider than the lane, placing the ego in oncoming
traffic before the run began.

**Scores produced before this change are not comparable with scores produced after it.**
