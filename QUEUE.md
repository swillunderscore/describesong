# describesong — queue (working name; rename is decision 3)

Describe a song in plain English; get back artist / title / album of songs
that sound like that, from a community-built database of audio embeddings.
No audio is ever uploaded or hosted. Only identities and 2 KB vectors.

## Decisions — resolved 2026-09-11

1. MODEL: CLAP `larger_clap_music_and_speech` fp16, fixed windows (10 s, one
   per ~30 s, up to 8, averaged; plus up to 4 per-moment vectors kept),
   pinned forever, model hash stored per vector. Measured against MuQ-MuLan:
   roughly a tie at the top, MuLan 9x the cost and 1.3 GB in-browser. See
   the comparison section.
2. HOSTING: the pi, in an arm64 container, behind Cloudflare Tunnel (already
   installed there for swillearth.io; this is a second hostname on it). Main
   PC is just another client. All vectors live on the pi.
3. NAME / DOMAIN: still open. Not blocking the build; blocks the public URL.
4. LICENSES: code AGPL-3.0, data ODbL. No accounts, no audio, no tracking.
   Attribution to MusicBrainz, AcoustID, LRCLIB.
5. ACOUSTID API KEY: still open — he registers at acoustid.org/new-application.
   Blocks only the identify step; everything else builds around it.
6. UNIDENTIFIABLE TRACKS: stored, unverified, with the file's tags; a
   confirmation prompt shows a prior label to the next submitter; labels
   normalised (case, punctuation, feat.) before counting agreement.
7. HOMESTEAD RE-EMBED with fixed windows: later, if the mixes disappoint.
8. LYRICS as the second signal: LRCLIB for identified tracks (server-side,
   embedding kept, text discarded), Whisper in the browser for unidentified.
   Plus hashed word-trigrams for exact-phrase lookup.
9. BROAD-SEARCH DETECTION: when top results bunch with no clear winner, say
   so and suggest adding an instrument, era or mood.

## Verified (2026-09-11)

- rusty-chromaprint -> WASM: 249 KB. Fed identical 11025 Hz mono PCM, it
  matches real fpcalc 948/948 frames, 100%. Fed 44.1 kHz and left to resample
  itself, 90% identical with ~1 bit of 32 differing — resampler only. So the
  browser resamples to 11025 Hz mono before fingerprinting.
- ONNX fp16 text tower (what the pi runs) vs PyTorch: cosine 1.00000,
  11 ms/query on desktop CPU. Browser audio tower (transformers.js fp16) vs
  PyTorch on the same 10 s window: cosine 0.99999. One space, end to end.
- transformers.js has ClapAudioModelWithProjection and
  ClapTextModelWithProjection for exactly Xenova/larger_clap_music_and_speech.
- CLAP audio tower expects 48 kHz, 10 s windows, and its default truncation is
  a RANDOM crop. Windows must be fixed and pre-cut by the client.
- AcoustID lookup works as documented; needs a registered client key.
- Navidrome-style streams are not involved anywhere; nothing here touches audio
  server-side.

## Retrieval test on his library (2026-09-11) — the model question REOPENED

Blind descriptions, no names, rank of the intended track out of the test library:
    SAN DIEGO VIP (dubstep)          2      Illmerica (electro house)   2
    Consolação (solo bossa guitar)   8      Jaded (lo-fi hip hop)       8
    a Kendrick track 8      Runnin' (90s rap instr.)   62-82
    Song For My Father (jazz-hop)  114      Frank Ocean-ish r&b        65
    BTSTU (falsetto lo-fi pop)     938      Khruangbin                231
    Blue Bossa (jazz guitar duo)   294
    Destructo – Higher: "heavy bassy dubstep 2010s" -> 67
                        "hard electro house, bass drop, chanted hook" -> 7
Reading: instrumental/timbral descriptions land top-10; vocal character and
loose genre words land 60-900. CLAP is literal about sound. On a million-track
DB these ranks scale up. MuQ-MuLan's documented gains are exactly on
text->music retrieval, and a model swap after launch means everyone
re-embeds — so the model should be chosen BEFORE launch by running THESE
SAME QUERIES through MuQ-MuLan on the same library. Decision 1 is reopened
pending that measurement.

Also: "confidence" is not a 0-1 scale. Cross-modal (text vs audio) cosines
top out around 0.5-0.65 by construction; what matters is rank and the gap to
the next result, and that is what the UI should show.

## CLAP vs MuQ-MuLan, measured (2026-09-11, RX 9060 XT, same 3 fixed windows)

Rank of the intended track out of the test library, 14 blind queries:
                          CLAP  MuLan                          CLAP  MuLan
    SAN DIEGO VIP            4      2     Song For My Father    87    241
    Illmerica                1      5     Frank Ocean-ish r&b  127    489
    Consolação               1     14     BTSTU (falsetto)     701    334
    Jaded (lo-fi)          110     48     Khruangbin           484     18
    Kendrick                 1      9     Blue Bossa           210     66
    Runnin'                106     25     Higher as "dubstep"   99    132
                                          Higher as "electro"   29      3
    median rank             93     30     Higher, vague "2012"  23     36
    top-10                4/14   4/14     embed time          280s  2505s
    top-50                6/14   9/14

Reading: MuLan lifts the middle (median 93 -> 30) and rescues loose/vocal
descriptions (Khruangbin 484 -> 18, Runnin' 106 -> 25) but regresses others
(Frank Ocean 127 -> 489, Song For My Father 87 -> 241) and top-10 is identical.
It costs 9x the compute and a 1.3 GB browser download against 143 MB.
Both fail the same class: vocal character. That is a TEXT problem — lyrics —
not an audio-model problem, and no audio model fixes it.

Also: this deterministic-window CLAP run beats the earlier random-window CLAP
vectors on several targets (Illmerica 2 -> 1, Kendrick 8 -> 1, Consolação
8 -> 1). Fixed windows matter. Evidence for homestead item 162.

DECISION 1 RESOLVED: CLAP fp16, fixed windows, pinned. Model hash stored per
vector. Lyrics (LRCLIB server-side; Whisper client-side for unidentified) are
the second signal and the one the data says to build. MuLan revisited only
if a browser build appears and the audio signal is the bottleneck, which
today it is not.

## Plan (build order; 1 is done)

1. [x] fingerprint-wasm/ — Chromaprint in the browser.
2. [x] web/ — one page. WRITTEN, not yet run in a browser. Search bar -> /search. "Add your music" -> folder
       picker (webkitdirectory; File System Access API where available) ->
       Web Worker: decode (Web Audio) -> resample 11025 mono -> fingerprint ->
       POST /identify -> resample 48 k mono -> DETERMINISTIC windows (10 s at
       20 / 50 / 80 % of the track, mean, L2-normalise) -> CLAP audio tower
       (transformers.js, WebGPU if present) -> POST /submit. Progress, and a
       plain statement that nothing but IDs and vectors leave the machine.
3. [x] server/ — FastAPI + SQLite + hnswlib/FAISS. /identify proxies AcoustID
       (rate-limited, cached) and fetches MusicBrainz metadata once per MBID.
       /submit validates model hash, unit norm, and consensus against other
       submissions for the same MBID. /search embeds the query with the CLAP
       TEXT tower (onnxruntime, CPU) and returns top-N with metadata. Index
       rebuilt incrementally.
4. [ ] Seed: homestead's library re-embedded THROUGH THE SAME CLIENT PATH so
       the seed is indistinguishable from user submissions.
5. [ ] Deploy per decision 2. Then leave it alone.

## Smoke test (2026-09-11, desktop, no AcoustID key yet)

Three real tracks pushed through the server by the exact protocol the browser
uses (fixed windows, fp16-equivalent vectors, WASM fingerprint): all three
searches returned their track at #1, confidence 100. Resubmitting the same
file merged into the same track (dedupe by fingerprint). The second identify
of that file returned the first submitter's label as `prior`, which is what
drives the "someone said this is X — correct?" prompt. A vector from a
different model was rejected with 400. Found and fixed: a 1-1 label tie was
resolved at random; ties now keep the earlier label and a newcomer needs
strictly more votes to take over.

## Landmines

- compare.py v1 decoded the entire library into RAM (the whole test library as float32 PCM)
  and filled memory and swap on the desktop. Stream in chunks; never hold
  more than one. The site's client must be built the same way: one file at a
  time, PCM discarded after embedding.
- This desktop's Python is 3.14 and PyTorch publishes no ROCm wheels for it,
  so `pip install torch --index-url .../rocm*` fails silently and pip falls
  back to a CUDA build that cannot see the RX 9060 XT. Use a 3.12 env (conda)
  for ROCm.

- One model variant, forever. fp16 vs fp32 vs quantized differ enough to
  break consensus.
- Deterministic windows, forever. Same reason.
- Chromaprint must see 11025 Hz mono, or fingerprints drift from fpcalc's.

### Landmine: WebGPU vs WASM embeddings differ (measured 2026-09-11)
Same 10 s window, same fp16 model, same transformers.js: browser WASM = Python at
cosine 1.00000; browser WebGPU = 0.988 (fp16 AND fp32 — it is the WebGPU kernels,
not precision). WebGPU users agree with each other at 0.99997. Two camps, 0.988
apart. Harmless for search (rank gaps are 0.05–0.2) and for consensus (keyed by
fingerprint, vectors averaged). DECISION (mine, overridable): WebGPU stays default
— 3× faster (390 ms vs 1163 ms per window). transformers.js pinned to 3.8.1 in
worker.js so a CDN bump cannot create a third camp.

### Deploy (Pi) — decided 2026-09-11
Name: describesong (describesong.com, RDAP-available; he registers). No image
build (32-bit dockerd + arm64 = SIGSYS): deps in /mnt/nvme/describesong/pylibs via
deploy/pi-install.sh, stock python:3.12-slim, systemd --user unit
deploy/describesong.service on 127.0.0.1:8095 (8090 is llama-server) (cap-drop ALL, read-only, 1.5 GB cap).
AcoustID key: /mnt/nvme/describesong/env (600). Cloudflare: token-managed tunnel,
so the public hostname is added in the Zero Trust dashboard (his account):
describesong.com -> http://localhost:8095.

### Client labels (added 2026-09-11)
Unidentified files are labelled from their own tags (ID3v2.2/2.3/2.4, FLAC Vorbis
comments) via readTags() in web/app.js; filename is the last resort. Verified on
4 real MP3s (artist/title/album correct). FLAC parser is UNTESTED on real files —
the test library is all MP3s, no FLACs. M4A/Ogg/Opus fall through to filename (v2).

### Confidence calibration (measured 2026-09-11, the test library x 14 queries + 5 obtuse words)
Absolute cosine is useless as confidence: "gay" scores top1 0.608, higher than
most true hits (0.51–0.64). What separates a real description from an obtuse
word is the top-minus-median GAP: specific queries 0.39–0.65 (median near 0),
obtuse words 0.21–0.26 (median ~0.35: everything matches "song" equally). One
genuine query ("dense conscious rap, urgent male vocals…") also gaps only 0.25
in this rap-heavy library — that IS "fits a lot of music here". Constants:
GAP_REF 0.55, BROAD_GAP 0.30, MIN_FOR_STATS 20, CAL_FLOOR 0.15. Old threshold
(0.03) never fired for anything.

### Scan speed (measured in-browser on the Pi service, 2026-09-11)
Per track: decode 0.16 s (112 s track) – 0.31 s (214 s track); worker
(fingerprint + 4–7 CLAP windows on WebGPU) 0.77–1.18 s. The "3 hours" I said
earlier was a guess, not a measurement — retracted. Scan loop is now pipelined
(next file decodes during embed; identify+submit overlap the next embed, max 4
in flight; confirm dialogs serialised), so the embed is the only serial cost.
Contact email: swillsoftware@proton.me (footer + legal.html).

### 2026-09-11 evening — redesign + resume + concurrency
- Design: "technicolor darkroom" — two OKLCH tones drift through hue over 240 s
  (his desktop recolours from the wallpaper; the site recolours from the clock).
  Fraunces + Azeret Mono, self-hosted in web/fonts (OFL; no third-party requests,
  legal.html promises none). Ko-fi is a gradient pill in the header. Results show
  a confidence bar per row. Shared style.css for index + legal.
- Folder picking uses showDirectoryPicker (prompt says "view files", not
  "upload") where it exists; <input webkitdirectory> elsewhere.
- Resume, two layers: localStorage (name+size+mtime) AND the server: identify
  returns known/submissions; a known+verified track skips the embed; a
  known+unverified one offers the file's tags as a label-only vote (submit with
  mean=null). Worker split into fingerprint / embed / drop so identify sits
  between them; stage A (decode+fp+identify) runs one file ahead of the GPU.
- Concurrency: per-request SQLite connections in WAL; 2 users x 40 overlapping
  submits on 20 shared recordings → 80 ok, 0 errors, 60 rows, 0.2 s. The real
  shared limit is AcoustID's 3 lookups/s per key → server-side token bucket,
  waits up to 6 s then falls back to tags (unverified) instead of failing.
- Server changes are LOCAL until his first scan finishes (restart would fail
  his in-flight requests); static files are live.

### Design, take 3 (2026-09-11, after "solid colors man")
His reference is the Homestead web app: SOLID tone panels (p/s pair), nested
rows a lighter tint of the same tone, dark ink everywhere, wallpaper only in
the gaps. Site now: header/side/footer = tone B, main = tone A, nested blocks
= color-mix(tone, white 22%), ink #15151a, rings for numbers, JetBrains Mono
(the bar's font). tones.js drifts the pair through hue (1.5°/s, phase from the
clock so every visitor sees the same pair) and paints the two deep tones as a
Bayer-dithered pixel sky on a fixed canvas — visible only in the gaps. body
background must stay transparent (an in-flow body background paints ABOVE a
z-index:-1 canvas; that was the "flat dark" bug). Takes 1 (serif/gradient) and
2 (glass/dark) were rejected as generic-AI — do not go back to them.

### 2026-09-11 late — width, font, water, sliders
- Layout is fluid (main fills the window, side column clamp(340px,27vw,520px)).
- Font is the visitor's system UI font (system-ui stack) — no bundled font.
- The site TITLE is the "describesong" wordmark block in the header (big,
  .brand); the h1 is the instruction and stays moderate. (He corrected me.)
- water.js: WebGL2 wave equation (RG16F ping-pong, viscosity term), refraction
  with dispersion + caustics of the pixel sky, drops from the pointer + light
  rain. Tiers off/low/mid/high (sim at 1/8, 1/4, 1/2 res). Auto tier measured
  on load (mean rAF interval vs display period over ~110 frames; 7.0 ms here →
  mid). PAUSED whenever a scan runs (root[data-scanning]) — CLAP gets the GPU.
- Corner block "🎨 colors": hue / sat / bright / water sliders, persisted in
  localStorage; ink flips to light below the desktop's luminance threshold.

### 2026-09-11 night — hyprwater ported (water.js v2)
Read from ~/.config/hypr/hyprwater/src (Shaders.hpp, GlassRenderer.cpp) and
ported: wavesim.frag verbatim (9-point Laplacian, viscosity l−lp, uneven bed,
sponge, soft clamp, DoG round taps + dipole strokes, chunked ambient impulses
in the 0.29–0.38 ring, seaEnergy tame), his time model (sim = real × speed,
1/120 s steps, SUB 1/2/4, interpolation between the two states), viscosity →
max-speed root (K 0.78), damping 0.9994, waveSpeed √depth, the band-limited
smooth copy (two 2x blits + gaussian σ = clamp(95√causticK, 3, 24)) for the
warp with the p=4 soft limiter, causticsplat.vert/frag forward splat + blur
r = clamp(lensK·30, 2.1, 12), the additive caustic branch, absorption + murk,
mouse wake (0.014 s sampling, stroke push at 0.009, cap 0.012·mouse) and click
tap. Defaults = his hyprwater-tuning.conf values. Sliders: quality (auto/off/
low/mid/high → sim 384/640/1024), brightness, depth, speed (log), activity,
viscosity, water colour, murk, mouse wake, scale; all persisted.
NOT ported (say so if asked): Stable-Fluids currents (the 4 fluid passes and
velocity advection), window physics / layers (no windows on a web page),
light_from_backdrop branch, lens/fresnel/specular/blur of the glass windows
(the site has no glass windows; the water is the whole backdrop).
Verified: no GL errors, mid tier at 7.0 ms/frame; at speed 1.0 the caustic
veins and warp are unmistakably hyprwater; at his 0.019 it is a near-still
pool, as on his desktop.
Colours box: header toggles (was un-closable); "Hue shifts over time" checkbox,
off → the hue slider is the static colour. Random example placeholder per load.
All copy sentence case; wordmark "Describesong".

### 2026-09-11 late night — app layout, bar-mounted settings, repo
- main is min-height 100vh with rows auto/1fr/auto: the sidebar stretches to
  the bottom (support block pinned at its foot: "No ads. No tracking." + Ko-fi),
  the bottom bar is always at the bottom. No empty wallpaper below content.
- Water/sky stay FIXED behind the page while content scrolls — the desktop rule
  ("a moving window slides across standing water"). No infinite water; the
  results are capped at 30 so the page is never long anyway.
- Colours & water box is a block IN the bottom bar; opens upward; click
  outside closes it. Water freezes on hidden tab, window blur, or a scan.
- His slider values live in HIS browser's localStorage — never reset them
  again from a test tab (a depth reset to 3.69 may have clobbered his choice).
- Repo: git initialised, AGPL-3.0 LICENSE, README, .gitignore (data, models,
  library, venvs, wasm build dirs). Footer links github.com/swillunderscore/
  describesong — HE creates the repo (publishing is his action):
    gh repo create swillunderscore/describesong --public --source ~/describesong --push
- Ads: none; recommendation stays no ads (the support block is the gesture).

### LIVE — 2026-09-11 (night)
describesong.com (+ www) → Cloudflare tunnel "raspberry-pi" → HTTP localhost:8095
on the Pi, as a "published application route" (the new dashboard name for
public hostnames; "Hostname routes" is the WARP/private thing and stays empty).
Cloudflare terminates TLS; the tunnel to the Pi is its own encrypted link; the
service is plain HTTP on localhost, like swillearth's nginx on :80. No nginx
needed here: one process serves page + API, and no COOP/COEP.
Verified from outside: index, wasm (application/wasm), worker, legal all 200;
search through the tunnel (#1 Wolfgang Gartner 92%); the rate limiter records
the real client IP (CF-Connecting-IP), not the tunnel's.
Repo public: github.com/swillunderscore/describesong (he created it; I push).
Gotcha: a resolver that looked the name up BEFORE the record existed caches
the miss for a while (his PC's systemd-resolved did) — resolvectl flush-caches.

### Scaling the search index (decision, 2026-09-12)
Today: means as float32 in RAM, brute force (M @ q). Fine to ~500k tracks
(2 KB/track, container cap 1.5 GB, ~0.2 s/search). The "400 GB RAM for every
song ever" figure is ONLY for that naive layout — it is not what large vector
search does. Plan, in order, each a bounded change with no data migration
(the vectors are already on disk in SQLite):
  1. ~300k tracks: faiss IVF-PQ (64-byte codes) → ~100 MB RAM per 1M tracks,
     millisecond search; exact re-rank of the top 200 from the fp16 rows.
     REQUIREMENTS (his, 2026-09-12): (a) the rebuild is AUTOMATIC and
     event-driven — no timer, no cron: when tracks added since the last build
     exceed 10% of the built size (min 20k), the server retrains and rebuilds
     in a background thread at low priority and swaps the new index in
     atomically; searches keep answering from the old one meanwhile. Nothing
     to tend. (b) The slow second pass: after the fast approximate answer, an
     exact scan of everything runs at low priority (only while no other search
     is waiting) and refines the list under a small spinner — this is what
     catches a track the clustering fits badly, independent of (a).
     Until then: today's index is exact and updates on every insert, so there
     is nothing to compact or rebuild.
  2. ~10M: IVF lists on disk (faiss OnDiskInvertedLists) or DiskANN — RAM
     stays ~1–2 GB regardless of size; disk ≈ 2–3 KB/track (drop moments).
  3. 100M+: the Pi's 611 GB holds ~200M at that size; RAM still ~2 GB.
Key-lookup databases (his earth game's trillions of rows) don't apply: they
find rows BY KEY via a B-tree. Similarity search has no key — every query must
compare against everything, so it needs the special indexes above.
SEO 2026-09-12: title with the query phrase, meta description, canonical, OG/
twitter cards, favicon, robots.txt, sitemap.xml. What actually ranks a
brand-new domain is links (r/tipofmytongue etc.) — his move.

### 2026-09-12 — asks
- Colours box lives in the HEADER now (opens downward), called "Colors";
  Ko-fi block says "Make it faster →". Sidebar links legal.html#scale, which
  tells the scale story honestly ("exact to ~500k, very-nearly-exact after,
  under a second at 200M; memory pushes the exact line out") — kept OFF the
  front page so nobody reads a limit into a 600-track index.
- FUTURE (with the approximate index, step 1 of the scaling plan): answer fast
  from the index, then keep an exact re-scan running in the background at low
  priority (only while no other search is waiting), refining the list in place
  under a small spinner. Not built; nothing to build until ~300k tracks.
- Boot: describesong is a systemd --user unit, enabled, Restart=always,
  linger on; docker and cloudflared are system services. Verified below.

### Scrub (2026-09-12)
Public repo scanned for identifiers. Found and removed: the Pi's user@LAN
address as sync.sh's default (now PI= must be given), and 35 "/home/<user>/"
cargo-registry paths in the wasm's panic strings (byte-patched to
"/home/user/", same length — code sections and fingerprints proven identical;
a full rebuild produced different code sections, so it was NOT used). The
only email is the project address on purpose. Old commits still hold the old
strings until he squashes history (his force-push).

### Rebuild banner (spec, 2026-09-12 — build with scaling step 1)
When a rebuild runs, the page shows one line at the top, pushed over the
existing /api/events stream (no polling): what is happening, why, and a
finish estimate from the measured rate ("Reorganising the index — 1.2M tracks
outgrew the fast path. About 4 min left."). When it finishes the line becomes
a short notice for a while ("Index rebuilt: 1.2M tracks. Searches are exact
again for now.") and then goes away. Concise; no jargon; nothing modal. Both
messages may carry the one honest link to legal.html#scale — a rebuild means
the site got popular and the Pi is at its limit, which is the coffee case.


### BUILT 2026-09-12 — the index looks after itself (server/vindex.py)
- Exact float32 matmul while n ≤ 150k. Beyond: faiss IVF-PQ (64-byte codes,
  nlist = 2√n clamped 256..2048, nprobe = nlist/8 ≥ 32), 1000 candidates
  re-ranked EXACTLY from the fp16 memmap (vectors.f16, row i = ids[i]). The
  library median for confidence comes from a fixed 5k-vector sample.
- Rebuild = automatic, event-driven: added_since_build > max(20k, 10% of
  built) → background thread (faiss on 2 threads), trains on ≤120k rows, adds
  in 20k chunks, publishes progress over /api/events, swaps atomically, saves
  index.faiss + index.json so restarts don't retrain (rows added after the
  save are inserted incrementally). Until the first build lands the server
  answers by exact chunked scan of the memmap ("scan" mode).
- Slow second pass: GET /api/search?exact=1 scans every row in 50k chunks and
  yields (503 "busy") whenever a normal search is in flight. The page calls it
  after any answer with exact:false and refines the list under a spinner.
- Banner: rebuild running (progress + ETA) → "Index rebuilt: N tracks" for
  90 s → gone. Failure shows for 60 s and searching continues on the old index.
- Measured: local 300k realistic set (real CLAP seeds perturbed, 22 real text
  queries): recall@10 vs exact 0.995 (min 0.9), IVF search 4 ms median, exact
  scan 0.26 s, rebuild on +12% fired. First attempt (4√n lists, 24 probes,
  heavy-noise synthetic data) measured 0.17 — the data was structureless and
  the probes too few; both fixed. Startup loader streams rows (a million bytes
  objects at once would have blown the 1.5 GB cap).
- Pi proof at 600k inside the capped container: see the line below.
- PI PROOF (600k realistic vectors, 2026-09-12): load 18 s, first build 108 s,
  IVF search 8.0 ms median / 27 ms p95, exact scan 0.78 s, recall@10 vs exact
  0.991 (min 0.9), +12% growth → rebuild fired, 149 s. Bench RSS 1.0 GB steady
  (600 MB of it the memmap = reclaimable page cache), 1.9 GB peak during the
  growth rebuild WITH the generator's own arrays.
- CAVEAT found by the run: "kernel does not support memory limit capabilities"
  — this Pi's kernel has no cgroup memory controller, so the unit's --memory
  1500m is NOT enforced (never was). Enabling it needs `cgroup_enable=memory
  cgroup_memory=1` in /boot/firmware/cmdline.txt + reboot — his call. Memory
  today: ~0.5 GB resident + 64 MB per million tracks of codes; the vectors
  themselves live in page cache.

### BUILT 2026-09-12 — words first (decision 8 delivered), names search
- lyrics.py: for every track with artist+title the Pi asks LRCLIB (free, no
  key, UA identifies us) for lyrics, picks the result nearest in duration
  (±12 s), hashes word-TRIGRAMS (sha1 → 63-bit ints), stores the hashes in
  lyric_grams, discards the text. tracks.lyrics_state: none/found/missing/
  instrumental. One worker thread, 4 req/s, fed by submits + a startup
  catch-up of every 'none'. legal.html updated (word hashes are listed as a
  thing kept; lyrics text is not).
- tracks_fts (FTS5, contentless) over artist/title/album, rebuilt when counts
  drift; a name match requires EVERY query word of 3+ letters.
- Search: on page 1, lyric matches (≥34% of the query's trigrams, or any hit
  for ≤5-word queries) and name matches LEAD, marked via="lyrics"/"name"
  (badges "matched the words" / "matched the name"); the sound ranking
  follows. Measured locally on 6 real tracks: LRCLIB found 3/6; 4-word runs
  from real lyrics find their track — see the test line below.
- MuLan record, corrected: the earlier test measured MuQ-MuLan median rank 30
  vs CLAP 93 and top-50 9/14 vs 6/14 (top-10 tied 4/14). I framed that as a
  tie and leaned on the cost (9× compute, 1.3 GB download); it was not a tie.
  He is right. Decision on MuLan is his; it would mean an ONNX export, a
  re-scan of every track, and desktop-only scanning.

### Measured 2026-09-12 — LLM in the search path: NO (on this Pi)
- Qwen2.5-1.5B (homestead's llama-server, CPU) extracts facts correctly with
  a JSON grammar but takes ~90 s per query (1.4 tok/s; prompt eval 30-40 s).
  Facts now come from server/facts.py — patterns, microseconds, copies only
  what the text says (years, decades ±, early/mid/late, instrumental / no
  vocals, male/female vocals, nationality → ISO country).
- Caption rewrite by the same model, measured on 12 real queries against the
  real index: median rank 60 vs 85 raw, top-10 tied 3/12, swings both ways
  (Eple 309→52 and 721→44, but 290→1102; BTSTU 415→1311; Consola 4→81);
  max(raw, caption) median 87. A coin flip, not a feature. Not built.
- "I need to know" queued deep search: fine idea, nothing measured that it
  would run yet. Parked.
- Fewer windows per track measured worse than the all-window mean (median
  134-175 vs 78). Averaging the whole track stays.

### BUILT 2026-09-12 — quotes insist; facts from the file's own tags; mobile header
- Lyric BIGRAM hashes stored alongside trigrams (lyric_bigrams); tracks found
  before the table existed are re-fetched once at startup. A phrase in
  "quotes" must be present (all its bigrams, or trigrams for 3+ words); the
  matches lead, ordered by how the REST of the sentence sounds ("says 'oh
  yeah' a bunch, female vocals" = tracks containing "oh yeah", ranked by the
  sound of "female vocals"). No match → quoted_miss → the page says so and
  shows the closest sounds. Single quoted words are ignored (no unigram index).
- track_facts(track_id, year, genres, country, source): the client now reads
  year (TYER/TDRC/TDRL/TYE, FLAC DATE) and genre (TCON/TCO, FLAC GENRE) from
  the file and sends them; stored with source='tags' unless MusicBrainz facts
  already exist for the track. MusicBrainz facts (year/genres/country) are the
  next step, pending the filter measurement.
- Header stats show on mobile again (smaller blocks; the coffee block drops
  its caption line).
- Rewrite, attempt 2 (few-shot, "leave caption-shaped queries alone", prompt
  cached): the captions are now GOOD (Consola untouched, "sad piano thing" →
  "slow, melancholic solo piano piece") and it still does nothing for rank:
  median 114 vs 85 raw, top-10 3/12 both, top-30 4/12 both. Latency with the
  cache: 22-35 s per query (prompt eval alone 12-15 s on this CPU). Dead.
  Conclusion: the sentence is not the problem; the space is. Words (names,
  lyrics) and facts (year, vocals, country) are the levers left.

### BUILT 2026-09-12 — precision on demand (no model)
- Field syntax in the box: artist:/by:, title:/song:, album:, lyrics:/words:,
  year:, country:, from: (year or country by its value), sound:. Values end at
  a closing quote or the first comma; the rest is free text. Labelled names go
  through FTS on THAT column and lead as "matched the name"; lyrics: behaves
  like quotes; year:/country: and stated facts in plain words (facts.parse)
  FILTER the sound results — tracks with unknown facts are never excluded;
  "instrumental"/"no vocals" excludes tracks whose lyrics were found.
- Negated phrases ("not microwave beepy", "without drums") are dropped from
  the sound query: the text tower cannot negate, and including them pulls in
  what the person is ruling out.
- Client-side query model: rejected. A 0.5B LLM is a 300-500 MB download for
  a search box, and the labelled-field syntax gives the precision he asked for
  at zero cost; the ambiguity (chicago the title / artist / place) is resolved
  by the label when it matters and tolerable when it doesn't.
- Verified locally on real tracks: artist:, title:, by:, lyrics:, year:, from:,
  negation, instrumental all behave; no tracebacks.

### BUILT 2026-09-12 — time and place (measured first: Eple 309→64 with "early 2000s", 164→36 with "instrumental")
- mbfacts.py: MusicBrainz worker, 1 req/s, recording → first release year +
  genre tags + artist ids; artist → country (cached in `artists`). Queued on
  submit for identified tracks; startup catch-up for tracks without facts.
- facts.py: script_of() (latin/cyrillic/greek/cjk/kana/hangul/arabic/hebrew/
  thai/devanagari) and lang_hints() (ø/å/ö/ñ/ł… → candidate countries) from
  artist+title, for EVERY track, no network; stored in track_facts.
- Filters: a known country decides; unknown country is excluded only by a
  non-Latin script that contradicts (a Cyrillic name when "norwegian" was
  asked; a Latin name when "japanese" was asked is NOT excluded — romanised
  names exist). Letter hints never exclude (Röyksopp's ö is not Norwegian).
  Year: unknown never excluded. Instrumental: excludes tracks whose lyrics
  were found (LRCLIB mismatches can wrongly exclude an instrumental — known).
- Results show "year · country" when known.
- One-time load: the 1,989 MusicBrainz facts fetched for the measurement go
  into the Pi's track_facts (years, genres) immediately; the worker then fills
  countries (~45 min of polite requests).

### Measured 2026-09-12 — captions (LP-MusicCaps, all 2,286 test tracks, 3 windows each)
Same 12 queries, rank of the intended track: CLAP median 96 (top-10 4/12);
captions alone via BM25 median 152 (top-10 0), via MiniLM sentence
embedding median 173 (top-10 2); fusion CLAP+MiniLM median 61 (top-10 1,
top-30 4); fusion of all three median 75 (top-10 1, top-30 5). Fusion helps
the tail (Khruangbin 595→46, Blue Bossa 210→78, Higher 29→11) and hurts the
head (SAN DIEGO VIP 4→31, Kendrick 2→12, Consola 1→28). The model also
contradicts itself across windows (male/female vocal on the same track).
Verdict: NOT worth a browser export (~900 MB, days, uncertain) at this
quality. Parked. If revisited: only as a soft signal for concrete "menu"
words (claps, whistling, vocal gender), never as a ranker. The captioner is
CC-BY-NC, which would also need a decision.
Facts tie note: "early 2000s … no vocals" ranks a known-2002 track and a
known-instrumental track equally (each satisfies one stated fact); sound
breaks the tie. Eple's own facts arrive when the MusicBrainz worker reaches
it (it was past the cut of the measurement cache).
- Year source corrected (2026-09-12): AcoustID matched Eple to the recording
  id on a 2018 compilation, so "first release" said 2018. The worker now also
  asks MusicBrainz for the earliest release year of any recording of that
  title by that artist and takes the minimum. A contradicting year DEMOTES a
  track below the unknowns instead of dropping it; a contradicting known
  country or script still drops.

### Measured 2026-09-12 — "contains X" (captions vs CLAP, AudioSet referee)
Referee: AST (527 AudioSet classes) over all 2,286 test tracks, three windows,
max per class; positives = the referee's top 3 % per class. Average precision
/ P@10, CLAP vs captions (BM25+MiniLM) vs fused:
  instruments — CLAP wins clearly: acoustic guitar .58/.28, piano .63/.24,
  trumpet .35/.12, violin .21/.09, drum machine .24/.04.
  captions win: rapping .16/.04 (CLAP's "rapping" is nearly blind), bass
  guitar .12/.06; saxophone about even, fused best at P@10 .70.
  vocal gender: both poor (female .09/.09, male .11/.05).
  hand claps, whistling, harmonica, beatboxing, church bells: the referee is
  too unsure inside full mixes (97th-percentile prob ≤ 0.006) — UNMEASURED,
  and no better referee is at hand.
  means: AP .23 CLAP / .13 captions / .20 fused; P@10 .40 / .27 / .44.
Verdict: captions add on a few categories and lose on most; fusion is a wash;
the one question that motivated this (claps, whistling) cannot be settled
with any referee we have. Parked for good unless labelled data appears. The
ONE thing worth keeping from it: CLAP is nearly blind to "rapping" as a
query word — worth a vocabulary note in "what the index hears" and maybe a
rap-specific phrasing hint ("male rap vocals over a hip hop beat" scored far
better than "rapping" in earlier tests).

### Measured 2026-09-12 — HIS labels (115 clips, the referee that matters)
Precision of each system's claims, judged by him (song-level; unsure excluded):
  hand claps        CLAP 0/14 = 0%    captions 7/11 = 64%   AudioSet-AST 7/8 = 88%   random 50%
  whistling         CLAP 1/13 = 8%    captions claimed NONE  AudioSet-AST 8/8 = 100%  random 0%
  female lead vocal CLAP 12/12 = 100% captions 8/13 = 62%   AudioSet-AST 5/6 = 83%   random 33%
Reading: CLAP is excellent on vocal gender and BLIND to concrete sound
events; the caption model is mediocre everywhere and never even mentions
whistling; the AudioSet classifier is the one that hears events. DECISION:
no captions. Add an EVENT TAGGER at scan time — the same AudioSet model, which
already exists for the browser (Xenova/ast-finetuned-audioset-10-10-0.4593,
transformers.js) — storing (class, probability) per track for a curated set
of searchable events (claps, whistling, saxophone, harmonica, beatboxing,
church bells, crowd, applause, laughter, …). Query words map to classes and
act as facts (filter / tier), like year and country. ~50 B per track.

### BUILT 2026-09-12 — sound events (the tagger his labels chose)
- web/events.json: 91 AudioSet classes worth searching (claps, whistling,
  applause, cheering, laughter, beatboxing, chant, choir, rapping, male/female
  singing, ~40 instruments, bells, rain, thunder, sirens, speech, distortion,
  echo…) and 148 words people type for them.
- worker.js runs Xenova/ast-finetuned-audioset-10-10-0.4593 (fp16 on WebGPU,
  q8/WASM fallback) on the same windows as CLAP, 48→16 kHz by a 3-tap
  low-pass + decimation, sigmoid per class, max over windows, kept ≥ 0.05.
- Scan flow: new track → events + embed + submit; known track WITHOUT events
  → events only (mean null) — so re-picking the folder backfills the library
  at ~0.5 s/track; known WITH events → skipped as before. DONE_KEY bumped to
  v2 so old "finished" memories don't hide files from the backfill.
- Server: track_events(track_id, cls, prob); identify returns has_events;
  submit validates against the class list; search maps words → classes and
  ranks tracks known to have the sound (prob ≥ 0.15) first — absence never
  excludes; describe returns the heard events as chips ("Heard in the
  track"), before the CLAP words.
- Verified in the browser against a scratch server: "Island Spell" → Whistling
  0.34 (his label: yes); Kendrick "Bitch, Don't Kill My Vibe" → Rapping 0.32,
  Speech, and NO clapping (he labelled claps yes; the tagger's recall on that
  track is nil — precision was what we measured). 16 s for two tracks incl.
  model load. No console errors.

### FIXED 2026-09-12 — the first library re-scan (42 tracks in 14 min, ✗ and =)
- Bug 1: the tagger was loaded once PER CALL. The scan runs several tracks
  at once, so a fresh worker started four 174 MB model instantiations side
  by side; most failed, each ✗ took ~20 s, and events.json was re-fetched
  for every track (the 304 flood in the Pi log). Now one shared load, a
  ladder (fp16 WebGPU → q8 WASM), and a spent ladder fails fast.
- Bug 2: a known track whose file tags matched the stored label returned
  before submitting — "already in, same label" — so its tagged sounds were
  thrown away. Now submitted when there is anything to submit.
- Bug 3: the 48→16 kHz step was a 3-tap average (aliasing). Now a 33-tap
  windowed-sinc low-pass. Verified against the PyTorch reference model on
  the same file: Guitar 0.11 / 0.11, Singing 0.10 / 0.11, Speech 0.07 / 0.05;
  fp16 WebGPU, fp32 WebGPU and q8 WASM agree within 0.02 (in-page test).
- "Guitar" and "Singing" were missing from the class list. Added (93 now).
- The ✗ line now names the stage ("sounds not tagged — …"); the finish line
  counts "N without sounds". DONE memory bumped to v3 so files the broken
  scan marked finished are looked at again.
- Water: an opaque canvas switched on while paused for a scan (or resized
  while paused) had never been drawn → black. A frame is always drawn before
  it is trusted; a lost GL context hides the canvas and rebuilds on restore.
- Throughput after the fix, scratch server: four known tracks in 5 s.

### FIXED 2026-09-12 — "scandinavian artist lofi electronic staccato 2000s" put Madlib above Eple
- Two causes, both measured on a copy of the live index (Eple outside the
  top 100 before; #1 after, for that query and for "norwegian duo early
  2000s plucky staccato beepy"):
  1. "scandinavian" was not a word the fact parser knew (single
     nationalities only), so only "2000s" applied. facts.REGIONS now maps
     region words to sets of countries (scandinavian/nordic, baltic,
     benelux, iberian, balkan, latin american, east asian, west african,
     caribbean, middle eastern, british isles); a stated country is always
     a set. Not "uk"/"usa": "uk garage" is a genre, and a stated country
     DROPS tracks that contradict it.
  2. Facts were applied AFTER retrieval, to the 400 nearest by sound. A track
     the facts fit but the sound model ranks 500th was never in the pool.
     Now every track KNOWN to fit all stated facts joins the pool (scored
     exactly from the memmap, capped at 20k), then the tiering sorts.
- Why verified tracks sit above unverified ones whenever a year or country
  is stated: the 287 unverified tracks have no MusicBrainz identity, so no
  year or country, so they can never be KNOWN to match. That is the design
  (unknown ranks below known-matching, above contradicting). Open option:
  look up unverified artists by name on MusicBrainz for a country.
- Scan client now retries through a server restart (connection refused,
  502/503/504) instead of marking the file failed.

### BUILT 2026-09-12 — places, "is", names for unidentified tracks, empty-tag sentinel
- server/places.py: 186 countries with name aliases, demonyms, continent,
  sub-region, languages, extra groups. Every place word is DERIVED from it:
  79 group adjectives for free text (nordic, western, west african,
  spanish-speaking, balkan, post-soviet, mediterranean…) and 55 noun forms
  for "from X" / "country is X" (west africa, the middle east, scandinavia).
  Country names never match in free text (Chad, Jordan, Georgia, Turkey).
  Longest match first ("south african" before "african").
- "artist is kendrick", "country is norway", "the singer is billie eilish":
  same as the colon syntax; a value runs to the next comma. Also
  band/singer as artist fields, and bare "from norway" / "from the
  netherlands" in free text.
- Unidentified tracks (287) now get a country by ARTIST NAME on MusicBrainz
  (exact normalised name match with search score ≥ 90, first artist of a
  credit list) and a year by artist+title recording search. Source
  "musicbrainz-name". A wrong country drops the track from every search
  that states one, hence the strictness. Queued at startup and on submit.
- A tagger that heard nothing stores a sentinel row, so the track is not
  re-tagged on every re-scan; files whose tagging or submit FAILED are no
  longer remembered as done, so the next pick retries them.
- Decided without asking (say if wrong): "western" = W/N/S Europe + US CA
  AU NZ; "scandinavian" includes FI IS FO; "middle eastern" excludes the
  Caucasus and the Maghreb, includes EG; "latin american" includes the
  Spanish/Portuguese/French Caribbean; a stated place still DROPS tracks
  whose known country contradicts it.

### BUILT 2026-09-12 — before friends scan: AcoustID id as backup identity, MusicBrainz errors retried
- tracks.acoustid: AcoustID's own id for the recording (a fuzzy match), taken
  when the top lookup result scores ≥ 0.9, with or without a MusicBrainz
  link. Identify falls back to it when the exact fingerprint hash is unknown,
  so two rips of one unidentified song become one track; the client submits
  under the canonical fp_hash the server hands back. 0.9 not 0.5: a sample
  can share enough of a fingerprint with its source, and merging a sample
  into its original is the worse error (his call: "backup, not primary").
- mbfacts: a MusicBrainz network/5xx failure is stored as *-error and retried
  at the next start; a real miss stays a miss. The "verified but no country"
  re-check now runs at most every 30 days instead of at every restart (219
  tracks × 3 requests before anything new got looked up).
- Pipeline audit on the live index, 2,276 tracks: vectors 2,276, name index
  2,276, sounds 2,251 (25 heard nothing / failed before the sentinel), lyrics
  found 1,304 + instrumental 257 + not on LRCLIB 715, year 1,983, country
  1,770 (+ the 287 name lookups in flight).

### BUILT 2026-09-12 — covers and 30-second previews on every result
- server/media.py: by name, from the two public catalogue APIs made for this
  (a link back to the store is the price): Apple's iTunes Search API first
  (no key, stable preview URLs, 600 px art, ~20 requests/min), Deezer second
  (no key; preview URLs expire, so the track id is stored and a fresh URL is
  fetched at play time via /api/play/{id}). A match needs the same artist and
  title (normalised, parentheticals dropped) and a duration within 6 s.
  media(track_id, source, ext_id, preview, cover, link, state, fetched).
  One paced worker; catch-up at start (2,276 tracks ≈ 2 h); new tracks on
  submit; errors retried on the next submission; circuit breaker as facts.
- Results carry cover + play; the cover IS the play button (triangle on
  hover, bars while playing, a thin progress line, "on Apple Music" /
  "on Deezer" link while it plays). One <audio> for the page, kept in the
  document — Chrome aborts play() on a detached element (measured: AbortError).
  No preview → the cover alone; nothing known → a solid block, so rows align.
- Why not YouTube: the official embed needs a video id, the Data API allows
  100 searches a day, and scraping search is against their terms. Previews
  are the above-board version of the same button. Verified in the browser:
  a real click plays Apple's preview (3.9 s in after 4 s, 30 s long).
- Decided without asking (say if wrong): Apple before Deezer; 6 s duration
  tolerance; 54 px cover; placeholder blocks for rows without art.

### MEASURED 2026-09-12 — can a store's 30-second preview stand in for a full scan?
- 60 random tracks with both an Apple preview and a full-scan vector. The
  preview embedded as three 10 s windows (all of it) with CLAP (PyTorch fp32,
  same weights), compared to the stored full-scan mean (8 windows across the
  song). Script: scratchpad/measure_preview.py.
- cosine preview vs full scan: median 0.903, min 0.430. For scale, a track's
  nearest OTHER track in the index sits at median 0.879 — a preview is about
  as close to its own song as the closest different song is.
- queried by the preview vector, the song's own full vector ranks #1 47 %,
  top-3 80 %, top-10 87 %, median rank 2. The misses are songs whose 30 s
  slice is not the song (SMUCKERS rank 327, Young Blood 216, Wajatta 14).
- Verdict: a preview-derived vector is a usable stand-in for ~4 in 5 songs
  and a wrong one for ~1 in 8. If previews ever seed the index they need
  their own tier ("from a 30-second preview"), replaced by any full scan.
  You cannot choose which 30 s a store serves; Apple and Deezer may serve
  different slices, so two stores could give ~60 s. Not measured.
- FLAC: verified end to end in the browser (decode, Vorbis-comment tags,
  fingerprint, embed, submit — 3 s). mp3/flac/wav/m4a/ogg/opus accepted.

### MEASURED 2026-09-12 — his friend's track, CLAP vs MuLan (cached trial vectors, same 2,286 tracks)
Where "Fishy fishy" lands. NOTE: these queries are MY RECONSTRUCTION of his
search, not his search — I cannot see what he types. Built from the words
/api/describe/1332 returns (what the "what the index hears" box shows for the
track) because he said he typed the top terms from it. Only "all these fishes"
came from him, quoted in his own message. Both models got identical queries,
so the gap is real whoever phrased them.

| query                                                | CLAP | MuLan |
|------------------------------------------------------|------|-------|
| grungy lo-fi trip hop beat                           |  297 |    23 |
| trip hop sample-based beat neo soul lo-fi hip hop *  | 1280 |    10 |
| dusty sample-based beat with a spoken word sample    |  643 |     1 |
| kids voice sample lofi hip hop                       |  807 |     4 |
| speech sample over a lofi beat                       |  105 |    31 |
| sesame street sample                                 | 2255 |   140 |
| grunge                                               |  561 |  1619 |
| **median over 10 queries**                           |**429**| **27** |

* these six words are exactly what /api/describe returns for the track, i.e.
  what the box would have shown him — not necessarily the order he typed.
- Neither model knows "grunge" as a texture; MuLan is worse on that one word
  and better on every phrase. CLAP is not broken, it is trained on general
  audio-caption pairs (AudioSet-scale) where "grunge" is 90s rock; MuLan is
  trained on music with music descriptions.
- COST of MuLan in the browser: 663M params = 1.3 GB fp16 / ~660 MB int8,
  against CLAP's ~200 MB. transformers.js has no MuQ support, so it needs a
  hand-written ONNX Runtime Web path. Not a config change.

### MEASURED 2026-09-12 — can the browser transcribe lyrics itself?
10 tracks that DO have LRCLIB lyrics; transcribe locally, hash trigrams the
same way lyrics.py does, measure overlap with the real ones.

| model            | median overlap | min | max | s/track (2060-class GPU) |
|------------------|----------------|-----|-----|--------------------------|
| whisper-base     | 14 %           | 0 % | 47 %| 3.3 |
| whisper-small    | 26 %           | 0 % | 53 %| 4.4 |

- Two tracks at 0 % both times: sung-through with heavy backing. Whisper is
  a speech model; singing over music is its worst case.
- NO ACCOUNTS AND NO LYRIC UPLOADS NEEDED, whatever we decide: the index has
  only ever stored hashed trigrams, never text (server/lyrics.py). A browser
  transcription would submit the same hashes LRCLIB-derived ones use. His
  worry about users uploading lyrics is already designed out.
- Where it would actually pay: the 715 tracks LRCLIB does not have, which
  today are unfindable by words at all. Would need its own tier ("heard, not
  looked up") so a transcription never outranks real lyrics.

### BUILT 2026-09-12 — MuLan's audio tower exported to ONNX. It works.
Scratch: scratchpad/onnx/ (export_audio.py, cut3.py, endtoend.py).

- ONLY THE AUDIO HALF SHIPS. MuLan is two towers: audio 334M, text 328M. The
  browser needs the audio one; the text tower runs on the Pi, once per query,
  not once per track. That halves the download before anything else.
- torch.onnx.export (dynamo) traced it first try, opset 18, 816 nodes, 28
  distinct ops, all standard. **cosine vs PyTorch: 1.000000, max abs diff 8e-08.**
- One blocker: node 5 is STFT, which ONNX Runtime Web has no kernel for. Cut
  the graph after it, so the model takes the spectrogram and the browser makes
  it (n_fft 2048, hop 240, periodic Hann, reflect-padded 1024 each side — all
  read out of the graph's own initialisers, not guessed). A shape vector the
  tail still wanted is baked in as a constant. Remaining risky ops: NONE.
- END TO END, on real audio: numpy STFT -> cut ONNX model vs PyTorch
  mulan(wavs=...) = **cosine 1.0**, on random noise and on Fishy fishy itself.
- SIZE: fp32 1212 MB / fp16 638 MB (cosine 0.999999) / int8 321 MB (cosine
  0.887 — too lossy, needs per-layer mixed precision, not a blanket pass).
  fp16 is the shipping candidate; CLAP's browser download is ~200 MB.
- HARDWARE: ONNX Runtime Web targets WebGPU, a browser API, not a vendor SDK.
  His ROCm card, NVIDIA, Intel and integrated all take the same path, with
  WASM as the fallback everywhere. Nothing here is CUDA-only.
- STILL TO DO: the JS spectrogram (~40 lines, FFT over 1001 frames), ORT Web
  wired into worker.js, a second vector kind in the DB + a MuLan text encoder
  on the Pi, and a decision about the 638 MB download.

### BUILT 2026-09-12 — results say what can find a track, not "unverified"
- Five pips per row: name, words, year, country, sounds (words shows
  "instrumental" when LRCLIB says so). Lit = the index has that search path
  for this track. /api/search returns `has` per result.
- Fishy fishy reads: sounds and preview yes, everything else no — which is
  the honest reason it was hard to find.

### MEASURED 2026-09-12 — MuLan really is ~10x slower than CLAP, and it is not the browser's fault
Same machine, same CPU backend, one 10 s window, median of 6:

| model                         | ms / 10 s window |
|-------------------------------|------------------|
| CLAP audio tower (PyTorch fp32)|   55 |
| MuLan audio tower (ONNX fp32)  |  530 |
| MuLan audio tower (ONNX fp16)  |  576 |

- The earlier "9x" from compare.py was NOT a batching artifact; it holds up.
- fp16 is not faster on CPU (no native fp16 compute) — it is for SIZE.
- Cause is architecture, not parameter count (334M vs ~150M): MuQ works at a
  much finer time resolution, 1001 frames per 10 s window.
- CLAP IS UNTOUCHED. Nothing in the fp16/int8/STFT work above changed the
  model the site runs. That work is all on the MuLan conversion.

### BUILT 2026-09-12 — sound-only search
- `?sound_only=1`, checkbox on the page: "Nothing is written down about this
  song — go by sound alone". Drops stated facts, the name lead, lyric matching
  and fact tiering, so a well-documented track cannot outrank an obscure one
  on paperwork it happens to have. His idea.
- Badges now show ONLY what is missing (no lyrics / no year / no country) and
  say nothing when the index has it. His correction: lit pips implied every
  path mattered equally, when the sound is the point of the site.

### NEXT (his call) — a local embedding program, his idea and the right one
A small CLI people run on their own machine: no 638 MB browser download, the
full GPU, and ONNX Runtime's native providers cover ROCm, CUDA, DirectML and
CPU from the same file. Power users get speed and MuLan; the browser stays the
zero-install path. This is what makes MuLan shippable without forcing 638 MB
on a casual visitor.

### CORRECTION 2026-09-12 — the 10x was per WINDOW, not per track
At the window counts each model actually ships with (CLAP 8 windows, MuLan 3):

| model | ms/window | windows | per track (CPU) |
|-------|-----------|---------|-----------------|
| CLAP  |  55       | 8       | 0.44 s |
| MuLan | 513       | 3       | 1.54 s |

**3.5x per track, not 10x.** I quoted the per-window figure as if it were the
per-track one twice. His ~1 s/track in the browser on the first scan is
normal and healthy, not a symptom of anything wrong.

### DECIDED 2026-09-12 — the local scanner is a portable GUI program, not a CLI
His call, and the constraints are his:
- Windows first. A lot of people will not touch a terminal.
- PORTABLE. Nothing installed, ever. One file, run it, close it, delete it.
- No CUDA, no ROCm, no PyTorch to install: ONNX Runtime on Windows ships the
  DirectML provider, which runs on any GPU (AMD, NVIDIA, Intel, integrated)
  on stock drivers. That is the whole reason ONNX was the right export target.
- The browser path stays exactly as it is. The program is for people with big
  libraries who want MuLan quality; the browser is for everyone else.

### MEASURED 2026-09-12 — what MuLan would cost the Pi
The text tower exports too (its own forward only accepts raw strings, so the
wrapper calls the RoBERTa + proj + transformer path directly; verified cosine
1.000000 against mulan(texts=...)).

| text tower | on disk | cosine vs fp32 | ms/query (4 x86 threads) |
|------------|---------|----------------|--------------------------|
| fp32       | 1315 MB | —              | 12 |
| fp16       |  658 MB | conversion emits a bad Cast; needs a fix | — |
| int8       |  330 MB | 0.978          |  5 |

- **RAM ON THE PI: ~150 MB.** Clean process, baseline 44 MB -> peak 195 MB with
  the int8 text tower loaded and run. ONNX Runtime memory-maps the weights, so
  resident memory is well under the file size. The server uses 70 MB today, the
  container cap is 1500 MB. Not close to a problem.
- int8 holds up far better on the TEXT tower (0.978) than on the audio one
  (0.887) — a RoBERTa-style stack quantises well, the audio conformer does not.
- Searches stay fast: 5 ms/query here, so maybe 20-30 ms on the Pi's cores.

### DECIDED 2026-09-12 — no separate program after all
At 1.54 s/track the browser is good enough and a portable GUI is not worth
building. His call, and the 3.5x correction is what changed it. The local
scanner stays in the queue as an OPTION, not a plan.

### PROVEN 2026-09-12 — MuLan RUNS IN THE BROWSER. Measured in Chrome, this machine.
scratchpad/webtest/ (index.html, stft.js). Loads the fp16 audio tower through
onnxruntime-web 1.20.1, feeds it a spectrogram computed in JavaScript, and
compares the 512 numbers that come out against the PyTorch answer.

| backend | model load | per 10 s window | cosine vs PyTorch |
|---------|-----------|-----------------|-------------------|
| WebGPU  | 1299 ms   |   532 ms        | 0.999873 |
| WASM    |  934 ms   | 12085 ms        | 0.999999 |

- JS spectrogram (radix-2 FFT, 1001 frames): **92 ms**, negligible.
- **1.6 s/track on WebGPU** (3 windows), against ~1 s/track for CLAP today.
- WASM is 36 s/track: that is the no-GPU fallback and it is not usable for a
  library scan. A machine without WebGPU would need CLAP or a lot of patience.
- GOTCHA that cost two rounds: ORT Web does NOT fetch a model's external
  weights file on its own. It must be handed over explicitly via the
  `externalData` session option, named exactly as the .onnx references it.
  Without it you get a bare numeric error code and no message.
- WebGPU's 0.999873 is fp16 GPU drift, far tighter than CLAP's measured 0.988.

### DECIDED 2026-09-12 — one model, not two (his correction, and he is right)
Vectors from two models cannot be compared, averaged or ranked together, so a
phone submitting CLAP while a desktop submits MuLan would split the index into
two halves that cannot see each other. Earlier in this session I proposed
exactly that for mobile; it was incoherent and he caught it. If MuLan goes in,
MuLan is what everything uses, phones included. His call: "my decision is
quality". Searching is unaffected on any device — the text half runs on the Pi.

### BUILT 2026-09-12 — the server can run either ear
- `VIBEFIND_MODEL=clap|mulan`. MODELS holds each ear's id, window count and
  sample rate; /api/stats reports them so the browser scans the right way.
- vectors gains a `model` column (migration rebuilds the table, existing rows
  become 'clap'); the index only ever loads one model's vectors, and its files
  are prefixed per ear, so switching is reversible and destroys nothing.
- text_embed picks the matching text half: CLAP's from HuggingFace, MuLan's
  int8 tower from the Pi's own models dir.
- server/seed_vectors.py fills an ear from an offline .npz, matching a file
  path to a track by artist+title with feat./remix tails stripped: **2,035 of
  2,286 of his trial vectors matched**; the rest arrive when he rescans.

MEASURED on a seeded copy of the live database, MuLan serving live searches:

| query | CLAP | MuLan |
|---|---|---|
| dusty sample-based beat with a spoken word sample |  643 | **1** |
| kids voice sample lofi hip hop                    |  807 | **8** |
| grungy lo-fi trip hop beat                        |  297 | **16** |

Controls still behave: "aggressive dubstep with huge wobbling bass" -> SAN
DIEGO VIP, "solo nylon string guitar brazilian" -> Consolação.

### BUILT 2026-09-12 — the browser side. A real scan produced a real MuLan vector.
- web/stft.js: the step ORT Web has no kernel for. Radix-2 FFT, 1001 frames,
  92 ms per window. Parameters read off the model, not guessed.
- worker.js: `initMulan()` declares the weights file IN THE SAME OBJECT as the
  model path, so the two cannot drift apart — that is the never-forget the user
  asked for. Tries WebGPU then WASM, and says which it used.
- 48 kHz -> 24 kHz by windowed-sinc, and windows at 20/50/80 % to match the
  trial vectors exactly.
- THE EAR IS THE SERVER'S. app.js no longer hard-codes the model id; it asks
  /api/stats at the start of every scan. Scanning with the wrong ear would
  produce vectors nothing can be compared to.
- BUG FOUND AND FIXED in the process: a known track skipped the embed, so a
  model switch would have left every existing track with no vector in the new
  space and silently unsearchable. identify now returns `has_vector` for the
  ACTIVE model and the scan re-embeds when it is false.
- VERIFIED end to end: fed the browser a track with no MuLan vector, it loaded
  the model, embedded it and submitted. **cosine 0.968 vs the PyTorch vector
  for the same file** — the gap is resampling (Web Audio + our filter vs
  librosa), and it is far inside the ~0.88 that separates a track from its
  nearest neighbour. 7 s for the track including the model load.

STILL TO DO before a switch: get the 606 MB model onto the Pi and confirm
Cloudflare will serve it, then `VIBEFIND_MODEL=mulan` in the service file.

### READY 2026-09-12 — MuLan is plumbed end to end. One word switches it on.
Everything below is deployed to the Pi and live-tested. The site is still on
CLAP; nothing about the switch is irreversible.

- Models on the Pi: web/models/mulan_spec_fp16.onnx(+.data) 609 MB for
  browsers, data/models/mulan_text_int8.onnx(+.data) 316 MB for the server.
- Cloudflare serves the 606 MB weights: HTTP 206 range requests, 6.7 MB/s,
  `immutable` so a browser fetches it once ever. cf-cache-status is DYNAMIC,
  so it comes off the Pi each first visit — ~95 s of its upstream per new
  scanner. Worth watching if the site gets busy.
- TO SWITCH: `VIBEFIND_MODEL=mulan` in deploy/describesong.service, then
  daemon-reload + restart. To switch back, the same line and restart; both
  ears' vectors and index files stay on disk.
- On switching: 2,035 of 2,276 tracks already have MuLan vectors (seeded from
  the trial), so search works immediately. The other 241 are invisible until
  someone scans them, and re-scanning a folder fills them at ~1.6 s/track.
- A browser with no WebGPU falls back to WASM at ~36 s/track. That is the one
  real cost of the switch and it lands on people with old machines.

### STILL OPEN
- Vocal separation before transcription, to lift the 26 % lyric figure. Not
  measured yet; the only thing he asked for that I have not done.
- int8 for the audio tower needs per-layer mixed precision (a blanket pass
  gave cosine 0.887). Would take the browser download from 606 MB to ~320 MB.
