<template>
  <div ref="motionRoot" class="p-6 space-y-6 gradient-bg min-h-full ios-animate-fade-in">
    <!-- 页面标题 -->
    <div class="flex items-center justify-between">
      <h1 class="ios-page-title">知识库</h1>
      <button 
        @click="showCreateModal = true"
        class="py-2.5 px-5 ios-gradient-primary text-white rounded-xl font-semibold shadow-lg hover:shadow-xl active:scale-[0.98] transition-all duration-200 flex items-center gap-2"
      >
        <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M12 4v16m8-8H4"></path>
        </svg>
        新建知识库
      </button>
    </div>

    <!-- 知识库列表 -->
    <div v-if="loading" class="flex items-center justify-center py-20">
      <div class="ios-loading-dots">
        <div></div>
        <div></div>
        <div></div>
      </div>
    </div>

    <div v-else-if="knowledgeBases.length === 0" class="ios-card">
      <div class="ios-empty-state">
        <div class="ios-empty-state-icon">
          <svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"></path>
          </svg>
        </div>
        <p class="ios-empty-state-text">暂无知识库</p>
        <button 
          @click="showCreateModal = true"
          class="mt-4 btn-ios-primary"
        >
          创建第一个知识库
        </button>
      </div>
    </div>

    <div v-else class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
      <div 
        v-for="kb in knowledgeBases" 
        :key="kb.kb_uuid"
        class="ios-card-hover cursor-pointer group"
        @click="viewKnowledgeBase(kb)"
      >
        <div class="p-5">
          <!-- 知识库图标和标题 -->
          <div class="flex items-start gap-4 mb-4">
            <div class="w-14 h-14 ios-gradient-primary rounded-2xl flex items-center justify-center flex-shrink-0 shadow-lg">
              <svg class="w-7 h-7 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"></path>
              </svg>
            </div>
            <div class="flex-1 min-w-0">
              <h3 class="font-semibold text-[16px] text-[#1C1C1E] truncate">{{ kb.name }}</h3>
              <p class="text-[12px] text-[#8E8E93] mt-1">创建于 {{ formatTime(kb.created_at) }}</p>
            </div>
          </div>

          <!-- 统计信息 -->
          <div class="flex items-center gap-4 mb-4">
            <div class="flex items-center gap-1 text-[13px] text-[#8E8E93]">
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"></path>
              </svg>
              {{ kb.doc_count || 0 }} 文档
            </div>
            <div class="flex items-center gap-1 text-[13px] text-[#8E8E93]">
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 10h16M4 14h16M4 18h16"></path>
              </svg>
              {{ kb.chunk_count || 0 }} 切片
            </div>
          </div>

          <!-- 描述 -->
          <p v-if="kb.description" class="text-[13px] text-[#8E8E93] line-clamp-2 mb-4">
            {{ kb.description }}
          </p>

          <!-- 操作按钮 -->
          <div class="flex items-center gap-2 pt-3 border-t border-[#E5E5EA]/60 opacity-0 group-hover:opacity-100 transition-opacity">
            <button 
              @click.stop="editKnowledgeBase(kb)"
              class="flex-1 py-2 text-[13px] font-semibold text-[#007AFF] hover:bg-[#007AFF]/5 rounded-lg transition-colors"
            >
              编辑
            </button>
            <button 
              @click.stop="deleteKnowledgeBase(kb.kb_uuid)"
              class="flex-1 py-2 text-[13px] font-semibold text-[#FF3B30] hover:bg-[#FF3B30]/5 rounded-lg transition-colors"
            >
              删除
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- 创建/编辑模态框 -->
    <div v-if="showCreateModal" class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/15 backdrop-blur-md">
      <div class="ios-card w-full max-w-lg ios-animate-fade-in">
        <div class="p-5 border-b border-[#E5E5EA]/60 flex items-center justify-between">
          <h2 class="ios-card-title">{{ editingKb ? '编辑知识库' : '新建知识库' }}</h2>
          <button @click="showCreateModal = false" class="ios-btn-icon text-[#8E8E93] hover:text-[#1C1C1E]">
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
            </svg>
          </button>
        </div>

        <div class="p-5 space-y-4">
          <div>
            <label class="block text-[13px] font-semibold text-[#8E8E93] mb-2 uppercase tracking-wider">名称</label>
            <input
              v-model="formData.name"
              type="text"
              placeholder="请输入知识库名称"
              class="ios-input"
            />
          </div>

          <div>
            <label class="block text-[13px] font-semibold text-[#8E8E93] mb-2 uppercase tracking-wider">描述</label>
            <textarea
              v-model="formData.description"
              placeholder="请输入知识库描述（可选）"
              class="ios-input h-28 resize-none"
            ></textarea>
          </div>
        </div>

        <div class="p-5 border-t border-[#E5E5EA]/60 flex items-center justify-end gap-3">
          <button 
            @click="showCreateModal = false"
            class="py-2.5 px-5 btn-ios-secondary"
          >
            取消
          </button>
          <button 
            @click="saveKnowledgeBase"
            :disabled="!formData.name.trim()"
            class="py-2.5 px-5 btn-ios-primary disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {{ editingKb ? '保存' : '创建' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import anime from 'animejs/lib/anime.es.js'

const router = useRouter()
const motionRoot = ref(null)
const userInfo = JSON.parse(localStorage.getItem('userInfo') || 'null')
const userId = userInfo?.user_id || ''

const knowledgeBases = ref([])
const loading = ref(true)
const showCreateModal = ref(false)
const editingKb = ref(null)
const formData = ref({ name: '', description: '' })

// 加载知识库列表
const loadKnowledgeBases = async () => {
  loading.value = true
  try {
    const res = await fetch(`/api/v1/knowledge-base?user_id=${userId}`)
    if (res.ok) {
      const data = await res.json()
      knowledgeBases.value = data?.items || []
    }
  } catch (error) {
    console.error('加载知识库失败:', error)
  } finally {
    loading.value = false
  }
}

// 创建/编辑知识库
const saveKnowledgeBase = async () => {
  if (!formData.value.name.trim()) {
    alert('请输入知识库名称')
    return
  }

  try {
    const url = editingKb.value 
      ? `/api/v1/knowledge-base/${editingKb.value.kb_uuid}`
      : '/api/v1/knowledge-base'
    
    const method = editingKb.value ? 'PUT' : 'POST'
    
    const res = await fetch(url, {
      method,
      headers: { 
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${localStorage.getItem('token')}`
      },
      body: JSON.stringify({
        ...formData.value,
        user_id: userId
      })
    })

    if (res.ok) {
      showCreateModal.value = false
      formData.value = { name: '', description: '' }
      editingKb.value = null
      await loadKnowledgeBases()
    } else {
      alert('操作失败')
    }
  } catch (error) {
    console.error('操作失败:', error)
    alert('操作失败')
  }
}

// 删除知识库
const deleteKnowledgeBase = async (kbUuid) => {
  if (!confirm('确定要删除这个知识库吗？这将同时删除所有关联的文档。')) return

  try {
    const res = await fetch(`/api/v1/knowledge-base/${kbUuid}`, {
      method: 'DELETE',
      headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` }
    })

    if (res.ok) {
      await loadKnowledgeBases()
    } else {
      alert('删除失败')
    }
  } catch (error) {
    console.error('删除失败:', error)
    alert('删除失败')
  }
}

// 查看详情
const viewKnowledgeBase = (kb) => {
  // 跳转到知识库详情页，显示文档列表
  router.push(`/kb/${kb.kb_uuid}`)
}

// 编辑知识库
const editKnowledgeBase = (kb) => {
  editingKb.value = kb
  formData.value = { name: kb.name, description: kb.description || '' }
  showCreateModal.value = true
}

// 格式化时间
const formatTime = (timestamp) => {
  if (!timestamp) return ''
  const date = new Date(timestamp)
  return date.toLocaleDateString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit' })
}

onMounted(async () => {
  await loadKnowledgeBases()
  await nextTick()
  anime({
    targets: motionRoot.value?.querySelectorAll('.ios-card, .ios-card-hover, .group'),
    opacity: [0, 1],
    translateY: [20, 0],
    scale: [0.98, 1],
    delay: anime.stagger(60),
    duration: 620,
    easing: 'easeOutExpo'
  })
})
</script>
