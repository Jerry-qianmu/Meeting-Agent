#!/bin/bash
# 会话管理 API 测试脚本

BASE_URL="http://localhost:8000/api/v1"
USER_ID="user_001"

echo "=========================================="
echo "会话管理 API 测试"
echo "=========================================="
echo ""

# 1. 创建新会话
echo "1. 创建新会话..."
CREATE_RESPONSE=$(curl -s -X POST "${BASE_URL}/session/create" \
  -H "Content-Type: application/json" \
  -d "{
    \"user_id\": \"${USER_ID}\",
    \"title\": \"测试对话 - $(date +%Y%m%d-%H%M%S)\"
  }")

echo "响应: $CREATE_RESPONSE"
SESSION_ID=$(echo $CREATE_RESPONSE | grep -o '"session_id":"[^"]*"' | cut -d'"' -f4)
echo "会话 ID: $SESSION_ID"
echo ""

if [ -z "$SESSION_ID" ]; then
    echo "❌ 创建会话失败，退出测试"
    exit 1
fi

# 2. 获取会话列表
echo "2. 获取会话列表..."
curl -s "${BASE_URL}/session/list?user_id=${USER_ID}&status=1" | jq '.'
echo ""

# 3. 获取会话详情
echo "3. 获取会话详情..."
curl -s "${BASE_URL}/session/${SESSION_ID}" | jq '.'
echo ""

# 4. 发送消息（完整聊天流程）
echo "4. 发送消息（完整聊天流程）..."
CHAT_RESPONSE=$(curl -s -X POST "${BASE_URL}/session/chat" \
  -H "Content-Type: application/json" \
  -d "{
    \"user_id\": \"${USER_ID}\",
    \"query\": \"什么是机器学习？\",
    \"session_id\": \"${SESSION_ID}\",
    \"top_k\": 5
  }")

echo "响应: $CHAT_RESPONSE"
echo ""

# 5. 获取消息列表
echo "5. 获取消息列表..."
curl -s "${BASE_URL}/session/message/list?session_id=${SESSION_ID}&limit=100" | jq '.'
echo ""

# 6. 更新会话标题
echo "6. 更新会话标题..."
curl -s -X PUT "${BASE_URL}/session/${SESSION_ID}/title" \
  -H "Content-Type: application/json" \
  -d '{"title": "机器学习讨论 - 已更新"}' | jq '.'
echo ""

# 7. 再次获取会话详情（验证标题更新）
echo "7. 再次获取会话详情（验证标题更新）..."
curl -s "${BASE_URL}/session/${SESSION_ID}" | jq '.'
echo ""

# 8. 发送第二条消息
echo "8. 发送第二条消息..."
curl -s -X POST "${BASE_URL}/session/chat" \
  -H "Content-Type: application/json" \
  -d "{
    \"user_id\": \"${USER_ID}\",
    \"query\": \"机器学习有哪些应用场景？\",
    \"session_id\": \"${SESSION_ID}\",
    \"top_k\": 5
  }" | jq '.'
echo ""

# 9. 再次获取消息列表（应该有 2 条对话）
echo "9. 再次获取消息列表（验证有 4 条消息）..."
curl -s "${BASE_URL}/session/message/list?session_id=${SESSION_ID}&limit=100" | jq '.messages | length'
echo ""

# 10. 获取会话列表（验证消息数量更新）
echo "10. 获取会话列表（验证消息数量更新）..."
curl -s "${BASE_URL}/session/list?user_id=${USER_ID}&status=1" | jq '.sessions[] | {title: .title, message_count: .message_count}'
echo ""

echo "=========================================="
echo "✅ 测试完成！"
echo "=========================================="
echo ""
echo "会话 ID: $SESSION_ID"
echo ""
echo "提示：可以在浏览器打开 http://localhost:8000/docs 查看完整的 API 文档"
