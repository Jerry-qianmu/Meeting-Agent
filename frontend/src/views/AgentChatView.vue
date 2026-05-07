<template>
  <div ref="agentView" class="agent-workbench">
    <aside class="agent-sidebar ios-card">
      <button
        @click="createNewSession"
        class="agent-primary-action"
      >
        <svg class="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.4" d="M12 5v14m7-7H5" />
        </svg>
        新对话
      </button>

      <div class="agent-section-title">会话历史 <span>({{ sessions.length }})</span></div>

      <div class="agent-scroll-list">
        <div
          v-for="session in sessions"
          :key="session.session_id"
          :data-session-id="session.session_id"
          class="agent-session-wrapper"
          :class="{ 'agent-session-wrapper-active': currentSessionId === session.session_id }"
        >
          <button
            type="button"
            @click="selectSession(session.session_id)"
            class="agent-session-item"
            :class="{ 'agent-session-item-active': currentSessionId === session.session_id }"
          >
            <span class="truncate font-semibold">{{ session.title }}</span>
            <small>{{ session.message_count || 0 }} 条消息 · {{ formatTime(session.updated_at) }}</small>
          </button>
          <div class="agent-session-actions">
            <button
              type="button"
              @click.stop="startEditSession(session)"
              class="agent-session-edit-btn"
              :title="'重命名'"
            >
              <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
              </svg>
            </button>
            <button
              type="button"
              @click.stop="deleteSession(session.session_id)"
              class="agent-session-delete-btn"
              :title="'删除会话'"
            >
              <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
              </svg>
            </button>
          </div>
        </div>

        <div v-if="sessions.length === 0" class="agent-empty">
          <svg class="h-7 w-7" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.8" d="M8 10h.01M12 10h.01M16 10h.01M7 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
          </svg>
          <p>暂无会话记录</p>
        </div>
      </div>
    </aside>

    <section class="agent-chat-panel ios-card">
      <div ref="chatContainer" class="agent-message-area">
        <div v-if="messages.length === 0" class="agent-welcome">
          <div class="agent-welcome-icon">
            <svg class="h-10 w-10" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 10h.01M12 10h.01M16 10h.01M7 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
            </svg>
          </div>
          <h2>开始对话</h2>
          <p>选择知识库和文档，然后提问吧。</p>

          <div class="agent-suggestions">
            <button v-for="suggestion in suggestions" :key="suggestion" @click="fillQuery(suggestion)">
              {{ suggestion }}
            </button>
          </div>
        </div>

        <div
          v-for="(msg, index) in messages"
          :key="index"
          class="agent-message-row"
          :class="msg.role === 'user' ? 'agent-message-row-user' : 'agent-message-row-assistant'"
        >
          <div :class="msg.role === 'user' ? 'ios-chat-bubble-user' : 'ios-chat-bubble-agent'">
            <p class="whitespace-pre-wrap text-[15px] leading-relaxed">{{ msg.content }}</p>

            <div v-if="msg.role === 'assistant' && msg.sources?.length" class="agent-sources">
              <p>参考来源</p>
              <div v-for="source in msg.sources.slice(0, 3)" :key="source.chunk_id" class="agent-source-item">
                <strong>{{ source.title || source.doc_id }}</strong>
                <span>{{ source.content }}</span>
              </div>
            </div>
          </div>
        </div>

        <div v-if="isLoading" class="agent-message-row agent-message-row-assistant">
          <div class="ios-chat-bubble-agent">
            <div class="ios-loading-dots">
              <div></div><div></div><div></div>
            </div>
          </div>
        </div>
      </div>

      <div class="agent-composer">
        <textarea
          v-model="query"
          @keydown.enter.exact.prevent="sendMessage"
          placeholder="输入问题，按 Enter 发送..."
          :disabled="isLoading"
        ></textarea>
        <div class="agent-composer-footer">
          <div class="agent-composer-left">
            <span>Shift + Enter 换行</span>
            <button 
              type="button"
              class="agent-kb-selector-btn"
              @click="toggleKbSelector"
              :class="{ 'agent-kb-selector-btn-active': kbSelectorOpen }"
              :disabled="isLoading"
            >
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
              </svg>
              <span>知识库 ({{ selectedKbIds.length }})</span>
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" :d="kbSelectorOpen ? 'M5 15l7-7 7 7' : 'M19 9l-7 7-7-7'" />
              </svg>
            </button>
          </div>
          <button @click="sendMessage" :disabled="!query.trim() || isLoading">
            {{ isLoading ? '发送中...' : '发送' }}
          </button>
        </div>
      </div>
    </section>

    <!-- 知识库选择器弹窗 -->
    <div 
      v-if="kbSelectorOpen" 
      class="agent-selector-overlay"
      @click.self="closeKbSelector"
    >
      <div class="agent-selector-panel">
        <div class="agent-selector-header">
          <h3>选择知识库</h3>
          <button @click="closeKbSelector" class="ios-btn-icon">
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
        
        <div class="agent-selector-list">
          <div 
            v-for="kb in knowledgeBases" 
            :key="kb.kb_uuid"
            class="agent-kb-item"
            :class="{ 'agent-kb-item-selected': selectedKbIds.includes(kb.kb_uuid) }"
          >
            <label class="agent-kb-checkbox-label">
              <input 
                type="checkbox" 
                :value="kb.kb_uuid" 
                v-model="selectedKbIds" 
                class="ios-checkbox"
              />
              <span class="agent-kb-info">
                <strong>{{ kb.name }}</strong>
                <small>{{ kb.doc_count || 0 }} 个文档</small>
              </span>
            </label>
            <button
              type="button"
              class="agent-docs-toggle-btn"
              :class="{ 'agent-docs-toggle-btn-active': openDocKbId === kb.kb_uuid }"
              @click="toggleDocList(kb.kb_uuid)"
              :title="'选择 ' + kb.name + ' 下的文档'"
            >
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
            </button>
          </div>

          <!-- 文档选择悬浮层 -->
          <div 
            v-if="openDocKbId && currentDocList.length > 0"
            class="agent-docs-panel"
          >
            <div class="agent-docs-header">
              <span class="agent-docs-title">选择文档</span>
              <button 
                type="button"
                class="agent-link-text"
                @click="toggleAllDocsInKb(openDocKbId)"
              >
                {{ allDocsInKbSelected ? '取消全选' : '全选' }}
              </button>
            </div>
            <div class="agent-docs-list">
              <label 
                v-for="doc in currentDocList"
                :key="doc.doc_uuid"
                class="agent-doc-item"
                :class="{ 'agent-doc-item-selected': selectedDocIds.includes(doc.doc_uuid) }"
              >
                <input 
                  type="checkbox" 
                  :value="doc.doc_uuid" 
                  v-model="selectedDocIds"
                  class="ios-checkbox"
                />
                <span class="agent-doc-info">
                  <strong>{{ doc.title }}</strong>
                  <small>{{ doc.status }}</small>
                </span>
              </label>
            </div>
          </div>

          <div v-if="knowledgeBases.length === 0" class="agent-empty-state">
            <p>暂无知识库</p>
          </div>
        </div>
      </div>
    </div>

    <!-- 重命名弹出框 -->
    <Transition name="rename-popup">
      <div v-if="editingSessionId" class="agent-rename-overlay" @mousedown.self="cancelEditSession">
        <div class="agent-rename-popup">
          <div class="agent-rename-header">
            <span>重命名会话</span>
            <button @click="cancelEditSession" class="agent-rename-close">
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
          <input
            ref="renameInput"
            v-model="editingTitle"
            @keydown.enter.prevent="saveSessionTitle"
            @keydown.escape.prevent="cancelEditSession"
            class="agent-rename-input"
            placeholder="输入新标题..."
            maxlength="255"
          />
          <div class="agent-rename-actions">
            <button @click="cancelEditSession" class="agent-rename-cancel">取消</button>
            <button @click="saveSessionTitle" class="agent-rename-save" :disabled="!editingTitle.trim()">保存</button>
          </div>
        </div>
      </div>
    </Transition>
  </div>
</template>

<script setup>
import { ref, onMounted, nextTick, computed, watch } from 'vue'
import { useRouter } from 'vue-router'
import anime from 'animejs/lib/anime.es.js'

const router = useRouter()
const userInfo = JSON.parse(localStorage.getItem('userInfo') || 'null')
const userId = userInfo?.user_id || ''

const sessions = ref([])
const currentSessionId = ref(null)
const knowledgeBases = ref([])
const documents = ref([])
const selectedKbIds = ref([])
const selectedDocIds = ref([])
const messages = ref([])
const query = ref('')
const isLoading = ref(false)
const chatContainer = ref(null)
const agentView = ref(null)

// 知识库选择器状态
const kbSelectorOpen = ref(false)
const openDocKbId = ref(null)
const kbDocsMap = ref({})

// 重命名会话状态
const editingSessionId = ref(null)
const editingTitle = ref('')
const renameInput = ref(null)

const suggestions = [
  '这个系统的主要功能是什么？',
  '如何上传和管理文档？',
  '知识库如何工作？',
  '检索的准确率如何？'
]

// 计算当前知识库下的文档列表
const currentDocList = computed(() => {
  if (!openDocKbId.value) return []
  return kbDocsMap.value[openDocKbId.value] || []
})

// 计算当前知识库下是否全选
const allDocsInKbSelected = computed(() => {
  if (!openDocKbId.value || currentDocList.value.length === 0) return false
  return currentDocList.value.every(doc => selectedDocIds.value.includes(doc.doc_uuid))
})

const loadSessions = async () => {
  if (!userId) return

  try {
    const res = await fetch(`/api/v1/session/list?user_id=${userId}&status=1&limit=50`)
    if (!res.ok) return

    const data = await res.json()
    sessions.value = data.sessions || []

    if (sessions.value.length > 0 && !currentSessionId.value) {
      selectSession(sessions.value[0].session_id)
    }
  } catch (error) {
    console.error('加载会话失败:', error)
  }
}

const createNewSession = async () => {
  if (!userId) {
    alert('请先登录')
    router.push('/login')
    return
  }

  try {
    const res = await fetch('/api/v1/session/create', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        user_id: userId,
        title: `对话 ${new Date().toLocaleString('zh-CN')}`
      })
    })

    if (!res.ok) {
      alert('创建会话失败')
      return
    }

    const data = await res.json()
    await loadSessions()
    selectSession(data.session_id)
  } catch (error) {
    console.error('创建会话失败:', error)
    alert('创建会话失败')
  }
}

const selectSession = async (sessionId) => {
  // 添加点击动画效果
  const sessionElement = document.querySelector(`[data-session-id="${sessionId}"]`)
  if (sessionElement) {
    anime({
      targets: sessionElement,
      scale: [0.98, 1],
      duration: 200,
      easing: 'easeOutQuad'
    })
  }
  
  currentSessionId.value = sessionId
  await loadMessages(sessionId)
}

const loadMessages = async (sessionId) => {
  try {
    const res = await fetch(`/api/v1/session/message/list?session_id=${sessionId}&limit=100`)
    if (!res.ok) {
      messages.value = []
      return
    }

    const data = await res.json()
    // 按 created_at 升序排序，时间相同时按 role 排序（user 在前，assistant 在后）
    const roleOrder = { 'user': 0, 'assistant': 1, 'system': 2, 'tool': 3 }
    const sortedMessages = (data.messages || []).sort((a, b) => {
      const timeDiff = new Date(a.created_at) - new Date(b.created_at)
      if (timeDiff !== 0) return timeDiff
      // 时间相同时，user 排在 assistant 前面
      return (roleOrder[a.role] ?? 99) - (roleOrder[b.role] ?? 99)
    })
    
    messages.value = sortedMessages.map(msg => ({
      message_id: msg.message_id,
      role: msg.role,
      content: msg.content,
      created_at: msg.created_at
    }))

    await nextTick()
    scrollToBottom()
  } catch (error) {
    console.error('加载消息失败:', error)
    messages.value = []
  }
}

const formatTime = (timestamp) => {
  if (!timestamp) return ''

  const date = new Date(timestamp)
  const now = new Date()
  const diff = now - date

  if (diff < 24 * 60 * 60 * 1000) {
    return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
  }

  const yesterday = new Date(now)
  yesterday.setDate(yesterday.getDate() - 1)
  if (date.toDateString() === yesterday.toDateString()) return '昨天'

  return date.toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' })
}

const deleteSession = async (sessionId) => {
  if (!confirm('确定要删除这个会话吗？此操作不可恢复。')) {
    return
  }

  const wasCurrentSession = sessionId === currentSessionId.value

  try {
    const res = await fetch(`/api/v1/session/${sessionId}`, {
      method: 'DELETE'
    })

    if (!res.ok) {
      const error = await res.json()
      alert(`删除失败：${error.detail || '未知错误'}`)
      return
    }

    // 先刷新会话列表
    await loadSessions()
    
    // 如果删除的是当前会话，选择第一个会话（不创建新会话）
    if (wasCurrentSession) {
      if (sessions.value.length > 0) {
        // 有其他会话，选择第一个
        selectSession(sessions.value[0].session_id)
      } else {
        // 没有其他会话了，创建一个新的
        await createNewSession()
      }
    }
  } catch (error) {
    console.error('删除会话失败:', error)
    alert('删除会话失败，请稍后重试')
  }
}

const loadKnowledgeBases = async () => {
  if (!userId) return

  try {
    const res = await fetch(`/api/v1/knowledge-base?user_id=${userId}`)
    if (!res.ok) return

    const data = await res.json()
    knowledgeBases.value = data?.items || []
    
    // 为每个知识库加载文档列表
    for (const kb of knowledgeBases.value) {
      await loadKbDocuments(kb.kb_uuid)
    }
  } catch (error) {
    console.error('加载知识库失败:', error)
  }
}

const loadKbDocuments = async (kbUuid) => {
  try {
    const res = await fetch(`/api/v1/document?kb_id=${kbUuid}&user_id=${userId}`)
    if (!res.ok) return

    const data = await res.json()
    kbDocsMap.value[kbUuid] = data?.items || []
  } catch (error) {
    console.error('加载文档失败:', error)
    kbDocsMap.value[kbUuid] = []
  }
}

// 打开/关闭知识库选择器
const toggleKbSelector = () => {
  kbSelectorOpen.value = !kbSelectorOpen.value
  if (kbSelectorOpen.value) {
    openDocKbId.value = null
  }
}

const closeKbSelector = () => {
  kbSelectorOpen.value = false
  openDocKbId.value = null
  // 清除已取消勾选知识库对应的文档选择
  cleanOrphanedDocs()
}

// 清理孤儿文档（知识库未选中时清除其文档）
const cleanOrphanedDocs = () => {
  if (selectedDocIds.value.length === 0) return
  
  // 过滤掉不属于已选知识库的文档
  const validDocIds = new Set()
  for (const kbUuid of selectedKbIds.value) {
    const docs = kbDocsMap.value[kbUuid] || []
    for (const doc of docs) {
      validDocIds.add(doc.doc_uuid)
    }
  }
  
  selectedDocIds.value = selectedDocIds.value.filter(id => validDocIds.has(id))
}

// 切换文档列表显示
const toggleDocList = (kbUuid) => {
  openDocKbId.value = openDocKbId.value === kbUuid ? null : kbUuid
}

// 重命名会话
const startEditSession = (session) => {
  editingSessionId.value = session.session_id
  editingTitle.value = session.title
  nextTick(() => {
    renameInput.value?.focus()
    renameInput.value?.select()
  })
}

const cancelEditSession = () => {
  editingSessionId.value = null
  editingTitle.value = ''
}

const saveSessionTitle = async () => {
  if (!editingTitle.value.trim() || !editingSessionId.value) return

  try {
    const res = await fetch(`/api/v1/session/${editingSessionId.value}/title`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(editingTitle.value.trim())
    })

    if (!res.ok) {
      alert('重命名失败')
      return
    }

    // 更新本地列表
    const session = sessions.value.find(s => s.session_id === editingSessionId.value)
    if (session) {
      session.title = editingTitle.value.trim()
    }
    cancelEditSession()
  } catch (error) {
    console.error('重命名失败:', error)
    alert('重命名失败，请稍后重试')
  }
}

// 切换知识库内文档全选
const toggleAllDocsInKb = (kbUuid) => {
  const docs = kbDocsMap.value[kbUuid] || []
  if (allDocsInKbSelected.value) {
    // 取消全选：从已选文档中移除该知识库的所有文档
    selectedDocIds.value = selectedDocIds.value.filter(
      id => !docs.some(doc => doc.doc_uuid === id)
    )
  } else {
    // 全选：添加该知识库的所有文档
    const docIds = docs.map(doc => doc.doc_uuid)
    selectedDocIds.value = [...new Set([...selectedDocIds.value, ...docIds])]
  }
}

const fillQuery = (text) => {
  query.value = text
}

const sendMessage = async () => {
  if (!query.value.trim() || isLoading.value) return

  if (!currentSessionId.value) {
    alert('请先创建或选择一个会话')
    return
  }

  const userMessage = query.value.trim()
  query.value = ''
  messages.value.push({ role: 'user', content: userMessage })

  await nextTick()
  scrollToBottom()
  isLoading.value = true

  try {
    const res = await fetch('/api/v1/agent/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: currentSessionId.value,
        query: userMessage,
        knowledge_base_ids: selectedKbIds.value,
        document_ids: selectedDocIds.value,
        top_k: 10
      })
    })

    if (res.ok) {
      const data = await res.json()
      messages.value.push({
        role: 'assistant',
        content: data.answer || data.content || '没有收到有效回复',
        sources: data.sources || []
      })
    } else {
      const error = await res.json()
      messages.value.push({
        role: 'assistant',
        content: `请求失败：${error.detail || '未知错误'}`
      })
    }
  } catch (error) {
    console.error('发送消息失败:', error)
    messages.value.push({
      role: 'assistant',
      content: '网络异常，请稍后重试。'
    })
  } finally {
    isLoading.value = false
    await nextTick()
    scrollToBottom()
    
    // 刷新会话列表以更新消息计数
    await loadSessions()
  }
}

const scrollToBottom = () => {
  if (!chatContainer.value) return

  anime({
    targets: chatContainer.value,
    scrollTop: chatContainer.value.scrollHeight,
    duration: 360,
    easing: 'easeOutCubic'
  })
}

const animatePanelEntrance = () => {
  if (!agentView.value) return

  anime({
    targets: agentView.value.querySelectorAll('.ios-card'),
    opacity: [0, 1],
    translateY: [14, 0],
    delay: anime.stagger(45),
    duration: 420,
    easing: 'easeOutCubic'
  })
}

watch(() => messages.value.length, async () => {
  await nextTick()
  const rows = chatContainer.value?.querySelectorAll('.agent-message-row')
  const latest = rows?.[rows.length - 1]
  if (!latest) return

  anime({
    targets: latest,
    opacity: [0, 1],
    translateY: [10, 0],
    duration: 280,
    easing: 'easeOutCubic'
  })
})

// 监听知识库选择变化，自动清理未选中知识库对应的文档
watch(selectedKbIds, (newKbIds, oldKbIds) => {
  if (newKbIds.length < oldKbIds.length) {
    // 有知识库被取消勾选，清理对应的文档
    cleanOrphanedDocs()
  }
}, { deep: true })

onMounted(async () => {
  animatePanelEntrance()
  await Promise.all([loadSessions(), loadKnowledgeBases()])
})
</script>
