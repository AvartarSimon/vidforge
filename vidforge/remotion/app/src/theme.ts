// Shared look for every composition. Override per segment through props.theme.
export type Theme = {
  bg: string;
  fg: string;
  muted: string;
  accent: string;
  font: string;
};

export const defaultTheme: Theme = {
  bg: "#0f1115",
  fg: "#f3f4f6",
  muted: "#9ca3af",
  accent: "#e76f51",
  font: 'Inter, "Segoe UI", "PingFang SC", "Microsoft YaHei", system-ui, sans-serif',
};

export const mergeTheme = (t?: Partial<Theme>): Theme => ({ ...defaultTheme, ...(t ?? {}) });

// Every composition receives these from vidforge; durationInFrames = narration length.
export type Base = {
  durationInFrames: number;
  fps: number;
  width: number;
  height: number;
  theme?: Partial<Theme>;
};
