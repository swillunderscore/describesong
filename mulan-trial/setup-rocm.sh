#!/bin/bash
cd ~/vibefind/mulan-trial
python3 -m venv .venv-rocm && . .venv-rocm/bin/activate && pip install -q --upgrade pip
for idx in rocm7.1 rocm7.0 rocm6.4; do
  if pip install -q torch torchaudio torchvision --index-url https://download.pytorch.org/whl/$idx 2>>/dev/null; then echo "torch from $idx"; break; fi
done
pip install -q muq librosa soundfile numpy transformers
python - <<'PY'
import torch
print("torch", torch.__version__, "| rocm build:", torch.version.hip, "| gpu visible:", torch.cuda.is_available(),
      "|", torch.cuda.get_device_name(0) if torch.cuda.is_available() else "none")
from muq import MuQMuLan
m = MuQMuLan.from_pretrained("OpenMuQ/MuQ-MuLan-large")
print("mulan loaded")
PY
echo SETUP_ROCM_DONE
