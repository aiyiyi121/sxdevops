import request from '@/api/request'


const READ_CONFIG = { suppressErrorMessage: true }

export const getWafAccounts = () => request.get('/cloud-security/waf/accounts/', READ_CONFIG)

export const getWafOverview = (params = {}) => request.get('/cloud-security/waf/overview/', {
  ...READ_CONFIG,
  params,
})

export const getWafResources = (params = {}) => request.get('/cloud-security/waf/resources/', {
  ...READ_CONFIG,
  params,
})

export const getWafEvents = (params = {}) => request.get('/cloud-security/waf/events/', {
  ...READ_CONFIG,
  params,
})

export const getInternalPlatformOverview = () => request.get('/cloud-security/internal-platform/overview/')
export const getInternalPlatformPosture = () => request.get('/cloud-security/internal-platform/posture/')
export const getInternalPlatformAssets = (params = {}) => request.get('/cloud-security/internal-platform/assets/', { params })
export const getInternalPlatformThreats = (params = {}) => request.get('/cloud-security/internal-platform/threats/', { params })
export const updateInternalPlatformThreat = (id, data) => request.post(`/cloud-security/internal-platform/threats/${id}/action/`, data)
export const getInternalPlatformSoftware = (params = {}) => request.get('/cloud-security/internal-platform/software/', { params })
export const updateInternalPlatformSoftwareStatus = (id, data) => request.post(`/cloud-security/internal-platform/software/${id}/status/`, data)
export const getInternalPlatformFindings = (params = {}) => request.get('/cloud-security/internal-platform/findings/', { params })
export const getInternalPlatformFinding = (id) => request.get(`/cloud-security/internal-platform/findings/${id}/`)
export const createInternalPlatformFinding = (data) => request.post('/cloud-security/internal-platform/findings/', data)
export const updateInternalPlatformFinding = (id, data) => request.patch(`/cloud-security/internal-platform/findings/${id}/`, data)
export const progressInternalPlatformFinding = (id, data) => request.post(`/cloud-security/internal-platform/findings/${id}/progress/`, data)
export const closeInternalPlatformFinding = (id, data) => request.post(`/cloud-security/internal-platform/findings/${id}/close/`, data)
export const reopenInternalPlatformFinding = (id, data = {}) => request.post(`/cloud-security/internal-platform/findings/${id}/reopen/`, data)
