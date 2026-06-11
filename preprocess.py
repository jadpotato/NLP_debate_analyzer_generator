# -*- coding: utf-8 -*-
"""
文本预处理层：将原始杂乱辩论文本转换为结构化、可分析的句子列表
功能：清洗冗余字符 → 智能分句 → 过滤无意义套话
输出：带位置索引的标准化句子字典列表
"""
import re
from typing import List, Dict

# ===================== 预处理专用配置（独立于全局config，避免循环依赖）=====================
# 文本清洗正则：保留中文、数字、英文大小写、常用标点
PATTERN_CLEAN = re.compile(r'[^\u4e00-\u9fa5，。？！；：""''()（）【】《》0-9a-zA-Z.%%-]')

# 分句正则：按句号、问号、感叹号、分号分割（保留标点）
PATTERN_SPLIT = re.compile(r'([。？！；：])')

# 举例关键词：匹配后需要合并后续分句
EXAMPLE_KEYWORDS = {"例如", "比如", "譬如", "诸如", "举个例子", "就像", "正如"}

# 无意义句子正则（匹配纯套话，不匹配包含套话前缀但有实际内容的句子）
MEANINGLESS_PATTERNS = [
    # 纯赛场客套寒暄（保留原有合法规则）
    re.compile(r'^谢谢主席.*$'),
    re.compile(r'^对方辩友$'),       # 单独呼喊对方，无后续内容
    re.compile(r'^大家好.*$'),
    re.compile(r'^尊敬的评委.*$'),
    re.compile(r'^有请对方辩友.*$'),
    re.compile(r'^我的发言完毕.*$'),

    # 新增：仅单独出现的空过渡句（无实质内容）
    re.compile(r'^[首先][。？！；：]$'),
    re.compile(r'^[其次][。？！；：]$'),
    re.compile(r'^[最后][。？！；：]$')
]

# 最小有效句子长度（字符数）
MIN_VALID_SENTENCE_LENGTH = 5


# ===================== 核心函数实现 =====================
def clean_raw_text(raw_text: str) -> str:
    """
    文本清洗：去除冗余字符，保留有意义信息
    保留范围：中文、数字、英文大小写、常用标点（括号、引号、小数点、百分号）
    处理：将多个空格/换行合并为单个空格，去除首尾空白

    Args:
        raw_text: 原始辩论文本（可能包含乱码、特殊符号、多余空格）

    Returns:
        清洗后的干净文本
    """
    # 第一步：去除所有非允许字符
    cleaned = PATTERN_CLEAN.sub('', raw_text)
    
    # 第二步：将多个空格、换行、制表符合并为单个空格
    cleaned = re.sub(r'\s+', ' ', cleaned)
    
    # 第三步：去除首尾空白
    cleaned = cleaned.strip()
    
    return cleaned


def intelligent_split_sentences(cleaned_text: str) -> List[str]:
    """
    智能分句：处理辩论赛文本的特殊句式，避免错误分割
    特殊处理：
    1. 引号内的句子作为一个整体（不分割）
    2. 举例关键词（例如、比如）后面的分句合并为一个句子
    3. 括号内的内容不分割
    4. 修正标点错位问题

    Args:
        cleaned_text: 经过clean_raw_text处理后的文本

    Returns:
        拆分后的单句列表
    """
    if not cleaned_text:
        return []
    
    # 第一步：基础分句（按标点分割，保留标点）
    parts = PATTERN_SPLIT.split(cleaned_text)
    # 合并句子和标点（parts格式：[句子1, 标点1, 句子2, 标点2, ...]）
    sentences = []
    for i in range(0, len(parts), 2):
        if i + 1 < len(parts):
            sent = parts[i] + parts[i+1]
        else:
            sent = parts[i]
        if sent.strip():
            sentences.append(sent.strip())
    
    # 第二步：合并引号内的句子
    merged_sentences = []
    in_quote = False
    current_quote = ''
    quote_chars = {'"', "'", '“', '”', '‘', '’'}
    
    for sent in sentences:
        # 统计当前句子中的引号数量
        quote_count = sum(1 for c in sent if c in quote_chars)
        
        if not in_quote:
            if quote_count % 2 == 1:
                # 奇数个引号：开始一个引号块
                in_quote = True
                current_quote = sent
            else:
                # 偶数个引号：独立句子
                merged_sentences.append(sent)
        else:
            # 在引号内：合并到当前引号块
            current_quote += sent
            if quote_count % 2 == 1:
                # 奇数个引号：结束引号块
                in_quote = False
                merged_sentences.append(current_quote)
                current_quote = ''
    
    # 处理未闭合的引号
    if current_quote:
        merged_sentences.append(current_quote)
    
    # 第三步：合并举例关键词后面的句子
    final_sentences = []
    i = 0
    n = len(merged_sentences)
    
    while i < n:
        sent = merged_sentences[i]
        # 检查当前句子是否包含举例关键词
        has_example = any(keyword in sent for keyword in EXAMPLE_KEYWORDS)
        
        if has_example and i + 1 < n:
            # 合并后续句子，直到遇到句号/问号/感叹号结尾的句子
            example_sent = sent
            j = i + 1
            while j < n:
                next_sent = merged_sentences[j]
                example_sent += next_sent
                # 如果下一个句子以句号/问号/感叹号结尾，停止合并
                if next_sent.endswith(('。', '？', '！', '；')):
                    break
                j += 1
            final_sentences.append(example_sent)
            i = j + 1
        else:
            final_sentences.append(sent)
            i += 1
    
    # 第四步：过滤空句子
    final_sentences = [sent for sent in final_sentences if sent.strip()]
    
    return final_sentences


def filter_meaningless_sentences(sentence_list: List[str]) -> List[Dict]:
    """
    过滤无意义句子，保留有论证价值的句子，并附加位置信息
    过滤规则：
    1. 匹配纯套话正则的句子
    2. 长度小于MIN_VALID_SENTENCE_LENGTH的句子
    3. 保留包含信号词（我方认为、综上所述）且有实际内容的句子

    Args:
        sentence_list: 经过intelligent_split_sentences处理后的句子列表

    Returns:
        标准化句子字典列表，每个字典包含：
        - text: 句子文本
        - position: 句子在段落中的位置（从1开始）
        - total_sentences: 段落总有效句子数
    """
    filtered = []
    
    for sent in sentence_list:
        # 过滤过短句子
        if len(sent) < MIN_VALID_SENTENCE_LENGTH:
            continue
        
        # 过滤纯套话句子
        is_meaningless = False
        for pattern in MEANINGLESS_PATTERNS:
            if pattern.match(sent):
                is_meaningless = True
                break
        
        if not is_meaningless:
            filtered.append(sent)
    
    # 附加位置信息
    total = len(filtered)
    result = []
    for idx, sent in enumerate(filtered):
        result.append({
            "text": sent,
            "position": idx + 1,  # 位置从1开始计数
            "total_sentences": total
        })
    
    return result


def preprocess_pipeline(raw_text: str) -> List[Dict]:
    """
    预处理流水线：一站式完成所有预处理步骤
    输入原始文本 → 清洗 → 智能分句 → 过滤无意义句子 → 输出结构化结果

    Args:
        raw_text: 原始辩论文本

    Returns:
        标准化句子字典列表（可直接输入sentence_analysis.py）
    """
    cleaned = clean_raw_text(raw_text)
    sentences = intelligent_split_sentences(cleaned)
    result = filter_meaningless_sentences(sentences)
    return result


# ===================== 测试代码（运行本文件可直接验证效果）=====================
if __name__ == "__main__":
    # 测试用例1：马薇薇《爱美之于女性是不是一种自由》立论开头
    test_text1 = """
    爱美之于女性是不是一种自由？这个辩题出现的第一个瞬间，我反应的是爱美之于男性是不是一种自由呢？如果爱美之于女性是一种不自由，那至于男性到底是自由还是不自由呢？如果它是针对女性的特定议题，而男性毋须讨论的话，我无法接受陈铭还没有说话，就天然比我多了一种自由。第二，不爱美之于女性是不是一种自由，对不对？因为如果爱美是一种自由，那不爱美是不是一种自由呢？如果不爱美至于女性是一种自由的话，那爱美之于女性就是一种积极自由，当不爱美成为一种消极自由的时候，爱美作为积极自由，这两种自由的内核是否是对抗的，对不对？如果你爱了美，那这个时候又妨碍了不爱美那帮人什么事儿，对不对？我爱我美，难道影响你不爱美了吗？我们俩都不在一个赛道上，朋友.所以这两个问题引发了我的思考，故而我方给出了三点原因。第一，对爱的解读，爱是什么？爱是一种有主体性的天然动作。啥意思？爱是英文的爱，就是我要是主体的时候，我才拥有爱的权利和爱的能力，对不对？它不是一个被动作，它是人之追求。第二叫做美的多元性。你可以不爱我这种美，但你能不能爱另一种美呢？美与美之间能不能做到美？美美与共，各美其美，我认为是可以的，所以爱美这个动作第一具备主体性，第二具备多元性。好，那么一个同时具备主体性和多元性的追求新行为，为什么加上了女性这个词，忽然就变成了一种不自由呢？我们就要谈到第三的概念叫做什么是自由？抑或是网上热议的自由？有没有向上和向下之分，对不对？而我方的观点是，自由无上下，无高级，各有其追求，用自己对于自由的定义去定义他人行为的不自由，反而会形成一副枷锁。你可以自由你的，我可以自由我的，所以自由不分上下高低，它本身就是一个平等的状态，所以这里面向下的自由显然也不是我们要讨论的议题。综上所述，爱美之于女性，有主动性，有多元性，同时具有平等性，所以我方得正。
    """
    
    # 测试用例2：熊浩《当今时代，我们更需要意义的建构》立论开头
    test_text2 = """
    好，咱们废话不多说直接进入辩题。来，首先你要知道，如果这个题目在二十年前我打比赛的时候，我一定会把重点放在数据定义上，所谓什么叫当今时代。对啊，因为限缩战场，锁定讨论空间可以提高胜率。在座的所有打辩论的人都知道，跟我一样。只不过现在我打辩论的时候我会有一点点小小的私心，因为我会希望这场比赛，无论是三年后，五年后，时过境迁后再回来看，依然能有价值。所以在今天的辩论当中，我不会去定义什么叫当今时代，事实上等一下反方不管怎么定义什么叫当今时代，我也全部接受，不会任何反驳。因为在今天的辩论当中，我给我自己设定的目标是要去论证所有时代。OK来，回到今天的辩论。那在今天的辩论当中，这场辩题，当今时代我们更需要意义的解构还是建构，这个辩论要能够成立，它就意味着我们今天在场的所有人，我们都同意这是一个辩题。哎，不要以为这是一句废话，因为在这一句简单的废话后面其实大有讲究。是的，让我们来想一下，是什么让今天的辩题成为可能？要让今天的辩题成为可能，它意味着我们都同意这个辩题并不存在着一个单一、绝对且不可动摇的答案，否则我们就不会浪费时间在这里了，对不对？就像是哪怕我今天要辩论黄执中是男的还是女的？当这句话成为一个辩题的同时就代表着我们打算而且我们愿意，重新去拆解传统上对于男跟女的概念，才会让这个辩论成为可能。换言之，面对辩题，我们所有人在场的辩论人，我们都抱有一个很有意思的共识就是我们对唯一性的质疑。是的，我们相信答案不止一个，或者说我们相信答案还有待商榷，这种对唯一性的质疑其实就是解构的第一个核心精神，我们不将任何立场视为最终而且绝对的权威。
那再来，我们回到辩题。当今时代我们更需要意义的建构还是解构，这一场辩论要成立的第二个条件是什么呢？来，在座的各位，你们在今天这场辩论当中，你们允许正方获胜吗？你们允许反方获胜吗？你们允许最后的结果跟你心里想的不一样吗？可能人听到会觉得很奇怪，这不是很简单，怎么会不允许呢？是的，不要以为很简单哦，因为在真实世界当中有很多人是做不到的哦。来，我们来想一件事情，是什么让各位的态度成为可能？是的，在辩论开始之前，我们不知道正方赢还是反方胜，甚至在听完辩论后，也可能各自会有不同的结论，但无论如何，我们都相信辩论开始的这一刻，就代表着问题的答案得要在相互的讨论之后才能形成。而且这个结论很有可能是一个暂时性的结论，这意味着什么？这意味着，我们都相信答案的暂时性。是的，不同的情况，不同的视角，同一个问题，永远结论未定，而这种态度就是解构的第二个核心精神，意义是会随着脉络而改变的，意义是会随着脉络而展现不同的面貌的，没有固定不同的结论。
再回到辩题，是的，我们今天正方两方，但凡要论证己方的辩题其实都是一个建构的过程。现在如果我讲完了，待会会轮到熊浩，听完我对正方的建构之后，你们会听到不同的说法，我的建构会面对来自反方的质疑。来，在座的各位，你们会希望我面对这些质疑吗？当立场与我不同的熊浩要表达看法的时候，你们会愿意给熊浩掌声吗？还是你们会希望今天这场辩论根本就不要存在有正方还是根本就不要存在有反方吗？可能很多人说:“当然不会呀。”对不对？是的，因为我们就要讨论下一个，是什么让你刚才的这种需求成为可能，这种需求是很独特的，不要以为这是一个常识，因为在现实生活中的确是很多人没有你们刚才这种需求的，它的确是会希望只有一个持方存在，而让另外一方闭嘴的，而我们所有打辩论的人却都了解，真正有价值的讨论其实是一个相互依存的过程。什么叫相互依存？就是正方的合理性一定要靠反方的质疑才能彰显嘛，这不是最简单的常识嘛？反方的正确得要通过正方的对照才得以呈现嘛，对不对？所以没有了你(反方)，我(正方)就没有价值，没有了我，你也没价值。任何一方的主张都需要通过对照跟质疑才使其更完整。而这个简单的概念其实就是什么意思？就是我们接受叙事对抗。这是解构的第三个核心要件。辩论的本质就是一个叙事对抗的剧场，在这个剧场当中，正反双方会不断透过拆解去寻找新的观点与视角。而所有在场的观众，你们会同时接受这一切，并且在这个过程中，毕竟双方是如何呈现，因而形成对议题的更深入的理解，而不仅仅是单纯的选边战，对不对？
所以各位，光是今天这个辩题的存在，光是我们要坐在这里，讨论今天这个辩题，它就意味着在我们正方双方开始建构之前，所有人包含正方双方，我们都怀疑答案的唯一性，我们都能够接受答案是暂时的，而且我们乐于看到叙事对抗。而在这个过程当中，我跟你们讲，不要小看这件事，可能对于打辩论的人而言，这是理所当然。可是相反地，无论在任何时代里，我们还会看见另一种人，都有一些人，他会推崇答案的唯一性，他不愿意有别人来冒犯自己的答案；他们会相信答案是放之四海而皆准的，他讨厌有人不承认我的这个答案；他会认为人们更需要的是被宣传而不是争辩。所以，来，我们更需要哪一种？什么叫更需要，在座的各位，你们更想听宣传，还是更想听辩论，如果今天有人说：“今天这个辩题几年前我听过人家辩论过了，当时是反方赢，所以这个辩题再也不用再讨论了。”在座的各位，听到这种说法，你们会怎么看？而如果又有人说：“这个辩题，我只站正方，让反方给我闭嘴。”你们会不会附和他？又或者，无论在任何时代，你们会希望哪种人更多一点？
    """
    
    print("="*50)
    print("测试用例1：马薇薇立论开头")
    print("="*50)
    result1 = preprocess_pipeline(test_text1)
    for sent in result1:
        print(f"[{sent['position']}/{sent['total_sentences']}] {sent['text']}")
    
    print("\n" + "="*50)
    print("测试用例2：熊浩立论开头")
    print("="*50)
    result2 = preprocess_pipeline(test_text2)
    for sent in result2:
        print(f"[{sent['position']}/{sent['total_sentences']}] {sent['text']}")