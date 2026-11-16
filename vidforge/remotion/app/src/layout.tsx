import { AbsoluteFill, useVideoConfig } from "remotion";
import { Theme } from "./theme";

// Where a composition may draw, and how large its text is. A landscape frame is all usable and
// everything is sized against 1920 px. A phone frame is neither: the top quarter belongs to the
// series badge and the presenter window, the lower third to the subtitles and the platform's own
// caption — and text sized against 1920 px comes out half as large as the subtitles next to it.
// `height` is the height of that usable band, so `height * 0.1` means the same thing in both.
export const useLayout = () => {
  const { width, height } = useVideoConfig();
  const tall = height > width;
  return {
    tall,
    width,
    top: tall ? height * 0.27 : 0,
    height: tall ? height * 0.39 : height,
    scale: Math.max(width / 1920, Math.min(width, height) / 1350),
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
