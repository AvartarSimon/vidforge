// GLSL for the live effects. Every texture keeps the image's top row at v = 0 (DOM uploads do that
// without UNPACK_FLIP_Y, and the FBO passes write in the same orientation); only the last pass,
// which draws to the canvas, flips — see `u_flip` in the vertex shader.

export const VERT = `#version 300 es
in vec2 a_pos;
uniform float u_flip;
out vec2 v_uv;
void main() {
  v_uv = vec2(a_pos.x * 0.5 + 0.5, u_flip > 0.5 ? 0.5 - a_pos.y * 0.5 : 0.5 + a_pos.y * 0.5);
  gl_Position = vec4(a_pos, 0.0, 1.0);
}`

// 美型: inverse warps, so every output pixel looks up where its content should come from.
// Eyes use a local scale (content near the centre is magnified, the rim stays put); the face uses a
// local translation of a few jaw-line anchors toward the middle of the lower face. Both fall off
// to zero at their radius, so nothing outside the face moves.
export const WARP = `#version 300 es
precision highp float;
in vec2 v_uv;
out vec4 o;
uniform sampler2D u_src;
uniform vec2 u_res;
uniform float u_on;
uniform vec4 u_eye[2];   // xy centre (px), z radius (px), w strength
uniform vec4 u_pt[6];    // xy anchor (px), zw displacement (px)
uniform float u_ptR;
void main() {
  vec2 p = v_uv * u_res;
  vec2 off = vec2(0.0);
  if (u_on > 0.5) {
    for (int i = 0; i < 2; i++) {
      vec2 d = p - u_eye[i].xy;
      float r = length(d) / max(u_eye[i].z, 1.0);
      if (r < 1.0) off -= d * u_eye[i].w * (1.0 - r * r);
    }
    for (int i = 0; i < 6; i++) {
      float r = length(p - u_pt[i].xy) / max(u_ptR, 1.0);
      if (r < 1.0) { float f = 1.0 - r * r; off -= u_pt[i].zw * f * f; }
    }
  }
  o = texture(u_src, (p + off) / u_res);
}`

// 磨皮: a bilateral filter — it only averages neighbours that already look alike, so skin flattens
// while eyes, brows, lips and the jaw edge (big colour steps) survive. Same idea as videofx.py.
export const BILATERAL = `#version 300 es
precision highp float;
in vec2 v_uv;
out vec4 o;
uniform sampler2D u_tex;
uniform vec2 u_px;
uniform float u_radius;
uniform float u_sigma;
void main() {
  vec3 c = texture(u_tex, v_uv).rgb;
  vec3 sum = c;
  float ws = 1.0;
  for (int ring = 1; ring <= 3; ring++) {
    float rr = u_radius * float(ring) / 3.0;
    for (int k = 0; k < 8; k++) {
      float a = 6.2831853 * float(k) / 8.0 + float(ring) * 0.39;
      vec3 s = texture(u_tex, v_uv + vec2(cos(a), sin(a)) * rr * u_px).rgb;
      vec3 df = s - c;
      float w = exp(-dot(df, df) / (2.0 * u_sigma * u_sigma)) * exp(-float(ring * ring) / 4.5);
      sum += s * w;
      ws += w;
    }
  }
  o = vec4(sum / ws, 1.0);
}`

export const BLUR = `#version 300 es
precision highp float;
in vec2 v_uv;
out vec4 o;
uniform sampler2D u_tex;
uniform vec2 u_dir;
void main() {
  vec3 c = texture(u_tex, v_uv).rgb * 0.2270270;
  c += texture(u_tex, v_uv + u_dir * 1.3846154).rgb * 0.3162162;
  c += texture(u_tex, v_uv - u_dir * 1.3846154).rgb * 0.3162162;
  c += texture(u_tex, v_uv + u_dir * 3.2307692).rgb * 0.0702703;
  c += texture(u_tex, v_uv - u_dir * 3.2307692).rgb * 0.0702703;
  o = vec4(c, 1.0);
}`

// Everything else in one pass. Mask channels: r = person, g = skin, b = clothes, a = hair.
export const COMPOSITE = `#version 300 es
precision highp float;
in vec2 v_uv;
out vec4 o;
uniform sampler2D u_warp;
uniform sampler2D u_smooth;
uniform sampler2D u_mask;
uniform sampler2D u_blur;
uniform sampler2D u_bg;
uniform vec2 u_px;
uniform vec4 u_crop;      // output uv -> source uv: xy offset, zw scale
uniform vec4 u_bgX;       // output uv -> background uv
uniform int u_bgMode;     // 0 none, 1 blur, 2 picture/video, 3 colour
uniform vec3 u_bgColor;
uniform float u_hasMask;
uniform float u_smoothAmt, u_whiten, u_rosy, u_sharpen, u_bright, u_contrast, u_sat, u_warm, u_edge;
uniform float u_clothes, u_hair;
uniform vec3 u_clothesC, u_hairC;

vec3 rgb2hsl(vec3 c) {
  float mx = max(c.r, max(c.g, c.b)), mn = min(c.r, min(c.g, c.b));
  float l = (mx + mn) * 0.5, h = 0.0, s = 0.0, d = mx - mn;
  if (d > 1e-5) {
    s = l > 0.5 ? d / (2.0 - mx - mn) : d / (mx + mn);
    if (mx == c.r) h = (c.g - c.b) / d + (c.g < c.b ? 6.0 : 0.0);
    else if (mx == c.g) h = (c.b - c.r) / d + 2.0;
    else h = (c.r - c.g) / d + 4.0;
    h /= 6.0;
  }
  return vec3(h, s, l);
}
float hue2rgb(float p, float q, float t) {
  t = fract(t);
  if (t < 1.0 / 6.0) return p + (q - p) * 6.0 * t;
  if (t < 0.5) return q;
  if (t < 2.0 / 3.0) return p + (q - p) * (2.0 / 3.0 - t) * 6.0;
  return p;
}
vec3 hsl2rgb(vec3 c) {
  if (c.y < 1e-5) return vec3(c.z);
  float q = c.z < 0.5 ? c.z * (1.0 + c.y) : c.z + c.y - c.z * c.y;
  float p = 2.0 * c.z - q;
  return vec3(hue2rgb(p, q, c.x + 1.0 / 3.0), hue2rgb(p, q, c.x), hue2rgb(p, q, c.x - 1.0 / 3.0));
}
// keep the pixel's own lightness (its shading, creases, highlights) and take hue and saturation
// from the target, so a recoloured shirt still looks lit by the room
vec3 recolour(vec3 col, vec3 target) {
  vec3 h = rgb2hsl(col), t = rgb2hsl(target);
  return hsl2rgb(vec3(t.x, t.y, clamp(h.z + (t.z - 0.5) * 0.7, 0.0, 1.0)));
}

void main() {
  vec2 uv = u_crop.xy + v_uv * u_crop.zw;
  vec3 w = texture(u_warp, uv).rgb;
  vec4 m = u_hasMask > 0.5 ? texture(u_mask, uv) : vec4(1.0, 0.0, 0.0, 0.0);
  float skin = m.g;
  vec3 col = w;
  if (u_smoothAmt > 0.0) col = mix(col, texture(u_smooth, uv).rgb, clamp(u_smoothAmt * skin * 1.1, 0.0, 1.0));
  if (u_sharpen > 0.0) {
    vec3 b = (texture(u_warp, uv + vec2(u_px.x, 0.0)).rgb + texture(u_warp, uv - vec2(u_px.x, 0.0)).rgb
            + texture(u_warp, uv + vec2(0.0, u_px.y)).rgb + texture(u_warp, uv - vec2(0.0, u_px.y)).rgb) * 0.25;
    // not on skin that was just smoothed: that would put back the texture 磨皮 took out
    col += (w - b) * u_sharpen * 2.0 * (1.0 - skin * u_smoothAmt);
  }
  if (u_whiten > 0.0) {
    float beta = 1.0 + u_whiten * 4.0;
    vec3 wc = log(max(col, 0.0) * (beta - 1.0) + 1.0) / log(beta);
    col = mix(col, wc, 0.25 + 0.75 * skin);
  }
  if (u_rosy > 0.0) col = mix(col, col * vec3(1.05, 0.96, 0.98) + vec3(0.025, 0.0, 0.01), u_rosy * skin);
  if (u_clothes > 0.0) col = mix(col, recolour(col, u_clothesC), m.b * u_clothes);
  if (u_hair > 0.0) col = mix(col, recolour(col, u_hairC), m.a * u_hair);
  col += u_bright * 0.25;
  col = (col - 0.5) * (1.0 + u_contrast * 0.5) + 0.5;
  float l = dot(col, vec3(0.299, 0.587, 0.114));
  col = mix(vec3(l), col, 1.0 + u_sat);
  col += vec3(u_warm, 0.0, -u_warm) * 0.06;
  if (u_bgMode > 0) {
    float person = smoothstep(0.45 - 0.35 * u_edge, 0.55 + 0.15 * u_edge, m.r);
    vec3 bg = u_bgMode == 1 ? texture(u_blur, uv).rgb
            : u_bgMode == 2 ? texture(u_bg, v_uv * u_bgX.zw + u_bgX.xy).rgb
            : u_bgColor;
    col = mix(bg, col, person);
  }
  o = vec4(clamp(col, 0.0, 1.0), 1.0);
}`
