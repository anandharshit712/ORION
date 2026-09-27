// ORION — SearchSection
//
// Adversarial search (docs/UI_DESIGN.md §11.4) over POST /api/search. The
// optimiser hunts for the parameter set that breaks a model rather than
// sampling the space, so the deliverable is the list of settings that failed —
// not a score.
//
// The budget field is the whole design problem. A search costs one credit per
// evaluation, and CMA-ES needs roughly ten evaluations per dimension before it
// beats random sampling, so too small a budget sells a result that means
// nothing. Leaving the field empty is therefore the recommended path: the
// backend charges the budget it computes for that scenario's dimensionality.
//
// Per the product decision, the cost is signalled but never quoted here: an
// info affordance says that a larger budget costs more, with no numbers and no
// estimate. It is hover/focus only — see InfoHint.

import { useMemo, useState } from 'react';
import { api } from '../../services/api';
import { useApiData, asList } from '../../hooks/useApiData';
import Icon from '../common/Icon';
import DataStates from './DataStates';
import InfoHint from '../common/InfoHint';
import './SearchSection.css';

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

function num(value, digits = 3) {
  return typeof value === 'number' ? value.toFixed(digits) : '—';
}

/** One parameter set that broke the model, flattened for display. */
function ParamList({ params }) {
  const entries = Object.entries(params || {});
  if (entries.length === 0) return <span className="search-muted">—</span>;
  return (
    <ul className="search-params">
      {entries.map(([key, value]) => (
        <li key={key}>
          <span className="search-params__key">{key}</span>
          <span className="num">{typeof value === 'number' ? value.toFixed(3) : String(value)}</span>
        </li>
      ))}
    </ul>
  );
}

function ResultPanel({ search }) {
  const result = search?.result;
  if (!result) return null;

  const failures = result.falsifications || [];

  return (
    <div className="search-result">
      <div className={`panel search-verdict ${result.falsification_found ? 'is-broken' : ''}`}>
        <span className="mono-label">Result</span>
        <p className="search-verdict__text">
          {result.falsification_found
            ? 'The model was broken by at least one setting in this space.'
            : 'No failure found within this budget.'}
        </p>
        <div className="search-verdict__meta">
          <span className={`chip chip--${result.falsification_found ? 'fail' : 'pass'}`}>
            {result.falsification_found ? 'falsified' : 'no falsification'}
          </span>
          <span className="mono-label">
            evaluations <span className="num">{result.n_evals}</span>
          </span>
          <span className="mono-label">
            distinct failures <span className="num">{result.distinct_failure_count}</span>
          </span>
          {/* The rate is the finding when most of the space fails; a list of
              eighty settings buries that and one number does not. */}
          <span className="mono-label">
            failure rate{' '}
            <span className="num">{Math.round((result.failure_rate || 0) * 100)}%</span>
          </span>
          <span className="mono-label">
            optimizer <span className="num">{result.optimizer_used}</span>
          </span>
        </div>
        {!result.falsification_found && (
          <p className="settings-hint">
            That is not proof the model is safe. Eight continuous dimensions cannot be
            covered by any budget — a guided search steers, it does not enumerate.
          </p>
        )}
      </div>

      {failures.length > 0 && (
        <div className="panel search-failures">
          <span className="mono-label">
            Settings that broke it <span className="num">{failures.length}</span>
          </span>
          <p className="settings-hint">
            Worst first. Two failures from opposite corners of the space are two bugs,
            not one.
          </p>
          <ol className="search-failure-list">
            {failures.map((params, i) => (
              <li key={i} className="search-failure">
                <span className="mono-label">#{i + 1}</span>
                <ParamList params={params} />
              </li>
            ))}
          </ol>
        </div>
      )}

      {result.evaluations_truncated && (
        <p className="settings-hint">
          The stored evaluation history was trimmed. Every failure is kept; some
          non-failing evaluations were dropped.
        </p>
      )}
    </div>
  );
}

export default function SearchSection() {
  const { data, loading, error, refresh } = useApiData(() => api.listSearches(), []);
  const searches = useMemo(() => asList(data, 'searches'), [data]);

  const [selected, setSelected] = useState(null);
  const [form, setForm] = useState({
    scenarioId: '',
    modelId: '',
    maxEvals: '',
    optimizer: 'cma_es',
  });
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState(null);

  const detail = useApiData(
    () => (selected == null ? Promise.resolve(null) : api.getSearchResult(selected)),
    [selected],
  );

  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    setFormError(null);
    try {
      const created = await api.startSearch({
        scenarioId: form.scenarioId.trim(),
        modelId: form.modelId.trim(),
        maxEvals: form.maxEvals,
        optimizer: form.optimizer,
      });
      setSelected(created.search_id);
      refresh();
    } catch (e) {
      setFormError(e?.message || 'Could not queue the search');
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="search-section">
      <div className="section-bar">
        <span className="mono-label">
          Adversarial search · /api/search <span className="num">{searches.length}</span>
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

      <form className="panel search-form" onSubmit={submit}>
        <span className="mono-label">Search for a failure</span>
        <div className="search-form__row">
          <label className="field">
            <span className="mono-label">Scenario</span>
            <input
              type="text"
              placeholder="../scenarios/lon/LON-003_emergency_stop.yaml"
              value={form.scenarioId}
              onChange={(e) => setForm({ ...form, scenarioId: e.target.value })}
            />
          </label>
          <label className="field">
            <span className="mono-label">Model</span>
            <input
              type="text"
              placeholder="model UUID or built-in name"
              value={form.modelId}
              onChange={(e) => setForm({ ...form, modelId: e.target.value })}
            />
          </label>
          <label className="field search-form__narrow">
            <span className="mono-label">
              Optimizer
            </span>
            <select
              value={form.optimizer}
              onChange={(e) => setForm({ ...form, optimizer: e.target.value })}
            >
              <option value="cma_es">CMA-ES</option>
              <option value="random">Random baseline</option>
            </select>
          </label>
          <label className="field search-form__narrow">
            <span className="mono-label">
              Budget
              <InfoHint text="A larger budget searches harder and costs more." />
            </span>
            <input
              type="number"
              min="10"
              max="2000"
              placeholder="recommended"
              value={form.maxEvals}
              onChange={(e) => setForm({ ...form, maxEvals: e.target.value })}
            />
          </label>
        </div>
        <div className="search-form__foot">
          <span className="settings-hint">
            Leave the budget empty to use the one recommended for this scenario — it
            scales with how many parameters the scenario actually varies.
          </span>
          <button
            type="submit"
            className="btn btn-primary btn-sm"
            disabled={busy || !form.scenarioId.trim() || !form.modelId.trim()}
          >
            <Icon name="search" size={14} /> Run search
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
        isEmpty={searches.length === 0}
        onRetry={refresh}
        loadingRows={4}
        loadingLabel="Loading searches"
        emptyLabel="No searches yet"
        emptyHint="Run one above to hunt for the settings that break a model."
      >
        <table className="data-table">
          <thead>
            <tr>
              <th>ID</th>
              <th>Scenario</th>
              <th>Model</th>
              <th>Dims</th>
              <th>Evals</th>
              <th>Status</th>
              <th>Falsified</th>
              <th>Created</th>
            </tr>
          </thead>
          <tbody>
            {searches.map((s) => (
              <tr
                key={s.search_id}
                className={selected === s.search_id ? 'is-selected' : ''}
                onClick={() => setSelected(s.search_id)}
              >
                <td className="settings-rows__id">{s.search_id}</td>
                <td>{String(s.scenario_id).split('/').pop()}</td>
                <td>{s.model_id}</td>
                <td className="num">{s.n_dims}</td>
                <td className="num">
                  {s.evals_done}/{s.max_evals}
                </td>
                <td>
                  <span className={`chip chip--${STATUS_CHIP[s.status] || 'queued'}`}>
                    {s.status}
                  </span>
                </td>
                <td>
                  {/* null means "not looked yet", which is a different answer
                      from "nothing found" — rendering it as "no" would say a
                      model is safe before anything ran. */}
                  {s.falsification_found == null ? (
                    <span className="search-muted">—</span>
                  ) : (
                    <span className={`chip chip--${s.falsification_found ? 'fail' : 'pass'}`}>
                      {s.falsification_found ? 'yes' : 'no'}
                    </span>
                  )}
                </td>
                <td>{when(s.created_at)}</td>
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
          loadingLabel="Loading search"
          emptyLabel="Search not found"
          emptyHint="It may have been removed."
        >
          {detail.data?.status === 'completed' ? (
            <ResultPanel search={detail.data} />
          ) : (
            <div className="panel search-pending">
              <span className="mono-label">
                Search {selected} · {detail.data?.status}
              </span>
              <p className="settings-hint">
                {detail.data?.status === 'failed'
                  ? detail.data?.error_message || 'The search failed.'
                  : 'Still running. Refresh to check again.'}
              </p>
              {detail.data?.best_fitness != null && (
                <span className="mono-label">
                  best fitness <span className="num">{num(detail.data.best_fitness)}</span>
                </span>
              )}
            </div>
          )}
        </DataStates>
      )}
    </section>
  );
}
