#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
DashScope 配置验证脚本
"""
import sys
sys.path.insert(0, '/mnt/d/Study/Agents/MA/data3/zb/MyAgent/backend')

from config.settings import Settings

s = Settings()

print('=' * 60)
print('DashScope 配置检查')
print('=' * 60)

# API Key 检查
print(f'[1] API Key 存在：{bool(s.dashscope_api_key)}')
if s.dashscope_api_key:
    print(f'    API Key 前 15 位：{s.dashscope_api_key[:15]}...')
    print(f'    API Key 长度：{len(s.dashscope_api_key)}')
    print(f'    API Key 格式：{"✓ 正确 (sk-开头)" if s.dashscope_api_key.startswith("sk-") else "✗ 错误 (不是 sk-开头)"}')
else:
    print('    ✗ API Key 为空，请检查 .env 文件')

# 模型配置检查
print()
print(f'[2] 模型配置:')
print(f'    Rewrite Model: {s.rewrite_model}')
print(f'    Strategy Model: {s.determine_retrieval_strategy_model}')
print(f'    Generation Model: {s.generation_model}')
print(f'    Quality Eval Model: {s.quality_eval_model}')
print(f'    Rerank Model: {s.rerank_model}')

# 检查模型名称是否有效
valid_models = ['qwen-plus', 'qwen-turbo', 'qwen-max', 'qwen-rerank-v2']
print()
print(f'[3] 模型名称有效性检查:')
for name, model in [('Rewrite', s.rewrite_model), 
                     ('Strategy', s.determine_retrieval_strategy_model),
                     ('Generation', s.generation_model),
                     ('Quality Eval', s.quality_eval_model),
                     ('Rerank', s.rerank_model)]:
    status = "✓ 有效" if model in valid_models else "⚠ 可能无效"
    print(f'    {name}: {model} - {status}')

# 测试 DashScope API 连接
print()
print(f'[4] 测试 DashScope API 连接...')
try:
    import dashscope
    from dashscope import Generation
    
    dashscope.api_key = s.dashscope_api_key
    
    response = Generation.call(
        model=s.rewrite_model,
        messages=[{'role': 'user', 'content': '你好'}],
        timeout=10
    )
    
    if response.status_code == 200:
        print(f'    ✓ API 连接成功！')
        print(f'    模型：{s.rewrite_model}')
    else:
        print(f'    ✗ API 调用失败: {response.status_code} - {response.message}')
except Exception as e:
    print(f'    ✗ 错误：{str(e)}')

print('=' * 60)
