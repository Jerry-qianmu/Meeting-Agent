"""
Token计数器工具
"""

import tiktoken
from typing import Optional


class TokenCounter:
    """Token计数器"""

    def __init__(self, model: str = "gpt-3.5-turbo"):
        """
        初始化token计数器

        Args:
            model: 模型名称，用于选择对应的tokenizer
        """
        try:
            self.encoding = tiktoken.encoding_for_model(model)
        except KeyError:
            self.encoding = tiktoken.get_encoding("cl100k_base")

    def count(self, text: str) -> int:
        """
        计算文本的token数量

        Args:
            text: 输入文本

        Returns:
            token数量
        """
        if not text:
            return 0
        return len(self.encoding.encode(text))

    def count_batch(self, texts: list) -> list:
        """
        批量计算token数量

        Args:
            texts: 文本列表

        Returns:
            token数量列表
        """
        return [self.count(text) for text in texts]

    def truncate(self, text: str, max_tokens: int) -> str:
        """
        截断文本到指定token数

        Args:
            text: 输入文本
            max_tokens: 最大token数

        Returns:
            截断后的文本
        """
        tokens = self.encoding.encode(text)
        if len(tokens) <= max_tokens:
            return text

        truncated_tokens = tokens[:max_tokens]
        return self.encoding.decode(truncated_tokens)

    def split_by_tokens(self, text: str, chunk_size: int, overlap: int = 0) -> list:
        """
        按token数分割文本

        Args:
            text: 输入文本
            chunk_size: 每个chunk的token数
            overlap: 重叠的token数

        Returns:
            分割后的文本列表
        """
        tokens = self.encoding.encode(text)

        if len(tokens) <= chunk_size:
            return [text]

        chunks = []
        start = 0

        while start < len(tokens):
            end = min(start + chunk_size, len(tokens))
            chunk_tokens = tokens[start:end]
            chunk_text = self.encoding.decode(chunk_tokens)
            chunks.append(chunk_text)

            start = end - overlap if overlap > 0 else end

            if end >= len(tokens):
                break

        return chunks

    def find_split_point(self, text: str, target_tokens: int, direction: str = "forward") -> int:
        """
        在文本中找到合适的分割点（在句子或段落边界）

        Args:
            text: 输入文本
            target_tokens: 目标token数
            direction: 查找方向，forward或backward

        Returns:
            分割点位置（字符索引）
        """
        tokens = self.encoding.encode(text)

        if len(tokens) <= target_tokens:
            return len(text)

        target_text = self.encoding.decode(tokens[:target_tokens])

        sentence_endings = ['.', '!', '?', '。', '！', '？', '\n']

        if direction == "forward":
            for i in range(len(target_text) - 1, -1, -1):
                if target_text[i] in sentence_endings:
                    return i + 1
        else:
            for i in range(len(target_text)):
                if target_text[i] in sentence_endings:
                    return i + 1

        return len(target_text)


token_counter = TokenCounter()
