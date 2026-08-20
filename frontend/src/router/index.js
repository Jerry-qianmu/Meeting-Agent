import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  {
    path: '/',
    redirect: '/login'
  },
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/LoginView.vue'),
    meta: { requiresAuth: false, title: '登录' }
  },
  {
    path: '/register',
    name: 'Register',
    component: () => import('@/views/RegisterView.vue'),
    meta: { requiresAuth: false, title: '注册' }
  },
  {
    path: '/knowledge-bases',
    name: 'KnowledgeBases',
    component: () => import('@/views/KnowledgeBasesView.vue'),
    meta: { requiresAuth: false, title: '数据库' }
  },
{
    path: '/kb/:id',
    name: 'KnowledgeBaseDetail',
    component: () => import('@/views/KnowledgeBaseDetailView.vue'),
    meta: { requiresAuth: false, title: '知识库详情' }
  },
  {
    path: '/agent',
    name: 'Agent',
    component: () => import('@/views/AgentChatView.vue'),
    meta: { requiresAuth: false, title: '助手' }
  },
  {
    path: '/chat',
    redirect: '/agent'
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

router.beforeEach((to, from, next) => {
  document.title = to.meta.title ? `${to.meta.title} - MyAgent` : 'MyAgent'

  const token = localStorage.getItem('token')
  const requiresAuth = to.meta.requiresAuth === true

  if (requiresAuth && !token) {
    next({
      path: '/login',
      query: { redirect: to.fullPath }
    })
    return
  }

  if (to.path === '/login' && token) {
    next('/agent')
    return
  }

  next()
})

export default router
