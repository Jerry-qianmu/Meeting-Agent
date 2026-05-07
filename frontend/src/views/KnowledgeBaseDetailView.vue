<template>
  <div ref="motionRoot" class="p-6 space-y-6 gradient-bg min-h-full ios-animate-fade-in">
    <!-- 导航栏 -->
    <div class="flex items-center gap-4 mb-2">
      <button @click="goBack" class="ios-btn-icon text-[#007AFF]">
        <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7"></path>
        </svg>
      </button>
      <div class="flex-1">
        <h1 class="ios-page-title text-[24px]">{{ knowledgeBase?.name || '知识库' }}</h1>
        <p class="text-[13px] text-[#8E8E93] mt-1">文档列表</p>
      </div>
    </div>

    <div v-if="loading" class="flex items-center justify-center py-20">
      <div class="ios-loading-dots">
        <div></div>
        <div></div>
        <div></div>
      </div>
    </div>

    <div v-else-if="!knowledgeBase" class="ios-card">
      <div class="ios-empty-state">
        <div class="ios-empty-state-icon">
          <svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"></path>
          </svg>
        </div>
        <p class="ios-empty-state-text">知识库不存在</p>
        <button @click="goBack" class="mt-4 btn-ios-primary">返回</button>
      </div>
    </div>

    <div v-else class="space-y-6">
      <!-- 知识库信息卡片 -->
      <div class="ios-card p-6">
        <div class="flex items-start gap-5 mb-5">
          <div class="w-16 h-16 ios-gradient-primary rounded-2xl flex items-center justify-center flex-shrink-0 shadow-lg">
            <svg class="w-8 h-8 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"></path>
            </svg>
          </div>
          <div class="flex-1">
            <h2 class="text-[20px] font-bold text-[#1C1C1E]">{{ knowledgeBase.name }}</h2>
            <p v-if="knowledgeBase.description" class="text-[14px] text-[#8E8E93] mt-2">{{ knowledgeBase.description }}</p>
          </div>
        </div>

        <!-- 统计信息 -->
        <div class="grid grid-cols-3 gap-4 p-4 bg-[#F2F2F7]/60 rounded-xl">
          <div class="text-center">
            <p class="text-[24px] font-bold text-[#007AFF]">{{ knowledgeBase.doc_count || 0 }}</p>
            <p class="text-[12px] text-[#8E8E93] mt-1">文档数</p>
          </div>
          <div class="text-center border-x border-[#E5E5EA]/60">
            <p class="text-[24px] font-bold text-[#34C759]">{{ knowledgeBase.chunk_count || 0 }}</p>
            <p class="text-[12px] text-[#8E8E93] mt-1">切片数</p>
          </div>
          <div class="text-center">
            <p class="text-[24px] font-bold text-[#AF52DE]">{{ formatTime(knowledgeBase.updated_at) }}</p>
            <p class="text-[12px] text-[#8E8E93] mt-1">更新时间</p>
          </div>
        </div>
      </div>

      <!-- 文档列表 -->
      <div class="ios-card overflow-hidden">
        <div class="p-4 border-b border-[#E5E5EA]/60 flex items-center justify-between">
          <h3 class="ios-card-title">文档列表</h3>
          <button 
            @click="showUploadModal = true"
            class="py-1.5 px-3 text-[13px] font-semibold text-[#007AFF] hover:bg-[#007AFF]/5 rounded-lg transition-colors"
          >
            上传文档
          </button>
        </div>

        <div v-if="documents.length === 0" class="ios-empty-state py-10">
          <div class="ios-empty-state-icon">
            <svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"></path>
            </svg>
          </div>
          <p class="ios-empty-state-text">暂无文档</p>
          <button @click="showUploadModal = true" class="mt-4 btn-ios-secondary">上传第一个文档</button>
        </div>

        <div v-else class="divide-y divide-[#E5E5EA]/60">
          <div 
            v-for="doc in documents" 
            :key="doc.doc_uuid"
            class="ios-list-item-hover group"
          >
            <div class="flex items-start gap-4 p-4">
              <div :class="['w-11 h-11 rounded-xl flex items-center justify-center flex-shrink-0', getFileIconColor(doc.file_type)]">
                <svg class="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"></path>
                </svg>
              </div>

              <div class="flex-1 min-w-0">
                <div class="flex items-start justify-between gap-4">
                  <div class="flex-1 min-w-0">
                    <h4 class="font-semibold text-[14px] text-[#1C1C1E] truncate">{{ doc.title }}</h4>
                    <p class="text-[11px] text-[#8E8E93] mt-1">{{ formatTime(doc.created_at) }}</p>
                  </div>
                  <span :class="['ios-badge', getStatusBadge(doc.status)]">{{ doc.status }}</span>
                </div>
                
                <div class="flex items-center gap-4 mt-2.5">
                  <span class="text-[11px] text-[#8E8E93]" v-if="doc.word_count">
                    {{ doc.word_count }} 字
                  </span>
                </div>
              </div>

              <div class="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                <button @click="deleteDocument(doc.doc_uuid)" class="ios-btn-icon text-[#8E8E93] hover:text-[#FF3B30]" title="删除文档">
                  <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
                  </svg>
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 上传模态框 -->
    <div v-if="showUploadModal" class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/15 backdrop-blur-md">
      <div class="ios-card w-full max-w-xl ios-animate-fade-in">
        <div class="p-5 border-b border-[#E5E5EA]/60 flex items-center justify-between">
          <h2 class="ios-card-title">上传文档</h2>
          <button @click="showUploadModal = false" class="ios-btn-icon text-[#8E8E93] hover:text-[#1C1C1E]">
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
            </svg>
          </button>
        </div>

        <div class="p-5">
          <div 
            @dragover.prevent="dragOver = true"
            @dragleave="dragOver = false"
            @drop.prevent="handleDrop($event)"
            :class="['border-2 border-dashed rounded-xl p-6 text-center transition-all duration-200 cursor-pointer', dragOver ? 'border-[#007AFF] bg-[#007AFF]/5' : 'border-[#E5E5EA] hover:border-[#C7C7CC]']"
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
            <svg class="w-10 h-10 mx-auto text-[#8E8E93] mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"></path>
            </svg>
            <p class="text-[14px] text-[#1C1C1E] font-medium">点击或拖拽文件到此处</p>
            <p class="text-[11px] text-[#8E8E93] mt-1">支持 PDF、TXT、MD 格式</p>
          </div>

          <div v-if="uploadQueue.length > 0" class="mt-4 space-y-2">
            <div v-for="(file, index) in uploadQueue" :key="index" class="ios-card p-3">
              <div class="flex items-center gap-3">
                <div class="w-9 h-9 rounded-lg bg-[#007AFF]/10 flex items-center justify-center flex-shrink-0">
                  <svg class="w-4 h-4 text-[#007AFF]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"></path>
                  </svg>
                </div>
                <div class="flex-1 min-w-0">
                  <p class="font-medium text-[13px] text-[#1C1C1E] truncate">{{ file.name }}</p>
                  <div class="flex items-center gap-2 mt-1">
                    <div class="flex-1 h-1.5 bg-[#E5E5EA] rounded-full overflow-hidden">
                      <div 
                        :class="['h-full rounded-full transition-all duration-300', file.status === 'completed' ? 'bg-[#34C759]' : file.status === 'error' ? 'bg-[#FF3B30]' : 'bg-[#007AFF]']"
                        :style="{ width: file.progress + '%' }"
                      ></div>
                    </div>
                    <span class="text-[10px] text-[#8E8E93] min-w-[50px] text-right">
                      {{ file.status === 'completed' ? '完成' : file.status === 'error' ? '失败' : file.progress + '%' }}
                    </span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div class="p-5 border-t border-[#E5E5EA]/60 flex items-center justify-end gap-3">
          <button @click="showUploadModal = false" class="py-2.5 px-5 btn-ios-secondary">关闭</button>
          <button @click="uploadFiles" :disabled="uploadQueue.length === 0" class="py-2.5 px-5 btn-ios-primary disabled:opacity-50">开始上传</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, nextTick } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import anime from 'animejs/lib/anime.es.js'

const router = useRouter()
const route = useRoute()
const motionRoot = ref(null)
const kbUuid = route.params.id  // 路由定义是 /kb/:id，所以用 params.id

const knowledgeBase = ref(null)
const documents = ref([])
const loading = ref(true)
const showUploadModal = ref(false)
const dragOver = ref(false)
const fileInput = ref(null)
const uploadQueue = ref([])

const loadKnowledgeBase = async () => {
  loading.value = true
  try {
    console.log('加载知识库详情，kbUuid:', kbUuid)
    const res = await fetch(`/api/v1/knowledge-base/${kbUuid}`)
    if (res.ok) {
      const data = await res.json()
      console.log('知识库详情:', data)
      knowledgeBase.value = data
    } else {
      console.error('加载知识库失败，状态:', res.status)
    }
  } catch (error) {
    console.error('加载知识库失败:', error)
  } finally {
    loading.value = false
  }
}

const loadDocuments = async () => {
  try {
    const userInfo = JSON.parse(localStorage.getItem('userInfo') || 'null')
    const userId = userInfo?.user_id || ''
    // 使用 kb_id 参数，后端 API 期望的是 kb_id
    const res = await fetch(`/api/v1/document?kb_id=${kbUuid}&user_id=${userId}`)
    if (res.ok) {
      const data = await res.json()
      documents.value = data?.items || []
      console.log('文档加载成功:', documents.value.length, '个文档')
    } else {
      console.error('加载文档失败，状态:', res.status)
    }
  } catch (error) {
    console.error('加载文档失败:', error)
  }
}

const triggerFileInput = () => fileInput.value?.click()
const handleFileSelect = (e) => addFiles(e.target.files)
const handleDrop = (e) => { dragOver.value = false; addFiles(e.dataTransfer.files) }

const addFiles = (files) => {
  Array.from(files).forEach(file => {
    if (!['.pdf', '.txt', '.md'].some(ext => file.name.toLowerCase().endsWith(ext))) {
      alert(`不支持的格式：${file.name}`)
      return
    }
    uploadQueue.value.push({ file, name: file.name, progress: 0, status: 'pending' })
  })
}

const uploadFiles = async () => {
  for (let item of uploadQueue.value) {
    if (item.status === 'completed') continue
    item.status = 'uploading'
    
    const formData = new FormData()
    formData.append('file', item.file)
    formData.append('kb_id', kbUuid)  // 后端期望 kb_id 而不是 kb_uuid
    formData.append('user_id', JSON.parse(localStorage.getItem('userInfo') || 'null')?.user_id || '')

    try {
      const res = await fetch('/api/v1/document/upload', {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` },
        body: formData
      })
      item.status = res.ok ? 'completed' : 'error'
      item.progress = 100
      if (res.ok) await loadDocuments()
    } catch {
      item.status = 'error'
    }
  }
}

const deleteDocument = async (docUuid) => {
  if (!confirm('确定要删除这个文档吗？')) return
  try {
    const res = await fetch(`/api/v1/document/${docUuid}`, {
      method: 'DELETE',
      headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` }
    })
    if (res.ok) await loadDocuments()
    else alert('删除失败')
  } catch {
    alert('删除失败')
  }
}

const goBack = () => router.push('/knowledge-bases')

const formatTime = (timestamp) => {
  if (!timestamp) return ''
  const date = new Date(timestamp)
  return date.toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' })
}

const getStatusBadge = (status) => {
  const map = { 'completed': 'ios-badge-success', 'processing': 'ios-badge-info', 'pending': 'ios-badge-warning', 'failed': 'ios-badge-danger' }
  return map[status] || 'ios-badge-gray'
}

const getFileIconColor = (type) => {
  const map = { 'pdf': 'ios-gradient-warm', 'txt': 'ios-gradient-primary', 'md': 'ios-gradient-cool' }
  return map[type] || 'bg-[#C7C7CC]'
}

onMounted(async () => {
  await Promise.all([loadKnowledgeBase(), loadDocuments()])
  await nextTick()
  anime({
    targets: motionRoot.value?.querySelectorAll('.ios-card, .ios-list-item-clickable, .group'),
    opacity: [0, 1],
    translateY: [18, 0],
    scale: [0.985, 1],
    delay: anime.stagger(55),
    duration: 580,
    easing: 'easeOutExpo'
  })
})
</script>
