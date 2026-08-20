# JWT 认证与短期记忆集成方案

## 概述

本文档描述了如何在 MyAgent 项目中实现 JWT 认证系统，并将短期记忆与用户/会话正确关联。

## 架构设计

```
┌─────────────────────────────────────────────────────────────┐
│                      前端 (Vue 3)                           │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  1. 用户注册 → POST /api/v1/auth/register                   │
│  2. 用户登录 → POST /api/v1/auth/login                      │
│  3. 保存 JWT token 到 localStorage                           │
│  4. 所有请求携带 Authorization: Bearer <token>              │
│  5. 创建对话时，后端从 token 解析 user_id                    │
│                                                              │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│                    后端 (FastAPI)                            │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  /api/v1/auth/register  → 用户注册                          │
│  /api/v1/auth/login     → 用户登录，返回 JWT token           │
│  /api/v1/auth/me        → 获取当前用户信息                   │
│                                                              │
│  /api/v1/session/create → 创建会话（从 token 获取 user_id）  │
│  /api/v1/session/chat   → 对话（从 token 获取 user_id）      │
│                                                              │
│  Agent 调用流程：                                            │
│  1. 从 token 解析 user_id                                   │
│  2. 传入 session_id 和 user_id 到 Agent                     │
│  3. Agent 检索短期记忆（按 session_id + user_id）            │
│  4. 将记忆注入到 Prompt                                       │
│  5. 生成答案后存储新的短期记忆                               │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

## 实现步骤

### 步骤 1: 数据库表修复

**执行 SQL 脚本**：
```bash
mysql -u root -p'DataSource2024!' knowledge_base_db < backend/database/mysql/fix_short_term_memory_table.sql
```

这将添加 `deleted_at` 字段到 `short_term_memory` 表。

### 步骤 2: 前端集成 JWT 认证

#### 2.1 创建认证状态管理

在 `frontend/src/stores/` 下创建 `auth.js`：

```javascript
import { ref, computed } from 'vue'
import axios from 'axios'

const API_BASE = '/api/v1'

export function useAuth() {
  const user = ref(null)
  const token = ref(localStorage.getItem('token') || null)
  
  // 设置 token 并保存到 localStorage
  const setToken = (newToken) => {
    token.value = newToken
    if (newToken) {
      localStorage.setItem('token', newToken)
    } else {
      localStorage.removeItem('token')
    }
  }
  
  // 用户注册
  const register = async (username, password, email, displayName) => {
    const response = await axios.post(`${API_BASE}/auth/register`, {
      username,
      password,
      email,
      display_name: displayName
    })
    
    if (response.data.success) {
      setToken(response.data.token)
      user.value = {
        user_id: response.data.user_id,
        username: response.data.username,
        display_name: response.data.display_name
      }
    }
    
    return response.data
  }
  
  // 用户登录
  const login = async (username, password) => {
    const response = await axios.post(`${API_BASE}/auth/login`, {
      username,
      password
    })
    
    if (response.data.success) {
      setToken(response.data.token)
      user.value = {
        user_id: response.data.user_id,
        username: response.data.username,
        display_name: response.data.display_name,
        email: response.data.email
      }
    }
    
    return response.data
  }
  
  // 登出
  const logout = () => {
    setToken(null)
    user.value = null
  }
  
  // 获取当前用户信息
  const fetchUserInfo = async () => {
    if (!token.value) return null
    
    const response = await axios.get(`${API_BASE}/auth/me`, {
      headers: {
        'Authorization': `Bearer ${token.value}`
      }
    })
    
    if (response.data.success) {
      user.value = response.data
    }
    
    return response.data
  }
  
  // Axios 拦截器：自动添加 token
  axios.interceptors.request.use(config => {
    if (token.value) {
      config.headers.Authorization = `Bearer ${token.value}`
    }
    return config
  })
  
  return {
    user,
    token,
    isAuthenticated: computed(() => !!token.value),
    register,
    login,
    logout,
    fetchUserInfo
  }
}
```

#### 2.2 创建登录/注册页面

在 `frontend/src/views/` 下创建 `LoginView.vue`：

```vue
<template>
  <div class="flex items-center justify-center min-h-screen bg-gray-100">
    <div class="w-full max-w-md p-8 space-y-6 bg-white rounded-xl shadow-lg">
      <h1 class="text-2xl font-bold text-center text-gray-800">MyAgent</h1>
      
      <!-- 切换登录/注册 -->
      <div class="flex gap-2">
        <button 
          @click="mode = 'login'"
          :class="['flex-1 py-2 rounded-lg', mode === 'login' ? 'bg-primary-500 text-white' : 'bg-gray-200']"
        >
          登录
        </button>
        <button 
          @click="mode = 'register'"
          :class="['flex-1 py-2 rounded-lg', mode === 'register' ? 'bg-primary-500 text-white' : 'bg-gray-200']"
        >
          注册
        </button>
      </div>
      
      <!-- 表单 -->
      <form @submit.prevent="handleSubmit" class="space-y-4">
        <div>
          <label class="block text-sm font-medium text-gray-700">用户名</label>
          <input 
            v-model="username"
            type="text"
            required
            class="w-full px-4 py-2 mt-1 border rounded-lg focus:ring-2 focus:ring-primary-500"
          />
        </div>
        
        <div>
          <label class="block text-sm font-medium text-gray-700">密码</label>
          <input 
            v-model="password"
            type="password"
            required
            class="w-full px-4 py-2 mt-1 border rounded-lg focus:ring-2 focus:ring-primary-500"
          />
        </div>
        
        <div v-if="mode === 'register'">
          <label class="block text-sm font-medium text-gray-700">邮箱（可选）</label>
          <input 
            v-model="email"
            type="email"
            class="w-full px-4 py-2 mt-1 border rounded-lg focus:ring-2 focus:ring-primary-500"
          />
        </div>
        
        <div v-if="error" class="p-3 text-sm text-red-600 bg-red-50 rounded-lg">
          {{ error }}
        </div>
        
        <button 
          type="submit"
          :disabled="loading"
          class="w-full py-3 text-white bg-primary-500 rounded-lg hover:bg-primary-600 disabled:opacity-50"
        >
          {{ loading ? '处理中...' : (mode === 'login' ? '登录' : '注册') }}
        </button>
      </form>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuth } from '@/stores/auth'

const router = useRouter()
const { login, register } = useAuth()

const mode = ref('login') // 'login' | 'register'
const username = ref('')
const password = ref('')
const email = ref('')
const error = ref('')
const loading = ref(false)

const handleSubmit = async () => {
  error.value = ''
  loading.value = true
  
  try {
    if (mode.value === 'login') {
      const result = await login(username.value, password.value)
      if (result.success) {
        router.push('/chat')
      } else {
        error.value = result.error || '登录失败'
      }
    } else {
      const result = await register(username.value, password.value, email.value)
      if (result.success) {
        router.push('/chat')
      } else {
        error.value = result.error || '注册失败'
      }
    }
  } catch (err) {
    error.value = err.response?.data?.detail || '请求失败'
  } finally {
    loading.value = false
  }
}
</script>
```

#### 2.3 修改路由配置

在 `frontend/src/router/index.js` 中添加路由保护：

```javascript
import { createRouter, createWebHistory } from 'vue-router'
import LoginView from '../views/LoginView.vue'
import AgentChatView from '../views/AgentChatView.vue'

const routes = [
  {
    path: '/',
    redirect: '/login'
  },
  {
    path: '/login',
    component: LoginView,
    meta: { requiresAuth: false }
  },
  {
    path: '/chat',
    component: AgentChatView,
    meta: { requiresAuth: true }
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

// 路由守卫：检查认证
router.beforeEach((to, from, next) => {
  const token = localStorage.getItem('token')
  
  if (to.meta.requiresAuth && !token) {
    next('/login')
  } else if (to.path === '/login' && token) {
    next('/chat')
  } else {
    next()
  }
})

export default router
```

#### 2.4 修改 AgentChatView 获取 user_id

```javascript
// 从 localStorage 获取 user_id（登录时保存）
const userId = localStorage.getItem('user_id') || 'user_001'  // 临时回退
```

### 步骤 3: 后端传递 session_id 和 user_id 到 Agent

修改 `session_controller.py` 的 `/chat` 接口：

```python
@router.post("/chat", summary="完整的聊天流程")
async def chat_with_session(
    user_id: Optional[str] = Body(None, description="用户 ID（从 token 解析）"),
    query: str = Body(...),
    session_id: Optional[str] = Body(None),
    # ... 其他参数
):
    # 1. 如果没有 session_id，创建新会话
    if not session_id:
        session = session_repo.create_session(user_id=user_id, ...)
        session_id = session['session_uuid']
    
    # 2. 调用 Agent，传入 session_id 和 user_id
    result = await service.invoke(query, config, session_id=session_id, user_id=user_id)
    
    # 3. 存储短期记忆
    memory_service = ShortTermMemoryService(db_client)
    memory_service.extract_memory_from_conversation(
        session_id=session_id,
        user_id=user_id,
        user_query=query,
        assistant_answer=result.get('answer', ''),
        message_id=assistant_message_id
    )
```

### 步骤 4: 启用短期记忆检索

修改 `generate_answer.py` 节点，注入短期记忆上下文：

```python
def generate_answer(state: KnowledgeAgentState):
    session_id = state.get("session_id")
    user_id = state.get("user_id")
    
    # 检索短期记忆
    if session_id:
        memory_service = ShortTermMemoryService(db_client)
        memory_context = memory_service.build_prompt_context(
            session_id=session_id,
            user_id=user_id,
            current_query=query,
            max_context_tokens=1000
        )
    
    # 注入到 Prompt
    user_prompt = f"用户问题：{query}\n\n{memory_context}\n上下文材料：..."
```

## 测试流程

1. **启动后端**：
```bash
cd backend
python3 -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

2. **测试认证 API**：
```bash
# 注册
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username": "testuser", "password": "123456", "email": "test@example.com"}'

# 登录
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "testuser", "password": "123456"}'
```

3. **前端测试**：
   - 访问 http://localhost:5173
   - 注册/登录
   - 进入聊天页面
   - 连续对话 3-4 次
   - 询问历史偏好，检查短期记忆是否生效

## 安全注意事项

1. **JWT Secret**：在生产环境中，将 `JWT_SECRET_KEY` 设置为一个强随机字符串，并存储在环境变量中
2. **HTTPS**：生产环境必须使用 HTTPS 传输
3. **Token 过期时间**：默认 72 小时，可根据需求调整
4. **密码强度**：建议添加密码复杂度校验

## 后续优化

1. ✅ 添加刷新 token 机制
2. ✅ 添加用户登出时撤销 token
3. ✅ 添加角色权限系统（admin/user）
4. ✅ 添加操作日志
5. ✅ 添加密码找回功能
