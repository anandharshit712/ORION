// ORION — ModelsPage  [P1]
// Route: /dashboard/models
// List org models and upload new model via SDK or Docker
// TODO [P1]: Implement this page.

import React from 'react';
import { useAuth } from '../context/AuthContext';
import './ModelsPage.css';

/**
 * ModelsPage — List org models and upload new model via SDK or Docker
 */
export default function ModelsPage() {
  const { user } = useAuth();

  return (
    <div className="ModelsPage">
      <h1>ModelsPage</h1>
      {/* TODO [P1]: Implement ModelsPage */}
      <p style={{ color: '#888' }}>ModelsPage — not yet implemented [P1]</p>
    </div>
  );
}
