import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import defaultSiteIcon from '@/assets/brand-mark.svg'
import { getSiteSettings, updateSiteSettings } from '@/api/modules/rbac'

export const DEFAULT_SITE_NAME = 'SXDevOps'
export { defaultSiteIcon }
export const SITE_SETTINGS_EVENT = 'sxdevops-site-settings-updated'

export const useSiteStore = defineStore('site', () => {
  const siteName = ref(DEFAULT_SITE_NAME)
  const customIconUrl = ref('')
  const siteIcon = computed(() => customIconUrl.value || defaultSiteIcon)

  function apply(settings) {
    siteName.value = settings.site_name || DEFAULT_SITE_NAME
    customIconUrl.value = settings.icon_url || ''
  }

  async function load(options = {}) {
    const settings = await getSiteSettings({ skipErrorMessage: options.silent !== false })
    apply(settings)
    return settings
  }

  async function save(data) {
    const settings = await updateSiteSettings(data)
    apply(settings)
    try {
      localStorage.setItem(SITE_SETTINGS_EVENT, String(Date.now()))
    } catch {}
    return settings
  }

  return { siteName, siteIcon, customIconUrl, load, save }
})
