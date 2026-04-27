// ORION — SettingsPage  [P1]
// Route: /dashboard/settings
// Org settings, API key management, team members
// TODO [P1]: Implement this page.

import React from 'react';
import { useAuth } from '../context/AuthContext';
import './SettingsPage.css';

/**
 * SettingsPage — Org settings, API key management, team members
 */
export default function SettingsPage() {
  const { user } = useAuth();

  return (
    <div className="SettingsPage">
      <h1>SettingsPage</h1>
      {/* TODO [P1]: Implement SettingsPage */}
      <p style={{ color: '#888' }}>SettingsPage — not yet implemented [P1]</p>
    </div>
  );
}
