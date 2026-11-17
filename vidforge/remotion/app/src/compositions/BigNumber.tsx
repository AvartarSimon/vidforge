import { interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { Base, mergeTheme } from "../theme";
import { Stage, isChinese, useLayout, SourceCaption } from "../layout";

export type BigNumberProps = Base & {
  title?: string;        // what the figure measures
  value: string;         // already formatted and scaled: "18.3"
  unit?: string;         // "万亿", "%", "亿人"
  caption?: string;      // "中国 · 2023"
  change?: number | null;       // percent change since `changeSince`
  changeSince?: string | null;
  source?: string;
};

// One number, full screen, counting up. This is the opening shot of a data video: the first
// seconds decide whether anyone keeps watching, and a figure large enough to fill the frame does
// that better than a sentence. The counter stops well before the segment ends so it can be read.
export const BigNumber: React.FC<BigNumberProps> = ({
  title, value, unit = "", caption, change, changeSince, source, theme,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const { width, height, scale } = useLayout();
  const t = mergeTheme(theme);

  // a hand-written project.json may well say 18.3 rather than "18.3"
  const text = String(value);
  const target = parseFloat(text.replace(/,/g, "")) || 0;
  const decimals = (text.split(".")[1] || "").length;
  const grow = spring({ frame, fps, config: { damping: 28, stiffness: 70 }, durationInFrames: Math.round(fps * 1.2) });
  const shown = (target * grow).toLocaleString(undefined, {
    minimumFractionDigits: decimals, maximumFractionDigits: decimals,
  });
  const up = (change ?? 0) >= 0;

  return (
    <Stage theme={t} style={{ alignItems: "center", justifyContent: "center" }}>
      {title && (
        <div style={{ color: t.muted, fontSize: 46 * scale, marginBottom: 18 * scale, opacity: interpolate(frame, [0, 10], [0, 1], { extrapolateRight: "clamp" }) }}>
          {title}
        </div>
      )}
      <div style={{ display: "flex", alignItems: "baseline", color: t.fg }}>
        <span style={{ fontSize: 220 * scale, fontWeight: 800, letterSpacing: -4 * scale, lineHeight: 1 }}>{shown}</span>
        {unit && <span style={{ fontSize: 86 * scale, fontWeight: 700, marginLeft: 16 * scale, color: t.accent }}>{unit}</span>}
      </div>
      {caption && (
        <div style={{ color: t.muted, fontSize: 40 * scale, marginTop: 24 * scale }}>{caption}</div>
      )}
      {change != null && (
        <div style={{
          marginTop: 28 * scale, fontSize: 44 * scale, fontWeight: 700,
          color: up ? "#2a9d8f" : "#e63946",
          opacity: interpolate(frame, [fps * 0.9, fps * 1.4], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }),
        }}>
          {up ? "▲" : "▼"} {Math.abs(change).toFixed(1)}%{changeSince ? (isChinese(title, caption, unit, source) ? `（较 ${changeSince} 年）` : ` (since ${changeSince})`) : ""}
        </div>
      )}
      {source && <SourceCaption text={source} color={t.muted} />}
    </Stage>
  );
};
