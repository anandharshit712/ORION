import { useEffect, useRef, useState } from 'react';

const MAX_RECONNECT_ATTEMPTS = 3;
const RECONNECT_BASE_MS = 500;

export function useSimulationStream(runId, token) {
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
    if (!runId || !token) return undefined;

    cancelledRef.current = false;

    const connect = () => {
      const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
      const url = `${proto}://${window.location.host}/ws/simulation/${runId}?token=${encodeURIComponent(token)}`;

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
          setError('Auth rejected or run not found');
          setStatus('rejected');
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

    connect();

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
  }, [runId, token]);

  return { frame, isConnected, status, error, latencyRef };
}
