import request from '../request'

export const login = (data) => request.post('/auth/login/', data)
export const logout = () => request.post('/auth/logout/')
export const getCurrentUser = () => request.get('/auth/me/')
export const syncPermissions = () => request.post('/auth/sync/')
export const getAssignmentOptions = () => request.get('/auth/assignment-options/')
export const getUserOptions = (params) => request.get('/users/options/', { params })

export const getUsers = (params) => request.get('/users/', { params })
export const createUser = (data) => request.post('/users/', data)
export const updateUser = (id, data) => request.patch(`/users/${id}/`, data)
export const deleteUser = (id) => request.delete(`/users/${id}/`)
export const resetUserPassword = (id, password) => request.post(`/users/${id}/reset_password/`, { password })
export const getUserK8sAccess = (id) => request.get(`/users/${id}/k8s-access/`)
export const updateUserK8sAccess = (id, data) => request.put(`/users/${id}/k8s-access/`, data)

export const getRoles = (params) => request.get('/roles/', { params })
export const createRole = (data) => request.post('/roles/', data)
export const updateRole = (id, data) => request.patch(`/roles/${id}/`, data)
export const deleteRole = (id) => request.delete(`/roles/${id}/`)

export const getGroups = (params) => request.get('/groups/', { params })
export const createGroup = (data) => request.post('/groups/', data)
export const updateGroup = (id, data) => request.patch(`/groups/${id}/`, data)
export const deleteGroup = (id) => request.delete(`/groups/${id}/`)

export const getPermissions = (params) => request.get('/permissions/', { params })
export const getModuleSettings = (config = {}) => request.get('/module-settings/', config)
export const updateModuleSettings = (data) => request.put('/module-settings/', data)
export const getSiteSettings = (config = {}) => request.get('/site-settings/', config)
export const updateSiteSettings = (data) => request.put('/site-settings/manage/', data)
