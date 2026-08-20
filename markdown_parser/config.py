"""
Markdown Parser 配置文件
"""

from dataclasses import dataclass
from typing import List, Dict


@dataclass
class NERConfig:
    """NER配置"""
    model_name: str = "Davlan/bert-base-multilingual-cased-ner-hrl"
    device: str = "cpu"
    batch_size: int = 32
    structured_keywords: Dict[str, Dict[str, List[str]]] = None

    def __post_init__(self):
        if self.structured_keywords is None:
            self.structured_keywords = {
                "signature": {
                    "zh": ["签名", "签字", "署名", "作者签名", "导师签名"],
                    "en": ["signature", "signed by", "author signature"]
                },
                "date": {
                    "zh": ["日期", "时间", "签字日期", "提交日期"],
                    "en": ["date", "submission date", "signed on"]
                },
                "contact": {
                    "zh": ["电话", "手机", "邮箱", "Email", "联系方式"],
                    "en": ["phone", "email", "contact", "tel"]
                },
                "affiliation": {
                    "zh": ["工作单位", "学校", "学院", "单位", "就读院校"],
                    "en": ["university", "institution", "affiliation", "department"]
                }
            }


@dataclass
class ChunkConfig:
    """Chunk配置"""
    min_tokens: int = 100
    max_tokens: int = 500
    target_tokens: int = 300
    overlap_tokens: int = 50
    merge_threshold: int = 150


@dataclass
class CleanerConfig:
    """清理配置"""
    header_footer_patterns: List[str] = None
    noise_patterns: List[str] = None
    min_content_length: int = 10

    def __post_init__(self):
        if self.header_footer_patterns is None:
            self.header_footer_patterns = [
                r'^第\s*\d+\s*页.*$',
                r'^.*Page\s*\d+.*$',
                r'^\d+\s*/\s*\d+$',
                r'^.*版权所有.*$',
                r'^.*Copyright.*$',
                r'^\s*-\s*\d+\s*-\s*$',
            ]

        if self.noise_patterns is None:
            self.noise_patterns = [
                r'^\s*$',
                r'^\s*[\-\*_]{3,}\s*$',
                r'^\s*\[image\].*$',
                r'^\s*Figure\s*\d+.*$',
                r'^\s*表\s*\d+.*$',
                r'^\s*Table\s*\d+.*$',
            ]


@dataclass
class ParserConfig:
    """主配置"""
    ner: NERConfig = None
    chunk: ChunkConfig = None
    cleaner: CleanerConfig = None

    def __post_init__(self):
        if self.ner is None:
            self.ner = NERConfig()
        if self.chunk is None:
            self.chunk = ChunkConfig()
        if self.cleaner is None:
            self.cleaner = CleanerConfig()
