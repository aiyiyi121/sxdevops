const appPodSpec = `      containers:
        - name: app
          image: nginx:stable
          ports:
            - containerPort: 80`

const workloadTemplate = `  selector:
    matchLabels:
      app: example-app
  template:
    metadata:
      labels:
        app: example-app
    spec:
${appPodSpec}`

const resourceTemplates = {
  node: { apiVersion: 'v1', kind: 'Node', clusterScoped: true, body: 'spec: {}' },
  namespace: { apiVersion: 'v1', kind: 'Namespace', clusterScoped: true },
  pod: {
    apiVersion: 'v1', kind: 'Pod',
    body: `spec:
  containers:
    - name: app
      image: nginx:stable
      ports:
        - containerPort: 80`,
  },
  deployment: {
    apiVersion: 'apps/v1', kind: 'Deployment',
    body: `spec:
  replicas: 1
${workloadTemplate}`,
  },
  statefulset: {
    apiVersion: 'apps/v1', kind: 'StatefulSet',
    body: `spec:
  serviceName: example-headless
  replicas: 1
${workloadTemplate}`,
  },
  daemonset: { apiVersion: 'apps/v1', kind: 'DaemonSet', body: `spec:
${workloadTemplate}` },
  job: {
    apiVersion: 'batch/v1', kind: 'Job',
    body: `spec:
  backoffLimit: 3
  template:
    spec:
      restartPolicy: Never
      containers:
        - name: job
          image: busybox:stable
          command: ["sh", "-c", "echo hello"]`,
  },
  cronjob: {
    apiVersion: 'batch/v1', kind: 'CronJob',
    body: `spec:
  schedule: "*/5 * * * *"
  jobTemplate:
    spec:
      template:
        spec:
          restartPolicy: OnFailure
          containers:
            - name: job
              image: busybox:stable
              command: ["sh", "-c", "echo hello"]`,
  },
  service: {
    apiVersion: 'v1', kind: 'Service',
    body: `spec:
  type: ClusterIP
  selector:
    app: example-app
  ports:
    - port: 80
      targetPort: 80
      protocol: TCP`,
  },
  endpoints: {
    apiVersion: 'v1', kind: 'Endpoints',
    body: `subsets:
  - addresses:
      - ip: 192.0.2.10
    ports:
      - port: 80
        protocol: TCP`,
  },
  ingressclass: {
    apiVersion: 'networking.k8s.io/v1', kind: 'IngressClass', clusterScoped: true,
    body: `spec:
  controller: k8s.io/ingress-nginx`,
  },
  ingress: {
    apiVersion: 'networking.k8s.io/v1', kind: 'Ingress',
    body: `spec:
  ingressClassName: nginx
  rules:
    - host: example.com
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: example-service
                port:
                  number: 80`,
  },
  pv: {
    apiVersion: 'v1', kind: 'PersistentVolume', clusterScoped: true,
    body: `spec:
  capacity:
    storage: 10Gi
  volumeMode: Filesystem
  accessModes:
    - ReadWriteOnce
  persistentVolumeReclaimPolicy: Retain
  storageClassName: manual
  hostPath:
    path: /mnt/data`,
  },
  pvc: {
    apiVersion: 'v1', kind: 'PersistentVolumeClaim',
    body: `spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 10Gi`,
  },
  storageclass: {
    apiVersion: 'storage.k8s.io/v1', kind: 'StorageClass', clusterScoped: true,
    body: `provisioner: example.com/provisioner
reclaimPolicy: Delete
volumeBindingMode: WaitForFirstConsumer
allowVolumeExpansion: true`,
  },
  configmap: { apiVersion: 'v1', kind: 'ConfigMap', body: `data:
  key: value` },
  secret: { apiVersion: 'v1', kind: 'Secret', body: `type: Opaque
stringData:
  key: value` },
  hpa: {
    apiVersion: 'autoscaling/v2', kind: 'HorizontalPodAutoscaler',
    body: `spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: example-deployment
  minReplicas: 1
  maxReplicas: 5
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 80`,
  },
  networkpolicy: {
    apiVersion: 'networking.k8s.io/v1', kind: 'NetworkPolicy',
    body: `spec:
  podSelector:
    matchLabels:
      app: example-app
  policyTypes:
    - Ingress
  ingress:
    - ports:
        - protocol: TCP
          port: 80`,
  },
  resourcequota: {
    apiVersion: 'v1', kind: 'ResourceQuota',
    body: `spec:
  hard:
    requests.cpu: "4"
    requests.memory: 8Gi
    limits.cpu: "8"
    limits.memory: 16Gi
    pods: "20"`,
  },
  limitrange: {
    apiVersion: 'v1', kind: 'LimitRange',
    body: `spec:
  limits:
    - type: Container
      default:
        cpu: 500m
        memory: 512Mi
      defaultRequest:
        cpu: 100m
        memory: 128Mi`,
  },
}

export function createK8sResourceTemplate(resourceType, namespace) {
  const key = String(resourceType || '').toLowerCase()
  const template = resourceTemplates[key]
  if (!template) throw new Error('不支持的资源类型。')
  const metadata = `metadata:\n  name: example-${key}${template.clusterScoped ? '' : `\n  namespace: ${JSON.stringify(namespace || 'default')}`}`
  return {
    kind: template.kind,
    yaml: `apiVersion: ${template.apiVersion}\nkind: ${template.kind}\n${metadata}\n${template.body ? `${template.body}\n` : ''}`,
  }
}

const memoryUnitFactors = {
  '': 1, n: 1e-9, u: 1e-6, m: 1e-3,
  k: 1e3, K: 1e3, M: 1e6, G: 1e9, T: 1e12, P: 1e15, E: 1e18,
  Ki: 1024, Mi: 1024 ** 2, Gi: 1024 ** 3, Ti: 1024 ** 4, Pi: 1024 ** 5, Ei: 1024 ** 6,
}

export function formatK8sMemory(value) {
  const match = String(value ?? '').trim().match(/^([+]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)([KMGTPE]i|[kKMGTPE]|[num]?)$/)
  if (!match) return '—'
  const bytes = Number(match[1]) * memoryUnitFactors[match[2]]
  if (!Number.isFinite(bytes)) return '—'
  return `${(bytes / 1024 ** 3).toLocaleString('zh-CN', { maximumFractionDigits: 2 })} G`
}
