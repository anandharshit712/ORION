// ORION — PlaybackControls  (docs/UI_DESIGN.md §11.5)
//
// Transport bar for stored-frame replay: play/pause, step, scrub, speed, and
// jump-to-event. Previously markup only; wired here for Phase 2.5.
//
// The scrub is a real `<input type="range">` rather than a styled div. A
// custom track would need pointer capture, touch handling and arrow-key
// support written by hand, and a timeline nobody can drive from the keyboard
// fails the accessibility bar in §10 — the native control has all of it.
//
// Jump-to-event markers come from the server (`event_markers`), not from
// re-deriving them here, so the viewer and any other client agree on which
// frame the collision happened at.

import Icon from '../common/Icon';
import './PlaybackControls.css';

const SPEEDS = [0.1, 0.5, 1, 2, 5];

/** Marker keys the server may send, in the order they matter to a reviewer. */
const MARKER_LABELS = {
  collision: 'Collision',
  off_road: 'Off road',
  min_ttc: 'Min TTC',
  hard_brake: 'Hard brake',
  first_brake: 'First brake',
};

export default function PlaybackControls({
  playing = false,
  onTogglePlay,
  index = 0,
  frameCount = 0,
  onSeek,
  speed = 1,
  onSpeedChange,
  markers = {},
  simTime = 0,
}) {
  const last = Math.max(0, frameCount - 1);
  const pct = last > 0 ? (index / last) * 100 : 0;

  // Only markers the server actually located. A disabled "Collision" button on
  // a run that never collided is noise.
  const jumps = Object.entries(markers).filter(
    ([, frame]) => typeof frame === 'number' && frame >= 0 && frame <= last,
  );

  const step = (delta) => onSeek?.(Math.min(last, Math.max(0, index + delta)));

  return (
    <div className="panel playback-bar" role="group" aria-label="Playback controls">
      <button
        className="playback-btn"
        type="button"
        aria-label="Step back one frame"
        onClick={() => step(-1)}
        disabled={index <= 0}
      >
        ‹
      </button>

      <button
        className="playback-btn playback-btn--primary"
        type="button"
        aria-label={playing ? 'Pause' : 'Play'}
        onClick={onTogglePlay}
        disabled={frameCount === 0}
      >
        {playing ? '❚❚' : <Icon name="play" size={16} />}
      </button>

      <button
        className="playback-btn"
        type="button"
        aria-label="Step forward one frame"
        onClick={() => step(1)}
        disabled={index >= last}
      >
        ›
      </button>

      <div className="playback-scrub">
        <input
          className="playback-range"
          type="range"
          min={0}
          max={last}
          step={1}
          value={index}
          onChange={(e) => onSeek?.(Number(e.target.value))}
          aria-label="Timeline"
          aria-valuetext={`Frame ${index + 1} of ${frameCount}, ${simTime.toFixed(2)} seconds`}
          disabled={frameCount === 0}
        />
        <div className="playback-scrub-track" aria-hidden="true">
          <div className="playback-scrub-fill" style={{ width: `${pct}%` }} />
          {jumps.map(([key, frame]) => (
            <span
              key={key}
              className={`playback-marker playback-marker--${key}`}
              style={{ left: `${last > 0 ? (frame / last) * 100 : 0}%` }}
            />
          ))}
        </div>
      </div>

      <span className="num playback-time">
        {simTime.toFixed(2)}s
      </span>
      <span className="mono-label playback-frame">
        {frameCount ? `${index + 1}/${frameCount}` : '—'}
      </span>

      <div className="playback-speed" role="group" aria-label="Playback speed">
        <span className="mono-label">SPEED</span>
        {SPEEDS.map((s) => (
          <button
            key={s}
            type="button"
            className={`playback-speed-btn ${s === speed ? 'is-active' : ''}`}
            aria-pressed={s === speed}
            onClick={() => onSpeedChange?.(s)}
          >
            {s}×
          </button>
        ))}
      </div>

      {jumps.length > 0 && (
        <div className="playback-jumps" role="group" aria-label="Jump to event">
          {jumps.map(([key, frame]) => (
            <button
              key={key}
              type="button"
              className={`btn btn-ghost btn-sm playback-jump playback-jump--${key}`}
              onClick={() => onSeek?.(frame)}
            >
              {MARKER_LABELS[key] || key}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
