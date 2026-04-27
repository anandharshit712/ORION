// ORION — ComparePage  [P2]
// Route: /dashboard/compare
// Model comparison — A vs B table with regression badges
// TODO [P2]: Implement this page.

import React from 'react';
import { useAuth } from '../context/AuthContext';
import './ComparePage.css';

/**
 * ComparePage — Model comparison — A vs B table with regression badges
 */
export default function ComparePage() {
  const { user } = useAuth();

  return (
    <div className="ComparePage">
      <h1>ComparePage</h1>
      {/* TODO [P2]: Implement ComparePage */}
      <p style={{ color: '#888' }}>ComparePage — not yet implemented [P2]</p>
    </div>
  );
}
