import { useAuthStore } from '@/stores/auth'
import { pinia } from '@/stores'

export function can(permission) {
  return useAuthStore(pinia).hasPermission(permission)
}

export function canAny(permissions) {
  return useAuthStore(pinia).hasAnyPermission(permissions)
}

export function canAll(permissions) {
  return useAuthStore(pinia).hasAllPermissions(permissions)
}

export function authorizedLandingPath(router, preferred = []) {
  const auth = useAuthStore(pinia)
  const allowed = meta => meta.permission
    ? auth.hasPermission(meta.permission)
    : Boolean(meta.anyPermissions?.length && auth.hasAnyPermission(meta.anyPermissions))
  const candidates = [...preferred, '/dashboard', ...router.getRoutes()
    .filter(route => !route.redirect && !route.meta.hidden && !route.path.includes(':'))
    .map(route => route.path)]
  for (const path of candidates) {
    if (typeof path !== 'string' || !path.startsWith('/') || path.startsWith('//') || path.includes('\\')) continue
    const target = router.resolve(path)
    if (target.matched.length && !target.meta.public && allowed(target.meta)) return target.fullPath
  }
  return '/403'
}
