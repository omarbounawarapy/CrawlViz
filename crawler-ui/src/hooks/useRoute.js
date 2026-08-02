import { useCallback, useState, useEffect } from "react";

// Small hash-based router: no dependency, because the actual routing needs
// here are a flat set of top-level sections plus optional query-string
// state (e.g. a future `?run=a&compare=b` for run comparison) -- both are
// within reach of this without pulling in react-router. See
// docs/V2_ARCHITECTURE.md §B.4 ("explicitly considered and rejected") for
// the reasoning; this hook is what that decision is betting on, so if a
// real need for nested/parameterized routes shows up, that's the signal
// to revisit it.

function parseHash(hash) {
  const raw = hash.replace(/^#/, "");
  const [path, queryString] = raw.split("?");
  return {
    path: path || "/",
    query: new URLSearchParams(queryString || ""),
  };
}

export function useRoute() {
  const [{ path, query }, setParsed] = useState(() => parseHash(window.location.hash));

  useEffect(() => {
    const onHashChange = () => setParsed(parseHash(window.location.hash));
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  const navigate = useCallback((newPath, params) => {
    const qs = params ? new URLSearchParams(params).toString() : "";
    window.location.hash = qs ? `${newPath}?${qs}` : newPath;
    setParsed({ path: newPath, query: new URLSearchParams(qs) });
  }, []);

  return { path, query, navigate };
}
