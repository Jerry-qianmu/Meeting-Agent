"""
可视化脚本 - 绘制图结构
"""

import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import networkx as nx
from matplotlib import font_manager
from typing import Dict, List


def visualize_graph(graph_data: Dict, output_path: str = "graph_structure.png"):
    """
    绘制图结构

    Args:
        graph_data: 图数据字典
        output_path: 输出文件路径
    """
    try:
        font_path = font_manager.findfont(
            font_manager.FontProperties(family='Microsoft YaHei')
        )
        plt.rcParams['font.family'] = 'Microsoft YaHei'
    except Exception:
        plt.rcParams['font.family'] = 'DejaVu Sans'

    G = nx.DiGraph()

    for node in graph_data["nodes"]:
        G.add_node(node["id"], **node)

    for edge in graph_data["edges"]:
        G.add_edge(edge["source"], edge["target"], edge_type=edge["type"])

    color_map = {
        "document": "#FF6B6B",
        "section": "#4ECDC4",
        "chunk": "#45B7D1",
        "entity": "#96CEB4",
        "image": "#FFD93D",  # 黄色
    }

    node_colors = []
    for node in graph_data["nodes"]:
        node_colors.append(color_map.get(node["type"], "#CCCCCC"))

    size_map = {
        "document": 2000,
        "section": 1500,
        "chunk": 1200,
        "entity": 800,
        "image": 1000,
    }
    node_sizes = [size_map.get(n["type"], 800) for n in graph_data["nodes"]]

    shape_map = {
        "document": "s",
        "section": "D",
        "chunk": "o",
        "entity": "^",
        "image": "p",  # 五边形
    }

    pos = {}

    doc_nodes = [n["id"] for n in graph_data["nodes"] if n["type"] == "document"]
    for i, nid in enumerate(doc_nodes):
        pos[nid] = (0, 4)

    sec_nodes = [n["id"] for n in graph_data["nodes"] if n["type"] == "section"]
    for i, nid in enumerate(sec_nodes):
        x = -len(sec_nodes) + i * 2
        pos[nid] = (x, 3)

    chunk_nodes = [n["id"] for n in graph_data["nodes"] if n["type"] == "chunk"]
    for i, nid in enumerate(chunk_nodes):
        x = -len(chunk_nodes) + i * 1.5
        pos[nid] = (x, 2)

    entity_nodes = [n["id"] for n in graph_data["nodes"] if n["type"] == "entity"]
    for i, nid in enumerate(entity_nodes):
        x = -len(entity_nodes) + i * 1.0
        pos[nid] = (x, 0.5)

    # Image 节点
    image_nodes = [n["id"] for n in graph_data["nodes"] if n["type"] == "image"]
    for i, nid in enumerate(image_nodes):
        x = -len(image_nodes) + i * 1.5
        pos[nid] = (x, -0.5)

    fig, ax = plt.subplots(1, 1, figsize=(28, 16))
    ax.set_title(
        "Markdown解析后的图结构",
        fontsize=16, fontweight='bold', pad=20
    )

    for ntype, marker in shape_map.items():
        nodelist = [n["id"] for n in graph_data["nodes"] if n["type"] == ntype]
        if not nodelist:
            continue
        nx.draw_networkx_nodes(
            G, pos,
            nodelist=nodelist,
            node_color=color_map[ntype],
            node_size=size_map[ntype],
            node_shape=marker,
            alpha=0.9,
            ax=ax
        )

    edge_styles = {
        "contains": {
            "style": "solid", "color": "#FF6B6B", "width": 2
        },
        "next": {
            "style": "solid", "color": "#45B7D1", "width": 2.5,
            "connectionstyle": "arc3,rad=0.1"
        },
        "mentions": {
            "style": "dashed", "color": "#96CEB4", "width": 1
        },
    }

    for etype, style in edge_styles.items():
        edgelist = [
            (e["source"], e["target"])
            for e in graph_data["edges"] if e["type"] == etype
        ]
        if not edgelist:
            continue
        nx.draw_networkx_edges(
            G, pos,
            edgelist=edgelist,
            edge_color=style["color"],
            width=style["width"],
            style=style["style"],
            arrows=True,
            arrowsize=15,
            connectionstyle=style.get("connectionstyle", "arc3,rad=0.0"),
            ax=ax,
            min_source_margin=15,
            min_target_margin=15,
        )

    short_labels = {}
    for n in graph_data["nodes"]:
        nid = n["id"]
        if n["type"] == "entity":
            short_labels[nid] = n["metadata"].get("name", nid)
        elif n["type"] == "chunk":
            short_labels[nid] = nid.replace("chunk_", "C")
        elif n["type"] == "section":
            short_labels[nid] = n["metadata"].get("title", nid)[:10]
        elif n["type"] == "image":
            short_labels[nid] = "IMG"
        else:
            short_labels[nid] = "Doc"

    nx.draw_networkx_labels(
        G, pos,
        labels=short_labels,
        font_size=8,
        font_weight='bold',
        ax=ax
    )

    legend_elements = [
        mpatches.Patch(facecolor="#FF6B6B", label="Document (文档根节点)"),
        mpatches.Patch(facecolor="#4ECDC4", label="Section (章节节点)"),
        mpatches.Patch(facecolor="#45B7D1", label="Chunk (文本块节点)"),
        mpatches.Patch(facecolor="#96CEB4", label="Entity (实体节点)"),
        mpatches.Patch(facecolor="#FFD93D", label="Image (图片节点)"),
        plt.Line2D([0], [0], color="#FF6B6B", linewidth=2, label="contains (包含)"),
        plt.Line2D([0], [0], color="#45B7D1", linewidth=2.5, label="next (顺序)"),
        plt.Line2D(
            [0], [0], color="#96CEB4", linewidth=1,
            linestyle='dashed', label="mentions (提及)"
        ),
        plt.Line2D(
            [0], [0], color="#FFD93D", linewidth=2,
            linestyle='dotted', label="associated_with (关联)"
        ),
    ]
    ax.legend(handles=legend_elements, loc='upper right', fontsize=10, framealpha=0.9)

    ax.axis('off')
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight', facecolor='white')
    plt.close()
    print(f"\n图已保存为 {output_path}")


def visualize_from_json(json_path: str, output_path: str = "graph_structure.png"):
    """从JSON文件加载并可视化"""
    with open(json_path, 'r', encoding='utf-8') as f:
        graph_data = json.load(f)

    visualize_graph(graph_data, output_path)


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("用法: python visualize.py <graph.json> [output.png]")
        sys.exit(1)

    json_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else "graph_structure.png"

    visualize_from_json(json_path, output_path)
