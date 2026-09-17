import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { Base, mergeTheme } from "../theme";

export type VocabItem = { word: string; ipa?: string; meaning?: string; example?: string };
export type VocabProps = Base & { title?: string; items: VocabItem[] };

// End card for the learner variant: words appear one after another with IPA, meaning, example.
export const Vocab: React.FC<VocabProps> = ({ title = "Vocabulary", items, theme }) => {
  const frame = useCurrentFrame();
  const { fps, width, height, durationInFrames } = useVideoConfig();
  const t = mergeTheme(theme);
  const sc = width / 1920;
  const n = Math.max(1, items.length);
  const revealFrames = durationInFrames * 0.7;
  const rowH = Math.min(92 * sc, (height * 0.64) / n);   // leave the bottom ~18% for burned subtitles
  const top = height * 0.16;
  return (
    <AbsoluteFill style={{ backgroundColor: t.bg, fontFamily: t.font }}>
      <div style={{ position: "absolute", top: height * 0.06, left: width * 0.08, color: t.fg, fontSize: 56 * sc, fontWeight: 700 }}>
        {title}
        <span style={{ color: t.accent, marginLeft: 16 * sc, fontSize: 28 * sc, fontWeight: 500 }}>{items.length} words</span>
      </div>
      {items.map((it, i) => {
        const start = (revealFrames * i) / n + 4;
        const s = spring({ frame: frame - start, fps, config: { damping: 18, stiffness: 120 } });
        const y = top + i * rowH;
        return (
          <div key={i} style={{ position: "absolute", top: y, left: width * 0.08, right: width * 0.08, height: rowH, display: "grid",
                                gridTemplateColumns: "26% 20% 54%", alignItems: "center", opacity: s, transform: `translateX(${(1 - s) * 30}px)`,
                                borderBottom: `1px solid ${t.muted}33` }}>
            <div>
              <div style={{ color: t.fg, fontSize: 38 * sc, fontWeight: 700 }}>{it.word}</div>
              {it.ipa && <div style={{ color: t.muted, fontSize: 22 * sc, fontFamily: "'Charis SIL', 'Doulos SIL', 'Segoe UI', sans-serif" }}>{it.ipa}</div>}
            </div>
            <div style={{ color: t.accent, fontSize: 30 * sc, fontWeight: 600 }}>{it.meaning}</div>
            <div style={{ color: t.muted, fontSize: 24 * sc, lineHeight: 1.3, opacity: interpolate(s, [0.6, 1], [0, 1]) }}>{it.example}</div>
          </div>
        );
      })}
    </AbsoluteFill>
  );
};
