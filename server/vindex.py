"""The vector index: exact while it fits, approximate when it doesn't, and it
looks after itself.

  * Up to EXACT_MAX tracks: one float32 matrix in RAM, a query is a matmul,
    every track is compared, nothing to build or tune.
  * Beyond: a faiss IVF-PQ index (64-byte codes, ~100 MB per million tracks)
    finds a few hundred candidates, which are then re-ranked EXACTLY from the
    fp16 vectors on disk. Recall is very-nearly-exact; the slow second pass
    (`exact_scan`) covers the rest.
  * Rebuilds are automatic and event-driven: when the tracks added since the
    last build exceed 10% of the built size (min 20k), a background thread
    retrains and rebuilds at low priority and swaps the new index in; searches
    keep answering from the old one meanwhile. Progress is reported through
    `on_event` (the page shows it). No timers, no cron, nothing to tend.

SQLite stays the source of truth; everything here is derived from it and can
be rebuilt from it. On disk: vectors.f16 (a memmap, row i = ids[i]), ids.npy,
index.faiss + index.json (so a restart does not retrain).
"""
import json, math, os, threading, time
import numpy as np

DIM = 512

class VectorIndex:
    EXACT_MAX = int(os.environ.get("VINDEX_EXACT_MAX", 150_000))
    REBUILD_FRACTION = 0.10
    REBUILD_MIN = int(os.environ.get("VINDEX_REBUILD_MIN", 20_000))
    CANDIDATES = 1000           # IVF candidates re-ranked exactly (reading 1000 fp16 rows is nothing)
    SAMPLE_MEDIAN = 5000        # vectors kept in RAM to estimate the library median in IVF mode

    def __init__(self, data_dir, on_event=None):
        self.dir = data_dir; self.on_event = on_event or (lambda e: None)
        self.lock = threading.RLock()
        self.ids = np.zeros(0, np.int64); self.pos = {}          # track id -> row
        self.n = 0; self.cap = 0; self.M16 = None                  # fp16 memmap, rows [0, cap)
        self.M32 = np.zeros((0, DIM), np.float32)                  # exact mode only
        self.mode = "exact"; self.ix = None; self.built_n = 0; self.added_since_build = 0
        self.sample = None; self._building = False; self.build_state = None
        self.busy = 0                                              # searches in flight (the slow pass yields to them)

    # ---- storage ------------------------------------------------------------
    def _f16_path(self): return os.path.join(self.dir, "vectors.f16")
    def _open(self, cap):
        self.cap = cap; self.M16 = np.memmap(self._f16_path(), np.float16, "r+" if os.path.exists(self._f16_path()) else "w+", shape=(cap, DIM))
    def _grow(self, need):
        if need <= self.cap: return
        newcap = max(need, self.cap * 2, 4096)
        old = self.M16; self.M16.flush() if self.M16 is not None else None
        tmp = self._f16_path() + ".tmp"; nm = np.memmap(tmp, np.float16, "w+", shape=(newcap, DIM))
        if old is not None and self.n: nm[:self.n] = old[:self.n]
        nm.flush(); del nm
        if old is not None: del old
        os.replace(tmp, self._f16_path()); self._open(newcap)

    def load_from_rows(self, rows, count):
        """rows: iterable of (track_id, fp16 bytes), streamed — never held all at once
        (a million rows as Python bytes objects is over a gigabyte, and the container
        has 1.5). count: how many to expect (SELECT COUNT), for the file size."""
        with self.lock:
            for p in (self._f16_path(), self._f16_path() + ".tmp"):
                if os.path.exists(p): os.remove(p)
            self.M16 = None; self.cap = 0; self._grow(max(count, 1))
            ids = np.zeros(count, np.int64); i = 0
            for tid, blob in rows:
                if i >= len(ids): ids = np.append(ids, np.zeros(max(1024, len(ids) // 4), np.int64)); self._grow(len(ids))
                ids[i] = tid; self.M16[i] = np.frombuffer(blob, np.float16); i += 1
            n = i; ids = ids[:n]
            self.M16.flush(); self.ids = ids; self.pos = {int(t): j for j, t in enumerate(ids)}; self.n = n
            np.save(os.path.join(self.dir, "ids.npy"), ids)
            self._choose_mode(startup=True)

    def _choose_mode(self, startup=False):
        if self.n <= self.EXACT_MAX:
            self.mode = "exact"; self.ix = None
            self.M32 = np.asarray(self.M16[:self.n], np.float32) if self.n else np.zeros((0, DIM), np.float32)
            return
        self.M32 = None
        try:
            import faiss
            meta_p = os.path.join(self.dir, "index.json"); ix_p = os.path.join(self.dir, "index.faiss")
            if startup and os.path.exists(ix_p) and os.path.exists(meta_p):
                meta = json.load(open(meta_p)); ix = faiss.read_index(ix_p)
                if meta.get("dim") == DIM and ix.ntotal <= self.n:
                    # rows added after the save go in incrementally; the growth rule decides the next full rebuild
                    if ix.ntotal < self.n:
                        ix.add_with_ids(np.asarray(self.M16[ix.ntotal:self.n], np.float32), np.arange(ix.ntotal, self.n, dtype=np.int64))
                    ix.nprobe = max(32, ix.nlist // 8); self.ix = ix; self.built_n = int(meta.get("built_n", ix.ntotal)); self.added_since_build = self.n - self.built_n
                    self.mode = "ivf"; self._sample(); return
        except Exception as e:
            print("vindex: could not load saved index:", e)
        # nothing usable yet: answer by exact scan of the memmap until the build lands
        self.mode = "scan"; self.ix = None; self._sample(); self._start_build()

    def _sample(self):
        rng = np.random.default_rng(0); k = min(self.SAMPLE_MEDIAN, self.n)
        idx = np.sort(rng.choice(self.n, k, replace=False)) if k else np.zeros(0, np.int64)
        self.sample = np.asarray(self.M16[idx], np.float32) if k else np.zeros((0, DIM), np.float32)

    # ---- writes -------------------------------------------------------------
    def add(self, tid, v):
        v = np.asarray(v, np.float32)
        with self.lock:
            tid = int(tid)
            if tid in self.pos:
                i = self.pos[tid]; self.M16[i] = v.astype(np.float16)
                if self.M32 is not None: self.M32[i] = v
            else:
                self._grow(self.n + 1); i = self.n; self.M16[i] = v.astype(np.float16)
                self.ids = np.append(self.ids, tid); self.pos[tid] = i; self.n += 1
                if self.M32 is not None: self.M32 = np.vstack([self.M32, v[None]])
                if self.ix is not None: self.ix.add_with_ids(v[None], np.array([i], np.int64))
            self.added_since_build += 1
            self._maybe_rebuild()

    def _maybe_rebuild(self):
        if self._building: return
        if self.mode == "exact" and self.n > self.EXACT_MAX: self._start_build(); return
        if self.mode in ("ivf", "scan") and self.added_since_build > max(self.REBUILD_MIN, self.REBUILD_FRACTION * self.built_n): self._start_build()

    def _start_build(self):
        if self._building: return
        self._building = True
        threading.Thread(target=self._build, name="vindex-build", daemon=True).start()

    def _build(self):
        try:
            import faiss
            t0 = time.time(); n = self.n
            faiss.omp_set_num_threads(2)                              # leave CPU for searches and scans
            # lists ~ 2*sqrt(n) and probe an eighth of them: at 1M that is 2000 lists, 250 probed,
            # ~125k code distances per query (10-20 ms on the pi). The first cut (4*sqrt(n) lists,
            # 24 probes) measured recall@10 of 0.17 on clustered data — probing too little of too much.
            nlist = int(max(256, min(2048, 2 * math.sqrt(n))))
            train_n = min(n, max(20_000, 40 * nlist), 120_000)
            rng = np.random.default_rng(1); tri = np.sort(rng.choice(n, train_n, replace=False))
            self._event("running", 0, n, None, "training")
            train = np.asarray(self.M16[tri], np.float32)
            q = faiss.IndexFlatIP(DIM); ix = faiss.IndexIVFPQ(q, DIM, nlist, 64, 8, faiss.METRIC_INNER_PRODUCT); ix.train(train); del train
            t1 = time.time(); step = 20_000
            for s in range(0, n, step):
                e = min(n, s + step); ix.add_with_ids(np.asarray(self.M16[s:e], np.float32), np.arange(s, e, dtype=np.int64))
                rate = e / max(1e-6, time.time() - t1); self._event("running", e, n, (n - e) / max(rate, 1), "adding")
            ix.nprobe = max(32, nlist // 8)
            faiss.write_index(ix, os.path.join(self.dir, "index.faiss.tmp"))
            with self.lock:
                # rows that arrived during the build
                if ix.ntotal < self.n: ix.add_with_ids(np.asarray(self.M16[ix.ntotal:self.n], np.float32), np.arange(ix.ntotal, self.n, dtype=np.int64))
                self.ix = ix; self.mode = "ivf"; self.M32 = None; self.built_n = self.n; self.added_since_build = 0; self._sample()
                os.replace(os.path.join(self.dir, "index.faiss.tmp"), os.path.join(self.dir, "index.faiss"))
                json.dump({"dim": DIM, "built_n": self.built_n, "nlist": nlist, "at": time.time()}, open(os.path.join(self.dir, "index.json"), "w"))
            self._event("done", n, n, 0, "rebuilt in %.0f s" % (time.time() - t0))
        except Exception as e:
            print("vindex: build failed:", e); self._event("failed", 0, self.n, None, str(e)[:120])
        finally:
            self._building = False

    def _event(self, state, done, total, eta, note):
        self.build_state = {"state": state, "done": int(done), "total": int(total), "eta_s": None if eta is None else int(eta), "note": note, "at": time.time()}
        try: self.on_event(self.build_state)
        except Exception: pass

    # ---- reads --------------------------------------------------------------
    def search(self, q, k=50):
        """-> (track ids, scores, library median, exact: bool)"""
        q = np.asarray(q, np.float32)
        with self.lock:
            if self.n == 0: return [], np.zeros(0), 0.0, True
            if self.mode == "exact":
                s = self.M32 @ q; top = np.argsort(-s)[:k]; return self.ids[top].tolist(), s[top], float(np.median(s)), True
            med = float(np.median(self.sample @ q)) if len(self.sample) else 0.0
            if self.mode == "ivf":
                D, I = self.ix.search(q[None], min(self.CANDIDATES, self.n)); cand = I[0][I[0] >= 0]
                rows = np.asarray(self.M16[np.sort(cand)], np.float32); cand = np.sort(cand)
                s = rows @ q; top = np.argsort(-s)[:k]; return self.ids[cand[top]].tolist(), s[top], med, False
        # "scan" mode (no index yet): exact, from the memmap, chunked
        r = self.exact_scan(q, k, yield_to_searches=False)
        return (r[0], r[1], r[2], True) if r else ([], np.zeros(0), 0.0, True)

    def exact_scan(self, q, k=50, yield_to_searches=True, chunk=50_000):
        """Compare against EVERY track from the fp16 file. In IVF mode this is
        the slow second pass: it gives way to normal searches (returns None)."""
        q = np.asarray(q, np.float32); n = self.n
        if n == 0: return [], np.zeros(0), 0.0
        best_s = np.zeros(0, np.float32); best_i = np.zeros(0, np.int64); meds = []
        for s0 in range(0, n, chunk):
            if yield_to_searches and self.busy > 0: return None
            e = min(n, s0 + chunk); sc = np.asarray(self.M16[s0:e], np.float32) @ q
            meds.append(np.median(sc))
            take = np.argsort(-sc)[:k]; best_s = np.concatenate([best_s, sc[take]]); best_i = np.concatenate([best_i, take + s0])
            o = np.argsort(-best_s)[:k]; best_s, best_i = best_s[o], best_i[o]
        return self.ids[best_i].tolist(), best_s, float(np.median(meds))

    def status(self):
        return {"mode": self.mode, "tracks": self.n, "built": self.built_n, "since_build": self.added_since_build, "building": self._building, "build": self.build_state}
