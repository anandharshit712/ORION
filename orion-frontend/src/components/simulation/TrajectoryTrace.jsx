// ORION — TrajectoryTrace  [P5]
// Rolling 3s position history as fading R3F line segments.
// TODO [P5]: Implement geometry (R3F <line>/<Line> with a cyan→amber gradient
// per design spec §11.5). Palette when implemented (3D material hexes — CSS
// vars cannot reach three.js): trace start cyan #25D3EE → end amber #F5A623.

import React from 'react';
import './TrajectoryTrace.css';

/**
 * TrajectoryTrace
 * Rolling 3s position history as fading R3F line segments (cyan→amber).
 */
export default function TrajectoryTrace(/* props */) {
  return (
    <div className="sim-overlay-stub">
      <span className="mono-label">TrajectoryTrace — not yet implemented [P5]</span>
    </div>
  );
}
