<template>
  <div class="fade-in workbench-page-shell k8s-page-shell">
    <section class="hero panel k8s-hero">
      <div class="release-hero-copy">
        <div class="release-hero-title-row release-hero-title-inline">
          <span class="release-header-icon k8s-header-icon"><el-icon><Monitor /></el-icon></span>
          <h2>K8s 集群管理</h2>
          <p class="subtitle inline-subtitle k8s-hero-desc">统一查看集群、工作负载、网络与存储。</p>
        </div>
      </div>
    </section>

    <div class="neo-tabs theme-blue k8s-main-tabs">
      <button v-for="tab in visibleMainTabs" :key="tab.key" class="neo-tab-btn" :class="{ active: activeTab === tab.key }" @click="switchTab(tab.key)">
        <el-icon style="margin-right:4px;"><component :is="tab.icon" /></el-icon>
        {{ tab.label }}
      </button>
    </div>

    <div v-if="activeTab !== 'clusters' && selectedClusterId && !selectedClusterConnected" class="empty-state">
      <div class="empty-icon">⚙</div>
      <div class="empty-text">当前集群未连接，请先测试连接或切换到已连接集群。</div>
      <div style="display:flex;gap:8px;margin-top:8px;">
        <el-button type="primary" @click="switchTab('clusters')">前往集群管理</el-button>
        <el-button @click="refreshView">重新加载</el-button>
      </div>
    </div>

    <template v-if="activeTab === 'clusters'">
      <div class="workbench-card k8s-cluster-card">
        <div class="section-toolbar">
          <div class="toolbar-head">
            <span class="toolbar-title">集群列表</span>
            <span class="toolbar-desc">统一管理已接入的 K8s 集群。</span>
          </div>
          <div class="workbench-card-actions">
            <el-button class="filter-refresh-btn" @click="fetchClusters">
              <el-icon><RefreshRight /></el-icon>
              刷新
            </el-button>
            <el-button v-if="canCreateCluster" class="filter-refresh-btn" @click="openClusterDialog()">
              <el-icon><Plus /></el-icon>
              新增集群
            </el-button>
          </div>
        </div>
        <div class="workbench-toolbar workbench-toolbar--history k8s-cluster-toolbar">
          <div class="workbench-toolbar-left">
            <el-input v-model="tableSearchKeyword" clearable placeholder="搜索集群名称 / API Server / 描述" class="k8s-cluster-search" />
          </div>
          <div class="workbench-toolbar-right">
            <el-tag type="info" effect="plain">集群总数 {{ clusters.length }}</el-tag>
            <el-tag type="success" effect="plain">运行中 {{ clusters.filter(item => item.status === 'connected').length }}</el-tag>
          </div>
        </div>
        <div class="k8s-cluster-layout">
          <div v-loading="clustersLoading" class="k8s-cluster-selector">
            <div class="source-grid k8s-source-grid">
              <article
                v-for="cluster in filterRows(clusters, ['name', 'api_server', 'status', 'description'])"
                :key="cluster.id"
                class="source-card k8s-source-card"
                :class="{ 'source-card--selected': cluster.id === selectedClusterId, 'source-card--unavailable': cluster.status !== 'connected' }"
              >
                <div class="source-card-topline">
                  <div class="source-provider-mark">Kubernetes</div>
                  <el-tag size="small" :type="cluster.status === 'connected' ? 'success' : 'info'" effect="plain">
                    {{ cluster.status === 'connected' ? '在线' : '未连接' }}
                  </el-tag>
                </div>
                <strong class="source-account-name" :title="cluster.name">{{ cluster.name }}</strong>
                <span class="source-account-id">{{ clusterOptionMeta(cluster) }}</span>
                <dl class="source-meta-list">
                  <div><dt>API Server</dt><dd :title="cluster.api_server">{{ cluster.api_server || '--' }}</dd></div>
                  <div><dt>描述</dt><dd :title="cluster.description">{{ cluster.description || '--' }}</dd></div>
                </dl>
                <div class="source-card-footer">
                  <div class="source-card-actions">
                    <el-button v-if="canAdminCluster(cluster)" link size="small" @click="testCluster(cluster)">测试</el-button>
                    <el-button v-if="canAdminCluster(cluster)" link size="small" @click="openClusterDialog(cluster)">编辑</el-button>
                    <el-popconfirm v-if="canAdminCluster(cluster)" title="确定删除该集群？" @confirm="delCluster(cluster)">
                      <template #reference><el-button link type="danger" size="small">删除</el-button></template>
                    </el-popconfirm>
                  </div>
                  <el-button
                    size="small"
                    :type="cluster.id === selectedClusterId ? 'default' : 'primary'"
                    :plain="cluster.id !== selectedClusterId"
                    :disabled="cluster.id === selectedClusterId"
                    @click="selectCluster(cluster)"
                  >{{ cluster.id === selectedClusterId ? '已选择' : '选择集群' }}</el-button>
                </div>
              </article>
            </div>
          </div>

          <aside class="selected-cluster-panel">
            <template v-if="selectedCluster">
              <div class="selected-cluster-heading">
                <div class="selected-cluster-heading-copy">
                  <span>集群概要</span>
                  <strong>{{ selectedCluster.name }}</strong>
                </div>
                <div class="selected-cluster-heading-actions">
                  <el-tag size="small" :type="selectedCluster.status === 'connected' ? 'success' : 'info'" effect="plain" :title="selectedCluster.status === 'connected' ? '可访问 Kubernetes API' : '请先测试集群连接'">
                    {{ selectedCluster.status === 'connected' ? '在线' : '未连接' }}
                  </el-tag>
                  <el-button v-if="canK8sTerminal && selectedClusterConnected" size="small" plain type="primary" @click.stop="showClusterConsole">
                    <el-icon><Monitor /></el-icon><span>集群控制台</span>
                  </el-button>
                </div>
              </div>
              <K8sClusterCapacity :data="capacitySnapshot" :loading="capacityLoading" :scoped="Boolean(selectedCluster.access_scope?.namespaces?.length)" :error="capacityError" />
              <div class="selected-cluster-stat-grid">
                <div v-for="stat in selectedClusterStats" :key="stat.label" class="selected-cluster-stat" :class="stat.tone" :title="stat.detail || `${stat.label} ${stat.value}`">
                  <span>{{ stat.label }}</span>
                  <strong>{{ stat.value }}</strong>
                </div>
              </div>
              <dl class="selected-cluster-meta">
                <div><dt>API Server</dt><dd :title="selectedCluster.api_server">{{ selectedCluster.api_server || '--' }}</dd></div>
                <div><dt>集群版本</dt><dd>{{ summary.server_version || '—' }}</dd></div>
                <div v-if="selectedCluster.description"><dt>描述</dt><dd :title="selectedCluster.description">{{ selectedCluster.description }}</dd></div>
              </dl>
            </template>
            <el-empty v-else description="请选择一个集群" :image-size="72" />
          </aside>
        </div>
      </div>
    </template>

    <template v-else-if="selectedClusterId">
      <div class="workbench-card k8s-resource-card">
        <div class="section-toolbar">
          <div class="toolbar-head">
            <span class="toolbar-title">{{ resourcePanelTitle }}</span>
            <span class="toolbar-desc">{{ resourcePanelDesc }}</span>
          </div>
          <div v-if="['workloads', 'network', 'storage', 'config', 'extended'].includes(activeTab)" class="workbench-card-actions k8s-resource-header-actions">
            <div v-if="activeTab === 'workloads'" class="k8s-subtab-switch">
              <button v-for="st in workloadSubTabs" :key="st" type="button" :class="{ active: workloadSub === st }" @click="workloadSub = st">{{ st }}</button>
            </div>
            <div v-else-if="activeTab === 'network'" class="k8s-subtab-switch">
              <button v-for="st in networkSubTabs" :key="st" type="button" :class="{ active: networkSub === st }" @click="networkSub = st">{{ st }}</button>
            </div>
            <div v-else-if="activeTab === 'storage'" class="k8s-subtab-switch">
              <button v-for="st in storageSubTabs" :key="st" type="button" :class="{ active: storageSub === st }" @click="storageSub = st">{{ st }}</button>
            </div>
            <div v-else-if="activeTab === 'config'" class="k8s-subtab-switch">
              <button v-for="st in configSubTabs" :key="st" type="button" :class="{ active: configSub === st }" @click="configSub = st">{{ st }}</button>
            </div>
            <div v-else-if="activeTab === 'extended'" class="k8s-subtab-switch">
              <button v-for="(label, key) in extendedTypes" :key="key" type="button" :class="{ active: extendedType === key }" @click="extendedType = key; fetchCurrentTab()">{{ label }}</button>
            </div>
          </div>
        </div>

        <div class="workbench-toolbar workbench-toolbar--history filter-bar--context">
          <div class="workbench-toolbar-left">
            <div class="filter-inline-group filter-inline-group--nowrap">
              <div class="current-data-source current-runtime-context" :title="selectedCluster?.name || '暂未选择集群'">
                <el-icon><Connection /></el-icon>
                <span>当前集群</span>
                <strong>{{ selectedCluster?.name || '暂未选择' }}</strong>
              </div>
              <div v-if="needsNamespace" class="filter-inline-context">
                <span class="filter-inline-label">当前命名空间</span>
                <el-select
                  v-model="selectedNamespace"
                  placeholder="选择命名空间"
                  @change="fetchCurrentTab"
                  class="industrial-select toolbar-filter-select filter-inline-select filter-inline-select--namespace"
                  popper-class="k8s-context-popper k8s-context-popper--namespace"
                  :popper-style="namespacePopperStyle"
                >
                  <template #empty>
                    <div class="context-dropdown-empty">当前集群未返回命名空间</div>
                  </template>
                  <el-option label="全部命名空间" value="_all">
                    <div class="context-option-row context-option-row--all">
                      <div class="context-option-main">
                        <div class="context-option-head">
                          <span class="context-option-title">全部命名空间</span>
                          <span class="context-status-pill context-status-pill--info">ALL</span>
                        </div>
                        <span class="context-option-subtitle">跨命名空间聚合视图</span>
                      </div>
                    </div>
                  </el-option>
                  <el-option v-for="ns in namespaceOptions" :key="ns.name" :label="ns.name" :value="ns.name">
                    <div class="context-option-row">
                      <div class="context-option-main">
                        <div class="context-option-head">
                          <span class="context-option-title">{{ ns.name }}</span>
                          <span
                            class="context-status-pill"
                            :class="namespaceStatusTagClass(ns.status)"
                          >
                            {{ namespaceStatusText(ns.status) }}
                          </span>
                        </div>
                        <span class="context-option-subtitle">{{ namespaceOptionMeta(ns) }}</span>
                      </div>
                    </div>
                  </el-option>
                </el-select>
              </div>
            </div>
            <el-input v-model="tableSearchKeyword" clearable placeholder="搜索当前列表名称、镜像、IP 或描述" style="width: 320px" />
          </div>
          <div class="workbench-toolbar-right k8s-context-toolbar-right">
            <el-button v-if="canCreateResource" type="primary" plain @click="yamlEditor?.open(selectedCluster, selectedNamespace, createResourceType)"><el-icon><Plus /></el-icon>YAML 创建</el-button>
            <el-select v-model="autoRefreshSeconds" style="width:116px" aria-label="自动刷新间隔">
              <el-option label="手动刷新" :value="0" /><el-option label="每 15 秒" :value="15" /><el-option label="每 30 秒" :value="30" /><el-option label="每 60 秒" :value="60" />
            </el-select>
            <el-tag v-if="summary.pvcs_pending" size="large" type="warning">PVC Pending {{ summary.pvcs_pending }}</el-tag>
            <el-button class="filter-refresh-btn" @click="refreshView"><el-icon><RefreshRight /></el-icon>刷新</el-button>
          </div>
        </div>

        <el-table v-if="activeTab === 'extended'" :data="pagedResourceRows" :row-key="resourceRowKey" stripe v-loading="loading">
          <el-table-column prop="name" label="名称" min-width="220" />
          <el-table-column prop="namespace" label="命名空间" width="160" />
          <el-table-column label="配置摘要" min-width="280"><template #default="{ row }"><code>{{ JSON.stringify(row.spec || {}) }}</code></template></el-table-column>
          <el-table-column label="Age" width="88"><template #default="{ row }">{{ resourceAge(row.created) }}</template></el-table-column>
          <el-table-column label="操作" width="72"><template #default="{ row }"><K8sResourceActions :actions="resourceActions(extendedType, row)" @select="handleResourceAction($event, row)" /></template></el-table-column>
        </el-table>
        <template v-if="activeTab === 'nodes'">
      <el-table :data="pagedResourceRows" :row-key="resourceRowKey" stripe v-loading="loading" style="width:100%">
        <el-table-column label="调度" width="100"><template #default="{ row }"><el-tag :type="row.unschedulable ? 'warning' : 'success'" size="small">{{ row.unschedulable ? '已禁止' : '可调度' }}</el-tag></template></el-table-column>
        <el-table-column prop="name" label="节点名称" min-width="180">
          <template #default="{ row }">
            <div style="display:flex;align-items:center;gap:8px;">
              <span class="state-pulse" :class="row.status==='Ready'?'running':'exited'"></span>
              <span style="font-weight:600;font-family:'Cascadia Code','Consolas',monospace;font-size:13px;">{{ row.name }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="90">
            <template #default="{ row }"><el-tag :type="row.status === 'Ready' ? 'success' : 'danger'" size="small">{{ row.status === 'Ready' ? '就绪' : '未就绪' }}</el-tag></template>
        </el-table-column>
        <el-table-column prop="roles" label="角色" width="120">
          <template #default="{ row }"><el-tag size="small" type="info">{{ row.roles }}</el-tag></template>
        </el-table-column>
        <el-table-column prop="version" label="Kubelet 版本" width="120" />
        <el-table-column prop="internal_ip" label="内部 IP" width="140" />
        <el-table-column label="Age" width="88"><template #default="{ row }">{{ resourceAge(row.created) }}</template></el-table-column>
        <el-table-column label="CPU/内存" width="150">
          <template #default="{ row }">
            <div style="font-size:12px">CPU: <b>{{ row.cpu }}</b></div>
            <div style="font-size:12px">Memory: <b>{{ formatK8sMemory(row.memory) }}</b></div>
          </template>
        </el-table-column>
        <el-table-column prop="os_image" label="系统" min-width="180" show-overflow-tooltip />
        <el-table-column label="操作" width="72" fixed="right">
          <template #default="{ row }"><K8sResourceActions :actions="resourceActions('node', row)" @select="handleResourceAction($event, row)" /></template>
        </el-table-column>
      </el-table>
        </template>

    <!-- ============ 命名空间 ============ -->
        <template v-if="activeTab === 'namespaces'">
      <el-table :data="pagedResourceRows" :row-key="resourceRowKey" stripe v-loading="loading" style="width:100%">
        <el-table-column prop="name" label="命名空间名称" min-width="200">
          <template #default="{ row }">
            <div style="display:flex;align-items:center;gap:8px;">
              <span class="state-pulse" :class="row.status==='Active'?'running':'exited'"></span>
              <span style="font-weight:600;font-family:'Cascadia Code','Consolas',monospace;font-size:13px;">{{ row.name }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }"><el-tag :type="row.status==='Active'?'success':'danger'" size="small">{{ row.status==='Active'?'活跃':'终止' }}</el-tag></template>
        </el-table-column>
        <el-table-column label="标签" width="80"><template #default="{ row }">{{ row.labelCount || 0 }}</template></el-table-column>
        <el-table-column label="Age" width="100"><template #default="{ row }">{{ resourceAge(row.created) }}</template></el-table-column>
        <el-table-column label="操作" width="72" fixed="right">
          <template #default="{ row }"><K8sResourceActions :actions="resourceActions('namespace', row)" @select="handleResourceAction($event, row)" /></template>
        </el-table-column>
      </el-table>
        </template>

    <!-- ============ 工作负载 / Pods ============ -->
        <template v-if="activeTab === 'workloads' && workloadSub === 'Pod'">
      <el-table :data="pagedResourceRows" :row-key="resourceRowKey" stripe v-loading="loading" style="width:100%">
        <el-table-column prop="name" label="Pod 名称" min-width="260">
          <template #default="{ row }">
            <div style="display:flex;align-items:center;gap:8px;">
              <span class="state-pulse" :class="row.status==='Running'?'running':row.status==='Pending'?'restarting':'exited'"></span>
              <span style="font-weight:600;font-family:'Cascadia Code','Consolas',monospace;font-size:12px;">{{ row.name }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="namespace" label="命名空间" width="130" />
        <el-table-column label="容器" min-width="120">
          <template #default="{ row }">
            <div class="pod-container-readiness" :title="normalizeContainerNames(row.containers).join(', ')">
              <span v-for="container in row.containers || []" :key="typeof container === 'string' ? container : container.name" class="pod-container-dot" :class="{ 'is-ready': typeof container === 'string' || container.ready }"></span>
              <span>{{ normalizeContainerNames(row.containers).length }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="restarts" label="重启次数" width="80">
          <template #default="{ row }">
            <span :style="{ color: row.restarts > 0 ? '#f59e0b' : '#10b981', fontWeight: 600 }">{{ row.restarts }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="controlled_by" label="受控对象" min-width="190" show-overflow-tooltip />
        <el-table-column prop="node" label="节点" width="140" show-overflow-tooltip />
        <el-table-column prop="qos" label="QoS" width="105"><template #default="{ row }">{{ row.qos || '-' }}</template></el-table-column>
        <el-table-column label="Age" width="88"><template #default="{ row }">{{ resourceAge(row.created) }}</template></el-table-column>
        <el-table-column prop="status" label="状态" width="110">
          <template #default="{ row }">
            <el-tag :type="row.status==='Running'?'success':row.status==='Pending'?'warning':'danger'" size="small">{{ row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="72" fixed="right">
          <template #default="{ row }"><K8sResourceActions :actions="resourceActions('pod', row)" @select="handleResourceAction($event, row)" /></template>
        </el-table-column>
      </el-table>
        </template>

        <template v-if="activeTab === 'workloads'">
      <el-table v-if="workloadSub==='Deployment'" :data="pagedResourceRows" :row-key="resourceRowKey" stripe v-loading="loading" style="width:100%">
        <el-table-column prop="name" label="名称" min-width="220">
          <template #default="{ row }">
            <div style="display:flex;align-items:center;gap:8px;">
              <span class="state-pulse" :class="row.ready_replicas===row.replicas?'running':'restarting'"></span>
              <span style="font-weight:600;font-family:'Cascadia Code','Consolas',monospace;font-size:13px;">{{ row.name }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="namespace" label="命名空间" width="130" />
        <el-table-column label="副本数" width="100"><template #default="{ row }"><span :style="{color:row.ready_replicas===row.replicas?'#10b981':'#f59e0b',fontWeight:600}">{{ row.ready_replicas }}/{{ row.replicas }}</span></template></el-table-column>
        <el-table-column prop="available_replicas" label="可用" width="78" />
        <el-table-column prop="images" label="镜像" min-width="240" show-overflow-tooltip />
        <el-table-column label="Age" width="88"><template #default="{ row }">{{ resourceAge(row.created) }}</template></el-table-column>
        <el-table-column label="操作" width="72" fixed="right">
          <template #default="{ row }"><K8sResourceActions :actions="resourceActions('deployment', row)" @select="handleResourceAction($event, row)" /></template>
        </el-table-column>
      </el-table>
      <el-table v-if="workloadSub==='StatefulSet'" :data="pagedResourceRows" :row-key="resourceRowKey" stripe v-loading="loading" style="width:100%">
        <el-table-column prop="name" label="名称" min-width="220">
          <template #default="{ row }">
            <div style="display:flex;align-items:center;gap:8px;">
              <span class="state-pulse" :class="row.ready_replicas===row.replicas?'running':'restarting'"></span>
              <span style="font-weight:600;font-family:'Cascadia Code','Consolas',monospace;font-size:13px;">{{ row.name }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="namespace" label="命名空间" width="130" />
        <el-table-column label="副本数" width="100"><template #default="{ row }"><span :style="{color:row.ready_replicas===row.replicas?'#10b981':'#f59e0b',fontWeight:600}">{{ row.ready_replicas }}/{{ row.replicas }}</span></template></el-table-column>
        <el-table-column prop="current_replicas" label="当前" width="76"><template #default="{ row }">{{ row.current_replicas ?? '-' }}</template></el-table-column>
        <el-table-column prop="images" label="镜像" min-width="240" show-overflow-tooltip />
        <el-table-column label="Age" width="88"><template #default="{ row }">{{ resourceAge(row.created) }}</template></el-table-column>
        <el-table-column label="操作" width="72" fixed="right">
          <template #default="{ row }"><K8sResourceActions :actions="resourceActions('statefulset', row)" @select="handleResourceAction($event, row)" /></template>
        </el-table-column>
      </el-table>
      <el-table v-if="workloadSub==='DaemonSet'" :data="pagedResourceRows" :row-key="resourceRowKey" stripe v-loading="loading" style="width:100%">
        <el-table-column prop="name" label="名称" min-width="220">
          <template #default="{ row }">
            <div style="display:flex;align-items:center;gap:8px;">
              <span class="state-pulse" :class="row.ready===row.desired?'running':'restarting'"></span>
              <span style="font-weight:600;font-family:'Cascadia Code','Consolas',monospace;font-size:13px;">{{ row.name }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="namespace" label="命名空间" width="130" />
        <el-table-column label="就绪数" width="100"><template #default="{ row }"><span :style="{color:row.ready===row.desired?'#10b981':'#f59e0b',fontWeight:600}">{{ row.ready }}/{{ row.desired }}</span></template></el-table-column>
        <el-table-column prop="current" label="当前" width="76" />
        <el-table-column prop="images" label="镜像" min-width="240" show-overflow-tooltip />
        <el-table-column label="Age" width="88"><template #default="{ row }">{{ resourceAge(row.created) }}</template></el-table-column>
        <el-table-column label="操作" width="72" fixed="right">
          <template #default="{ row }"><K8sResourceActions :actions="resourceActions('daemonset', row)" @select="handleResourceAction($event, row)" /></template>
        </el-table-column>
      </el-table>
      <el-table v-if="workloadSub==='Job'" :data="pagedResourceRows" :row-key="resourceRowKey" stripe v-loading="loading" style="width:100%">
        <el-table-column prop="name" label="名称" min-width="220">
          <template #default="{ row }">
            <div style="display:flex;align-items:center;gap:8px;">
              <span class="state-pulse" :class="row.status==='Complete'?'running':'restarting'"></span>
              <span style="font-weight:600;font-family:'Cascadia Code','Consolas',monospace;font-size:13px;">{{ row.name }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="namespace" label="命名空间" width="130" />
        <el-table-column prop="completions" label="完成数" width="100" />
        <el-table-column prop="status" label="状态" width="100"><template #default="{ row }"><el-tag :type="row.status==='Complete'?'success':'warning'" size="small">{{ row.status }}</el-tag></template></el-table-column>
        <el-table-column prop="duration" label="耗时" width="90" />
        <el-table-column prop="images" label="镜像" min-width="160" show-overflow-tooltip />
        <el-table-column label="Age" width="88"><template #default="{ row }">{{ resourceAge(row.created) }}</template></el-table-column>
        <el-table-column label="操作" width="72" fixed="right">
          <template #default="{ row }"><K8sResourceActions :actions="resourceActions('job', row)" @select="handleResourceAction($event, row)" /></template>
        </el-table-column>
      </el-table>
      <el-table v-if="workloadSub==='CronJob'" :data="pagedResourceRows" :row-key="resourceRowKey" stripe v-loading="loading" style="width:100%">
        <el-table-column prop="name" label="名称" min-width="200">
          <template #default="{ row }">
            <div style="display:flex;align-items:center;gap:8px;">
              <span class="state-pulse" :class="row.suspend?'exited':'running'"></span>
              <span style="font-weight:600;font-family:'Cascadia Code','Consolas',monospace;font-size:13px;">{{ row.name }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="namespace" label="命名空间" width="130" />
        <el-table-column prop="schedule" label="调度策略" width="140"><template #default="{ row }"><code style="font-size:12px;background:light-dark(#f1f5f9,var(--el-fill-color));padding:2px 6px;border-radius:3px">{{ row.schedule }}</code></template></el-table-column>
            <el-table-column label="是否暂停" width="88"><template #default="{ row }"><el-tag :type="row.suspend ? 'danger' : 'success'" size="small">{{ row.suspend ? '是' : '否' }}</el-tag></template></el-table-column>
        <el-table-column prop="active" label="活动数" width="78" />
        <el-table-column prop="last_schedule" label="最近调度" min-width="140" show-overflow-tooltip />
        <el-table-column label="Age" width="88"><template #default="{ row }">{{ resourceAge(row.created) }}</template></el-table-column>
        <el-table-column label="操作" width="72" fixed="right">
          <template #default="{ row }"><K8sResourceActions :actions="resourceActions('cronjob', row)" @select="handleResourceAction($event, row)" /></template>
        </el-table-column>
      </el-table>
        </template>

        <template v-if="activeTab === 'network'">
      <el-table v-if="networkSub==='Service'" :data="pagedResourceRows" :row-key="resourceRowKey" stripe v-loading="loading" style="width:100%">
        <el-table-column prop="name" label="名称" min-width="200">
          <template #default="{ row }">
            <div style="display:flex;align-items:center;gap:8px;">
              <span class="state-pulse" :class="'running'"></span>
              <span style="font-weight:600;font-family:'Cascadia Code','Consolas',monospace;font-size:13px;">{{ row.name }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="namespace" label="命名空间" width="130" />
        <el-table-column prop="type" label="类型" width="110"><template #default="{ row }"><el-tag size="small" :type="row.type==='LoadBalancer'?'warning':row.type==='NodePort'?'success':'info'">{{ row.type }}</el-tag></template></el-table-column>
        <el-table-column prop="cluster_ip" label="Cluster IP" width="140" />
        <el-table-column prop="external_ip" label="External IP" width="140" show-overflow-tooltip />
        <el-table-column prop="ports" label="端口" min-width="200" show-overflow-tooltip />
        <el-table-column label="Age" width="88"><template #default="{ row }">{{ resourceAge(row.created) }}</template></el-table-column>
        <el-table-column label="操作" width="72" fixed="right">
          <template #default="{ row }"><K8sResourceActions :actions="resourceActions('service', row)" @select="handleResourceAction($event, row)" /></template>
        </el-table-column>
      </el-table>
      <el-table v-if="networkSub==='Ingress'" :data="pagedResourceRows" :row-key="resourceRowKey" stripe v-loading="loading" style="width:100%">
        <el-table-column prop="name" label="名称" min-width="180">
          <template #default="{ row }">
            <div style="display:flex;align-items:center;gap:8px;">
              <span class="state-pulse" :class="'running'"></span>
              <span style="font-weight:600;font-family:'Cascadia Code','Consolas',monospace;font-size:13px;">{{ row.name }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="namespace" label="命名空间" width="130" />
        <el-table-column prop="class" label="Ingress Class" width="120" />
        <el-table-column prop="hosts" label="域名" min-width="200" show-overflow-tooltip />
        <el-table-column prop="address" label="地址" width="140" />
        <el-table-column prop="ports" label="端口" width="100" />
        <el-table-column label="Age" width="88"><template #default="{ row }">{{ resourceAge(row.created) }}</template></el-table-column>
        <el-table-column label="操作" width="72" fixed="right">
          <template #default="{ row }"><K8sResourceActions :actions="resourceActions('ingress', row)" @select="handleResourceAction($event, row)" /></template>
        </el-table-column>
      </el-table>
      <el-table v-if="networkSub === 'Endpoints'" :data="pagedResourceRows" :row-key="resourceRowKey" stripe v-loading="loading" style="width:100%">
        <el-table-column prop="name" label="名称" min-width="200" show-overflow-tooltip />
        <el-table-column prop="namespace" label="命名空间" width="130" />
        <el-table-column prop="addresses" label="Ready 地址" min-width="220" show-overflow-tooltip><template #default="{ row }">{{ row.addresses || '—' }}</template></el-table-column>
        <el-table-column prop="not_ready_addresses" label="NotReady 地址" min-width="180" show-overflow-tooltip><template #default="{ row }">{{ row.not_ready_addresses || '—' }}</template></el-table-column>
        <el-table-column prop="ports" label="端口" min-width="140" show-overflow-tooltip />
        <el-table-column label="Age" width="88"><template #default="{ row }">{{ resourceAge(row.created) }}</template></el-table-column>
        <el-table-column label="操作" width="72" fixed="right"><template #default="{ row }"><K8sResourceActions :actions="resourceActions('endpoints', row)" @select="handleResourceAction($event, row)" /></template></el-table-column>
      </el-table>
      <el-table v-if="networkSub === 'IngressClass'" :data="pagedResourceRows" :row-key="resourceRowKey" stripe v-loading="loading" style="width:100%">
        <el-table-column prop="name" label="名称" min-width="200" show-overflow-tooltip />
        <el-table-column prop="spec.controller" label="Controller" min-width="280" show-overflow-tooltip />
        <el-table-column label="默认类" width="100"><template #default="{ row }"><el-tag size="small" :type="row.is_default ? 'success' : 'info'">{{ row.is_default ? '是' : '否' }}</el-tag></template></el-table-column>
        <el-table-column label="Age" width="88"><template #default="{ row }">{{ resourceAge(row.created) }}</template></el-table-column>
        <el-table-column label="操作" width="72" fixed="right"><template #default="{ row }"><K8sResourceActions :actions="resourceActions('ingressclass', row)" @select="handleResourceAction($event, row)" /></template></el-table-column>
      </el-table>
      <el-table v-if="networkSub === 'NetworkPolicy'" :data="pagedResourceRows" :row-key="resourceRowKey" stripe v-loading="loading" style="width:100%">
        <el-table-column prop="name" label="名称" min-width="200" show-overflow-tooltip />
        <el-table-column prop="namespace" label="命名空间" width="130" />
        <el-table-column label="Pod Selector" min-width="260" show-overflow-tooltip><template #default="{ row }">{{ JSON.stringify(row.spec?.podSelector || {}) }}</template></el-table-column>
        <el-table-column label="Policy Types" min-width="160"><template #default="{ row }">{{ (row.spec?.policyTypes || []).join(', ') || '—' }}</template></el-table-column>
        <el-table-column label="Age" width="88"><template #default="{ row }">{{ resourceAge(row.created) }}</template></el-table-column>
        <el-table-column label="操作" width="72" fixed="right"><template #default="{ row }"><K8sResourceActions :actions="resourceActions('networkpolicy', row)" @select="handleResourceAction($event, row)" /></template></el-table-column>
      </el-table>
        </template>

    <!-- ============ 存储管理 ============ -->
        <template v-if="activeTab === 'storage'">
      <el-table v-if="storageSub==='PV'" :data="pagedResourceRows" :row-key="resourceRowKey" stripe v-loading="loading" style="width:100%">
        <el-table-column prop="name" label="名称" min-width="200">
          <template #default="{ row }">
            <div style="display:flex;align-items:center;gap:8px;">
              <span class="state-pulse" :class="row.status==='Bound'?'running':row.status==='Available'?'running':'warning'"></span>
              <span style="font-weight:600;font-family:'Cascadia Code','Consolas',monospace;font-size:13px;">{{ row.name }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="capacity" label="容量" width="90" />
        <el-table-column prop="access_modes" label="访问模式" width="100" />
        <el-table-column prop="reclaim_policy" label="回收策略" width="100" />
        <el-table-column prop="status" label="状态" width="90"><template #default="{ row }"><el-tag :type="row.status==='Bound'?'success':row.status==='Available'?'info':'warning'" size="small">{{ row.status }}</el-tag></template></el-table-column>
        <el-table-column prop="claim" label="绑定声明" min-width="250" show-overflow-tooltip />
        <el-table-column prop="storage_class" label="存储类" width="120" />
        <el-table-column label="Age" width="88"><template #default="{ row }">{{ resourceAge(row.created) }}</template></el-table-column>
        <el-table-column label="操作" width="72" fixed="right">
          <template #default="{ row }"><K8sResourceActions :actions="resourceActions('pv', row)" @select="handleResourceAction($event, row)" /></template>
        </el-table-column>
      </el-table>
      <el-table v-if="storageSub==='PVC'" :data="pagedResourceRows" :row-key="resourceRowKey" stripe v-loading="loading" style="width:100%">
        <el-table-column prop="name" label="名称" min-width="240">
          <template #default="{ row }">
            <div style="display:flex;align-items:center;gap:8px;">
              <span class="state-pulse" :class="row.status==='Bound'?'running':'warning'"></span>
              <span style="font-weight:600;font-family:'Cascadia Code','Consolas',monospace;font-size:13px;">{{ row.name }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="namespace" label="命名空间" width="130" />
        <el-table-column prop="status" label="状态" width="90"><template #default="{ row }"><el-tag :type="row.status==='Bound'?'success':'warning'" size="small">{{ row.status }}</el-tag></template></el-table-column>
        <el-table-column prop="capacity" label="容量" width="90" />
        <el-table-column prop="access_modes" label="访问模式" width="100" />
        <el-table-column prop="storage_class" label="存储类" width="120" />
        <el-table-column prop="volume" label="PV" min-width="180" show-overflow-tooltip />
        <el-table-column label="Age" width="88"><template #default="{ row }">{{ resourceAge(row.created) }}</template></el-table-column>
        <el-table-column label="操作" width="72" fixed="right">
          <template #default="{ row }"><K8sResourceActions :actions="resourceActions('pvc', row)" @select="handleResourceAction($event, row)" /></template>
        </el-table-column>
      </el-table>
      <el-table v-if="storageSub==='StorageClass'" :data="pagedResourceRows" :row-key="resourceRowKey" stripe v-loading="loading" style="width:100%">
        <el-table-column prop="name" label="名称" min-width="160">
          <template #default="{ row }">
            <div style="display:flex;align-items:center;gap:8px;">
              <span class="state-pulse" :class="'running'"></span>
              <span style="font-weight:600;font-family:'Cascadia Code','Consolas',monospace;font-size:13px;">{{ row.name }}</span>
              <el-tag v-if="row.is_default" type="primary" size="small" style="margin-left:6px">默认</el-tag>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="provisioner" label="Provisioner" min-width="220" show-overflow-tooltip />
        <el-table-column prop="reclaim_policy" label="回收策略" width="100" />
        <el-table-column prop="binding_mode" label="绑定模式" width="180" />
            <el-table-column label="允许扩展" width="90"><template #default="{ row }"><el-tag :type="row.allow_expansion ? 'success' : 'info'" size="small">{{ row.allow_expansion ? '是' : '否' }}</el-tag></template></el-table-column>
        <el-table-column label="Age" width="88"><template #default="{ row }">{{ resourceAge(row.created) }}</template></el-table-column>
        <el-table-column label="操作" width="72" fixed="right">
          <template #default="{ row }"><K8sResourceActions :actions="resourceActions('storageclass', row)" @select="handleResourceAction($event, row)" /></template>
        </el-table-column>
      </el-table>
        </template>

    <!-- ============ 配置管理 ============ -->
        <template v-if="activeTab === 'config'">
      <el-table v-if="configSub==='ConfigMap'" :data="pagedResourceRows" :row-key="resourceRowKey" stripe v-loading="loading" style="width:100%">
        <el-table-column prop="name" label="名称" min-width="250">
          <template #default="{ row }">
            <div style="display:flex;align-items:center;gap:8px;">
              <span class="state-pulse" :class="'running'"></span>
              <span style="font-weight:600;font-family:'Cascadia Code','Consolas',monospace;font-size:13px;">{{ row.name }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="namespace" label="命名空间" width="130" />
        <el-table-column prop="data_count" label="键值数" width="100" />
        <el-table-column label="Age" width="88"><template #default="{ row }">{{ resourceAge(row.created) }}</template></el-table-column>
        <el-table-column label="操作" width="72" fixed="right">
          <template #default="{ row }"><K8sResourceActions :actions="resourceActions('configmap', row)" @select="handleResourceAction($event, row)" /></template>
        </el-table-column>
      </el-table>
      <el-table v-if="configSub==='Secret'" :data="pagedResourceRows" :row-key="resourceRowKey" stripe v-loading="loading" style="width:100%">
        <el-table-column prop="name" label="名称" min-width="250">
          <template #default="{ row }">
            <div style="display:flex;align-items:center;gap:8px;">
              <span class="state-pulse" :class="'running'"></span>
              <span style="font-weight:600;font-family:'Cascadia Code','Consolas',monospace;font-size:13px;">{{ row.name }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="namespace" label="命名空间" width="130" />
        <el-table-column prop="type" label="类型" min-width="240"><template #default="{ row }"><code style="font-size:11px;background:light-dark(#f1f5f9,var(--el-fill-color));padding:2px 6px;border-radius:3px">{{ row.type }}</code></template></el-table-column>
        <el-table-column prop="data_count" label="键值数" width="100" />
        <el-table-column label="Age" width="88"><template #default="{ row }">{{ resourceAge(row.created) }}</template></el-table-column>
        <el-table-column label="操作" width="72" fixed="right">
          <template #default="{ row }"><K8sResourceActions :actions="resourceActions('secret', row)" @select="handleResourceAction($event, row)" /></template>
        </el-table-column>
      </el-table>
        </template>
        <el-pagination
          v-model:current-page="resourcePage"
          v-model:page-size="resourcePageSize"
          class="k8s-pagination"
          :page-sizes="[20, 50, 100]"
          :total="filteredResourceRows.length"
          layout="total, sizes, prev, pager, next"
          background
        />
      </div>
    </template>
    <template v-else>
      <div class="empty-state">
        <div class="empty-icon">⚙</div>
        <div class="empty-text">当前集群未连接，请先测试连接或切换到已连接集群。</div>
        <div style="display:flex;gap:8px;margin-top:8px;">
          <el-button type="primary" @click="switchTab('clusters')">前往集群管理</el-button>
          <el-button @click="refreshView">重新加载</el-button>
        </div>
      </div>
    </template>
<!-- ============ 集群弹窗 ============ -->
    <el-dialog :close-on-click-modal="false" class="workbench-edit-dialog" v-model="clusterDialogVisible" :title="editingClusterId ? '编辑集群' : '新增 K8s 集群'" width="90%" style="max-width:600px;" top="5vh" append-to-body destroy-on-close>
      <el-form class="workbench-editor-form--sectioned" label-position="top" :model="clusterForm" label-width="110px">
        <section class="workbench-editor-section">
          <div class="workbench-editor-heading"><span class="workbench-editor-step">01</span><h3>集群信息</h3></div>
          <div class="workbench-editor-grid">
            <el-form-item label="集群名称"><el-input v-model="clusterForm.name" placeholder="例如 prod-cluster" /></el-form-item>
            <el-form-item label="API Server"><el-input v-model="clusterForm.api_server" placeholder="填写证书匹配的域名或 IP，例如 https://k8s.example.com:6443（可选）" /></el-form-item>
            <el-form-item class="workbench-editor-full" label="描述"><el-input v-model="clusterForm.description" placeholder="集群用途描述" /></el-form-item>
          </div>
        </section>
        <section class="workbench-editor-section workbench-editor-section--tinted">
          <div class="workbench-editor-heading"><span class="workbench-editor-step">02</span><h3>连接凭据</h3></div>
          <div>
            <el-form-item label="KubeConfig"><el-input v-model="clusterForm.kubeconfig" type="textarea" :rows="12" placeholder="粘贴 kubeconfig YAML 内容" style="font-family:monospace;font-size:12px;" /></el-form-item>
          </div>
        </section>
      </el-form>
      <template #footer>
        <el-button @click="clusterDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="saveCluster" :loading="savingCluster">保存</el-button>
      </template>
    </el-dialog>

    <K8sTerminalDialog v-if="clusterConsoleDialogVisible" v-model="clusterConsoleDialogVisible" kind="cluster" :cluster="consoleCluster" />

    <!-- ============ YAML 查看弹窗 ============ -->
    <el-dialog v-model="yamlDialogVisible" class="k8s-yaml-dialog" :title="'YAML - ' + yamlResourceName" width="90%" style="max-width:800px;" top="3vh" append-to-body destroy-on-close>
      <div class="yaml-viewer-toolbar">
        <span class="yaml-viewer-badge">{{ yamlResourceType }}</span>
        <el-button size="small" type="primary" plain @click="copyYaml"><el-icon><DocumentCopy /></el-icon> 复制</el-button>
      </div>
      <div class="yaml-viewer-container" v-loading="yamlLoading">
        <pre class="yaml-viewer-code"><code>{{ yamlContent }}</code></pre>
      </div>
    </el-dialog>

    <!-- ============ Pod 详情弹窗 ============ -->
    <el-dialog v-model="podDialogVisible" :title="'Pod 列表 - ' + podWorkloadName" width="95%" style="max-width:1200px;" top="3vh" append-to-body destroy-on-close>
      <el-table :data="pagedPodList" :row-key="resourceRowKey" stripe v-loading="podLoading" style="width:100%" size="small">
        <el-table-column prop="name" label="Pod 名称" min-width="280">
          <template #default="{ row }">
            <div style="display:flex;align-items:center;gap:8px;">
              <span class="state-pulse" :class="row.status==='Running'?'running':row.status==='Pending'?'restarting':'exited'"></span>
              <span style="font-weight:600;font-family:'Cascadia Code','Consolas',monospace;font-size:12px;">{{ row.name }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="row.status==='Running'?'success':row.status==='Pending'?'warning':'danger'" size="small">{{ row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="restarts" label="重启" width="70">
          <template #default="{ row }">
            <span :style="{color: row.restarts > 0 ? '#f59e0b' : '#10b981', fontWeight: 600}">{{ row.restarts }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="node" label="节点" width="120" show-overflow-tooltip />
        <el-table-column label="IP 地址" width="160">
          <template #default="{ row }">
            <div style="font-size:11px;line-height:1.6">
              <div>Pod: <b style="color:var(--info)">{{ row.pod_ip || '-' }}</b></div>
              <div>Host: <span style="color:var(--text-secondary)">{{ row.host_ip || '-' }}</span></div>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="资源" width="150">
          <template #default="{ row }">
            <div style="font-size:11px;line-height:1.6">
              <div>CPU: <el-tag size="small" type="info" style="font-size:11px">{{ row.cpu_request }}</el-tag></div>
              <div>Mem: <el-tag size="small" type="info" style="font-size:11px">{{ row.memory_request }}</el-tag></div>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="age" label="运行时间" width="90">
          <template #default="{ row }">
            <span style="font-family:monospace;font-size:12px;color:var(--text-secondary)">{{ row.age }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="72" fixed="right">
          <template #default="{ row }"><K8sResourceActions :actions="resourceActions('pod', row)" @select="handleResourceAction($event, row)" /></template>
        </el-table-column>
      </el-table>
      <el-pagination v-model:current-page="podPage" :page-size="50" :total="filteredPodList.length" class="k8s-pagination" layout="total, prev, pager, next" background />
    </el-dialog>

    <!-- ============ 日志查看弹窗 ============ -->
    <K8sPodLogs v-if="logDialogVisible" v-model="logDialogVisible" :cluster="logCluster" :pod="logPod" />

    <!-- ============ 事件查看弹窗 ============ -->
    <el-dialog v-model="eventsDialogVisible" :title="'事件 - ' + eventsResourceName" width="90%" style="max-width:800px;" top="3vh" append-to-body destroy-on-close>
      <div v-loading="eventsLoading" style="min-height:120px;">
        <div v-if="eventsList.length === 0 && !eventsLoading" style="text-align:center;padding:40px;color:#94a3b8;">
          <el-icon :size="48" style="margin-bottom:8px;opacity:0.4"><Bell /></el-icon>
          <div>暂无事件</div>
        </div>
        <div v-else class="events-timeline">
          <div v-for="(ev, i) in eventsList" :key="i" class="event-item" :class="ev.type === 'Warning' ? 'event-warning' : 'event-normal'">
            <div class="event-indicator"></div>
            <div class="event-body">
              <div class="event-header">
                <el-tag :type="ev.type==='Warning'?'warning':''" size="small" effect="dark" style="font-size:11px">{{ ev.type }}</el-tag>
                <span class="event-reason">{{ ev.reason }}</span>
                <span v-if="ev.count > 1" class="event-count">×{{ ev.count }}</span>
                <span class="event-time">{{ formatEventTime(ev.last_time) }}</span>
              </div>
              <div class="event-message">{{ ev.message }}</div>
              <div class="event-source" v-if="ev.source">{{ ev.source }}</div>
            </div>
          </div>
        </div>
      </div>
    </el-dialog>

    <K8sTerminalDialog v-if="execDialogVisible" v-model="execDialogVisible" kind="pod" :cluster="execCluster" :pod="execPod" />

    <el-dialog :close-on-click-modal="false" class="workbench-edit-dialog" v-model="scaleDialogVisible" :title="'弹性伸缩 - ' + scaleForm.name" width="90%" style="max-width:420px;" top="5vh" append-to-body destroy-on-close>
      <el-form label-position="top" label-width="100px">
        <el-form-item label="工作负载">
          <el-tag>{{ scaleForm.workload_type }}</el-tag>
        </el-form-item>
        <el-form-item label="命名空间">
          <el-tag type="info">{{ scaleForm.namespace }}</el-tag>
        </el-form-item>
        <el-form-item label="副本数">
          <el-input-number v-model="scaleForm.replicas" :min="0" :max="200" controls-position="right" style="width:180px;" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="scaleDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="scaleLoading" @click="submitScale">应用</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="configEditorVisible" :title="configDialogTitle" width="90%" style="max-width:980px;" top="3vh" append-to-body destroy-on-close>
      <div class="filter-bar" style="margin-bottom:8px;">
        <el-tag type="info">{{ configForm.namespace }}</el-tag>
        <el-tag>{{ configForm.type }}</el-tag>
        <el-tag v-if="configForm.rollback_available" type="warning">可回滚</el-tag>
        <el-tag v-if="configForm.revision_count" type="success">历史 {{ configForm.revision_count }}</el-tag>
        <span class="config-editor-note">仅编辑 data/stringData，保存前建议先预览差异。</span>
      </div>
      <el-input v-model="configForm.content" type="textarea" :rows="18" placeholder="key: value" style="font-family:'Cascadia Code','Consolas',monospace;" />
      <div class="config-history-panel">
        <div class="config-history-head">
          <div class="config-history-title">
            <strong class="config-history-heading">历史版本</strong>
            <span class="config-history-note">每次保存前和回滚前都会自动留档，可随时预览差异并回滚到指定版本。</span>
          </div>
          <el-button size="small" plain :loading="configRevisionLoading" @click="fetchConfigRevisions">刷新历史</el-button>
        </div>
        <el-table :data="configRevisions" size="small" stripe v-loading="configRevisionLoading" max-height="220" empty-text="暂无历史版本">
          <el-table-column prop="created_at" label="时间" min-width="180" show-overflow-tooltip />
          <el-table-column prop="action" label="动作" width="110">
            <template #default="{ row }">
              <el-tag :type="row.action === 'rollback' ? 'warning' : 'info'" size="small">
                {{ row.action === 'rollback' ? '回滚前快照' : '更新前快照' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="operator" label="操作人" width="120" show-overflow-tooltip />
          <el-table-column label="操作" width="160" fixed="right">
            <template #default="{ row }">
              <div style="display:flex;gap:6px;">
                <el-button link type="primary" @click="previewConfigRevision(row)">预览</el-button>
                <el-button v-if="canManageK8s" link type="warning" @click="applyConfigRevisionRollback(row)">回滚</el-button>
              </div>
            </template>
          </el-table-column>
        </el-table>
      </div>
      <div style="display:flex;justify-content:space-between;gap:8px;margin-top:8px;flex-wrap:wrap;">
        <div style="display:flex;gap:8px;flex-wrap:wrap;">
          <el-button @click="configEditorVisible = false">关闭</el-button>
          <el-button type="info" plain :loading="configPreviewLoading" @click="previewConfigChange">预览本次变更</el-button>
          <el-button type="warning" plain :disabled="!configForm.rollback_available" :loading="configPreviewLoading" @click="previewConfigRollback">预览最近一次回滚</el-button>
        </div>
        <div style="display:flex;gap:8px;flex-wrap:wrap;">
          <el-button v-if="configForm.rollback_available" type="warning" :loading="configSaving" @click="applyConfigRollback">回滚到上一版本</el-button>
          <el-button type="primary" :loading="configSaving" @click="saveConfigResource">保存配置</el-button>
        </div>
      </div>
    </el-dialog>

    <K8sYamlEditor ref="yamlEditor" @applied="refreshView" />
    <el-dialog v-model="diffDialogVisible" :title="diffDialogTitle" width="90%" style="max-width:980px;" top="4vh" append-to-body destroy-on-close>
      <pre class="log-output terminal-log" style="min-height:320px;">{{ diffDialogContent || '暂无差异' }}</pre>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, shallowRef, computed, onMounted, onBeforeUnmount, nextTick, watch } from 'vue'
import { useRouteTabState } from '@/composables/useRouteTabState'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import { DocumentCopy, Monitor, Bell, Plus, Connection, FolderOpened, RefreshRight, WarningFilled } from '@element-plus/icons-vue'
import K8sYamlEditor from '@/components/k8s/K8sYamlEditor.vue'
import { formatK8sMemory } from '@/utils/k8sResources'
import K8sResourceActions from '@/components/k8s/K8sResourceActions.vue'
import K8sClusterCapacity from '@/components/k8s/K8sClusterCapacity.vue'
import K8sTerminalDialog from '@/components/k8s/K8sTerminalDialog.vue'
import K8sPodLogs from '@/components/k8s/K8sPodLogs.vue'
import {
  getK8sClusters, createK8sCluster, updateK8sCluster, deleteK8sCluster,
  testK8sConnection, getK8sSummary, getK8sCapacity, getK8sNamespaces,
  getK8sPods, getK8sServices, getK8sDeployments,
  getK8sNodes, getK8sStatefulSets, getK8sDaemonSets, getK8sJobs, getK8sCronJobs,
  getK8sIngresses, getK8sPVs, getK8sPVCs, getK8sStorageClasses,
  getK8sConfigMaps, getK8sSecrets, getK8sResourceYaml,
getK8sWorkloadPods, getK8sResourceEvents,
  scaleK8sWorkload, getK8sConfigResourceDetail,
  previewK8sConfigResource, updateK8sConfigResource,
  getK8sConfigRevisions, getK8sConfigRevisionPreview,
  getK8sConfigRollbackPreview, rollbackK8sConfigResource,
  rollbackK8sConfigResourceToRevision,
  deleteK8sResource, operateK8sWorkload, operateK8sNode, getK8sResources,
} from '@/api/modules/container'

const authStore = useAuthStore()
const canManageK8s = computed(() => authStore.hasPermission('ops.k8s.manage') && selectedCluster.value?.access_scope?.role !== 'viewer')
const canViewK8sSecrets = computed(() => authStore.hasPermission('ops.k8s.secret.view'))
const canCreateCluster = computed(() => authStore.hasPermission('ops.k8s.manage') && authStore.currentUser?.k8s_unrestricted !== false)
function canAdminCluster(cluster) {
  return authStore.hasPermission('ops.k8s.manage') && cluster?.access_scope?.role === 'admin' && !cluster?.access_scope?.namespaces?.length
}
const canExecK8s = computed(() => authStore.hasPermission('ops.k8s.exec') && selectedCluster.value?.access_scope?.allow_exec && selectedCluster.value?.access_scope?.role !== 'viewer')
const canK8sTerminal = computed(() => authStore.hasPermission('ops.k8s.terminal') && selectedCluster.value?.access_scope?.role === 'admin' && !selectedCluster.value?.access_scope?.namespaces?.length)

const mainTabs = [
  { key: 'clusters',   label: '集群管理', icon: 'OfficeBuilding' },
  { key: 'nodes',      label: '节点管理', icon: 'Monitor' },
  { key: 'namespaces', label: '命名空间', icon: 'FolderOpened' },
  { key: 'workloads',  label: '工作负载', icon: 'Cpu' },
  { key: 'network',    label: '网络管理', icon: 'Connection' },
  { key: 'storage',    label: '存储管理', icon: 'Coin' },
  { key: 'config',     label: '配置管理', icon: 'Setting' },
  { key: 'extended', label: '扩展资源', icon: 'Grid' },
]

// ====== 集群 ======
const clusters = ref([])
const selectedClusterId = ref(null)
const selectedClusterStorageKey = 'sxdevops.k8s.selected-cluster-id'
const selectedNamespace = ref('_all')
const namespaces = ref([])
const tableSearchKeyword = ref('')
const selectedCluster = computed(() => clusters.value.find(item => item.id === selectedClusterId.value) || null)
const selectedClusterConnected = computed(() => selectedCluster.value?.status === 'connected')
const namespaceOptions = computed(() => normalizeNamespaceItems(namespaces.value))
const namespaceCache = ref({})


const visibleMainTabs = computed(() => selectedCluster.value?.access_scope?.namespaces?.length ? mainTabs.filter(item => item.key !== 'nodes') : mainTabs)
const tabState = useRouteTabState({
  tabs: () => visibleMainTabs.value.map(item => item.key),
  defaultTab: 'clusters',
})
const activeTab = tabState.activeTab
const loading = ref(false)
const clustersLoading = ref(false)
const namespacePopperStyle = {
  width: '220px',
  minWidth: '220px',
  maxWidth: '220px',
}

const needsNamespace = computed(() => ['namespaces', 'workloads', 'config', 'extended'].includes(activeTab.value) || (activeTab.value === 'network' && networkSub.value !== 'IngressClass') || (activeTab.value === 'storage' && storageSub.value === 'PVC'))

function createEmptySummary() {
  return {
    status: 'disconnected',
    server_version: '',
    nodes_total: 0,
    nodes_ready: 0,
    pods_total: 0,
    pods_abnormal: 0,
    total_restarts: 0,
    workloads_total: 0,
    pvcs_pending: 0,
    alerts: [],
  }
}

const summary = ref(createEmptySummary())
const capacitySnapshot = shallowRef(null)
const capacityLoading = ref(false)
const capacityError = ref('')
const capacityCache = new Map()
const capacityRequests = new Map()
let capacityRequestId = 0
const lastNonZeroSummaryByCluster = ref({})

function formatCapacityCount(value) {
  return Number.isFinite(value) ? value.toLocaleString('zh-CN') : '—'
}

const selectedClusterStats = computed(() => [
  { label: 'Ready 节点', value: summary.value.scoped ? '—' : `${summary.value.nodes_ready}/${summary.value.nodes_total}`, tone: '' },
  { label: '工作负载', value: summary.value.workloads_total, tone: '' },
  { label: 'PVC Pending', value: summary.value.pvcs_pending, tone: summary.value.pvcs_pending ? 'is-warning' : '' },
  { label: 'Pod 容量', value: formatCapacityCount(capacitySnapshot.value?.resources?.pods?.capacity), tone: '', detail: '全部节点可容纳的 Pod 总数；仅完整集群范围可见。' },
  { label: 'Pod 用量', value: formatCapacityCount(capacitySnapshot.value?.resources?.pods?.usage), tone: 'is-success', detail: '已调度且未结束的 Pod 数量，不包含已完成、失败及未调度实例；仅完整集群范围可见。' },
  { label: '异常 Pod', value: summary.value.pods_abnormal, tone: summary.value.pods_abnormal ? 'is-warning' : '' },
])
const podSearchFields = [
  'name',
  'namespace',
  'status',
  'node',
  'ip',
  (row) => normalizeContainerNames(row.containers),
  (row) => (row.containers || []).map(item => typeof item === 'string' ? item : item?.image),
]

// ====== 其他 Tab 数据 ======
const extendedResources = shallowRef([])
const extendedType = ref('hpa')
const extendedTypes = { hpa: 'HPA', resourcequota: 'ResourceQuota', limitrange: 'LimitRange' }
const yamlEditor = ref(null)
const autoRefreshSeconds = ref(0)
let autoRefreshTimer = null
const nodes = shallowRef([])
const nsData = shallowRef([])
const pods = shallowRef([])
const deployments = shallowRef([])
const statefulsets = shallowRef([])
const daemonsets = shallowRef([])
const jobs = shallowRef([])
const cronjobs = shallowRef([])
const services = shallowRef([])
const ingresses = shallowRef([])
const endpoints = shallowRef([])
const ingressclasses = shallowRef([])
const networkpolicies = shallowRef([])
const pvs = shallowRef([])
const pvcs = shallowRef([])
const storageclasses = shallowRef([])
const configmaps = shallowRef([])
const secrets = shallowRef([])

// ====== Sub-tabs ======
const workloadSubTabs = ['Pod', 'Deployment', 'StatefulSet', 'DaemonSet', 'Job', 'CronJob']
const networkSubTabs = computed(() => selectedCluster.value?.access_scope?.namespaces?.length
  ? ['Service', 'Ingress', 'Endpoints', 'NetworkPolicy']
  : ['Service', 'Ingress', 'Endpoints', 'IngressClass', 'NetworkPolicy'])
const storageSubTabs = computed(() => selectedCluster.value?.access_scope?.namespaces?.length ? ['PVC'] : ['PV', 'PVC', 'StorageClass'])
const configSubTabs = ['ConfigMap', 'Secret']
const workloadSub = useRouteTabState({
  tabs: () => workloadSubTabs,
  defaultTab: 'Pod',
  queryKey: 'workloadSub',
}).activeTab
const networkSub = useRouteTabState({
  tabs: () => networkSubTabs.value,
  defaultTab: 'Service',
  queryKey: 'networkSub',
}).activeTab
const storageSub = useRouteTabState({
  tabs: () => storageSubTabs.value,
  defaultTab: 'PV',
  queryKey: 'storageSub',
}).activeTab
const configSub = useRouteTabState({
  tabs: () => configSubTabs,
  defaultTab: 'ConfigMap',
  queryKey: 'configSub',
}).activeTab

const resourceSources = {
  nodes: { rows: nodes, fields: ['name', 'internal_ip', 'roles', 'version', 'os_image'], load: getK8sNodes },
  namespaces: { rows: nsData, fields: ['name', 'status', 'created'], load: (id) => loadNamespaces(id, { force: true }) },
  Pod: { rows: pods, fields: podSearchFields, load: getK8sPods },
  Deployment: { rows: deployments, fields: ['name', 'namespace', 'images'], load: getK8sDeployments },
  StatefulSet: { rows: statefulsets, fields: ['name', 'namespace', 'images'], load: getK8sStatefulSets },
  DaemonSet: { rows: daemonsets, fields: ['name', 'namespace', 'images', 'node_selector'], load: getK8sDaemonSets },
  Job: { rows: jobs, fields: ['name', 'namespace', 'images', 'status'], load: getK8sJobs },
  CronJob: { rows: cronjobs, fields: ['name', 'namespace', 'images', 'schedule'], load: getK8sCronJobs },
  Service: { rows: services, fields: ['name', 'namespace', 'type', 'cluster_ip', 'ports'], load: getK8sServices },
  Ingress: { rows: ingresses, fields: ['name', 'namespace', 'class', 'hosts', 'address'], load: getK8sIngresses },
  Endpoints: { rows: endpoints, fields: ['name', 'namespace', 'addresses', 'not_ready_addresses', 'ports'], load: (id, ns) => getK8sResources(id, 'endpoints', ns) },
  IngressClass: { rows: ingressclasses, fields: ['name', (row) => row.spec?.controller], load: (id) => getK8sResources(id, 'ingressclass') },
  NetworkPolicy: { rows: networkpolicies, fields: ['name', 'namespace', (row) => JSON.stringify(row.spec?.podSelector), (row) => row.spec?.policyTypes], load: (id, ns) => getK8sResources(id, 'networkpolicy', ns) },
  PV: { rows: pvs, fields: ['name', 'capacity', 'access_modes', 'status', 'claim', 'storage_class'], load: getK8sPVs },
  PVC: { rows: pvcs, fields: ['name', 'namespace', 'status', 'capacity', 'storage_class', 'volume'], load: getK8sPVCs },
  StorageClass: { rows: storageclasses, fields: ['name', 'provisioner', 'reclaim_policy', 'binding_mode'], load: getK8sStorageClasses },
  ConfigMap: { rows: configmaps, fields: ['name', 'namespace', 'data_count', 'created'], load: getK8sConfigMaps },
  Secret: { rows: secrets, fields: ['name', 'namespace', 'type', 'data_count', 'created'], load: getK8sSecrets },
  extended: { rows: extendedResources, fields: ['name', 'namespace'], load: (id, ns) => getK8sResources(id, extendedType.value, ns) },
}
const resourceKey = computed(() => ({
  workloads: workloadSub.value,
  network: networkSub.value,
  storage: storageSub.value,
  config: configSub.value,
}[activeTab.value] || activeTab.value))
const currentResource = computed(() => resourceSources[resourceKey.value])
const createResourceType = computed(() => ({ nodes: 'node', namespaces: 'namespace', extended: extendedType.value }[resourceKey.value] || resourceKey.value.toLowerCase()))
const canCreateResource = computed(() => canManageK8s.value && (createResourceType.value !== 'secret' || canViewK8sSecrets.value) && (!['node', 'namespace', 'pv', 'storageclass', 'ingressclass'].includes(createResourceType.value) || canAdminCluster(selectedCluster.value)))
const resourceContextKey = computed(() => JSON.stringify([
  selectedClusterId.value, selectedNamespace.value, resourceKey.value,
  activeTab.value === 'extended' ? extendedType.value : '',
]))
const resourcePage = ref(1)
const resourcePageSize = ref(50)
const filteredResourceRows = computed(() => filterRows(currentResource.value?.rows.value || [], currentResource.value?.fields))
const pagedResourceRows = computed(() => filteredResourceRows.value.slice(
  (resourcePage.value - 1) * resourcePageSize.value, resourcePage.value * resourcePageSize.value,
))
const resourceRequests = new Map()
const resourceDataContexts = new Map()
const namespaceRequests = new Map()
const summaryRequests = new Map()
let resourceRequestId = 0
let viewDisposed = false

function resourceRowKey(row) {
  return `${row.namespace || ''}/${row.name}`
}

watch(resourceContextKey, () => {
  resourceRequestId += 1
  loading.value = false
  resourcePage.value = 1
  if (currentResource.value && resourceDataContexts.get(resourceKey.value) !== resourceContextKey.value) {
    currentResource.value.rows.value = []
  }
}, { flush: 'sync' })
watch([tableSearchKeyword, resourcePageSize], () => { resourcePage.value = 1 }, { flush: 'sync' })
watch(() => filteredResourceRows.value.length, (total) => {
  resourcePage.value = Math.min(resourcePage.value, Math.max(1, Math.ceil(total / resourcePageSize.value)))
})

const resourcePanelMeta = computed(() => {
  const map = {
    nodes: {
      title: '节点列表',
      desc: '延续任务工作台的列表密度，集中查看节点状态、版本与基础资源。',
    },
    namespaces: {
      title: '命名空间列表',
      desc: '统一承接命名空间状态和元数据视图，保持工作台式筛选与浏览节奏。',
    },
    workloads: {
      title: '工作负载列表',
      desc: '集中查看 Pod、Deployment、StatefulSet 等工作负载对象及其运行状态。',
    },
    network: {
      title: '网络资源列表',
      desc: '查看服务、入口、端点、入口类与网络策略。',
    },
    storage: {
      title: '存储资源列表',
      desc: '聚合 PV、PVC 与存储类资源，用一张卡片承接筛选与列表。',
    },
    extended: { title: '扩展资源', desc: '管理弹性伸缩、资源配额与限制范围。' },
    config: {
      title: '配置资源列表',
      desc: '统一承接 ConfigMap 与 Secret 的检索、编辑和 YAML 查看。',
    },
  }
  return map[activeTab.value] || {
    title: '资源列表',
    desc: '统一使用任务工作台的上下文筛选和列表承载方式。',
  }
})

const resourcePanelTitle = computed(() => resourcePanelMeta.value.title)
const resourcePanelDesc = computed(() => resourcePanelMeta.value.desc)

// ====== 切换 Tab ======
function switchTab(tab) {
  tabState.switchTab(tab)
}

function normalizeSearchValue(value) {
  if (Array.isArray(value)) {
    return value.map(normalizeSearchValue).join(' ')
  }
  if (value && typeof value === 'object') {
    return Object.values(value).map(normalizeSearchValue).join(' ')
  }
  return String(value || '').toLowerCase()
}

function filterRows(rows, fields = []) {
  const keyword = tableSearchKeyword.value.trim().toLowerCase()
  if (!keyword) return rows
  return rows.filter((row) => fields.some((field) => {
    const value = typeof field === 'function' ? field(row) : row?.[field]
    return normalizeSearchValue(value).includes(keyword)
  }))
}

function summaryAlertType(level) {
  const mapping = { success: 'success', warning: 'warning', danger: 'error' }
  return mapping[level] || 'info'
}

function safeInt(value) {
  const number = Number(value || 0)
  return Number.isFinite(number) ? number : 0
}

function runtimeSummaryTotal(payload) {
  return [
    'nodes_total',
    'pods_total',
    'services_total',
    'ingresses_total',
    'workloads_total',
    'pvcs_total',
    'configmaps_total',
    'secrets_total',
  ].reduce((total, key) => total + safeInt(payload?.[key]), 0)
}

function isZeroRuntimeSummary(payload) {
  return Boolean(payload?.degraded) && runtimeSummaryTotal(payload) === 0
}

function rememberUsableSummary(payload, clusterId) {
  if (!payload || isZeroRuntimeSummary(payload) || runtimeSummaryTotal(payload) === 0) return
  if (!clusterId) return
  lastNonZeroSummaryByCluster.value = {
    ...lastNonZeroSummaryByCluster.value,
    [clusterId]: { ...payload },
  }
}

function normalizeNamespaceItem(item) {
  if (typeof item === 'string') {
    const name = item.trim()
    return name ? { name, status: '', created: '', labels: {}, labelCount: 0 } : null
  }
  if (!item || typeof item !== 'object') return null
  const name = String(item.name || item.namespace || item.metadata?.name || '').trim()
  if (!name) return null
  const labels = item.labels && typeof item.labels === 'object'
    ? item.labels
    : (item.metadata?.labels && typeof item.metadata.labels === 'object' ? item.metadata.labels : {})
  return {
    ...item,
    name,
    status: String(item.status || item.phase || item.status?.phase || '').trim(),
    created: String(item.created || item.creation_timestamp || item.creationTimestamp || item.metadata?.creationTimestamp || '').trim(),
    labels,
    labelCount: Object.keys(labels).length,
  }
}

function normalizeNamespaceItems(items) {
  const uniqueMap = new Map()
  for (const item of Array.isArray(items) ? items : []) {
    const normalized = normalizeNamespaceItem(item)
    if (normalized?.name) uniqueMap.set(normalized.name, normalized)
  }
  return Array.from(uniqueMap.values()).sort((left, right) => left.name.localeCompare(right.name, 'zh-CN'))
}

function namespaceStatusText(status) {
  const value = String(status || '').trim()
  if (!value) return '可用'
  if (value === 'Active') return '活跃'
  if (value === 'Terminating') return '终止中'
  return value
}

function namespaceStatusTagType(status) {
  const value = String(status || '').trim()
  if (!value || value === 'Active') return 'success'
  if (value === 'Terminating') return 'warning'
  return 'info'
}

function namespaceStatusTagClass(status) {
  const type = namespaceStatusTagType(status)
  if (type === 'success') return 'context-status-pill--success'
  if (type === 'warning') return 'context-status-pill--warning'
  return 'context-status-pill--info'
}

function namespaceOptionMeta(namespace) {
  const created = String(namespace?.created || '').trim()
  const meta = []
  if (created) meta.push(`创建于 ${created.replace('T', ' ').slice(0, 16)}`)
  if (namespace?.labelCount) meta.push(`${namespace.labelCount} 个标签`)
  if (meta.length) return meta.join(' · ')
  return '命名空间资源视图'
}

function clusterOptionMeta(cluster) {
  const endpoint = String(cluster?.api_server || '').trim()
  const description = String(cluster?.description || '').trim()
  const meta = []
  if (endpoint) {
    try {
      meta.push(new URL(endpoint).host || endpoint)
    } catch {
      meta.push(endpoint)
    }
  }
  if (description) meta.push(description)
  return meta.join(' · ') || 'Kubernetes 集群连接'
}

function syncSelectedNamespace(preferred = selectedNamespace.value) {
  if (!preferred || preferred === '_all') {
    selectedNamespace.value = '_all'
    return
  }
  selectedNamespace.value = namespaceOptions.value.some((item) => item.name === preferred) ? preferred : '_all'
}

function setClusterStatus(clusterId, status) {
  const cluster = clusters.value.find((item) => item.id === clusterId)
  if (cluster && status && cluster.status !== status) {
    cluster.status = status
  }
}

async function loadNamespaces(clusterId, options = {}) {
  const { force = false } = options
  if (!clusterId) {
    namespaces.value = []
    return []
  }
  if (!force && namespaceCache.value[clusterId]?.length) {
    if (clusterId === selectedClusterId.value) namespaces.value = namespaceCache.value[clusterId]
    return namespaceCache.value[clusterId]
  }
  try {
    if (!namespaceRequests.has(clusterId)) {
      namespaceRequests.set(clusterId, getK8sNamespaces(clusterId).finally(() => namespaceRequests.delete(clusterId)))
    }
    const items = normalizeNamespaceItems(await namespaceRequests.get(clusterId))
    if (viewDisposed) return []
    if (clusterId === selectedClusterId.value) namespaces.value = items
    namespaceCache.value = {
      ...namespaceCache.value,
      [clusterId]: items,
    }
    return items
  } catch (e) {
    if (clusterId === selectedClusterId.value && !viewDisposed) namespaces.value = []
    return []
  }
}

async function fetchClusters() {
  if (clustersLoading.value) return
  clustersLoading.value = true
  try {
    const res = await getK8sClusters()
    if (viewDisposed) return
    clusters.value = res.results || res

    const persistedClusterId = readPersistedClusterId()
    const connectedCluster = clusters.value.find(item => item.status === 'connected')
    const current = clusters.value.find(item => item.id === selectedClusterId.value)
    const persisted = clusters.value.find(item => String(item.id) === persistedClusterId)
    if (persisted) {
      selectedClusterId.value = persisted.id
    } else if (current) {
      selectedClusterId.value = current.id
    } else if (activeTab.value !== 'clusters' && connectedCluster) {
      selectedClusterId.value = connectedCluster.id
    } else {
      selectedClusterId.value = clusters.value[0]?.id || null
    }
    persistSelectedClusterId(selectedClusterId.value)
    if (!selectedClusterId.value) {
      summary.value = createEmptySummary()
    }

  } catch (e) {
    return
  } finally {
    clustersLoading.value = false
  }
  if (selectedClusterId.value) {
    if (activeTab.value === 'clusters') await Promise.all([fetchSummary({ probe: true }), fetchCapacity()])
    else await onClusterChange()
  }
}

async function fetchSummary(options = {}) {
  const { probe = false } = options
  const clusterId = selectedClusterId.value
  if (!clusterId) {
    summary.value = createEmptySummary()
    return false
  }
  if (!probe && !selectedClusterConnected.value) {
    summary.value = createEmptySummary()
    return false
  }
  try {
    if (!summaryRequests.has(clusterId)) {
      summaryRequests.set(clusterId, getK8sSummary(clusterId).finally(() => summaryRequests.delete(clusterId)))
    }
    const payload = await summaryRequests.get(clusterId)
    if (viewDisposed) return false
    rememberUsableSummary(payload, clusterId)
    setClusterStatus(clusterId, payload.status || 'connected')
    if (clusterId === selectedClusterId.value) summary.value = payload
    return true
  } catch (e) {
    if (viewDisposed || clusterId !== selectedClusterId.value) return false
    const cachedSummary = lastNonZeroSummaryByCluster.value[clusterId]
    if (cachedSummary) {
      summary.value = { ...cachedSummary, degraded: true }
      return true
    }
    summary.value = createEmptySummary()
    setClusterStatus(clusterId, 'error')
    return false
  }
}

async function fetchCapacity() {
  const requestId = ++capacityRequestId
  const clusterId = selectedClusterId.value
  capacityLoading.value = false
  capacityError.value = ''
  capacitySnapshot.value = null
  if (!clusterId || activeTab.value !== 'clusters' || selectedCluster.value?.access_scope?.namespaces?.length) return
  const cached = capacityCache.get(clusterId)
  if (cached && Date.now() - cached.receivedAt < (cached.payload.unavailable_resources?.length ? 5000 : 30000)) {
    capacitySnapshot.value = cached.payload
    return
  }
  capacityLoading.value = true
  try {
    if (!capacityRequests.has(clusterId)) {
      capacityRequests.set(clusterId, getK8sCapacity(clusterId).finally(() => capacityRequests.delete(clusterId)))
    }
    const payload = await capacityRequests.get(clusterId)
    if (viewDisposed || requestId !== capacityRequestId || clusterId !== selectedClusterId.value) return
    capacityCache.set(clusterId, { payload, receivedAt: Date.now() })
    capacitySnapshot.value = payload
  } catch {
    if (!viewDisposed && requestId === capacityRequestId && clusterId === selectedClusterId.value) capacityError.value = '容量信息暂不可用，请刷新重试。'
  } finally {
    if (requestId === capacityRequestId) capacityLoading.value = false
  }
}

function refreshView() {
  if (activeTab.value === 'clusters') {
    return fetchClusters()
  }
  return refreshClusterContext()
}

async function refreshClusterContext(options = {}) {
  const { forceSummary = true, forceNamespaces = true } = options
  const clusterId = selectedClusterId.value
  const contextKey = resourceContextKey.value
  const previousNamespace = selectedNamespace.value
  if (!clusterId) {
    summary.value = createEmptySummary()
    return
  }
  const namespaceTask = needsNamespace.value
    ? loadNamespaces(clusterId, { force: forceNamespaces }).then(() => {
      if (viewDisposed || contextKey !== resourceContextKey.value) return
      syncSelectedNamespace(previousNamespace)
      if (selectedNamespace.value !== previousNamespace) return fetchCurrentTab()
    })
    : Promise.resolve([])
  const summaryTask = forceSummary
    ? fetchSummary({ probe: true })
    : Promise.resolve(selectedClusterConnected.value)
  const resourceTask = selectedClusterConnected.value
    ? fetchCurrentTab()
    : summaryTask.then((ready) => {
      if (ready && !viewDisposed && contextKey === resourceContextKey.value) return fetchCurrentTab()
    })
  await Promise.all([summaryTask, namespaceTask, resourceTask])
}

async function onClusterChange() {
  summary.value = lastNonZeroSummaryByCluster.value[selectedClusterId.value] || createEmptySummary()
  namespaces.value = namespaceCache.value[selectedClusterId.value] || []
  selectedNamespace.value = '_all'
  await Promise.all([refreshClusterContext({ forceSummary: true, forceNamespaces: false }), fetchCapacity()])
}

async function selectCluster(cluster) {
  if (!cluster || cluster.id === selectedClusterId.value) return
  selectedClusterId.value = cluster.id
  persistSelectedClusterId(cluster.id)
  await onClusterChange()
}

function readPersistedClusterId() {
  try {
    return window.localStorage.getItem(selectedClusterStorageKey) || ''
  } catch {
    return ''
  }
}

function persistSelectedClusterId(clusterId) {
  try {
    if (clusterId === null || clusterId === undefined || clusterId === '') {
      window.localStorage.removeItem(selectedClusterStorageKey)
    } else {
      window.localStorage.setItem(selectedClusterStorageKey, String(clusterId))
    }
  } catch { }
}

async function fetchCurrentTab() {
  const source = currentResource.value
  if (!source || !selectedClusterId.value || !selectedClusterConnected.value || viewDisposed) return
  loading.value = true
  const requestId = ++resourceRequestId
  const contextKey = resourceContextKey.value
  const key = resourceKey.value
  const id = selectedClusterId.value
  const ns = selectedNamespace.value
  try {
    if (!resourceRequests.has(contextKey)) {
      resourceRequests.set(contextKey, source.load(id, ns).finally(() => resourceRequests.delete(contextKey)))
    }
    const items = await resourceRequests.get(contextKey)
    if (viewDisposed || requestId !== resourceRequestId || contextKey !== resourceContextKey.value) return
    source.rows.value = items
    resourceDataContexts.set(key, contextKey)
  } catch (e) {
    if (!viewDisposed && requestId === resourceRequestId) ElMessage.error('获取数据失败')
  } finally {
    if (requestId === resourceRequestId) loading.value = false
  }
}

function normalizeContainerNames(containers) {
  return (containers || []).map((item) => (typeof item === 'string' ? item : item?.name)).filter(Boolean)
}

function resourceAge(value) {
  if (!value) return '-'
  const created = new Date(value)
  const elapsed = Date.now() - created.getTime()
  if (!Number.isFinite(elapsed) || elapsed < 0) return '-'
  const minutes = Math.floor(elapsed / 60000)
  if (minutes < 60) return `${minutes}m`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h`
  return `${Math.floor(hours / 24)}d`
}

const clusterConsoleDialogVisible = ref(false)
const consoleCluster = ref({})

function showClusterConsole() {
  if (!canK8sTerminal.value || !selectedClusterConnected.value) return
  consoleCluster.value = { id: selectedCluster.value.id, name: selectedCluster.value.name }
  clusterConsoleDialogVisible.value = true
}

function baseResourceActions(resourceType, row) {
  const action = (key, label, icon) => ({ key, label, icon, resourceType })
  const yaml = action('yaml', '查看 YAML', 'yaml')
  const events = action('events', '查看事件', 'events')
  if (resourceType === 'pod') {
    return [
      ...(canExecK8s.value ? [action('exec', '进入终端', 'shell')] : []),
      action('logs', '查看日志', 'logs'), yaml, events,
    ]
  }
  if (resourceType === 'node') return [yaml, events]
  if (resourceType === 'namespace' || resourceType === 'pv' || resourceType === 'storageclass') return [yaml]
  if (resourceType === 'pvc' || resourceType === 'service' || resourceType === 'ingress') return [yaml, events]
  if (resourceType === 'configmap' || resourceType === 'secret') {
    if (resourceType === 'secret' && !canViewK8sSecrets.value) return []
    return [
      ...(canManageK8s.value ? [action('edit', '编辑配置', 'edit')] : []),
      yaml,
    ]
  }
  return [
    ...(canManageK8s.value && ['deployment', 'statefulset'].includes(resourceType)
      ? [action('scale', '调整副本', 'scale')]
      : []),
    action('pods', '查看 Pods', 'pods'), yaml, events,
  ]
}

function resourceActions(resourceType, row) {
  const actions = ['hpa', 'networkpolicy', 'resourcequota', 'limitrange', 'endpoints', 'ingressclass'].includes(resourceType)
    ? [{ key: 'yaml', label: '查看 YAML', icon: 'yaml', resourceType }]
    : baseResourceActions(resourceType, row)
  const clusterResource = ['node', 'namespace', 'pv', 'storageclass', 'ingressclass'].includes(resourceType)
  if (!canManageK8s.value || (clusterResource && !canAdminCluster(selectedCluster.value))) return actions
  const add = (key, label, icon = 'edit', danger = false) => actions.push({ key, label, icon, danger, resourceType })
  if (resourceType !== 'secret' || canViewK8sSecrets.value) add('editYaml', '编辑 YAML')
  if (['deployment', 'statefulset', 'daemonset'].includes(resourceType)) add('rollout', '滚动重启', 'restart')
  if (resourceType === 'cronjob') add(row.suspend ? 'resume' : 'suspend', row.suspend ? '恢复调度' : '暂停调度')
  if (resourceType === 'node') add(row.unschedulable ? 'uncordon' : 'cordon', row.unschedulable ? '恢复节点调度' : '禁止节点调度')
  else add('deleteResource', resourceType === 'pod' ? '删除 Pod' : '删除资源', 'delete', true)
  return actions
}

async function handleResourceAction(action, row) {
  if (action.key === 'editYaml') return yamlEditor.value?.open(selectedCluster.value, selectedNamespace.value, action.resourceType, row)
  if (['rollout', 'suspend', 'resume', 'cordon', 'uncordon', 'deleteResource'].includes(action.key)) {
    const deletingPod = action.key === 'deleteResource' && action.resourceType === 'pod'
    const message = `确认${action.label} ${row.namespace ? row.namespace + '/' : ''}${row.name}？${deletingPod ? '是否自动补建取决于所属控制器及其策略；独立 Pod 删除后不会自动重建。' : ''}`
    try {
      await ElMessageBox.confirm(message, '确认操作', { type: 'warning', confirmButtonText: '确认', cancelButtonText: '取消' })
    } catch { return }
    const payload = { type: action.resourceType, name: row.name, namespace: row.namespace, operation: action.key === 'rollout' ? 'restart' : action.key }
    if (action.key === 'deleteResource') await deleteK8sResource(selectedClusterId.value, payload)
    else if (['cordon', 'uncordon'].includes(action.key)) await operateK8sNode(selectedClusterId.value, payload)
    else await operateK8sWorkload(selectedClusterId.value, payload)
    ElMessage.success('操作成功')
    if (deletingPod && podDialogVisible.value) {
      await showPodDetail(podWorkloadType.value, podWorkloadName.value, podWorkloadNamespace.value)
    }
    return refreshView()
  }
  const namespace = row.namespace
  if (action.key === 'exec') return openExecDialog(row)
  if (action.key === 'logs') return showPodLog(row.name, namespace, normalizeContainerNames(row.containers))
  if (action.key === 'yaml') return showYaml(action.resourceType, row.name, namespace)
  if (action.key === 'events') return showEvents(action.resourceType, row.name, namespace)
  if (action.key === 'scale') return openScaleDialog(action.resourceType, row)
  if (action.key === 'pods') return showPodDetail(action.resourceType, row.name, namespace)
  if (action.key === 'edit') return openConfigEditor(action.resourceType, row)
}

// ====== 集群 CRUD ======
const clusterDialogVisible = ref(false)
const editingClusterId = ref(null)
const savingCluster = ref(false)
const clusterForm = ref({ name: '', api_server: '', description: '', kubeconfig: '' })

function openClusterDialog(cluster) {
  if (!canManageK8s.value) return
  if (cluster) {
    editingClusterId.value = cluster.id
    clusterForm.value = { name: cluster.name, api_server: cluster.api_server, description: cluster.description, kubeconfig: '' }
  } else {
    editingClusterId.value = null
    clusterForm.value = { name: '', api_server: '', description: '', kubeconfig: '' }
  }
  clusterDialogVisible.value = true
}

async function saveCluster() {
  if (!canManageK8s.value) return
  if (!clusterForm.value.name) return ElMessage.warning('请填写集群名称')
  if (!clusterForm.value.kubeconfig && !editingClusterId.value) return ElMessage.warning('请粘贴 KubeConfig')
  savingCluster.value = true
  try {
    const data = { ...clusterForm.value }
    if (!data.kubeconfig) delete data.kubeconfig
    if (editingClusterId.value) {
      await updateK8sCluster(editingClusterId.value, data)
      ElMessage.success('集群已更新')
    } else {
      await createK8sCluster(data)
      ElMessage.success('集群已添加')
    }
    clusterDialogVisible.value = false
    fetchClusters()
  } catch (e) { /* */ }
  savingCluster.value = false
}

async function testCluster(row) {
  if (!canManageK8s.value) return
  try {
    const res = await testK8sConnection(row.id)
    if (res.success) ElMessage.success(res.message)
    else ElMessage.error(res.message)
    fetchClusters()
  } catch (e) { ElMessage.error('连接测试失败') }
}

async function delCluster(row) {
  if (!canManageK8s.value) return
  try {
    await deleteK8sCluster(row.id)
    ElMessage.success('集群已删除')
    fetchClusters()
  } catch (e) { ElMessage.error('删除失败') }
}

// ====== YAML 查看 ======
const yamlDialogVisible = ref(false)
const yamlContent = ref('')
const yamlResourceName = ref('')
const yamlResourceType = ref('')
const yamlLoading = ref(false)

async function showYaml(type, name, namespace) {
  if (type === 'secret' && !canViewK8sSecrets.value) return
  if (!selectedClusterId.value) return ElMessage.warning('请先选择集群')
  yamlResourceType.value = type
  yamlResourceName.value = name
  yamlContent.value = ''
  yamlDialogVisible.value = true
  yamlLoading.value = true
  try {
    const ns = namespace || selectedNamespace.value || 'default'
    const res = await getK8sResourceYaml(selectedClusterId.value, type, name, ns)
    yamlContent.value = res.yaml || res
  } catch (e) {
    yamlContent.value = '# 获取 YAML 失败'
    ElMessage.error('获取 YAML 失败')
  }
  yamlLoading.value = false
}

function copyYaml() {
  navigator.clipboard.writeText(yamlContent.value).then(() => {
  ElMessage.success('已复制到剪贴板')
  }).catch(() => {
    ElMessage.error('复制失败')
  })
}

// ====== Pod 详情 ======
const podDialogVisible = ref(false)
const podWorkloadName = ref('')
const podWorkloadType = ref('')
const podWorkloadNamespace = ref('default')
const podList = shallowRef([])
const podLoading = ref(false)
const podPage = ref(1)
const filteredPodList = computed(() => filterRows(podList.value, ['name', 'namespace', 'status', 'node', 'pod_ip', 'host_ip', 'cpu_request', 'memory_request']))
const pagedPodList = computed(() => filteredPodList.value.slice((podPage.value - 1) * 50, podPage.value * 50))
watch([podList, tableSearchKeyword], () => { podPage.value = 1 })

async function showPodDetail(workloadType, name, namespace) {
  if (!selectedClusterId.value) return ElMessage.warning('请先选择集群')
  podWorkloadType.value = workloadType
  podWorkloadName.value = name
  podWorkloadNamespace.value = namespace || selectedNamespace.value || 'default'
  podList.value = []
  podDialogVisible.value = true
  podLoading.value = true
  try {
    const ns = podWorkloadNamespace.value
    podList.value = await getK8sWorkloadPods(selectedClusterId.value, workloadType, name, ns)
  } catch (e) {
    ElMessage.error('获取 Pod 列表失败')
  }
  podLoading.value = false
}

const logDialogVisible = ref(false)
const logCluster = ref({})
const logPod = ref({})

function showPodLog(podName, namespace, containers) {
  logCluster.value = { id: selectedCluster.value.id, name: selectedCluster.value.name }
  logPod.value = { name: podName, namespace: namespace || 'default', containers: normalizeContainerNames(containers) }
  logDialogVisible.value = true
}

// ====== 事件查看 ======
const execDialogVisible = ref(false)
const execCluster = ref({})
const execPod = ref({})

function openExecDialog(row) {
  if (!canExecK8s.value) return
  execCluster.value = { id: selectedCluster.value.id, name: selectedCluster.value.name }
  execPod.value = { name: row.name, namespace: row.namespace || 'default', containers: normalizeContainerNames(row.containers) }
  execDialogVisible.value = true
}

const scaleDialogVisible = ref(false)
const scaleLoading = ref(false)
const scaleForm = ref({ workload_type: 'deployment', name: '', namespace: 'default', replicas: 1 })

function openScaleDialog(workloadType, row) {
  scaleForm.value = {
    workload_type: workloadType,
    name: row.name,
    namespace: row.namespace || 'default',
    replicas: Number(row.replicas || 0),
  }
  scaleDialogVisible.value = true
}

async function submitScale() {
  if (!selectedClusterId.value) return
  scaleLoading.value = true
  try {
    const res = await scaleK8sWorkload(selectedClusterId.value, { ...scaleForm.value })
    ElMessage.success(res.message || 'Scale submitted')
    scaleDialogVisible.value = false
    await Promise.all([fetchSummary(), fetchCurrentTab()])
  } catch (e) {
    ElMessage.error('Scale failed')
  }
  scaleLoading.value = false
}

const configEditorVisible = ref(false)
const configPreviewLoading = ref(false)
const configSaving = ref(false)
const configRevisionLoading = ref(false)
const configRevisions = ref([])
const diffDialogVisible = ref(false)
const diffDialogTitle = ref('差异预览')
const diffDialogContent = ref('')
const configForm = ref({
  type: 'configmap',
  name: '',
  namespace: 'default',
  content: '',
  rollback_available: false,
  revision_count: 0,
})
const configDialogTitle = computed(() => `${configForm.value.type} 配置 - ${configForm.value.name}`)

function syncConfigRevisionState(detail = {}) {
  if (typeof detail.rollback_available === 'boolean') {
    configForm.value.rollback_available = detail.rollback_available
  }
  if (typeof detail.revision_count === 'number') {
    configForm.value.revision_count = detail.revision_count
  } else {
    configForm.value.revision_count = configRevisions.value.length
  }
}

async function fetchConfigRevisions() {
  if (!selectedClusterId.value || !configForm.value.name) return
  configRevisionLoading.value = true
  try {
    const res = await getK8sConfigRevisions(
      selectedClusterId.value,
      configForm.value.type,
      configForm.value.name,
      configForm.value.namespace,
    )
    configRevisions.value = res.items || []
    syncConfigRevisionState({ revision_count: configRevisions.value.length, rollback_available: configRevisions.value.length > 0 })
  } catch (e) {
    configRevisions.value = []
    ElMessage.error('加载配置历史失败')
  }
  configRevisionLoading.value = false
}

async function openConfigEditor(type, row) {
  if (!canManageK8s.value || (type === 'secret' && !canViewK8sSecrets.value)) return
  if (!selectedClusterId.value) return
  configPreviewLoading.value = true
  try {
    const detail = await getK8sConfigResourceDetail(selectedClusterId.value, type, row.name, row.namespace)
    configForm.value = {
      type,
      name: row.name,
      namespace: row.namespace || 'default',
      content: detail.text || '',
      rollback_available: detail.rollback_available || false,
      revision_count: detail.revision_count || 0,
    }
    configRevisions.value = []
    configEditorVisible.value = true
    await fetchConfigRevisions()
  } catch (e) {
    ElMessage.error('加载配置详情失败')
  }
  configPreviewLoading.value = false
}

async function previewConfigChange() {
  if (!selectedClusterId.value) return
  configPreviewLoading.value = true
  try {
    const res = await previewK8sConfigResource(selectedClusterId.value, { ...configForm.value })
    diffDialogTitle.value = `保存前预览 - ${configForm.value.name}`
    diffDialogContent.value = res.diff || '暂无差异'
    diffDialogVisible.value = true
  } catch (e) {
    ElMessage.error('配置预览失败')
  }
  configPreviewLoading.value = false
}

async function saveConfigResource() {
  if (!selectedClusterId.value) return
  configSaving.value = true
  try {
    const res = await updateK8sConfigResource(selectedClusterId.value, { ...configForm.value })
    configForm.value.content = res.resource?.text || configForm.value.content
    syncConfigRevisionState(res.resource)
      ElMessage.success(res.message || '配置已更新')
    await fetchConfigRevisions()
    await Promise.all([fetchCurrentTab(), fetchSummary()])
  } catch (e) {
    ElMessage.error('保存配置失败')
  }
  configSaving.value = false
}

async function previewConfigRollback() {
  if (!selectedClusterId.value) return
  configPreviewLoading.value = true
  try {
    const res = await getK8sConfigRollbackPreview(selectedClusterId.value, configForm.value.type, configForm.value.name, configForm.value.namespace)
    diffDialogTitle.value = `最近回滚预览 - ${configForm.value.name}`
    diffDialogContent.value = res.diff || '当前版本与最近一次回滚没有差异'
    diffDialogVisible.value = true
  } catch (e) {
    ElMessage.error('回滚预览失败')
  }
  configPreviewLoading.value = false
}

async function applyConfigRollback() {
  if (!selectedClusterId.value) return
  configSaving.value = true
  try {
    const res = await rollbackK8sConfigResource(selectedClusterId.value, {
      type: configForm.value.type,
      name: configForm.value.name,
      namespace: configForm.value.namespace,
    })
    configForm.value.content = res.resource?.text || configForm.value.content
    syncConfigRevisionState(res.resource)
    ElMessage.success(res.message || '配置已回滚')
    await fetchConfigRevisions()
    await Promise.all([fetchCurrentTab(), fetchSummary()])
  } catch (e) {
    ElMessage.error('回滚失败')
  }
  configSaving.value = false
}

async function previewConfigRevision(row) {
  if (!selectedClusterId.value) return
  configPreviewLoading.value = true
  try {
    const res = await getK8sConfigRevisionPreview(
      selectedClusterId.value,
      configForm.value.type,
      configForm.value.name,
      configForm.value.namespace,
      row.id,
    )
    diffDialogTitle.value = `历史版本预览 - #${row.id}`
    diffDialogContent.value = res.diff || '暂无差异'
    diffDialogVisible.value = true
  } catch (e) {
    ElMessage.error('加载历史版本预览失败')
  }
  configPreviewLoading.value = false
}

async function applyConfigRevisionRollback(row) {
  if (!selectedClusterId.value) return
  configSaving.value = true
  try {
    const res = await rollbackK8sConfigResourceToRevision(selectedClusterId.value, {
      type: configForm.value.type,
      name: configForm.value.name,
      namespace: configForm.value.namespace,
      revision_id: row.id,
    })
    configForm.value.content = res.resource?.text || configForm.value.content
    syncConfigRevisionState(res.resource)
    ElMessage.success(res.message || '已回滚到指定历史版本')
    await fetchConfigRevisions()
    await Promise.all([fetchCurrentTab(), fetchSummary()])
  } catch (e) {
    ElMessage.error('回滚到指定历史版本失败')
  }
  configSaving.value = false
}

const eventsDialogVisible = ref(false)
const eventsResourceName = ref('')
const eventsList = ref([])
const eventsLoading = ref(false)

async function showEvents(type, name, namespace) {
  if (!selectedClusterId.value) return ElMessage.warning('请先选择集群')
  eventsResourceName.value = `${type}/${name}`
  eventsList.value = []
  eventsDialogVisible.value = true
  eventsLoading.value = true
  try {
    const ns = namespace || selectedNamespace.value || 'default'
    eventsList.value = await getK8sResourceEvents(selectedClusterId.value, type, name, ns)
  } catch (e) {
    ElMessage.error('获取事件失败')
  }
  eventsLoading.value = false
}

function formatEventTime(iso) {
  if (!iso) return '-'
  try {
    const d = new Date(iso)
    const now = new Date()
    const diff = Math.floor((now - d) / 1000)
    if (diff < 60) return `${diff}s ago`
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
    if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
    return `${Math.floor(diff / 86400)}d ago`
  } catch {
    return iso
  }
}

// ====== 初始化 ======
watch(activeTab, (tab, prev) => {
  if (!tab || tab === prev) return
  if (tab === 'clusters') {
    fetchClusters()
  } else if (selectedClusterId.value) {
    refreshClusterContext({ forceSummary: false, forceNamespaces: false })
  }
})

watch(workloadSub, (tab, prev) => {
  if (tab !== prev && activeTab.value === 'workloads' && selectedClusterId.value) fetchCurrentTab()
})
watch(networkSub, (tab, prev) => {
  if (tab !== prev && activeTab.value === 'network' && selectedClusterId.value) fetchCurrentTab()
})
watch(storageSub, (tab, prev) => {
  if (tab !== prev && activeTab.value === 'storage' && selectedClusterId.value) fetchCurrentTab()
})
watch(configSub, (tab, prev) => {
  if (tab !== prev && activeTab.value === 'config' && selectedClusterId.value) fetchCurrentTab()
})

watch(autoRefreshSeconds, (seconds) => {
  clearInterval(autoRefreshTimer)
  if (seconds) autoRefreshTimer = setInterval(() => {
    if (!loading.value && !document.hidden) refreshView()
  }, seconds * 1000)
})
onMounted(() => { fetchClusters() })
onBeforeUnmount(() => {
  viewDisposed = true
  clearInterval(autoRefreshTimer)
})
</script>

<style scoped>
.k8s-page-shell {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.k8s-pagination {
  display: flex;
  justify-content: flex-start;
  padding-top: 12px;
}

.k8s-page-shell :deep(.panel) {
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.98) 0%, rgba(250, 252, 255, 0.96) 100%);
  border: 1px solid rgba(15, 23, 42, 0.08);
  border-radius: 18px;
  box-shadow: 0 8px 24px rgba(15, 23, 42, 0.04);
  padding: 14px 16px;
}

.k8s-hero {
  background: linear-gradient(135deg, #fbfdff 0%, #f7faff 52%, #f9fbfd 100%);
  border-color: rgba(36, 91, 219, 0.09);
  display: flex;
  gap: 12px;
  justify-content: space-between;
  align-items: center;
}

.k8s-hero-desc {
  margin: 0;
  color: #64748b;
  font-size: 13px;
  line-height: 1.45;
}

.k8s-page-shell :deep(.release-hero-title-row) {
  display: flex;
  align-items: center;
  gap: 12px;
}

.k8s-page-shell :deep(.release-hero-title-inline) {
  flex-wrap: wrap;
}

.k8s-page-shell :deep(.hero h2) {
  margin: 0;
  font-size: 23px;
  color: #0f172a;
}

.k8s-header-icon {
  width: 42px;
  height: 42px;
  border-radius: 14px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  color: #245bdb;
  background: linear-gradient(180deg, #f3f7ff 0%, #ebf2ff 100%);
  border: 1px solid rgba(36, 91, 219, 0.12);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.8);
}

.k8s-main-tabs {
  overflow-x: auto;
  flex-wrap: nowrap;
  box-shadow: none;
  margin-top: 0;
  margin-bottom: 0;
}

.k8s-page-shell :deep(.neo-tab-btn) {
  min-height: 28px;
  padding: 0 10px;
  border-radius: 8px;
  font-size: 13px;
}

.k8s-page-shell :deep(.neo-tabs) {
  padding: 3px;
  border-radius: 12px;
  background: rgba(248, 250, 252, 0.88);
  border: 1px solid rgba(148, 163, 184, 0.14);
}

.k8s-page-shell :deep(.neo-tab-btn.active) {
  box-shadow: 0 0 0 1px rgba(59, 130, 246, 0.14), 0 8px 16px rgba(59, 130, 246, 0.12);
}

.k8s-page-shell :deep(.k8s-main-tabs .neo-tab-btn) {
  flex: 0 0 auto;
  white-space: nowrap;
  min-height: 38px;
  padding: 0 20px;
  border-radius: 8px;
}

.k8s-page-shell :deep(.k8s-main-tabs .neo-tab-btn.active) {
  color: #245bdb;
  font-weight: 600;
  background: rgba(36, 91, 219, 0.12);
  box-shadow: inset 0 0 0 1px rgba(36, 91, 219, 0.12);
}

.k8s-page-shell :deep(.k8s-main-tabs .neo-tab-btn:hover) {
  background: rgba(36, 91, 219, 0.06);
}

.k8s-subtab-switch {
  display: inline-flex;
  margin: 0;
  padding: 2px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 9px;
  background: #f8fafc;
}

.k8s-resource-header-actions { min-width: 0; }

:global(.k8s-yaml-dialog.el-dialog) {
  display: flex;
  flex-direction: column;
  max-height: calc(100dvh - 48px);
}

:global(.k8s-yaml-dialog .el-dialog__header) { flex-shrink: 0; }

:global(.k8s-yaml-dialog .el-dialog__body) {
  display: flex;
  flex-direction: column;
  min-height: 0;
  max-height: none;
  overflow: hidden;
}

:global(.k8s-yaml-dialog .yaml-viewer-toolbar) { flex-shrink: 0; }

:global(.k8s-yaml-dialog .yaml-viewer-container) {
  min-height: 0;
  overflow: auto;
}

.k8s-subtab-switch button {
  min-height: 28px;
  padding: 0 11px;
  border: 1px solid transparent;
  border-radius: 7px;
  background: transparent;
  color: #64748b;
  font-size: 12px;
  line-height: 1;
  cursor: pointer;
}

.k8s-subtab-switch button.active {
  border-color: rgba(37,99,235,.28);
  background: linear-gradient(135deg, #dbeafe 0%, #eff6ff 100%);
  color: #1d4ed8;
  box-shadow: inset 0 1px 0 rgba(255,255,255,.8), 0 2px 6px rgba(37,99,235,.14);
  font-weight: 700;
}

.pod-container-readiness {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  color: #64748b;
  font-variant-numeric: tabular-nums;
}

.pod-container-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #cbd5e1;
}

.pod-container-dot.is-ready { background: #22c55e; }

.k8s-cluster-layout {
  display: grid;
  flex: 1;
  grid-template-columns: minmax(0, 1fr) 390px;
  gap: 16px;
  align-items: stretch;
}

.k8s-cluster-selector { min-width: 0; min-height: 230px; }
.k8s-source-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }
.source-card-actions :deep(.el-button + .el-button) { margin-left: 0; }

.selected-cluster-panel {
  min-width: 0;
  min-height: 390px;
  padding: 18px;
  border: 1px solid #dce5f2;
  border-radius: 16px;
  background: linear-gradient(150deg, #f7faff, #fff 55%);
}

.selected-cluster-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 8px; margin-bottom: 18px; }
.selected-cluster-heading-copy { min-width: 0; display: flex; flex-direction: column; gap: 6px; }
.selected-cluster-heading-copy > span { color: #728198; font-size: 13px; }
.selected-cluster-heading-copy strong { color: #203652; font-size: 19px; overflow-wrap: anywhere; }
.selected-cluster-heading-actions { display: flex; flex-direction: column; align-items: flex-end; flex-shrink: 0; gap: 8px; }
.selected-cluster-stat-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; margin: 18px 0; }
.selected-cluster-stat { display: flex; min-width: 0; flex-direction: column; align-items: flex-start; gap: 8px; padding: 12px 10px; border: 1px solid #e1e8f2; border-radius: 10px; background: #f8fafd; }
.selected-cluster-stat span { color: #728198; font-size: 12px; line-height: 1.4; overflow-wrap: anywhere; }
.selected-cluster-stat strong { color: #203652; font-size: 21px; line-height: 1.2; font-variant-numeric: tabular-nums; white-space: nowrap; }
.selected-cluster-stat.is-success { border-color: rgba(16,185,129,.16); background: #f5fcf9; }.selected-cluster-stat.is-success strong { color: #059669; }
.selected-cluster-stat.is-warning { border-color: rgba(245,158,11,.18); background: #fffbf2; }.selected-cluster-stat.is-warning strong { color: #d97706; }
.selected-cluster-meta { display: grid; gap: 11px; margin: 0; padding-top: 12px; border-top: 1px solid #e5ebf4; font-size: 13px; }
.selected-cluster-meta > div { display: grid; grid-template-columns: 86px minmax(0, 1fr); gap: 8px; min-width: 0; }
.selected-cluster-meta dt { color: #8190a5; }
.selected-cluster-meta dd { overflow: hidden; margin: 0; color: #475569; line-height: 1.5; text-overflow: ellipsis; white-space: nowrap; }

.source-card {
  display: flex;
  min-width: 0;
  min-height: 220px;
  flex-direction: column;
  padding: 14px;
  border: 1px solid #dfe6ef;
  border-radius: 14px;
  background: #fff;
  transition: border-color .16s, background .16s;
}

.source-card--selected {
  border-color: #8db0f1;
  background: linear-gradient(140deg, #f2f7ff, #fff 75%);
  box-shadow: 0 0 0 1px #dce8ff;
}

.source-card--unavailable { background: #fcfcfd; }
.source-card-topline, .source-card-footer, .source-card-actions { display: flex; align-items: center; gap: 8px; }
.source-card-topline, .source-card-footer { justify-content: space-between; }
.source-card-topline { margin-bottom: 13px; }
.source-card-footer { margin-top: auto; flex-wrap: wrap; padding-top: 10px; border-top: 1px solid #edf0f5; gap: 6px; }
.source-card-actions { flex-wrap: wrap; gap: 5px; }
.source-provider-mark { padding: 4px 8px; border-radius: 7px; background: #eff5ff; color: #3673ce; font-size: 11px; font-weight: 700; }
.source-account-name { overflow: hidden; color: #233652; font-size: 15px; text-overflow: ellipsis; white-space: nowrap; }
.source-account-id { overflow: hidden; margin-top: 5px; color: #8190a5; font-size: 12px; text-overflow: ellipsis; white-space: nowrap; }
.source-meta-list { display: grid; gap: 7px; margin: 12px 0; font-size: 12px; }
.source-meta-list > div { display: grid; min-width: 0; grid-template-columns: 68px minmax(0, 1fr); gap: 8px; }
.source-meta-list dt { color: #8190a5; }
.source-meta-list dd { overflow: hidden; margin: 0; color: #475569; text-overflow: ellipsis; white-space: nowrap; }
.current-data-source { display: inline-flex; align-items: center; gap: 6px; min-width: 190px; max-width: 260px; height: 32px; padding: 0 10px; border: 1px solid rgba(51,112,255,.16); border-radius: 8px; background: #f7faff; }
.current-data-source .el-icon { flex: 0 0 auto; color: #3370ff; font-size: 14px; }
.current-data-source span { flex: 0 0 auto; color: #64748b; font-size: 11px; }
.current-data-source strong { overflow: hidden; color: #245bdb; font-size: 12px; text-overflow: ellipsis; white-space: nowrap; }

.k8s-page-shell .workbench-card,
.k8s-page-shell .tab-content {
  min-width: 0;
}

.k8s-page-shell .tab-content {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.k8s-page-shell .k8s-summary-grid,
.k8s-page-shell .audit-grid {
  gap: 8px;
}

.k8s-summary-card {
  justify-content: space-between;
  height: 68px;
  min-height: 68px;
  padding: 14px 16px;
  overflow: hidden;
}

.k8s-summary-card .stat-label {
  flex: 0 1 auto;
  min-width: 0;
  font-size: 13px;
  font-weight: 600;
  line-height: 1.2;
  color: #334155;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.k8s-summary-card .stat-value {
  flex: 1 1 auto;
  min-width: 0;
  font-size: clamp(18px, 2.8vw, 24px);
  line-height: 1;
  color: #1f2329;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.k8s-summary-card.audit-card--warning {
  background: linear-gradient(180deg, #fffdfa 0%, #ffffff 100%);
}

.k8s-summary-card.audit-card--success {
  background: linear-gradient(180deg, #fbfffd 0%, #ffffff 100%);
}

.k8s-summary-card.audit-card--danger {
  background: linear-gradient(180deg, #fffafb 0%, #ffffff 100%);
}

.k8s-summary-card.audit-card--action:hover {
  border-color: rgba(36, 91, 219, 0.16);
  box-shadow: 0 10px 20px rgba(36, 91, 219, 0.06);
}

.k8s-summary-card.audit-card--action.is-active {
  border-color: rgba(36, 91, 219, 0.24);
  background: linear-gradient(180deg, #f4f7ff 0%, #ffffff 100%);
  box-shadow: 0 0 0 1px rgba(36, 91, 219, 0.05), 0 12px 22px rgba(36, 91, 219, 0.08);
}

.k8s-page-shell .k8s-context-card {
  padding: 12px;
}

.k8s-page-shell .stats-grid.k8s-summary-grid {
  margin-bottom: 0 !important;
}

.k8s-page-shell .workbench-toolbar--history {
  margin-top: 0;
}

.k8s-page-shell :deep(.section-toolbar) {
  padding-bottom: 2px;
}

.k8s-page-shell :deep(.toolbar-title) {
  color: #0f172a;
}

.k8s-page-shell :deep(.toolbar-desc) {
  color: #64748b;
}

.filter-bar--context {
  align-items: center;
}

.k8s-context-toolbar-right {
  justify-content: flex-end;
  flex-wrap: nowrap;
  gap: 10px;
}

.filter-inline-group {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.filter-inline-group--nowrap {
  flex-wrap: nowrap;
}

.filter-inline-context {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  flex-wrap: nowrap;
  white-space: nowrap;
}

.filter-inline-label {
  flex: 0 0 auto;
  font-size: 12px;
  font-weight: 700;
  color: #64748b;
  line-height: 1;
  white-space: nowrap;
}

.filter-inline-select {
  width: 220px;
  min-width: 220px;
  flex: 0 0 220px;
}

.filter-inline-select--namespace {
  width: 220px;
  min-width: 220px;
  flex-basis: 220px;
}

.context-option-row {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  width: 100%;
  box-sizing: border-box;
}

.context-option-row--all .context-option-title {
  color: #1d4ed8;
}

.context-option-main {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-width: 0;
  gap: 2px;
}

.context-option-head {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.context-option-main--cluster {
  flex-direction: row;
  align-items: center;
  gap: 8px;
}

.context-option-title {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
  font-weight: 700;
  color: #0f172a;
}

.context-option-subtitle {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
  color: #64748b;
}

.context-status-pill {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: 0 0 auto;
  min-width: 40px;
  height: 20px;
  padding: 0 8px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 700;
  line-height: 1;
  white-space: nowrap;
  border: 1px solid transparent;
  box-sizing: border-box;
}

.context-status-pill--success {
  color: #65a30d;
  background: #f0fdf4;
  border-color: #d9f99d;
}

.context-status-pill--warning {
  color: #b45309;
  background: #fffbeb;
  border-color: #fde68a;
}

.context-status-pill--info {
  color: #64748b;
  background: #f8fafc;
  border-color: #cbd5e1;
}

.context-dropdown-empty {
  padding: 16px 10px;
  text-align: center;
  font-size: 12px;
  color: #64748b;
  background: linear-gradient(180deg, rgba(248, 250, 252, 0.98), rgba(255, 255, 255, 0.98));
}

:deep(.k8s-context-popper.el-select-dropdown),
:deep(.k8s-context-popper.el-popper) {
  box-sizing: border-box;
  background: #ffffff !important;
  border-radius: 16px;
  border: 1px solid rgba(203, 213, 225, 0.72) !important;
  box-shadow: 0 18px 40px rgba(15, 23, 42, 0.12) !important;
  overflow: hidden;
  backdrop-filter: blur(12px);
}

:deep(.k8s-context-popper--cluster.el-select-dropdown),
:deep(.k8s-context-popper--cluster.el-popper) {
  width: 220px !important;
  min-width: 220px !important;
  max-width: 220px !important;
}

:deep(.k8s-context-popper--namespace.el-select-dropdown),
:deep(.k8s-context-popper--namespace.el-popper) {
  width: 220px !important;
  min-width: 220px !important;
  max-width: 220px !important;
}

:deep(.k8s-context-popper--namespace .el-select-dropdown) {
  width: 220px !important;
  min-width: 220px !important;
  max-width: 220px !important;
}

:deep(.k8s-context-popper .el-popper__arrow::before) {
  border-color: rgba(203, 213, 225, 0.72) !important;
  background: #fff !important;
}

:deep(.k8s-context-popper .el-select-dropdown__wrap),
:deep(.k8s-context-popper .el-scrollbar),
:deep(.k8s-context-popper .el-select-dropdown__list) {
  background: #ffffff !important;
}

:deep(.k8s-context-popper .el-scrollbar__view) {
  padding: 4px;
  background: #ffffff;
}

:deep(.k8s-context-popper .el-select-dropdown__item) {
  min-height: 52px;
  height: auto;
  padding: 8px 10px;
  border-radius: 12px;
  color: #0f172a !important;
  font-family: inherit !important;
  white-space: normal !important;
  margin-bottom: 2px;
  background: transparent !important;
  transition: background-color 0.18s ease, box-shadow 0.18s ease, transform 0.18s ease;
  box-sizing: border-box;
}

:deep(.k8s-context-popper .el-select-dropdown__item.hover),
:deep(.k8s-context-popper .el-select-dropdown__item:hover) {
  background: rgba(241, 245, 249, 0.92) !important;
  transform: translateY(-1px);
}

:deep(.k8s-context-popper .el-select-dropdown__item.selected),
:deep(.k8s-context-popper .el-select-dropdown__item.is-selected) {
  background: rgba(219, 234, 254, 0.92) !important;
  color: #1d4ed8 !important;
  box-shadow: inset 0 0 0 1px rgba(96, 165, 250, 0.3);
}

:deep(.k8s-context-popper .el-select-dropdown__item.is-disabled) {
  opacity: 0.55;
}

.k8s-resource-card {
  padding-top: 12px;
  gap: 8px;
}

.k8s-cluster-card {
  display: flex;
  flex-direction: column;
  padding: 14px 16px;
  border: 1px solid #e2e8f0;
  border-radius: 16px;
  background: #fff;
}

.k8s-cluster-card :deep(.section-toolbar) {
  padding-bottom: 0;
  margin-bottom: 10px;
}

.k8s-cluster-toolbar {
  margin: 0 0 12px;
  padding: 10px 12px;
  min-height: 52px;
  border: 1px solid #e1e7ef;
  border-radius: 12px;
  background: #f8fafd;
}

.k8s-cluster-search { width: 280px; }

.k8s-cluster-table :deep(.el-table__header-wrapper th) {
  background: #f8fafc;
}

.k8s-page-shell :deep(.el-table) {
  --el-table-border-color: rgba(15, 23, 42, 0.08);
  --el-table-header-bg-color: #f8fafc;
  --el-table-row-hover-bg-color: #f8fbff;
  border-radius: 14px;
  overflow: hidden;
}

.k8s-page-shell :deep(.el-table th.el-table__cell) {
  height: 42px;
  padding: 0;
}

.k8s-page-shell :deep(.el-table th.el-table__cell > .cell) {
  font-size: 12px;
  font-weight: 700;
  color: #64748b;
}

.k8s-page-shell :deep(.el-table .el-table__cell) {
  padding: 10px 0;
}

.k8s-page-shell :deep(.el-table .cell) {
  line-height: 1.5;
}

.k8s-page-shell :deep(.el-table .el-button.is-link) {
  font-size: 12px;
}

.k8s-page-shell :deep(.el-table__fixed-right::before) {
  left: 72px;
  right: auto;
  width: 8px;
  background: linear-gradient(90deg, rgba(15, 23, 42, 0.1), rgba(15, 23, 42, 0));
}

@media (max-width: 1550px) {
  .k8s-cluster-layout { grid-template-columns: minmax(0, 1fr) 350px; }
  .k8s-source-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}

@media (max-width: 1200px) {
  .filter-bar--context .workbench-toolbar-left {
    flex-wrap: wrap;
  }

  .filter-inline-group--nowrap {
    flex-wrap: wrap;
  }
}

@media (max-width: 1100px) {
  .k8s-cluster-layout { grid-template-columns: minmax(0, 1fr); }
  .k8s-source-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
  .selected-cluster-panel { min-height: 0; }
}

@media (max-width: 980px) {
  .k8s-hero {
    flex-direction: column;
    align-items: flex-start;
  }

  .filter-inline-context {
    width: 100%;
  }

  .filter-inline-select {
    flex: 1 1 auto;
    width: auto;
    min-width: 0;
  }
}

@media (max-width: 800px) {
  .k8s-source-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .k8s-cluster-search { width: 240px; }
}

@media (max-width: 550px) {
  .k8s-source-grid { grid-template-columns: minmax(0, 1fr); }
  .k8s-cluster-card { padding: 12px; }
  .k8s-cluster-toolbar { overflow-x: auto; flex-wrap: nowrap; }
  .k8s-cluster-toolbar > * { flex-shrink: 0; }
  .selected-cluster-panel { padding: 12px; }
  .selected-cluster-stat { padding: 8px 6px; }
}
</style>




