# Changelog

## 2026-03-16 — 修复 clausal complement 无法生成问题

- **问题**：英语 grammar 中 clausal complement 结构（`cv1 + comp + clause`）无法从自身生成的 MRS 还原（generate=0）
- **原因**：`comp` 为 **空语义（raise-sem）词项**，MRS 中无对应 EP，generator 无法自动引入
- **修改**：在原有（空的）`trigger.mtr` 中新增 generator rule (cv1, cv2)：

```tdl
cv1-comp-trigger := generator_rule &
[ CONTEXT [ RELS <! [ PRED "_cv1_v_rel",
                      ARG2 #h ] !> ],
  FLAGS.TRIGGER "comp" ].
```
- **结果**：成功触发 complementizer 插入，`cv` 类句子恢复正常生成，实现 parse/generate 一致

## 2026-03-17 --- 修复不同 nmz 策略的语义不匹配

- **问题**：英韩 nominalization（NMZ）语义接口不一致，导致 eng → kor 部分失败、kor → eng 全部失败
- **原因**：
    - Korean（sentential）：SF = prop-or-ques，COG-ST = cog-st
    - English（specifier-taking）：SF = iforce，COG-ST = uniq-id
    - 两侧在 event（SF）与 nominal（COG-ST）层级约束不对齐
- **修改**：在 MRS 导出阶段统一语义特征（不修改 grammar）
    - SF: prop-or-ques → iforce
    - COG-ST: uniq-id → cog-st
- **结果**：解决部分问题。仍有几个句子还待考察。

## 2026-03-17 — 修复论元 optional 与信息结构导致的语义不对齐

- **问题**：英韩 grammar 在 nominalization 及其嵌套结构中仍存在生成失败，表现为：
  - Korean → English：object-only nominalization 无法生成
  - English → Korean：含 genitive / 弱论元结构生成失败
- **原因**：
  - 两侧对“缺省论元”的处理方式不同：
    - Korean：通过 `opt-subj` 规则引入隐含主语（`COG-ST: in-foc`）
    - English：保留普通未实现论元（`COG-ST: cog-st`）
  - English MRS 中包含 `ICONS`（信息结构约束，如 `non-focus`），而 Korean grammar 不支持该层信息
- **修改**：在 MRS normalization 阶段统一处理：
  - `COG-ST: in-foc → cog-st`
  - 删除信息结构约束：`ICONS: < ... > → ICONS: < >`
- **结果**：
  - 消除因论元 optional 与信息结构差异导致的语义不匹配
  - 英韩 nominalization 相关结构实现双向稳定生成

## 2026-03-18 — 调整 ERG-POSS nominalization 的 ANC 词序实现

- **问题**：ERG-POSS nominalization 在默认 Matrix 实现中无法正确解析，表现为：
  - 含 oblique / genitive / bare argument 的 nominalization 结构无法生成
  - 删除 ANC-WO 后又出现大量 overgenerate（finite / complement 结构重复解析）

- **原因**：
  - `erg-poss` 会触发 ANC 专用词序（ANC-WO），将结构送入 `anc-comp-head` 子系统
  - 该子系统限制了：
    - argument realization（特别是 complement 省略）
    - 与普通 `comp-head` 的组合能力
  - 同时，`anc-head-opt-comp` 对 SPR/SUBJ 约束过强，阻止 bare nominal 出现

- **修改**：

  1. **关闭 `trans-erg-poss-lex-rule` 的 ANC-WO 分流**
     - 将：
       - `HEAD.ANC-WO +`
     - 改为：
       - `HEAD.ANC-WO -`
     - 使其回到普通 `comp-head-phrase` 路径

  2. **放宽 `anc-head-opt-comp-phrase`**
     - 删除对 `SUBJ` 的限制
     - 保留一个弱的 `SPR` 要求：
       - `VAL.SPR < [ ] >`
     - 允许 complement 未显式实现的 nominalization

- **结果**：
  - 成功恢复以下结构：
    - oblique + nmz
    - genitive + nmz
    - bare transitive nominal
    - 无论元 nominal
  - 避免：
    - finite clause duplication
    - clausal complement duplication
  - 测试结果：**29/30 通过**

- **残留问题**：
  - `n1-erg n2-gen n3-obl tv2-nmz-abs tv1-fin` 仍有 overgenerate（2 parses）
  - 原因：
    - ANC 内部 argument 顺序未被完全约束（gen/obl 竞争）
    - 普通 noun possession 路径仍可误用

- **结论**：
  - 当前修改在不改动 Matrix/customizer 源码的前提下，实现了：
    - 正确解析能力
    - 可控的 overgenerate
  - 可作为后续语义对齐与类型学实验的稳定版本

## 2026-03-18 — 试验 split nominalization strategy（保留方案）

- **思路**：
  - 将 Georgian 的 `erg-poss` nominalization 拆成两个 strategy：
    - `erg-poss-intran`
    - `erg-poss-tran`
- **结果**：
  - 该方案能显著改善 transitive / intransitive nominalization 的可控性；
  - 最佳阶段达到 **29/30**。
- **问题**：
  - 整体复杂度明显上升，不符合该问题“本质上是 erg language 下 ANC optional realization 局部约束问题”的性质；
- **结论**：
  - 该 split 方案证明了问题可被 lexical-path 分流缓解，暂存为保留分析，不继续推进。

## 2026-03-18 — POSS-ACC 策略实验

- **思路**：
  使用与 ERG-POSS 相同的修复方式（关闭 `ANC-WO` 分流 + 放宽 `anc-head-opt-comp-phrase`）。
- **结果**：
  POSS-ACC 行为与 ERG-POSS 基本一致，主要测试全部通过。
- **问题**：
  `tv-nmz` 内部双论元语序仍不可控，存在 overgenerate。这一点与 ERG-POSS 也一致。
- **结论**：
  POSS-ACC 已基本可用，剩余问题为论元线性顺序约束。