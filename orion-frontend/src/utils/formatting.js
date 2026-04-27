// ORION — Formatting utilities  [Phase 1]
// Pure functions for formatting scores, dates, and credits in the UI.
// Keep these framework-free — no React imports.

/**
 * Format a score (0.0–1.0) as a percentage string.
 * e.g. formatScore(0.731) → "73.1%"
 */
export function formatScore(score) {
  if (score == null || isNaN(score)) return '—';
  return `${(score * 100).toFixed(1)}%`;
}

/**
 * Format a score as a 3-decimal number string.
 * e.g. formatScoreRaw(0.731) → "0.731"
 */
export function formatScoreRaw(score) {
  if (score == null || isNaN(score)) return '—';
  return score.toFixed(3);
}

/**
 * Return a CSS colour class based on a score threshold.
 * Used for colouring score cells green/amber/red.
 */
export function scoreColorClass(score) {
  if (score == null || isNaN(score)) return 'score-unknown';
  if (score >= 0.80) return 'score-pass';
  if (score >= 0.60) return 'score-warn';
  return 'score-fail';
}

/**
 * Format a delta (positive = improvement, negative = regression).
 * e.g. formatDelta(0.05) → "+5.0%" (green)
 *      formatDelta(-0.08) → "-8.0%" (red)
 */
export function formatDelta(delta) {
  if (delta == null || isNaN(delta)) return '—';
  const pct = (delta * 100).toFixed(1);
  return delta >= 0 ? `+${pct}%` : `${pct}%`;
}

/**
 * Format a timestamp ISO string as a human-readable date.
 * e.g. "2026-04-26T14:30:00Z" → "Apr 26, 2026 14:30"
 */
export function formatDate(isoString) {
  if (!isoString) return '—';
  const d = new Date(isoString);
  return d.toLocaleString('en-GB', {
    day: 'numeric', month: 'short', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  });
}

/**
 * Format a relative time from now.
 * e.g. "2 minutes ago", "3 hours ago"
 */
export function formatRelativeTime(isoString) {
  if (!isoString) return '—';
  const diffMs = Date.now() - new Date(isoString).getTime();
  const diffSec = Math.floor(diffMs / 1000);
  if (diffSec < 60) return `${diffSec}s ago`;
  if (diffSec < 3600) return `${Math.floor(diffSec / 60)}m ago`;
  if (diffSec < 86400) return `${Math.floor(diffSec / 3600)}h ago`;
  return `${Math.floor(diffSec / 86400)}d ago`;
}

/**
 * Format run credit count with appropriate label.
 * e.g. formatCredits(50) → "50 credits"
 *      formatCredits(-1) → "Unlimited"
 */
export function formatCredits(credits) {
  if (credits === -1) return 'Unlimited';
  if (credits == null) return '—';
  return `${credits.toLocaleString()} credit${credits === 1 ? '' : 's'}`;
}

/**
 * Format a duration in seconds as a readable string.
 * e.g. formatDuration(125.4) → "2m 5s"
 */
export function formatDuration(seconds) {
  if (seconds == null || isNaN(seconds)) return '—';
  const s = Math.round(seconds);
  if (s < 60) return `${s}s`;
  return `${Math.floor(s / 60)}m ${s % 60}s`;
}
