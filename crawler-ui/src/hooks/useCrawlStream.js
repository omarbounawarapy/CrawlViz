import { useRef, useEffect, useCallback } from "react";
import { normalizeEvent } from "../state/eventNormalizer";

export function useCrawlStream(dispatch, wsUrl = "ws://localhost:8765") {
  const wsRef      = useRef(null);
  const retryDelay = useRef(1000);
  const alive      = useRef(true);
  // Reconnect-with-backoff calls connect() from within connect()'s own
  // onclose handler. Holding the latest connect in a ref (rather than
  // referencing the `connect` binding directly) keeps that recursive call
  // from being a static reference-before-declaration.
  const connectRef = useRef(null);

  const connect = useCallback(() => {
    if (!alive.current) return;
    try {
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        retryDelay.current = 1000;
        dispatch({ type: "__WS_CONNECTED" });
      };

      ws.onmessage = ({ data }) => {
        const event = normalizeEvent(data);
        if (event) dispatch(event);
      };

      ws.onclose = () => {
        if (!alive.current) return;
        dispatch({ type: "__WS_DISCONNECTED" });
        setTimeout(() => connectRef.current?.(), retryDelay.current);
        retryDelay.current = Math.min(retryDelay.current * 2, 15000);
      };

      ws.onerror = () => ws.close();
    } catch {
      setTimeout(() => connectRef.current?.(), retryDelay.current);
    }
  }, [dispatch, wsUrl]);

  useEffect(() => {
    connectRef.current = connect;
  }, [connect]);

  useEffect(() => {
    alive.current = true;
    connect();
    return () => {
      alive.current = false;
      wsRef.current?.close();
    };
  }, [connect]);
}