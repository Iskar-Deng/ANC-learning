#!/usr/bin/env bash
set -euo pipefail

export LANG=C.UTF-8
export LC_ALL=C.UTF-8

SPLITS=(
  "dev"
  "test"
)

LANGS=(
  "62_svo_ng_er_d_ep"
  "18_sov_ng_ac_b_ep"
  "02_sov_gn_ac_b_ep"
  "50_svo_ng_ac_b_ep"
  "82_vos_ng_ac_b_ep"
  "08_sov_gn_er_b_se"
  "42_svo_gn_er_b_ep"
  "94_vos_ng_er_d_ep"
)

echo "========== Check runner log =========="
if [[ -f logs/generation/representative_dev_test_generation.log ]]; then
  tail -80 logs/generation/representative_dev_test_generation.log
else
  echo "[warn] missing logs/generation/representative_dev_test_generation.log"
fi

echo
echo "========== Raw generation summary =========="
python - <<'PY'
import json
from pathlib import Path

splits = ["dev", "test"]
langs = [
  "62_svo_ng_er_d_ep",
  "18_sov_ng_ac_b_ep",
  "02_sov_gn_ac_b_ep",
  "50_svo_ng_ac_b_ep",
  "82_vos_ng_ac_b_ep",
  "08_sov_gn_er_b_se",
  "42_svo_gn_er_b_ep",
  "94_vos_ng_er_d_ep",
]

for split in splits:
    print(f"\n==================== {split} raw ====================")
    print("language\ttotal\tempty\tover\tmax_candidates")
    for lang in langs:
        path = Path(f"data/{split}/generated/raw/{lang}.jsonl")
        if not path.exists():
            print(f"{lang}\tMISSING\tMISSING\tMISSING\tMISSING")
            continue

        total = empty = over = max_cands = 0

        with path.open(encoding="utf-8") as f:
            for line in f:
                x = json.loads(line)
                sent = x.get("sent", [])
                if not isinstance(sent, list):
                    sent = []

                total += 1
                n = len(sent)
                max_cands = max(max_cands, n)

                if n == 0:
                    empty += 1
                elif n > 1:
                    over += 1

        print(f"{lang}\t{total}\t{empty}\t{over}\t{max_cands}")
PY

echo
echo "========== Selection key counts =========="
for SPLIT in "${SPLITS[@]}"; do
  echo
  echo "==================== ${SPLIT} selection ===================="
  for LANG in "${LANGS[@]}"; do
    LOG="logs/generation/select_${LANG}_${SPLIT}.log"

    echo
    echo "---------- ${LANG} ----------"

    if [[ ! -f "$LOG" ]]; then
      echo "[missing log] $LOG"
      continue
    fi

    grep -E \
      "Total input rows|Total unique ids|Rows/ids requiring selection|Overgenerated ids|Same-bag overgenerated ids|Different-bag overgenerated ids|Resolved by S-marker suffix variant|Resolved by ANC A/P order|A/P order multiple match, random choice|Same-bag unresolved, random choice|Different-bag overgenerated, random choice|Empty ids|Single-candidate ids" \
      "$LOG" || true
  done
done

echo
echo "========== Selected data sanity check =========="
python - <<'PY'
import json
from pathlib import Path

splits = ["dev", "test"]
langs = [
  "62_svo_ng_er_d_ep",
  "18_sov_ng_ac_b_ep",
  "02_sov_gn_ac_b_ep",
  "50_svo_ng_ac_b_ep",
  "82_vos_ng_ac_b_ep",
  "08_sov_gn_er_b_se",
  "42_svo_gn_er_b_ep",
  "94_vos_ng_er_d_ep",
]

for split in splits:
    print(f"\n==================== {split} selected ====================")
    print("language\ttotal\tbad_sent")
    for lang in langs:
        path = Path(f"data/{split}/generated/selected/{lang}.jsonl")
        if not path.exists():
            print(f"{lang}\tMISSING\tMISSING")
            continue

        total = bad = 0
        with path.open(encoding="utf-8") as f:
            for line in f:
                x = json.loads(line)
                total += 1
                sent = x.get("sent")
                if not isinstance(sent, str) or not sent.strip():
                    bad += 1

        print(f"{lang}\t{total}\t{bad}")
PY

echo
echo "========== Different-bag random examples =========="
for SPLIT in "${SPLITS[@]}"; do
  echo
  echo "==================== ${SPLIT} random examples ===================="
  for LANG in "${LANGS[@]}"; do
    DETAILS="data/${SPLIT}/generated/details/${LANG}.jsonl"

    echo
    echo "---------- ${LANG} ----------"

    if [[ ! -f "$DETAILS" ]]; then
      echo "[missing details] $DETAILS"
      continue
    fi

    grep '"selection_reason": "different_bag_random"' "$DETAILS" | head -5 || true
  done
done

echo
echo "========== DONE =========="