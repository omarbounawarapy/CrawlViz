import { useCallback, useEffect, useRef } from "react";

/**
 * Wraps a reducer dispatch so a burst of events renders once per animation frame.
 * A big crawl emits hundreds of events a second; dispatching each one re-renders the
 * app and re-joins the whole graph every time. Replay controls (`__REPLAY_*`) and
 * anything that must be ordered against them flush the queue first.
 */
export function useBatchedDispatch(dispatch) {
  const queue = useRef([]);
  const frame = useRef(0);

  const flush = useCallback(() => {
    frame.current = 0;
    if (queue.current.length === 0) return;
    const events = queue.current;
    queue.current = [];
    dispatch(events.length === 1 ? events[0] : { type: "__BATCH", events });
  }, [dispatch]);

  useEffect(() => () => { if (frame.current) cancelAnimationFrame(frame.current); }, []);

  return useCallback((event) => {
    queue.current.push(event);
    if (!frame.current) frame.current = requestAnimationFrame(flush);
  }, [flush]);
}
