import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { Base, mergeTheme } from "../theme";

export type TitleCardProps = Base & {
  title: string;
  subtitle?: string;
  kicker?: string; // small text above the title, e.g. "PART 2"
};

// Chapter title card: kicker fades in, title springs up, accent rule grows, subtitle follows.
export const TitleCard: React.FC<TitleCardProps> = ({ title, subtitle, kicker, theme }) => {
  const frame = useCurrentFrame();
  const { fps, width } = useVideoConfig();
  const t = mergeTheme(theme);
  const scale = width / 1920;

  const rise = spring({ frame, fps, config: { damping: 200, stiffness: 120 } });
  const titleY = interpolate(rise, [0, 1], [60, 0]);
  const kickerOpacity = interpolate(frame, [0, 12], [0, 1], { extrapolateRight: "clamp" });
  const ruleWidth = interpolate(frame, [8, 40], [0, 220 * scale], { extrapolateRight: "clamp", extrapolateLeft: "clamp" });
  const subOpacity = interpolate(frame, [20, 40], [0, 1], { extrapolateRight: "clamp", extrapolateLeft: "clamp" });

  return (
    <AbsoluteFill style={{ backgroundColor: t.bg, fontFamily: t.font, justifyContent: "center", alignItems: "center" }}>
      <div style={{ maxWidth: width * 0.8, textAlign: "center" }}>
        {kicker && (
          <div style={{ color: t.accent, fontSize: 30 * scale, letterSpacing: 6 * scale, opacity: kickerOpacity, marginBottom: 24 * scale, textTransform: "uppercase" }}>
            {kicker}
          </div>
        )}
        <div style={{ color: t.fg, fontSize: 104 * scale, fontWeight: 800, lineHeight: 1.05, transform: `translateY(${titleY}px)`, opacity: rise }}>
          {title}
        </div>
        <div style={{ height: 6 * scale, width: ruleWidth, backgroundColor: t.accent, margin: `${36 * scale}px auto` }} />
        {subtitle && (
          <div style={{ color: t.muted, fontSize: 40 * scale, opacity: subOpacity }}>{subtitle}</div>
        )}
      </div>
    </AbsoluteFill>
  );
};
