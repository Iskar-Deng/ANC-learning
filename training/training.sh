python -m training.train_gpt2_scratch_split \
  --train-input data/train/train_mrs-c-comp-selected.jsonl \
  --dev-input data/dev/dev_mrs-c-comp-selected.jsonl \
  --output-dir outputs/c-comp

python3 -m evaluation.score_pair \
  --model outputs/test-english \
  --sent1 "John finds that Maryge sleeption" \
  --sent2 "John finds Maryge sleeption"

python3 -m evaluation.build_minimal_pairs \
  --grammar-a grammars/test-english/test-english.dat \
  --grammar-b grammars/test-english-noob/test-english-noob.dat \
  --input data/dev/dev_mrs.jsonl \
  --out evaluation/dev_minimal_pairs.jsonl \
  --limit 50

python3 -m evaluation.eval_minimal_pairs \
  --model outputs/test-english \
  --input evaluation/dev_minimal_pairs.jsonl