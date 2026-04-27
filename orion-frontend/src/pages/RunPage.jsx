// ORION — RunPage  [P1]
// Route: /dashboard/runs/:id
// Single run detail — scores, event log, link to SimulationViewer
// TODO [P1]: Implement this page.

import React from 'react';
import { useAuth } from '../context/AuthContext';
import './RunPage.css';

/**
 * RunPage — Single run detail — scores, event log, link to SimulationViewer
 */
export default function RunPage() {
  const { user } = useAuth();

  return (
    <div className="RunPage">
      <h1>RunPage</h1>
      {/* TODO [P1]: Implement RunPage */}
      <p style={{ color: '#888' }}>RunPage — not yet implemented [P1]</p>
    </div>
  );
}
