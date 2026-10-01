// Drawn spider, top view, ink on paper. Eight two-segment legs that step in
// alternating pairs (CSS, see loading.css). Sized by the parent via `size`.
const LEGS = [
  // [baseX, baseY, kneeX, kneeY, footX, footY]
  [-4, -9, -17, -24, -30, -20],
  [-5, -6, -24, -15, -38, -6],
  [-5, -3, -24, 4, -36, 18],
  [-4, 0, -17, 18, -26, 34],
];

export default function Spider({ size = 120, className = "" }) {
  const legs = [];
  LEGS.forEach((l, i) => {
    [-1, 1].forEach((side) => {
      const [bx, by, kx, ky, fx, fy] = l;
      legs.push(
        <polyline
          key={`${i}${side}`}
          className={`spider-leg spider-leg-${(i + (side > 0 ? 1 : 0)) % 2}`}
          points={`${bx * -side},${by} ${kx * -side},${ky} ${fx * -side},${fy}`}
          style={{ transformOrigin: `${bx * -side}px ${by}px` }}
        />,
      );
    });
  });
  return (
    <svg
      className={`spider ${className}`}
      width={size}
      height={size}
      viewBox="-50 -50 100 100"
      aria-hidden="true"
      focusable="false"
    >
      <g className="spider-body-bob">
        <g className="spider-legs" fill="none" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
          {legs}
        </g>
        <ellipse className="spider-abdomen" cx="0" cy="11" rx="11" ry="15" />
        <path className="spider-mark" d="M-4 6 L4 6 M-3 11 L3 11 M-2 16 L2 16" />
        <circle className="spider-head" cx="0" cy="-8" r="7.5" />
        <circle className="spider-eye" cx="-2.6" cy="-12" r="1.3" />
        <circle className="spider-eye" cx="2.6" cy="-12" r="1.3" />
      </g>
    </svg>
  );
}
