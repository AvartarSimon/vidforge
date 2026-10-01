import { AbsoluteFill, interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import { Base, mergeTheme } from "../theme";

export type LinePoint = { x: number; y: number };
export type LineSeries = { label: string; points: LinePoint[]; color?: string };
export type LineChartProps = Base & {
  title?: string;
  unit?: string;                 // already scaled by the Python side: "万亿", "%", "亿"
  lines: LineSeries[];
  source?: string;               // where the numbers came from — a data channel must always say
  highlightLast?: boolean;       // dot + value on the newest point of each line
  zeroBased?: boolean;           // start the y axis at 0 (honest for levels, noisy for rates)
};

const PALETTE = ["#e76f51", "#2a9d8f", "#e9c46a", "#8ecae6", "#bc6c25"];

// A time series drawn left to right as the narration talks over it. The line reaching the right
// edge at the same moment the sentence ends is the whole point: the viewer watches the trend
// happen rather than being shown a finished picture.
export const LineChart: React.FC<LineChartProps> = ({
  title, unit = "", lines, source, highlightLast = true, zeroBased = false, theme,
}) => {
  const frame = useCurrentFrame();
  const { durationInFrames, width, height } = useVideoConfig();
  const t = mergeTheme(theme);
  const scale = width / 1920;

  const left = width * 0.1, right = width * 0.94;
  const top = height * (title ? 0.26 : 0.16), bottom = height * 0.82;
  const all = lines.flatMap((l) => l.points);
  if (!all.length) return <AbsoluteFill style={{ backgroundColor: t.bg }} />;

  const xs = all.map((p) => p.x), ys = all.map((p) => p.y);
  const x0 = Math.min(...xs), x1 = Math.max(...xs);
  const yLo = zeroBased ? Math.min(0, ...ys) : Math.min(...ys);
  const yHi = Math.max(...ys);
  const pad = (yHi - yLo) * 0.12 || 1;
  // padding below the lowest point must not invent negative territory: an axis starting at -2
  // under a GDP series reads as "it was once negative", which is simply untrue
  const padded = yLo - pad;
  const yMin = zeroBased ? yLo : (yLo >= 0 && padded < 0 ? 0 : padded);
  const yMax = yHi + pad;
  const px = (x: number) => left + ((x - x0) / (x1 - x0 || 1)) * (right - left);
  const py = (y: number) => bottom - ((y - yMin) / (yMax - yMin || 1)) * (bottom - top);

  // drawn over the first 70% of the segment, so the last fifth is readable before the cut
  const progress = interpolate(frame, [0, durationInFrames * 0.7], [0, 1], { extrapolateRight: "clamp" });
  const fmt = (v: number) => (Math.abs(v) >= 100 ? v.toFixed(0) : v.toFixed(1));

  const gridY = [0, 0.25, 0.5, 0.75, 1].map((f) => yMin + (yMax - yMin) * f);

  return (
    <AbsoluteFill style={{ backgroundColor: t.bg, fontFamily: t.font }}>
      {title && (
        <div style={{ position: "absolute", top: height * 0.09, left, color: t.fg, fontSize: 60 * scale, fontWeight: 700 }}>
          {title}
          {unit && <span style={{ color: t.muted, fontSize: 30 * scale, marginLeft: 16 * scale }}>（{unit}）</span>}
        </div>
      )}

      <svg width={width} height={height} style={{ position: "absolute", inset: 0 }}>
        {gridY.map((gy, i) => (
          <g key={i}>
            <line x1={left} x2={right} y1={py(gy)} y2={py(gy)} stroke={t.muted} strokeOpacity={0.18} strokeWidth={1} />
            <text x={left - 14 * scale} y={py(gy) + 10 * scale} fill={t.muted} fontSize={26 * scale} textAnchor="end">
              {fmt(gy)}
            </text>
          </g>
        ))}
        <line x1={left} x2={right} y1={bottom} y2={bottom} stroke={t.muted} strokeOpacity={0.5} />
        {[x0, (x0 + x1) / 2, x1].map((gx, i) => (
          <text key={i} x={px(gx)} y={bottom + 42 * scale} fill={t.muted} fontSize={28 * scale} textAnchor="middle">
            {gx.toFixed(0)}
          </text>
        ))}

        {lines.map((l, li) => {
          const pts = [...l.points].sort((a, b) => a.x - b.x);
          const shown = Math.max(2, Math.ceil(pts.length * progress));
          const drawn = pts.slice(0, shown);
          const colour = l.color ?? PALETTE[li % PALETTE.length];
          const d = drawn.map((p, i) => `${i ? "L" : "M"}${px(p.x)},${py(p.y)}`).join(" ");
          const last = drawn[drawn.length - 1];
          return (
            <g key={li}>
              <path d={d} fill="none" stroke={colour} strokeWidth={6 * scale} strokeLinejoin="round" strokeLinecap="round" />
              {highlightLast && last && (
                <>
                  <circle cx={px(last.x)} cy={py(last.y)} r={10 * scale} fill={colour} />
                  <text x={px(last.x) - 18 * scale} y={py(last.y) - 22 * scale} fill={colour}
                        fontSize={34 * scale} fontWeight={700} textAnchor="end">
                    {fmt(last.y)}
                  </text>
                </>
              )}
            </g>
          );
        })}
      </svg>

      <div style={{ position: "absolute", top: height * (title ? 0.185 : 0.09), left, display: "flex", gap: 28 * scale }}>
        {lines.map((l, i) => (
          <div key={i} style={{ display: "flex", alignItems: "center", gap: 10 * scale, color: t.fg, fontSize: 30 * scale }}>
            <span style={{ width: 26 * scale, height: 6 * scale, borderRadius: 3, backgroundColor: l.color ?? PALETTE[i % PALETTE.length] }} />
            {l.label}
          </div>
        ))}
      </div>

      {source && (
        <div style={{ position: "absolute", bottom: height * 0.05, right: width * 0.06, color: t.muted, fontSize: 22 * scale }}>
          {source}
        </div>
      )}
    </AbsoluteFill>
  );
};
