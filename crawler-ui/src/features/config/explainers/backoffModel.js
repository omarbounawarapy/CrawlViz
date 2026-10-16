// The wait before each request. Mirrors the worker loop in
// pipelines/requests_pipeline.py: wait = max(min_delay - time since the last
// request, 0) + shared backoff + jitter; backoff grows on 429, decays otherwise.

/**
 * `outcomes`: "ok" | "429" | "fail" per request. `latency` is how long a request
 * itself takes. Returns per-request wait (jitter excluded) and the backoff after each.
 */
export function simulate(outcomes, cfg, latency = 0) {
  let backoff = 0;
  const waits = [];
  const backoffs = [];
  outcomes.forEach((kind, i) => {
    const sinceLast = i === 0 ? Infinity : latency;
    waits.push(Math.max(cfg.min_delay - sinceLast, 0) + backoff);
    if (kind === "429") {
      backoff = backoff === 0 ? cfg.backoff_start : Math.min(backoff * cfg.backoff_growth, cfg.backoff_max);
    } else if (kind === "fail") {
      backoff = Math.max(backoff * cfg.backoff_failure_decay, 0);
    } else {
      backoff = Math.max(backoff * cfg.backoff_success_decay, 0);
    }
    backoffs.push(backoff);
  });
  return { waits, backoffs };
}

/** `n` requests with `burst` consecutive 429s starting at request `at`. */
export function scenario(n, burst, at = Math.floor(n / 3)) {
  return Array.from({ length: n }, (_, i) => (i >= at && i < at + burst ? "429" : "ok"));
}

/** Timeline: when each request starts (s), the wait before it and the rate over a trailing window. */
export function timeline(outcomes, cfg, latency = 0.3) {
  const { waits } = simulate(outcomes, cfg, latency);
  const jitter = (cfg.jitter_max ?? 0) / 2; // expected value of uniform(0, jitter_max)
  let t = 0;
  const points = waits.map((w, i) => {
    t += (i === 0 ? 0 : Math.max(w + jitter, latency));
    return { t, wait: w + jitter, outcome: outcomes[i] };
  });
  return points.map((p, i) => {
    const from = points.slice(0, i + 1).filter((q, j) => j === i || p.t - q.t <= 10);
    const span = Math.max(p.t - from[0].t, 3);
    return { ...p, rate: from.length / span };
  });
}

/** The headline numbers shown under the chart. */
export function summary(cfg, latency = 0.3) {
  const jitter = (cfg.jitter_max ?? 0) / 2;
  const gap = Math.max(cfg.min_delay, latency) + jitter;
  return {
    steadyRate: 1 / Math.max(gap, 0.001),
    worstWait: cfg.min_delay + cfg.backoff_max + (cfg.jitter_max ?? 0),
  };
}

/**
 * The fetch settings in plain numbers: the most requests per second the crawl can
 * make, the most in flight at once, and how many times one page can be tried.
 * The rate is the lower of the global pace (min_delay plus half the jitter, on
 * average) and what the workers can sustain while each request takes `latency`.
 */
export function politeness(cfg, { workers, maxRetries }, latency = 0.3) {
  const { steadyRate } = summary(cfg, latency);
  const workerRate = workers / Math.max(latency, 0.001);
  const limitedBy = steadyRate <= workerRate ? "min_delay" : "workers";
  return {
    requestsPerSecond: Math.min(steadyRate, workerRate),
    inFlight: workers,
    attempts: maxRetries + 1,
    limitedBy,
  };
}
