import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { getCurrentUser, getModuleSettings, login as loginApi, logout as logoutApi } from '@/api/modules/rbac'

const TOKEN_KEY = 'sxdevops_token'
const USER_KEY = 'sxdevops_user'

function loadStoredUser() {
  try {
    const raw = localStorage.getItem(USER_KEY)
    return raw ? JSON.parse(raw) : null
  } catch {
    localStorage.removeItem(USER_KEY)
    return null
  }
}

export const useAuthStore = defineStore('auth', () => {
  const token = ref(localStorage.getItem(TOKEN_KEY) || '')
  const currentUser = ref(loadStoredUser())
  const initialized = ref(false)
  const moduleSettings = ref([])
  const moduleSettingsLoaded = ref(false)

  const isAuthenticated = computed(() => !!token.value && !!currentUser.value)
  const permissions = computed(() => currentUser.value?.effective_permissions || [])
  const displayName = computed(() => {
    if (!currentUser.value) return ''
    return currentUser.value.display_name || currentUser.value.username || ''
  })

  function persistToken(value) {
    token.value = value || ''
    if (token.value) {
      localStorage.setItem(TOKEN_KEY, token.value)
    } else {
      localStorage.removeItem(TOKEN_KEY)
    }
  }

  function persistUser(user) {
    currentUser.value = user || null
    if (currentUser.value) {
      localStorage.setItem(USER_KEY, JSON.stringify(currentUser.value))
    } else {
      localStorage.removeItem(USER_KEY)
    }
  }

  function setUser(user) {
    persistUser(user)
  }

  function setModuleSettings(settings) {
    moduleSettings.value = Array.isArray(settings) ? settings : []
    moduleSettingsLoaded.value = true
  }

  function clearSession() {
    persistToken('')
    persistUser(null)
    moduleSettings.value = []
    moduleSettingsLoaded.value = false
  }

  async function bootstrap() {
    if (initialized.value) return currentUser.value
    initialized.value = true

    if (!token.value) {
      persistUser(null)
      return null
    }

    const [user] = await Promise.all([
      reloadProfile({ silent: true, clearOnUnauthorized: true }),
      reloadModuleSettings({ silent: true }),
    ])
    return user
  }

  async function reloadProfile(options = {}) {
    const { silent = false, clearOnUnauthorized = true } = options
    initialized.value = true
    if (!token.value) return null
    try {
      const user = await getCurrentUser()
      setUser(user)
      return user
    } catch (error) {
      if (error?.response?.status === 401 && clearOnUnauthorized) {
        clearSession()
        return null
      }
      return silent ? currentUser.value : null
    }
  }

  async function login(payload) {
    const response = await loginApi(payload)
    persistToken(response.token)
    setUser(response.user)
    if (Array.isArray(response.module_settings)) {
      setModuleSettings(response.module_settings)
    } else {
      await reloadModuleSettings({ silent: true })
    }
    initialized.value = true
    return response
  }

  async function reloadModuleSettings(options = {}) {
    const { silent = false } = options
    if (!token.value) {
      setModuleSettings([])
      return []
    }
    try {
      const settings = await getModuleSettings({ skipErrorMessage: silent })
      setModuleSettings(settings)
      return moduleSettings.value
    } catch (error) {
      moduleSettingsLoaded.value = true
      if (silent) return moduleSettings.value
      throw error
    }
  }

  async function logout() {
    try {
      if (token.value) {
        await logoutApi()
      }
    } finally {
      clearSession()
      initialized.value = true
    }
  }

  function hasPermission(code) {
    if (!isAuthenticated.value || !currentUser.value?.is_active) return false
    if (!code) return true
    return permissions.value.includes(code)
  }

  function hasAnyPermission(codes = []) {
    if (!codes.length) return isAuthenticated.value && Boolean(currentUser.value?.is_active)
    return codes.some(code => hasPermission(code))
  }

  function hasAllPermissions(codes = []) {
    if (!codes.length) return isAuthenticated.value && Boolean(currentUser.value?.is_active)
    return codes.every(code => hasPermission(code))
  }

  return {
    token,
    currentUser,
    initialized,
    moduleSettings,
    moduleSettingsLoaded,
    isAuthenticated,
    permissions,
    displayName,
    bootstrap,
    login,
    logout,
    clearSession,
    setModuleSettings,
    hasPermission,
    hasAnyPermission,
    hasAllPermissions,
    reloadProfile,
    reloadModuleSettings,
  }
})
