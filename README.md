# ANC-learning

## Project structure

```text

data_processing/
  download.py
  split.py

semantic_extraction/
  run_semantic_extraction.sh
  extract_basic.py
  generate_pseudo_english.py
  parse_pseudo_with_grammar.py
  SEMANTIC_PIPELINE.md

grammar_build/
  generate_choices.py
  update_grammar_lexicon.py
  patch_anc_wo.py
  compile_grammar.sh
  build_all_grammars.sh
  GRAMMAR_PIPELINE.md

language_generation/
  generate_from_mrs_bank.py
  select_overgen.py
  GENERATION_PIPELINE.md

training/
  training/train_lm.py
  training/run_all_lm_training.sh
  training/TRAINING_PIPELINE.md

evaluation/

archive/
  debug_grammar/
  
```