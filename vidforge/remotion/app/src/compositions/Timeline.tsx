import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { Base, mergeTheme } from "../theme";

export type TimelineEvent = { date: string; text: string };
export type TimelineProps = Base & {
  title?: string;
  events: TimelineEvent[];
  // fraction of the segment after which the last event is fully shown (leave the rest static)
  revealBy?: number;
};

// Horizontal timeline: the rule draws across, events pop in one after another, evenly spread
// over `revealBy` of the narration so the last one lands before the voice moves on.
export const Timeline: React.FC<TimelineProps> = ({ title, events, revealBy = 0.85, theme }) => {
  const frame = useCurrentFrame();
  const { fps, width, height, durationInFrames } = useVideoConfig();
  const t = mergeTheme(theme);
  const scale = width / 1920;
  const n = Math.max(events.length, 1);

  const revealFrames = durationInFrames * revealBy;
  const lineProgress = interpolate(frame, [0, revealFrames], [0, 1], { extrapolateRight: "clamp" });

  const left = width * 0.08;
  const right = width * 0.92;
  const y = height * 0.55;
  const slot = (right - left) / n;

  return (
    <AbsoluteFill style={{ backgroundColor: t.bg, fontFamily: t.font }}>
      {title && (
        <div style={{ position: "absolute", top: height * 0.12, width, textAlign: "center", color: t.fg, fontSize: 64 * scale, fontWeight: 700 }}>
          {title}
        </div>
      )}
      {/* rule */}
      <div style={{ position: "absolute", left, top: y, height: 4 * scale, width: (right - left) * lineProgress, backgroundColor: t.muted, borderRadius: 2 }} />
      {events.map((e, i) => {
        const start = (revealFrames * i) / n + 6;
        const s = spring({ frame: frame - start, fps, config: { damping: 14, stiffness: 160 } });
        const shown = frame >= start;
        const x = left + slot * (i + 0.5);
        const above = i % 2 === 0;
        return (
          <div key={i} style={{ position: "absolute", left: x, top: y, opacity: shown ? 1 : 0 }}>
            <div style={{ position: "absolute", left: -10 * scale, top: -8 * scale, width: 20 * scale, height: 20 * scale, borderRadius: "50%", backgroundColor: t.accent, transform: `scale(${s})` }} />
            <div style={{ position: "absolute", left: -slot * 0.45, width: slot * 0.9, textAlign: "center", top: above ? -190 * scale : 40 * scale, transform: `translateY(${(1 - s) * (above ? -20 : 20)}px)`, opacity: s }}>
              <div style={{ color: t.accent, fontSize: 34 * scale, fontWeight: 700 }}>{e.date}</div>
              <div style={{ color: t.fg, fontSize: 28 * scale, lineHeight: 1.3, marginTop: 8 * scale }}>{e.text}</div>
            </div>
          </div>
        );
      })}
    </AbsoluteFill>
  );
};
