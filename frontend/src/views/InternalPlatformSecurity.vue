<template>
  <div class="security-page workbench-page-shell fade-in">
    <section class="hero panel">
      <div class="hero-title-row">
        <span class="header-icon"><el-icon><Lock /></el-icon></span>
        <h2>内部平台安全</h2>
        <p class="page-inline-desc">统一治理服务器病毒、勒索脚本与软件版本漏洞，持续覆盖阿里云和机房资产</p>
      </div>
    </section>

    <div class="audit-grid security-stat-grid">
      <button type="button" class="audit-card audit-card--inline audit-card--action" @click="openAssetView()">
        <span class="stat-copy"><span class="stat-label">纳管主机</span><small class="stat-foot">{{ summary.agent_online_count }} 台防护中</small></span>
        <strong class="stat-value">{{ summary.asset_total }}</strong>
      </button>
      <button type="button" class="audit-card audit-card--inline audit-card--danger audit-card--action" @click="openThreatView()">
        <span class="stat-copy"><span class="stat-label">未处置威胁</span><small class="stat-foot">严重 {{ summary.critical_threat_count }} 项</small></span>
        <strong class="stat-value">{{ summary.open_threat_count }}</strong>
      </button>
      <button type="button" class="audit-card audit-card--inline audit-card--warning audit-card--action" @click="openSoftwareView('HIGH')">
        <span class="stat-copy"><span class="stat-label">P0 / P1 软件风险</span><small class="stat-foot">P0 {{ summary.software_p0_count }} 项</small></span>
        <strong class="stat-value">{{ summary.software_high_risk_count }}</strong>
      </button>
      <button type="button" class="audit-card audit-card--inline audit-card--success audit-card--action" @click="openAssetView('online')">
        <span class="stat-copy"><span class="stat-label">Agent 在线率</span><small class="stat-foot">{{ summary.asset_risk_count }} 台存在风险</small></span>
        <strong class="stat-value">{{ protectionRate }}%</strong>
      </button>
    </div>

    <div class="runtime-strip">
      <span class="runtime-main"><el-icon><CircleCheck /></el-icon>最近扫描 {{ formatDateTime(summary.last_scan_at) }}</span>
      <span class="runtime-divider" />
      <span class="runtime-label">资产接入</span>
      <span v-for="connector in connectors" :key="connector.value" class="connector-chip" :class="`is-${connector.status}`">
        <i />{{ connector.label }} · {{ connectorStatusLabel(connector) }}
      </span>
    </div>

    <div class="neo-tabs theme-blue security-tabs" role="tablist" aria-label="内部平台安全工作台">
      <button v-for="tab in tabs" :key="tab.key" type="button" class="neo-tab-btn" :class="{ active: activeTab === tab.key }" @click="switchTab(tab.key)">
        <el-icon><component :is="tab.icon" /></el-icon>
        {{ tab.label }}
      </button>
    </div>

    <section v-if="activeTab === 'overview'" class="workbench-card content-card overview-card" v-loading="loading">
      <div class="section-toolbar">
        <div class="toolbar-head"><span class="toolbar-title">安全态势总览</span><span class="toolbar-desc">优先处理主机入侵事件，再推进高风险软件升级</span></div>
        <el-button class="filter-refresh-btn" :loading="loading" @click="reloadAll"><el-icon><Refresh /></el-icon>刷新</el-button>
      </div>
      <div class="overview-grid">
        <section class="overview-panel threat-panel">
          <div class="panel-heading"><span><el-icon><WarningFilled /></el-icon>高优先级威胁</span><button type="button" @click="openThreatView()">查看全部</button></div>
          <div v-if="topThreats.length" class="overview-list">
            <button v-for="item in topThreats" :key="item.id" type="button" class="overview-row" @click="openThreatDetail(item)">
              <span class="risk-mark" :class="`is-${item.severity}`" />
              <span class="overview-row-main"><strong>{{ item.title }}</strong><small>{{ item.asset_name }} · {{ item.asset_ip || '-' }} · {{ formatRelativeTime(item.detected_at) }}</small></span>
              <el-tag size="small" effect="light" :type="severityTagType(item.severity)">{{ item.severity_display }}</el-tag>
            </button>
          </div>
          <el-empty v-else description="暂无未处置威胁" :image-size="72" />
        </section>
        <section class="overview-panel software-panel">
          <div class="panel-heading"><span><el-icon><Box /></el-icon>高风险软件版本</span><button type="button" @click="openSoftwareView('HIGH')">查看全部</button></div>
          <div v-if="topSoftware.length" class="software-risk-list">
            <button v-for="item in topSoftware" :key="item.id" type="button" class="software-risk-row" @click="openSoftwareDetail(item)">
              <el-tag size="small" effect="light" :type="priorityTagType(item.priority)">{{ item.priority }}</el-tag>
              <span><strong>{{ item.software_name }}</strong><small>{{ item.current_version || '未登记' }} → {{ item.latest_version || '待确认' }}</small></span>
              <em>{{ item.plan_time || '待排期' }}</em>
            </button>
          </div>
        </section>
      </div>
      <div class="governance-path">
        <div><span class="path-index">1</span><strong>发现</strong><small>Agent、审计日志和云 API 汇聚威胁</small></div>
        <i />
        <div><span class="path-index">2</span><strong>阻断</strong><small>隔离主机、终止进程、保全样本</small></div>
        <i />
        <div><span class="path-index">3</span><strong>修复</strong><small>清理持久化、轮换凭据、补齐基线</small></div>
        <i />
        <div><span class="path-index">4</span><strong>复核</strong><small>关联工单与证据，持续跟踪版本治理</small></div>
      </div>
    </section>

    <section v-else-if="activeTab === 'host'" class="workbench-card content-card" v-loading="loading">
      <div class="section-toolbar">
        <div class="toolbar-head">
          <span class="toolbar-title">主机安全</span>
          <span class="toolbar-desc">检测恶意文件、勒索行为、可疑脚本、WebShell、挖矿与暴力破解</span>
        </div>
        <div class="host-toolbar-actions">
          <button type="button" class="signal-chip is-danger" @click="showProtectionGaps"><span>防护缺口</span><strong>{{ summary.protection_gap_count }}</strong></button>
          <button type="button" class="signal-chip is-warning" @click="showUnassignedThreats"><span>待认领</span><strong>{{ summary.unassigned_threat_count }}</strong></button>
          <div class="view-switch">
            <button type="button" :class="{ active: hostView === 'threats' }" @click="switchHostView('threats')">威胁事件</button>
            <button type="button" :class="{ active: hostView === 'assets' }" @click="switchHostView('assets')">资产防护</button>
          </div>
        </div>
      </div>

      <div v-if="hostView === 'threats'" class="workbench-toolbar workbench-toolbar--history filter-bar">
        <div class="workbench-toolbar-left">
          <el-select v-model="threatFilters.source" clearable placeholder="资产来源" style="width: 118px" @change="fetchThreats"><el-option v-for="item in sourceOptions" :key="item.value" :label="item.label" :value="item.value" /></el-select>
          <el-select v-model="threatFilters.threat_type" clearable placeholder="威胁类型" style="width: 118px" @change="fetchThreats"><el-option v-for="item in threatTypeOptions" :key="item.value" :label="item.label" :value="item.value" /></el-select>
          <el-select v-model="threatFilters.severity" clearable placeholder="风险等级" style="width: 108px" @change="fetchThreats"><el-option label="严重 / 高" value="high_risk" /><el-option label="严重" value="critical" /><el-option label="高" value="high" /><el-option label="中" value="medium" /><el-option label="低" value="low" /></el-select>
          <el-select v-model="threatFilters.status" clearable placeholder="处理状态" style="width: 108px" @change="fetchThreats"><el-option label="全部未处置" value="open_all" /><el-option v-for="item in threatStatusOptions" :key="item.value" :label="item.label" :value="item.value" /></el-select>
          <el-select v-model="threatFilters.owner_status" clearable placeholder="责任状态" style="width: 108px" @change="fetchThreats"><el-option label="待认领" value="unassigned" /><el-option label="已认领" value="assigned" /></el-select>
          <el-input v-model="threatFilters.keyword" clearable placeholder="搜索主机、IP、文件或命令" style="width: 205px" @keyup.enter="fetchThreats" @clear="fetchThreats" />
          <el-tag v-if="assetThreatScope" closable effect="plain" type="info" @close="clearAssetThreatScope">资产：{{ assetThreatScope }}</el-tag>
        </div>
        <div class="workbench-toolbar-right"><el-button class="filter-refresh-btn" @click="resetThreatFilters">重置</el-button><el-button class="filter-refresh-btn" @click="fetchThreats"><el-icon><Refresh /></el-icon>刷新</el-button></div>
      </div>
      <el-table v-if="hostView === 'threats'" :data="paginatedThreats" class="security-table threat-table" size="small" empty-text="暂无威胁事件">
        <el-table-column label="威胁事件" min-width="300"><template #default="{ row }"><div class="primary-cell"><div><span class="risk-mark" :class="`is-${row.severity}`" /><strong>{{ row.title }}</strong></div><span>{{ row.threat_type_display }} · {{ row.process_path || '未记录路径' }}</span></div></template></el-table-column>
        <el-table-column label="资产" min-width="190"><template #default="{ row }"><div class="stack-cell"><strong>{{ row.asset_name || '未知资产' }}</strong><span>{{ row.asset_ip || '-' }} · {{ row.asset_source_display }}</span></div></template></el-table-column>
        <el-table-column label="风险" width="82"><template #default="{ row }"><el-tag size="small" effect="light" :type="severityTagType(row.severity)">{{ row.severity_display }}</el-tag></template></el-table-column>
        <el-table-column label="状态" width="96"><template #default="{ row }"><el-tag size="small" effect="light" :type="threatStatusTagType(row.status)">{{ row.status_display }}</el-tag></template></el-table-column>
        <el-table-column label="发现时间" width="164"><template #default="{ row }">{{ formatDateTime(row.detected_at) }}</template></el-table-column>
        <el-table-column label="责任人" width="110"><template #default="{ row }"><span :class="{ 'owner-unassigned': !row.owner }">{{ row.owner || '待认领' }}</span></template></el-table-column>
        <el-table-column label="操作" width="180" fixed="right"><template #default="{ row }"><el-button link type="primary" @click="openThreatDetail(row)">详情</el-button><el-button v-if="canManage && canIsolate(row)" link type="warning" @click="openThreatAction(row, 'isolate')">隔离</el-button><el-button v-if="canManage && isThreatOpen(row)" link type="success" @click="openThreatAction(row, 'resolve')">解决</el-button></template></el-table-column>
      </el-table>
      <div v-if="hostView === 'threats'" class="table-footer">
        <span>共 {{ threats.length }} 起事件</span>
        <el-pagination :current-page="threatPage" :page-size="threatPageSize" :page-sizes="[10, 20, 50]" layout="sizes, prev, pager, next" :total="threats.length" small @current-change="handleThreatPageChange" @size-change="handleThreatPageSizeChange" />
      </div>

      <div v-else class="workbench-toolbar workbench-toolbar--history filter-bar">
        <div class="workbench-toolbar-left">
          <el-select v-model="assetFilters.source" clearable placeholder="资产来源" style="width: 122px" @change="fetchAssets"><el-option v-for="item in sourceOptions" :key="item.value" :label="item.label" :value="item.value" /></el-select>
          <el-select v-model="assetFilters.agent_status" clearable placeholder="Agent 状态" style="width: 118px" @change="fetchAssets"><el-option label="防护中" value="online" /><el-option label="离线" value="offline" /><el-option label="待接入" value="pending" /></el-select>
          <el-select v-model="assetFilters.protection_status" clearable placeholder="防护状态" style="width: 118px" @change="fetchAssets"><el-option label="全部防护缺口" value="gap" /><el-option label="防护正常" value="healthy" /></el-select>
          <el-select v-model="assetFilters.risk_level" clearable placeholder="风险状态" style="width: 120px" @change="fetchAssets"><el-option label="全部风险主机" value="at_risk" /><el-option label="严重" value="critical" /><el-option label="高" value="high" /><el-option label="中" value="medium" /><el-option label="无风险" value="clean" /></el-select>
          <el-input v-model="assetFilters.keyword" clearable placeholder="搜索主机、IP、系统或 OS" style="width: 230px" @keyup.enter="fetchAssets" @clear="fetchAssets" />
        </div>
        <div class="workbench-toolbar-right"><el-button class="filter-refresh-btn" @click="resetAssetFilters">重置</el-button><el-button class="filter-refresh-btn" @click="fetchAssets"><el-icon><Refresh /></el-icon>刷新</el-button></div>
      </div>
      <el-table v-if="hostView === 'assets'" :data="assets" class="security-table" size="small" empty-text="暂无安全资产">
        <el-table-column label="主机" min-width="220"><template #default="{ row }"><div class="stack-cell"><strong>{{ row.name }}</strong><span>{{ row.ip_address || '-' }} · {{ row.os_name || '未知 OS' }}</span></div></template></el-table-column>
        <el-table-column label="来源" width="122"><template #default="{ row }"><el-tag size="small" effect="plain">{{ row.source_display }}</el-tag></template></el-table-column>
        <el-table-column label="环境 / 系统" min-width="160"><template #default="{ row }"><div class="stack-cell"><strong>{{ row.environment || '-' }}</strong><span>{{ row.business_line || '未绑定系统' }}</span></div></template></el-table-column>
        <el-table-column label="Agent 防护" width="138"><template #default="{ row }"><div class="protection-cell"><el-tag size="small" effect="light" :type="protectionTagType(row.protection_status)">{{ row.protection_status_display }}</el-tag><small>{{ formatRelativeTime(row.last_seen_at) }}</small></div></template></el-table-column>
        <el-table-column label="风险状态" width="105"><template #default="{ row }"><el-tag size="small" effect="light" :type="assetRiskTagType(row.risk_level)">{{ row.risk_level_display }}</el-tag></template></el-table-column>
        <el-table-column label="未处置威胁" width="110"><template #default="{ row }"><button type="button" class="table-link" @click="openAssetThreats(row)">{{ row.open_threat_count }} 项</button></template></el-table-column>
        <el-table-column label="最近扫描" width="164"><template #default="{ row }">{{ formatDateTime(row.last_scan_at) }}</template></el-table-column>
        <el-table-column label="操作" width="80" fixed="right"><template #default="{ row }"><el-button link type="primary" @click="openAssetDetail(row)">详情</el-button></template></el-table-column>
      </el-table>
    </section>

    <section v-else class="workbench-card content-card" v-loading="loading">
      <div class="section-toolbar"><div class="toolbar-head"><span class="toolbar-title">软件版本安全</span><span class="toolbar-desc">来自《中间件.xlsx》的当前版本、已知风险、规避措施与目标版本台账</span></div><el-tag effect="light" type="warning">共 {{ summary.software_total }} 项 · 已排期 {{ summary.software_planned_count }} 项</el-tag></div>
      <div class="workbench-toolbar workbench-toolbar--history filter-bar">
        <div class="workbench-toolbar-left">
          <el-select v-model="softwareFilters.deployment_type" clearable placeholder="部署形态" style="width: 116px" @change="fetchSoftware"><el-option label="自建" value="self_hosted" /><el-option label="阿里云" value="aliyun" /><el-option label="基础镜像" value="base_image" /></el-select>
          <el-select v-model="softwareFilters.priority" clearable placeholder="优先级" style="width: 104px" @change="fetchSoftware"><el-option label="P0 / P1" value="HIGH" /><el-option v-for="level in ['P0', 'P1', 'P2', 'P3']" :key="level" :label="level" :value="level" /></el-select>
          <el-select v-model="softwareFilters.upgrade_necessity" clearable placeholder="升级必要性" style="width: 126px" @change="fetchSoftware"><el-option label="必要" value="required" /><el-option label="建议" value="recommended" /><el-option label="暂不必要" value="not_needed" /></el-select>
          <el-select v-model="softwareFilters.status" clearable placeholder="治理状态" style="width: 112px" @change="fetchSoftware"><el-option v-for="item in softwareStatusOptions" :key="item.value" :label="item.label" :value="item.value" /></el-select>
          <el-input v-model="softwareFilters.keyword" clearable placeholder="搜索软件、当前版本、目标版本或风险" style="width: 285px" @keyup.enter="fetchSoftware" @clear="fetchSoftware" />
        </div>
        <div class="workbench-toolbar-right"><el-button class="filter-refresh-btn" @click="resetSoftwareFilters">重置</el-button><el-button class="filter-refresh-btn" @click="fetchSoftware"><el-icon><Refresh /></el-icon>刷新</el-button></div>
      </div>
      <el-table :data="paginatedSoftwareItems" class="security-table software-table" size="small" empty-text="暂无软件版本项">
        <el-table-column label="软件 / 部署" min-width="170"><template #default="{ row }"><div class="stack-cell"><div class="software-name-row"><el-tag size="small" effect="light" :type="priorityTagType(row.priority)">{{ row.priority }}</el-tag><strong>{{ row.software_name }}</strong></div><span>{{ row.deployment_type_display }}</span></div></template></el-table-column>
        <el-table-column label="版本差距" min-width="210"><template #default="{ row }"><div class="version-cell"><span><small>当前</small>{{ row.current_version || '未登记' }}</span><i>→</i><span><small>建议</small>{{ row.latest_version || '待确认' }}</span></div><div v-if="row.other_versions" class="other-version">其他：{{ row.other_versions }}</div></template></el-table-column>
        <el-table-column label="版本风险" min-width="300"><template #default="{ row }"><span class="line-clamp">{{ row.risk_summary || '托管服务无固定版本风险' }}</span></template></el-table-column>
        <el-table-column label="必要性" width="96"><template #default="{ row }"><el-tag size="small" effect="light" :type="necessityTagType(row.upgrade_necessity)">{{ row.upgrade_necessity_display }}</el-tag></template></el-table-column>
        <el-table-column label="治理状态" width="102"><template #default="{ row }"><el-tag size="small" effect="light" :type="softwareStatusTagType(row.status)">{{ row.status_display }}</el-tag></template></el-table-column>
        <el-table-column label="计划" width="118"><template #default="{ row }">{{ row.plan_time || '待排期' }}</template></el-table-column>
        <el-table-column label="操作" width="138" fixed="right"><template #default="{ row }"><el-button link type="primary" @click="openSoftwareDetail(row)">详情</el-button><el-button v-if="canManage" link type="warning" @click="openSoftwareGovernance(row)">更新</el-button></template></el-table-column>
      </el-table>
      <div class="table-footer">
        <span>共 {{ softwareItems.length }} 项</span>
        <el-pagination :current-page="softwarePage" :page-size="softwarePageSize" :page-sizes="[10, 20, 50]" layout="sizes, prev, pager, next" :total="softwareItems.length" small @current-change="handleSoftwarePageChange" @size-change="handleSoftwarePageSizeChange" />
      </div>
    </section>

    <el-drawer v-model="assetDetailVisible" title="主机防护详情" size="600px" append-to-body>
      <template v-if="selectedAsset">
        <div class="drawer-tags"><el-tag effect="plain">{{ selectedAsset.source_display }}</el-tag><el-tag :type="protectionTagType(selectedAsset.protection_status)">{{ selectedAsset.protection_status_display }}</el-tag><el-tag :type="assetRiskTagType(selectedAsset.risk_level)">{{ selectedAsset.risk_level_display }}</el-tag></div>
        <h3 class="drawer-title">{{ selectedAsset.name }}</h3>
        <div class="detail-summary-grid asset-summary-grid">
          <div><span>IP 地址</span><strong>{{ selectedAsset.ip_address || '-' }}</strong><small>{{ selectedAsset.source_id || '未记录来源 ID' }}</small></div>
          <div><span>操作系统</span><strong>{{ selectedAsset.os_name || '未知 OS' }}</strong><small>{{ selectedAsset.tags?.join(' · ') || '暂无标签' }}</small></div>
          <div><span>环境</span><strong>{{ selectedAsset.environment || '-' }}</strong><small>{{ selectedAsset.business_line || '未绑定业务系统' }}</small></div>
          <div><span>威胁闭环</span><strong>{{ selectedAsset.open_threat_count }} 项未处置</strong><small>累计 {{ selectedAsset.threat_count }} 项 · 已解决 {{ selectedAsset.resolved_threat_count }} 项</small></div>
        </div>
        <section class="detail-callout" :class="selectedAsset.protection_status === 'healthy' ? 'detail-callout--success' : 'detail-callout--danger'">
          <span>Agent 防护状态</span>
          <p>{{ selectedAsset.protection_status === 'healthy' ? 'Agent 心跳正常，主机处于持续防护范围。' : '当前存在 Agent 离线、待接入或心跳超时，请优先恢复安全数据上报。' }}</p>
          <div class="protection-meta"><small>最近心跳 {{ formatDateTime(selectedAsset.last_seen_at) }}</small><small>最近扫描 {{ formatDateTime(selectedAsset.last_scan_at) }}</small></div>
        </section>
        <section class="detail-section asset-threat-section" v-loading="assetThreatsLoading">
          <div class="detail-section-title detail-section-title--split"><span>关联威胁</span><small>{{ assetThreats.length }} 起</small></div>
          <div v-if="assetThreats.length" class="asset-threat-list">
            <button v-for="item in assetThreats" :key="item.id" type="button" @click="openThreatFromAsset(item)"><span class="risk-mark" :class="`is-${item.severity}`" /><span><strong>{{ item.title }}</strong><small>{{ item.status_display }} · {{ formatRelativeTime(item.detected_at) }}</small></span><el-tag size="small" effect="light" :type="severityTagType(item.severity)">{{ item.severity_display }}</el-tag></button>
          </div>
          <el-empty v-else description="暂无关联威胁" :image-size="64" />
        </section>
      </template>
    </el-drawer>

    <el-drawer v-model="threatDetailVisible" title="威胁事件详情" size="600px" append-to-body>
      <template v-if="selectedThreat">
        <div class="drawer-tags"><el-tag :type="severityTagType(selectedThreat.severity)">{{ selectedThreat.severity_display }}</el-tag><el-tag :type="threatStatusTagType(selectedThreat.status)">{{ selectedThreat.status_display }}</el-tag><el-tag effect="plain">{{ selectedThreat.threat_type_display }}</el-tag></div>
        <h3 class="drawer-title">{{ selectedThreat.title }}</h3>
        <div class="detail-summary-grid">
          <div><span>受影响资产</span><strong>{{ selectedThreat.asset_name }}</strong><small>{{ selectedThreat.asset_ip || '-' }}</small></div>
          <div><span>资产来源</span><strong>{{ selectedThreat.asset_source_display }}</strong><small>{{ selectedThreat.source }}</small></div>
          <div><span>发现时间</span><strong>{{ formatDateTime(selectedThreat.detected_at) }}</strong><small>{{ selectedThreat.owner || '待认领' }}</small></div>
          <div><span>关联工单</span><strong>{{ selectedThreat.ticket_ref || '暂未关联' }}</strong><small>处置证据跟踪</small></div>
        </div>
        <section class="detail-section">
          <div class="detail-section-title">攻击证据</div>
          <dl class="detail-grid"><dt>文件 / 进程</dt><dd>{{ selectedThreat.process_path || '-' }}</dd><dt>命令行</dt><dd class="code-text">{{ selectedThreat.command_line || '-' }}</dd><dt>文件哈希</dt><dd class="code-text">{{ selectedThreat.file_hash || '-' }}</dd><dt>远端 IP</dt><dd>{{ selectedThreat.remote_ip || '-' }}</dd><dt>威胁说明</dt><dd>{{ selectedThreat.description || '-' }}</dd></dl>
        </section>
        <section class="detail-callout detail-callout--warning"><span>处置建议</span><p>{{ selectedThreat.suggestion || '请结合资产影响范围完成隔离、清理与复核。' }}</p></section>
        <section class="detail-section activity-section">
          <div class="detail-section-title detail-section-title--split"><span>处置记录</span><small>{{ selectedThreat.activities?.length || 0 }} 条</small></div>
          <div v-if="selectedThreat.activities?.length" class="activity-list"><div v-for="item in selectedThreat.activities" :key="item.id"><i /><span><strong>{{ item.action_display }}</strong><small>{{ item.actor || '系统' }} · {{ formatDateTime(item.created_at) }}</small><em>{{ item.from_status_display }} → {{ item.to_status_display }}</em><p>{{ item.message || '未填写处置说明' }}</p></span></div></div>
          <el-empty v-else description="暂无处置记录" :image-size="60" />
        </section>
        <div v-if="canManage" class="drawer-actions">
          <el-button v-if="canIsolate(selectedThreat)" type="warning" @click="openThreatAction(selectedThreat, 'isolate')">隔离主机</el-button>
          <el-button v-if="canMarkProcessing(selectedThreat)" type="primary" @click="openThreatAction(selectedThreat, 'progress')">{{ selectedThreat.status === 'isolated' ? '解除隔离并处理' : '标记处理中' }}</el-button>
          <el-button v-if="isThreatOpen(selectedThreat)" type="success" @click="openThreatAction(selectedThreat, 'resolve')">确认解决</el-button>
          <el-button v-if="isThreatOpen(selectedThreat)" type="danger" plain @click="openThreatAction(selectedThreat, 'ignore')">忽略误报</el-button>
          <el-button v-if="canReopen(selectedThreat)" type="primary" @click="openThreatAction(selectedThreat, 'reopen')">重新打开</el-button>
        </div>
      </template>
    </el-drawer>

    <el-dialog top="5vh" :close-on-click-modal="false" class="workbench-edit-dialog" v-model="threatActionVisible" :title="threatActionTitle" width="520px" append-to-body destroy-on-close>
      <el-form label-position="top" :model="threatActionForm" label-width="86px"><el-form-item label="责任人"><el-input v-model="threatActionForm.owner" maxlength="80" /></el-form-item><el-form-item label="关联工单"><el-input v-model="threatActionForm.ticket_ref" maxlength="160" /></el-form-item><el-form-item :label="threatActionReasonLabel" :required="threatActionNeedsReason"><el-input v-model="threatActionForm.message" type="textarea" :rows="3" maxlength="1000" show-word-limit :placeholder="threatActionPlaceholder" /></el-form-item></el-form>
      <template #footer><el-button @click="threatActionVisible = false">取消</el-button><el-button type="primary" :loading="saving" @click="submitThreatAction">确认</el-button></template>
    </el-dialog>

    <el-drawer v-model="softwareDetailVisible" title="软件版本安全详情" size="620px" append-to-body>
      <template v-if="selectedSoftware">
        <div class="drawer-tags"><el-tag :type="priorityTagType(selectedSoftware.priority)">{{ selectedSoftware.priority }}</el-tag><el-tag :type="necessityTagType(selectedSoftware.upgrade_necessity)">{{ selectedSoftware.upgrade_necessity_display }}</el-tag><el-tag effect="plain">{{ selectedSoftware.deployment_type_display }}</el-tag></div>
        <h3 class="drawer-title">{{ selectedSoftware.software_name }}</h3>
        <div class="version-compare"><div><span>当前版本</span><strong>{{ selectedSoftware.current_version || '未登记' }}</strong><small v-if="selectedSoftware.other_versions">其他环境：{{ selectedSoftware.other_versions }}</small></div><i>→</i><div class="target"><span>建议目标</span><strong>{{ selectedSoftware.latest_version || '待确认' }}</strong><small>{{ selectedSoftware.plan_time || '待排期' }}</small></div></div>
        <div class="software-detail-stack">
          <section class="detail-callout detail-callout--danger"><span>当前风险</span><p>{{ selectedSoftware.risk_summary || '暂未登记明确漏洞风险。' }}</p></section>
          <section class="detail-callout detail-callout--primary"><span>升级建议</span><p>{{ selectedSoftware.upgrade_advice || '待结合兼容性验证补充升级建议。' }}</p></section>
          <section class="detail-callout detail-callout--warning"><span>重大 Bug / 规避</span><p class="pre-line">{{ selectedSoftware.bug_advice || '暂无额外规避措施。' }}</p></section>
          <section class="detail-section owner-conclusion">
            <div class="detail-section-title">负责人结论</div>
            <dl class="detail-grid software-detail-grid"><dt>治理状态</dt><dd><el-tag size="small" effect="light" :type="softwareStatusTagType(selectedSoftware.status)">{{ selectedSoftware.status_display }}</el-tag></dd><dt>反馈说明</dt><dd>{{ selectedSoftware.owner_feedback || '暂未反馈' }}</dd></dl>
          </section>
        </div>
        <div v-if="canManage" class="drawer-actions"><el-button type="primary" @click="openSoftwareGovernance(selectedSoftware)">更新治理状态</el-button></div>
      </template>
    </el-drawer>

    <el-dialog top="5vh" :close-on-click-modal="false" class="workbench-edit-dialog" v-model="softwareGovernanceVisible" title="更新软件治理状态" width="540px" append-to-body destroy-on-close>
      <el-form label-position="top" :model="softwareGovernanceForm" label-width="92px"><el-form-item label="治理状态"><el-select v-model="softwareGovernanceForm.status" style="width:100%"><el-option v-for="item in softwareStatusOptions" :key="item.value" :label="item.label" :value="item.value" /></el-select></el-form-item><el-form-item label="升级计划"><el-input v-model="softwareGovernanceForm.plan_time" maxlength="80" placeholder="如 2026 Q4、暂不升级" /></el-form-item><el-form-item label="负责人反馈"><el-input v-model="softwareGovernanceForm.owner_feedback" type="textarea" :rows="4" maxlength="2000" show-word-limit /></el-form-item></el-form>
      <template #footer><el-button @click="softwareGovernanceVisible = false">取消</el-button><el-button type="primary" :loading="saving" @click="submitSoftwareGovernance">保存</el-button></template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Box, CircleCheck, DocumentChecked, Lock, Monitor, Refresh, WarningFilled } from '@element-plus/icons-vue'
import {
  getInternalPlatformAssets,
  getInternalPlatformPosture,
  getInternalPlatformSoftware,
  getInternalPlatformThreats,
  updateInternalPlatformSoftwareStatus,
  updateInternalPlatformThreat,
} from '@/api/modules/cloudsecurity'
import { useAuthStore } from '@/stores/auth'

const authStore = useAuthStore()
const canManage = computed(() => authStore.hasPermission('cloudsecurity.internal_platform.manage'))
const loading = ref(false)
const saving = ref(false)
const activeTab = ref('overview')
const hostView = ref('threats')
const posture = ref({})
const assets = ref([])
const threats = ref([])
const softwareItems = ref([])
const threatPage = ref(1)
const threatPageSize = ref(20)
const softwarePage = ref(1)
const softwarePageSize = ref(20)
const selectedAsset = ref(null)
const selectedThreat = ref(null)
const selectedSoftware = ref(null)
const assetThreats = ref([])
const assetThreatScope = ref('')
const assetDetailVisible = ref(false)
const assetThreatsLoading = ref(false)
const threatDetailVisible = ref(false)
const threatActionVisible = ref(false)
const softwareDetailVisible = ref(false)
const softwareGovernanceVisible = ref(false)
const threatAction = ref('resolve')

const tabs = [
  { key: 'overview', label: '安全态势', icon: DocumentChecked },
  { key: 'host', label: '主机安全', icon: Monitor },
  { key: 'software', label: '软件版本安全', icon: Box },
]
const threatStatusOptions = [
  { value: 'open', label: '待处理' }, { value: 'processing', label: '处理中' },
  { value: 'isolated', label: '已隔离' }, { value: 'resolved', label: '已解决' }, { value: 'ignored', label: '已忽略' },
]
const softwareStatusOptions = [
  { value: 'open', label: '待治理' }, { value: 'planned', label: '已排期' },
  { value: 'accepted', label: '风险接受' }, { value: 'done', label: '已完成' },
]
const summary = computed(() => posture.value.summary || {
  asset_total: 0, agent_online_count: 0, asset_risk_count: 0, open_threat_count: 0,
  critical_threat_count: 0, isolated_count: 0, protection_gap_count: 0,
  unassigned_threat_count: 0, software_total: 0,
  software_high_risk_count: 0, software_p0_count: 0, software_planned_count: 0,
})
const connectors = computed(() => posture.value.connectors || [])
const sourceOptions = computed(() => posture.value.asset_sources || [])
const threatTypeOptions = computed(() => posture.value.threat_types || [])
const topThreats = computed(() => posture.value.top_threats || [])
const topSoftware = computed(() => (posture.value.top_software || []).slice(0, 4))
const paginatedThreats = computed(() => {
  const start = (threatPage.value - 1) * threatPageSize.value
  return threats.value.slice(start, start + threatPageSize.value)
})
const paginatedSoftwareItems = computed(() => {
  const start = (softwarePage.value - 1) * softwarePageSize.value
  return softwareItems.value.slice(start, start + softwarePageSize.value)
})
const protectionRate = computed(() => summary.value.asset_total ? Math.round(summary.value.agent_online_count / summary.value.asset_total * 100) : 0)

const threatFilters = reactive({ source: '', threat_type: '', severity: '', status: 'open_all', owner_status: '', asset_id: '', keyword: '' })
const assetFilters = reactive({ source: '', agent_status: '', protection_status: '', risk_level: '', keyword: '' })
const softwareFilters = reactive({ deployment_type: '', priority: '', upgrade_necessity: '', status: '', keyword: '' })
const threatActionForm = reactive({ owner: '', ticket_ref: '', message: '' })
const softwareGovernanceForm = reactive({ status: 'open', plan_time: '', owner_feedback: '' })

const threatActionTitle = computed(() => ({ isolate: '隔离主机', progress: '标记处理中', resolve: '确认威胁已解决', ignore: '忽略误报', reopen: '重新打开威胁' }[threatAction.value] || '处置威胁'))
const threatActionNeedsReason = computed(() => ['ignore', 'reopen'].includes(threatAction.value))
const threatActionReasonLabel = computed(() => threatActionNeedsReason.value ? '操作原因' : '处置说明')
const threatActionPlaceholder = computed(() => ({
  ignore: '说明误报依据、授权来源或风险接受范围',
  reopen: '说明复核发现的新证据或重新打开原因',
}[threatAction.value] || '记录隔离范围、清理结果或复核证据'))

function cleanParams(source) {
  return Object.fromEntries(Object.entries(source).filter(([, value]) => value !== '' && value !== null && value !== undefined))
}

async function fetchPosture() {
  posture.value = await getInternalPlatformPosture()
}

async function fetchAssets() {
  assets.value = await getInternalPlatformAssets(cleanParams(assetFilters))
}

async function fetchThreats() {
  threats.value = await getInternalPlatformThreats(cleanParams(threatFilters))
  threatPage.value = 1
}

async function fetchSoftware() {
  softwareItems.value = await getInternalPlatformSoftware(cleanParams(softwareFilters))
  softwarePage.value = 1
}

async function reloadAll() {
  loading.value = true
  try {
    await Promise.all([fetchPosture(), fetchAssets(), fetchThreats(), fetchSoftware()])
  } finally {
    loading.value = false
  }
}

async function switchTab(tab) {
  activeTab.value = tab
  if (tab === 'host') await (hostView.value === 'threats' ? fetchThreats() : fetchAssets())
  if (tab === 'software') await fetchSoftware()
}

async function switchHostView(view) {
  hostView.value = view
  await (view === 'threats' ? fetchThreats() : fetchAssets())
}

function openThreatView() {
  activeTab.value = 'host'
  hostView.value = 'threats'
  Object.assign(threatFilters, { status: 'open_all', owner_status: '', asset_id: '' })
  assetThreatScope.value = ''
  void fetchThreats()
}

function openAssetView(agentStatus = '') {
  activeTab.value = 'host'
  hostView.value = 'assets'
  assetFilters.agent_status = agentStatus
  assetFilters.protection_status = ''
  void fetchAssets()
}

function openSoftwareView(priority = '') {
  activeTab.value = 'software'
  softwareFilters.priority = priority
  void fetchSoftware()
}

function openAssetThreats(asset) {
  hostView.value = 'threats'
  threatFilters.asset_id = asset.id
  threatFilters.keyword = ''
  threatFilters.status = 'open_all'
  assetThreatScope.value = asset.name
  void fetchThreats()
}

function clearAssetThreatScope() {
  threatFilters.asset_id = ''
  assetThreatScope.value = ''
  void fetchThreats()
}

function showProtectionGaps() {
  hostView.value = 'assets'
  Object.assign(assetFilters, { agent_status: '', protection_status: 'gap' })
  void fetchAssets()
}

function showUnassignedThreats() {
  hostView.value = 'threats'
  Object.assign(threatFilters, { status: 'open_all', owner_status: 'unassigned', asset_id: '' })
  assetThreatScope.value = ''
  void fetchThreats()
}

function resetThreatFilters() {
  Object.assign(threatFilters, { source: '', threat_type: '', severity: '', status: 'open_all', owner_status: '', asset_id: '', keyword: '' })
  assetThreatScope.value = ''
  void fetchThreats()
}

function resetAssetFilters() {
  Object.assign(assetFilters, { source: '', agent_status: '', protection_status: '', risk_level: '', keyword: '' })
  void fetchAssets()
}

function resetSoftwareFilters() {
  Object.assign(softwareFilters, { deployment_type: '', priority: '', upgrade_necessity: '', status: '', keyword: '' })
  void fetchSoftware()
}

function handleSoftwarePageChange(page) {
  softwarePage.value = page
}

function handleThreatPageChange(page) {
  threatPage.value = page
}

function handleThreatPageSizeChange(pageSize) {
  threatPageSize.value = pageSize
  threatPage.value = 1
}

async function openAssetDetail(item) {
  selectedAsset.value = item
  assetThreats.value = []
  assetDetailVisible.value = true
  assetThreatsLoading.value = true
  try {
    assetThreats.value = await getInternalPlatformThreats({ asset_id: item.id })
  } finally {
    assetThreatsLoading.value = false
  }
}

function openThreatFromAsset(item) {
  assetDetailVisible.value = false
  openThreatDetail(item)
}

function handleSoftwarePageSizeChange(pageSize) {
  softwarePageSize.value = pageSize
  softwarePage.value = 1
}

function openThreatDetail(item) {
  selectedThreat.value = item
  threatDetailVisible.value = true
}

function openThreatAction(item, action) {
  selectedThreat.value = item
  threatAction.value = action
  Object.assign(threatActionForm, { owner: item.owner || '', ticket_ref: item.ticket_ref || '', message: '' })
  threatActionVisible.value = true
}

async function submitThreatAction() {
  if (!selectedThreat.value) return
  if (threatActionNeedsReason.value && !threatActionForm.message.trim()) {
    ElMessage.warning('请填写操作原因')
    return
  }
  saving.value = true
  try {
    const updated = await updateInternalPlatformThreat(selectedThreat.value.id, { action: threatAction.value, ...threatActionForm })
    selectedThreat.value = updated
    threatActionVisible.value = false
    ElMessage.success('威胁处置状态已更新')
    await Promise.all([fetchPosture(), fetchThreats(), fetchAssets()])
  } finally {
    saving.value = false
  }
}

function openSoftwareDetail(item) {
  selectedSoftware.value = item
  softwareDetailVisible.value = true
}

function openSoftwareGovernance(item) {
  selectedSoftware.value = item
  Object.assign(softwareGovernanceForm, { status: item.status, plan_time: item.plan_time || '', owner_feedback: item.owner_feedback || '' })
  softwareGovernanceVisible.value = true
}

async function submitSoftwareGovernance() {
  if (!selectedSoftware.value) return
  saving.value = true
  try {
    const updated = await updateInternalPlatformSoftwareStatus(selectedSoftware.value.id, { ...softwareGovernanceForm })
    selectedSoftware.value = updated
    softwareGovernanceVisible.value = false
    ElMessage.success('软件治理状态已更新')
    await Promise.all([fetchPosture(), fetchSoftware()])
  } finally {
    saving.value = false
  }
}

function isThreatOpen(item) {
  return ['open', 'processing', 'isolated'].includes(item?.status)
}

function canIsolate(item) {
  return ['open', 'processing'].includes(item?.status)
}

function canMarkProcessing(item) {
  return ['open', 'isolated'].includes(item?.status)
}

function canReopen(item) {
  return ['resolved', 'ignored'].includes(item?.status)
}

function severityTagType(value) {
  return ({ critical: 'danger', high: 'danger', medium: 'warning', low: 'info' })[value] || 'info'
}

function threatStatusTagType(value) {
  return ({ open: 'danger', processing: 'warning', isolated: 'warning', resolved: 'success', ignored: 'info' })[value] || 'info'
}

function assetRiskTagType(value) {
  return ({ critical: 'danger', high: 'danger', medium: 'warning', low: 'info', clean: 'success' })[value] || 'info'
}

function protectionTagType(value) {
  return ({ healthy: 'success', stale: 'warning', offline: 'danger', pending: 'info' })[value] || 'info'
}

function priorityTagType(value) {
  return ({ P0: 'danger', P1: 'warning', P2: 'info', P3: 'success' })[value] || 'info'
}

function necessityTagType(value) {
  return ({ required: 'danger', recommended: 'warning', not_needed: 'success' })[value] || 'info'
}

function softwareStatusTagType(value) {
  return ({ open: 'danger', planned: 'warning', accepted: 'info', done: 'success' })[value] || 'info'
}

function connectorStatusLabel(item) {
  if (item.status === 'planned') return '待接入'
  if (item.status === 'connected') return `${item.asset_count} 台`
  return '未配置'
}

function formatDateTime(value) {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString('zh-CN', { hour12: false })
}

function formatRelativeTime(value) {
  if (!value) return '-'
  const minutes = Math.max(0, Math.floor((Date.now() - new Date(value).getTime()) / 60000))
  if (minutes < 60) return `${minutes} 分钟前`
  if (minutes < 1440) return `${Math.floor(minutes / 60)} 小时前`
  return `${Math.floor(minutes / 1440)} 天前`
}

onMounted(reloadAll)
</script>

<style scoped>
.security-page { display: flex; flex-direction: column; gap: 6px; }
.security-page > .security-tabs, .security-page > .content-card, .security-page > .runtime-strip { margin: 0; }
.panel { padding: 14px 16px; border: 1px solid rgba(15, 23, 42, .08); border-radius: 18px; background: linear-gradient(180deg, rgba(255,255,255,.98) 0%, rgba(250,252,255,.96) 100%); box-shadow: 0 8px 24px rgba(15,23,42,.04); }
.hero.panel { border-radius: 20px; border-color: rgba(36,91,219,.09); background: linear-gradient(135deg, #fbfdff 0%, #f7faff 52%, #f9fbfd 100%); }
.hero-title-row { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.hero h2 { margin: 0; color: #0f172a; font-size: 23px; }
.header-icon { width: 42px; height: 42px; display: inline-flex; align-items: center; justify-content: center; border: 1px solid rgba(36,91,219,.12); border-radius: 14px; background: linear-gradient(180deg,#f3f7ff 0%,#ebf2ff 100%); color: #245bdb; font-size: 20px; box-shadow: inset 0 1px 0 rgba(255,255,255,.8); }
.page-inline-desc { margin: 0; color: #475569; font-size: 13px; line-height: 1.45; transform: translateY(1px); }
.security-stat-grid { grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; margin: 0; }
.audit-card { min-height: 68px; display: grid; grid-template-columns: minmax(0, 1fr) auto; align-items: center; gap: 14px; padding: 12px 16px; border: 1px solid rgba(148,163,184,.17); border-radius: 14px; background: #fff; text-align: left; box-shadow: 0 8px 20px rgba(15,23,42,.035); }
button.audit-card { cursor: pointer; transition: border-color .18s ease, transform .18s ease, box-shadow .18s ease; }
button.audit-card:hover { border-color: rgba(51,112,255,.25); transform: translateY(-1px); box-shadow: 0 10px 24px rgba(51,112,255,.08); }
.audit-card--danger { background: linear-gradient(135deg, #fff 0%, #fff8f8 100%); }.audit-card--warning { background: linear-gradient(135deg, #fff 0%, #fffbf2 100%); }.audit-card--success { background: linear-gradient(135deg, #fff 0%, #f5fcf9 100%); }
.stat-copy { min-width: 0; display: flex; flex-direction: column; gap: 5px; }.stat-value { color: #172033; font-size: 24px; font-weight: 750; line-height: 1; text-align: right; white-space: nowrap; }.audit-card--danger .stat-value { color: #dc2626; }.audit-card--warning .stat-value { color: #d97706; }.audit-card--success .stat-value { color: #059669; }
.stat-label { overflow: hidden; color: #475569; font-size: 13px; font-weight: 650; text-overflow: ellipsis; white-space: nowrap; }.stat-foot { overflow: hidden; color: #94a3b8; font-size: 11px; font-weight: 400; text-overflow: ellipsis; white-space: nowrap; }
.runtime-strip { min-height: 34px; display: flex; align-items: center; gap: 10px; padding: 0 12px; overflow-x: auto; border: 1px solid rgba(148,163,184,.16); border-radius: 10px; background: #f8fafc; color: #64748b; font-size: 11px; white-space: nowrap; }
.runtime-main { display: inline-flex; align-items: center; gap: 6px; color: #0f766e; font-weight: 650; }.runtime-divider { width: 1px; height: 14px; background: rgba(148,163,184,.25); }.runtime-label { color: #94a3b8; }
.connector-chip { display: inline-flex; align-items: center; gap: 5px; }.connector-chip i { width: 6px; height: 6px; border-radius: 50%; background: #94a3b8; }.connector-chip.is-connected i { background: #10b981; box-shadow: 0 0 0 3px rgba(16,185,129,.08); }.connector-chip.is-planned i { background: #f59e0b; }
.security-tabs { width: 100%; display: flex; gap: 8px; padding: 3px; border: 1px solid rgba(148,163,184,.18); border-radius: 12px; background: rgba(255,255,255,.96); box-shadow: none; }
.security-tabs .neo-tab-btn { min-height: 38px; display: inline-flex; align-items: center; justify-content: center; gap: 6px; padding: 0 18px; border: 1px solid transparent; border-radius: 8px; background: transparent; color: #64748b; font-size: 13px; font-weight: 700; cursor: pointer; }
.security-tabs .neo-tab-btn.active { border-color: rgba(51,112,255,.14); background: #e8f0ff; color: #245bdb; box-shadow: inset 0 0 0 1px rgba(51,112,255,.04); }
.security-tabs .neo-tab-btn:focus, button.audit-card:focus, .view-switch button:focus, .signal-chip:focus, .panel-heading button:focus, .overview-row:focus, .software-risk-row:focus, .asset-threat-list button:focus, .table-link:focus { outline: none; }
.security-tabs .neo-tab-btn:focus-visible, button.audit-card:focus-visible, .view-switch button:focus-visible, .signal-chip:focus-visible, .panel-heading button:focus-visible, .overview-row:focus-visible, .software-risk-row:focus-visible, .asset-threat-list button:focus-visible, .table-link:focus-visible { outline: 2px solid rgba(36,91,219,.3); outline-offset: 2px; }
.content-card { padding: 14px 16px; border: 1px solid rgba(148,163,184,.16); border-radius: 14px; background: #fff; box-shadow: 0 10px 24px rgba(15,23,42,.035); }
.section-toolbar { min-height: 32px; display: flex; align-items: center; justify-content: space-between; gap: 12px; }.toolbar-head { display: inline-flex; align-items: baseline; gap: 8px; flex-wrap: wrap; }.toolbar-title { color: #172033; font-size: 14px; font-weight: 700; }.toolbar-desc { color: #94a3b8; font-size: 11px; }
.filter-refresh-btn { border-color: rgba(36,91,219,.12); color: #245bdb; }.filter-bar { margin: 8px 0; }.host-toolbar-actions { display: flex; align-items: center; gap: 6px; }.signal-chip { min-height: 28px; display: inline-flex; align-items: center; gap: 6px; padding: 0 9px; border: 1px solid rgba(148,163,184,.16); border-radius: 8px; background: #fff; color: #64748b; font-size: 11px; cursor: pointer; }.signal-chip strong { font-size: 12px; }.signal-chip.is-danger { border-color: rgba(239,68,68,.14); background: #fff8f8; color: #dc2626; }.signal-chip.is-warning { border-color: rgba(245,158,11,.16); background: #fffbf2; color: #d97706; }.view-switch { display: inline-flex; padding: 2px; border: 1px solid rgba(148,163,184,.18); border-radius: 9px; background: #f8fafc; }.view-switch button { min-height: 28px; padding: 0 11px; border: 0; border-radius: 7px; background: transparent; color: #64748b; font-size: 12px; cursor: pointer; }.view-switch button.active { background: #fff; color: #245bdb; box-shadow: 0 1px 4px rgba(15,23,42,.08); font-weight: 650; }
.overview-grid { display: grid; grid-template-columns: minmax(0, 1.2fr) minmax(360px, .8fr); gap: 10px; margin-top: 9px; }.overview-panel { min-width: 0; padding: 11px 13px; border: 1px solid rgba(148,163,184,.15); border-radius: 11px; background: #fbfcfe; }.panel-heading { display: flex; align-items: center; justify-content: space-between; gap: 10px; padding-bottom: 8px; border-bottom: 1px solid rgba(148,163,184,.12); }.panel-heading > span { display: inline-flex; align-items: center; gap: 7px; color: #334155; font-size: 13px; font-weight: 700; }.panel-heading button { padding: 0; border: 0; background: transparent; color: #3370ff; font-size: 11px; cursor: pointer; }
.overview-list, .software-risk-list { display: flex; flex-direction: column; }.overview-row, .software-risk-row { width: 100%; min-height: 58px; display: flex; align-items: center; gap: 9px; padding: 0; border: 0; border-bottom: 1px solid rgba(148,163,184,.1); background: transparent; color: inherit; text-align: left; cursor: pointer; }.overview-row:hover strong, .software-risk-row:hover strong { color: #245bdb; }.overview-row-main, .software-risk-row > span { min-width: 0; flex: 1; display: flex; flex-direction: column; gap: 3px; }.overview-row strong, .software-risk-row strong { overflow: hidden; color: #334155; font-size: 12px; text-overflow: ellipsis; white-space: nowrap; }.overview-row small, .software-risk-row small { overflow: hidden; color: #94a3b8; font-size: 11px; text-overflow: ellipsis; white-space: nowrap; }.software-risk-row em { color: #64748b; font-size: 11px; font-style: normal; }
.risk-mark { width: 8px; height: 8px; flex: 0 0 8px; border-radius: 50%; background: #94a3b8; }.risk-mark.is-critical { background: #dc2626; box-shadow: 0 0 0 4px rgba(220,38,38,.08); }.risk-mark.is-high { background: #f97316; }.risk-mark.is-medium { background: #f59e0b; }.risk-mark.is-low { background: #60a5fa; }
.governance-path { display: grid; grid-template-columns: minmax(0,1fr) 24px minmax(0,1fr) 24px minmax(0,1fr) 24px minmax(0,1fr); align-items: center; gap: 4px; margin-top: 10px; padding: 9px 12px; border: 1px solid rgba(51,112,255,.1); border-radius: 10px; background: #f7faff; }.governance-path > div { min-width: 0; display: grid; grid-template-columns: 22px auto; column-gap: 7px; }.governance-path strong { color: #334155; font-size: 12px; }.governance-path small { grid-column: 2; overflow: hidden; color: #94a3b8; font-size: 10px; text-overflow: ellipsis; white-space: nowrap; }.governance-path > i { height: 1px; background: rgba(51,112,255,.2); }.path-index { grid-row: 1 / 3; width: 22px; height: 22px; display: inline-flex; align-items: center; justify-content: center; border-radius: 7px; background: #e8f0ff; color: #245bdb; font-size: 11px; font-weight: 700; }
.security-table :deep(.el-table__header th) { background: #f8fafc; color: #64748b; font-size: 12px; }.security-table :deep(.el-table__cell) { padding: 9px 0; }.security-table :deep(.cell) { line-height: 1.4; }.security-table :deep(.el-table__body-wrapper) { overflow-y: visible; }.primary-cell, .stack-cell { min-width: 0; display: flex; flex-direction: column; gap: 4px; }.primary-cell > div, .software-name-row { min-width: 0; display: flex; align-items: center; gap: 7px; }.primary-cell strong, .stack-cell strong { overflow: hidden; color: #334155; font-size: 12px; text-overflow: ellipsis; white-space: nowrap; }.primary-cell span, .stack-cell span, .other-version { overflow: hidden; color: #94a3b8; font-size: 11px; text-overflow: ellipsis; white-space: nowrap; }.table-link { padding: 0; border: 0; background: transparent; color: #3370ff; font: inherit; cursor: pointer; }.owner-unassigned { color: #d97706; font-size: 11px; font-weight: 650; }.protection-cell { display: flex; align-items: flex-start; flex-direction: column; gap: 4px; }.protection-cell small { color: #94a3b8; font-size: 10px; }
.table-footer { min-height: 44px; display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 8px 72px 0 0; border-top: 1px solid rgba(148,163,184,.12); color: #94a3b8; font-size: 11px; }
.version-cell { display: grid; grid-template-columns: minmax(0,1fr) 18px minmax(0,1fr); align-items: center; gap: 5px; }.version-cell span { min-width: 0; display: flex; flex-direction: column; color: #334155; font-size: 11px; }.version-cell small { color: #94a3b8; font-size: 9px; }.version-cell i { color: #94a3b8; font-style: normal; }.line-clamp { display: -webkit-box; overflow: hidden; color: #475569; font-size: 11px; line-height: 1.55; -webkit-box-orient: vertical; -webkit-line-clamp: 2; }
.drawer-tags { display: flex; gap: 7px; flex-wrap: wrap; }.drawer-title { margin: 14px 0 18px; color: #172033; font-size: 18px; }.detail-summary-grid { display: grid; grid-template-columns: repeat(2, minmax(0,1fr)); gap: 8px; margin-bottom: 10px; }.detail-summary-grid > div { min-width: 0; display: flex; flex-direction: column; gap: 4px; padding: 11px 12px; border: 1px solid rgba(148,163,184,.14); border-radius: 10px; background: #f8fafc; }.detail-summary-grid span, .detail-summary-grid small { overflow: hidden; color: #94a3b8; font-size: 10px; text-overflow: ellipsis; white-space: nowrap; }.detail-summary-grid strong { overflow: hidden; color: #334155; font-size: 12px; text-overflow: ellipsis; white-space: nowrap; }.detail-section { padding: 13px 14px; border: 1px solid rgba(148,163,184,.15); border-radius: 11px; background: #fff; }.detail-section-title { margin-bottom: 11px; color: #334155; font-size: 12px; font-weight: 700; }.detail-section-title--split { display: flex; align-items: center; justify-content: space-between; gap: 12px; }.detail-section-title--split small { color: #94a3b8; font-size: 10px; font-weight: 500; }.detail-grid { display: grid; grid-template-columns: 104px minmax(0,1fr); gap: 11px 12px; margin: 0; font-size: 13px; }.detail-grid dt { color: #94a3b8; }.detail-grid dd { margin: 0; color: #334155; line-height: 1.6; overflow-wrap: anywhere; }.code-text { padding: 7px 9px; border-radius: 7px; background: #f8fafc; color: #475569 !important; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 11px; }.pre-line { white-space: pre-line; }.detail-callout { padding: 12px 14px; border: 1px solid rgba(148,163,184,.15); border-radius: 11px; background: #f8fafc; }.detail-callout span { color: #334155; font-size: 12px; font-weight: 700; }.detail-callout p { margin: 7px 0 0; color: #475569; font-size: 12px; line-height: 1.7; overflow-wrap: anywhere; }.detail-callout--primary { border-color: rgba(51,112,255,.14); background: #f4f8ff; }.detail-callout--success { border-color: rgba(16,185,129,.14); background: #f4fbf8; }.detail-callout--danger { border-color: rgba(239,68,68,.13); background: #fff7f7; }.detail-callout--warning { margin-top: 10px; border-color: rgba(245,158,11,.16); background: #fffbf2; }.protection-meta { display: flex; gap: 14px; margin-top: 8px; color: #94a3b8; }.asset-threat-section, .activity-section { margin-top: 10px; }.asset-threat-list { display: flex; flex-direction: column; }.asset-threat-list button { width: 100%; min-height: 54px; display: flex; align-items: center; gap: 9px; padding: 0; border: 0; border-bottom: 1px solid rgba(148,163,184,.1); background: transparent; text-align: left; cursor: pointer; }.asset-threat-list button > span:nth-child(2) { min-width: 0; flex: 1; display: flex; flex-direction: column; gap: 3px; }.asset-threat-list strong { overflow: hidden; color: #334155; font-size: 12px; text-overflow: ellipsis; white-space: nowrap; }.asset-threat-list small { color: #94a3b8; font-size: 10px; }.activity-list { display: flex; flex-direction: column; gap: 12px; }.activity-list > div { display: grid; grid-template-columns: 10px minmax(0,1fr); gap: 9px; }.activity-list > div > i { width: 8px; height: 8px; margin-top: 5px; border: 2px solid #fff; border-radius: 50%; background: #3370ff; box-shadow: 0 0 0 3px rgba(51,112,255,.12); }.activity-list > div > span { min-width: 0; display: grid; grid-template-columns: auto 1fr auto; align-items: baseline; gap: 4px 8px; }.activity-list strong { color: #334155; font-size: 12px; }.activity-list small, .activity-list em { color: #94a3b8; font-size: 10px; font-style: normal; }.activity-list em { text-align: right; }.activity-list p { grid-column: 1 / -1; margin: 2px 0 0; color: #64748b; font-size: 11px; line-height: 1.6; }.drawer-actions { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 18px; padding-top: 14px; border-top: 1px solid rgba(148,163,184,.16); }
.version-compare { display: grid; grid-template-columns: minmax(0,1fr) 30px minmax(0,1fr); align-items: stretch; gap: 8px; margin-bottom: 10px; }.version-compare > div { display: flex; flex-direction: column; gap: 5px; padding: 13px; border: 1px solid rgba(148,163,184,.16); border-radius: 10px; background: #f8fafc; }.version-compare > div.target { border-color: rgba(51,112,255,.16); background: #f4f8ff; }.version-compare > i { display: flex; align-items: center; justify-content: center; color: #94a3b8; font-style: normal; }.version-compare span, .version-compare small { color: #94a3b8; font-size: 11px; }.version-compare strong { color: #172033; font-size: 14px; }.software-detail-stack { display: flex; flex-direction: column; gap: 8px; }.software-detail-stack .detail-callout--warning { margin-top: 0; }.software-detail-grid { grid-template-columns: 88px minmax(0,1fr); }.owner-conclusion { margin-top: 2px; }
@media (max-width: 1000px) { .security-stat-grid { grid-template-columns: repeat(2, minmax(0,1fr)); }.overview-grid { grid-template-columns: 1fr; }.governance-path { grid-template-columns: repeat(2, minmax(0,1fr)); }.governance-path > i { display: none; } }
@media (max-width: 760px) { .page-inline-desc { display: none; }.security-stat-grid { grid-template-columns: 1fr; }.section-toolbar { align-items: flex-start; flex-direction: column; }.host-toolbar-actions { align-items: flex-start; flex-wrap: wrap; }.security-tabs { overflow-x: auto; }.security-tabs .neo-tab-btn { flex: 0 0 auto; }.runtime-strip { padding: 7px 10px; }.governance-path { grid-template-columns: 1fr; }.table-footer { align-items: flex-start; flex-direction: column; padding-right: 0; }.detail-summary-grid { grid-template-columns: 1fr; }.detail-grid { grid-template-columns: 86px minmax(0,1fr); }.activity-list > div > span { grid-template-columns: 1fr; }.activity-list em { text-align: left; } }
</style>
