# -*- coding: utf-8 -*-
"""
Chunk Graph - 基于标题层级构建 chunk 结构图
记录父子/兄弟关系，供后续检索时沿图取邻居 chunk

当前只实现结构边（标题层级），语义边后续扩展。
"""

import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class GraphNode:
    """图节点"""
    chunk_index: int
    heading_path: List[str]
    heading_level: int
    parent_index: Optional[int] = None
    children_indices: List[int] = field(default_factory=list)
    sibling_indices: List[int] = field(default_factory=list)


class ChunkGraph:
    """
    Chunk 结构图

    基于 heading_path 构建树：
    - 父子关系：heading_path 的包含关系
    - 兄弟关系：同一父节点下的其他子节点
    """

    def __init__(self):
        self.nodes: Dict[int, GraphNode] = {}

    def build_from_chunks(self, chunks: List[Dict[str, Any]]) -> 'ChunkGraph':
        """从 chunk 列表构建结构图"""
        if not chunks:
            return self

        for i, chunk in enumerate(chunks):
            heading_path = chunk.get('heading_path', [])
            if not heading_path:
                metadata = chunk.get('metadata', {})
                heading_path = metadata.get('heading_path', [])

            heading_level = chunk.get('heading_level', 0)
            if not heading_level and heading_path:
                last = heading_path[-1]
                heading_level = last.count('#', 0, last.index(' ')) if ' ' in last else len(heading_path)

            self.nodes[i] = GraphNode(
                chunk_index=i,
                heading_path=heading_path,
                heading_level=heading_level,
            )

        # 构建父子关系
        for i, node_i in self.nodes.items():
            best_parent = None
            best_parent_level = -1

            for j, node_j in self.nodes.items():
                if i == j:
                    continue
                if self._is_ancestor(node_j.heading_path, node_i.heading_path):
                    if node_j.heading_level > best_parent_level:
                        best_parent = j
                        best_parent_level = node_j.heading_level

            if best_parent is not None:
                node_i.parent_index = best_parent
                self.nodes[best_parent].children_indices.append(i)

        # 构建兄弟关系
        for i, node_i in self.nodes.items():
            if node_i.parent_index is not None:
                parent = self.nodes[node_i.parent_index]
                node_i.sibling_indices = [
                    idx for idx in parent.children_indices if idx != i
                ]

        logger.info(
            f"[ChunkGraph] 构建完成: {len(self.nodes)} 个节点, "
            f"{sum(1 for n in self.nodes.values() if n.parent_index is not None)} 个有父节点"
        )
        return self

    def _is_ancestor(self, candidate_path: List[str], target_path: List[str]) -> bool:
        """判断 candidate_path 是否是 target_path 的祖先"""
        if not candidate_path or not target_path:
            return False
        if len(candidate_path) >= len(target_path):
            return False
        return candidate_path == target_path[:len(candidate_path)]

    def get_parent(self, chunk_index: int) -> Optional[GraphNode]:
        node = self.nodes.get(chunk_index)
        if node and node.parent_index is not None:
            return self.nodes.get(node.parent_index)
        return None

    def get_children(self, chunk_index: int) -> List[GraphNode]:
        node = self.nodes.get(chunk_index)
        if not node:
            return []
        return [self.nodes[idx] for idx in node.children_indices if idx in self.nodes]

    def get_siblings(self, chunk_index: int) -> List[GraphNode]:
        node = self.nodes.get(chunk_index)
        if not node:
            return []
        return [self.nodes[idx] for idx in node.sibling_indices if idx in self.nodes]

    def get_ancestors(self, chunk_index: int) -> List[GraphNode]:
        """获取所有祖先节点（从近到远）"""
        ancestors = []
        node = self.nodes.get(chunk_index)
        while node and node.parent_index is not None:
            parent = self.nodes.get(node.parent_index)
            if parent:
                ancestors.append(parent)
                node = parent
            else:
                break
        return ancestors

    def get_context_window(
        self,
        chunk_index: int,
        include_parent: bool = True,
        include_siblings: bool = True,
        max_siblings: int = 2,
    ) -> List[int]:
        """
        获取 chunk 的上下文窗口（检索时补充上下文）

        Returns:
            包含自身、父节点、相邻兄弟的 chunk_index 列表
        """
        context = [chunk_index]

        if include_parent:
            parent = self.get_parent(chunk_index)
            if parent:
                context.append(parent.chunk_index)

        if include_siblings:
            siblings = self.get_siblings(chunk_index)
            siblings_sorted = sorted(siblings, key=lambda n: n.chunk_index)
            for s in siblings_sorted[:max_siblings]:
                context.append(s.chunk_index)

        return list(set(context))

    def enrich_chunk_metadata(self, chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """将图的结构信息写入 chunk 的 metadata"""
        for i, chunk in enumerate(chunks):
            node = self.nodes.get(i)
            if not node:
                continue

            metadata = chunk.get('metadata', {})
            if metadata is None:
                metadata = {}

            metadata['parent_index'] = node.parent_index
            metadata['children_indices'] = node.children_indices
            metadata['sibling_indices'] = node.sibling_indices
            chunk['metadata'] = metadata

        return chunks
