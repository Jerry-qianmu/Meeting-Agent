import { ref, computed } from 'vue'
import { authApi } from '@/api/auth'

// 认证状态
const user = ref(null)
const token = ref(localStorage.getItem('token') || null)
const userInfo = ref(JSON.parse(localStorage.getItem('userInfo') || 'null'))

// 是否正在加载
const loading = ref(false)

// 错误信息
const error = ref('')

// 注册成功消息
const registerMessage = ref('')

// 设置 token
const setToken = (newToken) => {
  token.value = newToken
  if (newToken) {
    localStorage.setItem('token', newToken)
  } else {
    localStorage.removeItem('token')
  }
}

// 设置用户信息
const setUserInfo = (newUserInfo) => {
  userInfo.value = newUserInfo
  if (newUserInfo) {
    localStorage.setItem('userInfo', JSON.stringify(newUserInfo))
  } else {
    localStorage.removeItem('userInfo')
  }
}

// 用户注册（不自动登录）
const register = async (username, password, email = '', displayName = '') => {
  loading.value = true
  error.value = ''
  registerMessage.value = ''
  
  try {
    const response = await authApi.register({
      username,
      password,
      email: email || null,
      display_name: displayName || username
    })
    
    if (response.data.success) {
      // 注册成功，但不自动登录
      registerMessage.value = '注册成功！请使用刚注册的账号登录。'
      // 清空密码字段
      return { success: true, message: registerMessage.value }
    } else {
      error.value = response.data.error || '注册失败'
      return { success: false, error: error.value }
    }
  } catch (err) {
    error.value = err.response?.data?.detail || err.response?.data?.error || '注册失败，请检查网络连接'
    return { success: false, error: error.value }
  } finally {
    loading.value = false
  }
}

// 用户登录
const login = async (username, password) => {
  loading.value = true
  error.value = ''
  registerMessage.value = ''
  
  try {
    const response = await authApi.login({
      username,
      password
    })
    
    if (response.data.success) {
      setToken(response.data.token)
      setUserInfo({
        user_id: response.data.user_id,
        username: response.data.username,
        display_name: response.data.display_name,
        email: response.data.email
      })
      user.value = userInfo.value
      return { success: true }
    } else {
      error.value = response.data.error || '登录失败'
      return { success: false, error: error.value }
    }
  } catch (err) {
    error.value = err.response?.data?.detail || err.response?.data?.error || '登录失败，请检查网络连接'
    return { success: false, error: error.value }
  } finally {
    loading.value = false
  }
}

// 用户登出
const logout = () => {
  setToken(null)
  setUserInfo(null)
  user.value = null
}

// 获取当前用户信息
const fetchUserInfo = async () => {
  if (!token.value) return null
  
  try {
    const response = await authApi.getMe()
    
    if (response.data.success) {
      setUserInfo({
        user_id: response.data.user_id,
        username: response.data.username,
        display_name: response.data.display_name,
        email: response.data.email,
        avatar_url: response.data.avatar_url,
        status: response.data.status,
        created_at: response.data.created_at
      })
      user.value = userInfo.value
      return { success: true }
    } else {
      // token 无效，清除登录状态
      logout()
      return { success: false, error: '登录已过期，请重新登录' }
    }
  } catch (err) {
    // token 无效，清除登录状态
    logout()
    return { success: false, error: '登录已过期，请重新登录' }
  }
}

// 验证 token 是否有效
const verifyToken = async () => {
  if (!token.value) return false
  
  try {
    const response = await authApi.verify()
    return response.data.valid
  } catch {
    return false
  }
}

// 初始化认证状态（从 localStorage 恢复）
const initAuth = async () => {
  if (token.value && !userInfo.value) {
    // token 存在但没有用户信息，尝试获取
    await fetchUserInfo()
  }
}

// 清空注册成功消息
const clearRegisterMessage = () => {
  registerMessage.value = ''
}

export function useAuth() {
  return {
    // 状态
    user,
    token,
    loading,
    error,
    registerMessage,
    
    // 计算属性
    isAuthenticated: computed(() => !!token.value),
    
    // 方法
    register,
    login,
    logout,
    fetchUserInfo,
    verifyToken,
    initAuth,
    clearRegisterMessage,
    
    // 清除错误
    clearError: () => {
      error.value = ''
    }
  }
}
