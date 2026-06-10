import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent

ACE_BIN = os.environ.get(
    "ACE_BIN",
    str(PROJECT_ROOT / "bin" / "ace-0.9.34" / "ace"),
)

MRS_REWRITE_RULES = [
    ("SF: prop-or-ques", "SF: iforce"),
    ("COG-ST: uniq-id", "COG-ST: cog-st"),
    ("COG-ST: in-foc", "COG-ST: cog-st"),
]

TRAINING_CONFIG = {
    # model / tokenizer
    "model_name": "gpt2",
    "text_field": "sent",

    # data
    "block_size": 32,

    # training
    "seed": 42,
    "max_steps": 70000,
    "per_device_train_batch_size": 16,
    "per_device_eval_batch_size": 16,
    "gradient_accumulation_steps": 2,
    "learning_rate": 5e-4,
    "warmup_steps": 590,
    "weight_decay": 0.01,

    # logging / saving
    "logging_steps": 100,
    "eval_steps": 5000,
    "save_steps": 5000,
    "save_total_limit": 1,

    # dataloader
    "dataloader_num_workers": 0,
}
