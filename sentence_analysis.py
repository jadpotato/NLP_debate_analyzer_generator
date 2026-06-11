# -*- coding: utf-8 -*-
"""
第二层：句子级基础分析层（修复版）
核心职责：对每个句子进行深度特征提取和角色分类，是解析层的核心基础
内部子模块：多角色独立打分 → 结构化位置特征叠加 → 角色择优判定 → 置信度计算 → 论据细分 → 立场标记
接口规范：严格遵循项目统一输入输出格式，与上下层无缝对接
依赖：jieba分词与词性标注（pip install jieba） + 全局config.py
"""
import jieba.posseg as pseg
from typing import List, Dict, Tuple, Optional
from config import (
    DEFINITION_KEYWORDS, STRONG_CLAIM_SIGNALS, TRUE_ATTACK_KW,
    ALL_EVIDENCE_KEYWORDS, EVIDENCE_DATA, EVIDENCE_CASE, EVIDENCE_QUOTE,
    EVIDENCE_INDUCE, EVIDENCE_COMMON, PATTERN_DEFINITION_SENTENCE,
    GLOBAL_VALID_THRESHOLD, SCORE_FULL, POS_ABS_SCORE, POS_REL_SCORE,
    SUMMARY_KW, SEQUENCE_KW, CAUSE_KW, RESULT_KW, QUESTION_KW,
    ROLE_DEFINITION, ROLE_ATTACK, ROLE_EVIDENCE, ROLE_CLAIM,
    ROLE_EXPLANATION, ROLE_OTHER,
    EVI_TYPE_DATA, EVI_TYPE_CASE, EVI_TYPE_QUOTE, EVI_TYPE_INDUCE, EVI_TYPE_COMMON,
    STANCE_PRO, STANCE_CON
)

# ====================================== 核心新增函数（按执行顺序） ======================================
def calc_single_role_score(text: str, pos: int, total_pos: int, target_role: str) -> int:
    """
    【核心新增1】单角色独立打分函数
    对单个句子，针对指定角色计算专属得分（共调用5次，分别计算5类角色分数）
    :param text: 单句文本
    :param pos: 句子绝对位置（段落内序号，从1开始）
    :param total_pos: 段落总句数
    :param target_role: 当前要计算的角色（ROLE_* 枚举）
    :return: 该角色当前得分（整数）
    """
    score = 0
    has_number = False
    has_proper_noun = False

    # 1. 词性特征（所有角色共享：数字/专有名词 +2分）
    words = pseg.cut(text)
    for _, flag in words:
        if flag == "m":
            has_number = True
        if flag in ["nr", "nz"]:
            has_proper_noun = True
    if has_number or has_proper_noun:
        score += 2

    # 2. 绝对位置特征（所有角色共享：段落首尾 +1分）
    if pos == 1 or pos == total_pos:
        score += POS_ABS_SCORE

    # 3. 分角色专属关键词打分
    if target_role == ROLE_DEFINITION:
        if any(kw in text for kw in DEFINITION_KEYWORDS):
            score += 4
    elif target_role == ROLE_ATTACK:
        # 仅对外反驳词加分，内部转折词不加分（根治立论误判ATTACK）
        if any(kw in text for kw in TRUE_ATTACK_KW):
            score += 3
    elif target_role == ROLE_EVIDENCE:
        # 数据论据场景过滤：仅包含"数据"无数字 → 不加分（解决"数据定义"误判）
        if "数据" in text and not has_number:
            pass
        elif any(kw in text for kw in ALL_EVIDENCE_KEYWORDS):
            score += 3
    elif target_role == ROLE_CLAIM:
        if any(kw in text for kw in STRONG_CLAIM_SIGNALS):
            score += 3
    elif target_role == ROLE_EXPLANATION:
        # 解释句无专属强关键词，仅靠位置/词性得分
        pass

    return score


def calc_relative_struct_score(text: str, prev_text: Optional[str]) -> Tuple[int, Dict[str, int]]:
    """
    【核心新增2】结构化相对位置加分函数
    检测前一句是否包含结构化衔接词，给当前句子对应角色定向加分
    :param text: 当前句子文本
    :param prev_text: 前一句文本（无前一句则为None）
    :return: (总加分, 各角色加分数典)
    """
    add_score = 0
    role_add = {
        ROLE_DEFINITION: 0,
        ROLE_ATTACK: 0,
        ROLE_EVIDENCE: 0,
        ROLE_CLAIM: 0,
        ROLE_EXPLANATION: 0
    }

    if not prev_text:
        return add_score, role_add

    # 匹配前一句的结构化衔接词类型
    if any(kw in prev_text for kw in SUMMARY_KW | SEQUENCE_KW | RESULT_KW):
        # 总结/序列/结果词 → 当前句偏向CLAIM
        role_add[ROLE_CLAIM] += POS_REL_SCORE
        add_score += POS_REL_SCORE
    elif any(kw in prev_text for kw in CAUSE_KW):
        # 原因词 → 当前句偏向EVIDENCE/EXPLANATION
        role_add[ROLE_EVIDENCE] += POS_REL_SCORE
        role_add[ROLE_EXPLANATION] += POS_REL_SCORE
        add_score += POS_REL_SCORE
    elif any(kw in prev_text for kw in QUESTION_KW):
        # 设问词 → 当前句偏向EXPLANATION
        role_add[ROLE_EXPLANATION] += POS_REL_SCORE
        add_score += POS_REL_SCORE

    return add_score, role_add


def get_max_role_from_scores(score_dict: Dict[str, int]) -> Tuple[str, int, List[int]]:
    """
    【核心新增3】多角色择优判定函数
    接收5个角色的得分，选出分数最高的角色；所有分数<全局阈值则归为OTHER
    :param score_dict: 五大角色得分字典 {"DEFINITION":4, "ATTACK":1, ...}
    :return: (最终角色, 最高分, 全量分数列表)
    """
    all_scores = list(score_dict.values())
    max_score = max(all_scores) if all_scores else 0

    # 所有分数低于全局阈值 → 归为OTHER
    if max_score < GLOBAL_VALID_THRESHOLD:
        return ROLE_OTHER, max_score, all_scores

    # 同分按优先级兜底：DEFINITION > ATTACK > EVIDENCE > CLAIM > EXPLANATION
    priority = [ROLE_DEFINITION, ROLE_ATTACK, ROLE_EVIDENCE, ROLE_CLAIM, ROLE_EXPLANATION]
    for role in priority:
        if score_dict[role] == max_score:
            return role, max_score, all_scores

    return ROLE_OTHER, max_score, all_scores


def calc_confidence_new(final_role: str, max_score: int, all_scores: List[int]) -> float:
    """
    【核心新增4】新置信度计算函数
    :param final_role: 最终判定角色
    :param max_score: 该角色最高分
    :param all_scores: 五大角色全量分数列表
    :return: 置信度（保留2位小数）
    """
    if final_role == ROLE_OTHER:
        # OTHER置信度：1 - 五大角色分数平均值
        avg_score = sum(all_scores) / len(all_scores)
        confidence = 1 - avg_score
    else:
        # 有效角色置信度：当前得分 / 该角色理论满分
        confidence = max_score / SCORE_FULL[final_role]

    return round(min(confidence, 1.0), 2)

# ====================================== 保留&重构原有函数 ======================================
def classify_sentence_role(sentence: Dict) -> Dict:
    """
    【重构】角色判定主函数（原函数全逻辑替换）
    输入：预处理后的句子字典（新增prev_text字段）
    输出：新增role、confidence、role_scores、struct_hit字段的句子字典
    """
    text = sentence["text"]
    pos = sentence["position"]
    total_pos = sentence["total_sentences"]
    prev_text = sentence.get("prev_text", None)

    # 1. 计算五大角色基础得分
    score_dict = {
        ROLE_DEFINITION: calc_single_role_score(text, pos, total_pos, ROLE_DEFINITION),
        ROLE_ATTACK: calc_single_role_score(text, pos, total_pos, ROLE_ATTACK),
        ROLE_EVIDENCE: calc_single_role_score(text, pos, total_pos, ROLE_EVIDENCE),
        ROLE_CLAIM: calc_single_role_score(text, pos, total_pos, ROLE_CLAIM),
        ROLE_EXPLANATION: calc_single_role_score(text, pos, total_pos, ROLE_EXPLANATION)
    }

    # 2. 叠加结构化相对位置加分
    _, role_add = calc_relative_struct_score(text, prev_text)
    for role in score_dict:
        score_dict[role] += role_add[role]

    # 3. 择优判定最终角色
    final_role, max_score, all_scores = get_max_role_from_scores(score_dict)

    # 4. 计算新置信度
    confidence = calc_confidence_new(final_role, max_score, all_scores)

    # 5. 写入结果
    sentence["role_scores"] = score_dict
    sentence["struct_hit"] = list(role_add.keys())[0] if sum(role_add.values()) > 0 else ""
    sentence["role"] = final_role
    sentence["confidence"] = confidence

    return sentence


def classify_evidence_type(sentence_with_role: Dict) -> Dict:
    """
    【保留不变】细分论据类型（仅对EVIDENCE角色生效）
    """
    role = sentence_with_role["role"]
    text = sentence_with_role["text"]
    evi_type = None

    if role == ROLE_EVIDENCE:
        if any(kw in text for kw in EVIDENCE_DATA):
            evi_type = EVI_TYPE_DATA
        elif any(kw in text for kw in EVIDENCE_CASE):
            evi_type = EVI_TYPE_CASE
        elif any(kw in text for kw in EVIDENCE_QUOTE):
            evi_type = EVI_TYPE_QUOTE
        elif any(kw in text for kw in EVIDENCE_INDUCE):
            evi_type = EVI_TYPE_INDUCE
        elif any(kw in text for kw in EVIDENCE_COMMON):
            evi_type = EVI_TYPE_COMMON

    sentence_with_role["evi_type"] = evi_type
    return sentence_with_role


def mark_sentence_stance(sentence_with_evi_type: Dict, global_stance: str) -> Dict:
    """
    【保留不变】标记句子所属立场
    """
    sentence_with_evi_type["stance"] = global_stance
    return sentence_with_evi_type

# ====================================== 对外批量处理主函数（接口不变，内部逻辑更新） ======================================
def analyze_sentence_list(
    preprocessed_sentences: List[Dict],
    global_stance: str = STANCE_PRO
) -> List[Dict]:
    """
    句子级分析流水线：一站式完成所有子模块处理
    【接口不变】输入输出格式与原版本完全一致，向下兼容
    :param preprocessed_sentences: preprocess.py输出的预处理句子列表
    :param global_stance: 全局立场（PRO/CON）
    :return: 完整的句子分析结果列表
    """
    analyzed_results = []
    n = len(preprocessed_sentences)

    for i in range(n):
        sentence = preprocessed_sentences[i].copy()
        # 新增：记录前一句文本（用于相对位置特征计算）
        sentence["prev_text"] = preprocessed_sentences[i-1]["text"] if i > 0 else None

        # 按顺序执行子模块
        step1 = classify_sentence_role(sentence)
        step2 = classify_evidence_type(step1)
        step3 = mark_sentence_stance(step2, global_stance)
        analyzed_results.append(step3)

    return analyzed_results

# ====================================== 双测试用例（保留不变，验证修复效果） ======================================
if __name__ == "__main__":
    # 导入预处理模块
    from preprocess import preprocess_pipeline

    # ------------------------------ 测试用例1：黄执中 正方 意义的解构 ------------------------------
    print("\n" + "="*120)
    print("【测试用例1】黄执中《当今时代，我们更需要意义的解构还是建构》正方立论")
    print("="*120)
    test_text1 = """
好，咱们废话不多说直接进入辩题。来，首先你要知道，如果这个题目在二十年前我打比赛的时候，我一定会把重点放在数据定义上，所谓什么叫当今时代。对啊，因为限缩战场，锁定讨论空间可以提高胜率。在座的所有打辩论的人都知道，跟我一样。只不过现在我打辩论的时候我会有一点点小小的私心，因为我会希望这场比赛，无论是三年后，五年后，时过境迁后再回来看，依然能有价值。所以在今天的辩论当中，我不会去定义什么叫当今时代，事实上等一下反方不管怎么定义什么叫当今时代，我也全部接受，不会任何反驳。因为在今天的辩论当中，我给我自己设定的目标是要去论证所有时代。OK来，回到今天的辩论。那在今天的辩论当中，这场辩题，当今时代我们更需要意义的解构还是建构，这个辩论要能够成立，它就意味着我们今天在场的所有人，我们都同意这是一个辩题。哎，不要以为这是一句废话，因为在这一句简单的废话后面其实大有讲究。是的，让我们来想一下，是什么让今天的辩题成为可能？要让今天的辩题成为可能，它意味着我们都同意这个辩题并不存在着一个单一、绝对且不可动摇的答案，否则我们就不会浪费时间在这里了，对不对？就像是哪怕我今天要辩论黄执中是男的还是女的？当这句话成为一个辩题的同时就代表着我们打算而且我们愿意，重新去拆解传统上对于男跟女的概念，才会让这个辩论成为可能。换言之，面对辩题，我们所有人在场的辩论人，我们都抱有一个很有意思的共识就是我们对唯一性的质疑。是的，我们相信答案不止一个，或者说我们相信答案还有待商榷，这种对唯一性的质疑其实就是解构的第一个核心精神，我们不将任何立场视为最终而且绝对的权威。
那再来，我们回到辩题。当今时代我们更需要意义的建构还是解构，这一场辩论要成立的第二个条件是什么呢？来，在座的各位，你们在今天这场辩论当中，你们允许正方获胜吗？你们允许反方获胜吗？你们允许最后的结果跟你心里想的不一样吗？可能人听到会觉得很奇怪，这不是很简单，怎么会不允许呢？是的，不要以为很简单哦，因为在真实世界当中有很多人是做不到的哦。来，我们来想一件事情，是什么让各位的态度成为可能？是的，在辩论开始之前，我们不知道正方赢还是反方胜，甚至在听完辩论后，也可能各自会有不同的结论，但无论如何，我们都相信辩论开始的这一刻，就代表着问题的答案得要在相互的讨论之后才能形成。而且这个结论很有可能是一个暂时性的结论，这意味着什么？这意味着，我们都相信答案的暂时性。是的，不同的情况，不同的视角，同一个问题，永远结论未定，而这种态度就是解构的第二个核心精神，意义是会随着脉络而改变的，意义是会随着脉络而展现不同的面貌的，没有固定不同的结论。
再回到辩题，是的，我们今天正方两方，但凡要论证己方的辩题其实都是一个建构的过程。现在如果我讲完了，待会会轮到熊浩，听完我对正方的建构之后，你们会听到不同的说法，我的建构会面对来自反方的质疑。来，在座的各位，你们会希望我面对这些质疑吗？当立场与我不同的熊浩要表达看法的时候，你们会愿意给熊浩掌声吗？还是你们会希望今天这场辩论根本就不要存在有正方还是根本就不要存在有反方吗？可能很多人说:“当然不会呀。”对不对？是的，因为我们就要讨论下一个，是什么让你刚才的这种需求成为可能，这种需求是很独特的，不要以为这是一个常识，因为在现实生活中的确是很多人没有你们刚才这种需求的，它的确是会希望只有一个持方存在，而让另外一方闭嘴的，而我们所有打辩论的人却都了解，真正有价值的讨论其实是一个相互依存的过程。什么叫相互依存？就是正方的合理性一定要靠反方的质疑才能彰显嘛，这不是最简单的常识嘛？反方的正确得要通过正方的对照才得以呈现嘛，对不对？所以没有了你(反方)，我(正方)就没有价值，没有了我，你也没价值。任何一方的主张都需要通过对照跟质疑才使其更完整。而这个简单的概念其实就是什么意思？就是我们接受叙事对抗。这是解构的第三个核心要件。辩论的本质就是一个叙事对抗的剧场，在这个剧场当中，正反双方会不断透过拆解去寻找新的观点与视角。而所有在场的观众，你们会同时接受这一切，并且在这个过程中，毕竟双方是如何呈现，因而形成对议题的更深入的理解，而不仅仅是单纯的选边战，对不对？
所以各位，光是今天这个辩题的存在，光是我们要坐在这里，讨论今天这个辩题，它就意味着在我们正方双方开始建构之前，所有人包含正方双方，我们都怀疑答案的唯一性，我们都能够接受答案是暂时的，而且我们乐于看到叙事对抗。而在这个过程当中，我跟你们讲，不要小看这件事，可能对于打辩论的人而言，这是理所当然。可是相反地，无论在任何时代里，我们还会看见另一种人，都有一些人，他会推崇答案的唯一性，他不愿意有别人来冒犯自己的答案；他们会相信答案是放之四海而皆准的，他讨厌有人不承认我的这个答案；他会认为人们更需要的是被宣传而不是争辩。所以，来，我们更需要哪一种？什么叫更需要，在座的各位，你们更想听宣传，还是更想听辩论，如果今天有人说：“今天这个辩题几年前我听过人家辩论过了，当时是反方赢，所以这个辩题再也不用再讨论了。”在座的各位，听到这种说法，你们会怎么看？而如果又有人说：“这个辩题，我只站正方，让反方给我闭嘴。”你们会不会附和他？又或者，无论在任何时代，你们会希望哪种人更多一点？
    """
    # 执行流水线
    preprocessed1 = preprocess_pipeline(test_text1)
    analyzed1 = analyze_sentence_list(preprocessed1, global_stance=STANCE_PRO)
    # 打印结果
    print(f"预处理完成，共得到 {len(analyzed1)} 条有效句子")
    print(f"{'序号':<4} {'角色':<14} {'置信度':<8} {'论据类型':<18} {'文本'}")
    print("-"*120)
    for idx, item in enumerate(analyzed1, 1):
        role = item["role"]
        confidence = f"{item['confidence']:.2f}"
        evi_type = item["evi_type"] if item["evi_type"] else "-"
        text = item["text"][:50] + "..." if len(item["text"]) > 50 else item["text"]
        print(f"{idx:<4} {role:<14} {confidence:<8} {evi_type:<18} {text}")
    # 统计角色分布
    print("\n【角色分布统计】")
    role_count1 = {}
    for item in analyzed1:
        role_count1[item["role"]] = role_count1.get(item["role"], 0) + 1
    for role, count in role_count1.items():
        print(f"{role}: {count} 条")

    # ------------------------------ 测试用例2：马薇薇 正方 爱美之于女性 ------------------------------
    print("\n" + "="*120)
    print("【测试用例2】马薇薇《爱美之于女性是不是一种自由》正方立论")
    print("="*120)
    test_text2 = """
爱美之于女性是不是一种自由？这个辩题出现的第一个瞬间，我反应的是爱美之于男性是不是一种自由呢？
如果爱美之于女性是一种不自由，那至于男性到底是自由还是不自由呢？
如果它是针对女性的特定议题，而男性毋须讨论的话，我无法接受陈铭还没有说话，就天然比我多了一种自由。
第二，不爱美之于女性是不是一种自由，对不对？
因为如果爱美是一种自由，那不爱美是不是一种自由呢？
如果不爱美至于女性是一种自由的话，那爱美之于女性就是一种积极自由，当不爱美成为一种消极自由的时候，爱美作为积极自由，这两种自由的内核是否是对抗的，对不对？
如果你爱了美，那这个时候又妨碍了不爱美那帮人什么事儿，对不对？
我爱我美，难道影响你不爱美了吗？我们俩都不在一个赛道上，朋友.
所以这两个问题引发了我的思考，故而我方给出了三点原因。
第一，对爱的解读，爱是什么？
爱是一种有主体性的天然动作。
爱是英文的爱，就是我要是主体的时候，我才拥有爱的权利和爱的能力，对不对？
它不是一个被动作，它是人之追求。
第二叫做美的多元性。
你可以不爱我这种美，但你能不能爱另一种美呢？
美与美之间能不能做到美？美美与共，各美其美，我认为是可以的，所以爱美这个动作第一具备主体性，第二具备多元性。
好，那么一个同时具备主体性和多元性的追求新行为，为什么加上了女性这个词，忽然就变成了一种不自由呢？
我们就要谈到第三的概念叫做什么是自由？
抑或是网上热议的自由？
有没有向上和向下之分，对不对？
而我方的观点是，自由无上下，无高级，各有其追求，用自己对于自由的定义去定义他人行为的不自由，反而会形成一副枷锁。
你可以自由你的，我可以自由我的，所以自由不分上下高低，它本身就是一个平等的状态，所以这里面向下的自由显然也不是我们要讨论的议题。
综上所述，爱美之于女性，有主动性，有多元性，同时具有平等性，所以我方得正。
    """
    # 执行流水线
    preprocessed2 = preprocess_pipeline(test_text2)
    analyzed2 = analyze_sentence_list(preprocessed2, global_stance=STANCE_PRO)
    # 打印结果
    print(f"预处理完成，共得到 {len(analyzed2)} 条有效句子")
    print(f"{'序号':<4} {'角色':<14} {'置信度':<8} {'论据类型':<18} {'文本'}")
    print("-"*120)
    for idx, item in enumerate(analyzed2, 1):
        role = item["role"]
        confidence = f"{item['confidence']:.2f}"
        evi_type = item["evi_type"] if item["evi_type"] else "-"
        text = item["text"][:50] + "..." if len(item["text"]) > 50 else item["text"]
        print(f"{idx:<4} {role:<14} {confidence:<8} {evi_type:<18} {text}")
    # 统计角色分布
    print("\n【角色分布统计】")
    role_count2 = {}
    for item in analyzed2:
        role_count2[item["role"]] = role_count2.get(item["role"], 0) + 1
    for role, count in role_count2.items():
        print(f"{role}: {count} 条")
    print("="*120)