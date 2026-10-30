import request from '@/api/request'

// ====== Docker 环境主机 ======
export const getDockerHosts = (params = {}, signal) => request.get('/docker/hosts/', { params, signal })
export const getDockerSummary = (id, refresh = false, signal) => request.get(`/docker/hosts/${id}/summary/`, { params: { refresh: refresh ? '1' : undefined }, signal })
export const createDockerHost = (data) => request.post('/docker/hosts/', data)
export const updateDockerHost = (id, data) => request.put(`/docker/hosts/${id}/`, data)
export const deleteDockerHost = (id) => request.delete(`/docker/hosts/${id}/`)
export const testDockerConnection = (id) => request.post(`/docker/hosts/${id}/test_connection/`)

// ====== Docker 容器 ======
export const getDockerContainers = (hostId, refresh = false, signal) => request.get('/docker/containers/', { params: { host_id: hostId, refresh: refresh ? '1' : undefined }, signal })
export const getDockerImages = (hostId, refresh = false, signal) => request.get('/docker/images/', { params: { host_id: hostId, refresh: refresh ? '1' : undefined }, signal })
export const getDockerLogPage = (containerId, params, signal) => request.get(`/docker/containers/${encodeURIComponent(containerId)}/log_page/`, { params, signal, timeout: 70000 })
export const getDockerImageInspect = (imageId, hostId) => request.get(`/docker/images/${encodeURIComponent(imageId)}/inspect/`, { params: { host_id: hostId } })
export const dockerContainerAction = (containerId, hostId, action) =>
  request.post(`/docker/containers/${containerId}/action/`, { host_id: hostId, action })
export const dockerContainerRemove = (containerId, hostId) =>
  request.delete(`/docker/containers/${containerId}/remove/`, { params: { host_id: hostId } })
export const getDockerContainerLogs = (containerId, hostId, tail = 200) =>
  request.get(`/docker/containers/${containerId}/logs/`, { params: { host_id: hostId, tail } })
export const getDockerContainerInspect = (containerId, hostId) =>
  request.get(`/docker/containers/${containerId}/inspect/`, { params: { host_id: hostId } })
export const dockerRemoveImages = (hostId, imageIds) =>
  request.delete('/docker/images/remove/', { data: { host_id: hostId, image_ids: imageIds } })
export const dockerPruneDanglingImages = (hostId) =>
  request.post('/docker/images/prune/', { host_id: hostId })

// ====== K8s 集群 ======
export const getK8sClusters = () => request.get('/k8s/clusters/')
export const createK8sCluster = (data) => request.post('/k8s/clusters/', data)
export const updateK8sCluster = (id, data) => request.put(`/k8s/clusters/${id}/`, data)
export const deleteK8sCluster = (id) => request.delete(`/k8s/clusters/${id}/`)
export const testK8sConnection = (id) => request.post(`/k8s/clusters/${id}/test_connection/`)
export const getK8sSummary = (id) => request.get(`/k8s/clusters/${id}/summary/`)
export const getK8sCapacity = (id) => request.get(`/k8s/clusters/${id}/capacity/`)
export const getK8sNamespaces = (id) => request.get(`/k8s/clusters/${id}/namespaces/`)
export const getK8sPods = (id, ns = 'default') => request.get(`/k8s/clusters/${id}/pods/`, { params: { namespace: ns } })
export const getK8sServices = (id, ns = 'default') => request.get(`/k8s/clusters/${id}/services/`, { params: { namespace: ns } })
export const getK8sDeployments = (id, ns = 'default') => request.get(`/k8s/clusters/${id}/deployments/`, { params: { namespace: ns } })
export const restartK8sPod = (clusterId, podName, ns) => request.post(`/k8s/clusters/${clusterId}/pods/${podName}/restart/`, { namespace: ns })

// ====== K8s 扩展资源 ======
export const getK8sNodes = (id) => request.get(`/k8s/clusters/${id}/nodes/`)
export const getK8sStatefulSets = (id, ns = 'default') => request.get(`/k8s/clusters/${id}/statefulsets/`, { params: { namespace: ns } })
export const getK8sDaemonSets = (id, ns = 'default') => request.get(`/k8s/clusters/${id}/daemonsets/`, { params: { namespace: ns } })
export const getK8sJobs = (id, ns = 'default') => request.get(`/k8s/clusters/${id}/jobs/`, { params: { namespace: ns } })
export const getK8sCronJobs = (id, ns = 'default') => request.get(`/k8s/clusters/${id}/cronjobs/`, { params: { namespace: ns } })
export const getK8sIngresses = (id, ns = 'default') => request.get(`/k8s/clusters/${id}/ingresses/`, { params: { namespace: ns } })
export const getK8sPVs = (id) => request.get(`/k8s/clusters/${id}/pvs/`)
export const getK8sPVCs = (id, ns = 'default') => request.get(`/k8s/clusters/${id}/pvcs/`, { params: { namespace: ns } })
export const getK8sStorageClasses = (id) => request.get(`/k8s/clusters/${id}/storageclasses/`)
export const getK8sConfigMaps = (id, ns = 'default') => request.get(`/k8s/clusters/${id}/configmaps/`, { params: { namespace: ns } })
export const getK8sSecrets = (id, ns = 'default') => request.get(`/k8s/clusters/${id}/secrets/`, { params: { namespace: ns } })
export const getK8sResourceYaml = (id, type, name, ns = 'default') => request.get(`/k8s/clusters/${id}/resource_yaml/`, { params: { type, name, namespace: ns } })
export const getK8sWorkloadPods = (id, workloadType, name, ns = 'default') => request.get(`/k8s/clusters/${id}/workload_pods/`, { params: { workload_type: workloadType, name, namespace: ns } })
export const getK8sPodLogs = (id, podName, ns = 'default', container = '', tailLines = 200) => request.get(`/k8s/clusters/${id}/pod_logs/`, { params: { pod_name: podName, namespace: ns, container, tail_lines: tailLines } })
export const getK8sPodLogPage = (id, params, signal) => request.get(`/k8s/clusters/${id}/pod_logs/`, { params: { ...params, paged: 1 }, signal, timeout: 90000, skipErrorMessage: true })
export const getK8sResourceEvents = (id, type, name, ns = 'default') => request.get(`/k8s/clusters/${id}/resource_events/`, { params: { type, name, namespace: ns } })
export const execK8sPod = (id, payload) => request.post(`/k8s/clusters/${id}/pod_exec/`, payload)
export const runK8sKubectl = (id, command) => request.post(`/k8s/clusters/${id}/kubectl/`, { command })
export const scaleK8sWorkload = (id, payload) => request.post(`/k8s/clusters/${id}/scale_workload/`, payload)
export const previewK8sYaml = (id, payload) => request.post(`/k8s/clusters/${id}/yaml_preview/`, payload)
export const applyK8sYaml = (id, payload) => request.post(`/k8s/clusters/${id}/yaml_apply/`, payload)
export const deleteK8sResource = (id, payload) => request.post(`/k8s/clusters/${id}/resource_delete/`, payload)
export const operateK8sWorkload = (id, payload) => request.post(`/k8s/clusters/${id}/workload_action/`, payload)
export const operateK8sNode = (id, payload) => request.post(`/k8s/clusters/${id}/node_action/`, payload)
export const getK8sResources = (id, type, namespace) => request.get(`/k8s/clusters/${id}/resources/`, { params: { type, namespace } })
export const getK8sConfigResourceDetail = (id, type, name, ns = 'default') =>
  request.get(`/k8s/clusters/${id}/config_resource_detail/`, { params: { type, name, namespace: ns } })
export const previewK8sConfigResource = (id, payload) => request.post(`/k8s/clusters/${id}/config_resource_preview/`, payload)
export const updateK8sConfigResource = (id, payload) => request.post(`/k8s/clusters/${id}/config_resource_update/`, payload)
export const getK8sConfigRevisions = (id, type, name, ns = 'default') =>
  request.get(`/k8s/clusters/${id}/config_resource_revisions/`, { params: { type, name, namespace: ns } })
export const getK8sConfigRevisionPreview = (id, type, name, ns = 'default', revisionId) =>
  request.get(`/k8s/clusters/${id}/config_resource_revision_preview/`, { params: { type, name, namespace: ns, revision_id: revisionId } })
export const getK8sConfigRollbackPreview = (id, type, name, ns = 'default') =>
  request.get(`/k8s/clusters/${id}/config_resource_rollback_preview/`, { params: { type, name, namespace: ns } })
export const rollbackK8sConfigResource = (id, payload) => request.post(`/k8s/clusters/${id}/config_resource_rollback/`, payload)
export const rollbackK8sConfigResourceToRevision = (id, payload) =>
  request.post(`/k8s/clusters/${id}/config_resource_rollback_to_revision/`, payload)
