import axios from 'axios'

const API_BASE = '/api/v1'

const api = axios.create({
  baseURL: API_BASE,
  timeout: 120000,  // 延长到 120 秒（Agent 对话可能较长）
  headers: {
    'Content-Type': 'application/json'
  }
})

// 知识库 API
export const knowledgeBaseApi = {
  // 获取知识库列表
  list: (userId) => api.get('/knowledge-base', { params: { user_id: userId } }),
  
  // 获取知识库详情
  get: (id) => api.get(`/knowledge-base/${id}`),
  
  // 创建知识库
  create: (data, userId) => api.post('/knowledge-base', { ...data, user_id: userId }),
  
  // 更新知识库
  update: (id, data) => api.put(`/knowledge-base/${id}`, data),
  
  // 删除知识库
  delete: (id) => api.delete(`/knowledge-base/${id}`),
  
  // 获取知识库统计
  getStats: (id) => api.get(`/knowledge-base/${id}/stats`)
}

// 文档 API
export const documentApi = {
  // 获取文档列表
  list: (params, userId) => api.get('/document', { params: { ...params, user_id: userId } }),
  
  // 获取文档详情
  get: (id) => api.get(`/document/${id}`),
  
  // 获取知识库的文档列表
  getByKb: (kbId, params, userId) => api.get(`/document/kb/${kbId}`, { params: { ...params, user_id: userId } }),
  
  // 获取文档处理状态
  getStatus: (id) => api.get(`/document/${id}/status`),
  
  // 获取文档的切片列表
  getChunks: (docId) => api.get(`/document/${docId}/chunks`),
  
  // 获取文档的切片列表（含向量数据）
  getChunksWithVectors: (docId) => api.get(`/document/${docId}/chunks-with-vectors`),
  
  // 上传文档
  upload: (kbId, file, title = null, userId = null) => {
    const formData = new FormData()
    formData.append('kb_id', kbId)
    formData.append('file', file)
    if (title) formData.append('title', title)
    if (userId) formData.append('user_id', userId)
    return api.post('/document/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    })
  },
  
  // 删除文档
  delete: (id) => api.delete(`/document/${id}`),
  
  // 重试处理
  retry: (id) => api.post(`/document/${id}/retry`)
}

// Agent API
export const agentApi = {
  // 与 Agent 对话
  chat: (data) => api.post('/agent/chat', data),
  
  // 检查 Agent 状态
  getStatus: () => api.get('/agent/status')
}

export default api
