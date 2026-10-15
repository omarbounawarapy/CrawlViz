// Small ports behind the NLP illustrations; tested against fixtures the Python code wrote.

/** Mean of the `k` highest similarities, as FeatureExtractor.target_similarity. */
export function topKMean(similarities, k) {
  const top = [...similarities].sort((a, b) => b - a).slice(0, Math.max(1, k));
  return top.reduce((a, b) => a + b, 0) / top.length;
}

/** Link context as models/links_extractor.py builds it: cut at `limit` characters, then the anchor's sentence. */
export function linkContext(text, anchor, limit) {
  const cut = text.slice(0, limit);
  if (!cut || !anchor) return cut;
  const hit = cut.split(".").find((s) => s.toLowerCase().includes(anchor.toLowerCase()));
  return hit === undefined ? cut : hit.trim();
}

const unit = (deg) => [Math.cos((deg * Math.PI) / 180), Math.sin((deg * Math.PI) / 180)];
const cosDist = (a, b) => 1 - (a[0] * b[0] + a[1] * b[1]) / (Math.hypot(...a) * Math.hypot(...b));

/** DBSCAN with cosine distance over points given as angles in degrees; -1 is noise (sklearn labels). */
export function clusterAngles(angles, eps, minSamples) {
  const pts = angles.map(unit);
  const near = pts.map((p) => pts.flatMap((q, j) => (cosDist(p, q) <= eps ? [j] : [])));
  const labels = Array(pts.length).fill(-2);
  let next = 0;
  pts.forEach((_, i) => {
    if (labels[i] !== -2 || near[i].length < minSamples) return;
    labels[i] = next;
    const queue = [...near[i]];
    while (queue.length) {
      const j = queue.pop();
      if (labels[j] === -1 || labels[j] === -2) {
        labels[j] = next;
        if (near[j].length >= minSamples) queue.push(...near[j]);
      }
    }
    next += 1;
  });
  return labels.map((l) => (l === -2 ? -1 : l));
}
