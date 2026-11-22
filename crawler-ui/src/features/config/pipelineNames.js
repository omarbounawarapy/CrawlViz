// The name each pipeline stage goes by on the page. The diagram and the table both read it, so a
// stage has one name wherever it appears. The keys are the settings keys in the backend schema.
export const STAGE_NAMES = {
  fetch: "Fetch",
  extract: "Extract",
  filter: "Filter",
  transform: "Transform",
  score: "Score",
  prioritize: "Order queue",
  storage: "Store",
  retry: "Retry",
  debug_log: "Debug trace",
};

export const stageName = (key) => STAGE_NAMES[key] ?? key.replace(/_/g, " ");
