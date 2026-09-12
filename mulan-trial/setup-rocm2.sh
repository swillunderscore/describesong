#!/bin/bash
cd ~/vibefind/mulan-trial
PY=""; for c in python3.13 python3.12 python3.11; do command -v $c >/dev/null && PY=$c && break; done
if [ -z "$PY" ] && command -v conda >/dev/null; then
  conda create -y -q -p ./.conda312 python=3.12 >/dev/null 2>&1 && PY=./.conda312/bin/python
fi
[ -z "$PY" ] && { echo "NO_OLDER_PYTHON"; exit 1; }
echo "using $PY ($($PY --version))"
rm -rf .venv-rocm2; $PY -m venv .venv-rocm2 && . .venv-rocm2/bin/activate && pip install -q --upgrade pip
ok=""
for idx in rocm7.1 rocm7.0 rocm6.4; do
  if pip install -q torch torchaudio torchvision --index-url https://download.pytorch.org/whl/$idx; then
    if python -c "import torch,sys; sys.exit(0 if torch.version.hip else 1)"; then ok=$idx; echo "torch from $idx"; break; fi
  fi
done
[ -z "$ok" ] && { echo "NO_ROCM_WHEEL"; exit 1; }
pip install -q muq librosa soundfile numpy transformers
python - <<'PY'
import torch
print("torch", torch.__version__, "| hip:", torch.version.hip, "| gpu visible:", torch.cuda.is_available(),
      "|", torch.cuda.get_device_name(0) if torch.cuda.is_available() else "none")
PY
echo SETUP_ROCM2_DONE
