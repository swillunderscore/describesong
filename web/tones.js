// technicolor for a web page. The desktop this comes from recolours every
// block from the current wallpaper's two-tone gradient pair; here the
// "wallpaper" is a pixel-art dither field painted from two tones that drift
// through hue for as long as the page is open (a full turn every 4 minutes).
// Two tones, ink chosen by contrast — the same rules as the bar. The corner
// sliders are the desktop's Colors tab: hue offset, saturation, brightness.
const root = document.documentElement, cv = document.getElementById("wp"), ctx = cv.getContext("2d", { alpha: false });
const CELL = 6, BAYER = [[0,32,8,40,2,34,10,42],[48,16,56,24,50,18,58,26],[12,44,4,36,14,46,6,38],[60,28,52,20,62,30,54,22],[3,35,11,43,1,33,9,41],[51,19,59,27,49,17,57,25],[15,47,7,39,13,45,5,37],[63,31,55,23,61,29,53,21]];
const still = matchMedia("(prefers-reduced-motion: reduce)").matches;
const KEY = "describesong.tc.v1";
const P = Object.assign({ h: 0, s: 100, v: 100, drift: true }, (() => { try { return JSON.parse(localStorage.getItem(KEY) || "{}"); } catch { return {}; } })());
const save = () => { try { localStorage.setItem(KEY, JSON.stringify(P)); } catch {} };
let hue = (Date.now() / 1000 / 240 * 360) % 360;          // same hue for everyone at the same moment
function oklch(L, C, h) {                                 // -> [r,g,b] 0..255, sRGB
  const a = C * Math.cos(h * Math.PI / 180), b = C * Math.sin(h * Math.PI / 180);
  const l_ = L + .3963377774 * a + .2158037573 * b, m_ = L - .1055613458 * a - .0638541728 * b, s_ = L - .0894841775 * a - 1.291485548 * b;
  const l = l_ ** 3, m = m_ ** 3, s = s_ ** 3;
  const lin = [4.0767416621 * l - 3.3077115913 * m + .2309699292 * s, -1.2684380046 * l + 2.6097574011 * m - .3413193965 * s, -.0041960863 * l - .7034186147 * m + 1.707614701 * s];
  return lin.map(v => { v = Math.max(0, Math.min(1, v)); return Math.round(255 * (v <= .0031308 ? 12.92 * v : 1.055 * v ** (1 / 2.4) - .055)); });
}
const css = c => `rgb(${c[0]} ${c[1]} ${c[2]})`;
const lum = c => { const f = v => { v /= 255; return v <= .04045 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4; }; return .2126 * f(c[0]) + .7152 * f(c[1]) + .0722 * f(c[2]); };
let cur = null;
function tones() {
  const hh = (P.drift ? hue + P.h : P.h), cs = P.s / 100, lv = P.v / 100;   // drift off = the slider IS the colour
  // the pair — solid block colours, like the p/s roles the desktop paints
  // every app with. Ink flips at the same luminance threshold the desktop uses.
  const A = oklch(.64 * lv, .12 * cs, hh), B = oklch(.68 * lv, .13 * cs, hh + 160);
  const Ad = oklch(.40 * lv, .11 * cs, hh), Bd = oklch(.34 * lv, .10 * cs, hh + 160);   // the same hues, deep: the pixel sky in the gaps
  root.style.setProperty("--a", css(A)); root.style.setProperty("--b", css(B));
  root.style.setProperty("--ad", css(Ad)); root.style.setProperty("--bd", css(Bd));
  const dark = lum(A) > 0.184;
  root.style.setProperty("--ink", dark ? "#15151a" : "#f5f5f8");
  root.style.setProperty("--ink2", dark ? "rgb(21 21 26 / .68)" : "rgb(245 245 248 / .72)");
  root.style.setProperty("--ink3", dark ? "rgb(21 21 26 / .45)" : "rgb(245 245 248 / .5)");
  return (cur = { A, B, Ad, Bd });
}
// separable box blur on RGBA bytes, radius r cells (the canvas is ~300 cells wide, so this is cheap)
function blur(d, w, h, r) {
  const tmp = new Uint8ClampedArray(d.length), n = 2 * r + 1;
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) { let R = 0, G = 0, B = 0; for (let k = -r; k <= r; k++) { const xx = Math.min(w - 1, Math.max(0, x + k)), i = (y * w + xx) * 4; R += d[i]; G += d[i + 1]; B += d[i + 2]; } const o = (y * w + x) * 4; tmp[o] = R / n; tmp[o + 1] = G / n; tmp[o + 2] = B / n; tmp[o + 3] = 255; }
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) { let R = 0, G = 0, B = 0; for (let k = -r; k <= r; k++) { const yy = Math.min(h - 1, Math.max(0, y + k)), i = (yy * w + x) * 4; R += tmp[i]; G += tmp[i + 1]; B += tmp[i + 2]; } const o = (y * w + x) * 4; d[o] = R / n; d[o + 1] = G / n; d[o + 2] = B / n; d[o + 3] = 255; }
}
function size() { cv.width = Math.ceil(innerWidth / CELL); cv.height = Math.ceil(innerHeight / CELL); }
let t0 = performance.now(), last = -1e9;
window.TC = { params: P, sky: cv, skyVersion: 0, tones: () => cur || tones(), save };
function paint(now) {
  const t = (now - t0) / 1000;
  if (!still) hue = (hue + (now - last > 0 ? (now - last) / 1000 * 1.5 : 0)) % 360;  // 1.5°/s
  last = now;
  const { Ad, Bd, A, B } = tones();
  const w = cv.width, h = cv.height, img = ctx.createImageData(w, h), d = img.data;
  for (let y = 0; y < h; y++) {
    const v = y / h;
    for (let x = 0; x < w; x++) {
      // a slow sky: vertical gradient, two long swells drifting across, a faint band of "sun"
      const f = v * 1.15 + .10 * Math.sin(x / w * 6.3 + t * .05 + v * 4) + .06 * Math.sin(x / w * 17 - t * .03) + .12 * Math.exp(-((v - .62) ** 2) / .01) - .10;
      // smooth: a soft blend between the two deep tones, the light pair
      // catching the "sun" band — the wallpaper as seen THROUGH glass, blurred,
      // which is what the desktop shows in the gaps (the dither read as stripes)
      const t1 = Math.max(0, Math.min(1, f)), gl = Math.max(0, 1 - f / .32);
      const base = [Ad[0] + (Bd[0] - Ad[0]) * t1, Ad[1] + (Bd[1] - Ad[1]) * t1, Ad[2] + (Bd[2] - Ad[2]) * t1];
      const lt = ((x + y) & 1) ? A : B;
      const c = [base[0] + (lt[0] - base[0]) * gl * .55, base[1] + (lt[1] - base[1]) * gl * .55, base[2] + (lt[2] - base[2]) * gl * .55];
      const i = (y * w + x) * 4; d[i] = c[0]; d[i + 1] = c[1]; d[i + 2] = c[2]; d[i + 3] = 255;
    }
  }
  blur(d, w, h, 3); blur(d, w, h, 3);            // two box passes ≈ gaussian: the glass blur
  ctx.putImageData(img, 0, 0); TC.skyVersion++;
}
size(); addEventListener("resize", () => { size(); paint(performance.now()); });
paint(performance.now());
if (!still) setInterval(() => paint(performance.now()), 400);   // 2.5 fps is plenty for a drift this slow

// ---- the corner sliders: the desktop's Colors tab, then its Water tab ----
const tc = document.getElementById("tc");
if (tc) {
  const $ = id => document.getElementById(id);
  const show = () => { $("tcHo").value = P.h + "°"; $("tcSo").value = P.s + "%"; $("tcVo").value = P.v + "%"; $("tcDrift").checked = !!P.drift; };
  $("tcH").value = P.h; $("tcS").value = P.s; $("tcV").value = P.v; show();
  const on = (id, k, f) => $(id).addEventListener("input", e => { P[k] = f(e.target.value); save(); show(); paint(performance.now()); });
  on("tcH", "h", v => +v); on("tcS", "s", v => +v); on("tcV", "v", v => +v);
  $("tcDrift").addEventListener("change", e => { P.drift = e.target.checked; if (!P.drift && P.h === 0) { P.h = Math.round(hue); $("tcH").value = P.h; } save(); show(); paint(performance.now()); });
  // only the header toggles; the body stays put (clicking a slider used to re-open it)
  tc.querySelector(".tch").addEventListener("click", () => { tc.classList.toggle("open"); $("tcx").textContent = tc.classList.contains("open") ? "▴" : "▾"; });
  document.addEventListener("click", e => { if (tc.classList.contains("open") && !tc.contains(e.target)) { tc.classList.remove("open"); $("tcx").textContent = "▾"; } });
  // water knobs: read and written through TC.params.water at the moment of use
  // (water.js replaces that object when it starts, so nothing may capture it).
  const QN = ["auto", "off", "low", "mid", "high"];
  const spd = { to: v => Math.exp(Math.log(0.002) + (Math.log(4) - Math.log(0.002)) * v / 100), from: sp => Math.round(100 * (Math.log(Math.max(sp, 0.002)) - Math.log(0.002)) / (Math.log(4) - Math.log(0.002))) };
  const fmtW = (k, v) => k === "quality" ? QN[v + 1] : k === "speed" ? (+v).toFixed(3) : (+v).toFixed(2);
  TC.wireWater = () => {
    const Wp = P.water; if (!Wp) return;
    const en = $("w_enabled"); en.checked = Wp.enabled !== false;
    if (!en.dataset.wired) { en.dataset.wired = "1"; en.addEventListener("change", e => { P.water.enabled = e.target.checked; save(); if (window.WATER) WATER.refresh(); }); }
    for (const el of tc.querySelectorAll('input[id^="w_"][type="range"]')) {
      const k = el.id.slice(2), out = el.nextElementSibling;
      el.value = k === "speed" ? spd.from(Wp.speed) : Wp[k]; out.value = fmtW(k, Wp[k]);
      if (!el.dataset.wired) { el.dataset.wired = "1"; el.addEventListener("input", e => { const Wn = P.water; Wn[k] = k === "speed" ? spd.to(+e.target.value) : +e.target.value; out.value = fmtW(k, Wn[k]); save(); if (window.WATER) WATER.refresh(); }); }
    }
  };
  $("tcMore").addEventListener("click", () => { const b = $("tcMoreBody"); b.hidden = !b.hidden; $("tcMore").textContent = b.hidden ? "I like settings" : "Enough settings"; });
  $("tcReset").addEventListener("click", () => { if (window.WATER) { Object.assign(P.water, WATER.defaults); save(); TC.wireWater(); WATER.refresh(); } });
}
