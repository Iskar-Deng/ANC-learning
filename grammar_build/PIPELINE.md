# Grammar Build Pipeline

```bash
# Build all 96 grammars
bash grammar_build/build_all_grammars.sh \
  --lexicon-json data/train/train_lexicon.json \
  --freezer-megabytes 4096
```

## Single-grammar workflow

```bash
# 1. Generate one choice file from typological parameters
python grammar_build/generate_choices.py \
  --clause-wo svo \
  --np-wo ng \
  --alignment erg-abs \
  --comp-system deranking \
  --strategy erg-poss
```

```bash
# 2. Customize target grammar from choice file
python external/matrix/matrix.py \
  --customizationroot external/matrix/gmcs \
  customize-to-destination \
  choices/62_svo_ng_er_d_ep.choice \
  grammars/62_svo_ng_er_d_ep
```

```bash
# 3. Update target grammar lexicon
python grammar_build/update_grammar_lexicon.py \
  --lexicon-json data/sample/sample_lexicon.json \
  --grammar-root grammars/62_svo_ng_er_d_ep
```

```bash
# 4. Patch ANC-WO if needed
python grammar_build/patch_anc_wo.py \
  --tdl grammars/62_svo_ng_er_d_ep/62_svo_ng_er_d_ep.tdl
```

```bash
# 5. Compile target grammar
./grammar_build/compile_grammar.sh \
  grammars/62_svo_ng_er_d_ep/62_svo_ng_er_d_ep.dat
```
