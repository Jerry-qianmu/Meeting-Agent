# -*- coding: utf-8 -*-
"""
轻量级 NER 工具
基于正则表达式的命名实体识别，零依赖、毫秒级
支持中文和英文实体抽取
"""

import re
import logging
from typing import List, Dict

logger = logging.getLogger(__name__)


class SimpleRegexNER:
    """基于正则的轻量 NER（无需模型，适合快速原型）"""

    def __init__(self):
        self.patterns = {
            # 中文人名 + 职称
            "PERSON": re.compile(
                r'(?:[一-鿿]{2,4})(?:先生|女士|教授|博士|总|经理|主任|院长|书记|主席)'
            ),
            # 中文组织名
            "ORG": re.compile(
                r'[一-鿿]{2,}(?:公司|集团|大学|学院|研究院|研究所|实验室|委员会|协会|'
                r'基金会|医院|银行|证券|基金|部委|局|厅|处|院|中心|联盟)'
            ),
            # 技术术语（中英文混合）
            "TECH": re.compile(
                r'(?:AI|机器学习|深度学习|大模型|LLM|Transformer|RAG|NLP|GPT|BERT|'
                r'CNN|RNN|LSTM|GAN|VAE|Diffusion|Attention|Fine-tuning|'
                r'Embedding|向量数据库|知识图谱|自然语言处理|计算机视觉|'
                r'强化学习|联邦学习|迁移学习|对比学习|contrastive learning|'
                r'auto.?encoder|graph neural|GNN|GCN|GAT|'
                r'scRNA-seq|scRNAseq|single.cell|clustering|'
                r'Laplacian|K-means|siamese|dropout)'
            ),
            # 日期
            "DATE": re.compile(
                r'\d{4}年(?:\d{1,2}月)?(?:\d{1,2}日)?'
                r'|\d{4}[-/]\d{1,2}[-/]\d{1,2}'
            ),
            # 数字 + 单位
            "NUMBER": re.compile(
                r'\d+(?:\.\d+)?(?:亿|万|%|美元|元|GB|MB|TB|KB|个|篇|次|倍|'
                r'percent|million|billion)'
            ),
            # 英文方法名（学术论文常见）
            "METHOD": re.compile(
                r'(?:scDeepCluster|scDSC|Contrastive.sc|ScDCCA|ScNAME|ScMMN|'
                r'Seurat|Scanpy|scVI|scANVI|Harmony|LIGER|Scanorama|'
                r'scSCCNIA|SIMCLR|MoCo|BYOL|DINO|MAE|'
                r'PCA|t-SNE|UMAP|diffusion map)'
            ),
        }

    def extract(self, text: str) -> List[Dict[str, str]]:
        """
        从文本中抽取实体

        Args:
            text: 输入文本

        Returns:
            List[Dict]: [{"text": "张三", "label": "PERSON"}, ...]
        """
        if not text:
            return []

        entities = []
        seen = set()  # 去重

        for label, pattern in self.patterns.items():
            for match in pattern.finditer(text):
                ent_text = match.group().strip()
                # 过滤过短的匹配
                if len(ent_text) < 2:
                    continue
                # 去重
                key = (ent_text, label)
                if key not in seen:
                    seen.add(key)
                    entities.append({"text": ent_text, "label": label})

        return entities

    def extract_unique_entities(self, text: str) -> List[Dict[str, str]]:
        """抽取去重后的唯一实体（同名实体只保留一个）"""
        entities = self.extract(text)
        seen_texts = set()
        unique = []
        for ent in entities:
            if ent["text"] not in seen_texts:
                seen_texts.add(ent["text"])
                unique.append(ent)
        return unique
