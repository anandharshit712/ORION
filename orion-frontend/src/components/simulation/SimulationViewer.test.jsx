import { describe, expect, it } from 'vitest';
import { laneRibbon } from './SimulationViewer';

// A flipped normal draws every lane on the wrong side of its centreline and
// looks plausible doing it, so the side is pinned here.
describe('laneRibbon', () => {
  it('puts the left edge at +y (three.js -z) for a lane running along +x', () => {
    const { left, right, index } = laneRibbon([[0, 0], [10, 0], [20, 0]], 4);
    expect(left[1][0]).toBeCloseTo(10);
    expect(left[1][2]).toBeCloseTo(-2);
    expect(right[1][2]).toBeCloseTo(2);
    expect(index.length).toBe(12); // two quads, two triangles each
  });

  it('follows a turn: a lane running along +y has its left edge at -x', () => {
    const { left } = laneRibbon([[0, 0], [0, 10]], 3.5);
    expect(left[0][0]).toBeCloseTo(-1.75);
  });
});
