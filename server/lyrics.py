"""Lyrics as a second signal, without storing lyrics.

For every track with an artist and a title, the Pi asks LRCLIB (free, open,
no key) for the lyrics, turns them into hashed word-trigrams, and throws the
text away. A search that contains three or more words in a row from a song
matches those hashes exactly — the case the sound model is worst at ("the one
that goes ...") is the case this is perfect at. Nobody can read lyrics back
out of the hashes; the most an attacker with their own lyrics corpus could do
is confirm a phrase is present, which is a Bloom-filter level of disclosure.

Fetching is a queue drained by one background thread, politely (4 req/s max),
triggered by submissions and by a catch-up pass at startup. No timers.
"""
import hashlib, json, re, threading, time, queue, unicodedata, urllib.parse, urllib.request

UA = "DescribeSong/1 (https://describesong.com; swillsoftware@proton.me)"
MIN_GAP_S = 0.25

def norm_words(text):
    t = unicodedata.normalize("NFKD", text or "").lower()
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = re.sub(r"\[[^\]]*\]|\([^)]*\)", " ", t)                # [chorus], (x2)
    t = t.replace("’", "'").replace("`", "'")
    t = re.sub(r"[^a-z0-9' \n]+", " ", t)
    return [w.strip("'") for w in t.split() if w.strip("'")]

def grams(words, n=3):
    """hashed word-trigrams as signed 63-bit ints (fits SQLite INTEGER)"""
    out = set()
    for i in range(len(words) - n + 1):
        h = hashlib.sha1(" ".join(words[i:i + n]).encode()).digest()
        out.add(int.from_bytes(h[:8], "big") & 0x7FFFFFFFFFFFFFFF)
    return out

def strip_synced(s):
    return re.sub(r"^\s*\[\d+:\d+(\.\d+)?\]\s*", "", s or "", flags=re.M)

def fetch_lyrics(artist, title, album=None, duration=None):
    """-> ('found', text) | ('instrumental', None) | ('missing', None). Never raises."""
    try:
        q = {"artist_name": artist, "track_name": title}
        if album: q["album_name"] = album
        u = "https://lrclib.net/api/search?" + urllib.parse.urlencode(q)
        d = json.load(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": UA}), timeout=12))
        if not d: return "missing", None
        if duration: d.sort(key=lambda r: abs((r.get("duration") or 0) - duration))
        best = d[0]
        if duration and abs((best.get("duration") or 0) - duration) > 12: return "missing", None
        if best.get("instrumental"): return "instrumental", None
        text = best.get("plainLyrics") or strip_synced(best.get("syncedLyrics"))
        return ("found", text) if text and len(text) > 20 else ("missing", None)
    except Exception:
        return "missing", None

class LyricsWorker:
    """One thread, one queue. store(tid, state, gram_set) is the caller's DB write."""
    def __init__(self, store, on_done=None):
        self.q = queue.Queue(); self.store = store; self.on_done = on_done or (lambda *_: None)
        self.pending = set(); self.lock = threading.Lock(); self.last = 0.0
        threading.Thread(target=self._run, name="lyrics", daemon=True).start()
    def enqueue(self, tid, artist, title, album, duration):
        if not artist or not title: return
        with self.lock:
            if tid in self.pending: return
            self.pending.add(tid)
        self.q.put((tid, artist, title, album, duration))
    def _run(self):
        while True:
            tid, artist, title, album, duration = self.q.get()
            wait = MIN_GAP_S - (time.time() - self.last)
            if wait > 0: time.sleep(wait)
            self.last = time.time()
            state, text = fetch_lyrics(artist, title, album, duration)
            g = grams(norm_words(text)) if text else set()
            try: self.store(tid, state, g)
            except Exception as e: print("lyrics: store failed", tid, e)
            with self.lock: self.pending.discard(tid)
            self.on_done(tid, state, len(g))
