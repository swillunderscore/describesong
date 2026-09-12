"""Facts about identified tracks from MusicBrainz: first release year, genre
tags, and the artist's country. One request per second, as MusicBrainz asks;
one worker thread; queued by submissions and by a catch-up pass at startup.
Artists are cached so a library of 2,000 tracks by 500 artists costs 2,500
requests, not 4,000. Nothing here is a timer: the queue drains and waits."""
import json, queue, re, threading, time, urllib.parse, urllib.request

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

def title_year(artist_id, title):
    """Earliest release year of ANY recording of this title by this artist. AcoustID
    often matches the recording id that lives on a 2018 compilation, whose own
    releases say 2018; the song is from 2001. The title-level minimum is the song's year."""
    q = 'arid:%s AND recording:"%s"' % (artist_id, title.replace('"', ""))
    d = _get("https://musicbrainz.org/ws/2/recording?query=%s&limit=25&fmt=json" % urllib.parse.quote(q))
    years = [int(r["first-release-date"][:4]) for r in (d or {}).get("recordings", []) if r.get("first-release-date", "")[:4].isdigit()]
    return min(years) if years else None

def recording(mbid):
    d = _get("https://musicbrainz.org/ws/2/recording/%s?inc=releases+genres+tags+artist-credits&fmt=json" % mbid)
    if not d: return None
    years = sorted(int(x["date"][:4]) for x in d.get("releases", []) if x.get("date", "")[:4].isdigit())
    tags = [t["name"] for t in sorted(d.get("genres", []) + d.get("tags", []), key=lambda t: -t.get("count", 0))]
    seen, genres = set(), []
    for t in tags:
        if t.lower() not in seen: seen.add(t.lower()); genres.append(t.lower())
    artists = [a["artist"]["id"] for a in d.get("artist-credit", []) if isinstance(a, dict) and a.get("artist", {}).get("id")]
    return {"year": years[0] if years else None, "genres": genres[:8], "artists": artists, "title": d.get("title")}

def artist(mbid):
    d = _get("https://musicbrainz.org/ws/2/artist/%s?fmt=json" % mbid)
    if not d: return None
    return {"country": d.get("country") or ((d.get("area") or {}).get("iso-3166-1-codes") or [None])[0], "name": d.get("name")}

def _norm(x): return re.sub(r"[^a-z0-9]+", "", (x or "").lower())
def first_artist(name):
    """'RAC, Body Language' / 'A & B' / 'A feat. B' -> 'RAC': the one whose country we want"""
    return re.split(r",|&|\bfeat\.?\b|\bft\.?\b|\bwith\b|\bvs\.?\b|\bx\b|/", name or "", 1, flags=re.I)[0].strip()
def artist_search(name):
    """An UNIDENTIFIED track's artist, by name. Only an exact name match with a
    top search score counts: 'Justice' has many, and a wrong country drops the
    track from every search that states one."""
    d = _get("https://musicbrainz.org/ws/2/artist?query=%s&limit=5&fmt=json" % urllib.parse.quote('artist:"%s"' % name.replace('"', "")))
    for a in (d or {}).get("artists", []):
        if int(a.get("score", 0)) >= 90 and _norm(a.get("name")) == _norm(name):
            return {"id": a["id"], "country": a.get("country") or ((a.get("area") or {}).get("iso-3166-1-codes") or [None])[0] or "", "name": a["name"]}
    return None
def name_year(artist, title):
    """earliest first-release year of a recording with this title by an artist of this name"""
    q = 'artist:"%s" AND recording:"%s"' % (artist.replace('"', ""), title.replace('"', ""))
    d = _get("https://musicbrainz.org/ws/2/recording?query=%s&limit=25&fmt=json" % urllib.parse.quote(q))
    years = [int(r["first-release-date"][:4]) for r in (d or {}).get("recordings", []) if int(r.get("score", 0)) >= 90 and r.get("first-release-date", "")[:4].isdigit()
             and any(_norm(c.get("name")) == _norm(artist) for c in r.get("artist-credit", []) if isinstance(c, dict))]
    return min(years) if years else None

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
        self.q.put(("mbid", tid, mbid))
    def enqueue_name(self, tid, artist, title):
        a = first_artist(artist)
        if not a: return
        with self.lock:
            if tid in self.pending: return
            self.pending.add(tid)
        self.q.put(("name", tid, (a, title or "")))
    def _pace(self):
        wait = GAP - (time.time() - self.last)
        if wait > 0: time.sleep(wait)
        self.last = time.time()
    def _run(self):
        while True:
            kind, tid, mbid = self.q.get()
            try:
                if kind == "name":
                    artist_name, title = mbid
                    key = "name:" + _norm(artist_name); c = self.aget(key)
                    if c is None:
                        self._pace(); a = artist_search(artist_name); c = (a or {}).get("country") or ""; self.aput(key, c, artist_name)
                        if a and a.get("id"): self.aput(a["id"], c, a.get("name"))
                    self._pace(); y = name_year(artist_name, title) if title else None
                    self.store(tid, y, [], c or None, "musicbrainz-name" if (c or y) else "musicbrainz-name-miss")
                    with self.lock: self.pending.discard(tid)
                    continue
                self._pace(); rec = recording(mbid)
                country = None
                if rec and rec["artists"] and rec.get("title"):
                    self._pace(); ty = title_year(rec["artists"][0], rec["title"])
                    if ty and (rec["year"] is None or ty < rec["year"]): rec["year"] = ty
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
