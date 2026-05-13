from datasets import load_dataset
import os

ds = load_dataset("BabyLM-community/BabyLM-2026-Strict")

print(ds)

def save_split_to_txt(dataset_split, output_path):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        for example in dataset_split:
            text = example.get("text", "")
            if text:
                f.write(text.strip() + "\n")

save_split_to_txt(ds["train"], "data/babylm.txt")