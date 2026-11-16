import { AbsoluteFill, getInputProps, useVideoConfig } from "remotion";
import { Theme } from "./theme";

// Where a composition may draw, and how large its text is. A landscape frame is all usable and
// everything is sized against 1920 px. A phone frame is neither: the top quarter belongs to the
// series badge and the presenter window, the lower third to the subtitles and the platform's own
// caption — and text sized against 1920 px comes out half as large as the subtitles next to it.
// `height` is the height of that usable band, so `height * 0.1` means the same thing in both.
// A landscape project that burns its subtitles in passes `clearBottom`, the share of the frame the
// subtitle line takes: the band stops above it, or the line sits across a chart's axis.
export const useLayout = () => {
  const { width, height } = useVideoConfig();
  const tall = height > width;
  const clear = tall ? 0 : Math.min(0.4, Number((getInputProps() as { clearBottom?: number }).clearBottom) || 0);
  return {
    tall,
    width,
    top: tall ? height * 0.27 : 0,
    height: tall ? height * 0.39 : height * (1 - clear),
    scale: Math.max(width / 1920, Math.min(width, height) / 1350) * (1 - clear / 2),
  };
};

// The backdrop over the whole frame, the content inside the usable band.
export const Stage: React.FC<{
  theme: Theme;
  style?: React.CSSProperties;
  opacity?: number;
  children: React.ReactNode;
}> = ({ theme, style, opacity, children }) => {
  const { width, top, height } = useLayout();
  return (
    <AbsoluteFill style={{ backgroundColor: theme.bg, fontFamily: theme.font, opacity }}>
      <div style={{ position: "absolute", left: 0, top, width, height, display: "flex", flexDirection: "column", ...style }}>
        {children}
      </div>
    </AbsoluteFill>
  );
};

// The few words a chart writes itself ("since 1960", "higher") follow the words it was given: an
// English project's chart said 倍 and 更高 next to English labels.
export const isChinese = (...given: (string | undefined)[]) => /[\u3400-\u9fff]/.test(given.join(""));
