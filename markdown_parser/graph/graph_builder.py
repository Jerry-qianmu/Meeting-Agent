"""
图结构构建器
"""

import json
from typing import List, Dict, Set
from dataclasses import dataclass, field
from ..chunkers.chunk_splitter import Chunk
from ..ner.entity_extractor import Entity
from ..parsers.markdown_parser import MarkdownSection


@dataclass
class GraphNode:
    """图节点"""
    id: str
    node_type: str
    metadata: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "type": self.node_type,
            "metadata": self.metadata
        }


@dataclass
class GraphEdge:
    """图边"""
    source: str
    target: str
    edge_type: str

    def to_dict(self) -> Dict:
        return {
            "source": self.source,
            "target": self.target,
            "type": self.edge_type
        }


@dataclass
class Graph:
    """图结构"""
    nodes: List[GraphNode] = field(default_factory=list)
    edges: List[GraphEdge] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [e.to_dict() for e in self.edges]
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    def get_node_by_id(self, node_id: str) -> GraphNode:
        for node in self.nodes:
            if node.id == node_id:
                return node
        return None

    def get_edges_by_source(self, source_id: str) -> List[GraphEdge]:
        return [e for e in self.edges if e.source == source_id]

    def get_edges_by_target(self, target_id: str) -> List[GraphEdge]:
        return [e for e in self.edges if e.target == target_id]


class GraphBuilder:
    """图结构构建器"""

    def __init__(self):
        self.node_counter = 0
        self.entity_nodes: Dict[str, str] = {}

    def build(
        self,
        document_title: str,
        sections: List[MarkdownSection],
        chunks: List[Chunk],
        structured_entities: List[Entity],
        narrative_entities: List[Entity],
        image_refs: List[Dict] = None
    ) -> Graph:
        """
        构建图结构

        Args:
            document_title: 文档标题
            sections: 章节列表
            chunks: Chunk列表
            structured_entities: 结构化实体列表
            narrative_entities: 叙述性实体列表
            image_refs: 图片引用列表

        Returns:
            图结构
        """
        graph = Graph()
        self.node_counter = 0
        self.entity_nodes = {}

        # 创建文档节点
        doc_node = self._create_document_node(document_title, chunks)
        graph.nodes.append(doc_node)

        # 创建章节节点
        section_nodes = self._create_section_nodes(sections)
        graph.nodes.extend(section_nodes)

        # 创建Chunk节点
        chunk_nodes = self._create_chunk_nodes(chunks)
        graph.nodes.extend(chunk_nodes)

        # 创建实体节点
        all_entities = structured_entities + narrative_entities
        entity_nodes = self._create_entity_nodes(all_entities)
        graph.nodes.extend(entity_nodes)

        # 创建图片节点
        image_nodes = []
        if image_refs:
            image_nodes = self._create_image_nodes(image_refs)
            graph.nodes.extend(image_nodes)

        # 创建边
        edges = self._create_edges(
            doc_node, section_nodes, chunk_nodes, chunks,
            image_nodes, image_refs
        )
        graph.edges.extend(edges)

        return graph

    def _create_document_node(self, title: str, chunks: List[Chunk]) -> GraphNode:
        """创建文档节点"""
        total_tokens = sum(c.token_count for c in chunks)

        return GraphNode(
            id="doc_root",
            node_type="document",
            metadata={
                "title": title,
                "total_chunks": len(chunks),
                "total_tokens": total_tokens
            }
        )

    def _create_section_nodes(self, sections: List[MarkdownSection]) -> List[GraphNode]:
        """创建章节节点"""
        nodes = []

        for i, section in enumerate(sections):
            self.node_counter += 1
            node = GraphNode(
                id=f"sec_{self.node_counter}",
                node_type="section",
                metadata={
                    "title": section.title,
                    "level": section.level,
                    "content_length": len(section.content)
                }
            )
            nodes.append(node)

        return nodes

    def _create_chunk_nodes(self, chunks: List[Chunk]) -> List[GraphNode]:
        """创建Chunk节点"""
        nodes = []

        for chunk in chunks:
            content_preview = chunk.content[:200] + "..." if len(chunk.content) > 200 else chunk.content

            node = GraphNode(
                id=chunk.id,
                node_type="chunk",
                metadata={
                    "title": chunk.section_title,
                    "tokens": chunk.token_count,
                    "breadcrumb": chunk.breadcrumb,
                    "content_preview": content_preview,
                    "is_structured": chunk.is_structured,
                    "entity_count": len(chunk.entities)
                }
            )
            nodes.append(node)

        return nodes

    def _create_entity_nodes(self, entities: List[Entity]) -> List[GraphNode]:
        """创建实体节点"""
        nodes = []
        seen_entities: Set[str] = set()

        for entity in entities:
            entity_key = f"{entity.text}_{entity.entity_type}"
            if entity_key in seen_entities:
                continue
            seen_entities.add(entity_key)

            if entity_key not in self.entity_nodes:
                self.node_counter += 1
                node_id = f"ent_{self.node_counter}"
                self.entity_nodes[entity_key] = node_id

                node = GraphNode(
                    id=node_id,
                    node_type="entity",
                    metadata={
                        "name": entity.text,
                        "category": entity.entity_type,
                        "is_structured": entity.is_structured,
                        "pattern_type": entity.pattern_type
                    }
                )
                nodes.append(node)

        return nodes

    def _create_image_nodes(self, image_refs: List[Dict]) -> List[GraphNode]:
        """创建图片节点"""
        nodes = []

        for img in image_refs:
            img_id = img.get("id", f"img_{self.node_counter + 1}")
            self.node_counter += 1

            # 提取caption文本
            caption = img.get("caption", [])
            caption_text = caption[0] if caption else ""

            node = GraphNode(
                id=img_id,
                node_type="image",
                metadata={
                    "path": img.get("path", ""),
                    "caption": caption_text,
                    "page": img.get("page", 0),
                    "associated_chunk": img.get("associated_chunk", ""),
                    "associated_section": img.get("associated_section", ""),
                    "description": "",  # 预留：由视觉模型填充
                    "summary": ""  # 预留：由视觉模型生成摘要
                }
            )
            nodes.append(node)

        return nodes

    def _create_edges(
        self,
        doc_node: GraphNode,
        section_nodes: List[GraphNode],
        chunk_nodes: List[GraphNode],
        chunks: List[Chunk],
        image_nodes: List[GraphNode] = None,
        image_refs: List[Dict] = None
    ) -> List[GraphEdge]:
        """创建边"""
        edges = []

        # Document -> Section 包含关系
        for sec_node in section_nodes:
            edges.append(GraphEdge(
                source=doc_node.id,
                target=sec_node.id,
                edge_type="contains"
            ))

        # Section -> Chunk 包含关系
        for i, chunk_node in enumerate(chunk_nodes):
            section_idx = min(i, len(section_nodes) - 1)
            if section_idx >= 0:
                edges.append(GraphEdge(
                    source=section_nodes[section_idx].id,
                    target=chunk_node.id,
                    edge_type="contains"
                ))

        # Chunk -> Chunk 顺序关系
        for i in range(len(chunk_nodes) - 1):
            edges.append(GraphEdge(
                source=chunk_nodes[i].id,
                target=chunk_nodes[i + 1].id,
                edge_type="next"
            ))

        # Chunk -> Entity 提及关系
        for chunk in chunks:
            for entity in chunk.entities:
                entity_key = f"{entity.text}_{entity.entity_type}"
                entity_node_id = self.entity_nodes.get(entity_key)

                if entity_node_id:
                    edges.append(GraphEdge(
                        source=chunk.id,
                        target=entity_node_id,
                        edge_type="mentions"
                    ))

        # Image -> Chunk 关联关系
        if image_nodes and image_refs:
            for img_node, img_ref in zip(image_nodes, image_refs):
                associated_chunk = img_ref.get("associated_chunk", "")
                if associated_chunk:
                    edges.append(GraphEdge(
                        source=img_node.id,
                        target=associated_chunk,
                        edge_type="associated_with"
                    ))

        return edges

    def get_statistics(self, graph: Graph) -> Dict:
        """获取图统计信息"""
        node_types = {}
        for node in graph.nodes:
            t = node.node_type
            node_types[t] = node_types.get(t, 0) + 1

        edge_types = {}
        for edge in graph.edges:
            t = edge.edge_type
            edge_types[t] = edge_types.get(t, 0) + 1

        chunks = [n for n in graph.nodes if n.node_type == "chunk"]
        token_counts = [n.metadata.get("tokens", 0) for n in chunks]

        entities = [n for n in graph.nodes if n.node_type == "entity"]
        entity_categories = {}
        for e in entities:
            cat = e.metadata.get("category", "UNKNOWN")
            entity_categories[cat] = entity_categories.get(cat, 0) + 1

        images = [n for n in graph.nodes if n.node_type == "image"]

        return {
            "total_nodes": len(graph.nodes),
            "node_types": node_types,
            "total_edges": len(graph.edges),
            "edge_types": edge_types,
            "chunk_stats": {
                "count": len(chunks),
                "token_range": [min(token_counts), max(token_counts)] if token_counts else [0, 0],
                "avg_tokens": sum(token_counts) / len(token_counts) if token_counts else 0
            },
            "entity_stats": {
                "total": len(entities),
                "categories": entity_categories
            },
            "image_stats": {
                "total": len(images)
            }
        }
