// ORION — BatchPage  [P1]
// Route: /dashboard/batches/:id
// Batch detail — progress bar, per-run table, aggregate scores
// TODO [P1]: Implement this page.

import React from 'react';
import { useAuth } from '../context/AuthContext';
import './BatchPage.css';

/**
 * BatchPage — Batch detail — progress bar, per-run table, aggregate scores
 */
export default function BatchPage() {
  const { user } = useAuth();

  return (
    <div className="BatchPage">
      <h1>BatchPage</h1>
      {/* TODO [P1]: Implement BatchPage */}
      <p style={{ color: '#888' }}>BatchPage — not yet implemented [P1]</p>
    </div>
  );
}
