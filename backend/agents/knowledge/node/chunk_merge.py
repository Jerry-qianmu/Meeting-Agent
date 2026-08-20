# -*- coding: utf-8 -*-
"""
Chunk Merge Node
合并相邻chunks，补充上下文，解决小chunk检索分数低的问题
"""

import logging
from typing import Dict, List, Any

from ..state import KnowledgeAgentState
from config.settings import Settings

logger = logging.getLogger(__name__)


def chunk_merge(state: KnowledgeAgentState) -> Dict:
    """
    合并相邻chunks，补充上下文

    输入：reranked_chunks（第一次rerank后的chunks）
    输出：chunk_merged_chunks（合并后的chunks）

    核心逻辑：
    1. 按doc_id分组
    2. 按chunk_index排序
    3. 滑动窗口合并相邻chunks
    4. 可选：从数据库获取上下文扩展短chunk
    """

    chunks = state.get("reranked_chunks", [])
    config = state.get("config", {})

    if not chunks:
        return {"chunk_merged_chunks": [], "merge_stats": {"input_count": 0, "output_count": 0}}

    # 从config读取配置（支持per-request覆盖），fallback到Settings
    settings = Settings()
    chunk_merge_enable = getattr(config, "chunk_merge_enable", settings.chunk_merge_enable)

    # 检查是否启用合并
    if not chunk_merge_enable:
        logger.info("[ChunkMerge] 合并功能已禁用，直接返回原始chunks")
        return {
            "chunk_merged_chunks": chunks,
            "merge_stats": {"input_count": len(chunks), "output_count": len(chunks), "merged_groups": 0, "expanded_chunks": 0}
        }

    # 合并配置
    max_merge_tokens = getattr(config, "chunk_merge_max_tokens", settings.chunk_merge_max_tokens)
    max_gap = getattr(config, "chunk_merge_max_gap", settings.chunk_merge_max_gap)
    enable_context_expansion = getattr(config, "chunk_merge_enable_context_expansion", settings.chunk_merge_enable_context_expansion)

    # 按doc_id分组
    doc_chunks = _group_by_doc_id(chunks)

    merged_results = []
    merge_stats = {
        "input_count": len(chunks),
        "merged_groups": 0,
        "expanded_chunks": 0,
    }

    for doc_id, doc_chunk_list in doc_chunks.items():
        # 按chunk_index排序（注意：是chunk_index，不是chunk_order）
        doc_chunk_list.sort(key=lambda x: x.get("chunk_index", 0))
        indices = [c.get("chunk_index", 0) for c in doc_chunk_list]
        logger.info(f"[ChunkMerge] doc_id={doc_id[:12]}..., chunks={len(doc_chunk_list)}, indices={indices}")

        # 滑动窗口合并
        i = 0
        while i < len(doc_chunk_list):
            current_group = [doc_chunk_list[i]]
            current_tokens = _count_tokens(doc_chunk_list[i]["content"])

            # 尝试向后扩展
            j = i + 1
            while j < len(doc_chunk_list):
                prev_chunk = doc_chunk_list[j - 1]
                curr_chunk = doc_chunk_list[j]

                # 检查间隔（使用chunk_index）
                gap = curr_chunk.get("chunk_index", 0) - prev_chunk.get("chunk_index", 0)

                # 检查token限制
                curr_tokens = _count_tokens(curr_chunk["content"])

                # 调试日志
                gap_ok = gap <= max_gap
                token_ok = current_tokens + curr_tokens <= max_merge_tokens
                if not gap_ok or not token_ok:
                    logger.info(
                        f"[ChunkMerge] ❌ 不合并 | "
                        f"chunk_index=[{prev_chunk.get('chunk_index')}, {curr_chunk.get('chunk_index')}] | "
                        f"gap={gap}(limit={max_gap}, ok={gap_ok}) | "
                        f"tokens={current_tokens}+{curr_tokens}={current_tokens+curr_tokens}(limit={max_merge_tokens}, ok={token_ok})"
                    )

                if gap_ok and token_ok:
                    current_group.append(curr_chunk)
                    current_tokens += curr_tokens
                    j += 1
                else:
                    break

            # 合并当前组
            if len(current_group) > 1:
                merged_chunk = _merge_chunk_group(current_group)
                merged_results.append(merged_chunk)
                merge_stats["merged_groups"] += 1
                indices = [c.get("chunk_index", "?") for c in current_group]
                ids = [c.get("chunk_id", "?")[:8] for c in current_group]
                tokens = [_count_tokens(c["content"]) for c in current_group]
                logger.info(
                    f"[ChunkMerge] ✅ 合并 {len(current_group)} 个chunk | "
                    f"doc={doc_id[:12]} | "
                    f"chunk_index={indices} | "
                    f"tokens={tokens} → {_count_tokens(merged_chunk['content'])} | "
                    f"chunk_id={ids}"
                )
            else:
                # 单个chunk，检查是否需要上下文扩展
                if enable_context_expansion:
                    expanded_chunk = _expand_context(current_group[0], state)
                    if expanded_chunk:
                        merged_results.append(expanded_chunk)
                        merge_stats["expanded_chunks"] += 1
                    else:
                        merged_results.append(current_group[0])
                else:
                    merged_results.append(current_group[0])

            i = j

    merge_stats["output_count"] = len(merged_results)

    logger.info(f"[ChunkMerge] 输入 {merge_stats['input_count']} 个chunk, "
                f"合并 {merge_stats['merged_groups']} 组, "
                f"扩展 {merge_stats['expanded_chunks']} 个, "
                f"输出 {merge_stats['output_count']} 个chunk")

    return {
        "chunk_merged_chunks": merged_results,
        "merge_stats": merge_stats
    }


def _group_by_doc_id(chunks: List[Dict]) -> Dict[str, List[Dict]]:
    """按doc_id分组"""
    doc_chunks = {}
    for chunk in chunks:
        doc_id = chunk.get("doc_id", "unknown")
        if doc_id not in doc_chunks:
            doc_chunks[doc_id] = []
        doc_chunks[doc_id].append(chunk)
    return doc_chunks


def _merge_chunk_group(chunks: List[Dict]) -> Dict:
    """
    合并一组chunks为一个大chunk

    策略：
    - 内容：直接拼接，用换行分隔
    - chunk_id：生成新的merged chunk_id
    - chunk_index：使用第一个chunk的index
    - rerank_score：取最大值（保留最相关的分数）
    """

    # 按chunk_index排序
    chunks.sort(key=lambda x: x.get("chunk_index", 0))

    # 合并内容
    merged_content = "\n\n".join([c["content"] for c in chunks])

    # 取第一个chunk作为基础
    merged_chunk = chunks[0].copy()
    merged_chunk["content"] = merged_content
    merged_chunk["chunk_id"] = f"{chunks[0]['chunk_id']}_merged_{len(chunks)}"

    # 保留合并来源信息
    merged_chunk["merged_from"] = [c["chunk_id"] for c in chunks]
    merged_chunk["merged_count"] = len(chunks)
    merged_chunk["token_count"] = _count_tokens(merged_content)

    # 分数取最大值（保留最相关的分数）
    merged_chunk["rerank_score"] = max([c.get("rerank_score", 0.0) for c in chunks])

    return merged_chunk


def _expand_context(chunk: Dict, state: KnowledgeAgentState) -> Dict:
    """
    从数据库中提取相邻chunk的上下文进行扩展

    当单个chunk较短时，尝试从数据库中获取其前后chunk来补充上下文
    扩展策略：取前一个chunk的最后200字符 + 当前chunk + 后一个chunk的前200字符
    """

    config = state.get("config", {})
    settings = Settings()
    min_tokens_for_expansion = getattr(config, "chunk_merge_min_tokens_for_expansion", settings.chunk_merge_min_tokens_for_expansion)

    # 检查chunk是否足够短，需要扩展
    chunk_tokens = _count_tokens(chunk["content"])
    if chunk_tokens >= min_tokens_for_expansion:
        return None

    # 获取目标知识库和文档信息
    target_kbs = state.get("target_knowledge_bases", [])
    doc_id = chunk.get("doc_id")
    chunk_index = chunk.get("chunk_index")

    if not target_kbs or not doc_id or chunk_index is None:
        return None

    try:
        # 将知识库ID转换为collection名称
        collection_names = _resolve_collections(target_kbs)
        if not collection_names:
            return None

        # 从数据库获取相邻chunks（使用第一个collection）
        adjacent_chunks = _fetch_adjacent_chunks(
            collection_name=collection_names[0],
            doc_id=doc_id,
            chunk_index=chunk_index,
            window_size=1
        )

        if not adjacent_chunks:
            return None

        # 构建扩展内容
        prev_content = ""
        next_content = ""

        for adj_chunk in adjacent_chunks:
            adj_index = adj_chunk.get("chunk_index", 0)
            if adj_index < chunk_index:
                prev_content = adj_chunk.get("content", "")
            elif adj_index > chunk_index:
                next_content = adj_chunk.get("content", "")

        # 如果没有相邻chunk，不需要扩展
        if not prev_content and not next_content:
            return None

        # 合并内容
        expanded_content = ""
        if prev_content:
            # 取前一个chunk的最后200字符
            expanded_content += prev_content[-200:] + "\n\n"
        expanded_content += chunk["content"]
        if next_content:
            # 取后一个chunk的前200字符
            expanded_content += "\n\n" + next_content[:200]

        # 创建扩展后的chunk
        expanded_chunk = chunk.copy()
        expanded_chunk["content"] = expanded_content
        expanded_chunk["chunk_id"] = f"{chunk['chunk_id']}_expanded"
        expanded_chunk["token_count"] = _count_tokens(expanded_content)
        expanded_chunk["expanded_from"] = [c["chunk_id"] for c in adjacent_chunks]

        logger.debug(f"[ChunkMerge] 扩展chunk {chunk.get('chunk_index')}: "
                    f"{chunk_tokens} -> {_count_tokens(expanded_content)} tokens")

        return expanded_chunk

    except Exception as e:
        logger.warning(f"[ChunkMerge] 上下文扩展失败: {e}")
        return None


def _resolve_collections(target_kbs: list) -> list:
    """
    将知识库 ID 列表解析为 Milvus collection 名称列表

    Args:
        target_kbs: 知识库ID列表（UUID格式）

    Returns:
        collection名称列表（格式：kb_{user_id}_{name}_{uuid}）
    """
    try:
        # 使用与 main.py 相同的导入路径，避免模块重复导入导致的单例问题
        from database.mysql.repository.knowledge_base_repository import KnowledgeBaseRepository
        from database.mysql.mysql_client import get_db_client

        db_client = get_db_client()
        kb_repo = KnowledgeBaseRepository(db_client)
        collection_names = []

        for kb_id in target_kbs:
            kb_info = kb_repo.get_by_id(kb_id)
            if kb_info and kb_info.get('collection_name'):
                collection_names.append(kb_info['collection_name'])
            else:
                logger.warning(f"[ChunkMerge] 知识库不存在或无 collection: {kb_id}")

        return collection_names
    except Exception as e:
        logger.warning(f"[ChunkMerge] 解析知识库collection名称失败: {e}")
        return []


def _fetch_adjacent_chunks(
    collection_name: str,
    doc_id: str,
    chunk_index: int,
    window_size: int = 1
) -> List[Dict]:
    """
    从数据库获取相邻chunks

    Args:
        collection_name: Milvus collection名称
        doc_id: 文档ID
        chunk_index: 当前chunk的index
        window_size: 前后各取多少个chunk

    Returns:
        相邻chunks列表
    """

    try:
        from database.milvus.milvus_service import MilvusService

        milvus_service = MilvusService()

        # 查询相邻chunks（使用chunk_index字段）
        filter_expr = (
            f'doc_id == "{doc_id}" && '
            f'chunk_index >= {chunk_index - window_size} && '
            f'chunk_index <= {chunk_index + window_size}'
        )

        results = milvus_service.client.query(
            collection_name=collection_name,
            filter=filter_expr,
            output_fields=["chunk_id", "doc_id", "chunk_index", "content"],
            limit=window_size * 2 + 1
        )

        return results

    except Exception as e:
        logger.warning(f"[ChunkMerge] 获取相邻chunks失败: {e}")
        return []


def _count_tokens(text: str) -> int:
    """计算token数量，使用项目统一的tokenizer"""
    if not text:
        return 0
    try:
        from service.tokenizer import count_tokens
        return count_tokens(text)
    except Exception:
        # fallback: 粗略估算
        return len(text) // 2
