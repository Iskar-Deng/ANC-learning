#!/usr/bin/env bash

# run_matrix_tests.py：
# 使用 ACE 对 grammar 的 test_sentences 进行自动测试。
# 普通句子应当能被解析（≥1 parse），带 "*" 的句子应当无法解析（0 parse）。
# 脚本逐句运行解析并输出解析数量与测试是否通过，用于快速检查 grammar 是否破坏原有测试集。
python3 -m scripts.run_matrix_tests \
  --grammar grammars/test-korean_final/test-korean.dat \
  --tests grammars/test-korean_final/test_sentences \
  --max-parses 50

# inspect_one.py：
# 该脚本用于调试单句解析结果：
# 调用 ACE 解析指定句子，并输出 derivation tree。
# 可选打印 MRS 或导出 Graphviz DOT 图，用于查看语法规则展开情况。
python3 -m scripts.debug_parse \
  --grammar grammars/test-english_20260316_152345/test-english.dat \
  --sent "n2 n1 iv1-fin" \
  --mrs \
  --tree \
  --png-out trees

# extract_mrs_from_tests.py：
# 从 grammar 的 test_sentences 中提取可解析句子的 MRS。
# 只处理好句（不处理带 * 的坏句），并保存到一个 jsonl 文件中。
python3 -m scripts.extract_mrs_from_tests \
  --grammar grammars/test-korean_final/test-korean.dat \
  --tests grammars/test-korean_final/test_sentences \
  --out mrs/test-korean.jsonl

# generate_from_mrs_bank.py：
# 根据 MRS jsonl 和指定 grammar 做 generation。
# 读取前一步保存的 MRS，生成所有可还原的句子，并保存到一个 jsonl 文件中。
python3 -m scripts.generate_from_mrs_bank \
  --grammar grammars/test-english_20260316_152345/test-english.dat \
  --input mrs/test-korean.jsonl \
  --out mrs/generated.jsonl