import { AbsoluteFill, useCurrentFrame, useVideoConfig } from "remotion";
import { Base } from "../theme";

export type HostStyle = {
  skin?: string;
  hair?: string;
  hairStyle?: "short" | "side" | "long" | "bald";
  shirt?: string;
  bg?: string;
  glasses?: boolean;
  eyes?: string;
  lips?: string;
  beard?: boolean;
};

export type HostProps = Base & {
  envelope: number[];      // 0..1 per frame, from the narration's loudness — drives the mouth
  name?: string;           // small caption, e.g. the channel name
  style?: HostStyle;
};

const defaults: Required<HostStyle> = {
  skin: "#e8b98f", hair: "#2b2118", hairStyle: "side", shirt: "#264653", bg: "#0f1115",
  glasses: false, eyes: "#2b2118", lips: "#a3534a", beard: false,
};

// deterministic blink: ~every 2.5–4 s, 5 frames long
const blinkAmount = (frame: number, fps: number) => {
  const period = Math.round(fps * 3.2);
  const phase = (frame + 37) % period;
  const jitter = ((Math.floor((frame + 37) / period) * 7919) % 23) - 11; // shift each blink a little
  const p = phase - Math.max(0, jitter);
  if (p < 0 || p > 5) return 0;
  return p <= 2 ? p / 2 : (5 - p) / 3;
};

// A stylised head-and-shoulders character. Deliberately NOT photoreal: it reads as a drawn host,
// so it needs no synthetic-media disclosure and never falls into the uncanny valley.
export const Host: React.FC<HostProps> = ({ envelope, name, style }) => {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();
  const s = { ...defaults, ...(style ?? {}) };
  const e = envelope[Math.min(frame, envelope.length - 1)] ?? 0;
  const eSmooth = Math.max(e, (envelope[Math.max(0, frame - 1)] ?? 0) * 0.7);
  const bob = Math.sin(frame / 17) * 2 + eSmooth * 2;
  const tilt = Math.sin(frame / 41) * 1.2;
  const blink = blinkAmount(frame, fps);
  const mouthH = 3 + eSmooth * 24;
  const mouthW = 30 + eSmooth * 8;
  const browLift = eSmooth * 3;
  const sc = Math.min(width / 480, height / 360);       // design space 480x360

  return (
    <AbsoluteFill style={{ backgroundColor: s.bg, justifyContent: "flex-end", alignItems: "center", overflow: "hidden" }}>
      <svg width={width} height={height} viewBox={`0 0 ${width / sc} ${height / sc}`} style={{ display: "block" }}>
        <g transform={`translate(${(width / sc) / 2}, 0)`}>
          {/* shoulders */}
          <path d={`M -150 ${360 / (height / sc) * 400} C -150 260 -80 240 0 240 C 80 240 150 260 150 ${400}`} fill={s.shirt} />
          <rect x={-150} y={300} width={300} height={200} fill={s.shirt} />
          {/* neck */}
          <rect x={-22} y={190} width={44} height={60} rx={14} fill={s.skin} />
          <g transform={`translate(0, ${bob}) rotate(${tilt})`}>
            {/* long hair behind the head */}
            {s.hairStyle === "long" && <path d="M -78 120 C -95 170 -90 230 -80 260 L 80 260 C 90 230 95 170 78 120 Z" fill={s.hair} />}
            {/* head */}
            <ellipse cx={0} cy={130} rx={72} ry={84} fill={s.skin} />
            {/* ears */}
            <ellipse cx={-72} cy={140} rx={12} ry={18} fill={s.skin} />
            <ellipse cx={72} cy={140} rx={12} ry={18} fill={s.skin} />
            {/* hair */}
            {s.hairStyle === "short" && <path d="M -76 112 C -76 30 76 30 76 112 C 62 84 32 74 0 76 C -32 74 -62 84 -76 112 Z" fill={s.hair} />}
            {s.hairStyle === "side" && <path d="M -78 116 C -84 28 74 22 80 98 C 62 62 26 62 -6 90 C -32 72 -58 82 -78 116 Z" fill={s.hair} />}
            {s.hairStyle === "long" && <path d="M -76 118 C -76 40 76 40 76 118 C 60 88 30 78 0 80 C -30 78 -60 88 -76 118 Z" fill={s.hair} />}
            {/* brows */}
            <path d={`M -44 ${104 - browLift} q 16 -10 32 -2`} stroke={s.hair} strokeWidth={5} fill="none" strokeLinecap="round" />
            <path d={`M 12 ${102 - browLift} q 16 -8 32 2`} stroke={s.hair} strokeWidth={5} fill="none" strokeLinecap="round" />
            {/* eyes */}
            <g transform={`translate(-28, 124) scale(1, ${1 - blink * 0.92})`}>
              <ellipse cx={0} cy={0} rx={11} ry={8} fill="#fff" />
              <circle cx={2} cy={0} r={4.5} fill={s.eyes} />
            </g>
            <g transform={`translate(28, 124) scale(1, ${1 - blink * 0.92})`}>
              <ellipse cx={0} cy={0} rx={11} ry={8} fill="#fff" />
              <circle cx={2} cy={0} r={4.5} fill={s.eyes} />
            </g>
            {s.glasses && (
              <g stroke="#333" strokeWidth={3} fill="none">
                <rect x={-46} y={112} width={36} height={24} rx={7} />
                <rect x={10} y={112} width={36} height={24} rx={7} />
                <line x1={-10} y1={124} x2={10} y2={124} />
              </g>
            )}
            {/* nose */}
            <path d="M 0 132 q -7 22 6 24" stroke="#c4906a" strokeWidth={3} fill="none" strokeLinecap="round" />
            {/* beard */}
            {s.beard && <path d="M -48 150 C -40 200 40 200 48 150 C 40 182 -40 182 -48 150 Z" fill={s.hair} opacity={0.85} />}
            {/* mouth */}
            <ellipse cx={0} cy={176} rx={mouthW / 2} ry={mouthH / 2} fill={s.lips} />
            {mouthH > 10 && <ellipse cx={0} cy={173} rx={mouthW / 2 - 6} ry={Math.max(1, (mouthH - 8) / 2)} fill="#5a1f1c" />}
          </g>
        </g>
      </svg>
      {name && (
        <div style={{ position: "absolute", left: 12 * sc, bottom: 10 * sc, color: "#fff", fontSize: 16 * sc, fontFamily: "Inter, Segoe UI, sans-serif", opacity: 0.85 }}>
          {name}
        </div>
      )}
    </AbsoluteFill>
  );
};
