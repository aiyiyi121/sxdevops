<template>
  <div class="fade-in release-page workbench-page-shell">
    <section class="hero panel">
      <div class="release-hero-copy">
        <div class="release-hero-title-row release-hero-title-inline">
          <span class="release-header-icon"><el-icon><Promotion /></el-icon></span>
          <h2>{{ pageTitle }}</h2>
          <p class="subtitle inline-subtitle">
            {{ pageSubtitle }}
          </p>
        </div>
      </div>
    </section>

    <div v-if="!isFlowMode" class="audit-grid">
      <button type="button" class="audit-card audit-card--inline audit-card--action" :class="{ 'is-active': activeSummaryKey === 'all' }" @click="applySummaryFilter('all')">
        <div class="stat-value">{{ summary.total }}</div>
        <div class="stat-label">发布单总数</div>
      </button>
      <button type="button" class="audit-card audit-card--inline audit-card--warning audit-card--action" :class="{ 'is-active': activeSummaryKey === 'pending' }" @click="applySummaryFilter('pending')">
        <div class="stat-value">{{ summary.pendingApproval }}</div>
        <div class="stat-label">待审批</div>
      </button>
      <button type="button" class="audit-card audit-card--inline audit-card--success audit-card--action" :class="{ 'is-active': activeSummaryKey === 'running' }" @click="applySummaryFilter('running')">
        <div class="stat-value">{{ summary.running }}</div>
        <div class="stat-label">运行中</div>
      </button>
      <button type="button" class="audit-card audit-card--inline audit-card--danger audit-card--action" :class="{ 'is-active': activeSummaryKey === 'failed' }" @click="applySummaryFilter('failed')">
        <div class="stat-value">{{ summary.failed }}</div>
        <div class="stat-label">执行失败</div>
      </button>
    </div>
    <div v-else class="audit-grid">
      <button type="button" class="audit-card audit-card--inline audit-card--action" :class="{ 'is-active': activeFlowSummaryKey === 'all' }" @click="applyFlowSummaryFilter('all')">
        <div class="stat-value">{{ flowSummary.total }}</div>
        <div class="stat-label">审批流总数</div>
      </button>
      <button type="button" class="audit-card audit-card--inline audit-card--success audit-card--action" :class="{ 'is-active': activeFlowSummaryKey === 'active' }" @click="applyFlowSummaryFilter('active')">
        <div class="stat-value">{{ flowSummary.active }}</div>
        <div class="stat-label">启用中</div>
      </button>
      <button type="button" class="audit-card audit-card--inline audit-card--warning audit-card--action" :class="{ 'is-active': activeFlowSummaryKey === 'scoped' }" @click="applyFlowSummaryFilter('scoped')">
        <div class="stat-value">{{ flowSummary.ticketScopes }}</div>
        <div class="stat-label">覆盖工单类型</div>
      </button>
      <button type="button" class="audit-card audit-card--inline audit-card--action" :class="{ 'is-active': activeFlowSummaryKey === 'dense' }" @click="applyFlowSummaryFilter('dense')">
        <div class="stat-value">{{ flowSummary.nodeCount }}</div>
        <div class="stat-label">审批节点数</div>
      </button>
    </div>

    <div v-if="!isFlowMode" class="workbench-card release-content-card">
      <div class="section-toolbar">
        <div class="toolbar-head">
          <span class="toolbar-title">发布工单列表</span>
          <span class="toolbar-desc">延续任务历史的信息密度和筛选布局，用一套工作台视图处理发布与审批。</span>
        </div>
        <div class="workbench-card-actions">
          <el-button v-if="canManageDeployments" type="primary" @click="openReleaseDialog">
            <el-icon><Plus /></el-icon>
            新建发布单
          </el-button>
        </div>
      </div>

      <div class="workbench-toolbar workbench-toolbar--history release-filter-bar">
        <div class="workbench-toolbar-left">
          <el-select v-model="envFilter" clearable placeholder="环境" style="width: 104px">
            <el-option v-for="item in environmentOptions" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
          <el-select v-model="bizFilter" clearable filterable placeholder="系统" style="width: 128px">
            <el-option v-for="item in businessLineOptions" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
          <el-input v-model="search" clearable placeholder="搜索应用 / 版本 / 镜像 / 目标 / 申请人" style="width: 280px" />
          <el-select v-model="modeFilter" clearable placeholder="模式" style="width: 104px">
            <el-option label="Docker 环境" value="docker_compose" />
            <el-option label="K8s 集群" value="k8s" />
          </el-select>
          <el-select v-model="strategyFilter" clearable placeholder="策略" style="width: 104px">
            <el-option label="标准发布" value="standard" />
            <el-option label="灰度发布" value="canary" />
            <el-option label="批次发布" value="batch" />
          </el-select>
          <el-select v-model="approvalFilter" clearable placeholder="审批状态" style="width: 112px">
            <el-option label="待审批" value="pending" />
            <el-option label="已通过" value="approved" />
            <el-option label="已拒绝" value="rejected" />
          </el-select>
          <el-select v-model="statusFilter" clearable placeholder="执行状态" style="width: 112px">
            <el-option v-for="item in statusOptions" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
        </div>
        <div class="workbench-toolbar-right">
          <el-button class="filter-refresh-btn" @click="fetchDeployments">
            <el-icon><RefreshRight /></el-icon>
            刷新
          </el-button>
        </div>
      </div>

      <el-table v-loading="loading" :data="filteredDeployments" stripe style="width: 100%" class="release-orders-table">
            <el-table-column label="应用" min-width="220">
              <template #default="{ row }">
                <div class="app-cell">
                  <div class="app-cell-title">
                    <span class="app-name">{{ row.app_name }}</span>
                    <el-tag v-if="row.is_current" size="small" type="success">当前生效</el-tag>
                  </div>
                  <div class="sub-text">{{ row.image || '-' }}</div>
                </div>
              </template>
            </el-table-column>
            <el-table-column prop="version" label="版本" width="90" />
            <el-table-column label="策略" min-width="150">
              <template #default="{ row }">
                <div class="strategy-cell">
                  <el-tag :type="strategyTagType(row.release_strategy)" size="small">{{ row.release_strategy_display }}</el-tag>
                  <div class="sub-text">{{ row.strategy_summary }}</div>
                </div>
              </template>
            </el-table-column>
            <el-table-column label="环境 / 系统" min-width="170">
              <template #default="{ row }">
                <div class="scope-cell">
                  <div class="scope-cell__env">
                    <el-tag size="small" :type="envTagType(row.environment)">{{ row.environment_display || '-' }}</el-tag>
                    <span class="scope-cell__mode">{{ row.deploy_mode_display }}</span>
                  </div>
                  <div class="scope-cell__system">
                    <span>{{ row.business_line || '未设置系统' }}</span>
                  </div>
                </div>
              </template>
            </el-table-column>
            <el-table-column label="发布目标" min-width="160">
              <template #default="{ row }">
                <div v-if="row.deploy_mode === 'k8s'" class="stack-cell">
                  <span>{{ row.cluster_name || '-' }}</span>
                  <div class="sub-text">NS: {{ row.namespace || 'default' }}</div>
                </div>
                <div v-else class="stack-cell">
                  <span>{{ row.docker_host_name || row.target_display }}</span>
                </div>
              </template>
            </el-table-column>
            <el-table-column label="审批" width="90">
              <template #default="{ row }">
                <el-tag size="small" :type="approvalTagType(row.approval_status)">{{ row.approval_status_display }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="状态" width="90">
              <template #default="{ row }">
                <el-tag size="small" :type="statusTagType(row.status)">{{ row.status_display }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="审批流" min-width="180">
              <template #default="{ row }">
                <div class="stack-cell">
                  <span>{{ row.approval_flow_name || '默认审批' }}</span>
                  <div class="sub-text">{{ row.current_approval_step?.node_name || row.approval_progress_text }}</div>
                </div>
              </template>
            </el-table-column>
            <el-table-column prop="submitter" label="申请人" width="110" />
            <el-table-column label="发布时间" width="170">
              <template #default="{ row }">{{ formatTime(row.deployed_at) }}</template>
            </el-table-column>
            <el-table-column label="操作" width="240" fixed="right" align="left" header-align="left" class-name="release-actions-column">
              <template #default="{ row }">
                <el-button v-if="canApproveDeployments && row.approval_status === 'pending'" link type="success" size="small" @click="openApprovalDialog(row, 'approve')">通过</el-button>
                <el-button v-if="canApproveDeployments && row.approval_status === 'pending'" link type="danger" size="small" @click="openApprovalDialog(row, 'reject')">驳回</el-button>
                <el-button v-if="canManageDeployments && row.can_advance_batch" link type="warning" size="small" @click="handleAdvanceBatch(row)">推进批次</el-button>
                <el-button v-if="canManageDeployments && row.approval_status !== 'pending' && row.status !== 'deploying'" link type="warning" size="small" @click="handleRerun(row)">重新执行</el-button>
                <el-button v-if="canManageDeployments && row.can_rollback" link type="warning" size="small" @click="handleRollback(row)">回滚</el-button>
                <el-button v-if="canManageDeployments && row.is_current && row.status === 'stopped'" link type="success" size="small" @click="handleStart(row)">启动</el-button>
                <el-button v-if="canManageDeployments && row.is_current && ['running', 'stopped', 'failed'].includes(row.status)" link type="danger" size="small" @click="handleRemove(row)">下线</el-button>
                <el-button link type="info" size="small" @click="viewDetail(row)">详情</el-button>
              </template>
            </el-table-column>
      </el-table>
    </div>
    <div v-else class="workbench-card release-content-card">
      <div class="section-toolbar">
        <div class="toolbar-head">
          <span class="toolbar-title">审批流列表</span>
          <span class="toolbar-desc">和任务历史相同的工作台容器，集中维护流程范围和审批节点。</span>
        </div>
        <div class="workbench-card-actions">
          <el-button v-if="canManageDeployments" type="primary" @click="openFlowDialog()">
            <el-icon><Plus /></el-icon>
            新建审批流
          </el-button>
        </div>
      </div>

      <div class="workbench-toolbar workbench-toolbar--history release-filter-bar">
        <div class="workbench-toolbar-left">
          <el-input v-model="flowSearch" clearable placeholder="搜索流程名称 / 描述" style="width: 280px" />
          <el-select v-model="flowEnvFilter" clearable placeholder="适用环境" style="width: 140px">
            <el-option label="全部环境" value="" />
            <el-option v-for="item in environmentOptions" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
          <el-switch v-model="onlyActiveFlow" inline-prompt active-text="启用中" inactive-text="全部" />
        </div>
        <div class="workbench-toolbar-right">
          <el-button @click="fetchFlows">
            <el-icon><RefreshRight /></el-icon>
            刷新
          </el-button>
        </div>
      </div>

      <el-table v-loading="flowLoading" :data="filteredFlows" stripe style="width: 100%">
            <el-table-column prop="name" label="流程名称" min-width="180" />
            <el-table-column label="适用范围" width="130">
              <template #default="{ row }">
                <el-tag size="small" :type="row.environment ? envTagType(row.environment) : 'info'">{{ row.environment_display }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="适用工单" min-width="180">
              <template #default="{ row }">
                <div class="node-preview">
                  <span
                    v-for="label in (row.ticket_type_labels?.length ? row.ticket_type_labels : ['应用发布'])"
                    :key="`${row.id}-${label}`"
                    class="node-chip node-chip--soft"
                  >
                    {{ label }}
                  </span>
                </div>
              </template>
            </el-table-column>
            <el-table-column label="审批节点" min-width="260">
              <template #default="{ row }">
                <div class="node-preview">
                  <span v-for="node in row.nodes" :key="node.id || `${row.id}-${node.order}`" class="node-chip">
                    {{ node.order }}. {{ node.name }} / {{ approverLabel(node.approver_type, node.approver_value) }}
                  </span>
                </div>
              </template>
            </el-table-column>
            <el-table-column label="状态" width="100">
              <template #default="{ row }">
                <el-tag size="small" :type="row.is_active ? 'success' : 'info'">{{ row.is_active ? '启用中' : '停用' }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="created_by" label="维护人" width="120" />
            <el-table-column label="更新时间" width="180">
              <template #default="{ row }">{{ formatTime(row.updated_at) }}</template>
            </el-table-column>
            <el-table-column label="操作" width="180" fixed="right">
              <template #default="{ row }">
                <el-button v-if="canManageDeployments" link type="primary" size="small" @click="openFlowDialog(row)">编辑</el-button>
                <el-button v-if="canManageDeployments" link type="danger" size="small" @click="handleDeleteFlow(row)">删除</el-button>
              </template>
            </el-table-column>
      </el-table>
    </div>

    <el-dialog top="5vh" :close-on-click-modal="false" class="workbench-edit-dialog" v-model="releaseDialogVisible" title="新建发布单" width="960px" append-to-body destroy-on-close>
      <el-form label-position="top" :model="releaseForm" label-width="110px" class="workbench-editor-form--sectioned release-form-grid">
        <section class="workbench-editor-section">
          <div class="workbench-editor-heading"><span class="workbench-editor-step">01</span><h3>发布信息</h3></div>
          <div class="workbench-editor-grid">
            <el-form-item label="应用名称" required><el-input v-model="releaseForm.app_name" /></el-form-item>
            <el-form-item label="版本号" required><el-input v-model="releaseForm.version" /></el-form-item>
            <el-form-item label="镜像地址" class="span-2"><el-input v-model="releaseForm.image" placeholder="为空时默认使用 应用名:版本号" /></el-form-item>
            <el-form-item label="系统" required>
              <el-select v-model="releaseForm.business_line" filterable placeholder="选择系统" style="width: 100%" @change="handleBusinessLineChange">
                <el-option v-for="item in businessLineOptions" :key="item.value" :label="item.label" :value="item.value" />
              </el-select>
            </el-form-item>
            <el-form-item label="发布环境" required>
              <el-select v-model="releaseForm.environment" style="width: 100%">
                <el-option v-for="item in releaseEnvironmentOptions" :key="item.value" :label="item.label" :value="item.value" />
              </el-select>
            </el-form-item>
          </div>
        </section>
        <section class="workbench-editor-section workbench-editor-section--tinted">
          <div class="workbench-editor-heading"><span class="workbench-editor-step">02</span><h3>部署目标</h3></div>
          <div class="workbench-editor-grid">
            <el-form-item label="发布模式" required>
              <el-radio-group v-model="releaseForm.deploy_mode">
                <el-radio-button label="docker_compose">Docker 环境</el-radio-button>
                <el-radio-button label="k8s">K8s 集群</el-radio-button>
              </el-radio-group>
            </el-form-item>
            <el-form-item v-if="releaseForm.deploy_mode === 'docker_compose'" label="Docker 环境" class="span-2" required>
              <el-select v-model="releaseForm.docker_host" filterable placeholder="选择 Docker 环境" style="width: 100%">
                <el-option v-for="host in dockerHosts" :key="host.id" :label="host.name" :value="host.id" />
              </el-select>
            </el-form-item>
            <template v-else>
              <el-form-item label="目标集群" required>
                <el-select v-model="releaseForm.cluster" filterable placeholder="选择 K8s 集群" style="width: 100%">
                  <el-option v-for="cluster in clusters" :key="cluster.id" :label="cluster.name" :value="cluster.id" />
                </el-select>
              </el-form-item>
              <el-form-item label="命名空间"><el-input v-model="releaseForm.namespace" placeholder="default" /></el-form-item>
              <el-form-item label="发布名称"><el-input v-model="releaseForm.release_name" placeholder="为空时自动生成" /></el-form-item>
              <el-form-item label="副本数"><el-input-number v-model="releaseForm.replicas" :min="1" :max="99" /></el-form-item>
            </template>
            <el-form-item label="容器端口"><el-input-number v-model="releaseForm.container_port" :min="1" :max="65535" /></el-form-item>
            <el-form-item label="服务端口"><el-input-number v-model="releaseForm.service_port" :min="1" :max="65535" /></el-form-item>
          </div>
        </section>
        <section class="workbench-editor-section workbench-editor-section--tinted">
          <div class="workbench-editor-heading"><span class="workbench-editor-step">03</span><h3>发布策略与变更说明</h3></div>
          <div class="workbench-editor-grid">
            <el-form-item label="发布策略" class="span-2">
              <el-radio-group v-model="releaseForm.release_strategy">
                <el-radio-button label="standard">标准发布</el-radio-button>
                <el-radio-button label="canary">灰度发布</el-radio-button>
                <el-radio-button label="batch">批次发布</el-radio-button>
              </el-radio-group>
            </el-form-item>
            <el-form-item v-if="releaseForm.release_strategy === 'canary'" label="灰度比例"><el-input-number v-model="releaseForm.canary_percent" :min="1" :max="100" /></el-form-item>
            <template v-if="releaseForm.release_strategy === 'batch'">
              <el-form-item label="批次数"><el-input-number v-model="releaseForm.batch_total" :min="2" :max="20" /></el-form-item>
              <el-form-item label="单批规模"><el-input-number v-model="releaseForm.batch_size" :min="1" :max="100" /></el-form-item>
            </template>
            <el-form-item label="变更说明" class="workbench-editor-full span-2"><el-input v-model="releaseForm.change_summary" type="textarea" :rows="2" placeholder="发布目的、变更点、影响范围" /></el-form-item>
            <el-form-item label="补充描述" class="workbench-editor-full span-2"><el-input v-model="releaseForm.description" type="textarea" :rows="2" /></el-form-item>
          </div>
        </section>
        <el-collapse class="workbench-editor-advanced">
          <el-collapse-item name="release-advanced" title="环境变量与扩展参数（可选）">
            <div>
              <el-form-item label="环境变量(JSON)" class="workbench-editor-full span-2"><el-input v-model="releaseForm.env_config_text" type="textarea" :rows="4" placeholder='例如：{"SPRING_PROFILES_ACTIVE":"prod"}' /></el-form-item>
              <el-form-item label="策略配置(JSON)" class="workbench-editor-full span-2"><el-input v-model="releaseForm.strategy_config_text" type="textarea" :rows="4" placeholder='可选扩展配置，例如：{"gateway":"istio","trafficPolicy":"header"}' /></el-form-item>
            </div>
          </el-collapse-item>
        </el-collapse>
      </el-form>
      <template #footer>
        <el-button @click="releaseDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="handleSaveRelease">提交审批</el-button>
      </template>
    </el-dialog>

    <el-dialog top="5vh" :close-on-click-modal="false" class="workbench-edit-dialog" v-model="approvalVisible" :title="approvalAction === 'approve' ? '审批通过' : '驳回发布'" width="520px" append-to-body destroy-on-close>
      <el-form label-position="top" :model="approvalForm" label-width="96px">
        <el-form-item label="发布单"><div>#{{ approvalTarget?.id }} · {{ approvalTarget?.app_name }} / {{ approvalTarget?.version }}</div></el-form-item>
        <el-form-item label="当前节点">
          <div>
            {{ approvalTarget?.current_approval_step?.node_name || '默认审批' }}
            <span class="sub-text">{{ approvalTarget?.current_approval_step ? approverLabel(approvalTarget.current_approval_step.approver_type, approvalTarget.current_approval_step.approver_value) : '' }}</span>
          </div>
        </el-form-item>
        <el-form-item label="审批意见"><el-input v-model="approvalForm.comment" type="textarea" :rows="3" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="approvalVisible = false">取消</el-button>
        <el-button :type="approvalAction === 'approve' ? 'success' : 'danger'" :loading="approvalSubmitting" @click="submitApproval">{{ approvalAction === 'approve' ? '确认通过' : '确认驳回' }}</el-button>
      </template>
    </el-dialog>
    <el-dialog top="5vh" :close-on-click-modal="false" class="workbench-edit-dialog" v-model="flowDialogVisible" :title="flowEditingId ? '编辑审批流' : '新建审批流'" width="920px" append-to-body destroy-on-close>
      <el-form label-position="top" :model="flowForm" label-width="100px">
        <div class="release-form-grid">
          <el-form-item label="流程名称" required><el-input v-model="flowForm.name" /></el-form-item>
          <el-form-item label="适用环境">
            <el-select v-model="flowForm.environment" style="width: 100%">
              <el-option label="全部环境" value="" />
              <el-option v-for="item in environmentOptions" :key="item.value" :label="item.label" :value="item.value" />
            </el-select>
          </el-form-item>
          <el-form-item label="适用工单" class="span-2">
            <el-checkbox-group v-model="flowForm.ticket_types">
              <el-checkbox v-for="option in WORK_ORDER_TYPE_OPTIONS" :key="option.value" :value="option.value">
                {{ option.label }}
              </el-checkbox>
            </el-checkbox-group>
          </el-form-item>
          <el-form-item label="描述" class="span-2"><el-input v-model="flowForm.description" type="textarea" :rows="2" /></el-form-item>
          <el-form-item label="启用流程"><el-switch v-model="flowForm.is_active" /></el-form-item>
        </div>
      </el-form>

      <div class="flow-nodes-card">
        <div class="flow-nodes-header">
          <div>
            <div class="section-title">审批节点</div>
            <div class="sub-text">支持按用户 / 角色 / 用户组配置节点，保存后会自动匹配新建发布单。</div>
          </div>
          <el-button type="primary" plain @click="addFlowNode">新增节点</el-button>
        </div>

        <el-table :data="flowForm.nodes" stripe>
          <el-table-column label="顺序" width="90">
            <template #default="{ row }"><el-input-number v-model="row.order" :min="1" :max="20" @change="normalizeNodeOrders" /></template>
          </el-table-column>
          <el-table-column label="节点名称 *" min-width="180">
            <template #default="{ row }"><el-input v-model="row.name" placeholder="如：研发负责人审批" /></template>
          </el-table-column>
          <el-table-column label="审批人类型 *" width="140">
            <template #default="{ row }">
              <el-select v-model="row.approver_type" style="width: 100%">
                <el-option label="指定用户" value="user" />
                <el-option label="指定角色" value="role" />
                <el-option label="指定用户组" value="group" />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column label="审批对象 *" min-width="220">
            <template #default="{ row }">
              <el-select v-model="row.approver_value" filterable style="width: 100%">
                <el-option v-for="option in approverOptions(row.approver_type)" :key="`${row.approver_type}-${option.value}`" :label="option.label" :value="option.value" />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column label="说明" min-width="180">
            <template #default="{ row }"><el-input v-model="row.description" placeholder="可选" /></template>
          </el-table-column>
          <el-table-column label="操作" width="90" fixed="right">
            <template #default="{ $index }"><el-button link type="danger" size="small" @click="removeFlowNode($index)">删除</el-button></template>
          </el-table-column>
        </el-table>
      </div>

      <template #footer>
        <el-button @click="flowDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="flowSaving" @click="handleSaveFlow">保存审批流</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="detailVisible" title="发布详情" width="920px" append-to-body destroy-on-close>
      <template v-if="detailItem">
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item label="应用">{{ detailItem.app_name }}</el-descriptions-item>
          <el-descriptions-item label="版本">{{ detailItem.version }}</el-descriptions-item>
          <el-descriptions-item label="系统">{{ detailItem.business_line || '-' }}</el-descriptions-item>
          <el-descriptions-item label="镜像">{{ detailItem.image || '-' }}</el-descriptions-item>
          <el-descriptions-item label="发布目标">
            <div v-if="detailItem.deploy_mode === 'k8s'" class="stack-cell detail-target-cell">
              <span>{{ detailItem.cluster_name || '-' }}</span>
              <div class="sub-text">NS: {{ detailItem.namespace || 'default' }}</div>
            </div>
            <div v-else class="stack-cell detail-target-cell">
              <span>{{ detailItem.docker_host_name || detailItem.target_display }}</span>
            </div>
          </el-descriptions-item>
          <el-descriptions-item label="CMDB 配置项">{{ detailItem.cmdb_item_name || '-' }}</el-descriptions-item>
          <el-descriptions-item label="CMDB 状态">{{ detailItem.cmdb_item_status || '-' }}</el-descriptions-item>
          <el-descriptions-item label="环境">{{ detailItem.environment_display }}</el-descriptions-item>
          <el-descriptions-item label="发布模式">{{ detailItem.deploy_mode_display }}</el-descriptions-item>
          <el-descriptions-item label="关联目标" :span="2">{{ detailItem.cmdb_targets?.join(' / ') || '-' }}</el-descriptions-item>
          <el-descriptions-item label="发布策略">{{ detailItem.release_strategy_display }}</el-descriptions-item>
          <el-descriptions-item label="策略说明">{{ detailItem.strategy_summary }}</el-descriptions-item>
          <el-descriptions-item label="审批流">{{ detailItem.approval_flow_name || '默认审批' }}</el-descriptions-item>
          <el-descriptions-item label="审批进度">{{ detailItem.approval_progress_text }}</el-descriptions-item>
          <el-descriptions-item label="审批状态">{{ detailItem.approval_status_display }}</el-descriptions-item>
          <el-descriptions-item label="执行状态">{{ detailItem.status_display }}</el-descriptions-item>
          <el-descriptions-item label="申请人">{{ detailItem.submitter || '-' }}</el-descriptions-item>
          <el-descriptions-item label="审批人">{{ detailItem.approver || '-' }}</el-descriptions-item>
          <el-descriptions-item label="执行人">{{ detailItem.deployer || '-' }}</el-descriptions-item>
          <el-descriptions-item label="执行次数">{{ detailItem.execution_count }}</el-descriptions-item>
          <el-descriptions-item label="上一成功版本">{{ detailItem.previous_success_version || '-' }}</el-descriptions-item>
          <el-descriptions-item label="回滚来源">{{ detailItem.rollback_source_version || '-' }}</el-descriptions-item>
          <el-descriptions-item label="审批时间">{{ formatTime(detailItem.approved_at) }}</el-descriptions-item>
          <el-descriptions-item label="完成时间">{{ formatTime(detailItem.finished_at) }}</el-descriptions-item>
          <el-descriptions-item v-if="detailItem.release_strategy === 'batch'" label="批次进度">{{ detailItem.batch_current }}/{{ detailItem.batch_total }}</el-descriptions-item>
          <el-descriptions-item v-if="detailItem.release_strategy === 'canary'" label="灰度比例">{{ detailItem.canary_percent }}%</el-descriptions-item>
          <el-descriptions-item label="发布目录" :span="2">{{ detailItem.deploy_dir || '-' }}</el-descriptions-item>
          <el-descriptions-item label="变更说明" :span="2">{{ detailItem.change_summary || '-' }}</el-descriptions-item>
          <el-descriptions-item label="审批意见" :span="2">{{ detailItem.approval_comment || '-' }}</el-descriptions-item>
        </el-descriptions>

        <el-divider content-position="left">运行状态</el-divider>
        <el-skeleton v-if="detailStatusLoading" :rows="4" animated />
        <template v-else-if="detailStatus">
          <el-alert :title="detailStatus.summary || '状态详情'" :type="statusAlertType(detailStatus.status)" :closable="false" show-icon style="margin-bottom: 8px" />
          <div class="status-meta">
            <el-tag size="small" :type="strategyTagType(detailStatus.release_strategy)">{{ detailStatus.release_strategy_display || '标准发布' }}</el-tag>
            <span class="sub-text">{{ detailStatus.strategy_summary }}</span>
            <span v-if="detailStatus.release_strategy === 'batch'" class="sub-text">批次进度：{{ detailStatus.batch_current }}/{{ detailStatus.batch_total }}</span>
            <span v-if="detailStatus.release_strategy === 'canary'" class="sub-text">灰度比例：{{ detailStatus.canary_percent }}%</span>
          </div>
          <div v-if="detailStatus.message" class="sub-text status-message">{{ detailStatus.message }}</div>
          <el-table v-if="detailStatus.items?.length" :data="detailStatus.items" stripe>
            <el-table-column prop="kind" label="类型" width="120" />
            <el-table-column prop="name" label="名称" min-width="220" />
            <el-table-column prop="state" label="状态" width="140" />
            <el-table-column prop="ready" label="就绪" width="100" />
            <el-table-column prop="ports" label="端口" min-width="120" />
          </el-table>
          <pre v-else-if="detailStatus.raw" class="log-output">{{ detailStatus.raw }}</pre>
        </template>

        <el-divider content-position="left">审批节点</el-divider>
        <div class="approval-steps">
          <div v-if="detailItem.approval_steps?.length" v-for="step in detailItem.approval_steps" :key="step.id" class="approval-step-card">
            <div class="approval-step-top">
              <div class="approval-step-title">{{ step.node_order }}. {{ step.node_name }}</div>
              <el-tag size="small" :type="stepStatusTagType(step.status)">{{ step.status_display }}</el-tag>
            </div>
            <div class="sub-text">{{ approverLabel(step.approver_type, step.approver_value) }}</div>
            <div class="sub-text">审批人：{{ step.approver || '-' }} · 处理时间：{{ formatTime(step.acted_at) }}</div>
            <div class="approval-step-comment">{{ step.comment || '暂无审批意见' }}</div>
          </div>
          <el-empty v-else description="当前未绑定审批流节点，默认走单节点审批" />
        </div>

        <el-divider content-position="left">发布日志</el-divider>
        <pre class="log-output">{{ detailItem.deploy_log || '暂无日志' }}</pre>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Promotion, RefreshRight } from '@element-plus/icons-vue'
import { getDockerHosts, getK8sClusters } from '@/api/modules/container'
import { advanceDeploymentBatch, approveDeployment, createDeployment, createDeploymentApprovalFlow, deleteDeploymentApprovalFlow, getDeploymentApprovalFlows, getDeployments, getDeploymentStatus, getUsers, rejectDeployment, removeDeployment, rerunDeployment, rollbackDeployment, startDeployment, updateDeploymentApprovalFlow } from '@/api/modules/ops'
import { getGroups, getRoles } from '@/api/modules/rbac'
import { useAuthStore } from '@/stores/auth'
import { WORK_ORDER_TYPE_OPTIONS, enrichWorkOrderFlows, getFlowTicketTypes, saveFlowTicketTypes } from '@/utils/workorderFlows'

const route = useRoute()
const authStore = useAuthStore()
const canManageDeployments = computed(() => authStore.hasPermission('ops.deployment.manage'))
const canApproveDeployments = computed(() => authStore.hasPermission('ops.deployment.approve'))

const loading = ref(false)
const flowLoading = ref(false)
const saving = ref(false)
const flowSaving = ref(false)
const deployments = ref([])
const flows = ref([])
const dockerHosts = ref([])
const clusters = ref([])
const users = ref([])
const roles = ref([])
const groups = ref([])
const resourceTree = ref([])

const environmentLabelMap = { prod: '生产', test: '测试', dev: '开发' }
const businessLineOptions = computed(() => (resourceTree.value || [])
  .filter(item => item.node_type === 'biz')
  .map(item => ({ label: item.name, value: item.name })))
const environmentOptions = computed(() => Object.entries(environmentLabelMap).map(([value, label]) => ({ label, value })))
const releaseEnvironmentOptions = computed(() => {
  const bizNode = (resourceTree.value || []).find(item => item.node_type === 'biz' && item.name === releaseForm.value.business_line)
  const options = (bizNode?.children || []).map(item => ({ label: environmentLabelMap[item.name] || item.name, value: item.name }))
  return options.length ? options : environmentOptions.value
})
const statusOptions = [
  { label: '待执行', value: 'pending' },
  { label: '发布中', value: 'deploying' },
  { label: '运行中', value: 'running' },
  { label: '已停止', value: 'stopped' },
  { label: '发布失败', value: 'failed' },
  { label: '已下线', value: 'removed' },
  { label: '已驳回', value: 'rejected' },
]

const search = ref('')
const bizFilter = ref('')
const envFilter = ref('')
const modeFilter = ref('')
const strategyFilter = ref('')
const approvalFilter = ref('')
const statusFilter = ref('')
const onlyCurrent = ref(false)
const flowSearch = ref('')
const flowEnvFilter = ref('')
const onlyActiveFlow = ref(false)
const activeSummaryKey = ref('all')
const activeFlowSummaryKey = ref('all')

const summary = computed(() => ({
  total: deployments.value.length,
  pendingApproval: deployments.value.filter(item => item.approval_status === 'pending').length,
  running: deployments.value.filter(item => item.is_current && item.status === 'running').length,
  failed: deployments.value.filter(item => item.status === 'failed').length,
  flowCount: flows.value.length,
}))
const isFlowMode = computed(() => route.name === 'WorkOrderApprovalFlows')
const pageTitle = computed(() => isFlowMode.value ? '审批流' : '应用发布')
const pageSubtitle = computed(() => (
  isFlowMode.value
    ? '统一配置应用发布、SQL 审计与事务工单可复用的审批流程。'
    : '面向公司自研应用发布，支持 Docker / K8s 环境，支持灰度与批次发布、审批流配置、回滚等。'
))
const flowSummary = computed(() => ({
  total: flows.value.length,
  active: flows.value.filter(item => item.is_active).length,
  ticketScopes: new Set(flows.value.flatMap(item => item.ticket_types || ['deployment'])).size,
  nodeCount: flows.value.reduce((sum, item) => sum + (item.node_count || item.nodes?.length || 0), 0),
}))
function routeQueryText(key) {
  const value = route.query[key]
  return Array.isArray(value) ? String(value[0] || '').trim() : String(value || '').trim()
}

function applyRouteFilters() {
  if (isFlowMode.value) return
  const keyword = routeQueryText('keyword')
  const service = routeQueryText('service')
  const status = routeQueryText('status')
  const environment = routeQueryText('environment')

  if (keyword || service) {
    search.value = keyword || service
    activeSummaryKey.value = 'all'
  }
  if (status && statusOptions.some(item => item.value === status)) {
    statusFilter.value = status
    approvalFilter.value = ''
    onlyCurrent.value = false
    activeSummaryKey.value = status === 'failed' ? 'failed' : 'all'
  }
  if (environment) {
    envFilter.value = environment
  }
}

watch(() => route.query, () => {
  applyRouteFilters()
})

const filteredDeployments = computed(() => deployments.value.filter((item) => {
  if (bizFilter.value && item.business_line !== bizFilter.value) return false
  if (envFilter.value && item.environment !== envFilter.value) return false
  if (modeFilter.value && item.deploy_mode !== modeFilter.value) return false
  if (strategyFilter.value && item.release_strategy !== strategyFilter.value) return false
  if (approvalFilter.value && item.approval_status !== approvalFilter.value) return false
  if (statusFilter.value && item.status !== statusFilter.value) return false
  if (onlyCurrent.value && !item.is_current) return false
  const keyword = search.value.trim().toLowerCase()
  if (!keyword) return true
  return [item.app_name, item.business_line, item.version, item.image, releaseTargetSearchText(item), item.submitter, item.approval_flow_name].some(value => String(value || '').toLowerCase().includes(keyword))
}))

const filteredFlows = computed(() => flows.value.filter((item) => {
  const ticketTypes = item.ticket_types || ['deployment']
  if (activeFlowSummaryKey.value === 'active' && !item.is_active) return false
  if (activeFlowSummaryKey.value === 'scoped' && !(ticketTypes.length > 1 || ticketTypes[0] !== 'deployment')) return false
  if (activeFlowSummaryKey.value === 'dense' && (item.node_count || item.nodes?.length || 0) < 3) return false
  if (flowEnvFilter.value !== '' && item.environment !== flowEnvFilter.value) return false
  if (onlyActiveFlow.value && !item.is_active) return false
  const keyword = flowSearch.value.trim().toLowerCase()
  if (!keyword) return true
  return [item.name, item.description, item.created_by].some(value => String(value || '').toLowerCase().includes(keyword))
}))

const envTagType = (env) => ({ prod: 'danger', test: 'warning', dev: 'info' }[env] || '')
const approvalTagType = (status) => ({ pending: 'warning', approved: 'success', rejected: 'danger' }[status] || '')
const statusTagType = (status) => ({ pending: 'warning', rejected: 'danger', deploying: 'warning', running: 'success', stopped: 'info', failed: 'danger', removed: 'info' }[status] || '')
const stepStatusTagType = (status) => ({ pending: 'warning', approved: 'success', rejected: 'danger' }[status] || '')
const strategyTagType = (strategy) => ({ standard: '', canary: 'warning', batch: 'success' }[strategy] || '')
const statusAlertType = (status) => ({ running: 'success', stopped: 'warning', deploying: 'info', pending: 'warning', failed: 'error', removed: 'info', rejected: 'error' }[status] || 'info')
const formatTime = (value) => (value ? new Date(value).toLocaleString('zh-CN') : '-')

function safeList(payload) {
  return payload?.results || payload || []
}

function releaseTargetSearchText(item) {
  if (item.deploy_mode === 'k8s') {
    return [item.cluster_name, item.namespace, item.target_display].join(' ')
  }
  return [item.docker_host_name, item.target_display].join(' ')
}

function parseJsonText(text, fieldName) {
  if (!text || !text.trim()) return {}
  try {
    const parsed = JSON.parse(text)
    if (typeof parsed !== 'object' || Array.isArray(parsed) || parsed === null) throw new Error()
    return parsed
  } catch {
    throw new Error(`${fieldName} 需要填写合法 JSON 对象`)
  }
}

async function fetchDeployments() {
  loading.value = true
  try {
    deployments.value = safeList(await getDeployments())
  } finally {
    loading.value = false
  }
}

function applySummaryFilter(key) {
  activeSummaryKey.value = key
  approvalFilter.value = ''
  statusFilter.value = ''
  onlyCurrent.value = false

  if (key === 'pending') {
    approvalFilter.value = 'pending'
    return
  }
  if (key === 'running') {
    statusFilter.value = 'running'
    onlyCurrent.value = true
    return
  }
  if (key === 'failed') {
    statusFilter.value = 'failed'
  }
}

function applyFlowSummaryFilter(key) {
  activeFlowSummaryKey.value = key
  flowSearch.value = ''
  flowEnvFilter.value = ''
  onlyActiveFlow.value = false
}

async function fetchFlows() {
  flowLoading.value = true
  try {
    flows.value = enrichWorkOrderFlows(safeList(await getDeploymentApprovalFlows()))
  } finally {
    flowLoading.value = false
  }
}

async function fetchLookups() {
  const [dockerHostRes, clusterRes, userRes, roleRes, groupRes] = await Promise.allSettled([getDockerHosts(), getK8sClusters(), getUsers(), getRoles(), getGroups()])
  dockerHosts.value = dockerHostRes.status === 'fulfilled' ? safeList(dockerHostRes.value) : []
  clusters.value = clusterRes.status === 'fulfilled' ? safeList(clusterRes.value) : []
  users.value = userRes.status === 'fulfilled' ? safeList(userRes.value) : []
  roles.value = roleRes.status === 'fulfilled' ? safeList(roleRes.value) : []
  groups.value = groupRes.status === 'fulfilled' ? safeList(groupRes.value) : []
  resourceTree.value = []
}

const releaseDialogVisible = ref(false)
const releaseForm = ref({})
function resetReleaseForm() {
  releaseForm.value = { app_name: '', business_line: '', version: '', image: '', environment: '', deploy_mode: 'docker_compose', docker_host: null, host: null, cluster: null, namespace: 'default', release_name: '', replicas: 1, container_port: null, service_port: null, release_strategy: 'standard', canary_percent: 10, batch_total: 2, batch_size: 1, change_summary: '', description: '', env_config_text: '', strategy_config_text: '' }
}
function handleBusinessLineChange(value) {
  const matched = (resourceTree.value || []).find(item => item.node_type === 'biz' && item.name === value)
  const envList = (matched?.children || []).map(item => item.name)
  if (!envList.length) return
  if (!envList.includes(releaseForm.value.environment)) {
    releaseForm.value.environment = envList[0]
  }
}
function openReleaseDialog() {
  resetReleaseForm()
  releaseDialogVisible.value = true
}
async function handleSaveRelease() {
  if (!releaseForm.value.app_name || !releaseForm.value.version) return ElMessage.warning('请填写应用名称和版本号')
  if (!releaseForm.value.business_line) return ElMessage.warning('请选择系统')
  if (!releaseForm.value.environment) return ElMessage.warning('请选择环境')
  if (releaseForm.value.deploy_mode === 'docker_compose' && !releaseForm.value.docker_host) return ElMessage.warning('请选择 Docker 环境')
  if (releaseForm.value.deploy_mode === 'k8s' && !releaseForm.value.cluster) return ElMessage.warning('请选择目标集群')
  let envConfig = {}
  let strategyConfig = {}
  try {
    envConfig = parseJsonText(releaseForm.value.env_config_text, '环境变量')
    strategyConfig = parseJsonText(releaseForm.value.strategy_config_text, '策略配置')
  } catch (error) {
    return ElMessage.warning(error.message)
  }
  saving.value = true
  try {
    const payload = { ...releaseForm.value, env_config: envConfig, strategy_config: strategyConfig }
    delete payload.env_config_text
    delete payload.strategy_config_text
    await createDeployment(payload)
    ElMessage.success('发布单已提交，等待审批')
    releaseDialogVisible.value = false
    await fetchDeployments()
  } finally {
    saving.value = false
  }
}

const approvalVisible = ref(false)
const approvalAction = ref('approve')
const approvalTarget = ref(null)
const approvalSubmitting = ref(false)
const approvalForm = ref({ comment: '' })
function openApprovalDialog(row, action) {
  approvalTarget.value = row
  approvalAction.value = action
  approvalForm.value = { comment: '' }
  approvalVisible.value = true
}
async function submitApproval() {
  approvalSubmitting.value = true
  try {
    const fn = approvalAction.value === 'approve' ? approveDeployment : rejectDeployment
    const res = await fn(approvalTarget.value.id, approvalForm.value)
    const message = approvalAction.value === 'approve' ? (res.approval_status === 'approved' ? '审批通过，已启动发布执行' : '审批通过，已流转到下一节点') : '已驳回发布申请'
    ElMessage.success(message)
    approvalVisible.value = false
    await fetchDeployments()
  } finally {
    approvalSubmitting.value = false
  }
}

async function askSummary(title, value) {
  try {
    const res = await ElMessageBox.prompt('可填写本次操作说明，便于审计留痕。', title, { inputValue: value, confirmButtonText: '确认', cancelButtonText: '取消' })
    return res.value || ''
  } catch (error) {
    if (error === 'cancel' || error === 'close') return null
    throw error
  }
}
async function handleRerun(row) {
  const changeSummary = await askSummary('重新执行发布', `重新执行 #${row.id}`)
  if (changeSummary === null) return
  await rerunDeployment(row.id, { change_summary: changeSummary })
  ElMessage.success('已创建新的重新执行发布单')
  await fetchDeployments()
}
async function handleRollback(row) {
  const changeSummary = await askSummary('创建回滚发布单', `回滚 ${row.app_name} 到上一成功版本`)
  if (changeSummary === null) return
  await rollbackDeployment(row.id, { change_summary: changeSummary })
  ElMessage.success('已创建回滚发布单')
  await fetchDeployments()
}
async function handleAdvanceBatch(row) {
  const changeSummary = await askSummary('推进发布批次', `推进 ${row.app_name} 的下一批次`)
  if (changeSummary === null) return
  await advanceDeploymentBatch(row.id, { change_summary: changeSummary })
  ElMessage.success('批次已推进')
  await fetchDeployments()
}
async function handleStart(row) { await startDeployment(row.id); ElMessage.success('当前版本已启动'); await fetchDeployments() }
async function handleRemove(row) { await removeDeployment(row.id); ElMessage.success('当前版本已下线'); await fetchDeployments() }
const detailVisible = ref(false)
const detailItem = ref(null)
const detailStatusLoading = ref(false)
const detailStatus = ref(null)
async function viewDetail(row) {
  detailItem.value = row
  detailVisible.value = true
  detailStatusLoading.value = true
  detailStatus.value = null
  try {
    detailStatus.value = await getDeploymentStatus(row.id)
  } finally {
    detailStatusLoading.value = false
  }
}

const flowDialogVisible = ref(false)
const flowEditingId = ref(null)
const flowForm = ref({})
function resetFlowForm() {
  flowForm.value = {
    name: '',
    environment: '',
    ticket_types: ['deployment'],
    description: '',
    is_active: true,
    nodes: [{ order: 1, name: '', approver_type: 'user', approver_value: '', description: '' }],
  }
}
function openFlowDialog(row = null) {
  if (!row) {
    flowEditingId.value = null
    resetFlowForm()
  } else {
    flowEditingId.value = row.id
    flowForm.value = {
      name: row.name,
      environment: row.environment ?? '',
      ticket_types: getFlowTicketTypes(row),
      description: row.description || '',
      is_active: row.is_active,
      nodes: (row.nodes || []).map(node => ({
        order: node.order,
        name: node.name,
        approver_type: node.approver_type,
        approver_value: node.approver_value,
        description: node.description || '',
      })),
    }
  }
  flowDialogVisible.value = true
}
function addFlowNode() { flowForm.value.nodes.push({ order: flowForm.value.nodes.length + 1, name: '', approver_type: 'user', approver_value: '', description: '' }) }
function removeFlowNode(index) {
  if (flowForm.value.nodes.length === 1) return ElMessage.warning('至少保留一个审批节点')
  flowForm.value.nodes.splice(index, 1)
  normalizeNodeOrders()
}
function normalizeNodeOrders() {
  const ordered = [...flowForm.value.nodes].sort((a, b) => a.order - b.order)
  flowForm.value.nodes = ordered.map((node, index) => ({ ...node, order: index + 1 }))
}
function approverOptions(type) {
  if (type === 'role') return roles.value.map(item => ({ label: item.name, value: item.code }))
  if (type === 'group') return groups.value.map(item => ({ label: item.name, value: item.code }))
  return users.value.map(item => ({ label: item.display_name || item.username, value: item.username }))
}
function approverLabel(type, value) {
  if (!value) return '-'
  const options = approverOptions(type)
  return options.find(item => item.value === value)?.label || value
}
async function handleSaveFlow() {
  if (!flowForm.value.name) return ElMessage.warning('请填写流程名称')
  if (!flowForm.value.ticket_types?.length) return ElMessage.warning('请至少选择一个适用工单')
  if (!flowForm.value.nodes.length) return ElMessage.warning('请至少配置一个审批节点')
  normalizeNodeOrders()
  const invalidNode = flowForm.value.nodes.find(node => !node.name || !node.approver_value)
  if (invalidNode) return ElMessage.warning('请完善所有审批节点的名称和审批对象')
  flowSaving.value = true
  try {
    const payload = {
      name: flowForm.value.name,
      environment: flowForm.value.environment,
      description: flowForm.value.description,
      is_active: flowForm.value.is_active,
      nodes: flowForm.value.nodes.map(node => ({
        order: node.order,
        name: node.name,
        approver_type: node.approver_type,
        approver_value: node.approver_value,
        description: node.description || '',
      })),
    }
    let savedFlow = null
    if (flowEditingId.value) {
      savedFlow = await updateDeploymentApprovalFlow(flowEditingId.value, payload)
      saveFlowTicketTypes(flowEditingId.value, flowForm.value.ticket_types)
      ElMessage.success('审批流已更新')
    } else {
      savedFlow = await createDeploymentApprovalFlow(payload)
      saveFlowTicketTypes(savedFlow?.id, flowForm.value.ticket_types)
      ElMessage.success('审批流已创建')
    }
    flowDialogVisible.value = false
    await fetchFlows()
  } finally {
    flowSaving.value = false
  }
}
async function handleDeleteFlow(row) {
  await ElMessageBox.confirm(`确认删除审批流“${row.name}”吗？`, '提示', { type: 'warning' })
  await deleteDeploymentApprovalFlow(row.id)
  ElMessage.success('审批流已删除')
  await fetchFlows()
}

onMounted(async () => {
  resetReleaseForm()
  resetFlowForm()
  applySummaryFilter('all')
  applyRouteFilters()
  await Promise.all([fetchDeployments(), fetchFlows(), fetchLookups()])
})
</script>

<style scoped>
.release-page{display:flex;flex-direction:column;gap:6px}
.panel{background:linear-gradient(180deg,rgba(255,255,255,.98) 0%,rgba(250,252,255,.96) 100%);border:1px solid rgba(15,23,42,.08);border-radius:18px;box-shadow:0 8px 24px rgba(15,23,42,.04);padding:14px 16px}
.hero{background:linear-gradient(135deg,#fbfdff 0%,#f7faff 52%,#f9fbfd 100%);display:flex;gap:12px;justify-content:space-between;border-color:rgba(36,91,219,.09)}
.hero h2{color:#0f172a;font-size:23px;margin:0}
.subtitle{color:#475569;margin:8px 0 0;max-width:620px}
.status-meta{display:flex;gap:10px}
.release-hero-title-row{display:flex;align-items:center;gap:12px}
.release-hero-title-inline{flex-wrap:wrap}
.inline-subtitle{margin:0;max-width:none;font-size:13px;line-height:1.45}
.release-header-icon{width:42px;height:42px;border-radius:14px;display:inline-flex;align-items:center;justify-content:center;font-size:20px;color:#245bdb;background:linear-gradient(180deg,#f3f7ff 0%,#ebf2ff 100%);border:1px solid rgba(36,91,219,.12);box-shadow:inset 0 1px 0 rgba(255,255,255,.8)}
.audit-grid{gap:10px}
.audit-card{border-radius:14px;border:1px solid rgba(15,23,42,.08);background:linear-gradient(180deg,rgba(255,255,255,.98) 0%,rgba(252,253,255,.94) 100%);box-shadow:0 4px 14px rgba(15,23,42,.03)}
.audit-card--inline{min-height:68px;padding:14px 16px}
.audit-card .stat-label{font-size:13px;font-weight:600;color:#334155}
.audit-card .stat-value{font-size:24px;color:#1f2329}
.audit-card--warning{background:linear-gradient(180deg,#fffdfa 0%,#ffffff 100%)}
.audit-card--success{background:linear-gradient(180deg,#fbfffd 0%,#ffffff 100%)}
.audit-card--danger{background:linear-gradient(180deg,#fffafb 0%,#ffffff 100%)}
.audit-card--action:hover{border-color:rgba(36,91,219,.16);box-shadow:0 10px 20px rgba(36,91,219,.06)}
.audit-card--action.is-active{border-color:rgba(36,91,219,.24);background:linear-gradient(180deg,#f4f7ff 0%,#ffffff 100%);box-shadow:0 0 0 1px rgba(36,91,219,.05),0 12px 22px rgba(36,91,219,.08)}
.sub-text{font-size:13px;color:var(--text-secondary);font-weight:400}
.release-content-card{margin-top:0}
.release-filter-bar{align-items:flex-start}.app-cell,.stack-cell,.strategy-cell{display:flex;flex-direction:column;gap:6px}.app-cell-title{display:flex;align-items:center;gap:8px}.app-name{font-weight:600}
.tag-line{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.scope-cell{display:flex;flex-direction:column;gap:6px;min-width:0}
.scope-cell__env{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.scope-cell__mode{font-size:12px;color:#64748b}
.scope-cell__system{font-size:13px;color:#0f172a;font-weight:600;line-height:1.35;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.detail-target-cell{min-width:0}
:deep(.release-orders-table .release-actions-column .cell){display:flex;justify-content:flex-start;padding-left:8px;padding-right:0}
:deep(.release-orders-table .el-table__fixed-right::before){left:72px;right:auto;width:8px;background:linear-gradient(90deg,rgba(15,23,42,.1),rgba(15,23,42,0))}
.node-preview{display:flex;flex-wrap:wrap;gap:8px}.node-chip{display:inline-flex;align-items:center;gap:4px;padding:4px 10px;border-radius:999px;background:rgba(64,158,255,.08);color:#409eff;font-size:12px}
.release-form-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:0 18px}.release-form-grid :deep(.span-2){grid-column:span 2}
.flow-nodes-card{margin-top:8px;border:1px solid var(--border-color-light);border-radius:16px;padding:16px;background:var(--el-bg-color-page)}.flow-nodes-header{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:8px}.section-title{font-size:15px;font-weight:600;color:var(--text-primary)}
.status-meta{display:flex;flex-wrap:wrap;align-items:center;gap:10px;margin-bottom:8px}.status-message{margin-bottom:8px}.approval-steps{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:8px}.approval-step-card{padding:14px;border-radius:14px;border:1px solid var(--border-color-light);background:var(--el-fill-color-lighter);display:flex;flex-direction:column;gap:8px}.approval-step-top{display:flex;justify-content:space-between;align-items:center;gap:10px}.approval-step-title{font-weight:600}.approval-step-comment{font-size:13px;color:var(--text-regular);line-height:1.6}
.log-output{max-height:56vh;overflow:auto;padding:12px;border-radius:12px;background:#0f172a;color:#e2e8f0;font-size:12px;line-height:1.6;white-space:pre-wrap;word-break:break-word}
@media (max-width:1200px){.release-form-grid{grid-template-columns:1fr}.release-form-grid :deep(.span-2){grid-column:span 1}}
@media (max-width:768px){.hero{flex-direction:column}}
.hero.panel { border-radius: 20px; }
</style>

