# DescribeSong

Describe a song in plain words — instruments, mood, tempo, era, where you heard it — and get its name.

A community index of *how songs sound*. Nobody uploads audio: your browser reads your files, identifies each one by acoustic fingerprint ([AcoustID](https://acoustid.org) + [MusicBrainz](https://musicbrainz.org)), and boils it down to a 2 KB vector ([LAION CLAP](https://github.com/LAION-AI/CLAP), run in the browser with WebGPU). Only the vector and the artist / title / album text are sent. Searching turns your sentence into the same kind of vector and ranks every stored song against it.

**What the server stores, and what it never stores:** [`web/legal.html`](web/legal.html).

## Layout

- `web/` — the site. `app.js` (search + folder scan), `worker.js` (Chromaprint via WASM + CLAP via transformers.js), `tones.js` (the two-tone technicolor palette), `water.js` (a port of [hyprwater](https://github.com/swillunderscore/Technicolor-Hyprland-QS-Dotfiles)), `wasm/` (the fingerprinter).
- `server/` — FastAPI. SQLite, a brute-force vector index in RAM, the CLAP text tower on ONNX Runtime (CPU). Runs on a Raspberry Pi.
- `fingerprint-wasm/` — Chromaprint (rusty-chromaprint) compiled to WebAssembly.
- `deploy/` — the Pi install script and systemd unit.
- `QUEUE.md` — the working log: every decision, measurement and landmine, in order.

## Run it

```
cd server && python -m venv .venv && .venv/bin/pip install -r requirements.txt
VIBEFIND_DATA=../data ACOUSTID_KEY=<your key from acoustid.org/new-application> .venv/bin/python -m uvicorn app:app --port 8080
```
Open http://localhost:8080. The text model (~240 MB) downloads on the first search; the browser downloads the audio model (~143 MB) on the first scan.

On a Raspberry Pi: `deploy/pi-install.sh`, then the unit in `deploy/describesong.service`.

## Licences

- Code: [AGPL-3.0](LICENSE). If you run a modified copy as a service, you must offer its source to your users.
- The database of vectors and labels: [ODbL](https://opendatacommons.org/licenses/odbl/) — use it for anything, share improvements to the database itself alike.
- Model weights: LAION CLAP (CC0). Fingerprints: Chromaprint (LGPL) via rusty-chromaprint.
