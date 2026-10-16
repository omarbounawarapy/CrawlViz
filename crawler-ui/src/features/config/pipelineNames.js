// The name each pipeline stage goes by on the page. The diagram and the table both read it, so a
// stage has one name wherever it appears. The keys are the settings keys in the backend schema.
export const STAGE_NAMES = {
  requests: "Fetch",
  processing: "Extract",
  filtering: "Filter",
  transformation: "Transform",
  scoring: "Score",
  priority: "Order queue",
  storage: "Store",
  retry: "Retry",
  debugging: "Debug trace",
};

export const stageName = (key) => STAGE_NAMES[key] ?? key.replace(/_/g, " ");
