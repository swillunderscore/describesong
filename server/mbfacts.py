"""Facts about identified tracks from MusicBrainz: first release year, genre
tags, and the artist's country. One request per second, as MusicBrainz asks;
one worker thread; queued by submissions and by a catch-up pass at startup.
Artists are cached so a library of 2,000 tracks by 500 artists costs 2,500
requests, not 4,000. Nothing here is a timer: the queue drains and waits."""
import json, queue, threading, time, urllib.parse, urllib.request

UA = "DescribeSong/1 (https://describesong.com; swillsoftware@proton.me)"
GAP = 1.05

def _get(url):
    for attempt in range(3):
        try:
            return json.load(urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=15))
        except Exception as e:
            if "503" in str(e) or "429" in str(e): time.sleep(5 + 5 * attempt); continue
            return None
    return None

def recording(mbid):
    d = _get("https://musicbrainz.org/ws/2/recording/%s?inc=releases+genres+tags+artist-credits&fmt=json" % mbid)
    if not d: return None
    years = sorted(int(x["date"][:4]) for x in d.get("releases", []) if x.get("date", "")[:4].isdigit())
    tags = [t["name"] for t in sorted(d.get("genres", []) + d.get("tags", []), key=lambda t: -t.get("count", 0))]
    seen, genres = set(), []
    for t in tags:
        if t.lower() not in seen: seen.add(t.lower()); genres.append(t.lower())
    artists = [a["artist"]["id"] for a in d.get("artist-credit", []) if isinstance(a, dict) and a.get("artist", {}).get("id")]
    return {"year": years[0] if years else None, "genres": genres[:8], "artists": artists}

def artist(mbid):
    d = _get("https://musicbrainz.org/ws/2/artist/%s?fmt=json" % mbid)
    if not d: return None
    return {"country": d.get("country") or ((d.get("area") or {}).get("iso-3166-1-codes") or [None])[0], "name": d.get("name")}

class FactsWorker:
    def __init__(self, store, artist_cache_get, artist_cache_put):
        self.q = queue.Queue(); self.store = store; self.aget = artist_cache_get; self.aput = artist_cache_put
        self.pending = set(); self.lock = threading.Lock(); self.last = 0.0
        threading.Thread(target=self._run, name="mbfacts", daemon=True).start()
    def enqueue(self, tid, mbid):
        if not mbid: return
        with self.lock:
            if tid in self.pending: return
            self.pending.add(tid)
        self.q.put((tid, mbid))
    def _pace(self):
        wait = GAP - (time.time() - self.last)
        if wait > 0: time.sleep(wait)
        self.last = time.time()
    def _run(self):
        while True:
            tid, mbid = self.q.get()
            try:
                self._pace(); rec = recording(mbid)
                country = None
                if rec:
                    for aid in rec["artists"][:2]:
                        c = self.aget(aid)
                        if c is None:
                            self._pace(); a = artist(aid); c = (a or {}).get("country") or ""; self.aput(aid, c, (a or {}).get("name"))
                        if c: country = c; break
                self.store(tid, rec["year"] if rec else None, rec["genres"] if rec else [], country, "musicbrainz" if rec else "musicbrainz-miss")
            except Exception as e:
                print("mbfacts: failed", tid, e)
            with self.lock: self.pending.discard(tid)
