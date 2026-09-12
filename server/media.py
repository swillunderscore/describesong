"""Covers and 30-second previews, by name, from the two public catalogue APIs
that exist for exactly this (a link back to the store is the price):
Apple's iTunes Search API first (no key, stable preview URLs, 600 px art),
Deezer second (no key; its preview URLs expire, so the track id is stored and
a fresh URL fetched at play time). A match needs the same artist and title
(normalised) and a duration within 6 s — a remix or a live cut is not the
song. No audio is ever stored: the browser streams the store's own preview.
One worker, paced (Apple asks for ~20 requests a minute); errors retried on
the next submission, like the facts worker."""
import json, queue, re, threading, time, urllib.error, urllib.parse, urllib.request

UA = "DescribeSong/1 (https://describesong.com; swillsoftware@proton.me)"
PACE = {"itunes": 3.3, "deezer": 0.6}
def _norm(x): return re.sub(r"[^a-z0-9]+", "", (x or "").lower())
def first_artist(name): return re.split(r",|&|\bfeat\.?\b|\bft\.?\b|\bwith\b|\bvs\.?\b|\bx\b|/", name or "", 1, flags=re.I)[0].strip()
def _bare(title): return re.sub(r"\s*[\(\[].*?[\)\]]\s*", " ", title or "").strip()   # "Eple (Edit)" -> "Eple"

class Unavailable(Exception): pass
def _get(url):
    for wait in (3, 10, 30):
        try: return json.load(urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=15))
        except urllib.error.HTTPError as e:
            if e.code in (403, 429, 500, 502, 503, 504): time.sleep(wait); continue
            if e.code == 404: return None
            raise Unavailable(str(e))
        except Exception as e: raise Unavailable(str(e))
    raise Unavailable("still refusing after 3 attempts")

def _match(cands, artist, title, duration):
    """cands: (artist, title, seconds, payload) -> the payload of the first true match"""
    a, t = _norm(first_artist(artist)), _norm(_bare(title))
    if not t: return None
    for ca, ct, secs, payload in cands:
        if a and a not in _norm(ca) and _norm(ca) not in a: continue
        if _norm(_bare(ct)) != t and not _norm(ct).startswith(t): continue
        if duration and secs and abs(secs - duration) > 6: continue
        return payload
    return None

def itunes(artist, title, duration):
    d = _get("https://itunes.apple.com/search?%s" % urllib.parse.urlencode({"term": "%s %s" % (first_artist(artist), _bare(title)), "entity": "song", "limit": 8}))
    cands = [(r.get("artistName"), r.get("trackName"), (r.get("trackTimeMillis") or 0) / 1000, r) for r in (d or {}).get("results", [])]
    r = _match(cands, artist, title, duration)
    if not r: return None
    return {"source": "itunes", "ext_id": str(r.get("trackId")), "preview": r.get("previewUrl"), "link": r.get("trackViewUrl"),
            "cover": (r.get("artworkUrl100") or "").replace("100x100bb", "600x600bb") or None}

def deezer(artist, title, duration):
    d = _get("https://api.deezer.com/search?%s" % urllib.parse.urlencode({"q": "%s %s" % (first_artist(artist), _bare(title)), "limit": 8}))
    cands = [(r.get("artist", {}).get("name"), r.get("title"), r.get("duration") or 0, r) for r in (d or {}).get("data", [])]
    r = _match(cands, artist, title, duration)
    if not r: return None
    return {"source": "deezer", "ext_id": str(r.get("id")), "preview": None, "link": r.get("link"), "cover": (r.get("album") or {}).get("cover_big") or (r.get("album") or {}).get("cover_medium")}

def deezer_preview(ext_id):
    """a fresh, short-lived preview URL for a Deezer track"""
    d = _get("https://api.deezer.com/track/%s" % ext_id)
    return (d or {}).get("preview") or None

class MediaWorker:
    def __init__(self, store):
        self.q = queue.Queue(); self.store = store; self.pending = set(); self.lock = threading.Lock(); self.last = {"itunes": 0.0, "deezer": 0.0}
        self.down = 0; self.probe = 0
        threading.Thread(target=self._run, name="media", daemon=True).start()
    def enqueue(self, tid, artist, title, duration):
        if not (artist or title): return
        with self.lock:
            if tid in self.pending: return
            self.pending.add(tid)
        self.q.put((tid, artist or "", title or "", duration or 0))
    def _pace(self, who):
        wait = PACE[who] - (time.time() - self.last[who])
        if wait > 0: time.sleep(wait)
        self.last[who] = time.time()
    def _run(self):
        while True:
            tid, artist, title, duration = self.q.get()
            try:
                if self.down >= 3:
                    self.probe += 1
                    if self.probe % 10: self.store(tid, None, "error"); continue
                self._pace("itunes"); m = itunes(artist, title, duration)
                if not m: self._pace("deezer"); m = deezer(artist, title, duration)
                self.store(tid, m, "ok" if m else "miss"); self.down = 0
            except Unavailable as e:
                self.down += 1; print("media: unavailable", tid, e, flush=True); self.store(tid, None, "error")
            except Exception as e:
                print("media: failed", tid, e, flush=True); self.store(tid, None, "error")
            finally:
                with self.lock: self.pending.discard(tid)
