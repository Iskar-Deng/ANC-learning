# Evaluation Pipeline

```bash
python evaluation/score_one_model_real_grammar.py \
  --model models/02_sov_gn_ac_b_ep/seed_42/checkpoint-70000 \
  --model-id 02_sov_gn_ac_b_ep \
  --selected-dir data/test/generated/selected \
  --common-ids results/e2_selected_coverage/test/common_ids.txt \
  --out-dir results/e2_real_grammar_preference/test_one_model \
  --batch-size 64 \
  --max-ids 100
```