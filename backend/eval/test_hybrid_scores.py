# -*- coding: utf-8 -*-
"""
混合检索分数对比测试脚本
对比 RRF 和 Weighted 两种融合策略的检索结果

用法：
  python eval/test_hybrid_scores.py --query "你的问题" --kb-id YOUR_KB_ID
"""

import argparse
import logging
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


def test_hybrid_scores(query: str, kb_id: str, top_k: int = 10):
    """对比 RRF 和 Weighted 两种策略的检索结果"""
    from database.mysql.mysql_client import init_mysql_pool
    from database.mysql.repository.knowledge_base_repository import KnowledgeBaseRepository
    from database.mysql.mysql_client import get_db_client
    from database.milvus.milvus_service import get_milvus_service
    from config.settings import Settings

    settings = Settings()
    init_mysql_pool(settings)
    db_client = get_db_client()
    kb_repo = KnowledgeBaseRepository(db_client)
    kb_info = kb_repo.get_by_id(kb_id)
    collection_name = kb_info.get("collection_name", "")

    if not collection_name:
        print(f"知识库 {kb_id} 不存在或无 collection")
        return

    milvus = get_milvus_service()

    # ===== 对比 RetrievalService.search() vs milvus.hybrid_search() =====
    from service.retrieval_service import get_retrieval_service
    retrieval = get_retrieval_service()

    results_via_service = retrieval.search(
        query=query, collection=collection_name, top_k=top_k,
        filter_expr=None, strategy="hybrid",
    )
    print(f"\n{'='*80}")
    print("=== 通过 RetrievalService.search() (与主流程一致) ===")
    print(f"{'='*80}")
    for i, r in enumerate(results_via_service[:10]):
        print(f"  [{i+1}] score={r.get('score',0):.4f} | chunk_id={r.get('chunk_id','')[:12]} | {r.get('content','')[:60].replace(chr(10),' ')}...")

    results_direct = milvus.hybrid_search(
        collection_name=collection_name, query=query, top_k=top_k, ranker="RRF", rrf_k=60,
    )
    print(f"\n{'='*80}")
    print("=== 直接调 milvus.hybrid_search() ===")
    print(f"{'='*80}")
    for i, r in enumerate(results_direct[:10]):
        print(f"  [{i+1}] score={r.get('score',0):.4f} | chunk_id={r.get('chunk_id','')[:12]} | {r.get('content','')[:60].replace(chr(10),' ')}...")

    # 对比差异
    print(f"\n{'='*80}")
    print("=== 差异对比 ===")
    print(f"{'='*80}")
    service_ids = [r.get("chunk_id", "") for r in results_via_service[:top_k]]
    direct_ids = [r.get("chunk_id", "") for r in results_direct[:top_k]]
    for i in range(min(top_k, len(service_ids), len(direct_ids))):
        match = "==" if service_ids[i] == direct_ids[i] else "!="
        print(f"  [{i+1}] service={service_ids[i][:12]}  direct={direct_ids[i][:12]}  {match}")
    print()

    # 测试不同策略
    strategies = [
        {"name": "RRF (k=60)", "ranker": "RRF", "rrf_k": 60},
        {"name": "RRF (k=30)", "ranker": "RRF", "rrf_k": 30},
        {"name": "Weighted (α=0.5)", "ranker": "Weight", "hybrid_alpha": 0.5},
        {"name": "Weighted (α=0.6)", "ranker": "Weight", "hybrid_alpha": 0.6},
        {"name": "Weighted (α=0.7)", "ranker": "Weight", "hybrid_alpha": 0.7},
    ]

    all_results = {}

    for s in strategies:
        try:
            if s["ranker"] == "RRF":
                results = milvus.hybrid_search(
                    collection_name=collection_name,
                    query=query,
                    top_k=top_k,
                    ranker="RRF",
                    rrf_k=s.get("rrf_k", 60),
                )
            else:
                results = milvus.hybrid_search(
                    collection_name=collection_name,
                    query=query,
                    top_k=top_k,
                    ranker="Weight",
                    hybrid_alpha=s.get("hybrid_alpha", 0.5),
                )

            all_results[s["name"]] = results
            logger.info(f"[{s['name']}] 返回 {len(results)} 条")
        except Exception as e:
            logger.error(f"[{s['name']}] 失败: {e}")
            all_results[s["name"]] = []

    # 打印对比结果
    print(f"\n{'='*80}")
    print(f"查询: {query}")
    print(f"Collection: {collection_name}")
    print(f"{'='*80}")

    # 按 chunk_id 汇合所有策略的结果
    chunk_scores = {}
    for strategy_name, results in all_results.items():
        for i, r in enumerate(results):
            cid = r.get("chunk_id", "")
            if cid not in chunk_scores:
                chunk_scores[cid] = {
                    "content": r.get("content", "")[:100],
                    "doc_id": r.get("doc_id", ""),
                    "scores": {},
                    "ranks": {},
                }
            chunk_scores[cid]["scores"][strategy_name] = r.get("score", 0.0)
            chunk_scores[cid]["ranks"][strategy_name] = i + 1

    # 按 RRF 排名排序
    sorted_chunks = sorted(
        chunk_scores.items(),
        key=lambda x: x[1]["ranks"].get("RRF (k=60)", 999)
    )

    # 打印表格
    strategy_names = list(all_results.keys())

    print(f"\n{'─'*80}")
    print(f"{'Rank':<6} | {'Chunk ID':<12} | ", end="")
    for name in strategy_names:
        print(f"{name:<20} | ", end="")
    print()
    print(f"{'─'*80}")

    for rank, (cid, info) in enumerate(sorted_chunks[:top_k], 1):
        print(f"{rank:<6} | {cid[:10]:<12} | ", end="")
        for name in strategy_names:
            score = info["scores"].get(name, 0.0)
            r = info["ranks"].get(name, "-")
            print(f"{score:.4f} (#{r}){'':<8} | ", end="")
        print()

    # 打印每个策略的 top-5 内容预览
    for strategy_name, results in all_results.items():
        print(f"\n{'─'*80}")
        print(f"[{strategy_name}] Top {min(5, len(results))}:")
        print(f"{'─'*80}")
        for i, r in enumerate(results[:5]):
            score = r.get("score", 0.0)
            preview = r.get("content", "")[:80].replace("\n", " ")
            print(f"  [{i+1}] score={score:.4f} | {preview}...")

    print(f"\n{'='*80}")

    # 导出为 CSV
    import csv
    output_file = "D:\\Study\\Agents\\MA\\data3\\zb\\MyAgent\\backend\\eval\\hybrid_score_comparison_rewrite.csv"
    with open(output_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        # 表头
        writer.writerow(["Rank", "Chunk ID", "Content Preview"] + [f"{name} Score" for name in strategy_names] + [f"{name} Rank" for name in strategy_names])
        # 数据
        for rank, (cid, info) in enumerate(sorted_chunks[:top_k], 1):
            row = [rank, cid, info["content"][:80]]
            for name in strategy_names:
                row.append(info["scores"].get(name, 0.0))
            for name in strategy_names:
                row.append(info["ranks"].get(name, "-"))
            writer.writerow(row)
    print(f"\n结果已导出到: {output_file}")


def test_rerank(query: str, kb_id: str, top_k: int = 10):
    """测试 rerank 效果：复用主流程 rerank.py 的逻辑"""
    from database.mysql.mysql_client import init_mysql_pool
    from database.mysql.repository.knowledge_base_repository import KnowledgeBaseRepository
    from database.mysql.mysql_client import get_db_client
    from database.milvus.milvus_service import get_milvus_service
    from agents.knowledge.node.rerank import rerank as do_rerank
    from config.settings import Settings

    settings = Settings()
    init_mysql_pool(settings)
    db_client = get_db_client()
    kb_repo = KnowledgeBaseRepository(db_client)
    kb_info = kb_repo.get_by_id(kb_id)
    collection_name = kb_info.get("collection_name", "")

    if not collection_name:
        print(f"知识库 {kb_id} 不存在或无 collection")
        return

    milvus = get_milvus_service()

    # 1. hybrid 检索（取较多候选给 rerank）
    search_limit = 50
    hybrid_results = milvus.hybrid_search(
        collection_name=collection_name, query=query,
        top_k=search_limit, ranker="RRF", rrf_k=60,
    )
    print(f"\n{'='*80}")
    print(f"=== Hybrid 检索结果 (top_k={search_limit}) ===")
    print(f"{'='*80}")
    for i, r in enumerate(hybrid_results[:10]):
        print(f"  [{i+1}] hybrid_score={r.get('score',0):.4f} | chunk_id={r.get('chunk_id','')[:12]} | {r.get('content','')[:60].replace(chr(10),' ')}...")

    # 2. 构造 mock state，复用主流程 rerank 逻辑
    mock_state = {
        "original_query": query,
        "rewritten_query": query,
        "Light_filtered_chunks": hybrid_results,
        "config": {
            "rerank_model": settings.rerank_model,
            "rerank_limit": settings.rerank_limit,
            "rerank_final_top_k": top_k,
        },
    }

    print(f"\n{'='*80}")
    print(f"=== 调用 Rerank (model={settings.rerank_model}, limit={settings.rerank_limit}, top_n={top_k}) ===")
    print(f"{'='*80}")

    # 3. 调用主流程 rerank
    result = do_rerank(mock_state)
    reranked = result.get("reranked_chunks", [])

    if not reranked:
        print("  ❌ Rerank 返回空结果")
        return

    # 4. 打印 rerank 结果
    print(f"\n{'─'*80}")
    print(f"{'Rank':<6} | {'Rerank':<10} | {'Hybrid':<10} | {'Chunk ID':<14} | Content Preview")
    print(f"{'─'*80}")

    for rank, c in enumerate(reranked, 1):
        rerank_score = c.get("rerank_score", 0.0)
        hybrid_score = c.get("hybrid_score") or c.get("score", 0.0)
        cid = c.get("chunk_id", "")[:12]
        preview = c.get("content", "")[:50].replace("\n", " ")
        print(f"  {rank:<4} | {rerank_score:<10.4f} | {hybrid_score:<10.4f} | {cid:<14} | {preview}...")

    # 5. 排名变化分析
    hybrid_ids = [r.get("chunk_id", "") for r in hybrid_results]
    reranked_ids = [c.get("chunk_id", "") for c in reranked]

    print(f"\n{'─'*80}")
    print("=== 排名变化（Hybrid → Rerank）===")
    print(f"{'─'*80}")
    for rank, cid in enumerate(reranked_ids[:10], 1):
        hybrid_rank = hybrid_ids.index(cid) + 1 if cid in hybrid_ids else -1
        shift = hybrid_rank - rank
        direction = f"↑{shift}" if shift > 0 else (f"↓{abs(shift)}" if shift < 0 else "→")
        print(f"  [{rank}] chunk_id={cid[:12]}  hybrid_rank={hybrid_rank}  {direction}")

    # 6. 分数断层分析
    if len(reranked) >= 3:
        scores = [c.get("rerank_score", 0.0) for c in reranked]
        max_gap = 0
        gap_pos = 0
        for i in range(1, len(scores)):
            gap = scores[i-1] - scores[i]
            if gap > max_gap:
                max_gap = gap
                gap_pos = i
        if max_gap > 0.05:
            print(f"\n  ⚠️ 分数断层: 位置 {gap_pos} 和 {gap_pos+1} 之间, 差值={max_gap:.4f}")
            print(f"     [{gap_pos}] score={scores[gap_pos-1]:.4f}")
            print(f"     [{gap_pos+1}] score={scores[gap_pos]:.4f}")
        else:
            print(f"\n  ✅ 分数分布平滑，无明显断层（最大差值={max_gap:.4f}）")

    print(f"\n{'='*80}")


def main():
    parser = argparse.ArgumentParser(description="混合检索分数对比测试")
    parser.add_argument("--query", required=True, help="测试查询")
    parser.add_argument("--kb-id", required=True, help="知识库 ID")
    parser.add_argument("--top-k", type=int, default=10, help="返回数量")
    parser.add_argument("--rerank", action="store_true", help="是否测试 rerank")
    args = parser.parse_args()

    if args.rerank:
        test_rerank(args.query, args.kb_id, args.top_k)
    else:
        test_hybrid_scores(args.query, args.kb_id, args.top_k)


if __name__ == "__main__":
    main()
