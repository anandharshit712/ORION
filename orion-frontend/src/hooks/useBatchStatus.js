// ORION — useBatchStatus hook  [Phase 1]
// Polls GET /api/runs/batch/{batchId}/status every POLL_INTERVAL_MS
// until the batch is complete (complete + failed === total).
// Auto-stops polling to avoid memory leaks.

import { useState, useEffect, useRef, useCallback } from 'react';
import api from '../services/api';
import { useAuth } from '../context/AuthContext';

const POLL_INTERVAL_MS = 2000;

/**
 * useBatchStatus(batchId)
 *
 * Returns:
 *   status  — { total, queued, running, complete, failed } | null
 *   isDone  — true when complete + failed === total
 *   error   — error message string | null
 *   refresh — manually trigger a poll
 */
export function useBatchStatus(batchId) {
  const { token } = useAuth();
  const [status, setStatus] = useState(null);
  const [error, setError] = useState(null);
  const intervalRef = useRef(null);

  const poll = useCallback(async () => {
    if (!batchId || !token) return;
    try {
      // TODO [P1]: Call api.getBatchStatus(token, batchId)
      // TODO [P1]: setStatus(data)
      // TODO [P1]: If data.complete + data.failed === data.total, clearInterval
    } catch (err) {
      setError(err.message);
    }
  }, [batchId, token]);

  useEffect(() => {
    if (!batchId) return;
    poll();
    intervalRef.current = setInterval(poll, POLL_INTERVAL_MS);
    return () => clearInterval(intervalRef.current);
  }, [batchId, poll]);

  const isDone = status
    ? status.complete + status.failed >= status.total && status.total > 0
    : false;

  return { status, isDone, error, refresh: poll };
}
