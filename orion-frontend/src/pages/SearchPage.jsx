// ORION — SearchPage  [P2]
// Route: /dashboard/search
// Adversarial search — instrument form + results table (§9.7).
// Visual restyle to "Mission Control" (ORION_UI_DESIGN.md §11.4). Data wiring
// out of scope — results render the §9.12 empty state until wired.

import React, { useState } from 'react';
import { useAuth } from '../context/AuthContext';
import Icon from '../components/common/Icon';
import './SearchPage.css';

const SCENARIO_PRESETS = [
  'scenarios/lon/LON-003_emergency_stop.yaml',
  'scenarios/lat/LAT-001_lane_change.yaml',
  'scenarios/vru/VRU-002_pedestrian_crossing.yaml',
];
const MODEL_OPTIONS = ['EmergencyBrake', 'ConstantAction', 'SimpleLaneKeep', 'Random'];

/**
 * SearchPage — adversarial parameter search instrument.
 */
export default function SearchPage() {
  const { user } = useAuth();
  const [scenario, setScenario] = useState(SCENARIO_PRESETS[0]);
  const [model, setModel] = useState('EmergencyBrake');
  const [budget, setBudget] = useState(200);
  const [objective, setObjective] = useState('min_composite');

  // Data wiring tracked separately — no fetch invented here.
  const results = [];

  return (
    <div className="search-page" id="search-page">
      <header className="search-head">
        <div>
          <h1>Adversarial Search</h1>
          <div className="search-sub mono-label">
            FAILURE DISCOVERY{user?.username ? ` · ORG=${user.username}` : ''}
          </div>
        </div>
      </header>

      <div className="panel panel--live search-form">
        <div className="search-form-cap mono-label">
          <Icon name="search" size={13} /> Search Parameters
        </div>
        <div className="search-grid">
          <label className="field">
            <span>Scenario</span>
            <input list="search-scenarios" value={scenario} onChange={(e) => setScenario(e.target.value)} />
            <datalist id="search-scenarios">
              {SCENARIO_PRESETS.map((p) => <option key={p} value={p} />)}
            </datalist>
          </label>
          <label className="field">
            <span>Model</span>
            <select value={model} onChange={(e) => setModel(e.target.value)}>
              {MODEL_OPTIONS.map((m) => <option key={m} value={m}>{m}</option>)}
            </select>
          </label>
          <label className="field">
            <span>Objective</span>
            <select value={objective} onChange={(e) => setObjective(e.target.value)}>
              <option value="min_composite">Minimise composite</option>
              <option value="max_collision">Maximise collision rate</option>
              <option value="min_ttc">Minimise min-TTC</option>
            </select>
          </label>
          <label className="field">
            <span>Budget (runs)</span>
            <input type="number" min="1" value={budget} onChange={(e) => setBudget(e.target.value)} />
          </label>
        </div>
        <button type="button" className="btn btn-primary search-launch" disabled>
          <Icon name="play" size={15} /> Launch Search
        </button>
      </div>

      <div className="panel search-results">
        <div className="search-results-cap mono-label">Worst-Case Findings</div>
        <div className="search-results-wrap">
          <table className="data-table" id="search-results-table">
            <thead>
              <tr>
                <th>Rank</th><th>Seed</th><th>Params</th>
                <th>Composite</th><th>Min TTC</th><th>Verdict</th>
              </tr>
            </thead>
            <tbody>
              {results.length === 0 ? (
                <tr>
                  <td colSpan={6} className="table-empty">
                    No search run yet — configure parameters and launch above.
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
