import random

input_file = "/home/dengh/workspace/ANC-learning/data/babylm.txt"

with open(input_file, "r", encoding="utf-8") as f:
    lines = f.readlines()

random.seed(42)
random.shuffle(lines)

n = len(lines)
train_end = int(n * 0.9)
dev_end = int(n * 0.95)

train_lines = lines[:train_end]
dev_lines = lines[train_end:dev_end]
test_lines = lines[dev_end:]

base_path = "/home/dengh/workspace/ANC-learning/data/"

with open(base_path + "train.txt", "w", encoding="utf-8") as f:
    f.writelines(train_lines)

with open(base_path + "dev.txt", "w", encoding="utf-8") as f:
    f.writelines(dev_lines)

with open(base_path + "test.txt", "w", encoding="utf-8") as f:
    f.writelines(test_lines)