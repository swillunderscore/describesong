"""Seed an ear's vectors from a .npz of (paths, vectors) computed offline.

Used to fill the MuLan index from the trial run so a switch does not empty the
search. Matches a file path to a track by normalised artist+title, then by
title alone when that is unique. Prints what it could NOT match, always.
"""
import os, re, sys, sqlite3, numpy as np

def norm(x): return re.sub(r"[^a-z0-9]+", "", (x or "").lower())

def main(npz_path, db_path, model, dry=False):
    d = np.load(npz_path, allow_pickle=True)
    paths = [str(p) for p in d["paths"]]; V = d["vectors"].astype(np.float32)
    V /= np.linalg.norm(V, axis=1, keepdims=True) + 1e-9
    c = sqlite3.connect(db_path); c.row_factory = sqlite3.Row
    tracks = c.execute("SELECT id, artist, title FROM tracks").fetchall()
    by_at, by_t = {}, {}
    for r in tracks:
        by_at.setdefault(norm(r["artist"]) + "|" + norm(r["title"]), []).append(r["id"])
        by_t.setdefault(norm(r["title"]), []).append(r["id"])
    # a second table keyed on the title with any "(feat. ...)" / "[remix]" tail
    # removed — the tags and the filenames disagree about those constantly
    def bare(t): return norm(re.sub(r"\s*[\(\[].*?[\)\]]\s*", " ", t or ""))
    by_bare = {}
    for r in tracks: by_bare.setdefault(norm(r["artist"]) + "|" + bare(r["title"]), []).append(r["id"])
    hit, miss, amb = [], [], 0
    for i, p in enumerate(paths):
        parts = p.replace("\\", "/").split("/")
        stem = re.sub(r"\.[a-z0-9]+$", "", parts[-1], flags=re.I)
        stem = re.sub(r"^\s*\d+\s*[-._) ]\s*", "", stem)          # "04 - Fishy fishy" -> "Fishy fishy"
        artist = parts[-3] if len(parts) >= 3 else ""
        # "100 gecs - mememe" -> "mememe" when the prefix is the folder's artist
        m = re.match(r"^(.{2,60}?)\s+-\s+(.+)$", stem)
        if m and norm(m.group(1)) and norm(m.group(1)) in norm(artist): stem = m.group(2)
        ids = (by_at.get(norm(artist) + "|" + norm(stem))
               or by_bare.get(norm(artist) + "|" + bare(stem)) or [])
        if not ids:
            for tbl, key in ((by_t, norm(stem)), (by_t, bare(stem))):
                t = tbl.get(key) or []
                if len(t) == 1: ids = t; break
                if len(t) > 1: amb += 1; break
        if len(ids) == 1: hit.append((ids[0], i))
        else: miss.append(p)
    print(f"{len(hit)} matched, {len(miss)} unmatched ({amb} ambiguous by title) of {len(paths)}")
    for p in miss[:10]: print("   no match:", p[-60:])
    if dry: return
    c.executemany("INSERT OR REPLACE INTO vectors(track_id, kind, pos, vec, model) VALUES(?,?,?,?,?)",
                  [(tid, "mean", 0, V[i].astype(np.float16).tobytes(), model) for tid, i in hit])
    c.commit()
    n = c.execute("SELECT COUNT(*) FROM vectors WHERE model=? AND kind='mean'", (model,)).fetchone()[0]
    print(f"{model} now has {n} mean vectors")

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3], dry="--dry" in sys.argv)
