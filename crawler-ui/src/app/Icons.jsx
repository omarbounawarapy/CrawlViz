// Small, hand-rolled stroke icons for the activity bar -- consistent with
// App.jsx's existing Logo (also raw SVG, no icon library). Eight glyphs is
// well within reach of this without adding a dependency; see
// docs/V2_ARCHITECTURE.md redesign audit re: "Lucide/Feather exclusively"
// being the generic-AI default this deliberately avoids.
//
// Every icon: 18×18 viewBox, currentColor stroke, 1.5 stroke width.

const common = {
  width: 16,
  height: 16,
  viewBox: "0 0 18 18",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.5,
  strokeLinecap: "round",
  strokeLinejoin: "round",
};

export function OverviewIcon() {
  return (
    <svg {...common}>
      <rect x="2.5" y="2.5" width="6" height="6" rx="1" />
      <rect x="9.5" y="2.5" width="6" height="6" rx="1" />
      <rect x="2.5" y="9.5" width="6" height="6" rx="1" />
      <rect x="9.5" y="9.5" width="6" height="6" rx="1" />
    </svg>
  );
}

export function GraphIcon() {
  return (
    <svg {...common}>
      <circle cx="9" cy="4" r="2" />
      <circle cx="4" cy="14" r="2" />
      <circle cx="14" cy="14" r="2" />
      <path d="M7.6 5.6L5.4 12.4M10.4 5.6l2.2 6.8" />
    </svg>
  );
}

export function PipelineIcon() {
  return (
    <svg {...common}>
      <rect x="1.5" y="7" width="4" height="4" rx="0.8" />
      <rect x="7" y="7" width="4" height="4" rx="0.8" />
      <rect x="12.5" y="7" width="4" height="4" rx="0.8" />
      <path d="M5.5 9h1.5M11 9h1.5" />
    </svg>
  );
}

export function TimelineIcon() {
  return (
    <svg {...common}>
      <path d="M2 9h14" />
      <path d="M5 6v6M9 5v8M13 6.5v5" />
      <circle cx="9" cy="9" r="1.4" fill="currentColor" stroke="none" />
    </svg>
  );
}

export function RunIcon() {
  return (
    <svg {...common}>
      <circle cx="9" cy="9" r="6.5" />
      <path d="M7.3 6.2l4.5 2.8-4.5 2.8z" fill="currentColor" stroke="none" />
    </svg>
  );
}

export function BlueprintIcon() {
  return (
    <svg {...common}>
      <path d="M5 2.5h6l2.5 2.5v10.5H5z" />
      <path d="M11 2.5V5h2.5" />
      <path d="M7 9h4M7 11.5h4" />
    </svg>
  );
}

export function DataIcon() {
  return (
    <svg {...common}>
      <ellipse cx="9" cy="4.2" rx="6" ry="2" />
      <path d="M3 4.2v9.6c0 1.1 2.7 2 6 2s6-.9 6-2V4.2" />
      <path d="M3 9c0 1.1 2.7 2 6 2s6-.9 6-2" />
    </svg>
  );
}

export function ConfigIcon() {
  return (
    <svg {...common}>
      <path d="M5 3v5M5 10v5M9 3v2M9 8v7M13 3v8M13 13.5v1.5" />
      <circle cx="5" cy="9" r="1.4" />
      <circle cx="9" cy="6.5" r="1.4" />
      <circle cx="13" cy="11" r="1.4" />
    </svg>
  );
}

export function ErrorDotIcon() {
  return (
    <svg width="6" height="6" viewBox="0 0 6 6">
      <circle cx="3" cy="3" r="3" fill="currentColor" />
    </svg>
  );
}
