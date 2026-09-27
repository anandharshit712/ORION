// ORION — SettingsSection
//
// Grouped instrument panels per docs/UI_DESIGN.md §11.4: Profile, Organisation,
// API Keys, Theme. Closes one of the two dashboard sections that still rendered
// the ComingSoon panel, over admin APIs that have existed since P1.1.
//
// The part that needs care is the API key. `POST /api/keys/` returns the
// plaintext exactly once and never again — same contract as a webhook secret.
// So the UI has to be honest about that: the key is shown in a panel that says
// it will not be shown again, with a copy button, and it disappears on the next
// action rather than lingering on screen. A "copy" that silently failed would
// lock someone out of a key they cannot re-read, so the button reports whether
// it worked.

import { useState } from 'react';
import { api } from '../../services/api';
import { useApiData, asList } from '../../hooks/useApiData';
import { useAuth } from '../../context/AuthContext';
import { useTheme } from '../../theme/ThemeContext';
import Icon from '../common/Icon';
import DataStates from './DataStates';
import './SettingsSection.css';

function when(value) {
  if (!value) return '—';
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? '—' : d.toISOString().slice(0, 16).replace('T', ' ');
}

/** The plaintext key, shown once. */
function NewKeyPanel({ secret, onDismiss }) {
  const [copied, setCopied] = useState(null);

  async function copy() {
    try {
      await navigator.clipboard.writeText(secret);
      setCopied(true);
    } catch {
      // Clipboard access is denied outside a secure context and in some
      // browsers. Saying so beats a button that looks like it worked — this
      // value cannot be read again.
      setCopied(false);
    }
  }

  return (
    <div className="settings-newkey panel panel--live">
      <span className="mono-label">New API key — shown once</span>
      <p className="settings-newkey__warn">
        This is the only time ORION will show this key. Copy it now; the server
        stores only a hash.
      </p>
      <code className="settings-newkey__value">{secret}</code>
      <div className="settings-newkey__actions">
        <button type="button" className="btn btn-primary btn-sm" onClick={copy}>
          <Icon name="copy" size={14} /> Copy
        </button>
        <button type="button" className="btn btn-ghost btn-sm" onClick={onDismiss}>
          Dismiss
        </button>
        {copied === true && <span className="settings-newkey__ok">Copied</span>}
        {copied === false && (
          <span className="settings-newkey__fail">
            Could not copy — select the key and copy it by hand
          </span>
        )}
      </div>
    </div>
  );
}

export default function SettingsSection() {
  const { user } = useAuth();
  const { theme, setTheme } = useTheme();

  const org = useApiData(() => api.getOrg(), []);
  const keys = useApiData(() => api.listApiKeys(), []);

  const [label, setLabel] = useState('');
  const [secret, setSecret] = useState(null);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState(null);

  const keyList = asList(keys.data, 'keys');

  async function createKey(event) {
    event.preventDefault();
    if (!label.trim()) return;
    setBusy(true);
    setActionError(null);
    try {
      const created = await api.createApiKey(label.trim());
      setSecret(created.plaintext);
      setLabel('');
      keys.refresh();
    } catch (e) {
      setActionError(e?.message || 'Could not create the key');
    } finally {
      setBusy(false);
    }
  }

  async function revoke(keyId) {
    setBusy(true);
    setActionError(null);
    try {
      await api.revokeApiKey(keyId);
      keys.refresh();
    } catch (e) {
      setActionError(e?.message || 'Could not revoke the key');
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="settings-section">
      <div className="section-bar">
        <span className="mono-label">Settings · profile, organisation, access</span>
      </div>

      <div className="settings-grid">
        <div className="panel settings-panel">
          <span className="mono-label">Profile</span>
          <dl className="settings-rows">
            <div>
              <dt>Username</dt>
              <dd>{user?.username || '—'}</dd>
            </div>
            <div>
              <dt>Email</dt>
              <dd>{user?.email || '—'}</dd>
            </div>
            <div>
              <dt>Role</dt>
              <dd>{user?.role || '—'}</dd>
            </div>
            <div>
              <dt>Verified</dt>
              <dd>
                <span className={`chip chip--${user?.email_verified ? 'pass' : 'fail'}`}>
                  {user?.email_verified ? 'yes' : 'no'}
                </span>
              </dd>
            </div>
          </dl>
        </div>

        <div className="panel settings-panel">
          <span className="mono-label">Organisation</span>
          <DataStates
            loading={org.loading}
            error={org.error}
            isEmpty={!org.loading && !org.error && !org.data}
            onRetry={org.refresh}
            loadingRows={4}
            loadingLabel="Loading organisation"
            emptyLabel="No organisation"
            emptyHint="This account is not attached to an organisation."
          >
            <dl className="settings-rows">
              <div>
                <dt>Name</dt>
                <dd>{org.data?.name}</dd>
              </div>
              <div>
                <dt>Slug</dt>
                <dd className="settings-rows__id">{org.data?.slug}</dd>
              </div>
              <div>
                <dt>Plan</dt>
                <dd>{org.data?.plan}</dd>
              </div>
              <div>
                <dt>Run credits</dt>
                <dd className="num">
                  {/* -1 is UNLIMITED_CREDITS. Rendering it as "-1" reads as a
                      negative balance, which is the opposite of what it means. */}
                  {org.data?.run_credits === -1 ? 'unlimited' : org.data?.run_credits}
                </dd>
              </div>
            </dl>
          </DataStates>
        </div>

        <div className="panel settings-panel">
          <span className="mono-label">Theme</span>
          <p className="settings-hint">
            Stored in this browser only, under <code>orion-theme</code>. Dark is the
            default.
          </p>
          <div className="settings-theme">
            {['dark', 'light'].map((option) => (
              <button
                key={option}
                type="button"
                className={`btn btn-sm ${theme === option ? 'btn-primary' : 'btn-ghost'}`}
                onClick={() => setTheme(option)}
                aria-pressed={theme === option}
              >
                {option}
              </button>
            ))}
          </div>
        </div>

        <div className="panel settings-panel settings-panel--wide">
          <span className="mono-label">
            API keys <span className="num">{keyList.length}</span>
          </span>
          <p className="settings-hint">
            For the SDK and CLI, which authenticate with{' '}
            <code>Authorization: Bearer</code> rather than the browser session.
          </p>

          {secret && <NewKeyPanel secret={secret} onDismiss={() => setSecret(null)} />}

          <form className="settings-keyform" onSubmit={createKey}>
            <label className="field">
              <span className="mono-label">Label</span>
              <input
                type="text"
                value={label}
                maxLength={128}
                placeholder="ci-pipeline"
                onChange={(e) => setLabel(e.target.value)}
              />
            </label>
            <button
              type="submit"
              className="btn btn-primary btn-sm"
              disabled={busy || !label.trim()}
            >
              <Icon name="key" size={14} /> Create key
            </button>
          </form>

          {actionError && (
            <p className="settings-error" role="alert">
              {actionError}
            </p>
          )}

          <DataStates
            loading={keys.loading}
            error={keys.error}
            isEmpty={keyList.length === 0}
            onRetry={keys.refresh}
            loadingRows={3}
            loadingLabel="Loading API keys"
            emptyLabel="No API keys"
            emptyHint="Create one to use the orion CLI or the Python SDK."
          >
            <table className="data-table">
              <thead>
                <tr>
                  <th>Label</th>
                  <th>Prefix</th>
                  <th>Created</th>
                  <th>Last used</th>
                  <th>Status</th>
                  <th aria-label="Actions" />
                </tr>
              </thead>
              <tbody>
                {keyList.map((k) => {
                  const revoked = Boolean(k.revoked_at);
                  return (
                    <tr key={k.id}>
                      <td>{k.label}</td>
                      <td className="settings-rows__id">{k.key_prefix}…</td>
                      <td>{when(k.created_at)}</td>
                      {/* Never used is a fact worth showing: a key nobody has
                          used is one nobody will miss when it is revoked. */}
                      <td>{k.last_used_at ? when(k.last_used_at) : 'never'}</td>
                      <td>
                        <span className={`chip chip--${revoked ? 'fail' : 'pass'}`}>
                          {revoked ? 'revoked' : 'active'}
                        </span>
                      </td>
                      <td>
                        {!revoked && (
                          <button
                            type="button"
                            className="btn btn-danger btn-sm"
                            onClick={() => revoke(k.id)}
                            disabled={busy}
                          >
                            Revoke
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </DataStates>
        </div>
      </div>
    </section>
  );
}
