// describesong — worker: fingerprint (Chromaprint, WASM) + embedding (CLAP, transformers.js).
// Receives 48 kHz mono PCM; nothing here touches the network except the model download.
import init, { fingerprint } from "./wasm/fingerprint_wasm.js";
import { AutoProcessor, ClapAudioModelWithProjection, AutoModelForAudioClassification, env } from "https://cdn.jsdelivr.net/npm/@huggingface/transformers@3.8.1";

const MODEL = "Xenova/larger_clap_music_and_speech";
const WIN_S = 10, MAX_WINDOWS = 8, MOMENTS = 4;
let proc, model;

let DEVICE = "";
// The sound-event tagger: an AudioSet classifier (527 classes). Measured on his
// own labels: 88-100 % precision on hand claps and whistling, where CLAP was
// 0-8 %. Loaded on demand the first time a track needs tagging.
const AST = "Xenova/ast-finetuned-audioset-10-10-0.4593";
let astProc = null, astModel = null, EVENTS = null;
async function initAst() {
  if (astModel) return;
  EVENTS = await (await fetch("events.json")).json();
  astProc = await AutoProcessor.from_pretrained(AST);
  try { astModel = await AutoModelForAudioClassification.from_pretrained(AST, { dtype: "fp16", device: DEVICE || "wasm" }); }
  catch (e) { astModel = await AutoModelForAudioClassification.from_pretrained(AST, { dtype: "q8", device: "wasm" }); }
}
// 48 kHz -> 16 kHz: a short low-pass then every third sample. Classification
// is indifferent to the last dB of the top octave.
function to16k(x) {
  const n = Math.floor(x.length / 3), y = new Float32Array(n);
  for (let i = 0; i < n; i++) { const j = i * 3; y[i] = 0.25 * (x[j - 1] || 0) + 0.5 * x[j] + 0.25 * (x[j + 1] || 0); }
  return y;
}
async function tagEvents(pcm, sampleRate) {
  await initAst();
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
    if (data.type === "init") { if (!model) await initModels(); self.postMessage({ id, ok: true, device: DEVICE }); return; }
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
    if (data.type === "embed") {
      const h = held.get(data.ref); held.delete(data.ref);
      if (!h) throw new Error("no audio held for ref " + data.ref);
      const { pcm, sampleRate } = h;
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
