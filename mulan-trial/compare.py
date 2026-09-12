#!/usr/bin/env python3
"""CLAP vs MuQ-MuLan on the same library, the same DETERMINISTIC windows, the
same blind queries. Rank of the intended track decides. Both models get
exactly the same audio: three 10 s windows at 20/50/80 % of each track,
embedded separately, averaged, unit-normalised — the protocol the site will
use, so the number measured is the number that ships."""
import os, sys, glob, json, time, numpy as np, torch, librosa
from concurrent.futures import ProcessPoolExecutor

ROOT = os.path.expanduser("~/vibefind/mulan-trial")
LIB  = os.path.join(ROOT, "library")
OUT  = os.path.join(ROOT, "out"); os.makedirs(OUT, exist_ok=True)
WIN_S = 10.0; FRACS = (0.20, 0.50, 0.80)
dev = "cuda" if torch.cuda.is_available() else "cpu"

def windows(path):
    """PCM windows at both rates. Decode once at 48 k, derive 24 k from it."""
    try:
        y, _ = librosa.load(path, sr=48000, mono=True)
    except Exception:
        return None
    n = len(y); w = int(WIN_S * 48000)
    if n < w: y = np.pad(y, (0, w - n)); n = w
    outs48 = []
    for f in FRACS:
        start = int(max(0, min(n - w, f * n - w / 2)))
        outs48.append(y[start:start + w].astype(np.float32))
    outs24 = [librosa.resample(x, orig_sr=48000, target_sr=24000) for x in outs48]
    return outs48, outs24

def chunks(files, n=24):
    """Decode a few files at a time and hand them straight to the models.

    The first version decoded the whole library up front — 2,286 tracks x 3
    windows at two sample rates is ~20 GB of float32 — and filled RAM and swap.
    Nothing here needs more than one chunk in memory at once.
    """
    with ProcessPoolExecutor(max_workers=4) as ex:
        for i in range(0, len(files), n):
            batch = files[i:i+n]
            out = [(p, r) for p, r in zip(batch, ex.map(windows, batch)) if r is not None]
            if out:
                yield ([p for p, _ in out],
                       np.stack([r[0] for _, r in out]), np.stack([r[1] for _, r in out]))

def load_clap():
    # The *WithProjection classes return the 512-d joint-space vectors by name
    # (.audio_embeds / .text_embeds). ClapModel.get_audio_features changed its
    # return type between transformers versions; this API did not.
    from transformers import ClapAudioModelWithProjection, ClapTextModelWithProjection, ClapProcessor
    M = "laion/larger_clap_music_and_speech"
    am = ClapAudioModelWithProjection.from_pretrained(M).to(dev).eval()
    tm = ClapTextModelWithProjection.from_pretrained(M).to(dev).eval()
    proc = ClapProcessor.from_pretrained(M)
    def audio(w48):
        out = []
        for i in range(0, len(w48), 8):
            batch = w48[i:i+8]; flat = [x for tr in batch for x in tr]
            try:
                inp = proc(audio=flat, sampling_rate=48000, return_tensors="pt")
            except (TypeError, ValueError):
                inp = proc(audios=flat, sampling_rate=48000, return_tensors="pt")
            with torch.no_grad():
                e = am(**{k: v.to(dev) for k, v in inp.items()}).audio_embeds.float().cpu().numpy()
            e = e.reshape(len(batch), 3, -1).mean(axis=1)
            out.append(e / (np.linalg.norm(e, axis=1, keepdims=True) + 1e-9))
        return np.concatenate(out)
    def text(qs):
        inp = proc(text=qs, return_tensors="pt", padding=True)
        with torch.no_grad():
            t = tm(**{k: v.to(dev) for k, v in inp.items()}).text_embeds.float().cpu().numpy()
        return t / (np.linalg.norm(t, axis=1, keepdims=True) + 1e-9)
    return audio, text

def load_mulan():
    from muq import MuQMuLan
    mulan = MuQMuLan.from_pretrained("OpenMuQ/MuQ-MuLan-large").to(dev).eval()
    def audio(w24):
        out = []
        for i in range(0, len(w24), 8):
            batch = w24[i:i+8]
            flat = torch.tensor(np.stack([x for tr in batch for x in tr])).to(dev)
            with torch.no_grad():
                e = mulan(wavs=flat).float().cpu().numpy()
            e = e.reshape(len(batch), 3, -1).mean(axis=1)
            out.append(e / (np.linalg.norm(e, axis=1, keepdims=True) + 1e-9))
        return np.concatenate(out)
    def text(qs):
        with torch.no_grad():
            t = mulan(texts=qs).float().cpu().numpy()
        return t / (np.linalg.norm(t, axis=1, keepdims=True) + 1e-9)
    return audio, text

TESTS = [
 ("SAN DIEGO VIP", "aggressive dubstep with huge wobbling bass drops and screeching synths"),
 ("Illmerica",     "big room electro house build up with a triumphant soaring synth lead"),
 ("Consola",       "solo nylon string guitar, brazilian, intricate fingerpicking, melancholy"),
 ("Reality Testing/09 - Jaded", "dreamy lo-fi hip hop beat, warm pads, dusty drums"),
 ("Kendrick",      "dense conscious rap, urgent male vocals, jazzy live instrumentation, west coast"),
 ("Runnin",        "laid back nineties rap, jazzy sample, smooth bassline, relaxed male rapper"),
 ("Song For My Father", "jazz sampled hip hop with a latin piano groove and boom bap drums"),
 ("Frank Ocean",   "moody alternative r&b, soft male vocals, sparse electric piano, late night"),
 ("BTSTU",         "hazy lo-fi pop with falsetto vocals, woozy detuned synths and tape crackle"),
 ("Khruangbin",    "psychedelic surf funk trio, reverb guitar, no vocals, thai influenced groove"),
 ("Blue Bossa",    "acoustic jazz guitar duo playing a bossa nova standard, mellow"),
 ("Destructo/Higher", "super heavy super bassy hard dubstep from the early 2010s"),
 ("Destructo/Higher", "hard electro house with a massive bass drop and a chanted vocal hook"),
 ("Destructo/Higher", "that huge electro banger from around 2012 that everyone played, big drop, party"),
]

def evaluate(name, V, text, paths):
    rows = []
    for key, q in TESTS:
        tv = text([q])[0]; s = V @ tv; order = np.argsort(-s)
        idx = [i for i, p in enumerate(paths) if key.lower() in p.lower()]
        rank = min(int(np.where(order == i)[0][0]) + 1 for i in idx) if idx else None
        rows.append((key, rank))
    return rows

if __name__ == "__main__":
    files = sorted(glob.glob(os.path.join(LIB, "**", "*.mp3"), recursive=True))
    print("files:", len(files), "| device:", dev, flush=True)
    clap_a, clap_t = load_clap(); mulan_a, mulan_t = load_mulan()
    paths, VC, VM = [], [], []; t0 = time.time(); tc = tm = 0.0
    for ps, w48, w24 in chunks(files):
        t = time.time(); VC.append(clap_a(w48)); tc += time.time() - t
        t = time.time(); VM.append(mulan_a(w24)); tm += time.time() - t
        paths += ps
        if len(paths) % 240 < 24:
            print("  %d/%d  clap %.2f tr/s  mulan %.2f tr/s" % (len(paths), len(files), len(paths)/max(tc,1e-6), len(paths)/max(tm,1e-6)), flush=True)
    VC = np.concatenate(VC); VM = np.concatenate(VM)
    np.savez(os.path.join(OUT, "CLAP.npz"), vectors=VC, paths=np.array(paths))
    np.savez(os.path.join(OUT, "MuQ-MuLan.npz"), vectors=VM, paths=np.array(paths))
    results = {"CLAP": evaluate("CLAP", VC, clap_t, paths), "MuQ-MuLan": evaluate("MuQ-MuLan", VM, mulan_t, paths)}
    print("\n%-42s %8s %10s" % ("target / query", "CLAP", "MuQ-MuLan"))
    for (k, q), (_, rc), (_, rm) in zip(TESTS, results["CLAP"], results["MuQ-MuLan"]):
        print("%-42s %8s %10s   %s" % (k[:24], rc, rm, q[:40]))
    n = len(paths)
    for name in results:
        rs = [r for _, r in results[name] if r]
        print("%s: median rank %d, in top-10: %d/%d, in top-50: %d/%d (of %d tracks)" % (
            name, int(np.median(rs)), sum(r <= 10 for r in rs), len(rs), sum(r <= 50 for r in rs), len(rs), n))
    print("embed time: clap %.0fs  mulan %.0fs" % (tc, tm))
