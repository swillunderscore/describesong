"""Second pass for the seeder: match the paths the name pass could not place,
using DURATION (which the database records and the file knows) plus a loose
title overlap. Only accepts a match when exactly one candidate fits.
"""
import os, re, sys, sqlite3, subprocess, numpy as np
from concurrent.futures import ThreadPoolExecutor

def norm(x): return re.sub(r"[^a-z0-9]+", " ", (x or "").lower()).split()
def dur(p):
    try:
        out = subprocess.run(["ffprobe","-v","quiet","-show_entries","format=duration","-of","csv=p=0",p],
                             capture_output=True, timeout=30).stdout.decode().strip()
        return int(round(float(out)))
    except Exception: return None

def main(npz_path, db_path, model, tol=2, dry=False):
    d = np.load(npz_path, allow_pickle=True)
    paths = [str(p) for p in d["paths"]]; V = d["vectors"].astype(np.float32)
    # the trial ran when the project lived at ~/vibefind; point stale paths at
    # wherever the library is now, or every ffprobe silently returns nothing
    lib = os.environ.get("VIBEFIND_LIBRARY", os.path.expanduser("~/describesong/mulan-trial/library"))
    paths = [os.path.join(lib, p.split("/library/", 1)[1]) if "/library/" in p else p for p in paths]
    missing = sum(1 for p in paths if not os.path.exists(p))
    print(f"{len(paths)} paths, {missing} not on disk (library: {lib})")
    V /= np.linalg.norm(V, axis=1, keepdims=True) + 1e-9
    c = sqlite3.connect(db_path); c.row_factory = sqlite3.Row
    done_paths = set()
    have = {r[0] for r in c.execute("SELECT track_id FROM vectors WHERE model=? AND kind='mean'", (model,))}
    todo_tracks = [r for r in c.execute("SELECT id, artist, title, duration FROM tracks") if r["id"] not in have]
    print(f"{len(todo_tracks)} tracks still without a {model} vector")
    # only the paths whose vector is not already placed
    placed_rows = set()
    for r in c.execute("SELECT track_id FROM vectors WHERE model=? AND kind='mean'", (model,)): placed_rows.add(r[0])
    idx = [i for i in range(len(paths))]
    print(f"probing {len(idx)} files for duration…")
    with ThreadPoolExecutor(max_workers=16) as ex: durs = list(ex.map(lambda i: dur(paths[i]), idx))
    by_dur = {}
    for i, dd in zip(idx, durs):
        if dd: by_dur.setdefault(dd, []).append(i)
    hit, amb, nod = [], 0, 0
    for r in todo_tracks:
        if not r["duration"]: nod += 1; continue
        cands = [i for dd in range(r["duration"] - tol, r["duration"] + tol + 1) for i in by_dur.get(dd, [])]
        if not cands: continue
        # A duration match alone is not enough: a wrong vector makes a track
        # findable by the wrong description forever, which is worse than a
        # missing one. At least one title word must agree, always.
        want = set(norm(r["title"]))
        scored = [(len(want & set(norm(os.path.basename(paths[i])))), i) for i in cands]
        best = max(s for s, _ in scored)
        top = [i for s, i in scored if s == best]
        if best == 0 or len(top) != 1: amb += 1; continue
        hit.append((r["id"], top[0]))
    print(f"{len(hit)} matched by duration, {amb} ambiguous, {nod} with no duration")
    if dry: return
    c.executemany("INSERT OR REPLACE INTO vectors(track_id, kind, pos, vec, model) VALUES(?,?,?,?,?)",
                  [(tid, "mean", 0, V[i].astype(np.float16).tobytes(), model) for tid, i in hit])
    c.commit()
    print(f"{model} now has {c.execute('SELECT COUNT(*) FROM vectors WHERE model=? AND kind=\"mean\"', (model,)).fetchone()[0]} mean vectors")

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3], dry="--dry" in sys.argv)
