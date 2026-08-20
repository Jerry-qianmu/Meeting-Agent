# -*- coding: utf-8 -*-
"""
Markdown 分块器 v2.0
采用 flat 累加器模式（借鉴 Unstructured），自上而下分块

算法：
1. 解析 markdown 为 flat 元素列表（heading/paragraph/table/code/list）
2. 累加器从上到下累加元素，遇到标题边界且累积 >= min_tokens 时 flush
3. 后处理吸收剩余小 chunk
4. 注入标题面包屑
"""

import re
import logging
import uuid
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

from service.tokenizer import count_tokens

logger = logging.getLogger(__name__)


# ============================================================
# 数据结构
# ============================================================

@dataclass
class Element:
    """Markdown 元素（flat 解析的原子单元）"""
    elem_type: str        # 'heading', 'paragraph', 'code', 'table', 'list'
    content: str          # 原始文本
    token_count: int      # token 估算
    heading_path: List[str]  # 当前所处的标题路径
    heading_level: int    # 标题层级（heading 类型专用，其他为 0）
    line_start: int       # 起始行号
    line_end: int         # 结束行号


@dataclass
class ChunkResult:
    """分块结果"""
    chunk_id: str
    content: str
    heading_path: List[str]
    heading_level: int
    token_count: int
    start_line: int
    end_line: int
    block_count: int
    metadata: Dict[str, Any] = field(default_factory=dict)


# ============================================================
# Markdown 解析
# ============================================================

HEADING_RE = re.compile(r'^(#{1,6})\s+(.+)$')
CODE_FENCE_RE = re.compile(r'^(`{3,}|~{3,})')
TABLE_ROW_RE = re.compile(r'^\|.+\|')
TABLE_SEPARATOR_RE = re.compile(r'^\|?\s*[-:]+[-| :]*$')
LIST_ITEM_RE = re.compile(r'^(\s*[-*+]|\s*\d+\.)\s+')


def _parse_elements(markdown_text: str) -> List[Element]:
    """将 markdown 解析为 flat 元素列表"""
    lines = markdown_text.split('\n')
    elements: List[Element] = []
    heading_path: List[str] = []
    heading_stack: List[tuple] = []  # [(level, title), ...]
    i = 0
    line_no = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        line_no = i

        # 空行跳过
        if not stripped:
            i += 1
            continue

        # 标题
        heading_match = HEADING_RE.match(stripped)
        if heading_match:
            level = len(heading_match.group(1))
            title = heading_match.group(2).strip()
            heading_text = f"{'#' * level} {title}"

            # 更新 heading_stack
            while heading_stack and heading_stack[-1][0] >= level:
                heading_stack.pop()
            heading_stack.append((level, title))
            heading_path = [f"{'#' * l} {t}" for l, t in heading_stack]

            elements.append(Element(
                elem_type='heading',
                content=heading_text,
                token_count=count_tokens(heading_text),
                heading_path=heading_path[:-1],  # 标题属于上一层级的上下文
                heading_level=level,
                line_start=line_no,
                line_end=line_no,
            ))
            i += 1
            continue

        # 代码块
        fence_match = CODE_FENCE_RE.match(stripped)
        if fence_match:
            fence_marker = fence_match.group(1)[:3]
            code_lines = [line]
            i += 1
            while i < len(lines):
                code_lines.append(lines[i])
                if lines[i].strip().startswith(fence_marker) and len(code_lines) > 1:
                    i += 1
                    break
                i += 1
            content = '\n'.join(code_lines)
            elements.append(Element(
                elem_type='code',
                content=content,
                token_count=count_tokens(content),
                heading_path=list(heading_path),
                heading_level=0,
                line_start=line_no,
                line_end=line_no + len(code_lines) - 1,
            ))
            continue

        # 表格（跳过独立分隔行）
        if TABLE_ROW_RE.match(stripped) and not TABLE_SEPARATOR_RE.match(stripped):
            table_lines = []
            table_start = line_no
            while i < len(lines) and (
                TABLE_ROW_RE.match(lines[i].strip()) or
                TABLE_SEPARATOR_RE.match(lines[i].strip())
            ):
                table_lines.append(lines[i])
                i += 1
            content = '\n'.join(table_lines)
            elements.append(Element(
                elem_type='table',
                content=content,
                token_count=count_tokens(content),
                heading_path=list(heading_path),
                heading_level=0,
                line_start=table_start,
                line_end=table_start + len(table_lines) - 1,
            ))
            continue

        # 列表
        if LIST_ITEM_RE.match(stripped):
            list_lines = []
            list_start = line_no
            while i < len(lines):
                s = lines[i].strip()
                if not s:
                    if i + 1 < len(lines) and LIST_ITEM_RE.match(lines[i + 1].strip()):
                        list_lines.append(lines[i])
                        i += 1
                        continue
                    break
                if LIST_ITEM_RE.match(s) or (lines[i].startswith('  ') and list_lines):
                    list_lines.append(lines[i])
                    i += 1
                else:
                    break
            if list_lines:
                content = '\n'.join(list_lines)
                elements.append(Element(
                    elem_type='list',
                    content=content,
                    token_count=count_tokens(content),
                    heading_path=list(heading_path),
                    heading_level=0,
                    line_start=list_start,
                    line_end=list_start + len(list_lines) - 1,
                ))
            continue

        # 普通段落
        para_lines = []
        para_start = line_no
        while i < len(lines):
            s = lines[i].strip()
            if not s:
                break
            if HEADING_RE.match(s):  # 标题边界：立即断开
                break
            if CODE_FENCE_RE.match(s) or TABLE_ROW_RE.match(s):
                break
            if LIST_ITEM_RE.match(s) and para_lines:
                break
            para_lines.append(lines[i])
            i += 1
        if para_lines:
            content = '\n'.join(para_lines)
            elements.append(Element(
                elem_type='paragraph',
                content=content,
                token_count=count_tokens(content),
                heading_path=list(heading_path),
                heading_level=0,
                line_start=para_start,
                line_end=para_start + len(para_lines) - 1,
            ))

    return elements


def _split_table_element(element: Element, max_tokens: int) -> List[Element]:
    """将超大表格按行拆分，每个子表重复表头（借鉴 Unstructured）"""
    lines = element.content.split('\n')
    if len(lines) <= 3:
        return [element]

    # 找表头 + 分隔行
    header_lines: List[str] = []
    data_start = 0
    for idx, line in enumerate(lines):
        if TABLE_SEPARATOR_RE.match(line.strip()):
            header_lines = lines[:idx + 1]
            data_start = idx + 1
            break

    if not header_lines or data_start >= len(lines):
        return [element]

    data_lines = lines[data_start:]
    header_text = '\n'.join(header_lines)
    header_tokens = count_tokens(header_text)

    results: List[Element] = []
    current_lines: List[str] = []
    current_tokens = header_tokens

    for line in data_lines:
        line_tokens = count_tokens(line)
        if current_tokens + line_tokens > max_tokens and current_lines:
            sub_content = header_text + '\n' + '\n'.join(current_lines)
            results.append(Element(
                elem_type='table',
                content=sub_content,
                token_count=count_tokens(sub_content),
                heading_path=element.heading_path,
                heading_level=0,
                line_start=element.line_start,
                line_end=element.line_start + len(header_lines) + len(current_lines),
            ))
            current_lines = []
            current_tokens = header_tokens

        current_lines.append(line)
        current_tokens += line_tokens

    if current_lines:
        sub_content = header_text + '\n' + '\n'.join(current_lines)
        results.append(Element(
            elem_type='table',
            content=sub_content,
            token_count=count_tokens(sub_content),
            heading_path=element.heading_path,
            heading_level=0,
            line_start=element.line_end - len(current_lines),
            line_end=element.line_end,
        ))

    return results if results else [element]


def _split_code_element(element: Element, max_tokens: int) -> List[Element]:
    """将超大代码块按行拆分，每个子块保留代码围栏头"""
    lines = element.content.split('\n')
    if len(lines) <= 2:
        return [element]

    # 提取代码围栏头（```python）和尾（```）
    fence_head = lines[0]
    fence_tail = lines[-1] if lines[-1].strip().startswith('```') or lines[-1].strip().startswith('~~~') else ''
    body_lines = lines[1:-1] if fence_tail else lines[1:]

    if not body_lines:
        return [element]

    results: List[Element] = []
    current_lines: List[str] = []
    current_tokens = count_tokens(fence_head) + count_tokens(fence_tail)

    for line in body_lines:
        line_tokens = count_tokens(line)
        if current_tokens + line_tokens > max_tokens and current_lines:
            sub_content = fence_head + '\n' + '\n'.join(current_lines) + '\n' + fence_tail
            results.append(Element(
                elem_type='code',
                content=sub_content,
                token_count=count_tokens(sub_content),
                heading_path=element.heading_path,
                heading_level=0,
                line_start=element.line_start,
                line_end=element.line_start + len(current_lines),
            ))
            current_lines = []
            current_tokens = count_tokens(fence_head) + count_tokens(fence_tail)

        current_lines.append(line)
        current_tokens += line_tokens

    if current_lines:
        sub_content = fence_head + '\n' + '\n'.join(current_lines) + '\n' + fence_tail
        results.append(Element(
            elem_type='code',
            content=sub_content,
            token_count=count_tokens(sub_content),
            heading_path=element.heading_path,
            heading_level=0,
            line_start=element.line_end - len(current_lines),
            line_end=element.line_end,
        ))

    return results if results else [element]


# ============================================================
# 分块器
# ============================================================

class MarkdownHierarchicalChunker:
    """
    Markdown 分块器 v3.0（Section-Based 模式）

    核心原则：一个 chunk 要么是多个完整子标题的合并，要么是单个标题的部分拆分，绝不混搭。

    Args:
        min_tokens: chunk 最小 token（低于此值的 chunk 尝试与邻居合并）
        max_tokens: chunk 最大 token（超过此值的 section 被拆分）
        target_tokens: 合并小 section 时的目标大小
        prepend_heading_path: 是否注入标题面包屑
    """

    def __init__(
        self,
        min_tokens: int = 200,
        max_tokens: int = 800,
        target_tokens: int = 500,
        prepend_heading_path: bool = True,
        overlap_ratio: float = 0.15,
    ):
        self.min_tokens = min_tokens
        self.max_tokens = max_tokens
        self.target_tokens = target_tokens
        self.prepend_heading_path = prepend_heading_path
        self.overlap_ratio = overlap_ratio

    def chunk(self, markdown_text: str, doc_id: str = "") -> List[ChunkResult]:
        """对 markdown 进行分块"""
        if not markdown_text or not markdown_text.strip():
            return []

        # Step 1: 解析为 flat 元素列表
        elements = _parse_elements(markdown_text)
        if not elements:
            return []

        # Step 2: 按标题分组为 sections
        sections = self._group_into_sections(elements)

        # Step 3: 合并小 section + 拆分大 section → chunks
        chunks = self._merge_and_split(sections)

        # Step 4: 注入标题面包屑
        if self.prepend_heading_path:
            for c in chunks:
                if c.heading_path and not c.content.startswith('<!--'):
                    breadcrumb = ' > '.join(c.heading_path)
                    c.content = f"<!-- {breadcrumb} -->\n\n{c.content}"
                    c.token_count = count_tokens(c.content)

        # 分配 ID
        for i, c in enumerate(chunks):
            c.chunk_id = str(uuid.uuid4())
            c.metadata['chunk_index'] = i

        logger.info(
            f"[MdChunker] 分块完成: {len(chunks)} 个 chunk, "
            f"总 token={sum(c.token_count for c in chunks)}, "
            f"最小={min(c.token_count for c in chunks) if chunks else 0}, "
            f"最大={max(c.token_count for c in chunks) if chunks else 0}"
        )
        return chunks

    # ── Section 分组 ──────────────────────────────────────────────

    def _group_into_sections(self, elements: List[Element]) -> List[dict]:
        """
        将 flat 元素列表按 heading_path 分组为 sections。
        每个元素的 heading_path 已由 _parse_elements 正确标记，直接按此分组。
        """
        sections: List[dict] = []
        # 按 heading_path 分组，保持顺序
        path_key_map: Dict[str, int] = {}  # heading_path_str → section index
        heading_counter: Dict[str, int] = {}  # heading_path_str → heading_level
        heading_texts: Dict[tuple, str] = {}  # heading_path tuple → 标题文本

        for element in elements:
            if element.elem_type == 'heading':
                # 记录 heading_level 和标题文本
                # key 用完整路径（父路径 + 标题文本），与 section 的 key 一致
                parent_key = tuple(element.heading_path)
                full_key = parent_key + (element.content,)
                heading_counter[full_key] = element.heading_level
                heading_texts[full_key] = element.content
                continue

            key = tuple(element.heading_path)
            if key not in path_key_map:
                path_key_map[key] = len(sections)
                sections.append({
                    'heading_path': list(element.heading_path),
                    'heading_level': 0,
                    'heading_text': '',  # 标题文本（从 heading_texts 填充）
                    'elements': [],
                    'token_count': 0,
                })
            idx = path_key_map[key]
            sections[idx]['elements'].append(element)
            sections[idx]['token_count'] += element.token_count

        # 填充 heading_level 和 heading_text
        for s in sections:
            key = tuple(s['heading_path'])
            if key in heading_counter:
                s['heading_level'] = heading_counter[key]
            else:
                s['heading_level'] = 0
            s['heading_text'] = heading_texts.get(key, '')

        return sections

    # ── 合并 + 拆分 ──────────────────────────────────────────────

    def _merge_and_split(self, sections: List[dict]) -> List[ChunkResult]:
        """
        核心逻辑：
        1. 同级小 section → 合并（多个完整子标题）
        2. 大 section → 拆分（单个标题的部分内容）
        3. 不混搭：拆分后剩余部分不与下一个 section 合并
        """
        chunks: List[ChunkResult] = []
        # 合并缓冲区：收集同级小 section
        merge_buf: List[Element] = []
        merge_heading: List[str] = []
        merge_heading_level: int = 0
        merge_tokens: int = 0

        def flush_merge_buf():
            """将合并缓冲区输出为一个 chunk"""
            nonlocal merge_buf, merge_tokens, merge_heading, merge_heading_level
            if merge_buf:
                chunks.extend(self._split_elements(merge_buf, merge_heading))
                merge_buf = []
                merge_tokens = 0
                merge_heading = []
                merge_heading_level = 0

        for section in sections:
            elems = section['elements']
            tokens = section['token_count']
            heading = section['heading_path']
            heading_level = section['heading_level']

            if not elems:
                continue

            # 超大 section：先 flush 缓冲区，再单独拆分
            if tokens > self.max_tokens:
                flush_merge_buf()
                chunks.extend(self._split_elements(elems, heading))
                continue

            # 小 section：尝试与缓冲区合并
            # 条件：同属一个顶级标题、同级 heading level、且合并后不超限
            can_merge = (
                not merge_buf
                or (
                    self._same_top_heading(merge_heading, heading)
                    and heading_level == merge_heading_level
                    and merge_tokens + tokens <= self.target_tokens
                )
            )

            if can_merge:
                # 注入完整面包屑路径（<!-- path --> 格式）
                heading_text = section.get('heading_text', '')
                if heading_text and heading:
                    from service.tokenizer import count_tokens as _ct
                    full_path = ' > '.join(heading)
                    breadcrumb = f'<!-- {full_path} -->'
                    merge_buf.append(Element(
                        elem_type='heading',
                        content=breadcrumb,
                        token_count=_ct(breadcrumb),
                        heading_path=list(heading),
                        heading_level=heading_level,
                        line_start=0, line_end=0,
                    ))
                    merge_tokens += _ct(breadcrumb)
                merge_buf.extend(elems)
                merge_tokens += tokens
                if len(heading) > len(merge_heading):
                    merge_heading = heading
                    merge_heading_level = heading_level
            else:
                # 不能合并：先 flush 缓冲区，再开始新的
                flush_merge_buf()
                merge_buf = list(elems)
                merge_tokens = tokens
                merge_heading = list(heading)
                merge_heading_level = heading_level

            # 缓冲区达到目标大小，输出
            if merge_tokens >= self.target_tokens:
                flush_merge_buf()

        # 剩余缓冲区
        flush_merge_buf()

        # 后处理：吸收过小的 chunk（仅限同级且同主题）
        chunks = self._absorb_tiny_chunks(chunks)

        return chunks

    def _split_elements(self, elements: List[Element], heading_path: List[str]) -> List[ChunkResult]:
        """
        将一组元素拆分为一个或多个 chunk。
        - 超大表格/代码块单独拆分
        - 其余元素按 target_tokens 聚合
        - 拆分后的 chunk 共享同一个 heading_path
        """
        result: List[ChunkResult] = []
        accum: List[Element] = []
        accum_tokens = 0

        for elem in elements:
            # 超大表格：按行拆分
            if elem.elem_type == 'table' and elem.token_count > self.max_tokens:
                if accum:
                    result.append(self._make_chunk(accum, heading_path))
                    accum = []
                    accum_tokens = 0
                sub_tables = _split_table_element(elem, self.max_tokens)
                for st in sub_tables:
                    result.append(self._make_chunk([st], heading_path))
                continue

            # 超大代码块：按行拆分
            if elem.elem_type == 'code' and elem.token_count > self.max_tokens:
                if accum:
                    result.append(self._make_chunk(accum, heading_path))
                    accum = []
                    accum_tokens = 0
                sub_codes = _split_code_element(elem, self.max_tokens)
                for sc in sub_codes:
                    result.append(self._make_chunk([sc], heading_path))
                continue

            # 超大段落：按句子边界切分 + overlap
            if elem.elem_type == 'paragraph' and elem.token_count > self.max_tokens:
                if accum:
                    result.append(self._make_chunk(accum, heading_path))
                    accum = []
                    accum_tokens = 0
                sub_chunks = self._split_long_paragraph(elem)
                for sc in sub_chunks:
                    result.append(self._make_chunk([sc], heading_path))
                continue

            # 超大表格/代码块/其他：单独输出
            if elem.token_count > self.max_tokens:
                if accum:
                    result.append(self._make_chunk(accum, heading_path))
                    accum = []
                    accum_tokens = 0
                result.append(self._make_chunk([elem], heading_path))
                continue

            # 正常元素：累加前检查是否需要先输出
            if accum and accum_tokens + elem.token_count > self.max_tokens:
                # 加上这个元素会超 max → 先输出已累积的
                result.append(self._make_chunk(accum, heading_path))
                accum = []
                accum_tokens = 0
            elif accum and accum_tokens >= self.target_tokens:
                # 已达 target → 输出，开始新 chunk
                result.append(self._make_chunk(accum, heading_path))
                accum = []
                accum_tokens = 0

            accum.append(elem)
            accum_tokens += elem.token_count

        if accum:
            result.append(self._make_chunk(accum, heading_path))

        return result

    # ── 超长段落切分 ──────────────────────────────────────────────

    # 句子边界分隔符（中英文）
    _SENTENCE_SEPS = re.compile(r'(?<=[.!?。！？])\s+|(?<=[.!?。！？])(?=[A-Z])')

    def _split_long_paragraph(self, elem: Element) -> List[Element]:
        """
        将超长段落按句子边界切分为多个子 Element，相邻 chunk 之间有 overlap。
        """
        text = elem.content
        target = self.target_tokens
        max_tokens = self.max_tokens
        # overlap token 数：约为 target 的 15%，至少 1 个句子
        overlap_tokens = max(int(target * self.overlap_ratio), 30)

        # 1. 按句子切分
        sentences = self._SENTENCE_SEPS.split(text)
        sentences = [s.strip() for s in sentences if s.strip()]
        if len(sentences) <= 1:
            # 只有一个句子或无法切分，直接返回
            return [elem]

        # 2. 累加句子，按 token 分组
        chunks_data: List[dict] = []  # [{'sentences': [...], 'tokens': N}, ...]
        current_sents: List[str] = []
        current_tokens = 0

        for sent in sentences:
            sent_tokens = count_tokens(sent)
            # 如果加上这个句子会超 max，先输出当前累积
            if current_sents and current_tokens + sent_tokens > max_tokens:
                chunks_data.append({'sentences': list(current_sents), 'tokens': current_tokens})
                # overlap：保留最后几个句子作为下一段的开头
                overlap_sents, overlap_tok = self._get_overlap_tail(current_sents, overlap_tokens)
                current_sents = overlap_sents
                current_tokens = overlap_tok
            current_sents.append(sent)
            current_tokens += sent_tokens

        if current_sents:
            chunks_data.append({'sentences': list(current_sents), 'tokens': current_tokens})

        # 3. 转为 Element
        result: List[Element] = []
        for cd in chunks_data:
            content = ' '.join(cd['sentences'])
            result.append(Element(
                elem_type='paragraph',
                content=content,
                token_count=cd['tokens'],
                heading_path=list(elem.heading_path),
                heading_level=0,
                line_start=elem.line_start,
                line_end=elem.line_end,
            ))

        return result

    @staticmethod
    def _get_overlap_tail(sentences: List[str], overlap_tokens: int) -> tuple:
        """从句子列表尾部取 overlap_tokens 个 token 的句子"""
        if not sentences:
            return [], 0
        overlap_sents: List[str] = []
        total = 0
        # 从后往前取
        for sent in reversed(sentences):
            t = count_tokens(sent)
            if total + t > overlap_tokens and overlap_sents:
                break
            overlap_sents.append(sent)
            total += t
        overlap_sents.reverse()
        return overlap_sents, total

    # ── 小 chunk 吸收 ────────────────────────────────────────────

    @staticmethod
    def _same_top_heading(path_a: List[str], path_b: List[str]) -> bool:
        """判断两个 heading_path 是否属于同一个顶级主题"""
        if not path_a or not path_b:
            return True
        return path_a[0] == path_b[0]

    def _absorb_tiny_chunks(self, chunks: List[ChunkResult]) -> List[ChunkResult]:
        """
        后处理：吸收过小的 chunk 到邻居。
        严格限制：必须同属一个顶级主题，且同级标题路径。
        """
        if len(chunks) <= 1:
            return chunks

        relaxed_max = self.max_tokens * 2
        i = 1
        while i < len(chunks):
            curr = chunks[i]
            if curr.token_count >= self.min_tokens:
                i += 1
                continue

            merged = False
            # 向前合并
            prev = chunks[i - 1]
            if prev.token_count + curr.token_count <= relaxed_max:
                if self._same_top_heading(prev.heading_path, curr.heading_path):
                    prev.content = prev.content + '\n\n' + curr.content
                    prev.token_count = count_tokens(prev.content)
                    prev.end_line = curr.end_line
                    prev.block_count += curr.block_count
                    if len(curr.heading_path) > len(prev.heading_path):
                        prev.heading_path = curr.heading_path
                    chunks.pop(i)
                    merged = True

            # 向后合并
            if not merged and i + 1 < len(chunks):
                nxt = chunks[i + 1]
                if curr.token_count + nxt.token_count <= relaxed_max:
                    if self._same_top_heading(curr.heading_path, nxt.heading_path):
                        nxt.content = curr.content + '\n\n' + nxt.content
                        nxt.token_count = count_tokens(nxt.content)
                        nxt.start_line = curr.start_line
                        nxt.block_count += curr.block_count
                        chunks.pop(i)
                        merged = True

            if not merged:
                i += 1

        return chunks

    # ── 工具方法 ──────────────────────────────────────────────────

    def _make_chunk(self, elements: List[Element], heading_path: List[str]) -> ChunkResult:
        """将多个元素合并为一个 chunk"""
        content = '\n\n'.join(e.content for e in elements)
        token_count = sum(e.token_count for e in elements)
        return ChunkResult(
            chunk_id='',
            content=content,
            heading_path=heading_path,
            heading_level=max((e.heading_level for e in elements), default=0),
            token_count=token_count,
            start_line=elements[0].line_start,
            end_line=elements[-1].line_end,
            block_count=len(elements),
        )


# ============================================================
# 便捷函数
# ============================================================

def chunk_markdown(
    markdown_text: str,
    doc_id: str = "",
    min_tokens: int = None,
    max_tokens: int = None,
    target_tokens: int = None,
    prepend_heading_path: bool = None,
    overlap_ratio: float = None,
) -> List[Dict[str, Any]]:
    """便捷函数：分块并返回字典列表（默认从 Settings 读取参数）"""
    from config.settings import Settings
    s = Settings()
    chunker = MarkdownHierarchicalChunker(
        min_tokens=min_tokens if min_tokens is not None else s.md_chunk_min_tokens,
        max_tokens=max_tokens if max_tokens is not None else s.md_chunk_max_tokens,
        target_tokens=target_tokens if target_tokens is not None else s.md_chunk_target_tokens,
        prepend_heading_path=prepend_heading_path if prepend_heading_path is not None else s.md_chunk_prepend_heading,
        overlap_ratio=overlap_ratio if overlap_ratio is not None else s.md_chunk_overlap_ratio,
    )
    results = chunker.chunk(markdown_text, doc_id)

    return [
        {
            'chunk_id': r.chunk_id,
            'content': r.content,
            'heading_path': r.heading_path,
            'heading_level': r.heading_level,
            'token_count': r.token_count,
            'start_char': 0,
            'end_char': len(r.content),
            'chunk_order': r.metadata.get('chunk_index', 0),
            'metadata': {
                'heading_path': r.heading_path,
                'heading_level': r.heading_level,
                'block_count': r.block_count,
                'start_line': r.start_line,
                'end_line': r.end_line,
            },
        }
        for r in results
    ]
