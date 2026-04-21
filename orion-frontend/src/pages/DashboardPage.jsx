import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { api } from '../services/api';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, RadarChart, Radar, PolarGrid,
  PolarAngleAxis, PolarRadiusAxis, BarChart, Bar,
} from 'recharts';
import './DashboardPage.css';

const MODELS = ['EmergencyBrake', 'ConstantAction', 'SimpleLaneKeep', 'Random'];
const SCENARIO_PRESETS = [
  'scenarios/basic/straight_road_lead_vehicle.yaml',
  'scenarios/basic/straight_road_empty.yaml',
  'scenarios/lon/LON-003_emergency_stop.yaml',
];

function LaunchSimPanel() {
  const { token } = useAuth();
  const navigate = useNavigate();
  const [scenarioPath, setScenarioPath] = useState(SCENARIO_PRESETS[0]);
  const [modelName, setModelName] = useState('EmergencyBrake');
  const [seed, setSeed] = useState(42);
  const [tickInterval, setTickInterval] = useState(0.02);
  const [launching, setLaunching] = useState(false);
  const [err, setErr] = useState(null);

  const onLaunch = async () => {
    setLaunching(true);
    setErr(null);
    try {
      const res = await api.startRun(token, scenarioPath, modelName, Number(seed), Number(tickInterval));
      navigate(`/simulation/${res.run_id}`);
    } catch (e) {
      setErr(e.message || 'Failed to start run');
    } finally {
      setLaunching(false);
    }
  };

  return (
    <div className="glass-card launch-sim-panel" id="launch-sim-panel">
      <div className="launch-sim-header">
        <h3 className="chart-title">Launch Live Simulation</h3>
        <span className="launch-sim-sub">Streams 50 Hz tick frames to the 3D viewer.</span>
      </div>
      <div className="launch-sim-grid">
        <label className="launch-sim-field">
          <span>Scenario</span>
          <input
            list="scenario-presets"
            value={scenarioPath}
            onChange={(e) => setScenarioPath(e.target.value)}
            disabled={launching}
          />
          <datalist id="scenario-presets">
            {SCENARIO_PRESETS.map((p) => <option key={p} value={p} />)}
          </datalist>
        </label>
        <label className="launch-sim-field">
          <span>Model</span>
          <select
            value={modelName}
            onChange={(e) => setModelName(e.target.value)}
            disabled={launching}
          >
            {MODELS.map((m) => <option key={m} value={m}>{m}</option>)}
          </select>
        </label>
        <label className="launch-sim-field">
          <span>Seed</span>
          <input
            type="number"
            value={seed}
            onChange={(e) => setSeed(e.target.value)}
            disabled={launching}
          />
        </label>
        <label className="launch-sim-field">
          <span>Tick interval (s)</span>
          <input
            type="number"
            step="0.005"
            min="0"
            value={tickInterval}
            onChange={(e) => setTickInterval(e.target.value)}
            disabled={launching}
          />
        </label>
        <button
          className="btn btn-primary launch-sim-btn"
          onClick={onLaunch}
          disabled={launching || !scenarioPath}
          id="launch-sim-button"
        >
          {launching ? 'Starting…' : '▶  Launch'}
        </button>
      </div>
      {err && <div className="launch-sim-error">{err}</div>}
    </div>
  );
}

function MetricCard({ label, value, color, icon }) {
  const score = typeof value === 'number' ? value : 0;
  const circumference = 2 * Math.PI * 40;
  const offset = circumference - (score / 100) * circumference;

  return (
    <div className="metric-card glass-card">
      <div className="metric-ring">
        <svg viewBox="0 0 100 100" className="metric-svg">
          <circle cx="50" cy="50" r="40" fill="none" stroke="rgba(255,255,255,0.05)" strokeWidth="6" />
          <circle
            cx="50" cy="50" r="40" fill="none"
            stroke={color}
            strokeWidth="6"
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={offset}
            transform="rotate(-90 50 50)"
            style={{ transition: 'stroke-dashoffset 1s ease' }}
          />
        </svg>
        <span className="metric-value">{score.toFixed(1)}</span>
      </div>
      <div className="metric-info">
        <span className="metric-icon">{icon}</span>
        <span className="metric-label">{label}</span>
      </div>
    </div>
  );
}

function Sidebar({ active, onNavigate }) {
  const { user, logout } = useAuth();
  const items = [
    { key: 'overview', icon: '📊', label: 'Overview' },
    { key: 'scenarios', icon: '🗺️', label: 'Scenarios' },
    { key: 'runs', icon: '🏁', label: 'Runs' },
    { key: 'models', icon: '🤖', label: 'Models' },
    { key: 'settings', icon: '⚙️', label: 'Settings' },
  ];

  return (
    <aside className="dashboard-sidebar" id="dashboard-sidebar">
      <div className="sidebar-brand">
        <span className="brand-icon">◆</span>
        <span className="brand-text">ORION</span>
      </div>
      <nav className="sidebar-nav">
        {items.map(item => (
          <button
            key={item.key}
            className={`sidebar-item ${active === item.key ? 'active' : ''}`}
            onClick={() => onNavigate(item.key)}
            id={`sidebar-${item.key}`}
          >
            <span className="sidebar-icon">{item.icon}</span>
            <span>{item.label}</span>
          </button>
        ))}
      </nav>
      <div className="sidebar-user">
        <div className="sidebar-user-info">
          <span className="sidebar-user-name">{user?.username || 'User'}</span>
          <span className="sidebar-user-email">{user?.email || ''}</span>
        </div>
        <button className="btn btn-ghost sidebar-logout" onClick={logout} id="sidebar-logout">⏻</button>
      </div>
    </aside>
  );
}

export default function DashboardPage() {
  const { token } = useAuth();
  const [view, setView] = useState('overview');
  const [runs, setRuns] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshCount, setRefreshCount] = useState(0);

  useEffect(() => {
    if (!token) return;
    setLoading(true);
    api.getRuns(token, 50)
      .then(data => setRuns(Array.isArray(data) ? data : data.runs || []))
      .catch(() => setRuns([]))
      .finally(() => setLoading(false));
  }, [token, refreshCount]);

  // Compute aggregates
  const latestRuns = runs.slice(0, 20);
  const avgComposite = runs.length ? runs.reduce((s, r) => s + (r.composite_score || 0), 0) / runs.length * 100 : 0;
  const avgSafety = runs.length ? runs.reduce((s, r) => s + (r.safety_score || 0), 0) / runs.length * 100 : 0;
  const avgCompliance = runs.length ? runs.reduce((s, r) => s + (r.compliance_score || 0), 0) / runs.length * 100 : 0;
  const avgStability = runs.length ? runs.reduce((s, r) => s + (r.stability_score || 0), 0) / runs.length * 100 : 0;
  const avgReactivity = runs.length ? runs.reduce((s, r) => s + (r.reactivity_score || 0), 0) / runs.length * 100 : 0;

  const lineData = latestRuns.map((r, i) => ({
    run: i + 1,
    composite: ((r.composite_score || 0) * 100).toFixed(1),
    safety: ((r.safety_score || 0) * 100).toFixed(1),
  })).reverse();

  const radarData = [
    { metric: 'Safety', value: avgSafety },
    { metric: 'Compliance', value: avgCompliance },
    { metric: 'Stability', value: avgStability },
    { metric: 'Reactivity', value: avgReactivity },
  ];

  const histogramData = [
    { range: '0-20', count: runs.filter(r => (r.composite_score || 0) * 100 < 20).length },
    { range: '20-40', count: runs.filter(r => { const s = (r.composite_score || 0) * 100; return s >= 20 && s < 40; }).length },
    { range: '40-60', count: runs.filter(r => { const s = (r.composite_score || 0) * 100; return s >= 40 && s < 60; }).length },
    { range: '60-80', count: runs.filter(r => { const s = (r.composite_score || 0) * 100; return s >= 60 && s < 80; }).length },
    { range: '80-100', count: runs.filter(r => (r.composite_score || 0) * 100 >= 80).length },
  ];

  return (
    <div className="dashboard-layout">
      <Sidebar active={view} onNavigate={setView} />
      <main className="dashboard-main" id="dashboard-main">
        <header className="dashboard-header">
          <div>
            <h1 className="dashboard-title">
              {view === 'overview' ? 'Dashboard' : view.charAt(0).toUpperCase() + view.slice(1)}
            </h1>
            <p className="dashboard-subtitle">
              {runs.length} runs recorded • {loading ? 'Loading…' : 'Up to date'}
            </p>
          </div>
          <button
            className="btn btn-ghost"
            onClick={() => setRefreshCount(c => c + 1)}
            disabled={loading}
            title="Refresh"
            style={{ fontSize: '1.1rem' }}
          >
            {loading ? '⏳' : '↻'} Refresh
          </button>
        </header>

        {view === 'overview' && (
          <>
            <LaunchSimPanel />

            {/* Metric Cards */}
            <div className="metrics-row">
              <MetricCard label="Composite" value={avgComposite} color="#6c63ff" icon="◆" />
              <MetricCard label="Safety" value={avgSafety} color="#34d399" icon="🛡️" />
              <MetricCard label="Compliance" value={avgCompliance} color="#60a5fa" icon="📋" />
              <MetricCard label="Stability" value={avgStability} color="#fbbf24" icon="⚖️" />
              <MetricCard label="Reactivity" value={avgReactivity} color="#f87171" icon="⚡" />
            </div>

            {/* Charts */}
            <div className="charts-grid">
              <div className="glass-card chart-card">
                <h3 className="chart-title">Run History</h3>
                <ResponsiveContainer width="100%" height={260}>
                  <LineChart data={lineData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                    <XAxis dataKey="run" stroke="#6b7280" fontSize={12} />
                    <YAxis stroke="#6b7280" fontSize={12} domain={[0, 100]} />
                    <Tooltip
                      contentStyle={{ background: '#1a1a2e', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 8 }}
                      labelStyle={{ color: '#9ca3af' }}
                    />
                    <Line type="monotone" dataKey="composite" stroke="#6c63ff" strokeWidth={2} dot={false} />
                    <Line type="monotone" dataKey="safety" stroke="#34d399" strokeWidth={2} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>

              <div className="glass-card chart-card">
                <h3 className="chart-title">Metric Breakdown</h3>
                <ResponsiveContainer width="100%" height={260}>
                  <RadarChart data={radarData}>
                    <PolarGrid stroke="rgba(255,255,255,0.08)" />
                    <PolarAngleAxis dataKey="metric" stroke="#9ca3af" fontSize={12} />
                    <PolarRadiusAxis domain={[0, 100]} tick={false} />
                    <Radar dataKey="value" stroke="#6c63ff" fill="#6c63ff" fillOpacity={0.2} strokeWidth={2} />
                  </RadarChart>
                </ResponsiveContainer>
              </div>

              <div className="glass-card chart-card">
                <h3 className="chart-title">Score Distribution</h3>
                <ResponsiveContainer width="100%" height={260}>
                  <BarChart data={histogramData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                    <XAxis dataKey="range" stroke="#6b7280" fontSize={12} />
                    <YAxis stroke="#6b7280" fontSize={12} />
                    <Tooltip
                      contentStyle={{ background: '#1a1a2e', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 8 }}
                    />
                    <Bar dataKey="count" fill="#6c63ff" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>

            {/* Recent Runs Table */}
            <div className="glass-card table-card">
              <h3 className="chart-title">Recent Runs</h3>
              <div className="table-wrapper">
                <table className="data-table" id="runs-table">
                  <thead>
                    <tr>
                      <th>ID</th>
                      <th>Model</th>
                      <th>Composite</th>
                      <th>Safety</th>
                      <th>Compliance</th>
                      <th>Stability</th>
                      <th>Reactivity</th>
                      <th>Collision</th>
                    </tr>
                  </thead>
                  <tbody>
                    {latestRuns.length === 0 ? (
                      <tr><td colSpan={8} className="table-empty">No runs yet — start an evaluation from the API.</td></tr>
                    ) : (
                      latestRuns.map(r => (
                        <tr key={r.run_id || r.id}>
                          <td title={r.run_id || r.id}>#{(r.run_id || r.id || '').slice(0, 8)}</td>
                          <td>{r.model_name}</td>
                          <td className="score-cell">{((r.composite_score || 0) * 100).toFixed(1)}</td>
                          <td>{((r.safety_score || 0) * 100).toFixed(1)}</td>
                          <td>{((r.compliance_score || 0) * 100).toFixed(1)}</td>
                          <td>{((r.stability_score || 0) * 100).toFixed(1)}</td>
                          <td>{((r.reactivity_score || 0) * 100).toFixed(1)}</td>
                          <td>{r.collision_occurred ? '💥' : '✅'}</td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </>
        )}

        {view !== 'overview' && (
          <div className="glass-card" style={{ padding: 'var(--space-10)', textAlign: 'center' }}>
            <p className="text-muted" style={{ fontSize: 'var(--font-lg)', color: 'var(--text-muted)' }}>
              {view.charAt(0).toUpperCase() + view.slice(1)} view coming soon.
            </p>
          </div>
        )}
      </main>
    </div>
  );
}
