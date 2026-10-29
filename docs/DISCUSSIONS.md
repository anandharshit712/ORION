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

---

## DI-03 — One run in five on LON-003 and LAT-001 ends at tick 1 and is still scored

**Status**: Open — nothing built, **post-build (decided 2026-09-29)**. It corrupts current
scores, as DI-02 did, but the user chose to keep it with the rest of the list rather than
make a second exception. Until it ships, LON-003 and LAT-001 batch means include roughly one
void run in five, and a batch's "worst run" on those two may be a one-tick non-event. Don't
quote either scenario's scores as clean. Also in `docs/PENDING.md`.

### Raised

2026-09-29. Question: *"How does rewatching a run work, and what does it cost the
database?"* While measuring stored-frame sizes, the "worst run" from the 100-run demo
(LON-003, `EmergencyBrake`, seed 139) came back with **2 frames**. A 20-second scenario.

### Finding

Verified by running seeds 42–141 of LON-003 against `EmergencyBrake` through
`EvaluationRunner.run_single`:

- **20 of 100 runs terminate `off_road` at t=0.02 s**, before the model has done anything.
- They are **scored anyway**, at 0.82–0.90 composite, and counted in the batch mean. The
  demo's "composite 0.949, collision rate 0%" includes 20 runs that never happened. The
  `ConstantAction` figure of "80% collision" is very likely 100% of the runs that actually
  ran, with the other 20% being these void starts.
- The batch's reported **worst run (seed 139) is one of them.** The "Replay →" link a
  customer follows to see the model's worst behaviour opens a one-tick non-event.
- **Cause.** `parameterization.ego_x_jitter: {min: -5, max: 5}` around `ego.initial.x: 0.0`
  on a flat road (no `template`). The flat lanes start at x=0. A car placed at x<0 has, as
  its nearest centreline point, the start of the lane, so its "lateral offset" is really its
  distance behind the road. Past half a lane width (1.75 m), `check_off_road` says off-road.
  The data fits: seeds that land at x=−2.43 and x=−4.88 terminate, while seeds at x=−1.3,
  −0.62 and −0.1 don't.
- **Affected**: LON-003 and LAT-001 (both flat, ego at x=0, jitter min −5). INT-004 also
  jitters, but it starts at x=−50 on a template road.
- **Why the suite missed it.** `test_every_scenario_starts_the_ego_inside_a_lane` checks
  **seed 42 only**, which jitters the car forward (+3.69 m). The invariant holds for the
  nominal draw and fails for a fifth of the real ones.
- **Knock-on**: `frame_store.should_store()` keeps frames for `off_road` runs, so these void
  runs are also the ones the database stores for playback.

### Direction agreed

None yet — raised, not discussed. First view:

1. **A run that terminates before the model's first action is void, not scored**, the same
   rule as `ModelSandboxError`: fail it, refund it, name it. A run the model never drove
   cannot count for or against it.
2. **Fix the scenarios** so every draw starts on the road (jitter forward only, or start the
   ego further in), and **make the invariant test sample the range**, not seed 42 alone.
   Checking the min and max of every positional range is cheap and exhaustive for a uniform
   box.
3. **Flat lanes should not end at x=0 behind the ego**, or off-road should mean "off the
   road", not "far from the nearest lane point". Which of these is right is a question below.

### To discuss before building

- Void or re-draw? Voiding is honest but costs the customer a run; re-drawing with the next
  seed breaks `seed = master_seed + run_index`, which is a stated invariant. Current view: void.
- Where does the boundary sit: "terminated on step 0", or "terminated before the model's
  action had any physical effect"? The second is more correct and harder to state.
- Fix the geometry (flat lanes extend behind the start) or the scenarios (no negative
  jitter), or both? Fixing the geometry changes `check_off_road` for every flat scenario.
- Scores change: LON-003 and LAT-001 baselines move, which needs a `METHODOLOGY.md`
  change-log entry and a scoring-version note. Every earlier batch on those two carries the
  artefact. Is that disclosed, or are stored batches re-summarised?
- Audit the whole library for the general case: any positional range whose endpoints are not
  all on the road. The fixed invariant test answers this mechanically.

---

## DI-04 — Replay and live streaming: storage and scaling gaps

**Status**: Open — nothing built, post-build. Also in `docs/PENDING.md`.

### Raised

2026-09-29, same question as DI-03: *"Will saving simulations for rewatch load the database,
and how is that managed?"*

### Finding

What works, verified in code:

- **Two rewatch paths.** Seed replay (`POST /api/runs/{id}/replay`) re-simulates from the
  scenario YAML stored with the run, not the file on disk, and streams it live. It stores
  nothing and reports both frame digests so the client can prove it matches. Stored-frame
  playback (`GET /api/runs/{id}/frames`) serves gzipped frames, **only for runs that collided
  or left the road** (`frame_store.should_store`).
- **Measured cost**: a LON-003 collision run is 152 frames, **118 KB of JSON → 4 KB gzipped
  (27×)**, at about 790 B per raw frame. `MAX_FRAMES = 20_000` and an 8 MB compressed cap
  refuse pathological runs outright rather than truncating them.
- **Frontend**: `/dashboard/runs/:runId` (`RunPage.jsx`) plays stored frames through the
  same `Scene` component the live viewer uses, with play/pause, step, a real range-input
  scrub, speed control and server-computed jump-to-event markers. When nothing is stored, it
  falls back to seed replay.

Gaps:

| Gap | Where | Consequence |
| --- | --- | --- |
| No retention policy for `run_frames` | `database/models.py`, no TTL or cleanup job | Grows forever with every failing run. Small per row, unbounded in total. |
| Frames live in the relational DB as `LargeBinary` | `RunFrameRecord.frames_gzip` | Fine at KB scale; object storage is the usual home once volume grows. |
| `reason = "pinned"` exists, no endpoint sets it | `RunFrameRecord.reason` | A customer cannot keep frames for a passing run they want to show someone. |
| Live-run registry is **in process memory** | `api/sim_registry.py`, `SimulationRegistry._runs` | Completed runs are never evicted (only `DELETE` removes one). Lost on restart. With more than one API process, a WebSocket landing on a different process from the one running the sim finds nothing. |
| `useReplayStream.js` is a dead stub | `orion-frontend/src/hooks/` | `RunPage` does its own playback. The stub still says `TODO [P5]`, and PENDING still lists the replay viewer as not built. |
| DI-03 void runs get stored | `should_store()` keeps `off_road` | The stored-frame budget is spent on non-events. |

### Direction agreed

None yet. First view: retention plus a pin endpoint are small and clearly worth doing.
Moving the registry out of process memory is only needed once there is more than one API
process. Object storage for frames is only needed once measured volume says so.

### To discuss before building

- Retention length: fixed (for example 90 days), per plan tier, or tied to the batch's own
  lifetime? Deleting frames loses nothing that seed replay can't rebuild, as long as the
  scenario YAML and the model artefact are still stored. Is the model artefact retained as
  long as the run is?
- Pinning: who can pin, how many per org, does it cost credits?
- Live-run registry: evict completed runs after N minutes, or move it to Redis (already a
  dependency for Celery) with pub/sub for frames so any API process can serve any socket?
- Do batch runs ever stream live? Today only single runs from `POST /api/runs/` do. Is
  "watch run 37 of a batch while it runs" a feature anyone needs?
- Delete `useReplayStream.js` and correct the PENDING entry, or keep the hook and move
  `RunPage`'s logic into it?

---

## DI-05 — The viewer draws 50 Hz data on a 60 Hz (or faster) screen with no interpolation

**Status**: Open — nothing built, post-build. Cosmetic: no score is affected. Also in
`docs/PENDING.md`.

### Raised

2026-09-29. Question: *"What refresh rate are frames shown at, and why that number?"*

### Finding

- The server sends one frame per simulation tick: **50 per second** (`tick_interval=0.02`),
  paced by a deadline in `SimulationEngine.run_async`. If it falls behind, it resets the
  deadline rather than bursting to catch up.
- Replay (`RunPage.jsx`) plays stored frames at `DT_MS = 20` divided by the speed
  multiplier: also 50 per second at 1×.
- The browser draws at the **display's refresh rate** (R3F render loop, commonly 60 Hz,
  often 120–144). `Vehicle` in `SimulationViewer.jsx` jumps to the latest frame's position.
  No interpolation between frames. On a 60 Hz screen, one frame in five is drawn twice,
  which shows as a slight, regular judder at speed. Network jitter on the live path makes it
  irregular.
- Every frame also triggers a React re-render of the HUD (`setFrame` per message). That's
  fine at 50 Hz, but it sets the ceiling if the rate ever rises.

### Direction agreed

None yet. First view: keep 50 Hz on the wire (it is the simulation's true rate, and sending
more would be invented data). Smooth on the client by drawing slightly in the past and
interpolating position and heading between the two frames either side of the draw time.
This is the standard fix and costs one frame (20 ms) of extra latency.

### To discuss before building

- Interpolate, or extrapolate from the last velocity? Interpolation never shows a position
  that didn't happen, which matters in a safety tool (a collision must never be drawn before
  it occurs). Current view: interpolate.
- How much buffer on the live path: one frame, or a small jitter buffer (2–3 frames) at the
  cost of 40–60 ms delay?
- Does the HUD stay on raw frames (numbers must match the frame exactly) while only the 3D
  scene is interpolated? Current view: yes.
- In slow-motion replay (0.1×), interpolation matters most. At 0.1× the screen gets a new
  frame only every 200 ms.

---

## DI-06 — Expanding beyond driving: other model types and other domains

**Status**: Open — direction only, post-build. **Which domain comes second is deliberately
undecided**; it is settled when this list is discussed, not before. Also in `docs/PENDING.md`.

### Raised

2026-09-29. Question: *"Could ORION evaluate other kinds of models — language models, image
networks, sequence models?"*

### Finding

Two different questions hide in that one.

**Other model architectures for driving: already supported.** The only contract is
`ModelInterface.predict(Observation) -> Action`. Rules, image networks, recurrent or
sequence models, reinforcement-learning policies and language-model planners all fit behind
it. The limit is the input, not the architecture: `Observation` is ground-truth state, so a
model that consumes camera pixels needs Phase 6 (sensor simulation).

**Other domains: about half the code is domain-neutral.**

| Domain-neutral (reusable) | Driving-specific |
| --- | --- |
| `RandomManager` seeding, `FrameHasher`, seed replay | `core/physics.py`, bicycle/Pacejka models |
| Parameterization ranges (`scenario/parameterizer.py`) | `core/road.py`, road templates, lanes |
| `StatisticalAggregator`, CIs, Wilson, worst/best by seed | `Observation` / `Action` fields |
| `analysis/regression_detector.py`, failure clustering, `search/` | Metrics: TTC, lane compliance, speed limit |
| Sandbox, container runner, `ModelWrapper` | The seven-step order of `SimulationEngine.step()` |
| Orgs, credits, Celery queue, CI runner, SDK | Scenario schema, the six-category taxonomy |

The test for whether a domain fits is **a closed loop**: the model acts, the world reacts,
the model acts again.

| Candidate | Fit | Why |
| --- | --- | --- |
| Other machines that move (delivery/warehouse robots, drones, boats) | **Strong** | Same loop, physics, safety questions. Swap world and metrics, keep the rest. |
| Agents acting in a software world (e.g. a language-model agent using tools) | **Possible, with caveats** | Loop exists and scenarios with varied settings make sense, but determinism and objective scoring both weaken. |
| Single-shot models (classifiers, forecasters) | **Poor** | No loop; dataset-with-perturbations evaluation is a crowded space and discards closed-loop simulation, the thing that differentiates ORION. |

### Direction agreed

- **No generic abstraction ahead of a second real domain.** An interface designed from one
  example is the driving interface with "car" deleted. Build the second domain for real, then
  extract the common core from two working examples.
- **The likely shape**, once extracted: a domain-neutral core plus a *domain pack* supplying
  (1) a deterministic world, `reset(seed)` / `step(action)`; (2) observation and action
  formats; (3) documented metrics; (4) a scenario format and its parameterization ranges.
- **Initial positioning view** (to be confirmed): the boundary is "autonomous systems that act
  in the physical world", where general-purpose evaluation tools are weakest.

### To discuss before building

- **Which second domain**, and is there a real user for it? Decided when the list is discussed.
- **Non-deterministic models.** Language models can answer identical input differently. Is
  replay then from a recording of every response rather than from the seed? How does the
  frame fingerprint work when regeneration is not bit-exact?
- **Softer scores.** Rubric or model-as-judge grading is not physics. How is it labelled so
  it is never read with the same confidence as a collision count? Does it get its own
  `METHODOLOGY.md` section and scoring version?
- **What moves into the core.** Is the step order a core rule with domain hooks, or entirely
  domain-owned? Do the four metric weights become per-domain config?
- **Product surface.** One product with domain packs, or separate products on a shared
  engine? Pricing per run may not mean the same thing across domains.
- **Phase 6 overlap.** Camera-based driving models (image networks on pixels) are the
  in-domain version of this question and are already on the roadmap. Should they come first?
