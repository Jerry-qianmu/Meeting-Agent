# -*- coding: utf-8 -*-
"""
测试 easy.json 中 passage 与 MySQL chunk 的匹配
用法：python eval/test_match.py --kb-id YOUR_KB_ID --dataset eval/easy.json
"""

import argparse
import json
import os
import re
import sys
from difflib import SequenceMatcher

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def normalize(text):
    """归一化：去 markdown、注释、空白，转小写"""
    t = re.sub(r'<!--.*?-->', '', text, flags=re.DOTALL)
    t = re.sub(r'\*\*([^*]+)\*\*', r'\1', t)
    t = re.sub(r'\*([^*]+)\*', r'\1', t)
    t = re.sub(r'#{1,6}\s+', '', t)
    t = re.sub(r'[|]', '', t)
    t = re.sub(r'\s+', '', t)
    return t.lower()


def match_passages(kb_id: str, dataset_path: str):
    from database.mysql.mysql_client import init_mysql_pool, get_db_client
    from database.mysql.repository.chunk_repository import ChunkRepository
    from config.settings import Settings

    settings = Settings()
    init_mysql_pool(settings)
    db_client = get_db_client()
    chunk_repo = ChunkRepository(db_client)

    with open(dataset_path, "r", encoding="utf-8") as f:
        dataset = json.load(f)

    all_chunks = chunk_repo.fetch_all(
        "SELECT chunk_uuid, content FROM chunk WHERE kb_uuid = %s", (kb_id,)
    )
    print(f"知识库 chunk 总数: {len(all_chunks)}\n")

    # 预归一化所有 chunk
    norm_chunks = [(c["chunk_uuid"], normalize(c["content"])) for c in all_chunks]

    total = 0
    found = 0

    for item in dataset:
        qid = item["id"]
        question = item["question"]
        passages = item["passages"]
        print(f"[{qid}] {question[:60]}...")

        for p in passages:
            total += 1
            content = p.get("content", "")
            if not content or len(content) < 20:
                print(f"  PASSAGE: (too short)")
                continue

            # 跳过第一行（仅当是标题格式时）
            lines = content.strip().split('\n')
            first_line = lines[0].strip()
            is_heading = first_line.startswith('#') or first_line.startswith('**')
            body = '\n'.join(lines[1:]) if is_heading and len(lines) > 1 else content
            norm_body = normalize(body)

            if len(norm_body) < 20:
                print(f"  PASSAGE body too short after normalize")
                continue

            # 1. 完整正文匹配
            best_ids = []
            match_type = ""

            for chunk_id, norm_content in norm_chunks:
                if norm_body in norm_content:
                    best_ids = [chunk_id]
                    match_type = "FULL"
                    break

            # 2. 兜底：按句子切分，逐段匹配
            if not best_ids:
                sentences = re.split(r'(?<=[.!?])\s+', body)
                sentences = [s.strip() for s in sentences if len(s.strip()) > 20]
                seen_chunks = []
                for sent in sentences:
                    ns = normalize(sent)
                    if len(ns) < 20:
                        continue
                    for chunk_id, norm_content in norm_chunks:
                        if ns[:60] in norm_content and chunk_id not in seen_chunks:
                            seen_chunks.append(chunk_id)
                            break
                if seen_chunks:
                    best_ids = seen_chunks
                    if len(seen_chunks) == 1:
                        match_type = "PARTIAL"
                    else:
                        match_type = f"MULTI({len(seen_chunks)})"

            if best_ids:
                found += 1
                status = "OK"
            else:
                status = "MISS"

            print(f"  [{status:<6} {match_type or '':<10}] chunks={[cid[:12] for cid in best_ids]}")
            print(f"    body: {norm_body[:60]}...")
        print()

    print(f"{'='*60}")
    print(f"匹配结果: {found}/{total} ({found/total*100:.1f}%)")
    print(f"{'='*60}")


def main():
    parser = argparse.ArgumentParser(description="测试 passage 与 chunk 匹配")
    parser.add_argument("--kb-id", required=True, help="知识库 ID")
    parser.add_argument("--dataset", default=None, help="数据集 JSON 路径")
    args = parser.parse_args()
    dataset_path = args.dataset or os.path.join(os.path.dirname(__file__), "easy.json")
    match_passages(args.kb_id, dataset_path)


if __name__ == "__main__":
    main()
