import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
import './style.css'

const savedThemeMode = localStorage.getItem('theme-mode') || 'system'
const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches
document.documentElement.dataset.themeMode = savedThemeMode
document.documentElement.dataset.theme = savedThemeMode === 'system'
  ? (prefersDark ? 'dark' : 'light')
  : savedThemeMode

const app = createApp(App)

app.use(createPinia())
app.use(router)

app.mount('#app')
