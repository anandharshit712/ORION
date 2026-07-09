// ORION — TTCWarningZone  [P5]
// Coloured ellipse around ego that turns red when TTC < 2s.
// TODO [P5]: Implement geometry (R3F semi-transparent ground ellipse).
// Palette when implemented (3D material hexes — CSS vars cannot reach three.js):
// hazard fill fail-red #FF5C5C at low opacity per design spec §11.5.

import React from 'react';
import './TTCWarningZone.css';

/**
 * TTCWarningZone
 * Semi-transparent hazard zone around ego; turns fail-red when TTC < 2s.
 */
export default function TTCWarningZone(/* props */) {
  return (
    <div className="sim-overlay-stub">
      <span className="mono-label">TTCWarningZone — not yet implemented [P5]</span>
    </div>
  );
}
