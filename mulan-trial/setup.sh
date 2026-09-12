#!/bin/bash
set -e
cd ~/vibefind/mulan-trial
python3 -m venv .venv
. .venv/bin/activate
pip install -q --upgrade pip
pip install -q torch torchaudio torchvision --index-url https://download.pytorch.org/whl/cpu
pip install -q muq librosa soundfile numpy
python - <<'PY'
# Pull the weights now so the timing run does not include the download.
from muq import MuQMuLan
m = MuQMuLan.from_pretrained("OpenMuQ/MuQ-MuLan-large")
print("model loaded:", type(m).__name__)
PY
echo SETUP_DONE
