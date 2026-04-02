from datasets import load_dataset

# 加载数据集
ds = load_dataset("BabyLM-community/BabyLM-2026-Strict")

# 看一下结构（建议先跑）
print(ds)

# 默认文本字段一般是 "text"
# 如果不确定，可以 print(ds["train"][0])

def save_split_to_txt(dataset_split, output_path):
    with open(output_path, "w", encoding="utf-8") as f:
        for example in dataset_split:
            text = example.get("text", "")
            if text:
                f.write(text.strip() + "\n")


# 保存各个 split
for split in ds.keys():
    save_split_to_txt(ds[split], f"{split}.txt")