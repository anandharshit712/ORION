// ORION — UsageBar
// Credits-used-vs-total horizontal bar (ORION_UI_DESIGN.md §11.4): track --bg-inset,
// fill --cyan, mono .num labels. Presentational only — no data wiring.

import './UsageBar.css';

const fmtNum = (n) => (typeof n === 'number' ? n.toLocaleString() : '—');

/**
 * UsageBar
 *
 * Props:
 *   used    number — credits consumed
 *   total   number — total credits in the period
 *   label   string — mono micro-label (default 'Run Credits')
 *   unit    string — value unit suffix (optional)
 */
export default function UsageBar({ used = 0, total = 0, label = 'Run Credits', unit }) {
  const safeTotal = total > 0 ? total : 0;
  const pct = safeTotal > 0 ? Math.max(0, Math.min(100, (used / safeTotal) * 100)) : 0;
  // near-limit (>=90%) surfaces the single attention color
  const near = pct >= 90;

  return (
    <div className="usage-bar">
      <div className="usage-head">
        <span className="mono-label">{label}</span>
        <span className="usage-readout num">
          {fmtNum(used)} <span className="usage-sep">/</span> {fmtNum(safeTotal)}
          {unit && <span className="usage-unit"> {unit}</span>}
        </span>
      </div>
      <div
        className="usage-track"
        role="progressbar"
        aria-valuenow={Math.round(pct)}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={`${label}: ${fmtNum(used)} of ${fmtNum(safeTotal)} used`}
      >
        <i className={`usage-fill ${near ? 'is-near' : ''}`} style={{ width: `${pct}%` }} />
      </div>
      <div className="usage-foot num">{pct.toFixed(0)}% used</div>
    </div>
  );
}
