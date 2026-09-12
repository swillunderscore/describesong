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
EVENTS = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "web", "events.json")))
EVENT_CLASSES = set(EVENTS["classes"]); EVENT_WORDS = EVENTS["words"]      # word people type -> AudioSet class
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

CREATE TABLE IF NOT EXISTS lyric_grams(track_id INTEGER NOT NULL, gram INTEGER NOT NULL, PRIMARY KEY(gram, track_id)) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS track_facts(track_id INTEGER PRIMARY KEY, year INTEGER, genres TEXT, country TEXT, source TEXT, fetched REAL, script TEXT, lang TEXT);
CREATE TABLE IF NOT EXISTS artists(mbid TEXT PRIMARY KEY, country TEXT, name TEXT);
CREATE TABLE IF NOT EXISTS track_events(track_id INTEGER NOT NULL, cls TEXT NOT NULL, prob REAL NOT NULL, PRIMARY KEY(track_id, cls)) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS idx_events_cls ON track_events(cls, prob);
CREATE TABLE IF NOT EXISTS lyric_bigrams(track_id INTEGER NOT NULL, gram INTEGER NOT NULL, PRIMARY KEY(gram, track_id)) WITHOUT ROWID;
CREATE VIRTUAL TABLE IF NOT EXISTS tracks_fts USING fts5(artist, title, album, content='');
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

with db() as _c:
    if "lyrics_state" not in [r[1] for r in _c.execute("PRAGMA table_info(tracks)")]:
        _c.execute("ALTER TABLE tracks ADD COLUMN lyrics_state TEXT DEFAULT 'none'")
    if "acoustid" not in [r[1] for r in _c.execute("PRAGMA table_info(tracks)")]:
        # AcoustID's own id for the recording: a fuzzy match, so two rips of the
        # same unidentified song share it while their exact fingerprints differ
        _c.execute("ALTER TABLE tracks ADD COLUMN acoustid TEXT"); _c.execute("CREATE INDEX IF NOT EXISTS idx_tracks_acoustid ON tracks(acoustid)")
    # names index: rebuild from tracks (contentless FTS holds no text of its own)
    if _c.execute("SELECT COUNT(*) FROM tracks_fts").fetchone()[0] != _c.execute("SELECT COUNT(*) FROM tracks").fetchone()[0]:
        _c.execute("DELETE FROM tracks_fts")
        _c.executemany("INSERT INTO tracks_fts(rowid, artist, title, album) VALUES(?,?,?,?)", _c.execute("SELECT id, artist, title, album FROM tracks").fetchall())

with db() as _c:
    cols = [r[1] for r in _c.execute("PRAGMA table_info(track_facts)")]
    for col in ("script", "lang"):
        if col not in cols: _c.execute("ALTER TABLE track_facts ADD COLUMN %s TEXT" % col)

# ---- the index --------------------------------------------------------------
# Exact matmul while it fits in RAM; faiss IVF-PQ with exact re-ranking beyond;
# automatic event-driven rebuilds; a slow exact second pass. See vindex.py.
from vindex import VectorIndex
_subs: set = set(); _loop = None
def _rebuild_event(ev): publish({"rebuild": ev})
INDEX = VectorIndex(DATA, on_event=_rebuild_event)
with db() as _c:
    INDEX.load_from_rows(((r["track_id"], r["vec"]) for r in _c.execute("SELECT track_id, vec FROM vectors WHERE kind='mean' ORDER BY track_id")),
                         _c.execute("SELECT COUNT(*) FROM vectors WHERE kind='mean'").fetchone()[0])
print("vindex:", INDEX.status())

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
        known = c.execute("SELECT id, fp_hash, mbid, artist, title, album, verified, submissions FROM tracks WHERE fp_hash=?", (fp_hash,)).fetchone()
    def verified_reply(known):
        # Already in, and verified: nothing a re-submission of the same encode
        # could add. The client skips the embed (resume from any browser).
        with db() as c: hev = c.execute("SELECT 1 FROM track_events WHERE track_id=? LIMIT 1", (known["id"],)).fetchone() is not None
        return {"fp_hash": known["fp_hash"], "mbid": known["mbid"], "artist": known["artist"], "title": known["title"], "album": known["album"],
                "verified": 1, "prior": None, "known": True, "submissions": known["submissions"], "has_events": hev, "acoustid": aid}
    mbid = meta = aid = None
    if known and known["mbid"]: return verified_reply(known)
    if ACOUSTID_KEY and acoustid_slot():
        import urllib.parse, urllib.request
        u = ("https://api.acoustid.org/v2/lookup?client=%s&meta=recordings+releasegroups&duration=%d&fingerprint=%s"
             % (ACOUSTID_KEY, body.duration, urllib.parse.quote(body.fingerprint)))
        try:
            d = json.load(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": UA}), timeout=8))
            # AcoustID's id for the recording, with or without a MusicBrainz link: the
            # BACKUP identity for what MusicBrainz does not know. 0.9, not 0.5: a
            # sample can share enough of a fingerprint with its source to score
            # lower than that, and merging a sample into its original is worse than
            # two rips of one song staying apart.
            top = max(d.get("results", []), key=lambda r: r.get("score", 0), default=None)
            if top and top.get("score", 0) >= 0.9 and top.get("id"): aid = top["id"]
            best = max((r for r in d.get("results", []) if r.get("recordings")), key=lambda r: r.get("score", 0), default=None)
            if best and best.get("score", 0) >= 0.5:
                rec = best["recordings"][0]; mbid = rec.get("id")
                meta = {"title": rec.get("title"), "artist": ", ".join(a.get("name", "") for a in rec.get("artists", []) or []),
                        "album": (rec.get("releasegroups") or [{}])[0].get("title")}
        except Exception:
            pass
    if not known and aid:
        # a different rip of a recording someone already submitted: same identity
        with db() as c:
            known = c.execute("SELECT id, fp_hash, mbid, artist, title, album, verified, submissions FROM tracks WHERE acoustid=? ORDER BY verified DESC, submissions DESC LIMIT 1", (aid,)).fetchone()
        if known:
            fp_hash = known["fp_hash"]
            if known["mbid"]: return verified_reply(known)
    # Nothing verified: hand back whatever a previous submitter said, so the
    # client can ask "someone labelled this X — correct?" (decision 6).
    prior = None
    if known and not known["mbid"]:
        prior = {"artist": known["artist"], "title": known["title"], "album": known["album"], "submissions": known["submissions"]}
    hev = False
    if known:
        with db() as c: hev = c.execute("SELECT 1 FROM track_events WHERE track_id=? LIMIT 1", (known["id"],)).fetchone() is not None
    return {"fp_hash": fp_hash, "mbid": mbid, "verified": 1 if mbid else 0, "prior": prior, "acoustid": aid,
            "known": bool(known), "submissions": known["submissions"] if known else 0, "has_events": hev, **(meta or {})}

# ---- /submit : identity + vectors, nothing else ----------------------------
class SubmitIn(BaseModel):
    model: str
    fp_hash: str = Field(min_length=40, max_length=40)
    mbid: str | None = None
    acoustid: str | None = Field(default=None, max_length=40)
    duration: int = Field(ge=1, le=36000)
    artist: str | None = Field(default=None, max_length=300)
    title: str | None = Field(default=None, max_length=300)
    album: str | None = Field(default=None, max_length=300)
    mean: list[float] | None = None          # None = label vote only; the recording must already be in
    year: int | None = Field(default=None, ge=1900, le=2100)      # from the file's own tags, if any
    genre: str | None = Field(default=None, max_length=100)
    events: dict[str, float] | None = None      # AudioSet classes the browser heard, with probabilities
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
    events = {}
    if body.events:
        for k, v in body.events.items():
            if k in EVENT_CLASSES and isinstance(v, (int, float)) and 0.0 <= float(v) <= 1.0: events[k] = round(float(v), 4)
        if len(events) > 60: raise HTTPException(400, "too many events")
    mean = None if vote_only else unit(body.mean); moments = [] if vote_only else [unit(m) for m in body.moments]
    now = time.time()
    with db() as c:
        row = c.execute("SELECT id, mbid, verified FROM tracks WHERE fp_hash=?", (body.fp_hash,)).fetchone()
        if vote_only and row is None: raise HTTPException(400, "label vote for a recording that is not in the database")
        if row is None:
            c.execute("INSERT INTO tracks(fp_hash, mbid, acoustid, duration, artist, title, album, verified, submissions, created) VALUES(?,?,?,?,?,?,?,?,1,?)",
                      (body.fp_hash, body.mbid, body.acoustid, body.duration, body.artist, body.title, body.album, 1 if body.mbid else 0, now))
            tid = c.execute("SELECT id FROM tracks WHERE fp_hash=?", (body.fp_hash,)).fetchone()["id"]
            new_track = True
        else:
            tid = row["id"]; c.execute("UPDATE tracks SET submissions=submissions+1 WHERE id=?", (tid,))
            if body.acoustid: c.execute("UPDATE tracks SET acoustid=? WHERE id=? AND acoustid IS NULL", (body.acoustid, tid))
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
        if events is not None:
            # {} means the tagger listened and heard nothing above threshold; a
            # sentinel row keeps that from being re-tagged on every re-scan
            c.execute("DELETE FROM track_events WHERE track_id=?", (tid,))
            c.executemany("INSERT INTO track_events(track_id, cls, prob) VALUES(?,?,?)", [(tid, k, v) for k, v in events.items()] or [(tid, "-", 0.0)])
        if vote_only: return {"ok": True, "track_id": tid, "vote": True, "events": len(events)}
        old = c.execute("SELECT vec FROM vectors WHERE track_id=? AND kind='mean'", (tid,)).fetchone()
        if old:
            prev = np.frombuffer(old["vec"], np.float16).astype(np.float32); mean = prev + mean; mean /= np.linalg.norm(mean) + 1e-9
        c.execute("INSERT OR REPLACE INTO vectors VALUES(?,?,?,?)", (tid, "mean", 0, mean.astype(np.float16).tobytes()))
        for i, m in enumerate(moments):
            c.execute("INSERT OR REPLACE INTO vectors VALUES(?,?,?,?)", (tid, "moment", i, m.astype(np.float16).tobytes()))
    INDEX.add(tid, mean)
    with db() as c:
        r = c.execute("SELECT artist, title, album FROM tracks WHERE id=?", (tid,)).fetchone()
        c.execute("INSERT OR REPLACE INTO tracks_fts(rowid, artist, title, album) VALUES(?,?,?,?)", (tid, r["artist"], r["title"], r["album"]))
    if body.year or body.genre:
        with db() as c:
            if not c.execute("SELECT 1 FROM track_facts WHERE track_id=? AND source='musicbrainz'", (tid,)).fetchone():
                c.execute("INSERT OR REPLACE INTO track_facts(track_id, year, genres, country, source, fetched) VALUES(?,?,?,?,?,?)",
                          (tid, body.year, json.dumps([body.genre.strip().lower()]) if body.genre else None, None, "tags", now))
    name_facts(tid)
    if body.mbid: FACTS.enqueue(tid, body.mbid)
    else: FACTS.enqueue_name(tid, body.artist, body.title)   # unidentified: the artist's country and the song's year by NAME
    queue_lyrics(tid)
    if new_track: publish_stats()
    return {"ok": True, "track_id": tid}

GAP_REF = 0.55        # top-minus-median gap of a specific query (measured 0.39–0.65)
BROAD_GAP = 0.30      # below this the query fits the library about equally (obtuse words: 0.21–0.26)
MIN_FOR_STATS = 20    # fewer tracks than this and the median is meaningless (1 track: top == median)
CAL_FLOOR = 0.15      # median cosine of unrelated tracks for a specific query, used while small

# ---- /search : a sentence in, songs out ------------------------------------
@app.get("/api/search")
def search(q: str, request: Request, k: int = 30, exact: int = 0, offset: int = 0):
    ratelimit(client_ip(request), 3000)
    q = q.strip()[:500]        # the text tower reads ~77 tokens anyway; no reason to tokenise a novel
    if not q: raise HTTPException(400, "empty query")
    # PRECISION ON DEMAND: labelled parts are matched as what they are (artist:,
    # title:, album:, lyrics:, year:, country:), quoted phrases must be in the
    # lyrics, stated facts filter, negated phrases are dropped, and what is left
    # is the sound. Nothing here needs a model; the sound model only ever sees
    # the sound words.
    import facts as _facts
    fields = _facts.parse_fields(q); free = fields.get("free", "")
    stated = _facts.parse(free); sound_q = _facts.strip_negations(stated["stripped"]) or free
    if fields.get("year"):
        y = _facts.parse(fields["year"]); stated["year_from"], stated["year_to"] = y["year_from"] or stated["year_from"], y["year_to"] or stated["year_to"]
    if fields.get("country"):
        stated["country"] = _facts.place(fields["country"]) or stated["country"]
    qv = text_embed(sound_q if len(sound_q) >= 2 else q)
    n = int(INDEX.n); offset = max(0, min(offset, 1000)); k = max(1, min(k, 100)); want = offset + k
    # a stated fact filters AFTER retrieval, so retrieve deep enough that a narrow
    # filter still leaves pages of results ("nineties rap" out of 8 candidates left 3)
    if stated["year_from"] or stated["country"] or stated["instrumental"] or any(re.search(r"(?<![\w])" + re.escape(w) + r"(?![\w])", free.lower()) for w in EVENT_WORDS): want = max(want, 400)
    if exact:
        # THE SLOW SECOND PASS: every track, from disk, only while nobody else is
        # searching. 503 means "not now" and the page keeps the fast answer.
        r = INDEX.exact_scan(qv, k=want)
        if r is None: raise HTTPException(503, "busy")
        ids, scores, med_all = r; is_exact = True
    else:
        INDEX.busy += 1
        try: ids, scores, med_all, is_exact = INDEX.search(qv, k=want)
        finally: INDEX.busy -= 1
    if not ids: return {"results": [], "broad": False, "small": True, "count": n, "exact": True}
    top_all = float(scores[0])
    # WORDS FIRST. Three words in a row from the lyrics, or every word of the
    # query in the name, is an exact kind of evidence the sound model cannot
    # give. Those tracks lead (only on the first page), marked with how.
    via = {}; quoted_miss = False
    phrases = re.findall(r'"([^"]{2,120})"|“([^”]{2,120})”', free); phrases = [a or b for a, b in phrases]
    if fields.get("lyrics"): phrases.append(fields["lyrics"])
    if offset == 0 and any(fields.get(f) for f in ("artist", "title", "album")):
        with db() as c:
            cond = " AND ".join("%s:%s" % (f, " ".join('"%s"' % t for t in re.findall(r"[^\s\"]+", fields[f]))) for f in ("artist", "title", "album") if fields.get(f))
            try:
                for r in c.execute("SELECT rowid FROM tracks_fts WHERE tracks_fts MATCH ? ORDER BY bm25(tracks_fts) LIMIT 100", (cond,)).fetchall(): via.setdefault(r["rowid"], ("name", 1.0))
            except Exception: pass
        if not via: quoted_miss = quoted_miss or True
    if offset == 0 and phrases:
        # QUOTES INSIST: only tracks whose lyrics contain every quoted phrase,
        # ordered by how the rest of the sentence sounds (or by name if nothing else was said)
        qh = quoted_hits(phrases)
        if qh is not None:
            if not qh: quoted_miss = True
            rest = re.sub(r'"[^"]*"|“[^”]*”', " ", q).strip(" ,.")
            keep = {t for t, _ in qh}
            if len(_lyr.norm_words(rest)) >= 2 and keep:
                rv = text_embed(rest); pos = [INDEX.pos[t] for t in keep if t in INDEX.pos]
                sc = np.asarray(INDEX.M16[np.sort(pos)], np.float32) @ rv if pos else np.zeros(0)
                order = np.argsort(-sc); srt = np.sort(pos)
                for i in order: via[int(INDEX.ids[srt[i]])] = ("lyrics", 0.5 + 0.5 * float(sc[i]))
            else:
                for t, _ in qh: via[t] = ("lyrics", 1.0)
    # SOUND EVENTS: words like "hand claps", "whistling", "saxophone" name AudioSet
    # classes the browser measured per track (measured 2026-09-12 on his labels:
    # the classifier was 88-100 % right on claps and whistling where CLAP was
    # 0-8 %). A track known to have the sound ranks up; absence never excludes,
    # because tracks scanned before the tagger existed have no events stored.
    want_events = set()
    for w, cls in EVENT_WORDS.items():
        if re.search(r"(?<![\w])" + re.escape(w) + r"(?![\w])", free.lower()): want_events.add(cls)
    if want_events and ids:
        with db() as c:
            hits = {}
            for r in c.execute("SELECT track_id, cls, prob FROM track_events WHERE cls IN (%s) AND prob >= 0.15 AND track_id IN (%s)" % (",".join("?" * len(want_events)), ",".join("?" * len(ids))), [*want_events, *ids]).fetchall():
                hits[r["track_id"]] = hits.get(r["track_id"], 0) + 1
        kept = sorted(zip(ids, scores), key=lambda x: (-hits.get(x[0], 0), -x[1]))
        ids, scores = [t for t, _ in kept], np.array([sc for _, sc in kept], np.float32)
    if stated["year_from"] or stated["country"] or stated["instrumental"]:
        # FACTS FIRST, NOT FACTS AFTER. The pool above is the 400 nearest by
        # sound; a track the facts fit but the sound model puts 500th was never
        # in it, and no amount of re-sorting could bring it back ("scandinavian
        # … 2000s" had Eple outside the top 100). So every track KNOWN to fit
        # all the stated facts joins the pool, scored exactly from the memmap.
        # Capped: at millions of tracks "2000s" alone is too many to score.
        conds, args = [], []
        if stated["year_from"]: conds.append("f.year BETWEEN ? AND ?"); args += [stated["year_from"], stated["year_to"]]
        if stated["country"]: conds.append("f.country IN (%s)" % ",".join("?" * len(stated["country"]))); args += sorted(stated["country"])
        if stated["instrumental"]: conds.append("t.lyrics_state='instrumental'")
        with db() as c:
            fit = [r["id"] for r in c.execute("SELECT t.id FROM tracks t JOIN track_facts f ON f.track_id=t.id WHERE " + " AND ".join(conds) + " LIMIT 20000", args).fetchall()]
        have = set(int(t) for t in ids); extra = [t for t in fit if t not in have and t in INDEX.pos]
        if extra:
            pos = np.array([INDEX.pos[t] for t in extra]); order = np.argsort(pos)
            sc = np.asarray(INDEX.M16[pos[order]], np.float32) @ qv
            ids = list(ids) + [extra[i] for i in order]; scores = np.concatenate([np.asarray(scores, np.float32), sc])
        # STATED FACTS: a track that contradicts one is dropped; the rest rank by how
        # many stated facts they are KNOWN to satisfy, then by sound (otherwise the
        # unidentified tracks, which can never contradict, float to the top).
        with db() as c:
            scripts = {_facts.SCRIPT_COUNTRIES.get(cc) for cc in (stated["country"] or ())}; want_script = scripts.pop() if len(scripts) == 1 else None   # one script for the whole region, or no hint
            tier = {}
            for r in c.execute("SELECT t.id, f.year, f.country, f.script, f.lang, t.lyrics_state FROM tracks t LEFT JOIN track_facts f ON f.track_id=t.id WHERE t.id IN (%s)" % ",".join("?" * len(ids)), list(ids)).fetchall():
                ok = True; known = 0; asked = 0
                demote = 0
                if stated["year_from"]:
                    asked += 1
                    # a wrong year demotes rather than drops: release dates for a recording
                    # can be a compilation's (Eple came back as 2018), and hiding a track
                    # for a data error is worse than showing it lower
                    if r["year"]:
                        if stated["year_from"] <= r["year"] <= stated["year_to"]: known += 1
                        else: demote = 1
                if stated["country"]:
                    asked += 1
                    if r["country"]: known += 1; ok = ok and r["country"] in stated["country"]
                    elif r["script"] and r["script"] != "latin" and want_script: known += 1; ok = ok and r["script"] == want_script
                    elif r["script"] and r["script"] != "latin" and not want_script: ok = False
                if stated["instrumental"]:
                    asked += 1
                    if r["lyrics_state"] in ("found", "instrumental"): known += 1; ok = ok and r["lyrics_state"] == "instrumental"
                if ok: tier[r["id"]] = known - demote          # known matches count up; a contradicting year counts down
        kept = sorted(((t, sc) for t, sc in zip(ids, scores) if t in tier), key=lambda x: (-tier[x[0]], -x[1]))
        if kept: ids, scores = [t for t, _ in kept], np.array([sc for _, sc in kept], np.float32)
    if offset == 0 and not phrases and not any(fields.get(f) for f in ("artist", "title", "album")):
        for t, frac in lyric_hits(q):
            if frac >= 0.34 or (frac > 0 and len(_lyr.norm_words(q)) <= 5): via.setdefault(t, ("lyrics", frac))
        for t, _ in name_hits(free): via.setdefault(t, ("name", 1.0))
    lead = [t for t, _ in sorted(via.items(), key=lambda kv: -kv[1][1])]
    merged = [(t, top_all) for t in lead] + [(t, float(sc)) for t, sc in zip(ids, scores) if t not in via]
    ids = [t for t, _ in merged][offset:offset + k]; scores = np.array([sc for _, sc in merged][offset:offset + k], np.float32)   # the page asked for
    if not len(ids): return {"results": [], "broad": False, "small": n < MIN_FOR_STATS, "count": n, "exact": bool(is_exact), "mode": INDEX.mode}
    with db() as c:
        rows = {r["id"]: r for r in c.execute("SELECT * FROM tracks WHERE id IN (%s)" % ",".join("?" * len(ids)), ids)}
        facts_rows = {r["track_id"]: r for r in c.execute("SELECT track_id, year, country FROM track_facts WHERE track_id IN (%s)" % ",".join("?" * len(ids)), ids)}
    # CONFIDENCE (decision 9, calibrated 2026-09-11 on the test library — see QUEUE.md).
    # The raw cosine says nothing: "gay" scores 0.61, above most true hits. What
    # separates a description from an obtuse word is how far the leader stands
    # above the WHOLE library's median: specific queries 0.39–0.65, obtuse words
    # 0.21–0.26. So confidence = (score - median) / GAP_REF, per row — the leader
    # of a vague query lands near 45%, of a specific one at 100%. Under
    # MIN_FOR_STATS tracks the live median is the query's own results, so a fixed
    # floor stands in and the client says the numbers are rough.
    small = n < MIN_FOR_STATS
    med = CAL_FLOOR if small else med_all
    top = top_all; gap = top - med
    broad = (not small) and gap < BROAD_GAP and not via     # a name or lyric match IS a clear winner
    res = []
    for tid, s in zip(ids, scores):
        r = rows.get(tid)
        if not r: continue
        v = via.get(tid); fr = facts_rows.get(tid)
        res.append({"id": int(tid), "artist": r["artist"], "title": r["title"], "album": r["album"], "mbid": r["mbid"], "year": fr["year"] if fr else None, "country": fr["country"] if fr else None,
                    "verified": bool(r["verified"]), "duration": r["duration"], "score": round(float(s), 4),
                    "via": v[0] if v else "sound",
                    "confidence": (100 if v[1] >= 0.99 else max(60, int(round(100 * v[1])))) if v else int(round(100 * max(0.0, min(1.0, (float(s) - med) / GAP_REF))))})
    return {"results": res, "broad": broad, "small": small, "count": n, "gap": round(gap, 3), "exact": bool(is_exact), "mode": INDEX.mode, "quoted_miss": quoted_miss}

# ---- what the index hears ---------------------------------------------------
# A track's vector against a vocabulary of phrases, same model, reversed. The
# vocabulary's text vectors are computed once and cached next to the data.
import vocab as _vocab
_VOC = {}
def vocab_matrix():
    if "M" in _VOC: return _VOC["M"]
    key = hashlib.sha1((MODEL_ID + "|" + "\n".join(_vocab.VOCAB)).encode()).hexdigest()[:12]
    p = os.path.join(DATA, "vocab-%s.npz" % key)
    if os.path.exists(p): M = np.load(p)["M"]
    else:
        M = np.stack([text_embed(t) for t in _vocab.VOCAB]).astype(np.float32); np.savez(p, M=M)
    _VOC["M"] = M; return M

@app.get("/api/describe/{tid}")
def describe(tid: int, request: Request):
    ratelimit(client_ip(request), 3000)
    with db() as c:
        row = c.execute("SELECT vec FROM vectors WHERE track_id=? AND kind='mean'", (tid,)).fetchone()
    if not row: raise HTTPException(404, "no such track")
    v = np.frombuffer(row["vec"], np.float16).astype(np.float32)
    M = vocab_matrix(); s = M @ v; med = float(np.median(s)); top = float(s.max())
    order = np.argsort(-s)
    out, seen = [], {}
    for i in order:
        g = _vocab.GROUP[_vocab.VOCAB[i]]
        if seen.get(g, 0) >= 3 and g != "genre": continue           # a spread of kinds, not eight moods
        seen[g] = seen.get(g, 0) + 1
        out.append({"tag": _vocab.VOCAB[i], "group": g, "score": round(float(s[i]), 4), "pct": int(round(100 * max(0.0, (float(s[i]) - med) / max(1e-6, top - med))))})
        if len(out) >= 12: break
    with db() as c:
        evs = [{"cls": r["cls"], "prob": round(r["prob"], 2)} for r in c.execute("SELECT cls, prob FROM track_events WHERE track_id=? AND prob >= 0.1 ORDER BY prob DESC LIMIT 12", (tid,)).fetchall()]
    return {"id": tid, "tags": out, "events": evs}

# ---- lyrics: hashed trigrams from LRCLIB, text discarded (see lyrics.py) ----
import lyrics as _lyr
def _store_lyrics(tid, state, g, g2=()):
    with db() as c:
        c.execute("DELETE FROM lyric_grams WHERE track_id=?", (tid,)); c.execute("DELETE FROM lyric_bigrams WHERE track_id=?", (tid,))
        if g: c.executemany("INSERT OR IGNORE INTO lyric_grams(track_id, gram) VALUES(?,?)", [(tid, x) for x in g])
        if g2: c.executemany("INSERT OR IGNORE INTO lyric_bigrams(track_id, gram) VALUES(?,?)", [(tid, x) for x in g2])
        c.execute("UPDATE tracks SET lyrics_state=? WHERE id=?", (state, tid))
LYRICS = _lyr.LyricsWorker(_store_lyrics)
def queue_lyrics(tid):
    with db() as c:
        r = c.execute("SELECT artist, title, album, duration, lyrics_state FROM tracks WHERE id=?", (tid,)).fetchone()
    if r and r["lyrics_state"] == "none": LYRICS.enqueue(tid, r["artist"], r["title"], r["album"], r["duration"])
with db() as _c:   # one-time: lyrics found before the bigram table existed are fetched again so quotes work on them
    if _c.execute("SELECT COUNT(*) FROM lyric_bigrams").fetchone()[0] == 0 and _c.execute("SELECT COUNT(*) FROM tracks WHERE lyrics_state='found'").fetchone()[0]:
        _c.execute("UPDATE tracks SET lyrics_state='none' WHERE lyrics_state='found'")
with db() as _c:   # catch-up: everything that has never been looked up
    for r in _c.execute("SELECT id, artist, title, album, duration FROM tracks WHERE lyrics_state='none' AND artist IS NOT NULL AND title IS NOT NULL").fetchall():
        LYRICS.enqueue(r["id"], r["artist"], r["title"], r["album"], r["duration"])
print("lyrics: queued", LYRICS.q.qsize())

def quoted_hits(phrases, limit=200):
    """Every quoted phrase must be present (all of its bigrams, or trigrams for 3+ words).
    -> [(track_id, 1.0)] or [] ; None if no phrase was usable (single words)."""
    need = None
    for ph in phrases:
        w = _lyr.norm_words(ph)
        if len(w) < 2: continue
        g = list(_lyr.grams(w, 3)) if len(w) >= 3 else list(_lyr.grams(w, 2)); table = "lyric_grams" if len(w) >= 3 else "lyric_bigrams"
        with db() as c:
            rows = c.execute("SELECT track_id FROM %s WHERE gram IN (%s) GROUP BY track_id HAVING COUNT(*) = ? LIMIT ?" % (table, ",".join("?" * len(g))), (*g, len(g), limit)).fetchall()
        got = {r["track_id"] for r in rows}
        need = got if need is None else (need & got)
    return None if need is None else [(t, 1.0) for t in need]

# ---- facts: MusicBrainz for identified tracks; script/language hints from the names for every track ----
import mbfacts as _mb, facts as _facts
def _store_facts(tid, year, genres, country, source):
    with db() as c:
        row = c.execute("SELECT script, lang, year, genres FROM track_facts WHERE track_id=?", (tid,)).fetchone()
        c.execute("INSERT OR REPLACE INTO track_facts(track_id, year, genres, country, source, fetched, script, lang) VALUES(?,?,?,?,?,?,?,?)",
                  (tid, year or (row["year"] if row else None), json.dumps(genres) if genres else (row["genres"] if row else None), country, source, time.time(), row["script"] if row else None, row["lang"] if row else None))
def _artist_get(mbid):
    with db() as c: r = c.execute("SELECT country FROM artists WHERE mbid=?", (mbid,)).fetchone()
    return None if r is None else (r["country"] or "")
def _artist_put(mbid, country, name):
    with db() as c: c.execute("INSERT OR REPLACE INTO artists(mbid, country, name) VALUES(?,?,?)", (mbid, country, name))
FACTS = _mb.FactsWorker(_store_facts, _artist_get, _artist_put)
def name_facts(tid):
    """script and letter hints from the track's own artist/title — for every track, no network"""
    with db() as c:
        r = c.execute("SELECT artist, title FROM tracks WHERE id=?", (tid,)).fetchone()
        if not r: return
        txt = (r["artist"] or "") + " " + (r["title"] or "")
        sc = _facts.script_of(txt); lh = ",".join(_facts.lang_hints(txt)) or None
        if c.execute("SELECT 1 FROM track_facts WHERE track_id=?", (tid,)).fetchone(): c.execute("UPDATE track_facts SET script=?, lang=? WHERE track_id=?", (sc, lh, tid))
        else: c.execute("INSERT INTO track_facts(track_id, script, lang, source) VALUES(?,?,?,?)", (tid, sc, lh, "names"))
with db() as _c:
    for r in _c.execute("SELECT t.id FROM tracks t LEFT JOIN track_facts f ON f.track_id=t.id WHERE f.track_id IS NULL OR f.script IS NULL AND f.lang IS NULL").fetchall(): name_facts(r["id"])
    for r in _c.execute("SELECT t.id, t.mbid FROM tracks t LEFT JOIN track_facts f ON f.track_id=t.id WHERE t.mbid IS NOT NULL AND (f.source IS NULL OR f.source NOT LIKE 'musicbrainz%' OR f.source LIKE '%-error' OR (f.country IS NULL AND f.source='musicbrainz' AND f.fetched < strftime('%s','now') - 30*86400))").fetchall(): FACTS.enqueue(r["id"], r["mbid"])
    # unidentified tracks: look the artist up by name (country) and the title (year)
    for r in _c.execute("SELECT t.id, t.artist, t.title FROM tracks t LEFT JOIN track_facts f ON f.track_id=t.id WHERE t.mbid IS NULL AND (f.source IS NULL OR f.source IN ('names', 'tags') OR f.source LIKE '%-error')").fetchall(): FACTS.enqueue_name(r["id"], r["artist"], r["title"])
print("facts: queued", FACTS.q.qsize())

def lyric_hits(q, limit=30):
    """tracks sharing hashed trigrams with the query -> [(track_id, fraction of query grams matched)]"""
    g = list(_lyr.grams(_lyr.norm_words(q)))
    if not g: return []
    with db() as c:
        rows = c.execute("SELECT track_id, COUNT(*) n FROM lyric_grams WHERE gram IN (%s) GROUP BY track_id ORDER BY n DESC LIMIT ?" % ",".join("?" * len(g)), (*g, limit)).fetchall()
    return [(r["track_id"], r["n"] / len(g)) for r in rows]

def name_hits(q, limit=10):
    """every query word (3+ letters) present in artist/title/album -> [(track_id, rank)]"""
    toks = [t for t in re.findall(r"[a-z0-9]+", q.lower()) if len(t) >= 3]
    if not toks: return []
    with db() as c:
        try: rows = c.execute("SELECT rowid, bm25(tracks_fts) r FROM tracks_fts WHERE tracks_fts MATCH ? ORDER BY r LIMIT ?", (" ".join('"%s"' % t for t in toks), limit)).fetchall()
        except Exception: return []
    return [(r["rowid"], float(r["r"])) for r in rows]

@app.get("/api/similar/{tid}")
def similar(tid: int, request: Request, k: int = 30):
    """Tracks nearest to THIS track's vector — browsing by sound, and the honest
    demonstration of what the index can and cannot tell apart."""
    ratelimit(client_ip(request), 3000)
    with db() as c:
        row = c.execute("SELECT vec FROM vectors WHERE track_id=? AND kind='mean'", (tid,)).fetchone()
    if not row: raise HTTPException(404, "no such track")
    v = np.frombuffer(row["vec"], np.float16).astype(np.float32)
    INDEX.busy += 1
    try: ids, scores, med, is_exact = INDEX.search(v, k=max(1, min(k, 100)) + 1)
    finally: INDEX.busy -= 1
    pairs = [(t, float(sc)) for t, sc in zip(ids, scores) if t != tid][:k]
    with db() as c:
        rows = {r["id"]: r for r in c.execute("SELECT * FROM tracks WHERE id IN (%s)" % ",".join("?" * len(pairs)), [t for t, _ in pairs])}
    res = [{"id": int(t), "artist": rows[t]["artist"], "title": rows[t]["title"], "album": rows[t]["album"], "verified": bool(rows[t]["verified"]), "via": "sound",
            "score": round(sc, 4), "confidence": int(round(100 * max(0.0, min(1.0, sc))))} for t, sc in pairs if t in rows]
    return {"results": res, "exact": bool(is_exact), "count": int(INDEX.n)}

def stats_dict():
    with db() as c:
        t = c.execute("SELECT COUNT(*) n, SUM(verified) v, SUM(created > ?) w FROM tracks", (time.time() - 7 * 86400,)).fetchone()
    st = INDEX.status()
    with db() as c: ly = c.execute("SELECT SUM(lyrics_state='found') f, SUM(lyrics_state='none') p FROM tracks").fetchone()
    return {"tracks": t["n"], "verified": t["v"] or 0, "week": t["w"] or 0, "model": MODEL_ID, "acoustid": bool(ACOUSTID_KEY), "lyrics": ly["f"] or 0, "lyrics_pending": ly["p"] or 0,
            "mode": st["mode"], "rebuild": st["build"] if st["building"] else None}

@app.get("/api/stats")
def stats(): return stats_dict()

# LIVE COUNTS. One open connection per tab, and a message only when a track is
# added — nothing polls. A comment line every 25 s keeps the tunnel's idle
# timeout from closing it (a few bytes). submit() runs in a worker thread, so
# it hands the message to the event loop with call_soon_threadsafe.
import asyncio
from fastapi.responses import StreamingResponse
@app.on_event("startup")
async def _grab_loop():
    global _loop; _loop = asyncio.get_running_loop()
def publish(obj):
    if not _subs or _loop is None: return
    msg = json.dumps(obj)
    for q in list(_subs): _loop.call_soon_threadsafe(q.put_nowait, msg)
def publish_stats(): publish(stats_dict())
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
