<template>
  <div class="mac-window-shell app-shell-bg">
    <div class="mac-aurora" aria-hidden="true">
      <div class="ambient-band ambient-band-a"></div>
      <div class="ambient-band ambient-band-b"></div>
      <div class="ambient-grid"></div>
    </div>

    <nav class="ios-navbar app-navbar" data-motion>
      <div class="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-4">
        <div class="flex min-w-0 items-center gap-3">
          <div class="brand-mark" data-motion-icon>
            <svg class="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 7.5A2.5 2.5 0 016.5 5h11A2.5 2.5 0 0120 7.5v9a2.5 2.5 0 01-2.5 2.5h-11A2.5 2.5 0 014 16.5v-9z" />
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 9h8M8 13h5" />
            </svg>
          </div>
          <div class="min-w-0">
            <h1 class="app-title truncate text-[16px] font-bold">MyAgent 知识工作台</h1>
            <p class="app-subtitle hidden text-[12px] sm:block">数据库、文档与智能问答</p>
          </div>
        </div>

        <div class="flex flex-wrap items-center gap-3">
          <div class="nav-segment">
            <router-link
              v-for="item in navItems"
              :key="item.path"
              :to="item.path"
              class="nav-pill"
              :class="{ 'nav-pill-active': item.active(route.path) }"
            >
              <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" :d="item.icon" />
              </svg>
              <span>{{ item.label }}</span>
            </router-link>
          </div>

          <div class="theme-switch" aria-label="主题切换">
            <button
              v-for="option in themeOptions"
              :key="option.value"
              type="button"
              class="theme-option"
              :class="{ 'theme-option-active': themeMode === option.value }"
              :title="option.title"
              @click="setThemeMode(option.value)"
            >
              <span>{{ option.icon }}</span>
            </button>
          </div>

          <div v-if="isAuthenticated" class="hidden items-center gap-3 border-l border-[var(--border)] pl-4 sm:flex">
            <div class="user-avatar">{{ userInitial }}</div>
            <span class="user-name max-w-28 truncate text-[14px] font-semibold">{{ userName }}</span>
            <button
              @click="handleLogout"
              class="ios-btn-icon text-[var(--muted)] hover:text-[#D92D20]"
              title="退出登录"
            >
              <svg class="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
              </svg>
            </button>
          </div>
        </div>
      </div>
    </nav>

    <main class="mac-page-content px-4 py-5 sm:px-6 lg:px-8">
      <router-view v-slot="{ Component }">
        <transition mode="out-in" @enter="onRouteEnter" @leave="onRouteLeave" :css="false">
          <component :is="Component" class="motion-scope" />
        </transition>
      </router-view>
    </main>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import anime from 'animejs/lib/anime.es.js'

const router = useRouter()
const route = useRoute()
const systemQuery = window.matchMedia('(prefers-color-scheme: dark)')
const themeMode = ref(localStorage.getItem('theme-mode') || 'system')

const navItems = [
  {
    label: '数据库',
    path: '/knowledge-bases',
    icon: 'M4 7c0-1.657 3.582-3 8-3s8 1.343 8 3-3.582 3-8 3-8-1.343-8-3zm0 0v5c0 1.657 3.582 3 8 3s8-1.343 8-3V7M4 12v5c0 1.657 3.582 3 8 3s8-1.343 8-3v-5',
    active: (path) => path.startsWith('/knowledge-bases') || path.startsWith('/kb/')
  },
  {
    label: '助手',
    path: '/agent',
    icon: 'M8 10h.01M12 10h.01M16 10h.01M7 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z',
    active: (path) => path.startsWith('/agent') || path.startsWith('/chat')
  }
]

const themeOptions = [
  { value: 'light', icon: '☼', title: '浅色模式' },
  { value: 'dark', icon: '◐', title: '深色模式' },
  { value: 'system', icon: '◎', title: '跟随系统' }
]

const resolvedTheme = computed(() => {
  if (themeMode.value === 'system') {
    return systemQuery.matches ? 'dark' : 'light'
  }
  return themeMode.value
})

const applyTheme = () => {
  document.documentElement.dataset.theme = resolvedTheme.value
  document.documentElement.dataset.themeMode = themeMode.value
}

const setThemeMode = (mode) => {
  themeMode.value = mode
  localStorage.setItem('theme-mode', mode)
  applyTheme()
  animateThemeSwitch()
}

const isAuthenticated = computed(() => {
  return !!localStorage.getItem('token')
})

const userName = computed(() => {
  const userInfo = JSON.parse(localStorage.getItem('userInfo') || 'null')
  return userInfo?.display_name || userInfo?.username || '用户'
})

const userInitial = computed(() => {
  return userName.value?.charAt(0)?.toUpperCase() || 'U'
})

const onRouteEnter = (el, done) => {
  const timeline = anime.timeline({
    easing: 'easeOutCubic',
    complete: done
  })

  timeline
    .add({
      targets: el,
      opacity: [0, 1],
      translateY: [12, 0],
      duration: 260
    })
    .add({
      targets: el.querySelectorAll('.ios-card, .ios-card-hover, button, input, textarea, select'),
      opacity: [0, 1],
      translateY: [10, 0],
      delay: anime.stagger(18, { start: 20 }),
      duration: 320
    }, '-=120')
}

const onRouteLeave = (el, done) => {
  anime({
    targets: el,
    opacity: [1, 0],
    translateY: [0, -6],
    duration: 150,
    easing: 'easeInQuad',
    complete: done
  })
}

const handleLogout = () => {
  if (confirm('确定退出登录吗？')) {
    localStorage.removeItem('token')
    localStorage.removeItem('userInfo')
    router.push('/login')
  }
}

const animateThemeSwitch = () => {
  anime({
    targets: ['.app-navbar', '.ios-card', '.login-copy'],
    scale: [0.995, 1],
    duration: 260,
    easing: 'easeOutCubic'
  })
}

const handleSystemThemeChange = () => {
  if (themeMode.value === 'system') {
    applyTheme()
    animateThemeSwitch()
  }
}

applyTheme()

onMounted(async () => {
  await nextTick()

  systemQuery.addEventListener('change', handleSystemThemeChange)

  anime.timeline({ easing: 'easeOutCubic' })
    .add({
      targets: '[data-motion]',
      opacity: [0, 1],
      translateY: [-8, 0],
      duration: 360
    })
    .add({
      targets: '[data-motion-icon]',
      scale: [0.86, 1],
      rotate: [-4, 0],
      duration: 520,
      easing: 'easeOutExpo'
    }, '-=180')
    .add({
      targets: '.nav-pill, .theme-option',
      opacity: [0, 1],
      translateY: [-6, 0],
      delay: anime.stagger(28),
      duration: 260
    }, '-=260')

})

onBeforeUnmount(() => {
  systemQuery.removeEventListener('change', handleSystemThemeChange)
})
</script>
