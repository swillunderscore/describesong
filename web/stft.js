// The step ONNX Runtime Web has no kernel for, done here instead. Parameters
// are read off the model's own initialisers, not guessed: n_fft 2048, hop 240,
// periodic Hann, reflect-padded 1024 either side. Output [1, frames, 1025, 2].
export const N_FFT = 2048, HOP = 240, BINS = N_FFT / 2 + 1;
const WIN = new Float32Array(N_FFT);
for (let i = 0; i < N_FFT; i++) WIN[i] = 0.5 * (1 - Math.cos(2 * Math.PI * i / N_FFT));
// in-place iterative radix-2 FFT
const LOG = Math.log2(N_FFT), REV = new Uint16Array(N_FFT);
for (let i = 0; i < N_FFT; i++) { let r = 0; for (let b = 0; b < LOG; b++) r |= ((i >> b) & 1) << (LOG - 1 - b); REV[i] = r; }
const COS = new Float32Array(N_FFT / 2), SIN = new Float32Array(N_FFT / 2);
for (let i = 0; i < N_FFT / 2; i++) { COS[i] = Math.cos(-2 * Math.PI * i / N_FFT); SIN[i] = Math.sin(-2 * Math.PI * i / N_FFT); }
function fft(re, im) {
  for (let i = 0; i < N_FFT; i++) if (REV[i] > i) { let t = re[i]; re[i] = re[REV[i]]; re[REV[i]] = t; t = im[i]; im[i] = im[REV[i]]; im[REV[i]] = t; }
  for (let len = 2; len <= N_FFT; len <<= 1) {
    const half = len >> 1, step = N_FFT / len;
    for (let i = 0; i < N_FFT; i += len) for (let j = 0; j < half; j++) {
      const k = j * step, c = COS[k], s = SIN[k], a = i + j, b = a + half;
      const xr = re[b] * c - im[b] * s, xi = re[b] * s + im[b] * c;
      re[b] = re[a] - xr; im[b] = im[a] - xi; re[a] += xr; im[a] += xi;
    }
  }
}
export function stft(y) {
  const P = N_FFT / 2, n = y.length + 2 * P;
  const p = new Float32Array(n);                       // reflect pad
  for (let i = 0; i < n; i++) { let j = i - P; if (j < 0) j = -j; if (j >= y.length) j = 2 * (y.length - 1) - j; p[i] = y[j]; }
  const frames = 1 + Math.floor((n - N_FFT) / HOP);
  const out = new Float32Array(frames * BINS * 2);
  const re = new Float32Array(N_FFT), im = new Float32Array(N_FFT);
  for (let f = 0; f < frames; f++) {
    const o = f * HOP;
    for (let i = 0; i < N_FFT; i++) { re[i] = p[o + i] * WIN[i]; im[i] = 0; }
    fft(re, im);
    const b = f * BINS * 2;
    for (let k = 0; k < BINS; k++) { out[b + k * 2] = re[k]; out[b + k * 2 + 1] = im[k]; }
  }
  return { data: out, dims: [1, frames, BINS, 2] };
}
