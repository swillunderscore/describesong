// hyprwater, ported. The same pipeline as ~/.config/hypr/hyprwater, at the
// visitor's GPU's scale, with the same knobs and the same defaults as his
// hyprwater-tuning.conf:
//   wavesim.frag      — d²h/dt² = c²∇²h with viscosity, an uneven bed, sponge
//                       edges, DoG deposits (round taps + dipole strokes),
//                       ambient agitation injected OFF-SCREEN so waves arrive
//   waveSmooth        — band-limited copy (two 2x blits + gaussian) that the
//                       refraction warp reads, so the warp never folds
//   causticsplat      — forward splat of light through the surface, blurred
//   glass             — warp the backdrop by the smooth slope, add the caustic,
//                       absorption + murk
// Time model is his too: sim time = real time × speed, whole 1/120 s steps,
// sub-stepped at low speed, the render interpolating between the two stored
// states. Paused while a scan runs — CLAP needs that GPU more than a ripple.
(() => {
  const cv = document.getElementById("water"), note = document.getElementById("tcNote");
  const say = m => { if (note) note.textContent = "Water: " + m; };
  if (!cv || !window.TC) return;
  // preserveDrawingBuffer: a paused water keeps showing its last frame instead of blinking to the bare sky
  const gl = cv.getContext("webgl2", { antialias: false, alpha: false, depth: false, stencil: false, powerPreference: "low-power", preserveDrawingBuffer: true });
  if (!gl || !gl.getExtension("EXT_color_buffer_float")) { say("not available in this browser"); return; }
  gl.getExtension("OES_texture_float_linear");
  // ---- his knobs, his values (hyprwater-tuning.conf 2026-09-11) ----
  // His tuning, as he left it on 2026-09-11 (brightness/mouse/scale/speed set by
  // hand on the site; the rest from hyprwater-tuning.conf). Visitors get only
  // on/off and quality; the water itself is not a preference.
  const DEF = { intensity: 0.19, depth: 3.7, speed: 0.0567, agitation: 1, viscosity: 0, scale: 2.7, mouse: 0.46, absorption: 0, murk: 0, bed: 1 };
  const stored = TC.params.water || {};
  const W = Object.assign({}, DEF, stored, { quality: stored.quality ?? -1, enabled: stored.enabled !== false }); TC.params.water = W; if (TC.wireWater) TC.wireWater();
  const VIS = 0.105, STEP = 1 / 120, WATER_N = 1.333, SNELL = 1 - 1 / WATER_N;
  const causticK = () => Math.max(W.depth, 0.10) * SNELL * 0.080 * 0.100;     // waterCausticK()
  const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;

  const VS = `#version 300 es\nout vec2 v_texcoord; void main(){ vec2 p = vec2((gl_VertexID<<1)&2, gl_VertexID&2); v_texcoord = p; gl_Position = vec4(p*2.0-1.0, 0.0, 1.0); }`;
  const WAVESIM = `#version 300 es
precision highp float;
uniform sampler2D tex; uniform vec2 texelSize; uniform float waveSpeed, damping, volComp, bedVariation, viscosity, maxSpeed, hBias;
uniform vec4 sSeg[8]; uniform vec4 sPar[8]; uniform vec4 impulse2;
in vec2 v_texcoord; layout(location = 0) out vec4 fragColor;
float bedDepth(vec2 p) {
  float d = sin(p.x * 7.3 + 1.7) * sin(p.y * 5.9 - 0.4) + 0.55 * sin(p.x * 13.1 - 2.2) * sin(p.y * 11.7 + 1.1) + 0.30 * sin((p.x + p.y) * 19.3 + 0.6);
  return d * 0.5; }
void main() {
  vec2 uv = v_texcoord; vec4 c = texture(tex, uv);
  float h = c.r - hBias, hPrev = c.g - hBias;
  vec4 nL = texture(tex, uv + vec2(-texelSize.x, 0.0)), nR = texture(tex, uv + vec2(texelSize.x, 0.0));
  vec4 nD = texture(tex, uv + vec2(0.0, -texelSize.y)), nU = texture(tex, uv + vec2(0.0, texelSize.y));
  vec4 dA = texture(tex, uv + vec2(-texelSize.x, -texelSize.y)), dB = texture(tex, uv + vec2(texelSize.x, -texelSize.y));
  vec4 dC = texture(tex, uv + vec2(-texelSize.x, texelSize.y)), dE = texture(tex, uv + vec2(texelSize.x, texelSize.y));
  float edge = (nL.r + nR.r + nD.r + nU.r) - 4.0 * hBias, corn = (dA.r + dB.r + dC.r + dE.r) - 4.0 * hBias;
  float l = (4.0 * edge + corn - 20.0 * h) / 6.0;
  float edgeP = (nL.g + nR.g + nD.g + nU.g) - 4.0 * hBias, cornP = (dA.g + dB.g + dC.g + dE.g) - 4.0 * hBias;
  float lp = (4.0 * edgeP + cornP - 20.0 * hPrev) / 6.0;
  float localSpeed = clamp(maxSpeed * waveSpeed * (0.65 + 0.35 * bedVariation * bedDepth(v_texcoord)), 0.01, maxSpeed);
  float hNext = h + (h - hPrev) * damping + localSpeed * l + viscosity * (l - lp);
  for (int si = 0; si < 8; si++) {
    if (sPar[si].w == 0.0) continue;
    vec2 A = sSeg[si].xy, AB = sSeg[si].zw - A; float l2 = dot(AB, AB), ra = max(sPar[si].z, 1e-9);
    if (dot(sPar[si].xy, sPar[si].xy) < 0.5) {
      vec2 q = (v_texcoord - A) * vec2(1.0, texelSize.x / max(texelSize.y, 1e-6)); float d = length(q);
      hNext += (exp(-(d * d) / (ra * ra)) - 0.25 * exp(-(d * d) / (4.0 * ra * ra))) * sPar[si].w;
    } else {
      float t = l2 > 1e-12 ? clamp(dot(v_texcoord - A, AB) / l2, 0.0, 1.0) : 0.0;
      vec2 r = v_texcoord - (A + t * AB); float along = dot(r, sPar[si].xy), across = dot(r, vec2(-sPar[si].y, sPar[si].x)), rb = ra * 3.5;
      hNext += sPar[si].w * (along / ra) * exp(-(along * along) / (ra * ra) - (across * across) / (rb * rb)) * 2.0;
    }
  }
  if (impulse2.w != 0.0) {
    vec2 q2 = (v_texcoord - impulse2.xy) * vec2(1.0, texelSize.x / max(texelSize.y, 1e-6)); float d2 = length(q2), r3 = max(impulse2.z, 1e-9);
    hNext += (exp(-(d2 * d2) / (r3 * r3)) - 0.25 * exp(-(d2 * d2) / (4.0 * r3 * r3))) * impulse2.w;
  }
  hNext -= volComp;
  vec2 dW = min(v_texcoord, 1.0 - v_texcoord); float sponge = smoothstep(0.0, 0.10, min(dW.x, dW.y));
  hNext *= mix(0.96, 1.0, sponge);
  float aa = abs(hNext); if (aa > 0.30) hNext = sign(hNext) * (0.30 + 0.19 * (1.0 - exp(-(aa - 0.30) / 0.19)));
  fragColor = vec4(hNext + hBias, h + hBias, 0.0, 1.0);
}`;
  const BLIT = `#version 300 es\nprecision highp float; uniform sampler2D tex; in vec2 v_texcoord; out vec4 o; void main(){ o = texture(tex, v_texcoord); }`;
  const GAUSS = `#version 300 es
precision highp float; uniform sampler2D tex; uniform vec2 direction; uniform float radius; in vec2 v_texcoord; out vec4 o;
void main(){ float sigma = max(radius / 3.0, 0.3); vec4 acc = vec4(0.0); float wsum = 0.0; int n = int(ceil(radius));
  for (int i = -32; i <= 32; i++) { if (i < -n || i > n) continue; float w = exp(-float(i * i) / (2.0 * sigma * sigma)); acc += texture(tex, v_texcoord + direction * float(i)) * w; wsum += w; }
  o = acc / wsum; }`;
  const SPLAT_VS = `#version 300 es
precision highp float;
uniform sampler2D tex; uniform float waveSubFrac, waveBias, causticK, gridN; flat out vec2 vLand;
const float VIS = ${VIS};
float waveH(vec2 q) { vec2 uv = 0.5 + (q - 0.5) * (2.0 * VIS); vec2 hh = texture(tex, uv).rg - waveBias; return mix(hh.y, hh.x, waveSubFrac); }
void main() {
  float fid = float(gl_VertexID), iy = floor(fid / gridN), ix = fid - iy * gridN;
  vec2 tuv = (vec2(ix, iy) + 0.5) / gridN, q = 0.5 + (tuv - 0.5) / (2.0 * VIS);
  const float e = 0.0150;
  vec2 grad = vec2(waveH(q + vec2(e, 0.0)) - waveH(q - vec2(e, 0.0)), waveH(q + vec2(0.0, e)) - waveH(q - vec2(0.0, e))) / (2.0 * e);
  vec2 pq = q + causticK * grad, ptex = 0.5 + (pq - 0.5) * (2.0 * VIS);
  gl_Position = vec4(ptex * 2.0 - 1.0, 0.0, 1.0); vLand = ptex * gridN; gl_PointSize = 2.0;
}`;
  const SPLAT_FS = `#version 300 es
precision highp float; flat in vec2 vLand; out vec4 o;
void main(){ float w = max(0.0, 1.0 - abs(gl_FragCoord.x - vLand.x)) * max(0.0, 1.0 - abs(gl_FragCoord.y - vLand.y)); o = vec4(w, w, w, 0.0); }`;
  const GLASS = `#version 300 es
precision highp float;
uniform sampler2D uSky, waveTex, waveSmoothTex, causticTex;
uniform vec2 fullSize; uniform float waveSubFrac, waveBias, causticK, shimmerIntensity, shimmerScale, shimmerDepth, shimmerAbsorption, shimmerMurk, budgetPx;
in vec2 v_texcoord; out vec4 o;
const float VIS = ${VIS};
float waveHS(vec2 q) { vec2 uv = 0.5 + (q - 0.5) * (2.0 * VIS); vec2 hh = texture(waveSmoothTex, uv).rg - waveBias; return mix(hh.y, hh.x, waveSubFrac); }
vec2 waveSlopeSmooth(vec2 q, float e) { return vec2(waveHS(q + vec2(e, 0.0)) - waveHS(q - vec2(e, 0.0)), waveHS(q + vec2(0.0, e)) - waveHS(q - vec2(0.0, e))) / (2.0 * e); }
void main() {
  vec2 uv = v_texcoord;                                  // screen uv, y up (sky uploaded flipped)
  // screen -> wave field q, as the desktop maps the whole desk onto the field: a point in the water is a point on the screen
  vec2 wp = 0.5 + ((uv - 0.5) * fullSize) / max(fullSize.x, 1.0) * (0.85 * shimmerScale);
  vec2 waveGrad = waveSlopeSmooth(wp, 0.0150) * min(shimmerIntensity, 1.0);
  float qToPx = fullSize.x / max(0.85 * shimmerScale, 1e-4);
  vec2 waveWarp = waveGrad * (causticK * qToPx) / max(fullSize, vec2(1.0));
  vec2 budget = vec2(budgetPx) / max(fullSize, vec2(1.0));
  vec2 wn = abs(waveWarp) / budget; waveWarp = waveWarp * inversesqrt(sqrt(1.0 + wn * wn * wn * wn));   // p=4 soft limiter
  vec3 color = texture(uSky, uv + waveWarp).rgb;
  if (shimmerIntensity > 0.001) {
    vec2 cuv = 0.5 + (wp - 0.5) * (2.0 * VIS);
    vec3 c = texture(causticTex, cuv).rgb;
    float lum = dot(color, vec3(0.2126, 0.7152, 0.0722)); float headroom = 1.0 - smoothstep(0.55, 1.0, lum);
    vec3 cz = c - vec3(1.0);
    color += vec3(1.0, 0.985, 0.95) * max(cz, vec3(0.0)) * shimmerIntensity * 0.35 * headroom;
    color *= 1.0 + min(cz, vec3(0.0)) * shimmerIntensity * 0.5;
    vec3 ABSORB = vec3(0.340, 0.0565, 0.0092) * shimmerAbsorption; float path = 2.0 * max(shimmerDepth, 0.0), b = shimmerMurk * 2.5;
    vec3 trans = exp(-(ABSORB + vec3(b)) * path), veil = exp(-ABSORB * path * 0.5) * (1.0 - exp(-b * path));
    float amb = dot(color, vec3(0.2126, 0.7152, 0.0722));
    color = color * trans + veil * amb;
  }
  o = vec4(color, 1.0);
}`;
  const sh = (t, s) => { const x = gl.createShader(t); gl.shaderSource(x, s); gl.compileShader(x); if (!gl.getShaderParameter(x, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(x)); return x; };
  const prog = (vs, fs) => { const p = gl.createProgram(); gl.attachShader(p, sh(gl.VERTEX_SHADER, vs)); gl.attachShader(p, sh(gl.FRAGMENT_SHADER, fs)); gl.linkProgram(p); if (!gl.getProgramParameter(p, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(p)); return p; };
  let pSim, pBlit, pGauss, pSplat, pGlass;
  try { pSim = prog(VS, WAVESIM); pBlit = prog(VS, BLIT); pGauss = prog(VS, GAUSS); pSplat = prog(SPLAT_VS, SPLAT_FS); pGlass = prog(VS, GLASS); }
  catch (e) { say("shader failed: " + e.message.slice(0, 80)); console.error(e); return; }
  const U = (p, n) => gl.getUniformLocation(p, n);
  const vao = gl.createVertexArray(); gl.bindVertexArray(vao);
  const mkTex = (w, h, fmt, filt) => { const t = gl.createTexture(); gl.bindTexture(gl.TEXTURE_2D, t); gl.texImage2D(gl.TEXTURE_2D, 0, fmt, w, h, 0, fmt === gl.RGBA16F ? gl.RGBA : gl.RGBA, fmt === gl.RGBA16F ? gl.HALF_FLOAT : gl.UNSIGNED_BYTE, null);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, filt); gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, filt); gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE); gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE); return t; };
  const mkFb = t => { const f = gl.createFramebuffer(); gl.bindFramebuffer(gl.FRAMEBUFFER, f); gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, t, 0); return f; };
  const clear = (f, r = 0, g = 0) => { gl.bindFramebuffer(gl.FRAMEBUFFER, f); gl.clearColor(r, g, 0, 1); gl.clear(gl.COLOR_BUFFER_BIT); };
  const skyTex = mkTex(2, 2, gl.RGBA, gl.LINEAR); let skyV = -1;

  // ---- buffers, sized by tier (his SIM = 1024 with the caustic at 1024) ----
  const TIERS = [null, { sim: 384, cau: 384 }, { sim: 640, cau: 640 }, { sim: 1024, cau: 1024 }];
  let tier = 0, SIM = 0, CAU = 0, wave = [], waveFb = [], cur = 0, half, halfFb, smooth, smoothFb, smoothTmp, smoothTmpFb, cau, cauFb, cauTmp, cauTmpFb;
  function alloc(t) {
    SIM = TIERS[t].sim; CAU = TIERS[t].cau; cv.width = innerWidth; cv.height = innerHeight;
    wave = [mkTex(SIM, SIM, gl.RGBA16F, gl.LINEAR), mkTex(SIM, SIM, gl.RGBA16F, gl.LINEAR)]; waveFb = wave.map(mkFb); waveFb.forEach(f => clear(f));
    half = mkTex(SIM / 2, SIM / 2, gl.RGBA16F, gl.LINEAR); halfFb = mkFb(half);
    smooth = mkTex(SIM / 4, SIM / 4, gl.RGBA16F, gl.LINEAR); smoothFb = mkFb(smooth); smoothTmp = mkTex(SIM / 4, SIM / 4, gl.RGBA16F, gl.LINEAR); smoothTmpFb = mkFb(smoothTmp);
    cau = mkTex(CAU, CAU, gl.RGBA16F, gl.LINEAR); cauFb = mkFb(cau); cauTmp = mkTex(CAU, CAU, gl.RGBA16F, gl.LINEAR); cauTmpFb = mkFb(cauTmp);
    stepCount = 0; seaEnergy = 0; pendingSim = 0; strokes = []; amb = null;
  }
  // ---- input: the cursor is a fingertip trailed in the pool; a click is a tap ----
  // Screen -> wave uv, exactly as sampleMouseWake(): 0.5 + g * 0.85 * scale * 2 * VIS, g = (cursor - desk/2) / desk.x
  const toSim = (x, y) => [0.5 + (x - innerWidth / 2) / innerWidth * 0.85 * W.scale * 2 * VIS, 0.5 + (y - innerHeight / 2) / innerWidth * 0.85 * W.scale * 2 * VIS];
  let strokes = [], mk = { amount: 0, px: 0, py: 0, x: 0, y: 0, dx: 0, dy: 0 }, prevCur = null, lastMv = 0, click = null;
  addEventListener("pointermove", e => {
    const t = performance.now(); if (t - lastMv < 14) return; lastMv = t;
    if (!prevCur) { prevCur = [e.clientX, e.clientY]; return; }
    const dx = e.clientX - prevCur[0], dy = e.clientY - prevCur[1]; prevCur = [e.clientX, e.clientY];
    const mag = Math.hypot(dx, dy); if (W.mouse <= 0.001 || mag <= 0.3 || mag >= 400) return;
    const [mx, my] = toSim(e.clientX, e.clientY);
    if (mk.amount <= 1e-6) { const k = 0.85 * W.scale * 2 * VIS / innerWidth; mk.px = mx - dx * k; mk.py = my - dy * k; }
    mk.x = mx; mk.y = my; mk.dx = dx / mag; mk.dy = dy / mag; mk.r = 0.010;
    mk.amount = Math.min(mk.amount + mag * 0.00012 * W.mouse, 0.012 * Math.max(W.mouse, 0.05));
    if (Math.hypot(mk.x - mk.px, mk.y - mk.py) > 0.009 && strokes.length < 24) { strokes.push({ ...mk, round: false }); mk.px = mk.x; mk.py = mk.y; mk.amount = 0; }
  }, { passive: true });
  addEventListener("pointerdown", e => { if (W.mouse > 0.001) { const [x, y] = toSim(e.clientX, e.clientY); click = { x, y, r: 0.022, amount: 0.06 * W.mouse }; } }, { passive: true });

  // ---- the step (stepWaveSim) ----
  let stepCount = 0, seaEnergy = 0, pendingSim = 0, amb = null, lastT = 0;
  const rnd = () => Math.random();
  const uS = { tex: U(pSim, "tex"), texel: U(pSim, "texelSize"), ws: U(pSim, "waveSpeed"), damp: U(pSim, "damping"), vol: U(pSim, "volComp"), bed: U(pSim, "bedVariation"), visc: U(pSim, "viscosity"), max: U(pSim, "maxSpeed"), bias: U(pSim, "hBias"), seg: U(pSim, "sSeg"), par: U(pSim, "sPar"), imp: U(pSim, "impulse2") };
  function simSteps(dReal) {
    const speed = Math.max(0, Math.min(4, W.speed));
    const SUB = speed >= 0.4 ? 1 : (speed >= 0.15 ? 2 : 4), sub = STEP / SUB;
    pendingSim += Math.min(dReal, 0.25) * speed;
    let n = Math.floor(pendingSim / sub); n = Math.min(n, 4 * SUB); pendingSim -= n * sub;
    if (n <= 0) return { SUB, frac: Math.min(1, pendingSim / sub) };
    seaEnergy *= Math.pow(0.9958, n);
    const ag = Math.max(0, Math.min(1, W.agitation)), thick = Math.max(0, Math.min(1, W.viscosity));
    const every = Math.max(2, Math.round(Math.exp(Math.log(900) + (Math.log(6) - Math.log(900)) * ag)) * SUB);
    const visc = 0.005 + 0.060 * thick, K = 0.78, disc = Math.max(K * K * 0.5 - 4 * visc, 0), uRoot = (K / Math.SQRT2 + Math.sqrt(disc)) * 0.5;
    gl.useProgram(pSim); gl.viewport(0, 0, SIM, SIM); gl.disable(gl.BLEND);
    gl.uniform2f(uS.texel, 1 / SIM, 1 / SIM); gl.uniform1f(uS.ws, Math.min(Math.sqrt(Math.max(W.depth, 0.01)), 1)); gl.uniform1f(uS.damp, SUB === 1 ? 0.9994 : Math.pow(0.9994, 1 / SUB));
    gl.uniform1f(uS.bed, W.bed); gl.uniform1f(uS.bias, 0); gl.uniform1f(uS.visc, visc / (SUB * SUB)); gl.uniform1f(uS.max, uRoot * uRoot / (SUB * SUB)); gl.uniform1f(uS.vol, 0);
    for (let i = 0; i < n; i++) {
      stepCount++;
      // ambient agitation: a disturbance every `every` steps, somewhere in the OFF-SCREEN ring, delivered in six chunks
      if (ag > 0.001 && stepCount % every === 0 && !amb) {
        const rad = 0.025 + 0.050 * thick + 0.020 * rnd(), tame = 1 / (1 + seaEnergy * 0.12), a = (0.10 + 0.16 * rnd()) * (0.45 + 0.55 * ag) * tame; seaEnergy += a;
        const ang = rnd() * Math.PI * 2, rr = 0.29 + 0.09 * rnd();   // his ring: outside the visible ±VIS window, inside the sponge
        amb = { x: 0.5 + Math.cos(ang) * rr, y: 0.5 + Math.sin(ang) * rr, r: rad, chunk: a / 6, left: a };
      }
      if (click) { gl.uniform4f(uS.imp, click.x, click.y, click.r, -click.amount); click = null; }
      else if (amb) { const c = Math.min(amb.chunk, amb.left); amb.left -= c; gl.uniform4f(uS.imp, amb.x, amb.y, amb.r, c); if (amb.left <= 1e-6) amb = null; }
      else gl.uniform4f(uS.imp, 0, 0, 1, 0);
      const seg = new Float32Array(32), par = new Float32Array(32); let ns = 0;
      while (strokes.length && ns < 8) { const s = strokes.shift(); const ra = s.r, len = Math.hypot(s.x - s.px, s.y - s.py);
        seg[ns * 4] = s.px; seg[ns * 4 + 1] = s.py; seg[ns * 4 + 2] = s.x; seg[ns * 4 + 3] = s.y; par[ns * 4] = s.dx; par[ns * 4 + 1] = s.dy; par[ns * 4 + 2] = ra; par[ns * 4 + 3] = s.amount / (1 + 0.6 * len / ra); ns++; }
      gl.uniform4fv(uS.seg, seg); gl.uniform4fv(uS.par, par);
      gl.bindFramebuffer(gl.FRAMEBUFFER, waveFb[1 - cur]); gl.activeTexture(gl.TEXTURE0); gl.bindTexture(gl.TEXTURE_2D, wave[cur]); gl.uniform1i(uS.tex, 0);
      gl.drawArrays(gl.TRIANGLES, 0, 3); cur = 1 - cur;
    }
    return { SUB, frac: Math.min(1, pendingSim / sub) };
  }
  // ---- band-limited copy of the surface, for the warp (buildSmoothWave) ----
  const uB = { tex: U(pBlit, "tex") }, uG = { tex: U(pGauss, "tex"), dir: U(pGauss, "direction"), r: U(pGauss, "radius") };
  function blit(src, dstFb, w, h) { gl.useProgram(pBlit); gl.bindFramebuffer(gl.FRAMEBUFFER, dstFb); gl.viewport(0, 0, w, h); gl.activeTexture(gl.TEXTURE0); gl.bindTexture(gl.TEXTURE_2D, src); gl.uniform1i(uB.tex, 0); gl.drawArrays(gl.TRIANGLES, 0, 3); }
  function gauss(src, tmpFb, tmp, dstFb, w, h, radiusTexels) {
    gl.useProgram(pGauss); gl.uniform1f(uG.r, radiusTexels);
    gl.bindFramebuffer(gl.FRAMEBUFFER, tmpFb); gl.viewport(0, 0, w, h); gl.activeTexture(gl.TEXTURE0); gl.bindTexture(gl.TEXTURE_2D, src); gl.uniform1i(uG.tex, 0); gl.uniform2f(uG.dir, 1 / w, 0); gl.drawArrays(gl.TRIANGLES, 0, 3);
    gl.bindFramebuffer(gl.FRAMEBUFFER, dstFb); gl.bindTexture(gl.TEXTURE_2D, tmp); gl.uniform2f(uG.dir, 0, 1 / h); gl.drawArrays(gl.TRIANGLES, 0, 3);
  }
  function buildSmooth() {
    blit(wave[cur], halfFb, SIM / 2, SIM / 2); blit(half, smoothFb, SIM / 4, SIM / 4);                        // two exact 2x steps, never one 4x
    const sigmaSim = Math.max(3, Math.min(24, 95 * Math.sqrt(causticK())));
    gauss(smooth, smoothTmpFb, smoothTmp, smoothFb, SIM / 4, SIM / 4, 3 * sigmaSim / 4);
  }
  // ---- caustic: forward splat, then the reconstruction blur ----
  const uP = { tex: U(pSplat, "tex"), frac: U(pSplat, "waveSubFrac"), bias: U(pSplat, "waveBias"), k: U(pSplat, "causticK"), n: U(pSplat, "gridN") };
  function buildCaustic(frac) {
    gl.useProgram(pSplat); gl.bindFramebuffer(gl.FRAMEBUFFER, cauTmpFb); gl.viewport(0, 0, CAU, CAU); gl.clearColor(0, 0, 0, 1); gl.clear(gl.COLOR_BUFFER_BIT);
    gl.enable(gl.BLEND); gl.blendFunc(gl.ONE, gl.ONE);
    gl.activeTexture(gl.TEXTURE0); gl.bindTexture(gl.TEXTURE_2D, wave[cur]); gl.uniform1i(uP.tex, 0); gl.uniform1f(uP.frac, frac); gl.uniform1f(uP.bias, 0); gl.uniform1f(uP.k, causticK()); gl.uniform1f(uP.n, CAU);
    gl.drawArrays(gl.POINTS, 0, CAU * CAU); gl.disable(gl.BLEND);
    const lensK = causticK() * 10; gauss(cauTmp, cauFb, cau, cauTmpFb, CAU, CAU, Math.max(2.1, Math.min(12, lensK * 30)));   // result lands in cauTmp
  }
  // ---- glass ----
  const uL = { sky: U(pGlass, "uSky"), wave: U(pGlass, "waveTex"), sm: U(pGlass, "waveSmoothTex"), cau: U(pGlass, "causticTex"), full: U(pGlass, "fullSize"), frac: U(pGlass, "waveSubFrac"), bias: U(pGlass, "waveBias"), k: U(pGlass, "causticK"), int: U(pGlass, "shimmerIntensity"), sc: U(pGlass, "shimmerScale"), dep: U(pGlass, "shimmerDepth"), abs: U(pGlass, "shimmerAbsorption"), murk: U(pGlass, "shimmerMurk"), bud: U(pGlass, "budgetPx") };
  function glass(frac) {
    if (skyV !== TC.skyVersion) { skyV = TC.skyVersion; gl.activeTexture(gl.TEXTURE3); gl.bindTexture(gl.TEXTURE_2D, skyTex); gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, true); gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, TC.sky); gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, false); }
    gl.useProgram(pGlass); gl.bindFramebuffer(gl.FRAMEBUFFER, null); gl.viewport(0, 0, cv.width, cv.height);
    gl.activeTexture(gl.TEXTURE0); gl.bindTexture(gl.TEXTURE_2D, wave[cur]); gl.uniform1i(uL.wave, 0);
    gl.activeTexture(gl.TEXTURE1); gl.bindTexture(gl.TEXTURE_2D, smooth); gl.uniform1i(uL.sm, 1);
    gl.activeTexture(gl.TEXTURE2); gl.bindTexture(gl.TEXTURE_2D, cauTmp); gl.uniform1i(uL.cau, 2);
    gl.activeTexture(gl.TEXTURE3); gl.bindTexture(gl.TEXTURE_2D, skyTex); gl.uniform1i(uL.sky, 3);
    gl.uniform2f(uL.full, cv.width, cv.height); gl.uniform1f(uL.frac, frac); gl.uniform1f(uL.bias, 0); gl.uniform1f(uL.k, causticK());
    gl.uniform1f(uL.int, W.intensity); gl.uniform1f(uL.sc, W.scale); gl.uniform1f(uL.dep, W.depth); gl.uniform1f(uL.abs, W.absorption); gl.uniform1f(uL.murk, W.murk); gl.uniform1f(uL.bud, 36);
    gl.drawArrays(gl.TRIANGLES, 0, 3);
  }
  // ---- tiers: measured on this GPU, overridable, paused while scanning ----
  let auto = 2, probing = true, probeT = [];
  const QN = ["off", "low", "mid", "high"];
  // frozen whenever nobody is looking: hidden tab, another window on top, or a scan that needs the GPU
  // An unfocused-but-visible window keeps running: the block colours drift
  // regardless, and a frozen water under drifting blocks looked broken.
  // off = the user's choice (canvas hidden, nothing runs). paused = nobody is
  // looking or the GPU is needed: the field is KEPT and the last frame stays
  // on screen, so coming back resumes the same water instead of a fresh pool.
  const off = () => W.enabled === false || reduced;
  const paused = () => document.hidden || !!document.documentElement.dataset.scanning;
  const wanted = () => off() ? 0 : (W.quality >= 0 ? W.quality : auto);
  function apply(t) {
    if (t === tier) return; tier = t;
    if (!t) { cv.hidden = true; return; }
    if (TIERS[t].sim !== SIM) alloc(t);            // only a resolution change rebuilds the field
    cv.hidden = false;
  }
  const status = extra => say(off() ? "off" : (W.quality >= 0 ? QN[W.quality] : `auto → ${QN[auto]}`) + (document.documentElement.dataset.scanning ? " · paused for the scan" : paused() ? " · paused" : "") + (extra || (probing ? " · measuring…" : "")));
  let refresh = () => {};
  function loop(now) {
    requestAnimationFrame(loop);
    const want = wanted(); if (want !== tier) { apply(want); status(); }
    if (!tier || paused()) { lastT = now; return; }
    const dReal = lastT ? (now - lastT) / 1000 : 0; lastT = now;
    if (probing && dReal > 0 && dReal < 0.2) { probeT.push(dReal * 1000); if (probeT.length >= 110) {
      const s = probeT.slice(20), mean = s.reduce((a, b) => a + b, 0) / s.length, base = Math.min(...s); probing = false;
      if (W.quality < 0 && mean > base * 1.35) { auto = auto > 1 ? auto - 1 : 0; apply(wanted()); }
      status(` · ${mean.toFixed(1)} ms/frame on this GPU`);
    } }
    const { frac } = simSteps(dReal);
    buildSmooth(); buildCaustic(frac); glass(frac);
  }
  addEventListener("resize", () => { if (tier) { cv.width = innerWidth; cv.height = innerHeight; } });
  document.addEventListener("visibilitychange", () => setTimeout(refresh, 0));
  apply(wanted()); status(); requestAnimationFrame(loop);
  refresh = () => { const w = wanted(); if (w !== tier) apply(w); status(); };
  window.WATER = { tier: () => tier, auto: () => auto, params: W, defaults: DEF, status, steps: () => stepCount, paused, refresh };
})();
