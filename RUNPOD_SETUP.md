# RunPod Environment Setup

This file lists the manually curated environment needed to rerun the full
pipeline from a clean RunPod instance. It is not a `pip freeze` snapshot.

Run commands from the repository root unless noted otherwise.

## Recommended Base

- Ubuntu 22.04 or similar Linux image
- NVIDIA GPU image with CUDA 12.x
- Persistent volume large enough for generated corpora, grammars, and models
- Many CPU cores help ACE generation; GPU matters mainly for LM training

## 1. System Packages

```bash
apt-get update
apt-get install -y \
  build-essential \
  curl \
  git \
  git-lfs \
  locales \
  rsync \
  time \
  tmux \
  unzip \
  wget
```

Set a locale before importing PyDelphin/ACE:

```bash
export LANG=C.UTF-8
export LC_ALL=C.UTF-8
```

If the image does not provide `C.UTF-8`, use:

```bash
locale-gen en_US.UTF-8
export LANG=en_US.UTF-8
export LC_ALL=en_US.UTF-8
```

## 2. Clone Code

```bash
cd /workspace
git clone https://github.com/Iskar-Deng/ANC-learning.git
cd ANC-learning
git switch -c codex/fix-genitive-realization --track origin/codex/fix-genitive-realization
```

## 3. Conda Environment

Create the environment from the curated file:

```bash
conda env create -f environment.yml
conda activate anc
```

Install the spaCy English model used by `semantic_extraction/extract_basic.py`:

```bash
python -m spacy download en_core_web_md
```

Quick Python dependency check:

```bash
python - <<'PY'
import sys
import numpy
import torch
import transformers
import datasets
import spacy
import delphin
import tqdm

print("python", sys.version)
print("numpy", numpy.__version__)
print("torch", torch.__version__, "cuda", torch.cuda.is_available())
print("transformers", transformers.__version__)
print("datasets", datasets.__version__)
print("spacy", spacy.__version__)
print("delphin", delphin.__version__)
print("tqdm", tqdm.__version__)
PY
```

## 4. External Dependencies

The repo expects two external resources that are not installed by conda.

### ACE

Place the ACE binary here:

```text
bin/ace-0.9.34/ace
```

Then make it executable:

```bash
chmod +x bin/ace-0.9.34/ace
```

Verify that the path matches `utils.py`:

```bash
python - <<'PY'
from utils import ACE_BIN
from pathlib import Path

print("ACE_BIN =", ACE_BIN)
print("exists =", Path(ACE_BIN).exists())
print("executable =", Path(ACE_BIN).exists() and Path(ACE_BIN).stat().st_mode & 0o111 != 0)
PY
```

By default `utils.py` looks for ACE at `bin/ace-0.9.34/ace` relative to the
repository root. To override it for a custom ACE location:

```bash
export ACE_BIN=/absolute/path/to/ace
```

### Grammar Matrix

Place the Grammar Matrix repository here:

```text
external/matrix/
```

The following paths must exist:

```text
external/matrix/matrix.py
external/matrix/gmcs/
```

Verify:

```bash
test -f external/matrix/matrix.py
test -d external/matrix/gmcs
```

## 5. First Smoke Test

Generate choices:

```bash
python grammar_build/generate_choices.py \
  --all \
  --out-dir choices \
  --manifest manifest.tsv
```

After preparing or copying `data/train.txt`, run a tiny semantic extraction
smoke:

```bash
mkdir -p smoke
head -5000 data/train.txt > smoke/train_smoke.txt

bash semantic_extraction/run_semantic_extraction.sh \
  --input smoke/train_smoke.txt \
  --update-grammar
```

If this succeeds, test one target grammar after building grammars:

```bash
bash grammar_build/build_all_grammars.sh \
  --lexicon-json smoke/train_smoke/train_smoke_lexicon.json \
  --freezer-megabytes 4096
```

For the full run order, see `README.md`.

## 6. Notes

- `spacy` requires `en_core_web_md`; the package alone is not enough.
- `pydelphin` is only the Python wrapper; ACE is a separate binary.
- ACE generation is CPU-heavy. Tune `--workers` in
  `language_generation/run_all_language_generation.sh`.
- LM training is GPU-heavy and uses Hugging Face `Trainer`; `accelerate` is
  included for that runtime.
