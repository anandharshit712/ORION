// ORION — ScenariosSection
//
// Filterable scenario grid (docs/UI_DESIGN.md §11.4): category chip, name, mono
// id, params. Reads GET /scenarios/ — mounted at the root, not under /api
// (CLAUDE.md §8).
//
// The category is derived from the scenario name's ID prefix (LON-003 -> LON)
// because the API returns no category field. A scenario whose name does not
// match the convention lands in "other" rather than being dropped: an unlisted
// scenario is worse than an oddly-filed one.

import { useMemo, useState } from 'react';
import { api } from '../../services/api';
import { useApiData, asList } from '../../hooks/useApiData';
import Icon from '../common/Icon';
import DataStates from './DataStates';
import './ScenariosSection.css';

const CATEGORIES = ['all', 'LON', 'LAT', 'INT', 'VRU', 'EMG', 'MLT'];

const CATEGORY_LABEL = {
  LON: 'Longitudinal control',
  LAT: 'Lateral control',
  INT: 'Intersection negotiation',
  VRU: 'Vulnerable road users',
  EMG: 'Emergency / anomaly',
  MLT: 'Multi-agent',
};

/** "LON-003 Emergency Stop" -> "LON". Unrecognised names -> "other". */
function categoryOf(scenario) {
  const match = /^([A-Z]{3})-\d+/.exec(String(scenario.name || '').trim());
  return match ? match[1] : 'other';
}

function idOf(scenario) {
  const match = /^([A-Z]{3}-\d+)/.exec(String(scenario.name || '').trim());
  return match ? match[1] : `#${scenario.id}`;
}

export default function ScenariosSection() {
  const [category, setCategory] = useState('all');
  const { data, loading, error, refresh } = useApiData(() => api.getScenarios(), []);
  const scenarios = useMemo(() => asList(data, 'scenarios'), [data]);

  const counts = useMemo(() => {
    const out = { all: scenarios.length };
    for (const c of CATEGORIES.slice(1)) {
      out[c] = scenarios.filter((s) => categoryOf(s) === c).length;
    }
    return out;
  }, [scenarios]);

  const shown = useMemo(
    () => (category === 'all' ? scenarios : scenarios.filter((s) => categoryOf(s) === category)),
    [scenarios, category],
  );

  return (
    <section className="scenarios-section">
      <div className="section-bar">
        <div className="seg-control" role="tablist" aria-label="Filter scenarios by category">
          {CATEGORIES.map((c) => (
            <button
              key={c}
              type="button"
              role="tab"
              aria-selected={category === c}
              className={`seg-btn ${category === c ? 'is-active' : ''}`}
              onClick={() => setCategory(c)}
              title={CATEGORY_LABEL[c] || 'All categories'}
            >
              {c} <span className="num seg-count">{counts[c] ?? 0}</span>
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
        loadingRows={6}
        loadingLabel="Loading scenarios"
        emptyLabel={category === 'all' ? 'No scenarios registered' : `No ${category} scenarios`}
        emptyHint={
          category === 'all'
            ? 'Scenarios are registered in the database the first time they are run.'
            : 'Pick another category.'
        }
      >
        <div className="scenario-grid">
          {shown.map((s) => {
            const cat = categoryOf(s);
            return (
              <article key={s.id} className="panel scenario-card">
                <div className="scenario-head">
                  <span className={`chip ${cat === 'other' ? 'chip-queued' : 'chip-done'}`}>{cat}</span>
                  <span className="scenario-id num">{idOf(s)}</span>
                </div>

                <h3 className="scenario-name">{s.name}</h3>
                {s.description && <p className="scenario-desc">{s.description}</p>}

                <div className="spec-strip scenario-specs">
                  <div>
                    <span className="num">{Number(s.duration || 0).toFixed(0)}<em>s</em></span>
                    <span className="mono-label">duration</span>
                  </div>
                  <div>
                    <span className="num">{s.num_traffic_objects ?? 0}</span>
                    <span className="mono-label">actors</span>
                  </div>
                  <div>
                    <span className="num">{s.road_type || '—'}</span>
                    <span className="mono-label">road</span>
                  </div>
                  <div>
                    <span className="num">v{s.version}</span>
                    <span className="mono-label">version</span>
                  </div>
                </div>

                <div className="scenario-hash num" title={s.content_hash}>
                  <Icon name="key" size={11} /> {String(s.content_hash || '').slice(0, 16)}
                </div>
              </article>
            );
          })}
        </div>
      </DataStates>
    </section>
  );
}
