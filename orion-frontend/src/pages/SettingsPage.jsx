// ORION — SettingsPage  [P1]
// Route: /dashboard/settings
// Grouped instrument panels (ORION_UI_DESIGN.md §11.4): Profile, Organization,
// API Keys, Theme. Visual restyle only — profile/org read existing `user`
// fields; API-key data wiring is out of scope (renders §9.12 empty state).

import React from 'react';
import { useAuth } from '../context/AuthContext';
import ThemeToggle from '../components/common/ThemeToggle';
import Icon from '../components/common/Icon';
import './SettingsPage.css';

/**
 * SettingsPage — account, org, API keys, theme.
 */
export default function SettingsPage() {
  const { user } = useAuth();

  // Data wiring tracked separately — no fetch invented here.
  const apiKeys = [];

  const profileRows = [
    { label: 'Username', value: user?.username },
    { label: 'Email', value: user?.email },
    { label: 'Full Name', value: user?.full_name },
    { label: 'Role', value: user?.role },
  ];
  const orgRows = [
    { label: 'Organization', value: user?.organization?.name ?? user?.org?.name },
    { label: 'Plan', value: user?.organization?.plan ?? user?.org?.plan },
    {
      label: 'Run Credits',
      value: user?.credits_remaining ?? user?.organization?.credits_remaining,
      mono: true,
    },
  ];

  return (
    <div className="settings-page" id="settings-page">
      <header className="settings-head">
        <div>
          <h1>Settings</h1>
          <div className="settings-sub mono-label">ACCOUNT · ORG · ACCESS · THEME</div>
        </div>
      </header>

      {/* Profile */}
      <section className="panel settings-section">
        <div className="settings-section-cap mono-label">01 / Profile</div>
        <dl className="settings-rows">
          {profileRows.map((r) => (
            <div className="settings-row" key={r.label}>
              <dt className="mono-label">{r.label}</dt>
              <dd className="num">{r.value || '—'}</dd>
            </div>
          ))}
        </dl>
      </section>

      {/* Organization */}
      <section className="panel settings-section">
        <div className="settings-section-cap mono-label">02 / Organization</div>
        <dl className="settings-rows">
          {orgRows.map((r) => (
            <div className="settings-row" key={r.label}>
              <dt className="mono-label">{r.label}</dt>
              <dd className={r.mono ? 'num is-credits' : 'num'}>
                {r.value != null && r.value !== '' ? r.value : '—'}
              </dd>
            </div>
          ))}
        </dl>
      </section>

      {/* API Keys */}
      <section className="panel settings-section settings-keys">
        <div className="settings-section-cap mono-label">
          <Icon name="key" size={13} /> 03 / API Keys
        </div>
        <div className="settings-keys-wrap">
          <table className="data-table" id="api-keys-table">
            <thead>
              <tr>
                <th>Label</th><th>Key</th><th>Created</th><th>Last Used</th><th></th>
              </tr>
            </thead>
            <tbody>
              {apiKeys.length === 0 ? (
                <tr>
                  <td colSpan={5} className="table-empty">
                    No API keys — generate one to authenticate the SDK / CLI.
                  </td>
                </tr>
              ) : (
                apiKeys.map((k) => (
                  <tr key={k.id}>
                    <td>{k.label}</td>
                    <td className="key-cell num">
                      <span className="key-prefix">{k.prefix}••••••••</span>
                      <button className="key-copy" type="button" aria-label="Copy key">
                        <Icon name="copy" size={13} />
                      </button>
                    </td>
                    <td className="num">{k.created_at}</td>
                    <td className="num">{k.last_used_at || '—'}</td>
                    <td className="key-actions">
                      <button className="btn btn-danger btn-sm" type="button">Revoke</button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>

      {/* Theme */}
      <section className="panel settings-section">
        <div className="settings-section-cap mono-label">04 / Theme</div>
        <div className="settings-theme">
          <div className="settings-theme-copy">
            <span className="mono-label">Interface Theme</span>
            <p>Dark (carbon) is the default. Light is blueprint-paper. Preference is per-browser.</p>
          </div>
          <ThemeToggle />
        </div>
      </section>
    </div>
  );
}
