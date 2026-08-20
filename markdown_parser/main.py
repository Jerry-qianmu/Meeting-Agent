"""
Markdown Parser 主入口 - 支持MD和JSON文件
"""

import os
import re
import json
from typing import Dict, List, Optional
from .config import ParserConfig
from .cleaners.text_cleaner import TextCleaner
from .parsers.markdown_parser import MarkdownParser
from .parsers.json_parser import JsonParser
from .ner.entity_extractor import EntityExtractor
from .chunkers.chunk_splitter import ChunkSplitter
from .graph.graph_builder import GraphBuilder, Graph


class MarkdownProcessor:
    """Markdown/JSON处理器"""

    def __init__(self, config: ParserConfig = None):
        self.config = config or ParserConfig()

        # 初始化各组件
        self.cleaner = TextCleaner(self.config.cleaner)
        self.md_parser = MarkdownParser()
        self.json_parser = JsonParser()
        self.entity_extractor = EntityExtractor(self.config.ner)
        self.chunk_splitter = ChunkSplitter(self.config.chunk)
        self.graph_builder = GraphBuilder()

    def process_file(self, file_path: str, json_path: str = None) -> Dict:
        """
        处理文件

        Args:
            file_path: MD文件路径
            json_path: JSON文件路径（可选，用于获取图片和图注信息）

        Returns:
            处理结果字典
        """
        # 读取MD文件
        with open(file_path, 'r', encoding='utf-8') as f:
            raw_text = f.read()

        document_title = os.path.splitext(os.path.basename(file_path))[0]

        # 如果有JSON文件，解析图片和图注
        image_blocks = []
        if json_path and os.path.exists(json_path):
            parsed_json = self.json_parser.parse(json_path)
            image_blocks = parsed_json.get("image_blocks", [])

        return self.process_text(raw_text, document_title, image_blocks)

    def process_text(self, text: str, document_title: str = "Untitled", image_blocks: List = None) -> Dict:
        """处理文本"""
        # Step 1: 清理文本（页眉页脚、噪声）
        cleaned_text, removed_items = self.cleaner.clean(text)

        # Step 2: 从markdown中移除图片引用（因为图片信息来自JSON）
        cleaned_text = self._remove_image_refs(cleaned_text)

        # Step 3: 解析markdown结构
        sections = self.md_parser.parse(cleaned_text)

        # Step 4: 处理每个section
        all_chunks = []
        all_structured_entities = []
        all_narrative_entities = []

        for section in sections:
            breadcrumb = self.md_parser.get_breadcrumb(section)

            # 提取实体
            structured, narrative = self.entity_extractor.extract_structured_entities(section.content)

            # 正则补充提取
            regex_entities = self.entity_extractor.extract_with_regex(section.content)
            narrative.extend(regex_entities)

            # 去重
            structured = self.entity_extractor.deduplicate(structured)
            narrative = self.entity_extractor.deduplicate(narrative)

            # 分割chunk
            chunks = self.chunk_splitter.split(
                section.content,
                section_title=section.title,
                breadcrumb=breadcrumb
            )

            # 将实体分配到chunks
            chunks = self.chunk_splitter.assign_entities_to_chunks(
                chunks,
                structured + narrative
            )

            # 标记包含结构化实体的chunks
            for chunk in chunks:
                if any(e.is_structured for e in chunk.entities):
                    chunk.is_structured = True

            all_chunks.extend(chunks)
            all_structured_entities.extend(structured)
            all_narrative_entities.extend(narrative)

        # Step 5: 处理图片信息（来自JSON）
        image_refs = []
        if image_blocks:
            image_refs = self._process_image_blocks(image_blocks, all_chunks)

        # Step 6: 构建图结构
        graph = self.graph_builder.build(
            document_title=document_title,
            sections=sections,
            chunks=all_chunks,
            structured_entities=all_structured_entities,
            narrative_entities=all_narrative_entities,
            image_refs=image_refs
        )

        stats = self.graph_builder.get_statistics(graph)

        return {
            "document_title": document_title,
            "graph": graph,
            "statistics": stats,
            "chunks": all_chunks,
            "structured_entities": all_structured_entities,
            "narrative_entities": all_narrative_entities,
            "removed_items": removed_items,
            "image_refs": image_refs
        }

    def _remove_image_refs(self, text: str) -> str:
        """从markdown中移除图片引用"""
        # 移除 ![alt](path) 格式
        text = re.sub(r'!\[[^\]]*\]\([^)]+\)', '', text)
        # 移除 Figure/Table 标题行
        text = re.sub(r'^(?:Figure|Fig\.?|图|Table|表)\s*\d+[:.：].*$', '', text, flags=re.MULTILINE | re.IGNORECASE)
        # 移除子图标注 (A), (B), (C) 等独立行
        text = re.sub(r'^\s*\(?[A-Z]\)?\s*$', '', text, flags=re.MULTILINE)
        # 清理多余空行
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()

    def _process_image_blocks(self, image_blocks: List, chunks: List) -> List[Dict]:
        """
        处理图片块，关联到最近的chunk

        Args:
            image_blocks: 图片块列表
            chunks: Chunk列表

        Returns:
            图片引用列表
        """
        image_refs = []

        for i, img in enumerate(image_blocks):
            img_info = {
                "id": f"img_{i + 1}",
                "path": img.img_path if hasattr(img, 'img_path') else img.get("img_path", ""),
                "caption": img.image_caption if hasattr(img, 'image_caption') else img.get("image_caption", []),
                "footnote": img.image_footnote if hasattr(img, 'image_footnote') else img.get("image_footnote", []),
                "page": img.page_idx if hasattr(img, 'page_idx') else img.get("page_idx", 0),
                "associated_chunk": "",
                "associated_section": ""
            }

            # 关联到最近的chunk（基于页面位置）
            if chunks:
                # 简单策略：按顺序关联
                chunk_idx = min(i, len(chunks) - 1)
                img_info["associated_chunk"] = chunks[chunk_idx].id
                img_info["associated_section"] = chunks[chunk_idx].section_title

            image_refs.append(img_info)

        return image_refs

    def save_result(self, result: Dict, output_dir: str, prefix: str = "output"):
        """保存处理结果"""
        os.makedirs(output_dir, exist_ok=True)

        # 保存图结构JSON
        graph_path = os.path.join(output_dir, f"{prefix}_graph.json")
        with open(graph_path, 'w', encoding='utf-8') as f:
            f.write(result["graph"].to_json())

        # 保存统计信息
        stats_path = os.path.join(output_dir, f"{prefix}_stats.json")
        with open(stats_path, 'w', encoding='utf-8') as f:
            json.dump(result["statistics"], f, indent=2, ensure_ascii=False)

        # 保存chunks
        chunks_path = os.path.join(output_dir, f"{prefix}_chunks.json")
        chunks_data = [c.to_dict() for c in result["chunks"]]
        with open(chunks_path, 'w', encoding='utf-8') as f:
            json.dump(chunks_data, f, indent=2, ensure_ascii=False)

        # 保存实体
        entities_path = os.path.join(output_dir, f"{prefix}_entities.json")
        entities_data = {
            "structured": [e.to_dict() for e in result["structured_entities"]],
            "narrative": [e.to_dict() for e in result["narrative_entities"]]
        }
        with open(entities_path, 'w', encoding='utf-8') as f:
            json.dump(entities_data, f, indent=2, ensure_ascii=False)

        # 保存图片信息
        if result.get("image_refs"):
            images_path = os.path.join(output_dir, f"{prefix}_images.json")
            with open(images_path, 'w', encoding='utf-8') as f:
                json.dump(result["image_refs"], f, indent=2, ensure_ascii=False)

        print(f"结果已保存到: {output_dir}")

    def print_summary(self, result: Dict):
        """打印处理摘要"""
        print("=" * 60)
        print(f"文档: {result['document_title']}")
        print("=" * 60)

        stats = result["statistics"]

        print(f"\n节点总数: {stats['total_nodes']}")
        for node_type, count in stats['node_types'].items():
            print(f"  {node_type}: {count}")

        print(f"\n边总数: {stats['total_edges']}")
        for edge_type, count in stats['edge_types'].items():
            print(f"  {edge_type}: {count}")

        print(f"\nChunk统计:")
        print(f"  数量: {stats['chunk_stats']['count']}")
        print(f"  Token范围: {stats['chunk_stats']['token_range'][0]} ~ {stats['chunk_stats']['token_range'][1]}")
        print(f"  平均Token: {stats['chunk_stats']['avg_tokens']:.0f}")

        print(f"\n实体统计:")
        print(f"  总数: {stats['entity_stats']['total']}")
        print(f"  结构化实体: {len(result['structured_entities'])}")
        print(f"  叙述性实体: {len(result['narrative_entities'])}")
        for cat, count in stats['entity_stats']['categories'].items():
            print(f"  {cat}: {count}")

        if result.get('image_refs'):
            print(f"\n图片统计:")
            print(f"  总数: {len(result['image_refs'])}")

        if result['removed_items']:
            print(f"\n清理的噪声: {len(result['removed_items'])}项")


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description="Markdown Parser - 基于图RAG的Markdown解析系统")
    parser.add_argument("input", help="输入MD文件路径")
    parser.add_argument("--json", help="JSON文件路径（可选，用于获取图片和图注信息）")
    parser.add_argument("-o", "--output", default="output", help="输出目录")
    parser.add_argument("-v", "--verbose", action="store_true", help="详细输出")

    args = parser.parse_args()

    processor = MarkdownProcessor()
    result = processor.process_file(args.input, args.json)

    processor.print_summary(result)
    processor.save_result(result, args.output)

    if args.verbose:
        print("\n" + "=" * 60)
        print("图结构JSON:")
        print("=" * 60)
        print(result["graph"].to_json())


if __name__ == "__main__":
    main()
