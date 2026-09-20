// ORION — Sidebar
// Dashboard sidebar: numbered nav (Mission Control), credits gauge, user chip.
// See docs/UI_DESIGN.md §9.6. Preserves ids: dashboard-sidebar, sidebar-<key>, sidebar-logout.

import { Link } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import Icon from './Icon';
import './Sidebar.css';

// `ready: false` means the section still renders the ComingSoon panel. Those
// entries stay visible but are not navigable (D-10): letting someone click
// through to an empty page reads as a broken product, while hiding six of seven
// entries would leave a one-item sidebar that reads as a broken install.
// Flip a flag to true in the same change that wires the section up.
const NAV_ITEMS = [
  { key: 'overview', icon: 'overview', label: 'Overview', ready: true },
  { key: 'scenarios', icon: 'scenarios', label: 'Scenarios', ready: false },
  { key: 'runs', icon: 'runs', label: 'Runs', ready: false },
  { key: 'models', icon: 'models', label: 'Models', ready: false },
  { key: 'batches', icon: 'batches', label: 'Batches', ready: false },
  { key: 'compare', icon: 'compare', label: 'Compare', ready: false },
  { key: 'settings', icon: 'settings', label: 'Settings', ready: false },
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
            className={
              `side-item ${active === item.key ? 'active' : ''}` +
              (item.ready ? '' : ' side-item--soon')
            }
            onClick={item.ready ? () => onNavigate(item.key) : undefined}
            disabled={!item.ready}
            id={`sidebar-${item.key}`}
            aria-current={active === item.key ? 'page' : undefined}
            title={item.ready ? undefined : `${item.label} is not available yet`}
          >
            <span className="side-ix">{String(i + 1).padStart(2, '0')}</span>
            <Icon name={item.icon} size={17} />
            <span className="side-label">{item.label}</span>
            {!item.ready && <span className="side-soon mono-label">soon</span>}
          </button>
        ))}
      </nav>

      <div className="side-foot">
        {/* The credits gauge is the route into billing (Phase 1.4). The
            numbered nav above is for dashboard sections; billing is its own
            page, and without this link it had no way in at all. */}
        <Link className="credits panel" to="/billing" id="sidebar-billing">
          <div className="credits-k mono-label">Run Credits</div>
          <div className="credits-v num">{credits != null ? credits.toLocaleString() : '—'}</div>
          <span className="credits-cta mono-label">Manage plan</span>
        </Link>
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
