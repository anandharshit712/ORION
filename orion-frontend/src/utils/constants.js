// ORION — Frontend constants  [Phase 1]
// Single source of truth for tier names, score thresholds, and metric weights.
// These MUST stay in sync with the backend constants in arep/evaluation/.

// ── Subscription tiers ───────────────────────────────────────────────────

export const PLAN_TIERS = {
  free: {
    name: 'Free',
    monthlyCredits: 50,
    price: 0,
    currency: 'USD',
    maxConcurrentRuns: 1,
    scenarioAccess: ['LON'],
    features: ['50 runs/month', 'LON scenarios only', '1 concurrent run'],
  },
  starter: {
    name: 'Starter',
    monthlyCredits: 500,
    price: 49,
    currency: 'USD',
    maxConcurrentRuns: 3,
    scenarioAccess: ['LON', 'LAT', 'INT', 'VRU', 'EMG', 'MLT'],
    features: ['500 runs/month', 'All scenario categories', '3 concurrent runs'],
  },
  pro: {
    name: 'Pro',
    monthlyCredits: 3000,
    price: 199,
    currency: 'USD',
    maxConcurrentRuns: 10,
    scenarioAccess: ['LON', 'LAT', 'INT', 'VRU', 'EMG', 'MLT'],
    features: ['3,000 runs/month', 'Adversarial search', '10 concurrent runs', 'PDF reports'],
  },
  enterprise: {
    name: 'Enterprise',
    monthlyCredits: -1,        // unlimited
    price: null,               // custom
    maxConcurrentRuns: -1,     // unlimited
    scenarioAccess: ['LON', 'LAT', 'INT', 'VRU', 'EMG', 'MLT'],
    features: ['Unlimited runs', 'Priority support', 'SLA', 'Custom scenarios', 'SSO'],
  },
};

// ── Score thresholds ─────────────────────────────────────────────────────
// These mirror arep/evaluation/safety.py — keep in sync.

export const SCORE_THRESHOLDS = {
  pass: 0.80,                  // composite score >= this → PASS badge
  warn: 0.60,                  // composite score >= this → WARN badge
  // below warn → FAIL badge
};

export const TTC_THRESHOLDS = {
  safe: 10.0,                  // TTC >= 10s → full safety score
  critical: 2.0,               // TTC < 2s → critical flag
};

// ── Metric weights ────────────────────────────────────────────────────────
// MUST match CompositeEvaluator weights — never change independently.

export const METRIC_WEIGHTS = {
  safety: 0.50,
  compliance: 0.20,
  stability: 0.15,
  reactivity: 0.15,
};

// ── Regression thresholds ────────────────────────────────────────────────
// MUST match analysis/regression_detector.py

export const REGRESSION_THRESHOLDS = {
  composite: 0.05,             // 5% drop → regression
  safety: 0.10,                // 10% drop → regression
  collisionRate: 0.01,         // 1pp increase → regression
};

// ── Dashboard sections ───────────────────────────────────────────────────

export const DASHBOARD_SECTIONS = [
  { key: 'overview',  label: 'Overview',  icon: '⊞' },
  { key: 'runs',      label: 'Runs',      icon: '▶' },
  { key: 'models',    label: 'Models',    icon: '◈' },
  { key: 'scenarios', label: 'Scenarios', icon: '⚑' },
  { key: 'compare',   label: 'Compare',   icon: '⇔' },
  { key: 'search',    label: 'Adversarial Search', icon: '⚡', planRequired: 'pro' },
  { key: 'settings',  label: 'Settings',  icon: '⚙' },
  { key: 'billing',   label: 'Billing',   icon: '◎' },
];

// ── API base URL ──────────────────────────────────────────────────────────
// Vite proxy handles /api → localhost:8000 in dev.
// In production this should come from an environment variable.

export const API_BASE = import.meta.env.VITE_API_BASE || '';
