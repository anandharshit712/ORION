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
- **Nothing rewards making progress.** Safety, compliance, stability and
  reactivity all measure how the vehicle behaves; none measures whether it got
  anywhere. A model that brakes to a standstill in the first second and never
  moves again scores 0.962 stability and 0.988 composite on LON-001, because a
  stationary car has no jerk, no steering variance, no speeding and no
  collisions. This is the single largest thing to know when reading a composite
  score: **a high score is evidence of not crashing, not evidence of driving.**
  Scenario pass/fail inherits it — the criterion is a collision and intervention
  rate, so refusing to move passes most of the library. Any comparison between
  two models has to be read with this in mind, and comparing a real model
  against `EmergencyBrake` is not the compliment it looks like. Adding a
  progress term is tracked in `docs/PENDING.md`; `tests/test_reference_model.py`
  pins the current behaviour so it cannot change unnoticed.
- **Road topology is modelled, but geometry is not sensed.** Since Phase 1.5 a
  scenario can declare a junction, an on-ramp or a roundabout, and all six
  categories execute. What the model receives is still lane offset and object
  positions — there is no map, no route and no lookahead along the road graph,
  so a model cannot plan through a junction, only react inside one. The
  roundabout template in particular has a single-lane circulating carriageway
  that only a lane-following controller can stay on.
- **No certification claim.** ORION is not an ISO 26262 or ISO 21448 tool and
  produces no evidence package for either.

---

## 8.5 How certain is a score?

`arep/statistics/aggregator.py`

A mean on its own is not evidence. Every metric is reported with the sample
behind it:

```
safety 0.73  ->  safety 0.73 +/- 0.04  (95% CI, n=100)
```

**Means** carry a t-distribution interval. The standard deviation uses `ddof=1`,
the sample standard deviation, because the runs are a sample of the scenario's
parameter space and not the whole of it. `ddof=0` would quietly understate the
spread.

**The collision rate** carries a Wilson score interval instead, because it is a
proportion rather than a mean. The usual normal approximation runs off the end
of the scale near 0 and 1 — it will happily report a lower bound below zero —
and near zero is exactly where a good model's collision rate lives. Wilson stays
inside `[0, 1]` and stays sensible at small n.

**Percentiles** (5th, 25th, 75th, 95th) are reported alongside the interval
because they answer a different question. The interval says how well the mean is
pinned down; the percentiles say what the spread actually looks like. A model
that is reliably mediocre and one that is usually excellent but occasionally
catastrophic can share a mean and a standard deviation. Their 5th percentiles do
not look remotely alike, and for a safety argument the lower tail is the
interesting end.

### Small samples

The interval widens as n falls, and that is the point — a 5-run batch must not
read as confidently as a 100-run one. Measured on the same data:

| n | 95% CI width |
| --- | --- |
| 5 | 0.106 |
| 20 | 0.082 |
| 100 | 0.038 |

Specific behaviours worth knowing:

- **n = 1**: standard deviation is 0 and the interval collapses to the point
  estimate. There is no spread to estimate from one run. This is reported as-is
  rather than padded with an invented width.
- **All runs identical**: the same collapse, for the same reason. The standard
  error is zero, so the t-interval is undefined and the point estimate is
  returned.
- **n < 5**: flagged `low_confidence` in the API response, and the dashboard
  says "small sample — interval is wide" next to every affected score. A wide
  bar is easy to miss; a confident-looking mean is not.
- **Zero collisions**: never reported as a zero collision probability. Zero in
  20 runs still has an upper bound above 10%. The bound is the defensible claim,
  not the point estimate.

### Which run to look at

Each batch names a `worst_run_seed` and a `best_run_seed`. These are seeds, not
database ids, because a seed can be re-run and a row id cannot — naming the
worst run is only useful if you can reproduce it.

A collision outranks a low composite when choosing the worst run. The run a
reviewer needs is the one that crashed, even when a different run scored lower
on the weighted average.

### Importance sampling, and why `n` is not the run count

`arep/scenario/importance.py`

Uniform sampling spends runs evenly across a scenario's declared parameter
ranges. At suite scale that is mostly waste: a scenario whose failures live in
a narrow corner will spend 95 of 100 runs re-confirming the safe region. A
batch may instead name a sub-region and oversample it, so the runs land where
the failures are:

```python
region = ImportanceRegion(
    bounds={"lead_vehicle.initial_x": (25.0, 32.0)},   # the failing corner
    fraction=0.6,                                       # 60% of runs drawn there
)
runner.run_batch(path, model, num_runs=100, importance=region)
```

Two properties make this safe to publish a number from.

**The bias is paid back.** Each run carries the likelihood ratio between the
scenario's declared uniform distribution and the distribution it was actually
drawn from, and every mean, interval and percentile is computed against those
weights. A batch that draws half its runs from a failure region occupying 10%
of the space sees collisions in over half its runs; the weighted estimator
reports the scenario's rate, not the draw's. `tests/test_importance_sampling.py`
pins this against a rate that is known by construction.

The weight follows where a point *landed*, not which branch of the sampler
produced it. The proposal is a mixture — with probability `fraction` it draws
from the region, otherwise from the whole declared space — and that second
branch lands inside the region too, at a rate equal to the region's volume.
Weighting by the branch under-counts the region and biases every rate the batch
reports. It is a silent error: the estimate stays plausible and is simply
wrong.

**The reported `n` falls.** A weighted batch publishes an `effective_n`
(Kish: `(Σw)² / Σw²`) alongside its run count, and every interval is built on
the effective figure for both the standard error and the degrees of freedom. A
100-run batch that spent 60 runs in one corner is not 100 runs' worth of
evidence about the scenario as a whole, and an interval that ignored that would
be narrower than the evidence supports — the direction that gets a model signed
off. For an ordinary uniform batch `effective_n == num_runs` exactly.

Two limits worth stating:

- **Region bounds narrow a declared range and never widen it.** A bound
  reaching outside the scenario's own `parameterization` block is clipped to
  it, and one that does not overlap at all is dropped. A suite may concentrate
  runs inside what the scenario author sanctioned; it may not score a model on
  parameters the author never wrote down.
- **A region pinned to a single value (zero volume) cannot be weighted back.**
  Those runs are reported at weight 0 and contribute nothing to the population
  estimate — the proposal density there is infinite and no estimator exists. A
  batch where *every* run is degenerate is refused rather than averaged. Such
  runs still ran and their failures are still real failures; they just cannot
  speak for the rest of the space.

Importance sampling is available through `EvaluationRunner.run_batch` — the
CLI, SDK and library paths. **`POST /api/runs/batch` does not accept a region**,
because `RunRecord` has no column to persist a weight and a queued batch would
lose it, leaving the API to report the biased draw as if it were the scenario.
The API path is uniform-only until that column exists.

---

## 8.6 When ORION calls a change a regression

A score is only meaningful against another score. In CI, ORION compares the new
suite report against a previous one and fails the build when any scenario moves
past one of these:

| What moved | How far it has to move |
| --- | --- |
| Composite score | down more than **0.05** |
| Safety score | down more than **0.10** |
| Collision rate | up more than **1 percentage point** |

Safety gets the looser band deliberately. It is the noisier of the two across
seeds, and a check that fires on ordinary run-to-run variation gets switched
off within a week — at which point it protects nothing.

**The comparison is per scenario, never on the suite average.** A model that
improves slightly on four scenarios and degrades badly on the fifth has an
unchanged mean and a new way to crash. Averaging is exactly the operation that
hides the finding.

These thresholds are heuristics for "look at this", not statistical tests. They
do not account for the width of the interval around either score, so a
comparison built on very few runs per scenario can move past them by chance.
Read them alongside the n and the interval from §8.5 — with 5 runs a 0.05 move
may be well inside the noise, and with 100 it is unlikely to be.

A missing baseline is the normal first run: the comparison is skipped, not
failed. Nothing about the scoring itself changes when a baseline is supplied —
the same run produces the same scores either way. The baseline only decides
whether a build goes red.

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
| 4.3-fix | Leaving the carriageway fails a scenario | Pass/fail only; no composite moves. Scenarios where a model ends up off the road now fail instead of passing — this is a change in the verdict, not in any score. |
| 4.3-fix | Twelve scenarios had their lead-vehicle start positions moved further away | Composite rises and collision rate falls on those twelve for any braking model. They contained a parameter corner no braking behaviour could survive — see below. Scores on them are not comparable across this change. |
| 4.3 | Importance sampling: aggregates are weighted, batches report `effective_n` | No effect on any uniform batch — `effective_n == num_runs` and the estimators are the ones they always were. A batch run with `importance=` reports the scenario's rates rather than its own draw's, and an interval built on the effective sample size. |
| 1.5-fix | One lane-centre formula for the flat road and the road graph | Lane compliance rises from 0.0 to 1.0 on the 15 scenarios that start the ego at y=-1.75; composite rises by exactly +0.100 for each. INT-003 rises +0.050 from dropping a lateral `ego_x_jitter` wider than its lane. The 5 templated scenarios are unchanged. |

### Leaving the road is a failure

The pass criterion used to be the collision rate alone. Nothing checked whether
the vehicle was still on the road, so a model that drove off it passed.

Measured on INT-004, the roundabout-entry scenario:

| model | outcome | composite |
| --- | --- | --- |
| `ReferenceDriver` | off-road at 3.5 s | 0.912 |
| `SimpleLaneKeep` | off-road at 2.6 s | 0.801 |
| `EmergencyBrake` | stopped, ran to timeout | 0.992 |

All three were recorded as passes. The scoring compounds the problem rather
than catching it: an off-road run terminates early, so there is very little of
it left to score badly, and departing the carriageway promptly can outscore
driving the scenario properly.

`run_suite` now fails a scenario when more than 1% of runs end `off_road`, the
same bar the collision rate uses, and `off_road_rate` is reported per scenario
and suite-wide. This changes verdicts only — no composite, mean or interval
moves, so scores remain comparable across the change.

Two consequences worth stating, because both were previously invisible:

- **A PD lane-keeper is marginally stable and occasionally diverges.** On an
  untouched scenario (LON-001) `SimpleLaneKeep` ends off the road on 1 seed in
  20. That was always true; it simply never failed anything.
- **The roundabout template cannot be driven by anything in the repo.** Its
  circulating carriageway is a single lane on a curve, so a straight path
  across the circle is off-road at every point between the two crossings. Both
  steering models leave it within four seconds. INT-004's former "pass" was
  entirely an artefact of this criterion.

### The 4.3 feasibility correction

Twelve scenarios contained a corner of their declared parameter ranges where no
braking behaviour avoided contact. The check is deliberately generous to the
scenario — the ego brakes at its full declared `max_deceleration` from tick
zero, with no reaction delay — so a scenario failing it cannot be passed by any
braking model at all. It was scoring a model on the geometry it was handed
rather than on how it responded.

LON-002 was the worst of them and the one that surfaced it: at the corner the
ego needed about 48 m to stop while the lead could start 35 m ahead. It failed
`emergency_brake` on 10% of runs, which reads exactly like a demanding scenario
rather than a broken one.

The fix moves each lead's start position further away — both the nominal `x` and
the `initial_x` range, shifted together so the spread that blocks
pattern-learning is preserved — until the worst corner has at least 5 m of
slack. The scenarios still demand hard braking; they no longer demand the
impossible. Discrimination was re-measured on all twelve: `emergency_brake` now
collides on none of them and `ConstantAction` still collides on 80–100%, so the
scenarios separate a braking model from a non-braking one exactly as before.

Affected: LON-002, LON-003, LON-004, LON-005, LON-008, LON-010, LAT-008,
LAT-010, MLT-002, EMG-007, EMG-009, VRU-003.

Not affected, deliberately: EMG-001, EMG-002, LAT-003 and LAT-007 are evasion
scenarios where braking is *supposed* to be insufficient. `tests/test_scenario_feasibility.py`
enforces the invariant for every scenario and carries an explicit allowlist for
those, so adding to it is a claim about a scenario's purpose rather than a way
to silence the check.

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
