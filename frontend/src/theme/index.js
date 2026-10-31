import { computed, ref } from 'vue'
import { darkColor, themePalette } from './palette'

const THEME_STORAGE_KEY = 'sxdevops-theme'
const DEFAULT_THEME = 'charcoal'
export const THEME_CHANGE_EVENT = 'sxdevops-theme-changed'
export const theme = ref(DEFAULT_THEME)
export const themeOptions = [
  { value: 'light', label: '浅色' },
  { value: 'charcoal', label: '炭灰', recommended: true },
  { value: 'dark', label: '深蓝灰' },
]
export const themeLabel = computed(() => themeOptions.find(option => option.value === theme.value).label)
export const colorScheme = computed(() => theme.value === 'light' ? 'light' : 'dark')

function normalizeTheme(value) {
  return themeOptions.some(option => option.value === value) ? value : DEFAULT_THEME
}

export function resolveThemeColor(value, role = 'text') {
  return colorScheme.value === 'dark' ? darkColor(value, role, themePalette(theme.value)) : value
}

function savedTheme() {
  try {
    return normalizeTheme(localStorage.getItem(THEME_STORAGE_KEY))
  } catch {
    return DEFAULT_THEME
  }
}

function applyTheme(value) {
  theme.value = normalizeTheme(value)
  document.documentElement.classList.toggle('dark', colorScheme.value === 'dark')
  document.documentElement.dataset.theme = theme.value
  document.documentElement.style.colorScheme = colorScheme.value
  window.dispatchEvent(new CustomEvent(THEME_CHANGE_EVENT, { detail: theme.value }))
}

export function initializeTheme() {
  applyTheme(savedTheme())
  window.addEventListener('storage', event => {
    if (event.key === THEME_STORAGE_KEY || event.key === null) applyTheme(savedTheme())
  })
}

export function setTheme(value) {
  applyTheme(value)
  try {
    localStorage.setItem(THEME_STORAGE_KEY, theme.value)
  } catch {
    return
  }
}
