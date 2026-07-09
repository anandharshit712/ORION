// ORION — PlaybackControls  [P5]
// Play/pause/speed/scrub timeline bar for replay mode
// TODO [P5]: Wire to replay state (play/pause/scrub/speed handlers).
// Visual frame restyled to the "Mission Control" design system; control logic
// is still a stub (no props consumed yet) — markup only.

import React from 'react';
import Icon from '../common/Icon';
import './PlaybackControls.css';

/**
 * PlaybackControls
 * Transport bar: play/pause · scrub timeline · speed. Amber = active control.
 */
export default function PlaybackControls(/* props */) {
  return (
    <div className="panel playback-bar" role="group" aria-label="Playback controls">
      <button className="playback-btn playback-btn--primary" type="button" aria-label="Play" disabled>
        <Icon name="play" size={16} />
      </button>

      <div className="playback-scrub" aria-hidden="true">
        <div className="playback-scrub-track">
          <div className="playback-scrub-fill" style={{ width: '0%' }} />
        </div>
      </div>

      <span className="num playback-time">0.00s</span>

      <div className="playback-speed" role="group" aria-label="Playback speed">
        <span className="mono-label">SPEED</span>
        <span className="num playback-speed-v">1.0×</span>
      </div>

      <span className="mono-label playback-note">REPLAY — NOT YET IMPLEMENTED [P5]</span>
    </div>
  );
}
