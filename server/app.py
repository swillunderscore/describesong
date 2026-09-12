"""describesong server — identities, vectors, search. Never audio.

Three endpoints and a static site. Runs on the pi in an arm64 container behind
Cloudflare Tunnel. The heavy work (decoding, fingerprinting, embedding) happens
in the submitter's browser; this side stores 2 KB per track and answers a
sentence with a dot product.
"""
import hashlib, json, os, re, sqlite3, threading, time, unicodedata
import numpy as np
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

DATA = os.environ.get("VIBEFIND_DATA", "./data"); os.makedirs(DATA, exist_ok=True)
DB = os.path.join(DATA, "describesong.sqlite")
# ONE model, forever. A vector from anything else is rejected at the door.
MODEL_ID = "Xenova/larger_clap_music_and_speech@fp16"
DIM = 512
ACOUSTID_KEY = os.environ.get("ACOUSTID_KEY", "")        # decision 5: his to register
UA = "describesong/0.1 (+https://github.com/)"                # name/domain pending

app = FastAPI(title="describesong", docs_url=None, redoc_url=None)

# Static files must REVALIDATE on every load: after a deploy, a browser that
# heuristically cached app.js next to a fresh index.html runs the old client
# against the new server (it happened: a test tab ran a water.js without the
# functions the page expected). no-cache still allows the ETag 304 round trip,
# so it costs one small request per file, not a re-download.
@app.middleware("http")
async def _revalidate_static(request, call_next):
    # Behind the tunnel the server only ever sees plain HTTP; Cloudflare says
    # what the VISITOR used in CF-Visitor. Plain http:// gets sent to https://,
    # and HTTPS answers carry HSTS so the browser stops trying http at all.
    # Nothing legitimate posts more than ~60 KB (one vector + four moments as
    # JSON + a fingerprint). A body limit stops a 100 MB JSON from being parsed
    # into the container's 1.5 GB and knocking the service over.
    if request.method == "POST" and int(request.headers.get("content-length") or 0) > 512 * 1024:
        from fastapi.responses import JSONResponse
        return JSONResponse({"detail": "request too large"}, status_code=413)
    cfv = request.headers.get("cf-visitor", "")
    if '"http"' in cfv:
        from fastapi.responses import RedirectResponse
        return RedirectResponse("https://" + request.headers.get("host", "describesong.com") + str(request.url.path) + ("?" + request.url.query if request.url.query else ""), status_code=301)
    resp = await call_next(request)
    if not request.url.path.startswith("/api/"): resp.headers["Cache-Control"] = "no-cache"
    if cfv: resp.headers["Strict-Transport-Security"] = "max-age=31536000"
    return resp

# ---- storage ---------------------------------------------------------------

def db():
    c = sqlite3.connect(DB, check_same_thread=False); c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL"); return c

SCHEMA = """
CREATE TABLE IF NOT EXISTS tracks(
  id INTEGER PRIMARY KEY,
  fp_hash TEXT UNIQUE NOT NULL,        -- sha1 of the chromaprint: the identity when AcoustID has none
  mbid TEXT,                           -- MusicBrainz recording id when AcoustID matched
  duration INTEGER,
  artist TEXT, title TEXT, album TEXT, -- best current label (verified from MB, or consensus)
  verified INTEGER NOT NULL DEFAULT 0, -- 1 = from MusicBrainz, 0 = from submitter tags
  submissions INTEGER NOT NULL DEFAULT 0,
  created REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS tracks_mbid ON tracks(mbid);
CREATE TABLE IF NOT EXISTS labels(     -- every label ever offered for an unverified track
  track_id INTEGER NOT NULL, norm TEXT NOT NULL, artist TEXT, title TEXT, album TEXT,
  votes INTEGER NOT NULL DEFAULT 1, PRIMARY KEY(track_id, norm)
);
CREATE TABLE IF NOT EXISTS vectors(    -- mean vector + up to 4 moments, all unit norm, float16 on disk
  track_id INTEGER NOT NULL, kind TEXT NOT NULL, pos INTEGER NOT NULL, vec BLOB NOT NULL,
  PRIMARY KEY(track_id, kind, pos)
);
CREATE TABLE IF NOT EXISTS ratelimit(ip TEXT PRIMARY KEY, window REAL, n INTEGER);
"""
with db() as c: c.executescript(SCHEMA)

def norm_label(*parts):
    """Case, punctuation, diacritics and 'feat.' noise removed — so two people
    typing the same song differently count as agreeing."""
    s = " ".join(p or "" for p in parts).lower()
    s = unicodedata.normalize("NFKD", s); s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = re.sub(r"\((feat|ft|featuring)[^)]*\)|\[[^\]]*\]|\b(official|video|audio|remaster(ed)?|lyrics)\b", " ", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return " ".join(s.split())

# ---- the index: brute force, on purpose ------------------------------------
#
# 512 floats x N tracks as one matrix; a query is a single matmul. At 100k
# tracks that is ~50 ms on the pi, at 1M ~0.5 s — and it is exact, has no
# build step, no C++ dependency to compile on arm, and nothing to tune. hnswlib
# is the upgrade when the matmul is the slowest thing, and not before.
class Index:
    def __init__(self): self.lock = threading.Lock(); self.ids = np.zeros(0, np.int64); self.M = np.zeros((0, DIM), np.float32); self.load()
    def load(self):
        with db() as c:
            rows = c.execute("SELECT track_id, vec FROM vectors WHERE kind='mean'").fetchall()
        ids = np.array([r["track_id"] for r in rows], np.int64)
        M = np.stack([np.frombuffer(r["vec"], np.float16).astype(np.float32) for r in rows]) if rows else np.zeros((0, DIM), np.float32)
        with self.lock: self.ids, self.M = ids, M
    def add(self, tid, v):
        with self.lock:
            if tid in self.ids: self.M[np.where(self.ids == tid)[0][0]] = v
            else: self.ids = np.append(self.ids, tid); self.M = np.vstack([self.M, v[None]])
    def search(self, q, k=50):
        with self.lock:
            if len(self.ids) == 0: return [], np.zeros(0), 0.0
            s = self.M @ q; top = np.argsort(-s)[:k]; return self.ids[top].tolist(), s[top], float(np.median(s))
INDEX = Index()

# ---- text tower (the only model on the server) -----------------------------
_text = {}
def text_embed(q: str) -> np.ndarray:
    if not _text:
        import onnxruntime as ort
        from huggingface_hub import hf_hub_download
        from transformers import AutoTokenizer
        repo = "Xenova/larger_clap_music_and_speech"
        _text["tok"] = AutoTokenizer.from_pretrained(repo)
        _text["sess"] = ort.InferenceSession(hf_hub_download(repo, "onnx/text_model_fp16.onnx"), providers=["CPUExecutionProvider"])
    ids = _text["tok"]([q], return_tensors="np", padding=True)["input_ids"]
    out = _text["sess"].run(None, {"input_ids": ids})
    v = next(o for o in out if o.ndim == 2 and o.shape[-1] == DIM)[0].astype(np.float32)
    return v / (np.linalg.norm(v) + 1e-9)

# ---- rate limiting: the whole anti-junk story is "not very fast" -----------
def client_ip(request: Request) -> str:
    # Behind the Cloudflare tunnel every request arrives from the tunnel's own
    # address, so request.client.host is the same for the whole internet and a
    # per-IP limit silently becomes a global one. Cloudflare puts the real
    # address in CF-Connecting-IP. The service is bound to 127.0.0.1 and only
    # reachable through the tunnel, so the header cannot be spoofed from outside.
    return request.headers.get("cf-connecting-ip") or (request.client.host if request.client else "?")

def ratelimit(ip: str, per_hour: int):
    now = time.time()
    with db() as c:
        # Windows older than a day are dead: drop them, so an address is held
        # only while its counter matters (legal.html promises exactly this).
        c.execute("DELETE FROM ratelimit WHERE window < ?", (now - 86400,))
        r = c.execute("SELECT window, n FROM ratelimit WHERE ip=?", (ip,)).fetchone()
        if r and now - r["window"] < 3600:
            if r["n"] >= per_hour: raise HTTPException(429, "slow down")
            c.execute("UPDATE ratelimit SET n=n+1 WHERE ip=?", (ip,))
        else:
            c.execute("INSERT OR REPLACE INTO ratelimit(ip, window, n) VALUES(?,?,1)", (ip, now))

# ---- /identify : fingerprint -> MusicBrainz id -> artist/title/album --------
class IdentifyIn(BaseModel):
    fingerprint: str = Field(min_length=16, max_length=20000)
    duration: int = Field(ge=1, le=36000)

# AcoustID allows 3 lookups/second per application key, for ALL users of this
# site together. Five people scanning at once (~0.7/s each) would blow through
# it, AcoustID would answer 429, and every one of their tracks would silently
# land as "unverified" with file tags. So lookups queue through a token bucket
# and wait their turn (a few hundred ms per user in that case) instead.
_AID_LOCK = threading.Lock(); _AID_TIMES: list[float] = []
def acoustid_slot(max_wait: float = 6.0) -> bool:
    deadline = time.time() + max_wait
    while True:
        with _AID_LOCK:
            now = time.time(); _AID_TIMES[:] = [t for t in _AID_TIMES if now - t < 1.0]
            if len(_AID_TIMES) < 3: _AID_TIMES.append(now); return True
            wait = 1.0 - (now - _AID_TIMES[0])
        if time.time() + wait > deadline: return False     # too busy: fall back to file tags (unverified)
        time.sleep(max(0.01, wait))

@app.post("/api/identify")
def identify(body: IdentifyIn, request: Request):
    ratelimit(client_ip(request), 6000)    # one per track: a full-speed scan is ~2400/h from one address; the 600 here broke every scan past 600 tracks
    fp_hash = hashlib.sha1(body.fingerprint.encode()).hexdigest()
    with db() as c:
        known = c.execute("SELECT id, mbid, artist, title, album, verified, submissions FROM tracks WHERE fp_hash=?", (fp_hash,)).fetchone()
    if known and known["mbid"]:
        # Already in, and verified: nothing a re-submission of the same encode
        # could add. The client skips the embed (resume from any browser).
        return {"fp_hash": fp_hash, "mbid": known["mbid"], "artist": known["artist"], "title": known["title"], "album": known["album"],
                "verified": 1, "prior": None, "known": True, "submissions": known["submissions"]}
    mbid = meta = None
    if ACOUSTID_KEY and acoustid_slot():
        import urllib.parse, urllib.request
        u = ("https://api.acoustid.org/v2/lookup?client=%s&meta=recordings+releasegroups&duration=%d&fingerprint=%s"
             % (ACOUSTID_KEY, body.duration, urllib.parse.quote(body.fingerprint)))
        try:
            d = json.load(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": UA}), timeout=8))
            best = max((r for r in d.get("results", []) if r.get("recordings")), key=lambda r: r.get("score", 0), default=None)
            if best and best.get("score", 0) >= 0.5:
                rec = best["recordings"][0]; mbid = rec.get("id")
                meta = {"title": rec.get("title"), "artist": ", ".join(a.get("name", "") for a in rec.get("artists", []) or []),
                        "album": (rec.get("releasegroups") or [{}])[0].get("title")}
        except Exception:
            pass
    # Nothing verified: hand back whatever a previous submitter said, so the
    # client can ask "someone labelled this X — correct?" (decision 6).
    prior = None
    if known and not known["mbid"]:
        prior = {"artist": known["artist"], "title": known["title"], "album": known["album"], "submissions": known["submissions"]}
    return {"fp_hash": fp_hash, "mbid": mbid, "verified": 1 if mbid else 0, "prior": prior,
            "known": bool(known), "submissions": known["submissions"] if known else 0, **(meta or {})}

# ---- /submit : identity + vectors, nothing else ----------------------------
class SubmitIn(BaseModel):
    model: str
    fp_hash: str = Field(min_length=40, max_length=40)
    mbid: str | None = None
    duration: int = Field(ge=1, le=36000)
    artist: str | None = Field(default=None, max_length=300)
    title: str | None = Field(default=None, max_length=300)
    album: str | None = Field(default=None, max_length=300)
    mean: list[float] | None = None          # None = label vote only; the recording must already be in
    moments: list[list[float]] = Field(default_factory=list, max_length=4)

def unit(v):
    a = np.asarray(v, np.float32)
    if a.shape != (DIM,) or not np.all(np.isfinite(a)): raise HTTPException(400, "bad vector")
    n = np.linalg.norm(a)
    if not (0.9 < n < 1.1): raise HTTPException(400, "vector not unit norm")
    return a / n

@app.post("/api/submit")
def submit(body: SubmitIn, request: Request):
    ratelimit(client_ip(request), 6000)
    if body.model != MODEL_ID: raise HTTPException(400, "unsupported model; this database is %s" % MODEL_ID)
    vote_only = body.mean is None; new_track = False
    mean = None if vote_only else unit(body.mean); moments = [] if vote_only else [unit(m) for m in body.moments]
    now = time.time()
    with db() as c:
        row = c.execute("SELECT id, mbid, verified FROM tracks WHERE fp_hash=?", (body.fp_hash,)).fetchone()
        if vote_only and row is None: raise HTTPException(400, "label vote for a recording that is not in the database")
        if row is None:
            c.execute("INSERT INTO tracks(fp_hash, mbid, duration, artist, title, album, verified, submissions, created) VALUES(?,?,?,?,?,?,?,1,?)",
                      (body.fp_hash, body.mbid, body.duration, body.artist, body.title, body.album, 1 if body.mbid else 0, now))
            tid = c.execute("SELECT id FROM tracks WHERE fp_hash=?", (body.fp_hash,)).fetchone()["id"]
            new_track = True
        else:
            tid = row["id"]; c.execute("UPDATE tracks SET submissions=submissions+1 WHERE id=?", (tid,))
            if body.mbid and not row["mbid"]:
                c.execute("UPDATE tracks SET mbid=?, artist=?, title=?, album=?, verified=1 WHERE id=?", (body.mbid, body.artist, body.title, body.album, tid))
        if not body.mbid and (body.artist or body.title):
            # Consensus on tags: every offered label is a vote; the leader is shown.
            n = norm_label(body.artist, body.title)
            c.execute("INSERT INTO labels(track_id, norm, artist, title, album) VALUES(?,?,?,?,?) ON CONFLICT(track_id, norm) DO UPDATE SET votes=votes+1", (tid, n, body.artist, body.title, body.album))
            # Ties go to the EARLIER label. The smoke test showed why: one wrong
            # relabel of a single-submission track is a 1-1 tie, and "ORDER BY
            # votes" alone let the newcomer win at random. A label only takes
            # over when it has strictly more agreement than the one showing.
            lead = c.execute("SELECT artist, title, album, votes FROM labels WHERE track_id=? ORDER BY votes DESC, rowid ASC LIMIT 1", (tid,)).fetchone()
            cur = c.execute("SELECT artist, title FROM tracks WHERE id=?", (tid,)).fetchone()
            curv = c.execute("SELECT votes FROM labels WHERE track_id=? AND norm=?", (tid, norm_label(cur["artist"], cur["title"]))).fetchone()
            if curv is None or lead["votes"] > curv["votes"] or norm_label(lead["artist"], lead["title"]) == norm_label(cur["artist"], cur["title"]):
                c.execute("UPDATE tracks SET artist=?, title=?, album=? WHERE id=? AND verified=0", (lead["artist"], lead["title"], lead["album"], tid))
        # Vectors: a resubmission averages in (2 KB each; float16 on disk).
        if vote_only: return {"ok": True, "track_id": tid, "vote": True}
        old = c.execute("SELECT vec FROM vectors WHERE track_id=? AND kind='mean'", (tid,)).fetchone()
        if old:
            prev = np.frombuffer(old["vec"], np.float16).astype(np.float32); mean = prev + mean; mean /= np.linalg.norm(mean) + 1e-9
        c.execute("INSERT OR REPLACE INTO vectors VALUES(?,?,?,?)", (tid, "mean", 0, mean.astype(np.float16).tobytes()))
        for i, m in enumerate(moments):
            c.execute("INSERT OR REPLACE INTO vectors VALUES(?,?,?,?)", (tid, "moment", i, m.astype(np.float16).tobytes()))
    INDEX.add(tid, mean)
    if new_track: publish_stats()
    return {"ok": True, "track_id": tid}

GAP_REF = 0.55        # top-minus-median gap of a specific query (measured 0.39–0.65)
BROAD_GAP = 0.30      # below this the query fits the library about equally (obtuse words: 0.21–0.26)
MIN_FOR_STATS = 20    # fewer tracks than this and the median is meaningless (1 track: top == median)
CAL_FLOOR = 0.15      # median cosine of unrelated tracks for a specific query, used while small

# ---- /search : a sentence in, songs out ------------------------------------
@app.get("/api/search")
def search(q: str, request: Request, k: int = 30):
    ratelimit(client_ip(request), 3000)
    q = q.strip()[:500]        # the text tower reads ~77 tokens anyway; no reason to tokenise a novel
    if not q: raise HTTPException(400, "empty query")
    qv = text_embed(q)
    ids, scores, med_all = INDEX.search(qv, k=max(1, min(k, 100)))
    n = int(len(INDEX.ids))
    if not ids: return {"results": [], "broad": False, "small": True, "count": n}
    with db() as c:
        rows = {r["id"]: r for r in c.execute("SELECT * FROM tracks WHERE id IN (%s)" % ",".join("?" * len(ids)), ids)}
    # CONFIDENCE (decision 9, calibrated 2026-09-11 on 2286 tracks — see QUEUE.md).
    # The raw cosine says nothing: "gay" scores 0.61, above most true hits. What
    # separates a description from an obtuse word is how far the leader stands
    # above the WHOLE library's median: specific queries 0.39–0.65, obtuse words
    # 0.21–0.26. So confidence = (score - median) / GAP_REF, per row — the leader
    # of a vague query lands near 45%, of a specific one at 100%. Under
    # MIN_FOR_STATS tracks the live median is the query's own results, so a fixed
    # floor stands in and the client says the numbers are rough.
    small = n < MIN_FOR_STATS
    med = CAL_FLOOR if small else med_all
    top = float(scores[0]); gap = top - med
    broad = (not small) and gap < BROAD_GAP
    res = []
    for tid, s in zip(ids, scores):
        r = rows.get(tid)
        if not r: continue
        res.append({"artist": r["artist"], "title": r["title"], "album": r["album"], "mbid": r["mbid"],
                    "verified": bool(r["verified"]), "duration": r["duration"], "score": round(float(s), 4),
                    "confidence": int(round(100 * max(0.0, min(1.0, (float(s) - med) / GAP_REF))))})
    return {"results": res, "broad": broad, "small": small, "count": n, "gap": round(gap, 3)}

def stats_dict():
    with db() as c:
        t = c.execute("SELECT COUNT(*) n, SUM(verified) v, SUM(created > ?) w FROM tracks", (time.time() - 7 * 86400,)).fetchone()
    return {"tracks": t["n"], "verified": t["v"] or 0, "week": t["w"] or 0, "model": MODEL_ID, "acoustid": bool(ACOUSTID_KEY)}

@app.get("/api/stats")
def stats(): return stats_dict()

# LIVE COUNTS. One open connection per tab, and a message only when a track is
# added — nothing polls. A comment line every 25 s keeps the tunnel's idle
# timeout from closing it (a few bytes). submit() runs in a worker thread, so
# it hands the message to the event loop with call_soon_threadsafe.
import asyncio
from fastapi.responses import StreamingResponse
_subs: set = set(); _loop = None
@app.on_event("startup")
async def _grab_loop():
    global _loop; _loop = asyncio.get_running_loop()
def publish_stats():
    if not _subs or _loop is None: return
    msg = json.dumps(stats_dict())
    for q in list(_subs): _loop.call_soon_threadsafe(q.put_nowait, msg)
@app.get("/api/events")
async def events(request: Request):
    q: asyncio.Queue = asyncio.Queue(); _subs.add(q)
    async def gen():
        try:
            yield "data: %s\n\n" % json.dumps(await asyncio.to_thread(stats_dict))
            while True:
                try: yield "data: %s\n\n" % await asyncio.wait_for(q.get(), 25)
                except asyncio.TimeoutError: yield ": ping\n\n"
        finally: _subs.discard(q)
    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

WEB = os.path.join(os.path.dirname(__file__), "..", "web")
if os.path.isdir(WEB): app.mount("/", StaticFiles(directory=WEB, html=True), name="web")
