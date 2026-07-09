import { useMemo, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Canvas, useFrame } from '@react-three/fiber';
import { OrbitControls, Grid } from '@react-three/drei';
import * as THREE from 'three';
import { useAuth } from '../../context/AuthContext';
import { useSimulationStream } from '../../hooks/useSimulationStream';
import Icon from '../common/Icon';
import './SimulationViewer.css';

const ROAD_LENGTH = 400;
const ROAD_WIDTH = 14;   // 2 lanes × 3.5m default × safety margin
const LANE_WIDTH = 3.5;

// ── Mission Control palette (3D materials only — CSS vars can't reach three.js).
//    Allowed hardcoded token hexes per design spec §11.5.
// Reserved hazard/marker hexes (used once TTC zones / traces land): fail #FF5C5C,
// text-white #E7ECF5 — both on the allowed 3D-material list.
const C_CARBON = '#0A0C10';   // --bg-base   (scene background)
const C_LINE = '#3A4456';     // neutral structural line (road, grid)
const C_CYAN = '#25D3EE';     // accent / lane edge
const C_AMBER = '#F5A623';    // ego vehicle
const C_NPC = '#5A6478';      // neutral grey NPC

// NPCs render neutral grey; the type only affects geometry size, not colour.
const NPC_COLOUR = C_NPC;

function Road() {
  const markings = useMemo(() => {
    const segments = [];
    const dashLen = 3;
    const gap = 6;
    for (let x = -ROAD_LENGTH / 2; x < ROAD_LENGTH / 2; x += dashLen + gap) {
      segments.push([x, 0, x + dashLen]);
    }
    return segments;
  }, []);

  return (
    <group>
      <mesh rotation={[-Math.PI / 2, 0, 0]} receiveShadow>
        <planeGeometry args={[ROAD_LENGTH, ROAD_WIDTH]} />
        <meshStandardMaterial color={C_CARBON} />
      </mesh>
      {/* centre lane dashes — neutral structural line */}
      {markings.map(([x0, _, x1], i) => (
        <mesh key={i} position={[(x0 + x1) / 2, 0.01, 0]} rotation={[-Math.PI / 2, 0, 0]}>
          <planeGeometry args={[x1 - x0, 0.15]} />
          <meshStandardMaterial color={C_LINE} />
        </mesh>
      ))}
      {/* road edges — cyan accent */}
      <mesh position={[0, 0.011, ROAD_WIDTH / 2]} rotation={[-Math.PI / 2, 0, 0]}>
        <planeGeometry args={[ROAD_LENGTH, 0.2]} />
        <meshStandardMaterial color={C_CYAN} />
      </mesh>
      <mesh position={[0, 0.011, -ROAD_WIDTH / 2]} rotation={[-Math.PI / 2, 0, 0]}>
        <planeGeometry args={[ROAD_LENGTH, 0.2]} />
        <meshStandardMaterial color={C_CYAN} />
      </mesh>
    </group>
  );
}

function Vehicle({ x, y, heading, length = 4.5, width = 2.0, height = 1.5, color = C_AMBER }) {
  const ref = useRef();
  useFrame(() => {
    if (!ref.current) return;
    ref.current.position.x = x;
    ref.current.position.z = -y;      // backend y → threejs -z (xz ground plane)
    ref.current.position.y = height / 2;
    ref.current.rotation.y = -heading; // CCW in backend → CW around three.js Y
  });
  return (
    <mesh ref={ref} castShadow>
      <boxGeometry args={[length, height, width]} />
      <meshStandardMaterial color={color} />
    </mesh>
  );
}

function Scene({ frame }) {
  const ego = frame?.ego;
  const npcs = frame?.npcs ?? [];
  return (
    <>
      <ambientLight intensity={0.6} />
      <directionalLight position={[50, 80, 40]} intensity={0.9} castShadow />
      <Road />
      <Grid
        args={[ROAD_LENGTH, ROAD_LENGTH]}
        position={[0, 0.005, 0]}
        cellColor={C_LINE}
        sectionColor={C_LINE}
        fadeDistance={250}
        infiniteGrid={false}
      />
      {ego && (
        <Vehicle
          x={ego.x}
          y={ego.y}
          heading={ego.heading}
          color={C_AMBER}
        />
      )}
      {npcs.map((n) => (
        <Vehicle
          key={n.id}
          x={n.x}
          y={n.y}
          heading={n.heading}
          color={NPC_COLOUR}
          length={n.type === 'truck' ? 8.0 : n.type === 'pedestrian' ? 0.5 : 4.5}
          width={n.type === 'truck' ? 2.5 : n.type === 'pedestrian' ? 0.5 : 2.0}
          height={n.type === 'pedestrian' ? 1.7 : 1.5}
        />
      ))}
    </>
  );
}

// ── Reticle gauge — circular SVG ring + cardinal ticks + centred mono numeral.
//    Driven by the live composite score (derived display-only from sub-scores).
function ReticleGauge({ value }) {
  const pct = Math.max(0, Math.min(1, value ?? 0));
  const CIRC = 452; // 2πr at r=72
  const offset = CIRC * (1 - pct);
  const numeral = ((value ?? 0) * 100).toFixed(1);
  return (
    <div className="sim-reticle" role="img" aria-label={`Composite score ${numeral}`}>
      <svg viewBox="0 0 200 200">
        <circle cx="100" cy="100" r="86" fill="none" stroke="var(--border-strong)" strokeWidth="1" />
        <circle cx="100" cy="100" r="72" fill="none" stroke="var(--bg-inset)" strokeWidth="10" />
        <circle
          cx="100" cy="100" r="72" fill="none" stroke="var(--amber)" strokeWidth="10"
          strokeLinecap="butt" strokeDasharray={CIRC} strokeDashoffset={offset}
          transform="rotate(-90 100 100)"
        />
        <line x1="100" y1="6" x2="100" y2="20" stroke="var(--tick)" strokeWidth="1.5" />
        <line x1="100" y1="180" x2="100" y2="194" stroke="var(--tick)" strokeWidth="1.5" />
        <line x1="6" y1="100" x2="20" y2="100" stroke="var(--tick)" strokeWidth="1.5" />
        <line x1="180" y1="100" x2="194" y2="100" stroke="var(--tick)" strokeWidth="1.5" />
      </svg>
      <div className="sim-reticle-read">
        <div className="sim-reticle-big num">{numeral}</div>
        <div className="mono-label">Composite</div>
      </div>
    </div>
  );
}

function MetricBar({ label, value }) {
  const pct = Math.round((value ?? 0) * 100);
  const tone = pct >= 80 ? 'pass' : pct >= 60 ? 'warn' : 'fail';
  return (
    <div className="sim-metric">
      <span className="mono-label sim-metric-label">{label}</span>
      <div className="sim-metric-track">
        <div className={`sim-metric-fill sim-metric-fill--${tone}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="num sim-metric-value">{pct}</span>
    </div>
  );
}

function Readout({ label, value, unit, tone }) {
  return (
    <div className="sim-readout">
      <div className="mono-label">{label}</div>
      <div className={`num sim-readout-v${tone ? ` sim-readout-v--${tone}` : ''}`}>
        {value}
        {unit && <span className="sim-readout-unit num">{unit}</span>}
      </div>
    </div>
  );
}

function HUD({ frame, status, latencyRef, runId }) {
  if (!frame) {
    return (
      <div className="panel sim-hud sim-hud-empty">
        <span className="mono-label">Awaiting first frame</span>
        <span className="num sim-hud-status">{status}</span>
      </div>
    );
  }
  const metrics = frame.monitor?.metrics_current ?? {};
  const verdict = frame.monitor?.verdict_so_far ?? 'UNKNOWN';
  const verdictChip = verdict === 'PASS' ? 'chip-pass'
    : verdict === 'FAIL' ? 'chip-fail' : 'chip-queued';

  // Composite is not in the per-tick frame; derive for display only using the
  // documented live-proxy weights (safety .5 / compliance .2 / stability .15 / reactivity .15).
  const composite =
    (metrics.safety_score ?? 0) * 0.5 +
    (metrics.compliance_score ?? 0) * 0.2 +
    (metrics.stability_score ?? 0) * 0.15 +
    (metrics.reactivity_score ?? 0) * 0.15;

  const speedKmh = ((frame.ego?.speed ?? 0) * 3.6).toFixed(1);
  const accelX = frame.ego?.accel_x ?? 0;
  const accelY = frame.ego?.accel_y ?? 0;
  const accelG = (Math.hypot(accelX, accelY) / 9.81).toFixed(2);
  const simTime = ((frame.t_ms ?? 0) / 1000).toFixed(2);

  // No dedicated collision flag in the frame — safety_score == 0 is the proxy.
  const collision = (metrics.safety_score ?? 1) <= 0;

  const latStats = latencyRef.current;
  const avgLatency = latStats.count > 0 ? (latStats.sumMs / latStats.count).toFixed(0) : '—';
  const maxLatency = latStats.count > 0 ? latStats.maxMs.toFixed(0) : '—';

  const events = Array.isArray(frame.events) ? frame.events.slice(-5) : [];

  return (
    <>
      {/* top status strip */}
      <div className="panel sim-statusbar">
        <span className="sim-status-id mono-label">
          RUN <b className="num">{runId}</b>
        </span>
        <span className="sim-status-scn mono-label">{frame.scenario_name || 'SCENARIO'}</span>
        <span className="sim-status-spacer" />
        <span className="sim-status-cell mono-label">
          T <b className="num">{simTime}</b>s
        </span>
        <span className="sim-status-cell mono-label">
          TICK <b className="num">{frame.tick}</b>
        </span>
        <span className="sim-status-rec mono-label">
          <span className="live-dot amber blink" aria-hidden="true" /> REC
        </span>
      </div>

      {/* right telemetry cluster */}
      <div className="panel panel--live sim-cluster">
        <div className="sim-cluster-top">
          <span className="mono-label">Live Telemetry</span>
          <span className="num sim-latency">{avgLatency}/{maxLatency} ms</span>
        </div>
        <ReticleGauge value={composite} />
        <div className="sim-readouts">
          <Readout label="Speed" value={speedKmh} unit="km/h" />
          <Readout label="G-Force" value={accelG} unit="g" tone="cyan" />
          <Readout label="Min TTC" value={(metrics.safety_score ?? 0).toFixed(2)} unit="s" tone="cyan" />
          <Readout
            label="Collision"
            value={collision ? 'YES' : 'NONE'}
            tone={collision ? 'fail' : 'amber'}
          />
        </div>
      </div>

      {/* bottom: metric bars + verdict */}
      <div className="panel sim-bottombar">
        <div className="sim-bars">
          <MetricBar label="Safety" value={metrics.safety_score} />
          <MetricBar label="Compliance" value={metrics.compliance_score} />
          <MetricBar label="Stability" value={metrics.stability_score} />
          <MetricBar label="Reactivity" value={metrics.reactivity_score} />
        </div>
        <div className="sim-verdict-wrap">
          <span className="mono-label">Verdict</span>
          <span className={`chip ${verdictChip} sim-verdict-chip`}>{verdict}</span>
        </div>
      </div>

      {events.length > 0 && (
        <div className="panel sim-events">
          <div className="mono-label sim-events-head">Events</div>
          {events.map((e, i) => (
            <div key={i} className="sim-event">
              <span className="num sim-event-t">{(e.t_ms / 1000).toFixed(2)}s</span>
              <span className="sim-event-type">{e.type}</span>
              {e.detail && <span className="sim-event-detail">{e.detail}</span>}
            </div>
          ))}
        </div>
      )}
    </>
  );
}

export default function SimulationViewer() {
  const { runId } = useParams();
  const { token } = useAuth();
  const navigate = useNavigate();
  const { frame, status, error, latencyRef } = useSimulationStream(runId, token);

  return (
    <div className="sim-viewer">
      <button
        className="btn btn-ghost btn-sm sim-back-btn"
        onClick={() => navigate('/dashboard')}
        title="Back to Dashboard"
      >
        <Icon name="chevron-right" size={14} className="sim-back-icon" />
        Dashboard
      </button>
      <Canvas
        shadows
        camera={{ position: [0, 50, 50], fov: 40 }}
        style={{ background: C_CARBON }}
      >
        <Scene frame={frame} />
        <OrbitControls
          enableDamping
          dampingFactor={0.1}
          target={[frame?.ego?.x ?? 0, 0, -(frame?.ego?.y ?? 0)]}
          maxPolarAngle={Math.PI / 2}
        />
      </Canvas>
      <HUD frame={frame} status={status} latencyRef={latencyRef} runId={runId} />
      {error && (
        <div className="panel sim-error">
          <Icon name="warning" size={14} className="sim-error-icon" />
          <span className="mono-label sim-error-msg">{error}</span>
        </div>
      )}
    </div>
  );
}
