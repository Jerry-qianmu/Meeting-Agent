# -*- coding: utf-8 -*-
"""
API Controller 路由导出
"""

from api_controller.knowledge_base_controller import router as knowledge_base_router
from api_controller.document_controller import router as document_router
from api_controller.agent_controller import router as agent_router

from api_controller.session_controller import router as session_router
from api_controller.auth_controller import router as auth_router

__all__ = ['knowledge_base_router', 'document_router', 'agent_router','session_router', 'auth_router']
