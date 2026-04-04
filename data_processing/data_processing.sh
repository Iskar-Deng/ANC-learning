#!/usr/bin/env bash
# -*- coding: utf-8 -*-

# Part 1: 伪英语与 MRS 条目生成

# 1. 构建伪英语基础语法
grammar_build/iterate.sh test-english

# 2. 用 spaCy parse 并提取可用结构
python data_processing/extract_basic.py \
  --input data/train.txt \
  --output data/train.jsonl \
  --stats-output data/train_stats.json

# 3. 生成伪英语并记录词汇
python data_processing/generate_pseudo_english.py \
  --input data/train.jsonl \
  --out-jsonl data/train_pseudo.jsonl \
  --out-lexicon data/train_lexicon.json \
  --out-stats data/train_pseudo_stats.json

# 4. 更新英语语法词表
python data_processing/update_grammar_lexicon.py \
  --lexicon-json data/train_lexicon.json \
  --grammar-root grammars/test-english \
  --no-trigger

# 5. 人工语法修补
# （手动修改 grammar files）

# 6. 重编译英语语法
grammar_build/recompile_grammar.sh grammars/test-english/test-english.dat

# 7. 生成 MRS
python -m data_processing.parse_pseudo_with_grammar \
  --grammar grammars/test-english/test-english.dat \
  --input data/train_pseudo.jsonl \
  --out data/train_mrs.jsonl \
  --max-parses 20

# Part 2: 具体语言生成

# 1. 构建目标语言基础语法
grammar_build/iterate.sh test-korean

# 2. 更新目标语法词表
python data_processing/update_grammar_lexicon.py \
  --lexicon-json data/train_lexicon.json \
  --grammar-root grammars/test-korean \
  --no-trigger

# 3. 人工语法修补
# （手动修改 grammar files）

# 4. 重编译目标语法
grammar_build/recompile_grammar.sh grammars/test-korean/test-korean.dat

# 5. 从 MRS bank 生成对应语言
nohup python3 -m grammar_build.generate_from_mrs_bank \
  --grammar grammars/test-english/test-english.dat \
  --input data/train_mrs.jsonl \
  --out data/train_mrs-test-english.jsonl \
  --no-mrs \
  --workers 12 \
  --chunksize 100 \
  --max-gen 20 \
  > logs/generate-english.log 2>&1 &

# 6. 去重 / 选择 overgeneration 输出
python data_processing/select_overgen.py \
  --input data/train_mrs-test-english.jsonl \
  --out data/train_mrs-test-english-selected.jsonl \
  --left-suffix gs \
  --right-suffix ob

# 7. 检查 overgeneration
python data_processing/show_overgen.py \
  data/train_mrs-test-english.jsonl