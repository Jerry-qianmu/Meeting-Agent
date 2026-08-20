"""
JSON解析器 - 处理PDF转MD工具生成的JSON文件
"""

import json
from typing import List, Dict, Optional
from dataclasses import dataclass, field


@dataclass
class ContentBlock:
    """内容块"""
    block_type: str  # text, image, table, equation
    content: str
    page_idx: int
    bbox: List[float] = field(default_factory=list)
    metadata: Dict = field(default_factory=dict)


@dataclass
class ImageBlock(ContentBlock):
    """图片块"""
    img_path: str = ""
    image_caption: List[str] = field(default_factory=list)
    image_footnote: List[str] = field(default_factory=list)


@dataclass
class TextBlock(ContentBlock):
    """文本块"""
    text_level: int = 0  # 0=正文, 1=一级标题, 2=二级标题, etc.


class JsonParser:
    """JSON解析器"""

    def __init__(self):
        pass

    def parse(self, json_path: str) -> Dict:
        """
        解析JSON文件

        Args:
            json_path: JSON文件路径

        Returns:
            解析结果字典
        """
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        return self._parse_content(data)

    def parse_data(self, data: List[Dict]) -> Dict:
        """
        解析JSON数据

        Args:
            data: JSON数据列表

        Returns:
            解析结果字典
        """
        return self._parse_content(data)

    def _parse_content(self, data: List[Dict]) -> Dict:
        """解析内容"""
        text_blocks = []
        image_blocks = []
        table_blocks = []
        equation_blocks = []

        for item in data:
            item_type = item.get("type", "text")

            if item_type == "text":
                block = self._parse_text_block(item)
                text_blocks.append(block)
            elif item_type == "image":
                block = self._parse_image_block(item)
                image_blocks.append(block)
            elif item_type == "table":
                block = self._parse_table_block(item)
                table_blocks.append(block)
            elif item_type == "equation":
                block = self._parse_equation_block(item)
                equation_blocks.append(block)

        return {
            "text_blocks": text_blocks,
            "image_blocks": image_blocks,
            "table_blocks": table_blocks,
            "equation_blocks": equation_blocks,
            "total_blocks": len(data)
        }

    def _parse_text_block(self, item: Dict) -> TextBlock:
        """解析文本块"""
        return TextBlock(
            block_type="text",
            content=item.get("text", ""),
            page_idx=item.get("page_idx", 0),
            bbox=item.get("bbox", []),
            text_level=item.get("text_level", 0),
            metadata={
                "text_level": item.get("text_level", 0)
            }
        )

    def _parse_image_block(self, item: Dict) -> ImageBlock:
        """解析图片块"""
        return ImageBlock(
            block_type="image",
            content=item.get("content", ""),
            page_idx=item.get("page_idx", 0),
            bbox=item.get("bbox", []),
            img_path=item.get("img_path", ""),
            image_caption=item.get("image_caption", []),
            image_footnote=item.get("image_footnote", []),
            metadata={
                "img_path": item.get("img_path", ""),
                "image_caption": item.get("image_caption", []),
                "image_footnote": item.get("image_footnote", [])
            }
        )

    def _parse_table_block(self, item: Dict) -> ContentBlock:
        """解析表格块"""
        return ContentBlock(
            block_type="table",
            content=item.get("content", ""),
            page_idx=item.get("page_idx", 0),
            bbox=item.get("bbox", []),
            metadata={
                "table_caption": item.get("table_caption", []),
                "table_footnote": item.get("table_footnote", [])
            }
        )

    def _parse_equation_block(self, item: Dict) -> ContentBlock:
        """解析公式块"""
        return ContentBlock(
            block_type="equation",
            content=item.get("content", ""),
            page_idx=item.get("page_idx", 0),
            bbox=item.get("bbox", []),
            metadata={
                "equation": item.get("equation", "")
            }
        )

    def extract_sections(self, text_blocks: List[TextBlock]) -> List[Dict]:
        """
        从文本块中提取章节结构

        Args:
            text_blocks: 文本块列表

        Returns:
            章节列表
        """
        sections = []
        current_section = None
        current_content = []

        for block in text_blocks:
            # 检查是否为标题
            if block.text_level > 0:
                # 保存上一个section
                if current_section is not None:
                    current_section["content"] = '\n\n'.join(current_content)
                    sections.append(current_section)

                # 开始新section
                current_section = {
                    "title": block.content,
                    "level": block.text_level,
                    "start_page": block.page_idx,
                    "content": ""
                }
                current_content = []
            else:
                # 普通文本
                if block.content.strip():
                    current_content.append(block.content)

        # 保存最后一个section
        if current_section is not None:
            current_section["content"] = '\n\n'.join(current_content)
            sections.append(current_section)

        return sections

    def get_document_structure(self, parsed_data: Dict) -> Dict:
        """
        获取文档结构

        Args:
            parsed_data: 解析后的数据

        Returns:
            文档结构字典
        """
        text_blocks = parsed_data["text_blocks"]
        image_blocks = parsed_data["image_blocks"]
        table_blocks = parsed_data["table_blocks"]

        # 提取标题
        title = ""
        for block in text_blocks:
            if block.text_level == 1:
                title = block.content
                break

        # 提取章节
        sections = self.extract_sections(text_blocks)

        # 提取图片信息
        images = []
        for img in image_blocks:
            images.append({
                "path": img.img_path,
                "caption": img.image_caption,
                "footnote": img.image_footnote,
                "page": img.page_idx
            })

        return {
            "title": title,
            "sections": sections,
            "images": images,
            "total_pages": max(b.page_idx for b in text_blocks) + 1 if text_blocks else 0,
            "total_images": len(images),
            "total_tables": len(table_blocks)
        }
