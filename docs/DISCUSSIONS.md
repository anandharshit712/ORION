# Discussions — features and gaps raised in design reviews

**What this file is.** A record of features and gaps that came up while walking through the
project out loud, in interview-style reviews where one person explains the system and the other
pushes on it. Explaining a system to someone who does not know it is a good way to find the
places where the story and the code disagree. Each entry keeps the full reasoning, so the
build conversation can start where the review left off rather than from zero.

**When it applies: after the build, not now.** This is a post-build backlog. No entry is
picked up until every build item in `docs/ROADMAP.md` is done. Until then, the remaining
roadmap work proceeds exactly as the roadmap specifies. Its scope, order and design are not
changed to fit an entry here, and entries are not started early because the work happens to
be nearby. An entry that turns out to block a roadmap item goes to the roadmap, through the
normal route, rather than being built from here.

**What it is not.** It does not set priority — `docs/ROADMAP.md` does. It is not the open-work
list either: every entry here that needs building also has a short entry in `docs/PENDING.md`,
which points back here for the detail. When an entry is built, mark it **Built**, link the
change, and move any lasting rule into the governing document it belongs to
(`ARCHITECTURE.md`, `METHODOLOGY.md`, `CLAUDE.md`).

**Entry format.** Every entry has the same sections:

- **Raised** — date, and the question that exposed it.
- **Finding** — what the code does today, with file references. Verified against the code,
  not recalled.
- **Direction agreed** — what the review concluded should happen.
- **Proposed design** — a starting point for the build, not a decision.
- **To discuss before building** — the questions that must be settled in the build
  conversation. An entry is not ready to build while this list has unanswered items that
  change the design.
- **Status** — Open / In discussion / Built.

---

## DI-01 — Environmental physics: weather, friction and wind that actually affect the run

**Status**: Open — nothing built, post-build. Also in `docs/PENDING.md` under "Scoring and analysis".

### Raised

2026-09-28. Question: *"Each run changes its parameters — if rain is heavy, friction drops.
How do you manage the physics behind that?"*

### Finding

The dynamic tyre physics exists. What is missing is the connection between the scenario's
weather and that physics.

| Piece | State today | Where |
| --- | --- | --- |
| Dynamic physics (Pacejka tyres, weight transfer, drag, rolling resistance) | **Works** | `arep/core/physics.py`, `_update_dynamic` |
| Surface friction values: dry 1.0, gravel 0.6, wet 0.5, ice 0.2 | **Works** | `SurfaceType.get_friction()` |
| Friction setting | **One global value per evaluation**, from config (`phys.surface_friction`, env `AREP_SURFACE_FRICTION`) | `arep/config/__init__.py` |
| Default physics mode | **`kinematic`**, which assumes perfect grip and ignores friction entirely | `config/__init__.py`, `mode: str = "kinematic"` |
| Per-run randomisation | Positions, speeds and NPC behaviour parameters **only**. No friction, wind or visibility. | `arep/scenario/parameterizer.py` |
| `weather.condition` / `visibility` in YAML | **Labels.** Carried into `WorldState` and the tick frame; nothing in physics or `Observation` reads them. | `scenario/executor.py`, `simulation/engine.py` |
| `friction_mu` in the tick frame | **Hardcoded `1.0`**, whatever the surface | `simulation/engine.py`, `get_tick_frame` |
| Per-segment surface | `RoadSegment.surface` field exists; **physics never reads it** | `arep/core/road.py` |
| Wind | **Not modelled.** Drag is computed against the car's own speed, as if the air were still. | `core/physics.py` |
| NPC braking | NPCs decelerate at scripted values (up to −9.81 m/s²) **regardless of surface** | `simulation/npc_bt.py`, scenario YAML |
| Black-ice scenario EMG-004 | Declares a `change_weather` event with `friction_mu: 0.1` over x=80–130 m. The event used to be silently dropped, so the scenario ran and passed on dry-road grip. Since DI-02 it is **refused at load** instead. | `scenarios/emg/EMG-004_black_ice_friction_loss.yaml` |

`docs/ARCHITECTURE.md` already specifies the target: friction is "a per-tile property in the
physics world, not a global parameter" (§2.4), and anything that changes during a run has a
"schedule fixed at parameterization time" (§2.3). The code has not caught up with the spec.

**Why it matters.** Stopping distance is roughly `v² / (2·μ·a_max)`. At 90 km/h (25 m/s) with
8 m/s² of braking, that is about 39 m on a dry road and about 78 m on a wet one. A 55 m gap is
comfortable in one case and a collision in the other. A scenario whose YAML says "snow" but
whose physics is dry reports a pass the model never earned.

### Direction agreed

1. **Environmental physics varies per run**, sampled from the scenario's parameterization
   block the same way speeds and gaps are.
2. **It can also change during a run**, and this is the realistic case: an ice patch, a puddle,
   a crosswind gust off a bridge, a fog bank.
3. **But every in-run change is described by a few numbers drawn at the start of the run.**
   "Ice from x=80 m to x=130 m, μ=0.15" or "gust at t=6.2 s, 4 m/s from the left, 1.5 s". No
   per-tick random drift. Reasons:
   - A failure has to be explainable. Failure clustering (`analysis/failure_clustering.py`)
     and adversarial search (`search/`) both work by naming the parameters behind a failure.
     Per-tick noise leaves nothing to name.
   - Search needs a small number of dimensions. A zone is 3 numbers; per-tick noise is
     thousands, and `recommended_evals(n_dims)` would price it out of reach.
   - It keeps determinism and replay intact with no new mechanism: the schedule comes from
     the seed, so the same seed gives the same schedule.
   - It keeps "one scenario = one behavioural requirement". Randomly varying everything turns
     every scenario into "handle everything", which measures nothing specific.
4. **Change by place is preferred over change by time** for surface properties. Real friction
   changes with location, not over a 20-second window. Time-based changes belong to things that
   really are time-based: wind gusts, and later perhaps a light changing or sensor glare.

### Proposed design

In build order. Each step can merge on its own and leaves `main` working.

1. **Refuse unknown event types at load.** This is DI-02, a prerequisite: until it lands,
   any event added for this feature can silently fail to apply.
2. **Friction as a per-run knob.** Add `surface_friction: {min, max}` to the parameterization
   block. Sample it from the `weather` subsystem stream of `RandomManager` (already declared,
   currently unused), so adding it does not shift any other stream's draws and old runs stay
   reproducible. Apply it through `VehiclePhysics.set_surface_friction()` at run start.
3. **Friction zones by location.** Read friction from the surface under the car on each step,
   through `RoadGraph` / `RoadSegment.surface` when a graph exists, or a list of x-ranges on
   the flat road. A zone's position, length and μ can each be ranges in the parameterization
   block. This makes EMG-004 real.
4. **Report the real value.** `get_tick_frame()` emits the friction actually under the car
   instead of the hardcoded 1.0. This stays deterministic, so it is allowed in the canonical frame.
5. **Wind gusts.** A timed event: start time, duration, speed, direction. It adds a lateral
   force and changes the relative air speed used by the drag term. Dynamic mode only.
6. **Visibility zones.** Objects beyond the visibility distance are removed from the
   `Observation` the model receives. Scoring still sees the ground truth. This overlaps with
   Phase 6 (sensor simulation) — see the questions below.
7. **Mode enforcement.** A scenario that declares any environmental physics requires
   `dynamic` mode. Running it in `kinematic` is refused, not silently approximated.

Skipped for now: continuous random drift of any parameter within a run. Add it only if a real
case turns up that zones and timed events cannot express.

### To discuss before building

**Which physics parameters to include.** The list of candidates, with a first view on each:

| Parameter | Changes during a run? | First view |
| --- | --- | --- |
| Surface friction μ | Yes, by location | **Include** — the core of this entry |
| Wind speed and direction | Yes, over time (gusts) | **Include** — lateral push plus relative-air drag |
| Visibility distance | Yes, by location | **Include**, but see the Phase 6 question |
| Rolling resistance | With surface (gravel and wet roads are higher) | Tie to surface type rather than a separate knob? |
| Air density | Negligible within a run | Fixed; possibly per run for altitude or heat — probably not worth it |
| Drag coefficient, frontal area | No — properties of the car | Fixed per vehicle |
| Vehicle mass / payload | No, but differs per run (a loaded car stops later) | Candidate per-run knob — does it belong in environment or vehicle config? |
| Road grade (slope) | Yes, by location | **Not modelled at all today** — gravity along the slope affects braking. In scope, or separate? |
| Tyre wear / pressure / temperature | Slowly | Out of scope — the tyre model is uncalibrated, so this would be false precision |
| Puddles / aquaplaning | By location | A friction zone with very low μ covers most of it; true aquaplaning is speed-dependent — worth it? |

**When and how values change.**

- Zones by location for surfaces, timed events for wind — agreed in principle. Is there a
  surface case that needs time? A road drying out is too slow for a 20–25 s run.
- Is a zone edge sharp or gradual? A sharp change from μ=1.0 to 0.15 in one step is a worst
  case, and arguably unrealistic; a ramp over a few metres adds a parameter.
- On a `RoadGraph`, does a zone attach to a whole segment (simple, already has a `surface`
  field) or to a distance range within a segment (more expressive)?
- Can several zones and gusts appear in one run? What limits their number, so the search
  dimensions stay bounded?

**How weather labels map to physics.**

- Does `condition: rain` imply a friction range automatically (for example rain → μ 0.4–0.6),
  or must every scenario state its ranges explicitly? Explicit is more honest; implied is less
  typing and more consistent across the library.
- Where do those default ranges come from, and who signs off on them? They are scoring inputs
  and go in `docs/METHODOLOGY.md`.

**Fairness to the model under test.**

- NPCs currently brake at scripted decelerations whatever the surface. On ice, a lead car
  stopping at 9.81 m/s² while the ego is limited by μ=0.2 is an impossible test, not a hard
  one. Do NPCs get friction limits too? If so, NPC behaviour on existing scenarios changes.
- Does the model's `Observation` include the weather label? Real cars can see rain but not
  measure μ. Current view: expose the label, never μ — but decide it explicitly, because it is
  a wire-format change (`Observation.to_dict()`/`from_dict()` must change together).
- "Do not vary the thing under test" (`ARCHITECTURE.md` §1.6): EMG-004 keeps friction fixed,
  because friction is what it tests. Which other scenarios should vary friction, and which
  should stay dry because friction would change their behavioural requirement?

**Physics modes.**

- Refuse `kinematic` for environmental scenarios (as proposed), or switch to `dynamic`
  automatically? Automatic switching changes cost without the customer choosing it.
- Should `dynamic` become the default for batch runs? It costs roughly 20–50 µs per step
  against the kinematic model. Measure it on a full suite before deciding.
- Kinematic scores and dynamic scores are not comparable. Does the report state the mode on
  every score?

**Visibility and Phase 6.**

- Is "remove objects beyond visibility distance" a small, honest step now, or the start of
  sensor simulation that the roadmap reserves for Phase 6? Sharp cut-off or probabilistic
  detection? The probabilistic version clearly belongs in Phase 6.

**Scoring, search and pricing.**

- This changes scores, so it needs a `METHODOLOGY.md` change-log entry and a scoring-version
  bump. Which baselines are re-run? `run_suite --baseline` comparisons across the change will
  show as regressions — how is that communicated?
- Results broken down by weather (`ARCHITECTURE.md` §L4, "pass rate by weather condition"):
  build it in the same change, or later?
- New parameterization knobs become search dimensions, which raises `recommended_evals()` and
  therefore the price of a search. Acceptable, or do environment knobs stay out of search by
  default?
- OpenSCENARIO export (`osc_exporter.py`) already loses the parameterization block. Zones and
  gusts make that loss larger — note it, or extend the exporter?

**Calibration.** The Pacejka coefficients are uncalibrated. Environmental physics built on them
supports ranking models against each other on the same simulated road; it does not support an
absolute claim such as "stops in 41 m in rain". Confirm the customer-facing wording before
release.

---

## DI-02 — Unknown scenario events are silently dropped

**Status**: **Built** — commit `1eee550` on `feat/scenario-library-bts`, 2026-09-28. It was
built ahead of the post-build rule because it corrupted scores in the live library, not just
a future feature. `IMPLEMENTED_EVENT_TYPES` in `scenario/events.py` is the single list;
`ScenarioValidator` refuses anything else at load; `run_suite` skips such a scenario and names
it in the report. The fix also found a second victim: INT-002 declared two
`change_traffic_light` events and had been scored against a light that never changed.
`change_traffic_light` is now implemented. `change_weather` is not, so EMG-004 stays refused
until DI-01.

Still open from the questions below: the audit for YAML keys the parser accepts and ignores.

### Raised

2026-09-28, found while checking DI-01 against the code.

### Finding

`EventExecutor._execute()` in `arep/scenario/events.py` handles `spawn_vehicle` and
`spawn_pedestrian`. Any other `type` does nothing, with no error and no log line. The module
docstring advertises `change_traffic_light` and `change_weather`, and neither is implemented.

EMG-004 relies on `change_weather`. It loads, runs and scores as if the ice patch were there.

This breaks the rule the project set for itself in Phases 2–4: *unsupported input is skipped
and reported, never silently dropped — a scenario missing its hazard still runs and still
produces a score, which is the dangerous failure.*

### Direction agreed

An event type the engine does not implement must fail the scenario at load time. Refusing is
better than scoring a run on a hazard that never happened.

### Proposed design

- Keep a set of implemented event types in `events.py`. `ScenarioValidator` rejects any other
  type with a `ScenarioParseError` that names the event and the file.
- Delete `change_traffic_light` and `change_weather` from the docstring until they exist.
- Add a library-wide test: every scenario in `scenarios/` uses only implemented event types.
  Until DI-01 step 3 ships, this test fails on EMG-004, which is the point.

### To discuss before building

- What happens to EMG-004 in the meantime? Options: mark it excluded from `--scenarios all`
  until DI-01 ships (the suite goes from 21 to 20, stated in the report), or leave it failing
  to load so the gap is loud. Either way the current "18 of 21 pass" figure changes.
- Is `change_traffic_light` needed by any scenario today, or should it be removed rather than
  built?
- Audit for the same bug elsewhere: YAML keys the parser accepts and ignores (for example
  `ego.constraints` fields, `behavior.parameters` keys an NPC type does not read). Should
  unknown keys be refused as well, or only unknown event types?
