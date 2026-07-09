// ORION — Sidebar
// Dashboard sidebar: numbered nav (Mission Control), credits gauge, user chip.
// See ORION_UI_DESIGN.md §9.6. Preserves ids: dashboard-sidebar, sidebar-<key>, sidebar-logout.

import { useAuth } from '../../context/AuthContext';
import Icon from './Icon';
import './Sidebar.css';

const NAV_ITEMS = [
  { key: 'overview', icon: 'overview', label: 'Overview' },
  { key: 'scenarios', icon: 'scenarios', label: 'Scenarios' },
  { key: 'runs', icon: 'runs', label: 'Runs' },
  { key: 'models', icon: 'models', label: 'Models' },
  { key: 'batches', icon: 'batches', label: 'Batches' },
  { key: 'compare', icon: 'compare', label: 'Compare' },
  { key: 'settings', icon: 'settings', label: 'Settings' },
];

export default function Sidebar({ active, onNavigate }) {
  const { user, logout } = useAuth();
  const credits =
    user?.credits_remaining ??
    user?.organization?.credits_remaining ??
    user?.org?.credits_remaining ??
    null;
  const initial = (user?.username || user?.email || 'U').charAt(0).toUpperCase();

  return (
    <aside className="side" id="dashboard-sidebar">
      <div className="side-brand">
        <span className="side-mark" aria-hidden="true" />
        ORION
      </div>

      <nav className="side-nav" aria-label="Dashboard sections">
        {NAV_ITEMS.map((item, i) => (
          <button
            key={item.key}
            type="button"
            className={`side-item ${active === item.key ? 'active' : ''}`}
            onClick={() => onNavigate(item.key)}
            id={`sidebar-${item.key}`}
            aria-current={active === item.key ? 'page' : undefined}
          >
            <span className="side-ix">{String(i + 1).padStart(2, '0')}</span>
            <Icon name={item.icon} size={17} />
            <span className="side-label">{item.label}</span>
          </button>
        ))}
      </nav>

      <div className="side-foot">
        <div className="credits panel">
          <div className="credits-k mono-label">Run Credits</div>
          <div className="credits-v num">{credits != null ? credits.toLocaleString() : '—'}</div>
        </div>
        <div className="side-user">
          <span className="side-av" aria-hidden="true">{initial}</span>
          <span className="side-user-info">
            <span className="side-user-name">{user?.username || 'Operator'}</span>
            <span className="side-user-email">{user?.email || ''}</span>
          </span>
          <button
            className="side-logout"
            onClick={logout}
            id="sidebar-logout"
            title="Log out"
            aria-label="Log out"
          >
            <Icon name="power" size={16} />
          </button>
        </div>
      </div>
    </aside>
  );
}
