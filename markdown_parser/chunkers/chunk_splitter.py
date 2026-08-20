"""
Chunk分割器 - 基于token数量的智能分块
"""

import re
from typing import List, Dict, Optional
from dataclasses import dataclass, field
from ..config import ChunkConfig
from ..utils.token_counter import TokenCounter
from ..ner.entity_extractor import Entity


@dataclass
class Chunk:
    """Chunk类"""
    id: str
    content: str
    token_count: int
    start_pos: int
    end_pos: int
    section_title: str = ""
    breadcrumb: str = ""
    entities: List[Entity] = field(default_factory=list)
    is_structured: bool = False
    chunk_type: str = "text"

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "content": self.content,
            "token_count": self.token_count,
            "start_pos": self.start_pos,
            "end_pos": self.end_pos,
            "section_title": self.section_title,
            "breadcrumb": self.breadcrumb,
            "entities": [e.to_dict() for e in self.entities],
            "is_structured": self.is_structured,
            "chunk_type": self.chunk_type
        }


class ChunkSplitter:
    """Chunk分割器"""

    def __init__(self, config: ChunkConfig = None):
        self.config = config or ChunkConfig()
        self.token_counter = TokenCounter()
        self.chunk_counter = 0

    def split(self, text: str, section_title: str = "", breadcrumb: str = "") -> List[Chunk]:
        """
        分割文本为chunks

        分块策略：
        1. 先按段落分割（支持多种分段方式）
        2. 每个段落作为一个独立的chunk
        3. 只有连续的短段落才合并
        """
        if not text.strip():
            return []

        self.chunk_counter = 0

        # Step 1: 按段落分割
        paragraphs = self._split_paragraphs(text)

        # Step 2: 处理每个段落
        chunks = self._process_paragraphs(paragraphs, section_title, breadcrumb)

        return chunks

    def _split_paragraphs(self, text: str) -> List[Dict]:
        """
        按段落分割文本

        支持多种分段方式：
        1. 空行分隔
        2. 首行缩进（中文论文常见）
        3. 段落首行不缩进但有明显边界
        """
        paragraphs = []
        lines = text.split('\n')

        current_para = []
        current_start = 0
        char_pos = 0

        for i, line in enumerate(lines):
            line_stripped = line.strip()

            # 判断是否为段落边界
            is_paragraph_boundary = False

            # 规则1: 空行
            if line_stripped == '':
                is_paragraph_boundary = True

            # 规则2: 首行缩进（4个空格或1个tab）
            elif line.startswith('    ') or line.startswith('\t'):
                # 如果当前有累积的段落，先保存
                if current_para:
                    is_paragraph_boundary = True

            # 规则3: 新的句子开头（大写字母或中文开头，且前面有内容）
            elif current_para and len(current_para) > 0:
                # 检查是否是新段落的开始
                prev_line = current_para[-1].strip() if current_para else ''
                if prev_line and self._is_sentence_end(prev_line):
                    # 前一行是句子结尾，当前行是新段落
                    if line_stripped and line_stripped[0].isupper():
                        is_paragraph_boundary = True

            if is_paragraph_boundary and current_para:
                para_text = '\n'.join(current_para)
                if para_text.strip():
                    paragraphs.append({
                        "text": para_text,
                        "start": current_start,
                        "end": current_start + len(para_text),
                        "tokens": self.token_counter.count(para_text)
                    })
                current_para = []
                current_start = char_pos
            else:
                current_para.append(line)

            char_pos += len(line) + 1  # +1 for newline

        # 处理最后一个段落
        if current_para:
            para_text = '\n'.join(current_para)
            if para_text.strip():
                paragraphs.append({
                    "text": para_text,
                    "start": current_start,
                    "end": current_start + len(para_text),
                    "tokens": self.token_counter.count(para_text)
                })

        return paragraphs

    def _is_sentence_end(self, line: str) -> bool:
        """判断行是否以句子结尾"""
        line = line.rstrip()
        if not line:
            return False

        # 英文句子结尾
        if line.endswith(('.', '!', '?')):
            return True

        # 中文句子结尾
        if line.endswith(('。', '！', '？', '；')):
            return True

        # 引用标记 [1, 2] 或 [1-5]
        if re.search(r'\[\d+(?:,\s*\d+)*\]\s*$', line):
            return True

        return False

    def _process_paragraphs(self, paragraphs: List[Dict], section_title: str, breadcrumb: str) -> List[Chunk]:
        """
        处理段落列表，生成chunks

        策略：
        - 每个段落默认独立作为一个chunk
        - 只有当段落太短且下一个段落也短时才合并
        - 合并后不能超过max_tokens
        """
        if not paragraphs:
            return []

        chunks = []
        i = 0

        while i < len(paragraphs):
            para = paragraphs[i]
            para_tokens = para["tokens"]

            # 情况1: 段落token数在合理范围内，直接作为chunk
            if para_tokens >= self.config.min_tokens:
                if para_tokens <= self.config.max_tokens:
                    chunk = self._create_chunk(
                        para["text"],
                        para["start"],
                        para["end"],
                        section_title,
                        breadcrumb
                    )
                    chunks.append(chunk)
                    i += 1
                else:
                    # 段落太长，需要分割
                    sub_chunks = self._split_long_paragraph(para, section_title, breadcrumb)
                    chunks.extend(sub_chunks)
                    i += 1

            # 情况2: 段落太短，尝试与下一个段落合并
            else:
                merged_text = para["text"]
                merged_start = para["start"]
                merged_end = para["end"]
                merged_tokens = para_tokens
                merge_count = 0

                # 向后查看，尝试合并连续的短段落
                j = i + 1
                while j < len(paragraphs):
                    next_para = paragraphs[j]
                    next_tokens = next_para["tokens"]

                    # 如果合并后超过max_tokens，停止
                    if merged_tokens + next_tokens > self.config.max_tokens:
                        break

                    # 合并段落
                    merged_text += '\n\n' + next_para["text"]
                    merged_end = next_para["end"]
                    merged_tokens += next_tokens
                    merge_count += 1
                    j += 1

                    # 如果合并后达到min_tokens，停止
                    if merged_tokens >= self.config.min_tokens:
                        break

                # 创建合并后的chunk
                if merge_count > 0:
                    chunk = self._create_chunk(
                        merged_text,
                        merged_start,
                        merged_end,
                        section_title,
                        breadcrumb
                    )
                    chunks.append(chunk)
                    i = j
                else:
                    # 没有合并，单独作为一个chunk（即使很短）
                    chunk = self._create_chunk(
                        para["text"],
                        para["start"],
                        para["end"],
                        section_title,
                        breadcrumb
                    )
                    chunks.append(chunk)
                    i += 1

        return chunks

    def _split_long_paragraph(self, paragraph: Dict, section_title: str, breadcrumb: str) -> List[Chunk]:
        """
        分割长段落

        在句子边界处分割
        """
        text = paragraph["text"]
        start_pos = paragraph["start"]

        # 按句子分割
        sentences = self._split_sentences(text)

        chunks = []
        current_chunk_sentences = []
        current_chunk_tokens = 0
        current_start = start_pos

        for sentence in sentences:
            sentence_tokens = self.token_counter.count(sentence)

            # 如果单个句子就超过max_tokens，需要按token分割
            if sentence_tokens > self.config.max_tokens:
                # 保存当前chunk
                if current_chunk_sentences:
                    chunk_text = ' '.join(current_chunk_sentences)
                    chunk = self._create_chunk(
                        chunk_text,
                        current_start,
                        current_start + len(chunk_text),
                        section_title,
                        breadcrumb
                    )
                    chunks.append(chunk)
                    current_chunk_sentences = []
                    current_chunk_tokens = 0
                    current_start = current_start + len(chunk_text) + 1

                # 分割长句子
                sub_chunks = self._split_by_tokens(sentence, current_start, section_title, breadcrumb)
                chunks.extend(sub_chunks)
                if sub_chunks:
                    current_start = sub_chunks[-1].end_pos

            # 如果加上这个句子超过max_tokens，保存当前chunk
            elif current_chunk_tokens + sentence_tokens > self.config.max_tokens:
                if current_chunk_sentences:
                    chunk_text = ' '.join(current_chunk_sentences)
                    chunk = self._create_chunk(
                        chunk_text,
                        current_start,
                        current_start + len(chunk_text),
                        section_title,
                        breadcrumb
                    )
                    chunks.append(chunk)
                    current_start = current_start + len(chunk_text) + 1

                current_chunk_sentences = [sentence]
                current_chunk_tokens = sentence_tokens

            else:
                current_chunk_sentences.append(sentence)
                current_chunk_tokens += sentence_tokens

        # 处理最后一个chunk
        if current_chunk_sentences:
            chunk_text = ' '.join(current_chunk_sentences)
            chunk = self._create_chunk(
                chunk_text,
                current_start,
                current_start + len(chunk_text),
                section_title,
                breadcrumb
            )
            chunks.append(chunk)

        return chunks

    def _split_sentences(self, text: str) -> List[str]:
        """按句子分割文本"""
        # 中英文句子结束符
        sentence_endings = re.compile(r'(?<=[。！？.!?])\s*')

        sentences = sentence_endings.split(text)

        # 过滤空句子
        sentences = [s.strip() for s in sentences if s.strip()]

        return sentences

    def _split_by_tokens(self, text: str, start_pos: int, section_title: str, breadcrumb: str) -> List[Chunk]:
        """按token数分割文本"""
        chunks = []
        tokens = self.token_counter.encoding.encode(text)

        current_start = 0
        while current_start < len(tokens):
            end = min(current_start + self.config.target_tokens, len(tokens))
            chunk_tokens = tokens[current_start:end]
            chunk_text = self.token_counter.encoding.decode(chunk_tokens)

            # 尝试在句子边界处分割
            split_point = self.token_counter.find_split_point(chunk_text, self.config.target_tokens)
            if split_point < len(chunk_text):
                chunk_text = chunk_text[:split_point]

            chunk = self._create_chunk(
                chunk_text,
                start_pos + current_start,
                start_pos + current_start + len(chunk_text),
                section_title,
                breadcrumb
            )
            chunks.append(chunk)

            # 移动到下一个位置
            actual_tokens = self.token_counter.encoding.encode(chunk_text)
            current_start += len(actual_tokens)

        return chunks

    def _create_chunk(self, text: str, start: int, end: int, section_title: str, breadcrumb: str) -> Chunk:
        """创建chunk对象"""
        self.chunk_counter += 1

        return Chunk(
            id=f"chunk_{self.chunk_counter}",
            content=text,
            token_count=self.token_counter.count(text),
            start_pos=start,
            end_pos=end,
            section_title=section_title,
            breadcrumb=breadcrumb
        )

    def assign_entities_to_chunks(self, chunks: List[Chunk], entities: List[Entity]) -> List[Chunk]:
        """将实体分配到对应的chunks"""
        for entity in entities:
            for chunk in chunks:
                # 检查实体是否在chunk范围内
                if entity.start >= chunk.start_pos and entity.end <= chunk.end_pos:
                    chunk.entities.append(entity)
                    break

        return chunks

    def create_image_placeholder(self, image_path: str, section_title: str, breadcrumb: str) -> Chunk:
        """创建图片占位chunk（预留接口）"""
        self.chunk_counter += 1

        return Chunk(
            id=f"chunk_img_{self.chunk_counter}",
            content=f"[IMAGE: {image_path}]",
            token_count=0,
            start_pos=0,
            end_pos=0,
            section_title=section_title,
            breadcrumb=breadcrumb,
            chunk_type="image"
        )
