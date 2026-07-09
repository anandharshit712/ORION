import { useState, useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { useTheme } from '../theme/ThemeContext';
import { api } from '../services/api';
import { BUILD_HASH } from '../utils/constants';
import HudBar from '../components/common/HudBar';
import Sidebar from '../components/common/Sidebar';
import Icon from '../components/common/Icon';
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

const pct = (x) => (typeof x === 'number' ? x * 100 : 0);
const fmt = (x) => pct(x).toFixed(1);

// ── Chart palette (recomputed from CSS vars on theme change) ──────────────
function useChartPalette() {
  const { theme } = useTheme();
  return useMemo(() => {
    const v = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
    return {
      amber: v('--amber'), cyan: v('--cyan'),
      grid: v('--border'), axis: v('--text-mute'),
      tooltipBg: v('--bg-elev'), border: v('--border'),
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [theme]);
}

function MetricPanel({ label, value, accent = 'cyan', live = false }) {
  const v = typeof value === 'number' ? value : 0;
  const w = Math.max(0, Math.min(100, v));
  return (
    <div className={`panel metric ${live ? 'panel--live' : ''}`}>
      <div className="metric-top"><span className="mono-label">{label}</span></div>
      <div className={`metric-val num ${accent === 'amber' ? 'is-amber' : ''}`}>{v.toFixed(1)}</div>
      <div className="metric-bar"><i className={accent} style={{ width: `${w}%` }} /></div>
    </div>
  );
}

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
    <div className="panel panel--live launch-panel" id="launch-sim-panel">
      <div className="launch-head">
        <span className="mono-label">Launch Live Simulation</span>
        <span className="launch-sub">Streams 50 Hz tick frames to the 3D viewer</span>
      </div>
      <div className="launch-grid">
        <label className="launch-field">
          <span className="mono-label">Scenario</span>
          <input list="scenario-presets" value={scenarioPath}
            onChange={(e) => setScenarioPath(e.target.value)} disabled={launching} />
          <datalist id="scenario-presets">
            {SCENARIO_PRESETS.map((p) => <option key={p} value={p} />)}
          </datalist>
        </label>
        <label className="launch-field">
          <span className="mono-label">Model</span>
          <select value={modelName} onChange={(e) => setModelName(e.target.value)} disabled={launching}>
            {MODELS.map((m) => <option key={m} value={m}>{m}</option>)}
          </select>
        </label>
        <label className="launch-field">
          <span className="mono-label">Seed</span>
          <input type="number" value={seed} onChange={(e) => setSeed(e.target.value)} disabled={launching} />
        </label>
        <label className="launch-field">
          <span className="mono-label">Tick (s)</span>
          <input type="number" step="0.005" min="0" value={tickInterval}
            onChange={(e) => setTickInterval(e.target.value)} disabled={launching} />
        </label>
        <button className="btn btn-primary launch-btn" onClick={onLaunch}
          disabled={launching || !scenarioPath} id="launch-sim-button">
          {launching ? 'Starting…' : <><Icon name="play" size={15} /> Launch</>}
        </button>
      </div>
      {err && <div className="launch-error"><Icon name="warning" size={14} /> {err}</div>}
    </div>
  );
}

function verdict(r) {
  if (r.collision_occurred) return 'fail';
  const c = pct(r.composite_score);
  return c >= 80 ? 'pass' : 'fail';
}

function ComingSoon({ view }) {
  return (
    <div className="panel empty-state">
      <span className="mono-label">{view} · not yet wired</span>
      <p>This section will render here. The visual language is ready; data wiring is tracked separately.</p>
    </div>
  );
}

export default function DashboardPage() {
  const { token } = useAuth();
  const palette = useChartPalette();
  const [view, setView] = useState('overview');
  const [runs, setRuns] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [refreshCount, setRefreshCount] = useState(0);

  useEffect(() => {
    if (!token) return;
    setLoading(true);
    setError(null);
    api.getRuns(token, 50)
      .then((data) => setRuns(Array.isArray(data) ? data : data.runs || []))
      .catch((e) => { setRuns([]); setError(e.message || 'Failed to load runs'); })
      .finally(() => setLoading(false));
  }, [token, refreshCount]);

  const latestRuns = runs.slice(0, 20);
  const avg = (k) => (runs.length ? runs.reduce((s, r) => s + (r[k] || 0), 0) / runs.length * 100 : 0);
  const avgComposite = avg('composite_score');
  const avgSafety = avg('safety_score');
  const avgCompliance = avg('compliance_score');
  const avgStability = avg('stability_score');
  const avgReactivity = avg('reactivity_score');

  const lineData = latestRuns.map((r, i) => ({
    run: i + 1, composite: Number(fmt(r.composite_score)), safety: Number(fmt(r.safety_score)),
  })).reverse();

  const radarData = [
    { metric: 'Safety', value: avgSafety },
    { metric: 'Compliance', value: avgCompliance },
    { metric: 'Stability', value: avgStability },
    { metric: 'Reactivity', value: avgReactivity },
  ];

  const histogramData = [
    { range: '0-20', count: runs.filter((r) => pct(r.composite_score) < 20).length },
    { range: '20-40', count: runs.filter((r) => { const s = pct(r.composite_score); return s >= 20 && s < 40; }).length },
    { range: '40-60', count: runs.filter((r) => { const s = pct(r.composite_score); return s >= 40 && s < 60; }).length },
    { range: '60-80', count: runs.filter((r) => { const s = pct(r.composite_score); return s >= 60 && s < 80; }).length },
    { range: '80-100', count: runs.filter((r) => pct(r.composite_score) >= 80).length },
  ];

  const tooltipStyle = {
    background: palette.tooltipBg, border: `1px solid ${palette.border}`,
    borderRadius: 3, fontFamily: 'var(--ff-mono)', fontSize: 12,
  };
  const axisProps = { stroke: palette.axis, fontSize: 11, fontFamily: 'var(--ff-mono)' };

  const title = view === 'overview' ? 'Dashboard' : view.charAt(0).toUpperCase() + view.slice(1);

  return (
    <div className="dash-shell">
      <a href="#dashboard-main" className="skip-link">Skip to content</a>
      <HudBar seed={42} />
      <div className="dash-body">
        <Sidebar active={view} onNavigate={setView} />
        <main className="dash-main" id="dashboard-main">
          <header className="dash-head">
            <div>
              <h1>{title}</h1>
              <div className="dash-sub num">
                {runs.length} RUNS RECORDED · {loading ? 'LOADING…' : error ? 'ERROR' : 'UP TO DATE'}
              </div>
            </div>
            <div className="dash-actions">
              <button className="btn btn-ghost btn-sm" onClick={() => setRefreshCount((c) => c + 1)} disabled={loading}>
                <Icon name="refresh" size={14} /> Refresh
              </button>
            </div>
          </header>

          {view === 'overview' ? (
            <>
              <LaunchSimPanel />

              {error && !loading && (
                <div className="panel error-state">
                  <span className="mono-label"><Icon name="warning" size={14} /> Error</span>
                  <p>{error}</p>
                  <button className="btn btn-ghost btn-sm" onClick={() => setRefreshCount((c) => c + 1)}>Retry</button>
                </div>
              )}

              <div className="metrics">
                <MetricPanel label="Composite" value={avgComposite} accent="amber" live />
                <MetricPanel label="Safety" value={avgSafety} accent="cyan" />
                <MetricPanel label="Compliance" value={avgCompliance} accent="cyan" />
                <MetricPanel label="Stability" value={avgStability} accent="cyan" />
                <MetricPanel label="Reactivity" value={avgReactivity} accent="cyan" />
              </div>

              <div className="charts">
                <div className="panel chart-card">
                  <h3 className="mono-label">Run History
                    <span className="legend"><b className="a">Composite</b><b className="c">Safety</b></span>
                  </h3>
                  <ResponsiveContainer width="100%" height={250}>
                    <LineChart data={lineData}>
                      <CartesianGrid strokeDasharray="3 3" stroke={palette.grid} />
                      <XAxis dataKey="run" {...axisProps} />
                      <YAxis domain={[0, 100]} {...axisProps} />
                      <Tooltip contentStyle={tooltipStyle} labelStyle={{ color: palette.axis }} />
                      <Line type="monotone" dataKey="composite" stroke={palette.amber} strokeWidth={2} dot={false} />
                      <Line type="monotone" dataKey="safety" stroke={palette.cyan} strokeWidth={2} dot={false} />
                    </LineChart>
                  </ResponsiveContainer>
                </div>

                <div className="panel chart-card">
                  <h3 className="mono-label">Metric Breakdown</h3>
                  <ResponsiveContainer width="100%" height={250}>
                    <RadarChart data={radarData}>
                      <PolarGrid stroke={palette.grid} />
                      <PolarAngleAxis dataKey="metric" stroke={palette.axis} fontSize={11} fontFamily="var(--ff-mono)" />
                      <PolarRadiusAxis domain={[0, 100]} tick={false} axisLine={false} />
                      <Radar dataKey="value" stroke={palette.amber} fill={palette.amber} fillOpacity={0.18} strokeWidth={2} />
                    </RadarChart>
                  </ResponsiveContainer>
                </div>

                <div className="panel chart-card">
                  <h3 className="mono-label">Score Distribution</h3>
                  <ResponsiveContainer width="100%" height={250}>
                    <BarChart data={histogramData}>
                      <CartesianGrid strokeDasharray="3 3" stroke={palette.grid} />
                      <XAxis dataKey="range" {...axisProps} />
                      <YAxis {...axisProps} allowDecimals={false} />
                      <Tooltip contentStyle={tooltipStyle} cursor={{ fill: palette.grid }} />
                      <Bar dataKey="count" fill={palette.cyan} radius={[2, 2, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </div>

              <div className="panel table-card">
                <div className="table-cap mono-label">Recent Runs · /api/runs</div>
                <div className="table-wrap">
                  <table className="data-table" id="runs-table">
                    <thead>
                      <tr>
                        <th>ID</th><th>Model</th><th>Composite</th><th>Safety</th>
                        <th>Comply</th><th>Stable</th><th>React</th><th>Verdict</th>
                      </tr>
                    </thead>
                    <tbody>
                      {loading ? (
                        <tr><td colSpan={8} className="table-empty">Loading runs…</td></tr>
                      ) : latestRuns.length === 0 ? (
                        <tr><td colSpan={8} className="table-empty">No runs yet — launch an evaluation above.</td></tr>
                      ) : (
                        latestRuns.map((r) => {
                          const v = verdict(r);
                          return (
                            <tr key={r.run_id || r.id}>
                              <td className="t-id" title={r.run_id || r.id}>#{(r.run_id || r.id || '').slice(0, 8)}</td>
                              <td className="t-model">{r.model_name}</td>
                              <td className="t-score">{fmt(r.composite_score)}</td>
                              <td>{fmt(r.safety_score)}</td>
                              <td>{fmt(r.compliance_score)}</td>
                              <td>{fmt(r.stability_score)}</td>
                              <td>{fmt(r.reactivity_score)}</td>
                              <td><span className={`chip chip-${v}`}>{v}</span></td>
                            </tr>
                          );
                        })
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            </>
          ) : (
            <ComingSoon view={view} />
          )}
        </main>
      </div>
      <footer className="dash-foot">
        <span className="amb">ORION//AREP</span>
        <span>DETERMINISTIC · dt=0.02s · SEED-PINNED</span>
        <span>BUILD {BUILD_HASH}</span>
        <span>© 2026 BEAMHASH</span>
      </footer>
    </div>
  );
}
