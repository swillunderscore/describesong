"""Scale test for vindex: N clustered vectors (music is clustered, random
Gaussian vectors are unrealistically easy), real text queries when the text
tower is cached, else queries near cluster centres. Reports build time, RSS,
latency and recall@10 of the IVF path against the exact scan.
  python bench_scale.py N [data_dir]      (env VINDEX_EXACT_MAX to force IVF)"""
import os, sys, time, resource, numpy as np
sys.path.insert(0, os.path.dirname(__file__))
from vindex import VectorIndex, DIM
N = int(sys.argv[1]); D = sys.argv[2] if len(sys.argv) > 2 else "/tmp/vindex-bench"; os.makedirs(D, exist_ok=True)
rss = lambda: resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
rng = np.random.default_rng(0)
# REAL structure: seed vectors are real CLAP track embeddings; the collection is
# built by perturbing them slightly (a member of a cluster sits at cosine ~0.9
# to its seed, like remixes/versions/similar tracks do). The first version used
# heavy Gaussian noise, which made every vector nearly random on the sphere —
# no structure to find, recall 0.3, and nothing like music.
seeds = np.load(os.environ.get("SEEDS", os.path.expanduser("~/describesong/mulan-trial/out/CLAP.npz")), allow_pickle=True)["vectors"].astype(np.float32)
seeds /= np.linalg.norm(seeds, axis=1, keepdims=True); K = len(seeds); print(f"seeds: {K} real vectors")
def batch(s, e):
    c = rng.integers(0, K, e - s); x = seeds[c] + 0.10 * rng.standard_normal((e - s, DIM), dtype=np.float32) / np.sqrt(DIM) * 8; return x / np.linalg.norm(x, axis=1, keepdims=True)
# queries: real text embeddings when the text tower is cached, else perturbed seeds
def text_queries():
    try:
        import onnxruntime as ort
        from huggingface_hub import hf_hub_download
        from transformers import AutoTokenizer
        repo = "Xenova/larger_clap_music_and_speech"; tok = AutoTokenizer.from_pretrained(repo)
        sess = ort.InferenceSession(hf_hub_download(repo, "onnx/text_model_fp16.onnx"), providers=["CPUExecutionProvider"])
        QS = ["aggressive dubstep with huge wobbling bass drops and screeching synths", "big room electro house build up with a triumphant soaring synth lead", "solo nylon string guitar, brazilian, intricate fingerpicking, melancholy", "dreamy lo-fi hip hop beat, warm pads, dusty drums", "dense conscious rap, urgent male vocals, jazzy live instrumentation", "laid back nineties rap, jazzy sample, smooth bassline", "jazz sampled hip hop with a latin piano groove and boom bap drums", "moody alternative r&b, soft male vocals, sparse electric piano", "hazy lo-fi pop with falsetto vocals, woozy detuned synths", "psychedelic surf funk trio, reverb guitar, no vocals", "acoustic jazz guitar duo playing a bossa nova standard", "super heavy super bassy hard dubstep", "hard electro house with a massive bass drop and a chanted vocal hook", "eighties synth pop with a gated snare and a saxophone solo", "fast punk rock, shouted gang vocals", "ambient piano with long reverb tails", "reggaeton beat with an autotuned hook", "trap song with a flute melody and a whispered chorus", "drum and bass with a soulful female vocal", "gay", "song", "banger"]
        out = []
        for q in QS:
            ids = tok([q], return_tensors="np", padding=True)["input_ids"]; o = sess.run(None, {"input_ids": ids})
            v = next(x for x in o if x.ndim == 2 and x.shape[-1] == DIM)[0].astype(np.float32); out.append(v / np.linalg.norm(v))
        print(f"queries: {len(out)} real text embeddings"); return np.stack(out)
    except Exception as e:
        print("queries: text tower unavailable (%s) — perturbed seeds" % str(e)[:60]); q = seeds[rng.integers(0, K, 40)] + 0.3 * rng.standard_normal((40, DIM), dtype=np.float32) / np.sqrt(DIM) * 8; return q / np.linalg.norm(q, axis=1, keepdims=True)
events = []
ix = VectorIndex(D, on_event=lambda ev: (events.append(ev), print("  event:", ev["state"], ev["done"], "/", ev["total"], ev["note"], "eta", ev["eta_s"]) if ev["state"] != "running" or ev["done"] % 100000 == 0 else None))
t = time.time()
def gen():
    for s in range(0, N, 50000):
        x = batch(s, min(N, s + 50000)).astype(np.float16)
        for i in range(len(x)): yield s + i, x[i].tobytes()
ix.load_from_rows(gen(), N)
print(f"loaded {N} in {time.time()-t:.1f}s mode={ix.mode} rss={rss():.0f} MB")
while ix._building: time.sleep(1)
print(f"after build: mode={ix.mode} rss={rss():.0f} MB events={len(events)} last={events[-1]['note'] if events else None}")
# queries: near-centre (what a matching description looks like) + a few far ones
qs = text_queries()
lat = []; rec = []; lat_exact = []
for q in qs:
    t = time.time(); ids, sc, med, ex = ix.search(q, 10); lat.append(time.time() - t)
    t = time.time(); tru = ix.exact_scan(q, 10, yield_to_searches=False); lat_exact.append(time.time() - t)
    rec.append(len(set(ids) & set(tru[0])) / 10)
print(f"search: mode={ix.mode} exact={ex} median {np.median(lat)*1000:.1f} ms, p95 {np.percentile(lat,95)*1000:.1f} ms | exact scan median {np.median(lat_exact):.2f} s | recall@10 vs exact: {np.mean(rec):.3f} (min {min(rec):.1f})")
# growth: add 12% more and confirm an automatic rebuild fires
added = int(max(ix.REBUILD_MIN, 0.12 * ix.built_n)) + 1 if ix.mode == "ivf" else 0
if added:
    x = batch(N, N + added); t = time.time()
    for i in range(added): ix.add(N + i, x[i])
    while ix._building: time.sleep(1)
    print(f"added {added}: rebuild fired={any(e['state']=='done' and e['at']>t for e in events)} in {time.time()-t:.0f}s, built_n={ix.built_n}, rss={rss():.0f} MB")
