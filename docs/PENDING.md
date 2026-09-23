# Pending — deferred and known-open items

**What this file is.** A running list of work that is known, deliberately not being
done right now, and would otherwise only exist in someone's memory or a chat log.

**What it is not.** It does not set priority — `docs/ROADMAP.md` does that, and when the
two disagree the roadmap wins. Nothing here is a blocker for the phase in progress; an
item that becomes one gets moved into the roadmap and out of this file.

Each entry says what is missing, why it is open, and what would unblock it. An item with
no "unblocked by" line is simply not scheduled yet.

Last reviewed: 2026-09-23.

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

### Adversarial search has no API, tier gate or credit accounting
`arep/search/` is CLI and library only. `POST /api/search` does not exist, and neither does
the "Pro tier and above, consumes `max_evals` credits" rule the roadmap specifies.

### Model comparison has no API or PDF download
`RegressionDetector` works and the HTML report renders, but `POST /api/compare`,
`GET /api/compare/{id}/results` and `GET /api/compare/{id}/report.pdf` do not exist, so
comparison is CLI-only and uncharged.

### Interop fixtures are not committed
Two acceptance criteria name third-party files that are absent:
`tests/fixtures/TownSimple.xodr` (4.2) and the ASAM `CutIn.osc` sample (4.4). Both parsers
are tested against generated or round-tripped input instead, so neither has been exercised
against a file this project did not write.

### Deterministic replay (2.5)
`FrameHasher` records a per-run digest on `RunRecord.frame_hash` for both live and batch
runs, but nothing replays from it. Closes the `RunPage` stub.

### Pacejka coefficients are uncalibrated
Plausible defaults, not fitted to a measured tire. Documented in `docs/METHODOLOGY.md`.
Do not publish absolute handling claims from them, and do not tune them to make a
scenario pass.

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

### Scenario library is 21 of a target 60
Phase 4.3. All 21 execute; 18 pass against `emergency_brake`, and the three that fail
(EMG-002, LAT-003, MLT-007) fail correctly — each needs evasive steering or gentle
braking, which a brake-only model cannot do. Do not "fix" them by weakening the scenario.

---

## Product decisions outstanding

### Tier entitlements beyond credits
Plans currently differ only by credit allocation. Scenario access and concurrent-run caps
are unspecified.

The open question is what happens to in-flight work on a downgrade. Suggested starting
point: count running tasks only, a batch counts as one, return 429 at the cap, and let
in-flight work finish.

---

## Not started, by design

Tracked in `docs/ROADMAP.md`; listed here so the file reads as a complete picture.

- **Outbound webhooks (3.1)** — only inbound Stripe webhooks exist.
- **GitLab CI integration (3.3)** — the GitHub Action exists.
- **Model versioning API (3.4)** — `models.version` is a column with an index; no history endpoints.
- **ROS2 connector (4.1)** — the HTTP model bridge exists; no `rclpy` transport.
- **Standards alignment (4.5)** — no ISO 26262/21448 traceability matrix or ODD declarations. Certification is never claimed.
- **Sensor simulation (Phase 6)** — observation is ground-truth state. No LiDAR, camera, GPS/IMU. Until it ships, ORION is planning/control evaluation: do not promise perception testing anywhere.
