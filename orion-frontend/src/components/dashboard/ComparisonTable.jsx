// ORION — ComparisonTable  [P2]
// Side-by-side model comparison (.data-table §9.7): model columns, mono values,
// win/loss deltas colored --pass/--fail. Data wiring tracked separately.

import './ComparisonTable.css';

const fmt = (x) => (typeof x === 'number' ? x.toFixed(1) : '—');

/**
 * ComparisonTable — metrics across models, side by side.
 *
 * Props (optional):
 *   models   [{ name, scores: { metricKey: number }, deltas?: { metricKey: number } }]
 *   metrics  [{ key, label }]  — rows to render
 *   title    string            — panel caption
 *
 * Each metric is one row; each model is one column. A delta (vs baseline) is
 * shown beneath the value, colored --pass (positive) / --fail (negative).
 */
export default function ComparisonTable({
  models,
  metrics = [
    { key: 'composite', label: 'Composite' },
    { key: 'safety', label: 'Safety' },
    { key: 'compliance', label: 'Compliance' },
    { key: 'stability', label: 'Stability' },
    { key: 'reactivity', label: 'Reactivity' },
  ],
  title = 'Model Comparison',
} = {}) {
  const hasData = Array.isArray(models) && models.length > 0;
  const colCount = hasData ? models.length + 1 : 2;

  return (
    <div className="panel comparison-table">
      <div className="comparison-cap mono-label">{title}</div>
      <div className="comparison-wrap">
        <table className="data-table">
          <thead>
            <tr>
              <th>Metric</th>
              {hasData
                ? models.map((m, i) => <th key={m.name ?? i} className="cmp-col">{m.name}</th>)
                : <th>Model</th>}
            </tr>
          </thead>
          <tbody>
            {hasData ? (
              metrics.map((metric) => (
                <tr key={metric.key}>
                  <td className="cmp-metric">{metric.label}</td>
                  {models.map((m, i) => {
                    const val = m.scores?.[metric.key];
                    const delta = m.deltas?.[metric.key];
                    const hasDelta = typeof delta === 'number' && delta !== 0;
                    const up = hasDelta && delta > 0;
                    return (
                      <td key={m.name ?? i} className="cmp-cell">
                        <span className="cmp-val num">{fmt(val)}</span>
                        {hasDelta && (
                          <span className={`cmp-delta num ${up ? 'is-up' : 'is-down'}`}>
                            {up ? '▲' : '▼'} {Math.abs(delta).toFixed(1)}
                          </span>
                        )}
                      </td>
                    );
                  })}
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan={colCount} className="table-empty">
                  Select models to compare — results render here.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
