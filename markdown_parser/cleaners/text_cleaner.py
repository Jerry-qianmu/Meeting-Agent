"""
文本清理器 - 处理页眉页脚、噪声等
"""

import re
from typing import List, Dict, Tuple
from ..config import CleanerConfig


class TextCleaner:
    """文本清理器"""

    def __init__(self, config: CleanerConfig = None):
        self.config = config or CleanerConfig()
        self._compile_patterns()

    def _compile_patterns(self):
        """预编译正则表达式"""
        self.header_footer_regex = [
            re.compile(p, re.IGNORECASE) for p in self.config.header_footer_patterns
        ]
        self.noise_regex = [
            re.compile(p, re.IGNORECASE) for p in self.config.noise_patterns
        ]

    def clean(self, text: str) -> Tuple[str, List[Dict]]:
        """清理文本"""
        lines = text.split('\n')
        cleaned_lines = []
        removed_items = []

        for i, line in enumerate(lines):
            if self._is_header_footer(line):
                removed_items.append({
                    "type": "header_footer",
                    "line": i + 1,
                    "content": line.strip()
                })
                continue

            if self._is_noise(line):
                removed_items.append({
                    "type": "noise",
                    "line": i + 1,
                    "content": line.strip()
                })
                continue

            cleaned_line = self._clean_line(line)
            if cleaned_line is not None:
                cleaned_lines.append(cleaned_line)

        cleaned_text = '\n'.join(cleaned_lines)
        cleaned_text = self._remove_extra_newlines(cleaned_text)

        return cleaned_text, removed_items

    def _is_header_footer(self, line: str) -> bool:
        """判断是否为页眉页脚"""
        line = line.strip()
        if not line:
            return False

        for pattern in self.header_footer_regex:
            if pattern.match(line):
                return True

        return False

    def _is_noise(self, line: str) -> bool:
        """判断是否为噪声"""
        line = line.strip()
        if not line:
            return True

        for pattern in self.noise_regex:
            if pattern.match(line):
                return True

        return False

    def _clean_line(self, line: str) -> str:
        """清理单行内容"""
        line = line.strip()

        if len(line) < self.config.min_content_length:
            return None

        line = self._clean_special_chars(line)

        return line

    def _clean_special_chars(self, text: str) -> str:
        """清理特殊字符"""
        text = re.sub(r'[​‌‍﻿]', '', text)
        text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
        return text

    def _remove_extra_newlines(self, text: str) -> str:
        """移除多余的空行"""
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()

    def extract_metadata(self, text: str) -> Dict[str, str]:
        """提取文档元数据"""
        metadata = {}

        page_match = re.search(r'第\s*(\d+)\s*页', text)
        if page_match:
            metadata['page'] = page_match.group(1)

        date_match = re.search(r'(\d{4}年\d{1,2}月\d{1,2}日)', text)
        if date_match:
            metadata['date'] = date_match.group(1)

        lines = text.split('\n')
        for line in lines:
            line = line.strip()
            if line and len(line) > 5:
                metadata['title'] = line
                break

        return metadata

    def remove_references_section(self, text: str) -> Tuple[str, str]:
        """移除参考文献部分"""
        ref_patterns = [
            r'^#{1,3}\s*References\s*$',
            r'^#{1,3}\s*参考文献\s*$',
            r'^#{1,3}\s*Bibliography\s*$',
        ]

        for pattern in ref_patterns:
            match = re.search(pattern, text, re.MULTILINE | re.IGNORECASE)
            if match:
                main_text = text[:match.start()].strip()
                references = text[match.start():].strip()
                return main_text, references

        return text, ""
