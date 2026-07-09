# ORION Frontend Redesign — Implementation Plan

> **STATUS: COMPLETE (Phases A–I done, 2026-06-26).** Implemented on branch `feat/ui-redesign-mission-control`. Production build green; grep guards clean (no purple, no `glass-card`, no Inter, `fetch` only in `api.js`, `localStorage` only `orion_token`/`orion-theme`). Legacy token aliases removed. Remaining optional follow-ups noted inline are non-blocking.

> **Companion to `ORION_UI_DESIGN.md`** (the design system) and `design/sample-mission-control.html` (approved sample).
> **Scope:** total visual redesign of `orion-frontend/` to the "Mission Control" language + dark/light theming. **Visual only.** No new features, no new routes, no backend, no TypeScript migration, no new libraries (except Google Fonts already linked). Wiring of currently-unrouted pages is out of scope unless explicitly requested.
> **Approach:** token-first, then shell, then surfaces, then polish. Each phase is independently shippable and leaves the app in a working state.

---

## 0. Constraints (carried from CLAUDE.md §9 & §12)

- All HTTP through `src/services/api.js`. Auth token only in `AuthContext`. `orion-theme` is the only new localStorage key (UI pref, no auth/PII).
- Charts: **Recharts only**. No Chart.js/D3/Tailwind/CSS-modules. CSS co-located.
- 3D: `@react-three/fiber` + `drei` only (no raw imperative Three in components).
- Don't break: routing (`App.jsx`), `AuthContext`, `api.js`, hooks (`useSimulationStream`, `useBatchStatus`, `useReplayStream`), `OrgContext` (still unmounted — leave as-is, Phase 0.6 elsewhere decides).
- Plain JSX. No element `id`s removed if used by tests/automation (preserve existing `id=` hooks like `launch-sim-button`, `runs-table`, `dashboard-sidebar`).

---

## 1. Sequencing overview

```
A Foundation ──► B App shell ──► C Landing ──► D Auth ──► E Dashboard overview
                                   │                              │
                                   └──────────────► F Feature pages (parallelizable)
G Simulation viewer ──► H Cross-cutting (404/ErrorBoundary/skeletons/a11y/responsive) ──► I Cleanup/QA
```
A and B are blocking (everything depends on tokens + shell). C/D/E/F/G are mostly independent after B. H/I are last.

---

## Phase A — Foundation (tokens, theme, fonts, primitives)  ⟵ BLOCKING

**Goal:** the design system exists in code; one component can be built against it.

Files:
- `index.html` — swap Inter `<link>` for Chakra Petch + Saira + JetBrains Mono (preconnect kept). Add **no-FOUC inline script** setting `data-theme` from `localStorage['orion-theme']` (fallback `dark`) before paint. Update `<meta name="description">` if needed.
- `src/index.css` — **rewrite token layer**: `[data-theme="dark"]` + `[data-theme="light"]` color blocks (§3 of design doc, exact hex), `:root` for `--ff-*`, keep `--space-*`, redefine `--radius-*` (2/3/4px), add `--t-*`/`--ease`/`--focus`. Rebuild global utilities: `.btn*`, `.field`, `.panel`/`.panel--live` (+crop-marks), `.data-table`, `.chip*`, `.mono-label`, `.num`, `.spec-strip`, grid backdrop (`body::before/::after`), animations (reveal/blink), `prefers-reduced-motion` block. Add **legacy-alias block** (commented `MIGRATION ONLY`) mapping old tokens/`.glass-card` → new, so unmigrated files still render.
- `src/main.jsx` — wrap `<App/>` in `<ThemeProvider>`.
- **NEW** `src/theme/ThemeContext.jsx` — `ThemeProvider` + `useTheme()` ({theme, toggleTheme, setTheme}); reads/writes `orion-theme`, sets `data-theme` on `<html>`.
- **NEW** `src/components/common/ThemeToggle.jsx` (+`.css`) — the toggle control (sample HUD style).
- **NEW** `src/components/common/Icon.jsx` — inline-SVG icon set (§7 list).

**Acceptance:** app boots, dark default, toggling `ThemeToggle` flips theme + persists + no flash on reload; a scratch `.panel`/`.btn-primary`/`.num` render exactly like the sample in both themes; no console errors.

---

## Phase B — App shell  ⟵ BLOCKING for dashboard

Files:
- **NEW** `src/components/common/HudBar.jsx` (+`.css`) — sticky top status strip (§6.1): wordmark, live status, seed/build/clock, `⌘K` hint, `ThemeToggle`. Build hash can be a constant in `utils/constants.js`.
- `src/components/common/Sidebar.jsx` (+`.css`) — **implement the stub** as the real sidebar (§9.6): numbered nav (Overview/Scenarios/Runs/Models/Batches/Compare/Settings; Billing if `billing_enabled`), credits gauge, user chip, icons from `Icon.jsx`. Replaces the inline `Sidebar` currently inside `DashboardPage.jsx` (move logic out, keep `id="dashboard-sidebar"` + `id="sidebar-<key>"` + `id="sidebar-logout"`).
- `src/pages/DashboardPage.css` + layout shell in `DashboardPage.jsx` — adopt HUD + sidebar + main grid + footer system-line. (Overview content styled in Phase E.)

**Acceptance:** authed shell shows HUD + real sidebar + footer in both themes; nav active state = amber; logout works; preserved element ids intact.

---

## Phase C — Landing

Files: `pages/LandingPage.jsx`, `components/common/Navbar.jsx`(+css), `landing/Hero.jsx`(+`Hero.css`), `landing/FeatureCards.jsx`(+css), `landing/StatsSection.jsx`(+css), `landing/Footer.jsx`(+css).
- Navbar: transparent→scrim-on-scroll, ThemeToggle, CTAs.
- Hero: replace purple R3F starfield/constellation with the **instrument cluster** (reticle gauge + sparkline + telemetry grid) per §11.1; new headline/lead/CTAs/spec-strip; staggered reveal. (If keeping a 3D element: subtle carbon+amber wireframe road — no orbs/glow.)
- FeatureCards/StatsSection/Footer: panel + crop-marks, icons, mono numerals, grid backdrop.

**Acceptance:** `/` matches sample §01 language; no purple/glow/float; both themes; CTAs route to `/signup` `/login`; reduced-motion respected.

---

## Phase D — Auth

Files: `pages/LoginPage.jsx`, `pages/SignupPage.jsx`, `pages/ResetPasswordPage.jsx`(+css), `components/auth/LoginForm.jsx`, `components/auth/SignupForm.jsx`, `components/auth/AuthForms.css`.
- Two-column instrument frame (§11.2): aside panel + form card (`.panel--live`), mono labels/inputs, amber submit, cyan links.
- Preserve behaviors: inline forgot-password panel + anti-enumeration message; reset reads `?token=`, no-token error, success → `Go to Login`; client validation in `--fail` style.

**Acceptance:** all three auth screens match sample §02; existing `api.forgotPassword/resetPassword/login/signup` calls untouched; validation + error states styled; both themes.

---

## Phase E — Dashboard overview

Files: `pages/DashboardPage.jsx`(+css) overview view; dashboard components `dashboard/ScoreCard`(+css), `ScoreDistribution`, `RegressionChart`(+css), `FailureClusterPanel`(+css), `ComparisonTable`(+css), `SmartAlerts`.
- LaunchSimPanel → instrument-frame form (keep `id="launch-sim-panel"`/`"launch-sim-button"`).
- 5 metric panels (§9.4) replacing emoji MetricCards (Composite amber/live, rest cyan, deltas).
- Charts: re-theme Recharts via §12 recipe (palette recomputed on theme change); Run History line, Metric Breakdown radar/bars, Score Distribution histogram.
- Recent Runs table → §9.7 + PASS/FAIL chips (keep `id="runs-table"`).
- Empty/loading/error states (§9.12). "Coming soon" section views → styled empty panels.

**Acceptance:** overview matches sample §03 in both themes; charts recolor correctly on toggle (no hardcoded `#6c63ff`); metric numerals tabular; table chips correct; ids preserved.

---

## Phase F — Feature pages (parallelizable after B)

Restyle to spec (§11.4); **no wiring/new features.** Files:
- `pages/ModelsPage.jsx`(+css), `models/ModelCard`(+css), `models/ModelUploadForm`(+css).
- `pages/BatchPage.jsx`(+css) (+ `hooks/useBatchStatus` consumed as-is) — batch progress readouts/chips.
- `pages/ComparePage.jsx`(+css) + `dashboard/ComparisonTable`.
- `pages/SearchPage.jsx`(+css).
- `pages/SettingsPage.jsx`(+css) — incl. API-keys panel + a theme control mirroring HUD.
- `pages/BillingPage.jsx`(+css), `billing/PlanCard`(+css), `billing/UsageBar` (behind `billing_enabled`).
- `components/common/AlertBanner.jsx`(+css) → §9.11.

**Acceptance:** each file uses tokens only, panel/crop-mark language, mono numerals, icons (no emoji); renders in both themes even if route is unwired.

---

## Phase G — Simulation viewer

Files: `components/simulation/SimulationViewer.jsx`(+css), `PlaybackControls`(+css), `TrajectoryTrace`, `TTCWarningZone`, `NPCIntentOverlay`.
- R3F scene recolor to palette (carbon bg, cyan/amber lines, fail-red TTC zones) per §11.5.
- HUD overlay = full instrument treatment (status strip, telemetry reticles, metric bars, verdict chip, `← Dashboard` ghost). Keep `useSimulationStream` contract + `latencyRef` HUD readout. Keep frame schema consumption unchanged.

**Acceptance:** `/simulation/:runId` overlay matches the language; 3D readable in both themes; no protocol changes; latency/verdict display correct.

---

## Phase H — Cross-cutting

Files:
- **NEW** `src/pages/NotFoundPage.jsx`(+css) — 404 instrument panel; wire as the `*` route in `App.jsx` (replace silent redirect; keep redirect only as deeper fallback if desired).
- **NEW** `src/components/common/ErrorBoundary.jsx` — wrap app in `main.jsx`/`App.jsx`; §9.12 error panel + reset.
- `App.jsx` `ProtectedRoute` loading fallback → skeleton/HUD style.
- Skeleton/loading + empty + error states audited across all data views (§9.12).
- Responsive pass (§10 breakpoints) + a11y pass (focus rings, aria-labels on icon buttons, reduced-motion, skip link, table scroll containers).

**Acceptance:** unknown route shows 404; thrown render error shows boundary not white screen; keyboard-only nav works; reduced-motion verified; layouts hold at 1280/1024/375.

---

## Phase I — Cleanup & QA

- Migrate any remaining files off legacy aliases; **delete the legacy-alias block** from `index.css`.
- Grep guards (expect 0 hits in `orion-frontend/src`): `#6c63ff`, `#a78bfa`, `glass-card` (post-migration), emoji in JSX, `font-family.*Inter`, raw `fetch(`, new `localStorage` token reads.
- Manual verification both themes on every route; capture before/after screenshots.
- Update **CLAUDE.md §9** to point to `ORION_UI_DESIGN.md` as the binding source for all frontend work (add a short "Design system" subsection + governance line; note `orion-theme` localStorage exception; mark redesign phases done). Update memory (`MEMORY.md`) pointer if useful.

**Acceptance:** grep guards clean; both themes correct everywhere; CLAUDE.md references the design doc; lint/build pass.

---

## 2. New files summary

```
src/theme/ThemeContext.jsx
src/components/common/ThemeToggle.jsx (+css)
src/components/common/Icon.jsx
src/components/common/HudBar.jsx (+css)
src/components/common/ErrorBoundary.jsx
src/pages/NotFoundPage.jsx (+css)
```
Plus rewrites of `index.html`, `index.css`, `main.jsx`, and restyle of every page/component listed in Phases B–G.

---

## 3. Risks & mitigations

| Risk | Mitigation |
|------|-----------|
| Token rename breaks many CSS files at once | Legacy-alias bridge (Phase A) keeps unmigrated files rendering; remove only in Phase I. |
| Recharts colors don't update on theme toggle | §12 recipe — recompute palette from CSS vars keyed on `theme`. |
| Removing R3F starfield breaks `Hero` imports/build | Replace contents but keep a valid component; verify build after Phase C. |
| Preserved test/automation `id`s lost in refactor | Explicitly retain listed ids when moving Sidebar/LaunchPanel/tables. |
| FOUC on theme | Blocking inline script in `index.html` before app JS. |
| Scope creep into features/wiring | Plan is visual-only; unrouted pages styled but not wired unless asked. |

---

## 4. Verification checklist (per phase + final)

- [ ] Dark default; toggle persists; no FOUC.
- [ ] No banned aesthetics (§1) anywhere; grep guards clean.
- [ ] All numerals mono+tabular; no emoji; icons from `Icon.jsx`.
- [ ] Contrast AA both themes; focus rings; reduced-motion.
- [ ] Charts recolor on toggle; tooltips themed.
- [ ] Existing behaviors intact (auth flows, launch run, refresh, WS stream, ids).
- [ ] Responsive at 1280 / 1024 / 375.
- [ ] `npm run build` clean; no console errors.
- [ ] CLAUDE.md §9 updated to bind future work to `ORION_UI_DESIGN.md`.

---

## 5. Out of scope (do not do unless asked)

New features · new routes/endpoints · wiring currently-unrouted pages · backend changes · TypeScript migration · new dependencies/icon libs · OrgProvider mounting · auth/security changes (those live in ORION_SAAS_ROADMAP Phase 0).
