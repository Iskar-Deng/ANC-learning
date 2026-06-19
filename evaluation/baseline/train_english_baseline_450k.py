#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

import utils  # noqa: E402


# Baseline-only override: resume the 150k run and keep checkpoints every 50k.
utils.TRAINING_CONFIG["eval_steps"] = 50000
utils.TRAINING_CONFIG["save_steps"] = 50000
utils.TRAINING_CONFIG["save_total_limit"] = 20


def patch_resume_trainer_state() -> None:
    if "--resume-from-checkpoint" not in sys.argv:
        return

    arg_index = sys.argv.index("--resume-from-checkpoint")
    if arg_index + 1 >= len(sys.argv):
        return

    state_path = Path(sys.argv[arg_index + 1]) / "trainer_state.json"
    if not state_path.exists():
        return

    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["eval_steps"] = utils.TRAINING_CONFIG["eval_steps"]
    state["save_steps"] = utils.TRAINING_CONFIG["save_steps"]
    state_path.write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


patch_resume_trainer_state()

from training.train_lm import main  # noqa: E402


if __name__ == "__main__":
    main()
