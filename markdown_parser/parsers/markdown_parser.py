"""
Markdown解析器
"""

import re
from typing import List, Dict, Optional
from dataclasses import dataclass, field


@dataclass
class MarkdownSection:
    """Markdown章节"""
    title: str
    level: int
    content: str
    start_line: int
    end_line: int
    children: List['MarkdownSection'] = field(default_factory=list)
    parent: Optional['MarkdownSection'] = None


class MarkdownParser:
    """Markdown解析器"""

    def __init__(self):
        self.heading_pattern = re.compile(r'^(#{1,6})\s+(.+)$', re.MULTILINE)

    def parse(self, markdown_text: str) -> List[MarkdownSection]:
        """
        解析markdown文本，返回章节列表

        Args:
            markdown_text: markdown文本

        Returns:
            章节列表
        """
        lines = markdown_text.split('\n')
        sections = []
        current_section = None
        current_content = []

        for i, line in enumerate(lines):
            match = self.heading_pattern.match(line.strip())

            if match:
                if current_section is not None:
                    current_section.content = '\n'.join(current_content).strip()
                    current_section.end_line = i - 1
                    sections.append(current_section)

                level = len(match.group(1))
                title = match.group(2).strip()

                current_section = MarkdownSection(
                    title=title,
                    level=level,
                    content='',
                    start_line=i,
                    end_line=len(lines) - 1
                )
                current_content = []
            else:
                current_content.append(line)

        if current_section is not None:
            current_section.content = '\n'.join(current_content).strip()
            current_section.end_line = len(lines) - 1
            sections.append(current_section)

        if not sections:
            sections.append(MarkdownSection(
                title="Untitled",
                level=1,
                content=markdown_text.strip(),
                start_line=0,
                end_line=len(lines) - 1
            ))

        self._build_hierarchy(sections)

        return sections

    def _build_hierarchy(self, sections: List[MarkdownSection]):
        """构建章节层级关系"""
        if not sections:
            return

        stack = [sections[0]]

        for section in sections[1:]:
            while stack and stack[-1].level >= section.level:
                stack.pop()

            if stack:
                section.parent = stack[-1]
                stack[-1].children.append(section)

            stack.append(section)

    def get_section_tree(self, sections: List[MarkdownSection]) -> Dict:
        """获取章节树结构"""
        if not sections:
            return {}

        root_sections = [s for s in sections if s.parent is None]

        def build_tree(section):
            tree = {
                "title": section.title,
                "level": section.level,
                "content_length": len(section.content),
                "children": []
            }

            for child in section.children:
                tree["children"].append(build_tree(child))

            return tree

        if len(root_sections) == 1:
            return build_tree(root_sections[0])
        else:
            return {
                "title": "Root",
                "level": 0,
                "children": [build_tree(s) for s in root_sections]
            }

    def extract_sections_by_level(self, sections: List[MarkdownSection], level: int) -> List[MarkdownSection]:
        """按层级提取章节"""
        return [s for s in sections if s.level == level]

    def merge_short_sections(self, sections: List[MarkdownSection], min_length: int = 100) -> List[MarkdownSection]:
        """合并过短的章节"""
        if not sections:
            return []

        merged = []
        current = sections[0]

        for section in sections[1:]:
            if len(current.content) < min_length and current.level >= section.level:
                current.content += '\n\n' + section.content
                current.end_line = section.end_line
            else:
                merged.append(current)
                current = section

        merged.append(current)

        return merged

    def get_breadcrumb(self, section: MarkdownSection) -> str:
        """获取章节的面包屑路径"""
        breadcrumb = [section.title]
        parent = section.parent

        while parent:
            breadcrumb.insert(0, parent.title)
            parent = parent.parent

        return ' > '.join(breadcrumb)
