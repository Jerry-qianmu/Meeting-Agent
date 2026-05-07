# 前端集成指南 - 会话管理

## 📋 概述

本文档说明如何在前端实现对话会话管理功能，包括创建会话、记录消息、显示历史对话等。

## 🎯 核心功能

1. **创建新对话** - 用户点击"新对话"按钮
2. **记录对话** - 自动记录用户消息和助手回复
3. **显示历史** - 打开会话时加载并显示历史对话
4. **会话列表** - 显示用户的所有会话

## 🔗 API 接口

### 会话管理

| 方法 | 路径 | 功能 |
|------|------|------|
| POST | `/api/v1/session/create` | 创建新会话 |
| GET | `/api/v1/session/list?user_id=xxx` | 获取会话列表 |
| GET | `/api/v1/session/{session_id}` | 获取会话详情 |
| PUT | `/api/v1/session/{session_id}/title` | 更新会话标题 |
| DELETE | `/api/v1/session/{session_id}` | 删除会话 |

### 消息管理

| 方法 | 路径 | 功能 |
|------|------|------|
| POST | `/api/v1/session/message/create` | 创建消息 |
| GET | `/api/v1/session/message/list?session_id=xxx` | 获取消息列表 |
| POST | `/api/v1/session/message/{message_id}/update` | 更新消息 |

### 完整聊天流程

| 方法 | 路径 | 功能 |
|------|------|------|
| POST | `/api/v1/session/chat` | 完整的聊天流程（一步完成） |

## 💻 前端实现示例

### 1. API Service 层

```javascript
// frontend/src/api/session.js
import axios from 'axios';

const API_BASE = '/api/v1';

export const sessionApi = {
  // 创建新会话
  async createSession(userData) {
    const response = await axios.post(`${API_BASE}/session/create`, {
      user_id: userData.userId,
      title: userData.title || null,
      knowledge_base_ids: userData.knowledgeBaseIds || null,
      document_ids: userData.documentIds || null
    });
    return response.data;
  },

  // 获取会话列表
  async listSessions(userId, status = 1, limit = 50, offset = 0) {
    const response = await axios.get(`${API_BASE}/session/list`, {
      params: { user_id: userId, status, limit, offset }
    });
    return response.data;
  },

  // 获取会话详情
  async getSession(sessionId, userId) {
    const response = await axios.get(`${API_BASE}/session/${sessionId}`, {
      params: { user_id: userId }
    });
    return response.data;
  },

  // 获取消息列表
  async getMessages(sessionId, limit = 100, offset = 0) {
    const response = await axios.get(`${API_BASE}/session/message/list`, {
      params: { session_id: sessionId, limit, offset }
    });
    return response.data;
  },

  // 完整聊天流程（推荐）
  async chat(userData) {
    const response = await axios.post(`${API_BASE}/session/chat`, {
      user_id: userData.userId,
      query: userData.query,
      session_id: userData.sessionId || null,
      knowledge_base_ids: userData.knowledgeBaseIds || null,
      document_ids: userData.documentIds || null,
      top_k: userData.topK || 10
    });
    return response.data;
  }
};
```

### 2. Vue 组件 - 对话页面

```vue
<!-- frontend/src/views/AgentChatView.vue -->
<template>
  <div class="chat-container">
    <!-- 左侧：会话列表 -->
    <div class="session-sidebar">
      <button @click="createNewSession" class="new-session-btn">
        + 新对话
      </button>
      
      <div class="session-list">
        <div
          v-for="session in sessions"
          :key="session.session_id"
          @click="selectSession(session.session_id)"
          :class="{ active: currentSessionId === session.session_id }"
          class="session-item"
        >
          <div class="session-title">{{ session.title }}</div>
          <div class="session-meta">
            {{ session.message_count }} 条消息
          </div>
        </div>
      </div>
    </div>

    <!-- 右侧：对话区域 -->
    <div class="chat-main">
      <!-- 消息列表 -->
      <div class="message-list" ref="messageList">
        <div
          v-for="msg in messages"
          :key="msg.message_id"
          :class="['message', msg.role]"
        >
          <div class="message-avatar">
            {{ msg.role === 'user' ? '👤' : '🤖' }}
          </div>
          <div class="message-content">
            {{ msg.content }}
          </div>
          <div class="message-time">
            {{ formatTime(msg.created_at) }}
          </div>
        </div>
        
        <!-- 加载状态 -->
        <div v-if="isLoading" class="message assistant">
          <div class="message-content">正在思考...</div>
        </div>
      </div>

      <!-- 输入区域 -->
      <div class="input-area">
        <textarea
          v-model="userInput"
          placeholder="输入您的问题..."
          @keydown.enter.exact.prevent="sendMessage"
          :disabled="isLoading"
        ></textarea>
        <button 
          @click="sendMessage" 
          :disabled="!userInput.trim() || isLoading"
        >
          发送
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, nextTick } from 'vue';
import { sessionApi } from '@/api/session';

// 状态
const userId = 'user_001'; // TODO: 从用户认证获取
const sessions = ref([]);
const messages = ref([]);
const currentSessionId = ref(null);
const userInput = ref('');
const isLoading = ref(false);
const messageList = ref(null);

// 初始化
onMounted(async () => {
  await loadSessions();
});

// 加载会话列表
async function loadSessions() {
  try {
    const response = await sessionApi.listSessions(userId);
    sessions.value = response.sessions;
    
    // 如果有会话，选中第一个
    if (sessions.value.length > 0) {
      selectSession(sessions.value[0].session_id);
    }
  } catch (error) {
    console.error('加载会话列表失败:', error);
  }
}

// 创建新会话
async function createNewSession() {
  try {
    const response = await sessionApi.createSession({
      userId: userId,
      title: `对话 ${new Date().toLocaleString()}`
    });
    
    // 添加到会话列表
    sessions.value.unshift({
      session_id: response.session_id,
      title: response.title,
      message_count: 0
    });
    
    // 切换到新会话
    selectSession(response.session_id);
  } catch (error) {
    console.error('创建会话失败:', error);
  }
}

// 选择会话
async function selectSession(sessionId) {
  currentSessionId.value = sessionId;
  await loadMessages(sessionId);
}

// 加载消息列表
async function loadMessages(sessionId) {
  try {
    const response = await sessionApi.getMessages(sessionId, 100);
    messages.value = response.messages;
    
    // 滚动到底部
    await nextTick();
    scrollToBottom();
  } catch (error) {
    console.error('加载消息失败:', error);
  }
}

// 发送消息
async function sendMessage() {
  const query = userInput.value.trim();
  if (!query || isLoading.value) return;
  
  // 清空输入框
  userInput.value = '';
  isLoading.value = true;
  
  try {
    // 使用完整的聊天流程 API
    const response = await sessionApi.chat({
      userId: userId,
      query: query,
      sessionId: currentSessionId.value,
      topK: 10
    });
    
    // 将助手回复添加到消息列表
    messages.value.push({
      message_id: response.assistant_message_id,
      role: 'assistant',
      content: response.answer,
      created_at: new Date().toISOString()
    });
    
    // 滚动到底部
    await nextTick();
    scrollToBottom();
    
  } catch (error) {
    console.error('发送消息失败:', error);
    
    // 显示错误消息
    messages.value.push({
      message_id: null,
      role: 'assistant',
      content: '抱歉，处理您的请求时出现了错误。',
      created_at: new Date().toISOString()
    });
  } finally {
    isLoading.value = false;
  }
}

// 滚动到底部
function scrollToBottom() {
  if (messageList.value) {
    messageList.value.scrollTop = messageList.value.scrollHeight;
  }
}

// 格式化时间
function formatTime(timestamp) {
  const date = new Date(timestamp);
  return date.toLocaleTimeString('zh-CN', { 
    hour: '2-digit', 
    minute: '2-digit' 
  });
}
</script>

<style scoped>
.chat-container {
  display: flex;
  height: 100vh;
}

.session-sidebar {
  width: 300px;
  border-right: 1px solid #e5e7eb;
  padding: 16px;
  overflow-y: auto;
}

.new-session-btn {
  width: 100%;
  padding: 12px;
  background: #3b82f6;
  color: white;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  margin-bottom: 16px;
}

.session-item {
  padding: 12px;
  border-radius: 8px;
  cursor: pointer;
  margin-bottom: 8px;
  transition: background-color 0.2s;
}

.session-item:hover {
  background: #f3f4f6;
}

.session-item.active {
  background: #dbeafe;
  border-left: 3px solid #3b82f6;
}

.session-title {
  font-weight: 500;
  margin-bottom: 4px;
}

.session-meta {
  font-size: 12px;
  color: #6b7280;
}

.chat-main {
  flex: 1;
  display: flex;
  flex-direction: column;
}

.message-list {
  flex: 1;
  padding: 24px;
  overflow-y: auto;
}

.message {
  display: flex;
  margin-bottom: 24px;
}

.message.user {
  flex-direction: row-reverse;
}

.message-avatar {
  font-size: 24px;
  margin: 0 12px;
}

.message-content {
  max-width: 70%;
  padding: 12px 16px;
  border-radius: 12px;
  line-height: 1.5;
}

.message.user .message-content {
  background: #3b82f6;
  color: white;
  border-bottom-right-radius: 4px;
}

.message.assistant .message-content {
  background: #f3f4f6;
  color: #1f2937;
  border-bottom-left-radius: 4px;
}

.message-time {
  font-size: 12px;
  color: #9ca3af;
  margin-top: 4px;
}

.input-area {
  display: flex;
  padding: 16px 24px;
  border-top: 1px solid #e5e7eb;
  gap: 12px;
}

.input-area textarea {
  flex: 1;
  padding: 12px;
  border: 1px solid #d1d5db;
  border-radius: 8px;
  resize: none;
  font-family: inherit;
  min-height: 50px;
}

.input-area button {
  padding: 12px 24px;
  background: #3b82f6;
  color: white;
  border: none;
  border-radius: 8px;
  cursor: pointer;
}

.input-area button:disabled {
  background: #9ca3af;
  cursor: not-allowed;
}
</style>
```

## 🔄 完整的聊天流程

### 推荐方式：使用 `/session/chat` 接口

这是最简单的实现方式，后端会自动处理：
1. 创建/获取会话
2. 记录用户消息
3. 调用 Agent 处理
4. 记录助手消息
5. 返回答案

```javascript
// 前端只需调用一次
const response = await sessionApi.chat({
  userId: 'user_001',
  query: '什么是机器学习？',
  sessionId: currentSessionId.value, // 可选，不传则创建新会话
  knowledgeBaseIds: ['kb-xxx'],      // 可选
  documentIds: ['doc-xxx'],          // 可选
  topK: 10                           // 可选
});

// 返回结果包含：
// - session_id: 会话 ID
// - user_message_id: 用户消息 ID
// - assistant_message_id: 助手消息 ID
// - answer: 助手回答
// - sources: 引用来源
```

### 分步方式：手动管理消息

如果你想更精细地控制，可以分步调用：

```javascript
// 1. 创建会话
const session = await sessionApi.createSession({
  userId: 'user_001',
  title: '我的对话'
});
const sessionId = session.session_id;

// 2. 记录用户消息
const userMsg = await sessionApi.createMessage({
  sessionId: sessionId,
  userId: 'user_001',
  role: 'user',
  content: '什么是机器学习？'
});

// 3. 调用 Agent（使用原有的 Agent API）
const agentResponse = await axios.post('/api/v1/agent/chat', {
  query: '什么是机器学习？',
  knowledge_base_ids: ['kb-xxx']
});

// 4. 记录助手消息
const assistantMsg = await sessionApi.createMessage({
  sessionId: sessionId,
  userId: 'user_001',
  role: 'assistant',
  content: agentResponse.answer,
  model: 'qwen-plus',
  tokens_prompt: 150,
  tokens_completion: 200,
  latency_ms: 2500
});

// 5. 获取消息列表（显示历史）
const messages = await sessionApi.getMessages(sessionId);
```

## 📝 注意事项

### 1. UUID 格式

所有 ID 字段都是字符串格式（带连字符的 UUID），例如：
```javascript
"550e8400-e29b-41d4-a716-446655440000"
```

### 2. 角色字段

消息角色使用字符串：
- `user` - 用户消息
- `assistant` - 助手消息
- `system` - 系统消息
- `tool` - 工具消息

### 3. 时间戳

所有时间字段使用 ISO 8601 格式：
```javascript
"2026-05-03T13:15:30"
```

### 4. 分页

获取消息列表时支持分页：
```javascript
// 获取最近 100 条消息
const messages = await sessionApi.getMessages(sessionId, 100, 0);

// 获取下一页
const moreMessages = await sessionApi.getMessages(sessionId, 100, 100);
```

## 🧪 测试

### 使用 Postman 测试

#### 1. 创建会话
```http
POST http://localhost:8000/api/v1/session/create
Content-Type: application/json

{
  "user_id": "user_001",
  "title": "测试对话"
}
```

#### 2. 发送消息
```http
POST http://localhost:8000/api/v1/session/chat
Content-Type: application/json

{
  "user_id": "user_001",
  "query": "什么是机器学习？",
  "session_id": "会话 ID（从上一步获取）",
  "top_k": 10
}
```

#### 3. 获取消息列表
```http
GET http://localhost:8000/api/v1/session/message/list?session_id=会话ID&limit=100
```

#### 4. 获取会话列表
```http
GET http://localhost:8000/api/v1/session/list?user_id=user_001&status=1&limit=50
```

## 🎨 前端样式建议

### 消息气泡样式

```css
/* 用户消息 - 右侧蓝色气泡 */
.message.user .message-content {
  background: #3b82f6;  /* 蓝色 */
  color: white;
  border-bottom-right-radius: 4px;
  margin-left: auto;
}

/* 助手消息 - 左侧白色气泡 */
.message.assistant .message-content {
  background: #f3f4f6;  /* 浅灰色 */
  color: #1f2937;
  border-bottom-left-radius: 4px;
  margin-right: auto;
}
```

### 引用来源显示

```vue
<div v-if="response.sources && response.sources.length > 0" class="sources">
  <div class="sources-title">引用来源：</div>
  <div 
    v-for="(source, index) in response.sources" 
    :key="index"
    class="source-item"
  >
    [{{ index + 1 }}] {{ source.title || source.filename }}
  </div>
</div>
```

## 📚 相关文档

- [会话 API 文档](http://localhost:8000/docs) - Swagger UI
- [数据库表结构](./DATABASE_SCHEMA.md)
- [短期记忆系统](./SHORT_TERM_MEMORY.md)
