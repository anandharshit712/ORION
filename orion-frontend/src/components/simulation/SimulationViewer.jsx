import { useMemo, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Canvas, useFrame } from '@react-three/fiber';
import { OrbitControls, Grid } from '@react-three/drei';
import * as THREE from 'three';
import { useAuth } from '../../context/AuthContext';
import { useSimulationStream } from '../../hooks/useSimulationStream';
import './SimulationViewer.css';

const ROAD_LENGTH = 400;
const ROAD_WIDTH = 14;   // 2 lanes × 3.5m default × safety margin
const LANE_WIDTH = 3.5;

const NPC_COLOURS = {
  car: '#ff5757',
  truck: '#ff8a3d',
  motorcycle: '#ffdc5c',
  pedestrian: '#ffde59',
  bicycle: '#ffde59',
  unknown: '#ff9d9d',
};

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
        <meshStandardMaterial color="#2a2a2f" />
      </mesh>
      {markings.map(([x0, _, x1], i) => (
        <mesh key={i} position={[(x0 + x1) / 2, 0.01, 0]} rotation={[-Math.PI / 2, 0, 0]}>
          <planeGeometry args={[x1 - x0, 0.15]} />
          <meshStandardMaterial color="#e8e8e8" />
        </mesh>
      ))}
      <mesh position={[0, 0.011, ROAD_WIDTH / 2]} rotation={[-Math.PI / 2, 0, 0]}>
        <planeGeometry args={[ROAD_LENGTH, 0.2]} />
        <meshStandardMaterial color="#f4f4f4" />
      </mesh>
      <mesh position={[0, 0.011, -ROAD_WIDTH / 2]} rotation={[-Math.PI / 2, 0, 0]}>
        <planeGeometry args={[ROAD_LENGTH, 0.2]} />
        <meshStandardMaterial color="#f4f4f4" />
      </mesh>
    </group>
  );
}

function Vehicle({ x, y, heading, length = 4.5, width = 2.0, height = 1.5, color = '#5aa8ff' }) {
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
        cellColor="#333"
        sectionColor="#444"
        fadeDistance={250}
        infiniteGrid={false}
      />
      {ego && (
        <Vehicle
          x={ego.x}
          y={ego.y}
          heading={ego.heading}
          color="#5aa8ff"
        />
      )}
      {npcs.map((n) => (
        <Vehicle
          key={n.id}
          x={n.x}
          y={n.y}
          heading={n.heading}
          color={NPC_COLOURS[n.type] || NPC_COLOURS.unknown}
          length={n.type === 'truck' ? 8.0 : n.type === 'pedestrian' ? 0.5 : 4.5}
          width={n.type === 'truck' ? 2.5 : n.type === 'pedestrian' ? 0.5 : 2.0}
          height={n.type === 'pedestrian' ? 1.7 : 1.5}
        />
      ))}
    </>
  );
}

function MetricBar({ label, value }) {
  const pct = Math.round((value ?? 0) * 100);
  const tint = pct >= 80 ? '#4ade80' : pct >= 60 ? '#facc15' : '#f87171';
  return (
    <div className="sim-metric">
      <span className="sim-metric-label">{label}</span>
      <div className="sim-metric-track">
        <div
          className="sim-metric-fill"
          style={{ width: `${pct}%`, background: tint }}
        />
      </div>
      <span className="sim-metric-value">{pct}</span>
    </div>
  );
}

function HUD({ frame, status, latencyRef }) {
  if (!frame) {
    return (
      <div className="sim-hud sim-hud-empty">
        Awaiting first frame… ({status})
      </div>
    );
  }
  const metrics = frame.monitor?.metrics_current ?? {};
  const verdict = frame.monitor?.verdict_so_far ?? 'UNKNOWN';
  const verdictClass = verdict === 'PASS' ? 'verdict-pass'
    : verdict === 'FAIL' ? 'verdict-fail' : 'verdict-inconclusive';

  const speedKmh = ((frame.ego?.speed ?? 0) * 3.6).toFixed(1);
  const accelX = frame.ego?.accel_x ?? 0;
  const accelY = frame.ego?.accel_y ?? 0;
  const accelG = (Math.hypot(accelX, accelY) / 9.81).toFixed(2);
  const simTime = ((frame.t_ms ?? 0) / 1000).toFixed(2);

  const latStats = latencyRef.current;
  const avgLatency = latStats.count > 0 ? (latStats.sumMs / latStats.count).toFixed(0) : '—';
  const maxLatency = latStats.count > 0 ? latStats.maxMs.toFixed(0) : '—';

  const events = Array.isArray(frame.events) ? frame.events.slice(-5) : [];

  return (
    <>
      <div className="sim-hud sim-hud-tl">
        <div><span>t</span> {simTime}s</div>
        <div><span>speed</span> {speedKmh} km/h</div>
        <div><span>|a|</span> {accelG} g</div>
        <div><span>tick</span> {frame.tick}</div>
        <div className="sim-hud-muted">
          lat avg {avgLatency}ms · max {maxLatency}ms · {status}
        </div>
      </div>
      <div className="sim-hud sim-hud-tr">
        <MetricBar label="Safety"     value={metrics.safety_score} />
        <MetricBar label="Compliance" value={metrics.compliance_score} />
        <MetricBar label="Stability"  value={metrics.stability_score} />
        <MetricBar label="Reactivity" value={metrics.reactivity_score} />
      </div>
      <div className={`sim-verdict ${verdictClass}`}>{verdict}</div>
      {events.length > 0 && (
        <div className="sim-hud sim-hud-bl">
          {events.map((e, i) => (
            <div key={i} className="sim-event">
              <span>{(e.t_ms / 1000).toFixed(2)}s</span> {e.type} {e.detail || ''}
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
        className="sim-back-btn"
        onClick={() => navigate('/dashboard')}
        title="Back to Dashboard"
      >
        ← Dashboard
      </button>
      <Canvas
        shadows
        camera={{ position: [0, 50, 50], fov: 40 }}
        style={{ background: '#0a0a12' }}
      >
        <Scene frame={frame} />
        <OrbitControls
          enableDamping
          dampingFactor={0.1}
          target={[frame?.ego?.x ?? 0, 0, -(frame?.ego?.y ?? 0)]}
          maxPolarAngle={Math.PI / 2}
        />
      </Canvas>
      <HUD frame={frame} status={status} latencyRef={latencyRef} />
      {error && <div className="sim-error">{error}</div>}
    </div>
  );
}
