import random
from pathlib import Path


repo_root = Path(__file__).resolve().parents[1]
data_dir = repo_root / "data"
input_file = data_dir / "babylm.txt"

with open(input_file, "r", encoding="utf-8") as f:
    lines = f.readlines()

random.seed(42)
random.shuffle(lines)

n = len(lines)
train_end = int(n * 0.9)
dev_end = int(n * 0.95)

splits = {
    "train.txt": lines[:train_end],
    "dev.txt": lines[train_end:dev_end],
    "test.txt": lines[dev_end:],
}

for filename, split_lines in splits.items():
    with open(data_dir / filename, "w", encoding="utf-8") as f:
        f.writelines(split_lines)
