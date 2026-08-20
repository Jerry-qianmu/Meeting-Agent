# -*- coding: utf-8 -*-
"""
Markdown 结构解析器
从 Markdown 文本中提取标题层级、表格、引用等结构化信息
"""

import re
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


class MarkdownParser:
    """Markdown 文档解析器，提取结构化信息"""

    def __init__(self):
        self.heading_pattern = re.compile(r'^(#{1,6})\s+(.+)$', re.MULTILINE)
        self.table_pattern = re.compile(r'^\|(.+)\|$', re.MULTILINE)
        self.ref_pattern = re.compile(
            r'(?:见|详见|参见|参考|如图|如表|图|表|第)\s*'
            r'(\d+(?:\.\d+)*|[一二三四五六七八九十]+(?:\.[一二三四五六七八九十]+)*)',
            re.MULTILINE
        )

    def parse(self, markdown_text: str) -> dict:
        """
        解析 Markdown，返回结构化数据

        Returns:
            dict: {
                "sections": [{"level": int, "title": str, "content": str, "start_pos": int}],
                "tables": [{"headers": [str], "rows": [[str]], "position": int}],
                "references": [{"target": str, "context": str, "position": int}],
                "raw_text": str,
            }
        """
        sections = self._extract_sections(markdown_text)
        tables = self._extract_tables(markdown_text)
        references = self._extract_references(markdown_text)

        logger.info(
            f"[MarkdownParser] 解析完成: {len(sections)} 个章节, "
            f"{len(tables)} 个表格, {len(references)} 个引用"
        )

        return {
            "sections": sections,
            "tables": tables,
            "references": references,
            "raw_text": markdown_text,
        }

    def _extract_sections(self, text: str) -> List[Dict[str, Any]]:
        """提取标题层级结构"""
        sections = []
        lines = text.split('\n')
        current_section = None
        content_buffer = []
        char_pos = 0

        for line in lines:
            match = self.heading_pattern.match(line.strip())

            if match:
                # 保存上一个 section 的内容
                if current_section:
                    current_section['content'] = '\n'.join(content_buffer).strip()
                    sections.append(current_section)

                level = len(match.group(1))
                title = match.group(2).strip()
                current_section = {
                    'level': level,
                    'title': title,
                    'content': '',
                    'start_pos': char_pos,
                }
                content_buffer = []
            else:
                content_buffer.append(line)

            char_pos += len(line) + 1  # +1 for newline

        # 保存最后一个 section
        if current_section:
            current_section['content'] = '\n'.join(content_buffer).strip()
            sections.append(current_section)

        # 如果没有找到任何标题，将整个文本作为一个 section
        if not sections and text.strip():
            sections.append({
                'level': 1,
                'title': 'Untitled',
                'content': text.strip(),
                'start_pos': 0,
            })

        return sections

    def _extract_tables(self, text: str) -> List[Dict[str, Any]]:
        """提取表格结构"""
        tables = []
        lines = text.split('\n')
        in_table = False
        table_lines = []
        table_start_pos = 0
        current_pos = 0

        for line in lines:
            stripped = line.strip()
            if stripped.startswith('|') and stripped.endswith('|'):
                if not in_table:
                    in_table = True
                    table_lines = []
                    table_start_pos = current_pos
                table_lines.append(stripped)
            else:
                if in_table and table_lines:
                    table = self._parse_table_lines(table_lines)
                    if table:
                        table['position'] = table_start_pos
                        tables.append(table)
                    table_lines = []
                in_table = False

            current_pos += len(line) + 1

        # 处理文末的表格
        if table_lines:
            table = self._parse_table_lines(table_lines)
            if table:
                table['position'] = table_start_pos
                tables.append(table)

        return tables

    def _parse_table_lines(self, lines: List[str]) -> Optional[Dict[str, Any]]:
        """解析表格行为结构化数据"""
        if len(lines) < 2:
            return None

        def split_row(line):
            return [cell.strip() for cell in line.strip('|').split('|')]

        headers = split_row(lines[0])
        # 跳过分隔行（第二行通常是 |---|---|）
        rows = []
        for line in lines[2:]:
            if not all(c in '-| ' for c in line):
                rows.append(split_row(line))

        return {"headers": headers, "rows": rows}

    def _extract_references(self, text: str) -> List[Dict[str, Any]]:
        """提取文档内部引用"""
        references = []
        for match in self.ref_pattern.finditer(text):
            ref_target = match.group(1)
            ref_context = text[max(0, match.start() - 50):match.end() + 50]
            references.append({
                "target": ref_target,
                "context": ref_context,
                "position": match.start(),
            })
        return references
