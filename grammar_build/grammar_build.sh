#!/usr/bin/env bash

# run_matrix_tests.py：
# 使用 ACE 对 grammar 的 test_sentences 进行自动测试。
# 普通句子应当能被解析（≥1 parse），带 "*" 的句子应当无法解析（0 parse）。
# 脚本逐句运行解析并输出解析数量与测试是否通过，用于快速检查 grammar 是否破坏原有测试集。
python3 -m grammar_build.run_matrix_tests \
  --grammar grammars/test-hebrew_final/test-hebrew.dat \
  --tests grammars/test-hebrew_final/test_sentences \
  --max-parses 50

# debug_parse.py：
# 该脚本用于调试单句解析结果：
# 调用 ACE 解析指定句子，并输出 derivation tree。
# 可选打印 MRS 或导出 Graphviz DOT 图，用于查看语法规则展开情况。

python3 -m grammar_build.debug_parse \
  --grammar grammars/test-hebrew/test-hebrew.dat \
  --sent "I haves seetionac hege" \
  --mrs \
  --tree \
  --png-out trees

# debug_generate.py：
# 该脚本用于调试单个 MRS 的生成结果：
# 调用 ACE 根据输入 MRS 生成可能句子，并输出所有 surface forms。
python3 -m grammar_build.debug_generate \
  --grammar grammars/test-english/test-english.dat \
  --mrs '[ LTOP: h0 INDEX: e2 [ e SF: iforce E.TENSE: tense E.ASPECT: aspect E.MOOD: mood ] RELS: < [ \"exist_q_rel\"<-1:-1> LBL: h4 ARG0: x3 [ x SPECI: bool COG-ST: cog-st PNG: png ] RSTR: h5 BODY: h6 ]  [ \"_hawe_v_rel\"<-1:-1> LBL: h7 ARG0: e8 [ e SF: iforce E.TENSE: tense E.ASPECT: aspect E.MOOD: mood ] ARG1: x9 [ x SPECI: bool COG-ST: cog-st PNG: png ] ARG2: h10 ]  [ \"nominalized_rel\"<-1:-1> LBL: h11 ARG0: x3 ARG1: h12 ]  [ \"_show_v_rel\"<-1:-1> LBL: h1 ARG0: e2 ARG1: x3 ARG2: h13 ]  [ \"exist_q_rel\"<-1:-1> LBL: h14 ARG0: x15 [ x SPECI: bool COG-ST: cog-st PNG: png ] RSTR: h16 BODY: h17 ]  [ \"_hole_n_rel\"<-1:-1> LBL: h18 ARG0: x15 ]  [ \"_exist_v_rel\"<-1:-1> LBL: h19 ARG0: e20 [ e SF: iforce E.TENSE: tense E.ASPECT: aspect E.MOOD: mood ] ARG1: x15 ] > HCONS: < h0 qeq h1 h5 qeq h11 h10 qeq h21 h12 qeq h7 h13 qeq h19 h16 qeq h18 > ICONS: < > ]'

# extract_mrs_from_tests.py：
# 从 grammar 的 test_sentences 中提取可解析句子的 MRS。
# 只处理好句（不处理带 * 的坏句），并保存到一个 jsonl 文件中。
# utils.py 中定义了 MRS_REWRITE_RULES，可以在提取 MRS 时对其进行重写，以适应不同 grammar 之间的 MRS 结构差异。
python3 -m grammar_build.extract_mrs_from_tests \
  --grammar grammars/test-georgian_del_ANCWO/test-georgian.dat \
  --tests grammars/test-georgian_del_ANCWO/test_sentences \
  --out mrs/test-georgian.jsonl

# generate_from_mrs_bank.py：
# 根据 MRS jsonl 和指定 grammar 做 generation。
# 读取前一步保存的 MRS，生成所有可还原的句子，并保存到一个 jsonl 文件中。
python3 -m grammar_build.generate_from_mrs_bank \
  --grammar grammars/test-random/test-random.dat \
  --input data/sample/pseudo_parsed.jsonl \
  --out data/random_output.jsonl