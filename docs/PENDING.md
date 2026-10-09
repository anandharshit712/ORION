# Pending — deferred and known-open items

**What this file is.** A running list of work that is known, deliberately not being
done right now, and would otherwise only exist in someone's memory or a chat log.

**What it is not.** It does not set priority — `docs/ROADMAP.md` does that, and when the
two disagree the roadmap wins. Nothing here is a blocker for the phase in progress; an
item that becomes one gets moved into the roadmap and out of this file.

Each entry says what is missing, why it is open, and what would unblock it. An item with
no "unblocked by" line is simply not scheduled yet.

Last reviewed: 2026-09-28.

---

## Blocked on something outside the code

### Stripe live mode
`PLAN_PRICES` and `TOPUP_PRICE_ID` in `arep/api/billing.py` are placeholders and no
test-mode round trip has run against the live API.

Stripe signup is invite-only in India and requires a registered company, so an account
cannot be created at all.

Nothing is blocked by this: `billing_enabled` defaults to `false`, checkout and portal
return 503, and credits are granted by hand through `POST /api/admin/orgs/{id}/credits`.
The webhook signature check, the idempotency ledger and the credit grants are all tested
against hand-built events.

**Unblocked by** a payment-provider decision — a Merchant of Record (Paddle, Lemon
Squeezy), an India-domestic PSP (Razorpay), or incorporation. Coupling is four call sites
in one file, and `webhook_events.provider` is already generic, so the switch is small.
Do not build a provider abstraction before a provider is chosen.

### gVisor in production
Implemented and verified — `ORION_CONTAINER_RUNTIME=runsc` gives a `4.19.0-gvisor` guest
kernel, +11% runtime, identical composite score.

What remains is operational: set `ORION_REQUIRE_HARDENED_RUNTIME=true` on the production
host so the API refuses customer code under plain `runc` instead of falling back.

**Unblocked by** a production host existing.

### Production deployment checks
The Phase 1 launch checklist still has items that need a deploy target: HTTPS everywhere,
and the sign-up → verify → org → first run → results walkthrough run against production
rather than a dev box.

---

## Needs an endpoint that does not exist

### Dashboard: Compare section
`compare` is disabled in `NAV_ITEMS` and renders `ComingSoon`.

`RegressionDetector` (`arep/analysis/regression_detector.py`) is fully implemented but
reachable only from the CLI — there is no HTTP route. `ComparePage.jsx` and
`ComparisonTable.jsx` exist as presentational shells.

**Unblocked by** an endpoint over `RegressionDetector.compare_from_db`.

### Dashboard: Settings section
`settings` is disabled. `SettingsPage.jsx` exists as a shell (Profile, Organization, API
Keys, Theme).

The backend is there — `/api/orgs/me` and `/api/keys/` CRUD — so this is frontend wiring,
not new API work.

---

## Frontend

### Six pages exist but are not routed
`BatchPage`, `ComparePage`, `ModelsPage`, `RunPage`, `SearchPage`, `SettingsPage` each
declare a `/dashboard/...` route in a header comment that `App.jsx` never defines.

Less of a conflict than it first looks. The working pattern is **lists are dashboard
sections** (`setView`), **details are routes** (`:id`):

| page | route | status |
| --- | --- | --- |
| `BatchPage` | `/dashboard/batches/:id` | detail view, complements `BatchesSection` |
| `RunPage` | `/dashboard/runs/:id` | detail view; depends on replay (2.5) |
| `ModelsPage` | `/dashboard/models` | **redundant** — superseded by `ModelsSection` |
| `ComparePage`, `SearchPage`, `SettingsPage` | — | future features |

Only `ModelsPage` actually duplicates anything. Decide whether to delete it before
building further on either pattern; do not add a seventh unrouted page.

### `useBatchStatus` is a stub
`src/hooks/useBatchStatus.js` has a `poll()` whose body is three TODOs — it never
fetches. Its broken default import of `api` is fixed, so it no longer throws, but it
returns `null` forever. `api.getBatchStatus(batchId)` exists and works.

Its only consumer is the unrouted `BatchPage`. `BatchesSection` deliberately does not use
it: `GET /jobs/` already returns every count the list needs, and one request per row
would be worse.

### `useReplayStream` is a stub
Same shape, for Phase 2.5 replay. Broken import fixed; body still TODO.

### Simulation overlay components are placeholders
`TrajectoryTrace`, `TTCWarningZone`, `NPCIntentOverlay` and `PlaybackControls` render
nothing — geometry and wiring are marked `TODO [P5]`.

### ESLint has no config
`npx eslint src` fails with "couldn't find an eslint.config.* file". ESLint 10 needs flat
config and none was ever added. CI does not run it, so this is invisible today: CI runs
`npm test` and `npm run build`, both green.

### Bundle is over the warning threshold
The production build emits one 1.48 MB chunk (407 kB gzipped) and Vite warns. Three.js and
Recharts dominate. Route-level code splitting would fix it.

### No TypeScript
Plain JSX throughout. A progressive migration is Phase 5 work.

---

## Scoring and analysis

### CMA-ES does not beat the random-search baseline
Acceptance criterion 2.3 asks that CMA-ES outperform random search over 50 evaluations. It
does not. Measured on LON-003 with `EmergencyBrake`, 50 evaluations each:

| optimizer | best fitness | evaluations |
| --- | --- | --- |
| CMA-ES | 1.57 | 50 (found no collision) |
| Random | **13.51** | 30 (stopped — found one) |

Most likely a budget problem: the search space has 8 dimensions, and 50 evaluations is far
too few for CMA-ES to build a useful covariance, so it is still exploring while random
search gets lucky. Needs either a much larger budget before the comparison means anything,
or a smaller default search space.

**Do not claim CMA-ES superiority in customer-facing material until this passes.** The
search is still useful — it finds and reproduces counter-examples — it is just not yet
demonstrably better than sampling.

### Search budget tooltip — deferred to the UI work

When the search UI is built, the run-count control gets an "i" affordance whose tooltip
appears on hover. **No price estimate and no numbers** — just that a larger budget costs
more. The information is there for anyone who wants it; choosing not to hover is the
customer's choice.

Suggested wording, which says what they gain as well as what it costs:

> More runs search harder and find rarer failures. Longer runs use more credits.

Picked up with the rest of the dashboard work, alongside the search form itself. Nothing in
the backend blocks it — `recommended_evals(n_dims)` already gives the minimum to show.

### Adversarial search has no API, tier gate or credit accounting
`arep/search/` is CLI and library only. `POST /api/search` does not exist, and neither does
the "Pro tier and above, consumes `max_evals` credits" rule the roadmap specifies.

**The algorithm questions are settled** (2026-09-24): CMA-ES beats random search from about
ten evaluations per dimension, `recommended_evals()` enforces that floor per scenario, every
scenario in the library is now searchable, and the search can return every failure rather
than stopping at the first. What remains is purely the pricing decision — charging per
*evaluation* means a search that stops early costs almost nothing while a thorough one
costs a lot, which may be exactly right or exactly backwards.

### Comparison has no PDF download endpoint
`POST /api/compare` and `GET /api/compare/{id}` exist and are charged correctly. What is
missing is `GET /api/compare/{id}/report.pdf`: the generator works and renders every
section, but WeasyPrint needs GTK, which is absent on Windows, so the endpoint could not be
exercised here.

### Interop fixtures are not committed
Two acceptance criteria name third-party files that are absent:
`tests/fixtures/TownSimple.xodr` (4.2) and the ASAM `CutIn.osc` sample (4.4). Both parsers
are tested against generated or round-tripped input instead, so neither has been exercised
against a file this project did not write.

### Deterministic replay — storage and scaling
Replay is built end to end (corrected 2026-09-29; this entry used to say the viewer was
missing). `RunPage` at `/dashboard/runs/:runId` plays stored frames with scrub, speed and
event markers, and offers seed replay. What is open: no retention for `run_frames`, no pin
endpoint, an in-memory live-run registry that never evicts completed runs and cannot serve
more than one API process, and a dead `useReplayStream.js` stub. Post-build. Details:
`docs/DISCUSSIONS.md` DI-04.

### Expanding beyond driving
Other model architectures already fit `ModelInterface`. Other domains would reuse about half
the code through a "domain pack". Direction only, post-build. The second domain is
deliberately undecided and will be settled when the discussion list is worked through.
Details: `docs/DISCUSSIONS.md` DI-06.

### Viewer judder: 50 Hz frames on a 60 Hz+ screen
The 3D viewer jumps to each frame with no interpolation, so on a 60 Hz display one frame in
five is drawn twice. Cosmetic, post-build. Details: `docs/DISCUSSIONS.md` DI-05.

### One run in five on LON-003 / LAT-001 is void but scored
A negative `ego_x_jitter` puts the ego behind the start of the flat road, and it terminates
`off_road` at t=0.02 s. Measured: 20 of 100 LON-003 runs, each scored 0.82–0.90 and counted
in the batch mean. The reported worst run (seed 139) is one of them. The library invariant
test checks seed 42 only. **This corrupts current scores**, but it is post-build by decision
(2026-09-29). Until then, don't quote LON-003 or LAT-001 scores as clean. Details:
`docs/DISCUSSIONS.md` DI-03.

### Pacejka coefficients are uncalibrated
Plausible defaults, not fitted to a measured tire. Documented in `docs/METHODOLOGY.md`.
Do not publish absolute handling claims from them, and do not tune them to make a
scenario pass.

### Weather does not reach the physics
Friction is one global value per evaluation, set in config, and the default `kinematic` mode
ignores it. `weather.condition` and `visibility` in scenario YAML are labels that physics and
`Observation` never read. `friction_mu` in the tick frame is hardcoded to 1.0. There is no
wind model. The agreed direction: environmental physics varies per run, and may change during
a run through zones (friction, visibility) and timed events (wind gusts). Every change is
fixed by a few numbers drawn at run start, never random drift from tick to tick.

**Post-build:** not picked up until the roadmap build is complete, and it does not change any
remaining roadmap item. **Full finding, design and open questions**: `docs/DISCUSSIONS.md`
DI-01. Even then, it is not ready to build until the parameter list, the NPC-fairness
question and the mode policy are settled there. Until it ships, EMG-004 is refused at load
(DI-02, built), so the suite runs 20 of 21 scenarios. It changes scoring, so it needs a `METHODOLOGY.md` change-log entry.

### TTC approximations
Constant-acceleration projection, with acceleration held constant over the projection and
steering not projected at all. Documented wherever it surfaces. TTC ranks models on a
scenario; it is not a calibrated time to impact.

---

## Coverage and verification

### PDF rendering is unverified on Windows
WeasyPrint cannot load its GTK libraries here, so `render_html()` is what the tests
exercise. The PDF step runs in Linux CI.

### OSC2 round trips lose the parameterisation block
By design, with a test pinning the behaviour. An exported scenario re-imported is the
concrete case, not the parameterised family.

### ~~Scenario library is 21 of a target 60~~ — closed 2026-09-29
Phase 4.3 is complete: 60 scenarios, ten per category. 59 execute (EMG-004 is refused at
load, DI-02) and 51 pass against `emergency_brake`. Seven of the eight failures are correct —
each needs evasive steering, or leaves the ego somewhere braking cannot help. The eighth is
below.

Three reserved themes were substituted rather than written: "pedestrian at night" (VRU),
"dust storm" and "flash-flood water" (EMG). All three need environmental physics, so writing
them now would have produced scenarios differing from their dry-daylight equivalents only in
the description. Each substitute file names the theme it stands in for. They return with
DI-01.

### ~~Ten scenarios have a corner no braking behaviour survives~~ — fixed 2026-09-29
Twelve in the end, once a usable margin floor was applied rather than just a non-negative one.
Each lead's start position moved further away, nominal `x` and the `initial_x` range shifted
together so the spread that blocks pattern-learning is preserved.

Re-measured on all twelve: `emergency_brake` now collides on none of them, `ConstantAction`
still collides on 80–100%. Nothing was weakened — the impossible corner was removed, not the
difficulty. `docs/METHODOLOGY.md` carries the change-log row; scores on those twelve are not
comparable across the change.

`tests/test_scenario_feasibility.py` enforces the invariant for every scenario present and
future, with an explicit allowlist for the cases where braking is meant to be insufficient.

### ~~The library has no reference model that can pass it~~ — fixed 2026-09-29
`ReferenceDriverModel` (`models/examples/example_models.py`, registered as `ReferenceDriver`
and as `reference` for `run_suite`): IDM car-following, PD lane keeping, bounded evasion. It
is a reference rather than a good driver — IDM parameters are conventional values from the
literature and deliberately not tuned against this library.

What it buys: "fails correctly" stops being an argument and becomes something measurable. Run
`--model reference` against any scenario the degenerate models fail and the result says
whether the scenario is demanding or broken. It has already earned this — it passes EMG-001,
which `emergency_brake` fails, proving that scenario's evasion requirement is real.

**It passes 32 of 59, against `emergency_brake`'s 52, and that is not a defect in it.**
Nothing in the composite rewards progress, so a model that drives has more opportunity to
fail than one that stops. Its own remaining weaknesses, measured and not tuned away:

- **Junctions needing a turn** (INT-003, INT-004, INT-005). It has no route, so it goes
  straight. INT-003 is unpassable by anything in the repo for that reason.
- **Approach speed at a sight-restricted junction** (INT-010, 0.70 collisions). It arrives at
  the speed limit because it has no notion that a junction is blind. The scenario's own
  description says a model that does this has already failed, so this is the correct outcome
  and a real gap in the model.
- **Its evasion heuristic costs it the road** on several lateral scenarios (EMG-003, LON-007,
  MLT-006 at 0.8–1.0 off-road). It steers away from an obstacle it cannot stop for, bounded to
  about one lane width, with no way to know whether the space it is steering into is road.
  Closing this properly needs the lane assignment below, not a bigger heuristic.

Deliberately not tuned further. Two rounds of adjustment produced mixed results, and a
reference tuned until scenarios pass is a reference that proves nothing.

### ~~Lane keeping was not achievable~~ — fixed 2026-09-30
`Observation.lane_offset` was the unsigned distance to the centreline, so a controller steered
the same way whichever side of the lane it had drifted to and every perturbation ran away.
`lane_heading_error` was hardcoded to 0.0, disabling the derivative term of any such
controller. Both fixed; off-road runs went 5/10 to 0/10 on the lane-keeping baseline for both
steering models in the repo.

The signed offset had existed since Phase 0.5 and the compliance metric used it throughout —
only the copy handed to the model was unsigned, so the platform scored models on a lane
discipline it never gave them the means to achieve. Scores move for any model that steers;
see the change log in `docs/METHODOLOGY.md`.

### Nothing in the composite rewards making progress
Found while testing the reference model, and larger than it looks.

On LON-001, `EmergencyBrake` scores **0.962 stability and 0.988 composite** by braking to a
standstill in the first second and sitting still for the remaining thirty. A stationary car
has no jerk, no steering variance, no speeding and no collisions. Safety, compliance,
stability and reactivity all measure *how* the vehicle behaves; none measures whether it got
anywhere.

The suite's pass criterion inherits it — pass is a collision and intervention rate, so
refusing to move passes most of the library. `emergency_brake` passing 51 of 60 is partly
this, and any comparison against it has to be read in that light.

**Not fixed here**, because a progress term is a scoring change: it needs a definition
(distance along the route? time to the scenario's objective? both, and how weighted?), a
`docs/METHODOLOGY.md` change-log row, and re-measured baselines for the whole library. It is
also the sort of term that is easy to get wrong in the dangerous direction — anything that
rewards speed has to be dominated by the safety term or the platform starts scoring
recklessness as competence.

`tests/test_reference_model.py::test_a_model_that_never_moves_still_scores_well` pins the
current behaviour, so adding the term will fail that test loudly rather than pass silently.

### ~~The roundabout template cannot be driven~~ — mostly a symptom, see below
`road_templates.roundabout()` does build the circulating carriageway as a single lane on a
curve, so the geometry is genuinely demanding and INT-004 remains the hardest scenario in the
library. But the reason *nothing* could drive it was not the geometry: it was that
`Observation.lane_offset` had no sign, so no controller could hold any lane, straight or
curved. That is fixed.

What remains specific to the roundabout: a straight path across the circle is off-road at
every point between the two crossings, so the scenario can only be passed by tracking the
circulating centreline. Its arms are single-lane with the centreline at y=0, which is why a
roundabout scenario must put the ego at `y: 0.0` and declare `lanes: 1` — the usual `y: -1.75`
two-lane convention starts the ego off the road.

### No lane assignment reaches the model
The binding limitation on the whole intersection category, and the residue of the
`lane_offset` defect.

A model is given the offset and heading error against the **nearest** lane. Nothing tells it
which lane it is supposed to be in. On a straight multi-lane road that is merely untidy — a
car drifting past the midpoint will settle into the neighbouring lane and hold it, which is
stable if not obedient. At a junction it is worse than untidy: the nearest lane can be an arm
crossing the vehicle's path, so a lane-following controller can be steered into conflicting
traffic by the interface itself.

Consequence: a model can react inside a junction but cannot plan through one, and ORION
cannot presently distinguish "took the wrong lane" from "held the wrong lane correctly".

Closing it means putting a route or a lane assignment in `Observation` — which lane, and what
comes next along it. That is an interface change with a wire-format consequence
(`Observation.to_dict()` is the sandbox and HTTP contract, and both sides move together), so
it is a design decision rather than a repair.

Until then, read INT results with the limitation in mind: they measure reaction inside a
junction, not negotiation of one.

### LON-002 is unsurvivable on about a tenth of its draws
Found while measuring the finished library; it predates Phase 4.3 and is identical at
`1932caa`, so it is not a regression from that work.

`emergency_brake` commands maximum deceleration from tick 0 — it is the upper bound on what
any braking model can do — and still collides on 10% of draws. The arithmetic: the ego draws
up to 27.78 m/s against a declared `max_deceleration` of 8.0, needing about 48 m to stop,
while `lead_vehicle.initial_x` draws as low as 35 m. No behaviour passes those draws, so the
scenario scores a model on its geometry rather than on its response, and it sits in the suite
as a permanent false negative.

This is not the same as EMG-002 or LAT-003, which fail because they ask for steering a
brake-only model does not have. Those are correct. This one asks for nothing that exists.

**Not fixed here, deliberately.** Raising the `initial_x` floor to roughly 55 m moves an
existing scenario's scores, so it needs its own change with a `docs/METHODOLOGY.md`
change-log row and a re-measured baseline — not a line buried in a library-expansion commit.
Worth checking the other pre-existing scenarios for the same arithmetic in the same pass.

### Suite → plan entitlement mapping
Phase 4.3 shipped the suites themselves — `SUITES` in `arep/cli/run_suite.py`: `core`
(LON+LAT, 20), `intersection`, `vru`, `emergency`, `multi-agent`, `full`. Which plan may run
which suite is not encoded anywhere, on purpose: it is a pricing decision, and putting an
entitlement table in the CI runner would leave the CLI, the API and the billing code each
holding their own copy of the answer. It belongs beside `PLAN_CREDITS` in `api/billing.py`
once the prices are set. See "Tier entitlements beyond credits" below — this is the same
decision.

### Importance sampling is not reachable over the API
`EvaluationRunner.run_batch(..., importance=...)` works for the CLI, SDK and library paths.
`POST /api/runs/batch` does not accept a region, because `RunRecord` has no column to persist
a run's importance weight: a queued batch would lose it, and the API would then publish the
biased draw as if it were the scenario's collision rate. Adding the column (and carrying the
weight through the Celery task) is the whole of what unblocks it.

### Phases 2 and 3: what is left needs people, not code
Every buildable item in both phases is done as of 2026-09-27. What remains cannot be
closed from this machine:

- **≥1 external beta user** running their own model. Needs an external person.
- **Statistical methodology reviewed by someone with a safety-engineering background.**
  `docs/METHODOLOGY.md` is written for exactly that review — every weight, threshold and
  stated approximation — but the reviewer cannot be us.
- **The GitHub Action against a real pull request** (3.2). The image is published and
  anonymously pullable; one PR settles it.
- **Publishing the GitLab component** (3.3) — see below.

### Publishing the GitLab CI component (3.3)
The component source is written, tested and pinned to the same image as the GitHub Action
(`ci/gitlab/templates/evaluate-model.yml`). Publishing it needs a `gitlab.com/orioneval`
project, which does not exist — a component is published from a GitLab project and ORION is
on GitHub. `ci/gitlab/README.md` has the five steps.

**Nobody is blocked.** Any GitLab project can run the suite today with the copy-paste job in
that README, which pulls the public image directly. The component only removes about fifteen
lines of YAML from a customer's pipeline.

### The GitHub Action against a real pull request
The three exit codes are verified inside the built image and both integration files are
parsed by test the way the platforms parse them. What no local check can answer is whether
GitHub accepts `action.yml` and pulls the image — the first push to `main` publishes it, and
one PR that adds the action settles it.

### Widening the ruff rule set
`[tool.ruff] lint.select` is pinned to `E4, E7, E9, F` — what ruff shipped as its default
through 0.15 and what the tree is clean against. Ruff 0.16 turns on `UP`, `I`, `DTZ`, `SIM`,
`PL`, `BLE` and `RUF` by default; against this tree that is **862 findings**, 729 of them
auto-fixable.

Worth doing family by family, each as its own commit, because the diff is large and
mechanical and would otherwise bury a real change. One of them is not cosmetic: **27
`DTZ003` hits for `datetime.utcnow()`**, which is deprecated in Python 3.12 and returns a
naive datetime — this repo already bans wall-clock reads inside simulation code, and these
are in the API and database layers where a naive UTC timestamp compared against an aware one
raises.

---

## Product decisions outstanding

### Tier entitlements beyond credits
Plans currently differ only by credit allocation. Scenario access and concurrent-run caps
are unspecified.

**One decision is made**: adversarial search has **no tier gate** (2026-09-27), against the
roadmap's "Pro tier and above". Credits are the limiter, and a customer who hits the feature
once on the free plan is the best argument for the paid one. That keeps the codebase free of
entitlement machinery — the first feature that genuinely needs a gate will have to add it.

The open question is what happens to in-flight work on a downgrade. Suggested starting
point: count running tasks only, a batch counts as one, return 429 at the cap, and let
in-flight work finish.

---

## Not started, by design

Tracked in `docs/ROADMAP.md`; listed here so the file reads as a complete picture.

- **ROS2 connector (4.1)** — the HTTP model bridge exists; no `rclpy` transport.
- **Standards alignment (4.5)** — no ISO 26262/21448 traceability matrix or ODD declarations. Certification is never claimed.
- **Sensor simulation (Phase 6)** — observation is ground-truth state. No LiDAR, camera, GPS/IMU. Until it ships, ORION is planning/control evaluation: do not promise perception testing anywhere.
