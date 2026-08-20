# -*- coding: utf-8 -*-
"""
Rerank 评估脚本
对 easy.json 中每个问题跑检索+rerank，检查目标 passage 在召回结果中的排名

用法：
  python eval/eval_rerank.py --kb-id YOUR_KB_ID --top-k 40
"""

import argparse
import json
import logging
import os
import re
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.WARNING, format="%(message)s")
logger = logging.getLogger(__name__)


def normalize(text):
    """归一化：去 markdown、注释、空白，转小写（与 test_match.py 一致）"""
    t = re.sub(r'<!--.*?-->', '', text, flags=re.DOTALL)
    t = re.sub(r'\*\*([^*]+)\*\*', r'\1', t)
    t = re.sub(r'\*([^*]+)\*', r'\1', t)
    t = re.sub(r'#{1,6}\s+', '', t)
    t = re.sub(r'[|]', '', t)
    t = re.sub(r'\s+', '', t)
    return t.lower()


def find_passage_chunk_ids(chunk_repo, kb_id: str, passages: list) -> list:
    """一次性拉取所有 chunk，用文本匹配找对应 chunk（与 test_match.py 一致的匹配逻辑）"""
    all_chunks = chunk_repo.fetch_all(
        "SELECT chunk_uuid, content FROM chunk WHERE kb_uuid = %s", (kb_id,)
    )
    if not all_chunks:
        return [{"chunk_id": "NO_CHUNKS", "match_type": "", "passage_preview": p.get("content", "")[:80], "chunk_preview": ""} for p in passages]

    # 预归一化所有 chunk
    norm_chunks = [(c["chunk_uuid"], normalize(c["content"]), c["content"]) for c in all_chunks]

    matched = []
    for p in passages:
        content = p.get("content", "")
        if not content or len(content) < 20:
            matched.append({"chunk_id": "NO_CONTENT", "match_type": "", "passage_preview": "", "chunk_preview": ""})
            continue

        # 跳过第一行（仅当是标题格式时）
        lines = content.strip().split('\n')
        first_line = lines[0].strip()
        is_heading = first_line.startswith('#') or first_line.startswith('**')
        body = '\n'.join(lines[1:]) if is_heading and len(lines) > 1 else content
        norm_body = normalize(body)

        if len(norm_body) < 20:
            matched.append({"chunk_id": "SHORT_BODY", "match_type": "", "passage_preview": content[:80].replace('\n', ' '), "chunk_preview": ""})
            continue

        # 1. 完整正文匹配
        best_id = "NOT_FOUND"
        best_preview = ""
        match_type = ""

        for chunk_id, norm_content, raw_content in norm_chunks:
            if norm_body in norm_content:
                best_id = chunk_id
                best_preview = raw_content[:80]
                match_type = "FULL"
                break

        # 2. 兜底：按句子切分，逐段匹配
        if best_id == "NOT_FOUND":
            sentences = re.split(r'(?<=[.!?])\s+', body)
            sentences = [s.strip() for s in sentences if len(s.strip()) > 20]
            for sent in sentences:
                ns = normalize(sent)
                if len(ns) < 20:
                    continue
                for chunk_id, norm_content, raw_content in norm_chunks:
                    if ns[:60] in norm_content:
                        best_id = chunk_id
                        best_preview = raw_content[:80]
                        match_type = "PARTIAL"
                        break
                if best_id != "NOT_FOUND":
                    break

        matched.append({
            "chunk_id": best_id,
            "match_type": match_type,
            "passage_preview": content[:80].replace('\n', ' '),
            "chunk_preview": best_preview.replace('\n', ' ') if best_preview else "",
        })

    return matched


def run_eval(kb_id: str, top_k: int = 40, dataset_path: str = None):
    """对数据集中每个问题跑评估"""
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

    if not kb_info:
        print(f"知识库 {kb_id} 不存在，请检查 kb_id 是否正确")
        return

    collection_name = kb_info.get("collection_name", "")
    if not collection_name:
        print(f"知识库 {kb_id} 无 collection_name")
        return

    milvus = get_milvus_service()
    from database.mysql.repository.chunk_repository import ChunkRepository
    chunk_repo = ChunkRepository(db_client)

    # 加载数据集
    if dataset_path is None:
        dataset_path = os.path.join(os.path.dirname(__file__), "easy.json")
    with open(dataset_path, "r", encoding="utf-8") as f:
        dataset = json.load(f)

    print(f"\n{'='*80}")
    print(f"评估开始 | 知识库: {collection_name} | 问题数: {len(dataset)} | top_k: {top_k}")
    print(f"{'='*80}\n")

    total_questions = len(dataset)
    total_passages = 0
    hit_at_5 = 0
    hit_at_10 = 0
    hit_at_20 = 0
    hit_at_top_k = 0
    mrr_sum = 0.0
    results_detail = []

    for item in dataset:
        qid = item["id"]
        question = item["question"]
        passages = item["passages"]
        total_passages += len(passages)

        # 1. hybrid 检索
        hybrid_results = milvus.hybrid_search(
            collection_name=collection_name,
            query=question,
            top_k=top_k,
            ranker="RRF",
            rrf_k=60,
        )

        # 2. rerank
        mock_state = {
            "original_query": question,
            "rewritten_query": question,
            "Light_filtered_chunks": hybrid_results,
            "config": {
                "rerank_model": settings.rerank_model,
                "rerank_limit": settings.rerank_limit,
                "rerank_final_top_k": min(top_k, 20),
            },
        }
        rerank_result = do_rerank(mock_state)
        reranked = rerank_result.get("reranked_chunks", [])
        reranked_ids = [c.get("chunk_id", "") for c in reranked]

        # 3. 在 MySQL 中找目标 passage 对应的 chunk_uuid
        matched = find_passage_chunk_ids(chunk_repo, kb_id, passages)

        # 4. 计算排名
        q_hits_5 = 0
        q_hits_10 = 0
        q_hits_20 = 0
        q_hits_top_k = 0
        q_mrr = 0.0
        passage_ranks = []

        for m in matched:
            cid = m["chunk_id"]
            match_type = m.get("match_type", "")
            if cid in ("NOT_FOUND", "ERROR", "NO_CONTENT", "SHORT_BODY", "NO_CHUNKS"):
                rank = -1
            elif cid in reranked_ids:
                rank = reranked_ids.index(cid) + 1
            else:
                hybrid_ids = [r.get("chunk_id", "") for r in hybrid_results]
                if cid in hybrid_ids:
                    rank = hybrid_ids.index(cid) + 1
                else:
                    rank = -1

            passage_ranks.append({
                "passage_preview": m["passage_preview"],
                "ground_truth_chunk_id": cid,
                "match_type": match_type,
                "rank": rank,
            })

            if rank > 0:
                if rank <= 5:
                    q_hits_5 += 1; q_hits_10 += 1; q_hits_20 += 1; q_hits_top_k += 1
                elif rank <= 10:
                    q_hits_10 += 1; q_hits_20 += 1; q_hits_top_k += 1
                elif rank <= 20:
                    q_hits_20 += 1; q_hits_top_k += 1
                elif rank <= top_k:
                    q_hits_top_k += 1
                q_mrr += 1.0 / rank

        hit_at_5 += q_hits_5
        hit_at_10 += q_hits_10
        hit_at_20 += q_hits_20
        hit_at_top_k += q_hits_top_k
        mrr_sum += q_mrr

        matched_count = len(matched)
        recalled_count = sum(1 for r in passage_ranks if r["rank"] > 0)
        recall_rate = recalled_count / matched_count if matched_count > 0 else 0
        status = "PASS" if recalled_count == matched_count else ("PARTIAL" if recalled_count > 0 else "FAIL")

        print(f"[{qid:>2}] {status} | 召回 {recalled_count}/{matched_count} | "
              f"MRR={q_mrr:.3f} | {question[:60]}...")
        for pr in passage_ranks:
            rank_str = f"#{pr['rank']}" if pr['rank'] > 0 else "MISS"
            gt_cid = pr['ground_truth_chunk_id'][:12]
            match_type = pr.get('match_type', '')
            print(f"      {rank_str:<6} | {match_type:<8} | gt={gt_cid:<14} | {pr['passage_preview'][:50]}")
        # 打印 rerank 后的 top chunk_ids
        top_reranked = reranked_ids[:5]
        print(f"      Rerank Top5: {', '.join(cid[:12] for cid in top_reranked)}")

        results_detail.append({
            "id": qid,
            "question": question[:80],
            "status": status,
            "matched_count": matched_count,
            "recalled_count": recalled_count,
            "recall_rate": recall_rate,
            "mrr": q_mrr,
            "passage_ranks": passage_ranks,
        })

    # 汇总
    print(f"\n{'='*80}")
    print(f"汇总报告")
    print(f"{'='*80}")
    print(f"  总问题数:     {total_questions}")
    print(f"  总 passage 数: {total_passages}")
    print(f"  Hit@5:        {hit_at_5}/{total_passages} ({hit_at_5/total_passages*100:.1f}%)")
    print(f"  Hit@10:       {hit_at_10}/{total_passages} ({hit_at_10/total_passages*100:.1f}%)")
    print(f"  Hit@20:       {hit_at_20}/{total_passages} ({hit_at_20/total_passages*100:.1f}%)")
    print(f"  Hit@{top_k}:      {hit_at_top_k}/{total_passages} ({hit_at_top_k/total_passages*100:.1f}%)")
    print(f"  MRR:          {mrr_sum/total_questions:.4f}")

    fail_questions = [r for r in results_detail if r["status"] == "FAIL"]
    if fail_questions:
        print(f"\n  完全未召回的问题 ({len(fail_questions)} 个):")
        for r in fail_questions:
            print(f"    [{r['id']}] {r['question']}")

    # 保存报告
    report = {
        "timestamp": datetime.now().isoformat(),
        "kb_id": kb_id,
        "collection_name": collection_name,
        "top_k": top_k,
        "total_questions": total_questions,
        "total_passages": total_passages,
        "hit_at_5": hit_at_5,
        "hit_at_10": hit_at_10,
        "hit_at_20": hit_at_20,
        "hit_at_top_k": hit_at_top_k,
        "mrr": mrr_sum / total_questions,
        "details": results_detail,
    }

    report_path = os.path.join(os.path.dirname(__file__), f"eval_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n  报告已保存: {report_path}")
    print(f"{'='*80}")


def main():
    parser = argparse.ArgumentParser(description="Rerank 评估脚本")
    parser.add_argument("--kb-id", required=True, help="知识库 ID")
    parser.add_argument("--dataset", default=None, help="数据集 JSON 路径（默认 eval/easy.json）")
    parser.add_argument("--top-k", type=int, default=40, help="检索返回数量")
    args = parser.parse_args()
    run_eval(args.kb_id, args.top_k, args.dataset)


if __name__ == "__main__":
    main()
