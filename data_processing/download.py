from datasets import load_dataset
from pathlib import Path


repo_root = Path(__file__).resolve().parents[1]
data_dir = repo_root / "data"

ds = load_dataset("BabyLM-community/BabyLM-2026-Strict")

print(ds)

def save_split_to_txt(dataset_split, output_path):
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        for example in dataset_split:
            text = example.get("text", "")
            if text:
                f.write(text.strip() + "\n")

save_split_to_txt(ds["train"], data_dir / "babylm.txt")
