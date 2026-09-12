#!/usr/bin/env bash
# One-shot on the Pi: pip-install the server deps into a bind-mounted pylibs dir.
# No `docker build`: this Pi has an aarch64 kernel with a 32-bit userland, and the
# 32-bit dockerd's seccomp profile mistranslates arm64 syscalls -> SIGSYS (exit 159)
# inside any arm64 RUN step. Every arm64 container on this Pi (immich, homestead
# embed-recs) already runs seccomp=unconfined for the same reason. Deps live on
# the volume, the image stays stock python:3.12-slim, and the app container
# gets cap-drop ALL + read-only rootfs + a memory cap to compensate.
set -euo pipefail
ROOT=/mnt/nvme/describesong
mkdir -p "$ROOT/pylibs" "$ROOT/data"
docker run --rm --platform linux/arm64 --security-opt seccomp=unconfined \
  --user "$(id -u):$(id -g)" -e HOME=/tmp -e PIP_CACHE_DIR=/tmp/pip \
  -v "$ROOT/src/server/requirements.txt:/req.txt:ro" -v "$ROOT/pylibs:/pylibs" \
  python:3.12-slim pip install --no-cache-dir --target /pylibs -r /req.txt
echo "pi-install: $(ls "$ROOT/pylibs" | wc -l) packages in $ROOT/pylibs"
