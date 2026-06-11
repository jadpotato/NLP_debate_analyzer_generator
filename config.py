# -*- coding: utf-8 -*-
"""
全局配置文件：统一管理所有关键词、正则、阈值、枚举常量
所有业务模块统一从这里导入配置，避免硬编码和重复定义
后续扩展关键词、调整权重仅需修改此文件
"""
import re

# ====================================== 关键词库与权重配置 ======================================
# 1. 定义关键词（权重 +4，全局最高优先级）
DEFINITION_KEYWORDS = {
    "定义为", "是指", "所谓", "指的是", "我们认为",
    "今天我们讨论的", "首先要明确", "何谓", "什么是",
    "本质上是", "根本是", "核心是"
}

# 2. 强论点信号词（权重 +3，独立于位置特征）
STRONG_CLAIM_SIGNALS = {
    "综上所述", "由此可见", "因此", "所以", "故",
    "我方认为", "我方观点是", "今天我方的立场是",
    "核心观点是", "根本原因是", "本质上是", "这意味着",
    "这表明", "这说明", "恰恰是", "正是", "总而言之"
}

# 3. 反驳关键词（核心修复：拆分对外反驳和内部转折）
## 3.1 真正对外反驳词（仅针对对方观点，命中才触发ATTACK打分，权重+3）
TRUE_ATTACK_KW = {
    "对方辩友", "我方反对", "对方混淆了", "对方偷换概念",
    "并非如此", "这是错误的", "荒谬", "我方不认同"
}
## 3.2 内部转折/衔接词（立论内部逻辑转折，不判定为ATTACK，仅作为普通文本）
INNER_TRANS_KW = {
    "但是", "然而", "可是", "不过", "相反", "只不过"
}

# 4. 论据关键词（权重 +3，分5类，补充辩稿高频常识）
## 数据/统计类论据
EVIDENCE_DATA = {"据统计", "调查显示", "数据表明", "%", "年", "万", "亿", "实验证明"}
## 案例/实例类论据
EVIDENCE_CASE = {"例如", "比如", "譬如", "举个例子", "就像", "正如", "历史上"}
## 引言/引用类论据
EVIDENCE_QUOTE = {"指出", "认为", "有言", "古语云", "俗话说", "书中写道"}
## 归纳/排比类论据
EVIDENCE_INDUCE = {"于是", "最终", "到头来", "一方面", "另一方面", "久而久之"}
## 常识类论据（补充辩稿高频名句）
EVIDENCE_COMMON = {"众所周知", "常理而言", "普遍认为", "大家都知道", "美美与共", "各美其美"}

# 合并所有论据关键词
ALL_EVIDENCE_KEYWORDS = EVIDENCE_DATA | EVIDENCE_CASE | EVIDENCE_QUOTE | EVIDENCE_INDUCE | EVIDENCE_COMMON

# 5. 【全新】结构化衔接词库（相对位置特征专用，分5组）
## 总结类词汇 → 后方句子偏向CLAIM
SUMMARY_KW = {"综上所述", "由此可见", "故而", "总而言之", "因此", "所以"}
## 序列类词汇 → 后方句子偏向CLAIM（分论点）
SEQUENCE_KW = {"第一", "第二", "第三", "首先", "其次", "最后"}
## 原因类词汇 → 后方句子偏向EVIDENCE/EXPLANATION
CAUSE_KW = {"因为", "由于"}
## 结果类词汇 → 后方句子偏向CLAIM
RESULT_KW = {"所以", "因此", "于是", "故而"}
## 设问引导类词汇 → 后方句子偏向EXPLANATION
QUESTION_KW = {"是什么", "为什么", "何谓", "怎么是"}

# 所有结构化衔接词合并（用于位置检索）
ALL_STRUCT_KW = SUMMARY_KW | SEQUENCE_KW | CAUSE_KW | RESULT_KW | QUESTION_KW

# ====================================== 正则表达式（核心修复：定义句正则） ======================================
# 修复：删除行首锚点^，匹配句中任意位置的X是Y结构，解决定义句大面积漏判
PATTERN_DEFINITION_SENTENCE = re.compile(r"(.+?)(是|指的是|定义为)(.+)")

# ====================================== 阈值与枚举常量（全新：分角色满分+全局阈值） ======================================
# 全局有效阈值（五大角色最高分 < 该值 → 归类为OTHER）
GLOBAL_VALID_THRESHOLD = 2

# 每个角色独立理论满分（用于置信度计算，解决原置信度偏低问题）
SCORE_FULL = {
    "DEFINITION": 6,    # 定义关键词(4) + 词性(2) → 满分6
    "ATTACK": 5,        # 反驳关键词(3) + 词性(2) → 满分5
    "EVIDENCE": 5,      # 论据关键词(3) + 词性(2) → 满分5
    "CLAIM": 5,         # 论点关键词(3) + 词性(2) → 满分5
    "EXPLANATION": 4    # 无强关键词，词性(2)+位置(2) → 满分4
}

# 位置加分常量
POS_ABS_SCORE = 1     # 绝对位置加分（段落首尾）
POS_REL_SCORE = 1     # 相对结构化位置加分（统一+1）

# 六大句子角色枚举
ROLE_DEFINITION = "DEFINITION"    # 定义句
ROLE_ATTACK = "ATTACK"            # 反驳句
ROLE_EVIDENCE = "EVIDENCE"        # 论据句
ROLE_CLAIM = "CLAIM"              # 论点句
ROLE_EXPLANATION = "EXPLANATION"  # 解释句
ROLE_OTHER = "OTHER"              # 其他无意义句

# 论据细分类型枚举
EVI_TYPE_DATA = "EVIDENCE_DATA"
EVI_TYPE_CASE = "EVIDENCE_CASE"
EVI_TYPE_QUOTE = "EVIDENCE_QUOTE"
EVI_TYPE_INDUCE = "EVIDENCE_INDUCE"
EVI_TYPE_COMMON = "EVIDENCE_COMMON"

# 立场枚举
STANCE_PRO = "PRO"  # 正方
STANCE_CON = "CON"  # 反方