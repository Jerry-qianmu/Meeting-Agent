# -*- coding: utf-8 -*-
"""
Chunk Enricher - 为每个 chunk 生成 description + keywords
参考 MDKeyChunker 的 enricher + rolling keys 设计

流程：
  chunk_1 → LLM(description_1, keywords_1)
  chunk_2 + description_1 → LLM(description_2, keywords_2)
  chunk_3 + description_2 → LLM(description_3, keywords_3)
"""

import json
import logging
from typing import List, Dict, Any, Optional

from dashscope import Generation

logger = logging.getLogger(__name__)


ENRICHER_SYSTEM = """你是一个文档分析专家。你的任务是为文档片段生成摘要描述和关键词。

## 输入
你会收到：
1. 当前文档片段（chunk）的完整内容
2. 标题路径（heading_path），显示该片段在文档层级中的位置
3. （可选）上一个片段的摘要描述，作为上下文参考

## 输出要求
严格返回 JSON 格式，不要输出其他内容：
{
  "description": "一句话描述这个片段的核心内容（50-100字）",
  "keywords": ["关键词1", "关键词2", "标识词3"]
}

## Description 要求
- 准确概括这个片段讨论的具体内容
- 如果片段包含多个层级（父标题+子标题），要体现层级关系，如"在X主题下，分别介绍了Y和Z"
- 如果涉及对比/关系，要体现出来（如"A与B的区别"）
- 参考上一个片段的摘要来保持连贯性，但以上一个摘要仅供参考，以当前内容为准
- 如果标题路径显示这是一个子节，description 中应体现它属于哪个父主题

## Keywords 要求
- 包含技术术语（如"Redis持久化"、"B+树"）
- 包含标识性词语（如"Fig1"、"表2"、"算法3"、"面试题5"）
- 包含实体名称（如"MySQL"、"Spring Boot"）
- 包含标题路径中的关键主题词（如父标题、子标题中的核心词）
- 每个 chunk 5-10 个关键词
- 不要包含无意义的通用词（如"方法"、"介绍"、"说明"）"""


def _call_enricher_llm(
    chunk_content: str,
    prev_description: Optional[str],
    model: str,
    api_key: str,
    heading_path: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """调用 LLM 生成 description 和 keywords"""
    user_parts = []

    if heading_path:
        breadcrumb = ' > '.join(heading_path)
        user_parts.append(f"【标题路径】\n{breadcrumb}")

    if prev_description:
        user_parts.append(f"【上一个片段的摘要】\n{prev_description}")

    content = chunk_content
    if len(content) > 3000:
        content = content[:3000] + "\n...(内容过长，已截断)"

    user_parts.append(f"【当前文档片段】\n{content}")
    user_prompt = "\n\n".join(user_parts)

    messages = [
        {"role": "system", "content": ENRICHER_SYSTEM},
        {"role": "user", "content": user_prompt},
    ]

    try:
        from service.llm_client import llm_call
        from config.settings import Settings
        cfg = Settings().get_llm_config("md_enrich", model=model)
        result = llm_call(messages=messages, model=cfg["model"], api_type=cfg["api_type"], api_key=cfg["api_key"] or api_key, base_url=cfg["base_url"])

        if result["status_code"] != 200:
            logger.warning(f"[ChunkEnricher] LLM 调用失败: status={result['status_code']}, model={model}")
            return {"description": "", "keywords": []}

        resp_content = result["content"]
        json_start = resp_content.find("{")
        json_end = resp_content.rfind("}") + 1
        if json_start >= 0 and json_end > json_start:
            result = json.loads(resp_content[json_start:json_end])
            return {
                "description": result.get("description", ""),
                "keywords": result.get("keywords", []),
            }

        logger.warning(f"[ChunkEnricher] JSON 解析失败: {resp_content[:200]}")
        return {"description": "", "keywords": []}

    except Exception as e:
        logger.error(f"[ChunkEnricher] LLM 异常: {e}")
        return {"description": "", "keywords": []}


class ChunkEnricher:
    """
    Chunk 富化器：为每个 chunk 生成 description + keywords

    Args:
        model: LLM 模型名
        api_key: DashScope API Key
    """

    def __init__(self, model: str = "qwen3.5-plus", api_key: str = ""):
        self.model = model
        self.api_key = api_key

    def enrich_chunks(
        self,
        chunks: List[Dict[str, Any]],
        content_key: str = "content",
        max_workers: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        并行富化 chunks

        Args:
            chunks: chunk 字典列表
            content_key: 内容字段名
            max_workers: 最大并发数

        Returns:
            原始 chunks 列表，每个增加了 description 和 keywords
        """
        if not chunks:
            return chunks

        if not self.api_key:
            logger.warning("[ChunkEnricher] API Key 未设置，跳过富化")
            for c in chunks:
                c['description'] = ""
                c['keywords'] = []
            return chunks

        logger.info(f"[ChunkEnricher] 开始并行富化 {len(chunks)} 个 chunk (workers={max_workers})")

        from concurrent.futures import ThreadPoolExecutor, as_completed

        def _enrich_one(index: int, chunk: dict) -> tuple:
            content = chunk.get(content_key, "")
            if not content.strip():
                return index, {"description": "", "keywords": []}
            # 从 chunk 的 metadata 或顶层获取 heading_path
            heading_path = chunk.get('heading_path', [])
            if not heading_path:
                heading_path = chunk.get('metadata', {}).get('heading_path', [])
            result = _call_enricher_llm(
                chunk_content=content,
                prev_description=None,  # 并行模式不传 rolling context
                model=self.model,
                api_key=self.api_key,
                heading_path=heading_path,
            )
            return index, result

        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {pool.submit(_enrich_one, i, c): i for i, c in enumerate(chunks)}
            done = 0
            for future in as_completed(futures):
                index, result = future.result()
                chunks[index]['description'] = result['description']
                chunks[index]['keywords'] = result['keywords']
                done += 1
                if done % 10 == 0:
                    logger.info(f"[ChunkEnricher] 已富化 {done}/{len(chunks)}")

        logger.info(f"[ChunkEnricher] 并行富化完成: {len(chunks)} 个 chunk")
        return chunks


def enrich_chunks(
    chunks: List[Dict[str, Any]],
    api_key: str,
    model: str = "qwen3.5-plus",
) -> List[Dict[str, Any]]:
    """便捷函数"""
    enricher = ChunkEnricher(model=model, api_key=api_key)
    return enricher.enrich_chunks(chunks)
