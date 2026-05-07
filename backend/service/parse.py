# -*- coding: utf-8 -*-
"""
PDF 解析服务
纯文本解析，不考虑图片处理
"""

import logging
import re
import uuid
from typing import List, Dict, Any, Tuple

import fitz  # PyMuPDF

logger = logging.getLogger(__name__)


def parse_pdf(
    file_content: bytes,
    job_id: str,
    collection: str,
    file_name: str,
    chunk_size: int = 500,
    chunk_overlap: int = 50,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    解析 PDF，仅提取纯文本并切片（不考虑图片）
    """
    doc = fitz.open(stream=file_content, filetype="pdf")

    # ── 提取所有文本块 ─────────────────────────────────────────────
    elements: List[Dict] = []

    for page_num, page in enumerate(doc, start=1):
        blocks = page.get_text("dict")["blocks"]

        # 按阅读顺序排序
        blocks.sort(key=lambda b: (b["bbox"][1], b["bbox"][0]))

        for b in blocks:
            if b["type"] != 0:
                continue

            text = "".join(
                span["text"]
                for line in b.get("lines", [])
                for span in line.get("spans", [])
            ).strip()

            if text:
                y_center = (b["bbox"][1] + b["bbox"][3]) / 2
                elements.append({
                    "type": "text",
                    "page": page_num,
                    "y_center": y_center,
                    "text": text,
                })

    doc.close()

    # 全局排序
    elements.sort(key=lambda e: (e["page"], e["y_center"]))

    logger.info(f"[Parser] 提取 {len(elements)} 个文本块")

    # ── 切分 ───────────────────────────────────────────────────────
    file_base = _file_base(file_name)
    chunks: List[Dict] = []
    image_records: List[Dict] = []

    buffer = ""
    text_len = 0
    chunk_idx = 0
    overlap_buf = ""
    first_page = None

    def _new_chunk_id() -> str:
        return str(uuid.uuid4())

    current_chunk_id = _new_chunk_id()

    def _seal():
        nonlocal buffer, text_len, chunk_idx, overlap_buf, first_page, current_chunk_id

        if buffer.strip():
            chunks.append({
                "chunk_id": current_chunk_id,
                "chunk_index": chunk_idx,
                "content": buffer,
                "metadata": {
                    "page": first_page,
                    "chunk_id": current_chunk_id,
                    "prev_chunk_id": None,
                    "next_chunk_id": None,
                },
            })

            overlap_buf = _smart_overlap(buffer, chunk_overlap)

        chunk_idx += 1
        buffer = ""
        text_len = 0
        first_page = None
        current_chunk_id = _new_chunk_id()

    # ── 核心优化：基于句子切分 ─────────────────────────────────────
    for elem in elements:
        if elem["type"] != "text":
            continue

        text = elem["text"]

        if first_page is None:
            first_page = elem["page"]

        # 注入 overlap
        if not buffer and overlap_buf:
            buffer = overlap_buf
            text_len = len(overlap_buf)
            overlap_buf = ""

        sentences = _split_sentences(text)

        for sent in sentences:
            sent_len = len(sent)

            # 超长句 fallback
            if sent_len > chunk_size:
                parts = [
                    sent[i:i + chunk_size]
                    for i in range(0, sent_len, chunk_size)
                ]
            else:
                parts = [sent]

            for part in parts:
                part_len = len(part)

                # 超出 → 封存
                if text_len + part_len > chunk_size:
                    _seal()

                    if overlap_buf:
                        buffer = overlap_buf
                        text_len = len(overlap_buf)
                        overlap_buf = ""

                buffer += part
                text_len += part_len

    # 收尾
    if buffer.strip():
        chunks.append({
            "chunk_id": current_chunk_id,
            "chunk_index": chunk_idx,
            "content": buffer,
            "metadata": {
                "page": first_page,
                "chunk_id": current_chunk_id,
                "prev_chunk_id": None,
                "next_chunk_id": None,
            },
        })

    # ── 后处理 ────────────────────────────────────────────────────
    chunks = _post_process_text_chunks(chunks, file_base)

    logger.info(f"[Parser] 完成：{len(chunks)} 个切片，0 条图片记录")
    return chunks, image_records


# ────────────────────────────────────────────────────────────────
# 工具函数
# ────────────────────────────────────────────────────────────────

def _file_base(file_name: str) -> str:
    return file_name.rsplit(".", 1)[0] if "." in file_name else file_name


def _split_sentences(text: str) -> List[str]:
    """
    中英文句子切分
    """
    if not text:
        return []

    parts = re.split(r'([。！？.!?\n])', text)

    sentences = []
    for i in range(0, len(parts) - 1, 2):
        sentences.append(parts[i] + parts[i + 1])

    if len(parts) % 2 != 0:
        sentences.append(parts[-1])

    return [s.strip() for s in sentences if s.strip()]


def _smart_overlap(text: str, overlap: int) -> str:
    if len(text) <= overlap:
        return text

    search_text = text[:overlap + 100]

    for sep in ['。\n', '。\n\n', '.\n', '.\n\n', '!\n', '!\n\n', '?\n', '?\n\n']:
        idx = search_text.rfind(sep)
        if idx > overlap * 0.5:
            return search_text[:idx + len(sep) - 1]

    idx = search_text.rfind('\n')
    if idx > overlap * 0.5:
        return search_text[:idx]

    idx = search_text.rfind(' ')
    if idx > overlap * 0.5:
        return search_text[:idx]

    return text[:overlap]


def _post_process_text_chunks(
    chunks: List[Dict],
    file_base: str
) -> List[Dict]:
    if not chunks:
        return chunks

    # 清理空 chunk
    chunks = [c for c in chunks if c["content"].strip()]

    for i, chunk in enumerate(chunks):
        chunk["chunk_index"] = i
        chunk["metadata"]["chunk_index"] = i

        chunk["metadata"]["prev_chunk_id"] = (
            chunks[i - 1]["chunk_id"] if i > 0 else None
        )

        chunk["metadata"]["next_chunk_id"] = (
            chunks[i + 1]["chunk_id"] if i < len(chunks) - 1 else None
        )

    logger.info(f"[Parser] 后处理完成：{len(chunks)} 个有效切片")
    return chunks