// ORION — RunPage  (docs/UI_DESIGN.md §11.5)
// Route: /dashboard/runs/:runId — stored-frame replay of one completed run.
//
// This closes the last acceptance criterion of Phase 2.5. Both backend modes
// have worked since the frame hash landed; what was missing was somewhere to
// scrub.
//
// It deliberately renders the *same* `Scene` the live viewer renders rather
// than a second one. The whole claim of deterministic replay is that the
// replay looks identical to the run, and two scene implementations would drift
// until it did not.
//
// Frames are stored only for runs that collided or left the road — everything
// else is cheaper to re-simulate from its seed. So a 404 here is the normal
// answer for a clean run, and the empty state says so and offers the replay
// button instead of reading like a fault.

import { useCallback, useEffect, useRef, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { Canvas } from '@react-three/fiber';

import { api } from '../services/api';
import { useApiData } from '../hooks/useApiData';
import Icon from '../components/common/Icon';
import DataStates from '../components/dashboard/DataStates';
import { Scene, HUD } from '../components/simulation/SimulationViewer';
import PlaybackControls from '../components/simulation/PlaybackControls';
import './RunPage.css';

// Frames were recorded at the simulation's fixed timestep. Playback speed is a
// multiple of real time, so 1× replays at the rate it happened.
const DT_MS = 20;

export default function RunPage() {
  const { runId } = useParams();
  const navigate = useNavigate();

  const { data, loading, error, refresh } = useApiData(
    () => api.getRunFrames(runId),
    [runId],
  );

  const [index, setIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [replayError, setReplayError] = useState(null);

  const frames = data?.frames || [];
  const frameCount = frames.length;
  const frame = frames[Math.min(index, Math.max(0, frameCount - 1))] || null;

  // A new run starts at the beginning, paused. Carrying the old index over
  // would land mid-way through a different run.
  useEffect(() => {
    setIndex(0);
    setPlaying(false);
  }, [runId]);

  // setInterval rather than requestAnimationFrame: playback is tied to the
  // simulation's fixed timestep, not to the display's refresh rate, and rAF
  // would replay faster on a 120 Hz monitor than on a 60 Hz one.
  useEffect(() => {
    if (!playing || frameCount === 0) return undefined;

    const id = setInterval(() => {
      setIndex((i) => {
        if (i >= frameCount - 1) {
          setPlaying(false);
          return frameCount - 1;
        }
        return i + 1;
      });
    }, DT_MS / speed);

    return () => clearInterval(id);
  }, [playing, speed, frameCount]);

  const seek = useCallback((next) => {
    setPlaying(false);
    setIndex(next);
  }, []);

  const latencyRef = useRef({ avg: 0, max: 0 });

  async function replayFromSeed() {
    setReplayError(null);
    try {
      const replay = await api.replayRun(runId);
      navigate(`/simulation/${replay.run_id}`);
    } catch (e) {
      setReplayError(e?.message || 'Could not start a replay');
    }
  }

  return (
    <div className="runpage">
      <div className="runpage-head">
        <Link to="/dashboard" className="btn btn-ghost btn-sm">
          <Icon name="chevron-right" size={14} className="flip" /> Dashboard
        </Link>
        <span className="mono-label">
          Run <span className="num">{runId}</span> · stored-frame replay
        </span>
        {data?.reason && <span className="chip chip--fail">{data.reason}</span>}
      </div>

      <DataStates
        loading={loading}
        error={error}
        isEmpty={!loading && !error && frameCount === 0}
        onRetry={refresh}
        loadingRows={6}
        loadingLabel="Loading frames"
        emptyLabel="No stored frames for this run"
        emptyHint="Frames are kept only for runs that collided or left the road. Everything else replays from its seed, which is exact and costs nothing to store."
        emptyAction={
          <button type="button" className="btn btn-primary btn-sm" onClick={replayFromSeed}>
            <Icon name="play" size={14} /> Replay from seed
          </button>
        }
      >
        <>
          <div className="runpage-stage panel panel--live">
            <Canvas camera={{ position: [0, 14, -22], fov: 55 }} dpr={[1, 2]}>
              <Scene frame={frame} />
            </Canvas>
            <HUD frame={frame} status="replay" latencyRef={latencyRef} runId={runId} />
          </div>

          <PlaybackControls
            playing={playing}
            onTogglePlay={() => setPlaying((p) => !p)}
            index={index}
            frameCount={frameCount}
            onSeek={seek}
            speed={speed}
            onSpeedChange={setSpeed}
            markers={data?.markers || {}}
            simTime={frame?.sim_time ?? 0}
          />
        </>
      </DataStates>

      {replayError && (
        <p className="settings-error" role="alert">
          {replayError}
        </p>
      )}
    </div>
  );
}
