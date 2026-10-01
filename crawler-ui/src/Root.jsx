import { useCallback, useEffect, useRef, useState } from "react";
import App from "./App.jsx";
import Landing from "./features/landing/Landing.jsx";
import SpiderLoader from "./features/loading/SpiderLoader.jsx";
import { useRoute } from "./hooks/useRoute";

const BOOT_MS = 1200;   // long enough for the spider to land and the ring to close
const ENTER_MS = 900;
const SEEN_KEY = "crawlviz:boot-seen";

// The boot screen plays once per browser session; returning to the page is instant.
function firstBoot() {
  try {
    if (sessionStorage.getItem(SEEN_KEY)) return false;
    sessionStorage.setItem(SEEN_KEY, "1");
  } catch { /* storage blocked: show it */ }
  return true;
}

// Eases toward 0.94 over `ms`, then snaps to 1 once `ready`. The bar is a
// timed reveal, not a measurement: the app has no real load phases to report.
function useTimedProgress(active, ms, ready) {
  const [p, setP] = useState(0);
  const start = useRef(0);
  useEffect(() => {
    if (!active) return undefined;
    start.current = performance.now();
    let raf;
    const tick = (now) => {
      const t = Math.min(1, (now - start.current) / ms);
      setP(0.94 * (1 - (1 - t) ** 2));
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [active, ms]);
  return ready ? 1 : p;
}

export default function Root() {
  const { path, navigate } = useRoute();
  const isLanding = path === "/" || path === "/welcome";
  // null = idle, "boot" = first paint, "enter" = landing -> app
  // The entrance plays once per session. On a reload everything is simply there.
  const [playIntro] = useState(firstBoot);
  const [loading, setLoading] = useState(playIntro ? "boot" : null);
  const [ready, setReady] = useState(false);
  const [pendingTo, setPendingTo] = useState(null);

  const progress = useTimedProgress(loading !== null, loading === "enter" ? ENTER_MS : BOOT_MS, ready);

  useEffect(() => {
    if (!loading) return undefined;
    let cancelled = false;
    const minTime = new Promise((r) => setTimeout(r, loading === "enter" ? ENTER_MS : BOOT_MS));
    // Fonts get at most 1.2s; a hung font request must not hold the page.
    const fonts = Promise.race([document.fonts?.ready ?? Promise.resolve(), new Promise((r) => setTimeout(r, 1200))]);
    Promise.all([minTime, fonts]).then(() => { if (!cancelled) setReady(true); });
    return () => { cancelled = true; };
  }, [loading]);

  const enter = useCallback((to) => { setReady(false); setPendingTo(to); setLoading("enter"); }, []);

  const onExit = useCallback(() => {
    if (pendingTo) { navigate(pendingTo); window.scrollTo(0, 0); setPendingTo(null); }
    setLoading(null);
  }, [pendingTo, navigate]);

  return (
    <>
      {isLanding ? <Landing onEnter={enter} instant={!playIntro} /> : <App />}
      {loading && <SpiderLoader progress={progress} done={ready} onExit={onExit} onSkip={() => setReady(true)} />}
    </>
  );
}
