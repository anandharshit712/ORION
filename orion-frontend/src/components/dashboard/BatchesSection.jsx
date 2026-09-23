// ORION — BatchesSection
//
// Batch list with live progress (docs/UI_DESIGN.md §11.4): queued/running/
// completed/failed as mono numerals, a thin progress bar, a status chip, and
// the composite mean / collision rate readouts.
//
// Reads GET /jobs/ — mounted at the root, not under /api (CLAUDE.md §8).
// A batch still running is re-polled; a finished one is not, because polling a
// terminal row forever is how a dashboard quietly becomes a load generator.

import { useEffect, useMemo } from 'react';
import { api } from '../../services/api';
import { useApiData, asList } from '../../hooks/useApiData';
import Icon from '../common/Icon';
import DataStates from './DataStates';
import './BatchesSection.css';

const POLL_MS = 4000;

const STATUS_CHIP = {
  completed: 'chip-done',
  running: 'chip-running',
  queued: 'chip-queued',
  failed: 'chip-fail',
};

const TERMINAL = new Set(['completed', 'failed', 'cancelled']);

function pct(value) {
  return typeof value === 'number' ? (value * 100).toFixed(1) : '—';
}

function BatchRow({ job }) {
  const total = job.num_runs || 0;
  const done = job.runs_completed || 0;
  const failed = job.runs_failed || 0;
  const settled = done + failed;
  const queued = Math.max(0, total - settled);
  const progress = total > 0 ? Math.round((settled / total) * 100) : 0;

  return (
    <div className="panel batch-card">
      <div className="batch-head">
        <div className="batch-title">
          <span className="batch-name">{job.scenario_name}</span>
          <span className="batch-model mono-label">{job.model_name}</span>
        </div>
        <span className={`chip ${STATUS_CHIP[job.status] || 'chip-queued'}`}>
          {job.status}
        </span>
      </div>

      <div
        className="batch-progress"
        role="progressbar"
        aria-valuenow={progress}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={`${job.scenario_name} progress`}
      >
        <i style={{ '--p': progress / 100 }} className={failed > 0 ? 'has-failures' : ''} />
      </div>

      <div className="spec-strip batch-counts">
        <div><span className="num">{total}</span><span className="mono-label">total</span></div>
        <div><span className="num">{queued}</span><span className="mono-label">queued</span></div>
        <div><span className="num is-pass">{done}</span><span className="mono-label">done</span></div>
        <div><span className={`num ${failed ? 'is-fail' : ''}`}>{failed}</span><span className="mono-label">failed</span></div>
        <div><span className="num is-amber">{pct(job.composite_mean)}</span><span className="mono-label">composite</span></div>
        <div><span className="num">{pct(job.collision_rate)}</span><span className="mono-label">collision %</span></div>
      </div>

      {job.error_message && (
        <div className="batch-error">
          <Icon name="warning" size={13} /> {job.error_message}
        </div>
      )}
    </div>
  );
}

export default function BatchesSection() {
  const { data, loading, error, refresh } = useApiData(() => api.getBatchJobs(), []);
  const jobs = useMemo(() => asList(data, 'jobs'), [data]);

  const active = useMemo(
    () => jobs.some((j) => !TERMINAL.has(j.status)),
    [jobs],
  );

  // Poll only while something is actually in flight.
  useEffect(() => {
    if (!active) return undefined;
    const id = setInterval(refresh, POLL_MS);
    return () => clearInterval(id);
  }, [active, refresh]);

  return (
    <section className="batches-section">
      <div className="section-bar">
        <span className="mono-label">
          Batch jobs · /jobs <span className="num">{jobs.length}</span>
          {active && <span className="batch-live"> · LIVE</span>}
        </span>
        <button type="button" className="btn btn-ghost btn-sm" onClick={refresh} disabled={loading}>
          <Icon name="refresh" size={14} /> Refresh
        </button>
      </div>

      <DataStates
        loading={loading}
        error={error}
        isEmpty={jobs.length === 0}
        onRetry={refresh}
        loadingRows={3}
        loadingLabel="Loading batches"
        emptyLabel="No batch jobs"
        emptyHint="Batches queued through POST /api/runs/batch appear here with live progress."
      >
        <div className="batch-list">
          {jobs.map((job) => <BatchRow key={job.id} job={job} />)}
        </div>
      </DataStates>
    </section>
  );
}
