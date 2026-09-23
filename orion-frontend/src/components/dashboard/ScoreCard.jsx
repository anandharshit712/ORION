// ORION — ScoreCard  [P1]
// Single metric score card: metric-panel pattern (docs/UI_DESIGN.md §9.4, §11.4).
// Big mono value (amber for composite, else --text), optional ▲/▼ delta, thin progress bar.
// Visual styling per Mission Control; data wiring tracked separately.

import './ScoreCard.css';

/**
 * ScoreCard — single metric score card.
 *
 * Props (all optional; styled placeholder shown when absent):
 *   label    string  — metric name (mono micro-label)
 *   value    number  — score 0–100
 *   delta    number  — change vs baseline; sign drives ▲/▼ + pass/fail color
 *   accent   'amber' | 'cyan'  — bar/value accent ('amber' marks composite)
 *   live     boolean — render as the featured (.panel--live) variant
 *   unit     string  — optional unit suffix (e.g. '%')
 *
 * Phase 2.1 — the interval is what turns a number into evidence:
 *   ciLow / ciHigh  number  — 95% interval bounds, same scale as `value`
 *   n               number  — sample size behind the mean
 *   lowConfidence   boolean — sample too small for the interval to say much
 */
export default function ScoreCard({
  label = 'Composite',
  value,
  delta,
  accent = 'cyan',
  live = false,
  unit,
  ciLow,
  ciHigh,
  n,
  lowConfidence = false,
} = {}) {
  const hasValue = typeof value === 'number';
  const v = hasValue ? value : 0;
  const w = Math.max(0, Math.min(100, v));
  const isAmber = accent === 'amber';

  const hasDelta = typeof delta === 'number' && delta !== 0;
  const deltaUp = hasDelta && delta > 0;

  const hasInterval =
    hasValue && typeof ciLow === 'number' && typeof ciHigh === 'number' && ciHigh > ciLow;
  const halfWidth = hasInterval ? (ciHigh - ciLow) / 2 : 0;
  const ciLeft = hasInterval ? Math.max(0, Math.min(100, ciLow)) : 0;
  const ciWidth = hasInterval ? Math.max(0, Math.min(100, ciHigh) - ciLeft) : 0;

  return (
    <div className={`panel score-card ${live ? 'panel--live' : ''}`}>
      <div className="score-card-top">
        <span className="mono-label">{label}</span>
        {hasDelta && (
          <span className={`score-delta num ${deltaUp ? 'is-up' : 'is-down'}`}>
            {deltaUp ? '▲' : '▼'} {Math.abs(delta).toFixed(1)}
          </span>
        )}
      </div>

      {hasValue ? (
        <div className={`score-val num ${isAmber ? 'is-amber' : ''}`}>
          {v.toFixed(1)}
          {unit && <span className="score-unit num">{unit}</span>}
        </div>
      ) : (
        <div className="score-val score-val--empty num">—</div>
      )}

      {/* The interval, not a second decoration. A mean with no sample size or
          spread invites more confidence than the run count supports, which is
          exactly what 2.1 exists to stop. Rendered as +/- half-width because
          that is how a reviewer reads it. */}
      {hasInterval && (
        <div className={`score-ci num ${lowConfidence ? 'is-weak' : ''}`}>
          &plusmn;{halfWidth.toFixed(1)}
          <span className="score-ci-meta">
            95% CI{typeof n === 'number' ? ` · n=${n}` : ''}
          </span>
        </div>
      )}

      <div className="score-bar">
        {/* The interval drawn on the bar itself: the band is the range the mean
            could plausibly sit in, the tick is the estimate. */}
        {hasInterval && (
          <span
            className="score-bar-ci"
            style={{ left: `${ciLeft}%`, width: `${ciWidth}%` }}
            aria-hidden="true"
          />
        )}
        <i
          className={isAmber ? 'amber' : 'cyan'}
          style={{ '--p': w / 100 }}
        />
      </div>

      {lowConfidence && (
        <div className="score-weak mono-label" role="note">
          small sample — interval is wide
        </div>
      )}
    </div>
  );
}
