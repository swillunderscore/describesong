// describesong — worker: fingerprint (Chromaprint, WASM) + embedding (CLAP, transformers.js).
// Receives 48 kHz mono PCM; nothing here touches the network except the model download.
import init, { fingerprint } from "./wasm/fingerprint_wasm.js";
import { stft } from "./stft.js";
import { normWords, grams } from "./lyrichash.js";
import { AutoProcessor, ClapAudioModelWithProjection, AutoModelForAudioClassification, env } from "https://cdn.jsdelivr.net/npm/@huggingface/transformers@3.8.1";

const MODEL = "Xenova/larger_clap_music_and_speech";
const WIN_S = 10, MAX_WINDOWS = 8, MOMENTS = 4;
let proc, model;

// ---- MuLan: the other ear, run through ONNX Runtime Web ---------------------
// Its audio tower is a plain ONNX graph; the one step ORT Web cannot do (the
// STFT) happens in stft.js just before. See QUEUE.md for the numbers.
const MULAN_REPO = "https://huggingface.co/swillsoftware/describesong-mulan/resolve/main/";
const MULAN = {
  // HOSTED ON HUGGING FACE, not the Pi. Cloudflare will not cache a file over
  // 512 MB below Enterprise, so served from home this came off his upstream on
  // every visit. Hugging Face has no such cap, serves it from a real CDN with
  // open CORS and range requests, and takes his connection out of the path.
  onnx: MULAN_REPO + "mulan_spec_fp16.onnx",
  // THE WEIGHTS. ORT Web does not fetch a model's external data on its own —
  // forget this and you get a bare numeric error with no message — so it is
  // declared here beside the model and the two cannot drift apart.
  data: MULAN_REPO + "mulan_spec_fp16.onnx.data",
  windows: 3, rate: 24000, win_s: 10,
};let ort = null, mulan = null, mulanDevice = "";
// WE KEEP THE WEIGHTS OURSELVES. Hugging Face answers with `cache-control:
// no-store` and a signed CDN link that expires, so the browser is forbidden
// from keeping the 635 MB and re-downloads it on every single visit. Served
// from the Pi instead, Cloudflare refuses anything over 512 MB. Either way the
// host decides, and both hosts decide wrong — so the bytes go into the Cache
// API under our own key and are read from there forever after.
const MULAN_CACHE = "describesong-mulan-v1";
async function cachedBytes(url, onProgress) {
  let cache = null;
  try { cache = await caches.open(MULAN_CACHE); } catch {}          // private windows have no cache
  if (cache) {
    const hit = await cache.match(url).catch(() => null);
    if (hit) return new Uint8Array(await hit.arrayBuffer());
  }
  const res = await fetch(url);
  if (!res.ok) throw new Error(`could not fetch ${url.split("/").pop()}: HTTP ${res.status}`);
  const buf = await res.arrayBuffer();
  if (cache) { try { await cache.put(url, new Response(buf.slice(0))); } catch {} }   // quota, private mode
  return new Uint8Array(buf);
}
async function initMulan(onProgress) {
  if (mulan) return;
  if (!ort) ort = await import("https://cdn.jsdelivr.net/npm/onnxruntime-web@1.20.1/dist/ort.webgpu.min.mjs");
  ort.env.wasm.numThreads = 1;
  const [graph, weights] = await Promise.all([cachedBytes(MULAN.onnx), cachedBytes(MULAN.data)]);
  const externalData = [{ path: "mulan_spec_fp16.onnx.data", data: weights }];
  const order = navigator.gpu ? ["webgpu", "wasm"] : ["wasm"];
  let last;
  for (const ep of order) {
    try {
      mulan = await ort.InferenceSession.create(graph, { executionProviders: [ep], externalData });
      mulanDevice = ep; return;
    } catch (e) { last = e; console.warn("MuLan on", ep, "failed:", String(e && e.message || e).slice(0, 200)); }
  }
  throw new Error("the sound model could not load in this browser: " + String(last && last.message || last).slice(0, 120));
}
// 48 kHz -> 24 kHz: the same windowed-sinc low-pass idea as the tagger's, at 2:1.
const LP24 = (() => { const N = 33, h = new Float32Array(N), fc = 0.23; let s = 0;
  for (let i = 0; i < N; i++) { const n = i - (N - 1) / 2, v = n === 0 ? 2 * fc : Math.sin(2 * Math.PI * fc * n) / (Math.PI * n), w = 0.54 - 0.46 * Math.cos(2 * Math.PI * i / (N - 1)); h[i] = v * w; s += h[i]; }
  for (let i = 0; i < N; i++) h[i] /= s; return h; })();
function to24k(x) {
  const n = Math.floor(x.length / 2), y = new Float32Array(n), N = LP24.length, M = (N - 1) / 2;
  for (let i = 0; i < n; i++) { const c = i * 2; let a = 0; for (let k = 0; k < N; k++) { const j = c + k - M; if (j >= 0 && j < x.length) a += LP24[k] * x[j]; } y[i] = a; }
  return y;
}
// his trial vectors were made from windows at 20/50/80 % — match them exactly,
// or the 2,035 already seeded would not line up with anything scanned later
function mulanWindows(pcm24) {
  const w = MULAN.win_s * MULAN.rate, n = pcm24.length, out = [];
  for (let i = 0; i < MULAN.windows; i++) {
    const c = Math.round((0.2 + 0.3 * i) * n);
    let st = Math.max(0, Math.min(Math.max(0, n - w), c - (w >> 1)));
    let seg = pcm24.subarray(st, st + w);
    if (seg.length < w) { const p = new Float32Array(w); p.set(seg); seg = p; }
    out.push(seg);
  }
  return out;
}
async function embedMulan(pcm48) {
  await initMulan();
  const pcm24 = to24k(pcm48), vecs = [];
  for (const seg of mulanWindows(pcm24)) {
    const S = stft(seg);
    const feed = {}; feed[mulan.inputNames[0]] = new ort.Tensor("float32", S.data, S.dims);
    const out = await mulan.run(feed);
    vecs.push(Float32Array.from(out[mulan.outputNames[0]].data));
  }
  const mean = new Float32Array(512);
  for (const v of vecs) { const u = unit(v); for (let i = 0; i < 512; i++) mean[i] += u[i] / vecs.length; }
  return { mean: unit(mean), moments: vecs.slice(0, MOMENTS).map(unit) };
}

let DEVICE = "", EAR = "clap";
// The sound-event tagger: an AudioSet classifier (527 classes). Measured on his
// own labels: 88-100 % precision on hand claps and whistling, where CLAP was
// 0-8 %. Loaded on demand the first time a track needs tagging.
const AST = "Xenova/ast-finetuned-audioset-10-10-0.4593";
let astProc = null, astModel = null, EVENTS = null, astReady = null, astRung = 0;
// One load, shared. The scan asks for several tracks at once and each call
// used to start its own copy of the model: on the first library re-scan that
// was four 174 MB instantiations side by side, the GPU ran out, and nearly
// every track logged ✗. A failed load is forgotten so the next track tries
// the next rung; an exhausted ladder fails fast instead of re-downloading.
const AST_LADDER = [{ dtype: "fp16", device: "webgpu" }, { dtype: "q8", device: "wasm" }];
async function initAst() {
  if (astModel) return;
  if (!astReady) astReady = (async () => {
    EVENTS ||= await (await fetch("events.json")).json();
    astProc ||= await AutoProcessor.from_pretrained(AST);
    if (!navigator.gpu && astRung === 0) astRung = 1;
    for (; astRung < AST_LADDER.length; astRung++) {
      try { astModel = await AutoModelForAudioClassification.from_pretrained(AST, AST_LADDER[astRung]); return; }
      catch (e) { console.warn("sound tagger: load failed on", AST_LADDER[astRung].device, "-", e.message); }
    }
    throw new Error("the sound tagger could not load in this browser");
  })().finally(() => { astReady = null; });
  await astReady;
}
// 48 kHz -> 16 kHz: a 33-tap windowed-sinc low-pass at 7.2 kHz, then every
// third sample. The first version was a 3-tap average, which let the top two
// octaves alias into the band; against the reference PyTorch model on the
// same file the browser's probabilities came out about half as high.
const LP = (() => { const N = 33, h = new Float32Array(N), fc = 0.15; let s = 0;
  for (let i = 0; i < N; i++) { const n = i - (N - 1) / 2, v = n === 0 ? 2 * fc : Math.sin(2 * Math.PI * fc * n) / (Math.PI * n), w = 0.54 - 0.46 * Math.cos(2 * Math.PI * i / (N - 1)); h[i] = v * w; s += h[i]; }
  for (let i = 0; i < N; i++) h[i] /= s; return h; })();
function to16k(x) {
  const n = Math.floor(x.length / 3), y = new Float32Array(n), N = LP.length, M = (N - 1) / 2;
  for (let i = 0; i < n; i++) { const c = i * 3; let a = 0; for (let k = 0; k < N; k++) { const j = c + k - M; if (j >= 0 && j < x.length) a += LP[k] * x[j]; } y[i] = a; }
  return y;
}
async function tagEvents(pcm, sampleRate) {
  await initAst();
  try { return await tagWith(pcm, sampleRate); }
  catch (e) {
    // a GPU that fails mid-inference (device lost under load) is not retried on the GPU
    if (astRung !== 0) throw e;
    console.warn("sound tagger: WebGPU failed, retrying on WASM -", e.message);
    astModel = null; astRung = 1; await initAst(); return await tagWith(pcm, sampleRate);
  }
}
async function tagWith(pcm, sampleRate) {
  const wins = windows(pcm, sampleRate); const best = {};
  const id2label = astModel.config.id2label;
  for (const wv of wins) {
    const inputs = await astProc(to16k(wv), { sampling_rate: 16000 });
    const { logits } = await astModel(inputs);
    const l = logits.data;
    for (let i = 0; i < l.length; i++) {
      const name = id2label[i]; if (!EVENTS.classes.includes(name)) continue;
      const p = 1 / (1 + Math.exp(-l[i]));
      if (p > (best[name] || 0)) best[name] = p;
    }
  }
  const out = {}; for (const [k, v] of Object.entries(best)) if (v >= 0.05) out[k] = Math.round(v * 10000) / 10000;
  return out;
}
// ---- lyrics, for tracks no database has words for -------------------------
// whisper-large-v3-turbo: measured against its own reference lyrics on 10
// songs — 41 % of word-triples, the same as full large-v3 at half the size
// (small managed 22 %). See QUEUE.md.
// THE WORDS NEVER LEAVE THIS MACHINE. They exist inside this worker for as
// long as it takes to hash them, and only the hashes are returned.
const ASR = "onnx-community/whisper-large-v3-turbo";
let asr = null, asrReady = null, asrDevice = "";
async function initAsr() {
  if (asr) return;
  if (!asrReady) asrReady = (async () => {
    const { pipeline } = await import("https://cdn.jsdelivr.net/npm/@huggingface/transformers@3.8.1");
    for (const [device, dtype] of (navigator.gpu ? [["webgpu", "q4"], ["wasm", "q4"]] : [["wasm", "q4"]])) {
      try {
        asr = await pipeline("automatic-speech-recognition", ASR, { device, dtype });
        asrDevice = device; return;
      } catch (e) { console.warn("lyrics model on", device, "failed:", String(e && e.message || e).slice(0, 160)); }
    }
    throw new Error("the lyrics model could not load in this browser");
  })().finally(() => { asrReady = null; });
  await asrReady;
}
async function hearLyrics(pcm48) {
  await initAsr();
  const y = to16k(pcm48);                       // same 33-tap low-pass the tagger uses
  const out = await asr(y, {
    chunk_length_s: 30, stride_length_s: 5, language: "en", task: "transcribe",
    // deterministic: greedy, no random retry. Measured: the default sampling
    // fallback gave 32/37/62 % on three runs of ONE track.
    do_sample: false, num_beams: 1, temperature: 0,
  });
  const words = normWords(out && out.text);
  const g = await grams(words, 3), g2 = await grams(words, 2);
  return { grams: g, bigrams: g2, words: words.length };   // the text itself is dropped here
}

async function initModels() {
  await init();
  proc = await AutoProcessor.from_pretrained(MODEL);
  // fp16, pinned. The server rejects anything else; every vector in the
  // database must come from the same weights or consensus means nothing.
  // WebGPU where the browser has it (Chrome/Edge everywhere, Safari 26+,
  // Firefox on Windows); otherwise, or if the GPU path fails to load, the
  // same weights on WASM — ~3x slower, identical vectors (cosine 1.00000).
  DEVICE = navigator.gpu ? "webgpu" : "wasm";
  try { model = await ClapAudioModelWithProjection.from_pretrained(MODEL, { dtype: "fp16", device: DEVICE }); }
  catch (e) {
    if (DEVICE !== "webgpu") throw e;
    console.warn("WebGPU load failed, falling back to WASM:", e.message);
    DEVICE = "wasm"; model = await ClapAudioModelWithProjection.from_pretrained(MODEL, { dtype: "fp16", device: DEVICE });
  }
}

function toI16(f32) { const o = new Int16Array(f32.length); for (let i = 0; i < f32.length; i++) { const v = Math.max(-1, Math.min(1, f32[i])); o[i] = v < 0 ? v * 32768 : v * 32767; } return o; }

// FIXED windows: one per ~30 s, at most eight, evenly placed. Deterministic,
// so two people embedding the same recording get the same vector — which is
// what lets a second submission confirm a first.
function windows(pcm, sr) {
  const n = pcm.length, w = WIN_S * sr, dur = n / sr;
  const count = Math.max(1, Math.min(MAX_WINDOWS, Math.round(dur / 30)));
  const out = [];
  for (let i = 0; i < count; i++) {
    const center = (i + 0.5) / count * n;
    let start = Math.round(center - w / 2); start = Math.max(0, Math.min(Math.max(0, n - w), start));
    let seg = pcm.subarray(start, start + w);
    if (seg.length < w) { const p = new Float32Array(w); p.set(seg); seg = p; }
    out.push(seg);
  }
  return out;
}
const unit = v => { let s = 0; for (const x of v) s += x * x; s = Math.sqrt(s) || 1; return Array.from(v, x => x / s); };

const held = new Map();   // ref -> { pcm, sampleRate } between fingerprint and embed
self.onmessage = async ({ data }) => {
  const { id } = data;
  try {
    if (data.type === "init") {
      EAR = data.ear || "clap";
      if (EAR === "mulan") { await init(); await initMulan(); self.postMessage({ id, ok: true, device: mulanDevice }); return; }
      if (!model) await initModels();
      self.postMessage({ id, ok: true, device: DEVICE }); return;
    }
    if (data.type === "fingerprint") {
      // Step 1, cheap: Chromaprint of the first ~2 minutes (it resamples
      // internally). The PCM is held here so the page can ask the server
      // whether this recording is already in BEFORE paying for the embed.
      const { pcm, sampleRate } = data;
      const fp = fingerprint(toI16(pcm.subarray(0, Math.min(pcm.length, 120 * sampleRate))), sampleRate, 1);
      held.set(id, { pcm, sampleRate });
      self.postMessage({ id, fingerprint: fp, duration: Math.round(pcm.length / sampleRate), ref: id }); return;
    }
    if (data.type === "drop") { held.delete(data.ref); self.postMessage({ id, ok: true }); return; }
    if (data.type === "events") {
      // sound events for a held recording; keepHeld leaves the PCM for a following embed
      const h = held.get(data.ref); if (!h) throw new Error("no audio held for ref " + data.ref);
      if (!data.keepHeld) held.delete(data.ref);
      const events = await tagEvents(h.pcm, h.sampleRate);
      self.postMessage({ id, events }); return;
    }
    if (data.type === "lyrics") {
      const h = held.get(data.ref); if (!data.keepHeld) held.delete(data.ref);
      if (!h) throw new Error("no audio held for ref " + data.ref);
      self.postMessage({ id, ...(await hearLyrics(h.pcm)), device: asrDevice }); return;
    }
    if (data.type === "embed") {
      const h = held.get(data.ref); held.delete(data.ref);
      if (!h) throw new Error("no audio held for ref " + data.ref);
      const { pcm, sampleRate } = h;
      if (EAR === "mulan") { self.postMessage({ id, ...(await embedMulan(pcm)) }); return; }
      const wins = windows(pcm, sampleRate); const vecs = [];
      for (const wv of wins) {
        const inputs = await proc(wv);
        const { audio_embeds } = await model(inputs);
        vecs.push(Float32Array.from(audio_embeds.data));
      }
      const mean = new Float32Array(512); for (const v of vecs) for (let i = 0; i < 512; i++) mean[i] += v[i] / vecs.length;
      const step = Math.max(1, Math.floor(vecs.length / MOMENTS));
      const moments = vecs.filter((_, i) => i % step === 0).slice(0, MOMENTS).map(unit);
      self.postMessage({ id, mean: unit(mean), moments }); return;
    }
    throw new Error("unknown message " + data.type);
  } catch (e) { self.postMessage({ id, error: e.message || String(e) }); }
};
