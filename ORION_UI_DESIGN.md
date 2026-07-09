# ORION UI Design System — "Mission Control"

> **Status:** v1.0 · Approved 2026-06-25 · **Governing document for ALL frontend work.**
> **Reference artifact:** `design/sample-mission-control.html` (the approved visual sample — open in a browser).
>
> **Authority:** Every change to `orion-frontend/` MUST conform to this document. Nothing visual ships outside the rules here unless the user explicitly authorizes a deviation. If a request and this doc conflict, stop and ask. When implementation detail is ambiguous, this doc + the sample file win.
>
> Companion: `ORION_UI_REDESIGN_PLAN.md` (how the migration is sequenced). CLAUDE.md §9 points here.

---

## 0. How to use this document

- Building a new screen/component → read §1–§10 (the system) then find the closest spec in §11.
- Touching colors, type, spacing, radius → use the tokens in §3–§5 **only**. Never hardcode a hex, px font size, or one-off radius.
- Unsure what something looks like → open `design/sample-mission-control.html`; it is the canonical render of this spec.
- Adding a token / component pattern not covered here → add it to this doc in the same edit (CLAUDE.md §0 standing instruction).

---

## 1. Design philosophy

ORION is a **deterministic, statistically rigorous test harness** for autonomous-driving policies. The UI must read like a **precision measurement instrument**, not a consumer AI app.

**The five principles (non-negotiable):**

1. **Instrument, not decoration.** Every element looks like it reports a measured value. Chrome serves data; it never competes with it.
2. **Structure is visible.** Grid lines, borders, corner crop-marks, section indices. The skeleton is part of the aesthetic — we expose it, we don't hide it behind blur.
3. **Numbers are sacred.** All numerals are monospace + tabular. A value never shifts horizontally as it updates. Data is the hero.
4. **Sharp and flat.** Hard 2–4px corners, 1px borders, no glassmorphism, no drop-shadow soup, no glow-float. Depth comes from borders and surface tone, not blur.
5. **Restraint with one signal.** Hazard amber is the single attention color. If everything glows, nothing reads. Amber marks the live/active/primary thing only.

**Banned (this is the "generic AI slop" we are escaping):**
`Inter`/`Roboto`/system-font body · purple/violet gradients · `backdrop-filter` glass cards as the primary surface · pulsing glow shadows · floating/levitating cards · rounded-2xl everything · emoji as UI icons · centered hero with two gradient blobs. None of these appear anywhere.

---

## 2. Brand & identity

- **Wordmark:** `ORION//AREP` (HUD contexts) or `ORION` (compact). Set in Chakra Petch 700, letter-spacing `.16–.18em`. The `//` is amber.
- **Mark:** a 45°-rotated amber square (`◆` rendered as a CSS square `transform: rotate(45deg)`), 7–8px, with a faint amber box-shadow. Used as the bullet before the wordmark and as a favicon basis.
- **Tagline:** "Robustness, measured." Secondary: "A test harness — not a simulator."
- **Voice in UI copy:** terse, technical, telemetry-flavored. Uppercase mono micro-labels (`MIN TTC`, `SYSTEM NOMINAL`, `SEED 42`). Avoid marketing fluff in the product surface; the landing page may be slightly warmer.

---

## 3. Color system

Tokens are CSS custom properties scoped by `[data-theme="dark"]` / `[data-theme="light"]` on `<html>`. **Dark is default.** Never use a color outside this table.

### 3.1 Dark theme (default)

```css
[data-theme="dark"]{
  /* surfaces */
  --bg-base:    #0A0C10;   /* app background (carbon) */
  --bg-sunken:  #07090C;   /* recessed: sidebar, page gutters */
  --bg-panel:   #101420;   /* default panel / card surface */
  --bg-elev:    #161C2A;   /* raised: popovers, menus, modals */
  --bg-inset:   #0C0F16;   /* inputs, progress tracks, table hover */

  /* structural grid + borders */
  --grid-line:  rgba(128,150,185,0.045);  /* 26px minor grid */
  --grid-major: rgba(128,150,185,0.075);  /* 130px major grid */
  --border:        rgba(140,160,195,0.14);
  --border-strong: rgba(140,160,195,0.26);

  /* text */
  --text:       #E7ECF5;   /* primary */
  --text-2:     #95A1B8;   /* secondary / labels */
  --text-mute:  #5A6478;   /* tertiary / hints / disabled */

  /* brand — hazard amber (single attention color) */
  --amber:      #F5A623;
  --amber-hi:   #FFC766;   /* hover / lighter */
  --amber-dim:  rgba(245,166,35,0.16);  /* fills, active nav bg, focus ring */
  --amber-line: rgba(245,166,35,0.40);  /* dashed accents, badges */

  /* signal cyan — secondary data line, links, secondary metrics */
  --cyan:       #25D3EE;
  --cyan-dim:   rgba(37,211,238,0.14);

  /* semantics (reserved — never used as brand decoration) */
  --pass:       #34D399;   /* PASS / safe / positive delta */
  --fail:       #FF5C5C;   /* FAIL / collision / negative delta */
  --warn:       #F5A623;   /* caution (== amber by design) */
  --info:       #25D3EE;   /* == cyan */

  /* misc */
  --tick:       rgba(149,161,184,0.55); /* default corner crop-marks */
  --focus:      rgba(245,166,35,0.55);  /* keyboard focus ring */
  --shadow:     0 18px 50px -24px rgba(0,0,0,0.85);
  --scrim:      rgba(7,9,12,0.72);       /* sticky bar backdrop */
}
```

### 3.2 Light theme (blueprint paper)

Light mode is **not** "white SaaS." It is technical blueprint paper: cool off-white, the same grid + corner-ticks, amber/cyan darkened for AA contrast.

```css
[data-theme="light"]{
  --bg-base:    #EEF1F6;
  --bg-sunken:  #E3E8F0;
  --bg-panel:   #FFFFFF;
  --bg-elev:    #FFFFFF;
  --bg-inset:   #F3F5F9;

  --grid-line:  rgba(28,46,82,0.05);
  --grid-major: rgba(28,46,82,0.08);
  --border:        rgba(20,34,64,0.13);
  --border-strong: rgba(20,34,64,0.24);

  --text:       #0D1322;
  --text-2:     #46526B;
  --text-mute:  #8590A4;

  --amber:      #C97A06;   /* darkened for contrast on light */
  --amber-hi:   #E8920E;
  --amber-dim:  rgba(232,146,14,0.14);
  --amber-line: rgba(201,122,6,0.45);

  --cyan:       #0C8FA8;
  --cyan-dim:   rgba(12,143,168,0.12);

  --pass:       #0E9F6E;
  --fail:       #E5484D;
  --warn:       #C97A06;
  --info:       #0C8FA8;

  --tick:       rgba(70,82,107,0.5);
  --focus:      rgba(201,122,6,0.5);
  --shadow:     0 18px 44px -26px rgba(20,34,64,0.4);
  --scrim:      rgba(238,241,246,0.78);
}
```

### 3.3 Color usage rules

- **Amber** = the live/active/primary signal only: primary button, active nav item, composite metric, "live" panel corner-ticks, the `//` in the wordmark, focus ring. Do **not** flood UI with amber.
- **Cyan** = secondary data + interaction: links, secondary chart line, secondary metric bars, secondary stats, "REC" indicators.
- **Pass/Fail** = verdict/semantic only (PASS/FAIL chips, collision flag, score deltas). Never used as a brand accent. Because `--warn === --amber`, never place an amber brand button immediately beside an amber caution state — disambiguate with a label.
- **Text hierarchy:** `--text` for values/headings, `--text-2` for labels/body, `--text-mute` for hints/placeholders/disabled.
- **Contrast target:** body text ≥ 4.5:1, large/secondary ≥ 3:1, in **both** themes. Amber on `--bg-base` is for accents/large text, not long body copy.

---

## 4. Typography

Three families, each with one job. Loaded via Google Fonts (preconnect in `index.html`).

```
Display / headings / wordmark : 'Chakra Petch'   (400 500 600 700)  — squared HUD character
UI / body / labels            : 'Saira'          (300 400 500 600 700 800)
Numerals / data / code / mono : 'JetBrains Mono' (400 500 700)      — tabular, all numbers
```

```css
:root{
  --ff-disp:'Chakra Petch', sans-serif;
  --ff-ui:'Saira', system-ui, sans-serif;
  --ff-mono:'JetBrains Mono', ui-monospace, monospace;
}
```

### 4.1 Type roles & scale

| Role | Family | Size | Weight | Tracking | Notes |
|------|--------|------|--------|----------|-------|
| Hero display | Chakra Petch | `clamp(40px,5.2vw,68px)` | 700 | -0.01em | line-height .98 |
| Page title (h1) | Chakra Petch | 26px | 700 | .02em | dashboard header |
| Panel/section title | Chakra Petch | 20px | 600 | .04em | |
| HUD section label (h2) | Chakra Petch | 15px | 600 | .22em UPPER | `01 / OVERVIEW` style |
| Body | Saira | 15px | 400 | normal | |
| Lead paragraph | Saira | 17px | 300 | normal | hero / aside intros |
| Small / secondary | Saira | 13px | 400 | normal | |
| **Mono micro-label** | JetBrains Mono | 10.5px | 400 | .22em UPPER | the signature label style |
| Form field label | JetBrains Mono | 10px | 400 | .18em UPPER | |
| Big metric numeral | JetBrains Mono | 34px | 700 | -0.01em | dashboard metric panels |
| Gauge numeral | JetBrains Mono | 46px | 700 | -0.01em | hero composite gauge |
| Table data | JetBrains Mono | 12px | 400/600 | normal | values 600, labels 400 |

### 4.2 Numerals rule (hard)

**Every number a user reads is JetBrains Mono with `font-feature-settings:'tnum' 1,'zero' 1;`** — scores, counts, seeds, timestamps, credits, latency, money, table cells, axis ticks. Reusable `.num` class. No exceptions. This is the core identity device.

### 4.3 Mono micro-label

The recurring label treatment (`.mono-label`): JetBrains Mono, 10.5px, `letter-spacing:.22em`, `text-transform:uppercase`, color `--text-mute` (or `--text-2` when prominent). Used for section labels, panel captions, telemetry keys, status text.

---

## 5. Spacing, grid, radius, borders, motion

### 5.1 Spacing scale (keep existing token names)

`--space-1:.25rem` `2:.5` `3:.75` `4:1` `5:1.25` `6:1.5` `8:2` `10:2.5` `12:3` `16:4` `20:5` (rem). Default panel padding `16–22px`. Section vertical rhythm `46px`. Gap between cards `14px`.

### 5.2 Layout grid & structural backdrop

- App max content width: **1280px**, centered, `0 24px` gutters.
- **Structural grid backdrop** is a fixed, non-interactive layer on the app background: minor lines every **26px**, major lines every **130px**, drawn with `--grid-line` / `--grid-major` via layered `linear-gradient`s. Plus two restrained corner radial glows (amber top-right, cyan bottom-left) at very low alpha. This is global atmosphere; it must never reduce text contrast.
- Dashboard shell grid: `230px` sidebar + fluid main.

### 5.3 Radius

```css
--radius-sm:2px; --radius-md:3px; --radius-lg:4px;  /* 4px is the MAX */
```
Default everything to `--radius-md` (3px). Pills/circles only for status dots, avatars, the gauge. **No `border-radius` > 4px anywhere** except intrinsic circles.

### 5.4 Borders & corner crop-marks

- Standard separators/panel edges: `1px solid var(--border)`. Emphasis edges: `--border-strong`.
- **Corner crop-marks** are the panel signature: 9px L-shaped marks (2px) at the top-left and bottom-right of every `.panel`, color `--tick`. On a "live/active/featured" panel (`.panel--live`) the marks are `--amber`. Implemented via `::before`/`::after`. Use them; they are how a card reads as an instrument frame.

### 5.5 Elevation

Depth via surface tone + border, not shadow. Order dark→light: `--bg-sunken < --bg-base < --bg-inset < --bg-panel < --bg-elev`. `--shadow` is reserved for genuinely floating layers only (dropdowns, modals, toasts).

### 5.6 Motion

```css
--t-fast:150ms; --t-base:200ms; --t-slow:350ms;
--ease:cubic-bezier(.2,.7,.2,1);
```
- Theme switch: `background`/`color`/`border-color` transition `--t-slow`.
- Hover/focus: `--t-fast`–`--t-base`.
- Allowed motion: staggered hero reveal on load (opacity+translateY, `animation-delay` steps of 80–100ms), gauge stroke-fill animation, number count-up on first paint, sparkline draw, nav/hover transitions, the HUD live-dot blink (2s), and the **ambient corner-glow breathe** — the two background radial-glow layers (amber TR on `body::after`, cyan BL on `#root::before`) drift opacity + a few-% scale/translate on long, out-of-phase loops (~13s / ~17s, `ease-in-out`). Background-only, very low alpha, must never pull focus from data.
- **Banned motion:** float/levitate loops, glow-pulse on cards/buttons/interactive elements (the ambient *background* glow above is the only sanctioned glow animation), slow-spin orbs, parallax star fields as primary decor (the landing 3D element is redesigned per §11.1, not removed wholesale, but stays subtle and instrument-like).
- **`@media (prefers-reduced-motion: reduce)`**: disable count-up, gauge animation, sparkline redraw loops, blink; render final state instantly. Mandatory.

---

## 6. Signature visual devices (the "Mission Control kit")

These recurring elements make the language identifiable. Reuse them; do not invent parallel patterns.

1. **HUD status bar** — sticky top strip, 38px, `--scrim` + blur, mono 11px. Contents: wordmark · live status (`● SYSTEM NOMINAL`) · spacer · `SEED 42` · `BUILD <hash>` · UTC clock · `⌘K` hint · theme toggle. Present on app (authed) surfaces.
2. **Structural grid backdrop** — §5.2.
3. **Panel + corner crop-marks** — §5.4. The base container for everything.
4. **Section indices** — headings prefixed `01 /`, `02 /` in amber mono; nav items numbered `01…07`.
5. **Mono micro-labels** — §4.3.
6. **Reticle gauge** — circular SVG progress ring with 4 cardinal tick marks + crosshair, big mono numeral centered, mono label beneath. Used for composite/headline scores.
7. **Sparkline / line chart on grid** — thin lines (amber primary, cyan secondary), square 4px data markers, horizontal grid rules, optional 8%-alpha area fill under the primary line.
8. **Status chips** — rectangular (radius 3px), 1px colored border, uppercase mono 9.5px: `PASS` (pass), `FAIL` (fail), plus `QUEUED`/`RUNNING`/`DONE` variants (§9.9).
9. **Live dot** — small circle with matching box-shadow + 2s blink for "live/online/recording."
10. **Spec strip** — bordered row of `value + mono-label` cells separated by 1px dividers (hero stats, KPI rows).

---

## 7. Iconography

- **No emoji anywhere in the product UI.** Replace all current emoji (📊🗺️🏁🤖⚙️🛡️⚡💥✅ etc.).
- Single custom **inline-SVG icon set** in `src/components/common/Icon.jsx`: stroke-based, `stroke-width:1.5`, `currentColor`, 18–20px, square/sharp joints (no rounded line-caps where avoidable), 24×24 viewBox.
- Required icons (min set): `overview` (grid/gauge), `scenarios` (route/map-pin), `runs` (flag), `models` (cube), `batches` (layers/stack), `compare` (columns), `settings` (sliders), `billing` (card), `search`, `key`, `upload`, `download`, `play` (launch), `refresh`, `power` (logout), `close`, `check`, `warning` (triangle), `chevron-down/right`, `external`, `copy`. Add to the set (and list it here) when a new one is needed.
- Decorative HUD glyphs (`◆`, `//`, `●`, `▲`/`▼` deltas) are CSS/text, not the icon set.
- No third-party icon library dependency (keeps bundle lean + style exact).

---

## 8. Theme system

- Source of truth: `data-theme` attribute on `<html>` ∈ {`dark`,`light`}. **Default `dark`.**
- Persisted to `localStorage` key **`orion-theme`**. (This is a UI preference, explicitly exempt from the JWT-in-localStorage rule of CLAUDE.md §9 — never store auth/PII here, theme only.)
- **No-FOUC:** a tiny blocking inline script in `index.html` sets `data-theme` from `localStorage` (fallback `dark`) **before** first paint.
- React access via `ThemeProvider` (`src/theme/ThemeContext.jsx`) exposing `{ theme, toggleTheme, setTheme }`; `useTheme()` hook. The HUD/nav `ThemeToggle` is the only control.
- New-visitor default is dark; we do **not** auto-follow `prefers-color-scheme` (dark is the brand default), but we **do** honor `prefers-reduced-motion`.
- **Charts must re-read CSS variables on theme change** (Recharts colors are passed from JS — recompute from `getComputedStyle` on theme toggle; see §12).

---

## 9. Component library

All components live in `orion-frontend/src/components/...`, CSS co-located (`Component.jsx` + `Component.css`), no CSS modules, no Tailwind (CLAUDE.md §9). Shared primitives may use global utility classes defined in `index.css`.

### 9.1 Button (`.btn`)
Chakra Petch 600, 12.5px, `.14em` uppercase, radius 3px, padding `12px 22px`.
- `.btn-primary`: bg `--amber`, text `#0A0C10`; hover `--amber-hi` + amber glow + `translateY(-1px)`.
- `.btn-ghost`: transparent, `--border-strong`; hover border/text `--cyan`.
- `.btn-danger`: transparent, border/text `--fail`; hover fills `--fail`.
- `.btn-sm`: 11px / `8px 14px`. Disabled: `opacity:.45; cursor:not-allowed`. Trailing arrow `→` in mono.

### 9.2 Input / select / textarea (`.field`)
Label = form-field mono label (§4.1). Control: bg `--bg-inset`, 1px `--border`, radius 3px, JetBrains Mono 14px, padding `12px 14px`. Focus: border `--amber` + `0 0 0 3px var(--amber-dim)`. Placeholder `--text-mute`. Error state: border `--fail` + helper text `--fail`. Selects use a custom chevron icon.

### 9.3 Panel (`.panel`)
The base surface. bg `--bg-panel`, 1px `--border`, radius 3px, corner crop-marks (§5.4). `.panel--live` = amber crop-marks for the active/featured panel. Hover for interactive panels: border → `--border-strong` (no lift, no glow).

### 9.4 Metric panel
Panel containing: top row (`.mono-label` + delta `▲/▼ n` colored pass/fail) · big mono numeral (composite = amber, others = `--text`) · thin progress bar (track `--bg-inset`, fill amber for composite else cyan). Composite metric uses `.panel--live`.

### 9.5 Reticle gauge
SVG per §6.6. Ring track `--bg-inset`, progress stroke `--amber` (`stroke-linecap:butt`), 4 cardinal ticks `--tick`. Center: mono numeral + mono label. Animated fill on mount (skip under reduced-motion).

### 9.6 Sidebar nav
`230px`, bg `--bg-sunken`, right border. Brand row (mark + `ORION`). Items: numbered (`01…`), icon + uppercase mono 12px label, `2px` transparent left-border. Hover: `--bg-inset` + `--text`. Active: `--amber` text + amber left-border + `--amber-dim` bg. Footer: credits gauge (mono value cyan + mini bar) + user chip (amber square avatar w/ initial + name/email mono).

### 9.7 Table (`.data-table`)
Full-width, collapsed borders, JetBrains Mono 12px. `th`: mono 9.5px `.14em` uppercase `--text-mute`, bottom 1px border. `td`: 11px padding, 1px row border, `--text-2`; ID cells `--cyan`, model/name cells `--text`, score cells `--text` 600. Row hover `--bg-inset`. Empty state row spans all columns, centered `--text-mute`.

### 9.8 Charts
Recharts only (CLAUDE.md §9). Theme per §12: grid `--border`, axes `--text-mute` mono 11px, primary series amber, secondary cyan, tooltip bg `--bg-elev` + 1px `--border` + mono. Line `strokeWidth:2`, square dots or none, optional faint area fill. Radar: grid `--border`, single amber series at low fill. Bars: amber/cyan, `radius:[2,2,0,0]`.

### 9.9 Status chip (`.chip`)
Radius 3px, 1px border, mono 9.5px `.12em` uppercase, transparent bg, colored border+text. Variants: `pass`(--pass) `fail`(--fail) `queued`(--text-mute) `running`(--amber) `done`(--cyan) `error`(--fail).

### 9.10 Modal / dialog
Overlay `--scrim`. Panel `--bg-elev` + `--shadow` + crop-marks. Mono title-bar caption + close icon. Sharp corners. Focus-trapped, `Esc` closes, returns focus to trigger.

### 9.11 Toast / inline alert (`AlertBanner`)
Left 2px accent border colored by severity (info=cyan, warn/caution=amber, error=fail, success=pass), bg `--bg-panel`, mono label + body. Toasts top-right, stack, auto-dismiss (pausable on hover); inline alerts inline.

### 9.12 Empty / loading / error states (every data view MUST define all three)
- **Empty:** bordered panel, centered mono-label + one-line `--text-mute` hint + optional primary action.
- **Loading:** skeleton blocks (bg `--bg-inset`, subtle shimmer respecting reduced-motion) matching final layout — not a spinner-only screen. A thin amber top progress bar is allowed for route/data loads.
- **Error:** panel with `--fail` 2px left border, mono `ERROR` label, message, retry button.

### 9.13 Tabs / segmented control
Mono uppercase labels, 2px bottom-border indicator amber on active, `--text-2`→`--text` on hover.

### 9.14 Badge / KPI cell
Spec-strip cell (§6.10): mono value (cyan small unit) + mono micro-label beneath, 1px dividers between cells.

---

## 10. Accessibility & responsive

- **Contrast** per §3.3 in both themes; verify amber/cyan text sizes meet ratio.
- **Focus:** visible ring `0 0 0 3px var(--focus)` on all interactive elements; never remove outlines without replacement. Logical tab order. Skip-to-content link on app shell.
- **Keyboard:** modals trap + `Esc`; menus arrow-navigable; all actions reachable without a mouse.
- **ARIA/semantics:** real `<button>`/`<a>`/`<table>`/`<nav>`/`<main>`; `aria-label` on icon-only buttons; live regions for streaming telemetry/toasts; gauges expose `role="img"` + `aria-label` with the value.
- **Reduced motion:** §5.6 — mandatory.
- **Breakpoints:** `≥1280` full · `900–1279` charts/auth collapse to 1 col, metrics → 2-up · `<900` sidebar collapses to an icon rail or HUD menu, metrics 2-up, tables horizontally scroll within their panel. No content is unreachable on mobile.
- **Density:** desktop-first (this is a pro tool) but never broken on tablet/phone.

---

## 11. Page-by-page specifications

Routes today: `/` `/login` `/signup` `/reset-password` `/dashboard/*` `/simulation/:runId`. Sub-pages exist as files but most are unwired (dashboard switches sections via internal `view` state with "coming soon" placeholders). **This redesign restyles every page/component file so it conforms whether or not it is currently routed. Wiring/new features are out of scope unless explicitly requested.**

### 11.0 App shell (authed)
HUD status bar (§6.1, includes ThemeToggle) → below it the page surface. Dashboard pages additionally render the sidebar (§9.6). Global grid backdrop + footer system line (`ORION//AREP · DETERMINISTIC dt=0.02s · BUILD <hash> · © 2026 BEAMHASH`).

### 11.1 Landing (`/`) — `LandingPage`, `Navbar`, `landing/Hero`, `FeatureCards`, `StatsSection`, `Footer`
- **Navbar:** transparent over hero → `--scrim`+blur on scroll. Wordmark left; links (`Platform`, `Scenarios`, `Docs`) center/right mono uppercase; `Sign in` ghost + `Start Evaluating` primary; ThemeToggle.
- **Hero:** two-column. Left: amber-bordered eyebrow badge, Chakra Petch display headline ("Robustness, **measured.** not guessed." — amber emphasis + outline-stroke treatment), Saira 300 lead, primary+ghost CTAs, spec strip (`50Hz`, `0.02s dt`, `6` classes, `4` axes). Right: **live instrument cluster** — reticle composite gauge + cyan sparkline + telemetry readout grid in a `--panel--live`. The existing R3F starfield/constellation is **replaced** by this instrument cluster (or, if a 3D element is kept, it becomes a subtle wireframe road/trajectory in carbon+amber — no purple, no glow orbs). Staggered load reveal.
- **FeatureCards:** grid of panels, each: icon (§7) + Chakra Petch title + Saira body + mono index. Crop-marks. No hover-lift glow — border-strong on hover only.
- **StatsSection:** spec-strip / big mono numerals on grid backdrop (e.g. determinism, scenario count, metric axes).
- **Footer:** system-line style, mono, columns of links, build hash, © .

### 11.2 Auth (`/login`, `/signup`, `/reset-password`) — `LoginForm`, `SignupForm`, `ResetPasswordPage`, `AuthForms.css`
- Two-column instrument frame (sample §02): left **aside panel** (mono `ACCESS CONTROL` label, Chakra Petch headline, short copy, telemetry rows: SESSION/SCOPE/RATE LIMIT/STATUS), right **form card** (`.panel--live`).
- **Login:** email + password (mono inputs, mono labels), "Keep session" + "Forgot password?" (cyan link), amber `Authenticate →`, footer "Request access →". Inline forgot-password panel fades in within the card (preserve existing behavior + anti-enumeration success message). Errors via §9.12 error style.
- **Signup:** same frame; username/email/password/confirm; client validation in `--fail` style.
- **Reset:** reads `?token=`; no token → error panel; valid → new+confirm password (min 6, must match) → success state replaces form with `Go to Login`.

### 11.3 Dashboard shell + Overview (`/dashboard`) — `DashboardPage`, real `Sidebar`
- Sidebar (§9.6, sections: Overview, Scenarios, Runs, Models, Batches, Compare, Settings — numbered; Billing if enabled). Main: page header (Chakra Petch h1 + mono sub `N RUNS · ORG=… · status`) + actions (`↻ Refresh` ghost, `▶ Launch Run` primary).
- **Overview:** Launch panel (scenario/model/seed/tick inputs → `▶ Launch`), 5 metric panels (Composite=amber/live, Safety/Compliance/Stability/Reactivity=cyan), charts row (Run History line + Metric Breakdown radar/bars), Recent Runs table (§9.7) with PASS/FAIL chips. Replace all emoji metric icons with §7 icons. Define empty/loading/error states (§9.12).
- Section views currently "coming soon" → render as styled empty-state panels (§9.12) until wired.

### 11.4 Section/feature pages (restyle to spec; wiring out of scope)
- **Scenarios:** filterable list/grid of scenario panels (category chip `LON/LAT/INT/VRU/EMG/MLT`, name, mono ID, params) → detail.
- **Runs:** full runs table (§9.7) + filters; row → run detail.
- **Models (`ModelsPage`, `ModelCard`, `ModelUploadForm`):** model panels (name, type built-in/uploaded/docker, mono id, created); upload form (multipart) + register-Docker form in instrument-frame card.
- **Batches (`BatchPage`):** batch list + live progress (queued/running/completed/failed counts as mono numerals + thin progress bar + status chip), composite mean / collision rate readouts.
- **Compare (`ComparePage`, `ComparisonTable`):** side-by-side model columns, mono values, win/loss deltas (pass/fail colored).
- **Search (`SearchPage`):** adversarial-search UI — instrument form + results table.
- **Settings (`SettingsPage`):** grouped instrument panels (Profile, Org, API Keys w/ `key` icon + copy + revoke, Theme). Theme control mirrors the HUD toggle.
- **Billing (`BillingPage`, `PlanCard`, `UsageBar`):** behind `billing_enabled`. Plan panels (mono price), `UsageBar` (credits used vs total, cyan fill, mono numerals).
- **Dashboard analytics components:** `ScoreCard` (metric-panel pattern), `ScoreDistribution` (histogram bars), `RegressionChart` (line on grid), `FailureClusterPanel` (clustered failures list/scatter), `SmartAlerts` (alert-banner stack §9.11) — all re-themed per §9.8.

### 11.5 Simulation viewer (`/simulation/:runId`) — `SimulationViewer`, `PlaybackControls`, overlays
- R3F scene re-themed: carbon background matching `--bg-base`, road/lane lines in `--border-strong`/cyan, ego vehicle amber, NPCs neutral, **TTC warning zones** in `--fail` gradient, trajectory trace cyan→amber.
- **HUD overlay** (the showcase of this language): top status strip (run id, scenario, sim time, `REC ●`), left/right telemetry panels (speed, g-force, min TTC, collision flag) as mono readouts + reticle gauges, bottom metric bars + verdict chip, `← Dashboard` ghost back button. All glassless instrument panels with crop-marks.
- `PlaybackControls`: transport bar (play/pause/scrub/speed) mono, amber active. Latency readout from `latencyRef` in mono.
- Overlay components (`TrajectoryTrace`, `TTCWarningZone`, `NPCIntentOverlay`) recolored to the palette.

### 11.6 System pages
- **404 (`NotFoundPage`, new):** instrument panel — big mono `404`, `SIGNAL LOST` mono-label, link home. Replaces the silent `Navigate to "/"` catch-all (route stays as fallback only).
- **ErrorBoundary (new, `common/ErrorBoundary.jsx`):** wraps the app; renders §9.12 error panel with reset, never a white screen.
- **Loading screen:** the `ProtectedRoute` loading fallback uses skeleton/HUD style, not bare "Loading…".

---

## 12. Recharts theming recipe

Charts get colors from JS, so they must recompute on theme change. Pattern:

```js
const readVar = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
// subscribe to theme via useTheme(); recompute palette in a useMemo keyed on `theme`.
const palette = { amber: readVar('--amber'), cyan: readVar('--cyan'),
  grid: readVar('--border'), axis: readVar('--text-mute'),
  tooltipBg: readVar('--bg-elev'), border: readVar('--border') };
```
- `CartesianGrid stroke={palette.grid}`; axes `stroke={palette.axis}` + `fontFamily:var(--ff-mono)` 11px.
- Primary series amber, secondary cyan; `Tooltip` `contentStyle={{background:palette.tooltipBg,border:'1px solid '+palette.border,borderRadius:3,fontFamily:'var(--ff-mono)'}}`.
- Never hardcode `#6c63ff` or any hex in chart props again.

---

## 13. CSS / file architecture

- **Tokens** live in `index.css` under `[data-theme="dark"]` / `[data-theme="light"]` + `:root` (font/space/radius/motion). One source of truth.
- Global utilities in `index.css`: `.btn*`, `.field`, `.panel`/`.panel--live`, `.data-table`, `.chip*`, `.mono-label`, `.num`, `.spec-strip`, grid-backdrop, animations.
- Per-component styling co-located (`Component.css`), referencing tokens only. **No hardcoded colors/sizes** — token or scale variable always.
- During migration only, a clearly-commented legacy-alias block may map old token names (`--accent-primary`→`--amber`, `--bg-primary`→`--bg-base`, `--text-primary`→`--text`, `.glass-card`→panel styles) so un-migrated files keep rendering. The alias block is deleted in the final migration phase (`ORION_UI_REDESIGN_PLAN.md` Phase I). New code must use canonical names only.

---

## 14. Governance — the rules of this doc

1. **This doc + `design/sample-mission-control.html` are the source of truth** for all `orion-frontend/` visual work.
2. Frontend changes that introduce colors, fonts, radii, components, or page layouts **must** use the tokens/components/specs here. No ad-hoc styling.
3. **Out of scope = don't do it.** Don't add features, routes, libraries, or aesthetics not described here unless the user explicitly asks. (Reaffirms CLAUDE.md §9.)
4. New pattern needed → add it to this doc in the same change (with tokens + spec), then implement.
5. Banned list (§1) is permanent. If asked for something on it, surface the conflict before proceeding.
6. Honor existing hard rules (CLAUDE.md §9 & §12): all HTTP through `services/api.js`; auth token only in `AuthContext`; `orion-theme` localStorage key is the sole UI-pref exception; Recharts only; no Tailwind/CSS-modules; co-located CSS; no TypeScript yet.
