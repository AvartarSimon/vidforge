import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { Base, mergeTheme } from "../theme";
import { Mark } from "./Mark";

export type OutroProps = Base & {
  name: string;
  slogan?: string;
  enName?: string;
  mark?: "ticks" | "line" | "axis";
  subscribe?: string;
  nextHint?: string;       // 「下期：…」— the single most useful thing an end card can carry
};

// At least five seconds, because YouTube's end screen elements are only clickable for as long as
// they are on screen. The right-hand side is deliberately left clear: that is where the end-screen
// video and subscribe widgets are placed in YouTube Studio, and a busy card buries them.
export const Outro: React.FC<OutroProps> = ({
  name, slogan, enName, mark = "ticks", subscribe, nextHint, theme,
}) => {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();
  const t = mergeTheme(theme);
  const scale = width / 1920;

  const draw = spring({ frame, fps, config: { damping: 26, stiffness: 110 }, durationInFrames: Math.round(fps * 0.7) });
  const fade = (delay: number) =>
    interpolate(frame, [fps * delay, fps * (delay + 0.35)], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });

  return (
    <AbsoluteFill style={{ backgroundColor: t.bg, fontFamily: t.font }}>
      <div style={{
        position: "absolute", left: width * 0.08, top: 0, bottom: 0, width: width * 0.46,
        display: "flex", flexDirection: "column", justifyContent: "center",
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 30 * scale }}>
          <Mark kind={mark} size={height * 0.2} progress={draw} fg={t.fg} accent={t.accent} />
          <div>
            <div style={{ color: t.fg, fontSize: 84 * scale, fontWeight: 800, letterSpacing: 5 * scale }}>{name}</div>
            {enName && <div style={{ color: t.muted, fontSize: 26 * scale, letterSpacing: 7 * scale }}>{enName}</div>}
          </div>
        </div>
        {slogan && (
          <div style={{ color: t.muted, fontSize: 36 * scale, marginTop: 28 * scale, opacity: fade(0.5) }}>{slogan}</div>
        )}
        {nextHint && (
          <div style={{ marginTop: 52 * scale, opacity: fade(0.9) }}>
            <div style={{ color: t.muted, fontSize: 26 * scale, letterSpacing: 4 * scale }}>下期</div>
            <div style={{ color: t.fg, fontSize: 46 * scale, fontWeight: 600, marginTop: 8 * scale, lineHeight: 1.35 }}>
              {nextHint}
            </div>
          </div>
        )}
        {subscribe && (
          <div style={{
            marginTop: 46 * scale, alignSelf: "flex-start", padding: `${14 * scale}px ${30 * scale}px`,
            border: `${3 * scale}px solid ${t.accent}`, borderRadius: 999, color: t.accent,
            fontSize: 32 * scale, fontWeight: 700, opacity: fade(1.3),
          }}>
            {subscribe}
          </div>
        )}
      </div>
      {/* kept empty on purpose: YouTube's end-screen cards go here */}
    </AbsoluteFill>
  );
};
