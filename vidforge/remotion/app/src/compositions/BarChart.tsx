import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { Base, mergeTheme } from "../theme";

export type BarItem = { label: string; value: number; color?: string; display?: string };
export type BarChartProps = Base & {
  title?: string;
  unit?: string;          // appended to the value, e.g. "M", "%", "°C"
  items: BarItem[];
  max?: number;           // scale; defaults to the largest value
  source?: string;        // small footnote, e.g. "Source: Maddison Project 2020"
};

// Horizontal bars grow one after another; values count up with the bar.
export const BarChart: React.FC<BarChartProps> = ({ title, unit = "", items, max, source, theme }) => {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();
  const t = mergeTheme(theme);
  const scale = width / 1920;
  const top = height * (title ? 0.24 : 0.14);
  const bottom = height * 0.88;
  const rowH = Math.min(120 * scale, (bottom - top) / Math.max(items.length, 1));
  const labelW = width * 0.22;
  const barMaxW = width * 0.56;
  const scaleMax = max ?? Math.max(...items.map((i) => i.value), 1);
  const allInt = items.every((i) => Number.isInteger(i.value));
  const fmt = (v: number) => (allInt ? Math.round(v).toLocaleString() : v.toFixed(1));

  return (
    <AbsoluteFill style={{ backgroundColor: t.bg, fontFamily: t.font }}>
      {title && (
        <div style={{ position: "absolute", top: height * 0.09, left: width * 0.08, color: t.fg, fontSize: 60 * scale, fontWeight: 700 }}>
          {title}
        </div>
      )}
      {items.map((it, i) => {
        const s = spring({ frame: frame - i * 10 - 4, fps, config: { damping: 22, stiffness: 90 } });
        const w = (it.value / scaleMax) * barMaxW * s;
        const y = top + i * rowH;
        return (
          <div key={i} style={{ position: "absolute", top: y, left: width * 0.08, height: rowH, display: "flex", alignItems: "center" }}>
            <div style={{ width: labelW, color: t.fg, fontSize: 34 * scale, textAlign: "right", paddingRight: 28 * scale, opacity: interpolate(s, [0, 0.3], [0, 1]) }}>
              {it.label}
            </div>
            <div style={{ width: w, height: rowH * 0.55, backgroundColor: it.color ?? t.accent, borderRadius: 6 * scale }} />
            <div style={{ color: t.muted, fontSize: 32 * scale, marginLeft: 20 * scale, opacity: s }}>
              {it.display ?? fmt(it.value * s) + unit}
            </div>
          </div>
        );
      })}
      {source && (
        <div style={{ position: "absolute", bottom: height * 0.05, right: width * 0.08, color: t.muted, fontSize: 22 * scale }}>{source}</div>
      )}
    </AbsoluteFill>
  );
};
