import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { Base, mergeTheme } from "../theme";
import { Mark } from "./Mark";

export type IntroProps = Base & {
  name: string;
  slogan?: string;
  enName?: string;
  mark?: "ticks" | "line" | "axis";
};

// About one second: the mark draws itself, the name slides in beside it, the slogan fades under.
// Any longer and it costs retention — an intro over ~5 s measurably lowers the share of viewers
// still watching at 0:30 — so this is meant to sit *after* the hook, not before it.
export const Intro: React.FC<IntroProps> = ({ name, slogan, enName, mark = "ticks", theme }) => {
  const frame = useCurrentFrame();
  const { fps, width, height, durationInFrames } = useVideoConfig();
  const t = mergeTheme(theme);
  const scale = width / 1920;

  const draw = spring({ frame, fps, config: { damping: 26, stiffness: 120 }, durationInFrames: Math.round(fps * 0.5) });
  const slide = spring({ frame: frame - Math.round(fps * 0.18), fps, config: { damping: 30, stiffness: 110 } });
  const out = interpolate(frame, [durationInFrames - Math.round(fps * 0.18), durationInFrames], [1, 0], {
    extrapolateLeft: "clamp", extrapolateRight: "clamp",
  });

  const markSize = height * 0.28;

  return (
    <AbsoluteFill style={{
      backgroundColor: t.bg, fontFamily: t.font, alignItems: "center", justifyContent: "center", opacity: out,
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 44 * scale }}>
        <Mark kind={mark} size={markSize} progress={draw} fg={t.fg} accent={t.accent} />
        <div style={{ overflow: "hidden" }}>
          <div style={{
            color: t.fg, fontSize: 104 * scale, fontWeight: 800, letterSpacing: 6 * scale,
            transform: `translateX(${interpolate(slide, [0, 1], [-40 * scale, 0])}px)`, opacity: slide,
          }}>
            {name}
          </div>
          {enName && (
            <div style={{ color: t.muted, fontSize: 30 * scale, letterSpacing: 8 * scale, marginTop: 6 * scale, opacity: slide }}>
              {enName}
            </div>
          )}
        </div>
      </div>
      {slogan && (
        <div style={{
          color: t.muted, fontSize: 40 * scale, marginTop: 42 * scale, letterSpacing: 3 * scale,
          opacity: interpolate(frame, [fps * 0.35, fps * 0.6], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }),
        }}>
          {slogan}
        </div>
      )}
    </AbsoluteFill>
  );
};
