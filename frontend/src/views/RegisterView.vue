<template>
  <div ref="authView" class="min-h-screen flex items-center justify-center p-4 gradient-bg">
    <div class="w-full max-w-md ios-card ios-animate-fade-in">
      <!-- Logo 和标题 -->
      <div class="p-8 pb-6 text-center">
        <div class="w-16 h-16 ios-gradient-primary rounded-2xl mx-auto flex items-center justify-center shadow-lg mb-5">
          <svg class="w-9 h-9 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M18 9v3m0 0v3m0-3h3m-3 0h-3m-2-5a4 4 0 11-8 0 4 4 0 018 0zM3 20a6 6 0 0112 0v1H3v-1z"></path>
          </svg>
        </div>
        <h1 class="text-[28px] font-bold text-[#1C1C1E]">创建账户</h1>
        <p class="text-[14px] text-[#8E8E93] mt-2">加入我们的知识库管理系统</p>
      </div>

      <!-- 注册表单 -->
      <div class="px-8 pb-8">
        <form @submit.prevent="handleRegister" class="space-y-5">
          <!-- 用户名 -->
          <div>
            <label class="block text-[12px] font-semibold text-[#8E8E93] mb-2 uppercase tracking-wider">用户名</label>
            <div class="relative">
              <svg class="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-[#8E8E93]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"></path>
              </svg>
              <input
                v-model="formData.username"
                type="text"
                placeholder="请输入用户名"
                class="ios-input pl-11"
                required
                minlength="3"
                maxlength="20"
              />
            </div>
          </div>

          <!-- 邮箱 -->
          <div>
            <label class="block text-[12px] font-semibold text-[#8E8E93] mb-2 uppercase tracking-wider">邮箱</label>
            <div class="relative">
              <svg class="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-[#8E8E93]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"></path>
              </svg>
              <input
                v-model="formData.email"
                type="email"
                placeholder="请输入邮箱"
                class="ios-input pl-11"
                required
              />
            </div>
          </div>

          <!-- 密码 -->
          <div>
            <label class="block text-[12px] font-semibold text-[#8E8E93] mb-2 uppercase tracking-wider">密码</label>
            <div class="relative">
              <svg class="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-[#8E8E93]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"></path>
              </svg>
              <input
                v-model="formData.password"
                :type="showPassword ? 'text' : 'password'"
                placeholder="请输入密码（至少 6 位）"
                class="ios-input pl-11 pr-12"
                required
                minlength="6"
              />
              <button
                type="button"
                @click="showPassword = !showPassword"
                class="absolute right-4 top-1/2 -translate-y-1/2 text-[#8E8E93] hover:text-[#1C1C1E] transition-colors"
              >
                <svg v-if="showPassword" class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21"></path>
                </svg>
                <svg v-else class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"></path>
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"></path>
                </svg>
              </button>
            </div>
          </div>

          <!-- 确认密码 -->
          <div>
            <label class="block text-[12px] font-semibold text-[#8E8E93] mb-2 uppercase tracking-wider">确认密码</label>
            <div class="relative">
              <svg class="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-[#8E8E93]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z"></path>
              </svg>
              <input
                v-model="formData.confirmPassword"
                :type="showConfirmPassword ? 'text' : 'password'"
                placeholder="请再次输入密码"
                class="ios-input pl-11 pr-12"
                required
                minlength="6"
              />
              <button
                type="button"
                @click="showConfirmPassword = !showConfirmPassword"
                class="absolute right-4 top-1/2 -translate-y-1/2 text-[#8E8E93] hover:text-[#1C1C1E] transition-colors"
              >
                <svg v-if="showConfirmPassword" class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21"></path>
                </svg>
                <svg v-else class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"></path>
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"></path>
                </svg>
              </button>
            </div>
          </div>

          <!-- 密码强度提示 -->
          <div v-if="formData.password" class="p-3 bg-[#F2F2F7]/60 rounded-xl">
            <p class="text-[11px] font-semibold text-[#8E8E93] mb-2">密码要求</p>
            <div class="space-y-1.5">
              <div class="flex items-center gap-2">
                <svg :class="['w-4 h-4', formData.password.length >= 6 ? 'text-[#34C759]' : 'text-[#8E8E93]']" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path>
                </svg>
                <span class="text-[12px] text-[#8E8E93]">至少 6 个字符</span>
              </div>
            </div>
          </div>

          <!-- 注册按钮 -->
          <button 
            type="submit" 
            :disabled="loading || !isValidPassword"
            class="w-full py-3 ios-gradient-primary text-white rounded-xl font-semibold shadow-lg hover:shadow-xl active:scale-[0.98] transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <span v-if="!loading">注册</span>
            <span v-else class="flex items-center justify-center gap-2">
              <div class="ios-loading-dots">
                <div></div><div></div><div></div>
              </div>
            </span>
          </button>
        </form>

        <!-- 登录链接 -->
        <div class="mt-6 text-center">
          <p class="text-[13px] text-[#8E8E93]">
            已有账户？
            <router-link to="/login" class="font-semibold text-[#007AFF] hover:text-[#007AFF]/80">立即登录</router-link>
          </p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, nextTick, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import anime from 'animejs/lib/anime.es.js'

const router = useRouter()
const loading = ref(false)
const authView = ref(null)
const showPassword = ref(false)
const showConfirmPassword = ref(false)
const formData = reactive({
  username: '',
  email: '',
  password: '',
  confirmPassword: ''
})

const isValidPassword = computed(() => {
  return formData.password.length >= 6 && formData.password === formData.confirmPassword
})

const handleRegister = async () => {
  if (formData.password !== formData.confirmPassword) {
    alert('两次输入的密码不一致')
    return
  }

  if (formData.password.length < 6) {
    alert('密码长度至少为 6 位')
    return
  }

  loading.value = true
  
  try {
    const res = await fetch('/api/v1/auth/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        username: formData.username,
        email: formData.email,
        password: formData.password
      })
    })

    if (res.ok) {
      alert('注册成功，请登录')
      router.push('/login')
    } else {
      const error = await res.json()
      alert(error.detail || error.message || '注册失败，请重试')
    }
  } catch (error) {
    console.error('注册失败:', error)
    alert('网络错误，请稍后重试')
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  await nextTick()
  anime({
    targets: authView.value?.querySelector('.ios-card'),
    opacity: [0, 1],
    translateY: [28, 0],
    scale: [0.96, 1],
    filter: ['blur(10px)', 'blur(0px)'],
    duration: 720,
    easing: 'easeOutExpo'
  })
  anime({
    targets: authView.value?.querySelectorAll('label, input, button, a, p'),
    opacity: [0, 1],
    translateY: [12, 0],
    delay: anime.stagger(42, { start: 160 }),
    duration: 520,
    easing: 'easeOutCubic'
  })
})
</script>
