import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { Base, mergeTheme } from "../theme";

export type CompareSide = { label: string; value: string; raw?: number; caption?: string; color?: string };
export type CompareProps = Base & {
  title?: string;
  unit?: string;
  left: CompareSide;
  right: CompareSide;
  ratio?: number | null;     // left / right, printed in the middle
  source?: string;
};

// Two figures facing each other, with the ratio spelled out between them. "中国 vs 美国",
// "2015 vs 2024" — the comparison is the argument in most of this channel's topics, and stating
// the ratio ("0.66 倍") saves the viewer the arithmetic that the narration would otherwise do.
export const Compare: React.FC<CompareProps> = ({ title, unit = "", left, right, ratio, source, theme }) => {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();
  const t = mergeTheme(theme);
  const scale = width / 1920;

  const bars = [left, right].map((s) => s.raw ?? (parseFloat(s.value.replace(/,/g, "")) || 0));
  const peak = Math.max(...bars, 1);

  const side = (s: CompareSide, i: number) => {
    const enter = spring({ frame: frame - i * 8, fps, config: { damping: 24, stiffness: 80 } });
    const h = (bars[i] / peak) * height * 0.34 * enter;
    const colour = s.color ?? (i === 0 ? t.accent : "#2a9d8f");
    return (
      <div key={i} style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "flex-end" }}>
        <div style={{ color: t.fg, fontSize: 96 * scale, fontWeight: 800, opacity: enter }}>
          {s.value}
          {unit && <span style={{ fontSize: 44 * scale, color: t.accent, marginLeft: 10 * scale }}>{unit}</span>}
        </div>
        <div style={{ width: width * 0.16, height: h, backgroundColor: colour, borderRadius: 10 * scale, marginTop: 20 * scale }} />
        <div style={{ color: t.fg, fontSize: 48 * scale, fontWeight: 700, marginTop: 24 * scale }}>{s.label}</div>
        {s.caption && <div style={{ color: t.muted, fontSize: 30 * scale, marginTop: 8 * scale }}>{s.caption}</div>}
      </div>
    );
  };

  return (
    <AbsoluteFill style={{ backgroundColor: t.bg, fontFamily: t.font }}>
      {title && (
        <div style={{ position: "absolute", top: height * 0.1, width: "100%", textAlign: "center", color: t.fg, fontSize: 58 * scale, fontWeight: 700 }}>
          {title}
        </div>
      )}
      <div style={{ position: "absolute", top: height * 0.24, bottom: height * 0.14, left: width * 0.06, right: width * 0.06, display: "flex", alignItems: "flex-end" }}>
        {side(left, 0)}
        {ratio != null && (
          <div style={{
            width: width * 0.14, textAlign: "center", color: t.muted, fontSize: 40 * scale, fontWeight: 700,
            opacity: interpolate(frame, [fps * 0.8, fps * 1.3], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }),
          }}>
            {ratio >= 1 ? `${ratio.toFixed(2)} 倍` : `${(1 / ratio).toFixed(2)} 倍`}
            <div style={{ fontSize: 24 * scale, marginTop: 6 * scale }}>
              {ratio >= 1 ? `${left.label} 更高` : `${right.label} 更高`}
            </div>
          </div>
        )}
        {side(right, 1)}
      </div>
      {source && (
        <div style={{ position: "absolute", bottom: height * 0.05, right: width * 0.06, color: t.muted, fontSize: 22 * scale }}>
          {source}
        </div>
      )}
    </AbsoluteFill>
  );
};
