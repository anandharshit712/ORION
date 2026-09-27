// ORION — RunsSection
//
// The full runs table with filters (docs/UI_DESIGN.md §11.4, table per §9.7).
//
// Reads GET /results/runs — the stored, historical record. It used to read
// GET /api/runs/, which lists the *live* in-memory registry: empty after a
// restart, and never containing a finished batch run. A customer with 500
// completed runs was told "no runs recorded".
//
// A stored run therefore has no `status` (it is here because it finished) and
// an integer id (the one replay takes, unlike the live registry's strings).
// A run with no composite shows a dash rather than 0.0 — a zero reads as
// "scored badly" rather than "not scored".

import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../../services/api';
import { useApiData, asList } from '../../hooks/useApiData';
import Icon from '../common/Icon';
import DataStates from './DataStates';
import './RunsSection.css';


// Stored runs are finished by definition, so "queued/running" are not states
// this section can show. What a reviewer actually wants to filter to is the
// ones that went wrong.
const FILTERS = ['all', 'passed', 'collided'];

/** Percentage string, or an em dash when the run has not been scored yet. */
function score(value) {
  return typeof value === 'number' ? (value * 100).toFixed(1) : '—';
}

const PASS_COMPOSITE = 0.8;

function verdict(run) {
  // A stored run has no `status`: it is in the database because it finished.
  // A collision is a fail regardless of the composite — a model can be
  // uncomfortable and safe, not comfortable and crashing.
  if (run.collision_occurred) return 'fail';
  if (typeof run.composite_score !== 'number') return null;
  return run.composite_score >= PASS_COMPOSITE ? 'pass' : 'fail';
}

function bucket(run) {
  return run.collision_occurred ? 'collided' : 'passed';
}

export default function RunsSection() {
  const navigate = useNavigate();
  const [filter, setFilter] = useState('all');
  // Stored runs, not the live registry. `GET /api/runs/` lists what is
  // currently streaming and is empty after a restart, so this section told a
  // customer with a finished 500-run batch that they had no runs.
  const { data, loading, error, refresh } = useApiData(() => api.getStoredRuns(200), []);

  const runs = useMemo(() => asList(data, 'runs'), [data]);
  const shown = useMemo(
    () => (filter === 'all' ? runs : runs.filter((r) => bucket(r) === filter)),
    [runs, filter],
  );

  const counts = useMemo(() => {
    const out = { all: runs.length };
    for (const f of FILTERS.slice(1)) out[f] = runs.filter((r) => bucket(r) === f).length;
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
            Runs · /results/runs <span className="num">{shown.length}</span>
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
                      onClick={() => navigate(`/dashboard/runs/${id}`)}
                      title="Open the replay"
                    >
                      <td className="t-id">#{String(id).slice(0, 8)}</td>
                      {/* A stored run names its scenario `scenario_id`; the
                          live-run shape used `scenario_path`/`scenario_name`.
                          All three are read so this survives either. */}
                      <td
                        className="t-scenario"
                        title={r.scenario_id || r.scenario_path || r.scenario_name}
                      >
                        {String(
                          r.scenario_id || r.scenario_path || r.scenario_name || '—',
                        ).split('/').pop()}
                      </td>
                      <td className="t-model">{r.model_name || '—'}</td>
                      <td>
                        <span
                          className={`chip ${r.collision_occurred ? 'chip-fail' : 'chip-done'}`}
                        >
                          {r.termination_reason || 'completed'}
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
