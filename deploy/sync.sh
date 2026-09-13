#!/usr/bin/env bash
# Deploy web/ to the Pi with every script/stylesheet URL stamped with the commit
# hash. Cloudflare caches .js/.css at its edge for hours (and tells browsers
# max-age=14400, overriding the origin's no-cache), so after a deploy a visitor
# could run an old app.js against a new page. A new URL per version cannot be
# stale anywhere. The repo keeps the plain names; only the deployed copy is stamped.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; PI="${PI:?set PI=user@host of the Pi, e.g. PI=pi@raspberrypi.local}"
V="$(git -C "$ROOT" rev-parse --short HEAD)$(git -C "$ROOT" diff --quiet || echo -dirty)"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
# models/ is EXCLUDED from staging: it is ~609 MB of weights that need no
# version stamping, and $T is a mktemp dir — on this machine /tmp is a 16 GB
# RAM disk, so copying them through it filled memory and broke the deploy.
# They go straight to the Pi below, where rsync skips them when unchanged.
rsync -a --exclude 'models/' "$ROOT/web/" "$T/web/"
for f in "$T"/web/*.html; do sed -i -E "s#(href|src)=\"(style\.css|app\.js|tones\.js|water\.js)\"#\1=\"\2?v=$V\"#g" "$f"; done
sed -i -E "s#new Worker\(\"worker\.js\"#new Worker(\"worker.js?v=$V\"#" "$T/web/app.js"
# --exclude models/ here too, or --delete would remove them from the Pi
rsync -az --delete --exclude 'models/' "$T/web/" "$PI:/mnt/nvme/describesong/src/web/"
# weights: straight from the repo, no staging, no compression (already packed)
if [ -d "$ROOT/web/models" ]; then rsync -a "$ROOT/web/models/" "$PI:/mnt/nvme/describesong/src/web/models/"; fi
echo "deployed web/ as version $V"
