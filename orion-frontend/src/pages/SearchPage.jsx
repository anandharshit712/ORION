// ORION — SearchPage  [P2]
// Route: /dashboard/search
// Adversarial search — launch and view results (Pro tier)
// TODO [P2]: Implement this page.

import React from 'react';
import { useAuth } from '../context/AuthContext';
import './SearchPage.css';

/**
 * SearchPage — Adversarial search — launch and view results (Pro tier)
 */
export default function SearchPage() {
  const { user } = useAuth();

  return (
    <div className="SearchPage">
      <h1>SearchPage</h1>
      {/* TODO [P2]: Implement SearchPage */}
      <p style={{ color: '#888' }}>SearchPage — not yet implemented [P2]</p>
    </div>
  );
}
