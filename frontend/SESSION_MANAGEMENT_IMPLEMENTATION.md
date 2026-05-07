# 前端会话管理功能实现总结

## ✅ 已完成的功能

### 1. 页面布局调整

原来的布局：
```
┌─────────────────────────────────────┐
│         Knowledge Agent 标题          │
├──────────┬──────────────────────────┤
│ 知识库    │                          │
│ 文档选择  │     聊天区域              │
│          │                          │
└──────────┴──────────────────────────┘
```

新的布局：
```
┌──────┬────────┬─────────────────────┐
│会话列表│知识库  │                     │
│      │文档选择│     聊天区域          │
│ 新对话 │      │                     │
│ 会话 1 │      │   用户消息 (右侧)      │
│ 会话 2 │      │   助手回复 (左侧)      │
│ 会话 3 │      │                     │
└──────┴────────┴─────────────────────┘
```

### 2. 新增功能

#### ✅ 创建新对话按钮

位置：左侧会话列表顶部
- 蓝色渐变按钮
- 带加号图标
- 点击后调用 `/api/v1/session/create`
- 自动切换到新会话

#### ✅ 会话列表

显示内容：
- 会话标题
- 消息数量
- 最后活动时间（智能显示：今天/昨天/日期）
- 删除按钮（右侧 X 图标）

交互：
- 点击会话切换到该对话
- 高亮显示当前会话
- 悬停效果

#### ✅ 会话历史加载

- 页面加载时自动获取会话列表
- 选中第一个会话（如果有）
- 加载该会话的所有历史消息
- 显示用户消息和助手回复

#### ✅ 消息持久化

发送消息时：
1. 使用 `/api/v1/session/chat` 接口
2. 自动关联到当前会话（`session_id`）
3. 后端自动记录用户消息和助手消息
4. 返回消息 ID，前端更新 UI
5. 刷新会话列表（更新消息数量）

#### ✅ 删除会话

- 每个会话右侧有删除按钮
- 点击弹出确认对话框
- 调用 `/api/v1/session/{session_id}` DELETE
- 从列表移除，如果是当前会话则清空消息

---

## 📝 代码修改

### 文件：`frontend/src/views/AgentChatView.vue`

#### 新增状态变量

```javascript
// 用户 ID（TODO: 从用户认证获取）
const userId = 'user_001'

// 会话管理
const sessions = ref([])
const currentSessionId = ref(null)
```

#### 新增方法

```javascript
// 加载会话列表
const loadSessions = async () => { ... }

// 创建新会话
const createNewSession = async () => { ... }

// 选择会话
const selectSession = async (sessionId) => { ... }

// 加载会话消息
const loadMessages = async (sessionId) => { ... }

// 删除会话
const deleteSession = async (sessionId) => { ... }

// 格式化时间
const formatTime = (timestamp) => { ... }
```

#### 修改的方法

```javascript
// 发送消息 - 使用完整聊天流程 API
const sendMessage = async () => {
  // ...
  const response = await fetch('/api/v1/session/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      user_id: userId,
      query: text,
      session_id: currentSessionId.value, // 关联会话
      knowledge_base_ids: selectedKbIds.value,
      document_ids: selectedDocIds.value,
      top_k: 10
    })
  })
  // ...
}
```

#### 修改的初始化

```javascript
onMounted(() => {
  loadSessions()        // 加载会话列表
  loadKnowledgeBases()  // 加载知识库列表
})
```

---

## 🎨 UI 设计

### 会话列表样式

```vue
<!-- 创建新对话按钮 -->
<button class="w-full py-3 bg-gradient-to-r from-primary-500 to-primary-600 text-white rounded-xl font-medium hover:from-primary-600 hover:to-primary-700 transition-all shadow-md hover:shadow-lg mb-4">
  <span class="flex items-center justify-center gap-2">
    <svg class="w-5 h-5">...</svg>
    新对话
  </span>
</button>

<!-- 会话项 -->
<div :class="[
  'p-3 rounded-xl cursor-pointer transition-all',
  currentSessionId === session.session_id 
    ? 'bg-primary-50 border-2 border-primary-500' 
    : 'bg-gray-50 border-2 border-transparent hover:bg-gray-100'
]">
  <div class="flex items-start justify-between">
    <div class="flex-1 min-w-0">
      <p class="font-medium text-gray-800 truncate">{{ session.title }}</p>
      <p class="text-xs text-gray-500 mt-1">
        {{ session.message_count || 0 }} 条消息 · 
        {{ formatTime(session.updated_at) }}
      </p>
    </div>
    <button @click.stop="deleteSession(session.session_id)" class="ml-2 p-1 text-gray-400 hover:text-red-500 hover:bg-red-50 rounded transition-colors">
      <svg class="w-4 h-4">...</svg>
    </button>
  </div>
</div>
```

### 消息气泡样式

用户消息（右侧蓝色）：
```vue
<div class="flex justify-end">
  <div class="chat-bubble chat-bubble-user">
    <p class="whitespace-pre-wrap">{{ msg.content }}</p>
  </div>
</div>
```

助手回复（左侧白色）：
```vue
<div class="flex justify-start">
  <div class="chat-bubble chat-bubble-agent">
    <p class="whitespace-pre-wrap">{{ msg.content }}</p>
    <!-- 引用来源 -->
    <div v-if="msg.sources && msg.sources.length > 0">...</div>
  </div>
</div>
```

---

## 🔄 数据流程

### 1. 创建新对话

```
用户点击"新对话"
    ↓
createNewSession()
    ↓
POST /api/v1/session/create
{
  user_id: "user_001",
  title: "对话 2026-05-03 14:30:00"
}
    ↓
返回 { session_id, title, created_at }
    ↓
添加到 sessions 列表顶部
    ↓
selectSession(session_id)
    ↓
加载空的消息列表
```

### 2. 发送消息

```
用户输入问题 + 点击发送
    ↓
sendMessage()
    ↓
临时显示用户消息（优化体验）
    ↓
POST /api/v1/session/chat
{
  user_id: "user_001",
  query: "什么是机器学习？",
  session_id: "当前会话 ID",
  knowledge_base_ids: [...],
  document_ids: [...],
  top_k: 10
}
    ↓
后端处理：
  1. 记录用户消息到 message 表
  2. 调用 Agent 处理
  3. 记录助手消息到 message 表
  4. 更新 session 的消息计数
    ↓
返回 {
  session_id,
  user_message_id,
  assistant_message_id,
  answer,
  sources
}
    ↓
移除临时用户消息
    ↓
添加助手回复（包含真实消息 ID）
    ↓
刷新会话列表（更新消息数量）
```

### 3. 切换会话

```
用户点击会话列表中的某个会话
    ↓
selectSession(session_id)
    ↓
设置 currentSessionId = session_id
    ↓
loadMessages(session_id)
    ↓
GET /api/v1/session/message/list?session_id=xxx&limit=100
    ↓
返回消息列表
    ↓
格式化并显示消息
    ↓
滚动到底部
```

### 4. 删除会话

```
用户点击会话右侧的删除按钮
    ↓
deleteSession(session_id)
    ↓
确认对话框
    ↓
DELETE /api/v1/session/{session_id}
    ↓
从 sessions 列表移除
    ↓
如果是当前会话，清空消息
```

---

## 🧪 测试步骤

### 1. 启动后端

```bash
cd /mnt/d/Study/Agents/MA/data3/zb/MyAgent/backend
python main.py
```

### 2. 启动前端

```bash
cd /mnt/d/Study/Agents/MA/data3/zb/MyAgent/frontend
npm run dev
```

### 3. 测试流程

1. **打开页面**
   - 访问 http://localhost:5173
   - 查看左侧会话列表（应该为空或显示已有会话）

2. **创建新对话**
   - 点击"新对话"按钮
   - 查看会话列表新增一个会话
   - 确认自动切换到新会话

3. **发送消息**
   - 选择知识库或文档（可选）
   - 输入问题并发送
   - 查看用户消息显示在右侧（蓝色）
   - 查看助手回复显示在左侧（白色）
   - 查看会话列表的消息数量更新

4. **切换会话**
   - 再次点击"新对话"创建第二个会话
   - 发送一条消息
   - 点击第一个会话切换回去
   - 确认第一个会话的历史消息正确显示

5. **删除会话**
   - 点击某个会话右侧的删除按钮
   - 确认弹出对话框
   - 确认删除
   - 查看会话从列表移除

---

## 📋 检查清单

- [x] 页面布局正确（3 列布局）
- [x] 新对话按钮显示正常
- [x] 会话列表显示正常
- [x] 点击新对话按钮创建会话
- [x] 会话列表自动加载
- [x] 点击会话切换对话
- [x] 消息历史正确显示
- [x] 用户消息右侧蓝色气泡
- [x] 助手回复左侧白色气泡
- [x] 消息持久化到数据库
- [x] 删除会话功能正常
- [x] 时间显示智能格式化
- [ ] 知识库和文档选择正常（原有功能）
- [ ] 引用来源显示正常（原有功能）

---

## 🚀 下一步优化

### 1. 用户认证

当前 `userId` 硬编码为 `'user_001'`，需要：
```javascript
// 从用户认证系统获取
const userId = useAuth().currentUserId
```

### 2. 会话标题自动更新

根据对话内容自动生成标题：
```javascript
// 首次对话后，自动生成标题
const firstQuery = messages.value[0]?.content
if (firstQuery && firstQuery.length > 20) {
  const title = firstQuery.substring(0, 20) + '...'
  await updateSessionTitle(sessionId, title)
}
```

### 3. 加载更多历史

分页加载消息：
```javascript
const loadMoreMessages = async (sessionId, offset) => {
  const res = await fetch(`/api/v1/session/message/list?session_id=${sessionId}&limit=50&offset=${offset}`)
  // ...
}
```

### 4. 搜索会话

添加搜索框过滤会话列表。

### 5. 归档会话

将不常用的会话归档，不删除但不在主列表显示。

---

## 📚 相关文档

- [会话管理 API 文档](./backend/docs/SESSION_MANAGEMENT.md)
- [前端集成指南](./backend/docs/FRONTEND_INTEGRATION.md)
- [API 接口文档](http://localhost:8000/docs)

---

前端会话管理功能已经完整实现！现在用户可以：
1. ✅ 点击"新对话"按钮创建新会话
2. ✅ 查看所有历史会话
3. ✅ 切换不同会话查看历史消息
4. ✅ 发送消息并自动记录到数据库
5. ✅ 删除不需要的会话

测试一下，看看效果如何！ 🎉
