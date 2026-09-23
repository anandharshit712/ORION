// ORION — RunsSection
//
// The full runs table with filters (docs/UI_DESIGN.md §11.4, table per §9.7).
// Reads GET /api/runs/, the same endpoint the Overview summarises; this view is
// the unsummarised one.
//
// Score fields are only populated once status === "completed", so a running row
// shows dashes rather than 0.0 — a zero here would read as "scored badly".

import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../../services/api';
import { useApiData, asList } from '../../hooks/useApiData';
import Icon from '../common/Icon';
import DataStates from './DataStates';
import './RunsSection.css';

const STATUS_CHIP = {
  completed: 'chip-done',
  running: 'chip-running',
  queued: 'chip-queued',
  failed: 'chip-fail',
  cancelled: 'chip-queued',
};

const FILTERS = ['all', 'completed', 'running', 'failed'];

/** Percentage string, or an em dash when the run has not been scored yet. */
function score(value) {
  return typeof value === 'number' ? (value * 100).toFixed(1) : '—';
}

function verdict(run) {
  if (run.status !== 'completed') return null;
  if (run.collision_occurred) return 'fail';
  return (run.composite_score || 0) >= 0.8 ? 'pass' : 'fail';
}

export default function RunsSection() {
  const navigate = useNavigate();
  const [filter, setFilter] = useState('all');
  const { data, loading, error, refresh } = useApiData(() => api.getRuns(200), []);

  const runs = useMemo(() => asList(data, 'runs'), [data]);
  const shown = useMemo(
    () => (filter === 'all' ? runs : runs.filter((r) => r.status === filter)),
    [runs, filter],
  );

  const counts = useMemo(() => {
    const out = { all: runs.length };
    for (const f of FILTERS.slice(1)) out[f] = runs.filter((r) => r.status === f).length;
    return out;
  }, [runs]);

  return (
    <section className="runs-section">
      <div className="section-bar">
        <div className="seg-control" role="tablist" aria-label="Filter runs by status">
          {FILTERS.map((f) => (
            <button
              key={f}
              type="button"
              role="tab"
              aria-selected={filter === f}
              className={`seg-btn ${filter === f ? 'is-active' : ''}`}
              onClick={() => setFilter(f)}
            >
              {f} <span className="num seg-count">{counts[f] ?? 0}</span>
            </button>
          ))}
        </div>
        <button type="button" className="btn btn-ghost btn-sm" onClick={refresh} disabled={loading}>
          <Icon name="refresh" size={14} /> Refresh
        </button>
      </div>

      <DataStates
        loading={loading}
        error={error}
        isEmpty={shown.length === 0}
        onRetry={refresh}
        loadingRows={8}
        loadingLabel="Loading runs"
        emptyLabel={filter === 'all' ? 'No runs recorded' : `No ${filter} runs`}
        emptyHint={
          filter === 'all'
            ? 'Launch an evaluation from the Overview to see results here.'
            : 'Try a different status filter.'
        }
      >
        <div className="panel table-card">
          <div className="table-cap mono-label">
            Runs · /api/runs <span className="num">{shown.length}</span>
          </div>
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Scenario</th>
                  <th>Model</th>
                  <th>Status</th>
                  <th>Composite</th>
                  <th>Safety</th>
                  <th>Comply</th>
                  <th>Stable</th>
                  <th>React</th>
                  <th>Verdict</th>
                </tr>
              </thead>
              <tbody>
                {shown.map((r) => {
                  const id = r.run_id || r.id || '';
                  const v = verdict(r);
                  return (
                    <tr
                      key={id}
                      className="is-clickable"
                      onClick={() => navigate(`/simulation/${id}`)}
                      title="Open in the simulation viewer"
                    >
                      <td className="t-id">#{String(id).slice(0, 8)}</td>
                      <td className="t-scenario" title={r.scenario_path || r.scenario_name}>
                        {String(r.scenario_path || r.scenario_name || '—').split('/').pop()}
                      </td>
                      <td className="t-model">{r.model_name || '—'}</td>
                      <td>
                        <span className={`chip ${STATUS_CHIP[r.status] || 'chip-queued'}`}>
                          {r.status || 'unknown'}
                        </span>
                      </td>
                      <td className="t-score num">{score(r.composite_score)}</td>
                      <td className="num">{score(r.safety_score)}</td>
                      <td className="num">{score(r.compliance_score)}</td>
                      <td className="num">{score(r.stability_score)}</td>
                      <td className="num">{score(r.reactivity_score)}</td>
                      <td>{v ? <span className={`chip chip-${v}`}>{v}</span> : <span className="t-pending">—</span>}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      </DataStates>
    </section>
  );
}
