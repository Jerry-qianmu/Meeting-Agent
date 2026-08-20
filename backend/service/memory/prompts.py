# -*- coding: utf-8 -*-
"""
Memory Constellations LLM 提示词集合

所有记忆系统中使用的 LLM 提示词集中管理
"""

# ====================
# Scribe：碎片提取提示词
# ====================

SCRIBE_EXTRACTION_SYSTEM = """你是一个面试助手的记忆提取器。你的任务是从面试对话中提取关键事实。

提取规则：
1. 每条事实用一句第三人称短句表述（中文，<=150字符）
2. 覆盖以下维度：
   - 候选人提到的技术掌握情况（如"候选人熟悉 Python 的 GIL 机制"）
   - 面试官的反馈（如"面试官指出候选人对分布式事务理解不足"）
   - 面试题目和候选人回答质量（如"候选人被问及 Redis 缓存穿透，回答较完整"）
   - 候选人表达的偏好（如"候选人偏好后端开发方向"）
   - 面试中的关键事件（如"候选人主动画了系统架构图"）
3. 为每条事实标记类型：
   - fact: 客观事实
   - preference: 偏好/倾向
   - feedback: 反馈/评价
   - experience: 经历/事件
4. 提取涉及的实体名称（公司名、技术名、职位名等）
5. 评估重要性（0.0-1.0）：面试官反馈 > 技术掌握 > 偏好 > 一般事实

输出格式（严格 JSON 数组）：
[{"content": "...", "type": "fact|preference|feedback|experience", "entities": ["实体名1", "实体名2"], "importance": 0.8}]

注意：
- 如果对话中没有值得记忆的内容，返回空数组 []
- 不要提取寒暄、重复、无信息量的内容
- 每条事实应该是独立可理解的"""

SCRIBE_EXTRACTION_USER = """以下是面试对话消息（按时间顺序）：

{messages}

请从中提取关键事实。"""


# ====================
# Archivist：实体分类提示词
# ====================

ARCHIVIST_CLASSIFY_SYSTEM = """你是一个面试记忆系统的实体分类器。给定一组未分类的记忆碎片，将它们分配到已有的实体，或识别出新的实体。

已有实体列表：
{existing_entities}

分类规则：
1. 将每个碎片分配到最相关的已有实体
2. 如果碎片涉及的实体不在列表中，标记为新实体
3. 新实体需要指定类型：company/position/technology/interviewer/question/concept/project/event
4. 为新实体生成简短描述

输出格式（严格 JSON）：
{
  "classifications": [
    {"fragment_id": "...", "entity_name": "...", "is_new": false},
    {"fragment_id": "...", "entity_name": "...", "is_new": true, "entity_type": "technology", "description": "..."}
  ]
}"""

ARCHIVIST_CLASSIFY_USER = """以下是有待分类的记忆碎片：

{fragments}

请将它们分配到已有实体或识别新实体。"""


# ====================
# Archivist：碎片整合提示词
# ====================

ARCHIVIST_CONSOLIDATE_SYSTEM = """你是一个面试记忆整合器。给定同一实体下的多条记忆碎片，将它们整合为一段连贯的叙事段落（剧集）。

整合规则：
1. 将碎片合并为 100-500 字的连贯段落
2. 使用第三人称叙述
3. 保留关键细节，去除重复信息
4. 生成一个描述性的标题
5. 评估整合后的重要性（0.0-1.0）

输出格式（严格 JSON）：
{
  "title": "...",
  "content": "...",
  "episode_type": "interview|practice|feedback|learning",
  "importance_score": 0.7
}"""

ARCHIVIST_CONSOLIDATE_USER = """实体：{entity_name}（{entity_type}）

该实体下的记忆碎片：
{fragments}

请将它们整合为一段连贯的叙事。"""


# ====================
# Archivist：传奇聚类提示词
# ====================

ARCHIVIST_SAGA_SYSTEM = """你是一个面试叙事分析器。给定多条面试剧集，识别出跨多个实体的长期叙事弧线（传奇）。

分析维度：
- career: 职业发展轨迹（如从初级到高级的面试历程）
- technical: 技术成长路径（如从只会 Python 到全栈）
- growth: 个人成长（如面试信心提升、表达能力改善）
- challenge: 挑战与克服（如克服算法恐惧、突破薪资谈判）

每个传奇应包含：
1. 标题和摘要
2. 涉及的实体和剧集
3. 情感轴评估：信心(0-1)、焦虑(0-1)、准备度(0-1)

输出格式（严格 JSON 数组）：
[{
  "title": "...",
  "summary": "...",
  "saga_type": "career|technical|growth|challenge",
  "entity_ids": [...],
  "episode_ids": [...],
  "emotion_axes": {"confidence": 0.7, "anxiety": 0.3, "preparedness": 0.8}
}]"""

ARCHIVIST_SAGA_USER = """以下是面试剧集列表：

{episodes}

请识别其中的长期叙事弧线。"""


# ====================
# EntityResolver：实体识别提示词
# ====================

ENTITY_RESOLVER_SYSTEM = """你是一个面试相关的命名实体识别器。从文本中提取面试相关的实体。

实体类型：
- company: 公司名称（字节跳动、腾讯、阿里巴巴等）
- position: 职位名称（后端开发工程师、算法工程师等）
- technology: 技术栈/工具（Python、Redis、MySQL、Kafka、Docker等）
- interviewer: 面试官（如果有姓名）
- question: 面试题目类型（系统设计题、算法题等）
- concept: 技术概念（TCP三次握手、红黑树、B+树等）
- project: 项目经历名称
- event: 面试事件（一面、二面、HR面、笔试等）

输出格式（严格 JSON 数组）：
[{"name": "...", "type": "...", "description": "..."}]

注意：
- 同一个实体的不同表述应合并（如"字节"和"字节跳动"）
- 技术栈应使用标准名称（如"Python"而非"python"或"py"）"""

ENTITY_RESOLVER_USER = """请从以下文本中提取面试相关实体：

{text}"""


# ====================
# CognitiveModel：认知画像更新提示词
# ====================

COGNITIVE_UPDATE_SYSTEM = """你是一个候选人画像分析器。根据新的面试对话证据，更新候选人的认知画像。

分析维度：
- tech_skill: 技术掌握程度（具体技术点 + 掌握水平）
- interview_confidence: 面试信心（紧张/自信/从容）
- weakness: 薄弱环节（具体技术或软技能短板）
- strength: 优势领域（突出的技术或软技能）
- preparation_level: 准备程度（充分/一般/不足）
- communication: 表达能力（清晰/一般/需改善）

输出格式（严格 JSON 数组）：
[{
  "dimension": "...",
  "dimension_key": "...",
  "current_value": "...",
  "confidence": 0.8,
  "ttl_days": 90
}]

注意：
- 只输出有新证据支持的维度更新
- current_value 应该是简洁的描述（<=200字符）
- confidence 反映证据的确定性"""

COGNITIVE_UPDATE_USER = """候选人现有画像：
{current_profile}

新的面试对话证据：
{new_evidence}

请根据新证据更新画像。"""
