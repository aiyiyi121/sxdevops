<template>
  <div class="fade-in aiops-config-page workbench-page-shell">
    <section class="hero panel">
      <div class="hero-copy">
        <div class="hero-title-row">
          <span class="hero-icon"><el-icon><ChatDotSquare /></el-icon></span>
          <h2>智能体配置</h2>
          <p class="page-inline-desc">统一管理智能助手的策略、问答类型、Skill、MCP 与模型提供商。</p>
        </div>
      </div>
    </section>

    <section class="tabs-card">
      <el-tabs v-model="activeTab" class="event-like-tabs">
        <el-tab-pane name="strategy">
          <template #label>
            <span class="tab-label"><el-icon><Setting /></el-icon>智能体策略</span>
          </template>
        </el-tab-pane>
        <el-tab-pane name="actions">
          <template #label>
            <span class="tab-label"><el-icon><Promotion /></el-icon>问答类型</span>
          </template>
        </el-tab-pane>
        <el-tab-pane name="skills">
          <template #label>
            <span class="tab-label"><el-icon><Tools /></el-icon>Skill</span>
          </template>
        </el-tab-pane>
        <el-tab-pane name="mcp">
          <template #label>
            <span class="tab-label"><el-icon><Connection /></el-icon>MCP</span>
          </template>
        </el-tab-pane>
        <el-tab-pane name="orchestration">
          <template #label>
            <span class="tab-label"><el-icon><Message /></el-icon>拓展功能-待实现</span>
          </template>
        </el-tab-pane>
        <el-tab-pane name="providers">
          <template #label>
            <span class="tab-label"><el-icon><Cpu /></el-icon>模型提供商</span>
          </template>
        </el-tab-pane>
      </el-tabs>
      <el-button size="small" :loading="loading.page" class="config-refresh-button" @click="refreshConfig">刷新</el-button>
    </section>

    <section class="panel">
      <template v-if="activeTab === 'strategy'">
        <AgentStrategyPanel
          :config="configForm" :capabilities="capabilityList"
          :provider="providers.find(item => item.id === defaultProviderId) || configuredDefaultProvider"
          :dirty="configDirty" :saving="saving.config" :loading="loading.page" :can-manage="canManageCapabilities"
          @save="saveConfig" @reset="resetConfigChanges" @providers="activeTab = 'providers'"
        />
      </template>

      <template v-else-if="activeTab === 'orchestration'">
        <div class="skill-summary-row">
          <div class="skill-summary-item">
            <span>协同任务</span>
            <strong>{{ a2aOverview.total }}</strong>
          </div>
          <div class="skill-summary-item">
            <span>待处理任务</span>
            <strong>{{ a2aOverview.queued }}</strong>
          </div>
          <div class="skill-summary-item">
            <span>Runbook 手册</span>
            <strong>{{ runbookOverview.total }}</strong>
          </div>
          <div class="skill-summary-item">
            <span>复盘知识</span>
            <strong>{{ reviewOverview.total }}</strong>
          </div>
        </div>
        <div v-if="canViewMcpServer" class="mcp-server-panel">
          <div class="section-toolbar audit-toolbar">
            <div class="toolbar-head">
              <span class="toolbar-title">sxdevops 对外 MCP Server</span>
              <span class="toolbar-desc">外部 Agent 通过 Token 鉴权调用平台只读工具，所有调用进入审计</span>
            </div>
          </div>
          <el-table :data="platformMcpManifest.tools || []" stripe size="small" class="console-table">
            <el-table-column prop="title" label="工具" min-width="180" show-overflow-tooltip />
            <el-table-column prop="name" label="MCP 名称" min-width="230" show-overflow-tooltip />
            <el-table-column prop="permission" label="权限" min-width="160" />
            <el-table-column label="状态" width="96">
              <template #default="{ row }">
                <el-tag size="small" :type="row.available === false ? 'warning' : 'success'">{{ row.available === false ? '受限' : '可用' }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="安全" width="96">
              <template #default="{ row }">
                <el-tag size="small" effect="plain" :type="row.annotations?.readOnlyHint ? 'success' : 'danger'">
                  {{ row.annotations?.readOnlyHint ? '只读' : '写入' }}
                </el-tag>
              </template>
            </el-table-column>
          </el-table>
        </div>
        <div class="audit-section">
          <div class="section-toolbar audit-toolbar">
            <div class="toolbar-head">
              <span class="toolbar-title">外部协同任务</span>
              <span class="toolbar-desc">接收其他系统或 Agent 提交的任务草案，平台确认后再执行</span>
            </div>
            <el-button v-if="canInvokeA2A" size="small" type="primary" @click="openA2ADialog">创建任务草案</el-button>
          </div>
          <el-table :data="a2aTasks" stripe size="small" class="console-table">
            <el-table-column type="expand">
              <template #default="{ row }">
                <div class="json-preview">{{ formatJsonCompact({ input_payload: row.input_payload, plan_steps: row.plan_steps, orchestration_state: row.orchestration_state, agent_results: row.agent_results, react_trace: row.react_trace, result_payload: row.result_payload }) }}</div>
              </template>
            </el-table-column>
            <el-table-column prop="title" label="任务标题" min-width="180" show-overflow-tooltip />
            <el-table-column prop="source_agent" label="来源" width="130" />
            <el-table-column label="问答类型" min-width="160">
              <template #default="{ row }">{{ formatCapabilityName(row.action_code) }}</template>
            </el-table-column>
            <el-table-column prop="agent_mode" label="模式" width="110" />
            <el-table-column prop="status_display" label="状态" width="110" />
            <el-table-column prop="created_at" label="创建时间" min-width="170" />
            <el-table-column v-if="canInvokeA2A" label="操作" width="230" fixed="right">
              <template #default="{ row }">
                <div class="table-actions">
                  <el-button link type="primary" :disabled="row.status !== 'queued'" @click="handleRunA2ATask(row)">运行</el-button>
                  <el-button link type="warning" :disabled="['completed', 'canceled'].includes(row.status)" @click="handleInterruptA2ATask(row)">中断</el-button>
                  <el-button link :disabled="['completed', 'canceled'].includes(row.status)" @click="handleCancelA2ATask(row)">取消</el-button>
                  <el-button v-if="canManageReviewKnowledge" link type="success" @click="handleAutoIngestReviewKnowledge(row, 'task')">沉淀</el-button>
                </div>
              </template>
            </el-table-column>
          </el-table>
          <div class="pagination-row">
            <el-pagination
              v-model:current-page="a2aPagination.page"
              :page-size="a2aPagination.pageSize"
              :total="a2aPagination.total"
              layout="total, prev, pager, next"
              @current-change="loadA2ATasks"
            />
          </div>
        </div>
        <div class="audit-section">
          <div class="section-toolbar audit-toolbar">
            <div class="toolbar-head">
              <span class="toolbar-title">Runbook 手册</span>
              <span class="toolbar-desc">把排障步骤、证据和复盘结论保存成可复用手册</span>
            </div>
            <el-button v-if="canManageRunbook" size="small" type="primary" @click="openRunbookDialog">生成手册草案</el-button>
          </div>
          <el-table :data="runbooks" stripe size="small" class="console-table">
            <el-table-column type="expand">
              <template #default="{ row }">
                <div class="json-preview">{{ formatJsonCompact({ content: row.content || '暂无内容', evidence: row.evidence, source_refs: row.source_refs }) }}</div>
              </template>
            </el-table-column>
            <el-table-column prop="title" label="标题" min-width="220" show-overflow-tooltip />
            <el-table-column prop="environment" label="环境" width="130" />
            <el-table-column prop="service" label="服务" width="150" />
            <el-table-column prop="version" label="版本" width="76" />
            <el-table-column prop="status_display" label="状态" width="100" />
            <el-table-column prop="updated_at" label="更新时间" min-width="170" />
            <el-table-column label="操作" width="270" fixed="right">
              <template #default="{ row }">
                <div class="table-actions">
                  <el-button link @click="handleViewRunbookVersions(row)">版本</el-button>
                  <el-button v-if="canManageRunbook" link type="primary" :disabled="row.status === 'published'" @click="handlePublishRunbook(row)">发布</el-button>
                  <el-button v-if="canManageRunbook" link type="warning" :disabled="row.status === 'archived'" @click="handleArchiveRunbook(row)">归档</el-button>
                  <el-button v-if="canManageReviewKnowledge" link type="success" @click="handleAutoIngestReviewKnowledge(row, 'runbook')">沉淀</el-button>
                  <el-button v-if="canManageRunbook" link type="danger" @click="handleDeleteRunbook(row)">删除</el-button>
                </div>
              </template>
            </el-table-column>
          </el-table>
          <div class="pagination-row">
            <el-pagination
              v-model:current-page="runbookPagination.page"
              :page-size="runbookPagination.pageSize"
              :total="runbookPagination.total"
              layout="total, prev, pager, next"
              @current-change="loadRunbooks"
            />
          </div>
        </div>
        <div class="audit-section">
          <div class="section-toolbar audit-toolbar">
            <div class="toolbar-head">
              <span class="toolbar-title">复盘知识</span>
              <span class="toolbar-desc">自动关联会话、协同任务、Runbook 和证据，形成可检索知识</span>
            </div>
          </div>
          <el-table :data="reviewKnowledge" stripe size="small" class="console-table">
            <el-table-column type="expand">
              <template #default="{ row }">
                <div class="json-preview">{{ formatJsonCompact({ summary: row.summary, evidence: row.evidence, source_refs: row.source_refs }) }}</div>
              </template>
            </el-table-column>
            <el-table-column prop="title" label="标题" min-width="220" show-overflow-tooltip />
            <el-table-column prop="environment" label="环境" width="130" />
            <el-table-column prop="service" label="服务" width="150" />
            <el-table-column prop="source_type_display" label="来源" width="110" />
            <el-table-column prop="updated_at" label="更新时间" min-width="170" />
            <el-table-column v-if="canManageReviewKnowledge" label="操作" width="92" fixed="right">
              <template #default="{ row }">
                <el-button link type="danger" @click="handleDeleteReviewKnowledge(row)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
          <div class="pagination-row">
            <el-pagination
              v-model:current-page="reviewPagination.page"
              :page-size="reviewPagination.pageSize"
              :total="reviewPagination.total"
              layout="total, prev, pager, next"
              @current-change="loadReviewKnowledge"
            />
          </div>
        </div>
      </template>

      <template v-else-if="activeTab === 'providers'">
        <div class="section-toolbar">
          <div class="toolbar-head">
            <span class="toolbar-title">模型供应商</span>
            <span class="toolbar-desc">
              管理外部 LLM 接入配置与默认模型。
              <strong class="provider-strategy-reminder">配置完成后，在列表中设为默认供应商，智能助手将使用该供应商的默认模型。</strong>
            </span>
          </div>
          <el-button v-if="canManageCapabilities" size="small" type="primary" @click="openProviderDialog()">新增提供商</el-button>
        </div>
        <el-table :data="providers" stripe class="console-table">
          <el-table-column prop="name" label="名称" min-width="180" />
          <el-table-column prop="provider_type" label="类型" width="150" />
          <el-table-column prop="base_url" label="Base URL" min-width="220" show-overflow-tooltip />
          <el-table-column prop="default_model" label="默认模型" width="160" />
          <el-table-column label="计费" width="96">
            <template #default="{ row }">
              <el-tag size="small" effect="plain">{{ formatProviderCurrency(row.price_currency) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="可用性" width="96">
            <template #default="{ row }">
              <el-tooltip :content="providerRuntimeHint(row)" placement="top" :disabled="row.runtime_ready">
                <el-tag size="small" :type="providerRuntimeTagType(row)">{{ providerRuntimeLabel(row) }}</el-tag>
              </el-tooltip>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="120">
            <template #default="{ row }">
              <el-tag size="small" :type="row.is_enabled ? 'success' : 'info'">{{ row.is_enabled ? '启用' : '停用' }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="默认供应商" width="150" align="center">
            <template #default="{ row }">
              <el-tag v-if="defaultProviderId === row.id" size="small" type="primary" effect="plain">当前默认</el-tag>
              <el-button v-else-if="canManageCapabilities" size="small" :disabled="!row.runtime_ready || selectingProviderId !== null" :loading="selectingProviderId === row.id" @click="handleSetDefaultProvider(row)">设为默认</el-button>
              <span v-else class="muted-text">--</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="220" fixed="right">
            <template #default="{ row }">
              <div v-if="canManageCapabilities" class="table-actions">
                <el-button link type="primary" @click="openProviderDialog(row)">编辑</el-button>
                <el-button link type="success" @click="handleTestProvider(row)">测试</el-button>
                <el-button link type="danger" @click="handleDeleteProvider(row)">删除</el-button>
              </div>
            </template>
          </el-table-column>
        </el-table>
      </template>

      <template v-else-if="activeTab === 'mcp'">
        <div class="section-toolbar">
          <div class="toolbar-head">
            <span class="toolbar-title">MCP 接入目录</span>
            <span class="toolbar-desc">管理平台内置与外部 MCP 的接入、鉴权和运行边界</span>
          </div>
          <el-button v-if="canManageCapabilities" size="small" type="primary" @click="openMcpDialog()">新增 MCP</el-button>
        </div>
        <div class="action-summary-row">
          <div v-for="item in mcpOverview" :key="item.label" class="action-summary-item">
            <span>{{ item.label }}</span>
            <strong>{{ item.value }}</strong>
          </div>
        </div>
        <div class="action-library">
          <div v-for="server in mcpServers" :key="server.id" class="action-package-row">
            <div class="action-package-main">
              <div class="action-package-title-row">
                <span class="action-package-name">{{ server.name }}</span>
                <el-tag size="small" effect="plain" :class="['type-tag', `type-tag--${server.server_type || 'http'}`]">{{ formatMcpType(server.server_type) }}</el-tag>
                <el-tag v-if="server.server_type !== 'platform_builtin'" size="small" effect="plain" :type="mcpRuntimeMode(server).type">{{ mcpRuntimeMode(server).label }}</el-tag>
                <el-tag size="small" effect="plain" :type="server.is_enabled ? 'success' : 'info'">{{ server.is_enabled ? '启用' : '停用' }}</el-tag>
              </div>
              <div class="action-package-desc">{{ server.description || '暂无描述' }}</div>
              <div v-if="server.endpoint_or_command" class="action-package-desc mcp-package-endpoint">地址或命令：{{ server.endpoint_or_command }}</div>
            </div>
            <div class="action-package-side">
              <button v-if="canManageCapabilities" type="button" class="action-package-stat stat-detail-button" @click="handleListMcpTools(server)">
                <span>启用工具</span>
                <strong>{{ (server.tool_whitelist || []).length }}</strong>
              </button>
              <div v-else class="action-package-stat">
                <span>启用工具</span>
                <strong>{{ (server.tool_whitelist || []).length }}</strong>
              </div>
              <div v-if="canManageCapabilities" class="table-actions">
                <el-button link type="primary" @click="openMcpDialog(server)">编辑</el-button>
                <el-button link type="success" @click="handleTestMcp(server)">测试</el-button>
                <el-button link type="danger" :disabled="server.is_builtin" @click="handleDeleteMcp(server)">删除</el-button>
              </div>
            </div>
          </div>
          <el-empty v-if="!mcpServers.length" description="暂无 MCP 接入" :image-size="64" />
        </div>
      </template>

      <template v-else-if="activeTab === 'skills'">
        <div class="section-toolbar">
          <div class="toolbar-head">
            <span class="toolbar-title">Skill 能力包</span>
            <span class="toolbar-desc">Skill 是可复用的方法包，由问答类型统一挂载；拆分后保留专业边界并复用公共方法，请核对启用状态与适用角色</span>
          </div>
          <div class="toolbar-actions">
            <el-button size="small" @click="openSkillMarketDialog">Skill 市场</el-button>
            <el-button size="small" type="primary" @click="openSkillDialog()">新增 Skill</el-button>
          </div>
        </div>
        <div class="skill-summary-row">
          <div class="skill-summary-item">
            <span>能力包</span>
            <strong>{{ skillOverview.total }}</strong>
          </div>
          <div class="skill-summary-item">
            <span>内置</span>
            <strong>{{ skillOverview.builtin }}</strong>
          </div>
          <div class="skill-summary-item">
            <span>自定义</span>
            <strong>{{ skillOverview.custom }}</strong>
          </div>
          <div class="skill-summary-item">
            <span>启用</span>
            <strong>{{ skillOverview.enabled }}</strong>
          </div>
        </div>
        <div class="skill-library">
          <div v-for="group in skillGroups" :key="group.category" class="skill-group">
            <div class="skill-group-head">
              <div class="toolbar-head">
                <span class="skill-group-title">{{ group.category }}</span>
                <span class="toolbar-desc">{{ group.items.length }} 个 Skill</span>
              </div>
            </div>
            <div class="skill-package-list">
              <div v-for="skill in group.items" :key="skill.id || skill.slug" class="skill-package-row">
                <div class="skill-package-main">
                  <div class="skill-package-title-row">
                    <span class="skill-package-name">{{ skill.name }}</span>
                    <el-tag size="small" effect="plain" :class="['type-tag', `type-tag--${getSkillTypeClass(skill)}`]">
                      {{ formatSkillType(skill) }}
                    </el-tag>
                    <el-tag size="small" :type="skillRiskTagType(skill.risk_level)" effect="plain">
                      能力风险：{{ formatSkillRiskLabel(skill.risk_level) }}
                    </el-tag>
                    <el-tag size="small" :type="skill.is_enabled ? 'success' : 'info'" effect="plain">
                      {{ skill.is_enabled ? '启用' : '停用' }}
                    </el-tag>
                  </div>
                  <div class="skill-package-desc">{{ skill.description || '暂无描述' }}</div>
                  <div class="skill-package-tags">
                    <el-tag v-if="skillCapabilityNames(skill).length > 1" size="small" effect="plain" type="success">{{ skillCapabilityNames(skill).length }} 项能力复用</el-tag>
                    <el-tag v-for="capability in skillCapabilityNames(skill)" :key="`${skill.slug}-${capability.code}`" size="small" effect="plain">
                      归属：{{ capability.name }}
                    </el-tag>
                    <span v-if="!skillCapabilityNames(skill).length" class="muted-text">暂未挂载到问答类型</span>
                  </div>
                </div>
                <div class="skill-package-side">
                  <button type="button" class="skill-package-stat stat-detail-button" @click="openSkillStatDetail(skill, 'tools')">
                    <span>工具依赖</span>
                    <strong>{{ skillRecommendedToolCount(skill) }}</strong>
                  </button>
                  <button type="button" class="skill-package-stat stat-detail-button" @click="openSkillStatDetail(skill, 'scenes')">
                    <span>场景</span>
                    <strong>{{ (skill.examples || []).length }}</strong>
                  </button>
                  <div class="table-actions">
                    <el-button link type="primary" @click="openSkillDialog(skill)">编辑</el-button>
                    <el-button link type="danger" :disabled="skill.is_builtin" @click="handleDeleteSkill(skill)">删除</el-button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </template>

      <template v-else-if="activeTab === 'actions'">
        <div class="section-toolbar">
          <div class="toolbar-head">
            <span class="toolbar-title">问答类型目录</span>
            <span class="toolbar-desc">统一配置问答类型和可复用 Skill，执行操作仍需确认并遵循权限和安全策略</span>
          </div>
          <span class="audit-hint">已配置 {{ capabilityOverview.total }} 项问答类型</span>
        </div>
        <div class="action-summary-row">
          <div class="action-summary-item">
            <span>问答类型总数</span>
            <strong>{{ capabilityOverview.total }}</strong>
          </div>
          <div class="action-summary-item">
            <span>可用类型</span>
            <strong>{{ capabilityOverview.available }}</strong>
          </div>
          <div class="action-summary-item">
            <span>需知识图谱环境</span>
            <strong>{{ capabilityOverview.environment }}</strong>
          </div>
          <div class="action-summary-item">
            <span>已关联 Skill</span>
            <strong>{{ capabilityOverview.mountedSkills }}</strong>
          </div>
        </div>
        <div class="action-library">
          <div v-for="capability in capabilityList" :key="capability.code" class="action-package-row">
                <div class="action-package-main">
                  <div class="action-package-title-row">
                    <span class="action-package-name">{{ capability.display_name || capability.code }}</span>
                    <span class="action-package-code">{{ capability.code }}</span>
                    <el-tag size="small" effect="plain" :type="actionModeTagType(capability.agent_mode)">
                      {{ formatActionMode(capability.agent_mode) }}
                    </el-tag>
                    <el-tag size="small" effect="plain" :type="actionRiskTagType(capability.risk_level)">
                      {{ actionRiskLabel(capability.risk_level) }}
                    </el-tag>
                    <el-tag size="small" effect="plain" :type="capability.requires_environment ? 'warning' : 'success'">
                      {{ capability.requires_environment ? '需知识图谱环境' : '免预选' }}
                    </el-tag>
                    <el-tooltip :content="capability.available_reason || '问答类型可用'" placement="top" :disabled="capability.available !== false">
                      <el-tag size="small" effect="plain" :type="actionAvailabilityTagType(capability.available)">
                        {{ actionAvailabilityLabel(capability.available) }}
                      </el-tag>
                    </el-tooltip>
                  </div>
                  <div class="action-package-desc">{{ capability.summary || capability.description || '暂无描述' }}</div>
                  <div class="action-package-tags">
                    <el-tag v-for="context in capability.required_context || []" :key="`${capability.code}-ctx-${context}`" size="small" effect="plain">
                      上下文：{{ context }}
                    </el-tag>
                    <el-tag v-for="legacyCode in capability.legacy_action_codes || []" :key="`${capability.code}-legacy-${legacyCode}`" size="small" effect="plain" type="info">
                      兼容：{{ legacyCode }}
                    </el-tag>
                    <span v-if="!(capability.required_context || []).length" class="muted-text">未要求前置上下文</span>
                  </div>
                </div>
                <div class="action-package-side">
                  <button type="button" class="action-package-stat stat-detail-button" @click="openCapabilityStatDetail(capability, 'examples')">
                    <span>示例</span>
                    <strong>{{ (capability.suggested_questions || []).length }}</strong>
                  </button>
                  <button type="button" class="action-package-stat stat-detail-button" @click="openCapabilityStatDetail(capability, 'skills')">
                    <span>已挂载 Skill</span>
                    <strong>{{ capabilitySkillCount(capability) }}</strong>
                    <small>当前可用 {{ capabilityAvailableSkillCount(capability) }}</small>
                  </button>
                  <button type="button" class="action-package-stat stat-detail-button" @click="openCapabilityStatDetail(capability, 'outputs')">
                    <span>输出</span>
                    <strong>{{ (capability.output_blocks || []).length }}</strong>
                  </button>
                  <el-button v-if="canManageCapabilities" link type="primary" @click="openCapabilityDialog(capability)">管理 Skill</el-button>
                </div>
          </div>
        </div>
      </template>

    </section>

    <ModelProviderDialog v-model="providerDialogVisible" :provider="editingProvider" :presets="providerPresets" @saved="reloadProviders" />

    <AgentAssetDialog v-model="mcpDialogVisible" :title="mcpForm.id ? '编辑 MCP' : '新增 MCP'" save-label="保存 MCP" :form="mcpForm" :rules="mcpRules" :saving="saving.mcp" @save="saveMcp" @invalid="fields => { if (fields?.auth_config_text) mcpAdvanced = ['auth'] }">
      <section class="asset-section">
        <div class="asset-heading"><span class="asset-step">01</span><h3>服务连接</h3><el-tag size="small" effect="plain" type="info">{{ formatMcpType(mcpForm.server_type) }}</el-tag></div>
        <div class="asset-grid">
          <el-form-item label="服务名称" prop="name"><el-input v-model="mcpForm.name" :disabled="mcpForm.is_builtin" maxlength="128" placeholder="例如：团队知识库 MCP" /></el-form-item>
          <el-form-item label="连接方式"><el-select v-model="mcpForm.server_type" :disabled="mcpForm.is_builtin" aria-label="连接方式"><el-option label="HTTP · 远程服务" value="http" /><el-option label="STDIO · 本地进程" value="stdio" /><el-option label="平台内置" value="platform_builtin" /></el-select></el-form-item>
          <el-form-item :label="mcpForm.server_type === 'stdio' ? '启动命令' : '服务地址'" prop="endpoint_or_command" class="asset-full"><el-input v-model="mcpForm.endpoint_or_command" :placeholder="mcpForm.server_type === 'stdio' ? '例如：npx -y @modelcontextprotocol/server-example' : 'https://mcp.example.com/mcp'" /><div class="asset-hint">{{ mcpForm.server_type === 'stdio' ? '填写可执行文件及参数，凭据在高级设置中配置。' : (mcpForm.server_type === 'platform_builtin' ? '平台内置服务由系统维护，可留空。' : '填写 MCP 服务的完整 HTTP 端点。') }}</div></el-form-item>
          <el-form-item label="服务说明" class="asset-full"><el-input v-model="mcpForm.description" type="textarea" :rows="2" placeholder="描述服务提供的数据或工具能力" /></el-form-item>
        </div>
      </section>
      <section class="asset-section asset-section--tinted">
        <div class="asset-heading"><span class="asset-step">02</span><h3>工具与运行</h3></div>
        <el-form-item label="允许使用的工具"><el-select v-model="mcpForm.tool_whitelist" multiple filterable allow-create default-first-option collapse-tags collapse-tags-tooltip :max-collapse-tags="4" placeholder="输入工具名称，按 Enter 添加" aria-label="允许使用的工具"><el-option v-for="tool in skillToolOptions" :key="tool" :label="tool" :value="tool" /></el-select><div class="asset-hint">填写 MCP 返回的工具名称，可通过列表中的“工具”查看；外部 MCP 留空时加载全部符合运行权限的工具。</div></el-form-item>
        <div v-if="mcpForm.server_type !== 'platform_builtin'" class="asset-grid">
          <el-form-item label="写操作权限"><el-switch v-model="mcpAllowWrite" active-text="允许写操作" inactive-text="只读" aria-label="允许 MCP 写操作" /><div class="asset-hint">默认只读，写入类工具仍受账号权限和确认流程约束。</div></el-form-item>
          <el-form-item label="请求超时（秒）"><el-input-number v-model="mcpTimeoutSeconds" :min="5" :max="300" controls-position="right" /></el-form-item>
        </div>
      </section>
      <el-collapse v-model="mcpAdvanced" class="asset-advanced"><el-collapse-item name="auth"><template #title><span>高级设置</span><span class="asset-summary">鉴权请求头与环境变量</span></template>
        <el-form-item label="鉴权配置（JSON）" prop="auth_config_text" class="asset-code"><el-input v-model="mcpForm.auth_config_text" type="textarea" :rows="6" placeholder='{"headers":{"Authorization":"Bearer xxx"},"env":{"TOKEN":"xxx"}}' /><div class="asset-hint">HTTP 使用 headers，STDIO 使用 env；STDIO 仅继承安全系统环境变量。</div></el-form-item>
      </el-collapse-item></el-collapse>
      <div class="asset-enable"><div><strong>启用此 MCP</strong><p>开启后可供智能体调用，实际使用仍遵循问答类型与用户权限。</p></div><el-switch v-model="mcpForm.is_enabled" aria-label="启用此 MCP" /></div>
    </AgentAssetDialog>

    <el-dialog top="5vh" :close-on-click-modal="false" class="workbench-edit-dialog" v-model="capabilityDialogVisible" title="配置问答类型" width="min(760px, 94vw)" destroy-on-close append-to-body>
      <div class="skill-detail-card">
        <div class="skill-detail-title">{{ capabilityForm.display_name || capabilityForm.code }}</div>
        <div class="skill-detail-desc">{{ capabilityForm.description || '暂无描述' }}</div>
      </div>
      <el-form label-position="top" :model="capabilityForm" label-width="102px">
        <el-form-item label="挂载 Skill">
          <el-select v-model="capabilityForm.skills" multiple filterable collapse-tags collapse-tags-tooltip placeholder="选择可复用的方法包" style="width:100%">
            <el-option v-for="skill in skills" :key="skill.slug" :label="`${skill.name}${skill.is_enabled ? '' : '（已停用）'}`" :value="skill.slug" />
          </el-select>
        </el-form-item>
      </el-form>
      <div class="runtime-note">同一个 Skill 可以服务多个能力；实际加载还需满足启用状态、智能体策略选择和当前账号角色范围。</div>
      <div v-if="selectedCapabilitySkills.length" class="stat-detail-list capability-skill-preview">
        <div v-for="skill in selectedCapabilitySkills" :key="skill.slug" class="stat-detail-item">
          <div class="stat-detail-main">
            <span class="stat-detail-label">{{ skill.name || skill.slug }}</span>
            <span class="stat-detail-desc">{{ skill.description || '暂无描述' }}</span>
          </div>
          <el-tag size="small" effect="plain" :type="skill.available ? 'success' : 'info'">{{ capabilitySkillAvailability(skill) }}</el-tag>
        </div>
      </div>
      <template #footer>
        <el-button @click="capabilityDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving.capability" @click="saveCapability">保存挂载</el-button>
      </template>
    </el-dialog>

    <AgentAssetDialog v-model="skillDialogVisible" :title="skillForm.id ? '编辑 Skill' : '新增 Skill'" save-label="保存 Skill" :form="skillForm" :rules="skillRules" :saving="saving.skill" @save="saveSkill" @invalid="fields => { if (fields?.output_contract_text) skillAdvanced = ['output'] }">
      <section class="asset-section">
        <div class="asset-heading"><span class="asset-step">01</span><h3>基本信息</h3><el-tag size="small" effect="plain" type="info">{{ skillForm.is_builtin ? '平台内置' : '团队技能' }}</el-tag></div>
        <div class="asset-grid">
          <el-form-item label="技能名称" prop="name"><el-input v-model="skillForm.name" maxlength="128" placeholder="例如：发布风险评估" /></el-form-item>
          <el-form-item label="唯一标识" prop="slug"><el-input v-model="skillForm.slug" :disabled="skillForm.is_builtin" placeholder="例如：release-risk-review" /><div class="asset-hint">使用字母、数字、下划线或短横线，内置标识不可修改。</div></el-form-item>
          <el-form-item label="技能来源"><el-select v-model="skillForm.source_type" :disabled="skillForm.is_builtin" aria-label="技能来源"><el-option label="平台内联" value="inline" /><el-option label="本地文件" value="local" /></el-select></el-form-item>
          <el-form-item label="分类"><el-select v-model="skillForm.category" filterable allow-create default-first-option placeholder="选择或输入分类" aria-label="技能分类"><el-option v-for="item in skillCategoryOptions" :key="item" :label="item" :value="item" /></el-select></el-form-item>
          <el-form-item label="技能说明" class="asset-full"><el-input v-model="skillForm.description" type="textarea" :rows="2" placeholder="描述这个技能适用的问题和预期结果" /></el-form-item>
        </div>
        <div class="asset-note"><div class="asset-tags"><span>挂载的问答类型</span><el-tag v-for="capability in skillCapabilityNames(skillForm)" :key="capability.code" size="small" effect="plain">{{ capability.name }}</el-tag><span v-if="!skillCapabilityNames(skillForm).length">尚未挂载</span></div><div class="asset-hint">在“问答类型”中管理挂载；同一技能可供多种问答复用。</div></div>
      </section>
      <section class="asset-section asset-section--tinted">
        <div class="asset-heading"><span class="asset-step">02</span><h3>技能指令</h3></div>
        <el-form-item label="指令内容" class="asset-code"><el-input v-model="skillForm.content" type="textarea" :rows="8" resize="vertical" placeholder="描述处理步骤、取证方式、判断标准与输出要求…" /></el-form-item>
        <el-form-item label="适用场景"><el-select v-model="skillForm.examples" multiple filterable allow-create default-first-option collapse-tags collapse-tags-tooltip :max-collapse-tags="3" placeholder="输入场景示例，按 Enter 添加" aria-label="适用场景" /></el-form-item>
      </section>
      <el-collapse v-model="skillAdvanced" class="asset-advanced">
        <el-collapse-item name="tools"><template #title><span>工具依赖与访问范围</span><span class="asset-summary">{{ (skillForm.builtin_tools || []).length + (skillForm.recommended_tools || []).length }} 项依赖</span></template>
          <div class="asset-grid"><el-form-item label="核心工具依赖"><el-select v-model="skillForm.builtin_tools" multiple filterable allow-create default-first-option collapse-tags collapse-tags-tooltip placeholder="选择或输入工具名" aria-label="核心工具依赖"><el-option v-for="tool in skillToolOptions" :key="tool" :label="tool" :value="tool" /></el-select></el-form-item>
          <el-form-item label="补充工具依赖"><el-select v-model="skillForm.recommended_tools" multiple filterable allow-create default-first-option collapse-tags collapse-tags-tooltip placeholder="选择或输入工具名" aria-label="补充工具依赖"><el-option v-for="tool in skillToolOptions" :key="tool" :label="tool" :value="tool" /></el-select></el-form-item></div>
          <el-form-item label="适用角色"><el-select v-model="skillForm.allowed_role_codes" multiple filterable allow-create default-first-option placeholder="输入角色编码，留空表示不额外限制" aria-label="适用角色" /><div class="asset-hint">角色范围仅收紧技能访问，不会授予账号额外权限。</div></el-form-item>
        </el-collapse-item>
        <el-collapse-item name="output"><template #title><span>运行参数与输出约束</span><span class="asset-summary">{{ skillForm.max_iterations ? `${skillForm.max_iterations} 轮迭代` : '默认迭代次数' }}</span></template>
          <div class="asset-grid"><el-form-item label="风险提示"><el-select v-model="skillForm.risk_level" aria-label="风险提示"><el-option label="只读" value="read_only" /><el-option label="草稿" value="draft" /><el-option label="写入" value="write" /><el-option label="执行" value="execute" /></el-select></el-form-item>
          <el-form-item label="最大迭代次数"><el-input-number v-model="skillForm.max_iterations" :min="0" :max="20" controls-position="right" /><div class="asset-hint">0 表示沿用智能体默认值。</div></el-form-item></div>
          <el-form-item label="输出约束（JSON）" prop="output_contract_text" class="asset-code"><el-input v-model="skillForm.output_contract_text" type="textarea" :rows="5" placeholder='{"sections":["结论","证据"],"blocks":["risk_notice"]}' /></el-form-item>
        </el-collapse-item>
      </el-collapse>
      <div class="asset-enable"><div><strong>启用此 Skill</strong><p>开启后按问答类型挂载和角色范围自动加载。</p></div><el-switch v-model="skillForm.is_enabled" aria-label="启用此 Skill" /></div>
    </AgentAssetDialog>

    <el-dialog v-model="skillMarketDialogVisible" title="Skill 市场" width="900px" destroy-on-close append-to-body>
      <div class="skill-summary-row">
        <div class="skill-summary-item">
          <span>市场能力包</span>
          <strong>{{ skillMarketSummary.total || 0 }}</strong>
        </div>
        <div class="skill-summary-item">
          <span>平台内置</span>
          <strong>{{ skillMarketSummary.builtin || 0 }}</strong>
        </div>
        <div class="skill-summary-item">
          <span>团队自定义</span>
          <strong>{{ skillMarketSummary.team || 0 }}</strong>
        </div>
        <div class="skill-summary-item">
          <span>已启用</span>
          <strong>{{ skillMarketSummary.enabled || 0 }}</strong>
        </div>
      </div>
      <el-table :data="skillMarketplace.items || []" stripe max-height="460" class="console-table">
        <el-table-column prop="name" label="名称" min-width="170" />
        <el-table-column prop="category" label="分类" width="120" />
        <el-table-column prop="source_display" label="来源" width="110" />
        <el-table-column prop="description" label="描述" min-width="240" show-overflow-tooltip />
        <el-table-column label="归属能力" min-width="180" show-overflow-tooltip>
          <template #default="{ row }">{{ skillCapabilityNames(row).map(item => item.name).join('、') || '暂未挂载' }}</template>
        </el-table-column>
        <el-table-column label="操作" width="110" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="handleCloneSkill(row)">克隆</el-button>
          </template>
        </el-table-column>
      </el-table>
      <template #footer>
        <el-button @click="skillMarketDialogVisible = false">关闭</el-button>
      </template>
    </el-dialog>

    <el-dialog top="5vh" :close-on-click-modal="false" class="workbench-edit-dialog" v-model="a2aDialogVisible" title="创建协同任务草案" width="720px" destroy-on-close append-to-body>
      <el-form class="workbench-editor-form--sectioned" label-position="top" :model="a2aForm" label-width="104px">
        <section class="workbench-editor-section">
          <div class="workbench-editor-heading"><span class="workbench-editor-step">01</span><h3>协同任务</h3></div>
          <div class="workbench-editor-grid">
            <el-form-item label="来源系统"><el-input v-model="a2aForm.source_agent" /></el-form-item>
            <el-form-item label="任务标题"><el-input v-model="a2aForm.title" placeholder="留空则使用问答类型名称" /></el-form-item>
            <el-form-item label="问答类型">
              <el-select v-model="a2aForm.action_code" filterable style="width:100%">
                <el-option v-for="capability in capabilityRegistry" :key="capability.code" :label="`${capability.display_name || capability.code}（${capability.code}）`" :value="capability.code" />
              </el-select>
            </el-form-item>
          </div>
        </section>
        <section class="workbench-editor-section workbench-editor-section--tinted">
          <div class="workbench-editor-heading"><span class="workbench-editor-step">02</span><h3>输入参数</h3></div>
          <div>
            <el-form-item label="输入参数">
              <el-input v-model="a2aForm.input_payload_text" type="textarea" :rows="8" />
            </el-form-item>
          </div>
        </section>
      </el-form>
      <template #footer>
        <el-button @click="a2aDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="saveA2ATask">创建任务草案</el-button>
      </template>
    </el-dialog>

    <el-dialog top="5vh" :close-on-click-modal="false" class="workbench-edit-dialog" v-model="runbookDialogVisible" title="生成 Runbook 手册草案" width="760px" destroy-on-close append-to-body>
      <el-form class="workbench-editor-form--sectioned" label-position="top" :model="runbookForm" label-width="104px">
        <section class="workbench-editor-section">
          <div class="workbench-editor-heading"><span class="workbench-editor-step">01</span><h3>手册信息</h3></div>
          <div class="workbench-editor-grid">
            <el-form-item label="标题"><el-input v-model="runbookForm.title" /></el-form-item>
            <el-form-item label="来源会话"><el-input v-model="runbookForm.source_session" placeholder="填写会话 ID 可从事故会话一键生成" /></el-form-item>
            <div class="dialog-grid">
              <el-form-item label="环境"><el-input v-model="runbookForm.environment" /></el-form-item>
              <el-form-item label="服务"><el-input v-model="runbookForm.service" /></el-form-item>
            </div>
            <el-form-item label="标签"><el-select v-model="runbookForm.tags" multiple filterable allow-create default-first-option style="width:100%" /></el-form-item>
            <el-form-item label="引用来源"><el-input v-model="runbookForm.source_refs_text" type="textarea" :rows="3" /></el-form-item>
          </div>
        </section>
        <section class="workbench-editor-section workbench-editor-section--tinted">
          <div class="workbench-editor-heading"><span class="workbench-editor-step">02</span><h3>引用与内容</h3></div>
          <div>
            <el-form-item label="内容"><el-input v-model="runbookForm.content" type="textarea" :rows="10" placeholder="留空则按环境、服务和标题生成基础草案" /></el-form-item>
          </div>
        </section>
      </el-form>
      <template #footer>
        <el-button @click="runbookDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="saveRunbookDraft">生成手册草案</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="runbookVersionDialogVisible" :title="currentRunbookVersionTitle || 'Runbook 版本历史'" width="840px" destroy-on-close append-to-body>
      <el-table :data="runbookVersions" stripe max-height="420">
        <el-table-column prop="version" label="版本" width="76" />
        <el-table-column prop="status_display" label="状态" width="96" />
        <el-table-column prop="change_note" label="说明" min-width="180" show-overflow-tooltip />
        <el-table-column prop="created_by" label="创建人" width="110" />
        <el-table-column prop="created_at" label="创建时间" min-width="170" />
        <el-table-column type="expand">
          <template #default="{ row }">
            <div class="json-preview">{{ formatJsonCompact({ content: row.content, evidence: row.evidence, source_refs: row.source_refs }) }}</div>
          </template>
        </el-table-column>
      </el-table>
      <template #footer>
        <el-button @click="runbookVersionDialogVisible = false">关闭</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="mcpToolsDialogVisible" title="MCP 工具列表" width="760px" destroy-on-close>
      <div class="section-title" style="margin-bottom:12px;">{{ currentMcpToolsTitle || '工具列表' }}</div>
      <div v-if="mcpToolDiagnostics.length" class="mcp-diagnostic-list">
        <div v-for="item in mcpToolDiagnostics" :key="`${item.name}-${item.status}`" class="mcp-diagnostic-item">
          <el-tag size="small" :type="mcpDiagnosticType(item.status)">{{ mcpDiagnosticLabel(item.status) }}</el-tag>
          <span>{{ item.name }}：{{ item.message || `发现 ${item.tool_count || 0} 个工具` }}</span>
        </div>
      </div>
      <el-table :data="mcpToolsList" stripe max-height="420">
        <el-table-column prop="name" label="工具名" min-width="180" />
        <el-table-column prop="description" label="描述" min-width="220" show-overflow-tooltip />
        <el-table-column label="参数" min-width="180" show-overflow-tooltip>
          <template #default="{ row }">{{ formatMcpToolSchema(row) }}</template>
        </el-table-column>
        <el-table-column label="安全提示" width="120">
          <template #default="{ row }">
            <el-tag v-if="row._meta?.description_warnings?.length" size="small" type="warning">需复核</el-tag>
            <span v-else class="muted-text">--</span>
          </template>
        </el-table-column>
      </el-table>
      <div v-if="!mcpToolsList.length" class="session-empty">暂无工具</div>
      <template #footer>
        <el-button @click="mcpToolsDialogVisible = false">关闭</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="statDetailDialogVisible" :title="statDetail.title || '统计详情'" width="640px" destroy-on-close append-to-body>
      <div v-if="statDetail.subtitle" class="stat-detail-subtitle">{{ statDetail.subtitle }}</div>
      <div v-if="statDetail.items.length" class="stat-detail-list">
        <div v-for="(item, index) in statDetail.items" :key="`${item.label}-${index}`" :class="['stat-detail-item', { 'stat-detail-item--tool': item.mcpBindings }]">
          <div class="stat-detail-main">
            <span class="stat-detail-label">{{ item.label }}</span>
            <span v-if="item.desc" class="stat-detail-desc">{{ item.desc }}</span>
            <div v-if="item.mcpBindings" class="stat-detail-mcp">
              <div class="stat-detail-mcp-title">MCP 依赖</div>
              <div v-if="item.mcpBindings.length" class="stat-detail-mcp-list">
                <div v-for="binding in item.mcpBindings" :key="`${item.label}-${binding.id || binding.name}`" class="stat-detail-mcp-card">
                  <div class="stat-detail-mcp-head">
                    <span class="stat-detail-mcp-name">{{ binding.name || '未命名 MCP' }}</span>
                    <el-tag size="small" effect="plain">{{ formatMcpType(binding.server_type) }}</el-tag>
                    <el-tag size="small" effect="plain" :type="binding.is_builtin ? 'success' : 'info'">
                      {{ binding.is_builtin ? '平台内置' : '外部接入' }}
                    </el-tag>
                    <el-tag size="small" :type="binding.is_enabled ? 'success' : 'info'">
                      {{ binding.is_enabled ? '已启用' : '已停用' }}
                    </el-tag>
                  </div>
                  <div class="stat-detail-mcp-meta">
                    <span>绑定工具：{{ binding.tool || item.label }}</span>
                    <span v-if="binding.endpoint_or_command">入口：{{ binding.endpoint_or_command }}</span>
                  </div>
                  <div v-if="binding.description" class="stat-detail-mcp-desc">{{ binding.description }}</div>
                </div>
              </div>
              <div v-else class="stat-detail-mcp-empty">未匹配已配置 MCP Server</div>
            </div>
          </div>
          <el-tag v-if="item.tag" size="small" effect="plain">{{ item.tag }}</el-tag>
        </div>
      </div>
      <div v-else class="stat-detail-empty">{{ statDetail.emptyText || '暂无详情' }}</div>
      <template #footer>
        <el-button @click="statDetailDialogVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ChatDotSquare, Connection, Cpu, Message, Promotion, Setting, Tools } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import AgentStrategyPanel from '@/components/aiops/AgentStrategyPanel.vue'
import AgentAssetDialog from '@/components/aiops/AgentAssetDialog.vue'
import ModelProviderDialog from '@/components/aiops/ModelProviderDialog.vue'
import { useAuthStore } from '@/stores/auth'
import { useRouteTabState } from '@/composables/useRouteTabState'
import {
  archiveAIOpsRunbook,
  autoIngestAIOpsReviewKnowledge,
  cancelAIOpsA2ATask,
  createAIOpsMcpServer,
  createAIOpsSkill,
  createAIOpsA2ATask,
  createAIOpsRunbookDraft,
  createAIOpsRunbookFromSession,
  cloneAIOpsSkill,
  deleteAIOpsMcpServer,
  deleteAIOpsProvider,
  deleteAIOpsSkill,
  deleteAIOpsReviewKnowledge,
  deleteAIOpsRunbook,
  getAIOpsA2ATasks,
  getAIOpsCapabilities,
  getAIOpsConfig,
  getAIOpsPlatformMcpManifest,
  getAIOpsProviderPresets,
  getAIOpsReviewKnowledge,
  getAIOpsRunbooks,
  getAIOpsRunbookVersions,
  getAIOpsSkillMarketplace,
  getAIOpsMcpServers,
  getAIOpsProviders,
  getAIOpsSkills,
  listAIOpsMcpTools,
  publishAIOpsRunbook,
  runAIOpsA2ATask,
  interruptAIOpsA2ATask,
  testAIOpsProvider,
  testAIOpsMcpServer,
  updateAIOpsConfig,
  updateAIOpsCapability,
  updateAIOpsMcpServer,
  updateAIOpsSkill,
} from '@/api/modules/aiops'

const configTabs = ['strategy', 'actions', 'skills', 'mcp', 'orchestration', 'providers']
const { activeTab } = useRouteTabState({
  tabs: configTabs,
  defaultTab: 'strategy',
})
const authStore = useAuthStore()
const loading = reactive({ page: false })
const saving = reactive({ config: false, mcp: false, skill: false, capability: false })

const providers = ref([])
const defaultProviderId = ref(null)
const selectingProviderId = ref(null)
const providerPresets = ref([])
const mcpServers = ref([])
const skills = ref([])
const capabilityRegistry = ref([])
const capabilityRegistrySummary = ref({})
const a2aTasks = ref([])
const runbooks = ref([])
const reviewKnowledge = ref([])
const platformMcpManifest = ref({ tools: [], rate_limit: {} })
const skillMarketplace = ref({ summary: {}, items: [] })

const a2aPagination = reactive({
  page: 1,
  pageSize: 10,
  total: 0,
})
const runbookPagination = reactive({
  page: 1,
  pageSize: 10,
  total: 0,
})
const reviewPagination = reactive({
  page: 1,
  pageSize: 10,
  total: 0,
})

const configForm = reactive({
  system_prompt: '',
  welcome_message: '',
  suggested_questions: [],
  enabled_capability_codes: [],
  is_enabled: true,
  allow_action_execution: true,
  require_confirmation: true,
  show_evidence: true,
  allow_analysis: true,
  max_history_messages: 12,
})

const providerDialogVisible = ref(false)
const mcpDialogVisible = ref(false)
const skillDialogVisible = ref(false)
const capabilityDialogVisible = ref(false)
const skillMarketDialogVisible = ref(false)
const mcpToolsDialogVisible = ref(false)
const a2aDialogVisible = ref(false)
const runbookDialogVisible = ref(false)
const runbookVersionDialogVisible = ref(false)
const statDetailDialogVisible = ref(false)
const runbookVersions = ref([])
const currentRunbookVersionTitle = ref('')
const statDetail = reactive({
  title: '',
  subtitle: '',
  items: [],
  emptyText: '',
})

const editingProvider = ref(null)
const configuredDefaultProvider = ref(null)
const configSnapshot = ref(null)
const configDirty = computed(() => Boolean(configSnapshot.value && JSON.stringify(configForm) !== JSON.stringify(configSnapshot.value)))
const mcpAdvanced = ref([])
const skillAdvanced = ref([])
function validateJsonObject(rule, value, callback) {
  try {
    const parsed = JSON.parse(value?.trim() || '{}')
    if (!parsed || Array.isArray(parsed) || typeof parsed !== 'object') throw new Error()
    callback()
  } catch { callback(new Error('请填写合法的 JSON 对象')) }
}
const mcpRules = {
  name: [{ required: true, whitespace: true, message: '请填写服务名称', trigger: 'blur' }],
  endpoint_or_command: [{ validator: (rule, value, callback) => callback(mcpForm.server_type !== 'platform_builtin' && !value?.trim() ? new Error('请填写服务地址或启动命令') : undefined), trigger: 'blur' }],
  auth_config_text: [{ validator: validateJsonObject, trigger: 'blur' }],
}
const skillRules = {
  name: [{ required: true, whitespace: true, message: '请填写技能名称', trigger: 'blur' }],
  slug: [{ required: true, message: '请填写唯一标识', trigger: 'blur' }, { pattern: /^[a-zA-Z0-9_-]+$/, message: '仅支持字母、数字、下划线和短横线', trigger: 'blur' }],
  output_contract_text: [{ validator: validateJsonObject, trigger: 'blur' }],
}
const mcpForm = reactive({})
const skillForm = reactive({})
const capabilityForm = reactive({ code: '', display_name: '', description: '', skills: [] })
const a2aForm = reactive({})
const runbookForm = reactive({})
const mcpToolsList = ref([])
const mcpToolDiagnostics = ref([])
const currentMcpToolsTitle = ref('')

const canInvokeA2A = computed(() => authStore.hasPermission('aiops.a2a.invoke'))
const canManageCapabilities = computed(() => authStore.hasPermission('aiops.config.manage'))
const mcpOverview = computed(() => [
  { label: 'MCP 总数', value: mcpServers.value.length },
  { label: '平台内置', value: mcpServers.value.filter(item => item.server_type === 'platform_builtin').length },
  { label: '外部接入', value: mcpServers.value.filter(item => item.server_type !== 'platform_builtin').length },
  { label: '已启用', value: mcpServers.value.filter(item => item.is_enabled).length },
])
const canManageRunbook = computed(() => authStore.hasPermission('aiops.runbook.manage'))
const canViewMcpServer = computed(() => authStore.hasPermission('aiops.mcp.view'))
const canManageReviewKnowledge = computed(() => authStore.hasPermission('aiops.review.manage'))
const mcpAuthConfig = computed(() => {
  try {
    const raw = mcpForm.auth_config_text?.trim()
    return raw ? JSON.parse(raw) : {}
  } catch (error) {
    return mcpForm.auth_config && typeof mcpForm.auth_config === 'object' ? mcpForm.auth_config : {}
  }
})
const mcpAllowWrite = computed({
  get: () => Boolean(mcpAuthConfig.value.allow_write),
  set: (value) => updateMcpAuthConfig({ allow_write: Boolean(value) }),
})
const mcpTimeoutSeconds = computed({
  get: () => Number(mcpAuthConfig.value.timeout_seconds || 20),
  set: (value) => updateMcpAuthConfig({ timeout_seconds: Number(value || 20) }),
})
const skillOverview = computed(() => ({
  total: skills.value.length,
  builtin: skills.value.filter(item => item.is_builtin).length,
  custom: skills.value.filter(item => !item.is_builtin).length,
  enabled: skills.value.filter(item => item.is_enabled).length,
}))
const skillGroups = computed(() => {
  const groups = new Map()
  skills.value.forEach((skill) => {
    const category = skill.category || '未分类'
    if (!groups.has(category)) groups.set(category, { category, items: [] })
    groups.get(category).items.push(skill)
  })
  return Array.from(groups.values())
    .map(group => ({
      ...group,
      items: group.items.slice().sort((a, b) => Number(b.is_builtin) - Number(a.is_builtin) || String(a.name).localeCompare(String(b.name), 'zh-CN')),
    }))
    .sort((a, b) => a.category.localeCompare(b.category, 'zh-CN'))
})
const capabilityOverview = computed(() => ({
  total: Number(capabilityRegistrySummary.value.total ?? capabilityRegistry.value.length) || 0,
  available: Number(
    capabilityRegistrySummary.value.available
      ?? capabilityRegistry.value.filter(item => item.available !== false).length,
  ) || 0,
  environment: capabilityRegistry.value.filter(item => item.requires_environment).length,
  mountedSkills: new Set(capabilityRegistry.value.flatMap(item => item.skills || [])).size,
}))
const capabilityList = computed(() => capabilityRegistry.value
  .slice()
  .sort((a, b) => String(a.display_name || a.code).localeCompare(String(b.display_name || b.code), 'zh-CN')))
const selectedCapabilitySkills = computed(() => {
  const capability = capabilityRegistry.value.find(item => item.code === capabilityForm.code)
  const details = new Map((capability?.skill_details || []).map(skill => [skill.slug, skill]))
  return (capabilityForm.skills || []).map(slug => ({
    ...(skills.value.find(skill => skill.slug === slug) || { slug, name: slug, is_enabled: false }),
    ...(details.get(slug) || {}),
  }))
})
const skillMarketSummary = computed(() => skillMarketplace.value?.summary || {})
const a2aOverview = computed(() => ({
  total: a2aPagination.total || a2aTasks.value.length,
  queued: a2aTasks.value.filter(item => item.status === 'queued').length,
  running: a2aTasks.value.filter(item => item.status === 'running').length,
  done: a2aTasks.value.filter(item => ['completed', 'canceled', 'failed'].includes(item.status)).length,
}))
const runbookOverview = computed(() => ({
  total: runbookPagination.total || runbooks.value.length,
  draft: runbooks.value.filter(item => item.status === 'draft').length,
  published: runbooks.value.filter(item => item.status === 'published').length,
  archived: runbooks.value.filter(item => item.status === 'archived').length,
}))
const reviewOverview = computed(() => ({
  total: reviewPagination.total || reviewKnowledge.value.length,
  session: reviewKnowledge.value.filter(item => item.source_type === 'session').length,
  task: reviewKnowledge.value.filter(item => item.source_type === 'task').length,
  runbook: reviewKnowledge.value.filter(item => item.source_type === 'runbook').length,
}))
const platformMcpOverview = computed(() => ({
  total: platformMcpManifest.value?.tools?.length || 0,
  available: (platformMcpManifest.value?.tools || []).filter(item => item.available !== false).length,
  rateLimit: platformMcpManifest.value?.rate_limit?.per_minute || 0,
}))
const skillCategoryOptions = computed(() => {
  const categories = new Set(['诊断与处置', '事件分析', '日志分析', '指标与 SLO', '任务编排', 'CMDB', '通用规范'])
  skills.value.forEach(item => {
    if (item.category) categories.add(item.category)
  })
  return Array.from(categories)
})
const skillToolOptions = computed(() => {
  const tools = new Set()
  mcpServers.value.forEach(server => (server.tool_whitelist || []).forEach(tool => tools.add(tool)))
  capabilityRegistry.value.forEach(capability => (capability.allowed_tools || []).forEach(tool => tools.add(tool)))
  return Array.from(tools).sort()
})

function formatMcpType(serverType) {
  if (serverType === 'platform_builtin') return '平台内置'
  if (serverType === 'stdio') return 'STDIO'
  return 'HTTP'
}

function updateMcpAuthConfig(patch) {
  try {
    const parsed = JSON.parse(mcpForm.auth_config_text?.trim() || '{}')
    if (!parsed || Array.isArray(parsed) || typeof parsed !== 'object') throw new Error()
  } catch {
    mcpAdvanced.value = ['auth']
    ElMessage.warning('请先修正鉴权配置中的 JSON，再调整运行参数')
    return
  }
  const nextConfig = { ...mcpAuthConfig.value, ...patch }
  mcpForm.auth_config = nextConfig
  mcpForm.auth_config_text = JSON.stringify(nextConfig, null, 2)
}

function mcpRuntimeMode(row = {}) {
  if (row.server_type === 'platform_builtin') return { label: '平台内置', type: 'success' }
  return row.auth_config?.allow_write ? { label: '可写', type: 'warning' } : { label: '只读', type: 'info' }
}

function mcpDiagnosticType(status) {
  if (status === 'connected') return 'success'
  if (status === 'failed') return 'danger'
  return 'info'
}

function mcpDiagnosticLabel(status) {
  if (status === 'connected') return '已连接'
  if (status === 'failed') return '失败'
  return '未知'
}

function formatMcpToolSchema(row = {}) {
  const properties = row.inputSchema?.properties || {}
  const names = Object.keys(properties)
  if (!names.length) return '无参数'
  return names.slice(0, 6).join('、') + (names.length > 6 ? '…' : '')
}

function formatSkillSource(row = {}) {
  if (row.is_builtin) return '平台内置'
  if (row.source_type === 'local') return '本地文件'
  return '自定义'
}

function formatSkillType(row = {}) {
  return formatSkillSource(row)
}

function getSkillTypeClass(row = {}) {
  if (row.is_builtin) return 'platform_builtin'
  return row.source_type === 'local' ? 'local' : 'custom'
}

function formatSkillRiskLabel(risk) {
  if (risk === 'read_only') return '只读'
  if (risk === 'draft') return '草稿'
  if (risk === 'write') return '写入'
  if (risk === 'execute') return '执行'
  return risk || '只读'
}

function skillRiskTagType(risk) {
  if (risk === 'read_only') return 'info'
  if (risk === 'draft') return 'warning'
  if (risk === 'write') return 'warning'
  if (risk === 'execute') return 'danger'
  return 'info'
}

function skillRecommendedTools(skill = {}) {
  return Array.from(new Set([...(skill.builtin_tools || []), ...(skill.recommended_tools || [])])).filter(Boolean)
}

function skillRecommendedToolCount(skill = {}) {
  return skillRecommendedTools(skill).length
}

function capabilitySkillCount(capability = {}) {
  return new Set(capability.skills || []).size
}

function capabilityAvailableSkillCount(capability = {}) {
  return (capability.skill_details || []).filter(skill => skill.available).length
}

function capabilitySkillAvailability(skill = {}) {
  if (skill.available) return '当前可用'
  if (!skill.is_enabled) return '已停用'
  return skill.available_reason || '保存后校验可用性'
}

function formatCapabilityName(code) {
  const capability = capabilityRegistry.value.find(item => item.code === code || (item.legacy_action_codes || []).includes(code))
  return capability?.display_name || code
}

function skillCapabilityNames(skill = {}) {
  if (!skill.slug) return []
  return capabilityRegistry.value
    .filter(capability => (capability.skills || []).includes(skill.slug))
    .map(capability => ({ code: capability.code, name: capability.display_name || capability.code }))
}

function openStatDetail({ title, subtitle, items, emptyText }) {
  statDetail.title = title
  statDetail.subtitle = subtitle || ''
  statDetail.items = Array.isArray(items) ? items : []
  statDetail.emptyText = emptyText || '暂无详情'
  statDetailDialogVisible.value = true
}

function openSkillStatDetail(skill = {}, type) {
  const skillName = skill.name || skill.slug || '--'
  if (type === 'tools') {
    const builtinTools = new Set((skill.builtin_tools || []).filter(Boolean))
    const recommendedTools = new Set((skill.recommended_tools || []).filter(Boolean))
    const items = skillRecommendedTools(skill).map(tool => ({
      label: tool,
      tag: builtinTools.has(tool) ? '核心工具' : '补充工具',
      desc: builtinTools.has(tool) && recommendedTools.has(tool) ? '同时声明在补充依赖中' : '',
      mcpBindings: mcpBindingsForSkillTool(skill, tool),
    }))
    openStatDetail({
      title: '工具依赖详情',
      subtitle: `Skill：${skillName}`,
      items,
      emptyText: '当前 Skill 未声明工具依赖',
    })
    return
  }
  const items = (skill.examples || []).filter(Boolean).map((example, index) => ({
    label: example,
    tag: `场景 ${index + 1}`,
  }))
  openStatDetail({
    title: '适用场景详情',
    subtitle: `Skill：${skillName}`,
    items,
    emptyText: '当前 Skill 未配置适用场景',
  })
}

function mcpBindingsForSkillTool(skill = {}, tool = '') {
  const toolName = String(tool || '').trim()
  if (!toolName) return []
  const bindings = Array.isArray(skill.mcp_bindings)
    ? skill.mcp_bindings.filter(binding => String(binding?.tool || '').trim() === toolName)
    : []
  if (bindings.length) {
    return bindings.map(binding => {
      const server = mcpServers.value.find(item => String(item.id) === String(binding.id))
      return { ...(server || {}), ...binding, tool: binding.tool || toolName }
    })
  }
  return mcpServers.value
    .filter(server => (server.tool_whitelist || []).some(item => String(item || '').trim() === toolName))
    .map(server => ({ ...server, tool: toolName }))
}

function openCapabilityStatDetail(capability = {}, type) {
  const capabilityName = capability.display_name || capability.code || '--'
  if (type === 'examples') {
    const items = (capability.suggested_questions || []).filter(Boolean).map((example, index) => ({
      label: example,
      tag: `示例 ${index + 1}`,
    }))
    openStatDetail({
      title: '示例入口详情',
      subtitle: `问答类型：${capabilityName}`,
      items,
      emptyText: '当前问答类型未配置示例入口',
    })
    return
  }
  if (type === 'skills') {
    const skillsBySlug = new Map(skills.value.map(item => [item.slug, item]))
    const details = new Map((capability.skill_details || []).map(skill => [skill.slug, skill]))
    const items = Array.from(new Set(capability.skills || [])).filter(Boolean).map((slug) => {
      const skill = { ...(skillsBySlug.get(slug) || {}), ...(details.get(slug) || {}) }
      return {
        label: skill?.name || slug,
        desc: skill?.description || `标识：${slug}`,
        tag: capabilitySkillAvailability(skill),
      }
    })
    openStatDetail({
      title: '挂载 Skill 详情',
      subtitle: `问答类型：${capabilityName} · 已挂载 ${capabilitySkillCount(capability)} / 当前可用 ${capabilityAvailableSkillCount(capability)}`,
      items,
      emptyText: '当前问答类型未挂载 Skill',
    })
    return
  }
  const items = (capability.output_blocks || []).filter(Boolean).map(block => ({
    label: block,
    tag: '输出块',
  }))
  openStatDetail({
    title: '结构化输出详情',
    subtitle: `问答类型：${capabilityName}`,
    items,
    emptyText: '当前问答类型未配置结构化输出块',
  })
}

function formatActionMode(mode) {
  if (mode === 'direct') return 'Direct'
  if (mode === 'react') return 'ReAct'
  if (mode === 'plan_react') return 'Plan+ReAct'
  return mode || '--'
}

function actionModeTagType(mode) {
  if (mode === 'direct') return 'info'
  if (mode === 'plan_react') return 'warning'
  return 'success'
}

function actionRiskLabel(risk) {
  if (risk === 'read_only') return '只读'
  if (risk === 'draft') return '草稿'
  if (risk === 'write') return '写入'
  if (risk === 'execute') return '执行'
  return risk || '--'
}

function actionRiskTagType(risk) {
  if (risk === 'read_only') return 'info'
  if (risk === 'draft') return 'warning'
  if (risk === 'execute') return 'danger'
  return 'warning'
}

function actionAvailabilityLabel(available) {
  return available === false ? '受限' : '可用'
}

function actionAvailabilityTagType(available) {
  return available === false ? 'warning' : 'success'
}

function formatProviderCurrency(currency) {
  return String(currency || '').toUpperCase() === 'CNY' ? '人民币' : '美元'
}

function providerRuntimeTagType(row = {}) {
  if (row.runtime_ready) return 'success'
  return row.is_enabled ? 'warning' : 'info'
}

function providerRuntimeLabel(row = {}) {
  if (row.runtime_ready) return '可用'
  return row.is_enabled ? '待配置' : '停用'
}

function providerRuntimeHint(row = {}) {
  if (row.runtime_ready) return '可作为智能助手运行模型'
  return row.setup_hint || (row.is_enabled ? '请补全模型配置后使用' : '当前已停用，启用后可作为运行模型')
}

function detectProviderPreset(provider = {}) {
  if (provider.provider_preset) return provider.provider_preset
  const normalizedBaseUrl = String(provider.base_url || '').replace(/\/+$/, '').toLowerCase()
  const defaultModel = String(provider.default_model || '').toLowerCase()
  const backupModel = String(provider.backup_model || '').toLowerCase()
  const matchedPreset = providerPresets.value.find((preset) => {
    if (preset.key === 'custom_openai_compatible') return false
    const presetBaseUrl = String(preset.base_url || '').replace(/\/+$/, '').toLowerCase()
    const presetDefaultModel = String(preset.default_model || '').toLowerCase()
    const presetBackupModel = String(preset.backup_model || '').toLowerCase()
    return Boolean(
      (presetBaseUrl && normalizedBaseUrl === presetBaseUrl)
      || (presetDefaultModel && defaultModel === presetDefaultModel)
      || (presetBackupModel && backupModel === presetBackupModel),
    )
  })
  if (matchedPreset) return matchedPreset.key
  const baseUrl = (provider.base_url || '').toLowerCase()
  if (baseUrl.includes('deepseek')) return 'deepseek'
  if (baseUrl.includes('bigmodel') || /^glm-/i.test(provider.default_model || '')) return 'zhipu_glm'
  if (baseUrl.includes('minimax') || /^minimax/i.test(provider.default_model || '')) return 'minimax'
  if (baseUrl.includes('xiaomimimo') || baseUrl.includes('mimo.mi.com')) return 'xiaomi_mimo'
  if (baseUrl.includes('volces.com') || baseUrl.includes('volcengine') || baseUrl.includes('doubao')) return 'volcengine_doubao'
  if (baseUrl.includes('dashscope') || baseUrl.includes('aliyuncs.com') || /^qwen/i.test(provider.default_model || '')) return 'aliyun_qwen'
  if (baseUrl.includes('moonshot') || /^kimi/i.test(provider.default_model || '')) return 'moonshot_kimi'
  if (String(provider.provider_type || '').toLowerCase() === 'openai_compatible') return 'custom_openai_compatible'
  return ''
}

function normalizeProviderList(data) {
  const items = Array.isArray(data) ? data : (Array.isArray(data?.results) ? data.results : [])
  return items.map(item => ({
    ...item,
    provider_preset: detectProviderPreset(item),
  }))
}
function resetMcpForm() {
  Object.keys(mcpForm).forEach(key => delete mcpForm[key])
  mcpAdvanced.value = []
  Object.assign(mcpForm, {
    id: null,
    name: '',
    server_type: 'http',
    endpoint_or_command: '',
    description: '',
    auth_config: {},
    auth_config_text: '{}',
    tool_whitelist: [],
    is_enabled: true,
  })
  mcpToolDiagnostics.value = []
}

function resetSkillForm() {
  Object.keys(skillForm).forEach(key => delete skillForm[key])
  skillAdvanced.value = []
  Object.assign(skillForm, {
    id: null,
    name: '',
    slug: '',
    source_type: 'inline',
    description: '',
    category: '',
    examples: [],
    builtin_tools: [],
    recommended_tools: [],
    max_iterations: 0,
    risk_level: 'read_only',
    output_contract: {},
    output_contract_text: '{}',
    content: '',
    allowed_role_codes: [],
    is_builtin: false,
    is_enabled: true,
  })
}

function resetA2AForm() {
  Object.assign(a2aForm, {
    source_agent: 'web-console',
    title: '',
    action_code: 'slo.analysis',
    input_payload_text: '{\n  "environment": "电商测试环境",\n  "service": "order-service"\n}',
  })
}

function resetRunbookForm() {
  Object.assign(runbookForm, {
    title: '',
    environment: '',
    service: '',
    source_session: '',
    content: '',
    tags: [],
    source_refs_text: '[]',
  })
}

function applyConfig(payload = {}) {
  defaultProviderId.value = payload.default_provider?.id || null
  configuredDefaultProvider.value = payload.default_provider || null
  Object.assign(configForm, {
    system_prompt: payload.system_prompt || '',
    welcome_message: payload.welcome_message || '',
    suggested_questions: [...(payload.suggested_questions || [])],
    enabled_capability_codes: [...(payload.enabled_capability_codes || [])],
    is_enabled: payload.is_enabled ?? true,
    allow_action_execution: payload.allow_action_execution ?? true,
    require_confirmation: true,
    show_evidence: payload.show_evidence ?? true,
    allow_analysis: payload.allow_analysis ?? true,
    max_history_messages: payload.max_history_messages || 12,
  })
  configSnapshot.value = JSON.parse(JSON.stringify(configForm))
}

function resetConfigChanges() {
  if (configSnapshot.value) Object.assign(configForm, JSON.parse(JSON.stringify(configSnapshot.value)))
}

async function optionalLoad(loader, fallback) {
  try {
    return await loader()
  } catch {
    if (typeof fallback === 'function') {
      fallback()
    }
    return null
  }
}

async function refreshConfig() {
  if (configDirty.value) {
    try {
      await ElMessageBox.confirm('刷新将丢弃尚未保存的策略修改，是否继续？', '刷新配置', { confirmButtonText: '刷新', cancelButtonText: '继续编辑', type: 'warning' })
    } catch { return }
  }
  await loadAll()
}

async function reloadProviders() {
  const [providerData, config] = await Promise.all([getAIOpsProviders(), getAIOpsConfig()])
  providers.value = normalizeProviderList(providerData)
  defaultProviderId.value = config.default_provider?.id || null
  configuredDefaultProvider.value = config.default_provider || null
}

async function reloadCapabilities() {
  const data = await getAIOpsCapabilities()
  capabilityRegistry.value = data?.capabilities || []
  capabilityRegistrySummary.value = data?.summary || {}
}
async function reloadAssets() {
  const [mcpData, skillData, marketData] = await Promise.all([getAIOpsMcpServers(), getAIOpsSkills(), getAIOpsSkillMarketplace(), reloadCapabilities()])
  mcpServers.value = mcpData || []
  skills.value = skillData || []
  skillMarketplace.value = marketData || { summary: {}, items: [] }
}

async function loadAll() {
  loading.page = true
  try {
    const [config, providerData, presetData, mcpData, skillData, marketData, capabilityData, mcpManifestData] = await Promise.all([
      getAIOpsConfig(),
      getAIOpsProviders(),
      getAIOpsProviderPresets(),
      getAIOpsMcpServers(),
      getAIOpsSkills(),
      getAIOpsSkillMarketplace(),
      getAIOpsCapabilities(),
      optionalLoad(() => getAIOpsPlatformMcpManifest({ skipErrorMessage: true })),
    ])
    applyConfig(config)
    providerPresets.value = presetData?.presets || []
    providers.value = normalizeProviderList(providerData)
    mcpServers.value = mcpData || []
    skills.value = skillData || []
    skillMarketplace.value = marketData || { summary: {}, items: [] }
    capabilityRegistry.value = capabilityData?.capabilities || []
    capabilityRegistrySummary.value = capabilityData?.summary || {}
    platformMcpManifest.value = mcpManifestData || { tools: [], rate_limit: {} }
    await Promise.all([
      optionalLoad(() => loadA2ATasks(a2aPagination.page, { skipErrorMessage: true }), () => {
        a2aPagination.total = 0
        a2aTasks.value = []
      }),
      optionalLoad(() => loadRunbooks(runbookPagination.page, { skipErrorMessage: true }), () => {
        runbookPagination.total = 0
        runbooks.value = []
      }),
      optionalLoad(() => loadReviewKnowledge(reviewPagination.page, { skipErrorMessage: true }), () => {
        reviewPagination.total = 0
        reviewKnowledge.value = []
      }),
    ])
  } finally {
    loading.page = false
  }
}

async function loadA2ATasks(page = 1, config = {}) {
  try {
    const data = await getAIOpsA2ATasks({ page, page_size: a2aPagination.pageSize }, config)
    a2aPagination.page = page
    a2aPagination.total = data.count || 0
    a2aTasks.value = data.results || data || []
  } catch (error) {
    const message = String(error?.response?.data?.detail || '')
    if (page > 1 && message.includes('无效页面')) {
      return loadA2ATasks(page - 1, config)
    }
    throw error
  }
}

async function loadRunbooks(page = 1, config = {}) {
  try {
    const data = await getAIOpsRunbooks({ page, page_size: runbookPagination.pageSize }, config)
    runbookPagination.page = page
    runbookPagination.total = data.count || 0
    runbooks.value = data.results || data || []
  } catch (error) {
    const message = String(error?.response?.data?.detail || '')
    if (page > 1 && message.includes('无效页面')) {
      return loadRunbooks(page - 1, config)
    }
    throw error
  }
}

async function loadReviewKnowledge(page = 1, config = {}) {
  try {
    const data = await getAIOpsReviewKnowledge({ page, page_size: reviewPagination.pageSize }, config)
    reviewPagination.page = page
    reviewPagination.total = data.count || 0
    reviewKnowledge.value = data.results || data || []
  } catch (error) {
    const message = String(error?.response?.data?.detail || '')
    if (page > 1 && message.includes('无效页面')) {
      return loadReviewKnowledge(page - 1, config)
    }
    throw error
  }
}

async function saveConfig() {
  saving.config = true
  try {
    const saved = await updateAIOpsConfig({ ...configForm, require_confirmation: true })
    applyConfig(saved)
    ElMessage.success('智能体策略已保存')
    await reloadCapabilities()
  } finally {
    saving.config = false
  }
}

async function handleSetDefaultProvider(provider) {
  if (!canManageCapabilities.value || !provider.runtime_ready || selectingProviderId.value !== null) return
  selectingProviderId.value = provider.id
  try {
    const config = await updateAIOpsConfig({ default_provider_id: provider.id })
    defaultProviderId.value = config.default_provider?.id || null
    ElMessage.success(`已将 ${provider.name} 设为默认供应商`)
  } finally {
    selectingProviderId.value = null
  }
}

function openProviderDialog(row) {
  editingProvider.value = row ? { ...row, provider_preset: detectProviderPreset(row) } : null
  providerDialogVisible.value = true
}

async function handleTestProvider(row) {
  try {
    const result = await testAIOpsProvider(row.id)
    ElMessage.success(result.message)
  } catch (error) {
    ElMessage.error(error.response?.data?.message || row.setup_hint || '模型测试失败')
  } finally {
    await reloadProviders()
  }
}

async function handleDeleteProvider(row) {
  await ElMessageBox.confirm(`确认删除模型提供商 ${row.name} 吗？`, '删除确认', { type: 'warning' })
  await deleteAIOpsProvider(row.id)
  ElMessage.success('模型提供商已删除')
  await reloadProviders()
}

function openMcpDialog(row) {
  resetMcpForm()
  if (row) Object.assign(mcpForm, JSON.parse(JSON.stringify(row)), { auth_config_text: JSON.stringify(row.auth_config || {}, null, 2) })
  mcpDialogVisible.value = true
}

async function handleTestMcp(row) {
  const result = await testAIOpsMcpServer(row.id)
  ElMessage.success(result.message || 'MCP 连接成功')
}

async function handleListMcpTools(row) {
  const result = await listAIOpsMcpTools(row.id)
  currentMcpToolsTitle.value = `${row.name} / ${result.count || 0} 个工具`
  mcpToolsList.value = result.tools || []
  mcpToolDiagnostics.value = result.diagnostics || []
  mcpToolsDialogVisible.value = true
}

async function saveMcp() {
  if (!canManageCapabilities.value) return
  saving.mcp = true
  try {
    const payload = { ...mcpForm }
    try {
      payload.auth_config = payload.auth_config_text?.trim() ? JSON.parse(payload.auth_config_text) : {}
    } catch (error) {
      ElMessage.error('鉴权配置不是合法 JSON')
      return
    }
    delete payload.auth_config_text
    if (mcpForm.id) await updateAIOpsMcpServer(mcpForm.id, payload)
    else await createAIOpsMcpServer(payload)
    mcpDialogVisible.value = false
    ElMessage.success('MCP 配置已保存')
    await reloadAssets()
  } finally {
    saving.mcp = false
  }
}

async function handleDeleteMcp(row) {
  await ElMessageBox.confirm(`确认删除 MCP ${row.name} 吗？`, '删除确认', { type: 'warning' })
  await deleteAIOpsMcpServer(row.id)
  ElMessage.success('MCP 已删除')
  await reloadAssets()
}

function openCapabilityDialog(capability) {
  Object.assign(capabilityForm, {
    code: capability.code,
    display_name: capability.display_name || capability.code,
    description: capability.description || '',
    skills: [...(capability.skills || [])],
  })
  capabilityDialogVisible.value = true
}

async function saveCapability() {
  if (!canManageCapabilities.value || !capabilityForm.code) return
  saving.capability = true
  try {
    const capability = await updateAIOpsCapability(capabilityForm.code, { skills: [...capabilityForm.skills] })
    capabilityRegistry.value = capabilityRegistry.value.map(item => item.code === capability.code ? capability : item)
    capabilityDialogVisible.value = false
    ElMessage.success('问答类型 Skill 挂载已保存')
  } finally {
    saving.capability = false
  }
}

function openSkillDialog(row) {
  resetSkillForm()
  if (row) {
    Object.assign(skillForm, {
      ...row,
      examples: Array.isArray(row.examples) ? [...row.examples] : [],
      builtin_tools: Array.isArray(row.builtin_tools) ? [...row.builtin_tools] : [],
      recommended_tools: Array.isArray(row.recommended_tools) ? [...row.recommended_tools] : [],
      allowed_role_codes: Array.isArray(row.allowed_role_codes) ? [...row.allowed_role_codes] : [],
      output_contract: row.output_contract && typeof row.output_contract === 'object' ? row.output_contract : {},
      output_contract_text: JSON.stringify(row.output_contract && typeof row.output_contract === 'object' ? row.output_contract : {}, null, 2),
    })
  }
  skillDialogVisible.value = true
}

async function saveSkill() {
  if (!canManageCapabilities.value) return
  saving.skill = true
  try {
    let outputContract = {}
    try {
      const rawContract = String(skillForm.output_contract_text || '').trim()
      outputContract = rawContract ? JSON.parse(rawContract) : {}
    } catch (error) {
      ElMessage.error('输出约束必须是合法 JSON 对象')
      return
    }
    if (!outputContract || Array.isArray(outputContract) || typeof outputContract !== 'object') {
      ElMessage.error('输出约束必须是 JSON 对象')
      return
    }
    const payload = {
      ...skillForm,
      output_contract: outputContract,
      examples: skillForm.examples || [],
      builtin_tools: skillForm.builtin_tools || [],
      recommended_tools: skillForm.recommended_tools || [],
      allowed_role_codes: skillForm.allowed_role_codes || [],
      max_iterations: Number(skillForm.max_iterations || 0),
    }
    delete payload.output_contract_text
    delete payload.applicable_actions
    delete payload.applicable_capabilities
    delete payload.capability_names
    delete payload.id
    delete payload.is_builtin
    if (skillForm.id) await updateAIOpsSkill(skillForm.id, payload)
    else await createAIOpsSkill(payload)
    skillDialogVisible.value = false
    ElMessage.success('Skill 已保存')
    await reloadAssets()
  } finally {
    saving.skill = false
  }
}

async function handleDeleteSkill(row) {
  await ElMessageBox.confirm(`确认删除 Skill ${row.name} 吗？`, '删除确认', { type: 'warning' })
  await deleteAIOpsSkill(row.id)
  ElMessage.success('Skill 已删除')
  await reloadAssets()
}

function openSkillMarketDialog() {
  skillMarketDialogVisible.value = true
}

async function handleCloneSkill(row) {
  await cloneAIOpsSkill(row.id, {})
  ElMessage.success('已克隆为团队 Skill')
  skillMarketDialogVisible.value = false
  await reloadAssets()
}

function openA2ADialog() {
  resetA2AForm()
  a2aDialogVisible.value = true
}

async function saveA2ATask() {
  let inputPayload = {}
  try {
    inputPayload = a2aForm.input_payload_text?.trim() ? JSON.parse(a2aForm.input_payload_text) : {}
  } catch (error) {
    ElMessage.error('输入参数必须是合法 JSON 对象')
    return
  }
  if (!inputPayload || Array.isArray(inputPayload) || typeof inputPayload !== 'object') {
    ElMessage.error('输入参数必须是 JSON 对象')
    return
  }
  await createAIOpsA2ATask({
    source_agent: a2aForm.source_agent,
    title: a2aForm.title,
    action_code: a2aForm.action_code,
    input_payload: inputPayload,
  })
  a2aDialogVisible.value = false
  ElMessage.success('协同任务草案已创建')
  await loadA2ATasks(1)
}

async function handleCancelA2ATask(row) {
  await ElMessageBox.confirm(`确认取消外部任务《${row.title}》吗？`, '取消确认', { type: 'warning' })
  await cancelAIOpsA2ATask(row.public_id)
  ElMessage.success('协同任务已取消')
  await loadA2ATasks(a2aPagination.page)
}

async function handleRunA2ATask(row) {
  await runAIOpsA2ATask(row.public_id)
  ElMessage.success('多 Agent 编排已完成')
  await loadA2ATasks(a2aPagination.page)
}

async function handleInterruptA2ATask(row) {
  await ElMessageBox.confirm(`确认中断协同任务《${row.title}》吗？`, '中断确认', { type: 'warning' })
  await interruptAIOpsA2ATask(row.public_id)
  ElMessage.success('协同任务已中断')
  await loadA2ATasks(a2aPagination.page)
}

function openRunbookDialog() {
  resetRunbookForm()
  runbookDialogVisible.value = true
}

async function saveRunbookDraft() {
  let sourceRefs = []
  try {
    sourceRefs = runbookForm.source_refs_text?.trim() ? JSON.parse(runbookForm.source_refs_text) : []
  } catch (error) {
    ElMessage.error('引用来源必须是合法 JSON 数组')
    return
  }
  if (!Array.isArray(sourceRefs)) {
    ElMessage.error('引用来源必须是 JSON 数组')
    return
  }
  const payload = {
    title: runbookForm.title,
    environment: runbookForm.environment,
    service: runbookForm.service,
    content: runbookForm.content,
    tags: runbookForm.tags || [],
    source_refs: sourceRefs,
  }
  if (runbookForm.source_session) {
    await createAIOpsRunbookFromSession({
      ...payload,
      source_session: runbookForm.source_session,
    })
  } else {
    await createAIOpsRunbookDraft(payload)
  }
  runbookDialogVisible.value = false
  ElMessage.success('Runbook 手册草案已生成')
  await loadRunbooks(1)
}

async function handlePublishRunbook(row) {
  await publishAIOpsRunbook(row.id, { change_note: '控制台发布' })
  ElMessage.success('Runbook 已发布并自动沉淀复盘知识')
  await Promise.all([loadRunbooks(runbookPagination.page), loadReviewKnowledge(reviewPagination.page)])
}

async function handleArchiveRunbook(row) {
  await ElMessageBox.confirm(`确认归档 Runbook《${row.title}》吗？`, '归档确认', { type: 'warning' })
  await archiveAIOpsRunbook(row.id, { change_note: '控制台归档' })
  ElMessage.success('Runbook 已归档')
  await loadRunbooks(runbookPagination.page)
}

async function handleViewRunbookVersions(row) {
  const data = await getAIOpsRunbookVersions(row.id)
  runbookVersions.value = data || []
  currentRunbookVersionTitle.value = `${row.title} / ${runbookVersions.value.length} 个版本`
  runbookVersionDialogVisible.value = true
}

async function handleDeleteRunbook(row) {
  await ElMessageBox.confirm(`确认删除 Runbook《${row.title}》吗？`, '删除确认', { type: 'warning' })
  await deleteAIOpsRunbook(row.id)
  ElMessage.success('Runbook 手册已删除')
  await loadRunbooks(runbooks.value.length === 1 && runbookPagination.page > 1 ? runbookPagination.page - 1 : runbookPagination.page)
}

async function handleAutoIngestReviewKnowledge(row, type) {
  const payload = {
    title: `${row.title} 复盘知识`,
  }
  if (type === 'task') payload.source_task = row.id
  if (type === 'runbook') payload.source_runbook = row.id
  await autoIngestAIOpsReviewKnowledge(payload)
  ElMessage.success('复盘知识已沉淀')
  await loadReviewKnowledge(1)
}

async function handleDeleteReviewKnowledge(row) {
  await ElMessageBox.confirm(`确认删除复盘知识《${row.title}》吗？`, '删除确认', { type: 'warning' })
  await deleteAIOpsReviewKnowledge(row.id)
  ElMessage.success('复盘知识已删除')
  await loadReviewKnowledge(reviewKnowledge.value.length === 1 && reviewPagination.page > 1 ? reviewPagination.page - 1 : reviewPagination.page)
}

function formatJsonCompact(value) {
  try {
    return JSON.stringify(value || {}, null, 2)
  } catch (error) {
    return String(value || '')
  }
}

onMounted(async () => {
  resetMcpForm()
  resetSkillForm()
  resetA2AForm()
  resetRunbookForm()
  await loadAll()
})
</script>

<style scoped>
.aiops-config-page {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.panel {
  background: linear-gradient(180deg, #ffffff 0%, #fffdf8 100%);
  border: 1px solid rgba(148, 163, 184, 0.16);
  border-radius: 18px;
  box-shadow: 0 12px 28px rgba(15, 23, 42, 0.05);
  padding: 14px 16px;
}

.aiops-config-page :deep(.el-button) {
  border-radius: 10px;
}

.hero-actions :deep(.el-button),
.section-toolbar :deep(.el-button),
.audit-toolbar-actions :deep(.el-button) {
  min-height: 26px;
  padding: 0 9px;
  font-weight: 500;
}

.hero-actions :deep(.el-button:not(.el-button--primary)),
.section-toolbar :deep(.el-button:not(.el-button--primary)),
.audit-toolbar-actions :deep(.el-button:not(.el-button--primary)) {
  border-color: rgba(148, 163, 184, 0.12);
  background: rgba(255, 255, 255, 0.9);
  color: #475569;
  box-shadow: none;
}

.hero-actions :deep(.el-button:not(.is-link):hover),
.section-toolbar :deep(.el-button:not(.is-link):hover),
.audit-toolbar-actions :deep(.el-button:not(.is-link):hover) {
  border-color: rgba(59, 130, 246, 0.18);
  color: #1d4ed8;
  background: #f8fbff;
}

.hero,
.hero-copy,
.hero-title-row,
.hero-actions,
.audit-grid,
.audit-toolbar-actions,
.skill-detail-meta {
  display: flex;
  gap: 8px;
}

.hero {
  min-height: 68px;
  padding: 14px 16px;
  align-items: center;
  justify-content: space-between;
  margin: 0;
  background: linear-gradient(135deg, #fbfdff 0%, #f7faff 52%, #f9fbfd 100%);
  border-color: rgba(36,91,219,.09);
}

.hero.panel {
  border-radius: 20px;
}

.config-refresh-button {
  flex: 0 0 auto;
  align-self: center;
  margin: 0 6px 0 8px;
}

.capability-skill-preview {
  margin-top: 12px;
}

.hero-copy {
  gap: 4px;
}

.hero-title-row {
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
}

.hero-icon {
  width: 42px;
  height: 42px;
  border-radius: 16px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: #245bdb;
  background: #e8f0ff;
}

.hero h2 {
  margin: 0;
  font-size: 23px;
  line-height: 1.1;
  color: #0f172a;
}

.page-inline-desc {
  margin: 0;
  color: #646a73;
  font-size: 13px;
  line-height: 1.45;
}

.hero-actions {
  align-items: center;
  flex-wrap: wrap;
}

.hero-actions :deep(.el-button) {
  min-height: 38px;
  padding: 0 16px;
  border-radius: 12px;
}

.tabs-card {
  display: flex;
  align-items: flex-start;
  width: 100%;
  padding: 3px;
  margin: 0;
  border: 1px solid rgba(148, 163, 184, 0.16);
  border-radius: 12px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.96), rgba(248, 250, 252, 0.9));
  box-shadow: none;
}

.event-like-tabs {
  min-width: 0;
  flex: 1;
  width: 0;
}

.event-like-tabs :deep(.el-tabs__header) {
  margin: 0;
}

.event-like-tabs :deep(.el-tabs__nav-wrap) {
  display: block;
  max-width: 100%;
  padding: 0;
  border: 0;
  border-radius: 0;
  background: transparent;
  box-shadow: none;
}

.event-like-tabs :deep(.el-tabs__nav-wrap::after),
.event-like-tabs :deep(.el-tabs__active-bar),
.event-like-tabs :deep(.el-tabs__content) {
  display: none;
}

.event-like-tabs :deep(.el-tabs__nav-scroll) {
  overflow: visible;
}

.event-like-tabs :deep(.el-tabs__nav) {
  display: flex;
  gap: 8px;
  border: 0;
}

.event-like-tabs :deep(.el-tabs__item) {
  min-height: 38px;
  height: 38px;
  padding: 0 20px !important;
  border-radius: 8px;
  color: #4e5969;
  font-size: 13px;
  font-weight: 700;
  line-height: 38px;
}

.event-like-tabs :deep(.el-tabs__item:hover) {
  background: rgba(51, 112, 255, 0.06);
  color: #245bdb;
}

.event-like-tabs :deep(.el-tabs__item.is-active) {
  background: #e8f0ff;
  color: #245bdb;
  box-shadow: inset 0 0 0 1px rgba(51, 112, 255, 0.08);
}

.tab-label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.tab-label :deep(.el-icon) {
  font-size: 15px;
}

.runtime-note {
  margin: -2px 0 10px;
  color: #64748b;
  font-size: 12px;
  line-height: 1.5;
}

.section-title {
  font-size: 14px;
  font-weight: 700;
  color: #0f172a;
  margin-bottom: 8px;
}

.section-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 8px;
}

.toolbar-actions {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.toolbar-head {
  display: inline-flex;
  align-items: baseline;
  gap: 10px;
  min-width: 0;
}

.toolbar-title {
  color: #0f172a;
  font-size: 14px;
  font-weight: 700;
  line-height: 1.2;
}

.toolbar-desc {
  color: #94a3b8;
  font-size: 12px;
  line-height: 1.4;
}

.provider-strategy-reminder {
  color: #334155;
  font-weight: 700;
}

.strategy-actions {
  margin-top: 0;
}

.dialog-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0 10px;
}

.audit-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
}

.audit-card {
  padding: 16px;
  border-radius: 16px;
  background: linear-gradient(180deg, #f8fafc 0%, #ffffff 100%);
  border: 1px solid #e2e8f0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.audit-card--inline {
  min-height: 68px;
}

.audit-card strong {
  font-size: 24px;
  color: #0f172a;
}

.cost-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
  margin: 8px 0 0;
}

.cost-panel {
  padding: 12px;
  border-radius: 14px;
  background: #ffffff;
  border: 1px solid #e2e8f0;
}

.cost-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.cost-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  color: #64748b;
  font-size: 12px;
}

.cost-row strong {
  color: #0f172a;
  font-weight: 700;
}

.json-preview {
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 260px;
  overflow: auto;
  margin: 0;
  padding: 10px 12px;
  border-radius: 12px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  color: #334155;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
  font-size: 12px;
  line-height: 1.55;
}

.audit-card--info {
  background: linear-gradient(145deg, #eff6ff 0%, #ffffff 100%);
}

.audit-card--success {
  background: linear-gradient(145deg, #ecfdf5 0%, #ffffff 100%);
}

.audit-card--warning {
  background: linear-gradient(145deg, #fffbeb 0%, #ffffff 100%);
}

.audit-card--danger {
  background: linear-gradient(145deg, #fef2f2 0%, #ffffff 100%);
}

.console-table {
  border-radius: 14px;
  overflow: hidden;
  border: 1px solid #e2e8f0;
}

.console-table :deep(th.el-table__cell) {
  background: #f8fafc;
  color: #475569;
  font-weight: 700;
}

.table-actions {
  display: inline-flex;
  align-items: center;
  gap: 2px;
}

.mcp-guard-card {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin: -2px 0 12px 102px;
  padding: 10px 12px;
  border-radius: 12px;
  background: linear-gradient(135deg, #f8fafc, #fff7ed);
  border: 1px solid #e2e8f0;
  color: #64748b;
  font-size: 12px;
  line-height: 1.5;
}

.mcp-guard-card strong {
  color: #0f172a;
  font-size: 13px;
}

.mcp-diagnostic-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 10px;
  padding: 10px;
  border-radius: 12px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
}

.mcp-diagnostic-item {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #475569;
  font-size: 12px;
  line-height: 1.5;
}

.muted-text {
  color: #94a3b8;
}

.mcp-server-panel {
  margin: 10px 0 12px;
  padding: 12px;
  border: 1px solid #e2e8f0;
  border-radius: 14px;
  background: #ffffff;
}

.audit-section {
  margin-top: 12px;
}

.audit-toolbar {
  justify-content: space-between;
  align-items: center;
}

.audit-toolbar-actions {
  align-items: center;
  flex-wrap: wrap;
}

.audit-hint {
  color: #64748b;
  font-size: 12px;
}

.pagination-row {
  display: flex;
  justify-content: flex-end;
  margin-top: 10px;
}

.empty-panel {
  padding: 18px 4px 8px;
}

.empty-copy {
  min-height: 120px;
  padding: 16px 18px;
  border-radius: 14px;
  background: linear-gradient(180deg, #fff 0%, #f8fafc 100%);
  border: 1px dashed rgba(148, 163, 184, 0.35);
  color: #64748b;
  font-size: 13px;
  line-height: 1.8;
}

.skill-summary-row {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
  margin-bottom: 10px;
}

.skill-summary-item {
  min-height: 58px;
  padding: 10px 12px;
  border-radius: 12px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.skill-summary-item span {
  color: #64748b;
  font-size: 12px;
  font-weight: 600;
}

.skill-summary-item strong {
  color: #0f172a;
  font-size: 22px;
  line-height: 1;
}

.skill-library {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.skill-group {
  border: 1px solid #e2e8f0;
  border-radius: 14px;
  background: #ffffff;
  overflow: hidden;
}

.skill-group-head {
  padding: 10px 12px;
  background: #f8fafc;
  border-bottom: 1px solid #e2e8f0;
}

.skill-group-title {
  color: #0f172a;
  font-size: 13px;
  font-weight: 800;
}

.skill-package-list {
  display: flex;
  flex-direction: column;
}

.skill-package-row {
  display: flex;
  align-items: stretch;
  justify-content: space-between;
  gap: 12px;
  padding: 12px;
}

.skill-package-row + .skill-package-row {
  border-top: 1px solid #edf2f7;
}

.skill-package-main {
  min-width: 0;
  flex: 1;
}

.skill-package-title-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
}

.skill-package-name {
  color: #0f172a;
  font-size: 14px;
  font-weight: 800;
  line-height: 1.3;
}

.skill-package-desc {
  margin-top: 6px;
  color: #64748b;
  font-size: 12px;
  line-height: 1.5;
}

.skill-package-tags {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
}

.skill-package-side {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
}

.skill-package-stat {
  width: 48px;
  min-height: 46px;
  border-radius: 12px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 3px;
}

.stat-detail-button {
  padding: 0;
  color: inherit;
  font: inherit;
  text-align: center;
  cursor: pointer;
  transition: border-color 0.18s ease, background 0.18s ease, box-shadow 0.18s ease, transform 0.18s ease;
}

.stat-detail-button:hover {
  border-color: rgba(36, 91, 219, 0.22);
  background: #f8fbff;
  box-shadow: 0 8px 18px rgba(36, 91, 219, 0.06);
  transform: translateY(-1px);
}

.stat-detail-button:focus-visible {
  outline: 2px solid rgba(36, 91, 219, 0.22);
  outline-offset: 2px;
}

.skill-package-stat span {
  color: #94a3b8;
  font-size: 11px;
}

.skill-package-stat strong {
  color: #0f172a;
  font-size: 16px;
  line-height: 1;
}

.action-summary-row {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
  margin-bottom: 10px;
}

.action-summary-item {
  min-height: 58px;
  padding: 10px 12px;
  border-radius: 12px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.action-summary-item span {
  color: #64748b;
  font-size: 12px;
  font-weight: 600;
}

.action-summary-item strong {
  color: #0f172a;
  font-size: 22px;
  line-height: 1;
}

.action-library {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.action-package-row {
  display: flex;
  align-items: stretch;
  justify-content: space-between;
  gap: 12px;
  padding: 12px;
  border: 1px solid #e2e8f0;
  border-radius: 14px;
  background: #ffffff;
}

.action-package-row + .action-package-row {
  border-top: 1px solid #e2e8f0;
}

.action-package-main {
  min-width: 0;
  flex: 1;
}

.action-package-title-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
}

.action-package-name {
  color: #0f172a;
  font-size: 14px;
  font-weight: 800;
  line-height: 1.3;
}

.action-package-code {
  color: #64748b;
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
  font-size: 12px;
  line-height: 1.3;
}

.action-package-desc {
  margin-top: 6px;
  color: #64748b;
  font-size: 12px;
  line-height: 1.5;
}

.mcp-package-endpoint {
  overflow-wrap: anywhere;
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
}

.action-package-tags {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
}

.action-package-side {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
}

.action-package-stat {
  width: 68px;
  min-height: 46px;
  border-radius: 12px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 3px;
}

.action-package-stat span {
  color: #94a3b8;
  font-size: 11px;
}

.action-package-stat strong {
  color: #0f172a;
  font-size: 16px;
  line-height: 1;
}

.action-package-stat small {
  color: #64748b;
  font-size: 10px;
  line-height: 1.2;
}

.stat-detail-subtitle {
  margin: -2px 0 10px;
  color: #64748b;
  font-size: 12px;
  line-height: 1.5;
}

.stat-detail-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 420px;
  overflow: auto;
}

.stat-detail-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 12px;
  border-radius: 12px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
}

.stat-detail-item--tool {
  align-items: flex-start;
}

.stat-detail-main {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.stat-detail-label {
  color: #0f172a;
  font-size: 13px;
  font-weight: 700;
  line-height: 1.45;
  word-break: break-word;
}

.stat-detail-desc {
  color: #64748b;
  font-size: 12px;
  line-height: 1.45;
  word-break: break-word;
}

.stat-detail-mcp {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px dashed rgba(148, 163, 184, 0.36);
}

.stat-detail-mcp-title {
  color: #475569;
  font-size: 11px;
  font-weight: 700;
}

.stat-detail-mcp-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.stat-detail-mcp-card {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 8px 10px;
  border-radius: 9px;
  background: #fff;
  border: 1px solid rgba(148, 163, 184, 0.28);
}

.stat-detail-mcp-head,
.stat-detail-mcp-meta {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
}

.stat-detail-mcp-name {
  color: #0f172a;
  font-size: 12px;
  font-weight: 700;
}

.stat-detail-mcp-meta,
.stat-detail-mcp-desc,
.stat-detail-mcp-empty {
  color: #64748b;
  font-size: 11px;
  line-height: 1.45;
  word-break: break-word;
}

.stat-detail-mcp-empty {
  color: #94a3b8;
}

.stat-detail-empty {
  padding: 18px 12px;
  border-radius: 12px;
  background: #f8fafc;
  border: 1px dashed rgba(148, 163, 184, 0.36);
  color: #94a3b8;
  font-size: 13px;
  text-align: center;
}

.skill-detail-card {
  margin-bottom: 16px;
  padding: 12px 14px;
  border-radius: 14px;
  background: linear-gradient(145deg, #fff7ed 0%, #f8fafc 100%);
  border: 1px solid rgba(148, 163, 184, 0.2);
}

.skill-detail-title {
  font-size: 14px;
  font-weight: 700;
  color: #0f172a;
  margin-bottom: 8px;
}

.skill-detail-meta {
  flex-wrap: wrap;
  color: #475569;
  font-size: 13px;
}

.skill-detail-desc {
  margin-top: 8px;
  color: #64748b;
  font-size: 13px;
  line-height: 1.6;
}

.type-tag {
  border-width: 1px;
}

.type-tag--platform_builtin {
  color: #166534;
  border-color: #86efac;
  background: #f0fdf4;
}

.type-tag--stdio {
  color: #1d4ed8;
  border-color: #93c5fd;
  background: #eff6ff;
}

.type-tag--http {
  color: #92400e;
  border-color: #fcd34d;
  background: #fffbeb;
}

.type-tag--local {
  color: #7c3aed;
  border-color: #c4b5fd;
  background: #f5f3ff;
}

.type-tag--custom {
  color: #0f766e;
  border-color: #99f6e4;
  background: #f0fdfa;
}

@media (max-width: 960px) {
  .audit-grid,
  .skill-summary-row,
  .action-summary-row,
  .dialog-grid {
    grid-template-columns: 1fr;
  }

  .skill-package-row,
  .skill-package-side,
  .action-package-row,
  .action-package-side {
    flex-direction: column;
    align-items: stretch;
  }

  .skill-package-side,
  .action-package-side {
    gap: 8px;
  }

  .skill-package-stat,
  .action-package-stat {
    width: 100%;
    min-height: 42px;
    flex-direction: row;
    justify-content: space-between;
    padding: 0 12px;
  }

}

@media (max-width: 760px) {
  .hero {
    align-items: flex-start;
    flex-direction: column;
  }

  .mcp-guard-card {
    margin-left: 0;
  }
}
</style>



