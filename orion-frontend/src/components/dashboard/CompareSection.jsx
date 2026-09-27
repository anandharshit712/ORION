// ORION — CompareSection
//
// Side-by-side model comparison (docs/UI_DESIGN.md §11.4) over POST /api/compare
// and GET /api/compare/{id}. This closes the last dashboard section that
// rendered ComingSoon; it was blocked on a regression endpoint, which 2.4 now
// provides.
//
// Three things the API shape makes non-obvious:
//   - a comparison is queued, not synchronous, so the list is the primary view
//     and a running job has no report yet;
//   - it costs credits (2 × runs × scenarios), charged before it queues, so the
//     form states the price before the button is pressed rather than after;
//   - `report.pdf` serves HTML where WeasyPrint's native libraries are absent,
//     which is most machines. The link says "report", not "PDF", because
//     promising a format the server may not produce is a worse lie than a
//     vaguer label.

import { useMemo, useState } from 'react';
import { api } from '../../services/api';
import { useApiData, asList } from '../../hooks/useApiData';
import Icon from '../common/Icon';
import DataStates from './DataStates';
import ComparisonTable from './ComparisonTable';
import './CompareSection.css';

const RUNS_PER_SCENARIO_PER_MODEL = 2;

/** Mirrors comparison_cost() in arep/api/compare.py. */
function cost(runsPerScenario, scenarioCount) {
  return RUNS_PER_SCENARIO_PER_MODEL * runsPerScenario * scenarioCount;
}

const STATUS_CHIP = {
  queued: 'queued',
  running: 'running',
  completed: 'done',
  failed: 'error',
};

function when(value) {
  if (!value) return '—';
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? '—' : d.toISOString().slice(0, 16).replace('T', ' ');
}

/**
 * Turn one scenario's metric deltas into the two-column shape ComparisonTable
 * renders. The backend names metrics `composite_score`; the table's default
 * rows are keyed `composite`, so the suffix is trimmed rather than widening
 * the table's vocabulary.
 */
function toTableModels(scenario, nameA, nameB) {
  const scoresA = {};
  const scoresB = {};
  const deltas = {};

  for (const d of scenario?.metric_deltas || []) {
    const key = String(d.metric || '').replace(/_score$/, '');
    scoresA[key] = d.value_a;
    scoresB[key] = d.value_b;
    deltas[key] = d.delta;
  }

  return [
    { name: nameA, scores: scoresA },
    { name: nameB, scores: scoresB, deltas },
  ];
}

function ReportPanel({ comparison }) {
  const report = comparison?.report;
  const [scenarioIndex, setScenarioIndex] = useState(0);

  if (!report) return null;

  const scenarios = report.scenario_comparisons || [];
  const scenario = scenarios[scenarioIndex];
  const regressed = (report.regressions || []).length > 0;

  return (
    <div className="compare-report">
      <div className={`panel compare-verdict ${regressed ? 'is-regressed' : ''}`}>
        <span className="mono-label">Verdict</span>
        <p className="compare-verdict__text">{report.recommendation || '—'}</p>
        <div className="compare-verdict__meta">
          <span className={`chip chip--${regressed ? 'fail' : 'pass'}`}>
            {regressed
              ? `${report.regressions.length} regression(s)`
              : 'no regression'}
          </span>
          <span className="mono-label">
            winner <span className="num">{report.overall_winner}</span>
          </span>
          <a
            className="btn btn-ghost btn-sm"
            href={api.comparisonReportUrl(comparison.comparison_id)}
          >
            <Icon name="download" size={14} /> Download report
          </a>
        </div>
      </div>

      {regressed && (
        <div className="panel compare-regressions">
          <span className="mono-label">Regressions</span>
          <table className="data-table">
            <thead>
              <tr>
                <th>Metric</th>
                <th>Baseline</th>
                <th>Candidate</th>
                <th>Delta</th>
                <th>Threshold</th>
              </tr>
            </thead>
            <tbody>
              {report.regressions.map((d, i) => (
                <tr key={`${d.metric}-${i}`}>
                  <td>{d.metric}</td>
                  <td className="num">{Number(d.value_a).toFixed(3)}</td>
                  <td className="num">{Number(d.value_b).toFixed(3)}</td>
                  <td className="num compare-delta is-fail">
                    {Number(d.delta).toFixed(3)}
                  </td>
                  <td className="num">{Number(d.threshold_used).toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {scenarios.length > 0 && (
        <>
          <div className="compare-scenario-tabs" role="tablist">
            {scenarios.map((s, i) => (
              <button
                key={s.scenario_id || i}
                type="button"
                role="tab"
                aria-selected={i === scenarioIndex}
                className={`compare-tab ${i === scenarioIndex ? 'is-active' : ''}`}
                onClick={() => setScenarioIndex(i)}
              >
                {s.scenario_id}
                {s.has_regression && <span className="compare-tab__flag">!</span>}
              </button>
            ))}
          </div>
          <ComparisonTable
            title={scenario?.scenario_id || 'Scenario'}
            models={toTableModels(
              scenario,
              report.model_a_name || 'A',
              report.model_b_name || 'B',
            )}
          />
        </>
      )}
    </div>
  );
}

export default function CompareSection() {
  const { data, loading, error, refresh } = useApiData(() => api.listComparisons(), []);
  const comparisons = useMemo(() => asList(data, 'comparisons'), [data]);

  const [selected, setSelected] = useState(null);
  const [form, setForm] = useState({
    modelA: '',
    modelB: '',
    scenarios: 'all',
    runs: 10,
  });
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState(null);

  const detail = useApiData(
    () => (selected == null ? Promise.resolve(null) : api.getComparison(selected)),
    [selected],
  );

  // "all" expands server-side, so the count is unknown until then. Quoting a
  // number we cannot stand behind is worse than saying it depends.
  const scenarioList = form.scenarios
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean);
  const knownCount = scenarioList.length === 1 && scenarioList[0] === 'all'
    ? null
    : scenarioList.length;

  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    setFormError(null);
    try {
      const created = await api.startComparison(
        form.modelA.trim(),
        form.modelB.trim(),
        scenarioList,
        Number(form.runs),
      );
      setSelected(created.comparison_id);
      refresh();
    } catch (e) {
      setFormError(e?.message || 'Could not queue the comparison');
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="compare-section">
      <div className="section-bar">
        <span className="mono-label">
          Comparisons · /api/compare <span className="num">{comparisons.length}</span>
        </span>
        <button
          type="button"
          className="btn btn-ghost btn-sm"
          onClick={refresh}
          disabled={loading}
        >
          <Icon name="refresh" size={14} /> Refresh
        </button>
      </div>

      <form className="panel compare-form" onSubmit={submit}>
        <span className="mono-label">Queue a comparison</span>
        <div className="compare-form__row">
          <label className="field">
            <span className="mono-label">Baseline</span>
            <input
              type="text"
              placeholder="EmergencyBrake"
              value={form.modelA}
              onChange={(e) => setForm({ ...form, modelA: e.target.value })}
            />
          </label>
          <label className="field">
            <span className="mono-label">Candidate</span>
            <input
              type="text"
              placeholder="model UUID or built-in name"
              value={form.modelB}
              onChange={(e) => setForm({ ...form, modelB: e.target.value })}
            />
          </label>
          <label className="field">
            <span className="mono-label">Scenarios</span>
            <input
              type="text"
              placeholder="all"
              value={form.scenarios}
              onChange={(e) => setForm({ ...form, scenarios: e.target.value })}
            />
          </label>
          <label className="field compare-form__narrow">
            <span className="mono-label">Runs each</span>
            <input
              type="number"
              min="1"
              max="500"
              value={form.runs}
              onChange={(e) => setForm({ ...form, runs: e.target.value })}
            />
          </label>
        </div>
        <div className="compare-form__foot">
          <span className="settings-hint">
            {knownCount === null
              ? `Costs 2 × ${form.runs} × (every scenario) credits — both models run each one.`
              : `Costs ${cost(Number(form.runs) || 0, knownCount)} credits: 2 models × ${form.runs} runs × ${knownCount} scenario(s).`}
          </span>
          <button
            type="submit"
            className="btn btn-primary btn-sm"
            disabled={busy || !form.modelA.trim() || !form.modelB.trim()}
          >
            <Icon name="compare" size={14} /> Run comparison
          </button>
        </div>
        {formError && (
          <p className="settings-error" role="alert">
            {formError}
          </p>
        )}
      </form>

      <DataStates
        loading={loading}
        error={error}
        isEmpty={comparisons.length === 0}
        onRetry={refresh}
        loadingRows={4}
        loadingLabel="Loading comparisons"
        emptyLabel="No comparisons yet"
        emptyHint="Queue one above to see two models scored on identical seeds."
      >
        <table className="data-table">
          <thead>
            <tr>
              <th>ID</th>
              <th>Baseline</th>
              <th>Candidate</th>
              <th>Scenarios</th>
              <th>Status</th>
              <th>Winner</th>
              <th>Created</th>
            </tr>
          </thead>
          <tbody>
            {comparisons.map((c) => (
              <tr
                key={c.comparison_id}
                className={selected === c.comparison_id ? 'is-selected' : ''}
                onClick={() => setSelected(c.comparison_id)}
              >
                <td className="settings-rows__id">{c.comparison_id}</td>
                <td>{c.model_a_id}</td>
                <td>{c.model_b_id}</td>
                <td className="num">{c.scenario_count}</td>
                <td>
                  <span className={`chip chip--${STATUS_CHIP[c.status] || 'queued'}`}>
                    {c.status}
                  </span>
                </td>
                <td>{c.overall_winner || '—'}</td>
                <td>{when(c.created_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </DataStates>

      {selected != null && (
        <DataStates
          loading={detail.loading}
          error={detail.error}
          isEmpty={!detail.loading && !detail.error && !detail.data}
          onRetry={detail.refresh}
          loadingRows={5}
          loadingLabel="Loading comparison"
          emptyLabel="Comparison not found"
          emptyHint="It may have been removed."
        >
          {detail.data?.status === 'completed' ? (
            <ReportPanel comparison={detail.data} />
          ) : (
            <div className="panel compare-pending">
              <span className="mono-label">
                Comparison {selected} · {detail.data?.status}
              </span>
              <p className="settings-hint">
                {detail.data?.status === 'failed'
                  ? detail.data?.error_message || 'The comparison failed.'
                  : 'Still running. Refresh to check again — the report appears once it completes.'}
              </p>
            </div>
          )}
        </DataStates>
      )}
    </section>
  );
}
