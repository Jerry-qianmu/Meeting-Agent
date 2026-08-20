"""
Query Expansion Node - 提问扩展
"""
import logging
from datetime import datetime
from typing import List, Dict, Any
from langchain_core.messages import HumanMessage
from copy import deepcopy
from ..state import KnowledgeAgentState
import os
import sys

logger = logging.getLogger(__name__)
cur_dir = os.path.dirname(__file__)
parent_dir = os.path.dirname(cur_dir)
grand_parent_dir = os.path.dirname(parent_dir)
sys.path.append(os.path.dirname(grand_parent_dir))

from config.settings import Settings
settings = Settings()
_MAX_EXPANSIONS = settings.max_expansions
def query_expansion(state: KnowledgeAgentState) -> dict:
    pass