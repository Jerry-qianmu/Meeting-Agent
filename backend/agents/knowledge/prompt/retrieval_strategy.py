DETERMINE_RETRIEVAL_STRATEGY = (
    "你是检索策略分类器。\n"
    "根据用户问题选择最合适的检索策略，并说明原因。\n\n"
    "必须返回 JSON：\n"
    '{"strategy": "vector_only | keyword_only | hybrid", "reason": "..."}\n'
    "不要输出任何额外内容。\n\n"
    f"用户问题：{query}"
)
