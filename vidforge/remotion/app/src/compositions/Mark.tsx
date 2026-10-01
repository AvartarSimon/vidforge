import { interpolate } from "remotion";

export type MarkKind = "ticks" | "line" | "axis";

// The channel mark, drawn rather than imported, so the opener and the end card can animate it
// and so it stays sharp at any size. Same three shapes as brand.logo_svg() on the Python side —
// keep them in step if either changes.
export const Mark: React.FC<{
  kind: MarkKind;
  size: number;
  progress: number;      // 0..1, how much of the mark has been drawn
  fg: string;
  accent: string;
}> = ({ kind, size: s, progress, fg, accent }) => {
  const pad = s * 0.16;
  const p = Math.max(0, Math.min(1, progress));

  if (kind === "line") {
    const pts: [number, number][] = [[0, 0.62], [0.25, 0.5], [0.5, 0.56], [0.75, 0.3], [1, 0.18]];
    const co = pts.map(([x, y]) => [pad + (s - 2 * pad) * x, pad + (s - 2 * pad) * y] as [number, number]);
    const shown = Math.max(2, Math.ceil(co.length * p));
    const d = co.slice(0, shown).map(([x, y], i) => `${i ? "L" : "M"}${x},${y}`).join(" ");
    const last = co[shown - 1];
    return (
      <svg width={s} height={s}>
        <path d={d} fill="none" stroke={fg} strokeWidth={s * 0.055} strokeLinecap="round" strokeLinejoin="round" />
        {p > 0.9 && <circle cx={last[0]} cy={last[1]} r={s * 0.075} fill={accent} />}
      </svg>
    );
  }

  if (kind === "axis") {
    const x0 = pad, y0 = s - pad;
    return (
      <svg width={s} height={s}>
        <path d={`M${x0},${pad} L${x0},${y0} L${pad + (s - 2 * pad) * p},${y0}`} fill="none" stroke={fg}
              strokeWidth={s * 0.05} strokeLinecap="round" />
        <circle cx={s * 0.66} cy={s * 0.36} r={s * 0.085 * Math.max(0, (p - 0.6) / 0.4)} fill={accent} />
      </svg>
    );
  }

  // ticks: a measuring scale — a chart axis and a timeline are the same picture, which is the
  // whole idea of a channel that reads today's news against the record.
  const base = s * 0.7;
  const n = 7;
  return (
    <svg width={s} height={s}>
      {Array.from({ length: n }, (_, i) => {
        const x = pad + ((s - 2 * pad) * i) / (n - 1);
        const isNow = i === n - 3;
        const grow = interpolate(p, [i / n * 0.8, i / n * 0.8 + 0.3], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
        const h = s * (isNow ? 0.3 : 0.16) * grow;
        const w = s * (isNow ? 0.055 : 0.035);
        return <rect key={i} x={x - w / 2} y={base - h} width={w} height={h} rx={w / 2} fill={isNow ? accent : fg} />;
      })}
      <rect x={pad} y={base} width={(s - 2 * pad) * p} height={s * 0.035} rx={s * 0.018} fill={fg} opacity={0.85} />
    </svg>
  );
};
