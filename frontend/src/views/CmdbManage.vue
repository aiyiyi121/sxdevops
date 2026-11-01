<template>
  <div class="fade-in cmdb-page workbench-page-shell" :class="{ 'cmdb-page--model': activeTab === 'model', 'cmdb-page--governance': activeTab === 'governance' }">
    <CmdbPlatformHeader v-if="isPlatformConfigRoute" />
    <section v-else class="hero panel">
      <div class="cmdb-hero-copy">
        <div class="cmdb-hero-title-row">
          <span class="cmdb-header-icon"><el-icon><component :is="activeWorkspace?.icon || Monitor" /></el-icon></span>
          <h2>{{ activeHeroTitle }}</h2>
          <p class="page-inline-desc">{{ activeWorkspace?.desc || '统一纳管资产台账、自动注册、生命周期与模型字段。' }}</p>
        </div>
      </div>
    </section>

    <div v-if="!isPlatformConfigRoute && activeWorkspaceTabs.length > 1" class="neo-tabs theme-blue cmdb-tabs cmdb-primary-tabs">
      <button
        v-for="tab in activeWorkspaceTabs"
        :key="tab.key"
        type="button"
        class="neo-tab-btn"
        :class="{ active: activeTab === tab.key }"
        @click="switchTab(tab.key)"
      >
        <el-icon><component :is="tab.icon" /></el-icon>
        <span>{{ tab.label }}</span>
      </button>
    </div>

    <div class="workbench-card cmdb-content-card" :class="{ 'cmdb-content-card--opsany': isOpsanyCmdbSurface }">
      <div class="section-toolbar">
        <div class="toolbar-head" :class="{ 'opsany-page-head': isOpsanyCmdbSurface }">
          <span class="toolbar-title">{{ activeTab === 'governance' ? '治理工作台' : (isOpsanyCmdbSurface ? activeSurfaceTitle : activeTabMeta?.label) }}</span>
          <span v-if="isOpsanyCmdbSurface" class="opsany-breadcrumb">{{ activeSurfaceBreadcrumb }}</span>
          <span class="toolbar-desc">{{ activeTab === 'governance' ? '按风险类型集中处置资产生命周期、数据同步与运行容量问题。' : (isOpsanyCmdbSurface ? activeSurfaceDesc : activeTabMeta?.desc) }}</span>
          <span v-if="isOpsanyCmdbSurface" class="opsany-help-link">了解更多</span>
        </div>
        <div class="workbench-card-actions">
          <el-button v-if="activeTab === 'ledger' && canManageCi" type="primary" @click="openCiDialog()">
            <el-icon><Plus /></el-icon>
            新建资产
          </el-button>
          <el-button v-if="activeTab === 'ledger' && canManageCi" :disabled="!ledgerSelection.length" @click="openBulkLedgerDialog">
            批量维护
          </el-button>
          <el-button v-if="activeTab === 'ledger' && canManageCi" @click="openBulkImportDialog">
            <el-icon><UploadFilled /></el-icon>
            批量导入
          </el-button>
          <el-button v-if="activeTab === 'ledger' && canViewCi" :loading="exportingLedger" :disabled="!ledgerSelection.length" @click="exportLedger">
            <el-icon><Download /></el-icon>
            批量导出
          </el-button>
          <el-button v-if="activeTab === 'requests' && canSubmitRequest" type="primary" @click="openRequestDialog">
            <el-icon><Plus /></el-icon>
            新建申请
          </el-button>
          <template v-if="activeTab === 'thresholds' && canManageCi">
            <el-button type="primary" @click="openThresholdPolicyDialog()">
              <el-icon><Plus /></el-icon>
              新建策略
            </el-button>
            <el-button @click="openMetricDialog()">
              <el-icon><Plus /></el-icon>
              录入指标
            </el-button>
          </template>
          <template v-if="isModelConfigRoute && canManageModel">
            <el-button :loading="builtinRefreshing" @click="refreshBuiltinCmdb">
              <el-icon><Download /></el-icon>
              导入内置分类
            </el-button>
            <el-button @click="openModelGroupDialog()">
              <el-icon><Plus /></el-icon>
              新建分组
            </el-button>
            <el-button type="primary" @click="openModelDialog()">
              <el-icon><Plus /></el-icon>
              新建模型
            </el-button>
          </template>
          <el-button v-if="activeTab !== 'model'" class="filter-refresh-btn" :loading="loading" @click="reloadAll">
            <el-icon><RefreshRight /></el-icon>
            刷新
          </el-button>
        </div>
      </div>

      <div v-if="activeTab === 'thresholds' || activeTab === 'audit'" class="platform-setting-strip">
        <div v-for="item in platformSettingCards" :key="item.key" class="platform-setting-card" :class="item.tone">
          <span>{{ item.label }}</span>
          <strong>{{ item.value }}</strong>
          <small>{{ item.desc }}</small>
        </div>
      </div>

      <template v-if="activeTab === 'overview'">
        <div class="overview-scope-toolbar">
          <div class="view-mode-bar overview-dimension-tabs">
            <button
              v-for="item in overviewResourceDimensionOptions"
              :key="item.key"
              type="button"
              :class="{ active: overviewResourceDimension === item.key }"
              @click="overviewResourceDimension = item.key"
            >
              {{ item.label }}
            </button>
          </div>
          <el-select
            v-model="overviewResourceScope"
            size="small"
            filterable
            :placeholder="overviewResourceScopePlaceholder"
            style="width: 240px"
          >
            <el-option
              v-for="item in overviewResourceScopeOptions"
              :key="item.value"
              :label="item.selectedLabel || item.title || item.label"
              :value="item.value"
            >
              <div class="overview-scope-option">
                <span>{{ item.title || item.label }}</span>
                <el-tag v-if="item.kindLabel" size="small" :type="item.kindType || 'info'">{{ item.kindLabel }}</el-tag>
              </div>
            </el-option>
          </el-select>
          <el-tag size="small" type="info">{{ overviewResourceScopeLabel }}</el-tag>
        </div>
        <div v-if="showOverviewTotalResourceView" class="total-resource-panel">
          <div class="total-resource-head">
            <div class="mini-panel-heading mini-panel-heading--inline">
              <div class="mini-panel-title">总资源视图</div>
              <div class="mini-panel-desc">{{ overviewResourceScopeDesc }}</div>
            </div>
            <el-tag class="total-resource-status" size="small" :type="resourceRequestNeeded ? 'warning' : 'success'">{{ resourceRequestNeeded ? '建议申请' : '暂不需要申请' }}</el-tag>
          </div>
          <div v-if="overviewMetricCollectionNotices.length" class="overview-metric-notice-list overview-metric-notice-list--under-title">
            <div v-for="item in overviewMetricCollectionNotices" :key="item.key" class="overview-metric-notice" :class="item.tone">
              <span>{{ item.title }}</span>
              <em>{{ item.desc }}</em>
            </div>
          </div>
          <div class="resource-usage-grid">
            <div v-for="item in aggregateResourceRows" :key="item.key" class="resource-usage-card" :class="item.tone">
              <div class="resource-usage-top">
                <span>{{ item.label }}</span>
                <div v-if="item.displayValue" class="resource-usage-main-value">
                  <small v-if="item.displayHint">{{ item.displayHint }}</small>
                  <strong>{{ item.displayValue }}</strong>
                </div>
              </div>
              <div v-if="item.progressRows?.length" class="resource-waterline-stack">
                <div
                  v-for="line in item.progressRows"
                  :key="line.key"
                  class="resource-waterline-line"
                  :class="[{ 'is-muted': !line.hasData }, line.tone]"
                >
                  <div class="resource-waterline-line-head">
                    <div>
                      <span>{{ line.label }}</span>
                      <em>{{ line.desc }}</em>
                    </div>
                    <strong>{{ line.percentText }}</strong>
                  </div>
                  <el-progress :percentage="line.percent" :stroke-width="7" :show-text="false" :color="line.color" />
                  <div class="resource-waterline-values">
                    <span>当前用量 <strong>{{ line.currentText }}</strong></span>
                    <span>总量 <strong>{{ line.totalText }}</strong></span>
                  </div>
                </div>
              </div>
              <el-progress v-else :percentage="item.percent" :stroke-width="8" :show-text="false" />
              <div class="resource-usage-meta">
                <span>{{ item.meta }}</span>
                <el-tag size="small" :type="item.tagType">{{ item.statusText }}</el-tag>
              </div>
              <div v-if="item.breakdownRows?.length" class="resource-usage-breakdown">
                <span v-for="row in item.breakdownRows" :key="row.label">
                  <em>{{ row.label }}</em>
                  <strong>{{ row.value }}</strong>
                </span>
              </div>
            </div>
          </div>
        </div>

        <div class="cmdb-overview-grid">
          <div class="mini-panel mini-panel--wide">
            <div class="mini-panel-head">
              <div class="mini-panel-heading mini-panel-heading--inline">
                <div class="mini-panel-title">资源盘点</div>
                <div class="mini-panel-desc">按模型和来源拆分当前纳管资源。</div>
              </div>
            </div>
            <div class="distribution-list">
              <div v-for="item in overviewInventoryByType" :key="item.type_name" class="distribution-row">
                <span>{{ item.type_name || '未分类' }}</span>
                <strong>{{ item.count }}</strong>
              </div>
              <el-empty v-if="!overviewInventoryByType.length" description="暂无资源数据" :image-size="72" />
            </div>
          </div>
          <div class="mini-panel overview-governance-panel">
            <div class="mini-panel-head overview-governance-panel-head">
              <div class="mini-panel-heading mini-panel-heading--inline">
                <div class="mini-panel-title">资产治理</div>
                <div class="mini-panel-desc">集中查看当前范围的风险分类与处置建议。</div>
              </div>
              <span class="overview-panel-counter">{{ pendingGovernanceCount }} 项待处理</span>
              <el-button link type="primary" @click="openAssetGovernance('all')">
                进入治理 <el-icon><ArrowRight /></el-icon>
              </el-button>
            </div>
            <div class="risk-list">
              <button
                v-for="item in governanceRiskRows"
                :key="item.key"
                type="button"
                class="risk-row risk-row--action"
                :class="item.tone"
                @click="applyGovernanceRisk(item)"
              >
                <span class="risk-row-head">
                  <span class="risk-row-icon"><el-icon><component :is="item.icon" /></el-icon></span>
                  <span class="risk-row-label">{{ item.label }}</span>
                  <strong>{{ item.value }}</strong>
                </span>
                <span class="risk-row-footer">
                  <span class="risk-row-status">{{ item.value ? '需要处理' : '当前正常' }}</span>
                </span>
              </button>
            </div>
            <section class="overview-governance-section overview-governance-section--suggestions">
              <div class="overview-governance-section-head">
                <strong>治理建议</strong>
                <span>{{ overviewSuggestionRows.length }} 条建议</span>
              </div>
              <div class="suggestion-list suggestion-list--compact">
                <button
                  v-for="item in overviewSuggestionRows"
                  :key="`${item.type}-${item.title}`"
                  type="button"
                  class="suggestion-row suggestion-row--action"
                  @click="applyOverviewSuggestion(item)"
                >
                  <div class="suggestion-copy">
                    <el-tag size="small" :type="suggestionTagType(item.severity)">{{ overviewSuggestionTypeText(item.type) }}</el-tag>
                    <el-tooltip :content="item.title" placement="top" :show-after="300">
                      <span class="suggestion-title">{{ item.title }}</span>
                    </el-tooltip>
                    <el-tag v-if="item.type === 'capacity'" size="small" :type="capacityGovernanceTagType(item)">
                      {{ capacityGovernanceText(item) }}
                    </el-tag>
                  </div>
                  <span class="suggestion-link">去处理</span>
                </button>
                <el-empty v-if="!overviewSuggestionRows.length" description="暂无治理建议" :image-size="72" />
              </div>
            </section>
          </div>
          <div class="mini-panel overview-cost-panel">
            <div class="mini-panel-head overview-cost-panel-head">
              <div class="mini-panel-heading mini-panel-heading--inline">
                <div class="mini-panel-title">成本管理</div>
                <div class="mini-panel-desc">{{ overviewCostScopeDesc }}</div>
              </div>
              <el-button link type="primary" @click="openCostManagement">
                查看详情 <el-icon><ArrowRight /></el-icon>
              </el-button>
            </div>
            <div v-loading="overviewCostLoading" class="overview-cost-summary">
              <div class="overview-cost-total">
                <span>{{ overviewCostTotalLabel }}</span>
                <strong>{{ formatMoney(overviewCostTotal) }}</strong>
                <small>{{ currentMonth() }} 月</small>
              </div>
              <div class="overview-cost-categories">
                <div class="overview-cost-categories-head">
                  <span>待优化成本项</span>
                  <strong>{{ overviewCostOptimizationCount }} 项</strong>
                </div>
                <div v-if="overviewCostCategoryRows.length" class="overview-cost-category-list">
                  <div v-for="item in overviewCostCategoryRows" :key="item.type" class="overview-cost-category-row">
                    <span>{{ item.label || item.type }}</span>
                    <strong>{{ item.count }} 项</strong>
                  </div>
                </div>
                <span v-else class="overview-cost-empty">当前暂无待优化成本项</span>
              </div>
            </div>
          </div>
        </div>
      </template>

      <template v-else-if="activeTab === 'repository'">
        <div v-loading="repositoryLoading" class="repository-shell">
          <div class="repository-summary-grid">
            <div v-for="item in repositoryCards" :key="item.key" class="repository-summary-card" :class="item.tone">
              <span>{{ item.label }}</span>
              <strong>{{ item.value }}</strong>
            </div>
          </div>

          <div class="opsany-model-tabs">
            <button
              v-for="item in repositoryGroupTabs"
              :key="item.key"
              type="button"
              :class="{ active: activeRepositoryGroupKey === item.key }"
              @click="activeRepositoryGroupKey = item.key"
            >
              {{ item.label }}
            </button>
          </div>

          <div class="repository-layout">
            <div class="mini-panel repository-tree-panel">
              <div class="mini-panel-head">
                <div>
                  <div class="mini-panel-title">模型树</div>
                  <div class="mini-panel-desc">按分组快速定位模型和资源目录。</div>
                </div>
              </div>
              <div class="repository-tree-list">
                <div v-for="group in repositoryTreeNodes" :key="group.id || group.code" class="repository-tree-group">
                  <div class="repository-tree-group-head">
                    <span>{{ group.name }}</span>
                    <strong>{{ group.resource_count || 0 }}</strong>
                  </div>
                  <button
                    v-for="model in group.children || []"
                    :key="model.id || model.model_id || model.code"
                    type="button"
                    class="repository-tree-model"
                    :class="{ active: ledgerFilters.ci_type === model.model_id }"
                    @click="openRepositoryModel(model)"
                  >
                    <span class="repository-tree-model-main">
                      <strong>{{ model.name }}</strong>
                      <small>{{ model.code || '-' }} / 字段 {{ model.field_count || 0 }}</small>
                    </span>
                    <span class="repository-tree-model-meta">
                      <b>{{ model.ci_count || 0 }}</b>
                      <em :class="{ danger: model.risk_count > 0 }">{{ model.risk_count || 0 }}</em>
                    </span>
                  </button>
                </div>
                <el-empty v-if="!repositoryTreeNodes.length" description="暂无模型树" :image-size="72" />
              </div>
            </div>

            <div class="mini-panel mini-panel--wide">
              <div class="mini-panel-head">
                <div>
                  <div class="mini-panel-title">模型分组</div>
                  <div class="mini-panel-desc">按业务域查看资源模型、实例规模和治理风险。</div>
                </div>
                <el-tag size="small" type="info">{{ repositoryGroups.length }} 个分组</el-tag>
              </div>
              <div class="repository-group-list">
                <div v-for="group in filteredRepositoryGroups" :key="group.code || group.name" class="repository-group-card">
                  <div class="repository-group-head">
                    <div class="resource-cell">
                      <strong>{{ group.name }}</strong>
                      <span>{{ group.code || 'custom' }} / {{ (group.models || []).length }} 个模型</span>
                    </div>
                    <div class="repository-group-badges">
                      <el-tag size="small" type="info">{{ group.resource_count || 0 }} 个资源</el-tag>
                      <el-tag size="small" :type="group.quality_score < 60 ? 'danger' : group.quality_score < 90 ? 'warning' : 'success'">质量 {{ group.quality_score ?? 100 }}</el-tag>
                    </div>
                  </div>
                  <div class="repository-model-list">
                    <div v-for="model in group.models || []" :key="model.id || model.code" class="repository-model-row">
                      <div class="resource-cell">
                        <strong>{{ model.name }}</strong>
                        <span>{{ model.code }}</span>
                      </div>
                      <div class="repository-model-metrics">
                        <span class="repository-model-count"><span class="repository-model-count-label">资源</span>{{ model.ci_count || 0 }}</span>
                        <span>活跃 {{ model.active_count || 0 }}</span>
                        <span :class="{ danger: modelRiskCount(model) > 0 }">风险 {{ modelRiskCount(model) }}</span>
                        <span class="repository-quality-chip" :class="repositoryQualityTone(model)">质量 {{ model.quality_score ?? 100 }}</span>
                      </div>
                      <div class="repository-model-actions">
                        <el-button link type="primary" @click="openRepositoryModel(model)">查看资源</el-button>
                        <el-button link :type="modelRiskCount(model) > 0 ? 'warning' : 'info'" @click="openGovernanceByRepositoryModel(model)">
                          {{ modelRiskCount(model) > 0 ? '处理风险' : '治理队列' }}
                        </el-button>
                      </div>
                    </div>
                  </div>
                </div>
                <el-empty v-if="!filteredRepositoryGroups.length" description="暂无资源仓库数据" :image-size="72" />
              </div>
            </div>

            <div class="mini-panel">
              <div class="mini-panel-head">
                <div>
                  <div class="mini-panel-title">资源 Top 模型</div>
                  <div class="mini-panel-desc">优先关注规模大、风险高的资源类型。</div>
                </div>
              </div>
              <div class="repository-top-list">
                <div v-for="item in repositoryTopModels" :key="item.id || item.code" class="repository-top-row">
                  <div class="resource-cell">
                    <strong>{{ item.name }}</strong>
                    <span>{{ item.group_name || item.code }}</span>
                  </div>
                  <div class="repository-top-value">
                    <strong>{{ item.ci_count || 0 }}</strong>
                    <span>风险 {{ modelRiskCount(item) }} / 质量 {{ item.quality_score ?? 100 }}</span>
                    <el-button link :type="modelRiskCount(item) > 0 ? 'warning' : 'info'" @click="openGovernanceByRepositoryModel(item)">
                      {{ modelRiskCount(item) > 0 ? '处理风险' : '治理队列' }}
                    </el-button>
                  </div>
                </div>
                <el-empty v-if="!repositoryTopModels.length" description="暂无模型排行" :image-size="72" />
              </div>
            </div>
          </div>
        </div>
      </template>

      <template v-else-if="activeTab === 'views'">
        <div v-loading="viewsLoading" class="views-shell">
          <div class="view-summary-grid">
            <div v-for="item in viewSummaryCards" :key="item.key" class="search-summary-card" :class="item.tone">
              <span>{{ item.label }}</span>
              <strong>{{ item.value }}</strong>
              <small v-if="item.hint">{{ item.hint }}</small>
            </div>
          </div>

          <div class="view-mode-bar views-mode-switcher">
            <button
              v-for="item in viewModeOptions"
              :key="item.key"
              type="button"
              :class="{ active: viewMode === item.key }"
              @click="switchOpsanyViewMode(item.key)"
            >
              <el-icon><component :is="item.icon" /></el-icon>
              <span>{{ item.label }}</span>
              <em>{{ item.count }}</em>
            </button>
          </div>

          <div class="workbench-toolbar workbench-toolbar--history cmdb-filter-bar">
            <div class="workbench-toolbar-left">
              <el-input v-model="applicationViewKeyword" clearable :placeholder="viewSearchPlaceholder" style="width: 260px" />
              <el-select v-model="viewFilters.business_line" clearable filterable placeholder="业务线" style="width: 150px" @change="fetchViewsSummary">
                <el-option v-for="item in businessLineOptions" :key="item" :label="item" :value="item" />
              </el-select>
              <el-select v-model="viewFilters.environment" clearable placeholder="环境" style="width: 120px" @change="fetchViewsSummary">
                <el-option label="生产" value="prod" />
                <el-option label="测试" value="test" />
                <el-option label="开发" value="dev" />
              </el-select>
              <el-select v-if="viewMode === 'application'" v-model="applicationViewRisk" clearable placeholder="健康状态" style="width: 132px">
                <el-option label="运行良好" value="success" />
                <el-option label="需关注" value="warning" />
                <el-option label="高风险" value="danger" />
              </el-select>
              <el-select v-if="viewMode === 'application'" v-model="applicationViewTeam" clearable filterable placeholder="负责团队" style="width: 140px">
                <el-option v-for="item in applicationViewTeamOptions" :key="item" :label="item" :value="item" />
              </el-select>
              <el-select v-if="viewMode === 'application'" v-model="applicationViewTier" clearable placeholder="服务等级" style="width: 120px">
                <el-option label="核心" value="core" />
                <el-option label="重要" value="important" />
                <el-option label="普通" value="normal" />
                <el-option label="未分级" value="" />
              </el-select>
              <el-select v-if="viewMode !== 'physical'" v-model="applicationViewOwner" clearable filterable placeholder="负责人" style="width: 132px">
                <el-option v-for="item in viewOwnerOptions" :key="item" :label="item" :value="item" />
              </el-select>
            </div>
            <div class="workbench-toolbar-right">
              <el-button @click="resetApplicationViewFilters">重置</el-button>
              <el-button :loading="viewsLoading" @click="fetchViewsSummary">刷新</el-button>
            </div>
          </div>

          <div class="opsany-view-layout">
            <aside class="opsany-view-tree">
              <el-input
                v-model="opsanyViewKeyword"
                clearable
                placeholder="请输入关键字搜索"
                class="opsany-tree-search"
              />
              <div class="opsany-view-tree-list">
                <button
                  v-for="node in filteredOpsanyViewTree"
                  :key="node.key"
                  type="button"
                  class="opsany-view-tree-node"
                  :class="{ active: isOpsanyViewNodeActive(node) }"
                  @click="selectOpsanyViewNode(node)"
                >
                  <span>{{ node.label }}</span>
                  <strong>{{ node.count }}</strong>
                </button>
              </div>
            </aside>

            <div class="mini-panel opsany-view-main">
            <template v-if="viewMode === 'application'">
              <div class="mini-panel-head">
                <div>
                  <div class="mini-panel-title">应用视图</div>
                  <div class="mini-panel-desc">按应用聚合主机、数据服务、依赖关系和治理风险，点击资源指标可回到账台。</div>
                </div>
                <el-tag size="small" type="info">{{ filteredApplicationViewRows.length }} 个应用</el-tag>
              </div>
              <div class="opsany-app-grid">
                <article v-for="row in filteredApplicationViewRows" :key="row.id || row.name" class="opsany-app-card">
                  <div class="opsany-app-card-head">
                    <div class="resource-cell">
                      <button v-if="row.id" type="button" class="resource-name-link" @click="openCiDetail(row)">{{ row.name }}</button>
                      <strong v-else>{{ row.name }}</strong>
                      <span>唯一标识：{{ row.code || row.source_unique_id || row.name || '-' }}</span>
                      <span>{{ row.business_line || '默认分组' }} · {{ row.environment_display || row.environment || '未设置环境' }}</span>
                    </div>
                    <el-tag :type="row.health_status || (row.risk_count ? 'warning' : 'success')" size="small">
                      {{ row.health_text || (row.risk_count ? `风险 ${row.risk_count}` : '运行良好') }}
                    </el-tag>
                  </div>
                  <div class="opsany-app-meta-strip">
                    <span><em>服务编码</em><strong>{{ row.service_code || row.code || '未填写' }}</strong></span>
                    <span><em>负责团队</em><strong>{{ row.owner_team || '未设置' }}</strong></span>
                    <span><em>服务等级</em><el-tag size="small" :type="applicationTierTagType(row.tier)">{{ row.tier_display || '未分级' }}</el-tag></span>
                  </div>
                  <div v-if="row.language || row.repo || row.endpoint || row.description" class="opsany-app-techline">
                    <span v-if="row.language">技术栈：{{ row.language }}</span>
                    <a v-if="row.repo" :href="row.repo" target="_blank" rel="noreferrer" @click.stop>代码仓库</a>
                    <a v-if="row.endpoint" :href="row.endpoint" target="_blank" rel="noreferrer" @click.stop>访问入口</a>
                    <span v-if="row.description" class="opsany-app-description">{{ row.description }}</span>
                  </div>
                  <div class="opsany-app-health">
                    <div class="opsany-app-health-head">
                      <span>资源关系覆盖率</span>
                      <strong>{{ row.coverage_rate ?? 0 }}%</strong>
                    </div>
                    <el-progress :percentage="Number(row.coverage_rate || 0)" :stroke-width="6" :show-text="false" :status="row.health_status === 'danger' ? 'exception' : row.health_status === 'warning' ? 'warning' : 'success'" />
                    <div class="opsany-app-health-meta">
                      <span>{{ row.risk_count ? (row.risk_items || []).join('、') : '关键资源关系完整' }}</span>
                      <span>同步 {{ formatTime(row.last_sync_at || row.updated_at) }}</span>
                    </div>
                  </div>
                  <div class="opsany-relation-grid">
                    <button type="button" class="opsany-relation-cell" @click="openLedgerByViewRow(row)">
                      <span>所关联主机</span>
                      <strong>{{ row.host_count || 0 }}</strong>
                    </button>
                    <button type="button" class="opsany-relation-cell" @click="openLedgerByViewRow(row)">
                      <span>所关联数据服务</span>
                      <strong>{{ row.data_service_count || 0 }}</strong>
                    </button>
                    <button type="button" class="opsany-relation-cell" @click="openCiDetail(row)">
                      <span>应用负责人</span>
                      <strong>{{ row.admin_user || '-' }}</strong>
                    </button>
                    <button type="button" class="opsany-relation-cell" @click="openLedgerByViewRow(row)">
                      <span>关系 / 来源</span>
                      <strong>{{ row.relation_count || 0 }} / {{ row.source_count || 0 }}</strong>
                    </button>
                  </div>
                </article>
                <el-empty v-if="!filteredApplicationViewRows.length" description="暂无应用视图数据" :image-size="72" />
              </div>
            </template>

            <template v-else-if="viewMode === 'host'">
              <div class="mini-panel-head">
                <div>
                  <div class="mini-panel-title">主机视图</div>
                  <div class="mini-panel-desc">按主机查看业务归属、运行环境、来源和关系数量，快速定位未纳管或孤立主机。</div>
                </div>
                <el-tag size="small" type="info">{{ filteredHostViewRows.length }} 台主机</el-tag>
              </div>
              <div class="opsany-host-grid">
                <article v-for="row in filteredHostViewRows" :key="row.id || row.name" class="opsany-host-card">
                  <div class="opsany-host-card-head">
                    <div class="resource-cell">
                      <button type="button" class="resource-name-link" @click="openCiDetail(row)">{{ row.name }}</button>
                      <span>{{ row.ci_type_name || '主机' }} · {{ row.ip || '暂无 IP' }}</span>
                    </div>
                    <el-tag size="small" :type="ledgerStatusTagType(row)">{{ ledgerStatusText(row) }}</el-tag>
                  </div>
                  <div class="opsany-host-meta-grid">
                    <div><span>业务线</span><strong>{{ row.business_line || '未归属' }}</strong></div>
                    <div><span>环境</span><strong>{{ row.environment_display || row.environment || '未设置' }}</strong></div>
                    <div><span>负责人</span><strong>{{ row.admin_user || '未设置' }}</strong></div>
                    <div><span>来源</span><strong>{{ row.source_type || '手工录入' }}</strong></div>
                  </div>
                  <div class="opsany-host-card-footer">
                    <span>关系 {{ row.relation_count || 0 }} 条 · 更新 {{ formatTime(row.updated_at) }}</span>
                    <el-button link type="primary" @click="openLedgerByViewRow(row)">查看台账</el-button>
                  </div>
                </article>
                <el-empty v-if="!filteredHostViewRows.length" description="暂无主机视图数据" :image-size="72" />
              </div>
            </template>

            <template v-else>
              <div class="mini-panel-head">
                <div>
                  <div class="mini-panel-title">机房视图</div>
                  <div class="mini-panel-desc">按机房、机柜和区域查看物理主机分布与机柜占用情况。</div>
                </div>
                <el-tag size="small" type="info">{{ filteredPhysicalViewRows.length }} 个机柜</el-tag>
              </div>
              <div class="opsany-physical-stats">
                <div class="opsany-physical-stat"><span class="opsany-stat-icon"><el-icon><OfficeBuilding /></el-icon></span><div><span>机房</span><strong>{{ physicalRoomCount }}</strong></div></div>
                <div class="opsany-physical-stat"><span class="opsany-stat-icon"><el-icon><Box /></el-icon></span><div><span>物理主机</span><strong>{{ physicalHostCount }}</strong></div></div>
                <div class="opsany-physical-stat"><span class="opsany-stat-icon"><el-icon><Platform /></el-icon></span><div><span>已占 U 位</span><strong>{{ physicalOccupiedU }}</strong></div></div>
                <div class="opsany-physical-stat"><span class="opsany-stat-icon"><el-icon><Warning /></el-icon></span><div><span>未分配机柜</span><strong>{{ physicalUnassignedRackCount }}</strong></div></div>
              </div>
              <div class="opsany-rack-stage">
                <article v-for="row in filteredPhysicalViewRows" :key="`${row.room}-${row.rack}-${row.zone}`" class="opsany-rack-card">
                  <div class="opsany-rack-visual">
                    <div class="opsany-rack-title">{{ row.room }} · {{ row.rack }}</div>
                    <div class="opsany-rack-shell">
                      <div v-for="slot in rackSlots(row)" :key="slot.u" class="opsany-rack-slot" :class="{ occupied: slot.host }">
                        <span>{{ slot.u }}</span>
                        <strong v-if="slot.host">{{ slot.host.name }}</strong>
                      </div>
                    </div>
                  </div>
                  <div class="opsany-rack-meta">
                    <strong>{{ row.room }} / {{ row.rack }}</strong>
                    <span>{{ row.zone || '未设置区域' }}</span>
                    <span>主机 {{ row.host_count || 0 }} 台 · 活跃 {{ row.active_count || 0 }} 台</span>
                    <span>已登记 U 位 {{ row.occupied_u || 0 }} 个</span>
                    <div class="opsany-rack-host-list">
                      <button v-for="host in row.hosts || []" :key="host.id" type="button" @click="openCiDetail(host)">
                        <span>{{ host.name }}</span><small>{{ host.u_position || 'U 位未登记' }}</small>
                      </button>
                    </div>
                  </div>
                </article>
                <el-empty v-if="!filteredPhysicalViewRows.length" description="暂无机房视图数据" :image-size="72" />
              </div>
            </template>

          </div>
          </div>
        </div>
      </template>

      <template v-else-if="activeTab === 'tags'">
        <div v-loading="tagLoading" class="tag-shell">
          <div class="tag-summary-grid">
            <div v-for="item in tagSummaryCards" :key="item.key" class="tag-summary-card" :class="item.tone">
              <span>{{ item.label }}</span>
              <strong>{{ item.value }}</strong>
            </div>
          </div>

          <div class="tag-category-row">
            <span v-for="item in dashboard.ci_by_tag || []" :key="item.id" class="tag-chip tag-chip--hot" :style="{ borderColor: item.color || '#dbe4f0', color: item.color || '#245bdb' }">
              {{ item.name }} <strong>{{ item.count }}</strong>
            </span>
            <span v-if="!(dashboard.ci_by_tag || []).length" class="sub-text">暂无已关联标签</span>
          </div>

          <el-table :data="ciTags" stripe class="cmdb-table">
            <el-table-column label="标签" min-width="190">
              <template #default="{ row }">
                <div class="tag-name-cell">
                  <span class="tag-color-dot" :style="{ background: row.color || '#245bdb' }"></span>
                  <div class="resource-cell">
                    <strong>{{ row.name }}</strong>
                    <span>{{ row.description || '暂无描述' }}</span>
                  </div>
                </div>
              </template>
            </el-table-column>
            <el-table-column label="分类" width="130">
              <template #default="{ row }">{{ row.category || '未分类' }}</template>
            </el-table-column>
            <el-table-column label="关联资源" width="100">
              <template #default="{ row }">{{ row.ci_count || 0 }}</template>
            </el-table-column>
            <el-table-column label="状态" width="96">
              <template #default="{ row }"><el-tag size="small" :type="row.is_active ? 'success' : 'info'">{{ row.is_active ? '启用' : '停用' }}</el-tag></template>
            </el-table-column>
            <el-table-column label="更新时间" width="170">
              <template #default="{ row }">{{ formatTime(row.updated_at) }}</template>
            </el-table-column>
            <el-table-column v-if="canManageCi" label="操作" width="130" fixed="right" align="left">
              <template #default="{ row }">
                <el-button link type="primary" @click="openTagDialog(row)">编辑</el-button>
                <el-button link type="danger" @click="deleteTagRow(row)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </template>

      <template v-else-if="activeTab === 'ledger'">
        <div class="ledger-host-layout">
          <aside class="opsany-view-tree ledger-resource-tree-panel">
            <div class="neo-tabs theme-blue ledger-perspective-tabs">
              <button
                v-for="tab in ledgerViewModeOptions"
                :key="tab.key"
                type="button"
                class="neo-tab-btn"
                :class="{ active: ledgerViewMode === tab.key }"
                @click="switchLedgerViewMode(tab.key)"
              >
                <el-icon><component :is="tab.icon" /></el-icon>
                <span>{{ tab.label }}</span>
              </button>
            </div>
            <div class="ledger-tree-panel-head">
              <div>
                <strong>{{ ledgerTreeTitle }}</strong>
                <span v-if="ledgerTreeDesc">{{ ledgerTreeDesc }}</span>
              </div>
              <div v-if="canManageCi" class="ledger-tree-actions">
                <el-tooltip :content="ledgerTreeRootCreateTooltip" placement="top">
                  <button type="button" @click="openLedgerResourceNodeCreateDialog(ledgerTreeRootCreateType)">
                    <el-icon><Plus /></el-icon>
                  </button>
                </el-tooltip>
              </div>
            </div>
            <el-input
              v-model="ledgerTreeKeyword"
              clearable
              :placeholder="ledgerTreeSearchPlaceholder"
              class="opsany-tree-search"
            />
            <div class="opsany-view-tree-list">
              <button
                type="button"
                class="opsany-view-tree-node"
                :class="{ active: !ledgerTreeContext }"
                @click="selectLedgerScope()"
              >
                <span>全部资源</span>
                <strong>{{ ledgerTreeQuickTotal ?? '—' }}</strong>
              </button>
              <button
                v-for="entry in activeLedgerTreeNodes"
                :key="entry.key"
                type="button"
                class="opsany-view-tree-node ledger-resource-tree-node"
                :class="[`is-level-${entry.level}`, { active: isLedgerTreeNodeActive(entry) }]"
                :style="{ '--ledger-node-depth': entry.depth || 0 }"
                @click="selectLedgerScope(entry)"
              >
                <span class="ledger-tree-node-label">
                  <span
                    v-if="entry.has_children"
                    class="ledger-tree-toggle"
                    role="button"
                    tabindex="0"
                    @click.stop="toggleLedgerTreeNode(entry)"
                    @keydown.enter.stop.prevent="toggleLedgerTreeNode(entry)"
                    @keydown.space.stop.prevent="toggleLedgerTreeNode(entry)"
                  >
                    <el-icon><component :is="entry.is_expanded ? ArrowDown : ArrowRight" /></el-icon>
                  </span>
                  <span v-else class="ledger-tree-toggle ledger-tree-toggle--leaf" />
                  <el-icon class="ledger-tree-node-icon"><component :is="ledgerTreeNodeIcon(entry)" /></el-icon>
                  <span>{{ entry.label }}</span>
                </span>
                <span class="ledger-tree-node-right">
                  <strong class="ledger-tree-node-count">{{ entry.count }}</strong>
                  <span v-if="hasLedgerResourceNodeActions(entry)" class="ledger-tree-node-actions">
                    <el-tooltip v-if="canAddLedgerResourceNodeChild(entry)" :content="ledgerNodeCreateChildTooltip(entry)" placement="top">
                      <span role="button" tabindex="0" @click.stop="openLedgerResourceNodeCreateDialog(ledgerNodeCreateChildType(entry), entry)" @keydown.enter.stop.prevent="openLedgerResourceNodeCreateDialog(ledgerNodeCreateChildType(entry), entry)" @keydown.space.stop.prevent="openLedgerResourceNodeCreateDialog(ledgerNodeCreateChildType(entry), entry)">
                        <el-icon><Plus /></el-icon>
                      </span>
                    </el-tooltip>
                    <el-tooltip v-if="canEditLedgerResourceNode(entry)" :content="ledgerResourceNodeEditTooltip(entry)" placement="top">
                      <span role="button" tabindex="0" @click.stop="openLedgerResourceNodeEditDialog(entry)" @keydown.enter.stop.prevent="openLedgerResourceNodeEditDialog(entry)" @keydown.space.stop.prevent="openLedgerResourceNodeEditDialog(entry)">
                        <el-icon><Edit /></el-icon>
                      </span>
                    </el-tooltip>
                    <el-tooltip v-if="canDeleteLedgerResourceNode(entry)" content="删除节点" placement="top">
                      <span role="button" tabindex="0" @click.stop="deleteLedgerResourceNode(entry)" @keydown.enter.stop.prevent="deleteLedgerResourceNode(entry)" @keydown.space.stop.prevent="deleteLedgerResourceNode(entry)">
                        <el-icon><Delete /></el-icon>
                      </span>
                    </el-tooltip>
                  </span>
                </span>
              </button>
            </div>
            <el-empty v-if="!activeLedgerTreeNodes.length" :description="ledgerTreeEmptyText" :image-size="56" />
          </aside>

          <div class="mini-panel opsany-view-main ledger-table-panel">
            <div class="mini-panel-head ledger-table-head">
              <div>
                <div class="mini-panel-title">{{ ledgerTableTitle }}</div>
                <div class="mini-panel-desc">{{ ledgerTableDesc }}</div>
              </div>
              <div class="inline-actions ledger-head-actions">
                <el-tag size="small" type="info">共 {{ ledgerPagination.total || ledgerItems.length }} 个资产</el-tag>
                <el-button
                  v-if="canManageSync"
                  size="small"
                  :loading="resourceWaterlinePageMetricLoading"
                  :disabled="!resourceWaterlineTargetRows(ledgerItems).length"
                  @click="refreshLedgerCurrentPageResourceWaterline"
                >
                  <el-icon><RefreshRight /></el-icon>
                  重新同步当前页资产水位
                </el-button>
              </div>
            </div>

            <div v-if="isThirdPartyLedgerMode" class="third-party-expiry-strip">
              <div class="third-party-expiry-copy">
                <strong>服务到期治理</strong>
                <span>按服务到期日与提醒提前天数自动分级。</span>
              </div>
              <div class="third-party-expiry-actions">
                <button
                  v-for="item in thirdPartyExpirySummaryRows"
                  :key="item.key"
                  type="button"
                  class="third-party-expiry-action"
                  :class="[item.tone, { active: ledgerFilters.expiry_risk === item.key }]"
                  @click="applyThirdPartyExpiryFilter(item.key)"
                >
                  <span>{{ item.label }}</span>
                  <strong>{{ item.value }}</strong>
                </button>
              </div>
            </div>

            <div class="workbench-toolbar workbench-toolbar--history cmdb-filter-bar">
            <div class="workbench-toolbar-left">
            <el-select v-model="ledgerFilters.ci_type" clearable filterable placeholder="资产类型" style="width: 150px" @change="fetchLedger">
              <el-option v-for="item in visibleAssetClassificationTypes" :key="item.id" :label="item.name" :value="item.id" />
            </el-select>
            <el-input v-model="ledgerFilters.asset_search" clearable placeholder="搜索资产名" style="width: 150px" @keyup.enter="fetchLedger" @clear="fetchLedger" />
            <el-input v-model="ledgerFilters.attribute_search" clearable placeholder="搜索属性 IP / ID等" style="width: 180px" @keyup.enter="fetchLedger" @clear="fetchLedger" />
            <el-select v-model="ledgerFilters.status" clearable placeholder="状态" style="width: 112px" @change="fetchLedger">
              <el-option label="使用中" value="active" />
              <el-option label="停机" value="stopped" />
              <el-option label="已下线" value="offline" />
            </el-select>
            <el-select v-model="ledgerFilters.tags" clearable filterable placeholder="标签" style="width: 132px" @change="fetchLedger">
              <el-option v-for="item in activeTagOptions" :key="item.id" :label="item.name" :value="item.id" />
            </el-select>
            <el-input v-model="ledgerFilters.source_type" clearable placeholder="搜索来源" style="width: 116px" @keyup.enter="fetchLedger" @clear="fetchLedger" />
            <el-input v-model="ledgerFilters.ownership" clearable placeholder="搜索部门 / 负责人" style="width: 180px" @keyup.enter="fetchLedger" @clear="fetchLedger" />
          </div>
          <div class="workbench-toolbar-right">
            <el-button @click="clearLedgerFilters">重置</el-button>
          </div>
            </div>
            <div v-if="ledgerTreeContext" class="ledger-tree-context-strip">
              <div class="ledger-tree-context-copy">
                <strong>{{ ledgerTreeContextText }}</strong>
                <span>{{ ledgerTreeContextHint }}</span>
              </div>
              <div class="inline-actions">
                <el-button size="small" @click="selectLedgerScope()">{{ ledgerTreeContextExitText }}</el-button>
              </div>
            </div>
            <div v-if="ledgerSummaryContext" class="ledger-tree-context-strip ledger-tree-context-strip--summary">
              <div class="ledger-tree-context-copy">
                <strong>{{ ledgerSummaryContextText }}</strong>
                <span>当前台账来自概览指标，可继续筛选、导出或批量维护。</span>
              </div>
              <div class="inline-actions">
                <el-button size="small" @click="clearLedgerSummaryContext">退出上下文</el-button>
              </div>
            </div>
            <div v-if="ledgerAuthorizationContext" class="ledger-tree-context-strip ledger-tree-context-strip--authorization">
              <div class="ledger-tree-context-copy">
                <strong>{{ ledgerAuthorizationContextText }}</strong>
                <span>当前台账按授权策略范围过滤，用于验证该策略覆盖的资源。</span>
              </div>
              <div class="inline-actions">
                <el-button size="small" @click="switchTab('authorization')">返回授权</el-button>
                <el-button size="small" @click="clearLedgerAuthorizationContext">退出上下文</el-button>
              </div>
            </div>
            <div v-if="ledgerViewContext" class="ledger-tree-context-strip ledger-tree-context-strip--view">
              <div class="ledger-tree-context-copy">
                <strong>{{ ledgerViewContextText }}</strong>
                <span>当前台账来自视图钻取，可继续筛选、批量维护或进入资源详情。</span>
              </div>
              <div class="inline-actions">
                <el-button size="small" @click="clearLedgerViewContext">退出上下文</el-button>
              </div>
            </div>
            <el-table v-loading="ledgerLoading" :data="ledgerItems" stripe class="cmdb-table" @selection-change="onLedgerSelectionChange">
          <el-table-column v-if="canManageCi" type="selection" width="42" />
          <el-table-column label="资产" min-width="220">
            <template #default="{ row }">
              <div class="resource-cell">
                <button type="button" class="resource-name-link resource-name-link--primary" @click="openCiDetail(row)">{{ row.name }}</button>
                <div class="resource-cell-meta">
                  <span>{{ row.ci_type_name }}</span>
                  <code v-if="row.id" class="asset-id-badge">资产 ID #{{ row.id }}</code>
                </div>
              </div>
            </template>
          </el-table-column>
          <el-table-column min-width="200">
            <template #header>
              <span class="ledger-attribute-column-title">
                属性
                <el-tooltip content="在资产分类的字段配置中勾选“在资产台账属性栏显示”的字段会按排序展示，最多显示 3 项。" placement="top">
                  <el-icon><InfoFilled /></el-icon>
                </el-tooltip>
              </span>
            </template>
            <template #default="{ row }">
              <div class="search-attribute-list">
                <el-tooltip v-for="item in ledgerAttributeEntries(row).slice(0, 3)" :key="item.key" :content="`${item.label || item.key}: ${formatValue(item.value)}`" placement="top" :show-after="300">
                  <span>{{ item.label || item.key }}: {{ formatValue(item.value) }}</span>
                </el-tooltip>
                <span v-if="!ledgerAttributeEntries(row).length" class="sub-text">-</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column v-if="hasLedgerWaterlineRows" label="资产水位" min-width="190">
            <template #default="{ row }">
              <el-tooltip v-if="isResourceWaterlineTarget(row)" placement="top" :show-after="300">
                <template #content>
                  <div class="resource-waterline-tooltip">
                    <div><span>采集来源</span><strong>{{ resourceWaterlineTooltipSource(row) }}</strong></div>
                    <div><span>采集时间</span><strong>{{ resourceWaterlineTooltipTime(row) }}</strong></div>
                  </div>
                </template>
                <div class="resource-waterline-cell">
                  <div v-for="item in resourceWaterlineRows(row)" :key="item.key" class="resource-waterline-row" :class="`is-${item.tone}`">
                    <span>{{ item.label }}</span>
                    <i><b :style="{ width: item.hasData ? `${item.percent}%` : '0%' }" /></i>
                    <strong>{{ item.hasData ? `${item.percent}%` : '-' }}</strong>
                  </div>
                </div>
              </el-tooltip>
              <span v-else class="sub-text">-</span>
            </template>
          </el-table-column>
          <el-table-column label="业务环境" width="136">
            <template #default="{ row }">
              <div class="stack-cell">
                <span>业务线：{{ ledgerBusinessLineDisplay(row) }}</span>
                <span>环境：{{ ledgerBusinessEnvironmentDisplay(row) }}</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column v-if="isThirdPartyLedgerMode" label="服务 / 供应商" min-width="180">
            <template #default="{ row }">
              <div class="stack-cell">
                <span>{{ row.attributes?.service_type || '-' }}</span>
                <div class="sub-text">{{ row.attributes?.provider || '-' }}</div>
              </div>
            </template>
          </el-table-column>
          <el-table-column v-if="isThirdPartyLedgerMode" label="账号主体" min-width="180">
            <template #default="{ row }">
              <div class="stack-cell">
                <span>{{ row.attributes?.account_subject || '-' }}</span>
                <div class="sub-text">服务地址：{{ row.attributes?.service_endpoint || '-' }}</div>
              </div>
            </template>
          </el-table-column>
          <el-table-column v-if="isThirdPartyLedgerMode" label="到期治理" min-width="190">
            <template #default="{ row }">
              <div class="stack-cell">
                <el-tag size="small" :type="externalExpiryTagType(row)">{{ externalExpiryText(row) }}</el-tag>
                <div class="sub-text">服务到期日 {{ row.attributes?.service_expiry_date || '-' }}</div>
              </div>
            </template>
          </el-table-column>
          <el-table-column v-if="isDataServiceLedgerMode" label="规格 / 容量" min-width="180">
            <template #default="{ row }">
              <div class="stack-cell">
                <span>{{ ledgerDataServiceSpec(row) }}</span>
                <div class="sub-text">
                  {{ ledgerDataServiceCapacity(row) }}
                  <el-tag v-if="ledgerDataServiceUsage(row)" size="small" :type="ledgerUsageTagType(row)" style="margin-left: 6px">
                    {{ ledgerDataServiceUsage(row) }}
                  </el-tag>
                </div>
              </div>
            </template>
          </el-table-column>
          <el-table-column v-if="isDataServiceLedgerMode" label="网络 / 版本" min-width="180">
            <template #default="{ row }">
              <div class="stack-cell">
                <span>{{ ledgerDataServiceNetwork(row) }}</span>
                <div class="sub-text">{{ ledgerDataServiceVersion(row) }}</div>
              </div>
            </template>
          </el-table-column>
          <el-table-column v-if="isEdgeServiceLedgerMode" label="入口 / 容量" min-width="190">
            <template #default="{ row }">
              <div class="stack-cell">
                <span>{{ ledgerEdgeEndpoint(row) }}</span>
                <div class="sub-text">{{ ledgerEdgeCapacity(row) }}</div>
              </div>
            </template>
          </el-table-column>
          <el-table-column v-if="isEdgeServiceLedgerMode" label="网络 / 策略" min-width="190">
            <template #default="{ row }">
              <div class="stack-cell">
                <span>{{ ledgerEdgeNetwork(row) }}</span>
                <div class="sub-text">{{ ledgerEdgePolicy(row) }}</div>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="资产状态" width="88">
            <template #default="{ row }"><el-tag size="small" :type="ledgerStatusTagType(row)">{{ ledgerStatusText(row) }}</el-tag></template>
          </el-table-column>
          <el-table-column label="来源 / 同步状态" min-width="150">
            <template #default="{ row }">
              <div class="stack-cell source-sync-cell">
                <span>来源：{{ ledgerSourceLabel(row) }}</span>
                <div class="source-sync-status sub-text">
                  <span>同步状态：</span>
                  <el-tag v-if="ledgerSourceSyncStatus(row)" size="small" :type="syncStatusTagType(ledgerSourceSyncStatus(row))">
                    {{ sourceMappingStatusText(ledgerSourceSyncStatus(row)) }}
                  </el-tag>
                  <span v-else>-</span>
                </div>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="部门 / 负责人" width="126">
            <template #default="{ row }">
              <div class="stack-cell ownership-cell">
                <span>部门：{{ ledgerOwnershipDepartmentDisplay(row) }}</span>
                <span>负责人：{{ ledgerOwnershipAdminDisplay(row) }}</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="标签" min-width="118">
            <template #default="{ row }">
              <div class="tag-chip-list">
                <span v-for="tag in row.tag_items || []" :key="tag.id" class="tag-chip" :style="{ borderColor: tag.color || '#dbe4f0', color: tag.color || '#245bdb' }">
                  {{ tag.name }}
                </span>
                <span v-if="!(row.tag_items || []).length" class="sub-text">-</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column v-if="isIdcLedgerMode" label="机房 / 机柜" min-width="170">
            <template #default="{ row }">
              <div class="stack-cell">
                <span>{{ row.attributes?.idc || row.attributes?.machine_room || row.attributes?.room || '-' }}</span>
                <div class="sub-text">{{ row.attributes?.rack || row.attributes?.cabinet || '-' }}{{ row.attributes?.u_position ? ` / ${row.attributes.u_position}` : '' }}</div>
              </div>
            </template>
          </el-table-column>
          <el-table-column v-if="isIdcLedgerMode" label="生命周期 / 服务到期" min-width="190">
            <template #default="{ row }">
              <div class="stack-cell">
                <div>
                  <el-tag size="small" :type="idcLifecycleTagType(row.attributes?.lifecycle_status)">{{ idcLifecycleText(row.attributes?.lifecycle_status) }}</el-tag>
                  <el-tag size="small" :type="serviceExpiryTagType(row)" style="margin-left: 6px">{{ serviceExpiryStatusText(row) }}</el-tag>
                </div>
                <div class="sub-text">服务到期 {{ serviceExpiryDate(row) || '-' }}</div>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="更新时间" width="170">
            <template #default="{ row }">{{ formatTime(row.updated_at) }}</template>
          </el-table-column>
          <el-table-column label="操作" width="150" fixed="right" align="left">
            <template #default="{ row }">
              <el-button link type="primary" @click="openCiDetail(row)">详情</el-button>
              <el-button v-if="canManageCi" link type="info" @click="openCiDialog(row)">编辑</el-button>
            </template>
          </el-table-column>
            </el-table>
            <div class="ledger-pagination">
              <el-pagination
                v-model:current-page="ledgerPagination.page"
                v-model:page-size="ledgerPagination.pageSize"
                background
                layout="total, sizes, prev, pager, next, jumper"
                :page-sizes="[10, 20, 50, 100]"
                :total="ledgerPagination.total"
                @size-change="handleLedgerPageSizeChange"
                @current-change="handleLedgerPageChange"
              />
            </div>
          </div>
        </div>
      </template>

      <template v-else-if="activeTab === 'requests'">
        <div class="workbench-toolbar workbench-toolbar--history cmdb-filter-bar">
          <div class="workbench-toolbar-left">
            <el-select v-model="requestFilters.status" clearable placeholder="状态" style="width: 120px" @change="fetchRequests">
              <el-option label="待审批" value="pending" />
              <el-option label="已批准" value="approved" />
              <el-option label="交付中" value="provisioning" />
              <el-option label="交付失败" value="failed" />
              <el-option label="已拒绝" value="rejected" />
              <el-option label="已交付" value="completed" />
            </el-select>
            <el-select v-model="requestFilters.business_line" clearable filterable placeholder="业务线" style="width: 150px" @change="fetchRequests">
              <el-option v-for="item in businessLineOptions" :key="item" :label="item" :value="item" />
            </el-select>
            <el-input v-model="requestFilters.search" clearable placeholder="搜索标题 / 申请人 / 规格" style="width: 260px" @keyup.enter="fetchRequests" />
          </div>
          <div class="workbench-toolbar-right">
            <el-button @click="clearRequestFilters">重置</el-button>
          </div>
        </div>

        <div class="request-summary-grid audit-grid">
          <button
            v-for="item in requestSummaryCards"
            :key="item.key"
            type="button"
            class="request-summary-card audit-card audit-card--inline audit-card--action"
            :class="[item.tone, { active: (requestFilters.status || 'all') === item.key }]"
            @click="applyRequestSummaryFilter(item.key)"
          >
            <span>{{ item.label }}</span>
            <strong>{{ item.value }}</strong>
          </button>
        </div>

        <el-table v-loading="requestLoading" :data="requestRows" stripe class="cmdb-table">
          <el-table-column label="申请" min-width="220">
            <template #default="{ row }">
              <div class="resource-cell">
                <strong>{{ row.title }}</strong>
                <span>{{ row.resource_type_label || requestResourceTypeLabel(row.resource_type) }} / {{ row.specification || '-' }} / {{ row.quantity || 1 }} 项</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="归属" min-width="160">
            <template #default="{ row }">
              <div class="stack-cell">
                <span>{{ row.business_line || '-' }}</span>
                <div class="sub-text">{{ row.environment_display || environmentText(row.environment) }}</div>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="交付方式" min-width="150">
            <template #default="{ row }">
              <div class="stack-cell">
                <span>{{ row.delivery_mode === 'cloud' ? row.provider_label : '人工交付' }}</span>
                <div class="sub-text">{{ row.specs?.region || row.specs?.cloud_credential_id ? `${row.specs?.region || '-'} / ${row.provisioning?.credential_name || `账号#${row.specs?.cloud_credential_id || '-'}`}` : '审批后补录交付信息' }}</div>
              </div>
            </template>
          </el-table-column>
          <el-table-column prop="applicant" label="申请人" width="120" />
          <el-table-column label="优先级" width="90">
            <template #default="{ row }"><el-tag size="small" :type="requestPriorityTagType(row.priority)">{{ requestPriorityText(row.priority) }}</el-tag></template>
          </el-table-column>
          <el-table-column label="状态" width="96">
            <template #default="{ row }"><el-tag size="small" :type="requestStatusTagType(row.status)">{{ row.status_display || requestStatusText(row.status) }}</el-tag></template>
          </el-table-column>
          <el-table-column label="交付资源" min-width="170">
            <template #default="{ row }">
              <div v-if="requestDeliveredItems(row).length" class="inline-cell">
                <el-button link type="primary" @click="openCiDetail(requestDeliveredItems(row)[0])">
                  {{ requestDeliveredItems(row)[0].name }}
                </el-button>
                <el-popover v-if="requestDeliveredItems(row).length > 1" placement="bottom" width="260" trigger="click">
                  <template #reference>
                    <el-tag size="small" type="info" class="clickable-tag">+{{ requestDeliveredItems(row).length - 1 }}</el-tag>
                  </template>
                  <div class="delivered-resource-list">
                    <button
                      v-for="item in requestDeliveredItems(row)"
                      :key="item.id"
                      type="button"
                      class="delivered-resource-row"
                      @click="openCiDetail(item)"
                    >
                      <strong>{{ item.name }}</strong>
                      <span>{{ item.ci_type_name || '-' }} / {{ item.status_display || item.status || '-' }}</span>
                    </button>
                  </div>
                </el-popover>
              </div>
              <span v-else class="sub-text">{{ row.status === 'completed' ? '未关联台账' : '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="reason" label="申请理由" min-width="180" show-overflow-tooltip />
          <el-table-column label="创建时间" width="170">
            <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
          </el-table-column>
          <el-table-column label="操作" width="250" fixed="right">
            <template #default="{ row }">
              <el-button link type="info" @click="openRequestDetail(row)">详情</el-button>
              <el-button v-if="canApproveRequest && row.status === 'pending'" link type="primary" @click="openRequestAction(row, 'approve')">批准</el-button>
              <el-button v-if="canApproveRequest && row.status === 'pending'" link type="danger" @click="openRequestAction(row, 'reject')">驳回</el-button>
              <el-button v-if="canExecuteRequest && row.status === 'approved' && row.delivery_mode === 'cloud'" link type="success" @click="openRequestAction(row, 'provision')">自动交付</el-button>
              <el-button v-if="canExecuteRequest && row.status === 'failed' && row.delivery_mode === 'cloud'" link type="danger" @click="openRequestAction(row, 'provision')">重试交付</el-button>
              <el-button v-if="canApproveRequest && row.status === 'approved' && row.delivery_mode !== 'cloud'" link type="success" @click="openRequestAction(row, 'complete')">人工交付</el-button>
            </template>
          </el-table-column>
        </el-table>
      </template>

      <template v-else-if="activeTab === 'governance'">
        <div class="ledger-host-layout governance-layout">
          <aside class="opsany-view-tree ledger-resource-tree-panel governance-tree-panel">
            <div class="neo-tabs theme-blue ledger-perspective-tabs governance-perspective-tabs">
              <button
                v-for="tab in ledgerViewModeOptions"
                :key="tab.key"
                type="button"
                class="neo-tab-btn"
                :class="{ active: ledgerViewMode === tab.key }"
                @click="switchGovernanceTreeMode(tab.key)"
              >
                <el-icon><component :is="tab.icon" /></el-icon>
                <span>{{ tab.label }}</span>
              </button>
            </div>
            <div class="ledger-tree-panel-head">
              <div>
                <strong>{{ ledgerTreeTitle }}</strong>
                <span>选择资产范围后查看对应治理项</span>
              </div>
            </div>
            <el-input
              v-model="ledgerTreeKeyword"
              clearable
              :placeholder="ledgerTreeSearchPlaceholder"
              class="opsany-tree-search"
            />
            <div class="opsany-view-tree-list">
              <button
                type="button"
                class="opsany-view-tree-node governance-tree-node"
                :class="{ active: !governanceTreeContext }"
                @click="selectGovernanceTreeScope()"
              >
                <span><el-icon><Collection /></el-icon>全部资源</span>
                <strong>{{ governanceTotalCount }}</strong>
              </button>
              <button
                v-for="entry in governanceLedgerTreeNodes"
                :key="entry.key"
                type="button"
                class="opsany-view-tree-node ledger-resource-tree-node governance-tree-node"
                :class="[`is-level-${entry.level}`, { active: isGovernanceTreeNodeActive(entry) }]"
                :style="{ '--ledger-node-depth': entry.depth || 0 }"
                @click="selectGovernanceTreeScope(entry)"
              >
                <span class="ledger-tree-node-label">
                  <span
                    v-if="entry.has_children"
                    class="ledger-tree-toggle"
                    role="button"
                    tabindex="0"
                    @click.stop="toggleLedgerTreeNode(entry)"
                    @keydown.enter.stop.prevent="toggleLedgerTreeNode(entry)"
                    @keydown.space.stop.prevent="toggleLedgerTreeNode(entry)"
                  >
                    <el-icon><component :is="entry.is_expanded ? ArrowDown : ArrowRight" /></el-icon>
                  </span>
                  <span v-else class="ledger-tree-toggle ledger-tree-toggle--leaf" />
                  <el-icon class="ledger-tree-node-icon"><component :is="ledgerTreeNodeIcon(entry)" /></el-icon>
                  <span>{{ entry.label }}</span>
                </span>
                <strong>{{ entry.governance_count }}</strong>
              </button>
            </div>
            <el-empty v-if="!governanceLedgerTreeNodes.length" :description="ledgerTreeEmptyText" :image-size="56" />
          </aside>

          <div class="mini-panel opsany-view-main governance-main-panel">
            <div v-if="governanceViewMode === 'categories'" class="governance-category-view">
              <div class="governance-category-head">
                <div>
                  <strong>治理分类</strong>
                  <span>{{ governanceTreeContext ? governanceTreeContextText : '全部资产范围' }}</span>
                </div>
                <div class="governance-category-total">
                  <strong>{{ activeGovernanceTotalCount }}</strong>
                  <span>项待治理</span>
                </div>
              </div>
            </div>
            <div v-else class="mini-panel-head governance-panel-head governance-detail-head">
              <div class="governance-detail-title">
                <el-button class="governance-back-button" @click="backToGovernanceCategories">
                  <el-icon><ArrowLeft /></el-icon>
                  返回分类
                </el-button>
                <div>
                  <div class="mini-panel-title">{{ activeGovernanceLabel }}</div>
                  <div class="mini-panel-desc">{{ activeGovernanceDescription }}</div>
                </div>
              </div>
              <div class="inline-actions governance-panel-actions">
                <el-tag size="small" :type="activeGovernanceTagType">{{ activeGovernanceCount }} 项待处理</el-tag>
                <template v-if="activeGovernanceKey === 'archive' && canManageCi">
                  <el-button size="small" type="warning" :disabled="!archiveSelection.length" @click="bulkArchiveCandidateAction('archive')">批量确认下线</el-button>
                  <el-button size="small" :disabled="!archiveSelection.length" @click="bulkArchiveCandidateAction('ignore')">批量忽略</el-button>
                </template>
                <el-button
                  v-if="activeGovernanceKey === 'sync' && canManageSync"
                  size="small"
                  type="primary"
                  :disabled="!syncRelationBulkRecordIds.length"
                  :loading="syncRelationBulkResolving"
                  @click="bulkResolveSyncRelations"
                >
                  批量关联 {{ syncRelationBulkRecordIds.length }}
                </el-button>
                <el-button v-if="activeGovernanceKey === 'capacity'" size="small" @click="openCapacityThresholds()">水位策略</el-button>
              </div>
            </div>
            <div v-if="governanceTreeContext" class="ledger-tree-context-strip">
              <div class="ledger-tree-context-copy">
                <strong>{{ governanceTreeContextText }}</strong>
                <span>{{ ledgerTreeContextHint }}</span>
              </div>
              <div class="inline-actions">
                <el-button size="small" type="primary" @click="openLedgerFromGovernanceTree">查看台账</el-button>
                <el-button size="small" @click="selectGovernanceTreeScope()">退出筛选</el-button>
              </div>
            </div>
            <div v-if="governanceScopeContext" class="ledger-tree-context-strip ledger-tree-context-strip--governance">
              <div class="ledger-tree-context-copy">
                <strong>{{ governanceScopeContextText }}</strong>
                <span>当前队列已按资产模型收窄。</span>
              </div>
              <div class="inline-actions">
                <el-button size="small" type="primary" @click="openRepositoryModel(governanceScopeContext)">查看台账</el-button>
                <el-button size="small" @click="clearGovernanceScopeContext">退出筛选</el-button>
              </div>
            </div>

            <div v-if="governanceViewMode === 'categories'" class="governance-category-grid">
              <button
                v-for="item in governanceFilterCards"
                :key="item.key"
                type="button"
                class="governance-category-card"
                :class="`is-${item.tone || 'info'}`"
                @click="openGovernanceCategory(item.key)"
              >
                <span class="governance-category-card-top">
                  <span class="governance-category-icon"><el-icon><component :is="item.icon" /></el-icon></span>
                  <span class="governance-category-copy">
                    <strong>{{ item.label }}</strong>
                    <small>{{ item.desc }}</small>
                  </span>
                </span>
                <span class="governance-category-metric">
                  <strong>{{ item.value }}</strong>
                  <small>项待治理</small>
                </span>
                <span class="governance-category-card-footer">
                  <span :class="['governance-category-status', `is-${item.tone || 'info'}`]">
                    {{ item.value ? '需要处理' : '当前正常' }}
                  </span>
                  <span>进入治理 <el-icon><ArrowRight /></el-icon></span>
                </span>
              </button>
            </div>

            <div v-else class="governance-workspace">
              <div v-if="activeGovernanceKey === 'archive'" class="governance-panel">
            <el-table :data="filteredArchiveCandidates" stripe table-layout="fixed" class="cmdb-table governance-standard-table" empty-text="当前没有待下线确认资产" @selection-change="onArchiveSelectionChange">
              <el-table-column v-if="canManageCi" type="selection" width="42" />
              <el-table-column label="资产" min-width="205">
                <template #default="{ row }">
                  <div class="governance-asset-cell">
                    <span class="governance-asset-icon"><el-icon><Box /></el-icon></span>
                    <div class="governance-asset-copy">
                      <el-tooltip :content="row.ci_name || `资产 ID #${row.ci || row.ci_id || '-'}`" placement="top" :show-after="300">
                        <button v-if="row.ci || row.ci_id" type="button" class="resource-name-link" @click="openCiDetail({ id: row.ci || row.ci_id })">{{ row.ci_name || `资产 ID #${row.ci || row.ci_id || '-'}` }}</button>
                        <strong v-else>{{ row.ci_name || `资产 ID #${row.ci || row.ci_id || '-'}` }}</strong>
                      </el-tooltip>
                      <div class="governance-asset-meta">
                        <span>{{ row.ci_type_name || row.source_type || '未分类资产' }}</span>
                        <code v-if="row.ci || row.ci_id">资产 ID #{{ row.ci || row.ci_id }}</code>
                      </div>
                    </div>
                  </div>
                </template>
              </el-table-column>
              <el-table-column prop="reason" label="原因" min-width="260" show-overflow-tooltip />
              <el-table-column prop="source_type" label="来源" width="110" />
              <el-table-column label="SLA" width="110">
                <template #default="{ row }">
                  <el-tag size="small" :type="governanceSlaTagType(row)">{{ governanceSlaText(row) }}</el-tag>
                </template>
              </el-table-column>
              <el-table-column label="操作" width="140">
                <template #default="{ row }">
                  <el-button v-if="canManageCi" link type="warning" @click="archiveCandidate(row)">确认下线</el-button>
                  <el-button v-if="canManageCi" link type="info" @click="ignoreArchive(row)">忽略</el-button>
                </template>
              </el-table-column>
            </el-table>
          </div>
              <div v-else-if="canViewSync && activeGovernanceKey === 'sync'" class="governance-panel">
            <el-table
              v-loading="syncFailureLoading"
              :data="filteredSyncFailureRecords"
              stripe
              table-layout="fixed"
              class="cmdb-table sync-governance-table"
              empty-text="当前没有同步失败记录"
            >
              <el-table-column label="资产 / 同步来源" min-width="260">
                <template #default="{ row }">
                  <div class="sync-governance-subject">
                    <el-tooltip :content="row.ci_name || row.after?.name || '未绑定资产'" placement="top" :show-after="300">
                      <button v-if="row.ci" type="button" class="resource-name-link" @click="openCiDetail({ id: row.ci })">{{ row.ci_name || row.after?.name || '未绑定资产' }}</button>
                      <strong v-else>{{ row.ci_name || row.after?.name || '未绑定资产' }}</strong>
                    </el-tooltip>
                    <el-tooltip :content="row.source_unique_id || row.after?.source_unique_id || '-'" placement="top" :show-after="300">
                      <span>来源 ID · {{ row.source_unique_id || row.after?.source_unique_id || '-' }}</span>
                    </el-tooltip>
                    <div class="sync-governance-task-line">
                      <el-tooltip :content="row.job_name || `任务 #${row.job}`" placement="top" :show-after="300">
                        <span>{{ row.job_name || `任务 #${row.job}` }}</span>
                      </el-tooltip>
                      <em>{{ row.job_source_type || '未标记来源' }}</em>
                    </div>
                  </div>
                </template>
              </el-table-column>
              <el-table-column label="异常与处理进度" min-width="300">
                <template #default="{ row }">
                  <div class="sync-governance-issue">
                    <div class="sync-governance-issue-head">
                      <el-tag size="small" effect="light" :type="row.relation_issue ? 'warning' : 'danger'">{{ syncGovernanceIssueText(row) }}</el-tag>
                      <el-tag size="small" effect="light" :type="retryStatusTagType(row.retry_status)">{{ retryStatusText(row.retry_status) }}</el-tag>
                      <el-tag size="small" effect="plain" :type="governanceSlaTagType(row)">{{ governanceSlaText(row) }}</el-tag>
                    </div>
                    <el-tooltip :content="syncGovernanceReasonText(row)" placement="top" :show-after="300">
                      <p>{{ syncGovernanceReasonText(row) }}</p>
                    </el-tooltip>
                    <span class="sync-governance-time">发现于 {{ formatTime(row.created_at) }}</span>
                  </div>
                </template>
              </el-table-column>
              <el-table-column label="操作" width="190" fixed="right" align="left">
                <template #default="{ row }">
                  <div class="sync-governance-actions">
                    <el-button v-if="canManageSync && row.status === 'failed'" link type="warning" @click="retrySyncRecordRow(row)">重试</el-button>
                    <el-button v-if="canManageSync && canResolveSyncRecord(row)" link type="primary" @click="openSyncResolveDialog(row)">绑定</el-button>
                    <el-button v-if="canManageSync" link type="info" @click="ignoreSyncGovernance(row)">忽略</el-button>
                    <el-dropdown v-if="row.relation_issue || row.ci" trigger="click" @command="command => handleSyncGovernanceMore(command, row)">
                      <el-button link type="info">
                        更多<el-icon class="el-icon--right"><ArrowDown /></el-icon>
                      </el-button>
                      <template #dropdown>
                        <el-dropdown-menu>
                          <el-dropdown-item v-if="row.relation_issue" command="record">关系详情</el-dropdown-item>
                          <el-dropdown-item v-if="row.ci" command="asset">资产详情</el-dropdown-item>
                        </el-dropdown-menu>
                      </template>
                    </el-dropdown>
                  </div>
                </template>
              </el-table-column>
            </el-table>
          </div>
              <div v-else-if="activeGovernanceKey === 'service_expiry'" class="governance-panel">
            <el-table :data="filteredServiceExpiryRows" stripe table-layout="fixed" class="cmdb-table governance-standard-table" empty-text="当前没有临近或已到期的服务">
              <el-table-column label="资产" min-width="230">
                <template #default="{ row }">
                  <div class="governance-asset-cell">
                    <span class="governance-asset-icon"><el-icon><Box /></el-icon></span>
                    <div class="governance-asset-copy">
                      <el-tooltip :content="row.ci_name || row.name || `资产 ID #${row.ci_id || row.ci || '-'}`" placement="top" :show-after="300">
                        <button v-if="row.ci_id || row.ci" type="button" class="resource-name-link" @click="openCiDetail({ id: row.ci_id || row.ci })">{{ row.ci_name || row.name || `资产 ID #${row.ci_id || row.ci || '-'}` }}</button>
                        <strong v-else>{{ row.ci_name || row.name || `资产 ID #${row.ci_id || row.ci || '-'}` }}</strong>
                      </el-tooltip>
                      <div class="governance-asset-meta">
                        <span>{{ row.ci_type_name || row.ci_type || '未分类资产' }}</span>
                        <code v-if="row.ci_id || row.ci">资产 ID #{{ row.ci_id || row.ci }}</code>
                      </div>
                    </div>
                  </div>
                </template>
              </el-table-column>
              <el-table-column label="服务到期日" width="130">
                <template #default="{ row }">{{ serviceExpiryDate(row) || '-' }}</template>
              </el-table-column>
              <el-table-column label="状态" width="130">
                <template #default="{ row }">
                  <el-tag size="small" :type="serviceExpiryTagType(row)">{{ serviceExpiryStatusText(row) }}</el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="action" label="治理建议" min-width="260" show-overflow-tooltip />
              <el-table-column label="操作" width="130" fixed="right">
                <template #default="{ row }">
                  <div class="governance-row-actions">
                    <el-button v-if="row.ci_id && canManageCi" link type="warning" @click="updateGovernanceStatus(row, 'service_expiry', 'ignored')">忽略</el-button>
                    <el-button v-if="row.ci_id" link type="primary" @click="openCiDetail({ id: row.ci_id })">详情</el-button>
                  </div>
                </template>
              </el-table-column>
            </el-table>
          </div>
              <div v-else-if="activeGovernanceKey === 'capacity'" class="governance-panel">
            <el-table :data="filteredCapacityRows" stripe table-layout="fixed" class="cmdb-table governance-standard-table" empty-text="当前没有超过水位策略的资产">
              <el-table-column label="资产" min-width="230">
                <template #default="{ row }">
                  <div class="governance-asset-cell">
                    <span class="governance-asset-icon"><el-icon><Box /></el-icon></span>
                    <div class="governance-asset-copy">
                      <el-tooltip :content="row.ci_name || `资产 ID #${row.ci_id || row.ci || '-'}`" placement="top" :show-after="300">
                        <button v-if="row.ci_id || row.ci" type="button" class="resource-name-link" @click="openCiDetail({ id: row.ci_id || row.ci })">{{ row.ci_name || `资产 ID #${row.ci_id || row.ci || '-'}` }}</button>
                        <strong v-else>{{ row.ci_name || `资产 ID #${row.ci_id || row.ci || '-'}` }}</strong>
                      </el-tooltip>
                      <div class="governance-asset-meta">
                        <span>{{ row.ci_type_name || row.ci_type || '未分类资产' }}</span>
                        <code v-if="row.ci_id || row.ci">资产 ID #{{ row.ci_id || row.ci }}</code>
                      </div>
                    </div>
                  </div>
                </template>
              </el-table-column>
              <el-table-column label="指标" width="120">
                <template #default="{ row }">{{ metricLabel(row.metric) }}</template>
              </el-table-column>
              <el-table-column label="使用率" width="110">
                <template #default="{ row }">
                  <el-tag size="small" :type="metricRiskType(row)">{{ row.usage_percent ?? '-' }}%</el-tag>
                </template>
              </el-table-column>
              <el-table-column label="处理状态" width="140">
                <template #default="{ row }">
                  <el-tag size="small" :type="capacityGovernanceTagType(row)">{{ capacityGovernanceText(row) }}</el-tag>
                </template>
              </el-table-column>
              <el-table-column label="阈值策略" min-width="210">
                <template #default="{ row }">
                  <div class="compact-stack">
                    <span>{{ capacityThresholdText(row) }}</span>
                    <small>{{ row.policy_scope || '默认策略' }}</small>
                  </div>
                </template>
              </el-table-column>
              <el-table-column label="采集时间" width="170">
                <template #default="{ row }">{{ formatTime(row.collected_at) }}</template>
              </el-table-column>
              <el-table-column label="操作" width="180" fixed="right" align="left">
                <template #default="{ row }">
                  <div class="governance-row-actions">
                    <el-button v-if="canCreateCapacityRequest(row)" link type="primary" @click="openCapacityRequestDialog(row)">申请扩容</el-button>
                    <el-button v-if="linkedCapacityRequest(row)" link type="warning" @click="openLinkedCapacityRequest(row)">申请详情</el-button>
                    <el-button v-if="canManageCi && (row.ci_id || row.ci)" link type="warning" @click="updateGovernanceStatus(row, 'capacity', 'ignored')">忽略</el-button>
                  </div>
                </template>
              </el-table-column>
            </el-table>
              </div>
            </div>
          </div>
        </div>
      </template>

      <template v-else-if="activeTab === 'authorization'">
        <div v-loading="authorizationLoading" class="authorization-shell">
          <div class="authorization-summary-grid">
            <div v-for="item in authorizationSummaryCards" :key="item.key" class="search-summary-card" :class="item.tone">
              <span>{{ item.label }}</span>
              <strong>{{ item.value }}</strong>
            </div>
          </div>
          <div class="mini-panel mini-panel--wide">
            <div class="mini-panel-head">
              <div>
                <div class="mini-panel-title">资源授权</div>
                <div class="mini-panel-desc">按用户或用户组限定业务线、环境和模型数据范围。</div>
              </div>
              <el-button v-if="canManageAuthorization" type="primary" @click="openAuthorizationDialog()">
                <el-icon><Plus /></el-icon>
                新建授权
              </el-button>
            </div>
            <el-table :data="authorizationRows" stripe class="cmdb-table">
              <el-table-column label="授权策略" min-width="190">
                <template #default="{ row }">
                  <div class="resource-cell">
                    <strong>{{ row.name }}</strong>
                    <span>{{ row.description || '暂无说明' }}</span>
                  </div>
                </template>
              </el-table-column>
              <el-table-column label="主体" min-width="150">
                <template #default="{ row }">
                  <div class="compact-stack">
                    <span>{{ row.principal_type_display || principalTypeText(row.principal_type) }}</span>
                    <small>{{ row.principal }}</small>
                  </div>
                </template>
              </el-table-column>
              <el-table-column label="权限" width="100">
                <template #default="{ row }">
                  <el-tag size="small" :type="row.permission === 'manage' ? 'warning' : 'info'">{{ row.permission_display || authorizationPermissionText(row.permission) }}</el-tag>
                </template>
              </el-table-column>
              <el-table-column label="范围" min-width="220">
                <template #default="{ row }">{{ row.scope_display || authorizationScopeText(row) }}</template>
              </el-table-column>
              <el-table-column label="状态" width="90">
                <template #default="{ row }"><el-tag size="small" :type="row.is_active ? 'success' : 'info'">{{ row.is_active ? '启用' : '停用' }}</el-tag></template>
              </el-table-column>
              <el-table-column label="更新时间" width="170">
                <template #default="{ row }">{{ formatTime(row.updated_at) }}</template>
              </el-table-column>
              <el-table-column v-if="canViewCi || canManageAuthorization" label="操作" width="190" fixed="right" align="left">
                <template #default="{ row }">
                  <el-button v-if="canViewCi" link type="info" @click="openLedgerByAuthorization(row)">验证范围</el-button>
                  <el-button v-if="canManageAuthorization" link type="primary" @click="openAuthorizationDialog(row)">编辑</el-button>
                  <el-button v-if="canManageAuthorization" link type="danger" @click="deleteAuthorizationRow(row)">删除</el-button>
                </template>
              </el-table-column>
            </el-table>
          </div>
        </div>
      </template>

      <template v-else-if="activeTab === 'sync'">
        <div class="sync-cloud-console">
          <section class="sync-cloud-section">
            <div class="section-toolbar sync-cloud-section-head">
              <div class="toolbar-head">
                <span class="toolbar-title">公有云账号</span>
                <span class="toolbar-desc">配置账号、选择云产品，保存后自动同步资源。</span>
              </div>
            </div>
            <div class="sync-provider-strip">
              <span v-for="item in publicCloudProviderOptions" :key="item.value">{{ item.label }}</span>
            </div>
            <div class="sync-account-card-grid">
              <article v-for="item in publicCloudAccountCards" :key="item.key" class="sync-account-tile">
                <div class="sync-account-tile-head">
                  <div>
                    <strong>{{ item.title }}</strong>
                    <span>{{ item.providerLabel }} / {{ item.accountLabel }}</span>
                  </div>
                  <el-tag size="small" :type="item.enabled ? 'success' : 'info'">{{ item.enabled ? '已启用' : '已停用' }}</el-tag>
                </div>
                <div class="sync-account-tile-meta">
                  <span>地域 {{ item.region }}</span>
                  <span>资产{{ item.assetCount }}</span>
                  <span>任务{{ item.jobCount }}</span>
                </div>
                <div class="sync-account-products">
                  <span v-for="product in item.productPreviewLabels" :key="`${item.key}-${product}`">{{ product }}</span>
                  <span v-if="item.productOverflowCount" class="sync-account-products-more">...</span>
                  <span v-if="!item.productLabels.length">未选择产品</span>
                </div>
                <div class="sync-account-tile-foot">
                  <small>最近同步：{{ item.lastSyncText }}</small>
                  <div class="sync-account-actions">
                    <el-button size="small" @click="openSyncAccountTaskDrawer(item)">查看任务</el-button>
                    <el-button v-if="canManageCloudAccounts" size="small" @click="openCloudCredentialEditDialog(item.credential)">编辑</el-button>
                    <el-button v-if="canManageCloudAccounts" size="small" type="danger" plain @click="deleteCloudCredentialRow(item)">删除</el-button>
                    <el-button v-if="canManageSync" size="small" type="primary" :loading="syncAccountManualSyncRunning" @click="runCredentialSelectedSyncJobs(item.credential)">手工同步</el-button>
                  </div>
                </div>
              </article>
              <button v-if="canManageCloudAccounts" type="button" class="sync-account-create-tile" @click="openPublicCloudCredentialDialog">
                <el-icon><Plus /></el-icon>
                <strong>添加公有云账号</strong>
                <span>选择阿里云或华为云，勾选 ECS、RDS、Redis 等需要同步的云产品。</span>
              </button>
              <el-empty v-if="!publicCloudAccountCards.length && !canManageCloudAccounts" description="暂无公有云账号" :image-size="72" />
            </div>
          </section>

          <section class="sync-cloud-section">
            <div class="section-toolbar sync-cloud-section-head">
              <div class="toolbar-head">
                <span class="toolbar-title">私有云账号</span>
                <span class="toolbar-desc">接入私有云账号后自动拉取主机资源，当前支持 ESXi 8.0.2，后续可扩展 PVE 等平台。</span>
              </div>
            </div>
            <div class="sync-account-card-grid sync-account-card-grid--private">
              <article v-for="item in privateCloudAccountCards" :key="item.key" class="sync-account-tile sync-account-tile--private">
                <div class="sync-account-tile-head">
                  <div>
                    <strong>{{ item.title }}</strong>
                    <span>{{ item.providerLabel }} / {{ item.accountLabel }}</span>
                  </div>
                  <el-tag size="small" :type="item.enabled ? 'success' : 'info'">{{ item.enabled ? '已启用' : '已停用' }}</el-tag>
                </div>
                <div class="sync-account-tile-meta">
                  <span>私有云 {{ item.region }}</span>
                  <span>资产{{ item.assetCount }}</span>
                  <span>任务{{ item.jobCount }}</span>
                </div>
                <div class="sync-account-products">
                  <span>虚拟机</span>
                  <span>物理机</span>
                </div>
                <div class="sync-account-tile-foot">
                  <small>最近同步：{{ item.lastSyncText }}</small>
                  <div class="sync-account-actions">
                    <el-button size="small" @click="openSyncAccountTaskDrawer(item)">查看任务</el-button>
                    <el-button v-if="canManageCloudAccounts" size="small" @click="openCloudCredentialEditDialog(item.credential)">编辑</el-button>
                    <el-button v-if="canManageCloudAccounts" size="small" type="danger" plain @click="deleteCloudCredentialRow(item)">删除</el-button>
                    <el-button v-if="canManageSync" size="small" type="primary" :loading="syncAccountManualSyncRunning" @click="runCredentialSelectedSyncJobs(item.credential)">手工同步</el-button>
                  </div>
                </div>
              </article>
              <button v-if="canManageCloudAccounts" type="button" class="sync-account-create-tile sync-account-create-tile--private" @click="openVsphereCredentialDialog">
                <el-icon><Plus /></el-icon>
                <strong>添加私有云账号</strong>
                <span>选择私有云类型并填写接入地址、账号和密码，保存后自动拉取主机资源。</span>
              </button>
              <el-empty v-if="!privateCloudAccountCards.length && !canManageCloudAccounts" description="暂无私有云账号" :image-size="72" />
            </div>
          </section>
        </div>

        <el-drawer
          v-model="syncAccountTaskDrawerVisible"
          :title="syncAccountTaskDrawerItem?.title ? `${syncAccountTaskDrawerItem.title} 的同步任务` : '同步任务'"
          size="760px"
          append-to-body
          destroy-on-close
        >
          <div v-if="syncAccountTaskDrawerItem" class="sync-account-task-drawer">
            <div class="sync-account-task-drawer-summary">
              <span>{{ syncAccountTaskDrawerItem.providerLabel }} / {{ syncAccountTaskDrawerItem.accountLabel }}</span>
              <strong>已启用自动同步 {{ syncAccountTaskDrawerItem.enabledTaskCount }} / 已停止自动同步 {{ syncAccountTaskDrawerItem.disabledTaskCount }}</strong>
              <small>点开可以查看每个同步任务会拉取哪些模型，以及当前是否已启用自动同步。</small>
            </div>
            <div class="sync-account-task-list sync-account-task-list--drawer">
              <div class="sync-account-task-head">
                <strong>同步任务明细</strong>
                <span>{{ syncAccountTaskDrawerItem.taskRows.length }} 个</span>
              </div>
              <div v-for="task in syncAccountTaskDrawerItem.taskRows" :key="`${syncAccountTaskDrawerItem.key}-${task.key}`" class="sync-account-task-row" :class="{ 'is-failed': syncTaskHasFailure(task) }">
                <div class="sync-account-task-main">
                  <strong>{{ task.label }}</strong>
                  <span>{{ task.targetLabel }} · {{ task.scheduleText }} · {{ task.autoSyncText }}</span>
                </div>
                <div class="sync-account-task-actions">
                  <el-tag size="small" :type="task.tagType">{{ task.statusText }}</el-tag>
                  <el-button v-if="canManageSync" link type="primary" :loading="syncAccountManualSyncRunning" @click="runCredentialSyncTask(task)">手工同步</el-button>
                  <el-button v-if="task.job && canViewSync" link type="info" @click="viewSyncRecords(task.job)">同步历史</el-button>
                  <el-button v-if="task.job && canViewSync && syncTaskHasFailure(task)" link type="warning" @click="viewSyncRecords(task.job, 'failed')">失败明细</el-button>
                  <el-button v-if="canManageSync" link type="info" @click="openCredentialSyncTaskDialog(task)">编辑</el-button>
                </div>
              </div>
            </div>
          </div>
        </el-drawer>
      </template>

      <template v-else-if="activeTab === 'sourceMappings'">
        <div class="workbench-toolbar workbench-toolbar--history cmdb-filter-bar">
          <div class="workbench-toolbar-left">
            <el-input v-model="sourceMappingFilters.search" clearable placeholder="搜索资源 / 来源唯一标识 / 账号" style="width: 280px" @keyup.enter="fetchSourceMappings" />
            <el-select v-model="sourceMappingFilters.source_type" clearable filterable placeholder="来源类型" style="width: 140px" @change="fetchSourceMappings">
              <el-option v-for="item in sourceMappingSourceOptions" :key="item" :label="item" :value="item" />
            </el-select>
            <el-select v-model="sourceMappingFilters.sync_status" clearable placeholder="同步状态" style="width: 120px" @change="fetchSourceMappings">
              <el-option label="成功" value="success" />
              <el-option label="失败" value="failed" />
              <el-option label="来源缺失" value="missing" />
              <el-option label="冲突" value="conflict" />
            </el-select>
          </div>
          <div class="workbench-toolbar-right">
            <el-button :loading="sourceMappingLoading" @click="fetchSourceMappings">查询</el-button>
            <el-button @click="clearSourceMappingFilters">重置</el-button>
          </div>
        </div>

        <div class="view-summary-grid">
          <div v-for="item in sourceMappingSummaryCards" :key="item.key" class="search-summary-card" :class="item.tone">
            <span>{{ item.label }}</span>
            <strong>{{ item.value }}</strong>
          </div>
        </div>

        <div class="mini-panel mini-panel--wide">
          <div class="mini-panel-head">
            <div>
              <div class="mini-panel-title">来源映射</div>
              <div class="mini-panel-desc">维护资源与外部采集源的唯一身份，支撑增量同步、全量对账和下线治理。</div>
            </div>
            <el-tag size="small" type="info">{{ sourceMappingRows.length }} 条映射</el-tag>
          </div>
          <el-table v-loading="sourceMappingLoading" :data="sourceMappingRows" stripe class="cmdb-table">
            <el-table-column label="资源" min-width="210">
              <template #default="{ row }">
                <div class="resource-cell">
                  <button v-if="row.ci" type="button" class="resource-name-link" @click="openCiDetail({ id: row.ci })">{{ row.ci_name || '-' }}</button>
                  <strong v-else>{{ row.ci_name || '-' }}</strong>
                  <span>{{ row.ci_type_name || modelName(row.ci_type) || '-' }}</span>
                </div>
              </template>
            </el-table-column>
            <el-table-column prop="source_type" label="来源类型" width="130" />
            <el-table-column label="账号 / 地域" min-width="170">
              <template #default="{ row }">
                <div class="compact-stack">
                  <span>{{ row.source_account || '-' }}</span>
                  <small>{{ row.source_region || '-' }}</small>
                </div>
              </template>
            </el-table-column>
            <el-table-column prop="source_unique_id" label="来源唯一标识" min-width="210" show-overflow-tooltip />
            <el-table-column label="同步状态" width="110">
              <template #default="{ row }">
                <el-tag size="small" :type="syncStatusTagType(row.sync_status)">{{ sourceMappingStatusText(row.sync_status) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="最后发现" width="170">
              <template #default="{ row }">{{ formatTime(row.last_seen_at) }}</template>
            </el-table-column>
            <el-table-column label="更新时间" width="170">
              <template #default="{ row }">{{ formatTime(row.updated_at) }}</template>
            </el-table-column>
            <el-table-column label="操作" width="220" fixed="right" align="left">
              <template #default="{ row }">
                <el-button link type="primary" @click="openSourceMappingDetail(row)">详情</el-button>
                <el-dropdown v-if="canManageSync" trigger="click" @command="status => updateSourceMappingStatus(row, status)">
                  <el-button link type="primary">标记</el-button>
                  <template #dropdown>
                    <el-dropdown-menu>
                      <el-dropdown-item
                        v-for="item in sourceMappingStatusActions"
                        :key="item.value"
                        :command="item.value"
                        :disabled="row.sync_status === item.value"
                      >
                        {{ item.label }}
                      </el-dropdown-item>
                    </el-dropdown-menu>
                  </template>
                </el-dropdown>
                <el-button v-if="canManageSync" link type="primary" @click="openSourceMappingDialog(row)">编辑</el-button>
                <el-button v-if="canManageSync" link type="danger" @click="deleteSourceMappingRow(row)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </template>

      <template v-else-if="activeTab === 'thresholds'">
        <div class="workbench-toolbar workbench-toolbar--history cmdb-filter-bar">
          <div class="workbench-toolbar-left">
            <el-select v-model="thresholdFilters.resource_type" clearable filterable placeholder="资源模型" style="width: 150px" @change="fetchThresholdManagement">
              <el-option v-for="item in ciTypes" :key="item.id" :label="item.name" :value="item.id" />
            </el-select>
            <el-select v-model="thresholdFilters.metric" clearable filterable allow-create placeholder="指标" style="width: 150px" @change="fetchThresholdManagement">
              <el-option v-for="item in metricNameOptions" :key="item" :label="metricLabel(item)" :value="item" />
            </el-select>
            <el-select v-model="thresholdFilters.enabled" clearable placeholder="状态" style="width: 120px" @change="fetchThresholdManagement">
              <el-option label="启用" :value="true" />
              <el-option label="停用" :value="false" />
            </el-select>
          </div>
          <div class="workbench-toolbar-right">
            <el-button :loading="thresholdLoading || metricLoading" @click="fetchThresholdManagement">查询</el-button>
            <el-button @click="clearThresholdFilters">重置</el-button>
          </div>
        </div>

        <div class="threshold-summary-grid">
          <div v-for="item in thresholdSummaryCards" :key="item.key" class="threshold-summary-card" :class="item.tone">
            <span>{{ item.label }}</span>
            <strong>{{ item.value }}</strong>
          </div>
        </div>

        <div class="threshold-grid">
          <div class="mini-panel mini-panel--wide">
            <div class="mini-panel-head">
              <div>
                <div class="mini-panel-title">容量阈值策略</div>
                <div class="mini-panel-desc">按资源模型和指标配置水位边界，概览与治理风险会按这些规则计算。</div>
              </div>
              <el-tag size="small" type="info">{{ thresholdPolicies.length }} 条策略</el-tag>
            </div>
            <el-table v-loading="thresholdLoading" :data="thresholdPolicies" stripe class="cmdb-table">
              <el-table-column label="适用模型" min-width="150">
                <template #default="{ row }">{{ row.resource_type_name || modelName(row.resource_type) || '全局' }}</template>
              </el-table-column>
              <el-table-column label="指标" min-width="130">
                <template #default="{ row }">{{ metricLabel(row.metric) }}</template>
              </el-table-column>
              <el-table-column label="阈值" min-width="260">
                <template #default="{ row }">
                  <div class="threshold-band">
                    <span>正常 {{ row.normal_threshold }}%</span>
                    <span>预警 {{ row.warning_threshold }}%</span>
                    <span>紧张 {{ row.critical_threshold }}%</span>
                    <span>超限 {{ row.exceeded_threshold }}%</span>
                  </div>
                </template>
              </el-table-column>
              <el-table-column label="状态" width="90">
                <template #default="{ row }">
                  <el-tag size="small" :type="row.enabled ? 'success' : 'info'">{{ row.enabled ? '启用' : '停用' }}</el-tag>
                </template>
              </el-table-column>
              <el-table-column v-if="canManageCi" label="操作" width="180" fixed="right" align="left">
                <template #default="{ row }">
                  <el-button link type="primary" @click="openThresholdPolicyDialog(row)">编辑</el-button>
                  <el-button link :type="row.enabled ? 'warning' : 'success'" @click="toggleThresholdPolicy(row)">
                    {{ row.enabled ? '停用' : '启用' }}
                  </el-button>
                  <el-button link type="danger" @click="deleteThresholdPolicyRow(row)">删除</el-button>
                </template>
              </el-table-column>
            </el-table>
          </div>

          <div class="mini-panel mini-panel--wide">
            <div class="mini-panel-head">
              <div>
                <div class="mini-panel-title">指标快照</div>
                <div class="mini-panel-desc">保留最近采集或手工录入的资源指标，用于判断水位风险和生成扩容建议。</div>
              </div>
              <el-tag size="small" type="warning">{{ waterlineRiskCount }} 个风险</el-tag>
            </div>
            <el-table v-loading="metricLoading" :data="resourceMetrics" stripe class="cmdb-table">
              <el-table-column label="资源" min-width="190">
                <template #default="{ row }">
                  <div class="resource-cell">
                    <button v-if="row.ci" type="button" class="resource-name-link" @click="openCiDetail({ id: row.ci })">{{ row.ci_name || `CI#${row.ci}` }}</button>
                    <strong v-else>{{ row.ci_name || `CI#${row.ci}` }}</strong>
                    <span>{{ row.ci_type_name || '-' }}</span>
                  </div>
                </template>
              </el-table-column>
              <el-table-column label="指标" min-width="120">
                <template #default="{ row }">{{ metricLabel(row.metric) }}</template>
              </el-table-column>
              <el-table-column label="当前值" width="130">
                <template #default="{ row }">{{ formatMetricValue(row) }}</template>
              </el-table-column>
              <el-table-column label="使用率" width="110">
                <template #default="{ row }">
                  <el-tag size="small" :type="metricRiskType(row)">{{ row.usage_percent ?? '-' }}%</el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="source" label="来源" width="120" />
              <el-table-column label="采集时间" width="170">
                <template #default="{ row }">{{ formatTime(row.collected_at) }}</template>
              </el-table-column>
              <el-table-column v-if="canManageCi || canSubmitRequest" label="操作" width="210" fixed="right" align="left">
                <template #default="{ row }">
                  <el-button v-if="isCapacityRisk(row) && canCreateCapacityRequest(row)" link type="primary" @click="openCapacityRequestDialog(row)">申请扩容</el-button>
                  <el-button link type="primary" @click="openMetricDialog(row)">编辑</el-button>
                  <el-button link type="danger" @click="deleteMetricRow(row)">删除</el-button>
                </template>
              </el-table-column>
            </el-table>
          </div>
        </div>
      </template>

      <template v-else-if="activeTab === 'audit'">
        <div class="workbench-toolbar workbench-toolbar--history cmdb-filter-bar">
          <div class="workbench-toolbar-left">
            <el-input v-model="auditFilters.search" clearable placeholder="搜索资源 / 动作 / 操作人 / 来源" style="width: 260px" @keyup.enter="fetchAuditLogs" />
            <el-date-picker
              v-model="auditFilters.range"
              type="daterange"
              range-separator="至"
              start-placeholder="开始日期"
              end-placeholder="结束日期"
              value-format="YYYY-MM-DD"
              style="width: 250px"
              @change="fetchAuditLogs"
            />
            <el-select v-model="auditFilters.action" clearable filterable placeholder="动作" style="width: 132px" @change="fetchAuditLogs">
              <el-option v-for="item in auditActionOptions" :key="item" :label="changeActionText(item)" :value="item" />
            </el-select>
            <el-select v-model="auditFilters.operator" clearable filterable placeholder="操作人" style="width: 132px" @change="fetchAuditLogs">
              <el-option v-for="item in auditOperatorOptions" :key="item" :label="item || '系统'" :value="item" />
            </el-select>
            <el-select v-model="auditFilters.source" clearable filterable placeholder="来源" style="width: 120px" @change="fetchAuditLogs">
              <el-option v-for="item in auditSourceOptions" :key="item" :label="changeSourceText(item)" :value="item" />
            </el-select>
          </div>
          <div class="workbench-toolbar-right">
            <el-button :loading="auditLoading" @click="fetchAuditLogs">查询</el-button>
            <el-button @click="clearAuditFilters">重置</el-button>
          </div>
        </div>

        <div class="audit-summary-grid">
          <div v-for="item in auditSummaryCards" :key="item.key" class="audit-summary-card" :class="item.tone">
            <span>{{ item.label }}</span>
            <strong>{{ item.value }}</strong>
          </div>
        </div>

        <el-table v-loading="auditLoading" :data="auditLogs" stripe class="cmdb-table">
          <el-table-column label="资源" min-width="190">
            <template #default="{ row }">
              <div class="resource-cell">
                <button v-if="row.ci" type="button" class="resource-name-link" @click="openCiDetail({ id: row.ci })">{{ row.ci_name || row.after?.name || row.before?.name || '-' }}</button>
                <strong v-else>{{ row.ci_name || row.after?.name || row.before?.name || '-' }}</strong>
                <span>{{ row.after?.ci_type_name || row.before?.ci_type_name || `CI#${row.ci || '-'}` }}</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="动作" width="120">
            <template #default="{ row }"><el-tag size="small" :type="changeActionTagType(row.action)">{{ changeActionText(row.action) }}</el-tag></template>
          </el-table-column>
          <el-table-column label="差异" min-width="220">
            <template #default="{ row }">
              <div class="audit-diff-cell">
                <span>{{ changeDiffText(row) }}</span>
                <el-tag v-if="changeDiffCount(row)" size="small" type="info">{{ changeDiffCount(row) }} 项</el-tag>
              </div>
            </template>
          </el-table-column>
          <el-table-column prop="operator" label="操作人" width="120">
            <template #default="{ row }">{{ row.operator || '系统' }}</template>
          </el-table-column>
          <el-table-column label="来源" width="120">
            <template #default="{ row }">{{ changeSourceText(row.source) }}</template>
          </el-table-column>
          <el-table-column label="时间" width="170">
            <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
          </el-table-column>
          <el-table-column label="操作" width="140" fixed="right" align="left">
            <template #default="{ row }">
              <el-button link type="primary" @click="openAuditDetail(row)">差异</el-button>
              <el-button v-if="row.ci" link type="info" @click="openCiDetail({ id: row.ci, name: row.ci_name })">详情</el-button>
            </template>
          </el-table-column>
        </el-table>
      </template>

      <template v-else-if="activeTab === 'model'">
        <div v-if="isModelCatalogRoute" class="opsany-model-catalog-layout" :class="{ 'opsany-model-catalog-layout--with-tree': hasModelCatalogTree }">
          <aside v-if="hasModelCatalogTree" class="opsany-view-tree ledger-resource-tree-panel">
            <div class="neo-tabs theme-blue ledger-perspective-tabs">
              <button
                v-for="tab in modelCatalogTreeModeOptions"
                :key="tab.key"
                type="button"
                class="neo-tab-btn"
                :class="{ active: modelCatalogTreeMode === tab.key }"
                @click="switchModelCatalogTreeMode(tab.key)"
              >
                <el-icon><component :is="tab.icon" /></el-icon>
                <span>{{ tab.label }}</span>
              </button>
            </div>
            <div class="ledger-tree-panel-head">
              <div>
                <strong>{{ modelCatalogTreeTitle }}</strong>
              </div>
            </div>
            <el-input
              v-model="modelCatalogTreeKeyword"
              clearable
              :placeholder="modelCatalogTreeSearchPlaceholder"
              class="opsany-tree-search"
            />
            <div class="opsany-view-tree-list">
              <button
                type="button"
                class="opsany-view-tree-node"
                :class="{ active: !modelCatalogTreeContext }"
                @click="selectModelCatalogTreeScope()"
              >
                <span>全部资产</span>
                <strong>{{ modelCatalogSourceRows.length }}</strong>
              </button>
              <button
                v-for="entry in activeModelCatalogTreeNodes"
                :key="entry.key"
                type="button"
                class="opsany-view-tree-node ledger-resource-tree-node"
                :class="[`is-level-${entry.level}`, { active: isModelCatalogTreeNodeActive(entry) }]"
                :style="{ '--ledger-node-depth': entry.depth || 0 }"
                @click="selectModelCatalogTreeScope(entry)"
              >
                <span class="ledger-tree-node-label">
                  <span
                    v-if="entry.has_children"
                    class="ledger-tree-toggle"
                    role="button"
                    tabindex="0"
                    @click.stop="toggleModelCatalogTreeNode(entry)"
                    @keydown.enter.stop.prevent="toggleModelCatalogTreeNode(entry)"
                    @keydown.space.stop.prevent="toggleModelCatalogTreeNode(entry)"
                  >
                    <el-icon><component :is="entry.is_expanded ? ArrowDown : ArrowRight" /></el-icon>
                  </span>
                  <span v-else class="ledger-tree-toggle ledger-tree-toggle--leaf" />
                  <el-icon class="ledger-tree-node-icon"><component :is="ledgerTreeNodeIcon(entry)" /></el-icon>
                  <span>{{ entry.label }}</span>
                </span>
                <strong>{{ entry.count }}</strong>
              </button>
            </div>
            <el-empty v-if="!activeModelCatalogTreeNodes.length" description="暂无归属资源" :image-size="56" />
          </aside>

          <div class="opsany-model-catalog-main">
            <template v-if="!isModelDetailRoute">
            <div class="opsany-model-tabs">
              <button
                v-for="item in modelGroupTabs"
                :key="item.key"
                type="button"
                :class="{ active: activeModelGroupKey === item.key }"
                @click="activeModelGroupKey = item.key"
              >
                {{ item.label }}
              </button>
            </div>
            <div class="opsany-model-toolbar">
              <div class="opsany-model-toolbar-left">
                <span>搜索模型：</span>
                <el-input v-model="opsanyModelKeyword" clearable placeholder="请输入模型名称" style="width: 220px" />
                <span>状态：</span>
                <el-select v-model="opsanyModelStatus" placeholder="状态" style="width: 150px">
                  <el-option label="启用中" value="active" />
                  <el-option label="全部" value="all" />
                  <el-option label="停用" value="inactive" />
                </el-select>
                <el-tag v-if="modelCatalogTreeContext && !isModelConfigRoute" size="small" type="info">{{ modelCatalogTreeContextText }}</el-tag>
                <el-button v-if="modelCatalogTreeContext && !isModelConfigRoute" size="small" @click="selectModelCatalogTreeScope()">退出归属筛选</el-button>
              </div>
            </div>
            <div class="opsany-model-section-list">
              <section v-for="section in opsanyModelSections" :key="section.key" class="opsany-model-section">
                <div class="opsany-model-section-head">
                  <strong>{{ section.label }}<span v-if="!isModelConfigRoute">（{{ section.models.length }}）</span></strong>
                  <span v-if="isModelConfigRoute && canManageModel" class="opsany-model-section-actions">
                    <button type="button" title="新建模型" @click="openModelDialog()"><el-icon><Plus /></el-icon></button>
                    <button type="button" title="编辑分组" :disabled="!section.group?.has_backend_group" @click="section.group?.has_backend_group && openModelGroupDialog(section.group)"><el-icon><Edit /></el-icon></button>
                    <button type="button" title="删除分组" :disabled="!section.group?.has_backend_group" @click="section.group?.has_backend_group && deleteModelGroupRow(section.group)"><el-icon><Delete /></el-icon></button>
                  </span>
                </div>
                <div class="opsany-model-card-grid">
                  <div
                    v-for="model in section.models"
                    :key="model.id || model.code"
                    class="opsany-model-card"
                    role="button"
                    tabindex="0"
                    :class="{ active: selectedModelId === model.id }"
                    @click="openModelCard(model)"
                    @keydown.enter.prevent="openModelCard(model)"
                  >
                    <span class="opsany-model-card-icon" :style="{ color: model.color || modelIconColor(model) }">
                      <el-icon><component :is="modelIconComponent(model)" /></el-icon>
                    </span>
                    <span class="opsany-model-card-main">
                      <strong>{{ model.name }}</strong>
                      <small>{{ model.code || '-' }}</small>
                    </span>
                    <span class="opsany-model-card-actions">
                      <span v-if="!isModelConfigRoute" class="opsany-model-card-count" :title="`${modelCardResourceCount(model)} 个资源`">
                        {{ modelCardResourceCount(model) }}
                      </span>
                      <button v-if="isModelConfigRoute && canManageModel" type="button" class="opsany-model-card-edit" title="配置资产分类" @click.stop="openModelConfigDrawer(model)">
                        <el-icon><Edit /></el-icon>
                      </button>
                    </span>
                  </div>
                </div>
              </section>
              <el-empty v-if="!filteredModelCards.length" description="暂无资产分类" :image-size="72" />
            </div>
            </template>
            <template v-else>
              <div class="model-detail-page-head">
                <el-button @click="backToModelList">
                  <el-icon><ArrowLeft /></el-icon>
                  返回资产分类
                </el-button>
                <div>
                  <strong>{{ selectedModel?.name || '模型详情' }}</strong>
                  <span>{{ selectedModel?.code || route.params.id || '-' }}</span>
                </div>
              </div>
              <div v-if="selectedModel" v-loading="modelResourceLoading" class="model-detail-layout model-detail-layout--resources-only">
                <section class="mini-panel mini-panel--wide model-detail-resources">
                  <div class="mini-panel-head">
                    <div>
                      <div class="mini-panel-title">资源实例</div>
                      <div class="mini-panel-desc">查看 {{ selectedModel.name }} 类型下已纳管资源，进入详情可继续看字段、关系和治理信息。</div>
                    </div>
                    <div class="inline-actions model-resource-actions">
                      <el-tag size="small" type="info">共 {{ modelResourcePagination.total || selectedModelResourceRows.length }} 条</el-tag>
                      <el-button
                        v-if="canManageSync"
                        size="small"
                        :loading="resourceWaterlinePageMetricLoading"
                        :disabled="!resourceWaterlineTargetRows(selectedModelResourceRows).length"
                        @click="refreshModelCurrentPageResourceWaterline"
                      >
                        <el-icon><RefreshRight /></el-icon>
                        重新同步当前页资产水位
                      </el-button>
                      <el-button size="small" @click="fetchModelResources(selectedModelId, { preservePage: true })">刷新</el-button>
                    </div>
                  </div>
                  <div v-if="isThirdPartyModelResourceMode" class="third-party-expiry-strip">
                    <div class="third-party-expiry-copy">
                      <strong>服务到期治理</strong>
                      <span>按服务到期日与提醒提前天数自动分级。</span>
                    </div>
                    <div class="third-party-expiry-actions">
                      <button
                        v-for="item in modelThirdPartyExpirySummaryRows"
                        :key="item.key"
                        type="button"
                        class="third-party-expiry-action"
                        :class="[item.tone, { active: modelResourceFilters.expiry_risk === item.key }]"
                        @click="applyModelThirdPartyExpiryFilter(item.key)"
                      >
                        <span>{{ item.label }}</span>
                        <strong>{{ item.value }}</strong>
                      </button>
                    </div>
                  </div>
                  <div class="workbench-toolbar workbench-toolbar--history cmdb-filter-bar">
                    <div class="workbench-toolbar-left">
                      <el-input v-model="modelResourceFilters.asset_search" clearable placeholder="搜索资产名" style="width: 150px" @keyup.enter="fetchModelResources(selectedModelId)" @clear="fetchModelResources(selectedModelId)" />
                      <el-input v-model="modelResourceFilters.attribute_search" clearable placeholder="搜索属性 IP / ID等" style="width: 180px" @keyup.enter="fetchModelResources(selectedModelId)" @clear="fetchModelResources(selectedModelId)" />
                      <el-select v-model="modelResourceFilters.status" clearable placeholder="状态" style="width: 112px" @change="handleModelResourceFilterChange">
                        <el-option label="使用中" value="active" />
                        <el-option label="停机" value="stopped" />
                        <el-option label="已下线" value="offline" />
                      </el-select>
                      <el-select v-model="modelResourceFilters.tags" clearable filterable placeholder="标签" style="width: 132px" @change="handleModelResourceFilterChange">
                        <el-option v-for="item in activeTagOptions" :key="item.id" :label="item.name" :value="item.id" />
                      </el-select>
                      <el-input v-model="modelResourceFilters.source_type" clearable placeholder="搜索来源" style="width: 116px" @keyup.enter="fetchModelResources(selectedModelId)" @clear="fetchModelResources(selectedModelId)" />
                      <el-input v-model="modelResourceFilters.ownership" clearable placeholder="搜索部门 / 负责人" style="width: 180px" @keyup.enter="fetchModelResources(selectedModelId)" @clear="fetchModelResources(selectedModelId)" />
                    </div>
                    <div class="workbench-toolbar-right">
                      <el-button @click="clearModelResourceFilters">重置</el-button>
                    </div>
                  </div>
                  <el-table :data="selectedModelResourceRows" stripe class="cmdb-table model-resource-table">
                    <el-table-column label="资产" min-width="220">
                      <template #default="{ row }">
                        <div class="resource-cell">
                          <button type="button" class="resource-name-link resource-name-link--primary" @click="openCiDetail(row)">{{ row.name }}</button>
                          <div class="resource-cell-meta">
                            <span>{{ row.ci_type_name }}</span>
                            <code v-if="row.id" class="asset-id-badge">资产 ID #{{ row.id }}</code>
                          </div>
                        </div>
                      </template>
                    </el-table-column>
                    <el-table-column label="属性" min-width="200">
                      <template #default="{ row }">
                        <div class="search-attribute-list">
                          <el-tooltip v-for="item in ledgerAttributeEntries(row).slice(0, 3)" :key="item.key" :content="`${item.label || item.key}: ${formatValue(item.value)}`" placement="top" :show-after="300">
                            <span>{{ item.label || item.key }}: {{ formatValue(item.value) }}</span>
                          </el-tooltip>
                          <span v-if="!ledgerAttributeEntries(row).length" class="sub-text">-</span>
                        </div>
                      </template>
                    </el-table-column>
                    <el-table-column v-if="hasModelResourceWaterlineRows" label="资产水位" min-width="190">
                      <template #default="{ row }">
                        <el-tooltip v-if="isResourceWaterlineTarget(row)" placement="top" :show-after="300">
                          <template #content>
                            <div class="resource-waterline-tooltip">
                              <div><span>采集来源</span><strong>{{ resourceWaterlineTooltipSource(row) }}</strong></div>
                              <div><span>采集时间</span><strong>{{ resourceWaterlineTooltipTime(row) }}</strong></div>
                            </div>
                          </template>
                          <div class="resource-waterline-cell">
                            <div v-for="item in resourceWaterlineRows(row)" :key="item.key" class="resource-waterline-row" :class="`is-${item.tone}`">
                              <span>{{ item.label }}</span>
                              <i><b :style="{ width: item.hasData ? `${item.percent}%` : '0%' }" /></i>
                              <strong>{{ item.hasData ? `${item.percent}%` : '-' }}</strong>
                            </div>
                          </div>
                        </el-tooltip>
                        <span v-else class="sub-text">-</span>
                      </template>
                    </el-table-column>
                    <el-table-column label="业务环境" width="136">
                      <template #default="{ row }">
                        <div class="stack-cell">
                          <span>业务线：{{ ledgerBusinessLineDisplay(row) }}</span>
                          <span>环境：{{ ledgerBusinessEnvironmentDisplay(row) }}</span>
                        </div>
                      </template>
                    </el-table-column>
                    <el-table-column v-if="isDataServiceModelResourceMode" label="规格 / 容量" min-width="180">
                      <template #default="{ row }">
                        <div class="stack-cell">
                          <span>{{ ledgerDataServiceSpec(row) }}</span>
                          <div class="sub-text">
                            {{ ledgerDataServiceCapacity(row) }}
                            <el-tag v-if="ledgerDataServiceUsage(row)" size="small" :type="ledgerUsageTagType(row)" style="margin-left: 6px">
                              {{ ledgerDataServiceUsage(row) }}
                            </el-tag>
                          </div>
                        </div>
                      </template>
                    </el-table-column>
                    <el-table-column v-if="isDataServiceModelResourceMode" label="网络 / 版本" min-width="180">
                      <template #default="{ row }">
                        <div class="stack-cell">
                          <span>{{ ledgerDataServiceNetwork(row) }}</span>
                          <div class="sub-text">{{ ledgerDataServiceVersion(row) }}</div>
                        </div>
                      </template>
                    </el-table-column>
                    <el-table-column v-if="isEdgeServiceModelResourceMode" label="入口 / 容量" min-width="190">
                      <template #default="{ row }">
                        <div class="stack-cell">
                          <span>{{ ledgerEdgeEndpoint(row) }}</span>
                          <div class="sub-text">{{ ledgerEdgeCapacity(row) }}</div>
                        </div>
                      </template>
                    </el-table-column>
                    <el-table-column v-if="isEdgeServiceModelResourceMode" label="网络 / 策略" min-width="190">
                      <template #default="{ row }">
                        <div class="stack-cell">
                          <span>{{ ledgerEdgeNetwork(row) }}</span>
                          <div class="sub-text">{{ ledgerEdgePolicy(row) }}</div>
                        </div>
                      </template>
                    </el-table-column>
                    <el-table-column v-if="isIdcModelResourceMode" label="机房 / 机柜" min-width="170">
                      <template #default="{ row }">
                        <div class="stack-cell">
                          <span>{{ row.attributes?.idc || row.attributes?.machine_room || row.attributes?.room || '-' }}</span>
                          <div class="sub-text">{{ row.attributes?.rack || row.attributes?.cabinet || '-' }}{{ row.attributes?.u_position ? ` / ${row.attributes.u_position}` : '' }}</div>
                        </div>
                      </template>
                    </el-table-column>
                    <el-table-column v-if="isIdcModelResourceMode" label="生命周期 / 服务到期" min-width="190">
                      <template #default="{ row }">
                        <div class="stack-cell">
                          <div>
                            <el-tag size="small" :type="idcLifecycleTagType(row.attributes?.lifecycle_status)">{{ idcLifecycleText(row.attributes?.lifecycle_status) }}</el-tag>
                            <el-tag size="small" :type="serviceExpiryTagType(row)" style="margin-left: 6px">{{ serviceExpiryStatusText(row) }}</el-tag>
                          </div>
                          <div class="sub-text">服务到期 {{ serviceExpiryDate(row) || '-' }}</div>
                        </div>
                      </template>
                    </el-table-column>
                    <el-table-column v-if="isThirdPartyModelResourceMode" label="服务 / 供应商" min-width="180">
                      <template #default="{ row }">
                        <div class="stack-cell">
                          <span>{{ row.attributes?.service_type || '-' }}</span>
                          <div class="sub-text">{{ row.attributes?.provider || '-' }}</div>
                        </div>
                      </template>
                    </el-table-column>
                    <el-table-column v-if="isThirdPartyModelResourceMode" label="账号主体" min-width="180">
                      <template #default="{ row }">
                        <div class="stack-cell">
                          <span>{{ row.attributes?.account_subject || '-' }}</span>
                          <div class="sub-text">服务地址：{{ row.attributes?.service_endpoint || '-' }}</div>
                        </div>
                      </template>
                    </el-table-column>
                    <el-table-column v-if="isThirdPartyModelResourceMode" label="到期治理" min-width="190">
                      <template #default="{ row }">
                        <div class="stack-cell">
                          <el-tag size="small" :type="externalExpiryTagType(row)">{{ externalExpiryText(row) }}</el-tag>
                          <div class="sub-text">服务到期日 {{ row.attributes?.service_expiry_date || '-' }}</div>
                        </div>
                      </template>
                    </el-table-column>
                    <el-table-column label="资产状态" width="88">
                      <template #default="{ row }"><el-tag size="small" :type="ledgerStatusTagType(row)">{{ ledgerStatusText(row) }}</el-tag></template>
                    </el-table-column>
                    <el-table-column label="来源 / 同步状态" min-width="150">
                      <template #default="{ row }">
                        <div class="stack-cell source-sync-cell">
                          <span>来源：{{ ledgerSourceLabel(row) }}</span>
                          <div class="source-sync-status sub-text">
                            <span>同步状态：</span>
                            <el-tag v-if="ledgerSourceSyncStatus(row)" size="small" :type="syncStatusTagType(ledgerSourceSyncStatus(row))">
                              {{ sourceMappingStatusText(ledgerSourceSyncStatus(row)) }}
                            </el-tag>
                            <span v-else>-</span>
                          </div>
                        </div>
                      </template>
                    </el-table-column>
                    <el-table-column label="部门 / 负责人" width="126">
                      <template #default="{ row }">
                        <div class="stack-cell ownership-cell">
                          <span>部门：{{ ledgerOwnershipDepartmentDisplay(row) }}</span>
                          <span>负责人：{{ ledgerOwnershipAdminDisplay(row) }}</span>
                        </div>
                      </template>
                    </el-table-column>
                    <el-table-column label="标签" min-width="118">
                      <template #default="{ row }">
                        <div class="tag-chip-list">
                          <span v-for="tag in row.tag_items || []" :key="tag.id" class="tag-chip" :style="{ borderColor: tag.color || '#dbe4f0', color: tag.color || '#245bdb' }">
                            {{ tag.name }}
                          </span>
                          <span v-if="!(row.tag_items || []).length" class="sub-text">-</span>
                        </div>
                      </template>
                    </el-table-column>
                    <el-table-column label="更新时间" width="170">
                      <template #default="{ row }">{{ formatTime(row.updated_at) }}</template>
                    </el-table-column>
                    <el-table-column label="操作" width="150" fixed="right" align="left">
                      <template #default="{ row }">
                        <el-button link type="primary" @click="openCiDetail(row)">详情</el-button>
                        <el-button v-if="canManageCi" link type="info" @click="openCiDialog(row)">编辑</el-button>
                      </template>
                    </el-table-column>
                  </el-table>
                  <div class="ledger-pagination model-resource-pagination">
                    <el-pagination
                      v-model:current-page="modelResourcePagination.page"
                      v-model:page-size="modelResourcePagination.pageSize"
                      background
                      layout="total, sizes, prev, pager, next, jumper"
                      :page-sizes="[10, 20, 50, 100]"
                      :total="modelResourcePagination.total"
                      @size-change="handleModelResourcePageSizeChange"
                      @current-change="handleModelResourcePageChange"
                    />
                  </div>
                  <el-empty v-if="!selectedModelResourceRows.length && !modelResourceLoading" description="暂无资源实例" :image-size="72" />
                </section>
              </div>
              <el-empty v-if="ciTypes.length && !selectedModel && !modelResourceLoading" description="未找到模型" :image-size="72" />
            </template>
          </div>
        </div>
        <div v-else-if="isModelTopologyRoute" class="topology-knowledge-shell">
          <div class="workbench-toolbar workbench-toolbar--history cmdb-filter-bar topology-filter-bar">
            <div class="workbench-toolbar-left">
              <el-select v-model="topologyFilters.ci_type" clearable filterable placeholder="资产分类" style="width: 160px" @change="fetchTopology">
                <el-option v-for="item in visibleAssetClassificationTypes" :key="item.id" :label="item.name" :value="item.id" />
              </el-select>
              <el-select v-model="topologyFilters.business_line" clearable filterable placeholder="业务线" style="width: 150px" @change="fetchTopology">
                <el-option v-for="item in businessLineOptions" :key="item" :label="item" :value="item" />
              </el-select>
              <el-select v-model="topologyFilters.environment" clearable filterable placeholder="环境" style="width: 130px" @change="fetchTopology">
                <el-option v-for="item in environmentOptions" :key="item" :label="environmentText(item)" :value="item" />
              </el-select>
              <el-segmented v-model="topologyFilters.scope" :options="topologyScopeOptions" @change="fetchTopology" />
            </div>
            <div class="workbench-toolbar-right">
              <el-button :loading="topologyLoading" @click="fetchTopology">刷新图谱</el-button>
              <el-button @click="clearTopologyFilters">重置</el-button>
            </div>
          </div>

          <div class="topology-summary-grid">
            <div v-for="item in topologySummaryCards" :key="item.key" class="topology-summary-card" :class="item.tone">
              <span>{{ item.label }}</span>
              <strong>{{ item.value }}</strong>
            </div>
          </div>

          <div v-loading="topologyLoading" class="topology-knowledge-layout">
            <section class="knowledge-graph-panel">
              <div class="knowledge-panel-head">
                <div>
                  <strong>资产分类拓扑图</strong>
                  <span>按业务、计算、数据库、中间件、存储、大数据、网络和第三方服务分层展示关系。</span>
                </div>
                <el-tag size="small" type="info">{{ topologyMeta.scope === 'exact' ? '精确范围' : '带邻居节点' }}</el-tag>
              </div>
              <div class="knowledge-graph-stage">
                <div class="knowledge-graph-source-note">
                  <el-icon><InfoFilled /></el-icon>
                  <span>{{ topologyGraphSourceText }}</span>
                </div>
                <div class="knowledge-graph-legend">
                  <div class="legend-title">资产分层</div>
                  <div v-for="lane in topologyGraphLanes" :key="lane.key" class="legend-row">
                    <span class="legend-dot" :style="{ background: lane.color }"></span>
                    <span>{{ lane.label }}</span>
                    <em>{{ lane.nodes.length }}</em>
                  </div>
                  <div class="legend-divider"></div>
                  <div class="legend-title">关系类型</div>
                  <div v-for="item in topologyRelationLegend" :key="item.type" class="legend-row">
                    <span class="legend-line"></span>
                    <span>{{ item.label }}</span>
                    <em>{{ item.count }}</em>
                  </div>
                </div>
                <div class="knowledge-graph-board" :style="{ width: `${topologyGraphBoard.width}px`, height: `${topologyGraphBoard.height}px` }">
                  <svg class="knowledge-graph-edges" :width="topologyGraphBoard.width" :height="topologyGraphBoard.height">
                    <path
                      v-for="edge in topologyGraphEdgePaths"
                      :key="edge.id"
                      :d="edge.path"
                      class="knowledge-board-edge"
                      :class="[`is-${edge.type}`, { 'is-match': edge.is_match }]"
                    />
                  </svg>
                  <section v-for="lane in topologyGraphLanes" :key="lane.key" class="knowledge-board-lane" :style="topologyLaneStyle(lane)">
                    <div class="knowledge-board-lane-title">
                      <span>{{ lane.label }}</span>
                      <strong>{{ lane.nodes.length }}</strong>
                    </div>
                    <div class="knowledge-board-lane-body">
                      <span class="knowledge-board-lane-count">{{ lane.nodes.length }} 个节点</span>
                    </div>
                  <button
                    v-for="node in lane.nodes"
                    :key="node.id"
                    type="button"
                    class="knowledge-board-node"
                    :class="{ 'is-match': node.is_match }"
                    :style="topologyBoardNodeStyle(node)"
                    @click="openCiDetail(node)"
                  >
                    <span class="knowledge-board-node-dot"></span>
                    <span class="knowledge-board-node-main">
                      <strong>{{ node.name }}</strong>
                      <small>{{ node.type || '-' }}</small>
                    </span>
                    <span class="knowledge-board-node-meta">{{ environmentText(node.env) }}</span>
                  </button>
                  </section>
                </div>
                <el-empty v-if="!topologyNodes.length && !topologyLoading" class="knowledge-graph-empty" description="暂无拓扑节点" :image-size="72" />
              </div>
            </section>

            <aside class="knowledge-relation-panel">
              <div class="knowledge-panel-head">
                <div>
                  <strong>关系链</strong>
                  <span>按当前筛选展示资产之间的依赖、承载和访问关系。</span>
                </div>
              </div>
              <div class="knowledge-relation-list">
                <div v-for="edge in topologyEdgeRows" :key="edge.id" class="knowledge-relation-row" :class="{ 'is-match': edge.is_match }">
                  <div class="knowledge-relation-chain">
                    <span>{{ edge.sourceName }}</span>
                    <strong>{{ edge.label }}</strong>
                    <span>{{ edge.targetName }}</span>
                  </div>
                  <p>{{ edge.description || relationTypeLabel(edge.type) }}</p>
                </div>
                <el-empty v-if="!topologyEdgeRows.length" description="暂无关系" :image-size="56" />
              </div>
            </aside>
          </div>
        </div>
      </template>
    </div>

    <el-dialog top="5vh" :close-on-click-modal="false" class="workbench-edit-dialog" v-model="requestDialogVisible" title="新建资产申请" width="920px" append-to-body destroy-on-close>
      <el-form label-position="top" v-loading="requestProvisioningOptionsLoading" :model="requestForm" label-width="104px" class="cmdb-form-grid request-create-form">
        <el-form-item label="申请标题" class="span-2" required><el-input v-model="requestForm.title" placeholder="例如：订单服务生产环境扩容 2 台" /></el-form-item>
        <el-form-item label="资产类型" required>
          <el-select v-model="requestForm.resource_type" filterable style="width: 100%" @change="onRequestResourceTypeChange">
            <el-option v-for="item in requestResourceTypeOptions" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
        </el-form-item>
        <div class="request-type-hint"><span>支持阿里云全量资源目录</span><small>{{ requestSelectedTypeMeta?.delivery === 'cloud' ? '可自动交付' : '审批后人工交付入库' }}</small></div>
        <el-form-item label="交付方式" class="span-2" required>
          <el-radio-group v-model="requestForm.specs.provisioning_mode" class="request-delivery-switch" @change="onRequestDeliveryModeChange">
            <el-radio-button value="cloud">云平台自动交付</el-radio-button>
            <el-radio-button value="manual">人工交付</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <template v-if="requestIsCloudDelivery">
          <div class="request-provision-hint span-2">
            <el-icon><Connection /></el-icon>
            <span>审批通过后由具备执行权限的运维人员发起创建，平台会记录实例 ID 并自动写入多云资产与 CMDB。</span>
          </div>
          <el-form-item label="目标平台" required>
            <el-select v-model="requestForm.specs.provider" style="width: 100%" @change="onRequestProviderChange">
              <el-option v-for="item in requestProviderOptions" :key="item.value" :label="item.label" :value="item.value" />
            </el-select>
          </el-form-item>
          <el-form-item label="交付账号" required>
            <el-select v-model="requestForm.specs.cloud_credential_id" filterable placeholder="选择已启用云账号" style="width: 100%" @change="onRequestCredentialChange">
              <el-option v-for="item in requestCredentialOptions" :key="item.id" :label="`${item.name}${item.health === 'healthy' ? ' · 健康' : ''}`" :value="item.id" />
            </el-select>
          </el-form-item>
          <el-form-item label="地域 / 站点" required><el-input v-model="requestForm.specs.region" placeholder="cn-hangzhou / cn-north-4 / vCenter 站点" /></el-form-item>
          <el-form-item label="可用区"><el-input v-model="requestForm.specs.zone" placeholder="可选，如 cn-hangzhou-h" /></el-form-item>
          <el-form-item label="实例命名" required><el-input v-model="requestForm.specs.instance_name_prefix" placeholder="单台为完整名称，多台自动追加 -01" /></el-form-item>
          <el-form-item label="申请数量"><el-input-number v-model="requestForm.quantity" :min="1" :max="20" style="width: 100%" /></el-form-item>

          <template v-if="requestIsAliyun && requestIsEcsType">
            <el-form-item label="镜像 ID" required><el-input v-model="requestForm.specs.image_id" placeholder="aliyun_3_x64_20G_alibase_20240528.vhd" /></el-form-item>
            <el-form-item label="实例规格" required><el-input v-model="requestForm.specs.instance_type" placeholder="ecs.g7.large" /></el-form-item>
            <el-form-item label="安全组 ID" required><el-input v-model="requestForm.specs.security_group_id" placeholder="sg-xxxx" /></el-form-item>
            <el-form-item label="交换机 ID" required><el-input v-model="requestForm.specs.vswitch_id" placeholder="vsw-xxxx" /></el-form-item>
            <el-form-item label="密钥对"><el-input v-model="requestForm.specs.key_pair_name" placeholder="推荐使用已有密钥对" /></el-form-item>
            <el-form-item label="系统盘">
              <div class="request-inline-fields">
                <el-select v-model="requestForm.specs.system_disk_category"><el-option label="ESSD" value="cloud_essd" /><el-option label="高效云盘" value="cloud_efficiency" /></el-select>
                <el-input-number v-model="requestForm.specs.system_disk_size" :min="20" :max="2048" />
                <span>GB</span>
              </div>
            </el-form-item>
          </template>

          <template v-else-if="requestIsAliyun">
            <div class="request-provision-hint span-2"><el-icon><InfoFilled /></el-icon><span>{{ requestSelectedTypeMeta?.label }}支持申请与审批，完成交付后会按资产类型写入 CMDB；当前采用人工交付。</span></div>
            <el-form-item label="资产名称" required><el-input v-model="requestForm.specs.resource_name" placeholder="例如 trade-rds-prod" /></el-form-item>
            <el-form-item label="资源 ID"><el-input v-model="requestForm.specs.resource_id" placeholder="实例 / 集群 / Bucket ID" /></el-form-item>
            <el-form-item label="规格 / 版本"><el-input v-model="requestForm.specs.instance_class" placeholder="实例规格、版本或套餐" /></el-form-item>
            <el-form-item label="容量 / 节点"><el-input v-model="requestForm.specs.capacity" placeholder="例如 100GB、3 节点" /></el-form-item>
            <el-form-item label="网络 / VPC"><el-input v-model="requestForm.specs.vpc_id" placeholder="VPC、交换机或终端节点" /></el-form-item>
            <el-form-item label="补充参数" class="span-2"><el-input v-model="requestForm.specs.extra_requirements" type="textarea" :rows="2" placeholder="填写白名单、带宽、节点规格等交付要求" /></el-form-item>
          </template>

          <template v-else-if="requestIsHuawei">
            <el-form-item label="镜像 ID" required><el-input v-model="requestForm.specs.image_id" placeholder="IMS 镜像 ID" /></el-form-item>
            <el-form-item label="规格 ID" required><el-input v-model="requestForm.specs.flavor_ref" placeholder="s6.large.2" /></el-form-item>
            <el-form-item label="安全组 ID" required><el-input v-model="requestForm.specs.security_group_id" placeholder="安全组 UUID" /></el-form-item>
            <el-form-item label="VPC ID" required><el-input v-model="requestForm.specs.vpc_id" placeholder="VPC UUID" /></el-form-item>
            <el-form-item label="子网 ID" required><el-input v-model="requestForm.specs.subnet_id" placeholder="子网 UUID" /></el-form-item>
            <el-form-item label="密钥对"><el-input v-model="requestForm.specs.key_name" placeholder="推荐使用已有密钥对" /></el-form-item>
            <el-form-item label="系统盘">
              <div class="request-inline-fields">
                <el-select v-model="requestForm.specs.root_volume_type"><el-option label="通用型 SSD V2" value="GPSSD2" /><el-option label="通用型 SSD" value="GPSSD" /><el-option label="高 IO" value="SAS" /></el-select>
                <el-input-number v-model="requestForm.specs.root_volume_size" :min="40" :max="2048" />
                <span>GB</span>
              </div>
            </el-form-item>
          </template>

          <template v-else-if="requestIsVsphere">
            <el-form-item label="虚机模板" required><el-input v-model="requestForm.specs.template_name" placeholder="vCenter 中的模板名称" /></el-form-item>
            <el-form-item label="数据存储" required><el-input v-model="requestForm.specs.datastore_name" placeholder="Datastore 名称" /></el-form-item>
            <el-form-item label="计算集群"><el-input v-model="requestForm.specs.cluster_name" placeholder="留空则沿用模板资源池" /></el-form-item>
            <el-form-item label="虚机目录"><el-input v-model="requestForm.specs.folder_name" placeholder="留空则沿用模板目录" /></el-form-item>
            <el-form-item label="CPU / 内存">
              <div class="request-inline-fields">
                <el-input-number v-model="requestForm.specs.cpu" :min="1" :max="128" />
                <span>核</span>
                <el-input-number v-model="requestForm.specs.memory_gb" :min="1" :max="1024" />
                <span>GB</span>
              </div>
            </el-form-item>
            <el-form-item label="创建后开机"><el-switch v-model="requestForm.specs.power_on" /></el-form-item>
          </template>
        </template>

        <el-form-item label="业务线" required>
          <el-select v-model="requestForm.business_line" filterable placeholder="选择业务线" style="width: 100%" @change="onRequestBusinessLineChange">
            <el-option v-for="item in businessLineOptions" :key="item" :label="item" :value="item" />
          </el-select>
        </el-form-item>
        <el-form-item label="环境" required>
          <el-select v-model="requestForm.environment" placeholder="选择环境" style="width: 100%">
            <el-option v-for="item in requestEnvironmentOptions" :key="item" :label="environmentText(item)" :value="item" />
          </el-select>
        </el-form-item>
        <el-form-item label="规格摘要"><el-input v-model="requestForm.specification" placeholder="例如 2C4G / ecs.g7.large" /></el-form-item>
        <el-form-item v-if="!requestIsCloudDelivery" label="数量"><el-input-number v-model="requestForm.quantity" :min="1" :max="20" /></el-form-item>
        <el-form-item v-if="!requestIsCloudDelivery && requestForm.quantity > 1" label="主机清单" class="span-2">
          <el-input
            v-model="requestForm.host_list_text"
            type="textarea"
            :rows="4"
            placeholder="每行一台：主机名, IP, 实例规格（可选）"
          />
        </el-form-item>
        <el-form-item label="优先级">
          <el-select v-model="requestForm.priority" style="width: 100%">
            <el-option label="低" value="low" />
            <el-option label="中" value="medium" />
            <el-option label="高" value="high" />
            <el-option label="紧急" value="urgent" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="!requestIsCloudDelivery && requestForm.quantity <= 1" label="主机名"><el-input v-model="requestForm.specs.hostname" placeholder="可在人工交付时补充" /></el-form-item>
        <el-form-item v-if="!requestIsCloudDelivery && requestForm.quantity <= 1" label="IP 地址"><el-input v-model="requestForm.specs.ip_address" placeholder="可在人工交付时补充" /></el-form-item>
        <el-form-item label="操作系统"><el-input v-model="requestForm.specs.os_type" placeholder="Linux / Windows" /></el-form-item>
        <el-form-item label="负责人"><el-input v-model="requestForm.specs.admin_user" /></el-form-item>
        <el-form-item label="申请理由" class="span-2" required>
          <el-input v-model="requestForm.reason" type="textarea" :rows="3" placeholder="说明用途、业务背景、上线窗口和期望交付时间" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="requestDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submitResourceRequest">提交申请</el-button>
      </template>
    </el-dialog>

    <el-dialog top="5vh" :close-on-click-modal="false" class="workbench-edit-dialog" v-model="requestActionVisible" :title="requestActionTitle" width="560px" append-to-body destroy-on-close>
      <div class="request-action-shell">
        <div v-if="requestActionRow" class="request-action-card">
          <strong>{{ requestActionRow.title }}</strong>
          <span>{{ requestActionRow.business_line || '-' }} / {{ environmentText(requestActionRow.environment) }} / {{ requestActionRow.specification || '-' }}</span>
          <span v-if="requestActionType === 'complete'">交付会将申请中的资产信息同步到 CMDB 台账；主机类资产同时写入主机资产。</span>
          <span v-if="requestActionType === 'provision'">将使用 {{ requestActionRow.provider_label }} 账号执行真实机器创建，并自动同步多云资产与 CMDB。</span>
          <el-alert v-if="requestActionType === 'provision' && requestActionRow.provisioning?.error" type="error" :closable="false" show-icon :title="requestActionRow.provisioning.error" />
        </div>
        <el-form label-position="top" v-if="requestActionType === 'complete'" :model="requestActionDeliveryForm" label-width="92px" class="cmdb-form-grid request-delivery-form">
          <template v-if="requestActionIsHost && Number(requestActionRow?.quantity || 1) > 1">
            <el-form-item label="交付清单" class="span-2" required>
              <el-input
                v-model="requestActionDeliveryForm.host_list_text"
                type="textarea"
                :rows="5"
                placeholder="每行一台：主机名 IP, 实例规格（可选）"
              />
            </el-form-item>
          </template>
          <template v-else-if="requestActionIsHost">
            <el-form-item label="主机名" required><el-input v-model="requestActionDeliveryForm.hostname" /></el-form-item>
            <el-form-item label="IP 地址" required><el-input v-model="requestActionDeliveryForm.ip_address" /></el-form-item>
          </template>
          <el-form-item v-if="requestActionIsHost" label="系统"><el-input v-model="requestActionDeliveryForm.os_type" placeholder="Linux / Windows" /></el-form-item>
          <el-form-item label="负责人"><el-input v-model="requestActionDeliveryForm.admin_user" /></el-form-item>
          <el-form-item v-if="requestActionIsHost" label="实例规格" class="span-2"><el-input v-model="requestActionDeliveryForm.instance_type" placeholder="ecs.g7.large / 2C4G" /></el-form-item>
        </el-form>
        <el-input
          v-model="requestActionNote"
          type="textarea"
          :rows="4"
          :placeholder="requestActionPlaceholder"
        />
      </div>
      <template #footer>
        <el-button @click="requestActionVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submitRequestAction">确认</el-button>
      </template>
    </el-dialog>

    <el-dialog top="5vh" :close-on-click-modal="false" class="workbench-edit-dialog" v-model="resourceNodeDialogVisible" :title="resourceNodeDialogTitle" width="560px" append-to-body destroy-on-close>
      <el-form label-position="top" :model="resourceNodeForm" label-width="92px" class="cmdb-form-grid">
        <el-form-item label="节点类型" required>
          <el-select v-model="resourceNodeForm.node_type" :disabled="!!resourceNodeEditingId" style="width: 100%" @change="onResourceNodeTypeChange">
            <el-option v-for="item in resourceNodeTypeOptions" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="resourceNodeParentRequired" :label="resourceNodeParentLabel" required>
          <el-input v-if="resourceNodeVirtualParentEntry" :model-value="resourceNodeVirtualParentLabel" :disabled="resourceNodeEditSortOnly" />
          <el-select v-else v-model="resourceNodeForm.parent" filterable :placeholder="`选择${resourceNodeParentLabel}`" :disabled="resourceNodeEditSortOnly" style="width: 100%">
            <el-option v-for="item in resourceNodeParentOptions" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="节点名称" required><el-input v-model="resourceNodeForm.name" :placeholder="resourceNodeNamePlaceholder" :disabled="resourceNodeEditSortOnly" /></el-form-item>
        <el-form-item label="排序"><el-input-number v-model="resourceNodeForm.sort_order" :min="0" :max="9999" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="resourceNodeDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveResourceNode">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog top="5vh" :close-on-click-modal="false" class="workbench-edit-dialog" v-model="completionDialogVisible" :title="completionDialogTitle" width="720px" append-to-body destroy-on-close>
      <div class="completion-dialog-shell">
        <div v-if="completionIssueRow" class="request-action-card">
          <strong>{{ completionIssueRow.ci_name }}</strong>
          <span>{{ completionIssueRow.ci_type_name || '-' }} / 当前缺失：{{ completionMissingFields.map(item => item.name || item.code).join('、') || '-' }}</span>
        </div>
        <div v-else class="request-action-card">
          <strong>已选择 {{ completionSelection.length }} 个待补全资源</strong>
          <span>批量填写公共归属字段，仍缺模型专属必填字段的资源会继续留在治理队列。</span>
        </div>
        <el-form label-position="top" :model="completionForm" label-width="92px" class="workbench-editor-form--sectioned cmdb-form-grid">
          <section class="workbench-editor-section">
            <div class="workbench-editor-heading"><span class="workbench-editor-step">01</span><h3>资源归属</h3></div>
            <div class="workbench-editor-grid">
              <el-form-item label="业务线">
                <el-select v-model="completionForm.business_line" clearable filterable allow-create placeholder="选择或填写业务线" style="width: 100%" @change="onCompletionBusinessLineChange">
                  <el-option v-for="item in businessLineOptions" :key="item" :label="item" :value="item" />
                </el-select>
              </el-form-item>
              <el-form-item label="环境">
                <el-select v-model="completionForm.environment" clearable filterable allow-create placeholder="选择或填写环境" style="width: 100%">
                  <el-option v-for="item in completionEnvironmentOptions" :key="item" :label="item" :value="item" />
                  <el-option label="生产" value="prod" />
                  <el-option label="测试" value="test" />
                  <el-option label="开发" value="dev" />
                </el-select>
              </el-form-item>
              <el-form-item label="负责人"><el-input v-model="completionForm.admin_user" placeholder="资源负责人 / 运维负责人" /></el-form-item>
              <el-form-item label="部门"><el-input v-model="completionForm.department" placeholder="归属部门 / 组织单元" /></el-form-item>
            </div>
          </section>
          <section class="workbench-editor-section workbench-editor-section--tinted">
            <div class="workbench-editor-heading"><span class="workbench-editor-step">02</span><h3>处理说明与属性</h3></div>
            <div>
              <el-form-item class="workbench-editor-full" label="处理说明"><el-input v-model="completionForm.note" /></el-form-item>
              <el-form-item label="扩展属性" class="span-2">
                <el-input v-model="completionForm.attributesText" type="textarea" :rows="7" placeholder='JSON 对象，用于补齐模型必填字段，例如 {"instance_id":"i-xxx"}' />
              </el-form-item>
            </div>
          </section>
        </el-form>
      </div>
      <template #footer>
        <el-button @click="completionDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveCompletionIssue">{{ completionIssueRow ? '保存并解决' : '批量保存并解决' }}</el-button>
      </template>
    </el-dialog>

    <el-dialog top="5vh" :close-on-click-modal="false" class="workbench-edit-dialog" v-model="completionAssignVisible" title="转派待补全" width="520px" append-to-body destroy-on-close>
      <div class="completion-dialog-shell">
        <div v-if="completionAssignRow" class="request-action-card">
          <strong>{{ completionAssignRow.ci_name }}</strong>
          <span>{{ completionAssignRow.ci_type_name || '-' }} / 缺失：{{ (completionAssignRow.missing_fields || []).map(item => item.name || item.code).join('、') || '-' }}</span>
        </div>
        <el-form label-position="top" :model="completionAssignForm" label-width="82px">
          <el-form-item label="处理人" required>
            <el-input v-model="completionAssignForm.assigned_to" maxlength="80" placeholder="填写接收人、团队或值班组" />
          </el-form-item>
          <el-form-item label="说明">
            <el-input v-model="completionAssignForm.note" type="textarea" :rows="3" maxlength="200" show-word-limit placeholder="说明转派原因或补全要求" />
          </el-form-item>
        </el-form>
      </div>
      <template #footer>
        <el-button @click="completionAssignVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveCompletionAssign">确认转派</el-button>
      </template>
    </el-dialog>

    <el-dialog top="5vh" :close-on-click-modal="false" class="workbench-edit-dialog" v-model="ciDialogVisible" :title="ciEditingId ? '编辑资产' : '新建资产'" width="720px" append-to-body destroy-on-close>
      <el-form label-position="top" :model="ciForm" label-width="92px" class="cmdb-form-grid">
        <el-form-item label="资产名称" required><el-input v-model="ciForm.name" placeholder="填写资产名称" /></el-form-item>
        <el-form-item label="资产分类" required>
          <el-select v-model="ciForm.ci_type" filterable placeholder="选择资产分类" style="width: 100%">
            <el-option v-for="item in ciTypes" :key="item.id" :label="item.name" :value="item.id" />
          </el-select>
        </el-form-item>
        <div v-if="selectedCiFormModel" class="ci-form-model-summary span-2">
          <div class="ci-form-model-summary-main">
            <strong>{{ selectedCiFormModel.name }}</strong>
            <span>{{ selectedCiFormModel.code || '-' }} / {{ selectedCiFormModel.group_name || '未分组' }}</span>
          </div>
          <div class="ci-form-model-summary-tags">
            <el-tag size="small" type="info">字段 {{ ciFormModelFields.length }}</el-tag>
            <el-tag size="small" :type="ciFormRequiredFields.length ? 'danger' : 'info'">必填 {{ ciFormRequiredFields.length }}</el-tag>
            <el-tag size="small" type="info">可选 {{ ciFormOptionalFieldCount }}</el-tag>
          </div>
          <p v-if="selectedCiFormModel.description">{{ selectedCiFormModel.description }}</p>
        </div>
        <div class="cmdb-form-section-title span-2">
          <span>基础信息</span>
          <small>所有资产通用字段</small>
        </div>
        <el-form-item label="业务线">
          <el-select v-model="ciForm.business_node" clearable filterable placeholder="选择业务线" style="width: 100%" @change="onCiBusinessNodeChange">
            <el-option v-for="item in ciBusinessNodeOptions" :key="item.id" :label="item.name" :value="item.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="环境">
          <el-select
            v-model="ciForm.environment_node"
            clearable
            filterable
            :disabled="!ciForm.business_node || !ciEnvironmentNodeOptions.length"
            :placeholder="ciForm.business_node ? '选择环境' : '请先选择业务线'"
            style="width: 100%"
          >
            <el-option v-for="item in ciEnvironmentNodeOptions" :key="item.id" :label="item.name" :value="item.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="来源云账号">
          <el-select v-model="ciForm.source_account" clearable filterable placeholder="选择来源云账号" style="width: 100%" @change="onCiSourceAccountChange">
            <el-option v-for="item in ciSourceAccountOptions" :key="item" :label="item" :value="item" />
          </el-select>
        </el-form-item>
        <el-form-item label="来源地域">
          <el-select
            v-model="ciForm.source_region"
            clearable
            filterable
            :disabled="!ciForm.source_account || !ciSourceRegionOptions.length"
            :placeholder="ciForm.source_account ? '选择来源地域' : '请先选择来源云账号'"
            style="width: 100%"
            @change="onCiSourceRegionChange"
          >
            <el-option v-for="item in ciSourceRegionOptions" :key="item" :label="item" :value="item" />
          </el-select>
        </el-form-item>
        <el-form-item label="部门"><el-input v-model="ciForm.department" placeholder="归属部门" /></el-form-item>
        <el-form-item label="负责人"><el-input v-model="ciForm.admin_user" placeholder="资源负责人" /></el-form-item>
        <el-form-item label="状态">
          <el-select v-model="ciForm.status" style="width: 100%">
            <el-option label="使用中" value="active" />
            <el-option label="停机" value="stopped" />
            <el-option label="已下线" value="offline" />
          </el-select>
        </el-form-item>
        <el-form-item label="月成本">
          <el-input-number
            v-model="ciForm.monthly_cost"
            :min="0"
            :precision="2"
            controls-position="right"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item label="标签" class="span-2">
          <el-select v-model="ciForm.tags" multiple clearable filterable placeholder="选择资源标签" style="width: 100%">
            <el-option v-for="item in activeTagOptions" :key="item.id" :label="item.name" :value="item.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="描述" class="span-2"><el-input v-model="ciForm.description" type="textarea" :rows="2" placeholder="补充说明、用途或维护信息" /></el-form-item>
        <template v-if="ciFormModelFields.length">
          <div class="cmdb-form-section-title span-2">
            <span>模型字段</span>
            <small>{{ selectedCiFormModel?.name || '当前模型' }}{{ ciFormRequiredFields.length ? ` · 必填 ${ciFormRequiredFields.map(item => item.name).join('、')}` : '' }}</small>
          </div>
          <el-form-item
            v-for="field in ciFormModelFields"
            :key="field.id || field.code"
            :label="field.name"
            :required="!!field.required"
            :class="{ 'span-2': isCiFormWideField(field) }"
          >
            <el-select
              v-if="field.field_type === 'enum'"
              v-model="ciForm.attributeValues[field.code]"
              clearable
              filterable
              :placeholder="`选择${field.name}`"
              style="width: 100%"
            >
              <el-option v-for="option in ciFieldOptions(field)" :key="option.value" :label="option.label" :value="option.value" />
            </el-select>
            <el-select
              v-else-if="field.field_type === 'multi_enum'"
              v-model="ciForm.attributeValues[field.code]"
              multiple
              clearable
              filterable
              :placeholder="`选择${field.name}`"
              style="width: 100%"
            >
              <el-option v-for="option in ciFieldOptions(field)" :key="option.value" :label="option.label" :value="option.value" />
            </el-select>
            <el-select v-else-if="field.field_type === 'boolean'" v-model="ciForm.attributeValues[field.code]" clearable :placeholder="`选择${field.name}`" style="width: 100%">
              <el-option label="是" :value="true" />
              <el-option label="否" :value="false" />
            </el-select>
            <el-input-number
              v-else-if="field.field_type === 'integer'"
              v-model="ciForm.attributeValues[field.code]"
              :precision="0"
              controls-position="right"
              style="width: 100%"
            />
            <el-input-number
              v-else-if="field.field_type === 'decimal'"
              v-model="ciForm.attributeValues[field.code]"
              controls-position="right"
              style="width: 100%"
            />
            <el-date-picker
              v-else-if="field.field_type === 'date'"
              v-model="ciForm.attributeValues[field.code]"
              type="date"
              value-format="YYYY-MM-DD"
              :placeholder="`选择${field.name}`"
              style="width: 100%"
            />
            <el-date-picker
              v-else-if="field.field_type === 'datetime'"
              v-model="ciForm.attributeValues[field.code]"
              type="datetime"
              value-format="YYYY-MM-DDTHH:mm:ss"
              :placeholder="`选择${field.name}`"
              style="width: 100%"
            />
            <el-input
              v-else-if="field.field_type === 'json'"
              v-model="ciForm.attributeValues[field.code]"
              type="textarea"
              :rows="3"
              :placeholder="`${field.name} JSON`"
            />
            <el-input v-else v-model="ciForm.attributeValues[field.code]" :placeholder="`填写${field.name}`" />
            <div class="ci-form-field-meta">{{ field.code === 'access_address' ? '浏览器可访问地址' : ciFormFieldMetaText(field) }}</div>
          </el-form-item>
        </template>
      </el-form>
      <template #footer>
        <el-button @click="ciDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveConfigItem">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog top="5vh" :close-on-click-modal="false" class="workbench-edit-dialog" v-model="bulkLedgerDialogVisible" title="批量维护资源" width="760px" append-to-body destroy-on-close>
      <div class="request-action-card">
        <strong>已选择 {{ ledgerSelection.length }} 个资源</strong>
        <span>仅填写需要统一变更的字段，未填写字段会保持原值。</span>
      </div>
      <el-form label-position="top" :model="bulkLedgerForm" label-width="92px" class="workbench-editor-form--sectioned cmdb-form-grid bulk-ledger-form">
        <section class="workbench-editor-section">
          <div class="workbench-editor-heading"><span class="workbench-editor-step">01</span><h3>资源归属</h3></div>
          <div class="workbench-editor-grid">
            <el-form-item label="业务线">
              <el-select v-model="bulkLedgerForm.business_node" clearable filterable placeholder="不变更" style="width: 100%" @change="onBulkLedgerBusinessNodeChange">
                <el-option v-for="item in bulkLedgerBusinessNodeOptions" :key="item.id" :label="item.name" :value="item.id" />
              </el-select>
            </el-form-item>
            <el-form-item label="环境">
              <el-select
            v-model="bulkLedgerForm.environment_node"
            clearable
            filterable
            :disabled="!bulkLedgerForm.business_node || !bulkLedgerEnvironmentNodeOptions.length"
            :placeholder="bulkLedgerForm.business_node ? '请选择环境' : '请先选择业务线'"
            style="width: 100%"
            @change="onBulkLedgerEnvironmentNodeChange"
          >
                <el-option v-for="item in bulkLedgerEnvironmentNodeOptions" :key="item.id" :label="item.name" :value="item.id" />
              </el-select>
            </el-form-item>
            <el-form-item label="部门"><el-input v-model="bulkLedgerForm.department" placeholder="不填写则不变更" /></el-form-item>
            <el-form-item label="负责人"><el-input v-model="bulkLedgerForm.admin_user" placeholder="不填写则不变更" /></el-form-item>
          </div>
        </section>
        <section class="workbench-editor-section workbench-editor-section--tinted">
          <div class="workbench-editor-heading"><span class="workbench-editor-step">02</span><h3>标签与状态</h3></div>
          <div class="workbench-editor-grid">
            <el-form-item label="标签动作">
              <el-select v-model="bulkLedgerForm.tag_action" style="width: 100%">
                <el-option label="追加标签" value="append" />
                <el-option label="替换标签" value="replace" />
                <el-option label="移除标签" value="remove" />
              </el-select>
            </el-form-item>
            <el-form-item label="标签">
              <el-select v-model="bulkLedgerForm.tag_ids" multiple clearable filterable placeholder="选择标签" style="width: 100%">
                <el-option v-for="item in activeTagOptions" :key="item.id" :label="item.name" :value="item.id" />
              </el-select>
            </el-form-item>
            <el-form-item label="状态">
              <el-select v-model="bulkLedgerForm.status" clearable placeholder="不变更" style="width: 100%">
                <el-option label="使用中" value="active" />
                <el-option label="停机" value="stopped" />
                <el-option label="已下线" value="offline" />
              </el-select>
            </el-form-item>
            <el-form-item label="备注" class="workbench-editor-full span-2">
              <el-input v-model="bulkLedgerForm.note" type="textarea" :rows="2" maxlength="200" show-word-limit />
            </el-form-item>
          </div>
        </section>
      </el-form>
      <template #footer>
        <el-button @click="bulkLedgerDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveBulkLedgerUpdate">确认维护</el-button>
      </template>
    </el-dialog>

    <el-dialog top="5vh" :close-on-click-modal="false" class="workbench-edit-dialog" v-model="tagDialogVisible" :title="tagEditingId ? '编辑标签' : '新建标签'" width="560px" append-to-body destroy-on-close>
      <el-form label-position="top" :model="tagForm" label-width="84px" class="cmdb-form-grid">
        <el-form-item label="标签名称" required><el-input v-model="tagForm.name" /></el-form-item>
        <el-form-item label="标签分类">
          <el-select v-model="tagForm.category" clearable filterable allow-create placeholder="选择或输入分类" style="width: 100%">
            <el-option v-for="item in tagCategoryOptions" :key="item" :label="item" :value="item" />
          </el-select>
        </el-form-item>
        <el-form-item label="标签颜色">
          <el-color-picker v-model="tagForm.color" />
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="tagForm.is_active" />
        </el-form-item>
        <el-form-item label="描述" class="span-2"><el-input v-model="tagForm.description" type="textarea" :rows="3" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="tagDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveTag">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog top="5vh" :close-on-click-modal="false" class="workbench-edit-dialog" v-model="authorizationDialogVisible" :title="authorizationEditingId ? '编辑资源授权' : '新建资源授权'" width="720px" append-to-body destroy-on-close>
      <el-form label-position="top" :model="authorizationForm" label-width="96px" class="workbench-editor-form--sectioned cmdb-form-grid">
        <section class="workbench-editor-section">
          <div class="workbench-editor-heading"><span class="workbench-editor-step">01</span><h3>授权主体与权限</h3></div>
          <div class="workbench-editor-grid">
            <el-form-item label="授权名称" required><el-input v-model="authorizationForm.name" placeholder="例如 支付业务只读授权" /></el-form-item>
            <el-form-item label="主体类型" required>
              <el-select v-model="authorizationForm.principal_type" style="width: 100%">
                <el-option label="用户" value="user" />
                <el-option label="用户组" value="group" />
              </el-select>
            </el-form-item>
            <el-form-item label="授权主体" required><el-input v-model="authorizationForm.principal" placeholder="用户名或用户组编码" /></el-form-item>
            <el-form-item label="授权权限" required>
              <el-select v-model="authorizationForm.permission" style="width: 100%">
                <el-option label="查看" value="view" />
                <el-option label="管理" value="manage" />
              </el-select>
            </el-form-item>
          </div>
        </section>
        <section class="workbench-editor-section workbench-editor-section--tinted">
          <div class="workbench-editor-heading"><span class="workbench-editor-step">02</span><h3>资源范围与状态</h3></div>
          <div class="workbench-editor-grid">
            <el-form-item label="业务线">
              <el-select v-model="authorizationForm.business_line" clearable filterable allow-create placeholder="全部业务线" style="width: 100%">
                <el-option v-for="item in businessLineOptions" :key="item" :label="item" :value="item" />
              </el-select>
            </el-form-item>
            <el-form-item label="环境">
              <el-select v-model="authorizationForm.environment" clearable placeholder="全部环境" style="width: 100%">
                <el-option label="生产" value="prod" />
                <el-option label="测试" value="test" />
                <el-option label="开发" value="dev" />
              </el-select>
            </el-form-item>
            <el-form-item label="资源模型">
              <el-select v-model="authorizationForm.ci_type" clearable filterable placeholder="全部模型" style="width: 100%">
                <el-option v-for="item in ciTypes" :key="item.id" :label="item.name" :value="item.id" />
              </el-select>
            </el-form-item>
            <el-form-item label="启用"><el-switch v-model="authorizationForm.is_active" /></el-form-item>
            <el-form-item label="说明" class="workbench-editor-full span-2"><el-input v-model="authorizationForm.description" type="textarea" :rows="3" /></el-form-item>
          </div>
        </section>
      </el-form>
      <template #footer>
        <el-button @click="authorizationDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveAuthorization">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="bulkImportVisible" title="批量导入资产台账" width="760px" append-to-body destroy-on-close>
      <div class="bulk-import-shell">
        <div class="bulk-import-template-picker">
          <span>模板模型</span>
          <el-select v-model="bulkImportTemplateTypeIds" multiple collapse-tags collapse-tags-tooltip filterable placeholder="不选则下载通用模板" style="width: 360px">
            <el-option v-for="item in ciTypes" :key="item.id" :label="item.name" :value="String(item.id)" />
          </el-select>
          <small>{{ bulkImportTemplateTypeIds.length > 1 ? '多个模型会下载为 ZIP 模板包，每个模型单独一份 CSV。' : '选择模型后会包含该模型的常用字段。' }}</small>
        </div>
        <div class="bulk-import-guide">
          <span class="bulk-import-guide__step">1</span>
          <span>下载模板并填写数据</span>
          <el-button link type="primary" :loading="downloadingTemplate" @click="downloadImportTemplate">{{ bulkImportTemplateDownloadLabel }}</el-button>
          <span class="bulk-import-guide__divider">·</span>
          <span class="bulk-import-guide__step">2</span>
          <span>上传 CSV 或 JSON 文件</span>
        </div>
        <div class="bulk-import-upload">
          <input ref="bulkImportFileInput" type="file" accept=".csv,.json,text/csv,application/json" @change="handleBulkImportFileChange" />
          <el-button @click="bulkImportFileInput?.click()">
            <el-icon><UploadFilled /></el-icon>
            选择文件
          </el-button>
          <span>{{ bulkImportFileName || '未选择文件，也可直接粘贴内容' }}</span>
        </div>
        <div class="bulk-import-editor-head">
          <span>导入内容</span>
          <el-radio-group v-model="bulkImportForm.format" size="small" @change="resetBulkImportPreview">
            <el-radio-button label="csv">CSV</el-radio-button>
            <el-radio-button label="json">JSON</el-radio-button>
          </el-radio-group>
        </div>
        <el-input
          v-model="bulkImportForm.text"
          type="textarea"
          :rows="10"
          :placeholder="bulkImportPlaceholder"
          @input="resetBulkImportPreview"
        />
        <div class="bulk-import-tip">系统会先校验并展示新增、更新和冲突结果，确认无误后再导入。</div>
        <div v-if="bulkImportPreview.records.length" class="preview-summary-grid">
          <div v-for="item in bulkImportPreviewCards" :key="item.key" class="preview-summary-card" :class="item.tone">
            <span>{{ item.label }}</span>
            <strong>{{ item.value }}</strong>
          </div>
        </div>
        <el-table v-if="bulkImportPreview.records.length" :data="bulkImportPreview.records" stripe class="cmdb-table preview-table">
          <el-table-column prop="action" label="动作" width="100">
            <template #default="{ row }"><el-tag size="small" :type="syncActionTagType(row.action)">{{ syncActionText(row.action) }}</el-tag></template>
          </el-table-column>
          <el-table-column label="资源" min-width="160">
            <template #default="{ row }">{{ row.name || row.after?.name || row.source_unique_id || '-' }}</template>
          </el-table-column>
          <el-table-column label="来源 ID" min-width="160">
            <template #default="{ row }">{{ row.source_unique_id || row.after?.attributes?.source_unique_id || row.after?.source_unique_id || '-' }}</template>
          </el-table-column>
          <el-table-column label="说明" min-width="220" show-overflow-tooltip>
            <template #default="{ row }">{{ syncPreviewText(row) }}</template>
          </el-table-column>
        </el-table>
      </div>
      <template #footer>
        <el-button @click="bulkImportVisible = false">取消</el-button>
        <el-button :loading="bulkImportLoading" @click="previewBulkImport">校验并预览</el-button>
        <el-button type="primary" :loading="bulkImportLoading" :disabled="!hasCurrentBulkImportPreview" @click="commitBulkImport">确认导入</el-button>
      </template>
    </el-dialog>

    <el-dialog top="5vh" :close-on-click-modal="false" class="workbench-edit-dialog" v-model="cloudCredentialDialogVisible" :title="cloudCredentialDialogTitle" width="720px" append-to-body destroy-on-close>
      <el-form label-position="top" :model="cloudCredentialForm" label-width="136px" class="workbench-editor-form--sectioned cmdb-form-grid cmdb-form-grid--wide-label">
        <section class="workbench-editor-section">
          <div class="workbench-editor-heading"><span class="workbench-editor-step">01</span><h3>账号信息</h3></div>
          <div class="workbench-editor-grid">
            <el-form-item label="云厂商" required>
              <el-select v-model="cloudCredentialForm.provider" :disabled="!!cloudCredentialEditingId" style="width: 100%">
                <el-option v-for="item in activeCloudCredentialProviderOptions" :key="item.value" :label="item.label" :value="item.value" />
              </el-select>
            </el-form-item>
            <el-form-item label="认证方式">
              <el-select v-model="cloudCredentialForm.auth_mode" style="width: 100%">
                <el-option :label="cloudCredentialForm.provider === 'vsphere' ? '用户名 / 密码' : 'AK/SK'" :value="cloudCredentialForm.provider === 'vsphere' ? 'secret' : 'aksk'" />
                <el-option v-if="cloudCredentialForm.provider !== 'vsphere'" label="STS / AssumeRole" value="sts" />
              </el-select>
            </el-form-item>
            <el-form-item label="账号名称" required><el-input v-model="cloudCredentialForm.name" placeholder="例如 阿里云-生产主账号" /></el-form-item>
            <el-form-item v-if="cloudCredentialForm.provider === 'vsphere'" :label="cloudCredentialAccountIdLabel" required><el-input v-model="cloudCredentialForm.account_id" /></el-form-item>
            <el-form-item :label="cloudCredentialDefaultRegionLabel" required><el-input v-model="cloudCredentialForm.default_region" placeholder="例如 cn-hangzhou / cn-north-4 / private-cloud-prod" /></el-form-item>
            <el-form-item v-if="cloudCredentialForm.provider === 'vsphere'" label="版本" required>
              <el-select v-model="cloudCredentialForm.private_cloud_version" style="width: 100%">
                <el-option v-for="item in privateCloudVersionOptions" :key="item.value" :label="item.label" :value="item.value" />
              </el-select>
            </el-form-item>
          </div>
        </section>
        <section class="workbench-editor-section workbench-editor-section--tinted">
          <div class="workbench-editor-heading"><span class="workbench-editor-step">02</span><h3>认证与采集配置</h3></div>
          <div class="workbench-editor-grid">
            <el-form-item :label="cloudCredentialAccessIdLabel" required><el-input v-model="cloudCredentialForm.access_key_id" /></el-form-item>
            <el-form-item :label="cloudCredentialSecretLabel" :required="!cloudCredentialEditingId"><el-input v-model="cloudCredentialForm.access_key_secret" show-password :placeholder="cloudCredentialEditingId ? '留空表示不修改' : ''" /></el-form-item>
            <el-form-item v-if="cloudCredentialForm.provider === 'huawei'" label="Project ID" required>
              <el-input v-model="cloudCredentialForm.project_id" placeholder="必填，用于华为云 AK/SK API 认证" />
            </el-form-item>
            <el-form-item v-if="isPublicCloudCredentialForm" label="同步产品" class="span-2" required>
              <el-checkbox-group v-model="cloudCredentialForm.sync_product_keys" class="cloud-product-picker">
                <el-checkbox v-for="item in cloudCredentialProductOptions" :key="item.key" :label="item.key" border>
                  <span class="cloud-product-option">
                    <strong>{{ item.label }}</strong>
                    <small>{{ item.desc }}</small>
                  </span>
                </el-checkbox>
              </el-checkbox-group>
            </el-form-item>
            <div class="prometheus-metrics-panel span-2">
              <el-form-item label="Prometheus 指标" class="prometheus-metrics-panel__item">
                <div class="sync-switch-field">
                  <el-switch v-model="cloudCredentialForm.prometheus_metrics_enabled" />
                  <small>优先从 Prometheus 获取 CPU、内存和磁盘用量；无数据时回退云商或 vSphere 接口。</small>
                </div>
              </el-form-item>
              <el-form-item v-if="cloudCredentialForm.prometheus_metrics_enabled" label="Prometheus 数据源" class="prometheus-metrics-panel__item">
                <el-select
              v-model="cloudCredentialForm.metric_datasource_id"
              clearable
              filterable
              :loading="metricDatasourceLoading"
              placeholder="留空则使用平台默认数据源"
              style="width: 100%"
              @visible-change="visible => visible && fetchMetricDatasources()"
            >
                  <el-option v-for="item in cloudMetricDatasourceOptions" :key="item.id" :label="metricDatasourceOptionLabel(item)" :value="String(item.id)" />
                </el-select>
              </el-form-item>
            </div>
            <el-form-item v-if="cloudCredentialForm.auth_mode === 'sts'" label="Role ARN"><el-input v-model="cloudCredentialForm.role_arn" /></el-form-item>
            <el-form-item v-if="cloudCredentialForm.auth_mode === 'sts'" label="External ID"><el-input v-model="cloudCredentialForm.external_id" /></el-form-item>
          </div>
        </section>
        <section class="workbench-editor-section workbench-editor-section--tinted">
          <div class="workbench-editor-heading"><span class="workbench-editor-step">03</span><h3>管理信息</h3></div>
          <div class="workbench-editor-grid">
            <el-form-item label="说明" class="workbench-editor-full span-2 cloud-credential-description"><el-input v-model="cloudCredentialForm.description" type="textarea" :rows="2" :placeholder="cloudCredentialDescriptionPlaceholder" /></el-form-item>
            <el-form-item label="负责人"><el-input v-model="cloudCredentialForm.owner" /></el-form-item>
            <el-form-item label="启用"><el-switch v-model="cloudCredentialForm.is_enabled" /></el-form-item>
          </div>
        </section>
      </el-form>
      <template #footer>
        <el-button @click="cloudCredentialDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="cloudCredentialSaving" @click="saveCloudCredential">{{ cloudCredentialEditingId ? '保存修改' : '保存并自动拉取' }}</el-button>
      </template>
    </el-dialog>

    <el-dialog top="5vh" :close-on-click-modal="false" class="workbench-edit-dialog" v-model="syncJobDialogVisible" :title="syncJobEditingId ? '编辑同步任务' : '新建同步任务'" :width="isMinimalSyncJobForm ? '520px' : '680px'" append-to-body destroy-on-close>
      <el-form label-position="top" :model="syncJobForm" label-width="96px" class="cmdb-form-grid sync-job-minimal-form">
        <template v-if="isMinimalSyncJobForm">
          <el-form-item label="任务名称" required class="span-2"><el-input v-model="syncJobForm.name" /></el-form-item>
          <el-form-item label="自动同步"><el-switch v-model="syncJobForm.collection_enabled" /></el-form-item>
          <el-form-item v-if="syncJobForm.collection_enabled" label="同步间隔" required>
            <el-input-number v-model="syncJobForm.interval_minutes" :min="1" :step="30" controls-position="right" style="width: 100%" />
          </el-form-item>
          <el-form-item label="差异预览">
            <div class="sync-switch-field">
              <el-switch v-model="syncJobForm.dry_run" />
              <small>开启后默认只预演新增、更新、冲突，不写入资产台账。</small>
            </div>
          </el-form-item>
          <el-form-item label="全量对账">
            <div class="sync-switch-field">
              <el-switch v-model="syncJobForm.full_sync" />
              <small>开启后会检查历史已绑定但本次没采集到的资源，并标记来源缺失或待下线候选。</small>
            </div>
          </el-form-item>
        </template>
        <template v-else>
          <el-form-item label="任务名称" required><el-input v-model="syncJobForm.name" /></el-form-item>
          <el-form-item label="同步模板" required>
            <el-select v-model="syncJobForm.templateKey" clearable filterable placeholder="选择同步资源类型" style="width: 100%" @change="applySyncTemplate">
              <el-option v-for="item in phaseOneSyncTemplates" :key="item.key" :label="item.label" :value="item.key">
                <div class="sync-template-option">
                  <strong>{{ item.label }}</strong>
                  <span>{{ item.desc }}</span>
                </div>
              </el-option>
            </el-select>
          </el-form-item>
          <el-form-item label="来源类型" required><el-input v-model="syncJobForm.source_type" placeholder="aliyun_ecs / vsphere_vm" /></el-form-item>
          <el-form-item label="采集器">
            <el-select v-model="syncJobForm.connector" clearable placeholder="选择采集器" style="width: 100%">
              <el-option label="阿里云" value="aliyun" />
              <el-option label="华为云" value="huaweicloud" />
              <el-option label="vSphere / ESXi" value="vsphere" />
              <el-option label="手工导入" value="manual_import" />
            </el-select>
          </el-form-item>
          <template v-if="isCloudSyncJob">
            <el-form-item label="资源账号" :required="!isVsphereSyncJob" class="span-2">
              <el-select
                v-model="syncJobForm.cloud_account_id"
                filterable
                clearable
                :loading="cloudCredentialLoading"
                :placeholder="cloudCredentialPlaceholder"
                style="width: 100%"
                @visible-change="visible => visible && fetchCloudCredentials()"
              >
                <el-option
                  v-for="item in syncCloudCredentialOptions"
                  :key="item.id"
                  :label="cloudCredentialOptionLabel(item)"
                  :value="String(item.id)"
                >
                  <div class="sync-cloud-option">
                    <strong>{{ item.name }}</strong>
                    <span>{{ item.provider_label || item.provider }} / {{ item.account_name || item.account_id || '未填账号别名' }} / {{ item.default_region || '未填区域' }}</span>
                  </div>
                </el-option>
              </el-select>
            </el-form-item>
          </template>
          <template v-if="isVsphereSyncJob">
            <el-form-item v-if="!syncJobForm.cloud_account_id" label="连接地址" required><el-input v-model="syncJobForm.vsphere_host" placeholder="vCenter / ESXi 地址" /></el-form-item>
            <el-form-item v-if="!syncJobForm.cloud_account_id" label="登录账号" required><el-input v-model="syncJobForm.vsphere_username" placeholder="administrator@vsphere.local" /></el-form-item>
            <el-form-item v-if="!syncJobForm.cloud_account_id" label="凭据引用" class="span-2">
              <el-input v-model="syncJobForm.vsphere_auth_ref" placeholder="例如 SXDEVOPS_VSPHERE_PROD" />
            </el-form-item>
          </template>
          <el-form-item label="资源类型" required><el-input v-model="syncJobForm.resource_type" placeholder="ecs / rds / vm" /></el-form-item>
          <el-form-item label="资产分类" required>
            <el-select v-model="syncJobForm.target_ci_type_code" filterable allow-create default-first-option placeholder="选择或输入资产分类编码" style="width: 100%">
              <el-option v-for="item in syncJobTargetTypeOptions" :key="item.value" :label="`${item.label} / ${item.value}`" :value="item.value" />
            </el-select>
          </el-form-item>
          <el-form-item label="唯一标识" required><el-input v-model="syncJobForm.unique_key" placeholder="instance_id / provider" /></el-form-item>
          <el-form-item label="同步间隔" required>
            <el-input-number v-model="syncJobForm.interval_minutes" :min="1" :step="30" controls-position="right" style="width: 100%" />
          </el-form-item>
          <el-form-item label="执行模式">
            <el-select v-model="syncJobForm.mode" style="width: 100%">
              <el-option label="手动" value="manual" />
              <el-option label="定时" value="scheduled" />
              <el-option label="导入" value="import" />
            </el-select>
          </el-form-item>
          <el-form-item label="自动同步"><el-switch v-model="syncJobForm.collection_enabled" /></el-form-item>
          <el-form-item label="差异预览">
            <div class="sync-switch-field">
              <el-switch v-model="syncJobForm.dry_run" />
              <small>开启后默认只预演新增、更新、冲突，不写入资产台账。</small>
            </div>
          </el-form-item>
          <el-form-item label="全量对账">
            <div class="sync-switch-field">
              <el-switch v-model="syncJobForm.full_sync" />
              <small>开启后会检查历史已绑定但本次没采集到的资源，并标记来源缺失或待下线候选。</small>
            </div>
          </el-form-item>
        </template>
      </el-form>
      <template #footer>
        <el-button @click="syncJobDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveSyncJob">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog top="5vh" :close-on-click-modal="false" class="workbench-edit-dialog" v-model="sourceMappingDialogVisible" :title="sourceMappingEditingId ? '编辑来源映射' : '新增来源映射'" width="720px" append-to-body destroy-on-close>
      <el-form label-position="top" :model="sourceMappingForm" label-width="110px" class="workbench-editor-form--sectioned cmdb-form-grid">
        <section class="workbench-editor-section">
          <div class="workbench-editor-heading"><span class="workbench-editor-step">01</span><h3>资源与同步状态</h3></div>
          <div class="workbench-editor-grid">
            <el-form-item label="关联资源" required class="span-2">
              <el-select v-model="sourceMappingForm.ci" filterable placeholder="选择配置项" style="width: 100%">
                <el-option
              v-for="item in sourceMappingCiOptions"
              :key="item.id"
              :label="`${item.name} / ${item.ci_type_name || '-'}`"
              :value="item.id"
            />
              </el-select>
            </el-form-item>
            <el-form-item label="来源类型" required><el-input v-model="sourceMappingForm.source_type" placeholder="aliyun_ecs / idc / manual_import" /></el-form-item>
            <el-form-item label="同步状态">
              <el-select v-model="sourceMappingForm.sync_status" style="width: 100%">
                <el-option label="成功" value="success" />
                <el-option label="失败" value="failed" />
                <el-option label="来源缺失" value="missing" />
                <el-option label="冲突" value="conflict" />
              </el-select>
            </el-form-item>
          </div>
        </section>
        <section class="workbench-editor-section workbench-editor-section--tinted">
          <div class="workbench-editor-heading"><span class="workbench-editor-step">02</span><h3>来源标识与数据</h3></div>
          <div class="workbench-editor-grid">
            <el-form-item label="来源账号"><el-input v-model="sourceMappingForm.source_account" placeholder="账号、订阅或租户" /></el-form-item>
            <el-form-item label="来源地域"><el-input v-model="sourceMappingForm.source_region" placeholder="cn-shanghai / 华东一区" /></el-form-item>
            <el-form-item label="唯一标识" required class="span-2"><el-input v-model="sourceMappingForm.source_unique_id" placeholder="云实例 ID / 资产编号 / 外部系统 ID" /></el-form-item>
            <el-form-item label="原始数据" class="span-2">
              <el-input v-model="sourceMappingForm.rawPayloadText" type="textarea" :rows="6" placeholder="JSON 对象，可保存采集原始字段。" />
            </el-form-item>
          </div>
        </section>
      </el-form>
      <template #footer>
        <el-button @click="sourceMappingDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveSourceMapping">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="sourceMappingDetailVisible" title="来源映射详情" width="820px" append-to-body destroy-on-close>
      <div v-if="sourceMappingDetailRow" class="audit-detail-shell">
        <div class="request-detail-statusbar">
          <div>
            <span>关联资源</span>
            <strong>{{ sourceMappingDetailRow.ci_name || `CI#${sourceMappingDetailRow.ci || '-'}` }}</strong>
          </div>
          <div>
            <span>来源类型</span>
            <strong>{{ sourceMappingDetailRow.source_type || '-' }}</strong>
          </div>
          <div>
            <span>同步状态</span>
            <strong>{{ sourceMappingStatusText(sourceMappingDetailRow.sync_status) }}</strong>
          </div>
          <div>
            <span>最后发现</span>
            <strong>{{ formatTime(sourceMappingDetailRow.last_seen_at) }}</strong>
          </div>
        </div>

        <div class="detail-section">
          <div class="detail-section-head">
            <div class="detail-section-title">来源身份</div>
            <el-button v-if="sourceMappingDetailRow.ci" link type="primary" @click="openCiDetail({ id: sourceMappingDetailRow.ci, name: sourceMappingDetailRow.ci_name })">查看资源</el-button>
          </div>
          <div class="attribute-grid">
            <div class="attribute-item">
              <span>唯一标识</span>
              <strong>{{ sourceMappingDetailRow.source_unique_id || '-' }}</strong>
            </div>
            <div class="attribute-item">
              <span>账号</span>
              <strong>{{ sourceMappingDetailRow.source_account || '-' }}</strong>
            </div>
            <div class="attribute-item">
              <span>地域</span>
              <strong>{{ sourceMappingDetailRow.source_region || '-' }}</strong>
            </div>
            <div class="attribute-item">
              <span>更新时间</span>
              <strong>{{ formatTime(sourceMappingDetailRow.updated_at) }}</strong>
            </div>
          </div>
        </div>

        <div class="detail-section">
          <div class="detail-section-title">原始载荷</div>
          <pre>{{ formatAuditJson(sourceMappingDetailRow.raw_payload) }}</pre>
        </div>
      </div>
    </el-dialog>

    <el-dialog top="5vh" :close-on-click-modal="false" class="workbench-edit-dialog" v-model="modelDialogVisible" :title="modelEditingId ? '编辑模型' : '新建模型'" width="760px" append-to-body destroy-on-close>
      <el-alert
        v-if="!modelEditingId"
        class="model-dialog-tip"
        title="字段配置和关系规则请保存后再点对应分类卡片进行编辑。"
        type="info"
        :closable="false"
        show-icon
      />
      <el-form label-position="top" :model="modelForm" label-width="90px" class="cmdb-form-grid">
        <el-form-item label="模型名称" required><el-input v-model="modelForm.name" /></el-form-item>
        <el-form-item label="模型编码"><el-input v-model="modelForm.code" placeholder="CLOUD_SERVER" /></el-form-item>
        <el-form-item label="模型分组">
          <el-select v-model="modelForm.group" clearable filterable placeholder="选择分组" style="width: 100%">
            <el-option v-for="item in ciModelGroups" :key="item.id" :label="item.name" :value="item.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="当前图标">
          <div class="model-icon-current">
            <span class="model-icon-preview" :style="{ color: modelIconColor(modelForm.icon) }">
              <el-icon><component :is="modelIconComponent(modelForm.icon)" /></el-icon>
            </span>
            <span>{{ selectedModelIconLabel }}</span>
          </div>
        </el-form-item>
        <el-form-item label="模型图标" class="span-2">
          <div class="model-icon-picker">
            <button
              v-for="item in modelIconOptions"
              :key="item.value"
              type="button"
              class="model-icon-option"
              :class="{ active: modelForm.icon === item.value }"
              @click="selectModelIcon(item)"
            >
              <span :style="{ color: item.color }"><el-icon><component :is="item.component" /></el-icon></span>
              <strong>{{ item.label }}</strong>
            </button>
          </div>
        </el-form-item>
        <el-form-item label="描述" class="span-2"><el-input v-model="modelForm.description" type="textarea" :rows="2" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="modelDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveModel">保存</el-button>
      </template>
    </el-dialog>

    <el-drawer
      v-model="modelConfigDrawerVisible"
      :title="selectedModel ? `${selectedModel.name} 配置信息` : '资产分类配置信息'"
      size="920px"
      append-to-body
      destroy-on-close
      class="model-config-drawer"
    >
      <div v-if="selectedModel" class="model-config-drawer-body">
        <section class="model-config-overview">
          <span class="opsany-model-card-icon" :style="{ color: selectedModel.color || modelIconColor(selectedModel) }">
            <el-icon><component :is="modelIconComponent(selectedModel)" /></el-icon>
          </span>
          <div class="model-config-overview-main">
            <div class="model-config-overview-title">
              <strong>{{ selectedModel.name }}</strong>
              <el-tag size="small" :type="selectedModel.is_active === false ? 'warning' : 'success'">{{ selectedModel.is_active === false ? '停用' : '启用' }}</el-tag>
            </div>
            <span>{{ selectedModel.code || '-' }} / {{ selectedModel.group_name || '未分组' }}</span>
            <p>{{ selectedModel.description || '暂无模型说明' }}</p>
          </div>
          <div class="model-config-overview-actions">
            <el-button @click="openModelDialog(selectedModel)">
              <el-icon><Edit /></el-icon>
              编辑基础信息
            </el-button>
          </div>
        </section>

        <div class="model-config-stat-grid">
          <div v-for="item in selectedModelStats" :key="item.key" class="model-detail-stat">
            <span>{{ item.label }}</span>
            <strong>{{ item.value }}</strong>
          </div>
        </div>

        <section class="model-config-section">
          <div class="model-config-section-head">
            <div>
              <strong>字段配置</strong>
              <span>“台账展示”决定资产台账属性栏的内容，按排序展示前 3 项。</span>
            </div>
            <el-button v-if="canManageModel" type="primary" size="small" @click="openFieldDialog()">
              <el-icon><Plus /></el-icon>
              新增字段
            </el-button>
          </div>
          <el-table :data="filteredModelFields" stripe class="cmdb-table model-config-table" max-height="420">
            <el-table-column label="字段" min-width="180">
              <template #default="{ row }">
                <div class="stack-cell">
                  <span>{{ row.name }}</span>
                  <div class="sub-text">{{ row.code }}</div>
                </div>
              </template>
            </el-table-column>
            <el-table-column label="类型 / 分组" min-width="150">
              <template #default="{ row }">
                <div class="stack-cell">
                  <span>{{ fieldTypeLabel(row.field_type) }}</span>
                  <div class="sub-text">{{ row.field_group || '未分组' }}</div>
                </div>
              </template>
            </el-table-column>
            <el-table-column label="数据要求" min-width="160">
              <template #default="{ row }">
                <div class="model-config-tags">
                  <el-tag size="small" :type="row.required ? 'danger' : 'info'">{{ row.required ? '必填' : '可选' }}</el-tag>
                  <el-tag v-if="row.unique" size="small" type="warning">唯一</el-tag>
                </div>
              </template>
            </el-table-column>
            <el-table-column label="台账展示" min-width="185">
              <template #default="{ row }">
                <div class="stack-cell">
                  <el-tag size="small" :type="row.is_display === false ? 'info' : 'success'">{{ row.is_display === false ? '不在属性栏显示' : '在属性栏显示' }}</el-tag>
                  <div class="sub-text">展示排序 {{ row.sort_order ?? 0 }} · {{ fieldSyncModeLabel(row.sync_mode) }}</div>
                </div>
              </template>
            </el-table-column>
            <el-table-column label="默认值" min-width="180" show-overflow-tooltip>
              <template #default="{ row }">
                <div class="field-rule-list">
                  <span v-if="fieldDefaultText(row)">默认：{{ fieldDefaultText(row) }}</span>
                  <span v-else class="sub-text">无默认值</span>
                </div>
              </template>
            </el-table-column>
            <el-table-column label="状态" width="92">
              <template #default="{ row }"><el-tag size="small" :type="row.is_active === false ? 'info' : 'success'">{{ row.is_active === false ? '停用' : '启用' }}</el-tag></template>
            </el-table-column>
            <el-table-column v-if="canManageModel" label="操作" width="150" fixed="right">
              <template #default="{ row }">
                <el-button link type="primary" @click="openFieldDialog(row)">编辑</el-button>
                <el-button link type="danger" @click="deleteFieldRow(row)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
        </section>

        <section class="model-config-section">
          <div class="model-config-section-head">
            <div>
              <strong>关系规则</strong>
              <span>维护该分类与其他资产分类之间的承载、依赖、包含等关系。</span>
            </div>
            <el-button v-if="canManageModel" type="primary" size="small" @click="openRelationRuleDialog()">
              <el-icon><Plus /></el-icon>
              新增关系
            </el-button>
          </div>
          <el-table :data="filteredRelationRules" stripe class="cmdb-table model-config-table" max-height="280">
            <el-table-column label="关系" min-width="260">
              <template #default="{ row }">
                <div class="stack-cell">
                  <span>{{ row.source_type_name || modelName(row.source_type) }} → {{ row.target_type_name || modelName(row.target_type) }}</span>
                  <div class="sub-text">{{ row.description || '暂无说明' }}</div>
                </div>
              </template>
            </el-table-column>
            <el-table-column label="类型" width="110">
              <template #default="{ row }">{{ relationTypeLabel(row.relation_type) }}</template>
            </el-table-column>
            <el-table-column label="约束" width="150">
              <template #default="{ row }">
                <div class="model-config-tags">
                  <el-tag size="small" :type="row.required ? 'danger' : 'info'">{{ row.required ? '必填' : '可选' }}</el-tag>
                  <el-tag size="small" type="info">{{ row.multiple === false ? '单目标' : '多目标' }}</el-tag>
                </div>
              </template>
            </el-table-column>
            <el-table-column label="状态" width="92">
              <template #default="{ row }"><el-tag size="small" :type="row.is_active === false ? 'info' : 'success'">{{ row.is_active === false ? '停用' : '启用' }}</el-tag></template>
            </el-table-column>
            <el-table-column v-if="canManageModel" label="操作" width="150" fixed="right">
              <template #default="{ row }">
                <el-button link type="primary" @click="openRelationRuleDialog(row)">编辑</el-button>
                <el-button link type="danger" @click="deleteRelationRuleRow(row)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
        </section>

      </div>
      <el-empty v-else description="请选择资产分类" :image-size="72" />
    </el-drawer>

    <el-dialog top="5vh" :close-on-click-modal="false" class="workbench-edit-dialog" v-model="modelGroupDialogVisible" :title="modelGroupEditingId ? '编辑模型分组' : '新建模型分组'" width="620px" append-to-body destroy-on-close>
      <el-form label-position="top" :model="modelGroupForm" label-width="92px" class="cmdb-form-grid">
        <el-form-item label="分组名称" required><el-input v-model="modelGroupForm.name" placeholder="例如 计算资源" /></el-form-item>
        <el-form-item label="分组编码" required><el-input v-model="modelGroupForm.code" placeholder="compute" /></el-form-item>
        <el-form-item label="排序"><el-input-number v-model="modelGroupForm.sort_order" :min="0" :max="9999" /></el-form-item>
        <el-form-item label="启用"><el-switch v-model="modelGroupForm.is_active" /></el-form-item>
        <el-form-item label="说明" class="span-2">
          <el-input v-model="modelGroupForm.description" type="textarea" :rows="2" placeholder="用于描述该分组下的资源模型范围" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="modelGroupDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveModelGroup">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog top="5vh" :close-on-click-modal="false" class="workbench-edit-dialog" v-model="fieldDialogVisible" :title="fieldEditingId ? '编辑模型字段' : '新建模型字段'" width="720px" append-to-body destroy-on-close>
      <el-form label-position="top" :model="fieldForm" label-width="92px" class="workbench-editor-form--sectioned cmdb-form-grid">
        <section class="workbench-editor-section">
          <div class="workbench-editor-heading"><span class="workbench-editor-step">01</span><h3>字段定义</h3></div>
          <div class="workbench-editor-grid">
            <el-form-item label="所属模型" required>
              <el-select v-model="fieldForm.ci_type" filterable placeholder="选择模型" style="width: 100%">
                <el-option v-for="item in ciTypes" :key="item.id" :label="item.name" :value="item.id" />
              </el-select>
            </el-form-item>
            <el-form-item label="字段名称" required><el-input v-model="fieldForm.name" /></el-form-item>
            <el-form-item label="字段编码" required><el-input v-model="fieldForm.code" placeholder="private_ip" /></el-form-item>
            <el-form-item label="字段类型">
              <el-select v-model="fieldForm.field_type" style="width: 100%" @change="onFieldTypeChange">
                <el-option label="字符串" value="string" />
                <el-option label="整数" value="integer" />
                <el-option label="小数" value="decimal" />
                <el-option label="布尔" value="boolean" />
                <el-option label="日期" value="date" />
                <el-option label="日期时间" value="datetime" />
                <el-option label="单选枚举" value="enum" />
                <el-option label="多选枚举" value="multi_enum" />
                <el-option label="IP 地址" value="ip" />
                <el-option label="URL" value="url" />
                <el-option label="JSON" value="json" />
              </el-select>
            </el-form-item>
            <el-form-item v-if="isEnumFieldType(fieldForm.field_type)" label="枚举选项" class="span-2">
              <div class="field-options-editor">
                <div v-for="(option, index) in fieldForm.options" :key="`field-option-${index}`" class="field-option-row">
                  <el-input v-model="option.label" placeholder="填写选项名称，如 虚拟机" />
                  <el-button text type="danger" :disabled="fieldForm.options.length <= 1" @click="removeFieldOption(index)">删除</el-button>
                </div>
                <div class="field-options-actions">
                  <el-button size="small" @click="addFieldOption"><el-icon><Plus /></el-icon>新增选项</el-button>
                </div>
              </div>
            </el-form-item>
          </div>
        </section>
        <section class="workbench-editor-section workbench-editor-section--tinted">
          <div class="workbench-editor-heading"><span class="workbench-editor-step">02</span><h3>同步与展示</h3></div>
          <div class="workbench-editor-grid">
            <el-form-item label="字段分组"><el-input v-model="fieldForm.field_group" placeholder="基础信息 / 资源规格 / 费用信息" /></el-form-item>
            <el-form-item label="排序"><el-input-number v-model="fieldForm.sort_order" :min="0" :max="9999" /></el-form-item>
            <el-form-item label="同步方式">
              <el-select v-model="fieldForm.sync_mode" style="width: 100%">
                <el-option label="来源优先" value="source" />
                <el-option label="人工优先" value="manual" />
              </el-select>
            </el-form-item>
            <el-form-item label="数据要求" class="span-2">
              <div class="field-setting-panel">
                <div class="switch-row">
                  <el-tooltip content="新建或编辑资产时必须填写该字段。" placement="top">
                    <el-checkbox v-model="fieldForm.required">必填</el-checkbox>
                  </el-tooltip>
                  <el-tooltip content="同一资产分类下，该字段的值不能重复。" placement="top">
                    <el-checkbox v-model="fieldForm.unique">唯一值</el-checkbox>
                  </el-tooltip>
                </div>
                <small>仅保留会影响数据校验的设置。</small>
              </div>
            </el-form-item>
            <el-form-item label="台账展示" class="span-2">
              <div class="field-setting-panel">
                <el-checkbox v-model="fieldForm.is_display">在资产台账属性栏显示</el-checkbox>
                <small>资产台账按字段排序显示前 3 项；取消后仍可在资产详情中查看。</small>
              </div>
            </el-form-item>
          </div>
        </section>
      </el-form>
      <template #footer>
        <el-button @click="fieldDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveField">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog top="5vh" :close-on-click-modal="false" class="workbench-edit-dialog" v-model="relationRuleDialogVisible" :title="relationRuleEditingId ? '编辑关系规则' : '新建关系规则'" width="680px" append-to-body destroy-on-close>
      <el-form label-position="top" :model="relationRuleForm" label-width="96px" class="workbench-editor-form--sectioned cmdb-form-grid">
        <section class="workbench-editor-section">
          <div class="workbench-editor-heading"><span class="workbench-editor-step">01</span><h3>模型与关系</h3></div>
          <div class="workbench-editor-grid">
            <el-form-item label="源模型" required>
              <el-select v-model="relationRuleForm.source_type" filterable placeholder="选择源模型" style="width: 100%">
                <el-option v-for="item in ciTypes" :key="item.id" :label="item.name" :value="item.id" />
              </el-select>
            </el-form-item>
            <el-form-item label="目标模型" required>
              <el-select v-model="relationRuleForm.target_type" filterable placeholder="选择目标模型" style="width: 100%">
                <el-option v-for="item in ciTypes" :key="item.id" :label="item.name" :value="item.id" />
              </el-select>
            </el-form-item>
            <el-form-item label="关系类型" required>
              <el-select v-model="relationRuleForm.relation_type" filterable allow-create style="width: 100%">
                <el-option v-for="item in baseRelationTypeOptions" :key="item.value" :label="item.label" :value="item.value" />
              </el-select>
            </el-form-item>
            <el-form-item label="方向">
              <el-select v-model="relationRuleForm.direction" style="width: 100%">
                <el-option label="源模型 -> 目标模型" value="outgoing" />
                <el-option label="目标模型 -> 源模型" value="incoming" />
              </el-select>
            </el-form-item>
          </div>
        </section>
        <section class="workbench-editor-section workbench-editor-section--tinted">
          <div class="workbench-editor-heading"><span class="workbench-editor-step">02</span><h3>约束与说明</h3></div>
          <div>
            <el-form-item label="规则约束" class="span-2">
              <div class="switch-row">
                <el-checkbox v-model="relationRuleForm.required">必填关系</el-checkbox>
                <el-checkbox v-model="relationRuleForm.multiple">允许多个目标</el-checkbox>
                <el-checkbox v-model="relationRuleForm.is_active">启用规则</el-checkbox>
              </div>
            </el-form-item>
            <el-form-item label="说明" class="workbench-editor-full span-2">
              <el-input v-model="relationRuleForm.description" type="textarea" :rows="2" placeholder="例如 应用必须运行在至少一台主机或集群上" />
            </el-form-item>
          </div>
        </section>
      </el-form>
      <template #footer>
        <el-button @click="relationRuleDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveRelationRule">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="syncPreviewVisible" title="同步差异预览" width="760px" append-to-body destroy-on-close>
      <div class="preview-summary-grid">
        <div v-for="item in syncPreviewCards" :key="item.key" class="preview-summary-card" :class="item.tone">
          <span>{{ item.label }}</span>
          <strong>{{ item.value }}</strong>
        </div>
      </div>
      <el-table :data="syncPreviewRecords" stripe class="cmdb-table preview-table">
        <el-table-column prop="action" label="动作" width="100">
          <template #default="{ row }"><el-tag size="small" :type="syncActionTagType(row.action)">{{ syncActionText(row.action) }}</el-tag></template>
        </el-table-column>
        <el-table-column label="资源" min-width="160">
          <template #default="{ row }">{{ row.name || row.after?.name || row.source_unique_id || '-' }}</template>
        </el-table-column>
        <el-table-column label="来源 ID" min-width="160">
          <template #default="{ row }">{{ row.source_unique_id || row.after?.source_unique_id || '-' }}</template>
        </el-table-column>
        <el-table-column label="说明" min-width="220" show-overflow-tooltip>
          <template #default="{ row }">{{ syncPreviewText(row) }}</template>
        </el-table-column>
      </el-table>
      <el-empty v-if="!syncPreviewRecords.length" description="暂无差异" :image-size="72" />
    </el-dialog>

    <el-dialog top="5vh" :close-on-click-modal="false" class="workbench-edit-dialog" v-model="syncRuntimeVisible" :title="syncRuntimeTitle" width="560px" append-to-body destroy-on-close @closed="resetSyncRuntimeForm">
      <div class="runtime-secret-shell">
        <div v-if="syncRuntimeRow" class="request-action-card">
          <strong>{{ syncRuntimeRow.name }}</strong>
          <span>{{ syncRuntimeRow.source_type || '-' }} / {{ syncRuntimeRow.config?.host || syncRuntimeRow.config?.source_account || '-' }}</span>
          <span>密码仅用于本次{{ syncRuntimeAction === 'dry_run' ? '预览' : '执行' }}，不会保存到同步任务配置。</span>
        </div>
        <el-form label-position="top" :model="syncRuntimeForm" label-width="92px" class="cmdb-form-grid">
          <el-form-item label="vCenter 密码" class="span-2" required>
            <el-input
              v-model="syncRuntimeForm.password"
              type="password"
              show-password
              autocomplete="new-password"
              placeholder="输入本次采集使用的 vSphere 密码"
              @keyup.enter="confirmSyncRuntime"
            />
          </el-form-item>
        </el-form>
        <div class="runtime-secret-hint">也可以在后端运行环境设置 {{ syncRuntimeAuthRef }}_PASSWORD，这样定时采集无需手工输入。</div>
      </div>
      <template #footer>
        <el-button @click="syncRuntimeVisible = false">取消</el-button>
        <el-button type="primary" :loading="syncRuntimeSubmitting" @click="confirmSyncRuntime">
          {{ syncRuntimeAction === 'dry_run' ? '开始预览' : '开始执行' }}
        </el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="syncRecordsVisible" :title="syncRecordsTitle" width="960px" append-to-body destroy-on-close @closed="syncRecordBatchDetail = null">
      <div class="preview-summary-grid sync-record-summary-grid">
        <button
          v-for="item in syncRecordSummaryCards"
          :key="item.key"
          type="button"
          class="preview-summary-card preview-summary-card--action"
          :class="[item.tone, { active: syncRecordStatusFilter === item.key }]"
          @click="selectSyncRecordStatus(item.key)"
        >
          <span>{{ item.label }}</span>
          <strong>{{ item.value }}</strong>
        </button>
      </div>
      <div v-if="syncRecordBatchDetail" class="sync-record-batch-head">
        <el-button link type="primary" @click="syncRecordBatchDetail = null">返回批次</el-button>
        <span>{{ syncRecordBatchDetail.label }} · {{ formatTime(syncRecordBatchDetail.latestAt) }}</span>
      </div>
      <el-table v-if="!syncRecordBatchDetail" v-loading="syncRecordsLoading" :data="syncRecordBatchRows" stripe class="cmdb-table sync-record-table">
        <el-table-column label="同步批次" min-width="220">
          <template #default="{ row }">
            <div class="sync-record-subject">
              <strong>{{ row.label }}</strong>
              <span>{{ row.legacy ? '历史同步记录' : `批次 ID · ${row.batchId.slice(-8)}` }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="同步结果" min-width="220">
          <template #default="{ row }">
            <div class="stack-cell">
              <el-tag size="small" :type="syncRecordStatusTagType(row.status)">{{ syncRecordStatusText(row.status) }}</el-tag>
              <div class="sub-text">{{ syncRecordBatchSummaryText(row) }}</div>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="资产项" width="108" align="right">
          <template #default="{ row }">{{ row.assetCount }}</template>
        </el-table-column>
        <el-table-column label="最近时间" width="170">
          <template #default="{ row }">{{ formatTime(row.latestAt) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="108" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openSyncRecordBatch(row)">查看详情</el-button>
          </template>
        </el-table-column>
        <template #empty>
          <el-empty description="暂无同步批次" :image-size="72" />
        </template>
      </el-table>
      <el-table v-else v-loading="syncRecordsLoading" :data="syncRecordBatchDetailRows" stripe class="cmdb-table sync-record-table">
        <el-table-column label="来源对象" min-width="230" show-overflow-tooltip>
          <template #default="{ row }">
            <div class="sync-record-subject">
              <strong>{{ syncRecordSubjectTitle(row) }}</strong>
              <span v-if="syncRecordSubjectMeta(row)">{{ syncRecordSubjectMeta(row) }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="结果 / 处理" width="132">
          <template #default="{ row }">
            <div class="stack-cell">
              <el-tag size="small" :type="syncRecordStatusTagType(row.status)">{{ syncRecordStatusText(row.status) }}</el-tag>
              <div class="sub-text">{{ syncRecordRetrySummary(row) }}</div>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="失败原因" min-width="300" show-overflow-tooltip>
          <template #default="{ row }">{{ syncFailureMessage(row.error_message) || syncRecordFallbackMessage(row) }}</template>
        </el-table-column>
        <el-table-column label="时间" width="158">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="142" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openSyncRecordDetail(row)">详情</el-button>
            <el-button v-if="canManageSync && row.status === 'failed'" link type="warning" @click="retrySyncRecordRow(row)">重试</el-button>
            <el-button v-if="canManageSync && canResolveSyncRecord(row)" link type="primary" @click="openSyncResolveDialog(row)">绑定</el-button>
          </template>
        </el-table-column>
        <template #empty>
          <el-empty description="暂无匹配记录" :image-size="72" />
        </template>
      </el-table>
    </el-dialog>

    <el-dialog v-model="syncRecordDetailVisible" title="同步记录详情" width="860px" append-to-body destroy-on-close>
      <div v-if="syncRecordDetailRow" class="audit-detail-shell">
        <div class="request-detail-statusbar">
          <div>
            <span>动作</span>
            <strong>{{ syncActionText(syncRecordDetailRow.action) }}</strong>
          </div>
          <div>
            <span>状态</span>
            <strong>{{ syncRecordStatusText(syncRecordDetailRow.status) }}</strong>
          </div>
          <div>
            <span>来源 ID</span>
            <strong>{{ syncRecordDetailRow.source_unique_id || '-' }}</strong>
          </div>
          <div>
            <span>时间</span>
            <strong>{{ formatTime(syncRecordDetailRow.created_at) }}</strong>
          </div>
        </div>

        <div class="detail-section">
          <div class="detail-section-head">
            <div class="detail-section-title">同步上下文</div>
            <el-button v-if="syncRecordDetailRow.ci" link type="primary" @click="openCiDetail({ id: syncRecordDetailRow.ci, name: syncRecordDetailRow.ci_name })">查看资源</el-button>
          </div>
          <div class="attribute-grid">
            <div class="attribute-item">
              <span>配置项</span>
              <strong>{{ syncRecordDetailRow.ci_name || `CI#${syncRecordDetailRow.ci || '-'}` }}</strong>
            </div>
            <div class="attribute-item">
              <span>同步任务</span>
              <strong>{{ syncRecordDetailRow.job_name || `#${syncRecordDetailRow.job || '-'}` }}</strong>
            </div>
            <div class="attribute-item">
              <span>重试状态</span>
              <strong>{{ retryStatusText(syncRecordDetailRow.retry_status) }}</strong>
            </div>
            <div class="attribute-item">
              <span>重试次数</span>
              <strong>{{ syncRecordDetailRow.retry_count || 0 }}</strong>
            </div>
          </div>
          <div v-if="syncRecordDetailRow.error_message" class="request-detail-note">{{ syncFailureMessage(syncRecordDetailRow.error_message) }}</div>
        </div>

        <div v-if="syncRecordDetailRow.relation_issue" class="detail-section">
          <div class="detail-section-head">
            <div class="detail-section-title">自动关系治理</div>
            <el-tag size="small" :type="syncRelationIssues.length ? 'warning' : 'success'">
              {{ syncRelationIssues.length ? `${syncRelationIssues.length} 项待处理` : '已处理' }}
            </el-tag>
          </div>
          <div v-loading="syncRelationIssueLoading" class="sync-relation-issue-list">
            <template v-if="syncRelationIssues.length">
              <div v-for="issue in syncRelationIssues" :key="syncRelationIssueKey(issue)" class="sync-relation-issue-card">
                <div class="relation-suggestion-rule">
                  <strong>{{ relationTypeLabel(issue.relation_type) }}</strong>
                  <span>{{ issue.direction === 'incoming' ? '来自' : '指向' }} {{ issue.peer_type_name || '-' }}</span>
                  <el-tag size="small" type="info">{{ syncRelationIssueReasonText(issue.reason) }}</el-tag>
                </div>
                <div v-if="issue.candidates?.length" class="relation-suggestion-list">
                  <div v-for="candidate in issue.candidates" :key="`${syncRelationIssueKey(issue)}-${candidate.id}`" class="relation-suggestion-item sync-relation-candidate">
                    <button type="button" class="relation-suggestion-main" @click="openCiDetail({ id: candidate.id })">
                      <strong>{{ candidate.name }}</strong>
                      <span>{{ relationCandidateText(candidate) }}</span>
                    </button>
                    <el-tag v-if="candidate.score !== undefined" size="small" type="success">{{ candidate.score }}分</el-tag>
                    <el-button
                      v-if="canManageSync"
                      link
                      type="primary"
                      :loading="syncRelationResolvingKey === `${syncRelationIssueKey(issue)}-${candidate.id}`"
                      @click.stop="resolveSyncRelationIssue(issue, candidate)"
                    >
                      关联
                    </el-button>
                  </div>
                </div>
                <el-empty v-else description="暂无候选资源" :image-size="52" />
              </div>
            </template>
            <el-empty v-else description="暂无待处理关系失败项" :image-size="58" />
          </div>
        </div>

        <div class="detail-section">
          <div class="detail-section-head">
            <div class="detail-section-title">字段差异</div>
            <el-tag size="small" type="info">{{ syncRecordDetailFields.length }} 项</el-tag>
          </div>
          <el-table v-if="syncRecordDetailFields.length" :data="syncRecordDetailFields" stripe class="cmdb-table detail-table">
            <el-table-column label="字段" width="160">
              <template #default="{ row }">{{ row.field }}</template>
            </el-table-column>
            <el-table-column label="同步前" min-width="220" show-overflow-tooltip>
              <template #default="{ row }">{{ formatAuditValue(row.before) }}</template>
            </el-table-column>
            <el-table-column label="同步后" min-width="220" show-overflow-tooltip>
              <template #default="{ row }">{{ formatAuditValue(row.after) }}</template>
            </el-table-column>
          </el-table>
          <el-empty v-else description="暂无字段级差异" :image-size="58" />
        </div>

        <div class="audit-raw-grid">
          <div class="detail-section">
            <div class="detail-section-title">同步前快照</div>
            <pre>{{ formatAuditJson(syncRecordDetailRow.before) }}</pre>
          </div>
          <div class="detail-section">
            <div class="detail-section-title">同步后快照</div>
            <pre>{{ formatAuditJson(syncRecordDetailRow.after) }}</pre>
          </div>
        </div>
      </div>
    </el-dialog>

    <el-dialog top="5vh" :close-on-click-modal="false" class="workbench-edit-dialog" v-model="syncResolveVisible" title="绑定同步来源" width="680px" append-to-body destroy-on-close>
      <div v-if="syncResolveRecord" class="sync-resolve-shell">
        <div class="request-action-card">
          <strong>{{ syncResolveRecord.after?.name || syncResolveRecord.ci_name || syncResolveRecord.source_unique_id || '-' }}</strong>
          <span>{{ syncResolveRecord.job_name || `#${syncResolveRecord.job}` }} / {{ syncResolveRecord.job_source_type || syncResolveRecord.after?.source_type || '-' }}</span>
          <span>{{ syncResolveRecord.error_message || '请确认来源唯一标识应绑定到哪个配置项。' }}</span>
        </div>
        <el-form label-position="top" :model="syncResolveForm" label-width="108px" class="cmdb-form-grid">
          <el-form-item label="目标配置项" class="span-2" required>
            <el-select v-model="syncResolveForm.ci_id" filterable placeholder="搜索并选择要绑定的配置项" style="width: 100%">
              <el-option
                v-for="item in syncResolveCiOptions"
                :key="item.id"
                :label="`${item.name} / ${item.ci_type_name || modelName(item.ci_type)} / ${item.business_line || '-'}`"
                :value="item.id"
              />
            </el-select>
          </el-form-item>
          <el-form-item label="来源 ID">
            <el-input :model-value="syncResolveSourceIdentity(syncResolveRecord)" disabled />
          </el-form-item>
          <el-form-item label="来源范围">
            <el-input :model-value="syncResolveSourceScope(syncResolveRecord)" disabled />
          </el-form-item>
          <el-form-item label="替换旧标识">
            <el-switch v-model="syncResolveForm.replace_existing" />
          </el-form-item>
          <el-form-item label="改绑来源">
            <el-switch v-model="syncResolveForm.rebind" />
          </el-form-item>
          <el-form-item label="处理说明" class="span-2">
            <el-input v-model="syncResolveForm.note" type="textarea" :rows="3" placeholder="例如：人工确认该来源 ID 属于当前配置项" />
          </el-form-item>
        </el-form>
      </div>
      <template #footer>
        <el-button @click="syncResolveVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submitSyncResolve">确认绑定</el-button>
      </template>
    </el-dialog>

    <el-drawer v-model="requestDetailVisible" :title="requestDetailRow?.title || '资源申请详情'" size="720px" append-to-body destroy-on-close>
      <div v-loading="requestDetailLoading" class="ci-detail-shell request-detail-shell">
        <template v-if="requestDetailRow">
          <div class="detail-heading">
            <div class="detail-heading-main">
              <div class="detail-title-row">
                <strong class="detail-main-title">{{ requestDetailRow.title }}</strong>
                <el-tag size="small" :type="requestStatusTagType(requestDetailRow.status)">{{ requestDetailRow.status_display || requestStatusText(requestDetailRow.status) }}</el-tag>
                <el-tag size="small" :type="requestPriorityTagType(requestDetailRow.priority)">{{ requestPriorityText(requestDetailRow.priority) }}</el-tag>
              </div>
              <div class="detail-subline">
                <span>{{ requestDetailRow.resource_type }} / {{ requestDetailRow.specification || '-' }} / {{ requestDetailRow.quantity || 1 }} 台</span>
                <span>{{ requestDetailRow.business_line || '未设置业务线' }}</span>
                <span>{{ requestDetailRow.environment_display || environmentText(requestDetailRow.environment) }}</span>
                <span>{{ requestDetailRow.applicant || '-' }}</span>
              </div>
            </div>
            <div v-if="canApproveRequest || canExecuteRequest" class="detail-heading-actions">
              <el-button v-if="canApproveRequest && requestDetailRow.status === 'pending'" size="small" type="primary" @click="openRequestAction(requestDetailRow, 'approve')">批准</el-button>
              <el-button v-if="canApproveRequest && requestDetailRow.status === 'pending'" size="small" type="danger" plain @click="openRequestAction(requestDetailRow, 'reject')">驳回</el-button>
              <el-button v-if="canExecuteRequest && requestDetailRow.status === 'approved' && requestDetailRow.delivery_mode === 'cloud'" size="small" type="success" @click="openRequestAction(requestDetailRow, 'provision')">自动交付</el-button>
              <el-button v-if="canExecuteRequest && requestDetailRow.status === 'failed' && requestDetailRow.delivery_mode === 'cloud'" size="small" type="danger" @click="openRequestAction(requestDetailRow, 'provision')">重试交付</el-button>
              <el-button v-if="canApproveRequest && requestDetailRow.status === 'approved' && requestDetailRow.delivery_mode !== 'cloud'" size="small" type="success" @click="openRequestAction(requestDetailRow, 'complete')">人工交付</el-button>
            </div>
          </div>

          <el-alert
            v-if="requestDetailRow.provisioning?.error"
            type="error"
            :closable="false"
            show-icon
            :title="`自动交付失败：${requestDetailRow.provisioning.error}`"
          />

          <div class="request-detail-statusbar">
            <div>
              <span>申请人</span>
              <strong>{{ requestDetailRow.applicant || '-' }}</strong>
            </div>
            <div>
              <span>审批人</span>
              <strong>{{ requestDetailRow.approver || '-' }}</strong>
            </div>
            <div>
              <span>审批时间</span>
              <strong>{{ formatTime(requestDetailRow.approved_at) }}</strong>
            </div>
            <div>
              <span>交付时间</span>
              <strong>{{ formatTime(requestDetailRow.completed_at) }}</strong>
            </div>
          </div>

          <div class="detail-grid">
            <div class="detail-section">
              <div class="detail-section-title">申请说明</div>
              <div class="request-detail-note">{{ requestDetailRow.reason || '-' }}</div>
              <div class="compact-stack">
                <div class="detail-kv">创建时间：{{ formatTime(requestDetailRow.created_at) }}</div>
                <div class="detail-kv">更新时间：{{ formatTime(requestDetailRow.updated_at) }}</div>
                <div class="detail-kv">资源类型：{{ requestDetailRow.resource_type || '-' }}</div>
                <div class="detail-kv">申请数量：{{ requestDetailRow.quantity || 1 }} 台</div>
              </div>
            </div>

            <div class="detail-section">
              <div class="detail-section-title">审批与交付说明</div>
              <div class="request-note-list">
                <div>
                  <span>审批意见</span>
                  <strong>{{ requestDetailRow.approval_comment || '-' }}</strong>
                </div>
                <div>
                  <span>交付说明</span>
                  <strong>{{ requestDetailRow.fulfillment_note || '-' }}</strong>
                </div>
              </div>
            </div>
          </div>

          <div class="detail-section">
            <div class="detail-section-head">
              <div class="detail-section-title">规格与主机清单</div>
              <el-tag size="small" type="info">{{ requestDetailSpecEntries.length }} 项</el-tag>
            </div>
            <div v-if="requestDetailSpecEntries.length" class="attribute-grid">
              <div v-for="item in requestDetailSpecEntries" :key="item.key" class="attribute-item">
                <span>{{ item.label }}</span>
                <strong>{{ item.value }}</strong>
              </div>
            </div>
            <el-empty v-else description="暂无规格明细" :image-size="58" />
          </div>

          <div class="detail-section">
            <div class="detail-section-head">
              <div class="detail-section-title">交付资源</div>
              <el-tag size="small" :type="requestDetailDeliveredItems.length ? 'success' : 'info'">{{ requestDetailDeliveredItems.length }} 台</el-tag>
            </div>
            <div v-if="requestDetailDeliveredItems.length" class="delivered-resource-list request-detail-delivered-list">
              <button
                v-for="item in requestDetailDeliveredItems"
                :key="item.id"
                type="button"
                class="delivered-resource-row"
                @click="openCiDetail(item)"
              >
                <strong>{{ item.name }}</strong>
                <span>{{ item.ci_type_name || '-' }} / {{ item.status_display || item.status || '-' }} / {{ item.sync_status || '-' }}</span>
              </button>
            </div>
            <el-empty v-else description="暂未交付资源" :image-size="58" />
          </div>

          <div v-if="canViewAudit" class="detail-section">
            <div class="detail-section-head">
              <div class="detail-section-title">申请审计流水</div>
              <el-button size="small" :loading="requestDetailLoading" @click="fetchRequestDetailAuditLogs(requestDetailRow)">刷新</el-button>
            </div>
            <div v-if="requestDetailAuditLogs.length" class="request-timeline">
              <div v-for="item in requestDetailAuditLogs" :key="item.id" class="request-timeline-item">
                <div class="request-timeline-dot" :class="changeActionTagType(item.action)" />
                <div class="request-timeline-card">
                  <div class="request-timeline-head">
                    <strong>{{ changeActionText(item.action) }}</strong>
                    <span>{{ formatTime(item.created_at) }}</span>
                  </div>
                  <div class="request-timeline-meta">
                    <el-tag size="small" :type="changeActionTagType(item.action)">{{ item.operator || '-' }}</el-tag>
                    <span>{{ changeDiffText(item) }}</span>
                    <el-button link type="primary" size="small" @click="openAuditDetail(item)">查看</el-button>
                  </div>
                </div>
              </div>
            </div>
            <el-empty v-else description="暂无审计流水" :image-size="58" />
          </div>
        </template>
      </div>
    </el-drawer>

    <el-drawer v-model="ciDetailVisible" :title="ciDetail?.name || '配置项详情'" size="760px" append-to-body destroy-on-close>
      <div v-loading="ciDetailLoading" class="ci-detail-shell">
        <template v-if="ciDetail">
          <div class="detail-heading">
            <div class="detail-heading-main">
              <div class="detail-title-row">
                <strong class="detail-main-title" :title="ciDetail.name">{{ ciDetail.name }}</strong>
                <el-tag size="small" :type="ledgerStatusTagType(ciDetail)">{{ ledgerStatusText(ciDetail) }}</el-tag>
                <el-tag size="small" type="info" effect="plain">{{ ciDetail.ci_type_name }}</el-tag>
              </div>
            </div>
            <div v-if="canManageCi" class="detail-heading-actions">
              <el-button v-if="canManageCi" type="primary" size="small" @click="openCiDialog(ciDetail)">
                <el-icon><Edit /></el-icon>
                编辑
              </el-button>
              <el-button v-if="canManageCi && ciDetail.status !== 'offline'" size="small" :loading="ciLifecycleSaving" @click="markConfigItemArchive(ciDetail)">
                <el-icon><Warning /></el-icon>
                待下线
              </el-button>
              <el-button v-else-if="canManageCi" size="small" type="success" plain :loading="ciLifecycleSaving" @click="restoreConfigItemStatus(ciDetail)">
                <el-icon><RefreshRight /></el-icon>
                恢复
              </el-button>
              <el-button v-if="canManageCi" type="danger" plain size="small" :loading="ciDeleting" @click="deleteConfigItemRow(ciDetail)">
                <el-icon><Warning /></el-icon>
                删除
              </el-button>
            </div>
          </div>

          <div v-if="canAccessAssetPassword || ciDetailWebAddress" class="detail-quick-actions">
            <el-tooltip v-if="ciDetailWebAddress" content="在新标签页中打开访问地址" placement="top" :show-after="300">
              <el-button class="detail-quick-action detail-quick-action--web" size="small" @click="openCiDetailWebAddress">
                <el-icon><TopRight /></el-icon>
                打开 Web
              </el-button>
            </el-tooltip>
            <el-button v-if="canAccessAssetPassword" class="detail-quick-action detail-quick-action--credential" size="small" @click="openAssetPasswordDialog">
              <el-icon><Key /></el-icon>
              登录凭据
            </el-button>
          </div>

          <div class="detail-grid">
            <div class="detail-section">
              <div class="detail-section-title">基础信息</div>
              <div class="compact-stack">
                <el-tooltip :content="`资产 ID：${ciDetail.id}`" placement="top" :show-after="300"><div class="detail-kv">资产 ID：{{ ciDetail.id }}</div></el-tooltip>
                <el-tooltip :content="`资产状态：${ledgerStatusText(ciDetail)}`" placement="top" :show-after="300"><div class="detail-kv">资产状态：{{ ledgerStatusText(ciDetail) }}</div></el-tooltip>
                <el-tooltip :content="`业务线：${ciDetail.business_line || '-'}`" placement="top" :show-after="300"><div class="detail-kv">业务线：{{ ciDetail.business_line || '-' }}</div></el-tooltip>
                <el-tooltip :content="`环境：${ciDetailEnvironmentName(ciDetail)}`" placement="top" :show-after="300"><div class="detail-kv">环境：{{ ciDetailEnvironmentName(ciDetail) }}</div></el-tooltip>
                <el-tooltip :content="`部门：${ciDetail.attributes?.department || '-'}`" placement="top" :show-after="300"><div class="detail-kv">部门：{{ ciDetail.attributes?.department || '-' }}</div></el-tooltip>
                <el-tooltip :content="`负责人：${ciDetail.admin_user || '-'}`" placement="top" :show-after="300"><div class="detail-kv">负责人：{{ ciDetail.admin_user || '-' }}</div></el-tooltip>
                <el-tooltip :content="`关系数：${ciDetail.relation_count || ciDetailImpact?.impact_summary?.total_related_count || 0}`" placement="top" :show-after="300"><div class="detail-kv">关系数：{{ ciDetail.relation_count || ciDetailImpact?.impact_summary?.total_related_count || 0 }}</div></el-tooltip>
                <el-tooltip :content="`本月成本：${ciDetailBaseCostText}`" placement="top" :show-after="300"><div class="detail-kv">本月成本：<strong>{{ ciDetailBaseCostText }}</strong></div></el-tooltip>
                <el-tooltip :content="`更新时间：${formatTime(ciDetail.updated_at)}`" placement="top" :show-after="300"><div class="detail-kv detail-kv--full">更新时间：{{ formatTime(ciDetail.updated_at) }}</div></el-tooltip>
                <div v-if="canViewSync" class="detail-kv detail-kv--source">采集来源：{{ ciDetailSourceText }}</div>
                <el-tooltip :content="`描述：${ciDetail.attributes?.description || '-'}`" placement="top" :show-after="300"><div class="detail-kv detail-kv--full">描述：{{ ciDetail.attributes?.description || '-' }}</div></el-tooltip>
              </div>
              <div class="detail-tag-list">
                <el-tooltip v-for="tag in ciDetail.tag_items || []" :key="tag.id" :content="tag.name" placement="top" :show-after="300">
                  <span class="tag-chip" :style="{ borderColor: tag.color || '#dbe4f0', color: tag.color || '#245bdb' }">
                    {{ tag.name }}
                  </span>
                </el-tooltip>
                <span v-if="!(ciDetail.tag_items || []).length" class="sub-text">暂无标签</span>
              </div>
            </div>

            <div class="detail-section">
              <div class="detail-section-title">模型字段</div>
              <div v-if="ciDetailDisplayFields.length" class="field-value-list">
                <el-tooltip v-for="field in ciDetailDisplayFields" :key="field.id || field.code" :content="`${field.name}：${formatValue(ciDetail.attributes?.[field.code])}`" placement="top" :show-after="300">
                  <div class="field-value-row">
                    <span>{{ field.name }}</span>
                    <strong>{{ formatValue(ciDetail.attributes?.[field.code]) }}</strong>
                  </div>
                </el-tooltip>
              </div>
              <el-empty v-else description="暂无字段定义" :image-size="58" />
            </div>
          </div>

          <div v-if="canViewCost" v-loading="ciDetailCostLoading" class="detail-section detail-section--cost">
            <div class="detail-section-head">
              <div class="detail-section-title">成本</div>
              <el-date-picker
                v-model="ciDetailCostMonth"
                type="month"
                value-format="YYYY-MM"
                format="YYYY-MM"
                placeholder="选择月份"
                style="width: 142px"
              />
            </div>
            <div class="cost-detail-summary">
              <el-tag size="small" :type="ciDetailCostMode.tagType">{{ ciDetailCostMode.label }}</el-tag>
              <div v-if="ciDetailPaygCurrentAmount !== null" class="cost-detail-value">
                <span>当前累计</span>
                <strong>{{ formatMoney(ciDetailPaygCurrentAmount) }}</strong>
              </div>
              <div class="cost-detail-value cost-detail-value--primary">
                <span>{{ ciDetailCostMetricLabel }}</span>
                <strong>{{ formatMoney(ciDetailCostAmount) }}</strong>
                <el-tag v-if="ciDetailCostIsProjected" size="small" type="warning">预计</el-tag>
              </div>
            </div>
          </div>

          <div v-if="isResourceWaterlineTarget(ciDetail)" class="detail-section">
            <div class="detail-section-head">
              <div class="detail-section-title">资产水位</div>
              <div class="detail-section-actions">
                <el-button
                  v-if="canManageSync"
                  size="small"
                  :loading="ciDetailWaterlineRefreshLoading"
                  @click="refreshCiDetailResourceWaterline"
                >
                  <el-icon><RefreshRight /></el-icon>
                  采集最新
                </el-button>
              </div>
            </div>
            <div ref="ciDetailWaterlineChartRef" class="detail-waterline-chart" />
          </div>

          <div class="detail-section">
            <div class="detail-section-head">
              <div>
                <div class="detail-section-title">关系与影响面</div>
                <div class="sub-text">按上游依赖和下游影响查看关联资源，默认分析 2 层。</div>
              </div>
              <div class="detail-section-actions">
                <el-tag size="small" type="info">{{ ciDetailImpact?.impact_summary?.total_related_count || 0 }} 个关联资源</el-tag>
                <el-button v-if="canViewTopology" size="small" type="primary" plain @click="openCiTopologyDialog">
                  <el-icon><Share /></el-icon>
                  查看拓扑图
                </el-button>
                <el-button v-if="canManageCi" size="small" @click="openRelationDialog">
                  <el-icon><Plus /></el-icon>
                  批量关联
                </el-button>
              </div>
            </div>
            <div class="impact-summary-grid">
              <div class="impact-summary-item">
                <span>上游资源</span>
                <strong>{{ ciDetailImpact?.impact_summary?.upstream_count || 0 }}</strong>
              </div>
              <div class="impact-summary-item">
                <span>下游资源</span>
                <strong>{{ ciDetailImpact?.impact_summary?.downstream_count || 0 }}</strong>
              </div>
              <div class="impact-summary-item">
                <span>关联总数</span>
                <strong>{{ ciDetailImpact?.impact_summary?.total_related_count || 0 }}</strong>
              </div>
            </div>
            <div class="impact-column-grid">
              <div class="impact-list-panel">
                <strong>上游影响</strong>
                <el-tooltip v-for="item in (ciDetailImpact?.upstream || []).slice(0, 4)" :key="`up-${item.id}`" :content="`${item.name} / ${item.ci_type_name || '-'} / ${relationTypeLabel(item.relation_type)} / ${item.depth} 层`" placement="top" :show-after="300">
                  <button type="button" class="impact-node-row" @click="openCiDetail(item)">
                    <span>{{ item.name }}</span>
                    <small>{{ item.ci_type_name || '-' }} / {{ relationTypeLabel(item.relation_type) }} / {{ item.depth }} 层</small>
                  </button>
                </el-tooltip>
                <span v-if="!(ciDetailImpact?.upstream || []).length" class="muted-text">暂无上游依赖</span>
              </div>
              <div class="impact-list-panel">
                <strong>下游影响</strong>
                <el-tooltip v-for="item in (ciDetailImpact?.downstream || []).slice(0, 4)" :key="`down-${item.id}`" :content="`${item.name} / ${item.ci_type_name || '-'} / ${relationTypeLabel(item.relation_type)} / ${item.depth} 层`" placement="top" :show-after="300">
                  <button type="button" class="impact-node-row" @click="openCiDetail(item)">
                    <span>{{ item.name }}</span>
                    <small>{{ item.ci_type_name || '-' }} / {{ relationTypeLabel(item.relation_type) }} / {{ item.depth }} 层</small>
                  </button>
                </el-tooltip>
                <span v-if="!(ciDetailImpact?.downstream || []).length" class="muted-text">暂无下游影响</span>
              </div>
            </div>
          </div>

          <div v-if="canViewAudit" class="detail-section">
            <div class="detail-section-title">变更记录</div>
            <el-table :data="ciDetailChangeLogs" stripe class="cmdb-table detail-table">
              <el-table-column prop="action" label="动作" width="110" show-overflow-tooltip />
              <el-table-column prop="operator" label="操作人" width="120" show-overflow-tooltip />
              <el-table-column prop="source" label="来源" width="110" show-overflow-tooltip />
              <el-table-column label="变更字段" min-width="180" show-overflow-tooltip>
                <template #default="{ row }">
                  <div class="audit-diff-cell audit-diff-cell--compact">
                    <span>{{ changeDiffText(row) }}</span>
                    <el-tag v-if="changeDiffCount(row)" size="small" type="info">{{ changeDiffCount(row) }}</el-tag>
                    <el-button link type="primary" size="small" @click="openAuditDetail(row)">查看</el-button>
                  </div>
                </template>
              </el-table-column>
              <el-table-column label="时间" width="160">
                <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
              </el-table-column>
            </el-table>
          </div>
        </template>
      </div>
    </el-drawer>

    <el-dialog v-model="ciTopologyVisible" :title="`${ciDetail?.name || '资产'} · 关联关系拓扑`" width="min(1280px, 94vw)" top="4vh" append-to-body destroy-on-close>
      <CmdbTopologyPanel
        v-if="ciTopologyVisible"
        :ci-types="ciTypes"
        :resource-tree="resourceNodeTree"
        :focus-ci-id="ciTopologyId"
        :can-manage="false"
      />
    </el-dialog>

    <el-dialog top="5vh" :close-on-click-modal="false" class="workbench-edit-dialog"
      v-model="assetPasswordDialogVisible"
      :title="`${ciDetail?.name || '资产'} · 登录凭据`"
      width="520px"
      append-to-body
      destroy-on-close
      @closed="resetAssetPasswordDialog"
    >
      <div v-loading="assetPasswordLoading" class="asset-password-shell">
        <div v-if="!assetPasswordLoading && !assetPasswordRecord" class="asset-password-missing-hint">暂未配置凭据，请先配置</div>
        <template v-if="assetPasswordRecord && !assetPasswordEditing">
          <div class="asset-password-summary">
            <el-tooltip :content="assetPasswordRecord.username || '未填写'" placement="top" :show-after="300">
              <div>
                <span>登录用户名</span>
                <strong>{{ assetPasswordRecord.username || '未填写' }}</strong>
              </div>
            </el-tooltip>
            <el-tooltip :content="assetPasswordRecord.has_password ? '已加密保存' : '未配置'" placement="top" :show-after="300">
              <div>
                <span>密码状态</span>
                <strong>{{ assetPasswordRecord.has_password ? '已加密保存' : '未配置' }}</strong>
              </div>
            </el-tooltip>
            <el-tooltip :content="assetPasswordRecord.remark || '无'" placement="top" :show-after="300">
              <div class="span-2">
                <span>备注</span>
                <strong>{{ assetPasswordRecord.remark || '无' }}</strong>
              </div>
            </el-tooltip>
          </div>

          <div v-if="revealedAssetPassword" class="asset-password-reveal">
            <div>
              <span>密码明文</span>
              <strong>{{ revealedAssetPassword }}</strong>
            </div>
            <el-button size="small" @click="copyRevealedAssetPassword">复制</el-button>
            <el-button size="small" @click="revealedAssetPassword = ''">隐藏</el-button>
          </div>

          <div class="asset-password-actions">
            <el-button v-if="canRevealAssetPassword" type="primary" :loading="assetPasswordRevealing" @click="revealAssetPassword">
              {{ revealedAssetPassword ? '重新查看' : '查看密码' }}
            </el-button>
            <el-button v-if="canManageAssetPassword" @click="startEditingAssetPassword">修改</el-button>
            <el-button v-if="canManageAssetPassword" type="danger" plain @click="removeAssetPassword">删除</el-button>
          </div>
        </template>

        <el-form label-position="top" v-else-if="canManageAssetPassword" label-width="88px" class="asset-password-form" autocomplete="off">
          <el-form-item label="登录用户名">
            <el-input v-model="assetPasswordForm.username" maxlength="150" autocomplete="off" autocapitalize="off" autocorrect="off" spellcheck="false" placeholder="例如 root、Administrator" />
          </el-form-item>
          <el-form-item label="登录密码" required>
            <el-input
              v-model="assetPasswordForm.password"
              type="text"
              :class="{ 'asset-password-input--masked': !assetPasswordEntryVisible }"
              autocomplete="off"
              autocapitalize="off"
              autocorrect="off"
              spellcheck="false"
              :placeholder="assetPasswordRecord ? '留空表示保持原密码' : '请输入需要加密保存的密码'"
            >
              <template #suffix>
                <el-button class="asset-password-visibility-toggle" link type="primary" :aria-label="assetPasswordEntryVisible ? '隐藏登录密码' : '显示登录密码'" @click="assetPasswordEntryVisible = !assetPasswordEntryVisible">
                  {{ assetPasswordEntryVisible ? '隐藏' : '显示' }}
                </el-button>
              </template>
            </el-input>
          </el-form-item>
          <el-form-item label="备注">
            <el-input v-model="assetPasswordForm.remark" type="textarea" :rows="3" maxlength="255" show-word-limit placeholder="可填写账号用途或使用说明" />
          </el-form-item>
          <div class="asset-password-actions">
            <el-button v-if="assetPasswordRecord" @click="cancelEditingAssetPassword">取消</el-button>
            <el-button type="primary" :loading="assetPasswordSaving" @click="saveAssetPassword">保存</el-button>
          </div>
        </el-form>

        <el-empty v-else description="该资产尚未配置登录凭据" :image-size="64" />
      </div>
    </el-dialog>

    <el-dialog top="5vh" class="workbench-edit-dialog"
      v-model="assetPasswordVerificationVisible"
      title="身份二次验证"
      width="420px"
      append-to-body
      destroy-on-close
      :close-on-click-modal="false"
      @closed="resetAssetPasswordVerification"
    >
      <el-form label-position="top" class="asset-password-form" autocomplete="on" @submit.prevent>
        <el-form-item label="当前平台用户">
          <el-input :model-value="currentPlatformUsername" name="username" autocomplete="username" readonly />
        </el-form-item>
        <el-form-item label="登录密码" required>
          <el-input
            v-model="assetPasswordVerificationForm.currentPassword"
            type="password"
            name="current-password"
            show-password
            autocomplete="current-password"
            autocapitalize="off"
            autocorrect="off"
            spellcheck="false"
            placeholder="请输入登录密码"
            @keyup.enter="confirmRevealAssetPassword"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button native-type="button" :disabled="assetPasswordRevealing" @click="assetPasswordVerificationVisible = false">取消</el-button>
        <el-button native-type="button" type="primary" :loading="assetPasswordRevealing" @click="confirmRevealAssetPassword">验证并查看</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="auditDetailVisible" title="审计差异详情" width="820px" append-to-body destroy-on-close>
      <div v-if="auditDetailRow" class="audit-detail-shell">
        <div class="request-action-card">
          <div>
            <span>变更资源</span>
            <strong>{{ auditDetailTitle }}</strong>
          </div>
          <div>
            <span>动作</span>
            <strong>{{ changeActionText(auditDetailRow.action) }}</strong>
          </div>
          <div>
            <span>来源</span>
            <strong>{{ changeSourceText(auditDetailRow.source) }}</strong>
          </div>
          <div>
            <span>操作人</span>
            <strong>{{ auditDetailRow.operator || '系统' }}</strong>
          </div>
          <div>
            <span>时间</span>
            <strong>{{ formatTime(auditDetailRow.created_at) }}</strong>
          </div>
        </div>

        <div class="detail-section">
          <div class="detail-section-head">
            <div class="detail-section-title">字段差异</div>
            <el-tag size="small" type="info">{{ auditDetailFields.length }} 项</el-tag>
          </div>
          <el-table v-if="auditDetailFields.length" :data="auditDetailFields" stripe class="cmdb-table detail-table">
            <el-table-column label="字段" width="160">
              <template #default="{ row }">{{ row.label || row.field }}</template>
            </el-table-column>
            <el-table-column label="变更前" min-width="220" show-overflow-tooltip>
              <template #default="{ row }">{{ row.before_text || formatAuditValue(row.before) }}</template>
            </el-table-column>
            <el-table-column label="变更后" min-width="220" show-overflow-tooltip>
              <template #default="{ row }">{{ row.after_text || formatAuditValue(row.after) }}</template>
            </el-table-column>
          </el-table>
          <el-empty v-else description="暂无字段级差异" :image-size="58" />
        </div>

        <div class="audit-raw-grid">
          <div class="detail-section">
            <div class="detail-section-title">变更前快照</div>
            <pre>{{ formatAuditJson(auditDetailRow.before) }}</pre>
          </div>
          <div class="detail-section">
            <div class="detail-section-title">变更后快照</div>
            <pre>{{ formatAuditJson(auditDetailRow.after) }}</pre>
          </div>
        </div>
      </div>
    </el-dialog>

    <el-dialog top="5vh" :close-on-click-modal="false" class="workbench-edit-dialog" v-model="thresholdPolicyDialogVisible" :title="thresholdPolicyEditingId ? '编辑水位策略' : '新建水位策略'" width="640px" append-to-body destroy-on-close>
      <el-form label-position="top" :model="thresholdPolicyForm" label-width="96px" class="workbench-editor-form--sectioned cmdb-form-grid">
        <section class="workbench-editor-section">
          <div class="workbench-editor-heading"><span class="workbench-editor-step">01</span><h3>适用范围</h3></div>
          <div class="workbench-editor-grid">
            <el-form-item label="适用模型">
              <el-select v-model="thresholdPolicyForm.resource_type" clearable filterable placeholder="不选则作为全局策略" style="width: 100%">
                <el-option v-for="item in ciTypes" :key="item.id" :label="item.name" :value="item.id" />
              </el-select>
            </el-form-item>
            <el-form-item label="指标" required>
              <el-select v-model="thresholdPolicyForm.metric" filterable allow-create placeholder="选择或输入指标名" style="width: 100%">
                <el-option v-for="item in metricNameOptions" :key="item" :label="metricLabel(item)" :value="item" />
              </el-select>
            </el-form-item>
          </div>
        </section>
        <section class="workbench-editor-section workbench-editor-section--tinted">
          <div class="workbench-editor-heading"><span class="workbench-editor-step">02</span><h3>水位阈值</h3></div>
          <div class="workbench-editor-grid">
            <el-form-item label="正常阈值"><el-input-number v-model="thresholdPolicyForm.normal_threshold" :min="0" :max="10000" :precision="2" /></el-form-item>
            <el-form-item label="预警阈值"><el-input-number v-model="thresholdPolicyForm.warning_threshold" :min="0" :max="10000" :precision="2" /></el-form-item>
            <el-form-item label="紧张阈值"><el-input-number v-model="thresholdPolicyForm.critical_threshold" :min="0" :max="10000" :precision="2" /></el-form-item>
            <el-form-item label="超限阈值"><el-input-number v-model="thresholdPolicyForm.exceeded_threshold" :min="0" :max="10000" :precision="2" /></el-form-item>
            <el-form-item label="启用"><el-switch v-model="thresholdPolicyForm.enabled" /></el-form-item>
          </div>
        </section>
      </el-form>
      <template #footer>
        <el-button @click="thresholdPolicyDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveThresholdPolicy">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog top="5vh" :close-on-click-modal="false" class="workbench-edit-dialog" v-model="metricDialogVisible" :title="metricEditingId ? '编辑指标快照' : '录入指标快照'" width="640px" append-to-body destroy-on-close>
      <el-form label-position="top" :model="metricForm" label-width="96px" class="workbench-editor-form--sectioned cmdb-form-grid">
        <section class="workbench-editor-section">
          <div class="workbench-editor-heading"><span class="workbench-editor-step">01</span><h3>资源与指标</h3></div>
          <div class="workbench-editor-grid">
            <el-form-item label="资源" class="span-2" required>
              <el-select v-model="metricForm.ci" filterable placeholder="选择资源" style="width: 100%">
                <el-option
              v-for="item in ledgerItems"
              :key="item.id"
              :label="`${item.name} / ${item.ci_type_name || modelName(item.ci_type)}`"
              :value="item.id"
            />
              </el-select>
            </el-form-item>
            <el-form-item label="指标" required>
              <el-select v-model="metricForm.metric" filterable allow-create placeholder="选择或输入指标名" style="width: 100%">
                <el-option v-for="item in metricNameOptions" :key="item" :label="metricLabel(item)" :value="item" />
              </el-select>
            </el-form-item>
            <el-form-item label="来源"><el-input v-model="metricForm.source" placeholder="manual / monitor / aliyun" /></el-form-item>
          </div>
        </section>
        <section class="workbench-editor-section workbench-editor-section--tinted">
          <div class="workbench-editor-heading"><span class="workbench-editor-step">02</span><h3>指标数值</h3></div>
          <div class="workbench-editor-grid">
            <el-form-item label="指标值"><el-input-number v-model="metricForm.value" :precision="4" /></el-form-item>
            <el-form-item label="单位"><el-input v-model="metricForm.unit" placeholder="%, GB, count" /></el-form-item>
            <el-form-item label="使用率"><el-input-number v-model="metricForm.usage_percent" :min="0" :max="10000" :precision="2" /></el-form-item>
          </div>
        </section>
      </el-form>
      <template #footer>
        <el-button @click="metricDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveMetric">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog top="5vh" :close-on-click-modal="false" class="workbench-edit-dialog" v-model="relationDialogVisible" title="批量关联资源关系" width="720px" append-to-body destroy-on-close>
      <el-form label-position="top" :model="relationForm" label-width="96px" class="cmdb-form-grid relation-dialog-form">
        <el-form-item label="关系方向" required>
          <el-select v-model="relationForm.direction" style="width: 100%">
            <el-option label="当前资源 → 目标资源" value="outgoing" :disabled="!relationDirectionOptions.includes('outgoing')" />
            <el-option label="来源资源 → 当前资源" value="incoming" :disabled="!relationDirectionOptions.includes('incoming')" />
          </el-select>
        </el-form-item>
        <el-form-item label="关系类型" required>
          <el-select v-model="relationForm.relation_type" filterable :disabled="!relationTypeOptions.length" :allow-create="false" style="width: 100%">
            <el-option v-for="item in relationTypeOptions" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
        </el-form-item>
        <el-alert
          v-if="activeRelationRule"
          class="span-2 relation-rule-hint"
          type="info"
          :closable="false"
          show-icon
          :title="activeRelationRule.flow_label"
          :description="activeRelationRule.description || '只允许选择该规则定义的目标资源类型。'"
        />
        <el-alert
          v-else-if="relationDialogVisible && relationRules.length"
          class="span-2 relation-rule-hint"
          type="warning"
          :closable="false"
          show-icon
          title="当前方向暂无可用关系规则"
          description="请切换到有规则的关系方向，或先在模型配置中新增关系规则。"
        />
        <el-form-item :label="relationForm.direction === 'incoming' ? '来源资源' : '目标资源'" class="span-2" required>
          <el-select
            v-model="relationForm.targets"
            multiple
            collapse-tags
            collapse-tags-tooltip
            filterable
            remote
            reserve-keyword
            :remote-method="fetchRelationTargets"
            placeholder="按名称或 IP 搜索并选择多个配置项"
            style="width: 100%"
          >
            <el-option
              v-for="item in relationTargets"
              :key="item.id"
              :label="relationTargetLabel(item)"
              :value="item.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="补充说明" class="span-2"><el-input v-model="relationForm.description" type="textarea" :rows="2" placeholder="可选，用于说明本次关联的业务背景" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="relationDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="relationSaving" @click="saveRelation">
          {{ relationForm.targets.length ? `创建 ${relationForm.targets.length} 条关系` : '保存' }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, defineComponent, h, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import CmdbPlatformHeader from '@/components/cmdb/CmdbPlatformHeader.vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  ArrowDown,
  ArrowLeft,
  ArrowRight,
  Aim,
  Box,
  Coin,
  Collection,
  CollectionTag,
  Compass,
  Connection,
  Cpu,
  DataAnalysis,
  DataBoard,
  DataLine,
  Delete,
  Document,
  DocumentChecked,
  Download,
  Edit,
  Files,
  Folder,
  FolderChecked,
  FolderOpened,
  Goods,
  Grid,
  Guide,
  Histogram,
  House,
  InfoFilled,
  Key,
  Link,
  List,
  Location,
  Lock,
  Management,
  Menu,
  Monitor,
  MostlyCloudy,
  Odometer,
  OfficeBuilding,
  Operation,
  Platform,
  Plus,
  Postcard,
  RefreshRight,
  Service,
  SetUp,
  Share,
  Ship,
  Switch,
  TakeawayBox,
  Tickets,
  TopRight,
  TrendCharts,
  UploadFilled,
  User,
  Warning,
} from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'
import echarts from '@/lib/echarts'
import {
  approveRequest,
  archiveArchiveCandidate,
  assignCompletionIssue,
  bulkActionArchiveCandidates,
  bulkCreateCIRelations,
  bulkImportConfigItems,
  bulkResolveCompletionIssues,
  bulkResolveSyncRecordRelations,
  createCIModelGroup,
  createCITag,
  createCIField,
  createCIRelation,
  createCIRelationRule,
  createCIType,
  createCloudCredential,
  createConfigItemPassword,
  createConfigItem,
  createResourceAuthorization,
  createResourceMetric,
  createResourceNode,
  createResourceRequest,
  createSourceMapping,
  createSyncJob,
  createThresholdPolicy,
  deleteCIRelationRule,
  deleteCIField,
  deleteCIModelGroup,
  deleteCITag,
  deleteCloudCredential,
  deleteConfigItemPassword,
  deleteConfigItem,
  deleteResourceAuthorization,
  deleteResourceMetric,
  deleteResourceNode,
  deleteSourceMapping,
  deleteSyncJob,
  deleteThresholdPolicy,
  downloadConfigItemImportTemplate,
  dryRunSyncJob,
  ensureCmdbBuiltins,
  exportConfigItems,
  getAvailableCIRelationRules,
  getArchiveCandidates,
  getChangeLogSummary,
  getChangeLogs,
  getCloudCredentials,
  getCIFields,
  getCIModelGroups,
  getCIRelationRules,
  getCITags,
  getCITypes,
  getCmdbCollectionSummary,
  getCmdbCostReport,
  getCmdbDashboard,
  getCmdbGovernanceRisks,
  getCmdbModelTree,
  getCmdbRepositorySummary,
  getCmdbTopology,
  getCmdbViewsSummary,
  getConfigItemImpact,
  getCompletionIssues,
  getConfigItem,
  getConfigItemPasswords,
  getConfigItemLedgerTree,
  getConfigItems,
  getCostRecords,
  getThirdPartyExpirySummary,
  getLatestResourceMetrics,
  getResourceNodeTree,
  getResourceMetrics,
  getResourceAuthorizations,
  getResourceRequest,
  getResourceRequestProvisioningOptions,
  getResourceRequests,
  getSourceAccountRegionOptions,
  getSourceMappings,
  getSyncRecords,
  getSyncRecordRelationCandidates,
  getSyncJobs,
  getThresholdPolicies,
  ignoreArchiveCandidate,
  ignoreCompletionIssue,
  ignoreSyncRecord,
  markConfigItemArchiveCandidate,
  mergeConfigItemDuplicates,
  resolveCompletionIssue,
  restoreConfigItemLifecycle,
  retryFailedSyncJob,
  retrySyncRecord,
  resolveSyncRecordRelation,
  resolveSyncRecordToCi,
  runDueSyncJobs,
  runSyncJob,
  syncCloudCredential,
  toggleSyncJobCollection,
  completeRequest,
  provisionResourceRequest,
  rejectRequest,
  bulkUpdateConfigItems,
  refreshCurrentPageResourceWaterline,
  revealConfigItemPassword,
  updateCIField,
  updateCIModelGroup,
  updateCIRelationRule,
  updateCITag,
  updateConfigItem,
  updateConfigItemGovernance,
  updateResourceAuthorization,
  updateCIType,
  updateResourceMetric,
  updateResourceNode,
  updateSourceMapping,
  updateCloudCredential,
  updateConfigItemPassword,
  updateSyncJob,
  updateThresholdPolicy,
} from '@/api/modules/cmdb'
import { getMetricDataSources } from '@/api/modules/ops'
import CmdbTopologyPanel from '@/components/cmdb/CmdbTopologyPanel.vue'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

const loading = ref(false)
const dashboardLoading = ref(false)
const repositoryLoading = ref(false)
const viewsLoading = ref(false)
const tagLoading = ref(false)
const auditLoading = ref(false)
const authorizationLoading = ref(false)
const sourceMappingLoading = ref(false)
const syncJobsLoading = ref(false)
const collectionSummaryLoading = ref(false)
const syncCenterBackgroundLoading = ref(false)
const ledgerLoading = ref(false)
const exportingLedger = ref(false)
const downloadingTemplate = ref(false)
const topologyLoading = ref(false)
const requestLoading = ref(false)
const thresholdLoading = ref(false)
const metricLoading = ref(false)
const builtinRefreshing = ref(false)
const BACKGROUND_REQUEST_CONFIG = { skipErrorMessage: true }
const dashboard = ref({})
const governanceRisks = ref({ capacity_waterline: {}, service_expiry_risks: [], risk_summary: {} })
const overviewCostReport = ref({})
const overviewCostOptimization = ref({})
const overviewCostLoading = ref(false)
const OVERVIEW_CACHE_TTL = {
  dashboard: 20 * 1000,
  resources: 45 * 1000,
  governance: 20 * 1000,
  cost: 60 * 1000,
}
let overviewDashboardCacheAt = 0
let overviewResourcesCacheAt = 0
let overviewGovernanceCacheAt = 0
let overviewCostCacheAt = 0
let overviewCostScopeKey = ''
let overviewDashboardRequest = null
let overviewResourcesRequest = null
let overviewGovernanceRequest = null
let overviewCostRequest = null
const repositorySummary = ref({ summary: {}, groups: [], top_models: [] })
const repositoryModelTree = ref({ summary: {}, groups: [], tree: [], top_models: [] })
const viewsSummary = ref({ summary: {}, applications: [], hosts: [], physical: [] })
const islandAnalysis = ref({ summary: {}, results: [] })
const collectionSummary = ref({ summary: {}, sources: [], jobs: [] })
const collectionSummaryLoaded = ref(false)
const resourceAuthorizations = ref([])
const sourceMappings = ref([])
const ciSourceAccountRegionOptions = ref([])
const auditSummary = ref({ total: 0, action_counts: [], operator_counts: [], source_counts: [] })
const ledgerItems = ref([])
const thirdPartyExpirySummary = ref({ total: 0, normal: 0, warning: 0, urgent: 0, expired: 0, missing: 0 })
const modelThirdPartyExpirySummary = ref({ total: 0, normal: 0, warning: 0, urgent: 0, expired: 0, missing: 0 })
const ledgerTreeItems = ref([])
const ledgerTreeLoaded = ref(false)
const modelCatalogTreeItems = ref([])
const ledgerSelection = ref([])
const modelResourceItems = ref([])
const modelResourceLoading = ref(false)
const ledgerPagination = reactive({
  page: 1,
  pageSize: 20,
  total: 0,
})
const modelResourcePagination = reactive({
  page: 1,
  pageSize: 20,
  total: 0,
})
const ledgerViewMode = ref('business')
const ledgerTreeContext = ref(null)
const ledgerTreeKeyword = ref('')
let ledgerTreeRequestSeq = 0
const modelCatalogTreeMode = ref('business')
const modelCatalogTreeContext = ref(null)
const modelCatalogTreeKeyword = ref('')
const expandedLedgerTreeKeys = ref(new Set())
const collapsedLedgerTreeKeys = ref(new Set())
const expandedModelCatalogTreeKeys = ref(new Set())
const collapsedModelCatalogTreeKeys = ref(new Set())
const ledgerSummaryContext = ref(null)
const ledgerAuthorizationContext = ref(null)
const ledgerViewContext = ref(null)
const topology = ref({ nodes: [], edges: [], meta: {} })
const resourceRequests = ref([])
const thresholdPolicies = ref([])
const resourceMetrics = ref([])
const overviewResourceMetrics = ref([])
const resourceWaterlinePageMetrics = ref([])
const resourceWaterlinePageMetricLoading = ref(false)
const overviewServerItems = ref([])
const overviewServerLoading = ref(false)
const overviewResourceDimension = ref('cloud_account')
const overviewResourceScope = ref('')
const overviewResourceDimensionOptions = [
  { key: 'business_environment', label: '业务环境维度' },
  { key: 'cloud_account', label: '云账号维度' },
]
const resourceNodeTree = ref([])
const cloudResourceNodeTree = ref([])
const treeLoading = ref(false)
const ciTypes = ref([])
const ciFields = ref([])
const ciModelGroups = ref([])
const ciTags = ref([])
const auditLogs = ref([])
const completionIssues = ref([])
const completionSelection = ref([])
const archiveCandidates = ref([])
const archiveSelection = ref([])
const syncFailureRecords = ref([])
const syncFailureLoading = ref(false)
const syncRelationBulkResolving = ref(false)
const syncJobs = ref([])
const syncAccountTaskDrawerVisible = ref(false)
const syncAccountTaskDrawerAccountId = ref('')
const activeSummaryKey = ref('all')
const activeGovernanceKey = ref('archive')
const governanceViewMode = ref('categories')
const governanceScopeContext = ref(null)
const governanceTreeContext = ref(null)
const saving = ref(false)
const syncDueRunning = ref(false)
const syncPreviewVisible = ref(false)
const syncPreview = ref({ summary: {}, records: [] })
const syncRuntimeVisible = ref(false)
const syncRuntimeSubmitting = ref(false)
const syncRuntimeAction = ref('run')
const syncRuntimeRow = ref(null)
const syncRuntimeForm = reactive({
  password: '',
})
const syncRecordsVisible = ref(false)
const syncRecordsLoading = ref(false)
const syncRecords = ref([])
const syncRecordsJob = ref(null)
const syncRecordStatusFilter = ref('all')
const syncRecordBatchDetail = ref(null)
const syncRecordDetailVisible = ref(false)
const syncRecordDetailRow = ref(null)
const syncRelationIssueLoading = ref(false)
const syncRelationIssues = ref([])
const syncRelationResolvingKey = ref('')
const syncResolveVisible = ref(false)
const syncResolveRecord = ref(null)
const requestDetailVisible = ref(false)
const requestDetailLoading = ref(false)
const requestDetailRow = ref(null)
const requestDetailAuditLogs = ref([])
const ciDetailVisible = ref(false)
const ciTopologyVisible = ref(false)
const ciTopologyId = ref(null)
const ciDetailLoading = ref(false)
const ciDeleting = ref(false)
const ciLifecycleSaving = ref(false)
const ciDetail = ref(null)
const ciDetailMappings = ref([])
const ciDetailChangeLogs = ref([])
const ciDetailImpact = ref(null)
const ciDetailCostHistory = ref([])
const ciDetailCostLoading = ref(false)
const ciDetailCostMonth = ref(currentMonth())
const ciDetailWaterlineRefreshLoading = ref(false)
const ciDetailWaterlineHistory = ref([])
const ciDetailWaterlineChartRef = ref(null)
const ciDetailWaterlineWindow = ref({ start: '', end: '' })
let ciDetailWaterlineChart = null
const assetPasswordDialogVisible = ref(false)
const assetPasswordLoading = ref(false)
const assetPasswordSaving = ref(false)
const assetPasswordRevealing = ref(false)
const assetPasswordVerificationVisible = ref(false)
const assetPasswordEditing = ref(false)
const assetPasswordRecord = ref(null)
const revealedAssetPassword = ref('')
const assetPasswordEntryVisible = ref(false)
const auditDetailVisible = ref(false)
const auditDetailRow = ref(null)
const relationDialogVisible = ref(false)
const relationSaving = ref(false)
const relationTargets = ref([])
const relationRules = ref([])
const resourceNodeDialogVisible = ref(false)
const resourceNodeEditingId = ref(null)
const resourceNodeVirtualParentEntry = ref(null)
const resourceNodeEditMode = ref('full')
const completionDialogVisible = ref(false)
const completionIssueRow = ref(null)
const completionAssignVisible = ref(false)
const completionAssignRow = ref(null)
const tagDialogVisible = ref(false)
const tagEditingId = ref(null)
const sourceMappingDialogVisible = ref(false)
const sourceMappingEditingId = ref(null)
const sourceMappingDetailVisible = ref(false)
const sourceMappingDetailRow = ref(null)
const authorizationDialogVisible = ref(false)
const authorizationEditingId = ref(null)
const thresholdPolicyDialogVisible = ref(false)
const thresholdPolicyEditingId = ref(null)
const metricDialogVisible = ref(false)
const metricEditingId = ref(null)
const cloudCredentialDialogVisible = ref(false)
const cloudCredentialSaving = ref(false)
const cloudCredentialEditingId = ref(null)

const canViewDashboard = computed(() => authStore.hasPermission('cmdb.dashboard.view'))
const canViewCi = computed(() => authStore.hasPermission('cmdb.ci.view'))
const canViewTopology = computed(() => authStore.hasPermission('cmdb.topology.view'))
const canManageCi = computed(() => authStore.hasPermission('cmdb.ci.manage'))
const canViewCost = computed(() => authStore.hasPermission('cmdb.cost.view'))
const canManageCost = computed(() => authStore.hasPermission('cmdb.cost.manage'))
const canSubmitRequest = computed(() => authStore.hasPermission('cmdb.request.submit'))
const canApproveRequest = computed(() => authStore.hasPermission('cmdb.request.approve'))
const canExecuteRequest = computed(() => authStore.hasPermission('cmdb.request.execute'))
const canViewRequests = computed(() => authStore.hasAnyPermission(['cmdb.ci.view', 'cmdb.request.submit', 'cmdb.request.approve', 'cmdb.request.execute']))
const canViewModel = computed(() => authStore.hasPermission('cmdb.model.view'))
const canManageModel = computed(() => authStore.hasPermission('cmdb.model.manage'))
const canViewSync = computed(() => authStore.hasPermission('cmdb.sync.view'))
const canManageSync = computed(() => authStore.hasPermission('cmdb.sync.manage'))
const canManageCloudAccounts = computed(() => authStore.hasPermission('ops.multicloud.manage'))
const canViewAuthorization = computed(() => authStore.hasPermission('cmdb.authorization.view'))
const canManageAuthorization = computed(() => authStore.hasPermission('cmdb.authorization.manage'))
const canViewAudit = computed(() => authStore.hasPermission('cmdb.audit.view'))
const canManageAssetPassword = computed(() => authStore.hasPermission('cmdb.password.manage'))
const canRevealAssetPassword = computed(() => authStore.hasPermission('cmdb.password.reveal'))
const canAccessAssetPassword = computed(() => canManageAssetPassword.value || canRevealAssetPassword.value)
const currentPlatformUsername = computed(() => authStore.currentUser?.username || authStore.displayName || '当前用户')
const canUseHostTerminal = computed(() => authStore.hasPermission('ops.host.terminal'))

const tabs = computed(() => [
  canViewDashboard.value && { key: 'overview', label: '总览', icon: Monitor, path: '/cmdb/overview', desc: '资源规模、容量水位、风险和申请建议。' },
  canViewCi.value && { key: 'ledger', label: '资产台账', icon: List, path: '/cmdb/ledger', desc: '统一查看机房、云、数据库、中间件和第三方服务资产，并按业务线/环境组织。' },
  canViewCi.value && { key: 'views', label: '视图展示', icon: DataBoard, path: '/cmdb/views', desc: '按应用与资源关系组织资源，快速看清应用视角。' },
  canViewRequests.value && { key: 'requests', label: '资源申请', icon: Tickets, path: '/cmdb/requests', desc: '提交主机资源申请，并完成审批、交付和台账同步。' },
  canViewCi.value && { key: 'governance', label: '资产治理', icon: Warning, path: '/cmdb/governance', desc: '集中处理待下线、同步失败、容量与服务到期风险。' },
  canViewAuthorization.value && { key: 'authorization', label: '资源授权', icon: Lock, path: '/cmdb/authorization', desc: '按用户和用户组控制业务线、环境和模型数据范围。' },
  canViewSync.value && { key: 'sync', label: '资产采集中心', icon: Connection, path: '/cmdb/sync', desc: '管理云账号、vSphere 和第三方服务的资产采集、预览入库与失败重试。' },
  (canViewModel.value || canManageModel.value) && { key: 'model', label: '资产分类', icon: SetUp, path: canViewModel.value ? '/cmdb/model' : '/cmdb/model/config', desc: '查看模型分组、模型字段、资源实例和字段约束。' },
  canViewCi.value && { key: 'thresholds', label: '容量策略', icon: DataBoard, path: '/cmdb/thresholds', desc: '配置容量阈值、录入资源指标，并驱动概览水位和治理风险。' },
  canViewAudit.value && { key: 'audit', label: '操作审计', icon: DocumentChecked, path: '/cmdb/audit', desc: '追踪资源创建、变更、删除、补全和归档等操作记录。' },
].filter(Boolean))

const workspaceGroupDefinitions = [
  { key: 'overview', label: '概览', icon: Monitor, desc: '全局资源态势与风险入口。', children: ['overview'] },
  { key: 'view', label: '视图展示', icon: DataBoard, desc: '应用视图与资源关系。', children: ['views'] },
  { key: 'repository', label: '资产台账', icon: Collection, desc: '资产台账与资源实例归集。', children: ['ledger'] },
  { key: 'model', label: '资产分类', icon: SetUp, desc: '资源模型、字段、图标、实例和自动采集。', children: ['model'] },
  { key: 'sync', label: '资产采集中心', icon: Connection, desc: '从云账号、虚拟化平台和第三方服务采集资产，预览后入库并跟进失败重试。', children: ['sync'] },
  { key: 'governance', label: '资产治理', icon: Warning, desc: '聚焦生命周期、同步、容量与服务到期风险。', children: ['governance'] },
  { key: 'operation', label: '资源运营', icon: Tickets, desc: '申请和授权运营。', children: ['requests', 'authorization'] },
  { key: 'setting', label: '平台设置', icon: DocumentChecked, desc: '平台策略、审计与变更追踪。', children: ['thresholds', 'audit'] },
]

const workspaceGroups = computed(() => {
  const tabMap = new Map(tabs.value.map(item => [item.key, item]))
  return workspaceGroupDefinitions
    .map(group => ({ ...group, tabs: group.children.map(key => tabMap.get(key)).filter(Boolean) }))
    .filter(group => group.tabs.length)
})

const routeTabMap = {
  CmdbOverview: 'overview',
  CmdbLedger: 'ledger',
  CmdbViews: 'views',
  CmdbRequests: 'requests',
  CmdbGovernance: 'governance',
  CmdbAuthorization: 'authorization',
  CmdbSync: 'sync',
  CmdbModel: 'model',
  CmdbModelConfig: 'model',
  CmdbModelDetail: 'model',
  CmdbModelTopology: 'model',
  CmdbThresholds: 'thresholds',
  CmdbAudit: 'audit',
}
const openedLedgerDetailId = ref('')
const activeTab = computed(() => routeTabMap[route.name] || tabs.value[0]?.key || 'overview')
const isModelDetailRoute = computed(() => route.name === 'CmdbModelDetail')
const isModelConfigRoute = computed(() => route.name === 'CmdbModelConfig')
const isModelTopologyRoute = computed(() => route.name === 'CmdbModelTopology')
const isPlatformConfigRoute = computed(() => activeTab.value === 'sync' || isModelConfigRoute.value)
const isModelDisplayRoute = computed(() => activeTab.value === 'model' && !isModelDetailRoute.value && !isModelConfigRoute.value && !isModelTopologyRoute.value)
const hasModelCatalogTree = computed(() => isModelDisplayRoute.value || isModelDetailRoute.value)
const isModelCatalogRoute = computed(() => isModelDisplayRoute.value || isModelConfigRoute.value || isModelDetailRoute.value)
const activeTabMeta = computed(() => tabs.value.find(item => item.key === activeTab.value))
const activeWorkspace = computed(() => workspaceGroups.value.find(group => group.tabs.some(tab => tab.key === activeTab.value)) || workspaceGroups.value[0])
const activeWorkspaceTabs = computed(() => activeWorkspace.value?.tabs || [])
const opsanySurfaceTabs = new Set(['views', 'model'])
const isOpsanyCmdbSurface = computed(() => opsanySurfaceTabs.has(activeTab.value))
const viewModeMeta = computed(() => {
  if (viewMode.value === 'host') return { title: '主机视图', desc: '以主机为中心查看业务归属、来源和运行关系。' }
  if (viewMode.value === 'physical') return { title: '机房视图', desc: '以机房和机柜为中心查看物理资产分布与占用。' }
  return { title: '应用视图', desc: '以应用为中心查看资源归属与依赖关系。' }
})
const activeSurfaceTitle = computed(() => {
  if (activeTab.value === 'views') return viewModeMeta.value.title
  if (isModelTopologyRoute.value) return '资产分类拓扑'
  if (isModelConfigRoute.value) return '资产分类配置'
  if (activeTab.value === 'model') return '资产分类视图'
  return activeTabMeta.value?.label || ''
})
const activeHeroTitle = computed(() => (activeTab.value === 'model' ? activeSurfaceTitle.value : (activeWorkspace.value?.label || 'CMDB 资源中心')))
const activeSurfaceBreadcrumb = computed(() => {
  const parent = activeWorkspace.value?.label || activeTabMeta.value?.label || 'CMDB'
  return `${parent} > ${activeSurfaceTitle.value}`
})
const activeSurfaceDesc = computed(() => {
  if (activeTab.value === 'views') return viewModeMeta.value.desc
  if (isModelTopologyRoute.value) return '按知识图谱方式展示资产之间的承载、依赖、访问与绑定关系，帮助核对关系完整性。'
  if (isModelConfigRoute.value) return '维护资产分类分组、模型字段、图标和关系规则，配置完成后在展示页查看效果。'
  if (activeTab.value === 'model') return '按资产分类梳理资源类型、字段、关系与实例详情。'
  return activeTabMeta.value?.desc || ''
})

const viewFilters = reactive({
  business_line: '',
  environment: '',
})
const viewMode = ref('application')
const applicationViewKeyword = ref('')
const applicationViewRisk = ref('')
const applicationViewOwner = ref('')
const applicationViewTeam = ref('')
const applicationViewTier = ref('')
const opsanyViewKeyword = ref('')
const selectedOpsanyViewNode = ref({ mode: 'application', key: 'all' })
const activeRepositoryGroupKey = ref('all')
const activeModelGroupKey = ref('all')
const opsanyModelKeyword = ref('')
const opsanyModelStatus = ref('active')
const builtinAutoEnsureAttempted = ref(false)

const standardAssetModelGroups = [
  { key: 'business', code: 'business', name: '业务模型' },
  { key: 'compute', code: 'compute', name: '计算资源' },
  { key: 'database', code: 'database', name: '数据库' },
  { key: 'middleware', code: 'middleware', name: '中间件' },
  { key: 'storage', code: 'storage', name: '存储' },
  { key: 'bigdata', code: 'bigdata', name: '大数据' },
  { key: 'network', code: 'network', name: '网络与入口' },
  { key: 'external', code: 'external', name: '其他资产' },
]
const standardAssetModelGroupCodes = new Set(standardAssetModelGroups.map(group => group.code))
const requiredCloudAssetModelCodes = [
  'CLOUD_SERVER',
  'VIRTUAL_MACHINE',
  'K8S_CLUSTER',
  'MYSQL',
  'POSTGRESQL',
  'REDIS',
  'MONGODB',
  'KAFKA',
  'ROCKETMQ',
  'ELASTICSEARCH',
  'OBJECT_STORAGE',
  'BLOCK_STORAGE',
  'FILE_STORAGE',
  'CLICKHOUSE',
  'HOLOGRES',
  'MAXCOMPUTE',
  'DATAWORKS',
  'LOAD_BALANCER',
  'NAT_GATEWAY',
  'ELASTIC_IP',
]
const requiredBuiltinRelationKeys = [
  ['APP_SERVICE', 'K8S_CLUSTER', 'runs_on'],
  ['K8S_CLUSTER', 'IDC_SERVER', 'runs_on'],
  ['K8S_CLUSTER', 'CLOUD_SERVER', 'runs_on'],
  ['K8S_CLUSTER', 'VIRTUAL_MACHINE', 'runs_on'],
]

const ledgerViewModeOptions = [
  { key: 'business', label: '业务环境维度', icon: FolderOpened },
  { key: 'cloud', label: '云账号维度', icon: MostlyCloudy },
]
const modelCatalogTreeModeOptions = [
  { key: 'business', label: '业务环境维度', icon: FolderOpened },
  { key: 'cloud', label: '云账号维度', icon: MostlyCloudy },
]
const businessResourceNodeTypeOptions = [
  { label: '业务线', value: 'biz' },
  { label: '环境', value: 'env' },
]
const cloudResourceNodeTypeOptions = [
  { label: '云账号', value: 'cloud_account' },
  { label: '云地域', value: 'cloud_region' },
  { label: '云集群', value: 'cloud_cluster' },
  { label: '云宿主机', value: 'cloud_host' },
]
const cloudResourceNodeTypes = new Set(cloudResourceNodeTypeOptions.map(item => item.value))
const childResourceNodeParentTypes = {
  env: ['biz'],
  cloud_region: ['cloud_account'],
  cloud_cluster: ['cloud_region'],
  cloud_host: ['cloud_region', 'cloud_cluster'],
}
const resourceNodeTypeLabels = {
  biz: '业务线',
  env: '环境',
  cloud_account: '云账号',
  cloud_region: '云地域',
  cloud_cluster: '云集群',
  cloud_host: '云宿主机',
}

const ledgerFilters = reactive({
  search: '',
  asset_search: '',
  attribute_search: '',
  ci_type: '',
  resource_node: '',
  business_node: '',
  business_line: '',
  service_type: '',
  provider: '',
  expiry_risk: '',
  source_account: '',
  source_account_missing: '',
  source_region: '',
  source_unique_id: '',
  vsphere_cluster: '',
  vsphere_host: '',
  availability_zone: '',
  engine: '',
  vpc_id: '',
  network_type: '',
  storage_class: '',
  acl: '',
  sync_status: '',
  idc: '',
  rack: '',
  lifecycle_status: '',
  environment_node: '',
  environment: '',
  status: '',
  tags: '',
  source_type: '',
  ownership: '',
  admin_user: '',
  department: '',
  system: '',
})

const cmdbUiStateStorageKey = 'sxdevops.cmdb.ui-state.v1'
let cmdbUiStateSaveTimer = null

function applySavedFilterValues(target, savedValues) {
  if (!savedValues || typeof savedValues !== 'object') return
  Object.keys(target).forEach((key) => {
    if (Object.prototype.hasOwnProperty.call(savedValues, key)) {
      target[key] = savedValues[key] ?? ''
    }
  })
}

function saveCmdbUiState() {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.setItem(cmdbUiStateStorageKey, JSON.stringify({
      assetTreeDefault: 'business',
      ledger: {
        filters: { ...ledgerFilters },
        viewMode: ledgerViewMode.value,
        treeContext: ledgerTreeContext.value ? { ...ledgerTreeContext.value } : null,
        treeKeyword: ledgerTreeKeyword.value,
        expandedKeys: Array.from(expandedLedgerTreeKeys.value),
        collapsedKeys: Array.from(collapsedLedgerTreeKeys.value),
      },
      views: {
        filters: { ...viewFilters },
        mode: viewMode.value,
        keyword: applicationViewKeyword.value,
        risk: applicationViewRisk.value,
        owner: applicationViewOwner.value,
        team: applicationViewTeam.value,
        tier: applicationViewTier.value,
        treeKeyword: opsanyViewKeyword.value,
        selectedNode: { ...selectedOpsanyViewNode.value },
      },
      model: {
        resourceFilters: { ...modelResourceFilters },
        treeMode: modelCatalogTreeMode.value,
        treeContext: modelCatalogTreeContext.value ? { ...modelCatalogTreeContext.value } : null,
        treeKeyword: modelCatalogTreeKeyword.value,
        expandedKeys: Array.from(expandedModelCatalogTreeKeys.value),
        collapsedKeys: Array.from(collapsedModelCatalogTreeKeys.value),
        groupKey: activeModelGroupKey.value,
        modelKeyword: opsanyModelKeyword.value,
        modelStatus: opsanyModelStatus.value,
        selectedModelId: selectedModelId.value,
      },
    }))
  } catch (error) {
    console.warn('save CMDB UI state failed', error)
  }
}

function scheduleCmdbUiStateSave() {
  if (typeof window === 'undefined') return
  if (cmdbUiStateSaveTimer) window.clearTimeout(cmdbUiStateSaveTimer)
  cmdbUiStateSaveTimer = window.setTimeout(saveCmdbUiState, 120)
}

function restoreCmdbUiState() {
  if (typeof window === 'undefined') return
  try {
    const saved = JSON.parse(window.localStorage.getItem(cmdbUiStateStorageKey) || 'null')
    if (!saved || typeof saved !== 'object') return
    const ledgerState = saved.ledger || {}
    const viewState = saved.views || {}
    const modelState = saved.model || {}
    // 旧缓存首次切换到业务环境默认值，后续仍记住用户主动选择的维度。
    const restoreLedgerTree = saved.assetTreeDefault === 'business' || ledgerState.viewMode === 'business'
    const restoreModelTree = saved.assetTreeDefault === 'business' || modelState.treeMode === 'business'
    applySavedFilterValues(ledgerFilters, ledgerState.filters)
    applySavedFilterValues(viewFilters, viewState.filters)
    applySavedFilterValues(modelResourceFilters, modelState.resourceFilters)
    if (restoreLedgerTree) {
      if (['cloud', 'business'].includes(ledgerState.viewMode)) ledgerViewMode.value = ledgerState.viewMode
      if (ledgerState.treeContext && typeof ledgerState.treeContext === 'object') ledgerTreeContext.value = { ...ledgerState.treeContext }
      if (typeof ledgerState.treeKeyword === 'string') ledgerTreeKeyword.value = ledgerState.treeKeyword
      if (Array.isArray(ledgerState.expandedKeys)) expandedLedgerTreeKeys.value = new Set(ledgerState.expandedKeys)
      if (Array.isArray(ledgerState.collapsedKeys)) collapsedLedgerTreeKeys.value = new Set(ledgerState.collapsedKeys)
    }
    if (['application', 'host', 'physical'].includes(viewState.mode)) viewMode.value = viewState.mode
    if (typeof viewState.keyword === 'string') applicationViewKeyword.value = viewState.keyword
    if (typeof viewState.risk === 'string') applicationViewRisk.value = viewState.risk
    if (typeof viewState.owner === 'string') applicationViewOwner.value = viewState.owner
    if (typeof viewState.team === 'string') applicationViewTeam.value = viewState.team
    if (typeof viewState.tier === 'string') applicationViewTier.value = viewState.tier
    if (typeof viewState.treeKeyword === 'string') opsanyViewKeyword.value = viewState.treeKeyword
    if (viewState.selectedNode && typeof viewState.selectedNode === 'object') selectedOpsanyViewNode.value = { ...viewState.selectedNode }
    if (restoreModelTree) {
      if (['cloud', 'business'].includes(modelState.treeMode)) modelCatalogTreeMode.value = modelState.treeMode
      if (modelState.treeContext && typeof modelState.treeContext === 'object') modelCatalogTreeContext.value = { ...modelState.treeContext }
      if (typeof modelState.treeKeyword === 'string') modelCatalogTreeKeyword.value = modelState.treeKeyword
      if (Array.isArray(modelState.expandedKeys)) expandedModelCatalogTreeKeys.value = new Set(modelState.expandedKeys)
      if (Array.isArray(modelState.collapsedKeys)) collapsedModelCatalogTreeKeys.value = new Set(modelState.collapsedKeys)
    }
    if (typeof modelState.groupKey === 'string') activeModelGroupKey.value = modelState.groupKey
    if (typeof modelState.modelKeyword === 'string') opsanyModelKeyword.value = modelState.modelKeyword
    if (typeof modelState.modelStatus === 'string') opsanyModelStatus.value = modelState.modelStatus
    if (modelState.selectedModelId !== undefined && modelState.selectedModelId !== null) selectedModelId.value = String(modelState.selectedModelId)
  } catch (error) {
    console.warn('restore CMDB UI state failed', error)
  }
}

const modelResourceFilters = reactive({
  search: '',
  asset_search: '',
  attribute_search: '',
  ci_type: '',
  service_type: '',
  provider: '',
  expiry_risk: '',
  source_account: '',
  source_account_missing: '',
  source_region: '',
  source_unique_id: '',
  vsphere_cluster: '',
  vsphere_host: '',
  availability_zone: '',
  engine: '',
  vpc_id: '',
  network_type: '',
  storage_class: '',
  acl: '',
  sync_status: '',
  idc: '',
  rack: '',
  lifecycle_status: '',
  status: '',
  tags: '',
  source_type: '',
  ownership: '',
})

const topologyFilters = reactive({
  ci_type: '',
  business_line: '',
  environment: '',
  scope: 'neighbors',
})

const topologyScopeOptions = [
  { label: '带邻居', value: 'neighbors' },
  { label: '精确范围', value: 'exact' },
]

const requestFilters = reactive({
  status: '',
  business_line: '',
  search: '',
})

const auditFilters = reactive({
  search: '',
  action: '',
  operator: '',
  source: '',
  range: [],
})

const thresholdFilters = reactive({
  resource_type: '',
  metric: '',
  enabled: '',
})

const thresholdPolicyForm = reactive({
  resource_type: '',
  metric: 'cpu_usage',
  normal_threshold: 70,
  warning_threshold: 85,
  critical_threshold: 95,
  exceeded_threshold: 100,
  enabled: true,
})

const metricForm = reactive({
  ci: '',
  metric: 'cpu_usage',
  value: 0,
  unit: '%',
  usage_percent: 0,
  source: 'manual',
})

const requestDialogVisible = ref(false)
const requestActionVisible = ref(false)
const requestActionType = ref('')
const requestActionRow = ref(null)
const requestActionNote = ref('')
const requestProvisioningOptions = ref({ providers: [], credentials: [] })
const requestProvisioningOptionsLoading = ref(false)
const requestActionDeliveryForm = reactive({
  hostname: '',
  ip_address: '',
  os_type: 'Linux',
  admin_user: '',
  instance_type: '',
  host_list_text: '',
})
const requestForm = reactive({
  title: '',
  resource_type: 'ecs',
  specification: '2C4G',
  business_line: '',
  environment: '',
  priority: 'medium',
  quantity: 1,
  reason: '',
  host_list_text: '',
  specs: {
    provisioning_mode: 'cloud',
    provider: 'aliyun',
    cloud_credential_id: '',
    region: '',
    zone: '',
    instance_name_prefix: '',
    hostname: '',
    ip_address: '',
    os_type: 'Linux',
    admin_user: '',
    instance_type: '',
    image_id: '',
    security_group_id: '',
    vswitch_id: '',
    key_pair_name: '',
    system_disk_category: 'cloud_essd',
    system_disk_size: 40,
    flavor_ref: '',
    vpc_id: '',
    subnet_id: '',
    key_name: '',
    root_volume_type: 'GPSSD',
    root_volume_size: 40,
    template_name: '',
    datastore_name: '',
    cluster_name: '',
    folder_name: '',
    cpu: 2,
    memory_gb: 4,
    power_on: true,
    resource_name: '',
    resource_id: '',
    instance_class: '',
    capacity: '',
    extra_requirements: '',
  },
})

const resourceNodeForm = reactive({
  name: '',
  node_type: 'biz',
  parent: '',
  sort_order: 0,
})

const tagForm = reactive({
  name: '',
  category: '',
  color: '#245bdb',
  description: '',
  is_active: true,
})

const authorizationForm = reactive({
  name: '',
  principal_type: 'user',
  principal: '',
  permission: 'view',
  business_line: '',
  environment: '',
  ci_type: '',
  description: '',
  is_active: true,
})

const completionForm = reactive({
  business_line: '',
  environment: '',
  admin_user: '',
  department: '',
  attributesText: '{}',
  note: '关键字段已补齐',
})

const completionAssignForm = reactive({
  assigned_to: '',
  note: '',
})

const ciDialogVisible = ref(false)
const ciEditingId = ref(null)
const ciForm = reactive({
  name: '',
  ci_type: '',
  ci_type_code: '',
  ci_type_group_code: '',
  business_node: '',
  business_line: '',
  department: '',
  environment_node: '',
  environment: '',
  resource_node: '',
  admin_user: '',
  status: 'active',
  monthly_cost: null,
  source_account: '',
  source_region: '',
  description: '',
  tags: [],
  baseAttributes: {},
  attributeValues: {},
})

const assetPasswordForm = reactive({
  username: '',
  password: '',
  remark: '',
})
const assetPasswordVerificationForm = reactive({
  currentPassword: '',
})

const bulkLedgerDialogVisible = ref(false)
const bulkLedgerForm = reactive({
  business_node: '',
  business_line: '',
  environment_node: '',
  environment: '',
  admin_user: '',
  department: '',
  status: '',
  tag_action: 'append',
  tag_ids: [],
  note: '批量维护资产台账',
})

const bulkImportVisible = ref(false)
const bulkImportLoading = ref(false)
const bulkImportPreview = ref({ summary: {}, records: [] })
const bulkImportFileInput = ref(null)
const bulkImportFileName = ref('')
const bulkImportPreviewReady = ref(false)
const bulkImportTemplateTypeIds = ref([])
const bulkImportForm = reactive({
  name: '资产台账批量导入',
  source_type: 'manual_import',
  format: 'csv',
  text: '',
})

const relationForm = reactive({
  direction: 'outgoing',
  relation_type: 'depends_on',
  targets: [],
  description: '',
})
const relationEvidenceSourceOptions = [
  { label: '人工维护', value: 'manual' },
  { label: '批量导入', value: 'import' },
  { label: '同步发现', value: 'sync' },
  { label: '治理建议', value: 'governance' },
  { label: '系统联动', value: 'system' },
]
const baseRelationTypeOptions = [
  { label: '依赖 depends_on', value: 'depends_on' },
  { label: '运行于 runs_on', value: 'runs_on' },
  { label: '连接 connects_to', value: 'connects_to' },
]
const relationTypeOptions = computed(() => {
  const grouped = new Map()
  relationRules.value
    .filter((rule) => rule.direction === relationForm.direction)
    .forEach((rule) => {
      const item = grouped.get(rule.relation_type) || { label: relationTypeLabel(rule.relation_type), value: rule.relation_type, peers: [] }
      if (rule.peer_type_name && !item.peers.includes(rule.peer_type_name)) item.peers.push(rule.peer_type_name)
      grouped.set(rule.relation_type, item)
    })
  return Array.from(grouped.values()).map((item) => ({
    ...item,
    label: relationFlowLabel({
      relation_type: item.value,
      peer_type_name: item.peers.join(' / ') || '目标资源',
      direction: relationForm.direction,
    }),
  }))
})
const relationDirectionOptions = computed(() => Array.from(new Set(relationRules.value.map((rule) => rule.direction))))
const activeRelationRule = computed(() => {
  const rule = relationRules.value.find((item) => item.direction === relationForm.direction && item.relation_type === relationForm.relation_type)
  return rule ? { ...rule, relation_type_label: relationTypeLabel(rule.relation_type), flow_label: relationFlowLabel(rule) } : null
})

function relationFlowLabel(rule = {}) {
  const currentName = ciDetail.value?.ci_type_name || '当前资源'
  const peerName = rule.peer_type_name || '目标资源'
  const relation = relationTypeLabel(rule.relation_type)
  return rule.direction === 'incoming'
    ? `${peerName} ${relation} ${currentName}`
    : `${currentName} ${relation} ${peerName}`
}

const syncJobDialogVisible = ref(false)
const syncJobEditingId = ref(null)
const phaseOneSyncTemplates = [
  {
    key: 'aliyun_ecs',
    label: '阿里云 ECS 自动注册',
    desc: '引用多云账号 cloud_account_id，自动注册云主机。',
    name: '阿里云 ECS 自动注册',
    source_type: 'aliyun_ecs',
    mode: 'scheduled',
    full_sync: true,
    config: { connector: 'aliyun', resource_type: 'ecs', target_ci_type_code: 'CLOUD_SERVER', unique_key: 'instance_id', cloud_account_id: '', collection_enabled: true, interval_minutes: 60, schedule_label: '每 60 分钟' },
  },
  {
    key: 'aliyun_rds',
    label: '阿里云 RDS 自动注册',
    desc: '注册阿里云 MySQL/RDS 到数据库模型。',
    name: '阿里云 RDS 自动注册',
    source_type: 'aliyun_rds',
    mode: 'scheduled',
    full_sync: true,
    config: { connector: 'aliyun', resource_type: 'rds', target_ci_type_code: 'MYSQL', unique_key: 'instance_id', cloud_account_id: '', collection_enabled: true, interval_minutes: 120, schedule_label: '每 120 分钟' },
  },
  {
    key: 'aliyun_redis',
    label: '阿里云 Redis 自动注册',
    desc: '注册阿里云 Redis/Tair 到 Redis 模型。',
    name: '阿里云 Redis 自动注册',
    source_type: 'aliyun_redis',
    mode: 'scheduled',
    full_sync: true,
    config: { connector: 'aliyun', resource_type: 'redis', target_ci_type_code: 'REDIS', unique_key: 'instance_id', cloud_account_id: '', collection_enabled: true, interval_minutes: 120, schedule_label: '每 120 分钟' },
  },
  {
    key: 'aliyun_mongodb',
    label: '阿里云 MongoDB 自动注册',
    desc: '注册阿里云 MongoDB 到 MongoDB 模型。',
    name: '阿里云 MongoDB 自动注册',
    source_type: 'aliyun_mongodb',
    mode: 'scheduled',
    full_sync: true,
    config: { connector: 'aliyun', resource_type: 'mongodb', target_ci_type_code: 'MONGODB', unique_key: 'instance_id', cloud_account_id: '', collection_enabled: true, interval_minutes: 120, schedule_label: '每 120 分钟' },
  },
  {
    key: 'aliyun_kafka',
    label: '阿里云 Kafka 自动注册',
    desc: '注册阿里云 Kafka 到消息中间件模型。',
    name: '阿里云 Kafka 自动注册',
    source_type: 'aliyun_kafka',
    mode: 'scheduled',
    full_sync: true,
    config: { connector: 'aliyun', resource_type: 'kafka', target_ci_type_code: 'KAFKA', unique_key: 'instance_id', cloud_account_id: '', collection_enabled: true, interval_minutes: 120, schedule_label: '每 120 分钟' },
  },
  {
    key: 'aliyun_rocketmq',
    label: '阿里云 RocketMQ 自动注册',
    desc: '注册阿里云 RocketMQ 到消息中间件模型。',
    name: '阿里云 RocketMQ 自动注册',
    source_type: 'aliyun_rocketmq',
    mode: 'scheduled',
    full_sync: true,
    config: { connector: 'aliyun', resource_type: 'rocketmq', target_ci_type_code: 'ROCKETMQ', unique_key: 'instance_id', cloud_account_id: '', collection_enabled: true, interval_minutes: 120, schedule_label: '每 120 分钟' },
  },
  {
    key: 'aliyun_oss',
    label: '阿里云 OSS 自动注册',
    desc: '注册阿里云 OSS Bucket 到对象存储模型。',
    name: '阿里云 OSS 自动注册',
    source_type: 'aliyun_oss',
    mode: 'scheduled',
    full_sync: true,
    config: { connector: 'aliyun', resource_type: 'oss', target_ci_type_code: 'OBJECT_STORAGE', unique_key: 'bucket', cloud_account_id: '', collection_enabled: true, interval_minutes: 180, schedule_label: '每 180 分钟' },
  },
  {
    key: 'aliyun_slb',
    label: '阿里云 SLB 自动注册',
    desc: '注册阿里云 SLB 到负载均衡模型。',
    name: '阿里云 SLB 自动注册',
    source_type: 'aliyun_slb',
    mode: 'scheduled',
    full_sync: true,
    config: { connector: 'aliyun', resource_type: 'slb', target_ci_type_code: 'LOAD_BALANCER', unique_key: 'instance_id', cloud_account_id: '', collection_enabled: true, interval_minutes: 120, schedule_label: '每 120 分钟' },
  },
  {
    key: 'huaweicloud_ecs',
    label: '华为云 ECS 自动注册',
    desc: '引用多云账号 cloud_account_id，自动注册云主机。',
    name: '华为云 ECS 自动注册',
    source_type: 'huaweicloud_ecs',
    mode: 'scheduled',
    full_sync: true,
    config: { connector: 'huaweicloud', resource_type: 'ecs', target_ci_type_code: 'CLOUD_SERVER', unique_key: 'instance_id', cloud_account_id: '', collection_enabled: true, interval_minutes: 60, schedule_label: '每 60 分钟' },
  },
  {
    key: 'huaweicloud_rds',
    label: '华为云 RDS 自动注册',
    desc: '引用多云账号 cloud_account_id，注册华为云 RDS 到数据库模型。',
    name: '华为云 RDS 自动注册',
    source_type: 'huaweicloud_rds',
    mode: 'scheduled',
    full_sync: true,
    config: { connector: 'huaweicloud', resource_type: 'rds', target_ci_type_code: 'MYSQL', unique_key: 'instance_id', cloud_account_id: '', collection_enabled: true, interval_minutes: 120, schedule_label: '每 120 分钟' },
  },
  {
    key: 'huaweicloud_redis',
    label: '华为云 Redis 自动注册',
    desc: '引用多云账号 cloud_account_id，注册华为云 Redis 到缓存模型。',
    name: '华为云 Redis 自动注册',
    source_type: 'huaweicloud_redis',
    mode: 'scheduled',
    full_sync: true,
    config: { connector: 'huaweicloud', resource_type: 'redis', target_ci_type_code: 'REDIS', unique_key: 'instance_id', cloud_account_id: '', collection_enabled: true, interval_minutes: 120, schedule_label: '每 120 分钟' },
  },
  {
    key: 'vsphere_vm',
    label: 'vSphere 虚拟机与物理机自动注册',
    desc: '连接私有云账号后自动注册虚拟机与 ESXi 宿主机资产。',
    name: 'vSphere 虚拟机与物理机自动注册',
    source_type: 'vsphere_vm',
    mode: 'scheduled',
    full_sync: true,
    config: { connector: 'vsphere', resource_type: 'vm', target_ci_type_code: 'VIRTUAL_MACHINE', unique_key: 'instance_id', cloud_account_id: '', host: '', username: '', auth_ref: 'SXDEVOPS_VSPHERE_PROD', collection_enabled: true, interval_minutes: 60, schedule_label: '每 60 分钟' },
  },
  {
    key: 'third_party_service',
    label: '第三方服务手工登记',
    desc: '和风天气、高德地图等外部服务登记到第三方服务 CI。',
    name: '第三方服务台账导入',
    source_type: 'third_party_import',
    mode: 'import',
    full_sync: false,
    config: {
      connector: 'manual_import',
      target_ci_type_code: 'THIRD_PARTY_SERVICE',
      unique_key: 'provider',
      sensitive_fields_policy: '不保存密钥明文，仅登记账号和服务到期信息。',
      required_fields: ['provider'],
      items: [
        {
          ci_type_code: 'THIRD_PARTY_SERVICE',
          name: '和风天气-生产账号',
          source_unique_id: 'heweather-prod-account',
          business_line: '电商业务线',
          environment: 'prod',
          admin_user: '应用运维',
          attributes: {
            provider: '和风天气',
            service_type: '天气 API',
            account_subject: '生产主体',
            backup_plan: '控制台导出应用配置，每季度归档',
            contract_no: 'HT-WEATHER-2026-001',
            service_expiry_date: '2026-12-31',
            service_expire_warning_days: 30,
          },
        },
        {
          ci_type_code: 'THIRD_PARTY_SERVICE',
          name: '高德地图-生产账号',
          source_unique_id: 'amap-prod-account',
          business_line: '电商业务线',
          environment: 'prod',
          admin_user: '应用运维',
          attributes: {
            provider: '高德地图',
            service_type: '地图 API',
            account_subject: '生产主体',
            backup_plan: '控制台导出 Key 与额度配置，每季度归档',
            contract_no: 'HT-AMAP-2026-001',
            service_expiry_date: '2026-11-30',
            service_expire_warning_days: 30,
          },
        },
      ],
    },
  },
]
const aliyunExtendedSyncTemplates = [
  ['aliyun_ack', 'ACK K8s 集群', '采集阿里云 ACK 集群到 K8S_CLUSTER 模型。', 'ack', 'K8S_CLUSTER', 'cluster_id', 120],
  ['aliyun_disk', '云盘', '采集阿里云云盘到块存储模型。', 'disk', 'BLOCK_STORAGE', 'volume_id', 180],
  ['aliyun_nas', 'NAS 文件存储', '采集阿里云 NAS 文件系统到文件存储模型。', 'nas', 'FILE_STORAGE', 'filesystem_id', 180],
  ['aliyun_clickhouse', 'ClickHouse', '采集阿里云 ClickHouse 集群到 ClickHouse 模型。', 'clickhouse', 'CLICKHOUSE', 'cluster_id', 180],
  ['aliyun_hologres', 'Hologres', '采集阿里云 Hologres 实例到 Hologres 模型。', 'hologres', 'HOLOGRES', 'instance_id', 180],
  ['aliyun_maxcompute', 'MaxCompute', '采集阿里云 MaxCompute 项目到 MaxCompute 模型。', 'maxcompute', 'MAXCOMPUTE', 'project_name', 180],
  ['aliyun_dataworks', 'DataWorks', '采集阿里云 DataWorks 工作空间到 DataWorks 模型。', 'dataworks', 'DATAWORKS', 'workspace_id', 180],
  ['aliyun_nat_gateway', 'NAT 网关', '采集阿里云 NAT 网关到 NAT_GATEWAY 模型。', 'nat_gateway', 'NAT_GATEWAY', 'instance_id', 120],
  ['aliyun_eip', 'EIP 弹性公网 IP', '采集阿里云弹性公网 IP 到弹性 IP 模型。', 'eip', 'ELASTIC_IP', 'allocation_id', 120],
  ['aliyun_elasticsearch', 'Elasticsearch', '采集阿里云 Elasticsearch 集群到 Elasticsearch 模型。', 'elasticsearch', 'ELASTICSEARCH', 'cluster_id', 180],
]
phaseOneSyncTemplates.push(...aliyunExtendedSyncTemplates.map(([key, label, desc, resourceType, targetType, uniqueKey, intervalMinutes]) => ({
  key,
  label: `阿里云 ${label} 自动注册`,
  desc,
  name: `阿里云 ${label} 自动注册`,
  source_type: key,
  mode: 'scheduled',
  full_sync: true,
  config: {
    connector: 'aliyun',
    resource_type: resourceType,
    target_ci_type_code: targetType,
    unique_key: uniqueKey,
    cloud_account_id: '',
    collection_enabled: true,
    interval_minutes: intervalMinutes,
    schedule_label: `每 ${intervalMinutes} 分钟`,
  },
})))
const huaweiExtendedSyncTemplates = [
  ['huaweicloud_eip', 'EIP 弹性公网 IP', '采集华为云弹性公网 IP 到弹性 IP 模型。', 'eip', 'ELASTIC_IP', 'allocation_id', 120],
  ['huaweicloud_obs', 'OBS 对象存储', '采集华为云 OBS Bucket 到对象存储模型。', 'obs', 'OBJECT_STORAGE', 'bucket', 180],
]
phaseOneSyncTemplates.push(...huaweiExtendedSyncTemplates.map(([key, label, desc, resourceType, targetType, uniqueKey, intervalMinutes]) => ({
  key,
  label: `华为云 ${label} 自动注册`,
  desc,
  name: `华为云 ${label} 自动注册`,
  source_type: key,
  mode: 'scheduled',
  full_sync: true,
  config: {
    connector: 'huaweicloud',
    resource_type: resourceType,
    target_ci_type_code: targetType,
    unique_key: uniqueKey,
    cloud_account_id: '',
    collection_enabled: true,
    interval_minutes: intervalMinutes,
    schedule_label: `每 ${intervalMinutes} 分钟`,
  },
})))
const defaultSyncFieldMappings = [
  { target: 'business_line', source: 'business_line', default: '', required: false },
  { target: 'admin_user', source: 'owner', default: '', required: false },
  { target: 'attributes.department', source: 'department', default: '', required: false },
]
const syncSourceTypeDisplayMap = Object.fromEntries(
  phaseOneSyncTemplates.map(item => [item.source_type, {
    label: item.label,
    desc: item.desc,
    name: item.name,
  }]),
)
function syncSourceTypeLabel(sourceType, fallback = '') {
  const key = String(sourceType || '').trim()
  return syncSourceTypeDisplayMap[key]?.label || fallback || key || '-'
}
const syncJobConfigBase = reactive({})
const syncJobForm = reactive({
  name: '',
  templateKey: '',
  connector: '',
  source_type: 'manual_import',
  mode: 'manual',
  dry_run: false,
  full_sync: false,
  collection_enabled: false,
  resource_type: '',
  target_ci_type_code: '',
  unique_key: '',
  interval_minutes: 60,
  cloud_account_id: '',
  vsphere_host: '',
  vsphere_username: '',
  vsphere_auth_ref: 'SXDEVOPS_VSPHERE_PROD',
})
const syncFieldMappings = ref([])
const cloudCredentials = ref([])
const cloudCredentialLoading = ref(false)
const cloudCredentialLoaded = ref(false)
const syncAccountConfiguring = ref(false)
const syncAccountManualSyncRunning = computed(() => syncAccountConfiguring.value || syncJobs.value.some(job => job.status === 'running'))
const publicCloudProviderOptions = [
  { value: 'aliyun', label: '阿里云' },
  { value: 'huawei', label: '华为云' },
]
const privateCloudProviderOptions = [
  { value: 'vsphere', label: 'VMware vSphere / ESXi' },
]
const privateCloudVersionOptions = [
  { value: 'esxi_8_0_2', label: 'ESXi 8.0.2' },
]
const defaultPrivateCloudVersion = privateCloudVersionOptions[0].value
const publicCloudProviderSet = new Set(publicCloudProviderOptions.map(item => item.value))
const privateCloudProviderSet = new Set(privateCloudProviderOptions.map(item => item.value))
const cloudProductKeyAliases = {
  aliyun_nfs: 'aliyun_nas',
}
const obsoleteSyncSourceTypes = new Set(['aliyun_security_group'])
const cloudCredentialKind = ref('public')
const cloudProductOptionsByProvider = {
  aliyun: [
    { key: 'aliyun_ecs', label: 'ECS 云主机', desc: '服务器资源' },
    { key: 'aliyun_rds', label: 'RDS 数据库', desc: 'MySQL/RDS' },
    { key: 'aliyun_redis', label: 'Redis 缓存', desc: 'Redis/Tair' },
    { key: 'aliyun_mongodb', label: 'MongoDB', desc: '文档数据库' },
    { key: 'aliyun_kafka', label: 'Kafka', desc: '消息队列' },
    { key: 'aliyun_rocketmq', label: 'RocketMQ', desc: '消息队列' },
    { key: 'aliyun_oss', label: 'OSS 对象存储', desc: 'Bucket' },
    { key: 'aliyun_slb', label: 'SLB 负载均衡', desc: '入口负载' },
    { key: 'aliyun_ack', label: 'ACK K8s 集群', desc: 'Kubernetes' },
    { key: 'aliyun_disk', label: '云盘', desc: '块存储' },
    { key: 'aliyun_nas', label: 'NAS 文件存储', desc: '文件存储' },
    { key: 'aliyun_elasticsearch', label: 'Elasticsearch', desc: '搜索集群' },
    { key: 'aliyun_clickhouse', label: 'ClickHouse', desc: 'OLAP' },
    { key: 'aliyun_hologres', label: 'Hologres', desc: '数仓' },
    { key: 'aliyun_maxcompute', label: 'MaxCompute', desc: 'ODPS' },
    { key: 'aliyun_dataworks', label: 'DataWorks', desc: '工作空间' },
    { key: 'aliyun_nat_gateway', label: 'NAT 网关', desc: '出口网关' },
    { key: 'aliyun_eip', label: 'EIP 弹性公网 IP', desc: '公网 IP' },
  ],
  huawei: [
    { key: 'huaweicloud_ecs', label: 'ECS 云主机', desc: '服务器资源' },
    { key: 'huaweicloud_rds', label: 'RDS 数据库', desc: 'MySQL/RDS' },
    { key: 'huaweicloud_redis', label: 'Redis 缓存', desc: 'DCS Redis' },
    { key: 'huaweicloud_eip', label: 'EIP 弹性公网 IP', desc: '公网 IP' },
    { key: 'huaweicloud_obs', label: 'OBS 对象存储', desc: 'Bucket' },
  ],
}
cloudProductOptionsByProvider.huaweicloud = cloudProductOptionsByProvider.huawei
const cloudProductBackfillKeysByProvider = {
  aliyun: [
    'aliyun_ack',
    'aliyun_disk',
    'aliyun_nas',
    'aliyun_elasticsearch',
    'aliyun_clickhouse',
    'aliyun_hologres',
    'aliyun_maxcompute',
    'aliyun_dataworks',
    'aliyun_nat_gateway',
    'aliyun_eip',
  ],
  huawei: ['huaweicloud_eip', 'huaweicloud_obs'],
  huaweicloud: ['huaweicloud_eip', 'huaweicloud_obs'],
}
const cloudCredentialForm = reactive({
  provider: 'aliyun',
  name: '',
  account_id: '',
  auth_mode: 'aksk',
  access_key_id: '',
  access_key_secret: '',
  project_id: '',
  role_arn: '',
  external_id: '',
  default_region: 'cn-hangzhou',
  owner: '',
  description: '',
  is_enabled: true,
  demo_mode: false,
  private_cloud_version: defaultPrivateCloudVersion,
  sync_product_keys: [],
  prometheus_metrics_enabled: true,
  metric_datasource_id: '',
})
const metricDatasources = ref([])
const metricDatasourceLoading = ref(false)
const cloudMetricDatasourceOptions = computed(() => metricDatasources.value.filter(item => item?.is_enabled !== false && item?.provider === 'prometheus'))
const activeCloudCredentialProviderOptions = computed(() => cloudCredentialKind.value === 'private' ? privateCloudProviderOptions : publicCloudProviderOptions)
const isPublicCloudCredentialForm = computed(() => publicCloudProviderSet.has(cloudCredentialForm.provider))
const cloudCredentialProductOptions = computed(() => cloudProductOptionsByProvider[cloudCredentialForm.provider] || [])
const cloudCredentialDialogTitle = computed(() => {
  if (cloudCredentialEditingId.value) return cloudCredentialForm.provider === 'vsphere' ? '编辑私有云账号' : '编辑公有云账号'
  return cloudCredentialForm.provider === 'vsphere' ? '添加私有云账号' : '添加公有云账号'
})
const cloudCredentialAccountIdLabel = computed(() => cloudCredentialForm.provider === 'vsphere' ? 'vCenter / ESXi 地址' : '账号 ID')
const cloudCredentialDefaultRegionLabel = computed(() => cloudCredentialForm.provider === 'vsphere' ? '私有云标识' : '默认地域')
const cloudCredentialAccessIdLabel = computed(() => cloudCredentialForm.provider === 'vsphere' ? '用户名' : 'AccessKey ID')
const cloudCredentialSecretLabel = computed(() => {
  if (cloudCredentialForm.provider === 'vsphere') return '密码'
  if (cloudCredentialForm.provider === 'huawei') return 'Secret Key'
  return 'AccessKey Secret'
})
const cloudCredentialDescriptionPlaceholder = computed(() => cloudCredentialForm.provider === 'vsphere' ? '例如 vcsa-prod / VMware ESXi 8.0.2' : '例如生产账号 / 负责人 / 用途说明')

const syncFilters = reactive({
  search: '',
  source_type: '',
  status: '',
})
const syncFocusTypes = ref([])
const syncFocusContext = ref(null)
const syncAccountContext = ref(null)

const syncResolveForm = reactive({
  ci_id: '',
  replace_existing: false,
  rebind: false,
  note: '',
})

const sourceMappingFilters = reactive({
  search: '',
  source_type: '',
  sync_status: '',
})

const sourceMappingForm = reactive({
  ci: '',
  source_type: '',
  source_account: '',
  source_region: '',
  source_unique_id: '',
  sync_status: 'success',
  rawPayloadText: '{}',
})

const sourceMappingStatusActions = [
  { value: 'success', label: '标记成功', text: '成功', type: 'success' },
  { value: 'failed', label: '标记失败', text: '失败', type: 'warning' },
  { value: 'missing', label: '标记来源缺失', text: '来源缺失', type: 'warning' },
  { value: 'conflict', label: '标记冲突', text: '冲突', type: 'warning' },
]

function createCmdbIcon(name, renderChildren) {
  return defineComponent({
    name,
    setup() {
      return () => h('svg', {
        viewBox: '0 0 24 24',
        width: '1em',
        height: '1em',
        fill: 'none',
        stroke: 'currentColor',
        'stroke-width': 1.7,
        'stroke-linecap': 'round',
        'stroke-linejoin': 'round',
        'aria-hidden': 'true',
      }, renderChildren())
    },
  })
}

const DatabaseIcon = createCmdbIcon('DatabaseIcon', () => [
  h('ellipse', { cx: 12, cy: 5.8, rx: 6.7, ry: 2.8 }),
  h('path', { d: 'M5.3 5.8v10.4c0 1.6 3 2.9 6.7 2.9s6.7-1.3 6.7-2.9V5.8' }),
  h('path', { d: 'M5.3 10.5c0 1.6 3 2.9 6.7 2.9s6.7-1.3 6.7-2.9' }),
  h('path', { d: 'M5.3 15.1c0 1.6 3 2.9 6.7 2.9s6.7-1.3 6.7-2.9' }),
  h('path', { d: 'M8.6 7.8h6.8' }),
])

const QueueIcon = createCmdbIcon('QueueIcon', () => [
  h('rect', { x: 4.5, y: 5.3, width: 6.2, height: 4.2, rx: 1.2 }),
  h('rect', { x: 8.7, y: 10.1, width: 6.2, height: 4.2, rx: 1.2 }),
  h('rect', { x: 12.9, y: 14.9, width: 6.2, height: 4.2, rx: 1.2 }),
  h('path', { d: 'M10.7 7.4h2.8' }),
  h('path', { d: 'M12.4 5.9l1.4 1.5-1.4 1.5' }),
  h('path', { d: 'M14.9 12.2h2.8' }),
  h('path', { d: 'M16.6 10.7l1.4 1.5-1.4 1.5' }),
])

const CacheIcon = createCmdbIcon('CacheIcon', () => [
  h('ellipse', { cx: 12, cy: 6.4, rx: 6.4, ry: 2.6 }),
  h('path', { d: 'M5.6 6.4v4.7c0 1.4 2.9 2.6 6.4 2.6s6.4-1.2 6.4-2.6V6.4' }),
  h('path', { d: 'M5.6 11.1v4.5c0 1.4 2.9 2.6 6.4 2.6s6.4-1.2 6.4-2.6v-4.5' }),
  h('path', { d: 'M8.4 9.2c1 .5 2.2.7 3.6.7s2.6-.2 3.6-.7' }),
  h('path', { d: 'M12.9 10.7 10.5 14h2.1l-1.1 3 3.1-4.1h-2.1l.4-2.2Z', fill: 'currentColor', stroke: 'none' }),
])

const modelDialogVisible = ref(false)
const modelConfigDrawerVisible = ref(false)
const modelEditingId = ref(null)
const selectedModelId = ref('')
const modelForm = reactive({
  name: '',
  code: '',
  group: '',
  icon: 'SetUp',
  color: '#3b82f6',
  description: '',
})

const modelIconOptions = [
  { value: 'Monitor', label: '主机', component: Monitor, color: '#2563eb' },
  { value: 'Cpu', label: '物理设备', component: Cpu, color: '#475569' },
  { value: 'Platform', label: '云主机', component: Platform, color: '#0ea5e9' },
  { value: 'MostlyCloudy', label: '云资源', component: MostlyCloudy, color: '#0284c7' },
  { value: 'OfficeBuilding', label: '机房', component: OfficeBuilding, color: '#334155' },
  { value: 'House', label: '机柜/区域', component: House, color: '#64748b' },
  { value: 'Connection', label: '网络', component: Connection, color: '#16a34a' },
  { value: 'Switch', label: '交换/负载', component: Switch, color: '#059669' },
  { value: 'Database', label: '数据库', component: DatabaseIcon, color: '#245bdb' },
  { value: 'Document', label: '文档数据库', component: Document, color: '#16a34a' },
  { value: 'Cache', label: '缓存', component: CacheIcon, color: '#0ea5e9' },
  { value: 'MessageQueue', label: '消息队列', component: QueueIcon, color: '#7c3aed' },
  { value: 'FolderOpened', label: '对象存储', component: Files, color: '#06b6d4' },
  { value: 'Files', label: '文件存储', component: FolderOpened, color: '#0891b2' },
  { value: 'Grid', label: '应用系统', component: Grid, color: '#3b82f6' },
  { value: 'Service', label: '第三方服务', component: Service, color: '#0f766e' },
  { value: 'Key', label: '账号密钥', component: Key, color: '#ca8a04' },
  { value: 'Link', label: '域名/API', component: Link, color: '#0f766e' },
  { value: 'Guide', label: '网关入口', component: Guide, color: '#0891b2' },
  { value: 'Box', label: '容器', component: Box, color: '#22c55e' },
  { value: 'Ship', label: 'Kubernetes', component: Ship, color: '#2563eb' },
  { value: 'DataAnalysis', label: '数据分析', component: DataAnalysis, color: '#9333ea' },
  { value: 'TrendCharts', label: '监控指标', component: TrendCharts, color: '#0ea5e9' },
  { value: 'Odometer', label: '资产水位', component: Odometer, color: '#f59e0b' },
  { value: 'Lock', label: '安全权限', component: Lock, color: '#dc2626' },
  { value: 'User', label: '人员账号', component: User, color: '#6366f1' },
  { value: 'SetUp', label: '通用配置', component: SetUp, color: '#64748b' },
  { value: 'CollectionTag', label: '标签分类', component: CollectionTag, color: '#16a34a' },
  { value: 'DocumentChecked', label: '证书/文档', component: DocumentChecked, color: '#8b5cf6' },
  { value: 'Postcard', label: '合同资质', component: Postcard, color: '#ca8a04' },
  { value: 'Share', label: '资源关系', component: Share, color: '#14b8a6' },
  { value: 'Location', label: '地域位置', component: Location, color: '#0f766e' },
  { value: 'Compass', label: '可用区', component: Compass, color: '#0891b2' },
  { value: 'Goods', label: '资产物品', component: Goods, color: '#475569' },
  { value: 'TakeawayBox', label: '软件包', component: TakeawayBox, color: '#7c3aed' },
  { value: 'UploadFilled', label: '同步采集', component: UploadFilled, color: '#245bdb' },
  { value: 'Folder', label: '目录', component: Folder, color: '#64748b' },
  { value: 'FolderChecked', label: '归档资产', component: FolderChecked, color: '#16a34a' },
  { value: 'Management', label: '管理对象', component: Management, color: '#475569' },
  { value: 'Operation', label: '任务流程', component: Operation, color: '#245bdb' },
  { value: 'Menu', label: '菜单模块', component: Menu, color: '#64748b' },
  { value: 'Aim', label: '目标服务', component: Aim, color: '#ef4444' },
  { value: 'DataLine', label: '链路指标', component: DataLine, color: '#0ea5e9' },
  { value: 'Histogram', label: '容量报表', component: Histogram, color: '#7c3aed' },
  { value: 'Tickets', label: '工单', component: Tickets, color: '#f97316' },
]
const modelIconMap = new Map(modelIconOptions.map(item => [item.value, item]))
modelIconMap.set('Cluster', { value: 'Cluster', label: '集群', component: Connection, color: '#0ea5e9' })
modelIconMap.set('Coin', modelIconMap.get('Database'))
modelIconMap.set('Notebook', modelIconMap.get('Database'))
modelIconMap.set('MessageBox', modelIconMap.get('MessageQueue'))
modelIconMap.set('Promotion', modelIconMap.get('MessageQueue'))
modelIconMap.set('Collection', modelIconMap.get('Cache'))
modelIconMap.set('Lightning', modelIconMap.get('Cache'))
const selectedModelIconLabel = computed(() => modelIconMap.get(modelForm.icon)?.label || '通用配置')

function normalizeModelIconValue(icon) {
  const legacyIconMap = {
    Coin: 'Database',
    Notebook: 'Database',
    MessageBox: 'MessageQueue',
    Promotion: 'MessageQueue',
    Collection: 'Cache',
    Lightning: 'Cache',
  }
  return legacyIconMap[icon] || icon || 'SetUp'
}

const modelGroupDialogVisible = ref(false)
const modelGroupEditingId = ref(null)
const modelGroupForm = reactive({
  name: '',
  code: '',
  description: '',
  sort_order: 0,
  is_active: true,
})

const fieldDialogVisible = ref(false)
const fieldEditingId = ref(null)
const fieldForm = reactive({
  ci_type: '',
  name: '',
  code: '',
  field_type: 'string',
  field_group: '',
  required: false,
  unique: false,
  is_display: true,
  options: [],
  sync_mode: 'source',
  is_active: true,
  sort_order: 0,
})

const modelRelationRules = ref([])
const relationRuleDialogVisible = ref(false)
const relationRuleEditingId = ref(null)
const relationRuleForm = reactive({
  source_type: '',
  target_type: '',
  relation_type: 'runs_on',
  direction: 'outgoing',
  required: false,
  multiple: true,
  description: '',
  is_active: true,
})

const summaryCards = computed(() => {
  const risk = dashboard.value.risk_summary || {}
  const waterline = dashboard.value.capacity_waterline || {}
  const quality = dashboard.value.data_quality || {}
  return [
    { key: 'all', label: '配置项总数', value: dashboard.value.ci_total || 0, tone: '' },
    { key: 'active', label: '活跃资源', value: dashboard.value.ci_active || 0, tone: 'audit-card--success' },
    { key: 'quality', label: '数据质量', value: quality.score ?? 100, tone: (quality.score ?? 100) < 60 ? 'audit-card--danger' : (quality.score ?? 100) < 90 ? 'audit-card--warning' : 'audit-card--success' },
    { key: 'risk', label: '水位风险', value: (waterline.warning || 0) + (waterline.critical || 0) + (waterline.exceeded || 0), tone: 'audit-card--warning' },
    { key: 'governance', label: '待治理', value: (risk.service_expiry || risk.third_party_expiry || 0) + (waterline.warning || 0) + (waterline.critical || 0) + (waterline.exceeded || 0) + (risk.sync_failures || 0) + (risk.archive_candidates || 0), tone: 'audit-card--danger' },
  ]
})

const dataQuality = computed(() => dashboard.value.data_quality || {})
const dataQualityTone = computed(() => {
  const score = dataQuality.value.score ?? 100
  if (score < 60) return 'danger'
  if (score < 90) return 'warning'
  return 'success'
})
const dataQualityIssueRows = computed(() => {
  const counts = dataQuality.value.issue_counts || {}
  return [
    { key: 'missing_ownership', label: '归属缺失', value: counts.missing_ownership || 0, target: 'completion' },
    { key: 'no_source', label: '来源缺失', value: counts.no_source || 0, target: 'completion' },
    { key: 'no_relation', label: '关系断点', value: counts.no_relation || 0, target: canViewSync.value ? 'sync' : 'all' },
    { key: 'completion_issues', label: '待补全', value: counts.completion_issues || 0, target: 'completion' },
    { key: 'archive_candidates', label: '待下线', value: counts.archive_candidates || 0, target: 'archive' },
    { key: 'sync_failures', label: '同步失败', value: counts.sync_failures || 0, target: 'sync' },
  ].filter(item => item.value)
})
const dataQualityModelRows = computed(() => (dataQuality.value.model_quality || []).slice(0, 6))

const waterlineCards = computed(() => {
  const item = dashboard.value.capacity_waterline || {}
  return [
    { key: 'normal', label: '正常', value: item.normal || 0, tone: 'normal' },
    { key: 'warning', label: '预警', value: item.warning || 0, tone: 'warning' },
    { key: 'critical', label: '紧张', value: item.critical || 0, tone: 'critical' },
    { key: 'exceeded', label: '超限', value: item.exceeded || 0, tone: 'exceeded' },
  ]
})
const waterlineRiskCount = computed(() => {
  const item = dashboard.value.capacity_waterline || {}
  return Number(item.warning || 0) + Number(item.critical || 0) + Number(item.exceeded || 0)
})
const aggregateResourceMetricDefs = [
  {
    key: 'cpu',
    label: 'CPU',
    metrics: ['cpu_usage'],
    capacityKeys: ['cpu', 'cpu_cores', 'cpu_count', 'vcpu', 'vcpus', 'num_cpu', 'num_cpus', 'cores'],
    usedKeys: ['cpu_used', 'used_cpu', 'cpu_used_cores', 'used_cpu_cores'],
    usageKeys: ['cpu_usage', 'cpu_usage_percent', 'cpu_utilization', 'cpu_utilization_percent', 'cpu_used_percent'],
    unit: '核',
  },
  {
    key: 'memory',
    label: '内存',
    metrics: ['memory_usage'],
    capacityKeys: ['memory_gb', 'ram_gb', 'memory_size_gb', 'memory_mb', 'ram_mb', 'memory'],
    usedKeys: ['memory_used_gb', 'used_memory_gb', 'memory_usage_gb', 'used_memory_mb'],
    usageKeys: ['memory_usage', 'memory_usage_percent', 'memory_utilization', 'memory_utilization_percent', 'memory_used_percent'],
    unit: 'GB',
  },
  {
    key: 'disk',
    label: '磁盘',
    metrics: ['disk_usage', 'storage_usage'],
    capacityKeys: ['disk_gb', 'storage_gb', 'capacity_gb', 'provisioned_gb', 'disk_size_gb', 'storage_capacity_gb', 'disk_tb', 'storage_tb'],
    usedKeys: ['disk_used_gb', 'storage_used_gb', 'used_disk_gb', 'used_storage_gb', 'disk_usage_gb', 'storage_usage_gb'],
    usageKeys: ['disk_usage', 'storage_usage', 'disk_usage_percent', 'storage_usage_percent', 'disk_utilization', 'storage_utilization', 'disk_used_percent', 'storage_used_percent'],
    unit: 'GB',
  },
]
function normalizeOverviewValue(value, fallback = '未标注') {
  const text = String(value ?? '').trim()
  if (!text || text === '-') return fallback
  return text
}

function overviewAttr(row, keys, fallback = '') {
  const attrs = row?.attributes || {}
  for (const key of keys) {
    const value = attrs[key] ?? row?.[key] ?? row?.key_attributes?.[key]
    if (value !== undefined && value !== null && String(value).trim() !== '') return value
  }
  return fallback
}

function overviewCiText(row) {
  const attrs = row?.attributes || {}
  return [
    row?.ci_type_code,
    row?.ci_type_name,
    row?.name,
    row?.source_label,
    row?.source_type,
    attrs.source,
    attrs.source_type,
    attrs.cloud_provider,
    attrs.provider,
  ].filter(Boolean).join(' ').toLowerCase()
}

function isOverviewPhysicalServer(row) {
  const code = String(row?.ci_type_code || '').toUpperCase()
  const typeName = String(row?.ci_type_name || '')
  return ['IDC_SERVER', 'PHYSICAL_SERVER'].includes(code)
    || typeName.includes('物理机')
    || typeName.includes('机房服务器')
}

function isOverviewCloudServer(row) {
  if (isOverviewPhysicalServer(row)) return false
  const text = overviewCiText(row)
  return text.includes('cloud_server')
    || text.includes('virtual_machine')
    || text.includes('云主机')
    || text.includes('虚拟机')
    || text.includes('ecs')
    || text.includes('vsphere')
    || text.includes('vmware')
}

function isOverviewIdcServer(row) {
  if (isOverviewPhysicalServer(row)) return true
  const text = overviewCiText(row)
  if (isOverviewCloudServer(row)) return false
  return text.includes('physical_server')
    || text.includes('物理机')
}

function isOverviewServer(row) {
  const text = overviewCiText(row)
  return isOverviewCloudServer(row)
    || isOverviewIdcServer(row)
    || text.includes('server')
    || text.includes('主机')
}

function overviewCiTypeGroupMeta(row) {
  const ciTypeId = String(row?.ci_type ?? row?.ci_type_id ?? '').trim()
  const ciType = ciTypes.value.find(item => String(item.id) === ciTypeId)
  const groupId = String(row?.ci_type_group ?? ciType?.group ?? row?.group ?? '').trim()
  const group = ciModelGroups.value.find(item => String(item.id) === groupId)
  const groupName = String(row?.ci_type_group_name || ciType?.group_name || group?.name || row?.group_name || '').trim()
  const groupCode = String(row?.ci_type_group_code || group?.code || '').toLowerCase()
  const code = String(row?.ci_type_code || ciType?.code || '').toUpperCase()
  return {
    groupName,
    isOtherAssets: groupCode === 'external' || ['THIRD_PARTY_SERVICE', 'ASSET_ITEM'].includes(code),
  }
}

function overviewCloudAccountLabel(row) {
  const groupMeta = overviewCiTypeGroupMeta(row)
  if (groupMeta.isOtherAssets && groupMeta.groupName) return groupMeta.groupName
  return normalizeOverviewValue(ledgerSourceAccount(row), '未关联账号')
}

function overviewCloudAccountKindMeta(account, rows = []) {
  const target = String(account || '').trim()
  if (!target) return { label: '云账号', type: 'info' }
  const otherAssetsGroup = rows.map(row => {
    const groupMeta = overviewCiTypeGroupMeta(row)
    return groupMeta.isOtherAssets ? groupMeta.groupName : ''
  }).find(Boolean)
  if (otherAssetsGroup) return { label: otherAssetsGroup, type: 'info' }
  const credential = cloudCredentials.value.find((item) => {
    const names = [
      item.name,
      item.account_name,
      item.account_id,
      item.default_region,
    ].map(value => String(value || '').trim()).filter(Boolean)
    return names.includes(target) || names.map(value => value.replace(/\/+$/, '')).includes(target)
  })
  const provider = String(credential?.provider || '').toLowerCase()
  if (privateCloudProviderSet.has(provider)) return { label: '私有云', type: 'success' }
  if (publicCloudProviderSet.has(provider)) return { label: '公有云', type: 'primary' }
  const isPrivate = rows.some(row => isVsphereLedgerRow(row) || String(ledgerSourceLabel(row)).toLowerCase().includes('vsphere'))
  return isPrivate ? { label: '私有云', type: 'success' } : { label: '公有云', type: 'primary' }
}

function overviewBusinessLineLabel(row) {
  return normalizeOverviewValue(row?.business_line || row?.attributes?.business_line, '未设置业务线')
}

function overviewEnvironmentLabel(row) {
  const value = row?.environment || row?.attributes?.environment
  return normalizeOverviewValue(environmentText(value), '未设置环境')
}

function overviewBusinessEnvironmentKey(row) {
  return `${overviewBusinessLineLabel(row)} / ${overviewEnvironmentLabel(row)}`
}

function overviewMetricCiCandidates(row) {
  return [
    row?.ci,
    row?.ci_id,
    row?.id,
    row?.ci_name,
    row?.name,
    row?.source_unique_id,
    row?.key_attributes?.source_unique_id,
    row?.attributes?.source_unique_id,
    row?.attributes?.instance_id,
    row?.attributes?.resource_id,
  ].filter(value => value !== undefined && value !== null && String(value).trim() !== '').map(value => String(value))
}

function isOverviewProviderSummaryRow(row = {}) {
  const attrs = row.attributes || {}
  return attrs.resource_kind === 'vsphere_capacity_summary'
    || String(attrs.source_unique_id || row.source_unique_id || '').startsWith('vsphere-summary:')
}

function isOverviewProviderSummaryMetric(row = {}) {
  return row.source === 'vsphere_summary' || String(row.source_unique_id || '').startsWith('vsphere-summary:')
}

function overviewProviderSummaryAccount(row = {}) {
  const attrs = row.attributes || {}
  const sourceUniqueId = String(attrs.source_unique_id || row.source_unique_id || '').trim()
  const sourceFromId = sourceUniqueId.startsWith('vsphere-summary:') ? sourceUniqueId.replace('vsphere-summary:', '').trim() : ''
  return String(
    row.source_account
    || attrs.source_account
    || primarySourceMapping(row)?.source_account
    || sourceFromId
    || '',
  ).trim()
}

function overviewCiKey(row) {
  return String(row?.ci || row?.ci_id || row?.id || '').trim()
}

function overviewRowMatchesCloudAccount(row) {
  const account = isOverviewProviderSummaryRow(row) ? overviewProviderSummaryAccount(row) : overviewCloudAccountLabel(row)
  return account && account !== '未关联账号' && (!overviewResourceScope.value || account === overviewResourceScope.value)
}

function overviewRowMatchesBusinessEnvironment(row) {
  return !!overviewResourceScope.value && overviewBusinessEnvironmentKey(row) === overviewResourceScope.value
}

function overviewRowMatchesScope(row) {
  if (overviewResourceDimension.value === 'business_environment') return overviewRowMatchesBusinessEnvironment(row)
  return overviewRowMatchesCloudAccount(row)
}

function overviewRecordMatchesScope(row = {}) {
  // Run-level failures without an asset identity belong to the sync center, not asset governance.
  if (row.after?.collection_failed || row.before?.collection_failed || String(row.source_unique_id || '').trim().toLowerCase() === 'collection') return false
  const ciKeys = overviewScopedCiKeySet.value
  const recordKeys = [
    row.ci,
    row.ci_id,
    row.ci_name,
    row.name,
    row.after?.ci,
    row.before?.ci,
    row.after?.ci_id,
    row.before?.ci_id,
    row.after?.source_unique_id,
    row.before?.source_unique_id,
    row.after?.instance_id,
    row.before?.instance_id,
  ].filter(value => value !== undefined && value !== null && String(value).trim() !== '').map(value => String(value))
  if (!recordKeys.length) return false
  if (recordKeys.some(key => ciKeys.has(key))) return true
  const accounts = [
    row.source_account,
    row.cloud_account,
    row.job_source_account,
    row.after?.source_account,
    row.before?.source_account,
    row.after?.cloud_account,
    row.before?.cloud_account,
    row.after?.account,
    row.before?.account,
    row.after?.account_id,
    row.before?.account_id,
    row.after?.account_name,
    row.before?.account_name,
    ...(Array.isArray(row.job_source_accounts) ? row.job_source_accounts : []),
  ].filter(value => value !== undefined && value !== null && String(value).trim() !== '').map(value => String(value).trim())
  if (overviewResourceDimension.value === 'cloud_account') {
    return !overviewResourceScope.value || accounts.some(account => account === overviewResourceScope.value)
  }
  const businessLines = [
    row.business_line,
    row.after?.business_line,
    row.before?.business_line,
    row.ci_business_line,
    row.after?.ci_business_line,
    row.before?.ci_business_line,
  ].filter(value => value !== undefined && value !== null && String(value).trim() !== '').map(value => normalizeOverviewValue(value, '未设置业务线'))
  const environments = [
    row.environment,
    row.after?.environment,
    row.before?.environment,
    row.ci_environment,
    row.after?.ci_environment,
    row.before?.ci_environment,
  ].filter(value => value !== undefined && value !== null && String(value).trim() !== '').map(value => normalizeOverviewValue(environmentText(value), '未设置环境'))
  return businessLines.some(business => environments.some(env => `${business} / ${env}` === overviewResourceScope.value))
}

function overviewNumber(value, key = '', unit = '') {
  if (value === undefined || value === null || value === '') return null
  const text = String(value).replace(/,/g, '').trim()
  const matched = text.match(/-?\d+(?:\.\d+)?/)
  if (!matched) return null
  let number = Number(matched[0])
  if (!Number.isFinite(number)) return null
  const lowered = `${key} ${text}`.toLowerCase()
  if (unit === 'GB') {
    if (lowered.includes('tb')) number *= 1024
    else if (lowered.includes('mb')) number /= 1024
    else if (lowered.includes('kb')) number /= 1024 * 1024
    else if (lowered.includes('byte') || lowered.endsWith(' b')) number /= 1024 * 1024 * 1024
  }
  return number
}

function overviewPercent(value, key = '') {
  const number = overviewNumber(value, key)
  if (number === null) return null
  const lowered = String(key).toLowerCase()
  if (number > 0 && number <= 1 && (lowered.includes('ratio') || lowered.includes('rate'))) return number * 100
  return Math.max(0, Math.min(100, number))
}

function firstOverviewMetricValue(row, keys = [], unit = '') {
  const attrs = row?.attributes || {}
  for (const key of keys) {
    const value = attrs[key] ?? row?.[key] ?? row?.key_attributes?.[key]
    const number = unit === '%' ? overviewPercent(value, key) : overviewNumber(value, key, unit)
    if (number !== null) return number
  }
  return null
}

function formatOverviewCapacity(value, unit) {
  if (!Number.isFinite(value) || value <= 0) return '-'
  if (unit === 'GB') {
    if (value >= 1024) return `${(value / 1024).toFixed(value >= 10240 ? 0 : 1).replace(/\.0$/, '')} TB`
    return `${value.toFixed(value >= 100 ? 0 : 1).replace(/\.0$/, '')} GB`
  }
  return `${value.toFixed(value >= 100 ? 0 : 1).replace(/\.0$/, '')} ${unit}`
}

function formatOverviewCpuMhz(value) {
  if (!Number.isFinite(value) || value <= 0) return '-'
  if (value >= 1000) return `${(value / 1000).toFixed(value >= 10000 ? 0 : 1).replace(/\.0$/, '')} GHz`
  return `${value.toFixed(0)} MHz`
}

function formatOverviewAllocatedCapacity(def, value) {
  if (def.key === 'cpu') return formatOverviewCapacity(value, 'vCPU')
  return formatOverviewCapacity(value, def.unit)
}

function overviewProviderSummaryForDef(def, rows) {
  let total = 0
  let used = 0
  let usageCount = 0
  const usageValues = []
  rows.filter(isOverviewProviderSummaryRow).forEach((row) => {
    const attrs = row.attributes || {}
    let rowTotal = 0
    let rowUsed = 0
    let rowUsage = null
    if (def.key === 'cpu') {
      rowTotal = overviewNumber(attrs.cpu_total_mhz, 'cpu_total_mhz') || 0
      rowUsed = overviewNumber(attrs.cpu_used_mhz, 'cpu_used_mhz') || 0
      rowUsage = overviewPercent(attrs.cpu_usage, 'cpu_usage')
    } else if (def.key === 'memory') {
      rowTotal = overviewNumber(attrs.memory_total_gb, 'memory_total_gb', 'GB') || 0
      rowUsed = overviewNumber(attrs.memory_used_gb, 'memory_used_gb', 'GB') || 0
      rowUsage = overviewPercent(attrs.memory_usage, 'memory_usage')
    } else if (def.key === 'disk') {
      rowTotal = overviewNumber(attrs.storage_total_gb, 'storage_total_gb', 'GB') || overviewNumber(attrs.disk_total_gb, 'disk_total_gb', 'GB') || 0
      rowUsed = overviewNumber(attrs.storage_used_gb, 'storage_used_gb', 'GB') || overviewNumber(attrs.disk_used_gb, 'disk_used_gb', 'GB') || 0
      rowUsage = overviewPercent(attrs.storage_usage ?? attrs.disk_usage, 'storage_usage')
    }
    if (rowTotal > 0) total += rowTotal
    if (rowUsed > 0) used += rowUsed
    if (rowUsage !== null) {
      usageValues.push(rowUsage)
      usageCount += 1
    }
  })
  const average = total > 0 && used > 0
    ? Math.round(used / total * 100)
    : usageValues.length
      ? Math.round(usageValues.reduce((sum, value) => sum + value, 0) / usageValues.length)
      : 0
  const capacityText = def.key === 'cpu' ? formatOverviewCpuMhz(total) : formatOverviewCapacity(total, def.unit)
  const usedText = def.key === 'cpu' ? formatOverviewCpuMhz(used) : formatOverviewCapacity(used, def.unit)
  return {
    totalCapacity: total,
    usedCapacity: used,
    capacityCount: total > 0 ? rows.filter(isOverviewProviderSummaryRow).length : 0,
    usageCount,
    average,
    peak: usageValues.length ? Math.round(Math.max(...usageValues)) : average,
    capacityText,
    usedText,
    isProviderSummary: total > 0 || usageCount > 0,
  }
}

function overviewAllocatedSummaryForDef(def, serverRows, scopedRows) {
  let totalCapacity = 0
  let capacityCount = 0
  const summaryRows = scopedRows.filter(isOverviewProviderSummaryRow)
  summaryRows.forEach((row) => {
    const attrs = row.attributes || {}
    let allocated = 0
    if (def.key === 'cpu') {
      allocated = overviewNumber(attrs.cpu_allocated_vcpu, 'cpu_allocated_vcpu') || 0
    } else if (def.key === 'memory') {
      allocated = overviewNumber(attrs.memory_allocated_gb, 'memory_allocated_gb', 'GB') || 0
    } else if (def.key === 'disk') {
      allocated = overviewNumber(attrs.storage_allocated_gb, 'storage_allocated_gb', 'GB')
        || overviewNumber(attrs.disk_allocated_gb, 'disk_allocated_gb', 'GB')
        || 0
    }
    if (allocated > 0) {
      totalCapacity += allocated
      capacityCount += 1
    }
  })
  if (totalCapacity > 0) {
    return {
      totalCapacity,
      capacityCount,
      capacityText: formatOverviewAllocatedCapacity(def, totalCapacity),
    }
  }
  const fallback = overviewCapacitySummary(def, serverRows)
  if (fallback.totalCapacity <= 0) {
    return {
      totalCapacity: 0,
      capacityCount: 0,
      capacityText: '-',
    }
  }
  return {
    totalCapacity: fallback.totalCapacity,
    capacityCount: fallback.capacityCount,
    capacityText: formatOverviewAllocatedCapacity(def, fallback.totalCapacity),
  }
}

function overviewCapacitySummary(def, rows) {
  let totalCapacity = 0
  let totalUsed = 0
  let capacityCount = 0
  let usageCount = 0
  const usageValues = []
  rows.forEach((row) => {
    const capacity = firstOverviewMetricValue(row, def.capacityKeys, def.unit)
    const usage = firstOverviewMetricValue(row, def.usageKeys, '%')
    const used = firstOverviewMetricValue(row, def.usedKeys, def.unit)
    if (capacity !== null && capacity > 0) {
      totalCapacity += capacity
      capacityCount += 1
    }
    if (usage !== null) {
      usageValues.push(usage)
      usageCount += 1
      if (capacity !== null && capacity > 0) totalUsed += capacity * usage / 100
    } else if (used !== null && capacity !== null && capacity > 0) {
      const percent = Math.max(0, Math.min(100, used / capacity * 100))
      usageValues.push(percent)
      usageCount += 1
      totalUsed += used
    }
  })
  const average = totalCapacity > 0 && totalUsed > 0
    ? Math.round(totalUsed / totalCapacity * 100)
    : usageValues.length
      ? Math.round(usageValues.reduce((sum, value) => sum + value, 0) / usageValues.length)
      : 0
  return {
    totalCapacity,
    usedCapacity: totalUsed,
    capacityCount,
    usageCount,
    average,
    peak: usageValues.length ? Math.round(Math.max(...usageValues)) : 0,
    capacityText: formatOverviewCapacity(totalCapacity, def.unit),
    usedText: formatOverviewCapacity(totalUsed, def.unit),
  }
}

function overviewMetricSnapshotUsedValue(def, row = {}) {
  const rawValue = overviewNumber(row.value, 'value', def.unit)
  if (rawValue === null || rawValue < 0) return null
  const unit = String(row.unit || '').trim().toLowerCase()
  if (def.key === 'cpu') {
    if (unit === 'ghz') return rawValue * 1000
    if (unit === 'mhz' || unit === '') return rawValue
    return null
  }
  if (def.unit === 'GB') {
    if (unit === 'tb') return rawValue * 1024
    return rawValue
  }
  return rawValue
}

function formatOverviewMetricSnapshotUsed(def, value) {
  if (!Number.isFinite(value) || value <= 0) return ''
  if (def.key === 'cpu') return formatOverviewCpuMhz(value)
  return formatOverviewCapacity(value, def.unit)
}

function formatOverviewWaterlineText(summary) {
  if (!summary?.usageCount && !summary?.isProviderSummary) return ''
  const parts = [`${summary.average || 0}%`]
  const usedText = summary.metricUsedText || summary.usedText
  if (usedText && usedText !== '-') parts.push(usedText)
  return parts.join(' · ')
}

function overviewMetricSnapshotCapacitySummary(def, metricRows, serverRows) {
  const usageByCiKey = new Map()
  const usedValueByCiKey = new Map()
  for (const row of metricRows || []) {
    if (!def.metrics.includes(row.metric)) continue
    const usage = Number(row.usage_percent)
    if (!Number.isFinite(usage)) continue
    const normalizedUsage = Math.max(0, Math.min(100, usage))
    const usedValue = overviewMetricSnapshotUsedValue(def, row)
    for (const key of overviewMetricCiCandidates(row)) {
      const previousUsage = usageByCiKey.get(key)
      if (!Number.isFinite(previousUsage) || normalizedUsage >= previousUsage) {
        usageByCiKey.set(key, normalizedUsage)
        if (usedValue !== null) usedValueByCiKey.set(key, usedValue)
      }
    }
  }
  if (!usageByCiKey.size) return null

  let totalCapacity = 0
  let totalUsed = 0
  let metricUsedTotal = 0
  let metricUsedCount = 0
  let capacityCount = 0
  let usageCount = 0
  const usageValues = []
  for (const row of serverRows || []) {
    const capacity = firstOverviewMetricValue(row, def.capacityKeys, def.unit)
    if (capacity === null || capacity <= 0) continue
    const usage = overviewMetricCiCandidates(row)
      .map(key => usageByCiKey.get(key))
      .find(value => Number.isFinite(value))
    if (!Number.isFinite(usage)) continue
    totalCapacity += capacity
    totalUsed += capacity * usage / 100
    const metricUsed = overviewMetricCiCandidates(row)
      .map(key => usedValueByCiKey.get(key))
      .find(value => Number.isFinite(value))
    if (Number.isFinite(metricUsed)) {
      metricUsedTotal += metricUsed
      metricUsedCount += 1
    }
    capacityCount += 1
    usageCount += 1
    usageValues.push(usage)
  }
  if (!usageCount) return null
  const average = totalCapacity > 0
    ? Math.round(totalUsed / totalCapacity * 100)
    : Math.round(usageValues.reduce((sum, value) => sum + value, 0) / usageValues.length)
  return {
    totalCapacity,
    usedCapacity: totalUsed,
    capacityCount,
    usageCount,
    average,
    peak: Math.round(Math.max(...usageValues)),
    capacityText: formatOverviewCapacity(totalCapacity, def.unit),
    usedText: formatOverviewCapacity(totalUsed, def.unit),
    metricUsedText: formatOverviewMetricSnapshotUsed(def, metricUsedTotal),
    metricUsedCount,
  }
}

const overviewAllRows = computed(() => overviewServerItems.value.length ? overviewServerItems.value : ledgerItems.value)
const overviewVisibleRows = computed(() => overviewAllRows.value.filter(row => isVisibleCiType(row) && !isOverviewProviderSummaryRow(row)))
const overviewServerRows = computed(() => overviewVisibleRows.value.filter(isOverviewServer))
const overviewCloudServerRows = computed(() => overviewServerRows.value.filter(isOverviewCloudServer))
const overviewAccountRows = computed(() => overviewVisibleRows.value.filter((row) => {
  const account = overviewCloudAccountLabel(row)
  return account && account !== '未关联账号'
}))
const overviewBusinessEnvironmentRows = computed(() => overviewVisibleRows.value.filter((row) => {
  return overviewBusinessLineLabel(row) !== '未设置业务线' || overviewEnvironmentLabel(row) !== '未设置环境'
}))
const overviewScopedCiRows = computed(() => {
  return overviewResourceDimension.value === 'business_environment'
    ? overviewBusinessEnvironmentRows.value.filter(overviewRowMatchesScope)
    : overviewAccountRows.value.filter(overviewRowMatchesScope)
})
const overviewScopedCiKeySet = computed(() => new Set(overviewScopedCiRows.value.flatMap(overviewMetricCiCandidates)))
const overviewCloudAccountScopeOptions = computed(() => {
  const resourceCounts = new Map()
  overviewAccountRows.value.forEach((row) => {
    const label = overviewCloudAccountLabel(row)
    resourceCounts.set(label, (resourceCounts.get(label) || 0) + 1)
  })
  return [{ value: '', title: '全部云账号', selectedLabel: '全部云账号', label: '全部云账号' }, ...Array.from(resourceCounts.entries())
    .sort((left, right) => right[1] - left[1] || left[0].localeCompare(right[0]))
    .map(([label]) => {
      const accountRows = overviewAccountRows.value.filter(row => overviewCloudAccountLabel(row) === label)
      const kind = overviewCloudAccountKindMeta(label, accountRows)
      return {
        value: label,
        title: label,
        kindLabel: kind.label,
        kindType: kind.type,
        selectedLabel: label,
        label: `${label} · ${kind.label}`,
      }
    })]
})
const overviewBusinessEnvironmentScopeOptions = computed(() => {
  const resourceCounts = new Map()
  overviewBusinessEnvironmentRows.value.forEach((row) => {
    const label = overviewBusinessEnvironmentKey(row)
    resourceCounts.set(label, (resourceCounts.get(label) || 0) + 1)
  })
  return Array.from(resourceCounts.entries())
    .sort((left, right) => right[1] - left[1] || left[0].localeCompare(right[0], 'zh-Hans-CN'))
    .map(([label]) => {
      return {
        value: label,
        title: label,
        selectedLabel: label,
        label,
      }
    })
})
const overviewResourceScopeOptions = computed(() => overviewResourceDimension.value === 'business_environment'
  ? overviewBusinessEnvironmentScopeOptions.value
  : overviewCloudAccountScopeOptions.value)
const overviewBusinessEnvironmentCostScope = computed(() => {
  if (overviewResourceDimension.value !== 'business_environment' || !overviewResourceScope.value) return null
  const row = overviewBusinessEnvironmentRows.value.find(item => overviewBusinessEnvironmentKey(item) === overviewResourceScope.value)
  if (!row) return null
  return {
    businessLine: String(row.business_line || row.attributes?.business_line || '').trim(),
    environment: String(row.environment || row.attributes?.environment || '').trim(),
  }
})
watch(overviewResourceScopeOptions, (options) => {
  if (!options.length) {
    overviewResourceScope.value = ''
    return
  }
  if (!options.some(item => item.value === overviewResourceScope.value)) {
    overviewResourceScope.value = options[0].value
  }
}, { immediate: true })
watch([overviewResourceDimension, overviewResourceScope], () => {
  overviewCostCacheAt = 0
  if (activeTab.value === 'overview') fetchOverviewCostSummary({ force: true })
})
const overviewResourceScopePlaceholder = computed(() => overviewResourceDimension.value === 'business_environment' ? '选择业务线 / 环境' : '选择云账号')
const overviewResourceScopeDesc = computed(() => overviewResourceDimension.value === 'business_environment'
  ? '按业务线与环境汇总服务器 CPU、内存、磁盘水位和治理事项，方便从业务视角判断容量与风险。'
  : '汇总所选云账号的 CPU、内存、磁盘容量与使用水位；选择全部云账号可查看总资源。')
const overviewFilteredServerRows = computed(() => {
  return overviewResourceDimension.value === 'business_environment'
    ? overviewServerRows.value.filter(overviewRowMatchesScope)
    : overviewCloudServerRows.value.filter(overviewRowMatchesScope)
})
const showOverviewTotalResourceView = computed(() => overviewResourceDimension.value === 'cloud_account' || overviewFilteredServerRows.value.some(isOverviewCloudServer))
const overviewAllocatedServerRows = computed(() => overviewFilteredServerRows.value.filter(isOverviewCloudServer))
const overviewProviderSummaryRows = computed(() => overviewAllRows.value.filter((row) => {
  return isOverviewProviderSummaryRow(row)
    && overviewResourceDimension.value === 'cloud_account'
    && overviewProviderSummaryAccount(row) === overviewResourceScope.value
}))
const overviewIsPrivateCloudScope = computed(() => {
  if (overviewResourceDimension.value !== 'cloud_account' || !overviewResourceScope.value) return false
  const kind = overviewCloudAccountKindMeta(overviewResourceScope.value, overviewFilteredServerRows.value)
  return kind.type === 'success' || overviewProviderSummaryRows.value.length > 0
})
const overviewMetricCiKeySet = computed(() => new Set(overviewFilteredServerRows.value.flatMap(overviewMetricCiCandidates)))
const overviewResourceScopeLabel = computed(() => {
  const count = overviewFilteredServerRows.value.length
  if (overviewServerLoading.value) return '服务器加载中'
  return `${overviewResourceScope.value || (overviewResourceDimension.value === 'cloud_account' ? '全部云账号' : overviewResourceScopePlaceholder.value)} ${count} 台`
})
const overviewScopeTitle = computed(() => overviewResourceScope.value || (overviewResourceDimension.value === 'business_environment' ? '当前业务环境范围' : '当前云账号范围'))

const overviewMetricCollectionIssues = computed(() => overviewFilteredServerRows.value
  .map((row) => {
    const attrs = row?.attributes || {}
    const status = String(attrs.metric_collection_status || '').trim()
    if (!['failed', 'fallback', 'partial'].includes(status)) return null
    return {
      id: row.id || row.name,
      name: row.name || attrs.instance_id || attrs.source_unique_id || '未命名服务器',
      status,
      error: String(attrs.metric_collection_error || '').trim(),
    }
  })
  .filter(Boolean))

const overviewMetricCollectionNotices = computed(() => {
  const failedRows = overviewMetricCollectionIssues.value.filter(item => item.status === 'failed')
  if (failedRows.length) {
    const firstError = failedRows.find(item => item.error)?.error || '请检查云账号是否具备 CloudMonitor 只读权限。'
    return [{
      key: 'metric-failed',
      tone: 'is-warning',
      title: `${overviewScopeTitle.value} 有 ${failedRows.length} 台服务器未采到实时用量`,
      desc: firstError,
    }]
  }
  const fallbackRows = overviewMetricCollectionIssues.value.filter(item => item.status === 'fallback')
  const partialRows = overviewMetricCollectionIssues.value.filter(item => item.status === 'partial')
  if (fallbackRows.length || partialRows.length) {
    const firstError = [...fallbackRows, ...partialRows].find(item => item.error)?.error || '请配置默认 Prometheus 数据源并确认 node_exporter target 可用。'
    return [{
      key: 'metric-fallback',
      tone: 'is-warning',
      title: `${overviewScopeTitle.value} 有 ${fallbackRows.length} 台使用 vSphere 回退、${partialRows.length} 台仅部分取得 Guest OS 指标`,
      desc: firstError,
    }]
  }
  return []
})

function overviewCountBy(rows, keyGetter, fallback = '未分类') {
  const counts = new Map()
  rows.forEach((row) => {
    const label = normalizeOverviewValue(keyGetter(row), fallback)
    counts.set(label, (counts.get(label) || 0) + 1)
  })
  return Array.from(counts.entries())
    .sort((left, right) => right[1] - left[1] || left[0].localeCompare(right[0]))
    .map(([label, count]) => ({ type_name: label, source_type: label, count }))
}

const overviewInventoryByType = computed(() => overviewCountBy(
  overviewScopedCiRows.value,
  row => row.ci_type_name || modelName(row.ci_type) || row.ci_type_code,
  '未分类',
))
function overviewMetricMatchesScope(row) {
  if (isOverviewProviderSummaryMetric(row)) {
    return overviewResourceDimension.value === 'cloud_account'
      && !!overviewResourceScope.value
      && overviewProviderSummaryAccount(row) === overviewResourceScope.value
  }
  const keys = overviewMetricCiKeySet.value
  if (keys.size) return overviewMetricCiCandidates(row).some(key => keys.has(key))
  return false
}

const aggregateResourceRows = computed(() => aggregateResourceMetricDefs.map((def) => {
  const matchingMetrics = []
  const summaryMetrics = []
  for (const row of overviewResourceMetrics.value || []) {
    if (!def.metrics.includes(row.metric)) continue
    if (!overviewMetricMatchesScope(row)) continue
    matchingMetrics.push(row)
    if (isOverviewProviderSummaryMetric(row)) summaryMetrics.push(row)
  }
  const vmMetrics = matchingMetrics.filter(row => !isOverviewProviderSummaryMetric(row))
  const metricRows = summaryMetrics.length ? summaryMetrics : matchingMetrics
  const values = []
  const seen = new Set()
  for (const row of metricRows) {
    const usage = Number(row.usage_percent)
    if (!Number.isFinite(usage)) continue
    const rowKey = `${row.ci || row.ci_id || row.ci_name || 'ci'}:${row.metric}`
    if (seen.has(rowKey)) continue
    seen.add(rowKey)
    values.push(Math.max(0, Math.min(100, Math.round(usage))))
  }
  const providerSummary = overviewProviderSummaryForDef(def, overviewProviderSummaryRows.value)
  const allocatedSummary = overviewAllocatedSummaryForDef(def, overviewAllocatedServerRows.value, overviewProviderSummaryRows.value)
  const vmActualSummary = overviewMetricSnapshotCapacitySummary(def, vmMetrics, overviewFilteredServerRows.value)
  const shouldShowProviderWaterlines = providerSummary.isProviderSummary || overviewIsPrivateCloudScope.value
  const rawRiskRows = capacityRiskRows.value.filter(row => def.metrics.includes(row.metric) && overviewMetricMatchesScope(row))
  const providerRiskProbe = {
    metric: def.metrics[0],
    usage_percent: providerSummary.average,
  }
  const providerRiskStatus = providerSummary.isProviderSummary && providerSummary.usageCount
    ? capacityRiskStatus(providerRiskProbe)
    : 'normal'
  const riskRows = providerSummary.isProviderSummary
    ? (['warning', 'critical', 'exceeded'].includes(providerRiskStatus) ? [providerRiskProbe] : [])
    : rawRiskRows
  const primaryRisk = [...riskRows].sort((left, right) => Number(right.usage_percent || 0) - Number(left.usage_percent || 0))[0] || null
  const status = primaryRisk ? capacityRiskStatus(primaryRisk) : 'normal'
  const metricSnapshotSummary = providerSummary.isProviderSummary ? null : vmActualSummary
  const specSummary = providerSummary.isProviderSummary
    ? providerSummary
    : (metricSnapshotSummary || overviewCapacitySummary(def, overviewFilteredServerRows.value))
  const average = specSummary.usageCount
    ? specSummary.average
    : values.length
      ? Math.round(values.reduce((sum, value) => sum + value, 0) / values.length)
      : 0
  const peak = values.length ? Math.max(...values) : specSummary.peak
  const riskCount = riskRows.length
  const requestOpen = riskRows.some(row => linkedCapacityRequest(row) && ['pending', 'approved'].includes(linkedCapacityRequest(row)?.status))
  const hasUsage = values.length > 0 || specSummary.usageCount > 0
  const hasCapacity = specSummary.capacityCount > 0 || (allocatedSummary?.capacityCount || 0) > 0
  const statusText = requestOpen ? '申请中' : riskCount ? '建议申请' : hasUsage ? '水位正常' : hasCapacity ? '已同步规格' : '待录入'
  const metricCountText = providerSummary.isProviderSummary
    ? values.length ? `${values.length} 个资源池快照` : ''
    : values.length ? `${values.length} 个指标` : specSummary.usageCount ? `${specSummary.usageCount} 台有使用率` : ''
  const capacityText = hasCapacity && !providerSummary.isProviderSummary
    ? `总量 ${specSummary.capacityText}`
    : ''
  const breakdownRows = providerSummary.isProviderSummary
    ? [
      { label: '已申请总量', value: allocatedSummary?.capacityText || '-' },
      { label: def.key === 'disk' ? '存储总量' : '物理总量', value: specSummary.capacityText || '-' },
    ].filter(row => row && row.value && row.value !== '-')
    : (hasUsage || hasCapacity
      ? [
        { label: '当前实际', value: specSummary.usedText || (hasUsage ? `${average}%` : '-') },
        { label: '已申请总量', value: allocatedSummary?.capacityText || specSummary.capacityText || '-' },
      ].filter(row => row && row.value && row.value !== '-')
      : [])
  // Waterline is always actual usage divided by actual capacity. Requested capacity is shown separately.
  const mainPercent = average
  const progressRows = shouldShowProviderWaterlines
    ? [
      {
        key: 'vm-actual',
        label: '虚拟机实际水位',
        desc: '当前虚拟机消耗 / 已采集虚拟机规格',
        percentText: vmActualSummary?.usageCount ? `${vmActualSummary.average || 0}%` : '待采集',
        currentText: vmActualSummary?.usageCount ? (vmActualSummary.usedText || '-') : '-',
        totalText: vmActualSummary?.usageCount ? (vmActualSummary.capacityText || '-') : '-',
        percent: vmActualSummary?.usageCount ? Math.max(0, Math.min(100, vmActualSummary.average || 0)) : 0,
        color: '#16a34a',
        tone: 'is-vm',
        hasData: !!vmActualSummary?.usageCount,
      },
      {
        key: 'pool-actual',
        label: '资源池实际水位',
        desc: '当前物理资源消耗 / 物理资源池总量',
        percentText: providerSummary.usageCount ? `${providerSummary.average || 0}%` : '待采集',
        currentText: providerSummary.usageCount ? (providerSummary.usedText || '-') : '-',
        totalText: providerSummary.capacityText || '-',
        percent: providerSummary.usageCount ? Math.max(0, Math.min(100, providerSummary.average || 0)) : 0,
        color: '#245bdb',
        tone: 'is-pool',
        hasData: providerSummary.usageCount > 0,
      },
    ]
    : (hasUsage || hasCapacity
      ? [
        {
          key: 'actual',
          label: '当前实际水位',
          desc: overviewResourceDimension.value === 'business_environment'
            ? '当前业务环境资源实际消耗 / 已采集服务器规格总量'
            : '当前云资源实际消耗 / 已采集服务器规格总量',
          percentText: hasUsage ? `${mainPercent}%` : '待采集',
          currentText: hasUsage ? (specSummary.usedText || '-') : '-',
          totalText: specSummary.capacityText || allocatedSummary?.capacityText || '-',
          percent: hasUsage ? Math.max(0, Math.min(100, mainPercent)) : 0,
          color: '#245bdb',
          tone: 'is-pool',
          hasData: hasUsage,
        },
      ]
      : [])
  const meta = [
    `${overviewFilteredServerRows.value.length} 台服务器`,
    metricCountText,
    capacityText,
    hasUsage && !providerSummary.isProviderSummary ? `峰值 ${peak}%` : '',
    riskCount ? `${riskCount} 个风险点` : '',
    !hasUsage && hasCapacity ? '待接入使用率' : '',
    !hasUsage && !hasCapacity ? '暂无指标快照' : '',
  ].filter(Boolean).join('，')
  return {
    ...def,
    average: mainPercent,
    percent: hasUsage ? Math.max(0, Math.min(100, mainPercent)) : 0,
    peak,
    hasData: hasUsage || hasCapacity,
    hasUsage,
    hasCapacity,
    displayValue: progressRows.length ? '' : hasUsage ? `${mainPercent}%` : hasCapacity ? specSummary.capacityText : '-',
    displayHint: '',
    riskCount,
    primaryRisk,
    status,
    statusText,
    tagType: requestOpen ? 'warning' : riskCount ? 'danger' : hasUsage ? 'success' : hasCapacity ? 'info' : 'info',
    tone: requestOpen ? 'is-warning' : riskCount ? 'is-danger' : hasUsage ? 'is-success' : hasCapacity ? 'is-info' : 'is-empty',
    meta,
    breakdownRows,
    progressRows,
  }
}))
const resourceRequestNeeded = computed(() => aggregateResourceRows.value.some(item => item.riskCount > 0))
const metricNameOptions = computed(() => Array.from(new Set([
  'cpu_usage',
  'memory_usage',
  'disk_usage',
  'storage_usage',
  'connection_usage',
  ...thresholdPolicies.value.map(item => item.metric),
  ...resourceMetrics.value.map(item => item.metric),
].filter(Boolean))).sort())
const thresholdSummaryCards = computed(() => {
  const enabledCount = thresholdPolicies.value.filter(item => item.enabled !== false).length
  const scopedModelCount = new Set(thresholdPolicies.value.map(item => item.resource_type).filter(Boolean)).size
  const manualCount = resourceMetrics.value.filter(item => item.source === 'manual').length
  return [
    { key: 'policies', label: '阈值策略', value: thresholdPolicies.value.length, tone: '' },
    { key: 'enabled', label: '启用策略', value: enabledCount, tone: 'success' },
    { key: 'models', label: '覆盖模型', value: scopedModelCount || '全局', tone: 'info' },
    { key: 'risks', label: '水位风险', value: waterlineRiskCount.value, tone: waterlineRiskCount.value ? 'warning' : 'success' },
    { key: 'metrics', label: '指标快照', value: resourceMetrics.value.length, tone: '' },
    { key: 'manual', label: '手工录入', value: manualCount, tone: 'info' },
  ]
})
const platformSettingCards = computed(() => {
  const enabledCount = thresholdPolicies.value.filter(item => item.enabled !== false).length
  const latestMetric = resourceMetrics.value
    .map(item => item.collected_at || item.updated_at)
    .filter(Boolean)
    .sort()
    .pop()
  return [
    { key: 'policy', label: '容量策略', value: `${enabledCount}/${thresholdPolicies.value.length}`, desc: enabledCount ? '策略正在生效' : '建议先配置策略', tone: enabledCount ? 'success' : 'warning' },
    { key: 'metric', label: '指标采集', value: resourceMetrics.value.length, desc: latestMetric ? `最近 ${formatTime(latestMetric)}` : '暂无指标快照', tone: resourceMetrics.value.length ? 'info' : 'warning' },
    { key: 'risk', label: '待处理风险', value: waterlineRiskCount.value, desc: waterlineRiskCount.value ? '请进入指标快照处理' : '当前水位正常', tone: waterlineRiskCount.value ? 'warning' : 'success' },
    { key: 'audit', label: '变更追踪', value: auditSummary.value.total || auditLogs.value.length || 0, desc: canViewAudit.value ? '可查看完整操作审计' : '暂无审计权限', tone: canViewAudit.value ? 'info' : '' },
  ]
})
const assetModelGroupsForUi = computed(() => {
  const activeGroups = ciModelGroups.value.filter(group => group.is_active !== false && String(group.code || '').toLowerCase() !== 'data')
  const byCode = new Map(activeGroups.map(group => [String(group.code || '').toLowerCase(), group]))
  const standardRows = standardAssetModelGroups.map((group, index) => {
    const apiGroup = byCode.get(group.code)
    return {
      ...(apiGroup || {}),
      id: apiGroup?.id ?? group.key,
      key: group.key,
      code: group.code,
      name: apiGroup?.name || group.name,
      sort_order: apiGroup?.sort_order ?? (index + 1) * 10,
      is_standard: true,
      has_backend_group: Boolean(apiGroup?.id),
    }
  })
  const standardCodes = new Set(standardAssetModelGroups.map(group => group.code))
  const customRows = activeGroups
    .filter(group => !standardCodes.has(String(group.code || '').toLowerCase()))
    .map(group => ({ ...group, key: String(group.id ?? group.code ?? group.name), has_backend_group: true }))
  return [...standardRows, ...customRows]
})
const modelGroupTabs = computed(() => [
  { key: 'all', label: '全部分组' },
  ...assetModelGroupsForUi.value.map(group => ({
    key: String(group.key ?? group.id ?? group.code ?? group.name),
    label: group.name,
  })),
])
const hiddenModelCardCodes = new Set(['MIDDLEWARE', 'CLOUD_DATABASE', 'VSPHERE_CAPACITY', 'SECURITY_GROUP', 'EIP', 'SPARK', 'HIVE', 'HBASE', 'DORIS'])
const visibleAssetClassificationTypes = computed(() => ciTypes.value.filter((model) => {
  if (hiddenModelCardCodes.has(String(model.code || '').toUpperCase())) return false
  const name = String(model.name || '').trim()
  return !['云数据库', 'Docker环境', 'vSphere资源统计', '数据仓库', 'Security Group', '安全组', '弹性IP', '弹性 IP', 'Spark', 'Hive', 'HBase', 'Doris', '物理机/宿主机'].includes(name)
}))
const modelCatalogSourceRows = computed(() => (
  modelCatalogTreeItems.value.length
    ? modelCatalogTreeItems.value
    : (ledgerTreeItems.value.length ? ledgerTreeItems.value : ledgerItems.value)
))
const modelCatalogScopedRows = computed(() => modelCatalogSourceRows.value.filter(row => modelCatalogResourceMatchesContext(row)))
const modelCatalogScopedModelCounts = computed(() => {
  const counter = new Map()
  visibleAssetClassificationTypes.value.forEach(model => counter.set(String(model.id), 0))
  modelCatalogScopedRows.value.forEach((row) => {
    const model = visibleAssetClassificationTypes.value.find(item => resourceBelongsToModel(row, item))
    if (!model?.id) return
    const key = String(model.id)
    counter.set(key, (counter.get(key) || 0) + 1)
  })
  return counter
})
const filteredModelCards = computed(() => {
  const keyword = opsanyModelKeyword.value.trim().toLowerCase()
  const status = opsanyModelStatus.value
  const rows = activeModelGroupKey.value === 'all'
    ? visibleAssetClassificationTypes.value
    : visibleAssetClassificationTypes.value.filter((model) => {
      const group = assetModelGroupsForUi.value.find(item => String(item.key ?? item.id ?? item.code ?? item.name) === activeModelGroupKey.value)
      return modelBelongsToGroup(model, group, activeModelGroupKey.value)
    })
  return rows.filter((model) => {
    if (hiddenModelCardCodes.has(String(model.code || '').toUpperCase())) return false
    if (status === 'active' && model.is_active === false) return false
    if (status === 'inactive' && model.is_active !== false) return false
    if (isModelDisplayRoute.value && modelCatalogTreeContext.value && !modelCardResourceCount(model)) return false
    if (!keyword) return true
    return [model.name, model.code, model.group_name, model.description]
      .some(value => String(value || '').toLowerCase().includes(keyword))
  })
})
const opsanyModelSections = computed(() => {
  const rows = filteredModelCards.value
  if (activeModelGroupKey.value !== 'all') {
    const group = assetModelGroupsForUi.value.find(item => String(item.key ?? item.id ?? item.code ?? item.name) === activeModelGroupKey.value)
    return rows.length ? [{
      key: activeModelGroupKey.value,
      label: group?.name || '全部分组',
      group,
      models: rows,
    }] : []
  }
  const sections = assetModelGroupsForUi.value
    .map(group => ({
      key: String(group.key ?? group.id ?? group.code ?? group.name),
      label: group.name,
      group,
      models: rows.filter(model => modelBelongsToGroup(model, group, String(group.key ?? group.id ?? group.code ?? group.name))),
    }))
    .filter(section => section.models.length)
  const groupedIds = new Set(sections.flatMap(section => section.models.map(model => model.id)))
  const ungrouped = rows.filter(model => !groupedIds.has(model.id))
  if (ungrouped.length) {
    sections.push({ key: 'ungrouped', label: '其他', group: null, models: ungrouped })
  }
  return sections
})

function modelBelongsToGroup(model, group, groupKey) {
  if (!group && !groupKey) return false
  const candidates = [
    model.group,
    model.group_id,
    model.group_code,
    model.group_name,
  ].map(value => String(value ?? ''))
  const keys = [
    groupKey,
    group?.key,
    group?.id,
    group?.code,
    group?.name,
  ].map(value => String(value ?? '')).filter(Boolean)
  if (keys.some(key => candidates.includes(key))) return true
  if (candidates.some(Boolean)) return false
  return inferAssetModelGroupCode(model) === String(group?.code || group?.key || groupKey || '').toLowerCase()
}

function inferAssetModelGroupCode(model = {}) {
  const explicitGroup = String(model.group_code || '').toLowerCase()
  if (standardAssetModelGroups.some(group => group.code === explicitGroup)) return explicitGroup
  const identity = `${model.code || ''} ${model.name || ''} ${model.group_name || ''}`.toUpperCase()
  if (/(THIRD_PARTY|EXTERNAL|SAAS|API|第三方|外部服务|服务商)/.test(identity)) return 'external'
  if (/(APP_SERVICE|APPLICATION|应用|业务|系统|服务)/.test(identity)) return 'business'
  if (/(CLOUD_SERVER|ECS|VIRTUAL_MACHINE|IDC_SERVER|PHYSICAL|HOST|K8S|KUBERNETES|DOCKER|VSPHERE|ESXI|云主机|虚拟机|机房|物理机|宿主机|容器|集群)/.test(identity)) return 'compute'
  if (/(MYSQL|MARIADB|POSTGRESQL|POSTGRES|MONGODB|MONGO|POLARDB|DATABASE|DB|RDS|数据库|文档数据库)/.test(identity)) return 'database'
  if (/(REDIS|TAIR|KAFKA|ROCKETMQ|RABBITMQ|EMQX|ELASTICSEARCH|NACOS|ZOOKEEPER|MQ|QUEUE|CACHE|缓存|消息|搜索|注册|配置中心|中间件)/.test(identity)) return 'middleware'
  if (/(OBJECT_STORAGE|BLOCK_STORAGE|FILE_STORAGE|OSS|COS|S3|NFS|VOLUME|DISK|对象存储|块存储|文件存储|存储桶|云盘)/.test(identity)) return 'storage'
  if (/(HADOOP|FLINK|CLICKHOUSE|HOLOGRES|MAXCOMPUTE|DATAWORKS|STARROCKS|大数据|数仓|OLAP)/.test(identity)) return 'bigdata'
  if (/(LOAD_BALANCER|SLB|CLB|NAT|EIP|FIREWALL|NGINX|DOMAIN|CERTIFICATE|网关|负载均衡|弹性 IP|防火墙|域名|证书|网络|入口)/.test(identity)) return 'network'
  return ''
}

function overviewDateWithinDays(value, days) {
  if (!value) return false
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return false
  const now = Date.now()
  const diff = date.getTime() - now
  return diff >= 0 && diff <= days * 24 * 60 * 60 * 1000
}

function overviewRowHasUpcomingDate(row = {}, keys = [], days = 60) {
  const attrs = row.attributes || row.ci_attributes || {}
  return keys.some(key => overviewDateWithinDays(attrs[key] || row[key], days))
}

const overviewScopedCapacityRiskRows = computed(() => capacityRiskRows.value.filter(row => overviewMetricMatchesScope(row)))
const overviewScopedArchiveCandidates = computed(() => archiveCandidates.value.filter(overviewRecordMatchesScope))
const overviewScopedSyncFailureRecords = computed(() => syncFailureRecords.value.filter(overviewRecordMatchesScope))
const overviewScopedServiceExpiryRows = computed(() => overviewScopedCiRows.value
  .map(row => ({ row, state: serviceExpiryState(row) }))
  .filter(item => item.state.status !== 'normal'))
const overviewScopedServiceExpirySummary = computed(() => overviewScopedServiceExpiryRows.value.reduce((summary, item) => {
  summary[item.state.status] = (summary[item.state.status] || 0) + 1
  return summary
}, { expired: 0, urgent: 0, warning: 0, missing: 0 }))
const overviewScopedExpiryCount = computed(() => overviewScopedServiceExpiryRows.value.length)
const governanceRiskRows = computed(() => {
  const capacityCount = overviewScopedCapacityRiskRows.value.length
  const syncCount = overviewScopedSyncFailureRecords.value.length
  const archiveCount = overviewScopedArchiveCandidates.value.length
  const serviceExpiryCount = overviewScopedExpiryCount.value
  return [
    { key: 'service_expiry', label: '服务到期', value: serviceExpiryCount, tone: serviceExpiryCount ? 'warning' : 'success', icon: Service },
    { key: 'capacity_risks', label: '容量风险', value: capacityCount, tone: capacityCount ? 'danger' : 'success', icon: Odometer },
    { key: 'sync_failures', label: '同步失败', value: syncCount, tone: syncCount ? 'danger' : 'success', icon: Connection },
    { key: 'archive_candidates', label: '待下线确认', value: archiveCount, tone: archiveCount ? 'warning' : 'success', icon: TakeawayBox },
  ]
})
const overviewSuggestionRows = computed(() => {
  const rows = []
  if (overviewScopedExpiryCount.value) {
    const summary = overviewScopedServiceExpirySummary.value
    const details = overviewScopedServiceExpiryRows.value.map(({ row, state }) => {
      const name = row.name || row.ci_name || `CI#${row.id || '-'}`
      const expiryDate = serviceExpiryDate(row)
      return expiryDate
        ? `${name}（服务到期日 ${expiryDate}，${state.label}）`
        : `${name}（${state.label}）`
    }).join('；')
    rows.push({
      type: 'expiry',
      severity: summary.expired || summary.urgent ? 'critical' : 'warning',
      title: `${overviewScopeTitle.value} 有 ${overviewScopedExpiryCount.value} 项服务到期事项需要处理：${details}`,
    })
  }
  overviewScopedCapacityRiskRows.value.slice(0, 3).forEach((item) => {
    rows.push({
      ...item,
      type: 'capacity',
      severity: capacityRiskStatus(item),
      title: `${item.ci_name || item.name || `CI#${item.ci_id || item.ci || '-'}`} ${metricLabel(item.metric)} ${item.usage_percent ?? '-'}%`,
    })
  })
  if (overviewScopedSyncFailureRecords.value.length) rows.push({ type: 'sync', severity: 'critical', title: `${overviewScopeTitle.value} 有 ${overviewScopedSyncFailureRecords.value.length} 条同步失败记录` })
  if (overviewScopedArchiveCandidates.value.length) rows.push({ type: 'archive', severity: 'warning', title: `${overviewScopeTitle.value} 有 ${overviewScopedArchiveCandidates.value.length} 项待下线确认` })
  return rows.slice(0, 6)
})
const pendingGovernanceCount = computed(() => governanceRiskRows.value.reduce((sum, item) => sum + Number(item.value || 0), 0))
const overviewCostScopeDesc = computed(() => overviewResourceDimension.value === 'business_environment'
  ? '汇总当前业务环境的本月成本与待优化费用项。'
  : '汇总当前云的本月成本与待优化费用项。')
const overviewCostTotalLabel = computed(() => overviewResourceDimension.value === 'business_environment'
  ? '当前业务环境本月费用'
  : '当前云本月费用')
const overviewCostTotal = computed(() => Number(overviewCostReport.value?.total_monthly_cost || 0))
const overviewCostCategoryRows = computed(() => listOf(overviewCostOptimization.value?.by_type)
  .filter(item => Number(item.count || 0) > 0)
  .sort((left, right) => Number(right.count || 0) - Number(left.count || 0))
  .slice(0, 4))
const overviewCostOptimizationCount = computed(() => Number(
  overviewCostOptimization.value?.suggestion_count
  || overviewCostCategoryRows.value.reduce((total, item) => total + Number(item.count || 0), 0),
))
const syncFailureCount = computed(() => {
  const dashboardFailures = Number(dashboard.value.risk_summary?.sync_failures || 0)
  return dashboardFailures || syncJobs.value.reduce((sum, item) => sum + Number(item.summary?.fail || 0), 0)
})
const governanceScopeContextText = computed(() => {
  const context = governanceScopeContext.value
  if (!context) return ''
  const parts = [context.group_name || context.group, context.code].filter(Boolean).join(' / ')
  return `模型风险：${context.name || context.model_name || '-'}${parts ? `（${parts}）` : ''}`
})
const governanceModelMatches = (row) => {
  const context = governanceScopeContext.value
  if (!context) return true
  const modelId = String(context.model_id || context.ci_type || context.id || '')
  const modelName = String(context.name || context.model_name || '').trim()
  const modelCode = String(context.code || '').trim().toUpperCase()
  const values = [
    row?.ci_type,
    row?.ci_type_id,
    row?.model_id,
    row?.ci_type_name,
    row?.ci_model_name,
    row?.after?.ci_type,
    row?.before?.ci_type,
    row?.after?.ci_type_id,
    row?.before?.ci_type_id,
    row?.after?.ci_type_name,
    row?.before?.ci_type_name,
    row?.after?.ci_type_code,
    row?.before?.ci_type_code,
    row?.after?.model_code,
    row?.before?.model_code,
    row?.target_ci_type_code,
    row?.resource_type,
  ].filter(value => value !== undefined && value !== null)
  return values.some((value) => {
    const text = String(value).trim()
    if (!text) return false
    if (modelId && text === modelId) return true
    if (modelName && text === modelName) return true
    if (modelCode && text.toUpperCase() === modelCode) return true
    return false
  })
}
const governanceAssetIndex = computed(() => {
  const byId = new Map()
  const byName = new Map()
  const byUniqueId = new Map()
  ledgerTreeItems.value.forEach((row) => {
    if (row?.id !== undefined && row?.id !== null) byId.set(String(row.id), row)
    if (row?.name) byName.set(String(row.name).trim(), row)
    const uniqueId = ledgerTreeField(row, ['source_unique_id', 'instance_id'])
    if (uniqueId) byUniqueId.set(uniqueId, row)
  })
  return { byId, byName, byUniqueId }
})

function governanceAssetForRow(row = {}) {
  const snapshots = [row?.after, row?.before, row].filter(Boolean)
  const ciValue = typeof row?.ci === 'object' ? row.ci?.id : row?.ci
  const ciId = row?.ci_id || ciValue
  if (ciId !== undefined && ciId !== null && ciId !== '') {
    const matched = governanceAssetIndex.value.byId.get(String(ciId))
    if (matched) return matched
  }
  for (const snapshot of snapshots) {
    const uniqueId = ledgerTreeField(snapshot, ['source_unique_id', 'instance_id'])
    if (uniqueId && governanceAssetIndex.value.byUniqueId.has(uniqueId)) return governanceAssetIndex.value.byUniqueId.get(uniqueId)
    const name = String(snapshot?.ci_name || snapshot?.name || '').trim()
    if (name && governanceAssetIndex.value.byName.has(name)) return governanceAssetIndex.value.byName.get(name)
  }
  const fallback = snapshots.find(snapshot => snapshot && Object.keys(snapshot).length) || row
  const isCollectionFailure = Boolean(
    row?.after?.collection_failed
    || row?.before?.collection_failed
    || String(row?.source_unique_id || '').trim().toLowerCase() === 'collection'
  )
  const context = row?.job_source_context || {}
  if (!isCollectionFailure || !context.source_account) return fallback
  const attributes = fallback?.attributes || fallback?.ci_attributes || {}
  return {
    ...fallback,
    source_account: context.source_account,
    source_region: context.source_region || fallback?.source_region || '',
    source_type: fallback?.source_type || row?.job_source_type || '',
    attributes: {
      ...attributes,
      source_account: context.source_account,
      source_region: context.source_region || attributes.source_region || '',
      provider: context.provider || attributes.provider || '',
    },
  }
}

function governanceTreeMatches(row, context = governanceTreeContext.value) {
  if (!context) return true
  const asset = governanceAssetForRow(row)
  const attrs = asset?.attributes || asset?.ci_attributes || {}
  if (context.view_mode === 'business') {
    const businessLine = ledgerBusinessLineFilter(asset)
    const contextKey = String(context.key || '')
    const isUnassignedBusiness = context.label === '未归属业务线'
      || context.business_line === '未归属业务线'
      || contextKey.includes('未归属业务线')
      || contextKey.includes('unassigned')
    if (isUnassignedBusiness ? Boolean(businessLine) : (context.business_line && businessLine !== context.business_line)) return false
    const environment = normalizeEnvironmentValue(asset?.environment || attrs.environment || attrs.env)
    if (['environment', 'system'].includes(context.level)) {
      const isUnassignedEnvironment = context.label === '未归属环境'
        || !context.environment
        || contextKey.includes('未归属环境')
        || contextKey.includes('未标注环境')
      if (isUnassignedEnvironment ? Boolean(environment) : environment !== normalizeEnvironmentValue(context.environment)) return false
    }
    if (context.system && ledgerSystemText(asset) !== context.system) return false
    return true
  }
  const account = ledgerTreeAccountText(asset)
  if (context.source_account_missing) {
    if (!account.includes('未关联账号')) return false
  } else if (context.source_account && account !== context.source_account) {
    return false
  }
  if (context.source_region && ledgerTreeRegionText(asset) !== context.source_region) return false
  if (context.vsphere_cluster && cleanVsphereCluster(attrs.cluster || attrs.vsphere_cluster) !== context.vsphere_cluster) return false
  if (context.vsphere_host && ledgerTreeText(attrs.host || attrs.host_name || attrs.esxi_host) !== context.vsphere_host) return false
  if (context.source_unique_id && ledgerTreeField(asset, ['source_unique_id', 'instance_id']) !== context.source_unique_id) return false
  return true
}

const governanceRowMatches = row => governanceModelMatches(row) && governanceTreeMatches(row)
const filteredCompletionIssues = computed(() => completionIssues.value.filter(governanceRowMatches))
const filteredArchiveCandidates = computed(() => archiveCandidates.value.filter(governanceRowMatches))
const filteredSyncFailureRecords = computed(() => syncFailureRecords.value.filter(governanceRowMatches))
const syncRelationIssueCount = computed(() => filteredSyncFailureRecords.value.filter(item => item.relation_issue).length)
const syncRelationBulkRecordIds = computed(() => filteredSyncFailureRecords.value.filter(item => item.relation_issue).map(item => item.id).filter(Boolean))
const capacityRiskRows = computed(() => governanceRisks.value.capacity_waterline?.top_risks || dashboard.value.capacity_waterline?.top_risks || [])
const filteredCapacityRows = computed(() => capacityRiskRows.value.filter(governanceRowMatches))
const serviceExpiryRows = computed(() => governanceRisks.value.service_expiry_risks || dashboard.value.service_expiry_risks || [])
const filteredServiceExpiryRows = computed(() => serviceExpiryRows.value.filter(governanceRowMatches))
const governanceFilterCards = computed(() => {
  const syncCount = filteredSyncFailureRecords.value.length
  const capacityCount = filteredCapacityRows.value.length
  const serviceExpiryCount = filteredServiceExpiryRows.value.length
  const cards = [
    { key: 'service_expiry', label: '服务到期', value: serviceExpiryCount, tone: serviceExpiryCount ? 'warning' : 'success', icon: Service, desc: '统一跟进已登记服务周期的续期、替换或下线事项。' },
    { key: 'capacity', label: '容量风险', value: capacityCount, tone: capacityCount ? 'danger' : 'success', icon: Odometer, desc: '按水位策略识别超阈值资源并发起扩容处理。' },
    canViewSync.value ? { key: 'sync', label: '同步失败', value: syncCount, tone: syncCount ? (syncRelationIssueCount.value ? 'danger' : 'warning') : 'success', icon: Connection, desc: '处理采集失败、关系写入失败与资源绑定问题。' } : null,
    { key: 'archive', label: '待下线确认', value: filteredArchiveCandidates.value.length, tone: filteredArchiveCandidates.value.length ? 'warning' : 'success', icon: TakeawayBox, desc: '核对闲置或失联资产，确认归档、恢复或下线。' },
  ]
  return cards.filter(Boolean)
})
const activeGovernanceCard = computed(() => governanceFilterCards.value.find(item => item.key === activeGovernanceKey.value) || governanceFilterCards.value[0])
const activeGovernanceLabel = computed(() => activeGovernanceCard.value?.label || '待下线确认')
const activeGovernanceDescription = computed(() => activeGovernanceCard.value?.desc || '集中处理资产生命周期与运行风险。')
const activeGovernanceCount = computed(() => Number(activeGovernanceCard.value?.value || 0))
const activeGovernanceTagType = computed(() => activeGovernanceCard.value?.tone || 'info')
const activeGovernanceTotalCount = computed(() => governanceFilterCards.value.reduce((sum, item) => sum + Number(item.value || 0), 0))

function governanceCountForTreeContext(context = null) {
  const matches = row => governanceModelMatches(row) && governanceTreeMatches(row, context)
  return archiveCandidates.value.filter(matches).length
    + (canViewSync.value ? syncFailureRecords.value.filter(matches).length : 0)
    + serviceExpiryRows.value.filter(matches).length
    + capacityRiskRows.value.filter(matches).length
}
function flattenResourceNodeRows(nodes, parent = null, trail = []) {
  return (nodes || []).flatMap((node) => {
    const nextTrail = [...trail, node.name].filter(Boolean)
    return [
      {
        ...node,
        parent_name: parent?.name || '',
        parent_path: trail.join(' / '),
        path_label: nextTrail.join(' / '),
        parent: node.parent || parent?.id || '',
        parent_id: node.parent_id || parent?.id || '',
        children_count: (node.children || []).length,
      },
      ...flattenResourceNodeRows(node.children || [], node, nextTrail),
    ]
  })
}
const resourceNodeRows = computed(() => flattenResourceNodeRows(resourceNodeTree.value))
const cloudResourceNodeRows = computed(() => flattenResourceNodeRows(cloudResourceNodeTree.value))
const resourceTreeBusinessOptions = computed(() => resourceNodeTree.value.map(item => ({
  label: item.name,
  value: item.id,
})))
const resourceNodeTypeOptions = computed(() => {
  if (cloudResourceNodeTypes.has(resourceNodeForm.node_type)) return cloudResourceNodeTypeOptions
  return isBusinessLedgerView.value ? businessResourceNodeTypeOptions : cloudResourceNodeTypeOptions
})
const resourceNodeParentRequired = computed(() => Boolean(childResourceNodeParentTypes[resourceNodeForm.node_type]))
const resourceNodeParentOptions = computed(() => {
  const parentTypes = childResourceNodeParentTypes[resourceNodeForm.node_type] || []
  const rows = parentTypes.some(type => cloudResourceNodeTypes.has(type)) ? cloudResourceNodeRows.value : resourceNodeRows.value
  return rows
    .filter(item => parentTypes.includes(item.node_type))
    .map(item => ({
      label: item.path_label || item.name,
      value: item.id,
    }))
})
const resourceNodeParentLabel = computed(() => {
  const labels = (childResourceNodeParentTypes[resourceNodeForm.node_type] || [])
    .map(type => resourceNodeTypeLabels[type])
    .filter(Boolean)
  return labels.join(' / ') || '父节点'
})
const resourceNodeVirtualParentLabel = computed(() => resourceNodeVirtualParentEntry.value?.path_label || resourceNodeVirtualParentEntry.value?.label || '')
const resourceNodeNamePlaceholder = computed(() => {
  const mapping = {
    biz: '例如 core / 交易系统',
    env: '例如 prod / test / dev',
    cloud_account: '例如 阿里云-生产主账号',
    cloud_region: '例如 cn-hangzhou',
    cloud_cluster: '例如 prod-cluster-01',
    cloud_host: '例如 esxi-host-01',
  }
  return mapping[resourceNodeForm.node_type] || '请输入节点名称'
})
const resourceTreeSummaryCards = computed(() => {
  const businessCount = resourceNodeTree.value.length
  const envCount = resourceNodeTree.value.reduce((sum, item) => sum + (item.children || []).length, 0)
  const resourceCount = resourceNodeTree.value.reduce((sum, item) => sum + Number(item.resource_count || 0), 0)
  const requestCount = resourceNodeTree.value.reduce((sum, item) => sum + Number(item.request_count || 0), 0)
  return [
    { key: 'business', label: '业务线', value: businessCount, tone: '' },
    { key: 'environment', label: '环境节点', value: envCount, tone: 'success' },
    { key: 'resources', label: '挂载资源', value: resourceCount, tone: 'info' },
    { key: 'requests', label: '关联申请', value: requestCount || resourceRequests.value.length, tone: 'warning' },
  ]
})
function ledgerTreeText(value) {
  return String(value || '').trim()
}

function ledgerTreeField(row, keys) {
  const attrs = row?.attributes || {}
  const firstSource = primarySourceMapping(row)
  const sourceValues = {
    source_account: firstSource?.source_account,
    source_region: firstSource?.source_region,
    source_unique_id: firstSource?.source_unique_id,
    sync_status: firstSource?.sync_status,
  }
  return keys
    .map(key => ledgerTreeText(sourceValues[key] ?? row?.[key] ?? attrs[key]))
    .find(value => value && value !== '-') || ''
}

function ledgerTreeAccountText(row) {
  if (isThirdPartyLedgerRow(row)) {
    const attrs = row?.attributes || {}
    const scopedAccount = ledgerTreeField(row, [
      'source_account',
      'cloud_account',
      'account_name',
      'account',
      'account_id',
    ])
    if (scopedAccount) return scopedAccount
    return ledgerTreeText(attrs.service_type || attrs.provider || attrs.provider_name || row?.ci_type_name || row?.name || '第三方服务')
  }
  const account = ledgerTreeField(row, [
    'source_account',
    'cloud_account',
    'account_name',
    'account',
    'account_id',
  ])
  const sourceType = ledgerTreeText(ledgerSourceLabel(row))
  if (account) return account
  if (sourceType && !['manual', 'manual_import'].includes(sourceType.toLowerCase())) return '未关联账号 / ' + sourceType
  return '手工录入 / 未关联账号'
}

function ledgerTreeRegionText(row) {
  return ledgerTreeField(row, ['source_region', 'cloud_region', 'region', 'region_id'])
}

function ledgerTreeProviderText(row) {
  const attrs = row?.attributes || {}
  return ledgerTreeText(attrs.provider || attrs.cloud_provider || attrs.provider_name || ledgerSourceLabel(row))
}

function isThirdPartyLedgerRow(row) {
  const attrs = row?.attributes || {}
  const identity = [
    row?.ci_type_name,
    row?.ci_type_code,
    row?.source_label,
    row?.source_type,
    attrs.service_type,
    attrs.provider,
    attrs.provider_name,
  ].filter(Boolean).join(' ')
  return /第三方|EXTERNAL|THIRD_PARTY|SAAS|API|服务商/i.test(identity)
}

function isVsphereLedgerRow(row) {
  const attrs = row?.attributes || {}
  const sourceType = ledgerTreeText(ledgerSourceLabel(row)).toLowerCase()
  const provider = ledgerTreeText(attrs.provider || attrs.cloud_provider || attrs.provider_name).toLowerCase()
  return sourceType.includes('vsphere') || provider.includes('vsphere')
}

function cleanVsphereCluster(value) {
  const text = ledgerTreeText(value)
  return text && !['vm', 'host', 'hosts'].includes(text.toLowerCase()) ? text : ''
}

function createLedgerTreeNode({
  key,
  label,
  level,
  sortOrder = 0,
  hasSortOrder = false,
  sourceAccount,
  sourceAccountMissing,
  sourceRegion = '',
  provider = '',
  vsphereCluster = '',
  vsphereHost = '',
  sourceUniqueId = '',
  businessLine = '',
  businessNode = '',
  environment = '',
  environmentNode = '',
  system = '',
  resourceNodeId = '',
  resourceNodeType = '',
  resourceNodeParentId = '',
  isSynced = false,
  searchText = '',
  parentPathKeys = [],
}) {
  const pathKeys = [...parentPathKeys, key]
  return {
    key,
    label,
    level,
    sort_order: Number(sortOrder || 0),
    has_sort_order: Boolean(hasSortOrder),
    count: 0,
    source_account: sourceAccountMissing ? '' : sourceAccount,
    source_account_missing: sourceAccountMissing ? '1' : '',
    source_region: sourceRegion,
    provider,
    vsphere_cluster: vsphereCluster,
    vsphere_host: vsphereHost,
    source_unique_id: sourceUniqueId,
    business_line: businessLine,
    business_node: businessNode,
    environment,
    environment_node: environmentNode,
    system,
    resource_node_id: resourceNodeId,
    resource_node_type: resourceNodeType,
    resource_node_parent_id: resourceNodeParentId,
    is_synced: Boolean(isSynced),
    searchText,
    pathKeys,
    children: new Map(),
  }
}

function ensureLedgerTreeChild(parent, options) {
  let node = parent.children.get(options.key)
  if (!node) {
    node = createLedgerTreeNode({
      ...options,
      parentPathKeys: parent.pathKeys || [parent.key],
    })
    parent.children.set(options.key, node)
  }
  return node
}

function isLedgerTreeDefaultExpanded(node) {
  return ['account', 'business'].includes(node?.level)
}

function ledgerTreeSortValue(node) {
  const sortOrder = Number(node?.sort_order ?? 0)
  return Number.isFinite(sortOrder) ? sortOrder : 0
}

function ledgerTreeSortPriority(node) {
  return node?.has_sort_order ? 0 : 1
}

function isLedgerTreeNodeExpanded(node) {
  if (!node?.key) return false
  if (collapsedLedgerTreeKeys.value.has(node.key)) return false
  if (expandedLedgerTreeKeys.value.has(node.key)) return true
  return isLedgerTreeDefaultExpanded(node)
}

function flattenLedgerTree(nodes, depth = 0, keyword = '') {
  return [...nodes.values()]
    .sort((left, right) => ledgerTreeSortPriority(left) - ledgerTreeSortPriority(right) || ledgerTreeSortValue(left) - ledgerTreeSortValue(right) || right.count - left.count || left.label.localeCompare(right.label, 'zh-Hans-CN'))
    .flatMap((node) => {
      const hasChildren = node.children.size > 0
      const isExpanded = hasChildren && (keyword || isLedgerTreeNodeExpanded(node))
      const children = isExpanded ? flattenLedgerTree(node.children, depth + 1, keyword) : []
      const searchText = String(node.searchText || node.label || '').toLowerCase()
      const matched = !keyword || searchText.includes(keyword) || children.length > 0
      if (!matched) return []
      return [
        {
          ...node,
          depth,
          has_children: hasChildren,
          is_expanded: Boolean(isExpanded),
          children: undefined,
        },
        ...children,
      ]
    })
}

function pruneEmptyLedgerTreeNodes(nodes) {
  ;[...nodes.entries()].forEach(([key, node]) => {
    pruneEmptyLedgerTreeNodes(node.children)
    if (!node.count && node.children.size === 0 && !node.resource_node_id) {
      nodes.delete(key)
    }
  })
  return nodes
}

function cloudResourceNodeKey(node, parentContext = {}) {
  return `cloud-node:${node?.id || ledgerTreeText(node?.name)}`
}

function cloudResourceNodeGroupIndex(groups) {
  const byId = new Map()
  const visit = (nodes) => {
    ;[...nodes.values()].forEach((node) => {
      if (node.resource_node_id) byId.set(String(node.resource_node_id), node)
      visit(node.children || new Map())
    })
  }
  visit(groups)
  return byId
}

function linkedCloudResourceNodeId(row) {
  const nodeId = row?.resource_node || row?.resource_node_id || row?.attributes?.resource_node_id
  return nodeId ? String(nodeId) : ''
}

function incrementCloudResourceNode(group, groupsById) {
  let current = group
  while (current) {
    current.count += 1
    current = current.resource_node_parent_id
      ? groupsById.get(String(current.resource_node_parent_id))
      : null
  }
}

function appendVsphereResourceGroups(regionGroup, row, context) {
  const attrs = row?.attributes || {}
  const clusterText = cleanVsphereCluster(attrs.cluster || attrs.vsphere_cluster)
  const hostText = ledgerTreeText(attrs.host || attrs.host_name || attrs.esxi_host)
  const sourceUniqueId = ledgerTreeField(row, ['source_unique_id', 'instance_id'])
  const vmText = ledgerTreeText(row?.name || attrs.name || attrs.vm_name || sourceUniqueId)
  const baseSearchText = `${context.accountText} ${context.regionText} ${context.providerText} ${clusterText} ${hostText} ${vmText} ${sourceUniqueId}`.trim()
  let parent = regionGroup
  if (clusterText) {
    parent = ensureLedgerTreeChild(regionGroup, {
      key: `cluster:${context.accountText}:${context.regionText}:${clusterText}`,
      label: clusterText,
      level: 'cluster',
      sourceAccount: context.accountText,
      sourceAccountMissing: context.isUnlinkedAccount,
      sourceRegion: context.regionText,
      provider: context.providerText,
      vsphereCluster: clusterText,
      searchText: baseSearchText,
    })
    parent.count += 1
  }
  if (hostText) {
    const hostGroup = ensureLedgerTreeChild(parent, {
      key: `host:${context.accountText}:${context.regionText}:${clusterText || 'no-cluster'}:${hostText}`,
      label: hostText,
      level: 'host',
      sourceAccount: context.accountText,
      sourceAccountMissing: context.isUnlinkedAccount,
      sourceRegion: context.regionText,
      provider: context.providerText,
      vsphereCluster: clusterText,
      vsphereHost: hostText,
      searchText: baseSearchText,
    })
    hostGroup.count += 1
  }
}

function seedCloudResourceNodeGroups(groups, nodes, parentGroup = null, parentContext = {}) {
  ;(nodes || []).forEach((node) => {
    const name = ledgerTreeText(node.name)
    if (!name) return
    const nodeType = node.node_type
    const key = cloudResourceNodeKey(node, parentContext)
    const nextContext = { ...parentContext }
    let group = parentGroup
    if (nodeType === 'cloud_account') {
      nextContext.account = name
      group = groups.get(key) || createLedgerTreeNode({
        key,
        label: name,
        level: 'account',
        sortOrder: node.sort_order,
        hasSortOrder: true,
        isSynced: node.is_synced,
        sourceAccount: name,
        searchText: name,
      })
      groups.set(key, group)
      group.sort_order = Number(node.sort_order || 0)
      group.has_sort_order = true
    } else if (parentGroup && nodeType === 'cloud_region') {
      nextContext.region = name
      group = ensureLedgerTreeChild(parentGroup, {
        key,
        label: name,
        level: 'region',
        sortOrder: node.sort_order,
        hasSortOrder: true,
        isSynced: node.is_synced,
        sourceAccount: parentContext.account,
        sourceRegion: name,
        searchText: `${parentContext.account || ''} ${name}`.trim(),
      })
      group.sort_order = Number(node.sort_order || 0)
      group.has_sort_order = true
    } else if (parentGroup && nodeType === 'cloud_cluster') {
      nextContext.cluster = name
      group = ensureLedgerTreeChild(parentGroup, {
        key,
        label: name,
        level: 'cluster',
        sortOrder: node.sort_order,
        hasSortOrder: true,
        isSynced: node.is_synced,
        sourceAccount: parentContext.account,
        sourceRegion: parentContext.region,
        vsphereCluster: name,
        searchText: `${parentContext.account || ''} ${parentContext.region || ''} ${name}`.trim(),
      })
      group.sort_order = Number(node.sort_order || 0)
      group.has_sort_order = true
    } else if (parentGroup && nodeType === 'cloud_host') {
      nextContext.host = name
      group = ensureLedgerTreeChild(parentGroup, {
        key,
        label: name,
        level: 'host',
        sortOrder: node.sort_order,
        hasSortOrder: true,
        isSynced: node.is_synced,
        sourceAccount: parentContext.account,
        sourceRegion: parentContext.region,
        vsphereCluster: parentContext.cluster,
        vsphereHost: name,
        searchText: `${parentContext.account || ''} ${parentContext.region || ''} ${parentContext.cluster || ''} ${name}`.trim(),
      })
      group.sort_order = Number(node.sort_order || 0)
      group.has_sort_order = true
    }
    if (!group) return
    group.resource_node_id = node.id
    group.resource_node_type = nodeType
    group.resource_node_parent_id = node.parent_id || node.parent || ''
    group.is_synced = Boolean(node.is_synced)
    seedCloudResourceNodeGroups(groups, node.children || [], group, nextContext)
  })
}

function buildCloudAccountTreeGroups(rows) {
  const groups = new Map()
  seedCloudResourceNodeGroups(groups, cloudResourceNodeTree.value)
  const groupsById = cloudResourceNodeGroupIndex(groups)
  ;(rows || []).forEach((row) => {
    const linkedNode = groupsById.get(linkedCloudResourceNodeId(row))
    if (linkedNode) {
      incrementCloudResourceNode(linkedNode, groupsById)
      if (linkedNode.level === 'region' && isVsphereLedgerRow(row)) {
        const accountText = ledgerTreeAccountText(row)
        const regionText = ledgerTreeRegionText(row)
        appendVsphereResourceGroups(linkedNode, row, {
          accountText,
          regionText,
          providerText: ledgerTreeProviderText(row),
          isUnlinkedAccount: accountText.includes('未关联账号'),
        })
      }
      return
    }
    const accountText = ledgerTreeAccountText(row)
    const regionText = ledgerTreeRegionText(row)
    const providerText = ledgerTreeProviderText(row)
    const isUnlinkedAccount = accountText.includes('未关联账号')
    const accountKey = `account:${accountText}`
    if (isThirdPartyLedgerRow(row) && !groups.has(accountKey)) return
    let accountGroup = groups.get(accountKey)
    if (!accountGroup) {
      accountGroup = createLedgerTreeNode({
        key: accountKey,
        label: accountText,
        level: 'account',
        sourceAccount: accountText,
        sourceAccountMissing: isUnlinkedAccount,
        provider: providerText,
        searchText: `${accountText} ${providerText}`.trim(),
      })
      groups.set(accountKey, accountGroup)
    }
    accountGroup.count += 1

    if (!regionText) return
    const regionGroup = ensureLedgerTreeChild(accountGroup, {
      key: `region:${accountText}:${regionText}`,
      label: regionText,
      level: 'region',
      sourceAccount: accountText,
      sourceAccountMissing: isUnlinkedAccount,
      sourceRegion: regionText,
      provider: providerText,
      searchText: `${accountText} ${regionText} ${providerText}`.trim(),
    })
    regionGroup.count += 1

    if (!isVsphereLedgerRow(row)) return
    appendVsphereResourceGroups(regionGroup, row, {
      accountText,
      regionText,
      providerText,
      isUnlinkedAccount,
    })
  })

  return pruneEmptyLedgerTreeNodes(groups)
}

const ledgerAccountTreeNodes = computed(() => {
  const treeRows = ledgerTreeItems.value.length ? ledgerTreeItems.value : ledgerItems.value
  const keyword = ledgerTreeKeyword.value.trim().toLowerCase()
  return flattenLedgerTree(buildCloudAccountTreeGroups(treeRows), 0, keyword)
})
const ledgerTreeQuickTotal = computed(() => {
  if (!ledgerTreeLoaded.value) return null
  return Array.from(buildCloudAccountTreeGroups(ledgerTreeItems.value).values())
    .reduce((total, node) => total + (Number(node.count) || 0), 0)
})
const filteredLedgerAccountTreeNodes = computed(() => {
  return ledgerAccountTreeNodes.value
})

function ledgerBusinessLineText(row) {
  const attrs = row?.attributes || {}
  const value = row?.business_node_name
    || row?.business_line
    || attrs.business_line
    || attrs.biz
    || attrs.biz_line
    || attrs.business_line_name
    || attrs.app_group
  return ledgerTreeText(value) || '未归属业务线'
}

function ledgerBusinessLineFilter(row) {
  const text = ledgerBusinessLineText(row)
  return text === '未归属业务线' ? '' : text
}

function ledgerEnvironmentText(row) {
  const attrs = row?.attributes || {}
  const value = row?.environment_node_name || row?.environment || attrs.environment || attrs.env
  const normalized = normalizeEnvironmentValue(value)
  return normalized || '未标注环境'
}

function ledgerBusinessEnvironmentText(row) {
  if (!ledgerBusinessLineFilter(row) || !row?.environment) return '未归属环境'
  return environmentText(row.environment_node_name || row.environment)
}

function ledgerEnvironmentDisplay(row) {
  if (isBusinessLedgerView.value && !row?.environment && !row?.environment_display) return '未归属'
  return row?.environment_display || environmentText(row?.environment) || row?.environment || '-'
}

function ledgerBusinessLineDisplay(row) {
  return ledgerBusinessLineFilter(row) || '-'
}

function ledgerBusinessEnvironmentDisplay(row) {
  if (!ledgerBusinessLineFilter(row)) return '-'
  return row.environment_node_name
    ? environmentText(row.environment_node_name)
    : (row?.environment ? environmentText(row.environment) : '-')
}

function ledgerOwnershipDepartmentDisplay(row) {
  return row?.attributes?.department || '-'
}

function ledgerOwnershipAdminDisplay(row) {
  return row?.admin_user || '-'
}

function ledgerSystemText(row) {
  const attrs = row?.attributes || {}
  return ledgerTreeText(
    attrs.system
    || attrs.business_system
    || attrs.app_name
    || attrs.application
    || attrs.service_name
    || '',
  )
}

const ledgerBusinessTreeNodes = computed(() => {
  const groups = new Map()
  resourceNodeTree.value.forEach((biz) => {
    const businessLabel = ledgerTreeText(biz.name)
    if (!businessLabel) return
    const isUnassignedBusiness = businessLabel === '未归属业务线'
    const businessKey = `business:node:${biz.id}`
    let businessGroup = groups.get(businessKey)
    if (!businessGroup) {
      businessGroup = createLedgerTreeNode({
        key: businessKey,
        label: businessLabel,
        level: 'business',
        sortOrder: biz.sort_order,
        hasSortOrder: true,
        businessLine: businessLabel,
        businessNode: biz.id,
        resourceNodeId: biz.id,
        resourceNodeType: 'biz',
        searchText: businessLabel,
      })
      groups.set(businessKey, businessGroup)
    } else if (!businessGroup.resource_node_id) {
      businessGroup.resource_node_id = biz.id
      businessGroup.resource_node_type = 'biz'
    }
    businessGroup.sort_order = Number(biz.sort_order || 0)

    ;(biz.children || []).forEach((env) => {
      const rawEnvironment = ledgerTreeText(env.name)
      if (!rawEnvironment) return
      const environment = normalizeEnvironmentValue(rawEnvironment)
      const environmentLabel = isUnassignedBusiness ? '未归属环境' : environmentText(environment)
      const environmentGroup = ensureLedgerTreeChild(businessGroup, {
        key: `environment:node:${env.id}`,
        label: environmentLabel,
        level: 'environment',
        sortOrder: env.sort_order,
        hasSortOrder: true,
        businessLine: businessLabel,
        businessNode: biz.id,
        environment: isUnassignedBusiness ? '' : environment,
        environmentNode: env.id,
        resourceNodeId: env.id,
        resourceNodeType: 'env',
        resourceNodeParentId: biz.id,
        searchText: `${businessLabel} ${environmentLabel} ${rawEnvironment}`.trim(),
      })
      environmentGroup.resource_node_id = env.id
      environmentGroup.resource_node_type = 'env'
      environmentGroup.resource_node_parent_id = biz.id
      environmentGroup.sort_order = Number(env.sort_order || 0)
    })
  })
  const treeRows = ledgerTreeItems.value.length ? ledgerTreeItems.value : ledgerItems.value
  treeRows.forEach((row) => {
    const businessLabel = ledgerBusinessLineText(row)
    const businessLine = ledgerBusinessLineFilter(row)
    // Legacy assets may only carry names: attach them to the existing tree node.
    const matchedBusiness = resourceNodeTree.value.find(biz => row?.business_node
      ? String(biz.id) === String(row.business_node)
      : ledgerTreeText(biz.name) === businessLabel)
    const businessNode = row?.business_node || matchedBusiness?.id || ''
    const environment = ledgerEnvironmentText(row)
    const matchedEnvironment = (matchedBusiness?.children || []).find(env => normalizeEnvironmentValue(env.name) === normalizeEnvironmentValue(environment))
    const environmentNode = row?.environment_node || matchedEnvironment?.id || ''
    const system = ledgerSystemText(row)
    const modelText = ledgerTreeText(row?.ci_type_name || row?.ci_type_code)
    const resourceText = ledgerTreeText(row?.name || row?.display_name)
    const isUnassignedBusiness = !businessLine
    const environmentLabel = ledgerBusinessEnvironmentText(row)
    const baseSearchText = `${businessLabel} ${environmentLabel} ${environment} ${system} ${modelText} ${resourceText}`.trim()
    const businessKey = businessNode ? `business:node:${businessNode}` : `business:legacy:${businessLabel}`
    let businessGroup = groups.get(businessKey)
    if (!businessGroup) {
      businessGroup = createLedgerTreeNode({
        key: businessKey,
        label: businessLabel,
        level: 'business',
        sortOrder: 0,
        businessLine,
        businessNode,
        searchText: `${businessLabel} ${baseSearchText}`.trim(),
      })
      groups.set(businessKey, businessGroup)
    }
    businessGroup.count += 1

    const environmentGroup = ensureLedgerTreeChild(businessGroup, {
      key: environmentNode
        ? `environment:node:${environmentNode}`
        : `environment:${businessKey}:${isUnassignedBusiness ? 'unassigned' : environment}`,
      label: environmentLabel,
      level: 'environment',
      sortOrder: 0,
      businessLine,
      businessNode,
      environment: isUnassignedBusiness ? '' : (environment === '未标注环境' ? '' : environment),
      environmentNode,
      searchText: `${businessLabel} ${environmentLabel} ${environment} ${baseSearchText}`.trim(),
    })
    environmentGroup.count += 1

    if (!system) return
    const systemGroup = ensureLedgerTreeChild(environmentGroup, {
      key: `system:${businessLabel}:${isUnassignedBusiness ? 'unassigned' : environment}:${system}`,
      label: system,
      level: 'system',
      sortOrder: 0,
      businessLine,
      businessNode,
      environment: isUnassignedBusiness ? '' : (environment === '未标注环境' ? '' : environment),
      environmentNode,
      system,
      searchText: `${businessLabel} ${environmentLabel} ${system} ${modelText} ${resourceText}`.trim(),
    })
    systemGroup.count += 1
  })

  const keyword = ledgerTreeKeyword.value.trim().toLowerCase()
  return flattenLedgerTree(groups, 0, keyword)
})

function isModelCatalogTreeDefaultExpanded(node) {
  return ['account', 'business'].includes(node?.level)
}

function isModelCatalogTreeNodeExpanded(node) {
  if (!node?.key) return false
  if (collapsedModelCatalogTreeKeys.value.has(node.key)) return false
  if (expandedModelCatalogTreeKeys.value.has(node.key)) return true
  return isModelCatalogTreeDefaultExpanded(node)
}

function flattenModelCatalogTree(nodes, depth = 0, keyword = '') {
  return [...nodes.values()]
    .sort((left, right) => ledgerTreeSortPriority(left) - ledgerTreeSortPriority(right) || ledgerTreeSortValue(left) - ledgerTreeSortValue(right) || right.count - left.count || left.label.localeCompare(right.label, 'zh-Hans-CN'))
    .flatMap((node) => {
      const hasChildren = node.children.size > 0
      const isExpanded = hasChildren && (keyword || isModelCatalogTreeNodeExpanded(node))
      const children = isExpanded ? flattenModelCatalogTree(node.children, depth + 1, keyword) : []
      const searchText = String(node.searchText || node.label || '').toLowerCase()
      const matched = !keyword || searchText.includes(keyword) || children.length > 0
      if (!matched) return []
      return [
        {
          ...node,
          depth,
          has_children: hasChildren,
          is_expanded: Boolean(isExpanded),
          children: undefined,
        },
        ...children,
      ]
    })
}

const modelCatalogAccountTreeNodes = computed(() => {
  const groups = buildCloudAccountTreeGroups(modelCatalogSourceRows.value)
  return flattenModelCatalogTree(groups, 0, modelCatalogTreeKeyword.value.trim().toLowerCase())
})

const modelCatalogBusinessTreeNodes = computed(() => {
  const groups = new Map()
  resourceNodeTree.value.forEach((biz) => {
    const businessLabel = ledgerTreeText(biz.name)
    if (!businessLabel) return
    const isUnassignedBusiness = businessLabel === '未归属业务线'
    const businessKey = `model-business:${businessLabel}`
    let businessGroup = groups.get(businessKey)
    if (!businessGroup) {
      businessGroup = createLedgerTreeNode({
        key: businessKey,
        label: businessLabel,
        level: 'business',
        sortOrder: biz.sort_order,
        hasSortOrder: true,
        businessLine: businessLabel,
        businessNode: biz.id,
        resourceNodeId: biz.id,
        resourceNodeType: 'biz',
        searchText: businessLabel,
      })
      groups.set(businessKey, businessGroup)
    }
    businessGroup.sort_order = Number(biz.sort_order || 0)

    ;(biz.children || []).forEach((env) => {
      const rawEnvironment = ledgerTreeText(env.name)
      if (!rawEnvironment) return
      const environment = normalizeEnvironmentValue(rawEnvironment)
      const environmentLabel = isUnassignedBusiness ? '未归属环境' : environmentText(environment)
      const environmentGroup = ensureLedgerTreeChild(businessGroup, {
        key: `model-environment:${businessLabel}:${isUnassignedBusiness ? 'unassigned' : environment}`,
        label: environmentLabel,
        level: 'environment',
        sortOrder: env.sort_order,
        hasSortOrder: true,
        businessLine: businessLabel,
        businessNode: biz.id,
        environment: isUnassignedBusiness ? '' : environment,
        environmentNode: env.id,
        resourceNodeId: env.id,
        resourceNodeType: 'env',
        resourceNodeParentId: biz.id,
        searchText: `${businessLabel} ${environmentLabel} ${rawEnvironment}`.trim(),
      })
      environmentGroup.resource_node_id = env.id
      environmentGroup.resource_node_type = 'env'
      environmentGroup.resource_node_parent_id = biz.id
      environmentGroup.sort_order = Number(env.sort_order || 0)
    })
  })
  modelCatalogSourceRows.value.forEach((row) => {
    const businessLabel = ledgerBusinessLineText(row)
    const businessLine = ledgerBusinessLineFilter(row)
    const environment = ledgerEnvironmentText(row)
    const system = ledgerSystemText(row)
    const modelText = ledgerTreeText(row?.ci_type_name || row?.ci_type_code)
    const resourceText = ledgerTreeText(row?.name || row?.display_name)
    const isUnassignedBusiness = !businessLine
    const environmentLabel = isUnassignedBusiness ? '未归属环境' : ledgerBusinessEnvironmentText(row)
    const baseSearchText = `${businessLabel} ${environmentLabel} ${environment} ${system} ${modelText} ${resourceText}`.trim()
    const businessKey = `model-business:${businessLabel}`
    let businessGroup = groups.get(businessKey)
    if (!businessGroup) {
      businessGroup = createLedgerTreeNode({
        key: businessKey,
        label: businessLabel,
        level: 'business',
        businessLine,
        businessNode: row?.business_node || '',
        searchText: `${businessLabel} ${baseSearchText}`.trim(),
      })
      groups.set(businessKey, businessGroup)
    }
    businessGroup.count += 1

    const environmentGroup = ensureLedgerTreeChild(businessGroup, {
      key: `model-environment:${businessLabel}:${isUnassignedBusiness ? 'unassigned' : environment}`,
      label: environmentLabel,
      level: 'environment',
      businessLine,
      businessNode: row?.business_node || '',
      environment: isUnassignedBusiness ? '' : (environment === '未标注环境' ? '' : environment),
      environmentNode: row?.environment_node || '',
      searchText: `${businessLabel} ${environmentLabel} ${environment} ${baseSearchText}`.trim(),
    })
    environmentGroup.count += 1

    if (!system) return
    const systemGroup = ensureLedgerTreeChild(environmentGroup, {
      key: `model-system:${businessLabel}:${isUnassignedBusiness ? 'unassigned' : environment}:${system}`,
      label: system,
      level: 'system',
      businessLine,
      businessNode: row?.business_node || '',
      environment: isUnassignedBusiness ? '' : (environment === '未标注环境' ? '' : environment),
      environmentNode: row?.environment_node || '',
      system,
      searchText: `${businessLabel} ${environmentLabel} ${system} ${modelText} ${resourceText}`.trim(),
    })
    systemGroup.count += 1
  })

  return flattenModelCatalogTree(groups, 0, modelCatalogTreeKeyword.value.trim().toLowerCase())
})

const isBusinessLedgerView = computed(() => ledgerViewMode.value === 'business')
const activeLedgerTreeNodes = computed(() => (isBusinessLedgerView.value ? ledgerBusinessTreeNodes.value : ledgerAccountTreeNodes.value))
const governanceTotalCount = computed(() => governanceCountForTreeContext())
const governanceLedgerTreeNodes = computed(() => activeLedgerTreeNodes.value.map(entry => ({
  ...entry,
  governance_count: governanceCountForTreeContext({
    ...entry,
    view_mode: isBusinessLedgerView.value ? 'business' : 'cloud',
  }),
})))
const isBusinessModelCatalogTreeView = computed(() => modelCatalogTreeMode.value === 'business')
const activeModelCatalogTreeNodes = computed(() => (isBusinessModelCatalogTreeView.value ? modelCatalogBusinessTreeNodes.value : modelCatalogAccountTreeNodes.value))
const modelCatalogTreeTitle = computed(() => (isBusinessModelCatalogTreeView.value ? '业务环境维度' : '云账号维度'))
const ledgerTreeTitle = computed(() => (isBusinessLedgerView.value ? '业务环境维度' : '云账号维度'))
const ledgerTreeRootCreateType = computed(() => (isBusinessLedgerView.value ? 'biz' : 'cloud_account'))
const ledgerTreeRootCreateTooltip = computed(() => (isBusinessLedgerView.value ? '新增业务线' : '新增云账号'))
const ledgerTreeDesc = computed(() => '')
const ledgerTreeSearchPlaceholder = computed(() => (isBusinessLedgerView.value ? '搜索业务线 / 资产名等' : '搜索云账号 / 资产名等'))
const modelCatalogTreeSearchPlaceholder = computed(() => (isBusinessModelCatalogTreeView.value ? '搜索业务线 / 资产名等' : '搜索云账号 / 资产名等'))
const ledgerTreeEmptyText = computed(() => (isBusinessLedgerView.value ? '暂无业务环境资源' : '暂无云账号资源'))
const ledgerTableTitle = computed(() => (isBusinessLedgerView.value ? '业务环境维度资产台账' : '云账号维度资产台账'))
const ledgerTableDesc = computed(() => (
  isBusinessLedgerView.value
    ? '按业务线、环境、归属和系统筛选当前纳管资产。'
    : '按云账号、资产分类、来源和归属筛选主机、云资源、数据库、中间件与第三方服务。'
))
const ledgerTreeContextHint = computed(() => (
  isBusinessLedgerView.value
    ? '当前按业务环境筛选，可继续叠加模型、状态、负责人等条件。'
    : '当前按账号或地域筛选，可继续叠加模型、状态、负责人等条件。'
))
const ledgerTreeContextExitText = computed(() => (isBusinessLedgerView.value ? '退出业务筛选' : '退出账号筛选'))

function ledgerTreeNodeIcon(entry) {
  const mapping = {
    account: Platform,
    region: OfficeBuilding,
    cluster: Share,
    host: Monitor,
    vm: Box,
    business: Folder,
    environment: FolderChecked,
    system: Collection,
  }
  return mapping[entry?.level] || MostlyCloudy
}

const ledgerTreeContextText = computed(() => {
  const context = ledgerTreeContext.value
  if (!context) return ''
  if (context.view_mode === 'business' || ['business', 'environment', 'system', 'biz', 'env'].includes(context.scope)) {
    const path = [
      context.business_line || context.label,
      context.environment ? environmentText(context.environment) : '',
      context.system,
    ].filter(Boolean).join(' / ')
    return `业务筛选：${path || context.label || '-'}`
  }
  const accountText = context.source_account_missing ? (context.label || '未关联账号') : (context.source_account || '-')
  const path = [
    accountText,
    context.source_region,
    context.vsphere_cluster,
    context.vsphere_host,
    context.scope === 'vm' ? context.label : '',
  ].filter(Boolean).join(' / ')
  if (path) return `账号筛选：${path}`
  return `账号筛选：${accountText}`
})
const governanceTreeContextText = computed(() => {
  const context = governanceTreeContext.value
  if (!context) return ''
  if (context.view_mode === 'business') {
    const path = [
      context.business_line || context.label,
      context.environment ? environmentText(context.environment) : (context.level === 'environment' ? context.label : ''),
      context.system,
    ].filter(Boolean).join(' / ')
    return `业务范围：${path || context.label || '-'}`
  }
  const accountText = context.source_account_missing ? (context.label || '未关联账号') : (context.source_account || context.label || '-')
  const path = [
    accountText,
    context.source_region,
    context.vsphere_cluster,
    context.vsphere_host,
    context.level === 'vm' ? context.label : '',
  ].filter(Boolean).join(' / ')
  return `云资源范围：${path || accountText}`
})
const ledgerSummaryContextText = computed(() => {
  const context = ledgerSummaryContext.value
  if (!context) return ''
  return `概览指标：${context.label || '-'}`
})
const ledgerAuthorizationContextText = computed(() => {
  const context = ledgerAuthorizationContext.value
  if (!context) return ''
  return `授权策略：${context.name || '-'} · ${context.principal || '-'} · ${context.scope || '-'}`
})
const ledgerViewContextText = computed(() => {
  const context = ledgerViewContext.value
  if (!context) return ''
  const scope = [
    context.name,
    context.business_line,
    context.environment ? environmentText(context.environment) : '',
    context.model,
  ].filter(Boolean).join(' · ')
  return `${context.label || '视图钻取'}${scope ? `：${scope}` : ''}`
})
const islandRows = computed(() => listOf(islandAnalysis.value.results || []))
const bulkRelationSuggestions = computed(() => {
  const seen = new Set()
  const rows = []
  islandRows.value.forEach((row) => {
    if (row.issue_type !== 'missing_required_relation' || !row.ci_id || !row.relation_type) return
    if (row.can_auto_create === false || row.governance_status === 'manual_required') return
    const candidate = (row.relation_candidates || [])[0]
    if (!candidate?.id) return
    const source = row.relation_direction === 'incoming' ? candidate.id : row.ci_id
    const target = row.relation_direction === 'incoming' ? row.ci_id : candidate.id
    const key = `${source}:${target}:${row.relation_type}`
    if (seen.has(key)) return
    seen.add(key)
    rows.push({
      source,
      target,
      relation_type: row.relation_type,
      description: `由孤岛分析批量建议创建：${row.ci_name || row.ci_id} ${relationTypeLabel(row.relation_type)} ${candidate.name || candidate.id}`,
      ci_name: row.ci_name || row.ci_id,
      candidate_name: candidate.name || candidate.id,
    })
  })
  return rows
})
const islandSummaryCards = computed(() => {
  const summary = islandAnalysis.value.summary || {}
  if (governanceScopeContext.value) {
    const rows = filteredIslandRows.value
    const countByType = (type) => rows.filter(item => item.issue_type === type).length
    const autoCount = rows.filter(item => islandCanAutoCreate(item)).length
    const manualCount = rows.filter(item => islandNeedsManualRelation(item)).length
    return [
      { key: 'total', label: '孤岛风险', value: rows.length, tone: 'warning' },
      { key: 'ownership', label: '归属缺失', value: countByType('missing_ownership'), tone: 'danger' },
      { key: 'relation', label: '关系断点', value: countByType('no_relation'), tone: 'warning' },
      { key: 'autoCandidate', label: '可自动关联', value: autoCount, tone: 'success' },
      { key: 'manualRequired', label: '需人工确认', value: manualCount, tone: 'danger' },
      { key: 'source', label: '来源缺失', value: countByType('no_source'), tone: 'info' },
    ]
  }
  return [
    { key: 'total', label: '孤岛风险', value: summary.total || islandRows.value.length, tone: 'warning' },
    { key: 'ownership', label: '归属缺失', value: summary.missing_ownership || 0, tone: 'danger' },
    { key: 'relation', label: '关系断点', value: summary.no_relation || 0, tone: 'warning' },
    { key: 'autoCandidate', label: '可自动关联', value: summary.relation_auto_candidate_count || 0, tone: 'success' },
    { key: 'manualRequired', label: '需人工确认', value: summary.relation_manual_required_count || 0, tone: 'danger' },
    { key: 'source', label: '来源缺失', value: summary.no_source || 0, tone: 'info' },
  ]
})
const viewSummaryCards = computed(() => {
  const summary = viewsSummary.value.summary || {}
  const applications = viewMode.value === 'application' ? filteredApplicationViewRows.value : applicationViewRows.value
  const riskCount = applications.filter(item => Number(item.risk_count || 0) > 0).length
  const completeCount = applications.filter(item => Number(item.coverage_rate || 0) >= 100).length
  return [
    { key: 'application', label: '应用数量', value: summary.application_count || 0, hint: '当前范围', tone: 'success' },
    { key: 'host', label: '关联主机', value: summary.host_count || 0, hint: `${summary.relation_count || 0} 条关系`, tone: '' },
    { key: 'healthy', label: '关系完整应用', value: completeCount, hint: applications.length ? `${Math.round(completeCount * 100 / applications.length)}% 覆盖` : '暂无数据', tone: 'info' },
    { key: 'risk', label: '风险应用', value: riskCount, hint: `未归属主机 ${summary.unowned_host_count || 0}`, tone: riskCount ? 'warning' : 'success' },
  ]
})
const applicationViewRows = computed(() => listOf(viewsSummary.value.applications || []))
const hostViewRows = computed(() => listOf(viewsSummary.value.hosts || []))
const physicalViewRows = computed(() => listOf(viewsSummary.value.physical || []))
const viewOwnerOptions = computed(() => Array.from(new Set([
  ...applicationViewRows.value.map(item => item.admin_user),
  ...hostViewRows.value.map(item => item.admin_user),
].filter(Boolean))).sort())
const applicationViewTeamOptions = computed(() => Array.from(new Set(applicationViewRows.value.map(item => item.owner_team).filter(Boolean))).sort((a, b) => a.localeCompare(b, 'zh-CN')))
const viewSearchPlaceholder = computed(() => {
  if (viewMode.value === 'host') return '搜索主机名称 / IP / 负责人'
  if (viewMode.value === 'physical') return '搜索机房 / 机柜 / 区域'
  return '搜索应用名称 / 编码 / 负责人'
})
const viewModeOptions = computed(() => [
  { key: 'application', label: '应用视图', icon: DataBoard, count: applicationViewRows.value.length },
  { key: 'host', label: '主机视图', icon: Monitor, count: hostViewRows.value.length },
  { key: 'physical', label: '机房视图', icon: OfficeBuilding, count: physicalViewRows.value.length },
])
const physicalRoomCount = computed(() => new Set(physicalViewRows.value.map(item => item.room).filter(Boolean)).size)
const physicalHostCount = computed(() => physicalViewRows.value.reduce((total, item) => total + Number(item.host_count || 0), 0))
const physicalOccupiedU = computed(() => physicalViewRows.value.reduce((total, item) => total + Number(item.occupied_u || 0), 0))
const physicalUnassignedRackCount = computed(() => physicalViewRows.value.filter(item => !item.rack || item.rack === '未分配机柜').length)
const opsanyViewTree = computed(() => {
  const rows = viewMode.value === 'host' ? hostViewRows.value : viewMode.value === 'physical' ? physicalViewRows.value : applicationViewRows.value
  const nodes = [{ mode: 'application', key: 'all', label: '全部应用', count: rows.length, scope: 'all' }]
  const groupMap = new Map()
  rows.forEach((row) => {
    const group = viewMode.value === 'physical' ? (row.room || '未分配机房') : (row.business_line || '默认分组')
    const scope = viewMode.value === 'physical' ? 'room' : 'business_line'
    const current = groupMap.get(group) || { mode: viewMode.value, key: `${scope}:${group}`, label: group, count: 0, scope, business_line: scope === 'business_line' ? group : '', room: scope === 'room' ? group : '' }
    current.count += 1
    groupMap.set(group, current)
  })
  nodes[0].mode = viewMode.value
  nodes[0].label = viewMode.value === 'host' ? '全部主机' : viewMode.value === 'physical' ? '全部机柜' : '全部应用'
  return nodes.concat([...groupMap.values()].sort((a, b) => b.count - a.count || a.label.localeCompare(b.label, 'zh-Hans-CN')))
})
const filteredOpsanyViewTree = computed(() => {
  const keyword = opsanyViewKeyword.value.trim().toLowerCase()
  if (!keyword) return opsanyViewTree.value
  return opsanyViewTree.value.filter(item => item.key === 'all' || item.label.toLowerCase().includes(keyword))
})
const activeOpsanyViewNode = computed(() => {
  if (selectedOpsanyViewNode.value.mode !== viewMode.value) {
    return { mode: viewMode.value, key: 'all', scope: 'all' }
  }
  return selectedOpsanyViewNode.value
})
const filteredApplicationViewRows = computed(() => {
  const node = activeOpsanyViewNode.value
  const keyword = applicationViewKeyword.value.trim().toLowerCase()
  return applicationViewRows.value.filter((row) => {
    if (node.scope === 'business_line' && (row.business_line || '默认分组') !== node.business_line) return false
    if (keyword && ![row.name, row.code, row.service_code, row.admin_user, row.owner_team, row.language, row.business_line, row.repo].some(value => String(value || '').toLowerCase().includes(keyword))) return false
    if (applicationViewRisk.value && row.health_status !== applicationViewRisk.value) return false
    if (applicationViewOwner.value && row.admin_user !== applicationViewOwner.value) return false
    if (applicationViewTeam.value && row.owner_team !== applicationViewTeam.value) return false
    if (applicationViewTier.value && row.tier !== applicationViewTier.value) return false
    return true
  })
})
const filteredHostViewRows = computed(() => {
  const node = activeOpsanyViewNode.value
  const keyword = applicationViewKeyword.value.trim().toLowerCase()
  return hostViewRows.value.filter((row) => {
    if (node.scope === 'business_line' && (row.business_line || '默认分组') !== node.business_line) return false
    if (keyword && ![row.name, row.ip, row.ci_type_name, row.admin_user, row.business_line, row.source_type].some(value => String(value || '').toLowerCase().includes(keyword))) return false
    if (applicationViewOwner.value && row.admin_user !== applicationViewOwner.value) return false
    return true
  })
})
const filteredPhysicalViewRows = computed(() => {
  const node = activeOpsanyViewNode.value
  const keyword = applicationViewKeyword.value.trim().toLowerCase()
  return physicalViewRows.value.filter((row) => {
    if (node.scope === 'room' && (row.room || '未分配机房') !== node.room) return false
    if (keyword && ![row.room, row.rack, row.zone, ...(row.business_lines || [])].some(value => String(value || '').toLowerCase().includes(keyword))) return false
    return true
  })
})
const overviewWorkspaces = computed(() => [
  canViewCi.value && { key: 'ledger', label: '资产台账', desc: '主机、云资源、数据库与服务实例', value: dashboard.value.ci_total || 0, icon: List },
  canViewModel.value && { key: 'model', label: '资产分类', desc: '模型分组、字段、关系和资源实例', value: ciTypes.value.length, icon: SetUp },
  canViewCi.value && { key: 'views', label: '视图展示', desc: '应用视图与资源关系', value: viewsSummary.value.summary?.application_count || 0, icon: DataBoard },
  canViewRequests.value && { key: 'requests', label: '资源申请', desc: '申请、审批、交付和自动入库', value: dashboard.value.pending_requests || resourceRequests.value.length, icon: Tickets },
  canViewCi.value && { key: 'governance', label: '治理队列', desc: '补全、下线、负责人和水位风险', value: pendingGovernanceCount.value, icon: Warning },
  canViewAuthorization.value && { key: 'authorization', label: '资源授权', desc: '按用户和用户组控制数据范围', value: authorizationRows.value.length, icon: Lock },
  canViewSync.value && { key: 'sync', label: '资产采集中心', desc: '自动注册、差异预览与失败重试', value: syncFailureCount.value, icon: Connection },
  canViewModel.value && { key: 'model', label: '模型管理', desc: '模型分组、字段和校验约束', value: ciTypes.value.length, icon: SetUp },
  canViewCi.value && { key: 'thresholds', label: '容量策略', desc: '阈值、指标快照和容量风险', value: waterlineRiskCount.value, icon: DataBoard },
  canViewAudit.value && { key: 'audit', label: '操作审计', desc: '资源变更、治理动作和来源追踪', value: auditSummary.value.total || auditLogs.value.length, icon: DocumentChecked },
].filter(Boolean))

const phaseOneGuideSteps = computed(() => [
  canViewSync.value && {
    key: 'sync',
    index: '01',
    title: '跑自动注册',
    desc: '在资产采集中心使用 vSphere、阿里云、华为云和第三方服务模板。',
    target: 'sync',
    tag: `${syncJobs.value.length || 0} 个任务`,
    tagType: syncJobs.value.length ? 'success' : 'info',
  },
  canViewCi.value && {
    key: 'ledger',
    index: '02',
    title: '核对资产台账',
    desc: '检查虚拟机、云主机、阿里云 DB/中间件与和风/高德服务。',
    target: 'ledger',
    tag: `${dashboard.value.ci_total || 0} 个 CI`,
    tagType: dashboard.value.ci_total ? 'success' : 'info',
  },
  canViewCi.value && {
    key: 'views',
    index: '03',
    title: '看视图关系',
    desc: '用应用视图确认资源归属与依赖是否看得清。',
    target: 'views',
    tag: '核心视图',
    tagType: 'primary',
  },
  canViewModel.value && {
    key: 'model',
    index: '04',
    title: '校验模型字段',
    desc: '确认虚拟机、云资源、中间件和第三方服务 CI 字段满足初版登记。',
    target: 'model',
    tag: `${ciTypes.value.length || 0} 个模型`,
    tagType: ciTypes.value.length ? 'success' : 'info',
  },
].filter(Boolean))

const phaseOneRequiredSyncTypes = [
  'vsphere_vm',
  'aliyun_ecs',
  'aliyun_rds',
  'aliyun_ack',
  'aliyun_redis',
  'aliyun_mongodb',
  'aliyun_kafka',
  'aliyun_rocketmq',
  'aliyun_oss',
  'aliyun_disk',
  'aliyun_nas',
  'aliyun_clickhouse',
  'aliyun_hologres',
  'aliyun_maxcompute',
  'aliyun_dataworks',
  'aliyun_slb',
  'aliyun_nat_gateway',
  'aliyun_eip',
  'aliyun_elasticsearch',
  'huaweicloud_ecs',
  'huaweicloud_rds',
  'huaweicloud_redis',
  'huaweicloud_eip',
  'huaweicloud_obs',
  'third_party_import',
]
const aliyunManagedSourceTypes = [
  'aliyun_rds',
  'aliyun_ack',
  'aliyun_redis',
  'aliyun_mongodb',
  'aliyun_kafka',
  'aliyun_rocketmq',
  'aliyun_oss',
  'aliyun_disk',
  'aliyun_nas',
  'aliyun_clickhouse',
  'aliyun_hologres',
  'aliyun_maxcompute',
  'aliyun_dataworks',
  'aliyun_slb',
  'aliyun_nat_gateway',
  'aliyun_eip',
  'aliyun_elasticsearch',
]
const phaseOneRequiredHardwareFields = ['asset_sn', 'idc', 'rack', 'model', 'serial_number', 'cpu', 'memory_gb', 'disk_gb']

function phaseOneRowText(row) {
  const attrs = row?.attributes || {}
  const sources = sourceMappingsOf(row)
    .flatMap(item => [item.source_type, item.source_account, item.source_region, item.source_unique_id])
  return [
    row?.name,
    row?.ci_type_name,
    row?.ci_type_code,
    row?.source_label,
    row?.source_type,
    row?.source_unique_id,
    attrs.source,
    attrs.source_type,
    attrs.source_account,
    attrs.source_region,
    attrs.cloud_provider,
    attrs.provider,
    attrs.account,
    attrs.account_name,
    attrs.region,
    attrs.region_id,
    ...sources,
  ].filter(Boolean).join(' ').toLowerCase()
}

function phaseOneRowMatches(row, keywords) {
  const text = phaseOneRowText(row)
  return keywords.some(keyword => text.includes(String(keyword).toLowerCase()))
}

function phaseOneHasAttribute(row, keys) {
  const attrs = row?.attributes || {}
  return keys.some(key => attrs[key] !== undefined && attrs[key] !== null && attrs[key] !== '')
}

const phaseOneSyncCoverage = computed(() => {
  const types = new Set(syncJobs.value.map(item => item.source_type).filter(Boolean))
  const present = phaseOneRequiredSyncTypes.filter(type => types.has(type))
  return { present: present.length, total: phaseOneRequiredSyncTypes.length }
})

const phaseOneIdcHardwareReadyCount = computed(() => idcLedgerRows.value.filter(row => (
  phaseOneRequiredHardwareFields.every(field => phaseOneHasAttribute(row, [field]))
)).length)

const phaseOneCloudProviderCoverage = computed(() => {
  const rows = cloudLedgerRows.value
  return [
    { key: 'vsphere', label: 'vSphere', ready: rows.some(row => phaseOneRowMatches(row, ['vsphere', 'vmware'])) },
    { key: 'aliyun', label: '阿里云', ready: rows.some(row => phaseOneRowMatches(row, ['aliyun', '阿里云', 'alibaba'])) },
    { key: 'huaweicloud', label: '华为云', ready: rows.some(row => phaseOneRowMatches(row, ['huaweicloud', '华为云'])) },
  ]
})

const phaseOneAliyunMiddlewareRows = computed(() => {
  const rows = ledgerItems.value
  return rows.filter(row => phaseOneRowMatches(row, ['aliyun', '阿里云', 'alibaba']))
})
const phaseOneAliyunMiddlewareTypes = [
  'MYSQL',
  'POSTGRESQL',
  'K8S_CLUSTER',
  'REDIS',
  'MONGODB',
  'KAFKA',
  'ROCKETMQ',
  'ELASTICSEARCH',
  'OBJECT_STORAGE',
  'BLOCK_STORAGE',
  'FILE_STORAGE',
  'CLICKHOUSE',
  'HOLOGRES',
  'MAXCOMPUTE',
  'DATAWORKS',
  'LOAD_BALANCER',
  'NAT_GATEWAY',
  'ELASTIC_IP',
]
function phaseOneMiddlewareTypeKey(row) {
  const code = String(row?.ci_type_code || '').toUpperCase()
  if (phaseOneAliyunMiddlewareTypes.includes(code)) return code
  const name = String(row?.ci_type_name || row?.name || '')
  if (name.includes('PostgreSQL') || name.includes('Postgres')) return 'POSTGRESQL'
  if (name.includes('ACK') || name.includes('K8s') || name.includes('Kubernetes')) return 'K8S_CLUSTER'
  if (name.includes('MySQL') || name.includes('RDS') || name.includes('数据库')) return 'MYSQL'
  if (name.includes('Redis')) return 'REDIS'
  if (name.includes('MongoDB')) return 'MONGODB'
  if (name.includes('Kafka')) return 'KAFKA'
  if (name.includes('RocketMQ')) return 'ROCKETMQ'
  if (name.includes('Elasticsearch')) return 'ELASTICSEARCH'
  if (name.includes('Cloud Disk') || name.includes('Block Storage')) return 'BLOCK_STORAGE'
  if (name.includes('NFS') || name.includes('File Storage')) return 'FILE_STORAGE'
  if (name.includes('ClickHouse')) return 'CLICKHOUSE'
  if (name.includes('Hologres')) return 'HOLOGRES'
  if (name.includes('MaxCompute')) return 'MAXCOMPUTE'
  if (name.includes('DataWorks')) return 'DATAWORKS'
  if (name.includes('对象存储') || name.includes('OSS')) return 'OBJECT_STORAGE'
  if (name.includes('负载均衡') || name.includes('SLB')) return 'LOAD_BALANCER'
  if (name.includes('NAT')) return 'NAT_GATEWAY'
  if (name.includes('Elastic IP') || name.includes('EIP')) return 'ELASTIC_IP'
  return ''
}
const phaseOneAliyunMiddlewareTypeCoverage = computed(() => {
  const codes = new Set(phaseOneAliyunMiddlewareRows.value.map(row => phaseOneMiddlewareTypeKey(row)).filter(Boolean))
  return {
    present: phaseOneAliyunMiddlewareTypes.filter(code => codes.has(code)).length,
    total: phaseOneAliyunMiddlewareTypes.length,
  }
})

const phaseOneThirdPartyProviderCoverage = computed(() => {
  const rows = thirdPartyLedgerRows.value
  return [
    { key: 'heweather', label: '和风天气', ready: rows.some(row => phaseOneRowMatches(row, ['和风天气', 'heweather', 'qweather'])) },
    { key: 'amap', label: '高德地图', ready: rows.some(row => phaseOneRowMatches(row, ['高德地图', 'amap', '高德'])) },
  ]
})

const phaseOneBackendCoverage = computed(() => dashboard.value.phase_one_coverage || null)

const phaseOneCoverageCards = computed(() => {
  const coverageTone = ready => ready ? 'is-ready' : 'is-pending'
  const coverageTag = ready => ready ? 'success' : 'warning'
  const backendCoverage = phaseOneBackendCoverage.value
  if (backendCoverage) {
    const waterline = backendCoverage.waterline || {}
    const waterlineGroups = waterline.groups || []
    const waterlineReady = Boolean(waterline.ready)
    const waterlinePartial = Boolean(waterline.partial)
    const waterlineRequestNeeded = Boolean(waterline.request_needed)
    const syncCoverage = backendCoverage.sync || {}
    const cloudCoverage = backendCoverage.cloud || {}
    const cloudProviders = cloudCoverage.providers || []
    const cloudReady = cloudProviders.filter(item => item.ready)
    const aliyunMiddlewareCoverage = backendCoverage.aliyun_middleware || {}
    const thirdPartyCoverage = backendCoverage.third_party || {}
    const thirdPartyProviders = thirdPartyCoverage.providers || []
    const thirdPartyReady = thirdPartyProviders.filter(item => item.ready)
    return [
      {
        key: 'waterline',
        title: '总资产水位',
        value: waterlineGroups.length ? waterlineGroups.map(item => `${item.label} ${item.ready ? `${item.average}%` : '-'}`).join(' / ') : '待录入',
        desc: waterlineRequestNeeded ? '已有风险水位，建议从卡片发起扩容申请。' : '用于判断 CPU、内存、磁盘是否需要申请扩容。',
        status: waterlineReady ? (waterlineRequestNeeded ? '建议申请' : '已接入') : waterlinePartial ? '部分接入' : '待接入',
        tagType: waterlineReady ? (waterlineRequestNeeded ? 'warning' : 'success') : waterlinePartial ? 'warning' : 'info',
        tone: coverageTone(waterlineReady),
        target: 'thresholds',
        ready: waterlineReady,
      },
      {
        key: 'sync',
        title: '自动注册模板',
        value: `${syncCoverage.present || 0}/${syncCoverage.total || phaseOneRequiredSyncTypes.length}`,
        desc: 'vSphere、阿里云、华为云、第三方服务模板是否齐备。',
        status: syncCoverage.ready ? '已齐备' : '待补齐',
        tagType: coverageTag(syncCoverage.ready),
        tone: coverageTone(syncCoverage.ready),
        target: 'sync',
        ready: Boolean(syncCoverage.ready),
      },
      {
        key: 'cloud',
        title: '虚拟机 / 云主机',
        value: `${cloudCoverage.count || 0} 台`,
        desc: cloudReady.length ? `已识别 ${cloudReady.map(item => item.label).join('、')} 来源，目标是 vSphere 虚拟机、阿里云和华为云主机都能同步。` : '等待 vSphere 虚拟机、阿里云或华为云主机同步结果。',
        status: cloudCoverage.ready ? '已纳管' : cloudCoverage.partial ? '部分纳管' : '待同步',
        tagType: coverageTag(cloudCoverage.ready),
        tone: coverageTone(cloudCoverage.ready),
        target: 'ledger',
        ready: Boolean(cloudCoverage.ready),
      },
      {
        key: 'aliyun-middleware',
        title: '阿里云 DB/中间件',
        value: `${aliyunMiddlewareCoverage.present || 0}/${aliyunMiddlewareCoverage.total || phaseOneAliyunMiddlewareTypes.length} 类`,
        desc: `当前 ${aliyunMiddlewareCoverage.count || 0} 项，目标覆盖 RDS、Redis、MongoDB、Kafka、RocketMQ、OSS、SLB。`,
        status: aliyunMiddlewareCoverage.ready ? '已纳管' : aliyunMiddlewareCoverage.partial ? '部分纳管' : '待同步',
        tagType: coverageTag(aliyunMiddlewareCoverage.ready),
        tone: coverageTone(aliyunMiddlewareCoverage.ready),
        target: 'ledger',
        ready: Boolean(aliyunMiddlewareCoverage.ready),
      },
      {
        key: 'third-party',
        title: '第三方服务',
        value: `${thirdPartyCoverage.count || 0} 项`,
        desc: thirdPartyReady.length ? `已登记 ${thirdPartyReady.map(item => item.label).join('、')}。` : '手工登记和风天气、高德地图等外部服务基本信息。',
        status: thirdPartyCoverage.ready ? '已登记' : thirdPartyCoverage.partial ? '部分登记' : '待登记',
        tagType: coverageTag(thirdPartyCoverage.ready),
        tone: coverageTone(thirdPartyCoverage.ready),
        target: 'ledger',
        ready: Boolean(thirdPartyCoverage.ready),
      },
    ].filter(item => {
      if (item.key === 'sync') return canViewSync.value
      if (item.key === 'waterline') return canViewCi.value
      return canViewCi.value
    })
  }
  const syncCoverage = phaseOneSyncCoverage.value
  const cloudReady = phaseOneCloudProviderCoverage.value.filter(item => item.ready)
  const cloudCoverageReady = cloudReady.length >= phaseOneCloudProviderCoverage.value.length
  const cloudCoveragePartial = cloudReady.length > 0
  const aliyunMiddlewareCoverage = phaseOneAliyunMiddlewareTypeCoverage.value
  const aliyunMiddlewareReady = aliyunMiddlewareCoverage.present >= aliyunMiddlewareCoverage.total
  const aliyunMiddlewarePartial = phaseOneAliyunMiddlewareRows.value.length > 0
  const thirdPartyReady = phaseOneThirdPartyProviderCoverage.value.filter(item => item.ready)
  const thirdPartyCoverageReady = thirdPartyReady.length >= phaseOneThirdPartyProviderCoverage.value.length
  const waterlineReady = aggregateResourceRows.value.some(item => item.hasData)
  const waterlineUsageReady = aggregateResourceRows.value.some(item => item.hasUsage)
  return [
    {
      key: 'waterline',
      title: '总资产水位',
      value: waterlineReady ? aggregateResourceRows.value.map(item => `${item.label} ${item.displayValue}`).join(' / ') : '待录入',
      desc: resourceRequestNeeded.value ? '已有风险水位，建议从卡片发起扩容申请。' : waterlineUsageReady ? '用于判断 CPU、内存、磁盘是否需要申请扩容。' : '已汇总同步规格容量，使用率接入后可判断是否需要扩容。',
      status: waterlineReady ? (resourceRequestNeeded.value ? '建议申请' : waterlineUsageReady ? '已接入' : '规格已同步') : '待接入',
      tagType: waterlineReady ? (resourceRequestNeeded.value ? 'warning' : 'success') : 'info',
      tone: coverageTone(waterlineReady),
      target: 'thresholds',
      ready: waterlineReady,
    },
    {
      key: 'sync',
      title: '自动注册模板',
      value: `${syncCoverage.present}/${syncCoverage.total}`,
      desc: 'vSphere、阿里云、华为云、第三方服务模板是否齐备。',
      status: syncCoverage.present >= syncCoverage.total ? '已齐备' : '待补齐',
      tagType: coverageTag(syncCoverage.present >= syncCoverage.total),
      tone: coverageTone(syncCoverage.present >= syncCoverage.total),
      target: 'sync',
      ready: syncCoverage.present >= syncCoverage.total,
    },
    {
      key: 'cloud',
      title: '虚拟机 / 云主机',
      value: `${cloudLedgerRows.value.length} 台`,
      desc: cloudReady.length ? `已识别 ${cloudReady.map(item => item.label).join('、')} 来源，目标是 vSphere 虚拟机、阿里云和华为云主机都能同步。` : '等待 vSphere 虚拟机、阿里云或华为云主机同步结果。',
      status: cloudCoverageReady ? '已纳管' : cloudCoveragePartial ? '部分纳管' : '待同步',
      tagType: coverageTag(cloudCoverageReady),
      tone: coverageTone(cloudCoverageReady),
      target: 'ledger',
      ready: cloudCoverageReady,
    },
    {
      key: 'aliyun-middleware',
      title: '阿里云 DB/中间件',
      value: `${aliyunMiddlewareCoverage.present}/${aliyunMiddlewareCoverage.total} 类`,
      desc: `当前 ${phaseOneAliyunMiddlewareRows.value.length} 项，目标覆盖 RDS、Redis、MongoDB、Kafka、RocketMQ、OSS、SLB。`,
      status: aliyunMiddlewareReady ? '已纳管' : aliyunMiddlewarePartial ? '部分纳管' : '待同步',
      tagType: coverageTag(aliyunMiddlewareReady),
      tone: coverageTone(aliyunMiddlewareReady),
      target: 'ledger',
      ready: aliyunMiddlewareReady,
    },
    {
      key: 'third-party',
      title: '第三方服务',
      value: `${thirdPartyLedgerRows.value.length} 项`,
      desc: thirdPartyReady.length ? `已登记 ${thirdPartyReady.map(item => item.label).join('、')}。` : '手工登记和风天气、高德地图等外部服务基本信息。',
      status: thirdPartyCoverageReady ? '已登记' : thirdPartyReady.length ? '部分登记' : '待登记',
      tagType: coverageTag(thirdPartyCoverageReady),
      tone: coverageTone(thirdPartyCoverageReady),
      target: 'ledger',
      ready: thirdPartyCoverageReady,
    },
  ].filter(item => {
    if (item.key === 'sync') return canViewSync.value
    if (item.key === 'waterline') return canViewCi.value
    return canViewCi.value
  })
})
const phaseOneCoverageReady = computed(() => phaseOneCoverageCards.value.length > 0 && phaseOneCoverageCards.value.every(item => item.ready))
const phaseOneActionItems = computed(() => {
  const coverage = phaseOneBackendCoverage.value
  const actionTone = done => done ? 'success' : 'warning'
  if (!coverage) {
    const syncCoverage = phaseOneSyncCoverage.value
    const cloudProviders = phaseOneCloudProviderCoverage.value
    const missingCloudProviders = cloudProviders.filter(item => !item.ready)
    const missingCloudLabels = missingCloudProviders.map(item => item.label).filter(Boolean)
    const missingCloudSourceTypes = missingCloudProviders.flatMap((item) => {
      if (item.key === 'vsphere') return ['vsphere_vm']
      if (item.key === 'aliyun') return ['aliyun_ecs']
      if (item.key === 'huaweicloud') return ['huaweicloud_ecs']
      return []
    })
    const aliyunMiddlewareCoverage = phaseOneAliyunMiddlewareTypeCoverage.value
    const aliyunMiddlewareReady = aliyunMiddlewareCoverage.present >= aliyunMiddlewareCoverage.total
    const thirdPartyProviders = phaseOneThirdPartyProviderCoverage.value
    const missingThirdPartyLabels = thirdPartyProviders.filter(item => !item.ready).map(item => item.label).filter(Boolean)
    const cloudReady = cloudProviders.every(item => item.ready)
    const thirdPartyReady = thirdPartyProviders.every(item => item.ready)
    const waterlineReady = aggregateResourceRows.value.some(item => item.hasData)
    const waterlineUsageReady = aggregateResourceRows.value.some(item => item.hasUsage)
    return [
      {
        key: 'waterline',
        coverageKey: 'waterline',
        title: resourceRequestNeeded.value ? '处理容量水位风险' : waterlineReady ? '复核总资源视图' : '接入 CPU/内存/磁盘水位',
        desc: resourceRequestNeeded.value ? '已有超阈值资源，进入水位策略查看风险并发起容量申请。' : waterlineUsageReady ? 'CPU、内存、磁盘已有最近水位，可从概览判断是否需要申请。' : waterlineReady ? 'CPU、内存、磁盘已汇总同步规格容量，继续接入使用率后可判断是否需要扩容。' : '录入或同步 CPU、内存、磁盘指标快照后，概览会自动汇总。',
        status: resourceRequestNeeded.value ? '建议申请' : waterlineReady ? (waterlineUsageReady ? '已接入' : '规格已同步') : '待接入',
        tagType: resourceRequestNeeded.value ? 'warning' : actionTone(waterlineReady),
        done: Boolean(waterlineReady && !resourceRequestNeeded.value),
        target: 'thresholds',
      },
      {
        key: 'sync',
        coverageKey: 'sync',
        title: syncCoverage.present >= syncCoverage.total ? '复核自动注册模板' : '补齐自动注册模板',
        desc: syncCoverage.present >= syncCoverage.total ? `初版 ${syncCoverage.present}/${syncCoverage.total} 个模板已就绪。` : `当前 ${syncCoverage.present}/${syncCoverage.total} 个模板，先补齐后再联调真实账号。`,
        status: syncCoverage.present >= syncCoverage.total ? '已齐备' : '待补齐',
        tagType: actionTone(syncCoverage.present >= syncCoverage.total),
        done: syncCoverage.present >= syncCoverage.total,
        target: 'sync',
      },
      {
        key: 'cloud',
        coverageKey: 'cloud',
        title: cloudReady ? '复核虚拟机 / 云主机来源' : `联调${missingCloudLabels.length ? missingCloudLabels.join('、') : '服务器资源'}同步`,
        desc: cloudReady ? 'vSphere 虚拟机、阿里云和华为云主机均已有同步结果。' : '进入资产采集中心聚焦缺失来源，先预览再执行，确认私有云资源注册到虚拟机模型，公有云 ECS 注册到云主机模型。',
        status: cloudReady ? '已纳管' : cloudProviders.some(item => item.ready) ? '部分纳管' : '待同步',
        tagType: actionTone(cloudReady),
        done: cloudReady,
        target: cloudReady ? 'ledger' : 'sync',
        sourceTypes: missingCloudSourceTypes,
      },
      {
        key: 'aliyun-middleware',
        coverageKey: 'aliyun-middleware',
        title: aliyunMiddlewareReady ? '复核阿里云 DB/中间件' : '补齐阿里云 DB/中间件',
        desc: aliyunMiddlewareReady ? 'RDS、Redis、MongoDB、Kafka、RocketMQ、OSS、SLB 均已有纳管数据。' : `当前 ${aliyunMiddlewareCoverage.present}/${aliyunMiddlewareCoverage.total} 类，继续联调阿里云中间件模板。`,
        status: aliyunMiddlewareReady ? '已纳管' : phaseOneAliyunMiddlewareRows.value.length ? '部分纳管' : '待同步',
        tagType: actionTone(aliyunMiddlewareReady),
        done: aliyunMiddlewareReady,
        target: aliyunMiddlewareReady ? 'ledger' : 'sync',
        sourceTypes: aliyunManagedSourceTypes,
      },
      {
        key: 'third-party',
        coverageKey: 'third-party',
        title: thirdPartyReady ? '复核第三方服务' : `登记${missingThirdPartyLabels.length ? missingThirdPartyLabels.join('、') : '第三方服务'}`,
        desc: thirdPartyReady ? '和风天气、高德地图等第三方服务基本信息已登记。' : '只登记服务、账号、负责人和服务到期信息，不保存 API Key 明文。',
        status: thirdPartyReady ? '已登记' : thirdPartyProviders.some(item => item.ready) ? '部分登记' : '待登记',
        tagType: actionTone(thirdPartyReady),
        done: thirdPartyReady,
        target: thirdPartyReady ? 'ledger' : 'sync',
        sourceTypes: ['third_party_import'],
      },
    ].sort((left, right) => Number(left.done) - Number(right.done))
  }

  const waterline = coverage.waterline || {}
  const sync = coverage.sync || {}
    const cloud = coverage.cloud || {}
  const aliyunMiddleware = coverage.aliyun_middleware || {}
  const thirdParty = coverage.third_party || {}
  const missingCloudProviders = (cloud.providers || []).filter(item => !item.ready)
  const missingThirdPartyProviders = (thirdParty.providers || []).filter(item => !item.ready)
  const missingCloudLabels = missingCloudProviders.map(item => item.label).filter(Boolean)
  const missingThirdPartyLabels = missingThirdPartyProviders.map(item => item.label).filter(Boolean)
  const missingCloudSourceTypes = missingCloudProviders.flatMap(item => item.source_types || []).filter(Boolean)

  return [
    {
      key: 'waterline',
      coverageKey: 'waterline',
      title: waterline.request_needed ? '处理容量水位风险' : waterline.ready ? '复核总资产水位' : '接入 CPU/内存/磁盘水位',
      desc: waterline.request_needed ? '已有超阈值资源，进入水位策略查看风险并发起容量申请。' : waterline.ready ? 'CPU、内存、磁盘已有最近水位，可从概览判断是否需要申请。' : '录入或同步 CPU、内存、磁盘指标快照后，概览会自动汇总。',
      status: waterline.request_needed ? '建议申请' : waterline.ready ? '已接入' : '待接入',
      tagType: waterline.request_needed ? 'warning' : actionTone(waterline.ready),
      done: Boolean(waterline.ready && !waterline.request_needed),
      target: 'thresholds',
    },
    {
      key: 'sync',
      coverageKey: 'sync',
      title: sync.ready ? '复核自动注册模板' : '补齐自动注册模板',
      desc: sync.ready ? `初版 ${sync.present || 0}/${sync.total || phaseOneRequiredSyncTypes.length} 个模板已就绪。` : `仍缺 ${(sync.missing || []).length} 个模板，先补齐后再联调真实账号。`,
      status: sync.ready ? '已齐备' : '待补齐',
      tagType: actionTone(sync.ready),
      done: Boolean(sync.ready),
      target: 'sync',
    },
    {
      key: 'cloud',
      coverageKey: 'cloud',
      title: cloud.ready ? '复核虚拟机 / 云主机来源' : `联调${missingCloudLabels.length ? missingCloudLabels.join('、') : '服务器资源'}同步`,
      desc: cloud.ready ? 'vSphere 虚拟机、阿里云和华为云主机均已有同步结果。' : '进入资产采集中心聚焦缺失来源，先预览再执行，确认私有云资源注册到虚拟机模型，公有云 ECS 注册到云主机模型。',
      status: cloud.ready ? '已纳管' : cloud.partial ? '部分纳管' : '待同步',
      tagType: actionTone(cloud.ready),
      done: Boolean(cloud.ready),
      target: cloud.ready ? 'ledger' : 'sync',
      sourceTypes: missingCloudSourceTypes,
    },
    {
      key: 'aliyun-middleware',
      coverageKey: 'aliyun-middleware',
      title: aliyunMiddleware.ready ? '复核阿里云 DB/中间件' : '补齐阿里云 DB/中间件',
      desc: aliyunMiddleware.ready ? 'RDS、Redis、MongoDB、Kafka、RocketMQ、OSS、SLB 均已有纳管数据。' : `当前 ${aliyunMiddleware.present || 0}/${aliyunMiddleware.total || phaseOneAliyunMiddlewareTypes.length} 类，继续联调阿里云中间件模板。`,
      status: aliyunMiddleware.ready ? '已纳管' : aliyunMiddleware.partial ? '部分纳管' : '待同步',
      tagType: actionTone(aliyunMiddleware.ready),
      done: Boolean(aliyunMiddleware.ready),
      target: aliyunMiddleware.ready ? 'ledger' : 'sync',
      sourceTypes: aliyunManagedSourceTypes,
    },
    {
      key: 'third-party',
      coverageKey: 'third-party',
      title: thirdParty.ready ? '复核第三方服务' : `登记${missingThirdPartyLabels.length ? missingThirdPartyLabels.join('、') : '第三方服务'}`,
      desc: thirdParty.ready ? '和风天气、高德地图等第三方服务基本信息已登记。' : '只登记服务、账号、负责人和服务到期信息，不保存 API Key 明文。',
      status: thirdParty.ready ? '已登记' : thirdParty.partial ? '部分登记' : '待登记',
      tagType: actionTone(thirdParty.ready),
      done: Boolean(thirdParty.ready),
      target: thirdParty.ready ? 'ledger' : 'sync',
      sourceTypes: ['third_party_import'],
    },
  ].sort((left, right) => Number(left.done) - Number(right.done))
})
const phaseOnePendingActionCount = computed(() => phaseOneActionItems.value.filter(item => !item.done).length)

const overviewWorkspaceGroups = computed(() => {
  const entryMap = new Map(overviewWorkspaces.value.map(item => [item.key, item]))
  return workspaceGroupDefinitions
    .filter(group => group.key !== 'overview')
    .map(group => ({ ...group, items: group.children.map(key => entryMap.get(key)).filter(Boolean) }))
    .filter(group => group.items.length)
})

const businessLineOptions = computed(() => Array.from(new Set([
  ...(dashboard.value.ci_by_business || []).map(item => item.business_line),
  ...ledgerItems.value.map(item => item.business_line),
  ...resourceNodeTree.value.map(item => item.name),
].filter(Boolean))).sort())
const sourceTypeOptions = computed(() => Array.from(new Set([
  ...(dashboard.value.ci_by_source || []).map(item => item.source_type || item.source),
  ...ledgerItems.value.map(item => item.source_label || item.source_type || item.attributes?.source_type || item.attributes?.source),
  ...syncJobs.value.map(item => item.source_type),
  ...sourceMappings.value.map(item => item.source_type),
].filter(Boolean))).sort())
const thirdPartyType = computed(() => ciTypes.value.find(item => item.code === 'THIRD_PARTY_SERVICE' || item.name === '第三方服务'))
const isThirdPartyLedgerMode = computed(() => {
  if (!ledgerFilters.ci_type || !thirdPartyType.value) return false
  return String(ledgerFilters.ci_type) === String(thirdPartyType.value.id)
})
const thirdPartyExpirySummaryRows = computed(() => [
  { key: '', label: '全部状态', value: Number(thirdPartyExpirySummary.value.total || 0), tone: 'info' },
  { key: 'expired', label: '已到期', value: Number(thirdPartyExpirySummary.value.expired || 0), tone: 'danger' },
  { key: 'urgent', label: '7 天内到期', value: Number(thirdPartyExpirySummary.value.urgent || 0), tone: 'danger' },
  { key: 'warning', label: '提醒期', value: Number(thirdPartyExpirySummary.value.warning || 0), tone: 'warning' },
  { key: 'normal', label: '正常', value: Number(thirdPartyExpirySummary.value.normal || 0), tone: 'success' },
  { key: 'missing', label: '未登记', value: Number(thirdPartyExpirySummary.value.missing || 0), tone: 'info' },
])
const modelThirdPartyExpirySummaryRows = computed(() => [
  { key: '', label: '全部状态', value: Number(modelThirdPartyExpirySummary.value.total || 0), tone: 'info' },
  { key: 'expired', label: '已到期', value: Number(modelThirdPartyExpirySummary.value.expired || 0), tone: 'danger' },
  { key: 'urgent', label: '7 天内到期', value: Number(modelThirdPartyExpirySummary.value.urgent || 0), tone: 'danger' },
  { key: 'warning', label: '提醒期', value: Number(modelThirdPartyExpirySummary.value.warning || 0), tone: 'warning' },
  { key: 'normal', label: '正常', value: Number(modelThirdPartyExpirySummary.value.normal || 0), tone: 'success' },
  { key: 'missing', label: '未登记', value: Number(modelThirdPartyExpirySummary.value.missing || 0), tone: 'info' },
])
const thirdPartyLedgerRows = computed(() => ledgerItems.value.filter(item => {
  if (thirdPartyType.value && String(item.ci_type) === String(thirdPartyType.value.id)) return true
  return item.ci_type_name === '第三方服务'
}))
const thirdPartyAttributeOptions = (key) => computed(() => Array.from(new Set(
  thirdPartyLedgerRows.value.map(item => item.attributes?.[key]).filter(Boolean),
)).sort())
const thirdPartyServiceTypeOptions = thirdPartyAttributeOptions('service_type')
const thirdPartyProviderOptions = thirdPartyAttributeOptions('provider')
const cloudType = computed(() => ciTypes.value.find(item => item.code === 'CLOUD_SERVER' || String(item.name || '').includes('云主机') || String(item.name || '').includes('ECS')))
const virtualMachineType = computed(() => ciTypes.value.find(item => item.code === 'VIRTUAL_MACHINE' || String(item.name || '').includes('虚拟机')))
const cloudScopedTypes = computed(() => ciTypes.value.filter((item) => {
  const code = String(item.code || '').toUpperCase()
  const name = String(item.name || '')
  return ['CLOUD_SERVER', 'VIRTUAL_MACHINE', 'K8S_CLUSTER'].includes(code)
    || name.includes('云主机')
    || name.includes('ECS')
    || name.includes('虚拟机')
    || name.includes('K8s')
    || name.includes('Kubernetes')
}))
const isCloudLedgerMode = computed(() => {
  if (!ledgerFilters.ci_type) return false
  return cloudScopedTypes.value.some(item => String(item.id) === String(ledgerFilters.ci_type))
})
const cloudLedgerRows = computed(() => ledgerItems.value.filter(item => {
  if (cloudType.value && String(item.ci_type) === String(cloudType.value.id)) return true
  if (virtualMachineType.value && String(item.ci_type) === String(virtualMachineType.value.id)) return true
  if (String(item.ci_type_code || '').toUpperCase() === 'K8S_CLUSTER') return true
  const name = String(item.ci_type_name || '')
  return name.includes('云主机') || name.includes('ECS') || name.includes('虚拟机') || name.includes('K8s') || name.includes('Kubernetes') || ['CLOUD_SERVER', 'VIRTUAL_MACHINE', 'K8S_CLUSTER'].includes(item.ci_type_code)
}))
const cloudAttributeOptions = (keys) => computed(() => Array.from(new Set(
  cloudLedgerRows.value.flatMap(item => keys.map(key => item.attributes?.[key]))
    .concat(sourceMappings.value.map(item => (keys.includes('source_account') ? item.source_account : keys.includes('source_region') ? item.source_region : '')))
    .filter(Boolean),
)).sort())
const cloudAccountOptions = cloudAttributeOptions(['source_account', 'cloud_account', 'account', 'account_id', 'account_name'])
const cloudRegionOptions = cloudAttributeOptions(['source_region', 'cloud_region', 'region', 'region_id'])
const cloudZoneOptions = cloudAttributeOptions(['availability_zone', 'zone_id', 'zone', 'az'])
const dataServiceTypes = computed(() => ciTypes.value.filter((item) => {
  const code = String(item.code || '').toUpperCase()
  const name = String(item.name || '')
  return ['MYSQL', 'POSTGRESQL', 'REDIS', 'MONGODB', 'KAFKA', 'ROCKETMQ', 'ELASTICSEARCH', 'CLICKHOUSE', 'HOLOGRES', 'MAXCOMPUTE', 'DATAWORKS'].includes(code)
    || name.includes('数据库')
    || name.includes('MySQL')
    || name.includes('PostgreSQL')
    || name.includes('Postgres')
    || name.includes('RDS')
    || name.includes('Redis')
    || name.includes('MongoDB')
    || name.includes('Kafka')
    || name.includes('RocketMQ')
    || name.includes('Elasticsearch')
    || name.includes('ClickHouse')
    || name.includes('Hologres')
    || name.includes('MaxCompute')
    || name.includes('DataWorks')
}))
const isDataServiceLedgerMode = computed(() => {
  if (!ledgerFilters.ci_type) return false
  return dataServiceTypes.value.some(item => String(item.id) === String(ledgerFilters.ci_type))
})
const dataServiceLedgerRows = computed(() => ledgerItems.value.filter((item) => {
  const code = String(item.ci_type_code || '').toUpperCase()
  const name = String(item.ci_type_name || '')
  return ['MYSQL', 'POSTGRESQL', 'REDIS', 'MONGODB', 'KAFKA', 'ROCKETMQ', 'ELASTICSEARCH', 'CLICKHOUSE', 'HOLOGRES', 'MAXCOMPUTE', 'DATAWORKS'].includes(code)
    || name.includes('数据库')
    || name.includes('MySQL')
    || name.includes('PostgreSQL')
    || name.includes('Postgres')
    || name.includes('RDS')
    || name.includes('Redis')
    || name.includes('MongoDB')
    || name.includes('Kafka')
    || name.includes('RocketMQ')
    || name.includes('Elasticsearch')
    || name.includes('ClickHouse')
    || name.includes('Hologres')
    || name.includes('MaxCompute')
    || name.includes('DataWorks')
}))
const dataServiceAttributeOptions = (keys) => computed(() => Array.from(new Set(
  dataServiceLedgerRows.value.flatMap(item => keys.map(key => item.attributes?.[key])).filter(Boolean),
)).sort())
const dataServiceEngineOptions = dataServiceAttributeOptions(['engine', 'db_engine', 'middleware_engine'])
const dataServiceVpcOptions = dataServiceAttributeOptions(['vpc_id', 'vpc'])
const dataServiceNetworkOptions = dataServiceAttributeOptions(['network_type', 'network'])
const ledgerSyncStatusOptions = [
  { label: '成功', value: 'success' },
  { label: '失败', value: 'failed' },
  { label: '来源缺失', value: 'missing' },
  { label: '冲突', value: 'conflict' },
]
const objectStorageTypes = computed(() => ciTypes.value.filter((item) => {
  const code = String(item.code || '').toUpperCase()
  const name = String(item.name || '')
  return code === 'OBJECT_STORAGE' || name.includes('对象存储') || name.includes('OSS')
}))
const loadBalancerTypes = computed(() => ciTypes.value.filter((item) => {
  const code = String(item.code || '').toUpperCase()
  const name = String(item.name || '')
  return code === 'LOAD_BALANCER' || name.includes('负载均衡') || name.includes('SLB')
}))
const storageServiceTypes = computed(() => ciTypes.value.filter((item) => {
  const code = String(item.code || '').toUpperCase()
  const name = String(item.name || '')
  return ['BLOCK_STORAGE', 'FILE_STORAGE'].includes(code) || name.includes('块存储') || name.includes('文件存储') || name.includes('云盘') || name.includes('NFS')
}))
const networkServiceTypes = computed(() => ciTypes.value.filter((item) => {
  const code = String(item.code || '').toUpperCase()
  const name = String(item.name || '')
  return ['NAT_GATEWAY', 'ELASTIC_IP'].includes(code) || name.includes('NAT') || name.includes('弹性 IP') || name.includes('EIP')
}))
const isObjectStorageLedgerMode = computed(() => {
  if (!ledgerFilters.ci_type) return false
  return objectStorageTypes.value.some(item => String(item.id) === String(ledgerFilters.ci_type))
})
const isLoadBalancerLedgerMode = computed(() => {
  if (!ledgerFilters.ci_type) return false
  return loadBalancerTypes.value.some(item => String(item.id) === String(ledgerFilters.ci_type))
})
const isStorageServiceLedgerMode = computed(() => {
  if (!ledgerFilters.ci_type) return false
  return storageServiceTypes.value.some(item => String(item.id) === String(ledgerFilters.ci_type))
})
const isNetworkServiceLedgerMode = computed(() => {
  if (!ledgerFilters.ci_type) return false
  return networkServiceTypes.value.some(item => String(item.id) === String(ledgerFilters.ci_type))
})
const isNetworkedEdgeLedgerMode = computed(() => isLoadBalancerLedgerMode.value || isNetworkServiceLedgerMode.value)
const isEdgeServiceLedgerMode = computed(() => isObjectStorageLedgerMode.value || isLoadBalancerLedgerMode.value || isStorageServiceLedgerMode.value || isNetworkServiceLedgerMode.value)
const edgeServiceLedgerRows = computed(() => ledgerItems.value.filter((item) => {
  const code = String(item.ci_type_code || '').toUpperCase()
  const name = String(item.ci_type_name || '')
  return ['OBJECT_STORAGE', 'LOAD_BALANCER', 'BLOCK_STORAGE', 'FILE_STORAGE', 'NAT_GATEWAY', 'ELASTIC_IP'].includes(code)
    || name.includes('对象存储')
    || name.includes('OSS')
    || name.includes('OBS')
    || name.includes('块存储')
    || name.includes('文件存储')
    || name.includes('云盘')
    || name.includes('NFS')
    || name.includes('负载均衡')
    || name.includes('SLB')
    || name.includes('NAT')
    || name.includes('弹性 IP')
    || name.includes('EIP')
}))
const edgeAttributeOptions = (keys) => computed(() => Array.from(new Set(
  edgeServiceLedgerRows.value.flatMap(item => keys.map(key => item.attributes?.[key])).filter(Boolean),
)).sort())
const objectStorageClassOptions = edgeAttributeOptions(['storage_class', 'storage_type'])
const objectStorageAclOptions = edgeAttributeOptions(['acl', 'access_control'])
const edgeVpcOptions = edgeAttributeOptions(['vpc_id', 'vpc'])
const edgeNetworkOptions = edgeAttributeOptions(['network_type', 'network'])
const idcType = computed(() => ciTypes.value.find(item => ['IDC_SERVER', 'PHYSICAL_SERVER'].includes(item.code) || ['机房服务器', '物理机'].includes(item.name)))
const isIdcLedgerMode = computed(() => {
  if (!ledgerFilters.ci_type || !idcType.value) return false
  return String(ledgerFilters.ci_type) === String(idcType.value.id)
})
const idcLedgerRows = computed(() => ledgerItems.value.filter(item => {
  if (idcType.value && String(item.ci_type) === String(idcType.value.id)) return true
  return ['机房服务器', '物理机'].includes(item.ci_type_name)
}))
const idcAttributeOptions = (keys) => computed(() => Array.from(new Set(
  idcLedgerRows.value.flatMap(item => keys.map(key => item.attributes?.[key])).filter(Boolean),
)).sort())
const idcRoomOptions = idcAttributeOptions(['idc', 'machine_room', 'room', 'datacenter'])
const idcRackOptions = idcAttributeOptions(['rack', 'cabinet'])
const idcLifecycleOptions = [
  { value: 'pending_rack', label: '待上架' },
  { value: 'running', label: '运行中' },
  { value: 'maintenance', label: '维修中' },
  { value: 'pending_offline', label: '待下线' },
  { value: 'offline', label: '已下线' },
  { value: 'retired', label: '已报废' },
]
const modelResourceFilterCiType = computed(() => modelResourceFilters.ci_type || selectedModelId.value)
function ciTypeInOptions(ciType, options) {
  if (!ciType) return false
  return options.value.some(item => String(item.id) === String(ciType))
}
const isThirdPartyModelResourceMode = computed(() => Boolean(modelResourceFilterCiType.value && thirdPartyType.value && String(modelResourceFilterCiType.value) === String(thirdPartyType.value.id)))
const isCloudModelResourceMode = computed(() => ciTypeInOptions(modelResourceFilterCiType.value, cloudScopedTypes))
const isDataServiceModelResourceMode = computed(() => ciTypeInOptions(modelResourceFilterCiType.value, dataServiceTypes))
const isObjectStorageModelResourceMode = computed(() => ciTypeInOptions(modelResourceFilterCiType.value, objectStorageTypes))
const isLoadBalancerModelResourceMode = computed(() => ciTypeInOptions(modelResourceFilterCiType.value, loadBalancerTypes))
const isStorageServiceModelResourceMode = computed(() => ciTypeInOptions(modelResourceFilterCiType.value, storageServiceTypes))
const isNetworkServiceModelResourceMode = computed(() => ciTypeInOptions(modelResourceFilterCiType.value, networkServiceTypes))
const isNetworkedEdgeModelResourceMode = computed(() => isLoadBalancerModelResourceMode.value || isNetworkServiceModelResourceMode.value)
const isEdgeServiceModelResourceMode = computed(() => isObjectStorageModelResourceMode.value || isLoadBalancerModelResourceMode.value || isStorageServiceModelResourceMode.value || isNetworkServiceModelResourceMode.value)
const isIdcModelResourceMode = computed(() => Boolean(modelResourceFilterCiType.value && idcType.value && String(modelResourceFilterCiType.value) === String(idcType.value.id)))
const tagCategoryOptions = computed(() => Array.from(new Set(ciTags.value.map(item => item.category).filter(Boolean))).sort())
const activeTagOptions = computed(() => ciTags.value.filter(item => item.is_active !== false))
const tagSummaryCards = computed(() => {
  const activeCount = ciTags.value.filter(item => item.is_active !== false).length
  const boundCount = ciTags.value.filter(item => Number(item.ci_count || 0) > 0).length
  return [
    { key: 'total', label: '标签总数', value: ciTags.value.length, tone: '' },
    { key: 'active', label: '启用标签', value: activeCount, tone: 'success' },
    { key: 'bound', label: '已关联标签', value: boundCount, tone: 'info' },
    { key: 'category', label: '标签分类', value: tagCategoryOptions.value.length, tone: 'warning' },
  ]
})
const authorizationRows = computed(() => listOf(resourceAuthorizations.value))
const authorizationSummaryCards = computed(() => {
  const activeCount = authorizationRows.value.filter(item => item.is_active !== false).length
  const manageCount = authorizationRows.value.filter(item => item.permission === 'manage').length
  const scopedBusinessCount = new Set(authorizationRows.value.map(item => item.business_line).filter(Boolean)).size
  return [
    { key: 'total', label: '授权策略', value: authorizationRows.value.length, tone: '' },
    { key: 'active', label: '启用策略', value: activeCount, tone: 'success' },
    { key: 'manage', label: '管理授权', value: manageCount, tone: 'warning' },
    { key: 'business', label: '覆盖业务线', value: scopedBusinessCount, tone: 'info' },
  ]
})
const auditActionOptions = computed(() => Array.from(new Set([
  ...auditLogs.value.map(item => item.action),
  ...(auditSummary.value.action_counts || []).map(item => item.action),
].filter(Boolean))).sort())
const auditOperatorOptions = computed(() => Array.from(new Set([
  ...auditLogs.value.map(item => item.operator),
  ...(auditSummary.value.operator_counts || []).map(item => item.operator),
].filter(Boolean))).sort())
const auditSourceOptions = computed(() => Array.from(new Set([
  ...auditLogs.value.map(item => item.source),
  ...(auditSummary.value.source_counts || []).map(item => item.source),
].filter(Boolean))).sort())
const auditSummaryCards = computed(() => {
  const actions = auditSummary.value.action_counts || []
  const total = auditSummary.value.total || auditLogs.value.length
  const writeCount = actions
    .filter(item => isAuditResourceAction(item.action))
    .reduce((sum, item) => sum + Number(item.count || 0), 0)
  const governanceCount = actions
    .filter(item => isAuditGovernanceAction(item.action))
    .reduce((sum, item) => sum + Number(item.count || 0), 0)
  const platformCount = actions
    .filter(item => isAuditPlatformAction(item.action))
    .reduce((sum, item) => sum + Number(item.count || 0), 0)
  return [
    { key: 'total', label: '审计记录', value: total, tone: '' },
    { key: 'write', label: '资源变更', value: writeCount, tone: 'success' },
    { key: 'governance', label: '治理动作', value: governanceCount, tone: 'warning' },
    { key: 'platform', label: '平台配置', value: platformCount, tone: 'info' },
  ]
})
const auditDetailFields = computed(() => {
  const row = auditDetailRow.value || {}
  if (Array.isArray(row.diff_fields) && row.diff_fields.length) return row.diff_fields
  return Object.entries(row.diff || {}).map(([field, value]) => ({
    field,
    label: field,
    before: value?.before,
    after: value?.after,
    before_text: formatAuditValue(value?.before),
    after_text: formatAuditValue(value?.after),
  }))
})
const auditDetailTitle = computed(() => {
  const row = auditDetailRow.value || {}
  return row.ci_name || row.after?.name || row.before?.name || `CI#${row.ci || '-'}`
})
const repositoryGroups = computed(() => listOf(repositorySummary.value.groups || []))
const repositoryTreeNodes = computed(() => listOf(repositoryModelTree.value.tree || []))
const repositoryTopModels = computed(() => listOf(repositorySummary.value.top_models || []))
const repositoryGroupTabs = computed(() => [
  { key: 'all', label: '全部' },
  ...repositoryGroups.value.map(group => ({
    key: String(group.id ?? group.code ?? group.name),
    label: group.name,
  })),
])
const filteredRepositoryGroups = computed(() => {
  if (activeRepositoryGroupKey.value === 'all') return repositoryGroups.value
  return repositoryGroups.value.filter(group => String(group.id ?? group.code ?? group.name) === activeRepositoryGroupKey.value)
})
const repositorySyncFailureCount = computed(() => repositoryGroups.value.reduce(
  (sum, group) => sum + (group.models || []).reduce((inner, model) => inner + Number(model.sync_failure_count || 0), 0),
  0,
))
const repositoryCards = computed(() => {
  const summary = repositorySummary.value.summary || {}
  const visibleModelCount = repositoryGroups.value.reduce((sum, group) => sum + (group.models || []).length, 0)
  return [
    { key: 'models', label: '资源模型', value: visibleModelCount, tone: '' },
    { key: 'items', label: '资源实例', value: summary.resource_count || 0, tone: 'success' },
    { key: 'risks', label: '治理风险', value: summary.risk_count || 0, tone: 'warning' },
    { key: 'sync', label: '同步失败', value: repositorySyncFailureCount.value, tone: 'danger' },
  ]
})
function resourceNodeEnvironmentValues(businessLine = '') {
  const node = resourceNodeTree.value.find(item => ledgerTreeText(item.name) === ledgerTreeText(businessLine))
  const seen = new Set()
  return (node?.children || [])
    .map(item => normalizeEnvironmentValue(item.name))
    .filter((value) => {
      if (!value || seen.has(value)) return false
      seen.add(value)
      return true
    })
}
const ciBusinessNodeOptions = computed(() => resourceNodeTree.value)
const ciEnvironmentNodeOptions = computed(() => {
  const node = resourceNodeTree.value.find(item => String(item.id) === String(ciForm.business_node))
  return node?.children || []
})
const environmentOptions = computed(() => {
  const seen = new Set()
  return resourceNodeTree.value
    .flatMap(item => resourceNodeEnvironmentValues(item.name))
    .filter((value) => {
      if (!value || seen.has(value)) return false
      seen.add(value)
      return true
    })
})
const requestEnvironmentOptions = computed(() => {
  const node = resourceNodeTree.value.find(item => item.name === requestForm.business_line)
  return (node?.children || []).map(item => item.name)
})
const completionEnvironmentOptions = computed(() => {
  const node = resourceNodeTree.value.find(item => item.name === completionForm.business_line)
  return (node?.children || []).map(item => item.name)
})
const ciSourcePairs = computed(() => {
  const pairs = new Map()
  const addPair = (account, region) => {
    const normalizedAccount = String(account || '').trim()
    const normalizedRegion = String(region || '').trim()
    if (!normalizedAccount) return
    pairs.set(`${normalizedAccount}\u0000${normalizedRegion}`, { account: normalizedAccount, region: normalizedRegion })
  }

  ciSourceAccountRegionOptions.value.forEach(item => addPair(item.source_account, item.source_region))
  sourceMappingRows.value.forEach(item => addPair(item.source_account, item.source_region))
  const cloudNodes = cloudResourceNodeRows.value
  cloudNodes
    .filter(item => item.node_type === 'cloud_account' && !item.parent_id)
    .forEach((accountNode) => {
      addPair(accountNode.name, '')
      cloudNodes
        .filter(item => item.node_type === 'cloud_region' && String(item.parent_id) === String(accountNode.id))
        .forEach(regionNode => addPair(accountNode.name, regionNode.name))
    })
  ledgerItems.value.forEach(item => {
    const mappings = sourceMappingsOf(item)
    if (mappings.length) {
      mappings.forEach(mapping => addPair(mapping.source_account, mapping.source_region))
      return
    }
    const attributes = item.attributes || {}
    addPair(
      item.source_account || attributes.source_account || attributes.cloud_account || attributes.account || attributes.account_id || attributes.account_name,
      item.source_region || attributes.source_region || attributes.cloud_region || attributes.region || attributes.region_id,
    )
  })
  return Array.from(pairs.values())
})
const ciSourceAccountOptions = computed(() => Array.from(new Set(
  ciSourcePairs.value.map(item => item.account),
)).sort())
const ciSourceRegionOptions = computed(() => Array.from(new Set(
  ciSourcePairs.value
    .filter(item => item.account === ciForm.source_account)
    .map(item => item.region)
    .filter(Boolean),
)).sort())
const bulkLedgerBusinessNodeOptions = computed(() => resourceNodeTree.value)
const bulkLedgerEnvironmentNodeOptions = computed(() => {
  const businessNode = resourceNodeTree.value.find(item => String(item.id) === String(bulkLedgerForm.business_node))
  return businessNode?.children || []
})
const completionMissingFields = computed(() => completionIssueRow.value?.missing_fields || [])
const topologyNodes = computed(() => listOf(topology.value.nodes || []))
const topologyEdges = computed(() => listOf(topology.value.edges || []))
const topologyMeta = computed(() => topology.value.meta || {})
const topologySummaryCards = computed(() => [
  { key: 'nodes', label: '节点数', value: topologyMeta.value.node_count || topologyNodes.value.length, tone: '' },
  { key: 'edges', label: '关系数', value: topologyMeta.value.edge_count || topologyEdges.value.length, tone: 'warning' },
  { key: 'matched', label: '命中节点', value: (topologyMeta.value.matched_node_ids || []).length, tone: 'success' },
  { key: 'scope', label: '拓扑范围', value: topologyMeta.value.scope === 'exact' ? '精确' : '邻居', tone: 'info' },
])
const topologyNodeMap = computed(() => new Map(topologyNodes.value.map(node => [String(node.id), node])))
const topologyGraphGroupDefs = [
  { key: 'business', label: '业务', color: '#3b82f6', keywords: ['应用', '服务', '系统', 'APP_SERVICE'] },
  { key: 'compute', label: '计算', color: '#0ea5e9', keywords: ['云主机', 'ECS', '虚拟机', 'VM', 'K8S', 'Kubernetes', '容器', '计算'] },
  { key: 'database', label: '数据库', color: '#f97316', keywords: ['MySQL', 'PostgreSQL', 'MongoDB', '数据库', 'RDS', 'DB'] },
  { key: 'middleware', label: '中间件', color: '#8b5cf6', keywords: ['Redis', 'Kafka', 'RocketMQ', 'RabbitMQ', 'EMQX', 'Elasticsearch', 'Nacos', 'ZooKeeper', '缓存', '消息', '搜索', '中间件'] },
  { key: 'storage', label: '存储', color: '#14b8a6', keywords: ['对象存储', '块存储', '文件存储', 'OSS', 'NFS', '存储'] },
  { key: 'bigdata', label: '大数据', color: '#eab308', keywords: ['Hadoop', 'Flink', 'ClickHouse', 'Hologres', 'MaxCompute', 'DataWorks', '大数据'] },
  { key: 'network', label: '网络入口', color: '#10b981', keywords: ['负载均衡', 'Nginx', '域名', '证书', '网关', '网络', 'SLB', 'CLB'] },
  { key: 'external', label: '其他资产', color: '#64748b', keywords: ['第三方', 'SaaS', 'API', '服务商', '资产物品', '办公物品'] },
]
const topologyGraphFallbackGroup = { key: 'other', label: '其他', color: '#64748b', keywords: [] }
function topologyNodeGroupDef(node = {}) {
  const identity = `${node.type || ''} ${node.name || ''} ${node.icon || ''}`.toLowerCase()
  return topologyGraphGroupDefs.find(group => group.keywords.some(keyword => identity.includes(String(keyword).toLowerCase()))) || topologyGraphFallbackGroup
}
const topologyGraphColumns = computed(() => {
  const buckets = topologyGraphGroupDefs.map(group => ({ ...group, nodes: [] }))
  const fallback = { ...topologyGraphFallbackGroup, nodes: [] }
  topologyNodes.value.forEach((node) => {
    const group = topologyNodeGroupDef(node)
    const bucket = buckets.find(item => item.key === group.key)
    ;(bucket || fallback).nodes.push(node)
  })
  return [...buckets, fallback].filter(column => column.nodes.length || column.key !== 'other')
})
const topologyGraphLanes = computed(() => {
  const laneWidth = 220
  const laneGap = 44
  const boardPadding = 28
  const nodeWidth = 176
  const nodeHeight = 58
  const nodeGap = 18
  const laneTop = 24
  const nodeTop = 72
  return topologyGraphColumns.value.map((column, index) => {
    const x = boardPadding + index * (laneWidth + laneGap)
    const laneHeight = Math.max(380, nodeTop + column.nodes.length * (nodeHeight + nodeGap) + 18)
    const nodes = column.nodes.map((node, nodeIndex) => ({
      ...node,
      groupKey: column.key,
      groupLabel: column.label,
      groupColor: column.color,
      boardX: x + Math.round((laneWidth - nodeWidth) / 2),
      boardY: laneTop + nodeTop + nodeIndex * (nodeHeight + nodeGap),
      boardWidth: nodeWidth,
      boardHeight: nodeHeight,
    }))
    return {
      ...column,
      x,
      y: laneTop,
      width: laneWidth,
      height: laneHeight,
      nodes,
    }
  })
})
const topologyGraphBoard = computed(() => ({
  width: Math.max(820, (topologyGraphLanes.value.length || 1) * 264 + 56),
  height: Math.max(460, ...topologyGraphLanes.value.map(lane => lane.y + lane.height + 28)),
}))
const topologyGraphNodeById = computed(() => new Map(
  topologyGraphLanes.value.flatMap(lane => lane.nodes).map(node => [String(node.id), node]),
))
const topologyGraphEdgePaths = computed(() => topologyEdges.value.map((edge) => {
  const source = topologyGraphNodeById.value.get(String(edge.source))
  const target = topologyGraphNodeById.value.get(String(edge.target))
  if (!source || !target) return null
  const sx = source.boardX + source.boardWidth
  const sy = source.boardY + Math.round(source.boardHeight / 2)
  const tx = target.boardX
  const ty = target.boardY + Math.round(target.boardHeight / 2)
  const reverse = tx < sx
  const control = Math.max(72, Math.abs(tx - sx) * 0.42)
  const c1x = sx + (reverse ? -control : control)
  const c2x = tx - (reverse ? -control : control)
  const type = String(edge.type || 'relation').replace(/[^a-zA-Z0-9_-]/g, '_')
  return {
    ...edge,
    type,
    path: `M ${sx} ${sy} C ${c1x} ${sy}, ${c2x} ${ty}, ${tx} ${ty}`,
  }
}).filter(Boolean))
const topologyRelationLegend = computed(() => {
  const rows = new Map()
  topologyEdgeRows.value.forEach((edge) => {
    const type = edge.type || 'relation'
    const current = rows.get(type) || { type, label: edge.label || relationTypeLabel(type), count: 0 }
    current.count += 1
    rows.set(type, current)
  })
  return Array.from(rows.values()).slice(0, 5)
})
const topologyGraphSourceText = computed(() => {
  const parts = [
    topologyFilters.business_line || '全部业务',
    topologyFilters.environment ? environmentText(topologyFilters.environment) : '全部环境',
    topologyFilters.ci_type ? modelName(topologyFilters.ci_type) : '全部资产分类',
  ]
  return `当前范围：${parts.join(' / ')}`
})
const topologyEdgeRows = computed(() => topologyEdges.value.map((edge) => {
  const source = topologyNodeMap.value.get(String(edge.source))
  const target = topologyNodeMap.value.get(String(edge.target))
  return {
    ...edge,
    sourceName: edge.source_name || source?.name || `CI#${edge.source}`,
    targetName: edge.target_name || target?.name || `CI#${edge.target}`,
    label: edge.label || relationTypeLabel(edge.type),
  }
}))
const ciDetailCostRows = computed(() => ciDetailCostHistory.value
  .filter(item => item.month === ciDetailCostMonth.value)
  .sort((left, right) => String(left.provider || '').localeCompare(String(right.provider || ''))))
const ciDetailCostAmount = computed(() => {
  if (ciDetailCostRows.value.length) {
    return ciDetailCostRows.value.reduce((total, item) => total + Number(item.amount || 0), 0)
  }
  if (ciDetailCostMonth.value === currentMonth()) return Number(ciDetail.value?.attributes?.monthly_cost || 0)
  return 0
})
const ciDetailCostIsProjected = computed(() => (
  ciDetailCostMonth.value === currentMonth() && Boolean(ciDetail.value?.attributes?.cost_is_projected)
))
const ciDetailPaygCurrentAmount = computed(() => {
  if (ciDetailCostMonth.value !== currentMonth()) return null
  const value = ciDetail.value?.attributes?.cost_actual_amount
  return value === undefined || value === null || value === '' ? null : Number(value)
})
const ciDetailCostMode = computed(() => {
  const providers = new Set(ciDetailCostRows.value.map(item => item.provider))
  const attributes = ciDetail.value?.attributes || {}
  const hasPayg = ciDetailPaygCurrentAmount.value !== null || providers.has('aliyun')
  const hasSubscription = Number(attributes.cost_subscription_amortized_amount || 0) > 0 || providers.has('aliyun_subscription')
  if (hasPayg && hasSubscription) return { label: '阿里云混合付费', tagType: 'warning' }
  if (hasPayg) return { label: '阿里云按量付费', tagType: 'success' }
  if (hasSubscription) return { label: '阿里云包年包月', tagType: 'primary' }
  if (providers.has('manual') || Number(attributes.monthly_cost || 0) > 0) return { label: '手工维护', tagType: 'info' }
  return { label: '未维护成本', tagType: 'info' }
})
const ciDetailCostMetricLabel = computed(() => {
  if (ciDetailCostMonth.value !== currentMonth()) return `${ciDetailCostMonth.value} 月成本`
  if (ciDetailCostMode.value.label === '阿里云包年包月') return '本月均摊'
  return '本月预计'
})
const ciDetailBaseCostText = computed(() => {
  const amount = formatMoney(ciDetailCostAmount.value)
  return ciDetailCostMode.value.label.includes('按量付费') ? `预估 ${amount}` : amount
})
const requestRows = computed(() => resourceRequests.value)
const requestProviderOptions = computed(() => requestProvisioningOptions.value.providers || [])
const requestResourceTypeFallback = [
  ['ecs', '云服务器 ECS', 'cloud'], ['rds', '云数据库 RDS', 'manual'], ['redis', '云数据库 Redis', 'manual'], ['mongodb', '云数据库 MongoDB', 'manual'],
  ['kafka', '消息队列 Kafka', 'manual'], ['rocketmq', '消息队列 RocketMQ', 'manual'], ['oss', '对象存储 OSS', 'manual'], ['slb', '负载均衡 SLB', 'manual'],
  ['ack', '容器服务 ACK', 'manual'], ['disk', '云盘', 'manual'], ['nas', '文件存储 NAS', 'manual'], ['clickhouse', '云数据库 ClickHouse', 'manual'],
  ['hologres', '实时数仓 Hologres', 'manual'], ['maxcompute', '大数据计算 MaxCompute', 'manual'], ['dataworks', '数据开发 DataWorks', 'manual'],
  ['nat_gateway', 'NAT 网关', 'manual'], ['eip', '弹性公网 IP', 'manual'], ['elasticsearch', '云搜索 Elasticsearch', 'manual'],
].map(([value, label, delivery]) => ({ value, label, delivery }))
const requestResourceTypeOptions = computed(() => {
  const items = requestProvisioningOptions.value.resource_types || []
  return items.length ? items : requestResourceTypeFallback
})
const requestSelectedTypeMeta = computed(() => requestResourceTypeOptions.value.find(item => item.value === requestForm.resource_type) || requestResourceTypeOptions.value[0] || null)
function requestResourceTypeLabel(value) {
  if (value === '主机' || value === 'host') return '云服务器 ECS'
  return requestResourceTypeOptions.value.find(item => item.value === value)?.label || value || '未指定类型'
}
const requestCredentialOptions = computed(() => (requestProvisioningOptions.value.credentials || [])
  .filter(item => item.provider === requestForm.specs.provider))
const requestSelectedCredential = computed(() => requestCredentialOptions.value
  .find(item => String(item.id) === String(requestForm.specs.cloud_credential_id)))
const requestIsCloudDelivery = computed(() => requestForm.specs.provisioning_mode === 'cloud')
const requestIsAliyun = computed(() => requestForm.specs.provider === 'aliyun')
const requestIsEcsType = computed(() => ['ecs', '主机'].includes(String(requestForm.resource_type || '').toLowerCase()))
const requestIsHuawei = computed(() => requestIsCloudDelivery.value && requestForm.specs.provider === 'huawei')
const requestIsVsphere = computed(() => requestIsCloudDelivery.value && requestForm.specs.provider === 'vsphere')
const requestSummaryCards = computed(() => {
  const counts = resourceRequests.value.reduce((acc, item) => {
    acc[item.status] = (acc[item.status] || 0) + 1
    return acc
  }, {})
  return [
    { key: 'all', label: '申请总数', value: resourceRequests.value.length, tone: '' },
    { key: 'pending', label: '待审批', value: counts.pending || 0, tone: 'warning' },
    { key: 'approved', label: '待执行', value: counts.approved || 0, tone: 'success' },
    { key: 'failed', label: '交付失败', value: counts.failed || 0, tone: 'danger' },
    { key: 'completed', label: '已交付', value: counts.completed || 0, tone: 'info' },
  ]
})

function applyRequestSummaryFilter(key) {
  requestFilters.status = key === 'all' ? '' : key
  fetchRequests()
}

function requestDeliveredItems(row) {
  if (Array.isArray(row?.delivered_items) && row.delivered_items.length) return row.delivered_items
  return row?.delivered_ci ? [row.delivered_ci] : []
}

function requestSpecEntries(row) {
  const specs = row?.specs && typeof row.specs === 'object' ? row.specs : {}
  const labelMap = {
    provider: '云平台',
    region: '地域 / 站点',
    zone: '可用区',
    instance_name_prefix: '实例命名',
    hostname: '主机名',
    ip_address: 'IP 地址',
    os_type: '操作系统',
    admin_user: '负责人',
    instance_type: '实例规格',
    cpu: 'CPU',
    memory_gb: '内存 GB',
    disk_gb: '磁盘 GB',
    image_id: '镜像 ID',
    security_group_id: '安全组 ID',
    vswitch_id: '交换机 ID',
    flavor_ref: '华为云规格',
    vpc_id: 'VPC ID',
    subnet_id: '子网 ID',
    template_name: 'vSphere 模板',
    datastore_name: '数据存储',
    cluster_name: '计算集群',
    resource_name: '资产名称',
    resource_id: '资源 ID',
    instance_class: '规格 / 版本',
    capacity: '容量 / 节点',
    extra_requirements: '补充参数',
  }
  const entries = []
  Object.entries(labelMap).forEach(([key, label]) => {
    const value = specs[key]
    if (value !== undefined && value !== null && value !== '') {
      entries.push({ key, label, value: key === 'provider' ? (row.provider_label || formatValue(value)) : formatValue(value) })
    }
  })
  const hosts = Array.isArray(specs.hosts) ? specs.hosts : Array.isArray(specs.items) ? specs.items : []
  hosts.forEach((host, index) => {
    if (!host || typeof host !== 'object') return
    const name = host.hostname || host.name || `第 ${index + 1} 台`
    const ip = host.ip_address || host.private_ip || host.ip || '-'
    const type = host.instance_type || host.specification || row?.specification || '-'
    entries.push({
      key: `host-${index}`,
      label: `主机 ${index + 1}`,
      value: `${name} / ${ip} / ${type}`,
    })
  })
  if (!entries.length && row?.specification) {
    entries.push({ key: 'specification', label: '规格说明', value: row.specification })
  }
  return entries
}
const requestDetailDeliveredItems = computed(() => requestDeliveredItems(requestDetailRow.value))
const requestDetailSpecEntries = computed(() => requestSpecEntries(requestDetailRow.value))
const requestActionIsHost = computed(() => ['主机', 'host', 'ecs'].includes(String(requestActionRow.value?.resource_type || '').toLowerCase()))
const requestActionTitle = computed(() => {
  if (requestActionType.value === 'approve') return '批准资源申请'
  if (requestActionType.value === 'reject') return '驳回资源申请'
  if (requestActionType.value === 'complete') return '完成资源交付'
  if (requestActionType.value === 'provision') return requestActionRow.value?.status === 'failed' ? '重试云平台交付' : '执行云平台交付'
  return '处理资源申请'
})
const requestActionPlaceholder = computed(() => {
  if (requestActionType.value === 'approve') return '填写审批意见，例如容量已确认。'
  if (requestActionType.value === 'reject') return '填写驳回原因，便于申请人调整后重提。'
  if (requestActionType.value === 'complete') return '填写交付说明，例如主机已创建并同步至台账。'
  if (requestActionType.value === 'provision') return '填写本次交付备注（选填），确认后将调用云平台创建机器。'
  return '填写处理说明'
})

const syncSourceOptions = computed(() => Array.from(new Set([
  ...syncJobs.value.map(item => item.source_type),
  ...sourceMappings.value.map(item => item.source_type),
].filter(Boolean))).sort())
const syncJobConnector = computed(() => {
  const formConnector = String(syncJobForm.connector || '').toLowerCase()
  if (formConnector) return formConnector
  const sourceType = String(syncJobForm.source_type || '').toLowerCase()
  if (sourceType.includes('vsphere')) return 'vsphere'
  if (sourceType.startsWith('aliyun_')) return 'aliyun'
  if (sourceType.startsWith('huaweicloud_')) return 'huaweicloud'
  return ''
})
const isCloudSyncJob = computed(() => ['aliyun', 'huaweicloud', 'vsphere'].includes(syncJobConnector.value))
const isVsphereSyncJob = computed(() => syncJobConnector.value === 'vsphere')
const isMinimalSyncJobForm = computed(() => Boolean(syncJobEditingId.value) || (isCloudSyncJob.value && !!syncJobForm.templateKey && !!syncJobForm.cloud_account_id))
const syncCloudProvider = computed(() => syncJobConnector.value === 'huaweicloud' ? 'huawei' : syncJobConnector.value)
const syncJobTargetTypeOptions = computed(() => ciTypes.value
  .map(item => ({
    value: String(item.code || item.ci_type_code || '').trim(),
    label: item.name || item.code || item.ci_type_code || '',
  }))
  .filter(item => item.value))
const syncCloudCredentialOptions = computed(() => cloudCredentials.value.filter((item) => {
  if (!item?.id) return false
  if (item.is_enabled === false) return false
  return !syncCloudProvider.value || item.provider === syncCloudProvider.value
}))
const cloudCredentialPlaceholder = computed(() => {
  if (cloudCredentialLoading.value) return '正在加载资源账号'
  if (!cloudCredentialLoaded.value) return '选择资源账号'
  if (!syncCloudCredentialOptions.value.length) return '暂无可用账号，请先在资产采集中心添加'
  return '选择资源账号'
})
const syncJointCards = computed(() => {
  const sourceTypes = new Set(syncJobs.value.map(item => item.source_type).filter(Boolean))
  const makeCard = ({ key, title, desc, types, hint }) => {
    const count = types.filter(type => sourceTypes.has(type)).length
    return {
      key,
      title,
      desc,
      sourceTypes: types,
      hint,
      count,
      total: types.length,
      ready: count >= types.length,
    }
  }
  return [
    makeCard({
      key: 'vsphere',
      title: 'vSphere 虚拟机',
      desc: '填写 host/username，预览或执行时输入一次性 vCenter 密码。',
      types: ['vsphere_vm'],
      hint: '打开 vSphere 虚拟机自动注册模板，先点预览并输入本次 vCenter 密码；也可设置 SXDEVOPS_VSPHERE_PROD_PASSWORD 供定时采集使用。',
    }),
    makeCard({
      key: 'aliyun-ecs',
      title: '阿里云 ECS',
      desc: '引用多云账号 cloud_account_id，把 ECS 注册到云主机模型。',
      types: ['aliyun_ecs'],
      hint: '确认多云账号里有阿里云制度账号，再编辑阿里云 ECS 模板填入 cloud_account_id 后预览。',
    }),
    makeCard({
      key: 'aliyun-middleware',
      title: '阿里云 DB/中间件',
      desc: 'RDS、ACK、Redis、MongoDB、Kafka、RocketMQ、OSS、云盘、NFS、大数据、网络入口与 ES 统一纳管。',
      types: aliyunManagedSourceTypes,
      hint: '逐个预览阿里云资源模板，确认账号、地域、实例 ID 和目标模型字段映射都正常。',
    }),
    makeCard({
      key: 'huaweicloud',
      title: '华为云',
      desc: 'ECS、RDS、Redis、EIP、OBS 通过 cloud_account_id 自动注册。',
      types: ['huaweicloud_ecs', 'huaweicloud_rds', 'huaweicloud_redis', 'huaweicloud_eip', 'huaweicloud_obs'],
      hint: '编辑华为云 ECS/RDS/Redis/EIP/OBS 模板填入 cloud_account_id，先预览再执行。',
    }),
    makeCard({
      key: 'third-party',
      title: '第三方服务',
      desc: '手工登记和风天气、高德地图等服务基本信息。',
      types: ['third_party_import'],
      hint: '打开第三方服务台账导入模板，只登记账号、负责人和服务到期信息，不保存 API Key 明文。',
    }),
  ]
})
const sourceMappingRows = computed(() => listOf(sourceMappings.value))
const sourceMappingSourceOptions = computed(() => Array.from(new Set(sourceMappingRows.value.map(item => item.source_type).filter(Boolean))).sort())
const sourceMappingCiOptions = computed(() => {
  const rows = new Map()
  ledgerItems.value.forEach(item => rows.set(item.id, {
    id: item.id,
    name: item.name,
    ci_type_name: item.ci_type_name || modelName(item.ci_type),
  }))
  sourceMappingRows.value.forEach(item => {
    if (!item.ci || rows.has(item.ci)) return
    rows.set(item.ci, {
      id: item.ci,
      name: item.ci_name || `#${item.ci}`,
      ci_type_name: item.ci_type_name || '',
    })
  })
  return Array.from(rows.values())
})
const syncResolveCiOptions = computed(() => {
  const keyword = String(syncResolveRecord.value?.after?.name || syncResolveRecord.value?.ci_name || '').toLowerCase()
  return [...sourceMappingCiOptions.value].sort((left, right) => {
    const leftName = String(left.name || '').toLowerCase()
    const rightName = String(right.name || '').toLowerCase()
    const leftScore = keyword && leftName === keyword ? 0 : keyword && leftName.includes(keyword) ? 1 : 2
    const rightScore = keyword && rightName === keyword ? 0 : keyword && rightName.includes(keyword) ? 1 : 2
    return leftScore - rightScore || String(left.name || '').localeCompare(String(right.name || ''))
  })
})
const sourceMappingSummaryCards = computed(() => {
  const rows = sourceMappingRows.value
  const failedCount = rows.filter(item => ['failed', 'conflict'].includes(item.sync_status)).length
  return [
    { key: 'total', label: '映射总数', value: rows.length, tone: '' },
    { key: 'sources', label: '来源类型', value: sourceMappingSourceOptions.value.length, tone: 'info' },
    { key: 'success', label: '同步成功', value: rows.filter(item => item.sync_status === 'success').length, tone: 'success' },
    { key: 'risk', label: '异常映射', value: failedCount + rows.filter(item => item.sync_status === 'missing').length, tone: failedCount ? 'danger' : 'warning' },
  ]
})
const collectionJobs = computed(() => listOf(collectionSummary.value.jobs || []))
const collectionSources = computed(() => listOf(collectionSummary.value.sources || []))
const collectionSummaryCards = computed(() => {
  const summary = collectionSummary.value.summary || {}
  return [
    { key: 'sources', label: '采集源', value: summary.source_count || collectionSources.value.length, tone: '' },
    { key: 'enabled', label: '已启用自动同步', value: summary.enabled_count || 0, tone: 'success' },
    { key: 'due', label: '待执行', value: summary.due_count || 0, tone: 'warning' },
    { key: 'unhealthy', label: '异常任务', value: summary.unhealthy_count || 0, tone: summary.unhealthy_count ? 'danger' : 'success' },
    { key: 'failed', label: '失败记录', value: summary.failed_count || 0, tone: 'danger' },
  ]
})
function syncJobAccountId(row) {
  const config = row?.config || {}
  return String(config.cloud_account_id || config.multicloud_account_id || '').trim()
}
function syncJobAccountLabel(row) {
  const config = row?.config || {}
  return String(config.source_account || config.account_name || config.account || '').trim()
}
function defaultProductKeysForProvider(provider) {
  return (cloudProductOptionsByProvider[provider] || []).map(item => item.key)
}
function normalizeCredentialProductKeys(provider, keys) {
  const allowed = new Set(defaultProductKeysForProvider(provider))
  return Array.from(new Set((Array.isArray(keys) ? keys : [])
    .map(item => cloudProductKeyAliases[String(item || '').trim()] || String(item || '').trim())
    .filter(key => allowed.has(key))))
}
function credentialProductKeys(credential) {
  const provider = String(credential?.provider || '').toLowerCase()
  const tags = credential?.tags && typeof credential.tags === 'object' ? credential.tags : null
  const hasExplicitSelection = !!tags && Object.prototype.hasOwnProperty.call(tags, 'sync_product_keys') && Array.isArray(tags.sync_product_keys)
  const selected = normalizeCredentialProductKeys(provider, tags?.sync_product_keys)
  if (hasExplicitSelection) return selected
  if (!selected.length) return defaultProductKeysForProvider(provider)
  return normalizeCredentialProductKeys(provider, [
    ...selected,
    ...(cloudProductBackfillKeysByProvider[provider] || []),
  ])
}
function productLabelByKey(provider, key) {
  return (cloudProductOptionsByProvider[provider] || []).find(item => item.key === key)?.label || key
}
function credentialProductLabels(credential) {
  const provider = String(credential?.provider || '').toLowerCase()
  return credentialProductKeys(credential).map(key => productLabelByKey(provider, key))
}
function syncAccountProductPreview(labels) {
  return (Array.isArray(labels) ? labels : []).slice(0, 9)
}
function credentialPrivateCloudVersionLabel(credential) {
  const value = String(credential?.tags?.private_cloud_version || defaultPrivateCloudVersion)
  return privateCloudVersionOptions.find(item => item.value === value)?.label || value || 'ESXi 8.0.2'
}

function ciTypeNameByCode(code) {
  const value = String(code || '').toUpperCase()
  return ciTypes.value.find(item => String(item.code || '').toUpperCase() === value)?.name || value || '-'
}

function syncTaskStatus(job) {
  if (!job) return { key: 'pending', text: '未执行', tag: 'info' }
  if (job.config?.collection_enabled === false) return { key: 'disabled', text: '已停用', tag: 'info' }
  if (job.status === 'running') return { key: 'running', text: '运行中', tag: 'warning' }
  if (job.status === 'failed') return { key: 'failed', text: '失败', tag: 'danger' }
  if (job.status === 'partial') return { key: 'partial', text: '部分成功', tag: 'warning' }
  if (job.status === 'success') return { key: 'success', text: '成功', tag: 'success' }
  return { key: 'pending', text: '待执行', tag: 'info' }
}

function syncTaskScheduleText(template, job = null) {
  const config = job?.config || template?.config || {}
  return config.schedule_label || job?.schedule_text || config.schedule || '按任务配置'
}

function syncTaskAutoSyncText(template, job = null) {
  const config = job?.config || template?.config || {}
  return config.collection_enabled === false ? '未开启自动同步' : '已启用自动同步'
}

function normalizeCloudSyncFailureReason(message = '') {
  const raw = String(message || '').trim()
  const lower = raw.toLowerCase()
  if (!raw) return ''
  const validationMessages = Array.from(raw.matchAll(/ErrorDetail\(string=['"](.+?)['"],\s*code=['"].+?['"]\)/g)).map(match => match[1]).filter(Boolean)
  if (validationMessages.length) {
    return `配置项字段校验失败：${Array.from(new Set(validationMessages)).join('；')}`
  }
  if (lower.includes('apigw.0301') || lower.includes('incorrect iam authentication information') || lower.includes('get token error')) {
    return `华为云账号认证信息不匹配，请核对当前地域的 Project ID、AK/SK 以及 IAM 用户项目授权。原始错误：${raw}`
  }
  return raw
}

function syncFailureMessage(message = '') {
  return normalizeCloudSyncFailureReason(message)
}

function syncRecordSubjectTitle(row = {}) {
  return row.ci_name || row.source_unique_id || `记录 #${row.id || '-'}`
}

function syncRecordSubjectMeta(row = {}) {
  const parts = []
  if (row.ci_name && row.source_unique_id) parts.push(`来源 ID：${row.source_unique_id}`)
  if (row.job_source_type) parts.push(row.job_source_type)
  return parts.join(' · ')
}

function syncRecordRetrySummary(row = {}) {
  if (row.retry_count) {
    return `${retryStatusText(row.retry_status)} · ${row.retry_count} 次`
  }
  if (row.status === 'failed') return '未处理'
  return retryStatusText(row.retry_status)
}

function syncRecordFallbackMessage(row = {}) {
  if (row.status === 'failed') return '未返回具体失败原因，请打开详情查看上下文。'
  return '-'
}

function syncTaskHasFailure(task) {
  const status = task?.job?.status || ''
  return ['failed', 'partial'].includes(status)
}

function credentialSyncTaskRows(credential) {
  const accountId = String(credential?.id || '').trim()
  return credentialSyncTemplates(credential).map((template) => {
    const job = syncJobs.value.find(row => row.source_type === template.source_type && syncJobAccountId(row) === accountId)
    const status = syncTaskStatus(job)
    const targetCode = job?.config?.target_ci_type_code || template.config?.target_ci_type_code
    const isVsphereInventoryTask = template.key === 'vsphere_vm'
    return {
      key: template.key,
      label: syncSourceTypeLabel(template.source_type, template.label || template.name),
      sourceType: isVsphereInventoryTask ? 'vSphere 资源清单' : syncSourceTypeLabel(template.source_type),
      targetLabel: isVsphereInventoryTask ? '虚拟机 / 物理机' : ciTypeNameByCode(targetCode),
      scheduleText: syncTaskScheduleText(template, job),
      autoSyncText: syncTaskAutoSyncText(template, job),
      autoSyncEnabled: (job?.config?.collection_enabled ?? template.config?.collection_enabled) !== false,
      statusText: status.text,
      statusKey: status.key,
      tagType: status.tag,
      job,
      template,
      credential,
    }
  })
}

function latestSyncTimeForTaskRows(taskRows = [], credential = null) {
  const timestamps = (taskRows || [])
    .map(row => row.job?.finished_at || row.job?.started_at || row.job?.last_run_at || '')
    .filter(Boolean)
    .map(value => new Date(value).getTime())
    .filter(value => Number.isFinite(value))
  const credentialTime = credential?.last_sync_at ? new Date(credential.last_sync_at).getTime() : null
  if (Number.isFinite(credentialTime)) timestamps.push(credentialTime)
  if (!timestamps.length) return ''
  return new Date(Math.max(...timestamps)).toISOString()
}

const syncAccountCards = computed(() => cloudCredentials.value.map((item) => {
  const accountId = String(item.id || '').trim()
  const taskRows = credentialSyncTaskRows(item)
  const createdTaskCount = taskRows.filter(row => row.job).length
  const enabledJobCount = taskRows.filter(row => row.job && row.job.config?.collection_enabled !== false).length
  const enabledTaskCount = taskRows.filter(row => row.autoSyncEnabled).length
  const syncedTaskCount = taskRows.filter(row => row.statusKey === 'success').length
  const disabledTaskCount = taskRows.filter(row => !row.autoSyncEnabled).length
  const unsyncedTaskCount = taskRows.filter(row => row.statusKey === 'pending').length
  const providerLabel = item.provider_label || item.provider || '-'
  const accountLabel = item.account_name || item.account_id || item.name || '-'
  const lastSyncTime = latestSyncTimeForTaskRows(taskRows, item)
  const productLabels = credentialProductLabels(item)
  const productPreviewLabels = syncAccountProductPreview(productLabels)
  return {
    key: accountId || item.name,
    id: accountId,
    title: item.name,
    provider: item.provider,
    providerLabel,
    accountLabel,
    region: item.default_region || '未设置地域',
    owner: item.owner || '未设置负责人',
    enabled: item.is_enabled !== false,
    health: item.last_test_status || 'unknown',
    healthText: item.last_test_message || '未做连通性检查',
    environmentCount: item.environment_count || 0,
    assetCount: item.asset_count || 0,
    jobCount: taskRows.length,
    createdTaskCount,
    enabledJobCount,
    enabledTaskCount,
    syncedTaskCount,
    disabledTaskCount,
    unsyncedTaskCount,
    lastSyncText: lastSyncTime ? formatTime(lastSyncTime) : '未同步',
    productLabels,
    productPreviewLabels,
    productOverflowCount: Math.max(0, productLabels.length - productPreviewLabels.length),
    privateCloudVersion: credentialPrivateCloudVersionLabel(item),
    taskRows,
    credential: item,
  }
}))
const publicCloudAccountCards = computed(() => syncAccountCards.value.filter(item => publicCloudProviderSet.has(item.provider)))
const privateCloudAccountCards = computed(() => syncAccountCards.value.filter(item => privateCloudProviderSet.has(item.provider)))
const syncAccountTaskDrawerItem = computed(() => syncAccountCards.value.find(item => String(item.id) === String(syncAccountTaskDrawerAccountId.value)) || null)
const filteredSyncJobs = computed(() => syncJobs.value.filter((item) => {
  if (obsoleteSyncSourceTypes.has(item.source_type)) return false
  if (syncFilters.source_type && item.source_type !== syncFilters.source_type) return false
  if (syncFocusTypes.value.length && !syncFocusTypes.value.includes(item.source_type)) return false
  if (syncFilters.status && item.status !== syncFilters.status) return false
  if (syncAccountContext.value && syncJobAccountId(item) !== syncAccountContext.value.id) return false
  const keyword = syncFilters.search.trim().toLowerCase()
  if (!keyword) return true
  return [item.name, item.source_type, item.created_by, syncJobAccountLabel(item)].some(value => String(value || '').toLowerCase().includes(keyword))
}))
const filteredCollectionJobs = computed(() => collectionJobs.value.filter((item) => {
  if (obsoleteSyncSourceTypes.has(item.source_type)) return false
  if (syncFilters.source_type && item.source_type !== syncFilters.source_type) return false
  if (syncFocusTypes.value.length && !syncFocusTypes.value.includes(item.source_type)) return false
  if (syncFilters.status && item.status !== syncFilters.status) return false
  if (syncAccountContext.value && syncJobAccountId(item) !== syncAccountContext.value.id) return false
  const keyword = syncFilters.search.trim().toLowerCase()
  if (!keyword) return true
  return [item.name, item.source_type, item.connector, item.target_ci_type_code, syncJobAccountLabel(item)].some(value => String(value || '').toLowerCase().includes(keyword))
}))
const syncPrimaryRows = computed(() => {
  const collectionRows = filteredCollectionJobs.value.map(item => ({
    key: `collection-${item.id || item.name || item.source_type}`,
    raw: item,
    taskKind: 'collection',
    taskKindLabel: '自动采集',
    name: syncSourceTypeLabel(item.source_type, item.name || item.source_type || '-'),
    source_type: syncSourceTypeLabel(item.source_type),
    target: item.target_ci_type_code || item.resource_type || item.connector || '-',
    scheduleText: item.schedule_text || '手动触发',
    enabled: item.enabled,
    status: item.status,
    resultText: `资源 ${item.resource_count || 0} / 样例 ${item.item_count || 0}${item.failed_count ? ` / 失败 ${item.failed_count}` : ''}`,
    lastTime: item.last_run_at || item.updated_at,
    nextText: item.is_due ? '待执行' : `下次 ${formatTime(item.next_run_at)}`,
  }))
  const syncRows = filteredSyncJobs.value.map(item => ({
    key: `sync-${item.id || item.name || item.source_type}`,
    raw: item,
    taskKind: 'sync',
    taskKindLabel: '同步任务',
    name: syncSourceTypeLabel(item.source_type, item.name || item.source_type || '-'),
    source_type: syncSourceTypeLabel(item.source_type),
    target: item.target_ci_type_code || item.resource_type || syncJobAccountLabel(item) || '-',
    scheduleText: item.config?.collection_enabled === false ? '手动触发' : (item.schedule_text || item.config?.schedule || '按任务配置'),
    enabled: item.config?.collection_enabled !== false,
    status: item.status,
    resultText: `新增 ${item.summary?.create || 0} / 更新 ${item.summary?.update || 0} / 失败 ${item.summary?.fail || 0}`,
    lastTime: item.updated_at || item.last_run_at,
    nextText: item.created_by ? `创建人 ${item.created_by}` : '保留手工/对账任务',
  }))
  const seen = new Set()
  return [...collectionRows, ...syncRows].filter((item) => {
    const identity = `${item.taskKind}:${item.raw?.id || item.name}:${item.source_type}`
    if (seen.has(identity)) return false
    seen.add(identity)
    return true
  })
})
const selectedModel = computed(() => ciTypes.value.find(item => String(item.id) === String(selectedModelId.value)) || null)
const selectedModelName = computed(() => selectedModel.value?.name || '全部模型')
const selectedCiFormModel = computed(() => ciTypes.value.find(item => String(item.id) === String(ciForm.ci_type)) || null)
const WEB_ADDRESS_GROUP_CODES = new Set(['middleware', 'bigdata'])
function isWebAddressAssetType(model = {}) {
  const groupCode = String(model.group_code || model.ci_type_group_code || '').toLowerCase()
  const typeCode = String(model.code || model.ci_type_code || '').toUpperCase()
  return WEB_ADDRESS_GROUP_CODES.has(groupCode) || typeCode === 'THIRD_PARTY_SERVICE'
}
const ciDetailTypeMeta = computed(() => {
  const detail = ciDetail.value || {}
  const loadedModel = ciTypes.value.find(item => String(item.id) === String(detail.ci_type))
  return {
    ...(loadedModel || {}),
    code: detail.ci_type_code || loadedModel?.code || '',
    group_code: detail.ci_type_group_code || loadedModel?.group_code || '',
  }
})
const isCiDetailWebAddressAsset = computed(() => isWebAddressAssetType(ciDetailTypeMeta.value))
const ciDetailWebAddress = computed(() => {
  if (!isCiDetailWebAddressAsset.value) return ''
  return normalizeWebAddress(ciDetail.value?.attributes?.access_address || ciDetail.value?.attributes?.ip_address)
})
const completionDialogTitle = computed(() => completionIssueRow.value ? '补全资源信息' : '批量补全资源信息')
const sourceMetadataFieldCodes = new Set(['source_type', 'source_account', 'source_region', 'source_unique_id'])
const baseAttributeFieldCodes = new Set(['department'])
const filteredModelFields = computed(() => {
  const rows = selectedModelId.value
    ? ciFields.value.filter(item => String(item.ci_type) === String(selectedModelId.value))
    : ciFields.value
  return rows
    .filter(item => !sourceMetadataFieldCodes.has(item.code) && !baseAttributeFieldCodes.has(item.code))
    .sort((a, b) => Number(a.sort_order || 0) - Number(b.sort_order || 0) || String(a.name || '').localeCompare(String(b.name || ''), 'zh-Hans-CN'))
})
const filteredRelationRules = computed(() => {
  const rows = selectedModelId.value
    ? modelRelationRules.value.filter(item => String(item.source_type) === String(selectedModelId.value) || String(item.target_type) === String(selectedModelId.value))
    : modelRelationRules.value
  return [...rows].sort((left, right) => Number(right.is_active !== false) - Number(left.is_active !== false))
})
const selectedModelFieldPreview = computed(() => filteredModelFields.value.slice(0, 8))
const selectedModelRelationPreview = computed(() => filteredRelationRules.value.slice(0, 6))
const selectedModelResourceRows = computed(() => modelResourceItems.value)
const ciFormHiddenAttributeCodes = new Set(['department', 'description', ...sourceMetadataFieldCodes])
const ciFormModelFields = computed(() => ciFields.value
  .filter(item => String(item.ci_type) === String(ciForm.ci_type) && item.is_active !== false && !ciFormHiddenAttributeCodes.has(item.code))
  .sort((a, b) => Number(a.sort_order || 0) - Number(b.sort_order || 0) || String(a.name || '').localeCompare(String(b.name || ''), 'zh-Hans-CN')))
const ciFormRequiredFields = computed(() => ciFormModelFields.value.filter(item => item.required))
const ciFormOptionalFieldCount = computed(() => Math.max(ciFormModelFields.value.length - ciFormRequiredFields.value.length, 0))
const hasLedgerWaterlineRows = computed(() => ledgerItems.value.some(isResourceWaterlineTarget))
const hasModelResourceWaterlineRows = computed(() => selectedModelResourceRows.value.some(isResourceWaterlineTarget))
const selectedModelStats = computed(() => {
  const model = selectedModel.value || {}
  return [
    { key: 'fields', label: '字段配置', value: filteredModelFields.value.length },
    { key: 'relations', label: '关系规则', value: filteredRelationRules.value.length },
    { key: 'status', label: '状态', value: model.is_active === false ? '停用' : '启用' },
  ]
})
const syncRecordsTitle = computed(() => {
  const title = syncRecordsJob.value?.name ? `同步记录 - ${syncRecordsJob.value.name}` : '同步记录'
  return syncRecordBatchDetail.value ? `${title} / ${syncRecordBatchDetail.value.label}` : title
})
const syncRuntimeTitle = computed(() => syncRuntimeAction.value === 'dry_run' ? '同步预览运行参数' : '同步执行运行参数')
const syncRuntimeAuthRef = computed(() => syncRuntimeRow.value?.config?.auth_ref || 'SXDEVOPS_VSPHERE_PROD')

const syncPreviewRecords = computed(() => listOf(syncPreview.value.records || []))
const syncRecordAllRows = computed(() => listOf(syncRecords.value))
function syncRecordBatchKey(row = {}) {
  const batchId = String(row.batch_id || '').trim()
  if (batchId) return `batch:${batchId}`
  const createdAt = String(row.created_at || '')
  return `legacy:${row.job || syncRecordsJob.value?.id || 'unknown'}:${createdAt.slice(0, 19) || 'unknown'}`
}

function syncRecordAssetKey(row = {}) {
  const sourceId = String(row.source_unique_id || '').trim()
  if (sourceId && sourceId !== 'collection') return `source:${sourceId}`
  if (row.ci) return `ci:${row.ci}`
  return ''
}

const syncRecordBatchGroups = computed(() => {
  const batches = new Map()
  for (const row of syncRecordAllRows.value) {
    const batchId = String(row.batch_id || '').trim()
    const createdAt = String(row.created_at || '')
    const key = syncRecordBatchKey(row)
    const existing = batches.get(key) || {
      key,
      batchId,
      legacy: !batchId || batchId.startsWith('legacy-'),
      latestAt: createdAt,
      totalCount: 0,
      statusCounts: {},
      assetKeys: new Set(),
    }
    existing.totalCount += 1
    const assetKey = syncRecordAssetKey(row)
    if (assetKey) existing.assetKeys.add(assetKey)
    existing.statusCounts[row.status || 'success'] = Number(existing.statusCounts[row.status || 'success'] || 0) + 1
    if (String(createdAt) > String(existing.latestAt || '')) existing.latestAt = createdAt
    batches.set(key, existing)
  }
  return Array.from(batches.values())
    .sort((left, right) => String(right.latestAt || '').localeCompare(String(left.latestAt || '')))
    .map(({ assetKeys, ...row }, index) => ({
      ...row,
      assetCount: assetKeys.size,
      label: `同步批次 ${index + 1}`,
      status: row.statusCounts.failed ? 'failed' : (row.statusCounts.resolved ? 'resolved' : 'success'),
    }))
})
const syncRecordBatchRows = computed(() => {
  const rows = syncRecordBatchGroups.value
  if (syncRecordStatusFilter.value === 'all') return rows
  return rows.filter(row => Number(row.statusCounts[syncRecordStatusFilter.value] || 0) > 0)
})
const syncRecordBatchDetailRows = computed(() => {
  const key = syncRecordBatchDetail.value?.key
  if (!key) return []
  return syncRecordAllRows.value.filter((row) => {
    return syncRecordBatchKey(row) === key
  })
})
const syncRecordSummaryCards = computed(() => {
  const rows = syncRecordBatchGroups.value
  const countByStatus = (status) => rows.filter(item => Number(item.statusCounts[status] || 0) > 0).length
  return [
    { key: 'all', label: '全部批次', value: rows.length, tone: '' },
    { key: 'failed', label: '失败批次', value: countByStatus('failed'), tone: 'danger' },
    { key: 'resolved', label: '已处理批次', value: countByStatus('resolved'), tone: 'success' },
    { key: 'success', label: '成功批次', value: countByStatus('success'), tone: 'success' },
  ]
})
const syncRecordDetailFields = computed(() => {
  const row = syncRecordDetailRow.value || {}
  const before = row.before && typeof row.before === 'object' && !Array.isArray(row.before) ? row.before : {}
  const after = row.after && typeof row.after === 'object' && !Array.isArray(row.after) ? row.after : {}
  const fields = Array.from(new Set([...Object.keys(before), ...Object.keys(after)]))
  return fields
    .map(field => ({
      field,
      before: before[field],
      after: after[field],
      changed: formatAuditValue(before[field]) !== formatAuditValue(after[field]),
    }))
    .filter(item => item.changed || item.before !== undefined || item.after !== undefined)
})
const syncPreviewCards = computed(() => {
  const summary = syncPreview.value.summary || {}
  return [
    { key: 'create', label: '新增', value: summary.create || 0, tone: 'success' },
    { key: 'update', label: '更新', value: summary.update || 0, tone: 'warning' },
    { key: 'relation', label: '自动关系', value: summary.relation_created || summary.relation_preview || 0, tone: summary.relation_failed ? 'danger' : 'success' },
    { key: 'skip', label: '跳过', value: summary.skip || 0, tone: '' },
    { key: 'conflict', label: '冲突', value: summary.conflict || 0, tone: 'danger' },
    { key: 'fail', label: '失败', value: summary.fail || 0, tone: 'danger' },
  ]
})
const bulkImportPlaceholder = computed(() => {
  if (bulkImportForm.format === 'csv') {
    return 'ci_type_name,ci_type_code,name,source_unique_id,business_line,department,environment,admin_user,private_ip,cpu\n云主机(ECS),CLOUD_SERVER,ecs-prod-01,i-xxx,core,基础架构部,prod,ops,10.0.0.8,4'
  }
  const type = ciTypes.value[0] || {}
  return JSON.stringify([
    {
      ci_type_name: type.name || '云主机(ECS)',
      ci_type_code: type.code || 'CLOUD_SERVER',
      name: 'ecs-prod-01',
      source_type: bulkImportForm.source_type || 'manual_import',
      source_unique_id: 'i-xxx',
      business_line: 'core',
      department: '基础架构部',
      environment: 'prod',
      admin_user: 'ops',
      attributes: {
        private_ip: '10.0.0.8',
        cpu: 4,
      },
    },
  ], null, 2)
})
const bulkImportPreviewCards = computed(() => {
  const summary = bulkImportPreview.value.summary || {}
  return [
    { key: 'create', label: '新增', value: summary.create || 0, tone: 'success' },
    { key: 'update', label: '更新', value: summary.update || 0, tone: 'warning' },
    { key: 'skip', label: '跳过', value: summary.skip || 0, tone: '' },
    { key: 'conflict', label: '冲突', value: summary.conflict || 0, tone: 'danger' },
    { key: 'fail', label: '失败', value: summary.fail || 0, tone: 'danger' },
  ]
})
const hasCurrentBulkImportPreview = computed(() => bulkImportPreviewReady.value)
const bulkImportTemplateDownloadLabel = computed(() => bulkImportTemplateTypeIds.value.length > 1 ? '下载模型模板包' : '下载当前模板')
const ciDetailFields = computed(() => {
  if (!ciDetail.value) return []
  if (Array.isArray(ciDetail.value.field_definitions) && ciDetail.value.field_definitions.length) {
    return ciDetail.value.field_definitions
  }
  return ciFields.value.filter(item => item.ci_type === ciDetail.value.ci_type && item.is_active !== false)
})
const ciDetailDisplayFields = computed(() => ciDetailFields.value.filter(field => field.code !== 'department'))
const ciDetailAttributeEntries = computed(() => {
  const attributes = ciDetail.value?.attributes || {}
  const modelFieldCodes = new Set(ciDetailFields.value.map(field => field.code))
  const baseAttributeCodes = new Set([
    'business_line', 'environment', 'admin_user', 'department',
    'source_type', 'source_account', 'source_region', 'source_unique_id',
    'resource_node_id',
  ])
  if (isCiDetailWebAddressAsset.value) baseAttributeCodes.add('ip_address')
  const hiddenCodes = new Set([...modelFieldCodes, ...baseAttributeCodes, ...resourceWaterlineAttributeCodes])
  return Object.entries(attributes)
    .filter(([key]) => !hiddenCodes.has(key))
    .map(([key, value]) => ({ key, value }))
})
const ciDetailSourceText = computed(() => {
  const sources = ciDetailMappings.value
    .map(item => syncSourceTypeLabel(item.source_type, item.source_type))
    .filter(Boolean)
  return Array.from(new Set(sources)).join('、') || '-'
})

function normalizeWebAddress(value) {
  const address = String(value || '').trim()
  if (!address) return ''
  if (/^https?:\/\//i.test(address)) return address
  if (/^[a-z][a-z0-9+.-]*:/i.test(address)) return ''
  return `https://${address}`
}

function openCiDetailWebAddress() {
  if (!ciDetailWebAddress.value) return
  window.open(ciDetailWebAddress.value, '_blank', 'noopener,noreferrer')
}

function disposeCiDetailWaterlineChart() {
  ciDetailWaterlineChart?.dispose()
  ciDetailWaterlineChart = null
}

function renderCiDetailWaterlineChart() {
  const chartElement = ciDetailWaterlineChartRef.value
  if (!chartElement) return
  if (ciDetailWaterlineChart && ciDetailWaterlineChart.getDom() !== chartElement) disposeCiDetailWaterlineChart()
  if (!ciDetailWaterlineChart) ciDetailWaterlineChart = echarts.init(chartElement, null, { renderer: 'canvas' })

  const windowEnd = new Date(ciDetailWaterlineWindow.value.end || Date.now())
  const windowStart = new Date(ciDetailWaterlineWindow.value.start || (windowEnd.getTime() - 6 * 60 * 60 * 1000))
  const metricColors = ['#245bdb', '#0f9f8f', '#f59e0b']
  const pointsByMetric = new Map()
  for (const definition of resourceWaterlineMetricDefs) {
    pointsByMetric.set(definition.key, ciDetailWaterlineHistory.value
      .filter(item => definition.metrics.includes(item.metric) && item.collected_at)
      .map(item => ({
        value: item.usage_percent === null || item.usage_percent === undefined || item.usage_percent === ''
          ? Number(item.value)
          : Number(item.usage_percent),
        collectedAt: item.collected_at,
        raw: item,
      }))
      .filter(item => Number.isFinite(item.value))
      .sort((left, right) => String(left.collectedAt).localeCompare(String(right.collectedAt))))
  }
  const hasUsagePercent = ciDetailWaterlineHistory.value.some(item => item.usage_percent !== null && item.usage_percent !== undefined && item.usage_percent !== '')
  const series = resourceWaterlineMetricDefs
    .map((definition, index) => ({
      name: definition.label,
      type: 'line',
      smooth: true,
      showSymbol: false,
      connectNulls: false,
      lineStyle: { width: 2 },
      itemStyle: { color: metricColors[index] },
      data: (pointsByMetric.get(definition.key) || []).map(item => [item.collectedAt, item.value, item.raw]),
    }))

  ciDetailWaterlineChart.setOption({
    color: metricColors,
    grid: { top: 36, right: 18, bottom: 32, left: 46 },
    legend: { top: 0, left: 0, itemWidth: 10, itemHeight: 10, textStyle: { color: '#475569', fontSize: 12 } },
    tooltip: {
      trigger: 'axis',
      backgroundColor: 'rgba(15, 23, 42, .92)',
      borderWidth: 0,
      textStyle: { color: '#f8fafc' },
      formatter: (items) => {
        const time = items?.[0]?.data?.[0] ? formatTime(items[0].data[0]) : '-'
        const rows = items.map(item => {
          const snapshot = item.data?.[2]
          const value = snapshot?.usage_percent === null || snapshot?.usage_percent === undefined || snapshot?.usage_percent === ''
            ? formatMetricValue(snapshot)
            : formatPercent(snapshot.usage_percent)
          return `${item.marker}${item.seriesName}：${value}`
        })
        const sourceLabel = resourceWaterlineSourceLabel([
          ...items.map(item => item.data?.[2]?.source),
          ciDetail.value?.attributes?.metric_collection_source,
          ciDetail.value?.attributes?.metric_datasource,
        ])
        return [time, ...rows, `采集来源：${sourceLabel}`].join('<br/>')
      },
    },
    xAxis: {
      type: 'time',
      min: windowStart.getTime(),
      max: windowEnd.getTime(),
      splitNumber: 6,
      axisLine: { lineStyle: { color: '#dbe4f0' } },
      axisLabel: { color: '#94a3b8', fontSize: 11, formatter: value => new Date(value).toLocaleString([], { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }) },
      splitLine: { show: false },
    },
    yAxis: {
      type: 'value',
      min: hasUsagePercent || !ciDetailWaterlineHistory.value.length ? 0 : undefined,
      max: hasUsagePercent || !ciDetailWaterlineHistory.value.length ? 100 : undefined,
      axisLabel: { color: '#94a3b8', fontSize: 11, formatter: value => hasUsagePercent || !ciDetailWaterlineHistory.value.length ? `${value}%` : value },
      splitLine: { lineStyle: { color: 'rgba(148, 163, 184, .16)' } },
    },
    series,
  }, true)
  ciDetailWaterlineChart.resize()
}

function listOf(response) {
  if (Array.isArray(response)) return response
  return response?.results || []
}

function totalOf(response, fallback = 0) {
  if (typeof response?.count === 'number') return response.count
  return fallback
}

const hiddenCiTypeCodes = new Set(['CLOUD_DATABASE', 'VSPHERE_CAPACITY', 'SECURITY_GROUP', 'EIP', 'SPARK', 'HIVE', 'HBASE', 'DORIS'])

function isDuplicateNatGatewayModel(item = {}) {
  const name = String(item.name || item.ci_type_name || '').replace(/\s+/g, '')
  return name === 'NAT网关'
}

function isVisibleCiType(item = {}) {
  if (item.is_active === false) return false
  const code = String(item.code || item.ci_type_code || '').toUpperCase()
  const name = String(item.name || item.ci_type_name || '')
  return !hiddenCiTypeCodes.has(code)
    && !isDuplicateNatGatewayModel(item)
    && !['云数据库', 'Docker环境', 'vSphere资源统计', '数据仓库', 'Security Group', '安全组', '弹性IP', '弹性 IP', 'Spark', 'Hive', 'HBase', 'Doris'].includes(name)
}

function withoutHiddenCiTypes(rows) {
  return listOf(rows).filter(isVisibleCiType)
}

function normalizeRepositoryPayload(payload = {}) {
  const next = { ...payload }
  next.groups = listOf(payload.groups).map(group => ({
    ...group,
    models: withoutHiddenCiTypes(group.models || []),
  })).filter(group => (group.models || []).length)
  next.top_models = withoutHiddenCiTypes(payload.top_models || [])
  next.tree = listOf(payload.tree).map(group => ({
    ...group,
    children: withoutHiddenCiTypes(group.children || group.models || []),
  })).filter(group => (group.children || []).length)
  return next
}

function islandIssueText(type) {
  const mapping = {
    missing_ownership: '归属缺失',
    no_relation: '关系断点',
    missing_required_relation: '必填关系缺失',
    duplicate_unique_field: '唯一字段重复',
    no_source: '来源缺失',
    unbound_cloud_resource: '云资源未绑定',
    unlinked_data_service: '数据服务未关联',
  }
  return mapping[type] || type || '-'
}

function duplicateUniqueText(row) {
  const names = Array.isArray(row?.duplicate_ci_names) ? row.duplicate_ci_names.filter(Boolean) : []
  if (!names.length) return `重复资源 ${row?.duplicate_count || 0} 个`
  return `涉及资源：${names.slice(0, 4).join('、')}${names.length > 4 ? ' 等' : ''}`
}

function islandSeverityType(severity) {
  if (severity === 'high') return 'danger'
  if (severity === 'medium') return 'warning'
  return 'info'
}

function islandCanAutoCreate(row) {
  if (row?.issue_type !== 'missing_required_relation') return false
  if (row.can_auto_create === true || row.governance_status === 'auto_candidate') return true
  return Boolean((row.relation_candidates || [])[0]?.id)
}

function islandNeedsManualRelation(row) {
  if (row?.issue_type !== 'missing_required_relation') return false
  if (row.governance_status === 'manual_required' || row.can_auto_create === false) return true
  return !(row.relation_candidates || []).length
}

function islandGovernanceText(row) {
  if (islandCanAutoCreate(row)) return '可自动关联'
  if (islandNeedsManualRelation(row)) return '需手动选择'
  if (row?.issue_type === 'duplicate_unique_field') return '需合并'
  if (row?.issue_type === 'missing_ownership') return '待补归属'
  if (row?.issue_type === 'no_source') return '待补来源'
  return '待治理'
}

function islandGovernanceTagType(row) {
  if (islandCanAutoCreate(row)) return 'success'
  if (islandNeedsManualRelation(row) || row?.issue_type === 'duplicate_unique_field') return 'warning'
  if (row?.severity === 'high') return 'danger'
  return 'info'
}

function relationTypeLabel(type) {
  const normalizedType = {
    contains: 'connects_to',
    hosted_on: 'connects_to',
  }[String(type || '').trim()] || type
  const mapping = {
    depends_on: '依赖',
    runs_on: '运行于',
    connects_to: '连接到',
  }
  return mapping[normalizedType] || normalizedType || '-'
}

function relationEvidenceSourceText(value) {
  return relationEvidenceSourceOptions.find(item => item.value === value)?.label || value || '人工维护'
}

function relationEvidenceText(row) {
  const evidence = row?.evidence || {}
  if (!Object.keys(evidence).length) return row?.description || '-'
  const source = evidence.source || evidence.issue_type || evidence.rule || evidence.candidate_id
  if (source) return String(source)
  return JSON.stringify(evidence)
}

function relationCandidateText(candidate) {
  const scope = [
    candidate?.ci_type_name,
    candidate?.business_line,
    candidate?.environment_display || candidate?.environment,
  ].filter(Boolean).join(' · ')
  const reasons = (candidate?.reasons || []).join(' / ')
  return [scope, reasons].filter(Boolean).join(' ｜ ') || '候选资源'
}

function modelName(id) {
  return ciTypes.value.find(item => item.id === id)?.name || '-'
}

function inferModelIconValue(model = {}) {
  const explicitIcon = model.icon || ''
  const identity = `${model.code || ''} ${model.name || ''}`.toUpperCase()
  const genericIcons = new Set(['', 'SETUP', 'DATABOARD'])
  if (!genericIcons.has(String(explicitIcon).toUpperCase())) return explicitIcon
  if (/(MONGODB|MONGO|DOCUMENT|文档)/.test(identity)) return 'Document'
  if (/(MYSQL|MARIADB|POSTGRESQL|POLARDB|RDS|DATABASE|DB|数据库)/.test(identity)) return 'Database'
  if (/(REDIS|TAIR|CACHE|缓存)/.test(identity)) return 'Cache'
  if (/(KAFKA|ROCKETMQ|RABBITMQ|MQ|QUEUE|消息)/.test(identity)) return 'MessageQueue'
  if (/(MIDDLEWARE|ELASTICSEARCH|中间件)/.test(identity)) return 'Operation'
  return explicitIcon || 'SetUp'
}

function modelIconMeta(input) {
  const icon = typeof input === 'object' && input !== null ? inferModelIconValue(input) : input
  return modelIconMap.get(icon || 'SetUp') || modelIconMap.get('SetUp')
}

function modelIconComponent(input) {
  return modelIconMeta(input)?.component || SetUp
}

function modelIconColor(input) {
  return modelIconMeta(input)?.color || '#64748b'
}

function topologyNodeIcon(node = {}) {
  const model = ciTypes.value.find(item => item.name === node.type || String(item.id) === String(node.ci_type))
  return modelIconComponent(model || { icon: node.icon, name: node.type })
}

function topologyNodeStyle(node = {}) {
  const model = ciTypes.value.find(item => item.name === node.type || String(item.id) === String(node.ci_type))
  const color = node.color || model?.color || modelIconColor(model || { icon: node.icon, name: node.type })
  return { '--topology-node-color': color }
}

function topologyLaneStyle(lane = {}) {
  return {
    left: `${lane.x || 0}px`,
    top: `${lane.y || 0}px`,
    width: `${lane.width || 220}px`,
    height: `${lane.height || 380}px`,
    '--lane-color': lane.color || '#245bdb',
  }
}

function topologyBoardNodeStyle(node = {}) {
  const base = topologyNodeStyle(node)
  return {
    ...base,
    left: `${node.boardX || 0}px`,
    top: `${node.boardY || 0}px`,
    width: `${node.boardWidth || 176}px`,
    height: `${node.boardHeight || 58}px`,
    '--node-color': node.groupColor || base['--topology-node-color'] || '#245bdb',
  }
}

function selectModelIcon(item) {
  modelForm.icon = item.value
  modelForm.color = item.color
}

function currentMonth() {
  const now = new Date()
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
}

function hasFreshOverviewCache(cachedAt, ttl) {
  return cachedAt && Date.now() - cachedAt < ttl
}

async function fetchOverviewCostSummary(options = {}) {
  const { force = false } = options
  if (!canViewCost.value) {
    overviewCostReport.value = {}
    overviewCostOptimization.value = {}
    return
  }
  const businessEnvironmentScope = overviewBusinessEnvironmentCostScope.value
  const scopeKey = overviewResourceDimension.value === 'cloud_account'
    ? `cloud_account:${overviewResourceScope.value || ''}`
    : `business_environment:${businessEnvironmentScope?.businessLine || '__unassigned__'}:${businessEnvironmentScope?.environment || '__unassigned__'}`
  if (!force && scopeKey === overviewCostScopeKey && hasFreshOverviewCache(overviewCostCacheAt, OVERVIEW_CACHE_TTL.cost)) return
  if (overviewCostRequest) return overviewCostRequest
  overviewCostLoading.value = true
  overviewCostRequest = (async () => {
    const params = { month: currentMonth() }
    if (overviewResourceDimension.value === 'cloud_account' && overviewResourceScope.value) {
      params.source_account = overviewResourceScope.value
    }
    if (businessEnvironmentScope) {
      params.business_line = businessEnvironmentScope.businessLine || '__unassigned__'
      params.environment = businessEnvironmentScope.environment || '__unassigned__'
    }
    const reportResult = await getCmdbCostReport(params)
    overviewCostReport.value = reportResult || {}
    overviewCostOptimization.value = reportResult?.optimization_preview || {}
    overviewCostScopeKey = scopeKey
    overviewCostCacheAt = Date.now()
  })()
  try {
    return await overviewCostRequest
  } finally {
    overviewCostRequest = null
    overviewCostLoading.value = false
  }
}

function switchTab(tabKey) {
  const tab = tabs.value.find(item => item.key === tabKey)
  if (tab && tab.path !== route.path) router.push(tab.path)
}

async function navigateToTab(tabKey) {
  const tab = tabs.value.find(item => item.key === tabKey)
  if (tab && tab.path !== route.path) await router.push(tab.path)
}

function setLedgerCoverageContext(item, labelSuffix = '') {
  ledgerSummaryContext.value = {
    key: `phase_one_${item.key}`,
    label: `${item.title}${labelSuffix ? `：${labelSuffix}` : ''}`,
  }
}

async function openPhaseOneCoverageCard(item) {
  if (!item) return
  if (item.key === 'waterline') {
    await navigateToTab('thresholds')
    await fetchThresholdManagement()
    return
  }
  if (item.key === 'sync') {
    clearSyncFilters()
    await navigateToTab('sync')
    await Promise.all([fetchSyncJobs(), fetchCollectionSummary(true)])
    return
  }

  resetLedgerFilters()
  if (item.key === 'cloud') {
    setLedgerCoverageContext(item, '虚拟机 / 云主机')
  } else if (item.key === 'third-party' && thirdPartyType.value?.id) {
    ledgerFilters.ci_type = thirdPartyType.value.id
    setLedgerCoverageContext(item, '第三方服务')
  } else if (item.key === 'aliyun-middleware') {
    setLedgerCoverageContext(item, '跨 MySQL/Redis/MongoDB/Kafka/RocketMQ/OSS/SLB 模型核查')
  } else {
    setLedgerCoverageContext(item)
  }

  await navigateToTab('ledger')
  await fetchLedger()
}

async function openPhaseOneAction(item) {
  if (!item) return
  if (item.target === 'sync') {
    clearSyncFilters()
    await navigateToTab('sync')
    await Promise.all([fetchSyncJobs(), fetchCollectionSummary(true)])
    const sourceTypes = Array.isArray(item.sourceTypes) ? item.sourceTypes.filter(Boolean) : []
    if (sourceTypes.length) {
      focusSyncJointCard({
        key: item.key,
        title: item.title,
        hint: item.desc,
        sourceTypes,
      })
    }
    return
  }

  const coverageCard = phaseOneCoverageCards.value.find(card => card.key === item.coverageKey || card.key === item.key)
  if (coverageCard) {
    await openPhaseOneCoverageCard(coverageCard)
    return
  }
  if (item.target) await navigateToTab(item.target)
}

function selectOpsanyViewNode(node) {
  selectedOpsanyViewNode.value = { ...node }
}

function switchOpsanyViewMode(mode) {
  if (!['application', 'host', 'physical'].includes(mode) || mode === viewMode.value) return
  viewMode.value = mode
  selectedOpsanyViewNode.value = { mode, key: 'all', scope: 'all' }
  opsanyViewKeyword.value = ''
}

function isOpsanyViewNodeActive(node) {
  const active = activeOpsanyViewNode.value
  return active.mode === node.mode && active.key === node.key
}

function parseRackU(value) {
  if (value === null || value === undefined) return null
  const match = String(value).match(/\d+/)
  if (!match) return null
  const u = Number(match[0])
  return Number.isInteger(u) && u >= 1 && u <= 42 ? u : null
}

function rackSlots(row) {
  const hostByU = new Map()
  ;(Array.isArray(row?.hosts) ? row.hosts : []).forEach((host) => {
    const u = parseRackU(host?.u_position ?? host?.u ?? host?.attributes?.u_position ?? host?.attributes?.u)
    if (u && !hostByU.has(u)) hostByU.set(u, host)
  })
  return Array.from({ length: 42 }, (_, index) => {
    const u = 42 - index
    return { u, host: hostByU.get(u) || null }
  })
}

function applySummary(card) {
  activeSummaryKey.value = card.key
  if (card.key === 'all') {
    resetLedgerFilters()
    ledgerSummaryContext.value = { key: card.key, label: card.label }
    switchTab('ledger')
    fetchLedger()
    return
  }
  if (card.key === 'active') {
    resetLedgerFilters()
    ledgerFilters.status = 'active'
    ledgerSummaryContext.value = { key: card.key, label: card.label }
    switchTab('ledger')
    fetchLedger()
    return
  }
  if (card.key === 'governance') {
    governanceViewMode.value = 'categories'
    switchTab('governance')
    fetchGovernanceRisks({ force: true })
    fetchGovernance()
    return
  }
  if (card.key === 'quality') {
    governanceViewMode.value = 'categories'
    switchTab('governance')
    fetchGovernanceRisks({ force: true })
    fetchGovernance()
    return
  }
  if (card.key === 'risk') {
    activeGovernanceKey.value = 'capacity'
    governanceViewMode.value = 'detail'
    switchTab('governance')
    fetchGovernanceRisks({ force: true })
  }
}

function normalizeGovernanceKey(target) {
  return governanceFilterCards.value.some(item => item.key === target)
    ? target
    : (governanceFilterCards.value[0]?.key || 'archive')
}

function openGovernanceCategory(target) {
  activeGovernanceKey.value = normalizeGovernanceKey(target)
  governanceViewMode.value = 'detail'
  archiveSelection.value = []
}

function backToGovernanceCategories() {
  governanceViewMode.value = 'categories'
  archiveSelection.value = []
}

function openAssetGovernance(target = 'all') {
  if (!target || target === 'all') {
    governanceViewMode.value = 'categories'
  } else {
    openGovernanceCategory(target)
  }
  switchTab('governance')
}

function applyOverviewSuggestion(item) {
  const targetMap = {
    capacity: 'capacity',
    sync: 'sync',
    archive: 'archive',
    expiry: 'service_expiry',
    service_expiry: 'service_expiry',
    third_party_service_expiry: 'service_expiry',
    asset_service_expiry: 'service_expiry',
  }
  openAssetGovernance(targetMap[item?.type] || 'archive')
}

function openCostManagement() {
  router.push('/cmdb/cost')
}

function applyGovernanceRisk(item) {
  const targetMap = {
    archive_candidates: 'archive',
    sync_failures: 'sync',
    capacity_risks: 'capacity',
    service_expiry: 'service_expiry',
  }
  const target = targetMap[item.key]
  if (target) {
    openAssetGovernance(target)
    return
  }
  openAssetGovernance('all')
}

function formatModelQualityIssues(issueCounts = {}) {
  const labels = [
    ['missing_ownership', '归属'],
    ['no_source', '来源'],
    ['no_relation', '关系'],
    ['completion_issues', '补全'],
    ['archive_candidates', '下线'],
    ['sync_failures', '同步'],
  ]
  const active = labels
    .filter(([key]) => Number(issueCounts?.[key] || 0) > 0)
    .map(([, label]) => label)
  return active.length ? active.slice(0, 3).join('、') : '正常'
}

function ensureAccessibleRoute() {
  if (!tabs.value.length) return router.replace('/403')
  const currentTab = routeTabMap[route.name]
  if (!tabs.value.some(item => item.key === currentTab)) router.replace(tabs.value[0].path)
}

async function fetchDashboard(options = {}) {
  const { useCache = false, force = false } = options
  if (!canViewDashboard.value) return
  if (useCache && !force && hasFreshOverviewCache(overviewDashboardCacheAt, OVERVIEW_CACHE_TTL.dashboard)) return dashboard.value
  if (overviewDashboardRequest) return overviewDashboardRequest
  dashboardLoading.value = true
  overviewDashboardRequest = (async () => {
    dashboard.value = await getCmdbDashboard(BACKGROUND_REQUEST_CONFIG)
    overviewDashboardCacheAt = Date.now()
    return dashboard.value
  })()
  try {
    return await overviewDashboardRequest
  } finally {
    overviewDashboardRequest = null
    dashboardLoading.value = false
  }
}

async function fetchGovernanceRisks(options = {}) {
  const { force = false } = options
  if (!canViewCi.value) return
  try {
    const response = await getCmdbGovernanceRisks({ ...BACKGROUND_REQUEST_CONFIG, params: force ? { refresh: 1 } : undefined })
    if (response) governanceRisks.value = response
    return governanceRisks.value
  } catch (error) {
    if (governanceRisks.value?.generated_at) {
      ElMessage.warning('风险数据刷新失败，已保留上一轮结果')
      return governanceRisks.value
    }
    throw error
  }
}

function currentThresholdParams() {
  const params = { page_size: 200 }
  if (thresholdFilters.resource_type) params.resource_type = thresholdFilters.resource_type
  if (thresholdFilters.metric) params.metric = thresholdFilters.metric
  if (thresholdFilters.enabled !== '') params.enabled = thresholdFilters.enabled
  return params
}

async function fetchThresholdPolicies() {
  if (!canViewCi.value) return
  thresholdLoading.value = true
  try {
    thresholdPolicies.value = listOf(await getThresholdPolicies(currentThresholdParams()))
  } finally {
    thresholdLoading.value = false
  }
}

async function fetchResourceMetrics() {
  if (!canViewCi.value) return
  metricLoading.value = true
  try {
    const params = { page_size: 1000 }
    if (thresholdFilters.metric) params.metric = thresholdFilters.metric
    resourceMetrics.value = listOf(await getResourceMetrics(params))
  } finally {
    metricLoading.value = false
  }
}

async function fetchOverviewResourceMetrics(rows = overviewServerItems.value) {
  if (!canViewCi.value) return
  const ciIds = Array.from(new Set(
    listOf(rows)
      .filter(row => isOverviewServer(row) || isOverviewProviderSummaryRow(row))
      .map(row => row?.id || row?.ci || row?.ci_id)
      .filter(value => value !== undefined && value !== null && String(value).trim() !== '')
      .map(value => String(value)),
  ))
  if (!ciIds.length) {
    overviewResourceMetrics.value = []
    return
  }
  const chunks = []
  for (let index = 0; index < ciIds.length; index += 150) {
    chunks.push(ciIds.slice(index, index + 150))
  }
  const metricNames = Array.from(new Set(aggregateResourceMetricDefs.flatMap(def => def.metrics))).join(',')
  const responses = await Promise.allSettled(chunks.map(chunk => getLatestResourceMetrics({
    ci_ids: chunk.join(','),
    metrics: metricNames,
  })))
  overviewResourceMetrics.value = responses
    .filter(result => result.status === 'fulfilled')
    .flatMap(result => listOf(result.value))
}

async function fetchOverviewServerItems(options = {}) {
  const { force = false } = options
  if (!canViewCi.value) return
  if (!force && hasFreshOverviewCache(overviewResourcesCacheAt, OVERVIEW_CACHE_TTL.resources)) return overviewServerItems.value
  if (overviewResourcesRequest) return overviewResourcesRequest
  overviewServerLoading.value = true
  overviewResourcesRequest = (async () => {
    const rows = listOf(await getConfigItemLedgerTree(
      { include_internal_summaries: true },
      BACKGROUND_REQUEST_CONFIG,
    ))
    overviewServerItems.value = rows
    await fetchOverviewResourceMetrics(rows)
    overviewResourcesCacheAt = Date.now()
    return rows
  })()
  try {
    return await overviewResourcesRequest
  } finally {
    overviewResourcesRequest = null
    overviewServerLoading.value = false
  }
}

async function fetchThresholdManagement() {
  await Promise.all([fetchThresholdPolicies(), fetchResourceMetrics()])
}

async function fetchTypesAndFields() {
  const canReadModelMetadata = canViewCi.value || canManageCi.value || canViewModel.value || canManageModel.value
  const canReadModelConfig = canViewModel.value || canManageModel.value
  const loadMetadata = () => Promise.allSettled([
    canReadModelMetadata ? getCITypes({ page_size: 200 }) : Promise.resolve([]),
    canReadModelMetadata ? getCIFields({ page_size: 300 }) : Promise.resolve([]),
    canReadModelConfig ? getCIModelGroups({ page_size: 100 }) : Promise.resolve([]),
    canReadModelConfig ? getCIRelationRules({ page_size: 300 }) : Promise.resolve([]),
  ])
  let [typesRes, fieldsRes, groupsRes, rulesRes] = await loadMetadata()
  const rawTypes = typesRes.status === 'fulfilled' ? listOf(typesRes.value) : []
  const rawGroups = groupsRes.status === 'fulfilled' ? listOf(groupsRes.value) : []
  const rawRules = rulesRes.status === 'fulfilled' ? listOf(rulesRes.value) : []
  if (shouldAutoEnsureAssetBuiltins(rawGroups, rawTypes, rawRules)) {
    builtinAutoEnsureAttempted.value = true
    try {
      await ensureCmdbBuiltins()
      ;[typesRes, fieldsRes, groupsRes, rulesRes] = await loadMetadata()
    } catch (error) {
      console.warn('auto ensure cmdb builtins failed', error)
    }
  }
  ciTypes.value = typesRes.status === 'fulfilled' ? withoutHiddenCiTypes(typesRes.value) : []
  const visibleTypeIds = new Set(ciTypes.value.map(item => String(item.id)))
  ciFields.value = fieldsRes.status === 'fulfilled'
    ? listOf(fieldsRes.value).filter(item => !item.ci_type || visibleTypeIds.has(String(item.ci_type)))
    : []
  ciModelGroups.value = groupsRes.status === 'fulfilled'
    ? listOf(groupsRes.value).filter(item => item.is_active !== false && String(item.code || '').toLowerCase() !== 'data')
    : []
  modelRelationRules.value = rulesRes.status === 'fulfilled'
    ? listOf(rulesRes.value).filter(item => visibleTypeIds.has(String(item.source_type)) && visibleTypeIds.has(String(item.target_type)))
    : []
}

function shouldAutoEnsureAssetBuiltins(groups = [], types = [], rules = []) {
  if (builtinAutoEnsureAttempted.value || !canManageModel.value) return false
  const activeGroupCodes = new Set(groups
    .filter(group => group.is_active !== false)
    .map(group => String(group.code || '').toLowerCase()))
  const activeTypeCodes = new Set(types
    .filter(type => type.is_active !== false)
    .map(type => String(type.code || '').toUpperCase()))
  const missingStandardGroup = [...standardAssetModelGroupCodes].some(code => !activeGroupCodes.has(code))
  const missingCloudAssetModels = requiredCloudAssetModelCodes.some(code => !activeTypeCodes.has(code))
  const hasOldDataGroup = activeGroupCodes.has('data')
  const hasOldDataModels = types.some(type => String(type.group_code || '').toLowerCase() === 'data')
  const hasObsoleteCloudDatabase = types.some(type => (
    String(type.code || '').toUpperCase() === 'CLOUD_DATABASE'
      || String(type.name || '').trim() === '云数据库'
  ) && type.is_active !== false)
  const typeCodeById = new Map(types.map(type => [String(type.id), String(type.code || '').toUpperCase()]))
  const activeRelationKeys = new Set(rules
    .filter(rule => rule.is_active !== false)
    .map(rule => `${typeCodeById.get(String(rule.source_type)) || ''}->${typeCodeById.get(String(rule.target_type)) || ''}:${rule.relation_type || ''}`))
  const missingBuiltinRelations = requiredBuiltinRelationKeys.some(([sourceCode, targetCode, relationType]) => (
    !activeRelationKeys.has(`${sourceCode}->${targetCode}:${relationType}`)
  ))
  const hasObsoleteK8sRelation = activeRelationKeys.has('K8S_CLUSTER->APP_SERVICE:runs_on')
  return missingStandardGroup || missingCloudAssetModels || hasOldDataGroup || hasOldDataModels || hasObsoleteCloudDatabase || missingBuiltinRelations || hasObsoleteK8sRelation
}

async function fetchTags() {
  if (!canViewCi.value) return
  tagLoading.value = true
  try {
    ciTags.value = listOf(await getCITags({ page_size: 200 }))
  } finally {
    tagLoading.value = false
  }
}

function currentAuditParams() {
  const params = { page_size: 80 }
  if (auditFilters.search) params.search = auditFilters.search
  if (auditFilters.action) params.action = auditFilters.action
  if (auditFilters.operator) params.operator = auditFilters.operator
  if (auditFilters.source) params.source = auditFilters.source
  if (Array.isArray(auditFilters.range) && auditFilters.range.length === 2) {
    params.start = auditFilters.range[0]
    params.end = auditFilters.range[1]
  }
  return params
}

async function fetchAuditLogs() {
  if (!canViewAudit.value) return
  auditLoading.value = true
  try {
    const params = currentAuditParams()
    const [logsRes, summaryRes] = await Promise.all([
      getChangeLogs(params),
      getChangeLogSummary(params),
    ])
    auditLogs.value = listOf(logsRes)
    auditSummary.value = summaryRes || { total: 0, action_counts: [], operator_counts: [], source_counts: [] }
  } finally {
    auditLoading.value = false
  }
}

function resetTagForm() {
  tagEditingId.value = null
  Object.assign(tagForm, {
    name: '',
    category: '',
    color: '#245bdb',
    description: '',
    is_active: true,
  })
}

function openTagDialog(row = null) {
  if (!row) {
    resetTagForm()
  } else {
    tagEditingId.value = row.id
    Object.assign(tagForm, {
      name: row.name || '',
      category: row.category || '',
      color: row.color || '#245bdb',
      description: row.description || '',
      is_active: row.is_active !== false,
    })
  }
  tagDialogVisible.value = true
}

async function saveTag() {
  if (!tagForm.name) return ElMessage.warning('请填写标签名称')
  saving.value = true
  try {
    const payload = { ...tagForm }
    if (tagEditingId.value) {
      await updateCITag(tagEditingId.value, payload)
      ElMessage.success('标签已更新')
    } else {
      await createCITag(payload)
      ElMessage.success('标签已创建')
    }
    tagDialogVisible.value = false
    await Promise.all([fetchTags(), fetchDashboard()])
  } finally {
    saving.value = false
  }
}

async function deleteTagRow(row) {
  await ElMessageBox.confirm(`确认删除标签「${row.name}」？已关联资源的标签需要先移除关联。`, '删除标签', { type: 'warning' })
  await deleteCITag(row.id)
  ElMessage.success('标签已删除')
    await Promise.all([fetchTags(), fetchDashboard(), fetchLedger()])
}

function resetAuthorizationForm() {
  authorizationEditingId.value = null
  Object.assign(authorizationForm, {
    name: '',
    principal_type: 'user',
    principal: '',
    permission: 'view',
    business_line: '',
    environment: '',
    ci_type: '',
    description: '',
    is_active: true,
  })
}

function openAuthorizationDialog(row = null) {
  if (!row) {
    resetAuthorizationForm()
  } else {
    authorizationEditingId.value = row.id
    Object.assign(authorizationForm, {
      name: row.name || '',
      principal_type: row.principal_type || 'user',
      principal: row.principal || '',
      permission: row.permission || 'view',
      business_line: row.business_line || '',
      environment: row.environment || '',
      ci_type: row.ci_type || '',
      description: row.description || '',
      is_active: row.is_active !== false,
    })
  }
  authorizationDialogVisible.value = true
}

async function saveAuthorization() {
  if (!authorizationForm.name.trim()) return ElMessage.warning('请填写授权名称')
  if (!authorizationForm.principal.trim()) return ElMessage.warning('请填写授权主体')
  if (authorizationForm.permission === 'manage' && !authorizationForm.business_line && !authorizationForm.ci_type) {
    return ElMessage.warning('管理授权至少限定业务线或资源模型')
  }
  const payload = {
    name: authorizationForm.name.trim(),
    principal_type: authorizationForm.principal_type,
    principal: authorizationForm.principal.trim(),
    permission: authorizationForm.permission,
    business_line: authorizationForm.business_line || '',
    environment: authorizationForm.environment || '',
    ci_type: authorizationForm.ci_type || null,
    description: authorizationForm.description || '',
    is_active: authorizationForm.is_active,
  }
  saving.value = true
  try {
    if (authorizationEditingId.value) {
      await updateResourceAuthorization(authorizationEditingId.value, payload)
      ElMessage.success('资源授权已更新')
    } else {
      await createResourceAuthorization(payload)
      ElMessage.success('资源授权已创建')
    }
    authorizationDialogVisible.value = false
    await fetchResourceAuthorizations()
  } finally {
    saving.value = false
  }
}

async function deleteAuthorizationRow(row) {
  await ElMessageBox.confirm(`确认删除授权策略「${row.name}」吗？`, '删除资源授权', { type: 'warning' })
  await deleteResourceAuthorization(row.id)
  ElMessage.success('资源授权已删除')
  await fetchResourceAuthorizations()
}

async function fetchRepositorySummary() {
  if (!canViewCi.value) return
  repositoryLoading.value = true
  try {
    const [summaryRes, treeRes] = await Promise.allSettled([
      getCmdbRepositorySummary(),
      getCmdbModelTree({ include_fields: true }, { skipErrorMessage: true }),
    ])
    repositorySummary.value = summaryRes.status === 'fulfilled'
      ? normalizeRepositoryPayload(summaryRes.value || { summary: {}, groups: [], top_models: [] })
      : { summary: {}, groups: [], top_models: [] }
    repositoryModelTree.value = treeRes.status === 'fulfilled'
      ? normalizeRepositoryPayload(treeRes.value || { summary: {}, groups: [], tree: [], top_models: [] })
      : { summary: repositorySummary.value.summary || {}, groups: repositorySummary.value.groups || [], tree: [], top_models: repositorySummary.value.top_models || [] }
  } finally {
    repositoryLoading.value = false
  }
}

async function fetchViewsSummary() {
  if (!canViewCi.value) return
  viewsLoading.value = true
  try {
    const params = {}
    Object.entries(viewFilters).forEach(([key, value]) => {
      if (value) params[key] = value
    })
    viewsSummary.value = await getCmdbViewsSummary(params)
  } finally {
    viewsLoading.value = false
  }
}

function resourceWaterlineTargetRows(rows = []) {
  return (rows || []).filter(isResourceWaterlineTarget)
}

function currentPageWaterlineCiIds(rows = []) {
  return [...new Set(resourceWaterlineTargetRows(rows)
    .map(row => row?.id)
    .filter(value => value !== undefined && value !== null && String(value).trim() !== '')
    .map(value => Number(value))
    .filter(value => Number.isFinite(value) && value > 0))]
}

function refreshWaterlineSuccessText(result = {}) {
  const metricCount = Number(result?.summary?.metric_snapshot || 0)
  const refreshedCount = Number(result?.refreshed_count || 0)
  const skippedCount = Number(result?.skipped_count || 0)
  if (metricCount > 0) {
    return `已刷新 ${refreshedCount || Math.ceil(metricCount / 3)} 个资产水位，新增 ${metricCount} 条快照`
  }
  if (skippedCount > 0) {
    return '当前页资源未采集到新的水位，请检查是否已配置对应同步任务'
  }
  return '当前页暂无可刷新的资产水位'
}

async function refreshCurrentPageWaterline(rows = [], reloadCurrentPage) {
  const ciIds = currentPageWaterlineCiIds(rows)
  if (!ciIds.length) {
    ElMessage.warning('当前页没有可刷新水位的虚拟机、ECS 或物理机')
    return
  }
  resourceWaterlinePageMetricLoading.value = true
  try {
    const result = await refreshCurrentPageResourceWaterline({ ci_ids: ciIds })
    resourceWaterlinePageMetrics.value = Array.isArray(result?.latest_metrics) ? result.latest_metrics : []
    ElMessage.success(refreshWaterlineSuccessText(result))
    if (typeof reloadCurrentPage === 'function') {
      await reloadCurrentPage()
    }
    await fetchDashboard()
  } finally {
    resourceWaterlinePageMetricLoading.value = false
  }
}

async function refreshCiDetailResourceWaterline() {
  const currentCi = ciDetail.value
  if (!currentCi?.id || !isResourceWaterlineTarget(currentCi)) return
  ciDetailWaterlineRefreshLoading.value = true
  try {
    const result = await refreshCurrentPageResourceWaterline({ ci_ids: [currentCi.id] })
    ElMessage.success(refreshWaterlineSuccessText(result))
    await openCiDetail(currentCi, false)
    await fetchDashboard()
  } finally {
    ciDetailWaterlineRefreshLoading.value = false
  }
}

async function refreshLedgerCurrentPageResourceWaterline() {
  await refreshCurrentPageWaterline(ledgerItems.value, () => fetchLedger({ preservePage: true, refreshTree: false }))
}

async function refreshModelCurrentPageResourceWaterline() {
  await refreshCurrentPageWaterline(
    selectedModelResourceRows.value,
    () => fetchModelResources(selectedModelId.value, { preservePage: true }),
  )
}

async function fetchLedger(options = {}) {
  if (!canViewCi.value) {
    resourceWaterlinePageMetrics.value = []
    return
  }
  const { preservePage = false, refreshTree = true } = options || {}
  if (!preservePage) ledgerPagination.page = 1
  ledgerLoading.value = true
  try {
    const params = {
      page: ledgerPagination.page,
      page_size: ledgerPagination.pageSize,
      include_fields: true,
      ...currentLedgerParams(),
    }
    if (refreshTree) {
      fetchLedgerTree()
    }
    const response = await getConfigItems(params)
    ledgerItems.value = withoutHiddenCiTypes(response)
    ledgerPagination.total = totalOf(response, ledgerItems.value.length)
    ledgerSelection.value = []
    await fetchThirdPartyExpirySummary()
  } finally {
    ledgerLoading.value = false
  }
}

async function fetchThirdPartyExpirySummary() {
  if (!canViewCi.value || !isThirdPartyLedgerMode.value) {
    thirdPartyExpirySummary.value = { total: 0, normal: 0, warning: 0, urgent: 0, expired: 0, missing: 0 }
    return
  }
  const params = currentLedgerParams()
  delete params.expiry_risk
  try {
    thirdPartyExpirySummary.value = await getThirdPartyExpirySummary(params)
  } catch (error) {
    console.warn('fetch third-party expiry summary failed', error)
  }
}

async function fetchModelThirdPartyExpirySummary(modelId = selectedModelId.value) {
  if (!canViewCi.value || !isThirdPartyModelResourceMode.value) {
    modelThirdPartyExpirySummary.value = { total: 0, normal: 0, warning: 0, urgent: 0, expired: 0, missing: 0 }
    return
  }
  const params = currentModelResourceParams(modelId)
  delete params.expiry_risk
  try {
    modelThirdPartyExpirySummary.value = await getThirdPartyExpirySummary(params)
  } catch (error) {
    console.warn('fetch model third-party expiry summary failed', error)
  }
}

function applyThirdPartyExpiryFilter(expiryRisk) {
  ledgerFilters.expiry_risk = ledgerFilters.expiry_risk === expiryRisk ? '' : expiryRisk
  fetchLedger()
}

function applyModelThirdPartyExpiryFilter(expiryRisk) {
  modelResourceFilters.expiry_risk = modelResourceFilters.expiry_risk === expiryRisk ? '' : expiryRisk
  fetchModelResources(selectedModelId.value)
}

function handleLedgerPageChange(page) {
  ledgerPagination.page = page
  fetchLedger({ preservePage: true, refreshTree: false })
}

function handleLedgerPageSizeChange(size) {
  ledgerPagination.pageSize = size
  ledgerPagination.page = 1
  fetchLedger({ preservePage: true, refreshTree: false })
}

async function fetchLedgerTree() {
  if (!canViewCi.value) return
  const requestSeq = ++ledgerTreeRequestSeq
  try {
    // Keep tree counts stable while the right-hand ledger is filtered by type or keyword.
    const response = await getConfigItemLedgerTree({}, { skipErrorMessage: true })
    if (requestSeq !== ledgerTreeRequestSeq) return
    ledgerTreeItems.value = withoutHiddenCiTypes(response)
    ledgerTreeLoaded.value = true
  } catch (error) {
    console.warn('fetch ledger tree failed', error)
  }
}

async function fetchModelCatalogTree() {
  if (!canViewCi.value) return
  modelCatalogTreeItems.value = withoutHiddenCiTypes(await getConfigItemLedgerTree())
}

async function fetchTopology() {
  if (!canViewModel.value) return
  topologyLoading.value = true
  try {
    const params = {
      ci_type: topologyFilters.ci_type || undefined,
      business_line: topologyFilters.business_line || undefined,
      environment: topologyFilters.environment || undefined,
      scope: topologyFilters.scope || 'neighbors',
    }
    topology.value = await getCmdbTopology(params) || { nodes: [], edges: [], meta: {} }
  } finally {
    topologyLoading.value = false
  }
}

async function fetchResourceNodeTree() {
  if (!canViewRequests.value && !canViewCi.value) return
  treeLoading.value = true
  try {
    const response = await getResourceNodeTree({ scope: 'all' })
    if (Array.isArray(response)) {
      resourceNodeTree.value = listOf(response)
      cloudResourceNodeTree.value = []
    } else {
      resourceNodeTree.value = listOf(response?.business)
      cloudResourceNodeTree.value = listOf(response?.cloud)
    }
  } finally {
    treeLoading.value = false
  }
}

async function fetchRequests() {
  if (!canViewRequests.value) return
  requestLoading.value = true
  try {
    const params = { page_size: 100 }
    Object.entries(requestFilters).forEach(([key, value]) => {
      if (value) params[key] = value
    })
    resourceRequests.value = listOf(await getResourceRequests(params))
  } finally {
    requestLoading.value = false
  }
}

async function fetchRequestDetailAuditLogs(row = requestDetailRow.value) {
  if (!canViewAudit.value || !row?.id) {
    requestDetailAuditLogs.value = []
    return
  }
  requestDetailLoading.value = true
  try {
    requestDetailAuditLogs.value = listOf(await getChangeLogs({
      source: 'resource_request',
      request_id: row.id,
      page_size: 20,
    }))
  } finally {
    requestDetailLoading.value = false
  }
}

async function openRequestDetail(row) {
  requestDetailRow.value = row
  requestDetailVisible.value = true
  await fetchRequestDetailAuditLogs(row)
}

async function refreshOpenRequestDetail(id) {
  if (!requestDetailVisible.value || !requestDetailRow.value || requestDetailRow.value.id !== id) return
  const fresh = resourceRequests.value.find(item => item.id === id)
  if (fresh) requestDetailRow.value = fresh
  await fetchRequestDetailAuditLogs(requestDetailRow.value)
}

async function fetchGovernance(options = {}) {
  const { useCache = false, force = false } = options
  if (!canViewCi.value) return
  if (useCache && !force && hasFreshOverviewCache(overviewGovernanceCacheAt, OVERVIEW_CACHE_TTL.governance)) return
  if (overviewGovernanceRequest) return overviewGovernanceRequest
  syncFailureLoading.value = !!canViewSync.value
  overviewGovernanceRequest = (async () => {
    const results = await Promise.allSettled([
      getCompletionIssues({ status: 'open', page_size: 100 }, BACKGROUND_REQUEST_CONFIG),
      getCompletionIssues({ status: 'assigned', page_size: 100 }, BACKGROUND_REQUEST_CONFIG),
      getArchiveCandidates({ status: 'pending', page_size: 100 }, BACKGROUND_REQUEST_CONFIG),
      canViewSync.value ? getSyncRecords({ status: 'failed', page_size: 100 }, BACKGROUND_REQUEST_CONFIG) : Promise.resolve({ results: [] }),
      canViewSync.value ? getSyncRecords({ relation_issue: 1, page_size: 100 }, BACKGROUND_REQUEST_CONFIG) : Promise.resolve({ results: [] }),
    ])
    const responseRows = index => results[index]?.status === 'fulfilled' ? listOf(results[index].value) : []
    if (results[0]?.status === 'fulfilled' || results[1]?.status === 'fulfilled') {
      completionIssues.value = [...responseRows(0), ...responseRows(1)]
    }
    if (results[2]?.status === 'fulfilled') archiveCandidates.value = responseRows(2)
    if (results[3]?.status === 'fulfilled' || results[4]?.status === 'fulfilled') {
      const syncRows = [...responseRows(3), ...responseRows(4)]
      syncFailureRecords.value = Array.from(new Map(syncRows.map(item => [item.id, item])).values())
    }
    overviewGovernanceCacheAt = Date.now()
  })()
  try {
    return await overviewGovernanceRequest
  } finally {
    overviewGovernanceRequest = null
    syncFailureLoading.value = false
  }
}

let syncJobsRequest = null
let collectionSummaryRequest = null

async function fetchSyncJobs() {
  if (!canViewSync.value) return
  if (syncJobsRequest) return syncJobsRequest
  syncJobsLoading.value = true
  syncJobsRequest = getSyncJobs({ page_size: 100 }, BACKGROUND_REQUEST_CONFIG).then((response) => {
    syncJobs.value = listOf(response)
    return syncJobs.value
  })
  try {
    return await syncJobsRequest
  } finally {
    syncJobsRequest = null
    syncJobsLoading.value = false
  }
}

async function fetchCollectionSummary(force = false) {
  if (!canViewSync.value) return
  if (collectionSummaryLoaded.value && !force) return collectionSummary.value
  if (collectionSummaryRequest) return collectionSummaryRequest
  collectionSummaryLoading.value = true
  collectionSummaryRequest = getCmdbCollectionSummary(BACKGROUND_REQUEST_CONFIG).then((response) => {
    collectionSummary.value = response || { summary: {}, sources: [], jobs: [] }
    collectionSummaryLoaded.value = true
    return collectionSummary.value
  })
  try {
    return await collectionSummaryRequest
  } finally {
    collectionSummaryRequest = null
    collectionSummaryLoading.value = false
  }
}

function currentSourceMappingParams() {
  const params = { page_size: 200 }
  if (sourceMappingFilters.search) params.search = sourceMappingFilters.search
  if (sourceMappingFilters.source_type) params.source_type = sourceMappingFilters.source_type
  if (sourceMappingFilters.sync_status) params.sync_status = sourceMappingFilters.sync_status
  return params
}

async function fetchSourceMappings() {
  if (!canViewSync.value) return
  sourceMappingLoading.value = true
  try {
    sourceMappings.value = listOf(await getSourceMappings(currentSourceMappingParams()))
  } finally {
    sourceMappingLoading.value = false
  }
}

async function fetchCiSourceAccountRegionOptions() {
  if (!canViewCi.value) return
  ciSourceAccountRegionOptions.value = listOf(await getSourceAccountRegionOptions())
}

async function fetchResourceAuthorizations() {
  if (!canViewAuthorization.value) return
  authorizationLoading.value = true
  try {
    resourceAuthorizations.value = listOf(await getResourceAuthorizations({ page_size: 200 }))
  } finally {
    authorizationLoading.value = false
  }
}

function refreshSyncCenterBackground(force = false) {
  if (!canViewSync.value || syncCenterBackgroundLoading.value) return
  syncCenterBackgroundLoading.value = true
  setTimeout(() => {
    Promise.allSettled([
      ciTypes.value.length ? Promise.resolve() : fetchTypesAndFields(),
      fetchCollectionSummary(force),
    ]).finally(() => {
      syncCenterBackgroundLoading.value = false
    })
  }, 80)
}

async function fetchSyncCenterData(options = {}) {
  const { force = false } = options
  if (!canViewSync.value) return
  if (force) collectionSummaryLoaded.value = false
  await Promise.allSettled([
    fetchCloudCredentials(force),
    fetchSyncJobs(),
  ])
  refreshSyncCenterBackground(force)
}

async function fetchOverviewData(options = {}) {
  const { force = false } = options
  await Promise.allSettled([
    fetchDashboard({ useCache: true, force }),
    fetchOverviewServerItems({ force }),
    fetchGovernance({ useCache: true, force }),
    fetchCloudCredentials(force),
    fetchOverviewCostSummary({ force }),
  ])
}

async function fetchActiveTabData(options = {}) {
  const { force = false } = options || {}
  if (activeTab.value === 'overview') {
    await fetchOverviewData({ force })
    return
  }
  if (activeTab.value === 'repository') {
    await Promise.allSettled([fetchDashboard(), fetchRepositorySummary()])
    return
  }
  if (activeTab.value === 'views') {
    await Promise.allSettled([fetchDashboard(), fetchViewsSummary()])
    return
  }
  if (activeTab.value === 'tags') {
    await Promise.allSettled([fetchDashboard(), fetchTags()])
    return
  }
  if (activeTab.value === 'ledger') {
    await Promise.allSettled([fetchDashboard(), fetchTypesAndFields(), fetchTags(), fetchResourceNodeTree(), fetchLedger()])
    return
  }
  if (activeTab.value === 'requests') {
    await Promise.allSettled([fetchDashboard(), fetchResourceNodeTree(), fetchRequests()])
    return
  }
  if (activeTab.value === 'governance') {
    await Promise.allSettled([fetchGovernanceRisks({ force }), fetchGovernance(), fetchResourceNodeTree()])
    fetchLedgerTree().catch(() => {})
    return
  }
  if (activeTab.value === 'authorization') {
    await Promise.allSettled([fetchTypesAndFields(), fetchResourceAuthorizations()])
    return
  }
  if (activeTab.value === 'sync') {
    await fetchSyncCenterData({ force })
    return
  }
  if (activeTab.value === 'sourceMappings') {
    await Promise.allSettled([fetchDashboard(), fetchSourceMappings()])
    return
  }
  if (activeTab.value === 'thresholds') {
    await Promise.allSettled([fetchDashboard(), fetchTypesAndFields(), fetchThresholdManagement()])
    return
  }
  if (activeTab.value === 'audit') {
    await fetchAuditLogs()
    return
  }
  if (activeTab.value === 'model') {
    await Promise.allSettled([fetchDashboard(), fetchTypesAndFields(), fetchResourceNodeTree(), fetchModelCatalogTree()])
    const detailTasks = []
    if (isModelTopologyRoute.value) detailTasks.push(fetchTopology())
    if (isModelDetailRoute.value) detailTasks.push(syncModelDetailSelection())
    if (detailTasks.length) await Promise.allSettled(detailTasks)
  }
}

async function reloadAll() {
  loading.value = true
  try {
    await fetchActiveTabData({ force: true })
  } finally {
    loading.value = false
  }
}

function resetLedgerFilters() {
  ledgerFilters.search = ''
  ledgerFilters.asset_search = ''
  ledgerFilters.attribute_search = ''
  ledgerFilters.ci_type = ''
  ledgerFilters.resource_node = ''
  ledgerFilters.business_node = ''
  ledgerFilters.business_line = ''
  ledgerFilters.service_type = ''
  ledgerFilters.provider = ''
  ledgerFilters.expiry_risk = ''
  ledgerFilters.source_account = ''
  ledgerFilters.source_account_missing = ''
  ledgerFilters.source_region = ''
  ledgerFilters.source_unique_id = ''
  ledgerFilters.vsphere_cluster = ''
  ledgerFilters.vsphere_host = ''
  ledgerFilters.availability_zone = ''
  ledgerFilters.engine = ''
  ledgerFilters.vpc_id = ''
  ledgerFilters.network_type = ''
  ledgerFilters.storage_class = ''
  ledgerFilters.acl = ''
  ledgerFilters.sync_status = ''
  ledgerFilters.idc = ''
  ledgerFilters.rack = ''
  ledgerFilters.lifecycle_status = ''
  ledgerFilters.environment_node = ''
  ledgerFilters.environment = ''
  ledgerFilters.status = ''
  ledgerFilters.tags = ''
  ledgerFilters.source_type = ''
  ledgerFilters.ownership = ''
  ledgerFilters.admin_user = ''
  ledgerFilters.department = ''
  ledgerFilters.system = ''
  ledgerTreeContext.value = null
  ledgerSummaryContext.value = null
  ledgerAuthorizationContext.value = null
  ledgerViewContext.value = null
}

function clearLedgerFilters() {
  resetLedgerFilters()
  fetchLedger()
}

function resetModelResourceFilters() {
  modelResourceFilters.search = ''
  modelResourceFilters.asset_search = ''
  modelResourceFilters.attribute_search = ''
  modelResourceFilters.ci_type = selectedModelId.value || ''
  modelResourceFilters.service_type = ''
  modelResourceFilters.provider = ''
  modelResourceFilters.expiry_risk = ''
  modelResourceFilters.source_account = ''
  modelResourceFilters.source_account_missing = ''
  modelResourceFilters.source_region = ''
  modelResourceFilters.source_unique_id = ''
  modelResourceFilters.vsphere_cluster = ''
  modelResourceFilters.vsphere_host = ''
  modelResourceFilters.availability_zone = ''
  modelResourceFilters.engine = ''
  modelResourceFilters.vpc_id = ''
  modelResourceFilters.network_type = ''
  modelResourceFilters.storage_class = ''
  modelResourceFilters.acl = ''
  modelResourceFilters.sync_status = ''
  modelResourceFilters.idc = ''
  modelResourceFilters.rack = ''
  modelResourceFilters.lifecycle_status = ''
  modelResourceFilters.status = ''
  modelResourceFilters.tags = ''
  modelResourceFilters.source_type = ''
  modelResourceFilters.ownership = ''
}

function handleModelResourceFilterChange() {
  fetchModelResources(selectedModelId.value)
}

function clearModelResourceFilters() {
  resetModelResourceFilters()
  fetchModelResources(selectedModelId.value)
}

function normalizeEnvironmentValue(value) {
  const normalized = String(value || '').trim().toLowerCase()
  const aliases = {
    '开发': 'dev',
    'development': 'dev',
    '生产': 'prod',
    'production': 'prod',
    '测试': 'test',
    'testing': 'test',
    '联调': 'uat',
    '集成': 'integration',
  }
  return aliases[normalized] || normalized
}

function ciDetailEnvironmentName(row = {}) {
  const environmentNodeName = String(row.environment_node_name || '').trim()
  if (environmentNodeName) return environmentText(environmentNodeName)
  const businessLine = String(row.business_line || row.business_node_name || '').trim()
  const rawEnvironment = String(row.environment || '').trim()
  if (!businessLine && !rawEnvironment) return '-'
  if (!businessLine && normalizeEnvironmentValue(rawEnvironment) === 'prod') return '-'
  return environmentText(normalizeEnvironmentValue(rawEnvironment || row.environment_display))
}

function clearLedgerTreeContext() {
  ledgerTreeContext.value = null
}

function switchGovernanceTreeMode(mode) {
  if (!['cloud', 'business'].includes(mode) || ledgerViewMode.value === mode) return
  ledgerViewMode.value = mode
  ledgerTreeKeyword.value = ''
  governanceTreeContext.value = null
  expandedLedgerTreeKeys.value = new Set()
  collapsedLedgerTreeKeys.value = new Set()
  archiveSelection.value = []
}

function selectGovernanceTreeScope(entry = null) {
  if (!entry || entry.scope === 'all') {
    governanceTreeContext.value = null
    archiveSelection.value = []
    return
  }
  expandLedgerTreePath(entry)
  governanceTreeContext.value = {
    ...entry,
    view_mode: isBusinessLedgerView.value ? 'business' : 'cloud',
    children: undefined,
  }
  archiveSelection.value = []
}

function isGovernanceTreeNodeActive(entry) {
  return Boolean(governanceTreeContext.value?.key && entry?.key && String(governanceTreeContext.value.key) === String(entry.key))
}

function openLedgerFromGovernanceTree() {
  const context = governanceTreeContext.value
  if (!context) return
  ledgerViewMode.value = context.view_mode === 'business' ? 'business' : 'cloud'
  selectLedgerScope(context)
  switchTab('ledger')
}

function switchLedgerViewMode(mode) {
  if (!['cloud', 'business'].includes(mode) || ledgerViewMode.value === mode) return
  ledgerViewMode.value = mode
  ledgerTreeKeyword.value = ''
  expandedLedgerTreeKeys.value = new Set()
  collapsedLedgerTreeKeys.value = new Set()
  resetLedgerFilters()
  fetchLedger()
}

function toggleLedgerTreeNode(entry) {
  if (!entry?.key || !entry.has_children) return
  const expanded = new Set(expandedLedgerTreeKeys.value)
  const collapsed = new Set(collapsedLedgerTreeKeys.value)
  if (entry.is_expanded) {
    collapsed.add(entry.key)
    expanded.delete(entry.key)
  } else {
    expanded.add(entry.key)
    collapsed.delete(entry.key)
  }
  expandedLedgerTreeKeys.value = expanded
  collapsedLedgerTreeKeys.value = collapsed
}

function expandLedgerTreePath(entry) {
  const keys = Array.isArray(entry?.pathKeys) ? entry.pathKeys.slice(0, -1) : []
  if (!keys.length) return
  const expanded = new Set(expandedLedgerTreeKeys.value)
  const collapsed = new Set(collapsedLedgerTreeKeys.value)
  keys.forEach((key) => {
    expanded.add(key)
    collapsed.delete(key)
  })
  expandedLedgerTreeKeys.value = expanded
  collapsedLedgerTreeKeys.value = collapsed
}

function resourceTreeContextFromNode(node, parent = null) {
  const businessLine = String(parent?.name || node?.business_line || node?.name || '').trim()
  const environment = parent?.name ? normalizeEnvironmentValue(node?.name) : ''
  return {
    node_id: node?.id || '',
    parent_id: parent?.id || '',
    node_type: parent?.name ? 'env' : 'biz',
    business_line: businessLine,
    business_node: parent?.id || node?.id || '',
    environment,
    environment_node: parent?.id ? node?.id || '' : '',
  }
}

function selectLedgerAccountScope(entry = null) {
  if (!entry || entry.scope === 'all') {
    ledgerTreeContext.value = null
    resetLedgerFilters()
    fetchLedger()
    return
  }
  expandLedgerTreePath(entry)
  resetLedgerFilters()
  ledgerTreeContext.value = {
    scope: entry.level || 'account',
    source_account: entry.source_account || '',
    source_account_missing: entry.source_account_missing || '',
    source_region: entry.source_region || '',
    source_unique_id: entry.source_unique_id || '',
    vsphere_cluster: entry.vsphere_cluster || '',
    vsphere_host: entry.vsphere_host || '',
    provider: entry.provider || '',
    label: entry.label || '',
    key: entry.key || '',
    node_id: entry.resource_node_id || '',
    parent_id: entry.resource_node_parent_id || '',
  }
  ledgerFilters.resource_node = entry.resource_node_id || ''
  ledgerFilters.source_account = entry.resource_node_id ? '' : (entry.source_account || '')
  ledgerFilters.source_account_missing = entry.resource_node_id ? '' : (entry.source_account_missing || '')
  ledgerFilters.source_region = entry.resource_node_id ? '' : (entry.source_region || '')
  ledgerFilters.source_unique_id = entry.resource_node_id ? '' : (entry.source_unique_id || '')
  ledgerFilters.vsphere_cluster = entry.resource_node_id ? '' : (entry.vsphere_cluster || '')
  ledgerFilters.vsphere_host = entry.resource_node_id ? '' : (entry.vsphere_host || '')
  fetchLedger()
}

function isLedgerAccountNodeActive(entry) {
  const context = ledgerTreeContext.value
  if (!context) return false
  if (context.key && entry.key) return String(context.key) === String(entry.key)
  return String(context.scope || '') === String(entry.level || '')
    && String(context.source_account || '') === String(entry.source_account || '')
    && String(context.source_account_missing || '') === String(entry.source_account_missing || '')
    && String(context.source_region || '') === String(entry.source_region || '')
    && String(context.source_unique_id || '') === String(entry.source_unique_id || '')
    && String(context.vsphere_cluster || '') === String(entry.vsphere_cluster || '')
    && String(context.vsphere_host || '') === String(entry.vsphere_host || '')
}

function selectLedgerBusinessScope(entry = null) {
  if (!entry || entry.scope === 'all') {
    ledgerTreeContext.value = null
    resetLedgerFilters()
    fetchLedger()
    return
  }
  expandLedgerTreePath(entry)
  resetLedgerFilters()
  ledgerTreeContext.value = {
    scope: entry.level || 'business',
    view_mode: 'business',
    business_line: entry.business_line || '',
    business_node: entry.business_node || '',
    environment: entry.environment || '',
    environment_node: entry.environment_node || '',
    system: entry.system || '',
    label: entry.label || '',
    key: entry.key || '',
  }
  ledgerFilters.business_line = entry.business_line || ''
  ledgerFilters.business_node = entry.business_node || ''
  ledgerFilters.environment = entry.environment || ''
  ledgerFilters.environment_node = entry.environment_node || ''
  ledgerFilters.system = entry.system || ''
  fetchLedger()
}

function selectLedgerScope(entry = null) {
  if (isBusinessLedgerView.value) {
    selectLedgerBusinessScope(entry)
    return
  }
  selectLedgerAccountScope(entry)
}

function isLedgerBusinessNodeActive(entry) {
  const context = ledgerTreeContext.value
  if (!context) return false
  if (context.key && entry.key) return String(context.key) === String(entry.key)
  return (context.view_mode === 'business' || ['business', 'environment', 'system'].includes(context.scope))
    && String(context.scope || '') === String(entry.level || '')
    && String(context.business_node || '') === String(entry.business_node || '')
    && String(context.business_line || '') === String(entry.business_line || '')
    && String(context.environment_node || '') === String(entry.environment_node || '')
    && String(context.environment || '') === String(entry.environment || '')
    && String(context.system || '') === String(entry.system || '')
}

function isLedgerTreeNodeActive(entry) {
  return isBusinessLedgerView.value ? isLedgerBusinessNodeActive(entry) : isLedgerAccountNodeActive(entry)
}

function switchModelCatalogTreeMode(mode) {
  if (!['cloud', 'business'].includes(mode) || modelCatalogTreeMode.value === mode) return
  modelCatalogTreeMode.value = mode
  modelCatalogTreeKeyword.value = ''
  modelCatalogTreeContext.value = null
  expandedModelCatalogTreeKeys.value = new Set()
  collapsedModelCatalogTreeKeys.value = new Set()
  if (isModelDetailRoute.value && selectedModelId.value) fetchModelResources()
}

function toggleModelCatalogTreeNode(entry) {
  if (!entry?.key || !entry.has_children) return
  const expanded = new Set(expandedModelCatalogTreeKeys.value)
  const collapsed = new Set(collapsedModelCatalogTreeKeys.value)
  if (entry.is_expanded) {
    collapsed.add(entry.key)
    expanded.delete(entry.key)
  } else {
    expanded.add(entry.key)
    collapsed.delete(entry.key)
  }
  expandedModelCatalogTreeKeys.value = expanded
  collapsedModelCatalogTreeKeys.value = collapsed
}

function expandModelCatalogTreePath(entry) {
  const keys = Array.isArray(entry?.pathKeys) ? entry.pathKeys.slice(0, -1) : []
  if (!keys.length) return
  const expanded = new Set(expandedModelCatalogTreeKeys.value)
  const collapsed = new Set(collapsedModelCatalogTreeKeys.value)
  keys.forEach((key) => {
    expanded.add(key)
    collapsed.delete(key)
  })
  expandedModelCatalogTreeKeys.value = expanded
  collapsedModelCatalogTreeKeys.value = collapsed
}

function selectModelCatalogTreeScope(entry = null) {
  if (!entry || entry.scope === 'all') {
    modelCatalogTreeContext.value = null
    if (isModelDetailRoute.value && selectedModelId.value) fetchModelResources()
    return
  }
  expandModelCatalogTreePath(entry)
  if (isBusinessModelCatalogTreeView.value) {
    modelCatalogTreeContext.value = {
      scope: entry.level || 'business',
      view_mode: 'business',
      business_line: entry.business_line || '',
      business_node: entry.business_node || '',
      environment: entry.environment || '',
      environment_node: entry.environment_node || '',
      system: entry.system || '',
      label: entry.label || '',
      key: entry.key || '',
    }
    if (isModelDetailRoute.value && selectedModelId.value) fetchModelResources()
    return
  }
  modelCatalogTreeContext.value = {
    scope: entry.level || 'account',
    resource_node: entry.resource_node_id || '',
    source_account: entry.source_account || '',
    source_account_missing: entry.source_account_missing || '',
    source_region: entry.source_region || '',
    source_unique_id: entry.source_unique_id || '',
    vsphere_cluster: entry.vsphere_cluster || '',
    vsphere_host: entry.vsphere_host || '',
    provider: entry.provider || '',
    label: entry.label || '',
    key: entry.key || '',
  }
  if (isModelDetailRoute.value && selectedModelId.value) fetchModelResources()
}

function modelCatalogContextParams() {
  const context = modelCatalogTreeContext.value
  if (!context) return {}
  if (context.view_mode === 'business') {
    const params = {
      ...(context.business_line ? { business_line: context.business_line } : {}),
      ...(context.business_node ? { business_node: context.business_node } : {}),
      ...(context.environment ? { environment: context.environment } : {}),
      ...(context.environment_node ? { environment_node: context.environment_node } : {}),
      ...(context.system ? { system: context.system } : {}),
    }
    if (params.business_node) delete params.business_line
    if (params.environment_node) delete params.environment
    return params
  }
  if (context.resource_node) {
    return { resource_node: context.resource_node }
  }
  return {
    ...(context.source_account ? { source_account: context.source_account } : {}),
    ...(context.source_account_missing ? { source_account_missing: context.source_account_missing } : {}),
    ...(context.source_region ? { source_region: context.source_region } : {}),
    ...(context.source_unique_id ? { source_unique_id: context.source_unique_id } : {}),
    ...(context.vsphere_cluster ? { vsphere_cluster: context.vsphere_cluster } : {}),
    ...(context.vsphere_host ? { vsphere_host: context.vsphere_host } : {}),
  }
}

function isModelCatalogTreeNodeActive(entry) {
  const context = modelCatalogTreeContext.value
  if (!context) return false
  if (context.key && entry.key) return String(context.key) === String(entry.key)
  if (isBusinessModelCatalogTreeView.value) {
    return String(context.scope || '') === String(entry.level || '')
      && String(context.business_line || '') === String(entry.business_line || '')
      && String(context.environment || '') === String(entry.environment || '')
      && String(context.system || '') === String(entry.system || '')
  }
  return String(context.scope || '') === String(entry.level || '')
    && String(context.source_account || '') === String(entry.source_account || '')
    && String(context.source_account_missing || '') === String(entry.source_account_missing || '')
    && String(context.source_region || '') === String(entry.source_region || '')
    && String(context.source_unique_id || '') === String(entry.source_unique_id || '')
    && String(context.vsphere_cluster || '') === String(entry.vsphere_cluster || '')
    && String(context.vsphere_host || '') === String(entry.vsphere_host || '')
}

const modelCatalogTreeContextText = computed(() => {
  const context = modelCatalogTreeContext.value
  if (!context) return ''
  if (context.view_mode === 'business') {
    return [
      context.business_line || context.label,
      context.environment ? environmentText(context.environment) : '',
      context.system,
    ].filter(Boolean).join(' / ') || context.label || '业务环境'
  }
  const accountText = context.source_account_missing ? (context.label || '未关联账号') : (context.source_account || context.label)
  return [
    accountText,
    context.source_region,
    context.vsphere_cluster,
    context.vsphere_host,
  ].filter(Boolean).join(' / ') || context.label || '云账号'
})

function modelCatalogResourceMatchesContext(row) {
  const context = modelCatalogTreeContext.value
  if (!context) return true
  if (context.view_mode === 'business') {
    if (context.business_node && String(row?.business_node || '') !== String(context.business_node)) return false
    if (!context.business_node && context.business_line && ledgerBusinessLineFilter(row) !== context.business_line) return false
    if (context.environment_node && String(row?.environment_node || '') !== String(context.environment_node)) return false
    if (!context.environment_node && context.environment && ledgerEnvironmentText(row) !== context.environment) return false
    if (context.system && ledgerSystemText(row) !== context.system) return false
    return true
  }
  if (context.resource_node) {
    return modelCatalogResourceNodeMatchesContext(row, context.resource_node)
  }
  const accountText = ledgerTreeAccountText(row)
  const sourceAccountMissing = accountText.includes('未关联账号') ? '1' : ''
  if (context.source_account_missing && sourceAccountMissing !== context.source_account_missing) return false
  if (context.source_account && accountText !== context.source_account) return false
  if (context.source_region && ledgerTreeRegionText(row) !== context.source_region) return false
  if (context.source_unique_id && ledgerTreeField(row, ['source_unique_id', 'instance_id']) !== context.source_unique_id) return false
  if (context.vsphere_cluster) {
    const attrs = row?.attributes || {}
    if (cleanVsphereCluster(attrs.cluster || attrs.vsphere_cluster) !== context.vsphere_cluster) return false
  }
  if (context.vsphere_host) {
    const attrs = row?.attributes || {}
    if (ledgerTreeText(attrs.host || attrs.host_name || attrs.esxi_host) !== context.vsphere_host) return false
  }
  return true
}

function modelCatalogResourceNodeMatchesContext(row, resourceNodeId) {
  const selectedNodeId = String(resourceNodeId || '')
  let currentNodeId = linkedCloudResourceNodeId(row)
  if (!selectedNodeId || !currentNodeId) return false
  if (currentNodeId === selectedNodeId) return true

  const nodesById = new Map(cloudResourceNodeRows.value.map(node => [String(node.id), node]))
  while (currentNodeId) {
    const currentNode = nodesById.get(currentNodeId)
    const parentNodeId = String(currentNode?.parent_id || '')
    if (!parentNodeId) return false
    if (parentNodeId === selectedNodeId) return true
    currentNodeId = parentNodeId
  }
  return false
}

function resourceBelongsToModel(row, model) {
  const attrs = row?.attributes || {}
  const resourceKeys = [
    row?.ci_type,
    row?.ci_type_id,
    row?.ci_type_code,
    row?.ci_type_name,
    attrs.ci_type,
    attrs.ci_type_id,
    attrs.ci_type_code,
    attrs.ci_type_name,
  ].map(value => String(value || '').trim()).filter(Boolean)
  const modelKeys = [model?.id, model?.code, model?.name]
    .map(value => String(value || '').trim())
    .filter(Boolean)
  return modelKeys.some(key => resourceKeys.includes(key))
}

function modelCardResourceCount(model) {
  const scopedCount = modelCatalogScopedModelCounts.value.get(String(model?.id))
  if (typeof scopedCount === 'number' && (modelCatalogSourceRows.value.length || modelCatalogTreeContext.value)) return scopedCount
  return Number(model?.ci_count || 0)
}

function clearLedgerSummaryContext() {
  ledgerSummaryContext.value = null
}

function clearLedgerAuthorizationContext() {
  ledgerAuthorizationContext.value = null
}

function clearLedgerViewContext() {
  ledgerViewContext.value = null
}

function ciTypeFilterValue(row) {
  if (row?.ci_type) return row.ci_type
  if (row?.ci_type_id) return row.ci_type_id
  if (row?.model_id) return row.model_id
  const code = String(row?.ci_type_code || '').toUpperCase()
  const name = String(row?.ci_type_name || '')
  return ciTypes.value.find(item => String(item.code || '').toUpperCase() === code || item.name === name)?.id || ''
}

function ciNeedsOwnership(row) {
  if (!row) return false
  const department = row.department || row.attributes?.department
  return !String(row.business_line || '').trim()
    || !String(row.admin_user || '').trim()
    || !String(department || '').trim()
}

function applyLedgerDrilldown(context, filters = {}) {
  resetLedgerFilters()
  if (filters.business_line || filters.environment || filters.system) {
    ledgerViewMode.value = 'business'
  }
  ledgerViewContext.value = context
  Object.entries(filters).forEach(([key, value]) => {
    if (key in ledgerFilters) ledgerFilters[key] = value || ''
  })
  switchTab('ledger')
  fetchLedger()
}

function openLedgerByViewRow(row) {
  applyLedgerDrilldown({
    label: '应用视图',
    name: row.name,
    business_line: row.business_line || '',
    environment: row.environment || '',
    model: row.ci_type_name || row.ci_type_code || '',
  }, {
    search: row.name || row.ip || '',
    ci_type: ciTypeFilterValue(row),
    business_line: row.business_line || '',
    environment: row.environment || '',
    status: row.status || '',
  })
}

function openHostRemote(row) {
  const hostId = hostTerminalId(row)
  if (canUseHostTerminal.value && hostId) {
    router.push({ name: 'WebShell', params: { hostId } })
    return
  }
  if (!canUseHostTerminal.value) {
    ElMessage.info('暂无主机远程访问权限，已打开资源详情')
  } else {
    ElMessage.info('暂无可远程访问的主机资产映射，已打开资源详情')
  }
  openCiDetail(row)
}

function openLedgerByResourceNode(node, parent = null) {
  const context = resourceTreeContextFromNode(node, parent)
  resetLedgerFilters()
  ledgerViewMode.value = 'business'
  ledgerTreeContext.value = {
    ...context,
    scope: context.node_type === 'env' ? 'environment' : 'business',
    view_mode: 'business',
    label: context.environment ? environmentText(context.environment) : context.business_line,
    key: context.environment_node
      ? `environment:node:${context.environment_node}`
      : `business:node:${context.business_node}`,
  }
  ledgerFilters.business_node = context.business_node || ''
  ledgerFilters.environment_node = context.environment_node || ''
  ledgerFilters.business_line = context.business_line
  ledgerFilters.environment = context.environment
  switchTab('ledger')
  fetchLedger()
}

function openLedgerByAuthorization(row) {
  resetLedgerFilters()
  const scopeText = row.scope_display || authorizationScopeText(row)
  ledgerAuthorizationContext.value = {
    id: row.id,
    name: row.name,
    principal: row.principal,
    scope: scopeText,
  }
  ledgerFilters.ci_type = row.ci_type || ''
  ledgerFilters.business_line = row.business_line || ''
  ledgerFilters.system = row.business_line || ''
  ledgerFilters.environment = row.environment || ''
  switchTab('ledger')
  fetchLedger()
}

function clearAuditFilters() {
  auditFilters.search = ''
  auditFilters.action = ''
  auditFilters.operator = ''
  auditFilters.source = ''
  auditFilters.range = []
  fetchAuditLogs()
}

function clearThresholdFilters() {
  thresholdFilters.resource_type = ''
  thresholdFilters.metric = ''
  thresholdFilters.enabled = ''
  fetchThresholdManagement()
}

function resetApplicationViewFilters() {
  applicationViewKeyword.value = ''
  applicationViewRisk.value = ''
  applicationViewOwner.value = ''
  applicationViewTeam.value = ''
  applicationViewTier.value = ''
  viewFilters.business_line = ''
  viewFilters.environment = ''
  opsanyViewKeyword.value = ''
  selectedOpsanyViewNode.value = { mode: viewMode.value, key: 'all', scope: 'all' }
  fetchViewsSummary()
}

function normalizeRepositoryModelContext(row) {
  const issueCounts = row?.issue_counts || row?.quality_issue_counts || {}
  return {
    ...row,
    model_id: row?.model_id || row?.ci_type || row?.id || '',
    name: row?.name || row?.model_name || row?.ci_type_name || '',
    code: row?.code || row?.ci_type_code || '',
    group_name: row?.group_name || row?.group || '',
    completion_issue_count: row?.completion_issue_count ?? issueCounts.completion_issues ?? 0,
    archive_candidate_count: row?.archive_candidate_count ?? issueCounts.archive_candidates ?? 0,
    sync_failure_count: row?.sync_failure_count ?? issueCounts.sync_failures ?? 0,
  }
}

function clearGovernanceScopeContext() {
  governanceScopeContext.value = null
  completionSelection.value = []
  archiveSelection.value = []
}

function openGovernanceByRepositoryModel(row) {
  const context = normalizeRepositoryModelContext(row)
  governanceScopeContext.value = context
  completionSelection.value = []
  archiveSelection.value = []
  if (Number(context.archive_candidate_count || 0) > 0) {
    activeGovernanceKey.value = 'archive'
  } else if (Number(context.sync_failure_count || 0) > 0 && canViewSync.value) {
    activeGovernanceKey.value = 'sync'
  } else {
    activeGovernanceKey.value = 'archive'
  }
  governanceViewMode.value = 'detail'
  switchTab('governance')
  fetchGovernance()
}

function openGovernanceByQualityIssue(item) {
  governanceScopeContext.value = null
  completionSelection.value = []
  archiveSelection.value = []
  activeGovernanceKey.value = normalizeGovernanceKey(item.target)
  governanceViewMode.value = 'detail'
  switchTab('governance')
  fetchGovernance()
}

function openRepositoryModel(row) {
  const context = normalizeRepositoryModelContext(row)
  resetLedgerFilters()
  ledgerFilters.ci_type = context.model_id || ''
  ledgerViewContext.value = {
    label: '资源仓库',
    name: context.name,
    model: context.code || context.name,
  }
  switchTab('ledger')
  fetchLedger()
}

function currentLedgerParams() {
  const params = {}
  const allowedKeys = new Set([
    'asset_search',
    'attribute_search',
    'status',
    'tags',
    'source_type',
    'ownership',
    'ci_type',
    'resource_node',
    'source_account',
    'source_account_missing',
    'source_region',
    'source_unique_id',
    'vsphere_cluster',
    'vsphere_host',
    'business_node',
    'business_line',
    'environment_node',
    'environment',
    'system',
    'provider',
    'service_type',
    'expiry_risk',
  ])
  Object.entries(ledgerFilters).forEach(([key, value]) => {
    if (!allowedKeys.has(key)) return
    if (value) params[key] = value
  })
  if (params.environment_node) delete params.environment
  return params
}

function currentModelResourceParams(modelId = selectedModelId.value) {
  const params = {}
  const allowedKeys = new Set([
    'asset_search',
    'attribute_search',
    'status',
    'tags',
    'source_type',
    'ownership',
    'expiry_risk',
  ])
  Object.entries(modelResourceFilters).forEach(([key, value]) => {
    if (key === 'ci_type') return
    if (!allowedKeys.has(key)) return
    if (value) params[key] = value
  })
  params.ci_type = modelResourceFilters.ci_type || modelId
  return params
}

function currentLedgerTreeParams() {
  const params = { ...currentLedgerParams() }
  if (ledgerTreeContext.value) {
    delete params.source_account
    delete params.source_account_missing
    delete params.source_region
    delete params.source_unique_id
    delete params.vsphere_cluster
    delete params.vsphere_host
    delete params.business_line
    delete params.business_node
    delete params.environment
    delete params.environment_node
    delete params.system
  }
  return params
}

function clearTopologyFilters() {
  topologyFilters.ci_type = ''
  topologyFilters.business_line = ''
  topologyFilters.environment = ''
  topologyFilters.scope = 'neighbors'
  fetchTopology()
}

function clearRequestFilters() {
  requestFilters.status = ''
  requestFilters.business_line = ''
  requestFilters.search = ''
  fetchRequests()
}

function resourceNodeTypeText(type) {
  return resourceNodeTypeLabels[type] || type || '-'
}

function isRootResourceNodeType(type) {
  return ['biz', 'cloud_account'].includes(type)
}

function firstParentIdForResourceNodeType(type) {
  const parentTypes = childResourceNodeParentTypes[type] || []
  const rows = parentTypes.some(item => cloudResourceNodeTypes.has(item)) ? cloudResourceNodeRows.value : resourceNodeRows.value
  return rows.find(item => parentTypes.includes(item.node_type))?.id || ''
}

function resetResourceNodeForm(type = 'biz', parent = null) {
  resourceNodeEditingId.value = null
  resourceNodeVirtualParentEntry.value = null
  resourceNodeEditMode.value = 'full'
  Object.assign(resourceNodeForm, {
    name: '',
    node_type: type,
    parent: isRootResourceNodeType(type) ? '' : (parent?.id || firstParentIdForResourceNodeType(type)),
    sort_order: 0,
  })
}

function openResourceNodeDialog(type = 'biz', row = null, parent = null, options = {}) {
  if (row) {
    resourceNodeEditingId.value = row.id
    resourceNodeVirtualParentEntry.value = null
    resourceNodeEditMode.value = options.editMode || (cloudResourceNodeTypes.has(row.node_type) && row.is_synced ? 'sort' : 'full')
    Object.assign(resourceNodeForm, {
      name: row.name || '',
      node_type: row.node_type || type,
      parent: isRootResourceNodeType(row.node_type) ? '' : (row.parent_id || row.parent || ''),
      sort_order: Number(row.sort_order || 0),
    })
  } else {
    resetResourceNodeForm(type, parent)
    resourceNodeVirtualParentEntry.value = options.virtualParentEntry || null
    resourceNodeEditMode.value = options.editMode || 'full'
    if (resourceNodeVirtualParentEntry.value) {
      resourceNodeForm.parent = ''
    }
    if (options.name) {
      resourceNodeForm.name = options.name
    }
  }
  resourceNodeDialogVisible.value = true
}

function onResourceNodeTypeChange() {
  resourceNodeVirtualParentEntry.value = null
  resourceNodeEditMode.value = 'full'
  if (isRootResourceNodeType(resourceNodeForm.node_type)) {
    resourceNodeForm.parent = ''
  } else {
    resourceNodeForm.parent = firstParentIdForResourceNodeType(resourceNodeForm.node_type)
  }
}

function buildResourceNodePayload() {
  const name = resourceNodeForm.name.trim()
  if (!name) throw new Error('请填写节点名称')
  const parentRequired = Boolean(childResourceNodeParentTypes[resourceNodeForm.node_type])
  if (parentRequired && !resourceNodeForm.parent && !resourceNodeVirtualParentEntry.value) {
    throw new Error(`请选择${resourceNodeParentLabel.value}`)
  }
  return {
    name,
    node_type: resourceNodeForm.node_type,
    parent: parentRequired ? resourceNodeForm.parent : null,
    sort_order: Number(resourceNodeForm.sort_order || 0),
  }
}

const resourceNodeEditSortOnly = computed(() => resourceNodeEditMode.value === 'sort')
const resourceNodeDialogTitle = computed(() => {
  if (!resourceNodeEditingId.value) return '新建资源树节点'
  return resourceNodeEditSortOnly.value ? '编辑节点排序' : '编辑资源树节点'
})

function cloudEntryParentContext(entry) {
  if (!entry) return null
  if (entry.level === 'account') return null
  if (entry.level === 'region') {
    return {
      ...entry,
      key: `account:${entry.source_account || entry.label}`,
      label: entry.source_account || entry.label,
      level: 'account',
      source_region: '',
      vsphere_cluster: '',
      vsphere_host: '',
      resource_node_id: '',
      resource_node_type: '',
      resource_node_parent_id: '',
      path_label: entry.source_account || entry.label,
    }
  }
  if (entry.level === 'cluster') {
    return {
      ...entry,
      key: `region:${entry.source_account}:${entry.source_region}`,
      label: entry.source_region,
      level: 'region',
      vsphere_cluster: '',
      vsphere_host: '',
      resource_node_id: '',
      resource_node_type: '',
      resource_node_parent_id: '',
      path_label: [entry.source_account, entry.source_region].filter(Boolean).join(' / '),
    }
  }
  if (entry.level === 'host') {
    const parentLevel = entry.vsphere_cluster ? 'cluster' : 'region'
    return {
      ...entry,
      key: parentLevel === 'cluster'
        ? `cluster:${entry.source_account}:${entry.source_region}:${entry.vsphere_cluster}`
        : `region:${entry.source_account}:${entry.source_region}`,
      label: parentLevel === 'cluster' ? entry.vsphere_cluster : entry.source_region,
      level: parentLevel,
      vsphere_host: '',
      resource_node_id: '',
      resource_node_type: '',
      resource_node_parent_id: '',
      path_label: [entry.source_account, entry.source_region, parentLevel === 'cluster' ? entry.vsphere_cluster : ''].filter(Boolean).join(' / '),
    }
  }
  return null
}

function resourceNodeTypeFromLedgerEntry(entry) {
  const mapping = {
    business: 'biz',
    environment: 'env',
    account: 'cloud_account',
    region: 'cloud_region',
    cluster: 'cloud_cluster',
    host: 'cloud_host',
  }
  return mapping[entry?.level] || ''
}

function findManualCloudResourceNode(entry) {
  if (!entry) return null
  const nodeId = entry.resource_node_id
  if (nodeId) {
    const matched = cloudResourceNodeRows.value.find(row => String(row.id) === String(nodeId))
    if (matched) return matched
  }
  const nodeType = resourceNodeTypeFromLedgerEntry(entry)
  const rows = cloudResourceNodeRows.value.filter(row => row.node_type === nodeType)
  if (entry.level === 'account') return rows.find(row => row.name === entry.source_account || row.name === entry.label) || null
  if (entry.level === 'region') {
    return rows.find(row => (
      (row.name === entry.source_region || row.name === entry.label)
      && row.parent_name === entry.source_account
    )) || null
  }
  return rows.find(row => row.path_label === [entry.source_account, entry.source_region, entry.vsphere_cluster, entry.vsphere_host || entry.label].filter(Boolean).join(' / '))
    || rows.find(row => row.name === entry.label && row.parent_path === [entry.source_account, entry.source_region, entry.level === 'host' ? entry.vsphere_cluster : ''].filter(Boolean).join(' / '))
    || null
}

async function createResourceNodeWithDuplicateFallback(payload, entry = null) {
  try {
    return await createResourceNode(payload)
  } catch (error) {
    await fetchResourceNodeTree()
    const fallback = entry ? ledgerResourceNodeRowFromEntry(entry) : null
    if (fallback) return fallback
    throw error
  }
}

async function ensureBusinessResourceNodeForEntry(entry) {
  const existing = ledgerResourceNodeRowFromEntry(entry)
  if (existing) return existing
  const nodeType = resourceNodeTypeFromLedgerEntry(entry)
  if (!['biz', 'env'].includes(nodeType)) {
    throw new Error('当前业务环境节点类型不支持编辑')
  }
  if (nodeType === 'biz') {
    const name = ledgerTreeText(entry.business_line || entry.label)
    if (!name) throw new Error('当前业务线名称为空，无法编辑')
    return createResourceNodeWithDuplicateFallback({
      name,
      node_type: 'biz',
      parent: null,
      sort_order: 0,
    }, entry)
  }
  const parent = await ensureBusinessResourceNodeForEntry({
    ...entry,
    level: 'business',
    label: entry.business_line || entry.label,
    environment: '',
    resource_node_id: entry.resource_node_parent_id || '',
    resource_node_type: 'biz',
  })
  const name = ledgerTreeText(entry.label || environmentText(entry.environment) || entry.environment)
  if (!name || name === '-') throw new Error('当前环境名称为空，无法编辑')
  return createResourceNodeWithDuplicateFallback({
    name,
    node_type: 'env',
    parent: parent.id,
    sort_order: 0,
  }, entry)
}

async function ensureManualCloudResourceNodeForEntry(entry) {
  const existing = findManualCloudResourceNode(entry)
  if (existing) return existing
  const nodeType = resourceNodeTypeFromLedgerEntry(entry)
  if (!cloudResourceNodeTypes.has(nodeType)) {
    throw new Error('当前云账号节点类型不支持新增')
  }
  const parentEntry = cloudEntryParentContext(entry)
  const parent = parentEntry ? await ensureManualCloudResourceNodeForEntry(parentEntry) : null
  const payload = {
    name: entry.label || entry.source_account || entry.source_region || entry.vsphere_cluster || entry.vsphere_host,
    node_type: nodeType,
    parent: parent?.id || null,
    sort_order: 0,
    is_synced: true,
  }
  return createResourceNodeWithDuplicateFallback(payload, entry)
}

async function saveResourceNode() {
  let payload
  try {
    payload = buildResourceNodePayload()
  } catch (error) {
    return ElMessage.warning(error.message)
  }
  saving.value = true
  try {
    if (!payload.parent && resourceNodeVirtualParentEntry.value) {
      const parent = await ensureManualCloudResourceNodeForEntry(resourceNodeVirtualParentEntry.value)
      payload.parent = parent.id
    }
    if (resourceNodeEditingId.value) {
      await updateResourceNode(resourceNodeEditingId.value, payload)
      ElMessage.success('资源树节点已更新')
    } else {
      await createResourceNode(payload)
      ElMessage.success('资源树节点已创建')
    }
    resourceNodeDialogVisible.value = false
    await Promise.all([fetchResourceNodeTree(), fetchLedger(), fetchRequests(), fetchDashboard()])
  } finally {
    saving.value = false
  }
}

async function deleteResourceNodeRow(row) {
  await ElMessageBox.confirm(`确认删除「${row.name}」吗？已关联资源或申请时后端会阻止删除。`, '删除资源树节点', { type: 'warning' })
  await deleteResourceNode(row.id)
  ElMessage.success('资源树节点已删除')
  await Promise.all([fetchResourceNodeTree(), fetchLedger(), fetchRequests(), fetchDashboard()])
}

function ledgerResourceNodeRowFromEntry(entry) {
  if (!entry) return null
  if (['account', 'region', 'cluster', 'host'].includes(entry.level)) return findManualCloudResourceNode(entry)
  if (!['business', 'environment'].includes(entry.level)) return null
  const nodeId = entry.resource_node_id
  if (nodeId) {
    const matched = resourceNodeRows.value.find(row => String(row.id) === String(nodeId))
    if (matched) return matched
  }
  if (entry.level === 'business') {
    return resourceNodeTree.value.find(row => row.name === entry.business_line || row.name === entry.label) || null
  }
  const business = resourceNodeTree.value.find(row => row.name === entry.business_line)
  const environment = normalizeEnvironmentValue(entry.environment || entry.label)
  return (business?.children || []).find(row => normalizeEnvironmentValue(row.name) === environment) || null
}

function isSyncedCloudLedgerResourceNode(entry) {
  const row = ledgerResourceNodeRowFromEntry(entry)
  const nodeType = row?.node_type || resourceNodeTypeFromLedgerEntry(entry)
  if (!cloudResourceNodeTypes.has(nodeType)) return false
  if (row) return row.is_synced !== false
  if (entry?.resource_node_id) return entry.is_synced !== false
  return true
}

function canEditLedgerResourceNode(entry) {
  if (!canManageCi.value) return false
  if (cloudResourceNodeTypes.has(resourceNodeTypeFromLedgerEntry(entry))) return true
  if (['business', 'environment'].includes(entry?.level)) return true
  return Boolean(ledgerResourceNodeRowFromEntry(entry))
}

function canDeleteLedgerResourceNode(entry) {
  if (!canManageCi.value) return false
  const row = ledgerResourceNodeRowFromEntry(entry)
  if (!row) return false
  if (cloudResourceNodeTypes.has(row.node_type)) return !isSyncedCloudLedgerResourceNode(entry)
  return true
}

function ledgerResourceNodeEditTooltip(entry) {
  if (isSyncedCloudLedgerResourceNode(entry)) return '编辑排序'
  return '编辑节点'
}

function ledgerNodeCreateChildType(entry) {
  if (isBusinessLedgerView.value && entry?.level === 'business') return 'env'
  if (!isBusinessLedgerView.value) {
    if (entry?.level === 'account') return 'cloud_region'
    if (entry?.level === 'region') return 'cloud_cluster'
    if (entry?.level === 'cluster') return 'cloud_host'
  }
  return ''
}

function canAddLedgerResourceNodeChild(entry) {
  if (!canManageCi.value) return false
  if (isBusinessLedgerView.value && entry?.level === 'business') {
    return Boolean(ledgerResourceNodeRowFromEntry(entry))
  }
  return Boolean(ledgerNodeCreateChildType(entry))
}

function ledgerNodeCreateChildTooltip(entry) {
  const type = ledgerNodeCreateChildType(entry)
  return type ? `新增${resourceNodeTypeText(type)}` : '新增子节点'
}

function hasLedgerResourceNodeActions(entry) {
  return canAddLedgerResourceNodeChild(entry) || canEditLedgerResourceNode(entry) || canDeleteLedgerResourceNode(entry)
}

function currentLedgerBusinessNode() {
  const context = ledgerTreeContext.value
  if (context?.view_mode === 'business') {
    const fromId = context.node_id
      ? resourceNodeTree.value.find(row => String(row.id) === String(context.node_id))
      : null
    if (fromId) return fromId
    const businessName = context.business_line || context.label
    const fromName = resourceNodeTree.value.find(row => row.name === businessName)
    if (fromName) return fromName
  }
  return resourceNodeTree.value[0] || null
}

function openLedgerResourceNodeCreateDialog(type = 'biz', entry = null) {
  if (type === 'biz') {
    openResourceNodeDialog('biz')
    return
  }
  if (type === 'cloud_account') {
    openResourceNodeDialog('cloud_account')
    return
  }
  const parent = entry?.level === 'business'
    ? ledgerResourceNodeRowFromEntry(entry)
    : (isBusinessLedgerView.value ? currentLedgerBusinessNode() : ledgerResourceNodeRowFromEntry(entry))
  if (!isBusinessLedgerView.value && entry && !parent) {
    openResourceNodeDialog(type, null, null, { virtualParentEntry: entry })
    return
  }
  if (!parent) {
    return ElMessage.warning(isBusinessLedgerView.value ? '请先新增业务线，再新增环境' : '请先新增上级云账号节点')
  }
  openResourceNodeDialog(type, null, parent)
}

async function openLedgerResourceNodeEditDialog(entry) {
  let row = ledgerResourceNodeRowFromEntry(entry)
  if (!row && ['business', 'environment'].includes(entry?.level)) {
    try {
      row = await ensureBusinessResourceNodeForEntry(entry)
      await fetchResourceNodeTree()
      row = ledgerResourceNodeRowFromEntry(entry) || row
    } catch (error) {
      return ElMessage.warning(error.message || '业务环境节点记录创建失败')
    }
  }
  if (!row && cloudResourceNodeTypes.has(resourceNodeTypeFromLedgerEntry(entry))) {
    try {
      row = await ensureManualCloudResourceNodeForEntry(entry)
      await fetchResourceNodeTree()
      row = ledgerResourceNodeRowFromEntry(entry) || row
    } catch (error) {
      return ElMessage.warning(error.message || '同步节点排序记录创建失败')
    }
  }
  if (!row) return ElMessage.warning('当前节点来自资产数据，请先在资源树中创建对应节点')
  const parentRows = cloudResourceNodeTypes.has(row.node_type) ? cloudResourceNodeRows.value : resourceNodeRows.value
  const parent = isRootResourceNodeType(row.node_type)
    ? null
    : parentRows.find(item => String(item.id) === String(row.parent_id || row.parent))
  openResourceNodeDialog(row.node_type || 'biz', row, parent, {
    editMode: isSyncedCloudLedgerResourceNode(entry) ? 'sort' : 'full',
  })
}

async function deleteLedgerResourceNode(entry) {
  const row = ledgerResourceNodeRowFromEntry(entry)
  if (!row) return ElMessage.warning('当前节点来自资产数据，不能直接删除')
  if (String(ledgerTreeContext.value?.node_id || '') === String(row.id)) {
    ledgerTreeContext.value = null
  }
  await deleteResourceNodeRow(row)
}

function resetThresholdPolicyForm() {
  thresholdPolicyEditingId.value = null
  Object.assign(thresholdPolicyForm, {
    resource_type: thresholdFilters.resource_type || '',
    metric: thresholdFilters.metric || 'cpu_usage',
    normal_threshold: 70,
    warning_threshold: 85,
    critical_threshold: 95,
    exceeded_threshold: 100,
    enabled: true,
  })
}

function openThresholdPolicyDialog(row = null) {
  if (row) {
    thresholdPolicyEditingId.value = row.id
    Object.assign(thresholdPolicyForm, {
      resource_type: row.resource_type || '',
      metric: row.metric || 'cpu_usage',
      normal_threshold: Number(row.normal_threshold ?? 70),
      warning_threshold: Number(row.warning_threshold ?? 85),
      critical_threshold: Number(row.critical_threshold ?? 95),
      exceeded_threshold: Number(row.exceeded_threshold ?? 100),
      enabled: row.enabled !== false,
    })
  } else {
    resetThresholdPolicyForm()
  }
  thresholdPolicyDialogVisible.value = true
}

function buildThresholdPolicyPayload() {
  const metric = thresholdPolicyForm.metric.trim()
  if (!metric) throw new Error('请填写指标名称')
  const normal = Number(thresholdPolicyForm.normal_threshold)
  const warning = Number(thresholdPolicyForm.warning_threshold)
  const critical = Number(thresholdPolicyForm.critical_threshold)
  const exceeded = Number(thresholdPolicyForm.exceeded_threshold)
  if (![normal, warning, critical, exceeded].every(Number.isFinite)) throw new Error('请填写有效阈值')
  if (!(normal <= warning && warning <= critical && critical <= exceeded)) {
    throw new Error('阈值必须满足：正常 <= 预警 <= 紧张 <= 超限')
  }
  return {
    resource_type: thresholdPolicyForm.resource_type || null,
    metric,
    normal_threshold: normal,
    warning_threshold: warning,
    critical_threshold: critical,
    exceeded_threshold: exceeded,
    enabled: thresholdPolicyForm.enabled,
  }
}

async function saveThresholdPolicy() {
  let payload
  try {
    payload = buildThresholdPolicyPayload()
  } catch (error) {
    return ElMessage.warning(error.message)
  }
  saving.value = true
  try {
    if (thresholdPolicyEditingId.value) {
      await updateThresholdPolicy(thresholdPolicyEditingId.value, payload)
      ElMessage.success('水位策略已更新')
    } else {
      await createThresholdPolicy(payload)
      ElMessage.success('水位策略已创建')
    }
    thresholdPolicyDialogVisible.value = false
    await Promise.all([fetchThresholdManagement(), fetchDashboard()])
  } finally {
    saving.value = false
  }
}

async function toggleThresholdPolicy(row) {
  await updateThresholdPolicy(row.id, { enabled: !row.enabled })
  ElMessage.success(row.enabled ? '水位策略已停用' : '水位策略已启用')
  await Promise.all([fetchThresholdPolicies(), fetchDashboard()])
}

async function deleteThresholdPolicyRow(row) {
  await ElMessageBox.confirm(`确认删除「${row.resource_type_name || '全局'} / ${metricLabel(row.metric)}」水位策略吗？`, '删除水位策略', { type: 'warning' })
  await deleteThresholdPolicy(row.id)
  ElMessage.success('水位策略已删除')
  await Promise.all([fetchThresholdManagement(), fetchDashboard()])
}

function resetMetricForm() {
  metricEditingId.value = null
  Object.assign(metricForm, {
    ci: ledgerItems.value[0]?.id || '',
    metric: thresholdFilters.metric || 'cpu_usage',
    value: 0,
    unit: '%',
    usage_percent: 0,
    source: 'manual',
  })
}

async function openMetricDialog(row = null) {
  if (!ledgerItems.value.length) await fetchLedger()
  if (row) {
    metricEditingId.value = row.id
    Object.assign(metricForm, {
      ci: row.ci || '',
      metric: row.metric || 'cpu_usage',
      value: Number(row.value || 0),
      unit: row.unit || '%',
      usage_percent: row.usage_percent ?? '',
      source: row.source || 'manual',
    })
  } else {
    resetMetricForm()
  }
  metricDialogVisible.value = true
}

function buildMetricPayload() {
  if (!metricForm.ci) throw new Error('请选择资源')
  const metric = metricForm.metric.trim()
  if (!metric) throw new Error('请填写指标名称')
  const value = Number(metricForm.value)
  if (!Number.isFinite(value)) throw new Error('请填写有效指标值')
  const usage = metricForm.usage_percent === '' || metricForm.usage_percent === null
    ? null
    : Number(metricForm.usage_percent)
  if (usage !== null && !Number.isFinite(usage)) throw new Error('请填写有效使用率')
  return {
    ci: metricForm.ci,
    metric,
    value,
    unit: metricForm.unit.trim(),
    usage_percent: usage,
    source: metricForm.source.trim() || 'manual',
  }
}

async function saveMetric() {
  let payload
  try {
    payload = buildMetricPayload()
  } catch (error) {
    return ElMessage.warning(error.message)
  }
  saving.value = true
  try {
    if (metricEditingId.value) {
      await updateResourceMetric(metricEditingId.value, payload)
      ElMessage.success('指标快照已更新')
    } else {
      await createResourceMetric(payload)
      ElMessage.success('指标快照已录入')
    }
    metricDialogVisible.value = false
    await Promise.all([fetchResourceMetrics(), fetchDashboard()])
  } finally {
    saving.value = false
  }
}

async function deleteMetricRow(row) {
  await ElMessageBox.confirm(`确认删除「${row.ci_name || row.ci} / ${metricLabel(row.metric)}」指标快照吗？`, '删除指标快照', { type: 'warning' })
  await deleteResourceMetric(row.id)
  ElMessage.success('指标快照已删除')
  await Promise.all([fetchResourceMetrics(), fetchDashboard()])
}

function resetRequestForm() {
  const firstCredential = (requestProvisioningOptions.value.credentials || [])[0]
  Object.assign(requestForm, {
    title: '',
    resource_type: 'ecs',
    specification: '2C4G',
    business_line: resourceNodeTree.value[0]?.name || '',
    environment: resourceNodeTree.value[0]?.children?.[0]?.name || '',
    priority: 'medium',
    quantity: 1,
    reason: '',
    host_list_text: '',
    specs: {
      provisioning_mode: firstCredential ? 'cloud' : 'manual',
      provider: firstCredential?.provider || 'aliyun',
      cloud_credential_id: firstCredential?.id || '',
      region: firstCredential?.default_region || '',
      zone: '',
      instance_name_prefix: '',
      hostname: '',
      ip_address: '',
      os_type: 'Linux',
      admin_user: authStore.displayName || '',
      instance_type: '',
      image_id: '',
      security_group_id: '',
      vswitch_id: '',
      key_pair_name: '',
      system_disk_category: 'cloud_essd',
      system_disk_size: 40,
      flavor_ref: '',
      vpc_id: '',
      subnet_id: '',
      key_name: '',
      root_volume_type: 'GPSSD',
      root_volume_size: 40,
      template_name: '',
      datastore_name: '',
      cluster_name: '',
      folder_name: '',
      cpu: 2,
      memory_gb: 4,
      power_on: true,
      resource_name: '',
      resource_id: '',
      instance_class: '',
      capacity: '',
      extra_requirements: '',
    },
  })
}

async function fetchRequestProvisioningOptions() {
  requestProvisioningOptionsLoading.value = true
  try {
    requestProvisioningOptions.value = await getResourceRequestProvisioningOptions()
  } finally {
    requestProvisioningOptionsLoading.value = false
  }
}

function onRequestDeliveryModeChange(mode) {
  if (mode === 'cloud' && !requestCredentialOptions.value.length) {
    const firstCredential = (requestProvisioningOptions.value.credentials || [])[0]
    if (firstCredential) {
      requestForm.specs.provider = firstCredential.provider
      requestForm.specs.cloud_credential_id = firstCredential.id
      requestForm.specs.region = firstCredential.default_region || ''
    }
  }
}

function onRequestResourceTypeChange(value) {
  const meta = requestResourceTypeOptions.value.find(item => item.value === value)
  if (meta?.delivery === 'manual' && requestForm.specs.provider === 'aliyun') {
    requestForm.specs.provisioning_mode = 'manual'
  }
  if (value !== 'ecs' && value !== '主机') {
    requestForm.specification = ''
  }
}

function onRequestProviderChange() {
  const firstCredential = requestCredentialOptions.value[0]
  requestForm.specs.cloud_credential_id = firstCredential?.id || ''
  requestForm.specs.region = firstCredential?.default_region || ''
}

function onRequestCredentialChange() {
  requestForm.specs.region = requestSelectedCredential.value?.default_region || requestForm.specs.region || ''
}

function onRequestBusinessLineChange() {
  requestForm.environment = requestEnvironmentOptions.value[0] || ''
}

function onCompletionBusinessLineChange() {
  if (!completionForm.environment || !completionEnvironmentOptions.value.includes(completionForm.environment)) {
    completionForm.environment = completionEnvironmentOptions.value[0] || completionForm.environment || ''
  }
}

function syncLinkedEnvironment(form, options) {
  if (!form.business_line) {
    form.environment = ''
    return
  }
  form.environment = normalizeEnvironmentValue(form.environment)
  if (form.environment && !options.includes(form.environment)) {
    form.environment = ''
  }
}

function onCiBusinessNodeChange() {
  ciForm.environment_node = ''
}

function onCiSourceAccountChange() {
  if (!ciForm.source_account || !ciSourceRegionOptions.value.includes(ciForm.source_region)) {
    ciForm.source_region = ''
  }
  syncCiFormResourceNode()
}

function onCiSourceRegionChange() {
  syncCiFormResourceNode()
}

function resolveCiFormResourceNodeId() {
  const account = String(ciForm.source_account || '').trim()
  if (!account) return ''
  const accountNodes = cloudResourceNodeRows.value.filter(item => (
    item.node_type === 'cloud_account'
    && !item.parent_id
    && item.name === account
  ))
  if (accountNodes.length !== 1) return ''
  const accountNode = accountNodes[0]
  const region = String(ciForm.source_region || '').trim()
  if (!region) return accountNode.id
  const regionNodes = cloudResourceNodeRows.value.filter(item => (
    item.node_type === 'cloud_region'
    && String(item.parent_id) === String(accountNode.id)
    && item.name === region
  ))
  return regionNodes.length === 1 ? regionNodes[0].id : accountNode.id
}

function syncCiFormResourceNode() {
  ciForm.resource_node = resolveCiFormResourceNodeId()
}

function syncBulkLedgerScopeFields() {
  const businessNode = bulkLedgerBusinessNodeOptions.value.find(item => String(item.id) === String(bulkLedgerForm.business_node))
  const environmentNode = bulkLedgerEnvironmentNodeOptions.value.find(item => String(item.id) === String(bulkLedgerForm.environment_node))
  bulkLedgerForm.business_line = businessNode?.name || ''
  bulkLedgerForm.environment = environmentNode ? normalizeEnvironmentValue(environmentNode.name) : ''
}

function onBulkLedgerBusinessNodeChange() {
  bulkLedgerForm.environment_node = ''
  syncBulkLedgerScopeFields()
}

function onBulkLedgerEnvironmentNodeChange() {
  syncBulkLedgerScopeFields()
}

async function openRequestDialog() {
  if (!resourceNodeTree.value.length) {
    await fetchResourceNodeTree()
  }
  await fetchRequestProvisioningOptions()
  resetRequestForm()
  requestDialogVisible.value = true
}

function normalizeCapacityRisk(row = {}) {
  if (row.type === 'capacity' && row.ci_id) {
    const matched = capacityRiskRows.value.find(item => String(item.ci_id) === String(row.ci_id))
    return { ...(matched || {}), ...row }
  }
  if ((row.ci || row.ci_id) && row.metric) {
    const matched = capacityRiskRows.value.find(item => String(item.ci_id || item.ci) === String(row.ci_id || row.ci) && item.metric === row.metric)
    return { ...(matched || {}), ...row }
  }
  return row || {}
}

function capacityModelId(row = {}) {
  if (row.ci_type_id) return row.ci_type_id
  if (row.resource_type && ciTypes.value.some(item => String(item.id) === String(row.resource_type))) return row.resource_type
  if (row.ci_type && ciTypes.value.some(item => String(item.id) === String(row.ci_type))) return row.ci_type
  const typeName = row.ci_type_name || row.ci_type || row.resource_type_name || ''
  return ciTypes.value.find(item => item.name === typeName || item.code === row.ci_type_code)?.id || ''
}

function capacityThresholdsForRisk(row = {}) {
  const raw = row.thresholds || {}
  if (Object.keys(raw).length) {
    return {
      warning: Number(raw.warning ?? raw.warning_threshold ?? 70),
      critical: Number(raw.critical ?? raw.critical_threshold ?? 85),
      exceeded: Number(raw.exceeded ?? raw.exceeded_threshold ?? 95),
    }
  }
  if (
    row.warning_threshold !== undefined
    || row.critical_threshold !== undefined
    || row.exceeded_threshold !== undefined
  ) {
    return {
      warning: Number(row.warning_threshold ?? 70),
      critical: Number(row.critical_threshold ?? 85),
      exceeded: Number(row.exceeded_threshold ?? 95),
    }
  }
  return capacityThresholdsForMetricRow(row)
}

function capacityRiskStatus(row = {}) {
  if (['warning', 'critical', 'exceeded', 'normal'].includes(row.status)) return row.status
  const usage = Number(row.usage_percent)
  if (!Number.isFinite(usage)) return 'unknown'
  const thresholds = capacityThresholdsForRisk(row)
  if (usage >= thresholds.exceeded) return 'exceeded'
  if (usage >= thresholds.critical) return 'critical'
  if (usage >= thresholds.warning) return 'warning'
  return 'normal'
}

function capacityRiskPriority(row = {}) {
  const status = capacityRiskStatus(row)
  if (status === 'exceeded' || status === 'critical') return 'high'
  if (status === 'warning') return 'medium'
  return 'low'
}

function capacityRiskStatusText(row = {}) {
  const map = {
    exceeded: '超限',
    critical: '紧急',
    warning: '预警',
    normal: '正常',
    unknown: '未知',
  }
  return map[capacityRiskStatus(row)] || '未知'
}

function linkedCapacityRequest(row = {}) {
  return normalizeCapacityRisk(row).linked_request || null
}

function hasActiveCapacityRequest(row = {}) {
  const request = linkedCapacityRequest(row)
  return ['pending', 'approved'].includes(request?.status)
}

function canCreateCapacityRequest(row = {}) {
  return canSubmitRequest.value && !hasActiveCapacityRequest(row)
}

function capacityGovernanceText(row = {}) {
  const risk = normalizeCapacityRisk(row)
  const request = risk.linked_request
  if (risk.governance_status === 'recheck_failed') return '待处理'
  if (request?.status === 'pending') return '已申请'
  if (request?.status === 'approved') return '已批准'
  if (request?.status === 'completed') return '已交付待复测'
  if (risk.governance_status === 'requesting') return '已申请'
  if (risk.governance_status === 'completed') return '已交付待复测'
  return '待处理'
}

function capacityGovernanceTagType(row = {}) {
  const risk = normalizeCapacityRisk(row)
  if (risk.governance_status === 'recheck_failed') return 'danger'
  const request = linkedCapacityRequest(row)
  if (request?.status === 'pending' || request?.status === 'approved') return 'warning'
  if (request?.status === 'completed') return 'success'
  return 'danger'
}

async function openLinkedCapacityRequest(row = {}) {
  const linked = linkedCapacityRequest(row)
  if (!linked?.id) return
  let detail = linked
  try {
    detail = await getResourceRequest(linked.id)
    const index = resourceRequests.value.findIndex(item => item.id === detail.id)
    if (index >= 0) resourceRequests.value.splice(index, 1, detail)
    else resourceRequests.value.unshift(detail)
  } catch {
    ElMessage.warning('未能加载最新申请详情，已展示风险中的申请快照')
  }
  await openRequestDetail(detail)
}

function isCapacityRisk(row = {}) {
  return ['warning', 'critical', 'exceeded'].includes(capacityRiskStatus(row))
}

function capacityThresholdText(row = {}) {
  const thresholds = capacityThresholdsForRisk(row)
  return `预警 ${thresholds.warning}% / 紧急 ${thresholds.critical}% / 超限 ${thresholds.exceeded}%`
}

function openCapacityThresholds(row = null) {
  thresholdFilters.resource_type = row ? capacityModelId(row) : ''
  thresholdFilters.metric = row?.metric || ''
  thresholdFilters.enabled = ''
  switchTab('thresholds')
  fetchThresholdManagement()
}

function openCapacityMetricDetail(item = {}) {
  thresholdFilters.resource_type = ''
  thresholdFilters.metric = item.metrics?.[0] || ''
  thresholdFilters.enabled = ''
  switchTab('thresholds')
  fetchThresholdManagement()
}

async function openCapacityRequestDialog(row = {}) {
  if (!resourceNodeTree.value.length) {
    await fetchResourceNodeTree()
  }
  await fetchRequestProvisioningOptions()
  resetRequestForm()
  const risk = normalizeCapacityRisk(row)
  const thresholds = capacityThresholdsForRisk(risk)
  const ciId = risk.ci_id || risk.ci
  const ciName = risk.ci_name || risk.name || (ciId ? `CI#${ciId}` : '容量风险资源')
  const metricName = metricLabel(risk.metric)
  const usage = risk.usage_percent ?? '-'
  const sourceType = risk.ci_type_name || risk.ci_type || risk.resource_type_name || '资源'
  const businessLine = risk.business_line || requestForm.business_line || resourceNodeTree.value[0]?.name || ''
  const businessNode = resourceNodeTree.value.find(item => item.name === businessLine) || resourceNodeTree.value[0]
  const envOptions = (businessNode?.children || []).map(item => item.name)
  const environment = risk.environment && envOptions.includes(risk.environment)
    ? risk.environment
    : (envOptions[0] || risk.environment || requestForm.environment || '')

  requestForm.title = `容量扩容申请：${ciName} ${metricName} ${usage}%`
  requestForm.resource_type = 'ecs'
  requestForm.specification = risk.specification || risk.instance_type || requestForm.specification || '2C4G'
  requestForm.business_line = businessNode?.name || businessLine
  requestForm.environment = environment
  requestForm.priority = capacityRiskPriority(risk)
  requestForm.quantity = 1
  requestForm.reason = [
    '容量风险来源：CMDB 水位治理',
    `资源：${ciName}（${sourceType}）`,
    `指标：${metricName}`,
    `当前使用率：${usage}%`,
    `风险级别：${capacityRiskStatusText(risk)}`,
    `阈值策略：预警 ${thresholds.warning}% / 紧急 ${thresholds.critical}% / 超限 ${thresholds.exceeded}%`,
    risk.policy_scope ? `命中策略：${risk.policy_scope}${risk.policy_id ? ` #${risk.policy_id}` : ''}` : '',
    '建议处理：评估扩容、清理或迁移负载，本申请用于触发资源扩容交付。',
  ].filter(Boolean).join('\n')
  requestForm.specs = {
    hostname: '',
    ip_address: '',
    os_type: risk.os_type || 'Linux',
    admin_user: risk.admin_user || authStore.displayName || '',
    instance_type: risk.instance_type || risk.specification || '',
    capacity_source: {
      ci_id: ciId || null,
      ci_name: ciName,
      ci_type: risk.ci_type || risk.ci_type_name || null,
      metric: risk.metric || '',
      usage_percent: risk.usage_percent ?? null,
      status: capacityRiskStatus(risk),
      thresholds,
      policy_id: risk.policy_id || null,
      policy_scope: risk.policy_scope || '',
      collected_at: risk.collected_at || '',
    },
  }
  requestDialogVisible.value = true
}

function parseRequestHostList() {
  const lines = requestForm.host_list_text
    .split(/\r?\n/)
    .map(line => line.trim())
    .filter(Boolean)
  if (!lines.length) throw new Error('请填写主机清单')
  return lines.map((line, index) => {
    const parts = line.split(/[,\s]+/).map(item => item.trim()).filter(Boolean)
    if (parts.length < 2) throw new Error(`第 ${index + 1} 行请填写主机名和 IP`)
    return {
      hostname: parts[0],
      ip_address: parts[1],
      instance_type: parts[2] || requestForm.specs.instance_type || '',
      os_type: requestForm.specs.os_type || 'Linux',
      admin_user: requestForm.specs.admin_user || '',
      specification: requestForm.specification.trim(),
    }
  })
}

function requestHostListTextFromSpecs(row) {
  const hosts = row?.specs?.hosts || row?.specs?.items || row?.specs?.resources || []
  if (!Array.isArray(hosts)) return ''
  return hosts
    .map(item => [
      item.hostname || item.name || '',
      item.ip_address || item.private_ip || item.ip || '',
      item.instance_type || '',
    ].filter(Boolean).join(' '))
    .filter(Boolean)
    .join('\n')
}

function resetRequestActionDeliveryForm(row) {
  const specs = row?.specs || {}
  Object.assign(requestActionDeliveryForm, {
    hostname: specs.hostname || specs.name || '',
    ip_address: specs.ip_address || specs.private_ip || specs.ip || '',
    os_type: specs.os_type || 'Linux',
    admin_user: specs.admin_user || row?.applicant || '',
    instance_type: specs.instance_type || row?.specification || '',
    host_list_text: requestHostListTextFromSpecs(row),
  })
}

function parseRequestActionHostList() {
  const lines = requestActionDeliveryForm.host_list_text
    .split(/\r?\n/)
    .map(line => line.trim())
    .filter(Boolean)
  if (!lines.length) throw new Error('请填写交付主机清单')
  return lines.map((line, index) => {
    const parts = line.split(/[,\s]+/).map(item => item.trim()).filter(Boolean)
    if (parts.length < 2) throw new Error(`第 ${index + 1} 行请填写主机名和 IP`)
    return {
      hostname: parts[0],
      ip_address: parts[1],
      instance_type: parts[2] || requestActionDeliveryForm.instance_type || '',
      os_type: requestActionDeliveryForm.os_type || 'Linux',
      admin_user: requestActionDeliveryForm.admin_user || '',
      specification: requestActionRow.value?.specification || '',
    }
  })
}

function buildRequestActionDeliveryPayload() {
  if (requestActionType.value !== 'complete') return {}
  if (!requestActionIsHost.value) {
    return {}
  }
  const quantity = Number(requestActionRow.value?.quantity || 1)
  const specs = {
    os_type: requestActionDeliveryForm.os_type.trim() || 'Linux',
    admin_user: requestActionDeliveryForm.admin_user.trim(),
    instance_type: requestActionDeliveryForm.instance_type.trim(),
  }
  if (quantity > 1) {
    const hosts = parseRequestActionHostList()
    if (hosts.length !== quantity) throw new Error('交付主机清单行数需与申请数量一致')
    specs.hosts = hosts
  } else {
    specs.hostname = requestActionDeliveryForm.hostname.trim()
    specs.ip_address = requestActionDeliveryForm.ip_address.trim()
    if (!specs.hostname || !specs.ip_address) throw new Error('请填写交付主机名和 IP 地址')
  }
  return { specs }
}

function buildRequestPayload() {
  if (!requestForm.title.trim()) throw new Error('请填写申请标题')
  if (!requestForm.business_line) throw new Error('请选择业务线')
  if (!requestForm.environment) throw new Error('请选择环境')
  if (!requestForm.reason.trim()) throw new Error('请填写申请理由')
  const specs = Object.fromEntries(
    Object.entries(requestForm.specs)
      .map(([key, value]) => [key, typeof value === 'string' ? value.trim() : value])
      .filter(([, value]) => value !== null && value !== undefined && value !== '')
  )
  specs.asset_type = requestForm.resource_type
  if (specs.provisioning_mode === 'cloud') {
    if (!specs.provider) throw new Error('请选择目标云平台')
    if (!specs.cloud_credential_id) throw new Error('请选择交付云账号')
    if (!specs.region) throw new Error('请填写目标地域或 vSphere 站点')
    if (!specs.instance_name_prefix) throw new Error('请填写实例名称或批量命名前缀')
    const provider = requestProviderOptions.value.find(item => item.value === specs.provider)
    const missing = (provider?.required_fields || []).filter(field => !specs[field])
    if (missing.length) throw new Error(`请补齐自动交付参数：${missing.join('、')}`)
    delete specs.hostname
    delete specs.ip_address
    delete specs.hosts
  } else if (requestForm.quantity > 1 && requestIsEcsType.value) {
    const hosts = parseRequestHostList()
    if (hosts.length !== requestForm.quantity) throw new Error('主机清单行数需与申请数量一致')
    specs.hosts = hosts
    delete specs.hostname
    delete specs.ip_address
  }
  return {
    title: requestForm.title.trim(),
    resource_type: requestForm.resource_type,
    specification: requestForm.specification.trim(),
    business_line: requestForm.business_line,
    environment: requestForm.environment,
    priority: requestForm.priority,
    quantity: requestForm.quantity,
    reason: requestForm.reason.trim(),
    specs,
  }
}

function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(url)
}

async function exportLedger() {
  if (!ledgerSelection.value.length) return ElMessage.warning('请先选择需要导出的资源')
  exportingLedger.value = true
  try {
    const ids = ledgerSelection.value.map(item => item.id).filter(Boolean).join(',')
    const blob = await exportConfigItems({ ids })
    const date = new Date().toISOString().slice(0, 10)
    const selectedTypeIds = new Set(ledgerSelection.value.map(item => String(item.ci_type || '')).filter(Boolean))
    downloadBlob(blob, `cmdb-ledger-${date}.${selectedTypeIds.size > 1 ? 'zip' : 'csv'}`)
    ElMessage.success(`已导出 ${ledgerSelection.value.length} 个资产`)
  } finally {
    exportingLedger.value = false
  }
}

async function downloadImportTemplate() {
  downloadingTemplate.value = true
  try {
    const params = {}
    if (bulkImportTemplateTypeIds.value.length) params.ci_types = bulkImportTemplateTypeIds.value.join(',')
    const blob = await downloadConfigItemImportTemplate(params)
    const date = new Date().toISOString().slice(0, 10)
    const extension = bulkImportTemplateTypeIds.value.length > 1 ? 'zip' : 'csv'
    downloadBlob(blob, `cmdb-import-template-${date}.${extension}`)
    ElMessage.success(extension === 'zip' ? '模型模板包已下载' : '导入模板已下载')
  } finally {
    downloadingTemplate.value = false
  }
}

async function submitResourceRequest() {
  let payload
  try {
    payload = buildRequestPayload()
  } catch (error) {
    return ElMessage.warning(error.message)
  }
  saving.value = true
  try {
    await createResourceRequest(payload)
    ElMessage.success('资源申请已提交')
    requestDialogVisible.value = false
    await Promise.all([fetchRequests(), fetchDashboard()])
  } finally {
    saving.value = false
  }
}

function openRequestAction(row, type) {
  requestActionRow.value = row
  requestActionType.value = type
  requestActionNote.value = ''
  if (type === 'complete') {
    resetRequestActionDeliveryForm(row)
  }
  requestActionVisible.value = true
}

async function submitRequestAction() {
  if (!requestActionRow.value || !requestActionType.value) return
  let deliveryPayload = {}
  try {
    deliveryPayload = buildRequestActionDeliveryPayload()
  } catch (error) {
    return ElMessage.warning(error.message)
  }
  saving.value = true
  try {
    const id = requestActionRow.value.id
    const data = { note: requestActionNote.value, comment: requestActionNote.value, ...deliveryPayload }
    if (requestActionType.value === 'approve') {
      await approveRequest(id, data)
      ElMessage.success('资源申请已批准')
    } else if (requestActionType.value === 'reject') {
      await rejectRequest(id, data)
      ElMessage.success('资源申请已驳回')
    } else if (requestActionType.value === 'complete') {
      await completeRequest(id, data)
      ElMessage.success('资源交付已完成，台账已同步')
      await Promise.all([fetchLedger(), fetchDashboard()])
    } else if (requestActionType.value === 'provision') {
      await provisionResourceRequest(id, data)
      ElMessage.success('机器创建成功，已同步多云资产与 CMDB')
      await Promise.all([fetchLedger(), fetchDashboard()])
    }
    requestActionVisible.value = false
    await fetchRequests()
    await refreshOpenRequestDetail(id)
  } finally {
    saving.value = false
  }
}

function clearSyncFilters() {
  syncFilters.search = ''
  syncFilters.source_type = ''
  syncFilters.status = ''
  syncFocusTypes.value = []
  syncFocusContext.value = null
  syncAccountContext.value = null
}

function focusSyncJointCard(item) {
  clearSyncFilters()
  const sourceTypes = Array.isArray(item?.sourceTypes) ? item.sourceTypes.filter(Boolean) : []
  syncFocusTypes.value = sourceTypes
  if (sourceTypes.length === 1) {
    syncFilters.source_type = sourceTypes[0]
  }
  syncFocusContext.value = {
    key: item?.key || '',
    title: item?.title || '联调模板',
    hint: item?.hint || '按当前聚焦范围查看同步模板，建议先预览再执行。',
  }
}

function focusSyncAccountCard(item) {
  clearSyncFilters()
  if (!item?.id) return
  syncAccountContext.value = {
    id: item.id,
    credential: item,
    title: `${item.providerLabel || item.provider || '-'} / ${item.title || '-'}`,
    hint: `账号 ${item.accountLabel || '-'} · 地域 ${item.region || '-'} · 任务 ${item.jobCount || 0} 个`,
  }
}

function clearSyncAccountContext() {
  syncAccountContext.value = null
}

function clearSourceMappingFilters() {
  sourceMappingFilters.search = ''
  sourceMappingFilters.source_type = ''
  sourceMappingFilters.sync_status = ''
  fetchSourceMappings()
}

async function fetchModelResources(modelId = selectedModelId.value, options = {}) {
  if (!canViewCi.value || !modelId) {
    modelResourceItems.value = []
    modelResourcePagination.total = 0
    resourceWaterlinePageMetrics.value = []
    return
  }
  const { preservePage = false } = options || {}
  if (!preservePage) modelResourcePagination.page = 1
  modelResourceLoading.value = true
  try {
    const response = await getConfigItems({
      page: modelResourcePagination.page,
      page_size: modelResourcePagination.pageSize,
      ...currentModelResourceParams(modelId),
      ...modelCatalogContextParams(),
    })
    modelResourceItems.value = withoutHiddenCiTypes(response)
    modelResourcePagination.total = totalOf(response, modelResourceItems.value.length)
    await fetchModelThirdPartyExpirySummary(modelId)
  } finally {
    modelResourceLoading.value = false
  }
}

function handleModelResourcePageChange(page) {
  modelResourcePagination.page = page
  fetchModelResources(selectedModelId.value, { preservePage: true })
}

function handleModelResourcePageSizeChange(size) {
  modelResourcePagination.pageSize = size
  modelResourcePagination.page = 1
  fetchModelResources(selectedModelId.value, { preservePage: true })
}

async function syncModelDetailSelection() {
  if (!isModelDetailRoute.value) return
  const modelId = route.params.id ? String(route.params.id) : ''
  selectedModelId.value = modelId
  modelResourceFilters.ci_type = modelId
  if (!modelId) {
    modelResourceItems.value = []
    return
  }
  await fetchModelResources(modelId)
}

function openModelDetail(row) {
  if (!row?.id) return
  router.push(`/cmdb/model/${row.id}`)
}

function openModelCard(row) {
  if (isModelConfigRoute.value) {
    openModelConfigDrawer(row)
    return
  }
  openModelDetail(row)
}

function backToModelList() {
  router.push('/cmdb/model')
}

async function selectModel(row) {
  const nextModelId = selectedModelId.value === row.id ? '' : row.id
  selectedModelId.value = nextModelId
  modelResourceItems.value = []
  if (nextModelId) await fetchModelResources(nextModelId)
}

function modelRowClassName({ row }) {
  return String(row.id) === String(selectedModelId.value) ? 'is-selected-model' : ''
}

function openBulkImportDialog() {
  bulkImportForm.name = '资产台账批量导入'
  bulkImportForm.source_type = bulkImportForm.source_type || 'manual_import'
  bulkImportForm.format = 'csv'
  bulkImportForm.text = ''
  const selectedTypeIds = [...new Set(ledgerSelection.value.map(item => String(item.ci_type || '')).filter(Boolean))]
  bulkImportTemplateTypeIds.value = selectedTypeIds.length ? selectedTypeIds : (ledgerFilters.ci_type ? [String(ledgerFilters.ci_type)] : [])
  bulkImportFileName.value = ''
  bulkImportPreviewReady.value = false
  bulkImportPreview.value = { summary: {}, records: [] }
  bulkImportVisible.value = true
}

function resetBulkImportPreview() {
  bulkImportPreviewReady.value = false
  bulkImportPreview.value = { summary: {}, records: [] }
}

async function handleBulkImportFileChange(event) {
  const file = event?.target?.files?.[0]
  if (!file) return
  bulkImportFileName.value = file.name
  const extension = file.name.toLowerCase().split('.').pop()
  if (extension === 'csv' || extension === 'json') bulkImportForm.format = extension
  bulkImportForm.text = await file.text()
  resetBulkImportPreview()
  if (bulkImportFileInput.value) bulkImportFileInput.value.value = ''
}

function buildBulkImportPayload(dryRun) {
  if (!bulkImportForm.text.trim()) throw new Error('请填写导入内容')
  return {
    name: bulkImportForm.name || '资产台账批量导入',
    source_type: bulkImportForm.source_type || 'manual_import',
    format: bulkImportForm.format,
    text: bulkImportForm.text,
    dry_run: dryRun,
  }
}

async function previewBulkImport() {
  bulkImportLoading.value = true
  try {
    const result = await bulkImportConfigItems(buildBulkImportPayload(true))
    bulkImportPreview.value = {
      summary: result?.summary || {},
      records: result?.records || [],
    }
    bulkImportPreviewReady.value = true
    ElMessage.success('导入预览已生成')
  } catch (error) {
    if (error?.message) ElMessage.warning(error.message)
  } finally {
    bulkImportLoading.value = false
  }
}

async function commitBulkImport() {
  bulkImportLoading.value = true
  try {
    const result = await bulkImportConfigItems(buildBulkImportPayload(false))
    bulkImportPreview.value = {
      summary: result?.summary || {},
      records: result?.records || [],
    }
    bulkImportPreviewReady.value = false
    ElMessage.success('批量导入已完成')
    await Promise.all([fetchLedger(), fetchDashboard(), fetchGovernanceRisks({ force: true }), fetchGovernance(), fetchSyncJobs()])
  } catch (error) {
    if (error?.message) ElMessage.warning(error.message)
  } finally {
    bulkImportLoading.value = false
  }
}

function parseJsonObject(text, fieldName, fallback = {}) {
  if (!text || !text.trim()) return fallback
  try {
    const value = JSON.parse(text)
    if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error()
    return value
  } catch {
    throw new Error(`${fieldName} 需要填写合法 JSON 对象`)
  }
}

function parseJsonArray(text, fieldName) {
  if (!text || !text.trim()) return []
  try {
    const value = JSON.parse(text)
    if (!Array.isArray(value)) throw new Error()
    return value
  } catch {
    throw new Error(`${fieldName} 需要填写合法 JSON 数组`)
  }
}

function ciFieldOptions(field) {
  const rawOptions = Array.isArray(field?.options) ? field.options : []
  return rawOptions.map((item) => {
    if (item && typeof item === 'object') {
      const value = item.value ?? item.key ?? item.label ?? item.name
      return { value, label: item.label ?? item.name ?? value }
    }
    return { value: item, label: item }
  }).filter(item => item.value !== undefined && item.value !== null && item.value !== '')
}

function isCiFormWideField(field) {
  return ['json', 'multi_enum'].includes(field?.field_type) || String(field?.name || '').length >= 10
}

function normalizeCiFormFieldValue(field, source = {}) {
  const hasValue = Object.prototype.hasOwnProperty.call(source, field.code)
  const rawValue = hasValue ? source[field.code] : field.default
  if (rawValue === undefined || rawValue === null || rawValue === '') {
    if (field.field_type === 'multi_enum') return []
    return ''
  }
  if (field.field_type === 'json') {
    return typeof rawValue === 'string' ? rawValue : JSON.stringify(rawValue, null, 2)
  }
  if (field.field_type === 'multi_enum') {
    if (Array.isArray(rawValue)) return [...rawValue]
    return String(rawValue).split(',').map(item => item.trim()).filter(Boolean)
  }
  if (field.field_type === 'boolean') {
    if (typeof rawValue === 'boolean') return rawValue
    const normalized = String(rawValue).toLowerCase()
    if (['true', '1', 'yes'].includes(normalized)) return true
    if (['false', '0', 'no'].includes(normalized)) return false
    return ''
  }
  if (['integer', 'decimal'].includes(field.field_type)) {
    const numeric = Number(rawValue)
    return Number.isFinite(numeric) ? numeric : undefined
  }
  return rawValue
}

function syncCiFormAttributeValues(source = ciForm.baseAttributes || {}) {
  const values = {}
  ciFormModelFields.value.forEach((field) => {
    values[field.code] = normalizeCiFormFieldValue(field, source)
  })
  ciForm.attributeValues = values
}

function isEmptyCiFormAttributeValue(field, value) {
  if (field.field_type === 'boolean') return value === '' || value === undefined || value === null
  if (field.field_type === 'multi_enum') return !Array.isArray(value) || !value.length
  return value === undefined || value === null || value === ''
}

function parseCiFormAttributeValue(field, value) {
  if (isEmptyCiFormAttributeValue(field, value)) return field.field_type === 'multi_enum' ? [] : ''
  if (field.field_type === 'json') {
    if (typeof value !== 'string') return value
    try {
      const parsed = JSON.parse(value)
      if (!parsed || typeof parsed !== 'object') throw new Error()
      return parsed
    } catch {
      throw new Error(`${field.name} 需要填写合法 JSON 对象或数组`)
    }
  }
  return value
}

function buildCiFormModelAttributes() {
  const attributes = {}
  for (const field of ciFormModelFields.value) {
    attributes[field.code] = parseCiFormAttributeValue(field, ciForm.attributeValues[field.code])
  }
  return attributes
}

function validateCiFormRequiredAttributes() {
  const missingField = ciFormModelFields.value.find(field => field.required && isEmptyCiFormAttributeValue(field, ciForm.attributeValues[field.code]))
  if (missingField) {
    ElMessage.warning(`请填写${missingField.name}`)
    return false
  }
  return true
}

function ciFormContextAttributesFromLedgerTree() {
  const context = ledgerTreeContext.value
  if (!context) return {}
  if (context.view_mode === 'business') {
    return {
      ...(context.business_line ? { business_line: context.business_line } : {}),
      ...(context.environment ? { environment: context.environment } : {}),
      ...(context.system ? { system: context.system } : {}),
    }
  }
  const attrs = {
    ...(context.source_account && !context.source_account_missing ? { source_account: context.source_account } : {}),
    ...(context.source_region ? { source_region: context.source_region } : {}),
    ...(context.node_id ? { resource_node_id: context.node_id } : {}),
    ...(context.parent_id ? { resource_node_parent_id: context.parent_id } : {}),
    ...(context.node_id ? { resource_node: context.node_id } : {}),
  }
  if (context.vsphere_cluster) {
    attrs.vsphere_cluster = context.vsphere_cluster
    attrs.cluster = context.vsphere_cluster
  }
  if (context.vsphere_host) {
    attrs.vsphere_host = context.vsphere_host
    attrs.host = context.vsphere_host
  }
  return attrs
}

function resetCiForm() {
  ciEditingId.value = null
  const contextAttributes = ciFormContextAttributesFromLedgerTree()
  const contextBusinessLine = contextAttributes.business_line || ''
  const contextEnvironment = normalizeEnvironmentValue(contextAttributes.environment)
  const {
    business_node: contextBusinessNode,
    environment_node: contextEnvironmentNode,
    resource_node: contextResourceNode,
    ...baseAttributes
  } = contextAttributes
  Object.assign(ciForm, {
    name: '',
    ci_type: ciTypes.value[0]?.id || '',
    ci_type_code: ciTypes.value[0]?.code || '',
    ci_type_group_code: ciTypes.value[0]?.group_code || '',
    business_node: contextBusinessNode || '',
    business_line: contextBusinessLine,
    department: '',
    environment_node: contextEnvironmentNode || '',
    environment: contextBusinessLine ? contextEnvironment : '',
    resource_node: contextResourceNode || '',
    admin_user: '',
    status: 'active',
    monthly_cost: null,
    source_account: contextAttributes.source_account || '',
    source_region: contextAttributes.source_region || '',
    description: '',
    tags: [],
    baseAttributes,
    attributeValues: {},
  })
  syncCiFormAttributeValues(baseAttributes)
}

function fillCiForm(item) {
  const attributes = item.attributes || {}
  Object.assign(ciForm, {
    name: item.name || '',
    ci_type: item.ci_type || '',
    ci_type_code: item.ci_type_code || '',
    ci_type_group_code: item.ci_type_group_code || '',
    business_node: item.business_node || '',
    business_line: item.business_line || '',
    department: attributes.department || '',
    environment_node: item.environment_node || '',
    environment: normalizeEnvironmentValue(item.environment),
    resource_node: item.resource_node || attributes.resource_node_id || '',
    admin_user: item.admin_user || '',
    status: item.status || 'active',
    monthly_cost: attributes.monthly_cost ?? null,
    source_account: primarySourceMapping(item)?.source_account || attributes.source_account || attributes.cloud_account || attributes.account || attributes.account_id || attributes.account_name || '',
    source_region: primarySourceMapping(item)?.source_region || attributes.source_region || attributes.cloud_region || attributes.region || attributes.region_id || '',
    description: attributes.description || '',
    tags: Array.isArray(item.tags) ? [...item.tags] : (item.tag_items || []).map(tag => tag.id),
    baseAttributes: { ...attributes },
    attributeValues: {},
  })
  syncCiFormAttributeValues(attributes)
}

async function openCiDialog(row = null) {
  const isDomEvent = row && typeof row === 'object' && 'currentTarget' in row && 'target' in row
  const item = isDomEvent ? null : row
  if (!resourceNodeTree.value.length) await fetchResourceNodeTree()
  try {
    await fetchCiSourceAccountRegionOptions()
  } catch {
    // Existing ledger and source-mapping data remain available as a fallback.
  }
  if (canViewSync.value && !sourceMappings.value.length) {
    try {
      sourceMappings.value = listOf(await getSourceMappings({ page_size: 200 }))
    } catch {
      // The ledger data remains available as a fallback for users without sync access.
    }
  }
  if (!item || item.id === undefined || item.id === null) {
    resetCiForm()
  } else {
    ciEditingId.value = item.id
    fillCiForm(item)
    try {
      const latest = await getConfigItem(item.id)
      ciEditingId.value = latest.id
      fillCiForm(latest)
    } catch {
      ElMessage.warning('未能加载最新配置项详情，已使用列表数据回填')
    }
  }
  ciDialogVisible.value = true
}

function onLedgerSelectionChange(rows) {
  ledgerSelection.value = rows || []
}

function resetBulkLedgerForm() {
  Object.assign(bulkLedgerForm, {
    business_node: '',
    business_line: '',
    environment_node: '',
    environment: '',
    admin_user: '',
    department: '',
    status: '',
    tag_action: 'append',
    tag_ids: [],
    note: '批量维护资产台账',
  })
}

async function openBulkLedgerDialog() {
  if (!ledgerSelection.value.length) return ElMessage.warning('请先选择需要维护的资源')
  if (!resourceNodeTree.value.length) await fetchResourceNodeTree()
  resetBulkLedgerForm()
  bulkLedgerDialogVisible.value = true
}

function openBulkLedgerDialogFromTreeContext() {
  const context = ledgerTreeContext.value
  if (!context) return ElMessage.warning('请先从资源树节点进入台账')
  if (!ledgerSelection.value.length) return ElMessage.warning('请先选择需要回填归属的资源')
  resetBulkLedgerForm()
  bulkLedgerForm.business_node = context.business_node || ''
  bulkLedgerForm.environment_node = context.environment_node || ''
  syncBulkLedgerScopeFields()
  bulkLedgerForm.note = context.environment
    ? `按资源树节点回填归属：${context.business_line}/${environmentText(context.environment)}`
    : `按资源树节点回填业务线：${context.business_line}`
  bulkLedgerDialogVisible.value = true
}

async function saveBulkLedgerUpdate() {
  if (!ledgerSelection.value.length) return
  const updates = {}
  const businessNode = bulkLedgerBusinessNodeOptions.value.find(item => String(item.id) === String(bulkLedgerForm.business_node))
  const environmentNode = bulkLedgerEnvironmentNodeOptions.value.find(item => String(item.id) === String(bulkLedgerForm.environment_node))
  if (businessNode && !environmentNode) {
    return ElMessage.warning('选择业务线后请同时选择环境')
  }
  if (businessNode && environmentNode) {
    updates.business_node = businessNode.id
    updates.business_line = businessNode.name
    updates.environment_node = environmentNode.id
    updates.environment = normalizeEnvironmentValue(environmentNode.name)
  }
  ;['admin_user', 'status'].forEach((key) => {
    const value = String(bulkLedgerForm[key] || '').trim()
    if (value) updates[key] = value
  })
  const department = String(bulkLedgerForm.department || '').trim()
  if (department) updates.attributes = { department }
  const tagIds = bulkLedgerForm.tag_ids || []
  if (!Object.keys(updates).length && !tagIds.length) {
    return ElMessage.warning('请填写至少一个需要变更的字段或标签')
  }
  await ElMessageBox.confirm(
    `确认批量维护已选择的 ${ledgerSelection.value.length} 个资源吗？`,
    '批量维护资源',
    { type: 'warning' },
  )
  saving.value = true
  try {
    const result = await bulkUpdateConfigItems({
      ids: ledgerSelection.value.map(item => item.id),
      updates,
      tag_ids: tagIds,
      tag_action: bulkLedgerForm.tag_action,
      note: bulkLedgerForm.note,
    })
    ElMessage.success(`已批量维护 ${result?.updated_count || 0} 个资源`)
    ledgerSelection.value = []
    bulkLedgerDialogVisible.value = false
    await Promise.all([fetchLedger(), fetchDashboard(), fetchRepositorySummary(), fetchGovernance(), fetchAuditLogs(), fetchResourceNodeTree()])
  } finally {
    saving.value = false
  }
}

async function saveConfigItem() {
  if (!ciForm.name) return ElMessage.warning('请填写资源名称')
  if (!ciForm.ci_type) return ElMessage.warning('请选择资产分类')
  if (!validateCiFormRequiredAttributes()) return
  let modelAttributes = {}
  try {
    modelAttributes = buildCiFormModelAttributes()
  } catch (error) {
    return ElMessage.warning(error.message)
  }
  saving.value = true
  try {
    const baseAttributes = ciForm.baseAttributes && typeof ciForm.baseAttributes === 'object'
      ? { ...ciForm.baseAttributes }
      : {}
    const attributes = {
      ...baseAttributes,
      ...modelAttributes,
      department: ciForm.department.trim(),
      source_account: ciForm.source_account.trim(),
      source_region: ciForm.source_region.trim(),
      description: ciForm.description || '',
    }
    if (ciForm.monthly_cost === null || ciForm.monthly_cost === undefined || ciForm.monthly_cost === '') {
      delete attributes.monthly_cost
    } else {
      attributes.monthly_cost = Number(ciForm.monthly_cost)
    }
    const resourceNodeId = resolveCiFormResourceNodeId() || ciForm.resource_node
    if (resourceNodeId) attributes.resource_node_id = resourceNodeId
    else delete attributes.resource_node_id
    const payload = {
      name: ciForm.name,
      ci_type: ciForm.ci_type,
      business_node: ciForm.business_node || null,
      environment_node: ciForm.environment_node || null,
      resource_node: resourceNodeId || null,
      admin_user: ciForm.admin_user,
      status: ciForm.status,
      tags: ciForm.tags || [],
      attributes,
    }
    if (ciEditingId.value) {
      const updated = await updateConfigItem(ciEditingId.value, payload)
      ciDetail.value = ciDetail.value?.id === updated.id ? updated : ciDetail.value
      ElMessage.success('配置项已更新')
    } else {
      await createConfigItem(payload)
      ElMessage.success('配置项已创建')
    }
    ciDialogVisible.value = false
    await Promise.all([fetchLedger(), fetchDashboard(), fetchGovernance(), fetchTags()])
    if (ciDetailVisible.value && ciDetail.value?.id) await openCiDetail(ciDetail.value, false)
  } finally {
    saving.value = false
  }
}

function formatImpactCounts(impact) {
  const blockingLabels = {
    relations: '资源关系',
    source_mappings: '采集来源',
    open_completion_issues: '待补全治理项',
    pending_archive_candidates: '待下线候选',
    cost_records: '成本记录',
  }
  const warningLabels = {
    sync_records: '同步记录',
    change_logs: '变更记录',
  }
  const blockingLines = Object.entries(impact?.blocking_counts || {})
    .filter(([, value]) => Number(value || 0) > 0)
    .map(([key, value]) => `${blockingLabels[key] || key}: ${value}`)
  const warningLines = Object.entries(impact?.warning_counts || {})
    .filter(([, value]) => Number(value || 0) > 0)
    .map(([key, value]) => `${warningLabels[key] || key}: ${value}`)
  const relationLines = (impact?.relation_samples || [])
    .slice(0, 5)
    .map(item => `- ${item.direction === 'outgoing' ? '出向' : '入向'} ${item.relation_label || item.relation_type}: ${item.related_ci_name}`)
  return [
    blockingLines.length ? `会删除或关闭的关联：\n${blockingLines.join('\n')}` : '未发现阻断类关联。',
    warningLines.length ? `会保留但解除 CI 链接的历史：\n${warningLines.join('\n')}` : '',
    relationLines.length ? `关系样例：\n${relationLines.join('\n')}` : '',
  ].filter(Boolean).join('\n\n')
}

async function deleteConfigItemRow(row) {
  if (!row?.id) return
  ciDeleting.value = true
  try {
    const impact = await getConfigItemImpact(row.id)
    const message = `确认删除配置项「${row.name}」吗？\n\n${formatImpactCounts(impact)}\n\n删除后资产台账不再显示该配置项，请确认已不再纳管。`
    await ElMessageBox.confirm(message, '删除配置项', {
      type: 'warning',
      confirmButtonText: '确认删除',
      cancelButtonText: '取消',
    })
    await deleteConfigItem(row.id, { force: impact?.blocking_total ? 'true' : undefined })
    ElMessage.success('配置项已删除')
    ciDetailVisible.value = false
    ciDetail.value = null
    await Promise.all([fetchLedger(), fetchDashboard(), fetchGovernance(), fetchSyncJobs()])
  } finally {
    ciDeleting.value = false
  }
}

async function updateGovernanceStatus(row, category, status) {
  const ciId = row?.ci_id || row?.ci
  if (!ciId || !canManageCi.value) return
  const ciName = row.ci_name || row.name || `资产 #${ciId}`
  const metricText = category === 'capacity' ? `（${metricLabel(row.metric)}）` : ''
  const actionText = status === 'resolved' ? '标记为已处理' : '忽略该治理项'
  await ElMessageBox.confirm(`确认将「${ciName}」${metricText}${actionText}吗？处理后该风险将从治理队列中移除。`, '更新治理状态', {
    type: status === 'ignored' ? 'warning' : 'info',
    confirmButtonText: '确认',
    cancelButtonText: '取消',
  })
  await updateConfigItemGovernance(ciId, {
    category,
    metric: category === 'capacity' ? row.metric : '',
    status,
    risk_fingerprint: row.risk_fingerprint || '',
    note: status === 'resolved' ? '治理中心标记已处理' : '治理中心人工忽略',
  })
  ElMessage.success(status === 'resolved' ? '已标记为已处理' : '已忽略该治理项')
  await Promise.all([fetchGovernanceRisks({ force: true }), fetchGovernance(), fetchDashboard(), fetchLedger()])
}

async function markConfigItemArchive(row) {
  if (!row?.id) return
  await ElMessageBox.confirm(
    `确认将「${row.name}」加入待下线治理队列吗？该操作不会直接下线资源，需要在治理中心确认。`,
    '标记待下线',
    {
      type: 'warning',
      confirmButtonText: '加入治理队列',
      cancelButtonText: '取消',
    },
  )
  ciLifecycleSaving.value = true
  try {
    await markConfigItemArchiveCandidate(row.id, {
      source_type: 'manual',
      reason: '资源详情人工标记待下线',
    })
    ElMessage.success('已加入待下线治理队列')
    await Promise.all([fetchGovernance(), fetchDashboard(), fetchLedger()])
    if (ciDetailVisible.value && ciDetail.value?.id) await openCiDetail(ciDetail.value, false)
  } finally {
    ciLifecycleSaving.value = false
  }
}

async function restoreConfigItemStatus(row) {
  if (!row?.id) return
  await ElMessageBox.confirm(`确认恢复「${row.name}」为使用中吗？相关待下线候选会同步关闭。`, '恢复资源', { type: 'warning' })
  ciLifecycleSaving.value = true
  try {
    const updated = await restoreConfigItemLifecycle(row.id, { status: 'active', note: '资源详情人工恢复' })
    ElMessage.success('资源已恢复')
    if (updated?.id) ciDetail.value = updated
    await Promise.all([fetchGovernance(), fetchDashboard(), fetchLedger()])
    if (ciDetailVisible.value && ciDetail.value?.id) await openCiDetail(ciDetail.value, false)
  } finally {
    ciLifecycleSaving.value = false
  }
}

async function openCiDetail(row, showDrawer = true) {
  if (showDrawer) ciDetailVisible.value = true
  disposeCiDetailWaterlineChart()
  ciDetailLoading.value = true
  ciDetailCostLoading.value = canViewCost.value
  ciDetailCostMonth.value = currentMonth()
  ciDetailCostHistory.value = []
  ciDetailWaterlineHistory.value = []
  const waterlineWindowEnd = new Date()
  ciDetailWaterlineWindow.value = {
    start: new Date(waterlineWindowEnd.getTime() - 6 * 60 * 60 * 1000).toISOString(),
    end: waterlineWindowEnd.toISOString(),
  }
  ciDetail.value = row
  try {
    const detailTask = getConfigItem(row.id)
    const mappingTask = canViewSync.value ? getSourceMappings({ ci: row.id, page_size: 50 }) : Promise.resolve([])
    const changeTask = canViewAudit.value ? getChangeLogs({ ci: row.id, page_size: 50 }) : Promise.resolve([])
    const impactTask = getConfigItemImpact(row.id, { max_depth: 2 })
    const costTask = canViewCost.value ? getCostRecords({ ci: row.id, page_size: 100 }) : Promise.resolve([])
    const metricTask = getResourceMetrics({
      ci: row.id,
      metrics: resourceWaterlineMetricDefs.flatMap(item => item.metrics).join(','),
      collected_after: ciDetailWaterlineWindow.value.start,
      collected_before: ciDetailWaterlineWindow.value.end,
      page_size: 500,
    })
    const [detailRes, mappingRes, changeRes, impactRes, costRes, metricRes] = await Promise.allSettled([
      detailTask,
      mappingTask,
      changeTask,
      impactTask,
      costTask,
      metricTask,
    ])
    if (detailRes.status === 'fulfilled') ciDetail.value = detailRes.value
    ciDetailMappings.value = mappingRes.status === 'fulfilled' ? listOf(mappingRes.value) : []
    ciDetailChangeLogs.value = changeRes.status === 'fulfilled' ? listOf(changeRes.value) : []
    ciDetailImpact.value = impactRes.status === 'fulfilled' ? impactRes.value : null
    ciDetailCostHistory.value = costRes.status === 'fulfilled' ? listOf(costRes.value) : []
    ciDetailWaterlineHistory.value = metricRes.status === 'fulfilled' ? listOf(metricRes.value) : []
    await nextTick()
    renderCiDetailWaterlineChart()
  } finally {
    ciDetailLoading.value = false
    ciDetailCostLoading.value = false
  }
}

function openCiTopologyDialog() {
  if (!ciDetail.value?.id || !canViewTopology.value) return
  ciTopologyId.value = ciDetail.value.id
  ciTopologyVisible.value = true
}

async function openLedgerDetailFromRoute() {
  const ciId = String(route.query.detail_ci_id || route.query.ci_id || '')
  if (route.name !== 'CmdbLedger' || !ciId || ciId === openedLedgerDetailId.value) return
  await openCiDetail({ id: ciId })
  openedLedgerDetailId.value = ciId
}

function resetAssetPasswordForm(record = null) {
  assetPasswordEntryVisible.value = false
  Object.assign(assetPasswordForm, {
    username: record?.username || '',
    password: '',
    remark: record?.remark || '',
  })
}

function resetAssetPasswordDialog() {
  assetPasswordRecord.value = null
  assetPasswordEditing.value = false
  revealedAssetPassword.value = ''
  assetPasswordVerificationVisible.value = false
  resetAssetPasswordVerification()
  resetAssetPasswordForm()
}

function resetAssetPasswordVerification() {
  assetPasswordVerificationForm.currentPassword = ''
}

async function openAssetPasswordDialog() {
  if (!ciDetail.value?.id || !canAccessAssetPassword.value) return
  assetPasswordDialogVisible.value = true
  assetPasswordLoading.value = true
  assetPasswordEditing.value = false
  revealedAssetPassword.value = ''
  try {
    const rows = listOf(await getConfigItemPasswords({ config_item: ciDetail.value.id }))
    assetPasswordRecord.value = rows[0] || null
    assetPasswordEditing.value = !assetPasswordRecord.value && canManageAssetPassword.value
    resetAssetPasswordForm(assetPasswordRecord.value)
  } finally {
    assetPasswordLoading.value = false
  }
}

function startEditingAssetPassword() {
  revealedAssetPassword.value = ''
  resetAssetPasswordForm(assetPasswordRecord.value)
  assetPasswordEditing.value = true
}

function cancelEditingAssetPassword() {
  resetAssetPasswordForm(assetPasswordRecord.value)
  assetPasswordEditing.value = false
}

async function saveAssetPassword() {
  if (!ciDetail.value?.id || !canManageAssetPassword.value) return
  if (!assetPasswordRecord.value && assetPasswordForm.password === '') {
    return ElMessage.warning('请输入登录密码')
  }
  const payload = {
    config_item: ciDetail.value.id,
    username: assetPasswordForm.username.trim(),
    remark: assetPasswordForm.remark.trim(),
  }
  if (assetPasswordForm.password !== '') payload.password = assetPasswordForm.password
  assetPasswordSaving.value = true
  try {
    assetPasswordRecord.value = assetPasswordRecord.value
      ? await updateConfigItemPassword(assetPasswordRecord.value.id, payload)
      : await createConfigItemPassword(payload)
    assetPasswordEditing.value = false
    revealedAssetPassword.value = ''
    resetAssetPasswordForm(assetPasswordRecord.value)
    ElMessage.success('登录凭据已保存')
  } finally {
    assetPasswordSaving.value = false
  }
}

function revealAssetPassword() {
  if (!assetPasswordRecord.value?.id || !canRevealAssetPassword.value) return
  revealedAssetPassword.value = ''
  resetAssetPasswordVerification()
  assetPasswordVerificationVisible.value = true
}

async function confirmRevealAssetPassword() {
  if (!assetPasswordRecord.value?.id || !canRevealAssetPassword.value) return
  const currentPassword = assetPasswordVerificationForm.currentPassword
  if (!currentPassword) return ElMessage.warning('请输入当前平台登录密码')
  assetPasswordRevealing.value = true
  try {
    const result = await revealConfigItemPassword(assetPasswordRecord.value.id, {
      current_password: currentPassword,
    })
    revealedAssetPassword.value = result.password || ''
    assetPasswordVerificationVisible.value = false
  } catch {
    // The request interceptor displays the verification error; keep the dialog open for retry.
  } finally {
    assetPasswordVerificationForm.currentPassword = ''
    assetPasswordRevealing.value = false
  }
}

async function copyRevealedAssetPassword() {
  if (!revealedAssetPassword.value) return
  try {
    await navigator.clipboard.writeText(revealedAssetPassword.value)
    ElMessage.success('密码已复制到剪贴板')
  } catch {
    ElMessage.warning('复制失败，请手动复制')
  }
}

async function removeAssetPassword() {
  if (!assetPasswordRecord.value?.id || !canManageAssetPassword.value) return
  await ElMessageBox.confirm(`确认删除「${ciDetail.value?.name || '该资产'}」的登录凭据吗？`, '删除登录凭据', { type: 'warning' })
  await deleteConfigItemPassword(assetPasswordRecord.value.id)
  ElMessage.success('登录凭据已删除')
  assetPasswordDialogVisible.value = false
}

async function fetchRelationTargets(keyword = '') {
  if (!canViewCi.value || !ciDetail.value?.id) return
  const params = { page_size: 100 }
  if (keyword) params.search = keyword
  const peerTypes = relationRules.value
    .filter((rule) => rule.direction === relationForm.direction)
    .filter((rule) => !relationForm.relation_type || rule.relation_type === relationForm.relation_type)
    .map((rule) => rule.peer_type)
    .filter(Boolean)
  if (relationRules.value.length && !peerTypes.length) {
    relationTargets.value = []
    return
  }
  if (peerTypes.length === 1) params.ci_type = peerTypes[0]
  const peerTypeSet = new Set(peerTypes)
  relationTargets.value = listOf(await getConfigItems(params))
    .filter(item => item.id !== ciDetail.value.id)
    .filter(item => !peerTypeSet.size || peerTypeSet.has(item.ci_type))
}

function relationTargetLabel(item) {
  const ip = firstHostValue(item, ['private_ip', 'ip_address', 'ip', 'public_ip', 'host_ip'])
  return [item.name, item.ci_type_name || '-', ip].filter(Boolean).join(' / ')
}

function relationCreateErrorText(errors) {
  const messages = []
  const appendMessage = (value) => {
    if (Array.isArray(value)) {
      value.forEach(appendMessage)
    } else if (value && typeof value === 'object') {
      Object.values(value).forEach(appendMessage)
    } else if (value) {
      messages.push(String(value))
    }
  }
  listOf(errors).forEach((item) => appendMessage(item?.errors || item))
  return Array.from(new Set(messages)).join('；')
}

async function fetchAvailableRelationRules() {
  if (!canViewCi.value || !ciDetail.value?.id) {
    relationRules.value = []
    return
  }
  const [outgoing, incoming] = await Promise.all([
    getAvailableCIRelationRules({ ci: ciDetail.value.id, direction: 'outgoing' }),
    getAvailableCIRelationRules({ ci: ciDetail.value.id, direction: 'incoming' }),
  ])
  relationRules.value = [...listOf(outgoing), ...listOf(incoming)]
}

function syncRelationFormWithRules() {
  const options = relationTypeOptions.value
  if (!options.some((item) => item.value === relationForm.relation_type)) {
    relationForm.relation_type = options[0]?.value || ''
  }
  relationForm.targets = []
}

async function openRelationDialog() {
  if (!ciDetail.value?.id) return
  Object.assign(relationForm, {
    direction: 'outgoing',
    relation_type: '',
    targets: [],
    description: '',
  })
  relationDialogVisible.value = true
  await fetchAvailableRelationRules()
  syncRelationFormWithRules()
  await fetchRelationTargets()
}

async function saveRelation() {
  if (!ciDetail.value?.id) return
  const targetIds = Array.from(new Set(listOf(relationForm.targets).filter(Boolean)))
  if (!targetIds.length) return ElMessage.warning('请选择目标资源')
  if (!relationForm.relation_type) return ElMessage.warning('请填写关系类型')
  const currentId = ciDetail.value.id
  if (targetIds.includes(currentId)) return ElMessage.warning('不能将资源关联到自身')
  const relations = targetIds.map(targetId => ({
    source: relationForm.direction === 'outgoing' ? currentId : targetId,
    target: relationForm.direction === 'outgoing' ? targetId : currentId,
    relation_type: relationForm.relation_type,
    description: relationForm.description,
  }))
  relationSaving.value = true
  try {
    const result = await bulkCreateCIRelations({ relations })
    const summary = result?.summary || {}
    const message = `已创建 ${summary.created || 0} 条关系，跳过 ${summary.skipped || 0} 条`
    if (summary.errors) {
      const detail = relationCreateErrorText(result?.errors)
      ElMessage.warning(`${message}，${summary.errors} 条失败${detail ? `：${detail}` : ''}`)
    } else {
      ElMessage.success(message)
    }
    relationDialogVisible.value = false
    await Promise.all([openCiDetail(ciDetail.value, false), fetchViewsSummary(), fetchAuditLogs()])
  } finally {
    relationSaving.value = false
  }
}

async function createSuggestedRelation(row, candidate) {
  if (!row?.ci_id || !candidate?.id || !row.relation_type) return
  const payload = {
    source: row.relation_direction === 'incoming' ? candidate.id : row.ci_id,
    target: row.relation_direction === 'incoming' ? row.ci_id : candidate.id,
    relation_type: row.relation_type,
    evidence_source: 'governance',
    confidence: Number(candidate.score || candidate.confidence || 85),
    evidence: {
      issue_type: row.issue_type,
      relation_rule_id: row.relation_rule_id || '',
      candidate_id: candidate.id,
      candidate_reasons: candidate.reasons || [],
    },
    description: `由孤岛分析推荐创建：${row.ci_name || row.ci_id} ${relationTypeLabel(row.relation_type)} ${candidate.name}`,
  }
  await createCIRelation(payload)
  ElMessage.success('建议关系已创建')
  await Promise.all([fetchGovernance(), fetchDashboard(), fetchViewsSummary()])
}

async function bulkCreateSuggestedRelations() {
  const relations = bulkRelationSuggestions.value.map(({ source, target, relation_type, description }) => ({
    source,
    target,
    relation_type,
    evidence_source: 'governance',
    confidence: 85,
    evidence: { source: 'island_analysis' },
    description,
  }))
  if (!relations.length) return ElMessage.warning('暂无可批量关联的建议')
  await ElMessageBox.confirm(
    `确认批量创建 ${relations.length} 条建议关系吗？重复关系会自动跳过。`,
    '批量关联建议',
    { type: 'warning' },
  )
  const result = await bulkCreateCIRelations({ relations })
  const summary = result?.summary || {}
  const message = `已创建 ${summary.created || 0} 条关系，跳过 ${summary.skipped || 0} 条`
  if (summary.errors) {
    ElMessage.warning(`${message}，${summary.errors} 条失败`)
  } else {
    ElMessage.success(message)
  }
  await Promise.all([fetchGovernance(), fetchDashboard(), fetchViewsSummary(), fetchAuditLogs()])
}

async function mergeDuplicateIssue(row) {
  const duplicateIds = (row.duplicate_ci_ids || []).filter(id => id && id !== row.ci_id)
  if (!row?.ci_id || !duplicateIds.length) {
    return ElMessage.warning('当前重复问题缺少可合并的资源')
  }
  const duplicateNames = (row.duplicate_ci_names || []).filter(name => name && name !== row.ci_name).join('、')
  await ElMessageBox.confirm(
    `确认以「${row.ci_name || row.ci_id}」作为主资源，合并重复资源「${duplicateNames || duplicateIds.join('、')}」吗？合并后重复资源会标记为已下线并保留追溯信息。`,
    '合并重复资源',
    {
      type: 'warning',
      confirmButtonText: '确认合并',
      cancelButtonText: '取消',
    },
  )
  await mergeConfigItemDuplicates(row.ci_id, {
    source_ids: duplicateIds,
    reason: `孤岛分析发现 ${row.duplicate_field_name || row.duplicate_field_code || '唯一字段'} 重复：${row.duplicate_value || '-'}`,
  })
  ElMessage.success('重复资源已合并')
  await Promise.all([fetchGovernance(), fetchDashboard(), fetchRepositorySummary(), fetchLedger(), fetchAuditLogs()])
}

function syncFieldMappingRowsFromConfig(config = {}) {
  const mapping = config.field_mappings || config.field_mapping || []
  if (Array.isArray(mapping)) {
    return mapping
      .filter(item => item && typeof item === 'object')
      .map(item => ({
        target: item.target || item.to || '',
        source: item.source || item.from || '',
        default: item.default ?? '',
        required: !!item.required,
      }))
  }
  if (mapping && typeof mapping === 'object') {
    return Object.entries(mapping).map(([target, source]) => ({
      target,
      source: source ?? '',
      default: '',
      required: false,
    }))
  }
  return []
}

function resetSyncFieldMappings(config = null) {
  const rows = config ? syncFieldMappingRowsFromConfig(config) : defaultSyncFieldMappings
  syncFieldMappings.value = rows.map(item => ({ ...item }))
}

function addSyncFieldMapping() {
  syncFieldMappings.value.push({ target: '', source: '', default: '', required: false })
}

function removeSyncFieldMapping(index) {
  syncFieldMappings.value.splice(index, 1)
}

function buildSyncFieldMappingConfig() {
  const rows = syncFieldMappings.value
    .map(item => ({
      target: String(item.target || '').trim(),
      source: String(item.source || '').trim(),
      default: item.default,
      required: !!item.required,
    }))
    .filter(item => item.target || item.source || item.default || item.required)

  const incomplete = rows.find(item => !item.target || !item.source)
  if (incomplete) {
    throw new Error('字段映射的目标字段和来源字段都需要填写')
  }

  const hasAdvancedConfig = rows.some(item => String(item.default ?? '').trim() || item.required)
  if (hasAdvancedConfig) {
    return rows.map(item => {
      const payload = {
        target: item.target,
        source: item.source,
      }
      if (String(item.default ?? '').trim()) payload.default = item.default
      if (item.required) payload.required = true
      return payload
    })
  }

  return rows.reduce((mapping, item) => {
    mapping[item.target] = item.source
    return mapping
  }, {})
}

function resetSyncJobForm() {
  syncJobEditingId.value = null
  Object.keys(syncJobConfigBase).forEach((key) => {
    delete syncJobConfigBase[key]
  })
  Object.assign(syncJobForm, {
    name: '',
    templateKey: '',
    connector: '',
    source_type: 'manual_import',
    mode: 'manual',
    dry_run: false,
    full_sync: false,
    collection_enabled: false,
    resource_type: '',
    target_ci_type_code: '',
    unique_key: '',
    interval_minutes: 60,
    cloud_account_id: '',
    vsphere_host: '',
    vsphere_username: '',
    vsphere_auth_ref: 'SXDEVOPS_VSPHERE_PROD',
  })
  resetSyncFieldMappings()
}

function syncQuickFieldsFromConfig(config = {}) {
  syncJobForm.connector = String(config.connector || syncJobForm.connector || '').trim().toLowerCase()
  syncJobForm.resource_type = String(config.resource_type || '').trim()
  syncJobForm.target_ci_type_code = String(config.target_ci_type_code || '').trim()
  syncJobForm.unique_key = String(config.unique_key || '').trim()
  syncJobForm.collection_enabled = config.collection_enabled !== false
  const interval = Number(config.interval_minutes || config.schedule_interval_minutes || syncJobForm.interval_minutes || 60)
  syncJobForm.interval_minutes = Number.isFinite(interval) && interval > 0 ? interval : 60
  syncJobForm.cloud_account_id = String(config.cloud_account_id || config.multicloud_account_id || '')
  syncJobForm.vsphere_host = String(config.host || config.vcenter_host || '')
  syncJobForm.vsphere_username = String(config.username || config.user || '')
  syncJobForm.vsphere_auth_ref = String(config.auth_ref || 'SXDEVOPS_VSPHERE_PROD')
}

function inferSyncJobConnector(sourceType = '') {
  const value = String(sourceType || '').toLowerCase()
  if (value.includes('vsphere')) return 'vsphere'
  if (value.startsWith('aliyun_')) return 'aliyun'
  if (value.startsWith('huaweicloud_')) return 'huaweicloud'
  return ''
}

function findSyncTemplateKey(row = {}, config = {}) {
  return phaseOneSyncTemplates.find(item =>
    item.source_type === row.source_type
    || (item.config?.connector === config.connector
      && item.config?.resource_type === config.resource_type
      && item.config?.target_ci_type_code === config.target_ci_type_code)
  )?.key || ''
}

function isPlaceholderVsphereHost(value) {
  const host = String(value || '').trim().toLowerCase()
  return !host || host.includes('example.com') || host.includes('example.local')
}

function mergeSyncQuickConfig(config = {}) {
  const next = { ...config }
  const connector = String(syncJobForm.connector || next.connector || '').trim().toLowerCase()
  if (connector) {
    next.connector = connector
  } else {
    delete next.connector
  }
  const resourceType = String(syncJobForm.resource_type || '').trim()
  if (resourceType) {
    next.resource_type = resourceType
  } else {
    delete next.resource_type
  }
  const targetCiTypeCode = String(syncJobForm.target_ci_type_code || '').trim()
  if (!targetCiTypeCode) throw new Error('请先选择目标资产分类')
  next.target_ci_type_code = targetCiTypeCode
  const uniqueKey = String(syncJobForm.unique_key || '').trim()
  if (!uniqueKey) throw new Error('请填写唯一标识字段')
  next.unique_key = uniqueKey
  const interval = Number(syncJobForm.interval_minutes)
  if (!Number.isFinite(interval) || interval <= 0) throw new Error('请填写有效的同步间隔')
  next.interval_minutes = interval
  next.schedule_label = `每 ${interval} 分钟`
  next.collection_enabled = !!syncJobForm.collection_enabled
  if (isCloudSyncJob.value) {
    const accountId = String(syncJobForm.cloud_account_id || '').trim()
    if (!accountId && !isVsphereSyncJob.value) throw new Error('请选择用于自动注册的云账号，系统会保存为 cloud_account_id。')
    if (accountId) {
      next.cloud_account_id = accountId
      delete next.multicloud_account_id
    } else {
      delete next.cloud_account_id
      delete next.multicloud_account_id
    }
  }
  if (isVsphereSyncJob.value) {
    const accountId = String(syncJobForm.cloud_account_id || '').trim()
    const host = String(syncJobForm.vsphere_host || '').trim()
    const username = String(syncJobForm.vsphere_username || '').trim()
    const authRef = String(syncJobForm.vsphere_auth_ref || '').trim()
    if (!accountId) {
      if (isPlaceholderVsphereHost(host)) throw new Error('请填写真实 vCenter 地址，或选择一个 VMware 资源账号。')
      if (!username) throw new Error('请填写 vSphere 账号，或选择一个 VMware 资源账号。')
      next.host = host
      next.username = username
      next.auth_ref = authRef || 'SXDEVOPS_VSPHERE_PROD'
    } else {
      delete next.host
      delete next.username
      delete next.user
      delete next.auth_ref
    }
    delete next.password
  }
  // 实际运行指标由云账号管理，避免同步任务承担重复且难以发现的配置。
  delete next.prometheus_metrics_enabled
  delete next.prometheus_metric_datasource_id
  delete next.metric_datasource_id
  delete next.prometheus_cpu_window
  delete next.prometheus_root_mountpoint
  delete next.field_mapping
  delete next.field_mappings
  return next
}

function cloudCredentialOptionLabel(item) {
  return [
    item.name,
    item.provider_label || item.provider,
    item.account_name || item.account_id,
    item.default_region,
  ].filter(Boolean).join(' / ')
}

function resetCloudCredentialForm(preset = {}) {
  const provider = preset.provider || (preset.kind === 'private' ? 'vsphere' : 'aliyun')
  const fallbackAuthMode = provider === 'vsphere' ? 'secret' : 'aksk'
  const authMode = preset.auth_mode === 'demo' ? fallbackAuthMode : (preset.auth_mode || fallbackAuthMode)
  cloudCredentialEditingId.value = preset.id || null
  cloudCredentialKind.value = privateCloudProviderSet.has(provider) ? 'private' : 'public'
  Object.assign(cloudCredentialForm, {
    provider,
    name: preset.name || '',
    account_id: preset.account_id || '',
    auth_mode: authMode,
    access_key_id: preset.access_key_id || '',
    access_key_secret: preset.access_key_secret || '',
    project_id: preset.project_id || '',
    role_arn: preset.role_arn || '',
    external_id: preset.external_id || '',
    default_region: preset.default_region || (provider === 'vsphere' ? 'private-cloud-prod' : provider === 'huawei' ? 'cn-north-4' : 'cn-hangzhou'),
    owner: preset.owner || '',
    description: preset.description || '',
    is_enabled: preset.is_enabled !== false,
    demo_mode: false,
    private_cloud_version: preset.private_cloud_version || (provider === 'vsphere' ? defaultPrivateCloudVersion : ''),
    sync_product_keys: preset.sync_product_keys || defaultProductKeysForProvider(provider),
    prometheus_metrics_enabled: preset.prometheus_metrics_enabled !== false,
    metric_datasource_id: preset.metric_datasource_id ? String(preset.metric_datasource_id) : '',
  })
}

function metricDatasourceOptionLabel(item) {
  const suffix = [item?.environment, item?.is_default ? '默认' : ''].filter(Boolean).join(' / ')
  return suffix ? `${item?.name || '-'} / ${suffix}` : (item?.name || '-')
}

async function fetchMetricDatasources() {
  if (metricDatasourceLoading.value) return metricDatasources.value
  metricDatasourceLoading.value = true
  try {
    metricDatasources.value = listOf(await getMetricDataSources({ page_size: 100 }, { skipErrorMessage: true }))
    return metricDatasources.value
  } catch {
    metricDatasources.value = []
    return metricDatasources.value
  } finally {
    metricDatasourceLoading.value = false
  }
}

function openCloudCredentialDialog(preset = {}) {
  if (!canManageCloudAccounts.value) return ElMessage.warning('需要多云账号管理权限')
  resetCloudCredentialForm(preset)
  void fetchMetricDatasources()
  cloudCredentialDialogVisible.value = true
}

function openPublicCloudCredentialDialog() {
  openCloudCredentialDialog({ kind: 'public', provider: 'aliyun' })
}

function openVsphereCredentialDialog() {
  openCloudCredentialDialog({ kind: 'private', provider: 'vsphere' })
}

function openCloudCredentialEditDialog(credential) {
  if (!canManageCloudAccounts.value) return ElMessage.warning('需要多云账号管理权限')
  const provider = String(credential?.provider || 'aliyun').toLowerCase()
  const tags = credential?.tags || {}
  resetCloudCredentialForm({
    id: credential?.id,
    kind: privateCloudProviderSet.has(provider) ? 'private' : 'public',
    provider,
    name: credential?.name || '',
    account_id: credential?.account_id || '',
    auth_mode: credential?.auth_mode || (provider === 'vsphere' ? 'secret' : 'aksk'),
    access_key_id: credential?.access_key_id || '',
    access_key_secret: '',
    project_id: credential?.project_id || '',
    role_arn: credential?.role_arn || '',
    external_id: credential?.external_id || '',
    default_region: credential?.default_region || '',
    owner: credential?.owner || '',
    description: credential?.description || '',
    is_enabled: credential?.is_enabled !== false,
    demo_mode: false,
    private_cloud_version: tags.private_cloud_version || (provider === 'vsphere' ? defaultPrivateCloudVersion : ''),
    sync_product_keys: credentialProductKeys(credential),
    prometheus_metrics_enabled: tags.prometheus_metrics_enabled !== false,
    metric_datasource_id: tags.metric_datasource_id || '',
  })
  cloudCredentialForm.sync_product_keys = credentialProductKeys(credential)
  cloudCredentialDialogVisible.value = true
}

let cloudCredentialRequest = null

async function fetchCloudCredentials(force = false) {
  if (cloudCredentialRequest) return cloudCredentialRequest
  if (cloudCredentialLoaded.value && !force) return cloudCredentials.value
  cloudCredentialLoading.value = true
  cloudCredentialRequest = (async () => {
    const response = await getCloudCredentials({ page_size: 100 }, { skipErrorMessage: true })
    cloudCredentials.value = listOf(response)
    cloudCredentialLoaded.value = true
    return cloudCredentials.value
  })()
  try {
    return await cloudCredentialRequest
  } catch {
    cloudCredentials.value = []
    cloudCredentialLoaded.value = true
    return cloudCredentials.value
  } finally {
    cloudCredentialRequest = null
    cloudCredentialLoading.value = false
  }
}

async function saveCloudCredential() {
  if (!canManageCloudAccounts.value) return ElMessage.warning('需要多云账号管理权限')
  const name = String(cloudCredentialForm.name || '').trim()
  const defaultRegion = String(cloudCredentialForm.default_region || '').trim()
  const isVsphere = cloudCredentialForm.provider === 'vsphere'
  const requiresCloudAuth = true
  const productKeys = normalizeCredentialProductKeys(cloudCredentialForm.provider, cloudCredentialForm.sync_product_keys)
  if (!name) return ElMessage.warning('请填写账号名称')
  if (!defaultRegion) return ElMessage.warning('请填写默认地域')
  if (isVsphere && !String(cloudCredentialForm.account_id || '').trim()) return ElMessage.warning('请填写 vCenter 或 ESXi 地址')
  if (isVsphere && !String(cloudCredentialForm.private_cloud_version || '').trim()) return ElMessage.warning('请选择私有云版本')
  if (cloudCredentialForm.provider === 'huawei' && requiresCloudAuth && !String(cloudCredentialForm.project_id || '').trim()) return ElMessage.warning('请填写 Project ID')
  if (isPublicCloudCredentialForm.value && !productKeys.length) return ElMessage.warning('请选择需要同步的云产品')
  if (requiresCloudAuth) {
    if (!String(cloudCredentialForm.access_key_id || '').trim()) return ElMessage.warning(isVsphere ? '请填写 VMware 用户名' : '请填写 AccessKey ID')
    if (!cloudCredentialEditingId.value && !String(cloudCredentialForm.access_key_secret || '').trim()) return ElMessage.warning(
      isVsphere ? '请填写 VMware 密码' : cloudCredentialForm.provider === 'huawei' ? '请填写 Secret Key' : '请填写 AccessKey Secret'
    )
  }
  cloudCredentialSaving.value = true
  try {
    const payload = {
      provider: cloudCredentialForm.provider,
      name,
      account_id: String(cloudCredentialForm.account_id || '').trim(),
      auth_mode: cloudCredentialForm.auth_mode === 'demo'
        ? (isVsphere ? 'secret' : 'aksk')
        : cloudCredentialForm.auth_mode,
      access_key_id: String(cloudCredentialForm.access_key_id || '').trim(),
      access_key_secret: String(cloudCredentialForm.access_key_secret || '').trim(),
      project_id: String(cloudCredentialForm.project_id || '').trim(),
      role_arn: String(cloudCredentialForm.role_arn || '').trim(),
      external_id: String(cloudCredentialForm.external_id || '').trim(),
      default_region: defaultRegion,
      owner: String(cloudCredentialForm.owner || '').trim(),
      description: String(cloudCredentialForm.description || '').trim(),
      tags: {
        sync_scope: isVsphere ? 'private_cloud' : 'public_cloud',
        sync_product_keys: productKeys,
        prometheus_metrics_enabled: !!cloudCredentialForm.prometheus_metrics_enabled,
        metric_datasource_id: String(cloudCredentialForm.metric_datasource_id || '').trim(),
        ...(isVsphere ? { private_cloud_version: cloudCredentialForm.private_cloud_version } : {}),
      },
      is_enabled: cloudCredentialForm.is_enabled,
      demo_mode: false,
    }
    const saved = cloudCredentialEditingId.value
      ? await updateCloudCredential(cloudCredentialEditingId.value, payload)
      : await createCloudCredential(payload)
    cloudCredentialDialogVisible.value = false
    cloudCredentialLoaded.value = false
    await fetchCloudCredentials(true)
    const refreshedCredential = cloudCredentials.value.find(item => String(item.id) === String(saved?.id)) || saved
    const createdSyncCount = cloudCredentialEditingId.value && canManageSync.value
      ? await ensureCredentialSelectedSyncJobs(refreshedCredential)
      : 0
    const card = syncAccountCards.value.find(item => String(item.id) === String(saved?.id))
    if (card) focusSyncAccountCard(card)
    if (cloudCredentialEditingId.value) {
      ElMessage.success(createdSyncCount ? `云账号已更新，已补齐 ${createdSyncCount} 个自动同步任务` : '云账号已更新')
    } else {
      await bootstrapCredentialSync(saved)
    }
  } finally {
    cloudCredentialSaving.value = false
  }
}

function openSyncJobDialog(row = null, preset = {}) {
  if (!row) {
    resetSyncJobForm()
    if (preset.templateKey) {
      syncJobForm.templateKey = preset.templateKey
      applySyncTemplate(preset.templateKey)
    }
    if (preset.cloud_account_id) {
      syncJobForm.cloud_account_id = String(preset.cloud_account_id)
    }
  } else {
    syncJobEditingId.value = row.id
    const config = row.config || {}
    Object.keys(syncJobConfigBase).forEach((key) => {
      delete syncJobConfigBase[key]
    })
    Object.assign(syncJobConfigBase, clonePlainObject(config))
    Object.assign(syncJobForm, {
      name: row.name || '',
      templateKey: findSyncTemplateKey(row, config),
      connector: String(config.connector || inferSyncJobConnector(row.source_type)).toLowerCase(),
      source_type: row.source_type || 'manual_import',
      mode: row.mode || 'manual',
      dry_run: !!row.dry_run,
      full_sync: !!config.full_sync,
    })
    syncQuickFieldsFromConfig(config)
    resetSyncFieldMappings(config)
  }
  syncJobDialogVisible.value = true
  if (isCloudSyncJob.value) fetchCloudCredentials()
}

function defaultSyncTemplateKeyForCredential(credential) {
  const provider = String(credential?.provider || '').toLowerCase()
  if (provider === 'vsphere') return 'vsphere_vm'
  if (provider === 'huawei' || provider === 'huaweicloud') return 'huaweicloud_ecs'
  if (provider === 'aliyun') return 'aliyun_ecs'
  return 'aliyun_ecs'
}

function openSyncJobDialogForCredential(credential) {
  openSyncJobDialog(null, {
    templateKey: defaultSyncTemplateKeyForCredential(credential),
    cloud_account_id: credential?.id ? String(credential.id) : '',
  })
}

function openVsphereSyncJobDialog() {
  openSyncJobDialog(null, { templateKey: 'vsphere_vm' })
}

function openSyncAccountTaskDrawer(item) {
  syncAccountTaskDrawerAccountId.value = String(item?.id || '')
  syncAccountTaskDrawerVisible.value = true
}

function providerSyncTemplateKeys(provider) {
  const value = String(provider || '').toLowerCase()
  if (value === 'aliyun') {
    return defaultProductKeysForProvider('aliyun')
  }
  if (value === 'huawei' || value === 'huaweicloud') {
    return defaultProductKeysForProvider('huawei')
  }
  if (value === 'vsphere') {
    return ['vsphere_vm']
  }
  return []
}

function credentialSyncTemplates(credential) {
  const provider = String(credential?.provider || '').toLowerCase()
  const keys = new Set(publicCloudProviderSet.has(provider) ? credentialProductKeys(credential) : providerSyncTemplateKeys(provider))
  return phaseOneSyncTemplates.filter(item => keys.has(item.key))
}

function clonePlainObject(value) {
  return JSON.parse(JSON.stringify(value || {}))
}

function buildCredentialSyncJobPayload(credential, template) {
  const config = clonePlainObject(template.config)
  const accountId = String(credential?.id || '').trim()
  const sourceAccount = credential?.account_name || credential?.name || credential?.account_id || ''
  config.cloud_account_id = accountId
  config.collection_enabled = true
  config.source_account = sourceAccount
  config.account_id = credential?.account_id || config.account_id || ''
  config.provider = credential?.provider || config.provider || ''
  if (credential?.default_region) {
    config.source_region = credential.default_region
    config.region_id = credential.default_region
  }
  delete config.access_key_id
  delete config.access_key_secret
  delete config.secret_key
  return {
    name: `${credential?.name || '云账号'} / ${template.name.replace(/模板$/, '')}`,
    source_type: template.source_type,
    mode: 'scheduled',
    dry_run: false,
    config: {
      ...config,
      full_sync: template.full_sync !== false,
    },
  }
}

async function enableCredentialSyncJobs(credential, options = {}) {
  if (!credential?.id) return ElMessage.warning('请先选择一个云账号')
  const templates = credentialSyncTemplates(credential)
  if (!templates.length) return ElMessage.warning('该云厂商暂未内置 CMDB 自动注册模板')
  if (!options.skipConfirm) {
    const taskNames = templates.map(item => item.label || item.name || item.key).join('、')
    await ElMessageBox.confirm(
      `将为「${credential.name}」创建或更新 ${templates.length} 个同步任务：${taskNames}。${options.runImmediately ? '保存任务后会立即执行一次。' : '后续可在账号卡片中手工执行。'}`,
      '启用账号同步',
      { type: 'warning' },
    )
  }
  syncAccountConfiguring.value = true
  try {
    await fetchSyncJobs()
    let created = 0
    let updated = 0
    const targetJobIds = []
    for (const template of templates) {
      const payload = buildCredentialSyncJobPayload(credential, template)
      const existing = syncJobs.value.find(row => row.source_type === template.source_type && syncJobAccountId(row) === String(credential.id))
      if (existing?.id) {
        const saved = await updateSyncJob(existing.id, payload)
        targetJobIds.push(saved?.id || existing.id)
        updated += 1
      } else {
        const saved = await createSyncJob(payload)
        if (saved?.id) targetJobIds.push(saved.id)
        created += 1
      }
    }
    await Promise.all([fetchSyncJobs(), fetchCollectionSummary(true)])
    let runCount = 0
    let runFailed = 0
    if (options.runImmediately) {
      for (const id of targetJobIds) {
        try {
          const result = await runSyncJob(id)
          const failedCount = Number(result?.summary?.fail || 0) + Number(result?.summary?.conflict || 0)
          if (failedCount) {
            runFailed += 1
          } else {
            runCount += 1
          }
        } catch {
          runFailed += 1
        }
      }
      await Promise.all([fetchSyncJobs(), fetchCollectionSummary(true), fetchLedger()])
    }
    if (!options.skipMessage) {
      const runText = options.runImmediately ? `，已执行 ${runCount} 个${runFailed ? `，失败 ${runFailed} 个` : ''}` : ''
      const message = `账号同步已启用：新建 ${created} 个，更新 ${updated} 个${runText}`
      ;(runFailed ? ElMessage.warning : ElMessage.success)(message)
    }
    return { created, updated, runCount, runFailed }
  } finally {
    syncAccountConfiguring.value = false
  }
}

async function ensureCredentialSelectedSyncJobs(credential) {
  if (!credential?.id) return 0
  const templates = credentialSyncTemplates(credential)
  if (!templates.length) return 0
  await fetchSyncJobs()
  let created = 0
  let updated = 0
  const selectedSourceTypes = new Set(templates.map(template => template.source_type))
  const accountJobs = syncJobs.value.filter(row => syncJobAccountId(row) === String(credential.id))
  const updateCollectionState = async (job, enabled) => {
    if (!job?.id || (job.config?.collection_enabled !== false) === enabled) return false
    await updateSyncJob(job.id, {
      name: job.name,
      source_type: job.source_type,
      mode: enabled ? 'scheduled' : 'manual',
      dry_run: !!job.dry_run,
      config: { ...clonePlainObject(job.config), collection_enabled: enabled },
    })
    updated += 1
    return true
  }
  for (const template of templates) {
    const matchingJobs = accountJobs.filter(row => row.source_type === template.source_type)
    const existing = matchingJobs[0]
    if (existing?.id) {
      await updateCollectionState(existing, true)
      for (const duplicate of matchingJobs.slice(1)) {
        await updateCollectionState(duplicate, false)
      }
      continue
    }
    await createSyncJob(buildCredentialSyncJobPayload(credential, template))
    created += 1
  }
  for (const job of accountJobs) {
    if (!job?.id || selectedSourceTypes.has(job.source_type)) continue
    await updateCollectionState(job, false)
  }
  if (created || updated) {
    await Promise.all([fetchSyncJobs(), fetchCollectionSummary(true)])
  }
  return created + updated
}

async function runCredentialSelectedSyncJobs(credential) {
  if (!credential?.id) return ElMessage.warning('请先选择一个云账号')
  syncAccountConfiguring.value = true
  try {
    await ensureCredentialSelectedSyncJobs(credential)
    await fetchSyncJobs()
    const templates = credentialSyncTemplates(credential)
    const jobs = templates
      .map(template => syncJobs.value.find(row => row.source_type === template.source_type && syncJobAccountId(row) === String(credential.id)))
      .filter(row => row?.id)
    if (!jobs.length) return ElMessage.warning('当前账号暂无可手工同步的任务')
    jobs.forEach(markSyncJobRunning)
    let runCount = 0
    let runFailed = 0
    for (const job of jobs) {
      try {
        const result = await runSyncJob(job.id)
        const failedCount = Number(result?.summary?.fail || 0) + Number(result?.summary?.conflict || 0)
        if (failedCount) {
          runFailed += 1
        } else {
          runCount += 1
        }
      } catch {
        runFailed += 1
      }
    }
    await Promise.all([fetchSyncJobs(), fetchCollectionSummary(true), fetchLedger()])
    const message = `手工同步已执行 ${runCount} 个${runFailed ? `，失败 ${runFailed} 个` : ''}`
    ;(runFailed ? ElMessage.warning : ElMessage.success)(message)
  } finally {
    syncAccountConfiguring.value = false
  }
}

async function ensureCredentialSyncTaskJob(task) {
  const credential = task?.credential || syncAccountTaskDrawerItem.value?.credential
  const template = task?.template
  if (task?.job?.id) return task.job
  if (!credential?.id || !template) throw new Error('请先选择一个云账号同步任务')
  await fetchSyncJobs()
  const existing = syncJobs.value.find(row => row.source_type === template.source_type && syncJobAccountId(row) === String(credential.id))
  if (existing?.id) return existing
  const saved = await createSyncJob(buildCredentialSyncJobPayload(credential, template))
  await Promise.all([fetchSyncJobs(), fetchCollectionSummary(true)])
  return saved
}

async function runCredentialSyncTask(task) {
  syncAccountConfiguring.value = true
  try {
    const job = await ensureCredentialSyncTaskJob(task)
    markSyncJobRunning(job)
    await executeSyncJob(job)
  } catch (error) {
    ElMessage.warning(error?.message || '同步任务准备失败')
  } finally {
    syncAccountConfiguring.value = false
  }
}

function markSyncJobRunning(job) {
  if (!job) return
  job.status = 'running'
  job.error_message = ''
}

function openCredentialSyncTaskDialog(task) {
  if (task?.job) {
    openSyncJobDialog(task.job)
    return
  }
  const credential = task?.credential || syncAccountTaskDrawerItem.value?.credential
  const template = task?.template
  if (!credential?.id || !template?.key) return ElMessage.warning('请先选择一个云账号同步任务')
  openSyncJobDialog(null, {
    templateKey: template.key,
    cloud_account_id: String(credential.id),
  })
}

async function bootstrapCredentialSync(credential) {
  if (!credential?.id) return
  let inventoryMessage = ''
  try {
    const result = await syncCloudCredential(credential.id)
    inventoryMessage = result?.message || ''
  } catch (error) {
    inventoryMessage = error?.message || '账号库存同步未完成'
  }
  if (!canManageSync.value) {
    ElMessage.success(inventoryMessage || '账号已保存，已触发资源库存同步')
    return
  }
  const result = await enableCredentialSyncJobs(credential, { skipConfirm: true, skipMessage: true, runImmediately: true })
  const count = result?.created + result?.updated || 0
  ElMessage.success(`账号已接入，已编排 ${count} 个自动注册任务并开始拉取主要资源`)
}

function applySyncTemplate(templateKey) {
  const template = phaseOneSyncTemplates.find(item => item.key === templateKey)
  if (!template) return
  Object.keys(syncJobConfigBase).forEach((key) => {
    delete syncJobConfigBase[key]
  })
  Object.assign(syncJobConfigBase, clonePlainObject(template.config))
  Object.assign(syncJobForm, {
    name: syncJobForm.name || template.name,
    connector: String(template.config.connector || inferSyncJobConnector(template.source_type)).toLowerCase(),
    source_type: template.source_type,
    mode: template.mode,
    dry_run: false,
    full_sync: template.full_sync,
  })
  syncQuickFieldsFromConfig(template.config)
  resetSyncFieldMappings(template.config)
  if (isCloudSyncJob.value) fetchCloudCredentials()
}

async function saveSyncJob() {
  if (!syncJobForm.name.trim()) return ElMessage.warning('请填写任务名称')
  if (!syncJobForm.source_type.trim()) return ElMessage.warning('请填写来源类型')
  let config = {}
  try {
    config = clonePlainObject(syncJobConfigBase)
    config = mergeSyncQuickConfig(config)
    const fieldMapping = buildSyncFieldMappingConfig()
    if (Array.isArray(fieldMapping) ? fieldMapping.length : Object.keys(fieldMapping).length) {
      config.field_mapping = fieldMapping
    }
  } catch (error) {
    return ElMessage.warning(error.message)
  }
  saving.value = true
  try {
    const payload = {
      name: syncJobForm.name.trim(),
      source_type: syncJobForm.source_type.trim(),
      mode: syncJobEditingId.value ? (syncJobForm.collection_enabled ? 'scheduled' : 'manual') : syncJobForm.mode,
      dry_run: syncJobForm.dry_run,
      config: {
        ...config,
        full_sync: !!syncJobForm.full_sync,
      },
    }
    if (syncJobEditingId.value) {
      await updateSyncJob(syncJobEditingId.value, payload)
      ElMessage.success('同步任务已更新')
    } else {
      await createSyncJob(payload)
      ElMessage.success('同步任务已创建')
    }
    syncJobDialogVisible.value = false
    await Promise.all([fetchSyncJobs(), fetchCollectionSummary(true)])
  } finally {
    saving.value = false
  }
}

async function deleteCloudCredentialRow(item) {
  if (!item?.credential?.id) return
  await ElMessageBox.confirm(`确认删除云账号“${item.title || item.credential.name}”吗？该账号下的环境和资源会一并清理。`, '删除云账号', { type: 'warning' })
  if (canManageSync.value) {
    await fetchSyncJobs()
  }
  await deleteCloudCredential(item.credential.id)
  if (canManageSync.value) {
    const relatedJobs = syncJobs.value.filter(row => syncJobAccountId(row) === String(item.id))
    await Promise.all(relatedJobs.map(row => deleteSyncJob(row.id).catch(() => null)))
  }
  cloudCredentialLoaded.value = false
  syncAccountTaskDrawerAccountId.value = syncAccountTaskDrawerAccountId.value === String(item.id) ? '' : syncAccountTaskDrawerAccountId.value
  await Promise.all([
    fetchCloudCredentials(true),
    fetchSyncJobs(),
    fetchCollectionSummary(true),
  ])
  ElMessage.success('云账号已删除')
}

function resetSourceMappingForm() {
  sourceMappingEditingId.value = null
  Object.assign(sourceMappingForm, {
    ci: '',
    source_type: '',
    source_account: '',
    source_region: '',
    source_unique_id: '',
    sync_status: 'success',
    rawPayloadText: '{}',
  })
}

async function openSourceMappingDialog(row = null) {
  if (!ledgerItems.value.length) {
    await fetchLedger()
  }
  if (!row) {
    resetSourceMappingForm()
  } else {
    sourceMappingEditingId.value = row.id
    Object.assign(sourceMappingForm, {
      ci: row.ci || '',
      source_type: row.source_type || '',
      source_account: row.source_account || '',
      source_region: row.source_region || '',
      source_unique_id: row.source_unique_id || '',
      sync_status: row.sync_status || 'success',
      rawPayloadText: JSON.stringify(row.raw_payload || {}, null, 2),
    })
  }
  sourceMappingDialogVisible.value = true
}

function openSourceMappingDetail(row) {
  sourceMappingDetailRow.value = row || null
  sourceMappingDetailVisible.value = true
}

async function updateSourceMappingStatus(row, status) {
  if (!row?.id || !status || row.sync_status === status) return
  const action = sourceMappingStatusActions.find(item => item.value === status)
  const sourceIdentity = `${row.source_type || '-'}:${row.source_unique_id || '-'}`
  await ElMessageBox.confirm(
    `确认将来源映射「${sourceIdentity}」标记为「${action?.text || status}」吗？`,
    '更新来源映射状态',
    { type: action?.type || 'warning' },
  )
  sourceMappingLoading.value = true
  try {
    const updated = await updateSourceMapping(row.id, { sync_status: status })
    ElMessage.success(`来源映射已标记为${action?.text || status}`)
    if (sourceMappingDetailRow.value?.id === row.id) {
      sourceMappingDetailRow.value = { ...sourceMappingDetailRow.value, ...(updated || {}), sync_status: status }
    }
    await Promise.all([fetchSourceMappings(), fetchDashboard(), fetchGovernance(), fetchAuditLogs()])
  } finally {
    sourceMappingLoading.value = false
  }
}

function buildSourceMappingPayload() {
  if (!sourceMappingForm.ci) throw new Error('请选择关联资源')
  if (!String(sourceMappingForm.source_type || '').trim()) throw new Error('请填写来源类型')
  if (!String(sourceMappingForm.source_unique_id || '').trim()) throw new Error('请填写来源唯一标识')
  const rawPayload = parseJsonObject(sourceMappingForm.rawPayloadText, '原始数据', {})
  return {
    ci: sourceMappingForm.ci,
    source_type: sourceMappingForm.source_type.trim(),
    source_account: sourceMappingForm.source_account.trim(),
    source_region: sourceMappingForm.source_region.trim(),
    source_unique_id: sourceMappingForm.source_unique_id.trim(),
    sync_status: sourceMappingForm.sync_status || 'success',
    raw_payload: rawPayload,
  }
}

async function saveSourceMapping() {
  let payload = {}
  try {
    payload = buildSourceMappingPayload()
  } catch (error) {
    return ElMessage.warning(error.message)
  }
  saving.value = true
  try {
    if (sourceMappingEditingId.value) {
      await updateSourceMapping(sourceMappingEditingId.value, payload)
      ElMessage.success('来源映射已更新')
    } else {
      await createSourceMapping(payload)
      ElMessage.success('来源映射已创建')
    }
    sourceMappingDialogVisible.value = false
    await Promise.all([fetchSourceMappings(), fetchDashboard(), fetchGovernance()])
  } finally {
    saving.value = false
  }
}

async function deleteSourceMappingRow(row) {
  await ElMessageBox.confirm(`确认删除来源映射“${row.source_type}:${row.source_unique_id}”吗？删除后该资源将无法通过该外部 ID 自动对账。`, '删除来源映射', { type: 'warning' })
  await deleteSourceMapping(row.id)
  ElMessage.success('来源映射已删除')
  await Promise.all([fetchSourceMappings(), fetchDashboard(), fetchGovernance()])
}

function resetModelForm() {
  modelEditingId.value = null
  Object.assign(modelForm, {
    name: '',
    code: '',
    group: ciModelGroups.value[0]?.id || '',
    icon: 'SetUp',
    color: '#3b82f6',
    description: '',
  })
}

function openModelDialog(row = null) {
  if (!row) {
    resetModelForm()
  } else {
    modelEditingId.value = row.id
    const icon = normalizeModelIconValue(row.icon || 'SetUp')
    Object.assign(modelForm, {
      name: row.name || '',
      code: row.code || '',
      group: row.group || '',
      icon,
      color: row.color || modelIconColor(icon),
      description: row.description || '',
    })
  }
  modelDialogVisible.value = true
}

async function openModelConfigDrawer(row) {
  if (!row?.id) return
  selectedModelId.value = row.id
  await fetchTypesAndFields()
  modelConfigDrawerVisible.value = true
}

async function saveModel() {
  if (!modelForm.name) return ElMessage.warning('请填写模型名称')
  saving.value = true
  try {
    const icon = normalizeModelIconValue(modelForm.icon)
    const payload = {
      name: modelForm.name,
      code: modelForm.code,
      group: modelForm.group || null,
      icon,
      color: modelForm.color || '#3b82f6',
      description: modelForm.description,
      is_active: true,
    }
    if (modelEditingId.value) {
      await updateCIType(modelEditingId.value, payload)
      ElMessage.success('模型已更新')
    } else {
      await createCIType(payload)
      ElMessage.success('模型已创建')
    }
    modelDialogVisible.value = false
    await fetchTypesAndFields()
  } finally {
    saving.value = false
  }
}

function resetModelGroupForm() {
  modelGroupEditingId.value = null
  Object.assign(modelGroupForm, {
    name: '',
    code: '',
    description: '',
    sort_order: ciModelGroups.value.length + 1,
    is_active: true,
  })
}

function openModelGroupDialog(row = null) {
  if (!row) {
    resetModelGroupForm()
  } else {
    modelGroupEditingId.value = row.id
    Object.assign(modelGroupForm, {
      name: row.name || '',
      code: row.code || '',
      description: row.description || '',
      sort_order: row.sort_order || 0,
      is_active: row.is_active !== false,
    })
  }
  modelGroupDialogVisible.value = true
}

async function saveModelGroup() {
  if (!modelGroupForm.name.trim()) return ElMessage.warning('请填写分组名称')
  if (!modelGroupForm.code.trim()) return ElMessage.warning('请填写分组编码')
  const payload = {
    name: modelGroupForm.name.trim(),
    code: modelGroupForm.code.trim(),
    description: modelGroupForm.description || '',
    sort_order: modelGroupForm.sort_order || 0,
    is_active: modelGroupForm.is_active,
  }
  saving.value = true
  try {
    if (modelGroupEditingId.value) {
      await updateCIModelGroup(modelGroupEditingId.value, payload)
      ElMessage.success('模型分组已更新')
    } else {
      await createCIModelGroup(payload)
      ElMessage.success('模型分组已创建')
    }
    modelGroupDialogVisible.value = false
    await Promise.all([fetchTypesAndFields(), fetchRepositorySummary()])
  } finally {
    saving.value = false
  }
}

async function toggleModelGroupActive(row) {
  await updateCIModelGroup(row.id, { is_active: !row.is_active })
  ElMessage.success(row.is_active ? '模型分组已停用' : '模型分组已启用')
  await Promise.all([fetchTypesAndFields(), fetchRepositorySummary()])
}

async function deleteModelGroupRow(row) {
  await ElMessageBox.confirm(`确认删除模型分组「${row.name}」吗？内置分组或仍包含模型时后端会阻止删除。`, '删除模型分组', { type: 'warning' })
  await deleteCIModelGroup(row.id)
  ElMessage.success('模型分组已删除')
  await Promise.all([fetchTypesAndFields(), fetchRepositorySummary()])
}

async function refreshBuiltinCmdb() {
  builtinRefreshing.value = true
  try {
    const response = await ensureCmdbBuiltins()
    const summary = response?.summary || {}
    ElMessage.success(
      `内置模板已刷新：${summary.types || 0} 个模型、${summary.fields || 0} 个字段、${summary.sync_jobs || 0} 个同步模板`
    )
    await Promise.all([
      fetchTypesAndFields(),
      fetchSyncJobs(),
      fetchCollectionSummary(true),
      fetchThresholdManagement(),
      fetchRepositorySummary(),
      fetchAuditLogs(),
    ])
  } finally {
    builtinRefreshing.value = false
  }
}

function resetFieldForm() {
  fieldEditingId.value = null
  Object.assign(fieldForm, {
    ci_type: selectedModelId.value || ciTypes.value[0]?.id || '',
    name: '',
    code: '',
    field_type: 'string',
    field_group: '',
    required: false,
    unique: false,
    is_display: true,
    options: [],
    sync_mode: 'source',
    is_active: true,
    sort_order: 0,
  })
}

function openFieldDialog(row = null) {
  if (!row) {
    resetFieldForm()
  } else {
    fieldEditingId.value = row.id
    Object.assign(fieldForm, {
      ci_type: row.ci_type,
      name: row.name || '',
      code: row.code || '',
      field_type: row.field_type || 'string',
      field_group: row.field_group || '',
      required: !!row.required,
      unique: !!row.unique,
      is_display: row.is_display !== false,
      options: normalizeFieldOptions(row.options),
      sync_mode: row.sync_mode || 'source',
      is_active: row.is_active !== false,
      sort_order: row.sort_order || 0,
    })
  }
  fieldDialogVisible.value = true
}

function isEnumFieldType(fieldType) {
  return ['enum', 'multi_enum'].includes(fieldType)
}

function normalizeFieldOptions(options) {
  return (Array.isArray(options) ? options : []).map((item) => {
    if (item && typeof item === 'object') {
      const label = item.label ?? item.name ?? item.value ?? item.key ?? ''
      return { label: String(label) }
    }
    return { label: String(item ?? '') }
  })
}

function onFieldTypeChange(fieldType) {
  if (isEnumFieldType(fieldType) && !fieldForm.options.length) addFieldOption()
}

function addFieldOption() {
  fieldForm.options.push({ label: '' })
}

function removeFieldOption(index) {
  fieldForm.options.splice(index, 1)
}

async function saveField() {
  if (!fieldForm.ci_type) return ElMessage.warning('请选择模型')
  if (!fieldForm.name || !fieldForm.code) return ElMessage.warning('请填写字段名称和字段编码')
  if (baseAttributeFieldCodes.has(String(fieldForm.code).trim().toLowerCase())) {
    return ElMessage.warning('部门是资产基础属性，不需要配置为模型字段')
  }
  const options = normalizeFieldOptions(fieldForm.options)
  if (isEnumFieldType(fieldForm.field_type)) {
    const invalidOption = options.find(option => !option.label.trim())
    if (invalidOption) return ElMessage.warning('请填写枚举选项名称')
    const uniqueValues = new Set(options.map(option => option.label.trim()))
    if (uniqueValues.size !== options.length) return ElMessage.warning('枚举选项值不能重复')
    if (!options.length) return ElMessage.warning('请至少添加一个枚举选项')
  }
  saving.value = true
  try {
    const payload = {
      ci_type: fieldForm.ci_type,
      name: fieldForm.name,
      code: fieldForm.code,
      field_type: fieldForm.field_type,
      field_group: fieldForm.field_group,
      required: fieldForm.required,
      unique: fieldForm.unique,
      is_display: fieldForm.is_display,
      options: isEnumFieldType(fieldForm.field_type) ? options.map(option => ({ value: option.label.trim(), label: option.label.trim() })) : [],
      sync_mode: fieldForm.sync_mode || 'source',
      sort_order: fieldForm.sort_order,
      is_active: fieldForm.is_active,
    }
    if (fieldEditingId.value) {
      await updateCIField(fieldEditingId.value, payload)
      ElMessage.success('字段已更新')
    } else {
      await createCIField(payload)
      ElMessage.success('字段已创建')
    }
    fieldDialogVisible.value = false
    await Promise.all([
      fetchTypesAndFields(),
      fetchLedger({ preservePage: true, refreshTree: false }),
    ])
  } finally {
    saving.value = false
  }
}

async function toggleFieldActive(row) {
  await updateCIField(row.id, { is_active: !row.is_active })
  ElMessage.success(row.is_active ? '字段已停用' : '字段已启用')
  await fetchTypesAndFields()
}

async function deleteFieldRow(row) {
  await ElMessageBox.confirm(`确认删除字段「${row.name}」吗？内置字段后端会阻止删除，已被资源使用的字段建议先停用观察。`, '删除模型字段', { type: 'warning' })
  await deleteCIField(row.id)
  ElMessage.success('字段已删除')
  await fetchTypesAndFields()
}

function resetRelationRuleForm() {
  relationRuleEditingId.value = null
  Object.assign(relationRuleForm, {
    source_type: selectedModelId.value || ciTypes.value[0]?.id || '',
    target_type: '',
    relation_type: 'runs_on',
    direction: 'outgoing',
    required: false,
    multiple: true,
    description: '',
    is_active: true,
  })
}

function openRelationRuleDialog(row = null) {
  if (!row) {
    resetRelationRuleForm()
  } else {
    relationRuleEditingId.value = row.id
    Object.assign(relationRuleForm, {
      source_type: row.source_type,
      target_type: row.target_type,
      relation_type: row.relation_type || 'runs_on',
      direction: row.direction || 'outgoing',
      required: !!row.required,
      multiple: row.multiple !== false,
      description: row.description || '',
      is_active: row.is_active !== false,
    })
  }
  relationRuleDialogVisible.value = true
}

async function saveRelationRule() {
  if (!relationRuleForm.source_type) return ElMessage.warning('请选择源模型')
  if (!relationRuleForm.target_type) return ElMessage.warning('请选择目标模型')
  if (!relationRuleForm.relation_type) return ElMessage.warning('请填写关系类型')
  const payload = {
    source_type: relationRuleForm.source_type,
    target_type: relationRuleForm.target_type,
    relation_type: relationRuleForm.relation_type,
    direction: relationRuleForm.direction || 'outgoing',
    required: relationRuleForm.required,
    multiple: relationRuleForm.multiple,
    description: relationRuleForm.description || '',
    is_active: relationRuleForm.is_active,
  }
  saving.value = true
  try {
    if (relationRuleEditingId.value) {
      await updateCIRelationRule(relationRuleEditingId.value, payload)
      ElMessage.success('关系规则已更新')
    } else {
      await createCIRelationRule(payload)
      ElMessage.success('关系规则已创建')
    }
    relationRuleDialogVisible.value = false
    await Promise.all([fetchTypesAndFields(), fetchGovernance()])
  } finally {
    saving.value = false
  }
}

async function toggleRelationRuleActive(row) {
  await updateCIRelationRule(row.id, { is_active: !row.is_active })
  ElMessage.success(row.is_active ? '关系规则已停用' : '关系规则已启用')
  await Promise.all([fetchTypesAndFields(), fetchGovernance()])
}

async function deleteRelationRuleRow(row) {
  await ElMessageBox.confirm(`确认删除「${row.source_type_name || modelName(row.source_type)} -> ${row.target_type_name || modelName(row.target_type)}」关系规则吗？`, '删除关系规则', { type: 'warning' })
  await deleteCIRelationRule(row.id)
  ElMessage.success('关系规则已删除')
  await Promise.all([fetchTypesAndFields(), fetchGovernance()])
}

async function openCompletionDialog(row) {
  if (!resourceNodeTree.value.length) await fetchResourceNodeTree()
  completionIssueRow.value = row
  Object.assign(completionForm, {
    business_line: row.ci_business_line || '',
    environment: row.ci_environment || '',
    admin_user: row.ci_admin_user || '',
    department: row.ci_department || row.ci_attributes?.department || '',
    attributesText: JSON.stringify(row.ci_attributes || {}, null, 2),
    note: '关键字段已补齐',
  })
  completionDialogVisible.value = true
}

async function openBulkCompletionDialog() {
  if (!completionSelection.value.length) return
  if (!resourceNodeTree.value.length) await fetchResourceNodeTree()
  completionIssueRow.value = null
  Object.assign(completionForm, {
    business_line: '',
    environment: '',
    admin_user: '',
    department: '',
    attributesText: '{}',
    note: '批量补齐关键字段',
  })
  completionDialogVisible.value = true
}

function onCompletionSelectionChange(rows) {
  completionSelection.value = rows || []
}

function onArchiveSelectionChange(rows) {
  archiveSelection.value = rows || []
}

async function saveCompletionIssue() {
  if (!completionIssueRow.value?.id && !completionSelection.value.length) return
  let attributes = {}
  try {
    attributes = parseJsonObject(completionForm.attributesText, '扩展属性', {})
  } catch (error) {
    return ElMessage.warning(error.message)
  }
  saving.value = true
  try {
    const isSingleCompletion = Boolean(completionIssueRow.value?.id)
    const businessLine = completionForm.business_line.trim()
    const environment = completionForm.environment
    const adminUser = completionForm.admin_user.trim()
    const department = completionForm.department.trim()
    if (isSingleCompletion || department) attributes.department = department || attributes.department || ''
    const ciUpdates = { attributes }
    if (isSingleCompletion || businessLine) ciUpdates.business_line = businessLine
    if (isSingleCompletion || environment) ciUpdates.environment = environment
    if (isSingleCompletion || adminUser) ciUpdates.admin_user = adminUser
    if (isSingleCompletion || department) ciUpdates.department = department
    if (isSingleCompletion) {
      await resolveCompletionIssue(completionIssueRow.value.id, {
        status: 'resolved',
        note: completionForm.note,
        ci_updates: ciUpdates,
      })
      ElMessage.success('资源信息已补全')
    } else {
      const result = await bulkResolveCompletionIssues({
        issue_ids: completionSelection.value.map(item => item.id),
        note: completionForm.note,
        ci_updates: ciUpdates,
      })
      const summary = result?.summary || {}
      const remaining = Number(summary.remaining || 0)
      ElMessage.success(remaining ? `已批量补全 ${summary.resolved || 0} 个，${remaining} 个仍需补充模型字段` : `已批量补全 ${summary.resolved || 0} 个资源`)
      completionSelection.value = []
    }
    completionDialogVisible.value = false
    await Promise.all([fetchGovernance(), fetchDashboard(), fetchLedger()])
  } finally {
    saving.value = false
  }
}

function openCompletionAssignDialog(row) {
  completionAssignRow.value = row
  Object.assign(completionAssignForm, {
    assigned_to: row.assigned_to || row.ci_admin_user || '',
    note: row.resolution_note || '请补齐关键字段后关闭治理项',
  })
  completionAssignVisible.value = true
}

async function saveCompletionAssign() {
  if (!completionAssignRow.value?.id) return
  const assignedTo = completionAssignForm.assigned_to.trim()
  if (!assignedTo) return ElMessage.warning('请填写处理人')
  saving.value = true
  try {
    await assignCompletionIssue(completionAssignRow.value.id, {
      assigned_to: assignedTo,
      note: completionAssignForm.note.trim(),
    })
    ElMessage.success('待补全问题已转派')
    completionAssignVisible.value = false
    await Promise.all([fetchGovernance(), fetchDashboard(), fetchLedger()])
  } finally {
    saving.value = false
  }
}

async function ignoreCompletion(row) {
  await ElMessageBox.confirm(`确认忽略「${row.ci_name || '该资源'}」的待补全问题吗？后续同一组缺失字段不会重复进入治理队列。`, '忽略待补全', { type: 'warning' })
  await ignoreCompletionIssue(row.id, { note: '页面确认忽略' })
  ElMessage.success('已忽略待补全问题')
  await Promise.all([fetchGovernance(), fetchDashboard(), fetchLedger()])
}

async function ignoreSyncGovernance(row) {
  await ElMessageBox.confirm(`确认忽略「${row.ci_name || row.after?.name || row.source_unique_id || '该同步记录'}」的同步治理事项吗？`, '忽略同步治理', { type: 'warning' })
  await ignoreSyncRecord(row.id, { note: '页面确认忽略' })
  ElMessage.success('已忽略同步治理事项')
  await Promise.all([fetchGovernance(), fetchDashboard(), fetchSyncJobs()])
}

async function bulkArchiveCandidateAction(action) {
  if (!archiveSelection.value.length) return
  const actionTextMap = {
    archive: '确认下线',
    restore: '恢复',
    ignore: '忽略',
  }
  const actionText = actionTextMap[action] || action
  await ElMessageBox.confirm(`确认${actionText}已选择的 ${archiveSelection.value.length} 个下线候选吗？`, `批量${actionText}下线候选`, { type: 'warning' })
  const result = await bulkActionArchiveCandidates({
    candidate_ids: archiveSelection.value.map(item => item.id),
    action,
    note: `页面批量${actionText}`,
  })
  archiveSelection.value = []
  ElMessage.success(`已批量${actionText} ${result?.updated_count || 0} 个下线候选`)
  await Promise.all([fetchGovernance(), fetchDashboard(), fetchLedger()])
}

async function archiveCandidate(row) {
  await ElMessageBox.confirm(`确认下线「${row.ci_name || '该资源'}」吗？资源会标记为已下线，并从待确认队列移除。`, '确认资产下线', { type: 'warning' })
  await archiveArchiveCandidate(row.id, { note: '页面确认下线' })
  ElMessage.success('资产已确认下线')
  await Promise.all([fetchGovernance(), fetchDashboard(), fetchLedger()])
}

async function ignoreArchive(row) {
  await ElMessageBox.confirm(`确认忽略「${row.ci_name || '该资源'}」的下线候选吗？`, '忽略下线候选', { type: 'warning' })
  await ignoreArchiveCandidate(row.id, { note: '页面确认忽略' })
  ElMessage.success('已忽略下线候选')
  await Promise.all([fetchGovernance(), fetchDashboard(), fetchLedger()])
}

function resetSyncRuntimeForm() {
  syncRuntimeForm.password = ''
  syncRuntimeSubmitting.value = false
}

function syncJobNeedsRuntimePassword(row) {
  const config = row?.config || {}
  const connector = String(config.connector || '').toLowerCase()
  const sourceType = String(row?.source_type || '').toLowerCase()
  return connector === 'vsphere' || sourceType.includes('vsphere')
}

function syncRuntimePayload() {
  const password = String(syncRuntimeForm.password || '').trim()
  return password ? { runtime_credentials: { password } } : {}
}

function openSyncRuntimeDialog(row, action = 'run') {
  syncRuntimeRow.value = row || null
  syncRuntimeAction.value = action
  resetSyncRuntimeForm()
  syncRuntimeVisible.value = true
}

async function executeSyncJob(row, action = 'run', payload = {}) {
  if (action === 'dry_run') {
    const result = await dryRunSyncJob(row.id, payload)
    syncPreview.value = {
      summary: result?.summary || {},
      records: result?.records || result?.items || [],
    }
    syncPreviewVisible.value = true
    return
  }
  const result = await runSyncJob(row.id, payload)
  const summary = result?.summary || {}
  const failedCount = Number(summary.fail || 0) + Number(summary.conflict || 0)
  const message = result?.error_message || syncRunResultText(summary)
  if (failedCount) {
    ElMessage.warning(message)
  } else {
    ElMessage.success(message)
  }
  await Promise.all([fetchSyncJobs(), fetchCollectionSummary(true), fetchDashboard(), fetchLedger(), fetchGovernance()])
}

async function confirmSyncRuntime() {
  if (!syncRuntimeForm.password.trim()) return ElMessage.warning('请输入本次采集使用的 vSphere 密码')
  if (!syncRuntimeRow.value?.id) return
  syncRuntimeSubmitting.value = true
  try {
    await executeSyncJob(syncRuntimeRow.value, syncRuntimeAction.value, syncRuntimePayload())
    syncRuntimeVisible.value = false
  } finally {
    syncRuntimeSubmitting.value = false
  }
}

async function runJob(row) {
  if (syncJobNeedsRuntimePassword(row)) return openSyncRuntimeDialog(row, 'run')
  await executeSyncJob(row, 'run')
}

async function runDueCollectionJobs() {
  syncDueRunning.value = true
  try {
    const result = await runDueSyncJobs()
    const count = result?.executed_count || 0
    if (count) {
      ElMessage.success(`已执行 ${count} 个到期采集任务`)
    } else {
      ElMessage.info('暂无到期采集任务')
    }
    if (result?.collection) {
      collectionSummary.value = result.collection
    }
    await Promise.all([fetchSyncJobs(), fetchDashboard(), fetchLedger(), fetchGovernance()])
  } finally {
    syncDueRunning.value = false
  }
}

async function dryRunJob(row) {
  if (syncJobNeedsRuntimePassword(row)) return openSyncRuntimeDialog(row, 'dry_run')
  await executeSyncJob(row, 'dry_run')
}

async function toggleCollectionJob(row, enabled) {
  await toggleSyncJobCollection(row.id, { enabled })
  ElMessage.success(enabled ? '自动同步已启用' : '自动同步已停止')
  await Promise.all([fetchSyncJobs(), fetchCollectionSummary(true)])
}

async function viewSyncRecords(row, status = 'all') {
  syncRecordsJob.value = row
  syncRecordStatusFilter.value = status || 'all'
  syncRecordBatchDetail.value = null
  syncRecordsVisible.value = true
  syncRecordsLoading.value = true
  try {
    syncRecords.value = listOf(await getSyncRecords({ job: row.id, page_size: 200 }))
  } finally {
    syncRecordsLoading.value = false
  }
}

function selectSyncRecordStatus(status) {
  syncRecordBatchDetail.value = null
  syncRecordStatusFilter.value = status || 'all'
}

function openSyncRecordBatch(batch) {
  syncRecordBatchDetail.value = batch || null
}

function syncRecordBatchSummaryText(batch) {
  const counts = batch?.statusCounts || {}
  const parts = []
  if (counts.success) parts.push(`成功 ${counts.success}`)
  if (counts.resolved) parts.push(`已处理 ${counts.resolved}`)
  if (counts.failed) parts.push(`失败 ${counts.failed}`)
  return parts.join(' · ') || `共 ${batch?.totalCount || 0} 项`
}

async function loadSyncRecordRelationCandidates(row = syncRecordDetailRow.value) {
  syncRelationIssues.value = []
  if (!row?.id || !row.relation_issue || !canViewSync.value) return
  syncRelationIssueLoading.value = true
  try {
    const result = await getSyncRecordRelationCandidates(row.id)
    syncRecordDetailRow.value = result?.record || row
    syncRelationIssues.value = listOf(result?.issues || [])
  } finally {
    syncRelationIssueLoading.value = false
  }
}

async function openSyncRecordDetail(row) {
  syncRecordDetailRow.value = row || null
  syncRecordDetailVisible.value = true
  await loadSyncRecordRelationCandidates(row)
}

function syncRelationIssueKey(issue) {
  return [issue?.index ?? 'unknown', issue?.relation_rule_id || '', issue?.relation_type || '', issue?.direction || ''].join('-')
}

function syncRelationIssueReasonText(reason) {
  if (reason === 'peer_not_found') return '未找到对端'
  if (reason === 'validation_failed') return '规则校验失败'
  return reason || '关系失败'
}

async function resolveSyncRelationIssue(issue, candidate) {
  if (!syncRecordDetailRow.value?.id || !candidate?.id) return
  if (issue?.index === undefined || issue?.index === null || issue?.index === '') {
    return ElMessage.warning('缺少关系失败项编号，无法自动处理')
  }
  const resolvingKey = `${syncRelationIssueKey(issue)}-${candidate.id}`
  syncRelationResolvingKey.value = resolvingKey
  try {
    const result = await resolveSyncRecordRelation(syncRecordDetailRow.value.id, {
      error_index: issue.index,
      candidate_id: candidate.id,
    })
    syncRecordDetailRow.value = result?.record || syncRecordDetailRow.value
    ElMessage.success('自动关系已关联')
    await Promise.all([
      loadSyncRecordRelationCandidates(syncRecordDetailRow.value),
      fetchGovernance(),
      fetchSyncJobs(),
      fetchCollectionSummary(true),
    ])
    if (syncRecordsVisible.value && syncRecordsJob.value?.id) {
      syncRecords.value = listOf(await getSyncRecords({ job: syncRecordsJob.value.id, page_size: 200 }))
    }
  } finally {
    syncRelationResolvingKey.value = ''
  }
}

async function bulkResolveSyncRelations() {
  const recordIds = syncRelationBulkRecordIds.value
  if (!recordIds.length) return ElMessage.warning('暂无可批量处理的自动关系失败记录')
  await ElMessageBox.confirm(
    `确认按最佳候选批量关联 ${recordIds.length} 条同步关系失败记录吗？无候选的记录会自动跳过。`,
    '批量关联自动关系',
    { type: 'warning' },
  )
  syncRelationBulkResolving.value = true
  try {
    const result = await bulkResolveSyncRecordRelations({ record_ids: recordIds })
    const summary = result?.summary || {}
    const message = `已处理 ${summary.resolved || 0} 项，跳过 ${summary.skipped || 0} 项`
    if (summary.failed) {
      ElMessage.warning(`${message}，失败 ${summary.failed} 项`)
    } else {
      ElMessage.success(message)
    }
    await Promise.all([fetchGovernance(), fetchSyncJobs(), fetchCollectionSummary(true), fetchDashboard(), fetchViewsSummary(), fetchAuditLogs()])
    if (syncRecordsVisible.value && syncRecordsJob.value?.id) {
      syncRecords.value = listOf(await getSyncRecords({ job: syncRecordsJob.value.id, page_size: 200 }))
    }
    if (syncRecordDetailVisible.value && syncRecordDetailRow.value?.id) {
      await loadSyncRecordRelationCandidates(syncRecordDetailRow.value)
    }
  } finally {
    syncRelationBulkResolving.value = false
  }
}

function syncRetrySummaryFeedback(summary = {}, records = []) {
  const countOf = key => Number(summary?.[key] || 0)
  const skipped = countOf('skipped')
  const failed = countOf('fail') + countOf('conflict')
  const retried = ['create', 'update', 'unchanged', 'archive_candidate', 'fail', 'conflict']
    .reduce((total, key) => total + countOf(key), 0) || records.length
  if (!retried && skipped) {
    return { type: 'info', message: `暂无可重试失败记录，已跳过 ${skipped} 条已修复记录` }
  }
  if (!retried && !skipped) {
    return { type: 'info', message: '暂无可重试失败记录' }
  }
  const parts = [`已重试 ${retried} 条失败记录`]
  if (skipped) parts.push(`跳过 ${skipped} 条已修复记录`)
  if (failed) parts.push(`${failed} 条仍需处理`)
  return {
    type: failed ? 'warning' : 'success',
    message: parts.join('，'),
  }
}

async function retryJob(row) {
  const result = await retryFailedSyncJob(row.id)
  const feedback = syncRetrySummaryFeedback(result?.summary || {}, result?.records || [])
  ElMessage[feedback.type](feedback.message)
  await Promise.all([fetchSyncJobs(), fetchCollectionSummary(true), fetchDashboard()])
  if (syncRecordsVisible.value) {
    syncRecordsJob.value = row
    syncRecords.value = listOf(await getSyncRecords({ job: row.id, page_size: 200 }))
  }
}

async function retrySyncRecordRow(row) {
  await retrySyncRecord(row.id)
  ElMessage.success('已重试该条失败记录')
  await Promise.all([fetchSyncJobs(), fetchCollectionSummary(true), fetchDashboard(), fetchLedger(), fetchGovernance()])
  if (syncRecordsJob.value?.id) {
    syncRecords.value = listOf(await getSyncRecords({ job: syncRecordsJob.value.id, page_size: 200 }))
  }
}

function canResolveSyncRecord(row) {
  return row?.status === 'failed' && ['conflict', 'fail'].includes(row?.action)
}

function handleSyncGovernanceMore(command, row) {
  if (command === 'record') {
    openSyncRecordDetail(row)
    return
  }
  if (command === 'asset' && row?.ci) openCiDetail({ id: row.ci })
}

function syncResolveSourceIdentity(row) {
  return row?.source_unique_id || row?.after?.source_unique_id || row?.after?.instance_id || '-'
}

function syncResolveSourceScope(row) {
  const after = row?.after || {}
  return [
    after.source_type || row?.job_source_type || '-',
    after.source_account || '-',
    after.source_region || '-',
  ].join(' / ')
}

async function openSyncResolveDialog(row) {
  syncResolveRecord.value = row
  if (!ledgerItems.value.length) await fetchLedger()
  const targetName = String(row?.after?.name || row?.ci_name || '').toLowerCase()
  const matched = sourceMappingCiOptions.value.find(item => String(item.name || '').toLowerCase() === targetName)
  Object.assign(syncResolveForm, {
    ci_id: row?.ci || matched?.id || '',
    replace_existing: false,
    rebind: false,
    note: row?.action === 'conflict' ? '人工确认采集来源归属' : '人工绑定失败同步来源',
  })
  syncResolveVisible.value = true
}

async function submitSyncResolve() {
  if (!syncResolveRecord.value?.id) return
  if (!syncResolveForm.ci_id) return ElMessage.warning('请选择目标配置项')
  saving.value = true
  try {
    await resolveSyncRecordToCi(syncResolveRecord.value.id, {
      ci_id: syncResolveForm.ci_id,
      replace_existing: syncResolveForm.replace_existing,
      rebind: syncResolveForm.rebind,
      note: syncResolveForm.note,
    })
    ElMessage.success('同步来源已绑定到配置项')
    syncResolveVisible.value = false
    await Promise.all([fetchSyncJobs(), fetchCollectionSummary(true), fetchDashboard(), fetchLedger(), fetchGovernance(), fetchSourceMappings()])
    if (syncRecordsJob.value?.id) {
      syncRecords.value = listOf(await getSyncRecords({ job: syncRecordsJob.value.id, page_size: 200 }))
    }
  } finally {
    saving.value = false
  }
}

function matchFieldText(item) {
  if (!item) return '-'
  if (typeof item === 'string') return item
  const label = item.label || item.field || item.key || '字段'
  const value = item.value === undefined || item.value === null || item.value === '' ? '' : `: ${item.value}`
  return `${label}${value}`
}

function keyAttributeEntries(row) {
  const attributes = row?.key_attributes || row?.attributes || {}
  if (Array.isArray(attributes)) {
    return attributes.map((item, index) => {
      const key = item.label || item.key || item.name || ('属性' + (index + 1))
      return {
        key,
        code: item.code || item.field || item.key || item.name || key,
        label: item.label || item.name || key,
        value: item.value ?? item.display_value ?? item,
      }
    })
  }
  return Object.entries(attributes).map(([key, value]) => ({ key, code: key, label: key, value }))
}

function normalizeAttributeDisplayValue(value) {
  if (value === undefined || value === null) return ''
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value).trim()
}

const ledgerAttributeHiddenKeys = new Set([
  'business_line',
  'environment',
  'source_region',
  'cloud_region',
  'source_account',
  'cloud_account',
  'source_unique_id',
])
const ledgerAttributeHiddenLabels = new Set(['业务线', '环境', '来源地域', '来源账号', '来源唯一标识'])
const ledgerIpAttributeKeys = new Set([
  'ip',
  'ip_address',
  'private_ip',
  'public_ip',
  'host_ip',
  'internal_ip',
  'external_ip',
])

function normalizeLedgerAttributeKey(value) {
  return String(value || '').trim().toLowerCase()
}

function normalizeLedgerAttributeLabel(value) {
  return String(value || '').trim()
}

function ledgerRowModelId(row) {
  const rawTypeId = row?.ci_type_id ?? row?.ci_type
  if (rawTypeId !== undefined && rawTypeId !== null && rawTypeId !== '') {
    const direct = ciTypes.value.find(item => String(item.id) === String(rawTypeId))
    if (direct) return String(direct.id)
    const rawTypeText = String(rawTypeId).trim()
    if (rawTypeText) {
      const byCode = ciTypes.value.find(item => String(item.code || '').trim().toUpperCase() === rawTypeText.toUpperCase())
      if (byCode) return String(byCode.id)
      const byName = ciTypes.value.find(item => String(item.name || '').trim() === rawTypeText)
      if (byName) return String(byName.id)
    }
    if (ciFields.value.some(item => String(item.ci_type) === String(rawTypeId))) return String(rawTypeId)
  }
  const typeCode = String(row?.ci_type_code || '').trim().toUpperCase()
  if (typeCode) {
    const byCode = ciTypes.value.find(item => String(item.code || '').trim().toUpperCase() === typeCode)
    if (byCode) return String(byCode.id)
  }
  const typeName = String(row?.ci_type_name || '').trim()
  if (typeName) {
    const byName = ciTypes.value.find(item => String(item.name || '').trim() === typeName)
    if (byName) return String(byName.id)
  }
  return ''
}

function ledgerFieldDefinitions(row) {
  const fieldCollections = [
    row?.field_definitions,
    row?.ci_field_definitions,
    row?.model_fields,
    row?.ci_fields,
    row?.fields,
    row?.attributes_schema?.fields,
    row?.schema?.fields,
  ]
  const directFields = fieldCollections.find(item => Array.isArray(item) && item.length)
  if (directFields) return directFields
  const modelId = ledgerRowModelId(row)
  if (!modelId) return []
  return ciFields.value.filter(item => String(item.ci_type) === String(modelId))
}

function ledgerFieldCode(field = {}) {
  return String(field?.code || field?.field || field?.key || field?.name || field?.label || '').trim()
}

function ledgerFieldLabel(field = {}) {
  return field?.name || field?.label || field?.title || field?.code || field?.field || field?.key || ''
}

function ledgerFieldMetaMap(row) {
  const map = new Map()
  ledgerFieldDefinitions(row).forEach((field, index) => {
    const code = normalizeLedgerAttributeKey(ledgerFieldCode(field))
    if (!code) return
    const meta = {
      sortOrder: Number(field?.sort_order ?? field?.order ?? field?.sequence ?? index),
      label: ledgerFieldLabel(field),
      isDisplay: field?.is_display !== false,
    }
    const current = map.get(code)
    if (!current) {
      map.set(code, meta)
      return
    }
    map.set(code, {
      sortOrder: Number.isFinite(current.sortOrder) ? current.sortOrder : meta.sortOrder,
      label: current.label || meta.label,
      isDisplay: current.isDisplay && meta.isDisplay,
    })
  })
  return map
}

function ledgerAttributeEntryKey(entry = {}) {
  return normalizeLedgerAttributeKey(entry.code || entry.key || entry.label)
}

function ledgerAttributeEntryLabel(entry = {}) {
  return normalizeLedgerAttributeLabel(entry.label || entry.key)
}

function ledgerAttributeEntries(row) {
  const metaMap = ledgerFieldMetaMap(row)
  return keyAttributeEntries(row)
    .filter((item) => {
      const key = ledgerAttributeEntryKey(item)
      const label = ledgerAttributeEntryLabel(item)
      if (ledgerAttributeHiddenKeys.has(key) || ledgerAttributeHiddenLabels.has(label)) return false
      const meta = metaMap.get(key)
      if (meta && !meta.isDisplay) return false
      return !ledgerIpAttributeKeys.has(key) || metaMap.has(key)
    })
    .map((item, index) => {
      const meta = metaMap.get(ledgerAttributeEntryKey(item)) || {}
      return {
        ...item,
        label: meta.label || item.label,
        sortOrder: Number.isFinite(meta.sortOrder) ? meta.sortOrder : Number.MAX_SAFE_INTEGER,
        fieldLabel: meta.label || '',
        index,
      }
    })
    .sort((a, b) => {
      const sortDiff = Number(a.sortOrder) - Number(b.sortOrder)
      if (sortDiff) return sortDiff
      const labelDiff = String(a.fieldLabel || a.label || a.key || '').localeCompare(String(b.fieldLabel || b.label || b.key || ''), 'zh-Hans-CN')
      if (labelDiff) return labelDiff
      return a.index - b.index
    })
    .map(({ index, sortOrder, fieldLabel, ...item }) => item)
}

function sourceMappingsOf(row) {

  if (Array.isArray(row?.source_mappings)) return row.source_mappings
  if (Array.isArray(row?.sources)) return row.sources
  return []
}

function primarySourceMapping(row) {
  return sourceMappingsOf(row)[0] || null
}

function sourceIdentityText(row) {
  const firstSource = primarySourceMapping(row)
  return firstSource?.source_unique_id || firstSource?.source_account || row?.key_attributes?.source_unique_id || '-'
}

function ledgerSourceLabel(row) {
  const firstSource = primarySourceMapping(row)
  return row?.source_label || row?.source_type || firstSource?.source_type || row?.attributes?.source_type || row?.attributes?.source || 'manual'
}

function ledgerSourceSyncStatus(row) {
  const firstSource = primarySourceMapping(row)
  return row?.source_sync_status || firstSource?.sync_status || ''
}

function ledgerSourceIdentity(row) {
  const firstSource = primarySourceMapping(row)
  return row?.source_unique_id || firstSource?.source_unique_id || row?.attributes?.source_unique_id || row?.key_attributes?.source_unique_id || '-'
}

function ledgerSourceAccount(row) {
  const firstSource = primarySourceMapping(row)
  return firstSource?.source_account || row?.source_account || row?.cloud_account || row?.attributes?.source_account || row?.attributes?.cloud_account || row?.attributes?.account || row?.attributes?.account_id || row?.attributes?.account_name || '-'
}

function ledgerSourceRegion(row) {
  const firstSource = primarySourceMapping(row)
  return firstSource?.source_region || row?.attributes?.source_region || row?.attributes?.cloud_region || row?.attributes?.region || row?.attributes?.region_id || '-'
}

function ledgerAvailabilityZone(row) {
  return row?.attributes?.availability_zone || row?.attributes?.zone_id || row?.attributes?.zone || row?.attributes?.az || '-'
}

function ledgerDataServiceSpec(row) {
  const attrs = row?.attributes || {}
  return attrs.instance_class || attrs.instance_type || attrs.spec || attrs.flavor || attrs.node_type || '-'
}

function ledgerDataServiceCapacity(row) {
  const attrs = row?.attributes || {}
  if (attrs.storage_gb || attrs.disk_gb) return `${attrs.storage_gb || attrs.disk_gb} GB`
  if (attrs.memory_gb) return `${attrs.memory_gb} GB 内存`
  if (attrs.capacity_gb) return `${attrs.capacity_gb} GB`
  const topicText = attrs.topic_count ? `Topic ${attrs.topic_count}` : ''
  const partitionText = attrs.partition_count ? `分区 ${attrs.partition_count}` : ''
  const groupText = attrs.group_count ? `Group ${attrs.group_count}` : ''
  const lagText = attrs.message_lag ? `Lag ${attrs.message_lag}` : ''
  const mqText = [topicText, partitionText, groupText, lagText].filter(Boolean).join(' / ')
  if (mqText) return mqText
  return '-'
}

function ledgerDataServiceUsage(row) {
  const attrs = row?.attributes || {}
  const value = attrs.storage_usage || attrs.storage_utilization || attrs.storage_usage_pct || attrs.memory_usage || attrs.memory_usage_pct || attrs.connection_usage
  if (value === undefined || value === null || value === '') return ''
  return `${value}%`
}

function ledgerUsageTagType(row) {
  const usage = Number(String(ledgerDataServiceUsage(row)).replace('%', ''))
  if (!Number.isFinite(usage)) return 'info'
  if (usage >= 95) return 'danger'
  if (usage >= 85) return 'warning'
  if (usage >= 70) return 'warning'
  return 'success'
}

function ledgerDataServiceNetwork(row) {
  const attrs = row?.attributes || {}
  const values = [attrs.vpc_id || attrs.vpc, attrs.vswitch_id || attrs.vswitch || attrs.subnet_id, attrs.network_type || attrs.network].filter(Boolean)
  return values.join(' / ') || '-'
}

function ledgerDataServiceVersion(row) {
  const attrs = row?.attributes || {}
  const engine = attrs.engine || attrs.db_engine || attrs.middleware_engine
  const version = attrs.version || attrs.engine_version
  if (engine && version) return `${engine} ${version}`
  return engine || version || '-'
}

function ledgerEdgeEndpoint(row) {
  const attrs = row?.attributes || {}
  return attrs.endpoint || attrs.domain || attrs.vip || attrs.bucket || attrs.instance_id || '-'
}

function ledgerEdgeCapacity(row) {
  const attrs = row?.attributes || {}
  if (attrs.storage_gb || attrs.capacity_gb) return `${attrs.storage_gb || attrs.capacity_gb} GB`
  const parts = [
    attrs.bandwidth ? `${attrs.bandwidth} Mbps` : '',
    attrs.backend_count ? `后端 ${attrs.backend_count}` : '',
    attrs.instance_class || attrs.spec || '',
  ].filter(Boolean)
  return parts.join(' / ') || '-'
}

function ledgerEdgeNetwork(row) {
  const attrs = row?.attributes || {}
  const parts = [attrs.vpc_id || attrs.vpc, attrs.vswitch_id || attrs.vswitch, attrs.network_type || attrs.network].filter(Boolean)
  return parts.join(' / ') || '-'
}

function ledgerEdgePolicy(row) {
  const attrs = row?.attributes || {}
  const parts = [
    attrs.storage_class || attrs.storage_type,
    attrs.acl || attrs.access_control,
    attrs.region || attrs.source_region,
  ].filter(Boolean)
  return parts.join(' / ') || '-'
}

const resourceWaterlineMetricDefs = [
  {
    key: 'cpu',
    label: 'CPU',
    metrics: ['cpu_usage'],
    attrKeys: ['cpu_usage', 'cpu_usage_percent', 'cpu_utilization', 'cpu_utilization_percent', 'cpu_used_percent'],
  },
  {
    key: 'memory',
    label: '内存',
    metrics: ['memory_usage'],
    attrKeys: ['memory_usage', 'memory_usage_percent', 'memory_utilization', 'memory_utilization_percent', 'memory_used_percent'],
  },
  {
    key: 'disk',
    label: '磁盘',
    metrics: ['disk_usage', 'storage_usage'],
    attrKeys: ['disk_usage', 'storage_usage', 'disk_usage_percent', 'storage_usage_percent', 'disk_utilization', 'storage_utilization', 'disk_used_percent', 'storage_used_percent'],
  },
]

const resourceWaterlineAttributeCodes = new Set([
  ...resourceWaterlineMetricDefs.flatMap(item => item.attrKeys),
  'cpu_used_mhz', 'memory_total_gb', 'memory_used_gb', 'memory_free_gb', 'memory_available_gb',
  'disk_used_gb', 'storage_used_gb', 'root_disk_total_gb', 'root_disk_free_gb', 'root_disk_available_gb', 'root_mountpoint',
  'metric_collection_source', 'metric_collection_status', 'metric_collection_error', 'metrics_collection_status',
  'metric_datasource', 'metric_collected_at', 'prometheus_target',
])

function isResourceWaterlineTarget(row = {}) {
  const code = String(row.ci_type_code || '').toUpperCase()
  const text = [
    code,
    row.ci_type_name,
    row.name,
    row.attributes?.cloud_provider,
    row.attributes?.provider,
  ].filter(Boolean).join(' ').toLowerCase()
  return ['CLOUD_SERVER', 'VIRTUAL_MACHINE', 'IDC_SERVER', 'PHYSICAL_SERVER'].includes(code)
    || text.includes('ecs')
    || text.includes('virtual_machine')
    || text.includes('cloud_server')
    || text.includes('虚拟机')
    || text.includes('云主机')
    || text.includes('物理机')
}

function resourceMetricCandidateKeys(row = {}) {
  return new Set([
    row.id,
    row.ci,
    row.ci_id,
    row.name,
    row.ci_name,
    row.source_unique_id,
    row.key_attributes?.source_unique_id,
    row.attributes?.source_unique_id,
    row.attributes?.instance_id,
    row.attributes?.resource_id,
  ].filter(value => value !== undefined && value !== null && String(value).trim() !== '').map(value => String(value)))
}

function resourceMetricRowsFor(row = {}) {
  const inlineRows = [
    ...(Array.isArray(row.latest_metric_snapshots) ? row.latest_metric_snapshots : []),
    ...(Array.isArray(row.metric_snapshots) ? row.metric_snapshots : []),
    ...(Array.isArray(row.metrics) ? row.metrics : []),
  ]
  const keys = resourceMetricCandidateKeys(row)
  const globalRows = [
    ...(resourceWaterlinePageMetrics.value || []),
    ...(resourceMetrics.value || []),
  ].filter((item) => {
    const metricKeys = resourceMetricCandidateKeys(item)
    return Array.from(metricKeys).some(key => keys.has(key))
  })
  return [...inlineRows, ...globalRows]
}

function latestResourceWaterlineMetric(row = {}, def) {
  const rows = resourceMetricRowsFor(row)
    .filter(item => def.metrics.includes(item.metric) && item.usage_percent !== undefined && item.usage_percent !== null && item.usage_percent !== '')
    .sort((left, right) => String(right.collected_at || '').localeCompare(String(left.collected_at || '')) || Number(right.id || 0) - Number(left.id || 0))
  return rows[0] || null
}

function resourceWaterlineTone(percent, hasData) {
  if (!hasData) return 'empty'
  if (percent >= 95) return 'danger'
  if (percent >= 85) return 'warning'
  if (percent >= 70) return 'notice'
  return 'success'
}

function resourceWaterlineRows(row = {}) {
  if (!isResourceWaterlineTarget(row)) {
    return resourceWaterlineMetricDefs.map(def => ({ ...def, percent: 0, hasData: false, tone: 'empty' }))
  }
  return resourceWaterlineMetricDefs.map((def) => {
    const metric = latestResourceWaterlineMetric(row, def)
    const metricPercent = metric ? overviewPercent(metric.usage_percent, def.key) : null
    const percent = metricPercent
    const normalizedPercent = percent === null ? 0 : Math.round(percent)
    return {
      ...def,
      percent: normalizedPercent,
      hasData: percent !== null,
      tone: resourceWaterlineTone(normalizedPercent, percent !== null),
    }
  })
}

function resourceWaterlineTooltipSource(row = {}) {
  const meta = resourceWaterlineSourceMeta(row)
  return meta.sourceLabel || '-'
}

function resourceWaterlineTooltipTime(row = {}) {
  const meta = resourceWaterlineSourceMeta(row)
  return meta.collectedAt ? formatTime(meta.collectedAt) : '-'
}

function resourceWaterlineSourceLabel(sourceValues = []) {
  const sources = Array.from(new Set(sourceValues
    .map(source => String(source || '').trim().toLowerCase())
    .filter(Boolean)))
  const sourceLabels = [
    sources.some(source => source.includes('aliyun_cloudmonitor')) && '阿里云云监控',
    sources.some(source => source.includes('aliyun_ecs_monitor')) && '阿里云 ECS 监控',
    sources.some(source => source.includes('prometheus')) && 'Prometheus',
    sources.some(source => source.includes('vsphere')) && 'vSphere',
    sources.some(source => source === 'manual') && '手工录入',
    sources.some(source => source === 'import') && '导入',
  ].filter(Boolean)
  return sourceLabels.join(' / ') || sources.join(' / ') || '-'
}

function resourceWaterlineSourceMeta(row = {}) {
  const metrics = resourceWaterlineMetricDefs.map(def => latestResourceWaterlineMetric(row, def)).filter(Boolean)
  const sourceLabel = resourceWaterlineSourceLabel([
    ...metrics.map(item => item.source),
    row.attributes?.metric_collection_source,
    row.attributes?.metric_datasource,
  ])
  const collectedAtValues = [
    ...metrics.map(item => item.collected_at),
  ].filter(Boolean).sort((left, right) => String(right).localeCompare(String(left)))
  return { sourceLabel, collectedAt: collectedAtValues[0] || '' }
}

function modelRiskCount(row) {
  if (row?.risk_count !== undefined && row?.risk_count !== null) return Number(row.risk_count || 0)
  return Number(row?.completion_issue_count || 0)
    + Number(row?.archive_candidate_count || 0)
    + Number(row?.sync_failure_count || 0)
}

function repositoryQualityTone(row) {
  const score = Number(row?.quality_score ?? 100)
  if (score < 60) return 'danger'
  if (score < 90) return 'warning'
  return 'success'
}

function formatValue(value) {
  if (value === undefined || value === null || value === '') return '-'
  if (typeof value === 'boolean') return value ? '是' : '否'
  if (Array.isArray(value)) {
    if (!value.length) return '-'
    return value.every(item => typeof item !== 'object') ? value.join('、') : JSON.stringify(value)
  }
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

const ciFieldTypeLabels = {
  string: '字符串',
  integer: '整数',
  decimal: '小数',
  boolean: '布尔',
  date: '日期',
  datetime: '日期时间',
  enum: '单选枚举',
  multi_enum: '多选枚举',
  ip: 'IP 地址',
  url: 'URL',
  json: 'JSON',
}

function fieldTypeLabel(type) {
  return ciFieldTypeLabels[type] || type || '-'
}

function fieldSyncModeLabel(syncMode) {
  if (syncMode === 'manual') return '人工优先'
  if (syncMode === 'source') return '来源优先'
  return syncMode || '来源优先'
}

function fieldDefaultText(row = {}) {
  const value = row.default
  if (value === undefined || value === null || value === '') return ''
  return formatValue(value)
}

function ciFormFieldMetaText(field = {}) {
  const parts = [
    field.code,
    field.field_group || '未分组',
    fieldTypeLabel(field.field_type),
    field.required ? '必填' : '可选',
  ].filter(Boolean)
  if (field.unique) parts.push('唯一')
  if (fieldDefaultText(field)) parts.push(`默认 ${fieldDefaultText(field)}`)
  return parts.join(' / ')
}

function openAuditDetail(row) {
  auditDetailRow.value = row || null
  auditDetailVisible.value = true
}

function formatAuditValue(value) {
  if (value === undefined || value === null || value === '') return '-'
  if (typeof value === 'boolean') return value ? '是' : '否'
  if (typeof value === 'object') {
    try {
      return JSON.stringify(value)
    } catch (error) {
      return String(value)
    }
  }
  return String(value)
}

function formatAuditJson(value) {
  if (value === undefined || value === null || value === '') return '-'
  try {
    return JSON.stringify(value, null, 2)
  } catch (error) {
    return String(value)
  }
}

function formatMoney(value) {
  const amount = Number(value || 0)
  if (!Number.isFinite(amount)) return '¥0'
  if (amount >= 10000) return `¥${(amount / 10000).toFixed(1)}万`
  return `¥${amount.toLocaleString(undefined, { maximumFractionDigits: 2 })}`
}

function formatPercent(value) {
  const percent = Number(value || 0)
  if (!Number.isFinite(percent)) return '0%'
  return `${percent.toFixed(1).replace(/\.0$/, '')}%`
}

function metricLabel(metric) {
  const labels = {
    cpu_usage: 'CPU 使用率',
    memory_usage: '内存使用率',
    disk_usage: '磁盘使用率',
    storage_usage: '存储使用率',
    connection_usage: '连接数使用率',
  }
  return labels[metric] || metric || '-'
}

function formatMetricValue(row) {
  const value = row.value ?? '-'
  return `${value}${row.unit || ''}`
}

function metricSnapshotSourceText(source) {
  const value = String(source || '').trim()
  if (value.includes('prometheus')) return 'Prometheus'
  if (value.includes('vsphere')) return 'vSphere'
  return value || '-'
}

function capacityThresholdsForMetricRow(row) {
  const metric = row?.metric || ''
  const ciTypeName = row?.ci_type_name || ''
  const ciTypeId = row?.ci_type_id || row?.ci_type || row?.resource_type || ''
  const policy = thresholdPolicies.value.find(item => item.enabled !== false && item.metric === metric && String(item.resource_type || '') === String(ciTypeId || ''))
    || thresholdPolicies.value.find(item => item.enabled !== false && item.metric === metric && item.resource_type_name === ciTypeName)
    || thresholdPolicies.value.find(item => item.enabled !== false && item.metric === metric && !item.resource_type)
  return {
    warning: Number(policy?.warning_threshold ?? 70),
    critical: Number(policy?.critical_threshold ?? 85),
    exceeded: Number(policy?.exceeded_threshold ?? 95),
  }
}

function metricRiskType(row) {
  const status = capacityRiskStatus(row)
  if (status === 'exceeded' || status === 'critical') return 'danger'
  if (status === 'warning') return 'warning'
  if (status === 'normal') return 'success'
  return 'info'
}

function requestStatusText(status) {
  const map = {
    pending: '待审批',
    approved: '已批准',
    provisioning: '交付中',
    failed: '交付失败',
    rejected: '已拒绝',
    completed: '已交付',
  }
  return map[status] || status || '-'
}

function requestStatusTagType(status) {
  if (status === 'approved' || status === 'completed') return 'success'
  if (status === 'pending') return 'warning'
  if (status === 'rejected' || status === 'failed') return 'danger'
  if (status === 'provisioning') return 'primary'
  return 'info'
}

function requestPriorityText(priority) {
  const map = {
    low: '低',
    medium: '中',
    high: '高',
    urgent: '紧急',
  }
  return map[priority] || priority || '-'
}

function requestPriorityTagType(priority) {
  if (priority === 'urgent') return 'danger'
  if (priority === 'high') return 'warning'
  if (priority === 'low') return 'info'
  return 'success'
}

function changeDiffText(row) {
  if (row.diff_preview) return row.diff_preview
  if (Array.isArray(row.diff_fields) && row.diff_fields.length) {
    const preview = row.diff_fields
      .slice(0, 3)
      .map(item => `${item.label || item.field}：${item.before_text || '-'} -> ${item.after_text || '-'}`)
      .join('；')
    return row.diff_fields.length > 3 ? `${preview} 等 ${row.diff_fields.length} 项` : preview
  }
  const keys = Object.keys(row.diff || {})
  if (keys.length) return keys.join('、')
  if (row.action === 'create') return '创建配置项'
  if (row.action === 'completion_assign') return '转派待补全'
  if (row.action === 'completion_ignore') return '忽略待补全'
  if (row.action === 'archive_mark') return '标记待下线'
  if (row.action === 'archive_confirm') return '确认下线'
  if (row.action === 'archive_archive') return '归档下线候选'
  if (row.action === 'archive_restore') return '恢复资源'
  return '-'
}

function changeDiffCount(row) {
  if (Number(row?.diff_count || 0)) return Number(row.diff_count)
  if (Array.isArray(row?.diff_fields)) return row.diff_fields.length
  return Object.keys(row?.diff || {}).length
}

function changeActionText(action) {
  const map = {
    create: '创建',
    update: '更新',
    bulk_update: '批量维护',
    delete: '删除',
    model_create: '模型创建',
    model_update: '模型更新',
    model_delete: '模型删除',
    model_group_create: '模型分组创建',
    model_group_update: '模型分组更新',
    model_group_delete: '模型分组删除',
    model_field_create: '字段创建',
    model_field_update: '字段更新',
    model_field_delete: '字段删除',
    relation_rule_create: '关系规则创建',
    relation_rule_update: '关系规则更新',
    relation_rule_delete: '关系规则删除',
    source_mapping_create: '采集来源创建',
    source_mapping_update: '采集来源更新',
    source_mapping_delete: '采集来源删除',
    threshold_policy_create: '阈值策略创建',
    threshold_policy_update: '阈值策略更新',
    threshold_policy_delete: '阈值策略删除',
    resource_metric_create: '指标快照创建',
    resource_metric_update: '指标快照更新',
    resource_metric_delete: '指标快照删除',
    sync_job_create: '同步任务创建',
    sync_job_update: '同步任务更新',
    sync_job_delete: '同步任务删除',
    authorization_create: '授权创建',
    authorization_update: '授权更新',
    authorization_delete: '授权删除',
    completion_resolve: '补全解决',
    completion_assign: '补全转派',
    completion_ignore: '补全忽略',
    archive_mark: '标记待下线',
    archive_confirm: '确认下线',
    archive_archive: '归档下线候选',
    archive_restore: '恢复资源',
    archive_ignore: '下线忽略',
    request_submit: '提交申请',
    request_approve: '批准申请',
    request_reject: '驳回申请',
    request_complete: '完成交付',
  }
  return map[action] || action || '-'
}

function changeSourceText(source) {
  const map = {
    manual: '手工',
    model: '模型配置',
    sync_job: '同步任务',
    authorization: '资源授权',
    source_mapping: '采集来源',
    threshold_policy: '阈值策略',
    resource_metric: '指标快照',
    relation: '资源关系',
    governance: '治理动作',
    resource_request: '资源申请',
  }
  return map[source] || source || '手工'
}

function isAuditResourceAction(action) {
  const value = String(action || '')
  return ['create', 'update', 'delete'].includes(value) || value.startsWith('source_mapping_') || value.startsWith('resource_metric_')
}

function isAuditGovernanceAction(action) {
  const value = String(action || '')
  return value.startsWith('completion_') || value.startsWith('archive_')
}

function isAuditPlatformAction(action) {
  const value = String(action || '')
  return value.startsWith('model_') || value.startsWith('relation_rule_') || value.startsWith('sync_job_') || value.startsWith('authorization_') || value.startsWith('threshold_policy_') || value.startsWith('request_')
}

function changeActionTagType(action) {
  if (action === 'request_approve' || action === 'request_complete') return 'success'
  if (action === 'request_reject') return 'danger'
  if (action === 'create' || action === 'archive_restore' || action === 'completion_resolve' || String(action || '').endsWith('_create')) return 'success'
  if (action === 'update' || action === 'bulk_update' || action === 'archive_mark' || action === 'archive_archive' || action === 'completion_assign' || String(action || '').endsWith('_update')) return 'warning'
  if (action === 'delete' || action === 'archive_confirm' || String(action || '').endsWith('_delete')) return 'danger'
  return 'info'
}

function statusTagType(status) {
  if (status === 'active') return 'success'
  if (status === 'idle') return 'warning'
  if (status === 'stopped') return 'warning'
  if (status === 'offline') return 'danger'
  return 'info'
}

function applicationTierTagType(tier) {
  return { core: 'danger', important: 'warning', normal: 'info' }[String(tier || '').toLowerCase()] || 'info'
}

function statusText(status) {
  if (status === 'active') return '使用中'
  if (status === 'idle') return '停机'
  if (status === 'stopped') return '停机'
  if (status === 'offline') return '已下线'
  return status || '-'
}

function cloudRuntimeStatusValue(row = {}) {
  const attrs = row.attributes || {}
  return String(
    attrs.instance_status
    || attrs.power_state
    || attrs.runtime_status
    || attrs.running_status
    || attrs.status
    || '',
  ).trim().toLowerCase()
}

function isCloudRuntimeStopped(row = {}) {
  const value = cloudRuntimeStatusValue(row)
  return ['stopped', 'stop', 'inactive', 'shutoff', 'poweredoff', 'power_off', 'off'].includes(value)
}

function isCloudRuntimeRunning(row = {}) {
  const value = cloudRuntimeStatusValue(row)
  return ['running', 'available', 'normal', 'active', 'poweredon', 'power_on', 'on'].includes(value)
}

function ledgerStatusText(row = {}) {
  if (row.status === 'offline') return statusText(row.status)
  if (row.status === 'idle' || row.status === 'stopped') return '停机'
  if (isCloudRuntimeStopped(row)) return '停机'
  if (isCloudRuntimeRunning(row)) return '运行中'
  return row.status_display || statusText(row.status)
}

function ledgerStatusTagType(row = {}) {
  if (row.status === 'offline' || row.status === 'idle' || row.status === 'stopped') return statusTagType(row.status)
  if (isCloudRuntimeStopped(row)) return 'warning'
  if (isCloudRuntimeRunning(row)) return 'success'
  return statusTagType(row.status)
}

function environmentText(environment) {
  const value = String(environment || '').trim()
  const normalized = value.toLowerCase()
  if (normalized === 'prod' || normalized === 'production' || value === '生产') return '生产'
  if (normalized === 'test' || normalized === 'testing' || value === '测试') return '测试'
  if (normalized === 'dev' || normalized === 'development' || value === '开发') return '开发'
  if (normalized === 'uat' || value === '联调') return '联调'
  if (normalized === 'integration' || value === '集成') return '集成'
  return value || '-'
}

function principalTypeText(type) {
  if (type === 'group') return '用户组'
  return '用户'
}

function authorizationPermissionText(permission) {
  if (permission === 'manage') return '管理'
  return '查看'
}

function authorizationScopeText(row) {
  return [
    row.business_line || '全部业务线',
    row.environment ? environmentText(row.environment) : '全部环境',
    row.ci_type_name || '全部模型',
  ].join(' / ')
}

function hostKindText(kind) {
  if (kind === 'physical') return '物理机'
  if (kind === 'cloud') return '云主机'
  if (kind === 'virtual') return '虚拟机'
  return kind || '-'
}

function firstHostValue(row, keys) {
  const attrs = row?.attributes || {}
  for (const key of keys) {
    const value = row?.[key] ?? attrs?.[key]
    if (value !== undefined && value !== null && value !== '') return value
  }
  return ''
}

function hostUniqueText(row) {
  return firstHostValue(row, ['unique_id', 'source_unique_id', 'code', 'host_name_code', 'asset_sn', 'serial_number', 'name']) || '-'
}

function hostNameText(row) {
  const unique = String(hostUniqueText(row))
  const name = firstHostValue(row, ['display_name', 'instance_name', 'show_name', 'name', 'hostname', 'host_name'])
  return name && String(name) !== unique ? name : hostKindText(row?.kind)
}

function hostHostnameText(row) {
  return firstHostValue(row, ['hostname', 'host_name', 'bk_host_name', 'name']) || '-'
}

function hostPrivateIpText(row) {
  return firstHostValue(row, ['private_ip', 'inner_ip', 'intranet_ip', 'ip_address', 'ip']) || '-'
}

function hostPublicIpText(row) {
  return firstHostValue(row, ['public_ip', 'outer_ip', 'internet_ip', 'eip', 'wan_ip']) || '-'
}

function hostRuntimeStatusText(row) {
  return firstHostValue(row, ['run_status_display', 'runtime_status', 'running_status']) || row?.status_display || statusText(row?.status)
}

function hostOsText(row) {
  return firstHostValue(row, ['os', 'os_type', 'os_name', 'system_type', 'platform']) || '-'
}

function memoryValueToMb(value) {
  if (value === undefined || value === null || value === '') return ''
  const text = String(value).trim()
  const numeric = Number.parseFloat(text.replace(/,/g, ''))
  if (Number.isNaN(numeric)) return text
  if (/m/i.test(text)) return Math.round(numeric)
  if (/g/i.test(text)) return Math.round(numeric * 1024)
  return numeric > 128 ? Math.round(numeric) : Math.round(numeric * 1024)
}

function hostMemoryMbText(row) {
  const explicitMb = firstHostValue(row, ['memory_mb', 'mem_mb', 'memory_m'])
  if (explicitMb !== '') return memoryValueToMb(explicitMb)
  const gb = firstHostValue(row, ['memory_gb', 'mem_gb'])
  if (gb !== '') return memoryValueToMb(gb)
  const memory = firstHostValue(row, ['memory', 'mem'])
  if (memory !== '') return memoryValueToMb(memory)
  return '-'
}

function hostTerminalId(row) {
  return firstHostValue(row, ['ops_host_id', 'host_id', 'host_asset_id', 'resource_host_id', 'terminal_host_id'])
}

function resourceSpecText(row) {
  const specs = []
  if (row.cpu) specs.push(`${row.cpu}C`)
  if (row.memory_gb) specs.push(`${row.memory_gb}G`)
  if (row.disk_gb) specs.push(`${row.disk_gb}G磁盘`)
  if (row.instance_type) specs.push(row.instance_type)
  return specs.join(' / ') || row.region || row.cloud_provider || '-'
}

function daysUntil(value) {
  if (!value) return null
  const date = new Date(`${String(value).slice(0, 10)}T00:00:00`)
  if (Number.isNaN(date.getTime())) return null
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  return Math.ceil((date.getTime() - today.getTime()) / 86400000)
}

function serviceExpiryDate(row = {}) {
  const attrs = row.attributes || {}
  return row.expire_date || attrs.service_expiry_date || attrs.warranty_end_date || attrs.warranty_expire_date || ''
}

function serviceExpiryState(row = {}) {
  const attrs = row.attributes || {}
  const hasExplicitRisk = row.days_left !== undefined && row.days_left !== null
  const expiryDate = serviceExpiryDate(row)
  if (!expiryDate && !hasExplicitRisk && !isThirdPartyLedgerRow(row)) return { status: 'normal', label: '未设置服务周期' }
  const days = hasExplicitRisk ? Number(row.days_left) : daysUntil(expiryDate)
  const warningDays = Number(attrs.service_expire_warning_days || 30)
  if (days === null) return { status: 'missing', label: '未登记到期日' }
  if (days < 0) return { status: 'expired', label: `已逾期 ${Math.abs(days)} 天` }
  if (days === 0) return { status: 'urgent', label: '今日到期' }
  if (days <= 7) return { status: 'urgent', label: `剩余 ${days} 天` }
  if (days <= Math.max(warningDays, 0)) return { status: 'warning', label: `剩余 ${days} 天` }
  return { status: 'normal', label: `剩余 ${days} 天` }
}

function serviceExpiryStatusText(row) {
  return serviceExpiryState(row).label
}

function serviceExpiryTagType(row) {
  const status = serviceExpiryState(row).status
  if (status === 'expired' || status === 'urgent') return 'danger'
  if (status === 'warning') return 'warning'
  if (status === 'normal') return 'success'
  return 'info'
}

function externalExpiryState(row) {
  return serviceExpiryState(row)
}

function externalExpiryText(row) {
  return externalExpiryState(row).label
}

function externalExpiryTagType(row) {
  const status = externalExpiryState(row).status
  if (status === 'expired') return 'danger'
  if (status === 'urgent') return 'danger'
  if (status === 'warning') return 'warning'
  if (status === 'normal') return 'success'
  return 'info'
}

function idcLifecycleText(status) {
  const map = {
    pending_rack: '待上架',
    running: '运行中',
    maintenance: '维修中',
    pending_offline: '待下线',
    offline: '已下线',
    retired: '已报废',
  }
  return map[status] || status || '未登记'
}

function idcLifecycleTagType(status) {
  if (status === 'running') return 'success'
  if (status === 'maintenance' || status === 'pending_offline') return 'warning'
  if (status === 'offline' || status === 'retired') return 'danger'
  return 'info'
}

function syncStatusTagType(status) {
  if (status === 'success') return 'success'
  if (status === 'partial') return 'warning'
  if (status === 'failed') return 'danger'
  if (status === 'missing') return 'warning'
  if (status === 'conflict') return 'danger'
  return 'info'
}

function collectionHealthTagType(status) {
  if (status === 'healthy') return 'success'
  if (status === 'due' || status === 'pending') return 'warning'
  if (status === 'failed') return 'danger'
  return 'info'
}

function collectionHealthText(status) {
  const map = {
    healthy: '健康',
    due: '待执行',
    failed: '待治理',
    disabled: '未启用',
    pending: '待观察',
  }
  return map[status] || status || '-'
}

function sourceMappingStatusText(status) {
  if (status === 'success') return '成功'
  if (status === 'failed') return '失败'
  if (status === 'missing') return '来源缺失'
  if (status === 'conflict') return '冲突'
  return status || '-'
}

function syncRecordStatusTagType(status) {
  if (status === 'failed') return 'danger'
  if (status === 'resolved') return 'success'
  if (status === 'success') return 'success'
  return 'info'
}

function syncRecordStatusText(status) {
  if (status === 'failed') return '失败'
  if (status === 'resolved') return '已处理'
  if (status === 'success') return '成功'
  return status || '-'
}

function syncGovernanceIssueText(row) {
  if (row?.relation_issue) return '自动关系'
  if (row?.action === 'conflict') return '来源冲突'
  return '同步失败'
}

function syncRelationIssueText(row) {
  const summary = row?.relation_issue_summary || row?.after?._sync_relations || {}
  const failed = Number(summary.failed || row?.relation_issue_count || 0)
  if (!failed) return ''
  const parts = [`自动关系失败 ${failed}`]
  if (summary.peer_not_found) parts.push(`未找到对端 ${summary.peer_not_found}`)
  if (summary.validation_failed) parts.push(`规则校验失败 ${summary.validation_failed}`)
  const firstError = Array.isArray(summary.errors) ? summary.errors[0] : null
  if (firstError?.relation_type) parts.push(relationTypeLabel(firstError.relation_type))
  return parts.join('，')
}

function syncGovernanceReasonText(row) {
  if (row?.relation_issue) return syncRelationIssueText(row) || syncPreviewText(row)
  return row?.error_message || syncPreviewText(row)
}

function retryStatusTagType(status) {
  if (status === 'success') return 'success'
  if (status === 'failed') return 'danger'
  return 'info'
}

function retryStatusText(status) {
  if (status === 'success') return '重试成功'
  if (status === 'failed') return '重试失败'
  return '未重试'
}

function syncActionTagType(action) {
  if (action === 'create') return 'success'
  if (action === 'update') return 'warning'
  if (action === 'archive_candidate') return 'danger'
  if (action === 'fail' || action === 'conflict') return 'danger'
  return 'info'
}

function syncActionText(action) {
  const map = {
    create: '新增',
    update: '更新',
    skip: '跳过',
    fail: '失败',
    conflict: '冲突',
    archive_candidate: '待下线',
  }
  return map[action] || action || '-'
}

function syncPreviewText(row) {
  const relationSummary = row.after?._sync_relations
  if (relationSummary?.total) {
    const preview = relationSummary.preview ? `，预计 ${relationSummary.preview}` : ''
    return `自动关系：创建 ${relationSummary.created || 0}${preview}，跳过 ${relationSummary.skipped || 0}，失败 ${relationSummary.failed || 0}`
  }
  if (row.error_message) return row.error_message
  const diffKeys = Object.keys(row.diff || {})
  if (diffKeys.length) return `变更字段：${diffKeys.join('、')}`
  if (row.action === 'create') return '来源端发现新资源'
  if (row.action === 'archive_candidate') return '全量同步未发现该来源资源，已进入待下线确认'
  if (row.action === 'skip') return '无变化'
  return '-'
}

function syncRunResultText(summary = {}) {
  const base = `同步任务已执行：新增 ${summary.create || 0}，更新 ${summary.update || 0}，跳过 ${summary.skip || 0}`
  const failTotal = Number(summary.fail || 0) + Number(summary.conflict || 0)
  const baseWithFailure = failTotal ? `${base}，失败 ${failTotal}` : base
  const relationTotal = Number(summary.relation_created || 0) + Number(summary.relation_skipped || 0) + Number(summary.relation_failed || 0)
  if (!relationTotal) return baseWithFailure
  return `${baseWithFailure}；自动关系创建 ${summary.relation_created || 0}，跳过 ${summary.relation_skipped || 0}，失败 ${summary.relation_failed || 0}`
}

function suggestionTagType(severity) {
  if (severity === 'exceeded' || severity === 'critical' || severity === 'danger') return 'danger'
  if (severity === 'warning') return 'warning'
  return 'info'
}

function overviewSuggestionTypeText(type) {
  const labels = {
    capacity: '容量风险',
    governance: '资料治理',
    sync: '同步失败',
    archive: '待下线确认',
    expiry: '服务到期',
    service_expiry: '服务到期',
    third_party_service_expiry: '服务到期',
    asset_service_expiry: '服务到期',
  }
  return labels[type] || type || '治理建议'
}

function governanceIsOverdue(row) {
  if (row?.is_overdue === true) return true
  if (!row?.due_at) return false
  const due = new Date(row.due_at).getTime()
  return Number.isFinite(due) && Date.now() > due
}

function governanceSlaText(row) {
  const age = Number(row?.age_days || 0)
  const dueDays = Number(row?.due_days || 0)
  if (!dueDays) return age ? `积压${age}天` : '今日新增'
  if (governanceIsOverdue(row)) return `逾期${Math.max(age - dueDays, 1)}天`
  const remaining = Math.max(dueDays - age, 0)
  return remaining ? `剩${remaining}天` : '今日到期'
}

function governanceSlaTagType(row) {
  if (governanceIsOverdue(row)) return 'danger'
  const age = Number(row?.age_days || 0)
  const dueDays = Number(row?.due_days || 0)
  if (dueDays && dueDays - age <= 1) return 'warning'
  return 'success'
}

function formatTime(value) {
  if (!value) return '-'
  return new Date(value).toLocaleString()
}

watch(tabs, ensureAccessibleRoute, { immediate: true })
watch(ciTypes, () => {
  if (selectedModelId.value && !ciTypes.value.some(item => String(item.id) === String(selectedModelId.value))) {
    selectedModelId.value = ''
    modelResourceItems.value = []
  }
})
watch(() => ciForm.ci_type, () => {
  if (!ciDialogVisible.value) return
  syncCiFormAttributeValues(ciForm.baseAttributes || {})
})
watch(ciFormModelFields, () => {
  if (!ciDialogVisible.value) return
  syncCiFormAttributeValues(ciForm.baseAttributes || {})
})
watch(() => cloudCredentialForm.provider, (provider) => {
  cloudCredentialKind.value = privateCloudProviderSet.has(provider) ? 'private' : 'public'
  cloudCredentialForm.sync_product_keys = defaultProductKeysForProvider(provider)
  if (provider === 'vsphere') {
    cloudCredentialForm.auth_mode = 'secret'
    cloudCredentialForm.private_cloud_version = cloudCredentialForm.private_cloud_version || defaultPrivateCloudVersion
    if (!cloudCredentialForm.default_region || ['cn-hangzhou', 'cn-north-4'].includes(cloudCredentialForm.default_region)) {
      cloudCredentialForm.default_region = 'private-cloud-prod'
    }
    return
  }
  cloudCredentialForm.private_cloud_version = ''
  if (cloudCredentialForm.auth_mode === 'secret') cloudCredentialForm.auth_mode = 'aksk'
  if (provider === 'huawei' && (!cloudCredentialForm.default_region || cloudCredentialForm.default_region === 'cn-hangzhou')) {
    cloudCredentialForm.default_region = 'cn-north-4'
  }
  if (provider === 'aliyun' && (!cloudCredentialForm.default_region || cloudCredentialForm.default_region === 'cn-north-4')) {
    cloudCredentialForm.default_region = 'cn-hangzhou'
  }
})
watch(() => relationForm.direction, async () => {
  if (!relationDialogVisible.value) return
  syncRelationFormWithRules()
  await fetchRelationTargets()
})
watch(() => relationForm.relation_type, async () => {
  if (!relationDialogVisible.value) return
  relationForm.targets = []
  await fetchRelationTargets()
})
watch(ledgerFilters, scheduleCmdbUiStateSave, { deep: true })
watch(viewFilters, scheduleCmdbUiStateSave, { deep: true })
watch([
  ledgerViewMode,
  ledgerTreeContext,
  ledgerTreeKeyword,
  expandedLedgerTreeKeys,
  collapsedLedgerTreeKeys,
  viewMode,
  applicationViewKeyword,
  applicationViewRisk,
  applicationViewOwner,
  opsanyViewKeyword,
  selectedOpsanyViewNode,
  modelCatalogTreeMode,
  modelCatalogTreeContext,
  modelCatalogTreeKeyword,
  expandedModelCatalogTreeKeys,
  collapsedModelCatalogTreeKeys,
  activeModelGroupKey,
  opsanyModelKeyword,
  opsanyModelStatus,
  selectedModelId,
  modelResourceFilters,
], scheduleCmdbUiStateSave, { deep: true })
watch(() => route.name, () => {
  fetchActiveTabData()
})
watch(() => [route.name, route.query.detail_ci_id, route.query.ci_id], () => {
  if (route.name !== 'CmdbLedger') {
    openedLedgerDetailId.value = ''
    return
  }
  openLedgerDetailFromRoute()
})
watch(() => [canViewCi.value, canViewRequests.value], ([canViewCiNow, canViewRequestsNow], [prevCanViewCi, prevCanViewRequests] = []) => {
  const ciBecameReady = canViewCiNow && !prevCanViewCi
  const requestBecameReady = canViewRequestsNow && !prevCanViewRequests
  if (activeTab.value === 'ledger' && ciBecameReady) fetchResourceNodeTree()
  if (activeTab.value === 'requests' && requestBecameReady) fetchResourceNodeTree()
  if (activeTab.value === 'governance' && ciBecameReady) Promise.allSettled([fetchResourceNodeTree(), fetchLedgerTree()])
})
watch(() => [route.name, route.params.id], () => {
  if (isModelDetailRoute.value) syncModelDetailSelection()
})
watch(ciDetailVisible, (visible) => {
  if (!visible) disposeCiDetailWaterlineChart()
})
onBeforeUnmount(disposeCiDetailWaterlineChart)
onMounted(async () => {
  restoreCmdbUiState()
  await reloadAll()
  await openLedgerDetailFromRoute()
})
</script>

<style scoped>
.cmdb-page{display:flex;flex-direction:column;gap:6px}
.cmdb-page--model{gap:6px}
.panel{background:linear-gradient(180deg,#fff 0%,#f8fbff 100%);border:1px solid rgba(36,91,219,.09);border-radius:14px;box-shadow:0 14px 34px rgba(15,23,42,.06);padding:14px 16px}
.hero{background:linear-gradient(135deg,#fbfdff 0%,#f7faff 52%,#f9fbfd 100%);display:flex;align-items:center;justify-content:space-between}
.hero.panel{border-radius:20px}
.cmdb-hero-title-row{display:flex;align-items:center;gap:12px;flex-wrap:wrap}
.cmdb-header-icon{width:42px;height:42px;border-radius:14px;display:inline-flex;align-items:center;justify-content:center;font-size:20px;color:#245bdb;background:#e8f0ff}
.hero h2{margin:0;color:#0f172a;font-size:23px}
.page-inline-desc{margin:0;color:#64748b;font-size:13px}
.audit-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px}
.audit-card{border:1px solid rgba(148,163,184,.18);background:#fff;border-radius:14px;min-height:68px;padding:14px 16px;text-align:left;box-shadow:0 12px 26px rgba(15,23,42,.04);cursor:pointer}
.audit-card.is-active{box-shadow:inset 0 0 0 1px rgba(51,112,255,.18),0 12px 26px rgba(15,23,42,.04);background:#f8fbff}
.audit-card--success{background:#f7fefb}.audit-card--warning{background:#fffaf0}.audit-card--danger{background:#fff7f7}
.stat-value{font-size:24px;line-height:1.05;color:#0f172a;font-weight:700}.stat-label{margin-top:4px;color:#64748b;font-size:13px;font-weight:600}
.governance-workspace,.governance-panel{min-width:0}
.governance-panel :deep(.el-table){width:100%}
.cmdb-page--governance .cmdb-content-card{overflow:hidden}
.governance-layout{grid-template-columns:240px minmax(0,1fr);gap:16px}
.governance-tree-panel{min-height:520px;border-right:1px solid rgba(148,163,184,.2);padding-right:14px}
.governance-tree-panel .opsany-view-tree-list{max-height:540px;overflow:auto;padding-right:2px}
.governance-tree-node{min-height:34px;border-radius:8px}
.governance-tree-node:not(.ledger-resource-tree-node){padding-left:8px}
.governance-tree-node>span{display:inline-flex;align-items:center;gap:7px}
.governance-tree-node>span .el-icon{flex:none;font-size:14px;color:#64748b}
.governance-tree-node:hover,.governance-tree-node.active{background:#e8f0ff;color:#245bdb}
.governance-tree-node:hover>span .el-icon,.governance-tree-node.active>span .el-icon{color:#245bdb}
.governance-tree-node strong{min-width:26px;height:20px;border-radius:6px;background:#f1f5f9;color:#64748b;font-weight:700}
.governance-tree-node.active strong{background:#fff;color:#245bdb;box-shadow:inset 0 0 0 1px rgba(51,112,255,.12)}
.governance-main-panel{min-width:0;padding:0;border:0;background:#fff}
.governance-category-view{margin-bottom:12px}
.governance-category-head{min-height:48px;display:flex;align-items:center;justify-content:space-between;gap:16px;padding-bottom:10px;border-bottom:1px solid rgba(148,163,184,.16)}
.governance-category-head>div:first-child{min-width:0;display:flex;align-items:baseline;gap:9px;flex-wrap:wrap}
.governance-category-head>div:first-child strong{color:#0f172a;font-size:15px}
.governance-category-head>div:first-child span{color:#64748b;font-size:12px}
.governance-category-total{flex:none;display:inline-flex;align-items:baseline;gap:5px;color:#64748b;font-size:12px}
.governance-category-total strong{color:#245bdb;font-size:24px;line-height:1}
.governance-category-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}
.governance-category-card{--governance-accent:#d97706;--governance-soft:#fff8eb;box-sizing:border-box;min-width:0;min-height:168px;padding:0;border:1px solid rgba(148,163,184,.2);border-radius:14px;background:#fff;box-shadow:0 12px 26px rgba(15,23,42,.04);color:inherit;text-align:left;cursor:pointer;overflow:hidden;transition:border-color .2s ease,box-shadow .2s ease,transform .2s ease}
.governance-category-card.is-danger{--governance-accent:#dc2626;--governance-soft:#fff3f3}
.governance-category-card.is-success{--governance-accent:#059669;--governance-soft:#effbf6}
.governance-category-card:hover{border-color:color-mix(in srgb,var(--governance-accent) 30%,#cbd5e1);box-shadow:0 16px 34px rgba(15,23,42,.08);transform:translateY(-1px)}
.governance-category-card:focus-visible{outline:2px solid rgba(36,91,219,.25);outline-offset:2px}
.governance-category-card-top{display:flex;align-items:flex-start;gap:11px;padding:16px 16px 8px}
.governance-category-icon{flex:none;width:36px;height:36px;border-radius:10px;display:inline-flex;align-items:center;justify-content:center;background:var(--governance-soft);color:var(--governance-accent);font-size:18px}
.governance-category-copy{min-width:0;display:flex;flex-direction:column;gap:4px;padding-top:1px}
.governance-category-copy strong{color:#0f172a;font-size:14px;line-height:1.3}
.governance-category-copy small{color:#64748b;font-size:12px;line-height:1.55}
.governance-category-metric{display:flex;align-items:baseline;gap:6px;padding:5px 16px 14px}
.governance-category-metric strong{color:#0f172a;font-size:28px;line-height:1;font-weight:750}
.governance-category-metric small{color:#64748b;font-size:12px}
.governance-category-card-footer{min-height:38px;padding:0 16px;border-top:1px solid rgba(148,163,184,.13);background:#fbfcfe;display:flex;align-items:center;justify-content:space-between;gap:12px;color:#64748b;font-size:12px}
.governance-category-card-footer>span:last-child{display:inline-flex;align-items:center;gap:4px;color:#245bdb;font-weight:700}
.governance-category-status{display:inline-flex;align-items:center;gap:6px}
.governance-category-status::before{content:'';width:6px;height:6px;border-radius:50%;background:var(--governance-accent)}
.governance-panel-head{align-items:center;margin-bottom:10px;padding-bottom:10px;border-bottom:1px solid rgba(148,163,184,.14)}
.governance-panel-head .mini-panel-title{font-size:14px;margin-bottom:3px}
.governance-detail-title{min-width:0;display:flex;align-items:center;gap:12px}
.governance-detail-title>div{min-width:0}
.governance-back-button{flex:none;height:34px;padding:0 14px;border-radius:8px;font-size:13px;font-weight:700}
.governance-panel-actions{flex:0 0 auto}
.governance-panel-actions .el-button{margin-left:0}
.governance-issue-cell{min-width:0;display:flex;flex-direction:column;align-items:flex-start;gap:5px}
.governance-issue-cell span:last-child{max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#475569;font-size:12px}
.governance-panel .compact-stack small.is-overdue{color:#dc2626;font-weight:700}
.governance-standard-table :deep(.el-table__cell){padding:10px 0;vertical-align:middle}
.governance-standard-table :deep(th.el-table__cell){padding:9px 0}
.governance-row-actions{display:flex;align-items:center;gap:2px;flex-wrap:wrap;white-space:nowrap}
.governance-row-actions .el-button{margin-left:0}
.governance-asset-cell{min-width:0;display:flex;align-items:center;gap:10px}
.governance-asset-icon{width:32px;height:32px;flex:none;border:1px solid rgba(36,91,219,.13);border-radius:7px;background:#eef4ff;color:#245bdb;display:inline-flex;align-items:center;justify-content:center;font-size:16px}
.governance-asset-copy{min-width:0;display:flex;flex:1;flex-direction:column;gap:4px}
.governance-asset-copy>strong{display:block;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#0f172a;font-size:13px;font-weight:700;line-height:1.35}
.governance-asset-meta{min-width:0;display:flex;align-items:center;gap:7px;color:#64748b;font-size:11px;line-height:1.35}
.governance-asset-meta>span{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.governance-asset-meta>code{flex:none;padding:1px 5px;border-radius:4px;background:#f1f5f9;color:#64748b;font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,"Liberation Mono",monospace;font-size:10px;line-height:1.4}
.sync-governance-table :deep(.el-table__cell){padding:10px 0;vertical-align:top}
.sync-governance-table :deep(th.el-table__cell){padding:9px 0;vertical-align:middle}
.sync-governance-subject{min-width:0;display:flex;flex-direction:column;gap:5px}
.sync-governance-subject>strong{display:block;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#0f172a;font-size:13px;font-weight:700;line-height:1.4}
.sync-governance-subject>span{display:block;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#64748b;font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,"Liberation Mono",monospace;font-size:11px;line-height:1.35}
.sync-governance-task-line{min-width:0;display:flex;align-items:center;gap:7px;padding-top:1px}
.sync-governance-task-line>span{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#475569;font-size:12px;line-height:1.35}
.sync-governance-task-line em{flex:none;padding:1px 5px;border-radius:4px;background:#f1f5f9;color:#64748b;font-size:10px;font-style:normal;line-height:1.5}
.sync-governance-issue{min-width:0;display:flex;flex-direction:column;align-items:flex-start;gap:6px}
.sync-governance-issue-head{display:flex;align-items:center;gap:6px;min-width:0;flex-wrap:wrap}
.sync-governance-issue p{display:-webkit-box;max-width:100%;margin:0;overflow:hidden;-webkit-box-orient:vertical;-webkit-line-clamp:2;color:#475569;font-size:12px;line-height:1.5;overflow-wrap:anywhere}
.sync-governance-time{color:#94a3b8;font-size:11px;line-height:1.35;white-space:nowrap}
.sync-governance-actions{display:flex;align-items:center;gap:2px;min-height:24px;white-space:nowrap}
.sync-governance-actions .el-button{margin-left:0}
.cmdb-tabs{display:flex;width:100%;padding:3px;gap:8px;border-radius:12px;border:1px solid rgba(148,163,184,.16);background:#fff;box-shadow:0 12px 26px rgba(15,23,42,.04);overflow:auto}
.cmdb-primary-tabs{position:relative;margin:0}
.neo-tab-btn{min-height:38px;padding:0 18px;border:0;border-radius:8px;background:transparent;color:#475569;font-size:13px;font-weight:700;line-height:1.2;display:inline-flex;align-items:center;gap:6px;white-space:nowrap;cursor:pointer}
.neo-tab-btn .el-icon{font-size:15px}
.neo-tab-btn:hover{background:rgba(51,112,255,.06);color:#245bdb}
.neo-tab-btn.active{background:#e8f0ff;color:#245bdb;box-shadow:inset 0 0 0 1px rgba(51,112,255,.1)}
.workbench-card{background:#fff;border:1px solid rgba(148,163,184,.18);border-radius:14px;box-shadow:0 14px 32px rgba(15,23,42,.05);padding:14px 16px}
.cmdb-content-card--opsany{border-radius:14px;box-shadow:0 14px 32px rgba(15,23,42,.05);border-color:rgba(148,163,184,.18);background:#fff;padding:14px 16px}
.cmdb-content-card--opsany .section-toolbar{align-items:center;margin-bottom:10px;padding-bottom:0;border-bottom:0}
.cmdb-content-card--opsany .workbench-card-actions{padding-top:2px}
.section-toolbar{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:10px}
.toolbar-head{display:inline-flex;align-items:baseline;gap:8px;flex-wrap:wrap}
.toolbar-title{font-size:15px;font-weight:800;color:#0f172a}.toolbar-desc{font-size:12px;color:#64748b}
.opsany-page-head{display:inline-flex;align-items:baseline;gap:8px;flex-wrap:wrap}
.opsany-page-head .toolbar-title{font-size:15px;line-height:1.3;font-weight:800;color:#0f172a}
.opsany-page-head .toolbar-desc{color:#64748b;font-size:12px}
.opsany-breadcrumb,.opsany-help-link{display:none}
.workbench-card-actions{display:flex;align-items:center;justify-content:flex-end;gap:8px;flex-wrap:wrap}
.workbench-toolbar{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:10px;padding:8px;border:1px solid rgba(148,163,184,.16);border-radius:10px;background:#f8fafc}
.workbench-toolbar-left,.workbench-toolbar-right{display:flex;align-items:center;gap:8px}
.overview-scope-toolbar{display:flex;align-items:center;justify-content:flex-start;gap:8px;flex-wrap:wrap;margin:0 0 8px;padding:0}
.overview-scope-option{min-width:0;display:flex;align-items:center;justify-content:space-between;gap:10px}
.overview-scope-option span{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.total-resource-panel{border:1px solid rgba(148,163,184,.14);border-radius:12px;background:linear-gradient(180deg,#fff 0%,#f8fbff 100%);padding:14px;margin-bottom:8px}
.total-resource-head{display:flex;align-items:flex-start;justify-content:space-between;gap:10px;margin-bottom:8px;min-width:0}
.total-resource-status{flex:0 0 auto}
.total-resource-actions{display:flex;align-items:center;justify-content:flex-end;gap:8px;flex-wrap:wrap;min-width:0}
.overview-dimension-tabs{flex:none}
.overview-dimension-tabs button{min-height:28px;padding:0 10px;font-size:12px}
.resource-usage-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}
.resource-usage-card{min-width:0;min-height:168px;border:1px solid rgba(148,163,184,.16);border-radius:12px;background:#fff;padding:12px;display:flex;flex-direction:column;gap:9px}
.resource-usage-card.is-danger{background:#fff7f7;border-color:rgba(239,68,68,.18)}
.resource-usage-card.is-warning{background:#fffbeb;border-color:rgba(245,158,11,.18)}
.resource-usage-card.is-success{background:#f7fefb;border-color:rgba(34,197,94,.16)}
.resource-usage-card.is-info{background:#f8fbff;border-color:rgba(51,112,255,.14)}
.resource-usage-card.is-empty{background:#f8fafc}
.resource-usage-top,.resource-usage-meta{display:flex;align-items:center;justify-content:space-between;gap:8px;min-width:0}
.resource-usage-top span{font-size:13px;font-weight:700;color:#334155}
.resource-usage-top strong{font-size:22px;line-height:1;color:#0f172a}
.resource-usage-main-value{display:flex;align-items:baseline;gap:6px;flex:0 0 auto}
.resource-usage-main-value small{color:#64748b;font-size:11px;font-weight:700;line-height:1}
.resource-usage-main-value strong{font-size:22px;line-height:1;color:#0f172a}
.resource-usage-meta span{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:12px;color:#64748b}
.resource-waterline-stack{display:flex;flex-direction:column;gap:9px}
.resource-waterline-line{display:flex;flex-direction:column;gap:4px;min-width:0}
.resource-waterline-line-head{display:flex;align-items:flex-start;justify-content:space-between;gap:10px;min-width:0}
.resource-waterline-line-head>div{min-width:0;display:flex;flex-direction:column;gap:2px}
.resource-waterline-line-head span{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#475569;font-size:11px;font-weight:800}
.resource-waterline-line-head em{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-style:normal;color:#94a3b8;font-size:10px;line-height:1.2}
.resource-waterline-line-head strong{flex:0 0 auto;color:#0f172a;font-size:13px;line-height:1;font-weight:800}
.resource-waterline-values{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:6px}
.resource-waterline-values span{min-width:0;border:1px solid rgba(148,163,184,.12);border-radius:7px;background:rgba(255,255,255,.72);padding:4px 6px;color:#64748b;font-size:10px;line-height:1.15;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.resource-waterline-values strong{color:#0f172a;font-size:11px;font-weight:800}
.resource-waterline-line.is-vm .resource-waterline-line-head span{color:#15803d}
.resource-waterline-line.is-pool .resource-waterline-line-head span{color:#245bdb}
.resource-waterline-line.is-muted .resource-waterline-line-head span,.resource-waterline-line.is-muted .resource-waterline-line-head strong,.resource-waterline-line.is-muted .resource-waterline-values strong{color:#94a3b8}
.resource-usage-breakdown{display:grid;grid-template-columns:repeat(auto-fit,minmax(92px,1fr));gap:6px}
.resource-usage-breakdown span{min-width:0;border:1px solid rgba(148,163,184,.14);border-radius:8px;background:rgba(248,250,252,.82);padding:6px 7px;display:flex;flex-direction:column;gap:3px}
.resource-usage-breakdown em{font-style:normal;font-size:11px;line-height:1.1;color:#64748b}
.resource-usage-breakdown strong{min-width:0;font-size:12px;line-height:1.18;color:#0f172a;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.overview-metric-notice-list{display:flex;flex-direction:column;gap:6px;margin-top:10px}
.overview-metric-notice-list--under-title{margin:0 0 10px}
.overview-metric-notice{display:flex;align-items:center;justify-content:space-between;gap:10px;border:1px solid rgba(148,163,184,.16);border-radius:10px;background:#f8fbff;padding:8px 10px;min-width:0}
.overview-metric-notice.is-warning{border-color:rgba(245,158,11,.22);background:#fffbeb}
.overview-metric-notice.is-info{border-color:rgba(51,112,255,.16);background:#f8fbff}
.overview-metric-notice span{font-size:12px;font-weight:800;color:#0f172a;white-space:nowrap}
.overview-metric-notice em{min-width:0;font-style:normal;font-size:12px;color:#64748b;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.phase-one-guide{border:1px solid rgba(51,112,255,.12);border-radius:12px;background:#f8fbff;padding:12px;margin-bottom:10px}
.phase-one-guide-head{display:flex;align-items:flex-start;justify-content:space-between;gap:10px;margin-bottom:10px}
.phase-one-guide-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}
.phase-one-guide-card{min-width:0;border:1px solid rgba(148,163,184,.16);border-radius:12px;background:#fff;padding:10px;display:grid;grid-template-columns:32px minmax(0,1fr) auto;align-items:center;gap:9px;text-align:left;cursor:pointer;transition:all .16s ease}
.phase-one-guide-card:hover{border-color:rgba(36,91,219,.18);box-shadow:0 12px 24px rgba(36,91,219,.06);transform:translateY(-1px)}
.phase-one-guide-index{width:32px;height:32px;border-radius:10px;background:#e8f0ff;color:#245bdb;display:inline-flex;align-items:center;justify-content:center;font-size:12px;font-weight:800}
.phase-one-guide-main{min-width:0;display:flex;flex-direction:column;gap:3px}
.phase-one-guide-main strong{font-size:13px;color:#0f172a}
.phase-one-guide-main span{font-size:12px;color:#64748b;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.phase-one-coverage{border:1px solid rgba(148,163,184,.14);border-radius:12px;background:linear-gradient(180deg,#fff 0%,#fbfdff 100%);padding:12px;margin-bottom:10px}
.phase-one-coverage-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}
.phase-one-coverage-card{min-width:0;border:1px solid rgba(148,163,184,.16);border-radius:12px;background:#fff;padding:11px 12px;display:flex;flex-direction:column;gap:8px;text-align:left;cursor:pointer;transition:all .16s ease}
.phase-one-coverage-card:hover{border-color:rgba(36,91,219,.18);box-shadow:0 12px 24px rgba(36,91,219,.06);transform:translateY(-1px)}
.phase-one-coverage-card.is-ready{background:#f7fefb;border-color:rgba(34,197,94,.16)}
.phase-one-coverage-card.is-pending{background:#fffaf0;border-color:rgba(245,158,11,.16)}
.phase-one-coverage-top{display:flex;align-items:center;justify-content:space-between;gap:8px;min-width:0}
.phase-one-coverage-top strong{font-size:13px;color:#0f172a;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.phase-one-coverage-value{font-size:22px;font-weight:800;line-height:1;color:#0f172a}
.phase-one-coverage-desc{min-height:34px;color:#64748b;font-size:12px;line-height:1.45;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.phase-one-actions{border:1px solid rgba(51,112,255,.10);border-radius:12px;background:#fff;padding:12px;margin-bottom:10px}
.phase-one-action-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}
.phase-one-action-card{min-width:0;border:1px solid rgba(245,158,11,.18);border-radius:12px;background:#fffaf0;padding:10px 12px;display:grid;grid-template-columns:32px minmax(0,1fr) auto;align-items:center;gap:10px;text-align:left;cursor:pointer;transition:all .16s ease}
.phase-one-action-card:hover{border-color:rgba(36,91,219,.2);box-shadow:0 12px 24px rgba(36,91,219,.06);transform:translateY(-1px)}
.phase-one-action-card.done{background:#f7fefb;border-color:rgba(34,197,94,.16)}
.phase-one-action-icon{width:32px;height:32px;border-radius:10px;background:#fff3d7;color:#b45309;display:inline-flex;align-items:center;justify-content:center}
.phase-one-action-card.done .phase-one-action-icon{background:#dcfce7;color:#15803d}
.phase-one-action-main{min-width:0;display:flex;flex-direction:column;gap:3px}
.phase-one-action-main strong{font-size:13px;color:#0f172a;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.phase-one-action-main span{font-size:12px;color:#64748b;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.overview-workspace-sections{display:flex;flex-direction:column;gap:10px;margin-bottom:10px}
.overview-workspace-section{border:1px solid rgba(148,163,184,.14);border-radius:12px;background:#fbfdff;padding:10px}
.overview-section-head{display:flex;align-items:baseline;gap:8px;flex-wrap:wrap;margin-bottom:8px}
.overview-section-head span{font-size:13px;font-weight:800;color:#0f172a}
.overview-section-head small{font-size:12px;color:#64748b}
.overview-entry-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:10px}
.overview-entry-card{min-width:0;border:1px solid rgba(148,163,184,.18);border-radius:12px;background:linear-gradient(180deg,#fff 0%,#fbfdff 100%);padding:12px;display:grid;grid-template-columns:34px minmax(0,1fr) auto;align-items:center;gap:10px;text-align:left;box-shadow:0 10px 22px rgba(15,23,42,.04);cursor:pointer}
.overview-entry-card:hover{border-color:rgba(36,91,219,.18);box-shadow:0 12px 24px rgba(36,91,219,.06)}
.overview-entry-icon{width:34px;height:34px;border-radius:10px;background:#e8f0ff;color:#245bdb;display:inline-flex;align-items:center;justify-content:center;font-size:16px}
.overview-entry-main{min-width:0;display:flex;flex-direction:column;gap:3px}
.overview-entry-main strong{font-size:13px;color:#0f172a}
.overview-entry-main span{font-size:12px;color:#64748b;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.overview-entry-value{font-size:22px;font-weight:800;color:#0f172a}
.cmdb-overview-grid,.governance-grid,.model-grid,.threshold-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}
.governance-grid,.model-grid,.threshold-grid{grid-template-columns:repeat(2,minmax(0,1fr))}
.mini-panel{border:1px solid rgba(148,163,184,.18);border-radius:12px;padding:12px;background:#fbfdff;min-width:0}
.mini-panel--wide{grid-column:span 1}
.governance-grid .mini-panel--wide{grid-column:1/-1}
.mini-panel-head{display:flex;align-items:flex-start;justify-content:space-between;gap:10px;margin-bottom:8px}
.mini-panel-title{font-size:13px;font-weight:800;color:#0f172a;margin-bottom:8px}
.mini-panel-title-link{width:100%;margin:0 0 8px;padding:0;border:0;background:transparent;display:flex;align-items:center;justify-content:space-between;gap:8px;color:#0f172a;font-size:13px;font-weight:800;cursor:pointer;text-align:left}
.mini-panel-title-link span:last-child{color:#245bdb;font-size:12px;font-weight:700}
.mini-panel-heading{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:8px}
.mini-panel-heading .mini-panel-title{margin-bottom:0}
.mini-panel-heading--inline{display:inline-flex;align-items:baseline;justify-content:flex-start;flex-wrap:wrap;gap:8px;margin-bottom:0;min-width:0}
.mini-panel-heading--inline .mini-panel-desc{min-width:0}
.mini-panel-head .mini-panel-title{margin-bottom:3px}
.mini-panel-head .mini-panel-heading--inline .mini-panel-title{margin-bottom:0}
.inline-actions{display:flex;align-items:center;gap:6px;flex-wrap:wrap;justify-content:flex-end}
.ledger-head-actions,.model-resource-actions{gap:4px;flex:0 0 auto}
.ledger-head-actions .el-button,.model-resource-actions .el-button{margin-left:0}
.mini-panel-desc{font-size:12px;color:#64748b;line-height:1.4}
.distribution-row,.suggestion-row{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:7px 0;border-bottom:1px solid rgba(148,163,184,.12);font-size:13px;color:#475569}
.suggestion-copy{display:flex;align-items:center;gap:8px;min-width:0;flex:1}
.suggestion-copy .suggestion-title{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.suggestion-actions{display:flex;align-items:center;gap:4px;flex:0 0 auto}
.suggestion-row--action{width:100%;border-top:0;border-left:0;border-right:0;background:transparent;text-align:left;cursor:pointer}
.suggestion-row--action:hover{background:#f8fbff}
.suggestion-link{flex:0 0 auto;color:#245bdb;font-size:12px;font-weight:700}
.distribution-row:last-child,.suggestion-row:last-child{border-bottom:0}
.resource-waterline-cell{min-width:0;display:flex;flex-direction:column;gap:4px;padding:2px 0}
.resource-waterline-row{display:grid;grid-template-columns:30px minmax(44px,88px) 34px;align-items:center;gap:6px;min-width:0}
.resource-waterline-row span{font-size:11px;font-weight:700;color:#64748b;white-space:nowrap}
.resource-waterline-row i{height:4px;border-radius:999px;background:#edf2f7;overflow:hidden;display:block}
.resource-waterline-row b{height:100%;border-radius:999px;background:#94a3b8;display:block;transition:width .16s ease}
.resource-waterline-row strong{font-size:11px;color:#334155;text-align:right;white-space:nowrap}
.resource-waterline-row.is-success b{background:#22c55e}
.resource-waterline-row.is-notice b{background:#3b82f6}
.resource-waterline-row.is-warning b{background:#f59e0b}
.resource-waterline-row.is-danger b{background:#ef4444}
.resource-waterline-row.is-empty span,.resource-waterline-row.is-empty strong{color:#94a3b8}
.resource-waterline-tooltip{min-width:176px;display:flex;flex-direction:column;gap:7px;padding:2px 0}
.resource-waterline-tooltip div{display:flex;align-items:center;justify-content:space-between;gap:18px;line-height:1.35}
.resource-waterline-tooltip span{color:rgba(255,255,255,.72);font-size:11px;font-weight:500}
.resource-waterline-tooltip strong{color:#fff;font-size:11px;font-weight:700;white-space:nowrap}
.audit-diff-cell{display:flex;align-items:center;gap:6px;min-width:0}
.audit-diff-cell span{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#475569;font-size:12px}
.audit-diff-cell--compact span{max-width:220px}
.audit-detail-shell{display:flex;flex-direction:column;gap:10px}
.audit-raw-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}
.audit-raw-grid pre,.detail-section>pre{max-height:220px;overflow:auto;margin:0;padding:10px;border-radius:10px;background:#0f172a;color:#e2e8f0;font-size:12px;line-height:1.6;white-space:pre-wrap;word-break:break-word}
.search-summary-grid,.repository-summary-grid,.view-summary-grid,.island-summary-grid,.authorization-summary-grid,.threshold-summary-grid,.governance-filter-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px;margin-bottom:10px}
.search-summary-card,.repository-summary-card,.threshold-summary-card{border:1px solid rgba(148,163,184,.18);border-radius:10px;background:#fff;padding:10px 12px;display:flex;align-items:center;justify-content:space-between;color:#475569;font-size:13px}
.search-summary-card strong,.repository-summary-card strong,.threshold-summary-card strong{font-size:20px;color:#0f172a}
.search-summary-card small{margin-left:auto;color:#94a3b8;font-size:11px;white-space:nowrap}
.search-summary-card.success,.repository-summary-card.success,.threshold-summary-card.success{background:#f7fefb}.search-summary-card.warning,.repository-summary-card.warning,.threshold-summary-card.warning{background:#fffaf0}.search-summary-card.danger,.repository-summary-card.danger,.threshold-summary-card.danger{background:#fff7f7}.search-summary-card.info,.repository-summary-card.info,.threshold-summary-card.info{background:#f8fafc}
.search-summary-card--action{appearance:none;font:inherit;cursor:pointer;text-align:left}
.search-summary-card--action.active{border-color:rgba(51,112,255,.34);box-shadow:0 0 0 2px rgba(51,112,255,.08);color:#245bdb}
.search-summary-card--action.active strong{color:#245bdb}
.search-summary-card--action:hover{border-color:rgba(51,112,255,.28)}
.platform-setting-strip{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px;margin:0 0 10px}
.platform-setting-card{min-width:0;display:grid;grid-template-columns:1fr auto;gap:3px 8px;padding:10px 12px;border:1px solid rgba(148,163,184,.18);border-radius:10px;background:#fff}
.platform-setting-card>span{color:#64748b;font-size:12px}.platform-setting-card>strong{color:#0f172a;font-size:18px;line-height:1.1}.platform-setting-card>small{grid-column:1 / -1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#94a3b8;font-size:11px}
.platform-setting-card.success{background:#f7fefb}.platform-setting-card.warning{background:#fffaf0}.platform-setting-card.info{background:#f8fafc}
.threshold-band{display:flex;align-items:center;gap:6px;flex-wrap:wrap}
.threshold-band span{border:1px solid rgba(148,163,184,.18);border-radius:999px;background:#f8fafc;padding:3px 8px;font-size:12px;color:#475569}
.collection-shell{display:flex;flex-direction:column;gap:8px;margin-bottom:10px}
.sync-account-shell{border:1px solid rgba(36,91,219,.09);border-radius:12px;background:#fbfdff;padding:12px;margin-bottom:10px}
.sync-account-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:8px}
.sync-account-card{min-width:0;border:1px solid rgba(148,163,184,.18);border-radius:10px;background:#fff;padding:10px 12px;display:flex;flex-direction:column;gap:7px;text-align:left;cursor:pointer;transition:all .16s ease;box-shadow:0 10px 22px rgba(15,23,42,.035)}
.sync-account-card:hover,.sync-account-card.active{border-color:rgba(36,91,219,.2);box-shadow:0 12px 24px rgba(36,91,219,.06);transform:translateY(-1px)}
.sync-account-card.active{background:#eef4ff}
.sync-account-card--ghost{background:#fbfdff;border-style:dashed}
.sync-account-card--create{background:#f8fbff;border-style:dashed;border-color:rgba(51,112,255,.2)}
.sync-account-card--create .sync-account-card-value{color:#245bdb}
.sync-account-card-head{display:flex;align-items:center;justify-content:space-between;gap:8px;min-width:0}
.sync-account-card-head strong{font-size:13px;color:#0f172a;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.sync-account-card-value{font-size:16px;font-weight:800;line-height:1.25;color:#0f172a}
.sync-account-card>span:nth-child(3){font-size:12px;color:#475569;line-height:1.4}
.sync-account-card>small{font-size:12px;color:#64748b;line-height:1.4;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.collection-source-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:8px}
.collection-source-card{border:1px solid rgba(148,163,184,.18);border-radius:10px;background:#fff;padding:10px 12px;box-shadow:0 10px 22px rgba(15,23,42,.035);min-width:0}
.collection-source-head{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:8px}
.collection-source-head strong{font-size:13px;color:#0f172a}
.collection-source-meta{display:flex;align-items:center;gap:8px;flex-wrap:wrap;color:#475569;font-size:12px;margin-bottom:6px}
.collection-error-preview{margin-top:7px;padding:6px 8px;border-radius:8px;background:#fff7ed;border:1px solid rgba(251,146,60,.18);font-size:12px;color:#9a3412;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.collection-panel{margin-bottom:10px}
.sync-joint-panel{border:1px solid rgba(51,112,255,.12);border-radius:12px;background:#f8fbff;padding:12px;margin-bottom:10px}
.sync-joint-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}
.sync-joint-card{min-width:0;border:1px solid rgba(148,163,184,.16);border-radius:12px;background:#fff;padding:10px 12px;display:flex;flex-direction:column;gap:7px;text-align:left;cursor:pointer;transition:all .16s ease}
.sync-joint-card:hover,.sync-joint-card.active{border-color:rgba(36,91,219,.2);box-shadow:0 12px 24px rgba(36,91,219,.06);transform:translateY(-1px)}
.sync-joint-card.active{background:#eef4ff}
.sync-joint-card-head{display:flex;align-items:center;justify-content:space-between;gap:8px;min-width:0}
.sync-joint-card-head strong{font-size:13px;color:#0f172a;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.sync-joint-card-value{font-size:21px;font-weight:800;line-height:1;color:#0f172a}
.sync-joint-card>span:last-child{min-height:34px;color:#64748b;font-size:12px;line-height:1.45;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.views-shell{display:flex;flex-direction:column;gap:10px}
.view-mode-bar{display:inline-flex;align-items:center;gap:6px;padding:3px;border:1px solid rgba(148,163,184,.16);border-radius:12px;background:#fff;box-shadow:0 12px 26px rgba(15,23,42,.04);width:max-content;max-width:100%;overflow:auto}
.view-mode-bar button{min-height:32px;padding:0 14px;border:0;border-radius:8px;background:transparent;color:#475569;font-size:13px;font-weight:700;white-space:nowrap;cursor:pointer}
.view-mode-bar button.active{background:#e8f0ff;color:#245bdb;box-shadow:inset 0 0 0 1px rgba(51,112,255,.12)}
.views-mode-switcher{width:100%;justify-content:flex-start;gap:6px;box-shadow:none}
.views-mode-switcher button{display:inline-flex;align-items:center;gap:6px;min-width:132px}.views-mode-switcher button em{font-style:normal;color:#94a3b8;font-size:11px}.views-mode-switcher button.active em{color:#245bdb}
.cmdb-content-card--opsany .views-shell{gap:16px}
.cmdb-content-card--opsany .repository-summary-grid{display:none}
.cmdb-content-card--opsany .view-mode-bar{display:flex;width:100%;padding:3px;gap:8px;border:1px solid rgba(148,163,184,.16);border-radius:12px;background:#fff;box-shadow:0 12px 26px rgba(15,23,42,.04)}
.cmdb-content-card--opsany .view-mode-bar button{min-height:38px;padding:0 18px;border-radius:8px;color:#475569;font-weight:700;position:relative}
.cmdb-content-card--opsany .view-mode-bar button.active{background:#e8f0ff;color:#245bdb;box-shadow:inset 0 0 0 1px rgba(51,112,255,.1)}
.cmdb-content-card--opsany .view-mode-bar button.active::after{display:none}
.opsany-view-layout{display:grid;grid-template-columns:236px minmax(0,1fr);gap:14px;align-items:start}
.opsany-view-tree{border-right:4px solid #e5e7eb;min-height:360px;padding-right:12px}
.opsany-tree-search{margin-bottom:12px}
.opsany-view-tree-list{display:flex;flex-direction:column;gap:4px}
.opsany-view-tree-node{width:100%;min-height:30px;border:0;border-radius:2px;background:transparent;padding:0 8px;display:flex;align-items:center;justify-content:space-between;gap:8px;color:#374151;font-size:13px;text-align:left;cursor:pointer}
.opsany-view-tree-node:hover,.opsany-view-tree-node.active{background:#eaf8f0;color:#16a34a}
.opsany-view-tree-node>span{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.opsany-view-tree-node strong{min-width:28px;height:20px;padding:0 6px;border-radius:2px;background:#e8fff4;color:#16a34a;font-size:12px;font-weight:500;display:inline-flex;align-items:center;justify-content:center}
.ledger-host-layout{display:grid;grid-template-columns:236px minmax(0,1fr);gap:14px;align-items:start}
.ledger-resource-tree-panel{min-height:520px}
.ledger-resource-tree-panel .ledger-perspective-tabs{width:100%;margin-bottom:12px;padding:3px;gap:6px;border-radius:12px;box-shadow:none}
.ledger-resource-tree-panel .ledger-perspective-tabs .neo-tab-btn{flex:1;min-height:34px;padding:0 8px;border-radius:8px;font-size:12px;justify-content:center}
.ledger-resource-tree-panel .ledger-perspective-tabs .neo-tab-btn .el-icon{font-size:14px}
.ledger-tree-panel-head{display:flex;align-items:flex-start;justify-content:space-between;gap:8px;margin-bottom:12px}
.ledger-tree-panel-head div:first-child{min-width:0;display:flex;flex-direction:column;gap:3px}
.ledger-tree-panel-head strong{font-size:14px;color:#1f2937;line-height:1.3}
.ledger-tree-panel-head span{font-size:12px;color:#6b7280;line-height:1.45}
.ledger-tree-actions{display:flex;gap:6px;flex:none}
.ledger-tree-actions button{width:28px;height:28px;border:1px solid rgba(148,163,184,.22);border-radius:8px;background:#fff;color:#475569;display:inline-flex;align-items:center;justify-content:center;cursor:pointer}
.ledger-tree-actions button:hover{border-color:rgba(51,112,255,.28);background:#f7faff;color:#245bdb}
.ledger-tree-node-label{display:inline-flex;align-items:center;gap:5px;min-width:0}
.ledger-tree-node-label span{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.opsany-view-tree-node>.ledger-tree-node-right{overflow:visible;white-space:nowrap}
.ledger-tree-node-right{display:inline-flex;align-items:center;justify-content:flex-end;gap:4px;flex:none;min-width:34px;margin-left:auto;padding-left:8px}
.ledger-tree-node-count{margin-left:auto}
.ledger-tree-node-actions{position:absolute;right:40px;top:50%;transform:translateY(-50%);display:inline-flex;align-items:center;gap:2px;padding:1px 2px;border:1px solid rgba(148,163,184,.16);border-radius:8px;background:rgba(255,255,255,.96);box-shadow:0 8px 18px rgba(15,23,42,.08);opacity:0;pointer-events:none;transition:opacity .16s ease}
.ledger-tree-node-actions span[role=button]{width:20px;height:20px;border-radius:6px;color:#64748b;display:inline-flex;align-items:center;justify-content:center;cursor:pointer}
.ledger-tree-node-actions span[role=button]:hover{background:rgba(51,112,255,.1);color:#245bdb}
.ledger-resource-tree-node:hover .ledger-tree-node-actions,.ledger-resource-tree-node.active .ledger-tree-node-actions{opacity:1;pointer-events:auto}
.ledger-tree-node-icon{font-size:14px;color:#64748b;flex:none}
.ledger-tree-toggle{width:16px;height:16px;border-radius:4px;display:inline-flex;align-items:center;justify-content:center;color:#94a3b8;flex:none}
.ledger-tree-toggle:hover{background:rgba(51,112,255,.08);color:#245bdb}
.ledger-tree-toggle .el-icon{font-size:12px}
.ledger-tree-toggle--leaf{visibility:hidden}
.ledger-resource-tree-node:hover,.ledger-resource-tree-node.active{background:#e8f0ff;color:#245bdb}
.ledger-resource-tree-node:hover .ledger-tree-node-icon,.ledger-resource-tree-node.active .ledger-tree-node-icon{color:#245bdb}
.ledger-resource-tree-node strong{background:#eef4ff;color:#245bdb}
.ledger-resource-tree-node{position:relative;padding-left:calc(8px + (var(--ledger-node-depth,0) * 16px))}
.ledger-resource-tree-node.is-level-vm strong{min-width:22px}
.ledger-pagination{display:flex;justify-content:flex-end;padding:12px 2px 0;border-top:1px solid rgba(148,163,184,.12);margin-top:10px}
.ledger-table-panel{min-width:0}
.ledger-table-head{margin-bottom:10px}
.opsany-view-main{min-width:0}
.opsany-app-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(360px,1fr));gap:18px}
.opsany-app-card{min-width:0;border:1px solid rgba(148,163,184,.16);border-radius:14px;background:#fff;box-shadow:0 8px 22px rgba(15,23,42,.055);padding:14px;transition:border-color .18s ease,box-shadow .18s ease,transform .18s ease}
.opsany-app-card:hover{border-color:rgba(51,112,255,.24);box-shadow:0 12px 28px rgba(36,91,219,.1);transform:translateY(-1px)}
.opsany-app-card-head{display:flex;align-items:flex-start;justify-content:space-between;gap:14px;margin-bottom:14px}
.opsany-app-card-head .resource-cell strong{font-size:15px;color:#1f2937}
.opsany-app-meta-strip{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:6px;margin:-2px 0 10px;padding:8px 9px;border:1px solid rgba(148,163,184,.14);border-radius:9px;background:#f8fafc}
.opsany-app-meta-strip>span{display:flex;flex-direction:column;gap:2px;min-width:0}
.opsany-app-meta-strip em{font-size:11px;color:#94a3b8;font-style:normal}
.opsany-app-meta-strip strong{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:12px;color:#334155}
.opsany-app-meta-strip .el-tag{align-self:flex-start}
.opsany-app-techline{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin:0 0 10px;color:#64748b;font-size:11px;line-height:1.5}
.opsany-app-techline a{color:#245bdb;text-decoration:none;font-weight:600}
.opsany-app-techline a:hover{text-decoration:underline}
.opsany-app-description{flex-basis:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#94a3b8}
.opsany-app-health{margin:0 0 13px;padding:10px 11px;border-radius:8px;background:#f8fafc;border:1px solid rgba(148,163,184,.14)}
.opsany-app-health-head,.opsany-app-health-meta{display:flex;align-items:center;justify-content:space-between;gap:8px}
.opsany-app-health-head{margin-bottom:6px;color:#64748b;font-size:12px}
.opsany-app-health-head strong{color:#0f172a;font-size:14px}
.opsany-app-health-meta{margin-top:6px;color:#94a3b8;font-size:11px}
.opsany-app-health-meta span:first-child{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#64748b}
.opsany-host-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:12px}
.opsany-host-card{min-width:0;border:1px solid rgba(148,163,184,.18);border-radius:10px;background:#fff;padding:14px;box-shadow:0 8px 20px rgba(15,23,42,.035)}
.opsany-host-card-head{display:flex;align-items:flex-start;justify-content:space-between;gap:10px;margin-bottom:12px}.opsany-host-card-head .resource-cell strong{font-size:14px;color:#0f172a}
.opsany-host-meta-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}.opsany-host-meta-grid>div{min-width:0;padding:8px 9px;border-radius:8px;background:#f8fafc}.opsany-host-meta-grid span{display:block;color:#94a3b8;font-size:11px;margin-bottom:3px}.opsany-host-meta-grid strong{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#334155;font-size:12px}
.opsany-host-card-footer{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-top:11px;padding-top:9px;border-top:1px solid rgba(148,163,184,.14);color:#94a3b8;font-size:11px}.opsany-host-card-footer .el-button{margin-left:0}
.opsany-relation-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}
.opsany-relation-cell{min-height:42px;border:1px solid #edf1f4;border-radius:3px;background:#fbfcfd;padding:8px 10px;display:flex;align-items:center;justify-content:space-between;gap:8px;color:#374151;cursor:pointer;text-align:left}
.opsany-relation-cell:hover{border-color:#b7ebd0;background:#f6fffb}
.opsany-relation-cell span{font-size:12px;color:#4b5563}
.opsany-relation-cell strong{min-width:24px;text-align:center;border-radius:2px;background:#e8fff4;color:#16a34a;font-size:13px;font-weight:600}
.opsany-physical-stats{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:16px;margin-bottom:16px}
.opsany-physical-stat{min-height:88px;border:1px solid #e5e7eb;border-radius:2px;background:#fff;padding:16px 22px;display:flex;align-items:center;gap:18px;box-shadow:none}
.opsany-stat-icon{width:50px;height:50px;border-radius:999px;display:inline-flex;align-items:center;justify-content:center;font-size:26px;color:#16a34a;background:#eaf8f0;box-shadow:0 0 0 6px rgba(22,163,74,.08);flex:none}
.opsany-physical-stat:nth-child(n+3) .opsany-stat-icon{color:#409eff;background:#ecf5ff;box-shadow:0 0 0 6px rgba(64,158,255,.1)}
.opsany-physical-stat div{min-width:0;display:flex;flex-direction:column;gap:6px}
.opsany-physical-stat span:not(.opsany-stat-icon){font-size:18px;line-height:1.25;color:#374151;font-weight:400}
.opsany-physical-stat strong{font-size:20px;line-height:1.1;color:#111827;font-weight:600}
.opsany-rack-stage{display:grid;grid-template-columns:repeat(auto-fill,minmax(430px,1fr));gap:22px;align-items:start}
.opsany-rack-card{min-width:0;display:grid;grid-template-columns:212px minmax(0,1fr);gap:18px;align-items:start;background:transparent}
.opsany-rack-visual{width:212px;position:relative}
.opsany-rack-title{position:absolute;top:-8px;left:50%;z-index:2;transform:translateX(-50%);max-width:150px;height:20px;padding:0 10px;border-radius:8px;background:#111827;color:#fff;font-size:11px;font-weight:700;line-height:20px;text-align:center;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;box-shadow:0 4px 10px rgba(0,0,0,.24)}
.opsany-rack-shell{height:604px;border:12px solid #3e4150;border-top-width:14px;border-bottom-width:8px;border-radius:2px;background:#07080d;padding:2px 7px 2px 16px;display:grid;grid-template-rows:repeat(42,1fr);gap:1px;box-shadow:inset 0 0 0 1px rgba(255,255,255,.04),8px 8px 20px rgba(15,23,42,.18)}
.opsany-rack-slot{position:relative;min-height:0;border-radius:1px;background:linear-gradient(180deg,rgba(255,255,255,.035),rgba(255,255,255,.012));display:flex;align-items:center}
.opsany-rack-slot span{position:absolute;left:-22px;width:18px;color:#e5e7eb;font-size:9px;line-height:1;text-align:center;opacity:.9}
.opsany-rack-slot strong{width:100%;height:100%;border-radius:2px;background:linear-gradient(180deg,#1f2937 0%,#111827 100%);border:1px solid rgba(148,163,184,.28);color:#d1d5db;font-size:10px;font-weight:500;display:flex;align-items:center;padding:0 8px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.opsany-rack-slot.occupied{background:linear-gradient(90deg,rgba(22,163,74,.34),rgba(22,163,74,.08))}
.opsany-rack-host-list{position:absolute;left:22px;right:10px;bottom:14px;display:flex;flex-direction:column;gap:6px}
.opsany-rack-host-list button{min-width:0;height:28px;border:1px solid rgba(148,163,184,.2);border-radius:3px;background:#232631;color:#d1d5db;padding:0 8px;display:flex;align-items:center;justify-content:space-between;gap:8px;font-size:11px;text-align:left;cursor:pointer}
.opsany-rack-host-list button:hover{border-color:rgba(22,163,74,.7);color:#fff}
.opsany-rack-host-list span,.opsany-rack-host-list small{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.opsany-rack-host-list small{color:#9ca3af;font-size:10px}
.opsany-rack-meta{min-width:0;border:1px solid #eef0f2;border-radius:4px;background:#fff;padding:14px;display:flex;flex-direction:column;gap:8px;color:#6b7280;font-size:12px;box-shadow:0 4px 14px rgba(15,23,42,.04)}
.opsany-rack-meta strong{font-size:15px;color:#1f2937}
.opsany-rack-meta span{line-height:1.45}
.view-metric-line,.view-host-chips{display:flex;align-items:center;gap:6px;flex-wrap:wrap}
.view-metric-line span{font-size:12px;color:#475569;background:#f8fafc;border:1px solid rgba(148,163,184,.14);border-radius:8px;padding:3px 7px}
.tag-summary-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px;margin-bottom:10px}
.tag-summary-card{border:1px solid rgba(148,163,184,.18);border-radius:10px;background:#fff;padding:10px 12px;display:flex;align-items:center;justify-content:space-between;color:#475569;font-size:13px}
.tag-summary-card strong{font-size:20px;color:#0f172a}
.tag-summary-card.success{background:#f7fefb}.tag-summary-card.warning{background:#fffaf0}.tag-summary-card.info{background:#f8fafc}
.audit-summary-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px;margin-bottom:10px}
.audit-summary-card{border:1px solid rgba(148,163,184,.18);border-radius:10px;background:#fff;padding:10px 12px;display:flex;align-items:center;justify-content:space-between;color:#475569;font-size:13px}
.audit-summary-card strong{font-size:20px;color:#0f172a}
.audit-summary-card.success{background:#f7fefb}.audit-summary-card.warning{background:#fffaf0}.audit-summary-card.info{background:#f8fafc}.audit-summary-card.danger{background:#fff7f7}
.search-match-list{display:flex;align-items:center;gap:5px;flex-wrap:wrap}
.search-attribute-list{display:flex;flex-direction:column;gap:3px;min-width:0;font-size:12px;color:#475569}
.search-attribute-list span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.tag-chip-list,.detail-tag-list,.tag-category-row{display:flex;align-items:center;gap:6px;flex-wrap:wrap}
.detail-tag-list{margin-top:8px}
.tag-category-row{min-height:38px;margin-bottom:10px;padding:8px;border:1px solid rgba(148,163,184,.16);border-radius:10px;background:#f8fafc}
.tag-chip{display:inline-flex;align-items:center;gap:4px;max-width:140px;border:1px solid #dbe4f0;border-radius:999px;background:#fff;padding:3px 8px;font-size:12px;font-weight:700;line-height:1.35;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.tag-chip strong{color:#0f172a}
.tag-chip--hot{max-width:180px}
.tag-shell{display:flex;flex-direction:column;gap:0}
.tag-name-cell{display:flex;align-items:center;gap:8px;min-width:0}
.tag-color-dot{width:10px;height:10px;border-radius:50%;box-shadow:0 0 0 3px rgba(36,91,219,.08);flex:none}
.repository-shell{display:flex;flex-direction:column;gap:10px}
.repository-layout{display:grid;grid-template-columns:minmax(260px,.55fr) minmax(0,1.05fr) minmax(280px,.7fr);gap:10px}
.cmdb-content-card--opsany .repository-shell{gap:18px}
.cmdb-content-card--opsany .repository-layout{grid-template-columns:1fr;gap:0}
.cmdb-content-card--opsany .repository-tree-panel{display:none}
.cmdb-content-card--opsany .repository-layout>.mini-panel:last-child{display:none}
.cmdb-content-card--opsany .repository-layout .mini-panel{border-radius:2px;background:#fff;border-color:#eef0f2;box-shadow:none}
.cmdb-content-card--opsany .repository-layout .mini-panel--wide{border:0;background:transparent;padding:0;box-shadow:none}
.cmdb-content-card--opsany .repository-layout .mini-panel--wide>.mini-panel-head{display:none}
.cmdb-content-card--opsany .repository-tree-group{border:0;border-radius:0;background:transparent;padding:0}
.cmdb-content-card--opsany .repository-tree-group-head{min-height:30px;color:#374151}
.cmdb-content-card--opsany .repository-tree-group-head strong{min-width:24px;height:20px;display:inline-flex;align-items:center;justify-content:center;border-radius:2px;background:#e8fff4;color:#16a34a}
.cmdb-content-card--opsany .repository-tree-model{border-radius:2px;background:transparent}
.cmdb-content-card--opsany .repository-tree-model:hover,.cmdb-content-card--opsany .repository-tree-model.active{background:#eaf8f0;color:#16a34a}
.cmdb-content-card--opsany .repository-group-list{gap:22px}
.cmdb-content-card--opsany .repository-group-card{border:0;border-radius:0;background:#fafafa;padding:16px;box-shadow:none;gap:14px}
.cmdb-content-card--opsany .repository-group-head{min-height:26px;justify-content:flex-start}
.cmdb-content-card--opsany .repository-group-head .resource-cell{flex-direction:row;align-items:center;gap:8px}
.cmdb-content-card--opsany .repository-group-head .resource-cell strong{font-size:14px;color:#111827}
.cmdb-content-card--opsany .repository-group-head .resource-cell span{border-radius:999px;background:#eef2f7;padding:4px 10px;color:#6b7280;font-size:12px}
.cmdb-content-card--opsany .repository-group-badges{display:none}
.cmdb-content-card--opsany .repository-model-list{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:14px}
.cmdb-content-card--opsany .repository-model-row{position:relative;min-height:54px;border:1px solid #eef0f2;border-radius:4px;background:#fff;padding:12px 42px 12px 48px;display:flex;align-items:center;box-shadow:0 2px 8px rgba(15,23,42,.03)}
.cmdb-content-card--opsany .repository-model-row::before{content:"";position:absolute;left:16px;top:50%;width:24px;height:24px;border-radius:999px;transform:translateY(-50%);border:1px solid #d1d5db;background:linear-gradient(180deg,#fff 0%,#f8fafc 100%)}
.cmdb-content-card--opsany .repository-model-row:hover{border-color:#b7ebd0;background:#fff}
.cmdb-content-card--opsany .repository-model-row .resource-cell{min-width:0;gap:3px}
.cmdb-content-card--opsany .repository-model-row .resource-cell strong{font-size:13px;color:#1f2937}
.cmdb-content-card--opsany .repository-model-row .resource-cell span{font-size:11px;color:#6b7280;text-transform:uppercase}
.cmdb-content-card--opsany .repository-model-metrics{margin-left:auto}
.cmdb-content-card--opsany .repository-model-metrics>span:not(:first-child),.cmdb-content-card--opsany .repository-quality-chip,.cmdb-content-card--opsany .repository-model-actions{display:none}
.cmdb-content-card--opsany .repository-model-count-label{display:none}
.cmdb-content-card--opsany .repository-model-metrics>.repository-model-count{position:absolute;right:16px;top:50%;min-width:24px;height:22px;transform:translateY(-50%);border:1px solid #99f6e4;border-radius:2px;background:#f0fdfa;color:#14b8a6;font-size:12px;font-weight:600;display:inline-flex;align-items:center;justify-content:center;padding:0 6px}
.repository-tree-panel{min-width:0}
.repository-tree-list{display:flex;flex-direction:column;gap:8px;max-height:520px;overflow:auto;padding-right:2px}
.repository-tree-group{border:1px solid rgba(148,163,184,.16);border-radius:12px;background:#fff;padding:8px;display:flex;flex-direction:column;gap:6px}
.repository-tree-group-head{display:flex;align-items:center;justify-content:space-between;gap:8px;min-height:28px;padding:0 4px;color:#0f172a;font-size:13px;font-weight:800}
.repository-tree-group-head strong{font-size:12px;color:#245bdb}
.repository-tree-model{width:100%;border:0;border-radius:9px;background:#f8fafc;padding:8px 9px;display:flex;align-items:center;justify-content:space-between;gap:8px;text-align:left;cursor:pointer;color:#334155;transition:all .16s ease}
.repository-tree-model:hover,.repository-tree-model.active{background:#eef4ff;color:#245bdb}
.repository-tree-model-main{display:flex;flex-direction:column;gap:2px;min-width:0}
.repository-tree-model-main strong{font-size:12px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.repository-tree-model-main small{font-size:11px;color:#64748b;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.repository-tree-model-meta{display:inline-flex;align-items:center;gap:5px;flex-shrink:0}
.repository-tree-model-meta b,.repository-tree-model-meta em{min-width:22px;height:22px;border-radius:999px;display:inline-flex;align-items:center;justify-content:center;font-size:11px;font-style:normal;font-weight:800;background:#fff;color:#245bdb;border:1px solid rgba(36,91,219,.12)}
.repository-tree-model-meta em{color:#64748b}
.repository-tree-model-meta em.danger{color:#dc2626;background:#fff7f7;border-color:rgba(220,38,38,.16)}
.repository-group-list,.repository-top-list{display:flex;flex-direction:column;gap:8px}
.repository-group-card{border:1px solid rgba(148,163,184,.16);border-radius:12px;background:#fff;padding:10px;display:flex;flex-direction:column;gap:8px}
.repository-group-head,.repository-model-row,.repository-top-row{display:flex;align-items:center;justify-content:space-between;gap:10px}
.repository-group-badges{display:flex;align-items:center;gap:6px;flex-wrap:wrap;justify-content:flex-end}
.repository-model-list{display:flex;flex-direction:column;gap:6px}
.repository-model-row{min-height:38px;border-radius:9px;background:#f8fafc;padding:7px 9px}
.repository-model-metrics{display:inline-flex;align-items:center;gap:8px;flex-wrap:wrap;color:#64748b;font-size:12px}
.repository-model-count-label{margin-right:4px}
.repository-model-metrics .danger{color:#dc2626;font-weight:700}
.repository-model-actions{display:inline-flex;align-items:center;gap:6px;flex-shrink:0}
.repository-quality-chip{display:inline-flex;align-items:center;border-radius:999px;padding:2px 8px;background:#eef4ff;color:#245bdb;font-weight:700}
.repository-quality-chip.warning{background:#fffbeb;color:#b45309}
.repository-quality-chip.danger{background:#fff7f7;color:#dc2626}
.repository-quality-chip.success{background:#f7fefb;color:#166534}
.repository-top-row{border-bottom:1px solid rgba(148,163,184,.12);padding:8px 0}
.repository-top-row:last-child{border-bottom:0}
.repository-top-value{display:flex;flex-direction:column;align-items:flex-end;gap:2px;color:#64748b;font-size:12px}
.repository-top-value strong{font-size:18px;color:#0f172a}
.opsany-model-tabs{display:flex;align-items:center;width:100%;gap:8px;padding:3px;border:1px solid rgba(148,163,184,.16);border-radius:12px;background:#fff;box-shadow:0 12px 26px rgba(15,23,42,.04);margin-bottom:10px;overflow:auto}
.opsany-model-tabs button{position:relative;min-height:38px;border:0;border-radius:8px;background:transparent;padding:0 18px;color:#475569;font-size:13px;font-weight:700;line-height:1.2;white-space:nowrap;cursor:pointer}
.opsany-model-tabs button:hover{background:rgba(51,112,255,.06);color:#245bdb}
.opsany-model-tabs button.active{background:#e8f0ff;color:#245bdb;box-shadow:inset 0 0 0 1px rgba(51,112,255,.1)}
.opsany-model-tabs button.active::after{display:none}
.opsany-model-catalog-layout{display:block}
.opsany-model-catalog-layout--with-tree{display:grid;grid-template-columns:236px minmax(0,1fr);gap:14px;align-items:start}
.opsany-model-catalog-main{min-width:0}
.cmdb-model-surface-tabs{margin:0}
.opsany-model-toolbar{display:flex;align-items:center;justify-content:space-between;gap:16px;margin-bottom:10px}
.opsany-model-toolbar-left{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.opsany-model-toolbar-left>span{font-size:13px;font-weight:600;color:#374151}
.opsany-model-section-list{display:flex;flex-direction:column;gap:12px}
.opsany-model-section{background:#f8fafc;padding:10px 12px;border:1px solid rgba(148,163,184,.14);border-radius:10px}
.opsany-model-section-head{min-height:24px;display:flex;align-items:center;gap:10px;margin-bottom:8px}
.opsany-model-section-head strong{font-size:14px;color:#111827;font-weight:700}
.opsany-model-section-actions{display:inline-flex;align-items:center;gap:4px}
.opsany-model-section-actions button{width:22px;height:22px;border:0;border-radius:3px;background:transparent;color:#6b7280;display:inline-flex;align-items:center;justify-content:center;cursor:pointer}
.opsany-model-section-actions button:hover{background:#e8f0ff;color:#245bdb}
.opsany-model-section-actions button:disabled{cursor:not-allowed;color:#cbd5e1;background:transparent}
.opsany-model-card-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(176px,1fr));gap:10px}
.opsany-model-card{min-height:58px;border:1px solid rgba(148,163,184,.16);border-radius:8px;background:#fff;padding:8px 9px;display:grid;grid-template-columns:28px minmax(0,1fr) 26px;align-items:center;gap:7px;text-align:left;color:#374151;box-shadow:0 4px 12px rgba(15,23,42,.025);cursor:pointer}
.opsany-model-card:hover,.opsany-model-card.active{border-color:rgba(36,91,219,.18);background:#f8fbff}
.opsany-model-card-icon{width:28px;height:28px;border:1px solid rgba(36,91,219,.12);border-radius:999px;display:inline-flex;align-items:center;justify-content:center;color:#245bdb;background:#f3f7ff;font-size:15px}
.opsany-model-card-main{min-width:0;display:flex;flex-direction:column;gap:2px}
.opsany-model-card-main strong{font-size:13px;color:#1f2937;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.opsany-model-card-main small{font-size:11px;color:#6b7280;text-transform:uppercase;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.opsany-model-card-actions{width:26px;display:inline-flex;flex-direction:column;align-items:center;justify-content:center;gap:2px}
.opsany-model-card-count{width:26px;height:18px;border:1px solid rgba(36,91,219,.12);border-radius:6px;background:#f8fbff;color:#245bdb;display:inline-flex;align-items:center;justify-content:center;font-size:10px;line-height:1;font-weight:800}
.opsany-model-card-edit{width:20px;height:18px;border:0;border-radius:4px;background:transparent;color:#94a3b8;display:inline-flex;align-items:center;justify-content:center;cursor:pointer}
.opsany-model-card-edit:hover{background:#e8f0ff;color:#245bdb}
.model-config-drawer :deep(.el-drawer__header){margin-bottom:0;padding:16px 18px 12px;border-bottom:1px solid rgba(148,163,184,.14)}
.model-config-drawer :deep(.el-drawer__body){padding:16px 18px;background:#f8fafc}
.model-config-drawer-body{display:flex;flex-direction:column;gap:12px}
.model-config-overview{display:grid;grid-template-columns:42px minmax(0,1fr) auto;align-items:center;gap:12px;border:1px solid rgba(148,163,184,.16);border-radius:12px;background:#fff;padding:12px;box-shadow:0 10px 22px rgba(15,23,42,.035)}
.model-config-overview .opsany-model-card-icon{width:42px;height:42px;font-size:20px}
.model-config-overview-main{min-width:0;display:flex;flex-direction:column;gap:4px}
.model-config-overview-title{display:flex;align-items:center;gap:8px;min-width:0}
.model-config-overview-title strong{font-size:16px;color:#0f172a;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.model-config-overview-main>span{font-size:12px;color:#64748b;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.model-config-overview-main p{margin:0;color:#475569;font-size:13px;line-height:1.55}
.model-config-overview-actions{display:flex;justify-content:flex-end}
.model-config-stat-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px}
.model-config-section{border:1px solid rgba(148,163,184,.16);border-radius:12px;background:#fff;padding:12px;box-shadow:0 10px 22px rgba(15,23,42,.03)}
.model-config-section-head{display:flex;align-items:flex-start;justify-content:space-between;gap:10px;margin-bottom:10px}
.model-config-section-head>div{min-width:0;display:flex;flex-direction:column;gap:3px}
.model-config-section-head strong{font-size:14px;color:#0f172a}
.model-config-section-head span{font-size:12px;color:#64748b;line-height:1.45}
.model-config-table{width:100%}
.model-config-tags{display:flex;align-items:center;gap:5px;flex-wrap:wrap}
.field-setting-panel{display:flex;flex-direction:column;gap:7px;width:100%;padding:9px 10px;border:1px solid rgba(148,163,184,.16);border-radius:10px;background:#f8fafc}
.field-setting-panel small{color:#64748b;font-size:12px;line-height:1.45}
.ledger-attribute-column-title{display:inline-flex;align-items:center;gap:4px}.ledger-attribute-column-title .el-icon{color:#94a3b8;font-size:14px;cursor:help}
.field-options-editor{display:flex;flex-direction:column;gap:8px;width:100%}
.field-option-row{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:center;gap:8px}
.field-options-actions{display:flex;align-items:center;gap:10px;color:#64748b;font-size:12px}
.model-dialog-tip{margin-bottom:12px}
.model-detail-page-head{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:4px 0 0}
.model-detail-page-head>div{min-width:0;display:flex;flex-direction:column;gap:4px}
.model-detail-page-head strong{font-size:18px;color:#111827;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.model-detail-page-head span{font-size:12px;color:#6b7280;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.model-detail-layout{display:grid;grid-template-columns:300px minmax(0,1fr);gap:18px;margin-top:18px;align-items:start}
.model-detail-layout--resources-only{grid-template-columns:minmax(0,1fr);margin-top:10px}
.model-detail-summary{display:flex;flex-direction:column;gap:12px;border-radius:2px;background:#fff;border-color:#eef0f2;box-shadow:none}
.model-detail-heading{display:grid;grid-template-columns:34px minmax(0,1fr);gap:10px;align-items:center}
.model-detail-heading>div{min-width:0;display:flex;flex-direction:column;gap:4px}
.model-detail-heading strong{font-size:15px;color:#111827;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.model-detail-heading span{font-size:12px;color:#6b7280;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.model-detail-stat-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px}
.model-detail-stat{min-width:0;border:1px solid #eef0f2;border-radius:4px;background:#fafafa;padding:8px;display:flex;flex-direction:column;gap:4px}
.model-detail-stat span{font-size:12px;color:#6b7280}
.model-detail-stat strong{font-size:18px;line-height:1;color:#111827}
.model-detail-note{border:1px dashed #e5e7eb;border-radius:4px;background:#fafafa;padding:8px 10px;color:#6b7280;font-size:12px;line-height:1.6}
.model-detail-list{display:flex;flex-direction:column;gap:7px}
.model-detail-list-head{display:flex;align-items:center;justify-content:space-between;gap:8px}
.model-detail-list-head strong{font-size:13px;color:#111827}
.model-detail-field-row{display:flex;align-items:center;justify-content:space-between;gap:8px;min-width:0;padding:7px 0;border-bottom:1px dashed #eef0f2}
.model-detail-field-row:last-child{border-bottom:0}
.model-detail-field-row span{min-width:0;color:#374151;font-size:12px;font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.model-detail-field-row small{flex:none;color:#9ca3af;font-size:11px;white-space:nowrap}
.model-detail-resources{min-width:0;border-radius:2px;background:#fff;border-color:#eef0f2;box-shadow:none}
.model-resource-table{margin-top:8px}
.cmdb-content-card--opsany .model-grid .mini-panel{border-radius:2px;background:#fff;border-color:#eef0f2;box-shadow:none}
.cmdb-content-card--opsany :deep(.cmdb-table th.el-table__cell){background:#eaf8f0;color:#1f2937;font-weight:500}
.cmdb-content-card--opsany :deep(.cmdb-table td.el-table__cell){border-bottom-color:#eef0f2}
.cmdb-content-card--opsany :deep(.cmdb-table .el-table__row:hover>td.el-table__cell){background:#f6fffb}
.cmdb-content-card--opsany :deep(.opsany-host-table .el-table__cell){padding:10px 0}
.opsany-host-name strong{color:#16a34a;font-weight:500}
.opsany-host-name span{color:#6b7280;font-size:12px}
.opsany-remote-link{display:inline-flex;align-items:center;gap:4px;color:#16a34a}
.opsany-remote-link :deep(.el-icon){font-size:14px}
.opsany-remote-link:hover{color:#15803d}
.cmdb-content-card--opsany :deep(.el-button--primary){--el-button-bg-color:#245bdb;--el-button-border-color:#245bdb;--el-button-hover-bg-color:#1d4ed8;--el-button-hover-border-color:#1d4ed8}
.cmdb-content-card--opsany :deep(.el-button--primary.is-link){--el-button-text-color:#245bdb;--el-button-hover-link-text-color:#1d4ed8}
.overview-governance-panel,.overview-cost-panel{grid-column:span 1;background:#fff}
.overview-governance-panel-head{align-items:center;margin-bottom:10px;padding-bottom:9px;border-bottom:1px solid rgba(148,163,184,.14)}
.overview-panel-counter{margin-left:auto;color:#94a3b8;font-size:11px;white-space:nowrap}
.overview-governance-panel-head .el-button{padding:0;font-size:11px}
.overview-governance-section{min-width:0}
.overview-governance-section--suggestions{padding-top:12px;border-top:1px solid rgba(148,163,184,.14)}
.overview-governance-section-head{min-height:24px;margin-bottom:8px;display:flex;align-items:center;justify-content:space-between;gap:8px}
.overview-governance-section-head strong{color:#334155;font-size:12px;font-weight:800}
.overview-governance-section-head span{color:#94a3b8;font-size:11px;white-space:nowrap}
.overview-cost-panel-head{align-items:center;margin-bottom:10px;padding-bottom:9px;border-bottom:1px solid rgba(148,163,184,.14)}
.overview-cost-panel-head .el-button{margin-left:auto;padding:0;font-size:11px}
.overview-cost-summary{display:flex;flex-direction:column;gap:10px;min-height:184px}
.overview-cost-total{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:end;gap:3px 10px;padding:12px;border:1px solid rgba(36,91,219,.14);border-radius:10px;background:#f7faff}
.overview-cost-total span{color:#64748b;font-size:12px;font-weight:700}
.overview-cost-total strong{color:#245bdb;font-size:24px;line-height:1;font-weight:800}
.overview-cost-total small{grid-column:1 / -1;color:#94a3b8;font-size:11px}
.overview-cost-categories{padding:10px 12px;border:1px solid rgba(148,163,184,.14);border-radius:10px;background:#fff}
.overview-cost-categories-head{display:flex;align-items:center;justify-content:space-between;gap:8px;color:#64748b;font-size:12px}
.overview-cost-categories-head strong{color:#0f172a;font-size:13px}
.overview-cost-category-list{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:6px;margin-top:8px}
.overview-cost-category-row{display:flex;align-items:center;justify-content:space-between;gap:6px;min-width:0;padding:6px 7px;border-radius:7px;background:#f8fafc;color:#64748b;font-size:11px}
.overview-cost-category-row span{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.overview-cost-category-row strong{flex:none;color:#334155;font-size:11px}
.overview-cost-empty{display:block;margin-top:8px;color:#94a3b8;font-size:11px}
.risk-list{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;margin-bottom:0}
.risk-row{--risk-accent:#d97706;--risk-soft:#fff7e8;min-width:0;min-height:66px;border:1px solid rgba(148,163,184,.16);border-radius:9px;background:#fff;padding:8px 9px;display:flex;flex-direction:column;justify-content:space-between;gap:4px;color:#64748b;transition:border-color .16s ease,box-shadow .16s ease,transform .16s ease}
.risk-row.danger{--risk-accent:#dc2626;--risk-soft:#fff1f2}.risk-row.success{--risk-accent:#059669;--risk-soft:#ecfdf5}
.risk-row--action{appearance:none;width:100%;font:inherit;cursor:pointer;text-align:left}
.risk-row--action:hover{border-color:color-mix(in srgb,var(--risk-accent) 28%,#cbd5e1);box-shadow:0 10px 20px rgba(15,23,42,.06);transform:translateY(-1px)}
.risk-row-head{min-width:0;display:grid;grid-template-columns:24px minmax(0,1fr) auto;align-items:center;gap:6px}
.risk-row-icon{width:24px;height:24px;border-radius:7px;background:var(--risk-soft);color:var(--risk-accent);display:inline-flex;align-items:center;justify-content:center;font-size:13px}
.risk-row-label{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#334155;font-size:12px;font-weight:700}
.risk-row-head>strong{color:#0f172a;font-size:20px;line-height:1;font-weight:800}
.risk-row-footer{min-width:0;display:flex;align-items:center;justify-content:space-between;gap:6px;color:#94a3b8;font-size:10px}
.risk-row-footer>span:last-child{display:inline-flex;align-items:center;gap:2px;color:#245bdb;font-weight:700;white-space:nowrap}
.risk-row-status{display:inline-flex;align-items:center;gap:5px;min-width:0;white-space:nowrap}
.risk-row-status::before{content:'';width:5px;height:5px;flex:none;border-radius:50%;background:var(--risk-accent)}
.suggestion-list--compact{max-height:174px;overflow:auto}
.quality-score-card{display:flex;align-items:center;justify-content:space-between;gap:8px;border:1px solid rgba(148,163,184,.14);border-radius:10px;background:#fff;padding:10px;margin-bottom:8px;font-size:12px;color:#64748b}
.quality-score-card strong{font-size:22px;color:#0f172a}
.quality-score-card.warning{background:#fffbeb}.quality-score-card.danger{background:#fff7f7}.quality-score-card.success{background:#f7fefb}
.quality-status-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin-bottom:8px}
.quality-status-grid>div,.quality-issue-row{border:1px solid rgba(148,163,184,.14);border-radius:10px;background:#fff;padding:8px 10px;display:flex;align-items:center;justify-content:space-between;font-size:12px;color:#64748b}
.quality-status-grid strong,.quality-issue-row strong{font-size:16px;color:#0f172a}
.quality-issue-row--action{appearance:none;width:100%;font:inherit;cursor:pointer;text-align:left}
.quality-issue-row--action:hover{border-color:rgba(51,112,255,.28);box-shadow:0 10px 20px rgba(36,91,219,.05)}
.quality-issue-list{display:flex;flex-direction:column;gap:6px}
.model-quality-list{display:flex;flex-direction:column;gap:6px}
.model-quality-row{display:flex;align-items:center;justify-content:space-between;gap:10px;border:1px solid rgba(148,163,184,.14);border-radius:10px;background:#fff;padding:8px 10px;min-width:0}
.model-quality-main{display:flex;flex-direction:column;gap:2px;min-width:0}
.model-quality-main strong{font-size:12px;color:#0f172a;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.model-quality-main span{font-size:12px;color:#64748b;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.model-quality-meta{display:flex;align-items:center;gap:8px;min-width:0;color:#64748b;font-size:12px;flex-wrap:wrap;justify-content:flex-end}
.model-quality-meta span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.waterline-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}
.waterline-item{border-radius:10px;padding:10px;border:1px solid rgba(148,163,184,.14);background:#fff;display:flex;align-items:center;justify-content:space-between}
.waterline-item.warning{background:#fffbeb}.waterline-item.critical{background:#fff7ed}.waterline-item.exceeded{background:#fef2f2}
.relation-chain{display:grid;grid-template-columns:minmax(0,1fr) auto minmax(0,1fr);align-items:center;gap:8px;min-width:0}
.relation-chain span{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.relation-chain strong{border-radius:999px;background:#eef4ff;color:#245bdb;padding:3px 8px;font-size:12px;white-space:nowrap}
.topology-knowledge-shell{display:flex;flex-direction:column;gap:10px}
.topology-filter-bar{margin:0}
.topology-summary-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px}
.topology-summary-card{min-width:0;border:1px solid rgba(148,163,184,.18);border-radius:10px;background:#fff;padding:10px 12px;display:flex;align-items:center;justify-content:space-between;color:#475569;font-size:13px;box-shadow:0 6px 16px rgba(15,23,42,.025)}
.topology-summary-card strong{font-size:20px;color:#0f172a}
.topology-summary-card.success{background:#f7fefb}.topology-summary-card.warning{background:#fffaf0}.topology-summary-card.info{background:#f8fafc}
.topology-knowledge-layout{display:grid;grid-template-columns:minmax(0,1fr) 320px;gap:12px;align-items:start}
.knowledge-graph-panel,.knowledge-relation-panel{min-width:0;border:1px solid rgba(148,163,184,.16);border-radius:12px;background:#fff;box-shadow:0 10px 22px rgba(15,23,42,.035)}
.knowledge-graph-panel{padding:12px;overflow:hidden}
.knowledge-relation-panel{padding:12px;position:sticky;top:12px}
.knowledge-panel-head{display:flex;align-items:flex-start;justify-content:space-between;gap:10px;margin-bottom:10px}
.knowledge-panel-head>div{min-width:0;display:flex;flex-direction:column;gap:3px}
.knowledge-panel-head strong{font-size:14px;color:#0f172a}
.knowledge-panel-head span{font-size:12px;color:#64748b;line-height:1.45}
.knowledge-graph-stage{position:relative;min-height:500px;border:1px solid rgba(148,163,184,.18);border-radius:18px;overflow:auto;background:linear-gradient(rgba(148,163,184,.07) 1px,transparent 1px),linear-gradient(90deg,rgba(148,163,184,.07) 1px,transparent 1px),linear-gradient(rgba(59,130,246,.1) 1px,transparent 1px),linear-gradient(90deg,rgba(59,130,246,.1) 1px,transparent 1px),radial-gradient(circle at top left,rgba(59,130,246,.08),transparent 28%),radial-gradient(circle at bottom right,rgba(16,185,129,.08),transparent 30%),linear-gradient(180deg,#f8fbff 0%,#f1f7fd 100%);background-size:22px 22px,22px 22px,88px 88px,88px 88px,auto,auto,auto;box-shadow:inset 0 1px 0 rgba(255,255,255,.8);scrollbar-width:thin}
.knowledge-graph-board{position:relative;min-width:100%}
.knowledge-graph-edges{position:absolute;inset:0;z-index:3;pointer-events:none}
.knowledge-board-edge{fill:none;stroke:rgba(139,92,246,.34);stroke-width:1.5;stroke-linecap:round;transition:opacity .16s ease,stroke-width .16s ease,stroke .16s ease}
.knowledge-board-edge.is-runs_on{stroke:rgba(8,145,178,.44)}
.knowledge-board-edge.is-connects_to{stroke:rgba(34,197,94,.42)}
.knowledge-board-edge.is-depends_on{stroke:rgba(139,92,246,.42);stroke-dasharray:8 6}
.knowledge-board-edge.is-binds_to{stroke:rgba(245,158,11,.52);stroke-dasharray:10 7}
.knowledge-board-edge.is-match{stroke-width:2.3;opacity:.95}
.knowledge-board-lane{position:absolute;z-index:2}
.knowledge-board-lane-title{position:absolute;left:0;right:0;top:0;z-index:7;height:34px;border:1px solid color-mix(in srgb,var(--lane-color,#245bdb) 24%,rgba(148,163,184,.2));border-radius:14px;background:rgba(255,255,255,.98);color:#0f172a;display:flex;align-items:center;justify-content:center;gap:8px;font-size:14px;font-weight:800;box-shadow:0 10px 22px rgba(15,23,42,.055)}
.knowledge-board-lane-title strong{min-width:22px;height:20px;border-radius:999px;background:color-mix(in srgb,var(--lane-color,#245bdb) 12%,#fff);color:var(--lane-color,#245bdb);display:inline-flex;align-items:center;justify-content:center;font-size:12px}
.knowledge-board-lane-body{position:absolute;left:0;right:0;top:46px;bottom:0;border:1px solid rgba(148,163,184,.18);border-radius:18px;background:color-mix(in srgb,var(--lane-color,#245bdb) 7%,rgba(255,255,255,.72));overflow:hidden}
.knowledge-board-lane-body::after{content:"";position:absolute;inset:0;background-image:linear-gradient(rgba(255,255,255,.28) 1px,transparent 1px),linear-gradient(90deg,rgba(255,255,255,.28) 1px,transparent 1px);background-size:28px 28px;pointer-events:none}
.knowledge-board-lane-count{position:absolute;top:12px;left:14px;z-index:5;padding:3px 9px;border-radius:8px;background:rgba(255,255,255,.9);color:#475569;font-size:12px;font-weight:700}
.knowledge-board-node{appearance:none;position:absolute;z-index:8;border:0;background:transparent;padding:0;display:grid;grid-template-columns:28px minmax(0,1fr);grid-template-rows:1fr auto;column-gap:8px;align-items:center;text-align:left;cursor:pointer;--node-color:var(--topology-node-color,#245bdb)}
.knowledge-board-node-dot{grid-row:1/3;width:26px;height:26px;border-radius:999px;background:var(--node-color);box-shadow:0 0 0 2px rgba(255,255,255,.98),0 0 0 5px color-mix(in srgb,var(--node-color) 12%,transparent)}
.knowledge-board-node-main{min-width:0;border:1px solid color-mix(in srgb,var(--node-color) 20%,rgba(148,163,184,.22));border-radius:14px;background:rgba(255,255,255,.96);padding:7px 9px;box-shadow:0 12px 24px rgba(15,23,42,.09);display:flex;flex-direction:column;gap:2px}
.knowledge-board-node-main strong,.knowledge-board-node-main small,.knowledge-board-node-meta{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.knowledge-board-node-main strong{font-size:12px;color:#0f172a;line-height:1.2}
.knowledge-board-node-main small{font-size:11px;color:#64748b;line-height:1.2}
.knowledge-board-node-meta{grid-column:2;color:#64748b;font-size:11px;margin-left:9px;margin-top:3px}
.knowledge-board-node:hover,.knowledge-board-node.is-match{z-index:12;filter:saturate(1.08)}
.knowledge-board-node:hover .knowledge-board-node-main,.knowledge-board-node.is-match .knowledge-board-node-main{border-color:color-mix(in srgb,var(--node-color) 38%,rgba(148,163,184,.24));box-shadow:0 16px 30px rgba(15,23,42,.14)}
.knowledge-graph-source-note{position:absolute;left:14px;bottom:14px;z-index:12;display:inline-flex;align-items:center;gap:6px;padding:7px 10px;border:1px solid rgba(148,163,184,.2);border-radius:999px;background:rgba(255,255,255,.96);color:#0f172a;font-size:11px;box-shadow:0 14px 30px rgba(15,23,42,.1)}
.knowledge-graph-legend{position:absolute;top:14px;right:14px;z-index:12;width:132px;padding:9px 10px;border:1px solid rgba(148,163,184,.2);border-radius:16px;background:rgba(255,255,255,.97);color:#334155;box-shadow:0 16px 34px rgba(15,23,42,.12);backdrop-filter:blur(8px)}
.legend-title{font-size:11px;font-weight:800;color:#0f172a;margin-bottom:6px}
.legend-row{display:grid;grid-template-columns:12px minmax(0,1fr) auto;align-items:center;gap:6px;min-height:20px;font-size:11px;color:#475569}
.legend-row span:nth-child(2){min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.legend-row em{font-style:normal;color:#94a3b8;font-size:10px}
.legend-dot{width:8px;height:8px;border-radius:999px}
.legend-line{width:12px;height:2px;border-radius:999px;background:rgba(139,92,246,.48)}
.legend-divider{height:1px;background:rgba(148,163,184,.18);margin:7px 0}
.knowledge-graph-empty{position:absolute;inset:0;z-index:14;display:flex;align-items:center;justify-content:center;background:rgba(248,250,252,.76)}
.knowledge-relation-list{display:flex;flex-direction:column;gap:8px;max-height:560px;overflow:auto;padding-right:2px}
.knowledge-relation-row{border:1px solid rgba(148,163,184,.16);border-radius:10px;background:#fff;padding:9px 10px}
.knowledge-relation-row.is-match{border-color:rgba(51,112,255,.22);background:#f8fbff}
.knowledge-relation-chain{display:grid;grid-template-columns:minmax(0,1fr) auto minmax(0,1fr);gap:8px;align-items:center}
.knowledge-relation-chain span{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#0f172a;font-size:12px;font-weight:700}
.knowledge-relation-chain strong{border-radius:999px;background:#eef4ff;color:#245bdb;padding:3px 8px;font-size:12px;white-space:nowrap}
.knowledge-relation-row p{margin:6px 0 0;color:#64748b;font-size:12px;line-height:1.45}
.detail-section--cost{gap:10px}
.cost-detail-summary{display:flex;align-items:center;gap:12px;min-height:42px;padding:8px 10px;border:1px solid rgba(148,163,184,.16);border-radius:8px;background:#fbfdff}
.cost-detail-value{display:inline-flex;align-items:baseline;gap:6px;min-width:0;color:#64748b;font-size:12px}
.cost-detail-value strong{color:#0f172a;font-size:16px;line-height:1.25;white-space:nowrap}
.cost-detail-value--primary{margin-left:auto}
.request-summary-grid{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:10px;margin:0 0 10px}
.request-summary-card{appearance:none;text-align:left;min-height:68px;border:1px solid rgba(148,163,184,.18);border-radius:14px;background:#fff;padding:14px 16px;display:flex;align-items:center;justify-content:space-between;color:#475569;font:inherit;font-size:13px;cursor:pointer;box-shadow:0 10px 24px rgba(15,23,42,.035)}
.request-summary-card:hover,.request-summary-card.active{border-color:rgba(36,91,219,.28);background:#f7faff;box-shadow:0 0 0 2px rgba(36,91,219,.06)}
.request-summary-card strong{font-size:24px;color:#0f172a}
.request-summary-card.success{background:#f7fefb}.request-summary-card.warning{background:#fffaf0}.request-summary-card.danger{background:#fff8f8}.request-summary-card.info{background:#f8fafc}
.request-create-form{padding-top:2px}
.request-type-hint{display:flex;align-items:center;justify-content:space-between;gap:8px;min-height:32px;padding:0 10px;border:1px solid rgba(36,91,219,.12);border-radius:8px;background:#f7faff;color:#245bdb;font-size:12px;font-weight:600}
.request-type-hint small{color:#64748b;font-weight:500}
.request-delivery-switch{width:100%}
.request-delivery-switch :deep(.el-radio-button){flex:1}
.request-delivery-switch :deep(.el-radio-button__inner){width:100%;font-weight:700}
.request-provision-hint{display:flex;align-items:center;gap:8px;margin:-2px 0 4px;padding:9px 12px;border:1px solid rgba(36,91,219,.12);border-radius:10px;background:#f7faff;color:#475569;font-size:13px;line-height:1.5}
.request-provision-hint .el-icon{color:#245bdb;font-size:16px}
.request-inline-fields{width:100%;display:flex;align-items:center;gap:8px}
.request-inline-fields :deep(.el-select){flex:1;min-width:0}
.request-inline-fields :deep(.el-input-number){width:116px}
.request-inline-fields>span{color:#64748b;font-size:12px}
.ledger-tree-context-strip{display:flex;align-items:center;justify-content:space-between;gap:10px;margin:-2px 0 10px;padding:9px 10px;border:1px solid rgba(51,112,255,.16);border-radius:10px;background:#f8fbff}
.ledger-tree-context-strip--summary{border-color:rgba(34,197,94,.18);background:#f7fefb}
.ledger-tree-context-strip--authorization{border-color:rgba(14,165,233,.18);background:#f7fcff}
.ledger-tree-context-strip--view{border-color:rgba(99,102,241,.18);background:#f8f7ff}
.ledger-tree-context-strip--governance{border-color:rgba(245,158,11,.2);background:#fffbeb}
.ledger-tree-context-copy{display:flex;align-items:center;gap:8px;min-width:0;flex-wrap:wrap;font-size:12px;color:#64748b}
.ledger-tree-context-copy strong{color:#245bdb;font-weight:800}
.ledger-tree-context-strip--summary .ledger-tree-context-copy strong{color:#15803d}
.ledger-tree-context-strip--authorization .ledger-tree-context-copy strong{color:#0369a1}
.ledger-tree-context-strip--view .ledger-tree-context-copy strong{color:#4f46e5}
.ledger-tree-context-strip--governance .ledger-tree-context-copy strong{color:#b45309}
.third-party-expiry-strip{display:flex;align-items:center;justify-content:space-between;gap:12px;margin:-2px 0 10px;padding:9px 10px;border:1px solid rgba(36,91,219,.12);border-radius:10px;background:#fbfdff}
.third-party-expiry-copy{display:inline-flex;align-items:baseline;gap:8px;min-width:0;flex-wrap:wrap;font-size:12px;color:#64748b}
.third-party-expiry-copy strong{color:#245bdb;font-size:12px;font-weight:800}
.third-party-expiry-actions{display:flex;align-items:center;justify-content:flex-end;gap:6px;flex-wrap:wrap}
.third-party-expiry-action{min-width:72px;height:30px;padding:0 8px;border:1px solid rgba(148,163,184,.18);border-radius:8px;background:#fff;color:#475569;display:inline-flex;align-items:center;justify-content:space-between;gap:7px;font:inherit;font-size:12px;cursor:pointer;transition:all .16s ease}
.third-party-expiry-action strong{color:#0f172a;font-size:13px;font-weight:800}
.third-party-expiry-action:hover,.third-party-expiry-action.active{border-color:rgba(51,112,255,.28);background:#eef4ff;color:#245bdb}
.third-party-expiry-action.active{box-shadow:inset 0 0 0 1px rgba(51,112,255,.1)}
.third-party-expiry-action.active strong{color:#245bdb}
.third-party-expiry-action.danger{background:#fff8f8;border-color:rgba(239,68,68,.18)}
.third-party-expiry-action.danger span,.third-party-expiry-action.danger strong{color:#dc2626}
.third-party-expiry-action.warning{background:#fffaf0;border-color:rgba(245,158,11,.2)}
.third-party-expiry-action.warning span,.third-party-expiry-action.warning strong{color:#b45309}
.third-party-expiry-action.success{background:#f7fefb;border-color:rgba(34,197,94,.18)}
.third-party-expiry-action.success span,.third-party-expiry-action.success strong{color:#15803d}
.resource-tree-summary-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px;margin-bottom:10px}
.resource-tree-summary-card{border:1px solid rgba(148,163,184,.18);border-radius:10px;background:#fff;padding:10px 12px;display:flex;align-items:center;justify-content:space-between;color:#475569;font-size:13px}
.resource-tree-summary-card strong{font-size:20px;color:#0f172a}
.resource-tree-summary-card.success{background:#f7fefb}.resource-tree-summary-card.warning{background:#fffaf0}.resource-tree-summary-card.info{background:#f8fafc}
.resource-tree-grid{display:grid;grid-template-columns:minmax(248px,.65fr) minmax(0,1.35fr);gap:10px}
.resource-tree-list{display:flex;flex-direction:column;gap:8px;max-height:420px;overflow:auto}
.resource-tree-biz{border:1px solid rgba(148,163,184,.16);border-radius:12px;background:#fff;padding:8px}
.resource-tree-node{display:flex;align-items:center;justify-content:space-between;gap:8px;min-height:30px;border-radius:8px;font-size:13px}
.resource-tree-node--action{width:100%;border:0;font:inherit;text-align:left;cursor:pointer;transition:all .16s ease}
.resource-tree-node--action:hover{box-shadow:0 8px 16px rgba(36,91,219,.08);transform:translateY(-1px)}
.resource-tree-node--action.is-active{box-shadow:inset 0 0 0 1px rgba(51,112,255,.22),0 8px 16px rgba(36,91,219,.08);background:#eef4ff;color:#245bdb}
.resource-tree-node-main{display:flex;align-items:center;gap:6px;min-width:0}
.resource-tree-node-main span{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.resource-tree-node small{font-size:11px;color:#64748b;font-weight:600}
.resource-tree-node.is-active small{color:#245bdb}
.resource-tree-node--biz{padding:0 8px;font-weight:800;color:#0f172a;background:#f4f7ff}
.resource-tree-node--biz strong{font-size:12px;color:#245bdb}
.resource-tree-env-list{display:flex;align-items:center;gap:6px;flex-wrap:wrap;padding:8px 2px 0}
.resource-tree-node--env{display:inline-flex;justify-content:center;width:auto;min-height:26px;padding:0 8px;border:1px solid rgba(34,197,94,.18);background:#f7fefb;color:#15803d}
.request-action-shell{display:flex;flex-direction:column;gap:10px}
.request-action-card{border:1px solid rgba(148,163,184,.18);border-radius:10px;background:#f8fafc;padding:10px 12px;display:flex;flex-direction:column;gap:4px}
.request-action-card strong{color:#0f172a;font-size:14px}.request-action-card span{color:#64748b;font-size:12px;line-height:1.45}
.bulk-ledger-form{margin-top:14px}
.asset-password-shell{display:flex;flex-direction:column;gap:12px;min-height:120px}
.asset-password-missing-hint{padding:8px 10px;border:1px solid rgba(245,158,11,.2);border-radius:8px;background:#fffaf0;color:#a16207;font-size:12px;line-height:1.4}
.asset-password-summary{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}
.asset-password-summary>div{display:flex;flex-direction:column;gap:4px;padding:10px 12px;border:1px solid rgba(148,163,184,.16);border-radius:10px;background:#f8fafc;min-width:0}
.asset-password-summary .span-2{grid-column:span 2}
.asset-password-summary span,.asset-password-reveal span{font-size:12px;color:#64748b}
.asset-password-summary strong{font-size:13px;color:#0f172a;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.asset-password-reveal{display:flex;align-items:center;gap:8px;padding:10px 12px;border:1px solid rgba(36,91,219,.16);border-radius:10px;background:#f4f7ff}
.asset-password-reveal>div{min-width:0;display:flex;flex:1;flex-direction:column;gap:4px}
.asset-password-reveal strong{font-family:Consolas,Monaco,monospace;font-size:14px;color:#0f172a;overflow-wrap:anywhere}
.asset-password-actions{display:flex;align-items:center;justify-content:flex-end;gap:8px}
.asset-password-form{padding-top:4px}
.asset-password-input--masked :deep(.el-input__inner){-webkit-text-security:disc}
.asset-password-visibility-toggle{min-width:32px;height:24px;padding:0 2px;font-size:12px}
.request-delivery-form{border:1px solid rgba(148,163,184,.14);border-radius:10px;background:#fff;padding:10px 12px 0}
.sync-resolve-shell{display:flex;flex-direction:column;gap:10px}
.request-detail-shell{gap:12px}
.request-detail-statusbar{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px}
.request-detail-statusbar>div{min-width:0;border:1px solid rgba(148,163,184,.16);border-radius:10px;background:#fff;padding:9px 10px;display:flex;flex-direction:column;gap:3px}
.request-detail-statusbar span,.request-note-list span{font-size:12px;color:#64748b}
.request-detail-statusbar strong,.request-note-list strong{min-width:0;color:#0f172a;font-size:12px;font-weight:700;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.request-detail-note{min-height:38px;color:#475569;font-size:12px;line-height:1.6;border:1px dashed rgba(148,163,184,.2);border-radius:10px;background:#fff;padding:8px 10px}
.request-note-list{display:flex;flex-direction:column;gap:8px}
.request-note-list>div{display:flex;flex-direction:column;gap:3px;border-bottom:1px dashed rgba(148,163,184,.16);padding-bottom:8px}
.request-note-list>div:last-child{border-bottom:0;padding-bottom:0}
.request-detail-delivered-list{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:6px}
.request-detail-delivered-list .delivered-resource-row{border:1px solid rgba(148,163,184,.16);background:#fff}
.request-timeline{display:flex;flex-direction:column;gap:8px}
.request-timeline-item{display:grid;grid-template-columns:14px minmax(0,1fr);gap:8px;align-items:flex-start}
.request-timeline-dot{width:10px;height:10px;border-radius:999px;background:#94a3b8;margin-top:10px;box-shadow:0 0 0 4px rgba(148,163,184,.14)}
.request-timeline-dot.success{background:#22c55e;box-shadow:0 0 0 4px rgba(34,197,94,.14)}
.request-timeline-dot.warning{background:#f59e0b;box-shadow:0 0 0 4px rgba(245,158,11,.14)}
.request-timeline-dot.danger{background:#ef4444;box-shadow:0 0 0 4px rgba(239,68,68,.14)}
.request-timeline-card{min-width:0;border:1px solid rgba(148,163,184,.16);border-radius:10px;background:#fff;padding:8px 10px}
.request-timeline-head,.request-timeline-meta{display:flex;align-items:center;gap:8px;min-width:0}
.request-timeline-head{justify-content:space-between;margin-bottom:5px}
.request-timeline-head strong{font-size:12px;color:#0f172a}.request-timeline-head span{font-size:12px;color:#94a3b8;white-space:nowrap}
.request-timeline-meta span{min-width:0;color:#64748b;font-size:12px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.resource-cell,.stack-cell{display:flex;flex-direction:column;gap:3px}.resource-cell-meta{min-width:0;display:flex;align-items:center;gap:7px}.resource-cell-meta>span{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.asset-id-badge{flex:none;padding:1px 5px;border-radius:4px;background:#f1f5f9;color:#64748b;font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,"Liberation Mono",monospace;font-size:10px;line-height:1.4}.inline-cell{display:inline-flex;align-items:center;gap:6px;min-width:0}.clickable-tag{cursor:pointer}.delivered-resource-list{display:flex;flex-direction:column;gap:4px}.delivered-resource-row{display:flex;flex-direction:column;align-items:flex-start;gap:2px;width:100%;padding:6px 8px;border:0;border-radius:8px;background:transparent;color:#0f172a;text-align:left;cursor:pointer}.delivered-resource-row:hover{background:#f3f6fb}.delivered-resource-row span{font-size:12px;color:#64748b}.resource-cell span,.sub-text{font-size:12px;color:#64748b}.source-status-line,.source-sync-status{display:flex;align-items:center;gap:6px;min-width:0}.source-status-line span,.source-sync-cell>span{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.source-sync-status .el-tag{flex:none}
.resource-cell--child{padding-left:14px;position:relative}
.resource-cell--child::before{content:"";position:absolute;left:2px;top:7px;width:6px;height:12px;border-left:1px solid rgba(148,163,184,.5);border-bottom:1px solid rgba(148,163,184,.5);border-radius:0 0 0 4px}
.cmdb-table{width:100%}
:deep(.cmdb-table .is-selected-model){--el-table-tr-bg-color:#f4f7ff}
.cmdb-form-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:0 16px}
.relation-dialog-form{row-gap:10px}
.cmdb-form-grid :deep(.el-form-item__label){align-items:center;min-height:32px;line-height:32px;white-space:nowrap}
.cmdb-form-grid :deep(.el-form-item__content){min-width:0}
.cmdb-form-grid :deep(.span-2){grid-column:span 2}
.ci-form-model-summary{min-width:0;margin:0 0 14px;padding:10px 12px;border:1px solid rgba(36,91,219,.12);border-radius:10px;background:#f8fbff;display:grid;grid-template-columns:minmax(0,1fr) auto;gap:6px 10px;align-items:center}
.ci-form-model-summary-main{min-width:0;display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.ci-form-model-summary-main strong{font-size:13px;color:#0f172a}
.ci-form-model-summary-main span{font-size:12px;color:#64748b}
.ci-form-model-summary-tags{display:flex;align-items:center;justify-content:flex-end;gap:6px;flex-wrap:wrap}
.ci-form-model-summary p{grid-column:1/-1;margin:0;color:#64748b;font-size:12px;line-height:1.5}
.ci-form-field-meta{width:100%;margin-top:4px;color:#94a3b8;font-size:11px;line-height:1.45;word-break:break-all}
.cmdb-form-section-title{display:flex;align-items:center;gap:8px;margin:2px 0 12px;color:#475569;font-size:12px;font-weight:800}
.cmdb-form-section-title span{flex:none}
.cmdb-form-section-title small{min-width:0;color:#94a3b8;font-size:12px;font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.cmdb-form-section-title::after{content:"";height:1px;flex:1;background:rgba(148,163,184,.22)}
.model-icon-current{width:100%;display:flex;align-items:center;gap:10px;color:#374151;font-size:13px}
.model-icon-preview{width:34px;height:34px;border:1px solid rgba(148,163,184,.18);border-radius:10px;background:#f8fafc;display:inline-flex;align-items:center;justify-content:center;font-size:18px}
.model-icon-picker{width:100%;display:grid;grid-template-columns:repeat(auto-fill,minmax(110px,1fr));gap:8px;max-height:286px;overflow:auto;padding:8px;border:1px solid rgba(148,163,184,.16);border-radius:12px;background:#f8fafc}
.model-icon-option{min-width:0;height:44px;border:1px solid rgba(148,163,184,.16);border-radius:10px;background:#fff;padding:0 10px;display:flex;align-items:center;gap:8px;text-align:left;cursor:pointer;transition:all .16s ease}
.model-icon-option:hover,.model-icon-option.active{border-color:rgba(36,91,219,.28);background:#eef4ff}
.model-icon-option span{width:24px;height:24px;border-radius:8px;background:#f8fafc;display:inline-flex;align-items:center;justify-content:center;font-size:16px;flex:none}
.model-icon-option strong{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:12px;color:#334155}
.runtime-secret-shell{display:flex;flex-direction:column;gap:12px}
.runtime-secret-hint{padding:8px 10px;border:1px solid rgba(51,112,255,.12);border-radius:10px;background:#f8fbff;color:#64748b;font-size:12px;line-height:1.6}
.sync-template-option{display:flex;align-items:center;gap:8px;min-width:0}
.sync-template-option strong{flex:0 0 auto;color:#1f2937;font-weight:800}
.sync-template-option span{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#64748b;font-size:12px}
.sync-cloud-option{display:flex;flex-direction:column;gap:2px;line-height:1.25}
.sync-cloud-option strong{font-size:13px;color:#0f172a}
.sync-cloud-option span{font-size:12px;color:#64748b}
.sync-job-minimal-form{row-gap:8px}
.sync-job-minimal-form :deep(.el-form-item){margin-bottom:8px}
.sync-switch-field{display:flex;flex-direction:column;align-items:flex-start;gap:4px;line-height:1.4}
.sync-switch-field small{font-size:12px;color:#64748b}
.prometheus-metrics-panel{display:grid;grid-template-columns:1fr;gap:8px;margin-bottom:4px;padding:9px 10px;border:1px solid rgba(148,163,184,.18);border-radius:8px;background:#fff}
.prometheus-metrics-panel :deep(.prometheus-metrics-panel__item){margin:0}
.prometheus-metrics-panel :deep(.prometheus-metrics-panel__item + .prometheus-metrics-panel__item){padding-top:8px}
.cloud-credential-description{margin-top:8px}
.cloud-product-picker{width:100%;display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:6px}
.cloud-product-picker :deep(.el-checkbox.is-bordered){height:auto;min-height:40px;margin:0;padding:5px 7px;border-radius:8px;background:#fff}
.cloud-product-picker :deep(.el-checkbox__label){min-width:0}
.cloud-product-option{display:flex;flex-direction:column;gap:2px;line-height:1.25}
.cloud-product-option strong{font-size:12px;color:#0f172a}
.cloud-product-option small{font-size:11px;color:#64748b}
.sync-cloud-console{display:flex;flex-direction:column;gap:12px}
.sync-cloud-section{border:1px solid rgba(148,163,184,.16);border-radius:14px;background:#fff;padding:14px 16px;box-shadow:0 10px 24px rgba(15,23,42,.04)}
.sync-cloud-section-head{margin-bottom:10px}
.sync-provider-strip{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:10px}
.sync-provider-strip span{height:24px;padding:0 9px;border-radius:999px;background:#f8fbff;border:1px solid rgba(36,91,219,.12);color:#245bdb;font-size:12px;font-weight:700;display:inline-flex;align-items:center}
.sync-account-card-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(282px,1fr));gap:10px;align-items:stretch}
.sync-account-card-grid--private{grid-template-columns:repeat(auto-fill,minmax(282px,1fr))}
.sync-account-tile{min-width:0;height:100%;border:1px solid rgba(148,163,184,.16);border-radius:12px;background:linear-gradient(180deg,#fff 0%,#f8fbff 100%);padding:12px;display:flex;flex-direction:column;gap:10px;box-shadow:0 4px 14px rgba(15,23,42,.03)}
.sync-account-tile--private{background:linear-gradient(180deg,#fff 0%,#f8fafc 100%)}
.sync-account-tile-head{display:flex;align-items:flex-start;justify-content:space-between;gap:10px;min-width:0}
.sync-account-tile-head>div{min-width:0;display:flex;flex-direction:column;gap:3px}
.sync-account-tile-head strong{font-size:14px;color:#0f172a;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.sync-account-tile-head span{font-size:12px;color:#64748b;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.sync-account-tile-meta{display:flex;align-items:center;gap:6px;flex-wrap:wrap}
.sync-account-tile-meta span{height:22px;padding:0 8px;border-radius:8px;background:#f8fafc;border:1px solid rgba(148,163,184,.14);color:#475569;font-size:12px;display:inline-flex;align-items:center}
.sync-account-products{position:relative;display:flex;align-items:flex-start;align-content:flex-start;gap:6px;flex-wrap:wrap;min-height:52px;max-height:78px;overflow:hidden;padding-right:34px}
.sync-account-products span{height:22px;line-height:22px;padding:0 8px;border-radius:999px;background:#eef4ff;color:#245bdb;font-size:11px;font-weight:700;display:inline-flex;align-items:center;max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.sync-account-products-more{position:absolute;right:0;bottom:0;min-width:28px;justify-content:center;box-shadow:0 0 0 4px #fff}
.sync-account-task-drawer{display:flex;flex-direction:column;gap:12px}
.sync-account-task-drawer-summary{border:1px solid rgba(148,163,184,.16);border-radius:12px;background:linear-gradient(180deg,#fff 0%,#f8fbff 100%);padding:12px;display:flex;flex-direction:column;gap:4px;box-shadow:0 8px 20px rgba(15,23,42,.035)}
.sync-account-task-drawer-summary span{font-size:12px;color:#64748b}
.sync-account-task-drawer-summary strong{font-size:15px;color:#0f172a}
.sync-account-task-drawer-summary small{font-size:12px;line-height:1.5;color:#64748b}
.sync-account-task-list{border:1px solid rgba(148,163,184,.14);border-radius:10px;background:rgba(248,250,252,.72);padding:8px;display:flex;flex-direction:column;gap:6px}
.sync-account-task-list--drawer{max-height:calc(100vh - 210px);overflow:auto}
.sync-account-task-head{display:flex;align-items:center;justify-content:space-between;gap:8px;color:#64748b;font-size:12px}
.sync-account-task-head strong{color:#0f172a;font-size:12px}
.sync-account-task-row{min-width:0;display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:center;gap:8px;border:1px solid rgba(148,163,184,.12);border-radius:8px;background:#fff;padding:7px 8px}
.sync-account-task-row.is-failed{border-color:rgba(239,68,68,.18);background:linear-gradient(180deg,#fff 0%,#fff7f7 100%)}
.sync-account-task-main{min-width:0;display:flex;flex-direction:column;gap:2px}
.sync-account-task-row strong{min-width:0;font-size:12px;color:#0f172a;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.sync-account-task-row span{min-width:0;font-size:11px;color:#64748b;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.sync-account-task-actions{display:inline-flex;align-items:center;gap:6px;min-width:118px;justify-content:flex-end}
.sync-account-task-actions :deep(.el-button){padding:0;font-size:12px}
.sync-account-tile-foot{display:flex;flex-direction:column;align-items:stretch;gap:8px;border-top:1px dashed rgba(148,163,184,.18);padding-top:9px;margin-top:auto}
.sync-account-tile-foot small{min-width:0;color:#64748b;font-size:12px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.sync-account-actions{width:100%;display:flex;align-items:center;justify-content:flex-end;gap:6px;flex-shrink:0;flex-wrap:nowrap;overflow:hidden}
.sync-account-actions :deep(.el-button){flex:0 0 auto;margin-left:0;padding-left:7px;padding-right:7px}
.sync-account-actions :deep(.el-button+.el-button){margin-left:0}
.sync-account-create-tile{height:100%;min-height:154px;border:1px dashed rgba(36,91,219,.25);border-radius:12px;background:#f8fbff;color:#245bdb;padding:14px;display:flex;flex-direction:column;align-items:flex-start;justify-content:center;gap:8px;text-align:left;cursor:pointer}
.sync-account-create-tile:hover{border-color:rgba(36,91,219,.42);background:#eef4ff}
.sync-account-create-tile :deep(.el-icon){font-size:20px}
.sync-account-create-tile strong{font-size:14px;color:#1d4ed8}
.sync-account-create-tile span{font-size:12px;line-height:1.6;color:#64748b}
.sync-account-create-tile--private{border-color:rgba(15,118,110,.22);background:#f8fdfa;color:#0f766e}
.sync-account-create-tile--private:hover{border-color:rgba(15,118,110,.36);background:#ecfdf5}
.sync-account-create-tile--private strong{color:#0f766e}
.sync-opsany-layout{display:grid;grid-template-columns:256px minmax(0,1fr);gap:14px;align-items:start}
.sync-account-shell--side{position:sticky;top:8px;margin-bottom:0}
.sync-account-shell--side .phase-one-guide-head{margin-bottom:10px}
.sync-account-shell--side .sync-account-grid{grid-template-columns:1fr;max-height:620px;overflow:auto;padding-right:2px}
.sync-task-panel{min-width:0}
.sync-task-head{align-items:flex-start;margin-bottom:10px}
.field-mapping-toolbar{display:flex;align-items:flex-start;justify-content:space-between;gap:12px}
.field-mapping-toolbar>div{display:flex;flex-direction:column;gap:2px;min-width:0}
.field-mapping-toolbar strong{font-size:13px;color:#0f172a}
.field-mapping-toolbar span{font-size:12px;line-height:1.45;color:#64748b}
.field-mapping-table{border:1px solid rgba(148,163,184,.12);border-radius:10px;overflow:hidden}
.bulk-import-shell{display:flex;flex-direction:column;gap:10px}
.bulk-import-template-picker{display:flex;align-items:center;gap:9px;min-height:42px;padding:0 11px;border:1px solid rgba(148,163,184,.16);border-radius:10px;background:#fff;color:#475569;font-size:12px}.bulk-import-template-picker>span{flex:0 0 auto;color:#334155;font-weight:700}.bulk-import-template-picker small{min-width:0;overflow:hidden;color:#94a3b8;font-size:11px;text-overflow:ellipsis;white-space:nowrap}
.bulk-import-guide{display:flex;align-items:center;gap:7px;min-height:38px;padding:0 11px;border:1px solid rgba(36,91,219,.12);border-radius:10px;background:#f6f9ff;color:#64748b;font-size:12px}
.bulk-import-guide__step{width:18px;height:18px;display:inline-flex;align-items:center;justify-content:center;border-radius:50%;background:#e8f0ff;color:#245bdb;font-size:11px;font-weight:800}
.bulk-import-guide__divider{color:#cbd5e1}.bulk-import-guide :deep(.el-button){padding:0;font-size:12px}
.bulk-import-upload{display:flex;align-items:center;gap:9px;min-height:42px;padding:0 11px;border:1px dashed rgba(51,112,255,.28);border-radius:10px;background:#fbfdff;color:#64748b;font-size:12px}
.bulk-import-upload input{display:none}.bulk-import-upload span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.bulk-import-editor-head{display:flex;align-items:center;justify-content:space-between;gap:12px;color:#334155;font-size:13px;font-weight:700}.bulk-import-tip{color:#94a3b8;font-size:12px;line-height:1.45}
.switch-row{display:flex;align-items:center;gap:14px;flex-wrap:wrap}
.ci-detail-shell{display:flex;flex-direction:column;gap:6px}
.detail-heading{display:flex;align-items:flex-start;justify-content:space-between;gap:10px}
.detail-heading-main{min-width:0;display:flex;flex-direction:column;gap:2px}
.detail-heading-actions{display:inline-flex;align-items:center;gap:6px;flex-shrink:0}
.detail-title-row{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.detail-main-title{font-size:16px;line-height:1.35;color:#0f172a}
.detail-subline{display:flex;align-items:center;gap:8px;flex-wrap:wrap;color:#64748b;font-size:12px}
.detail-quick-actions{align-self:flex-start;display:inline-flex;align-items:center;gap:4px;flex-wrap:wrap;padding:4px;border:1px solid rgba(51,112,255,.14);border-radius:9px;background:#f8fafc;box-shadow:0 3px 8px rgba(15,23,42,.035)}
.detail-quick-action{height:28px;padding:0 10px;border-radius:6px;font-size:12px;font-weight:600;box-shadow:none;transition:background .16s ease,border-color .16s ease,color .16s ease,box-shadow .16s ease}
.detail-quick-action--web{border-color:#cbdcff;background:#eaf2ff;color:#245bdb}
.detail-quick-action--credential{border-color:#cbdcff;background:#eaf2ff;color:#245bdb}
.detail-quick-action:hover{color:#245bdb;border-color:#b9d0ff;background:#f1f6ff;box-shadow:0 2px 5px rgba(36,91,219,.08)}
.detail-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:6px}
.detail-section{display:flex;flex-direction:column;gap:5px;padding:8px 10px;border-radius:9px;background:#f8fafc;border:1px solid rgba(148,163,184,.14);min-width:0}
.detail-section-head{display:flex;align-items:center;justify-content:space-between;gap:10px}
.detail-section-actions{display:flex;align-items:center;gap:8px;flex-shrink:0}
.detail-waterline-source{display:block;white-space:nowrap}
.detail-waterline-chart{width:100%;height:176px;border:1px solid rgba(148,163,184,.16);border-radius:10px;background:#fff}
.detail-section-desc{margin-top:3px;color:#64748b;font-size:12px;line-height:1.45}
.detail-section-title{font-size:12px;font-weight:800;color:#0f172a}
.compact-stack{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:6px 10px}
.muted-text{font-size:12px;color:#94a3b8}
.relation-suggestion-cell{display:flex;flex-direction:column;gap:6px;min-width:0}
.relation-suggestion-rule{display:flex;align-items:center;gap:8px;flex-wrap:wrap;font-size:12px}
.relation-suggestion-rule strong{color:#245bdb;font-weight:800}
.relation-suggestion-rule span{color:#64748b}
.relation-suggestion-list{display:flex;flex-direction:column;gap:6px}
.relation-suggestion-item{display:flex;align-items:center;justify-content:space-between;gap:8px;min-width:0;padding:6px 8px;border:1px solid rgba(148,163,184,.16);border-radius:8px;background:#fff}
.relation-suggestion-main{flex:1;min-width:0;display:flex;flex-direction:column;gap:2px;padding:0;border:0;background:transparent;text-align:left;cursor:pointer}
.relation-suggestion-main strong{max-width:170px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#0f172a;font-size:12px}
.relation-suggestion-main span{max-width:210px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#64748b;font-size:12px}
.sync-relation-issue-list{display:flex;flex-direction:column;gap:8px;min-height:58px}
.sync-relation-issue-card{display:flex;flex-direction:column;gap:8px;padding:8px;border:1px solid rgba(245,158,11,.18);border-radius:10px;background:#fff}
.sync-relation-candidate .relation-suggestion-main strong{max-width:260px}
.sync-relation-candidate .relation-suggestion-main span{max-width:360px}
.detail-kv{min-width:0;color:#475569;font-size:12px;line-height:1.5;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.detail-kv--full,.detail-kv--source{grid-column:1 / -1;white-space:normal;overflow:visible;text-overflow:clip;overflow-wrap:anywhere}
.field-value-list{display:flex;flex-direction:column;gap:6px}
.field-value-row,.attribute-item{display:flex;align-items:center;justify-content:space-between;gap:10px;min-width:0;padding-bottom:6px;border-bottom:1px dashed rgba(148,163,184,.18);font-size:12px}
.field-value-row:last-child,.attribute-item:last-child{padding-bottom:0;border-bottom:0}
.field-value-row span,.attribute-item span{flex:none;color:#64748b}
.field-value-row strong,.attribute-item strong{min-width:0;color:#0f172a;font-weight:600;text-align:right;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.attribute-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:6px 12px}
.impact-summary-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px}
.impact-summary-item{display:flex;align-items:center;justify-content:space-between;gap:8px;padding:8px 10px;border:1px solid rgba(148,163,184,.16);border-radius:10px;background:#fff;color:#64748b;font-size:12px}
.impact-summary-item strong{font-size:18px;color:#0f172a}
.impact-column-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}
.impact-list-panel{display:flex;flex-direction:column;gap:6px;min-width:0;padding:8px 10px;border:1px solid rgba(148,163,184,.16);border-radius:10px;background:#fff}
.impact-list-panel>strong{font-size:12px;color:#0f172a}
.impact-node-row{display:flex;flex-direction:column;gap:2px;min-width:0;padding:6px 0;border:0;border-bottom:1px dashed rgba(148,163,184,.18);background:transparent;text-align:left;cursor:pointer}
.impact-node-row:last-of-type{border-bottom:0}
.impact-node-row span{max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#245bdb;font-size:12px;font-weight:700}
.impact-node-row small{max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#64748b;font-size:11px}
.detail-table{margin-top:0}
.preview-summary-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px;margin-bottom:10px}
.preview-summary-card{border:1px solid rgba(148,163,184,.18);border-radius:10px;background:#fff;padding:10px 12px;display:flex;align-items:center;justify-content:space-between;color:#475569;font-size:13px}
.preview-summary-card strong{font-size:20px;color:#0f172a}
.preview-summary-card.success{background:#f7fefb}.preview-summary-card.warning{background:#fffaf0}.preview-summary-card.danger{background:#fff7f7}
.preview-summary-card--action{appearance:none;font:inherit;cursor:pointer;text-align:left}
.preview-summary-card--action.active{border-color:rgba(51,112,255,.34);box-shadow:0 0 0 2px rgba(51,112,255,.08);color:#245bdb}
.preview-summary-card--action.active strong{color:#245bdb}
.preview-summary-card--action:hover{border-color:rgba(51,112,255,.28)}
.sync-record-summary-grid{grid-template-columns:repeat(4,minmax(0,1fr))}
.sync-record-batch-head{display:flex;align-items:center;gap:8px;margin:0 0 8px;color:#64748b;font-size:12px}
.sync-record-table .stack-cell{gap:3px}
.sync-record-subject{min-width:0;display:flex;flex-direction:column;gap:2px}
.sync-record-subject strong{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#0f172a;font-size:13px}
.sync-record-subject span{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#64748b;font-size:12px}
.preview-table{margin-top:4px}
@media (max-width: 760px){.bulk-import-template-picker{align-items:flex-start;flex-direction:column;padding:9px 11px}.bulk-import-template-picker :deep(.el-select){width:100%!important}.bulk-import-template-picker small{white-space:normal}}
@media (max-width: 1100px){.audit-grid,.platform-setting-strip,.resource-usage-grid,.phase-one-guide-grid,.phase-one-coverage-grid,.phase-one-action-grid,.sync-joint-grid,.sync-opsany-layout,.overview-entry-grid,.cmdb-overview-grid,.governance-grid,.model-grid,.model-detail-layout,.threshold-grid,.resource-tree-grid,.repository-layout,.opsany-view-layout,.ledger-host-layout,.opsany-rack-card,.detail-grid,.opsany-model-catalog-layout--with-tree,.topology-knowledge-layout{grid-template-columns:1fr}.section-toolbar,.workbench-toolbar{align-items:flex-start;flex-direction:column}.workbench-toolbar-left{flex-wrap:wrap}.sync-account-shell--side,.knowledge-relation-panel{position:static}.opsany-view-tree{border-right:0;border-bottom:1px solid #e5e7eb;min-height:auto;padding-right:0;padding-bottom:12px}.opsany-rack-stage{grid-template-columns:repeat(auto-fill,minmax(280px,1fr))}}
@media (max-width: 1100px){.governance-tree-panel{min-height:auto;border-right:0;border-bottom:1px solid rgba(148,163,184,.2);padding-right:0;padding-bottom:12px}.governance-tree-panel .opsany-view-tree-list{max-height:280px}.cmdb-page--governance .workbench-card-actions{justify-content:flex-start}.overview-governance-panel,.overview-cost-panel{grid-column:1}}
@media (max-width: 760px){.ci-form-model-summary{grid-template-columns:1fr}.ci-form-model-summary-tags{justify-content:flex-start}.cmdb-form-section-title{align-items:flex-start;flex-direction:column;gap:4px}.cmdb-form-section-title::after{width:100%;flex:none}.cmdb-form-section-title small{white-space:normal}}
@media (max-width: 760px){.cmdb-form-grid,.preview-summary-grid,.request-summary-grid,.request-detail-statusbar,.resource-tree-summary-grid,.search-summary-grid,.repository-summary-grid,.view-summary-grid,.island-summary-grid,.authorization-summary-grid,.threshold-summary-grid,.governance-filter-grid,.collection-source-grid,.tag-summary-grid,.audit-summary-grid,.audit-raw-grid,.attribute-grid,.compact-stack,.impact-summary-grid,.impact-column-grid,.quality-status-grid,.model-detail-stat-grid,.opsany-app-grid,.opsany-model-card-grid,.opsany-physical-stats,.topology-summary-grid{grid-template-columns:1fr}.cost-detail-summary{align-items:flex-start;flex-wrap:wrap}.cost-detail-value--primary{margin-left:0}.cmdb-form-grid :deep(.span-2){grid-column:span 1}.opsany-page-head{align-items:flex-start;flex-direction:column;gap:6px}.cmdb-content-card--opsany .view-mode-bar,.opsany-model-tabs{gap:16px}.opsany-model-toolbar{align-items:flex-start;flex-direction:column}.opsany-model-toolbar-left{width:100%}.opsany-rack-visual{width:100%;max-width:212px}.opsany-rack-shell{height:560px}.opsany-rack-meta{max-width:100%}}
@media (max-width: 760px){.governance-category-grid{grid-template-columns:1fr}.governance-category-head{align-items:flex-start}.governance-panel-head{align-items:flex-start;flex-direction:column}.governance-detail-title{align-items:flex-start;flex-direction:column}.governance-panel-actions{justify-content:flex-start}}
.resource-name-link{width:fit-content;max-width:100%;padding:0;border:0;background:transparent;color:#0f172a;font:inherit;font-weight:700;line-height:1.4;text-align:left;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;cursor:pointer}.resource-name-link:hover{color:#245bdb;text-decoration:underline}
.resource-name-link--primary{color:#245bdb}.resource-name-link--primary:hover{color:#1d4ed8}
</style>
