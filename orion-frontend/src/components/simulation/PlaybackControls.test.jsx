// Playback transport (Phase 2.5).
//
// Test what fails silently. A scrub that looks draggable but is not keyboard
// operable, a jump-to-collision that points at the wrong frame, or a marker
// rendered for an event that never happened — none of those look broken on
// screen, and the last one would tell a reviewer a clean run crashed.

import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

import PlaybackControls from './PlaybackControls';

const base = {
  frameCount: 100,
  index: 10,
  simTime: 0.2,
  markers: { collision: 87, min_ttc: 40 },
};

describe('PlaybackControls', () => {
  it('drives the timeline with a real range input, so the keyboard works', () => {
    // A styled div would need pointer capture and arrow keys written by hand,
    // and docs/UI_DESIGN.md §10 requires every action be reachable without a
    // mouse.
    const onSeek = vi.fn();
    render(<PlaybackControls {...base} onSeek={onSeek} />);

    const slider = screen.getByRole('slider', { name: /timeline/i });
    expect(slider).toHaveAttribute('max', '99');

    fireEvent.change(slider, { target: { value: '42' } });
    expect(onSeek).toHaveBeenCalledWith(42);
  });

  it('announces position as time and frame, not as a bare number', () => {
    render(<PlaybackControls {...base} />);
    expect(screen.getByRole('slider')).toHaveAttribute(
      'aria-valuetext',
      expect.stringContaining('Frame 11 of 100'),
    );
  });

  it('jumps to the exact frame the server located the event at', () => {
    // Re-deriving markers client-side would let the viewer and the report
    // disagree about when the collision happened.
    const onSeek = vi.fn();
    render(<PlaybackControls {...base} onSeek={onSeek} />);

    fireEvent.click(screen.getByRole('button', { name: /collision/i }));
    expect(onSeek).toHaveBeenCalledWith(87);
  });

  it('offers no jump for an event that did not happen', () => {
    // The server sends null for a marker it could not locate. A disabled
    // "Collision" button on a clean run is worse than noise — it implies one.
    render(<PlaybackControls {...base} markers={{ collision: null, min_ttc: 40 }} />);

    expect(screen.queryByRole('button', { name: /collision/i })).toBeNull();
    expect(screen.getByRole('button', { name: /min ttc/i })).toBeInTheDocument();
  });

  it('ignores a marker pointing past the end of the recording', () => {
    // Truncated frames plus a marker from the full run would scrub to nowhere.
    render(<PlaybackControls {...base} frameCount={50} markers={{ collision: 87 }} />);
    expect(screen.queryByRole('button', { name: /collision/i })).toBeNull();
  });

  it('steps one frame at a time and stops at the ends', () => {
    const onSeek = vi.fn();
    const { rerender } = render(
      <PlaybackControls {...base} index={0} onSeek={onSeek} />,
    );

    expect(screen.getByRole('button', { name: /step back/i })).toBeDisabled();

    fireEvent.click(screen.getByRole('button', { name: /step forward/i }));
    expect(onSeek).toHaveBeenCalledWith(1);

    rerender(<PlaybackControls {...base} index={99} onSeek={onSeek} />);
    expect(screen.getByRole('button', { name: /step forward/i })).toBeDisabled();
  });

  it('shows play or pause according to state, not both', () => {
    const { rerender } = render(<PlaybackControls {...base} playing={false} />);
    expect(screen.getByRole('button', { name: /^play$/i })).toBeInTheDocument();

    rerender(<PlaybackControls {...base} playing />);
    expect(screen.getByRole('button', { name: /^pause$/i })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^play$/i })).toBeNull();
  });

  it('marks the active speed so 5× is not mistaken for real time', () => {
    const onSpeedChange = vi.fn();
    render(<PlaybackControls {...base} speed={5} onSpeedChange={onSpeedChange} />);

    expect(screen.getByRole('button', { name: '5×' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
    expect(screen.getByRole('button', { name: '1×' })).toHaveAttribute(
      'aria-pressed',
      'false',
    );

    fireEvent.click(screen.getByRole('button', { name: '0.5×' }));
    expect(onSpeedChange).toHaveBeenCalledWith(0.5);
  });

  it('disables transport when there is nothing to play', () => {
    render(<PlaybackControls {...base} frameCount={0} index={0} />);
    expect(screen.getByRole('button', { name: /^play$/i })).toBeDisabled();
    expect(screen.getByRole('slider')).toBeDisabled();
  });
});
