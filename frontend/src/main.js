import { createApp, watch } from 'vue'
import ElIcon from 'element-plus/es/components/icon/index'
import 'element-plus/dist/index.css'
import 'element-plus/theme-chalk/dark/css-vars.css'

import App from './App.vue'
import router from './router'
import './assets/main.css'
import './assets/theme.css'
import './assets/dialog-editor.css'
import { initializeTheme } from './theme'
import { pinia } from './stores'
import { useAuthStore } from './stores/auth'
import { SITE_SETTINGS_EVENT, useSiteStore } from './stores/site'

initializeTheme()

const app = createApp(App)

app.use(pinia)
app.use(ElIcon)

let workbenchUi
router.beforeResolve(async to => {
    if (to.name === 'ProductIntro') return
    workbenchUi ||= import('./plugins/workbench-ui').then(({ installWorkbenchUi }) => {
        installWorkbenchUi(app)
    }).catch(error => {
        workbenchUi = null
        throw error
    })
    await workbenchUi
})
app.use(router)

const authStore = useAuthStore(pinia)
const siteStore = useSiteStore(pinia)

watch(() => [router.currentRoute.value.meta?.title, siteStore.siteName, siteStore.siteIcon], ([pageTitle]) => {
    document.title = typeof pageTitle === 'string' && pageTitle.trim()
        ? `${pageTitle} - ${siteStore.siteName}`
        : siteStore.siteName
    const favicon = document.querySelector('link[rel="icon"]')
    if (favicon) {
        favicon.href = siteStore.siteIcon
        favicon.type = 'image/png'
    }
}, { immediate: true })

window.addEventListener('storage', event => {
    if (event.key === SITE_SETTINGS_EVENT) siteStore.load().catch(() => {})
})

Promise.allSettled([authStore.bootstrap(), siteStore.load()]).finally(() => {
    app.mount('#app')
})

