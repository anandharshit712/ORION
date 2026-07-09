// ORION — ScoreCard  [P1]
// Single metric score card: metric-panel pattern (ORION_UI_DESIGN.md §9.4, §11.4).
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
 */
export default function ScoreCard({
  label = 'Composite',
  value,
  delta,
  accent = 'cyan',
  live = false,
  unit,
} = {}) {
  const hasValue = typeof value === 'number';
  const v = hasValue ? value : 0;
  const w = Math.max(0, Math.min(100, v));
  const isAmber = accent === 'amber';

  const hasDelta = typeof delta === 'number' && delta !== 0;
  const deltaUp = hasDelta && delta > 0;

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

      <div className="score-bar">
        <i className={isAmber ? 'amber' : 'cyan'} style={{ width: `${w}%` }} />
      </div>
    </div>
  );
}
