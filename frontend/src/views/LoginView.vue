<template>
  <div ref="authView" class="auth-view flex items-center justify-center px-4 py-10">
    <section class="auth-panel login-shell w-full max-w-[980px]">
      <div class="login-copy">
        <p class="login-kicker">MyAgent Workspace</p>
        <h2>把知识库、文档和问答放进同一个工作流。</h2>
        <p>
          登录后可以管理数据库、上传文档，并用助手基于资料进行问答。
        </p>
        <div class="login-metrics" aria-hidden="true">
          <div>
            <strong>KB</strong>
            <span>结构化资料</span>
          </div>
          <div>
            <strong>AI</strong>
            <span>上下文问答</span>
          </div>
          <div>
            <strong>Doc</strong>
            <span>文档检索</span>
          </div>
        </div>
      </div>

      <div class="login-card ios-card">
        <div class="mb-7">
          <div class="brand-mark mb-5">
            <svg class="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
            </svg>
          </div>
          <h1 class="text-[28px] font-bold text-[#172033]">登录 MyAgent</h1>
          <p class="mt-2 text-[14px] text-[#667085]">进入你的知识工作台</p>
        </div>

        <form @submit.prevent="handleLogin" class="space-y-5">
          <div>
            <label class="form-label">用户名</label>
            <input
              v-model="formData.username"
              type="text"
              placeholder="请输入用户名"
              class="ios-input"
              required
            />
          </div>

          <div>
            <label class="form-label">密码</label>
            <div class="relative">
              <input
                v-model="formData.password"
                :type="showPassword ? 'text' : 'password'"
                placeholder="请输入密码"
                class="ios-input pr-12"
                required
              />
              <button
                type="button"
                @click="showPassword = !showPassword"
                class="absolute right-4 top-1/2 -translate-y-1/2 text-[#667085] hover:text-[#172033]"
                :title="showPassword ? '隐藏密码' : '显示密码'"
              >
                <svg v-if="showPassword" class="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 3l18 18M10.6 10.6a2 2 0 002.8 2.8M9.9 5.2A9.9 9.9 0 0112 5c4.5 0 8.3 2.9 9.5 7a10.8 10.8 0 01-2.4 3.9M6.1 6.1A10.7 10.7 0 002.5 12c1.2 4.1 5 7 9.5 7a9.7 9.7 0 004.1-.9" />
                </svg>
                <svg v-else class="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.5 12C3.7 7.9 7.5 5 12 5s8.3 2.9 9.5 7c-1.2 4.1-5 7-9.5 7s-8.3-2.9-9.5-7z" />
                </svg>
              </button>
            </div>
          </div>

          <div class="flex items-center justify-between">
            <label class="flex cursor-pointer items-center gap-2">
              <input v-model="formData.remember" type="checkbox" class="ios-checkbox" />
              <span class="text-[13px] text-[#475467]">记住我</span>
            </label>
            <router-link to="/register" class="text-[13px] font-semibold text-[#134E4A] hover:text-[#0F766E]">
              创建账号
            </router-link>
          </div>

          <button
            type="submit"
            :disabled="loading"
            class="w-full rounded-xl bg-[#134E4A] py-3 font-semibold text-white shadow-[0_12px_24px_rgba(19,78,74,.22)] transition hover:bg-[#0F766E] active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-50"
          >
            <span v-if="!loading">登录</span>
            <span v-else>登录中...</span>
          </button>
        </form>
      </div>
    </section>
  </div>
</template>

<script setup>
import { ref, reactive, nextTick, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import anime from 'animejs/lib/anime.es.js'
import { useAuth } from '@/stores/auth'

const router = useRouter()
const route = useRoute()
const loading = ref(false)
const showPassword = ref(false)
const authView = ref(null)
const { login } = useAuth()
const formData = reactive({
  username: '',
  password: '',
  remember: false
})

const handleLogin = async () => {
  loading.value = true

  try {
    const result = await login(formData.username, formData.password)
    
    if (result.success) {
      // 登录成功，跳转到重定向页面或默认到助手页面
      router.push(route.query.redirect || '/agent')
    } else {
      alert(result.error || '登录失败，请检查用户名和密码')
    }
  } catch (error) {
    console.error('登录失败:', error)
    alert('网络异常，请稍后重试')
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  await nextTick()

  anime({
    targets: authView.value?.querySelector('.login-shell'),
    opacity: [0, 1],
    translateY: [18, 0],
    duration: 460,
    easing: 'easeOutCubic'
  })
})
</script>
