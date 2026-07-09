// ORION — BatchPage  [P1]
// Route: /dashboard/batches/:id
// Batch detail — live progress counts, thin progress bar, status chip,
// composite-mean / collision-rate readouts. Visual restyle to "Mission
// Control" (ORION_UI_DESIGN.md §11.4). useBatchStatus usage unchanged.

import React from 'react';
import { useParams } from 'react-router-dom';
import { useBatchStatus } from '../hooks/useBatchStatus';
import Icon from '../components/common/Icon';
import './BatchPage.css';

const fmtNum = (n) => (typeof n === 'number' ? n.toLocaleString() : '0');
const fmtPct = (x) => (typeof x === 'number' ? (x * 100).toFixed(1) : '—');

function statusChip(isDone, s) {
  if (!s) return { cls: 'chip-queued', label: 'Queued' };
  if (isDone) return (s.failed || 0) > 0
    ? { cls: 'chip-error', label: 'Completed · errors' }
    : { cls: 'chip-done', label: 'Completed' };
  if ((s.running || 0) > 0) return { cls: 'chip-running', label: 'Running' };
  return { cls: 'chip-queued', label: 'Queued' };
}

/**
 * BatchPage — async batch progress + aggregate readouts.
 */
export default function BatchPage() {
  const { id } = useParams();
  const { status, isDone, error, refresh } = useBatchStatus(id);

  const total = status?.total ?? 0;
  const completed = status?.complete ?? 0;
  const progressPct = total > 0 ? Math.min(100, (completed / total) * 100) : 0;
  const chip = statusChip(isDone, status);

  return (
    <div className="batch-page" id="batch-page">
      <header className="batch-head">
        <div>
          <h1>Batch</h1>
          <div className="batch-sub num" title={id}>
            {id ? `#${String(id).slice(0, 8)}` : 'NO BATCH'} · {fmtNum(total)} RUNS
          </div>
        </div>
        <div className="batch-actions">
          <span className={`chip ${chip.cls}`}>{chip.label}</span>
          <button className="btn btn-ghost btn-sm" onClick={refresh}>
            <Icon name="refresh" size={14} /> Refresh
          </button>
        </div>
      </header>

      {error && (
        <div className="panel batch-error">
          <span className="mono-label"><Icon name="warning" size={14} /> Error</span>
          <p>{error}</p>
          <button className="btn btn-ghost btn-sm" onClick={refresh}>Retry</button>
        </div>
      )}

      {!status && !error ? (
        <div className="panel batch-empty">
          <span className="mono-label">Awaiting batch status</span>
          <p>Progress streams here once the batch reports in. Data wiring is tracked separately.</p>
        </div>
      ) : (
        <>
          <div className="panel panel--live batch-progress">
            <div className="batch-progress-head">
              <span className="mono-label">Progress</span>
              <span className="batch-progress-pct num">{progressPct.toFixed(0)}%</span>
            </div>
            <div className="batch-track">
              <i style={{ width: `${progressPct}%` }} />
            </div>
            <div className="batch-counts">
              <div className="batch-count">
                <span className="batch-count-v num">{fmtNum(status?.queued)}</span>
                <span className="mono-label">Queued</span>
              </div>
              <div className="batch-count">
                <span className="batch-count-v num is-amber">{fmtNum(status?.running)}</span>
                <span className="mono-label">Running</span>
              </div>
              <div className="batch-count">
                <span className="batch-count-v num is-pass">{fmtNum(status?.complete)}</span>
                <span className="mono-label">Completed</span>
              </div>
              <div className="batch-count">
                <span className="batch-count-v num is-fail">{fmtNum(status?.failed)}</span>
                <span className="mono-label">Failed</span>
              </div>
            </div>
          </div>

          <div className="batch-readouts spec-strip">
            <div>
              <div className="v num">{fmtPct(status?.composite_mean)}<small> /100</small></div>
              <div className="k">Composite Mean</div>
            </div>
            <div>
              <div className="v num">{fmtPct(status?.collision_rate)}<small> %</small></div>
              <div className="k">Collision Rate</div>
            </div>
            <div>
              <div className="v num">{fmtNum(total)}</div>
              <div className="k">Total Runs</div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
