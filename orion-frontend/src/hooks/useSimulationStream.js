import { useEffect, useRef, useState } from 'react';
import { api } from '../services/api';

const MAX_RECONNECT_ATTEMPTS = 3;
const RECONNECT_BASE_MS = 500;

// Application close code the server uses for a refused credential (D-04).
// Distinct from 1008 so we know to fetch a fresh ticket rather than give up.
const WS_AUTH_FAILED = 4401;

export function useSimulationStream(runId) {
  const [frame, setFrame] = useState(null);
  const [isConnected, setIsConnected] = useState(false);
  const [error, setError] = useState(null);
  const [status, setStatus] = useState('connecting');

  const socketRef = useRef(null);
  const attemptsRef = useRef(0);
  const reconnectTimerRef = useRef(null);
  const cancelledRef = useRef(false);
  const latencyRef = useRef({ count: 0, sumMs: 0, maxMs: 0 });

  useEffect(() => {
    if (!runId) return undefined;

    cancelledRef.current = false;

    // Each connection gets its own ticket: they are single-use and expire after
    // 60s, so a reconnect cannot replay the previous one.
    const connect = async () => {
      let ticket;
      try {
        const issued = await api.createWsTicket(runId);
        ticket = issued.ticket;
      } catch (err) {
        if (cancelledRef.current) return;
        setError(err.message || 'Could not authorise the stream');
        setStatus('rejected');
        return;
      }
      if (cancelledRef.current) return;

      const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
      const url = `${proto}://${window.location.host}/ws/simulation/${runId}?ticket=${encodeURIComponent(ticket)}`;

      const ws = new WebSocket(url);
      socketRef.current = ws;

      ws.onopen = () => {
        attemptsRef.current = 0;
        setIsConnected(true);
        setStatus('streaming');
        setError(null);
      };

      ws.onmessage = (ev) => {
        let parsed;
        try {
          parsed = JSON.parse(ev.data);
        } catch {
          return;
        }
        if (parsed && parsed.event === 'stream_end') {
          setStatus(`ended:${parsed.status || 'complete'}`);
          if (parsed.error) setError(parsed.error);
          return;
        }
        if (typeof parsed.emit_ts_ms === 'number') {
          const latencyMs = Date.now() - parsed.emit_ts_ms;
          const s = latencyRef.current;
          s.count += 1;
          s.sumMs += latencyMs;
          s.lastMs = latencyMs;
          if (latencyMs > s.maxMs) s.maxMs = latencyMs;
        }
        setFrame(parsed);
      };

      ws.onerror = () => {
        setError('WebSocket error');
      };

      ws.onclose = (ev) => {
        setIsConnected(false);
        if (cancelledRef.current) return;
        // Normal end-of-stream from server (code 1000) — do not reconnect.
        if (ev.code === 1000) {
          setStatus((prev) => (prev.startsWith('ended') ? prev : 'closed'));
          return;
        }
        if (ev.code === 1008) {
          setError('Run not found');
          setStatus('rejected');
          return;
        }
        if (ev.code === WS_AUTH_FAILED) {
          // The ticket was expired, already used, or for another run. A retry
          // mints a new one, so this is worth one reconnect rather than none.
          setError('Stream authorisation expired');
          if (attemptsRef.current >= MAX_RECONNECT_ATTEMPTS) {
            setStatus('rejected');
            return;
          }
          attemptsRef.current += 1;
          setStatus(`reconnecting (${attemptsRef.current}/${MAX_RECONNECT_ATTEMPTS})`);
          reconnectTimerRef.current = setTimeout(connect, RECONNECT_BASE_MS);
          return;
        }
        if (attemptsRef.current >= MAX_RECONNECT_ATTEMPTS) {
          setStatus('disconnected');
          return;
        }
        const delay = RECONNECT_BASE_MS * 2 ** attemptsRef.current;
        attemptsRef.current += 1;
        setStatus(`reconnecting (${attemptsRef.current}/${MAX_RECONNECT_ATTEMPTS})`);
        reconnectTimerRef.current = setTimeout(connect, delay);
      };
    };

    connect();          // async: the cleanup below handles an in-flight attempt

    return () => {
      cancelledRef.current = true;
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }
      const ws = socketRef.current;
      if (ws && ws.readyState <= WebSocket.OPEN) {
        ws.close(1000, 'component unmount');
      }
      socketRef.current = null;
    };
  }, [runId]);

  return { frame, isConnected, status, error, latencyRef };
}
