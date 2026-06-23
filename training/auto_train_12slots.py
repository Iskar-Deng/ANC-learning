import os, time, subprocess
from pathlib import Path

ROOT = Path("/workspace/ANC-learning")
TRAIN = ROOT / "data/train/generated/selected"
DEV = ROOT / "data/dev/generated/selected"
MANIFEST = ROOT / "data/transfer_manifest.tsv"
LOGDIR = ROOT / "logs/training"
MODELS = ROOT / "models"

SEED = "42"
GPUS = 4
SLOTS_PER_GPU = 3

LOGDIR.mkdir(parents=True, exist_ok=True)
MODELS.mkdir(exist_ok=True)

rows = []
for line in MANIFEST.read_text().splitlines()[1:]:
    lang, train_size, dev_size = line.split()
    rows.append((lang, int(train_size), int(dev_size)))

def complete(path, size):
    if not path.exists():
        return False
    s1 = path.stat().st_size
    time.sleep(1)
    s2 = path.stat().st_size
    return s1 == size and s2 == size

def done(lang):
    out = MODELS / lang / f"seed_{SEED}"
    return (out / "model.safetensors").exists() or (out / "pytorch_model.bin").exists()

def cmdline(pid):
    try:
        return Path(f"/proc/{pid}/cmdline").read_bytes().decode(errors="ignore").replace("\0", " ")
    except Exception:
        return ""

def environ(pid):
    try:
        data = Path(f"/proc/{pid}/environ").read_bytes().decode(errors="ignore").split("\0")
        return dict(x.split("=", 1) for x in data if "=" in x)
    except Exception:
        return {}

def current_running():
    langs = set()
    load = {g: 0 for g in range(GPUS)}

    for p in Path("/proc").iterdir():
        if not p.name.isdigit():
            continue
        pid = p.name
        cmd = cmdline(pid)
        if "training.train_lm" not in cmd or "--language" not in cmd:
            continue

        parts = cmd.split()
        try:
            lang = parts[parts.index("--language") + 1]
            langs.add(lang)
        except Exception:
            pass

        env = environ(pid)
        gpu_raw = env.get("CUDA_VISIBLE_DEVICES", "0").split(",")[0]
        try:
            gpu = int(gpu_raw)
        except Exception:
            gpu = 0
        if gpu in load:
            load[gpu] += 1

    return langs, load

def choose_gpu(load):
    candidates = [g for g in range(GPUS) if load[g] < SLOTS_PER_GPU]
    if not candidates:
        return None
    return min(candidates, key=lambda g: load[g])

print(time.strftime("%F %T"), "scheduler start", "slots", GPUS * SLOTS_PER_GPU, flush=True)

while True:
    running_langs, load = current_running()

    launched_now = 0
    for lang, ts, ds in rows:
        running_langs, load = current_running()

        gpu = choose_gpu(load)
        if gpu is None:
            break

        if lang in running_langs or done(lang):
            continue
        if not complete(TRAIN / f"{lang}.jsonl", ts):
            continue
        if not complete(DEV / f"{lang}.jsonl", ds):
            continue

        log_path = LOGDIR / f"{lang}.gpu{gpu}.log"
        env = os.environ.copy()
        env["CUDA_VISIBLE_DEVICES"] = str(gpu)

        cmd = [
            "python", "-m", "training.train_lm",
            "--language", lang,
            "--train-input", str(TRAIN / f"{lang}.jsonl"),
            "--dev-input", str(DEV / f"{lang}.jsonl"),
            "--seed", SEED,
        ]

        log = open(log_path, "a")
        subprocess.Popen(cmd, cwd=ROOT, env=env, stdout=log, stderr=log)

        print(time.strftime("%F %T"), "LAUNCH", lang, "gpu", gpu, "load_before", load[gpu], flush=True)
        launched_now += 1
        time.sleep(2)

    running_langs, load = current_running()
    print(time.strftime("%F %T"), "running", len(running_langs), "load", load, "launched_now", launched_now, flush=True)
    time.sleep(60)
