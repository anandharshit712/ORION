// ORION — FailureClusterPanel  [P2]
// Clustered failure conditions: each row = count + label + severity chip (§9.4/§9.9).
// Styled to Mission Control; data wiring tracked separately.

import './FailureClusterPanel.css';

// Map a cluster severity to a status-chip variant (§9.9).
const CHIP_BY_SEVERITY = {
  critical: 'fail',
  high: 'fail',
  medium: 'running', // amber caution
  low: 'done',       // cyan informational
};

/**
 * FailureClusterPanel — list of failure clusters.
 *
 * Props (optional):
 *   clusters  [{ id?, label, count, rate?, severity? }] — placeholder when absent
 *   title     string  — panel caption
 */
export default function FailureClusterPanel({
  clusters,
  title = 'Failure Clusters',
} = {}) {
  const hasData = Array.isArray(clusters) && clusters.length > 0;

  return (
    <div className="panel failure-cluster">
      <div className="failure-cap mono-label">{title}</div>

      {hasData ? (
        <ul className="failure-list">
          {clusters.map((c, i) => {
            const chip = CHIP_BY_SEVERITY[c.severity] || 'queued';
            return (
              <li className="failure-row" key={c.id ?? i}>
                <span className="failure-count num">{c.count ?? 0}</span>
                <span className="failure-meta">
                  <span className="failure-label">{c.label}</span>
                  {typeof c.rate === 'number' && (
                    <span className="failure-rate num">{(c.rate * 100).toFixed(1)}% of runs</span>
                  )}
                </span>
                <span className={`chip chip-${chip}`}>{c.severity || 'cluster'}</span>
              </li>
            );
          })}
        </ul>
      ) : (
        <div className="failure-empty">
          <span className="mono-label">No failure clusters</span>
          <p>Recurring fault conditions group here once failing runs are recorded.</p>
        </div>
      )}
    </div>
  );
}
