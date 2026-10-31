import { computed, onMounted, ref } from 'vue'

const stars = ref(null)
let nextRefresh = 0
let pending = null

async function loadStars() {
  if (Date.now() < nextRefresh) return
  if (pending) return pending
  nextRefresh = Date.now() + 5 * 60 * 1000
  pending = (async () => {
    try {
      const response = await fetch('/api/site-settings/repository/', {
        credentials: 'omit',
        signal: AbortSignal.timeout(7000),
      })
      if (!response.ok) return
      const result = await response.json()
      if (Number.isSafeInteger(result.stars) && result.stars >= 0) stars.value = result.stars
    } catch {
      // Keep the last value if this browser temporarily loses connectivity.
    } finally {
      pending = null
    }
  })()
  return pending
}

export function useRepositoryStars() {
  onMounted(loadStars)
  return {
    starsLabel: computed(() => stars.value === null ? '—' : stars.value.toLocaleString('en-US')),
  }
}
