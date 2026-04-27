// ORION — useReplayStream hook  [Phase 5]
// Fetches all stored tick frames for a completed run and exposes
// playback controls (play/pause, speed, scrub).
// Used by SimulationViewer when in replay mode (vs live streaming mode).

import { useState, useEffect, useRef, useCallback } from 'react';
import api from '../services/api';
import { useAuth } from '../context/AuthContext';

/**
 * useReplayStream(runId)
 *
 * Returns:
 *   frame        — current tick frame object (same shape as live WS frame)
 *   isPlaying    — boolean
 *   speed        — playback speed multiplier (0.1 | 0.5 | 1 | 2 | 5)
 *   progress     — 0.0–1.0 fraction through the replay
 *   totalTicks   — total number of ticks in the run
 *   currentTick  — current tick index
 *   play()       — start playback
 *   pause()      — pause playback
 *   setSpeed(n)  — change speed multiplier
 *   seekTo(tick) — jump to a specific tick index
 *   isLoading    — true while fetching frames from API
 *   error        — error message | null
 */
export function useReplayStream(runId) {
  const { token } = useAuth();
  const [frames, setFrames] = useState([]);
  const [currentTick, setCurrentTick] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  const intervalRef = useRef(null);

  // Fetch all frames on mount
  useEffect(() => {
    if (!runId || !token) return;
    setIsLoading(true);
    setCurrentTick(0);
    setIsPlaying(false);

    // TODO [P5]: Call api.getRunReplay(token, runId) → GET /api/runs/{runId}/replay
    // TODO [P5]: setFrames(data.frames)
    setIsLoading(false);
  }, [runId, token]);

  // Playback loop
  useEffect(() => {
    if (!isPlaying || frames.length === 0) {
      clearInterval(intervalRef.current);
      return;
    }
    const tickMs = 20 / speed;   // 50Hz base rate, adjusted for speed
    intervalRef.current = setInterval(() => {
      setCurrentTick(t => {
        if (t >= frames.length - 1) {
          setIsPlaying(false);
          return t;
        }
        return t + 1;
      });
    }, tickMs);
    return () => clearInterval(intervalRef.current);
  }, [isPlaying, speed, frames.length]);

  const frame = frames[currentTick] ?? null;
  const progress = frames.length > 1 ? currentTick / (frames.length - 1) : 0;

  return {
    frame,
    isPlaying,
    speed,
    progress,
    totalTicks: frames.length,
    currentTick,
    play: () => setIsPlaying(true),
    pause: () => setIsPlaying(false),
    setSpeed,
    seekTo: setCurrentTick,
    isLoading,
    error,
  };
}
