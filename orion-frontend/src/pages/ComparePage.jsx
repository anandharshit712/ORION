// ORION — ComparePage  [P2]
// Route: /dashboard/compare
// Side-by-side model comparison via the shared ComparisonTable (§9.7).
// Visual restyle to "Mission Control" (ORION_UI_DESIGN.md §11.4). Data wiring
// out of scope — the selector is a styled instrument; ComparisonTable owns its
// own empty state until models are wired in.

import React, { useState } from 'react';
import { useAuth } from '../context/AuthContext';
import ComparisonTable from '../components/dashboard/ComparisonTable';
import Icon from '../components/common/Icon';
import './ComparePage.css';

const MODEL_OPTIONS = ['EmergencyBrake', 'ConstantAction', 'SimpleLaneKeep', 'Random'];

/**
 * ComparePage — pick two models, view metrics side by side.
 */
export default function ComparePage() {
  const { user } = useAuth();
  const [modelA, setModelA] = useState('');
  const [modelB, setModelB] = useState('');

  return (
    <div className="compare-page" id="compare-page">
      <header className="compare-head">
        <div>
          <h1>Compare</h1>
          <div className="compare-sub mono-label">
            A / B METRIC DELTA{user?.username ? ` · ORG=${user.username}` : ''}
          </div>
        </div>
      </header>

      <div className="panel compare-selector">
        <div className="compare-selector-cap mono-label">Select Models</div>
        <div className="compare-selector-grid">
          <label className="field">
            <span>Model A</span>
            <select value={modelA} onChange={(e) => setModelA(e.target.value)}>
              <option value="">— select —</option>
              {MODEL_OPTIONS.map((m) => <option key={m} value={m}>{m}</option>)}
            </select>
          </label>
          <span className="compare-vs" aria-hidden="true">
            <Icon name="compare" size={18} />
          </span>
          <label className="field">
            <span>Model B</span>
            <select value={modelB} onChange={(e) => setModelB(e.target.value)}>
              <option value="">— select —</option>
              {MODEL_OPTIONS.map((m) => <option key={m} value={m}>{m}</option>)}
            </select>
          </label>
        </div>
      </div>

      <ComparisonTable title="Model Comparison · A vs B" />
    </div>
  );
}
