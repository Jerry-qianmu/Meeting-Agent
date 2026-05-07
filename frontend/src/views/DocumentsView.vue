<template>
  <div ref="motionRoot" class="p-6 space-y-6 gradient-bg min-h-full ios-animate-fade-in">
    <!-- 页面标题 -->
    <div class="flex items-center justify-between">
      <h1 class="ios-page-title">文档管理</h1>
      <button 
        @click="showUploadModal = true"
        class="py-2.5 px-5 ios-gradient-primary text-white rounded-xl font-semibold shadow-lg hover:shadow-xl active:scale-[0.98] transition-all duration-200 flex items-center gap-2"
      >
        <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12"></path>
        </svg>
        上传文档
      </button>
    </div>

    <!-- 搜索和筛选 -->
    <div class="ios-card p-4">
      <div class="flex items-center gap-4">
        <div class="flex-1 relative">
          <svg class="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-[#8E8E93]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"></path>
          </svg>
          <input
            v-model="searchQuery"
            @input="filterDocuments"
            type="text"
            placeholder="搜索文档..."
            class="ios-input-search w-full"
          />
        </div>
        <select v-model="statusFilter" @change="filterDocuments" class="ios-select w-40">
          <option value="">全部状态</option>
          <option value="completed">已完成</option>
          <option value="processing">处理中</option>
          <option value="pending">待处理</option>
          <option value="failed">失败</option>
        </select>
      </div>
    </div>

    <!-- 文档列表 -->
    <div class="ios-card overflow-hidden">
      <div v-if="loading" class="p-12 text-center">
        <div class="ios-loading-dots mx-auto">
          <div></div>
          <div></div>
          <div></div>
        </div>
        <p class="mt-4 text-[#8E8E93] text-[14px]">加载中...</p>
      </div>

      <div v-else-if="filteredDocuments.length === 0" class="ios-empty-state">
        <div class="ios-empty-state-icon">
          <svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"></path>
          </svg>
        </div>
        <p class="ios-empty-state-text">暂无文档</p>
        <button 
          @click="showUploadModal = true"
          class="mt-4 btn-ios-primary"
        >
          上传第一个文档
        </button>
      </div>

      <div v-else class="divide-y divide-[#E5E5EA]/60">
        <div 
          v-for="doc in filteredDocuments" 
          :key="doc.doc_uuid"
          class="ios-list-item-hover group"
        >
          <div class="flex items-start gap-4 p-4">
            <!-- 文档图标 -->
            <div :class="['w-12 h-12 rounded-xl flex items-center justify-center flex-shrink-0', getFileIconColor(doc.file_type)]">
              <svg class="w-6 h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"></path>
              </svg>
            </div>

            <!-- 文档信息 -->
            <div class="flex-1 min-w-0">
              <div class="flex items-start justify-between gap-4">
                <div class="flex-1 min-w-0">
                  <h3 class="font-semibold text-[15px] text-[#1C1C1E] truncate">{{ doc.title }}</h3>
                  <p class="text-[12px] text-[#8E8E93] mt-1">
                    {{ doc.file_size ? formatFileSize(doc.file_size) : '未知大小' }} · {{ formatTime(doc.created_at) }}
                  </p>
                </div>
                <span :class="['ios-badge', getStatusBadge(doc.status)]">
                  {{ doc.status }}
                </span>
              </div>
              
              <div class="flex items-center gap-4 mt-3">
                <div class="flex items-center gap-2 text-[12px] text-[#8E8E93]">
                  <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 10h16M4 14h16M4 18h16"></path>
                  </svg>
                  {{ doc.chunk_count || 0 }} 切片
                </div>
                <div class="flex items-center gap-2 text-[12px] text-[#8E8E93]" v-if="doc.word_count">
                  <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 5h12M9 3v2m6.366 1.366a2 2 0 012.828 2.828l-5.657 5.657a2 2 0 01-2.828 0L6 10.366"></path>
                  </svg>
                  {{ doc.word_count }} 字
                </div>
              </div>
            </div>

            <!-- 操作按钮 -->
            <div class="flex items-center gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
              <button 
                @click="viewDocument(doc)"
                class="ios-btn-icon text-[#8E8E93] hover:text-[#007AFF]"
                title="查看详情"
              >
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"></path>
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"></path>
                </svg>
              </button>
              <button 
                @click="downloadDocument(doc)"
                class="ios-btn-icon text-[#8E8E93] hover:text-[#34C759]"
                title="下载"
              >
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"></path>
                </svg>
              </button>
              <button 
                @click="deleteDocument(doc.doc_uuid)"
                class="ios-btn-icon text-[#8E8E93] hover:text-[#FF3B30]"
                title="删除"
              >
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path>
                </svg>
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 上传模态框 -->
    <div v-if="showUploadModal" class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/15 backdrop-blur-md">
      <div class="ios-card w-full max-w-2xl max-h-[80vh] overflow-hidden ios-animate-fade-in">
        <div class="p-5 border-b border-[#E5E5EA]/60 flex items-center justify-between">
          <h2 class="ios-card-title">上传文档</h2>
          <button @click="showUploadModal = false" class="ios-btn-icon text-[#8E8E93] hover:text-[#1C1C1E]">
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
            </svg>
          </button>
        </div>
        
        <div class="p-5 overflow-y-auto max-h-[calc(80vh-140px)]">
          <!-- 拖拽上传区域 -->
          <div 
            @dragover.prevent="dragOver = true"
            @dragleave="dragOver = false"
            @drop.prevent="handleDrop($event)"
            :class="['border-2 border-dashed rounded-xl p-8 text-center transition-all duration-200 cursor-pointer', dragOver ? 'border-[#007AFF] bg-[#007AFF]/5' : 'border-[#E5E5EA] hover:border-[#C7C7CC]']"
            @click="triggerFileInput"
          >
            <input 
              ref="fileInput"
              type="file" 
              multiple 
              accept=".pdf,.txt,.md"
              @change="handleFileSelect"
              class="hidden"
            />
            <svg class="w-12 h-12 mx-auto text-[#8E8E93] mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"></path>
            </svg>
            <p class="text-[15px] text-[#1C1C1E] font-medium">点击或拖拽文件到此处</p>
            <p class="text-[12px] text-[#8E8E93] mt-1.5">支持 PDF、TXT、MD 格式</p>
          </div>

          <!-- 文件列表 -->
          <div v-if="uploadQueue.length > 0" class="mt-5 space-y-2">
            <p class="ios-section-title mb-2">上传队列</p>
            <div v-for="(file, index) in uploadQueue" :key="index" class="ios-card p-3">
              <div class="flex items-center gap-3">
                <div class="w-10 h-10 rounded-lg bg-[#007AFF]/10 flex items-center justify-center flex-shrink-0">
                  <svg class="w-5 h-5 text-[#007AFF]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"></path>
                  </svg>
                </div>
                <div class="flex-1 min-w-0">
                  <p class="font-medium text-[14px] text-[#1C1C1E] truncate">{{ file.name }}</p>
                  <div class="flex items-center gap-3 mt-1">
                    <div class="flex-1 h-1.5 bg-[#E5E5EA] rounded-full overflow-hidden">
                      <div 
                        :class="['h-full rounded-full transition-all duration-300', file.status === 'completed' ? 'bg-[#34C759]' : file.status === 'error' ? 'bg-[#FF3B30]' : 'bg-[#007AFF]']"
                        :style="{ width: file.progress + '%' }"
                      ></div>
                    </div>
                    <span class="text-[11px] text-[#8E8E93] min-w-[60px] text-right">
                      {{ file.status === 'completed' ? '完成' : file.status === 'error' ? '失败' : file.progress + '%' }}
                    </span>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- 知识库选择 -->
          <div v-if="knowledgeBases.length > 0" class="mt-5">
            <p class="ios-section-title mb-2">选择知识库</p>
            <div class="space-y-2">
              <label 
                v-for="kb in knowledgeBases" 
                :key="kb.kb_uuid"
                class="ios-card-hover p-3 cursor-pointer flex items-center gap-3"
                :class="{ 'ios-card-selected': selectedKbUuid === kb.kb_uuid }"
              >
                <input
                  type="radio"
                  :value="kb.kb_uuid"
                  v-model="selectedKbUuid"
                  class="ios-checkbox rounded-full"
                />
                <div class="flex-1">
                  <p class="font-semibold text-[14px] text-[#1C1C1E]">{{ kb.name }}</p>
                  <p class="text-[11px] text-[#8E8E93]">{{ kb.doc_count || 0 }} 个文档</p>
                </div>
              </label>
            </div>
          </div>
        </div>

        <div class="p-5 border-t border-[#E5E5EA]/60 flex items-center justify-end gap-3">
          <button 
            @click="showUploadModal = false"
            class="py-2.5 px-5 btn-ios-secondary"
          >
            取消
          </button>
          <button 
            @click="uploadFiles"
            :disabled="!selectedKbUuid || uploadQueue.length === 0"
            class="py-2.5 px-5 btn-ios-primary disabled:opacity-50 disabled:cursor-not-allowed"
          >
            开始上传
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, computed, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import anime from 'animejs/lib/anime.es.js'

const router = useRouter()
const motionRoot = ref(null)
const userInfo = JSON.parse(localStorage.getItem('userInfo') || 'null')
const userId = userInfo?.user_id || ''

const documents = ref([])
const filteredDocuments = ref([])
const knowledgeBases = ref([])
const loading = ref(true)
const searchQuery = ref('')
const statusFilter = ref('')
const showUploadModal = ref(false)
const dragOver = ref(false)
const fileInput = ref(null)
const uploadQueue = ref([])
const selectedKbUuid = ref('')

// 加载文档列表
const loadDocuments = async () => {
  loading.value = true
  try {
    const res = await fetch(`/api/v1/document?user_id=${userId}`)
    if (res.ok) {
      const data = await res.json()
      documents.value = data?.items || []
      filteredDocuments.value = documents.value
    }
  } catch (error) {
    console.error('加载文档失败:', error)
  } finally {
    loading.value = false
  }
}

// 加载知识库列表
const loadKnowledgeBases = async () => {
  try {
    const res = await fetch(`/api/v1/knowledge-base?user_id=${userId}`)
    if (res.ok) {
      const data = await res.json()
      knowledgeBases.value = data?.items || []
      if (knowledgeBases.value.length > 0) {
        selectedKbUuid.value = knowledgeBases.value[0].kb_uuid
      }
    }
  } catch (error) {
    console.error('加载知识库失败:', error)
  }
}

// 过滤文档
const filterDocuments = () => {
  filteredDocuments.value = documents.value.filter(doc => {
    const matchSearch = !searchQuery.value || 
      doc.title.toLowerCase().includes(searchQuery.value.toLowerCase())
    const matchStatus = !statusFilter.value || doc.status === statusFilter.value
    return matchSearch && matchStatus
  })
}

// 文件操作
const triggerFileInput = () => fileInput.value?.click()
const handleFileSelect = (e) => addFiles(e.target.files)
const handleDrop = (e) => {
  dragOver.value = false
  addFiles(e.dataTransfer.files)
}

const addFiles = (files) => {
  Array.from(files).forEach(file => {
    if (!['.pdf', '.txt', '.md'].some(ext => file.name.toLowerCase().endsWith(ext))) {
      alert(`不支持的格式：${file.name}`)
      return
    }
    uploadQueue.value.push({
      file,
      name: file.name,
      progress: 0,
      status: 'pending'
    })
  })
}

// 上传文件
const uploadFiles = async () => {
  if (!selectedKbUuid.value) {
    alert('请选择知识库')
    return
  }

  for (let i = 0; i < uploadQueue.value.length; i++) {
    const item = uploadQueue.value[i]
    if (item.status === 'completed') continue

    item.status = 'uploading'
    item.progress = 0

    const formData = new FormData()
    formData.append('file', item.file)
    formData.append('kb_uuid', selectedKbUuid.value)

    try {
      const res = await fetch('/api/v1/document/upload', {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` },
        body: formData
      })

      if (res.ok) {
        item.status = 'completed'
        item.progress = 100
        await loadDocuments()
      } else {
        item.status = 'error'
      }
    } catch (error) {
      item.status = 'error'
    }
  }
}

// 删除文档
const deleteDocument = async (docUuid) => {
  if (!confirm('确定要删除这个文档吗？')) return

  try {
    const res = await fetch(`/api/v1/document/${docUuid}`, {
      method: 'DELETE',
      headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` }
    })

    if (res.ok) {
      await loadDocuments()
    } else {
      alert('删除失败')
    }
  } catch (error) {
    console.error('删除失败:', error)
    alert('删除失败')
  }
}

// 查看详情
const viewDocument = (doc) => {
  // TODO: 实现详情页跳转
  console.log('查看文档:', doc)
}

// 下载文档
const downloadDocument = async (doc) => {
  try {
    const res = await fetch(`/api/v1/document/${doc.doc_uuid}/download`, {
      headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` }
    })

    if (res.ok) {
      const blob = await res.blob()
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = doc.title
      a.click()
      window.URL.revokeObjectURL(url)
    }
  } catch (error) {
    console.error('下载失败:', error)
  }
}

// 工具函数
const formatFileSize = (bytes) => {
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
}

const formatTime = (timestamp) => {
  if (!timestamp) return ''
  const date = new Date(timestamp)
  return date.toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

const getStatusBadge = (status) => {
  const map = {
    'completed': 'ios-badge-success',
    'processing': 'ios-badge-info',
    'pending': 'ios-badge-warning',
    'failed': 'ios-badge-danger'
  }
  return map[status] || 'ios-badge-gray'
}

const getFileIconColor = (type) => {
  const map = {
    'pdf': 'ios-gradient-warm',
    'txt': 'ios-gradient-primary',
    'md': 'ios-gradient-cool'
  }
  return map[type] || 'bg-[#C7C7CC]'
}

onMounted(async () => {
  await Promise.all([loadDocuments(), loadKnowledgeBases()])
  await nextTick()
  anime({
    targets: motionRoot.value?.querySelectorAll('.ios-card, .ios-list-item-clickable, .group'),
    opacity: [0, 1],
    translateY: [18, 0],
    scale: [0.985, 1],
    delay: anime.stagger(55),
    duration: 560,
    easing: 'easeOutExpo'
  })
})
</script>
