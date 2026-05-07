#!/bin/bash
# 短期记忆功能测试脚本

BASE_URL="http://localhost:8000/api/v1"
USER_ID="user_001"

echo "=========================================="
echo "短期记忆功能测试"
echo "=========================================="

# 1. 创建新会话
echo -e "\n1. 创建新会话..."
SESSION_RESPONSE=$(curl -s -X POST "$BASE_URL/session/create" \
  -H "Content-Type: application/json" \
  -d "{\"user_id\": \"$USER_ID\", \"title\": \"短期记忆测试会话\"}")

echo "响应：$SESSION_RESPONSE"
SESSION_ID=$(echo $SESSION_RESPONSE | jq -r '.session_id')
echo "会话 ID: $SESSION_ID"

if [ "$SESSION_ID" == "null" ] || [ -z "$SESSION_ID" ]; then
  echo "❌ 创建会话失败"
  exit 1
fi

# 2. 第一次对话 - 询问用户偏好
echo -e "\n2. 第一次对话 - 设置用户偏好..."
curl -s -X POST "$BASE_URL/session/chat" \
  -H "Content-Type: application/json" \
  -d "{
    \"user_id\": \"$USER_ID\",
    \"session_id\": \"$SESSION_ID\",
    \"query\": \"我喜欢吃辣的菜，特别是川菜和湘菜。\",
    \"top_k\": 5
  }" | jq '.answer'

# 3. 第二次对话 - 询问用户偏好
echo -e "\n3. 第二次对话 - 设置另一个偏好..."
curl -s -X POST "$BASE_URL/session/chat" \
  -H "Content-Type: application/json" \
  -d "{
    \"user_id\": \"$USER_ID\",
    \"session_id\": \"$SESSION_ID\",
    \"query\": \"我平时喜欢喝咖啡，特别是拿铁和美式。\",
    \"top_k\": 5
  }" | jq '.answer'

# 4. 第三次对话 - 询问用户偏好
echo -e "\n4. 第三次对话 - 设置第三个偏好..."
curl -s -X POST "$BASE_URL/session/chat" \
  -H "Content-Type: application/json" \
  -d "{
    \"user_id\": \"$USER_ID\",
    \"session_id\": \"$SESSION_ID\",
    \"query\": \"我不吃香菜和葱花。\",
    \"top_k\": 5
  }" | jq '.answer'

# 5. 第四次对话 - 测试短期记忆是否生效
echo -e "\n5. 第四次对话 - 测试短期记忆（询问饮食偏好）..."
curl -s -X POST "$BASE_URL/session/chat" \
  -H "Content-Type: application/json" \
  -d "{
    \"user_id\": \"$USER_ID\",
    \"session_id\": \"$SESSION_ID\",
    \"query\": \"你知道我喜欢吃什么口味的菜吗？\",
    \"top_k\": 5
  }" | jq '.answer'

# 6. 查询会话消息数量
echo -e "\n6. 查询会话消息数量..."
curl -s -X GET "$BASE_URL/session/list?user_id=$USER_ID&status=1&limit=10" | \
  jq --arg sid "$SESSION_ID" '.sessions[] | select(.session_id == $sid) | {title: .title, message_count: .message_count}'

# 7. 查询短期记忆（通过 API 直接查询）
echo -e "\n7. 查询短期记忆..."
curl -s -X GET "$BASE_URL/memory/list?session_id=$SESSION_ID&user_id=$USER_ID&limit=10" | \
  jq '.memories[] | {created_at: .created_at, query: .query_summary, relevance: .base_relevance_score}'

echo -e "\n=========================================="
echo "测试完成！"
echo "=========================================="
