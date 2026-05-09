# utils.py

ACE_BIN = "/home/dengh/workspace/ANC-learning/bin/ace-0.9.34/ace"

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
    "num_train_epochs": 3,
    "per_device_train_batch_size": 16,
    "per_device_eval_batch_size": 16,
    "gradient_accumulation_steps": 2,
    "learning_rate": 5e-4,
    "warmup_steps": 590,
    "weight_decay": 0.01,

    # logging / saving
    "logging_steps": 100,
    "eval_steps": 2000,
    "save_steps": 2000,
    "save_total_limit": 2,

    # dataloader
    "dataloader_num_workers": 0,
}