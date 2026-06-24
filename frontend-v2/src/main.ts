import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
import { useAuthStore } from './stores/auth'

// Create app + plugins
const app = createApp(App)
const pinia = createPinia()

app.use(pinia)
app.use(router)

// Restore auth from localStorage BEFORE first navigation so guards see it
const auth = useAuthStore()
auth.restoreFromStorage()

// Mount
app.mount('#app')