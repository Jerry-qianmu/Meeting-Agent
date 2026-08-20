import logging
from datetime import datetime
from typing import List, Dict, Any, Optional, Annotated
import os
import sys

logger = logging.getLogger(__name__)
cur_dir = os.path.dirname(__file__)
parent_dir = os.path.dirname(cur_dir)
grand_parent_dir = os.path.dirname(parent_dir)
sys.path.append(os.path.dirname(grand_parent_dir))

from config.settings import Settings
settings = Settings()

from ..state import KnowledgeAgentState

# 检查是否指定了目标知识库，如果有则只检索这些知识库
def target_knowledge_base(state: KnowledgeAgentState) -> dict:
    # 从 state 中获取传入的 target_knowledge_bases（由 agent_service 传递）
    target_kbs = state.get("target_knowledge_bases", [])
    
    # 添加调试日志
    if target_kbs:
        logger.info(f"[target_knowledge_base] 指定了 {len(target_kbs)} 个知识库: {target_kbs[:2]}...")
    else:
        logger.info("[target_knowledge_base] 未指定知识库，将检索所有知识库")
    
    return {
        "target_knowledge_bases": target_kbs
    }

# 检查是否指定了目标文档，如果有则只检索这些文档
def target_documents(state: KnowledgeAgentState) -> dict:
    # 从 state 中获取传入的 target_documents（由 agent_service 传递）
    target_docs = state.get("target_documents", [])
    
    # 添加调试日志
    if target_docs:
        logger.info(f"[target_documents] 指定了 {len(target_docs)} 个文档: {target_docs[:2]}...")
    else:
        logger.info("[target_documents] 未指定文档，将检索所有文档")
    
    return {
        "target_documents": target_docs
    }

