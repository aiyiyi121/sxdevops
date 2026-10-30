<template>
  <div class="task-center-page">
    <div class="neo-tabs theme-blue log-center-tabs trace-center-tabs event-tabs-shell task-inner-tabs">
      <button
        v-for="tab in innerTabs"
        :key="tab.key"
        type="button"
        class="neo-tab-btn event-tab task-inner-tab-btn"
        :class="{ active: activeTab === tab.key }"
        @click="activeTab = tab.key"
      >
        <el-icon><component :is="tab.icon" /></el-icon>
        <span class="inner-tab-title">{{ tab.label }}</span>
      </button>
    </div>

    <div v-if="activeTab === 'history'" class="audit-grid task-source-grid">
      <button
        v-for="item in sourceCards"
        :key="item.key"
        type="button"
        class="task-source-card"
        :class="[item.cardClass, { 'is-active': taskFilters.trigger_source === item.source && taskFilters.target_type === (item.targetType || '') }]"
        @click="applySourceFilter(item.source, item.targetType || '')"
      >
        <div class="task-source-card__row">
          <span>{{ item.label }}</span>
          <strong>{{ item.value }}</strong>
        </div>
      </button>
    </div>

    <template v-if="activeTab === 'dispatch'">
      <div class="composer-grid">
        <div class="glass-card side-stack">
          <div class="card-head compact-head">
            <span>{{ ui.executionType }}</span>
            <el-tag size="small" type="info">{{ currentExecutionKindLabel }}</el-tag>
          </div>
          <div class="preset-grid execution-type-grid">
            <button
              v-for="option in executionTypeOptions"
              :key="option.value"
              type="button"
              class="preset-card"
              :class="{ active: executionKind === option.value }"
              @click="applyExecutionKind(option.value)"
            >
              <div class="preset-title">{{ option.label }}</div>
              <div class="preset-desc">{{ option.desc }}</div>
            </button>
          </div>
        </div>
        <div class="glass-card">
          <div class="card-head">
            <div class="card-title-with-action">
              <span>{{ ui.createTask }}</span>
              <el-button v-if="executionKind === 'k8s_command'" class="k8s-logic-button" size="small" text type="primary" @click="k8sLogicVisible = true">
                <el-icon><QuestionFilled /></el-icon>
                {{ ui.k8sLogicButton }}
              </el-button>
            </div>
            <div class="task-form-head-actions">
              <el-tag size="small" type="info">{{ ui.selectedTargets }} {{ selectedTargetCount }} {{ ui.unitTarget }}</el-tag>
              <el-button size="small" :loading="savingTemplate" @click="saveCurrentAsTemplate">{{ ui.saveAsTemplate }}</el-button>
              <el-button type="primary" size="small" :loading="submitting" :disabled="!selectedTargetCount" @click="submitTask">
                <el-icon><VideoPlay /></el-icon>
                {{ ui.executeNow }}
              </el-button>
            </div>
          </div>
          <div class="task-inline-tip">{{ taskForm.target_type === 'k8s' ? ui.k8sTip : ui.tip }}</div>
          <el-form :model="taskForm" label-width="88px" class="task-form task-dispatch-form">
            <div class="form-row">
              <el-form-item :label="ui.taskName" class="form-col wide">
                <el-input v-model="taskForm.name" :placeholder="ui.taskNamePlaceholder" />
              </el-form-item>
            </div>
            <div class="form-row">
              <el-form-item :label="ui.executionType" class="form-col">
                <el-select v-model="executionKind" style="width: 100%" @change="applyExecutionKind">
                  <el-option v-for="option in executionTypeOptions" :key="option.value" :label="option.label" :value="option.value" />
                </el-select>
              </el-form-item>
              <el-form-item :label="ui.executionMode" class="form-col">
                <el-select v-model="taskForm.execution_mode" style="width: 100%" :disabled="taskForm.task_type === 'run_playbook' || taskForm.target_type === 'k8s'">
                  <el-option v-for="option in availableExecutionModeOptions" :key="option.value" :label="option.label" :value="option.value" />
                </el-select>
              </el-form-item>
            </div>
            <el-form-item :label="ui.taskDesc">
              <el-input v-model="taskForm.description" :placeholder="ui.taskDescPlaceholder" />
            </el-form-item>
            <div v-if="taskForm.task_type === 'k8s_pod_exec'" class="template-payload-stack">
              <el-form-item :label="ui.script">
                <div class="script-editor-shell">
                  <div class="script-editor-head">
                    <span>K8s</span>
                    <strong>kubectl</strong>
                  </div>
                  <div class="script-editor-body">
                    <pre class="script-editor-highlight" aria-hidden="true" v-html="highlightScript(taskForm.payload.command, 'k8s')" />
                    <textarea v-model="taskForm.payload.command" class="script-editor-textarea" spellcheck="false" placeholder="例如：kubectl get deployment -A" @scroll="syncScriptEditorScroll" />
                  </div>
                </div>
              </el-form-item>
            </div>
            <div v-if="taskForm.target_type === 'host'" class="form-row">
              <el-form-item :label="ui.modeHint" class="form-col">
                <div class="detail-kv compact-kv">{{ executionModeHint(taskForm.execution_mode, taskForm.task_type) }}</div>
              </el-form-item>
            </div>
            <div v-if="taskForm.target_type === 'host' && taskForm.task_type === 'run_command'" class="form-row">
              <el-form-item :label="ui.script" class="form-col wide">
                <div class="script-editor-shell" :class="`script-editor-shell--${executionKind}`">
                  <div class="script-editor-head">
                    <span>{{ scriptEditorTitle }}</span>
                    <strong>{{ scriptEditorLanguage }}</strong>
                  </div>
                  <div class="script-editor-body">
                    <pre class="script-editor-highlight" aria-hidden="true" v-html="highlightScript(taskForm.payload.command, executionKind)" />
                    <textarea v-model="taskForm.payload.command" class="script-editor-textarea" spellcheck="false" :placeholder="executionKind === 'python' ? ui.pythonPlaceholder : ui.commandPlaceholder" @scroll="syncScriptEditorScroll" />
                  </div>
                </div>
              </el-form-item>
            </div>
            <div v-else-if="taskForm.target_type === 'host' && taskForm.task_type === 'run_playbook'" class="template-payload-stack">
              <div class="form-row">
                <el-form-item :label="ui.playbookFileName" class="form-col">
                  <el-input v-model="taskForm.payload.playbook_name" :placeholder="ui.playbookNamePlaceholder" />
                </el-form-item>
                <el-form-item :label="ui.timeout" class="form-col">
                  <el-input-number v-model="taskForm.timeout_seconds" :min="5" :max="120" style="width: 100%" />
                </el-form-item>
              </div>
              <el-form-item :label="ui.script">
                <div class="script-editor-shell script-editor-shell--playbook">
                  <div class="script-editor-head">
                    <span>Ansible Playbook</span>
                    <strong>YAML</strong>
                  </div>
                  <div class="script-editor-body">
                    <pre class="script-editor-highlight" aria-hidden="true" v-html="highlightScript(taskForm.payload.playbook_content, 'playbook')" />
                    <textarea v-model="taskForm.payload.playbook_content" class="script-editor-textarea" spellcheck="false" :placeholder="ui.playbookContentPlaceholder" @scroll="syncScriptEditorScroll" />
                  </div>
                </div>
              </el-form-item>
            </div>
            <div v-if="taskForm.target_type === 'host' && taskForm.task_type !== 'run_playbook'" class="form-row">
              <el-form-item v-if="taskForm.task_type !== 'run_command'" :label="ui.timeout" class="form-col">
                <el-input-number v-model="taskForm.timeout_seconds" :min="5" :max="120" style="width: 100%" />
              </el-form-item>
              <el-form-item :label="taskForm.task_type === 'run_command' ? ui.timeout : ui.strategy" class="form-col">
                <template v-if="taskForm.task_type === 'run_command'">
                  <el-input-number v-model="taskForm.timeout_seconds" :min="5" :max="120" style="width: 100%" />
                </template>
                <template v-else>
                  <el-radio-group v-model="taskForm.execution_strategy">
                    <el-radio label="continue">{{ ui.continueOnError }}</el-radio>
                    <el-radio label="stop_on_error">{{ ui.stopOnError }}</el-radio>
                  </el-radio-group>
                </template>
              </el-form-item>
            </div>
            <div v-if="taskForm.target_type === 'host' && taskForm.task_type === 'run_command'" class="form-row">
              <el-form-item :label="ui.strategy" class="form-col">
                <el-radio-group v-model="taskForm.execution_strategy">
                  <el-radio label="continue">{{ ui.continueOnError }}</el-radio>
                  <el-radio label="stop_on_error">{{ ui.stopOnError }}</el-radio>
                </el-radio-group>
              </el-form-item>
            </div>
            <div v-if="taskForm.target_type === 'host' && taskForm.task_type === 'run_playbook'" class="form-row">
              <el-form-item :label="ui.strategy" class="form-col">
                <el-radio-group v-model="taskForm.execution_strategy">
                  <el-radio label="continue">{{ ui.continueOnError }}</el-radio>
                  <el-radio label="stop_on_error">{{ ui.stopOnError }}</el-radio>
                </el-radio-group>
              </el-form-item>
            </div>
            <template v-if="taskForm.target_type === 'host'">
            <el-divider content-position="left">{{ ui.selectTargets }}</el-divider>
            <div class="toolbar">
              <div class="toolbar-row toolbar-row-main">
                <el-input v-model="targetFilters.search" :placeholder="ui.searchHostPlaceholder" clearable style="width: 220px" @keyup.enter="fetchTargets">
                  <template #prefix><el-icon><Search /></el-icon></template>
                </el-input>
                <el-select v-model="targetFilters.environment" clearable filterable :placeholder="ui.environment" style="width: 140px" @change="handleEnvironmentChange">
                  <el-option v-for="node in envNodes" :key="node.id" :label="node.name" :value="node.id" />
                </el-select>
                <el-select v-model="targetFilters.system" clearable :placeholder="ui.businessLine" style="width: 140px" :disabled="!targetFilters.environment">
                  <el-option v-for="system in currentSystemOptions" :key="system.id" :label="system.name" :value="system.id" />
                </el-select>
                <span class="toolbar-spacer" />
                <el-button size="small" type="primary" plain @click="fetchTargets">{{ ui.queryHosts }}</el-button>
                <el-button size="small" @click="clearSelection">{{ ui.clearSelection }}</el-button>
              </div>
              <div class="toolbar-row toolbar-row-summary">
                <div class="selection-strip">
                  <span class="selection-pill muted">{{ ui.matchedHosts }} {{ availableHosts.length }} {{ ui.unitHost }}</span>
                  <button v-if="effectiveHostTargetRefs.length" type="button" class="selection-pill selection-pill-button" @click="selectedTargetsExpanded = !selectedTargetsExpanded">
                    {{ ui.selectedHosts }} {{ effectiveHostTargetRefs.length }} {{ ui.unitHost }}
                    <el-icon :class="{ 'is-expanded': selectedTargetsExpanded }"><ArrowDown /></el-icon>
                  </button>
                  <span v-else class="selection-pill">{{ ui.selectedHosts }} 0 {{ ui.unitHost }}</span>
                  <span v-if="hasPrefillDraft && !selectedRows.length" class="selection-pill info">{{ prefillSourceLabel }}预填目标</span>
                </div>
                <div v-if="effectiveHostTargetRefs.length && selectedTargetsExpanded" class="selected-target-panel">
                  <div
                    v-for="item in selectedHostPreviewItems"
                    :key="item.key"
                    class="selected-target-item"
                  >
                    <strong>{{ item.name }}</strong>
                    <span>{{ item.meta }}</span>
                  </div>
                </div>
              </div>
            </div>
            <el-table ref="hostTableRef" :data="availableHosts" v-loading="targetLoading" row-key="id" max-height="320" :empty-text="ui.emptyHosts" @selection-change="handleSelectionChange">
              <el-table-column type="selection" width="44" reserve-selection />
              <el-table-column prop="name" :label="ui.hostName" min-width="140" />
              <el-table-column prop="ip_address" :label="ui.ipAddress" width="140" />
              <el-table-column prop="environment_name" :label="ui.environment" width="110" />
              <el-table-column prop="system_name" :label="ui.businessLine" width="120" />
              <el-table-column prop="status_display" :label="ui.status" width="90" />
            </el-table>
            </template>
            <template v-else-if="taskForm.target_type === 'k8s'">
            <el-divider content-position="left">{{ ui.selectTargets }}</el-divider>
            <div class="toolbar">
              <div class="toolbar-row toolbar-row-main">
                <el-input v-model="targetFilters.search" :placeholder="ui.searchK8sPlaceholder" clearable style="width: 220px" @keyup.enter="fetchTargets">
                  <template #prefix><el-icon><Search /></el-icon></template>
                </el-input>
                <el-select v-model="targetFilters.environment" clearable filterable :placeholder="ui.environment" style="width: 140px" @change="handleEnvironmentChange">
                  <el-option v-for="node in envNodes" :key="node.id" :label="node.name" :value="node.id" />
                </el-select>
                <el-select v-model="targetFilters.system" clearable :placeholder="ui.businessLine" style="width: 140px" :disabled="!targetFilters.environment">
                  <el-option v-for="system in currentSystemOptions" :key="system.id" :label="system.name" :value="system.id" />
                </el-select>
                <span class="toolbar-spacer" />
                <el-button size="small" type="primary" plain @click="fetchTargets">{{ ui.queryHosts }}</el-button>
                <el-button size="small" @click="clearSelection">{{ ui.clearSelection }}</el-button>
              </div>
              <div class="toolbar-row toolbar-row-summary">
                <div class="selection-strip">
                  <span class="selection-pill muted">{{ ui.matchedK8s }} {{ availableK8sTargets.length }} {{ ui.unitCluster }}</span>
                  <span class="selection-pill">{{ ui.selectedClusters }} {{ selectedK8sRows.length }} {{ ui.unitCluster }}</span>
                </div>
              </div>
            </div>
            <el-table ref="k8sTargetTableRef" :data="availableK8sTargets" v-loading="targetLoading" row-key="id" max-height="320" :empty-text="ui.emptyK8sTargets" @selection-change="handleK8sSelectionChange">
              <el-table-column type="selection" width="44" reserve-selection />
              <el-table-column prop="name" label="集群" min-width="160" />
              <el-table-column prop="environment_name" :label="ui.environment" width="110" />
              <el-table-column prop="system_name" :label="ui.businessLine" width="120" />
              <el-table-column prop="status_display" :label="ui.status" width="90" />
              <el-table-column prop="description" label="说明" min-width="220" show-overflow-tooltip />
            </el-table>
            </template>
            <div class="submit-row">
              <div class="submit-tip">{{ ui.submitTip }}</div>
            </div>
          </el-form>
        </div>
      </div>
    </template>
    <template v-else-if="activeTab === 'library'">
      <div class="glass-card template-list-card">
        <div class="card-head">
          <span>{{ ui.templateLibrary }}</span>
          <div class="task-form-head-actions">
            <el-button size="small" type="primary" @click="openTemplateCreateDialog">{{ ui.newTemplate }}</el-button>
            <el-button link type="primary" :loading="savingTemplate" @click="saveCurrentAsTemplate">{{ ui.saveCurrentConfig }}</el-button>
          </div>
        </div>
        <div class="section-tip section-gap">{{ ui.templateLibraryTip }}</div>
        <div class="toolbar section-gap template-toolbar">
          <div class="toolbar-left">
            <el-input v-model="templateFilters.search" clearable :placeholder="ui.templateSearchPlaceholder" style="width: 240px">
              <template #prefix><el-icon><Search /></el-icon></template>
            </el-input>
            <el-select v-model="templateFilters.execution_kind" clearable :placeholder="ui.executionType" style="width: 150px">
              <el-option v-for="option in executionTypeOptions" :key="option.value" :label="option.label" :value="option.value" />
            </el-select>
            <el-tag size="small" effect="plain" type="info">{{ ui.templateCount }} {{ filteredTemplates.length }}</el-tag>
          </div>
          <div class="toolbar-right">
            <el-button size="small" @click="resetTemplateFilters">{{ ui.resetFilters }}</el-button>
          </div>
        </div>
        <el-table size="small" :data="filteredTemplates" v-loading="templateLoading" row-key="id" :empty-text="templates.length ? ui.noTemplateMatch : ui.noTemplates">
          <el-table-column prop="name" :label="ui.taskName" min-width="180" show-overflow-tooltip />
          <el-table-column :label="ui.executionType" width="130">
            <template #default="{ row }">
              <el-tag size="small" effect="plain">{{ templateExecutionKindLabel(row) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="description" :label="ui.taskDesc" min-width="240" show-overflow-tooltip />
          <el-table-column :label="ui.executionMode" width="120">
            <template #default="{ row }">{{ executionModeLabel(row.execution_mode, row.execution_mode_display) }}</template>
          </el-table-column>
          <el-table-column :label="ui.strategy" width="110">
            <template #default="{ row }">{{ executionStrategyLabel(row.execution_strategy) }}</template>
          </el-table-column>
          <el-table-column :label="ui.timeout" width="100">
            <template #default="{ row }">{{ row.timeout_seconds }}s</template>
          </el-table-column>
          <el-table-column :label="ui.templateSource" width="90">
            <template #default="{ row }">
              <el-tag size="small" :type="row.is_builtin ? 'success' : 'info'">{{ row.is_builtin ? ui.builtinTemplate : ui.personalTemplate }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column :label="ui.actions" width="190" fixed="right">
            <template #default="{ row }">
              <div class="history-row-actions">
                <el-button link size="small" @click="openTemplateDetail(row)">{{ ui.viewTemplate }}</el-button>
                <el-button link type="primary" size="small" @click="applyTemplate(row)">{{ ui.applyTemplate }}</el-button>
                <el-dropdown v-if="!row.is_builtin" trigger="click" @command="command => handleTemplateAction(command, row)">
                  <el-button text size="small" class="history-more-btn">更多</el-button>
                  <template #dropdown>
                    <el-dropdown-menu>
                      <el-dropdown-item command="edit">{{ ui.editTemplate }}</el-dropdown-item>
                      <el-dropdown-item command="delete">{{ ui.deleteTemplate }}</el-dropdown-item>
                    </el-dropdown-menu>
                  </template>
                </el-dropdown>
              </div>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </template>
    <template v-else>
      <div class="glass-card history-card">
        <div class="card-head history-head">
          <span>{{ ui.history }}</span>
          <div class="history-actions">
            <el-tag size="small" type="info">{{ ui.selectedTasks }} {{ selectedCancelableTaskIds.length }} {{ ui.unitTask }}</el-tag>
            <el-button size="small" :disabled="!selectedCancelableTaskIds.length" @click="handleBatchCancel">{{ ui.batchCancel }}</el-button>
            <el-button size="small" @click="resetTaskFilters">{{ ui.resetFilters }}</el-button>
          </div>
        </div>
        <div class="toolbar history-toolbar">
          <div class="toolbar-left">
            <el-input v-model="taskFilters.search" clearable :placeholder="ui.searchTaskPlaceholder" style="width: 220px" @keyup.enter="fetchTasks">
              <template #prefix><el-icon><Search /></el-icon></template>
            </el-input>
            <el-select v-model="taskFilters.execution_kind" clearable :placeholder="ui.executionType" style="width: 140px" @change="fetchTasks">
              <el-option v-for="option in executionTypeOptions" :key="option.value" :label="option.label" :value="option.value" />
            </el-select>
            <el-select v-model="taskFilters.target_type" clearable :placeholder="ui.targetType" style="width: 120px" @change="fetchTasks">
              <el-option v-for="option in targetTypeOptions" :key="option.value" :label="option.label" :value="option.value" />
            </el-select>
            <el-select v-model="taskFilters.status" clearable :placeholder="ui.result" style="width: 120px" @change="fetchTasks">
              <el-option v-for="option in taskStatusOptions" :key="option.value" :label="option.label" :value="option.value" />
            </el-select>
            <el-select v-model="taskFilters.trigger_source" clearable :placeholder="ui.triggerSource" style="width: 130px" @change="fetchTasks">
              <el-option v-for="option in triggerSourceOptions" :key="option.value" :label="option.label" :value="option.value" />
            </el-select>
            <el-select v-model="taskFilters.risk_level" clearable :placeholder="ui.riskLevel" style="width: 110px" @change="fetchTasks">
              <el-option v-for="option in riskLevelOptions" :key="option.value" :label="option.label" :value="option.value" />
            </el-select>
          </div>
        </div>
        <el-table size="small" :data="tasks" v-loading="taskLoading" row-key="id" :empty-text="ui.emptyTasks" @selection-change="handleTaskHistorySelectionChange">
          <el-table-column type="selection" width="36" reserve-selection />
          <el-table-column :label="ui.taskName" min-width="220">
            <template #default="{ row }">
              <div class="history-name-cell">
                <button type="button" class="history-name-button" @click="openDetail(row)">
                  <strong>{{ row.name }}</strong>
                </button>
                <div class="history-name-meta">
                  <span>{{ row.target_type_display || ui.hostResource }}</span>
                  <span>{{ row.trigger_source_display || '-' }}</span>
                  <span>{{ row.risk_level_display || '-' }}</span>
                </div>
              </div>
            </template>
          </el-table-column>
          <el-table-column prop="environment_display" :label="ui.environment" width="112" show-overflow-tooltip />
          <el-table-column :label="ui.executionType" width="108">
            <template #default="{ row }">{{ templateExecutionKindLabel(row) }}</template>
          </el-table-column>
          <el-table-column prop="created_by" :label="ui.executor" width="86" show-overflow-tooltip />
          <el-table-column prop="target_count" :label="ui.targetCount" width="72" />
          <el-table-column :label="ui.result" width="112">
            <template #default="{ row }"><el-tag size="small" :type="taskStatusType(row.status)">{{ row.lifecycle_status_display || row.status_display }}</el-tag></template>
          </el-table-column>
          <el-table-column :label="ui.finishedAt" width="150">
            <template #default="{ row }">{{ formatDateTime(row.finished_at || row.created_at) }}</template>
          </el-table-column>
          <el-table-column :label="ui.actions" width="172" fixed="right">
            <template #default="{ row }">
              <div class="history-row-actions">
                <el-button link type="primary" size="small" @click="openDetail(row)">{{ ui.detail }}</el-button>
                <el-button v-if="canExecuteTask(row)" link type="success" size="small" @click="handleExecuteTask(row)">{{ ui.startTask }}</el-button>
                <el-button v-else link type="warning" size="small" :disabled="row.status === 'running'" @click="handleRerun(row)">{{ ui.rerun }}</el-button>
                <el-dropdown trigger="click" @command="command => handleHistoryAction(command, row)">
                  <el-button text size="small" class="history-more-btn">更多</el-button>
                  <template #dropdown>
                    <el-dropdown-menu>
                      <el-dropdown-item command="rename">{{ ui.renameTask }}</el-dropdown-item>
                      <el-dropdown-item command="copy">{{ ui.copyToDraft }}</el-dropdown-item>
                      <el-dropdown-item command="template">{{ ui.saveAsTemplate }}</el-dropdown-item>
                      <el-dropdown-item v-if="canCancelTask(row)" command="cancel">{{ ui.cancelTask }}</el-dropdown-item>
                      <el-dropdown-item :divided="canCancelTask(row)" command="delete" :disabled="!canDeleteTask(row)">{{ ui.deleteTask }}</el-dropdown-item>
                    </el-dropdown-menu>
                  </template>
                </el-dropdown>
              </div>
            </template>
          </el-table-column>
        </el-table>
        <div class="pagination-row">
          <el-pagination v-model:current-page="taskPage" :page-size="20" :total="taskTotal" layout="total, prev, pager, next" @current-change="fetchTasks" />
        </div>
      </div>
    </template>
    <el-dialog top="5vh" :close-on-click-modal="false" class="workbench-edit-dialog" v-model="templateCreateVisible" :title="templateDialogTitle" width="980px" destroy-on-close append-to-body>
      <div class="template-editor-topbar">
        <div class="section-tip">{{ ui.templateEditorTip }}</div>
      </div>
      <div class="template-editor-overview">
        <div class="template-overview-card">
          <span class="template-overview-label">{{ ui.executionType }}</span>
          <strong>{{ templateDraftTypeLabel }}</strong>
        </div>
        <div class="template-overview-card">
          <span class="template-overview-label">{{ ui.executionMode }}</span>
          <strong>{{ executionModeLabel(templateDraft.execution_mode) }}</strong>
        </div>
        <div class="template-overview-card">
          <span class="template-overview-label">{{ ui.timeout }}</span>
          <strong>{{ templateDraft.timeout_seconds }}s</strong>
        </div>
      </div>
      <div class="template-editor-layout">
        <div class="template-editor-panel template-editor-main">
          <el-form label-position="top" :model="templateDraft" label-width="92px" class="task-form">
            <div class="template-editor-section">
              <div class="template-editor-section-title">{{ ui.editorBasicInfo }}</div>
              <div class="form-row">
                <el-form-item :label="ui.taskName" class="form-col">
                  <el-input v-model="templateDraft.name" :placeholder="ui.taskNamePlaceholder" />
                </el-form-item>
                <el-form-item :label="ui.executionType" class="form-col">
                  <el-select v-model="templateExecutionKind" style="width: 100%" @change="handleTemplateExecutionKindChange">
                    <el-option v-for="option in executionTypeOptions" :key="option.value" :label="option.label" :value="option.value" />
                  </el-select>
                </el-form-item>
              </div>
              <el-form-item :label="ui.taskDesc">
                <el-input v-model="templateDraft.description" type="textarea" :rows="3" :placeholder="ui.taskDescPlaceholder" />
              </el-form-item>
            </div>
            <div class="template-editor-section">
              <div class="template-editor-section-title">{{ ui.editorExecution }}</div>
              <div class="form-row">
                <el-form-item :label="ui.executionMode" class="form-col">
                  <el-select v-model="templateDraft.execution_mode" style="width: 100%" :disabled="templateDraft.task_type === 'run_playbook' || templateDraft.target_type === 'k8s'">
                    <el-option v-for="option in availableTemplateExecutionModeOptions" :key="option.value" :label="option.label" :value="option.value" />
                  </el-select>
                </el-form-item>
                <el-form-item :label="ui.modeHint" class="form-col">
                  <div class="detail-kv compact-kv">{{ executionModeHint(templateDraft.execution_mode, templateDraft.task_type) }}</div>
                </el-form-item>
              </div>
              <div v-if="templateDraft.task_type !== 'run_command' && templateDraft.task_type !== 'run_playbook'" class="form-row">
                <el-form-item :label="ui.timeout" class="form-col">
                  <el-input-number v-model="templateDraft.timeout_seconds" :min="5" :max="120" style="width: 100%" />
                </el-form-item>
                <el-form-item :label="ui.strategy" class="form-col">
                  <el-radio-group v-model="templateDraft.execution_strategy">
                    <el-radio label="continue">{{ ui.continueOnError }}</el-radio>
                    <el-radio label="stop_on_error">{{ ui.stopOnError }}</el-radio>
                  </el-radio-group>
                </el-form-item>
              </div>
            </div>
            <div class="template-editor-section">
              <div class="template-editor-section-title">{{ ui.editorPayload }}</div>
              <div v-if="templateDraft.task_type === 'run_command'" class="template-payload-stack">
                <el-form-item :label="ui.script" class="form-col wide">
                  <div class="script-editor-shell" :class="`script-editor-shell--${templateExecutionKind}`">
                    <div class="script-editor-head">
                      <span>{{ templateScriptEditorTitle }}</span>
                      <strong>{{ templateScriptEditorLanguage }}</strong>
                    </div>
                    <div class="script-editor-body">
                      <pre class="script-editor-highlight" aria-hidden="true" v-html="highlightScript(templateDraft.payload.command, templateExecutionKind)" />
                      <textarea v-model="templateDraft.payload.command" class="script-editor-textarea" spellcheck="false" :placeholder="templateExecutionKind === 'python' ? ui.pythonPlaceholder : ui.commandPlaceholder" @scroll="syncScriptEditorScroll" />
                    </div>
                  </div>
                </el-form-item>
                <div class="form-row">
                  <el-form-item :label="ui.timeout" class="form-col">
                    <el-input-number v-model="templateDraft.timeout_seconds" :min="5" :max="120" style="width: 100%" />
                  </el-form-item>
                  <el-form-item :label="ui.strategy" class="form-col">
                    <el-radio-group v-model="templateDraft.execution_strategy">
                      <el-radio label="continue">{{ ui.continueOnError }}</el-radio>
                      <el-radio label="stop_on_error">{{ ui.stopOnError }}</el-radio>
                    </el-radio-group>
                  </el-form-item>
                </div>
              </div>
              <div v-else-if="templateDraft.task_type === 'run_playbook'" class="template-payload-stack">
                <div class="form-row">
                  <el-form-item :label="ui.playbookName" class="form-col">
                    <el-input v-model="templateDraft.payload.playbook_name" :placeholder="ui.playbookNamePlaceholder" />
                  </el-form-item>
                  <el-form-item :label="ui.timeout" class="form-col">
                    <el-input-number v-model="templateDraft.timeout_seconds" :min="5" :max="120" style="width: 100%" />
                  </el-form-item>
                </div>
                <el-form-item :label="ui.script">
                  <div class="script-editor-shell script-editor-shell--playbook">
                    <div class="script-editor-head">
                      <span>Ansible Playbook</span>
                      <strong>YAML</strong>
                    </div>
                    <div class="script-editor-body">
                      <pre class="script-editor-highlight" aria-hidden="true" v-html="highlightScript(templateDraft.payload.playbook_content, 'playbook')" />
                      <textarea v-model="templateDraft.payload.playbook_content" class="script-editor-textarea" spellcheck="false" :placeholder="ui.playbookContentPlaceholder" @scroll="syncScriptEditorScroll" />
                    </div>
                  </div>
                </el-form-item>
                <el-form-item :label="ui.strategy">
                  <el-radio-group v-model="templateDraft.execution_strategy">
                    <el-radio label="continue">{{ ui.continueOnError }}</el-radio>
                    <el-radio label="stop_on_error">{{ ui.stopOnError }}</el-radio>
                  </el-radio-group>
                </el-form-item>
              </div>
              <div v-else-if="templateDraft.task_type === 'k8s_pod_exec'" class="template-payload-stack">
                <el-form-item :label="ui.script" class="form-col wide">
                  <div class="script-editor-shell">
                    <div class="script-editor-head">
                      <span>K8s</span>
                      <strong>kubectl</strong>
                    </div>
                    <div class="script-editor-body">
                      <pre class="script-editor-highlight" aria-hidden="true" v-html="highlightScript(templateDraft.payload.command, 'k8s')" />
                      <textarea v-model="templateDraft.payload.command" class="script-editor-textarea" spellcheck="false" placeholder="例如：kubectl get deployment -A" @scroll="syncScriptEditorScroll" />
                    </div>
                  </div>
                </el-form-item>
                <div class="task-inline-tip">{{ ui.k8sTip }}</div>
              </div>
              <div v-else class="detail-kv">{{ ui.noExtraParams }}</div>
            </div>
          </el-form>
        </div>
        <div class="template-editor-side">
          <div class="template-editor-panel template-editor-preview">
            <div class="card-head compact-head">
              <span>{{ ui.previewTemplate }}</span>
              <el-tag size="small" effect="plain">{{ templateDraftTypeLabel }}</el-tag>
            </div>
            <div class="detail-summary">
              <div class="detail-chip">{{ ui.executionMode }}: {{ executionModeLabel(templateDraft.execution_mode) }}</div>
              <div class="detail-chip">{{ ui.strategy }}: {{ executionStrategyLabel(templateDraft.execution_strategy) }}</div>
              <div class="detail-chip">{{ ui.timeout }}: {{ templateDraft.timeout_seconds }}</div>
            </div>
            <div class="detail-section">
              <div class="detail-section-title">{{ ui.templatePayload }}</div>
              <pre v-if="templateDraft.task_type === 'run_command'" class="detail-code-block">{{ templateDraft.payload.command || '-' }}</pre>
              <template v-else-if="templateDraft.task_type === 'run_playbook'">
                <div class="detail-kv">{{ ui.playbookName }}: {{ templateDraft.payload.playbook_name || '-' }}</div>
                <pre class="detail-code-block template-code-block">{{ templateDraft.payload.playbook_content || '-' }}</pre>
              </template>
              <pre v-else-if="templateDraft.task_type === 'k8s_pod_exec'" class="detail-code-block">{{ templateDraft.payload.command || '-' }}</pre>
              <div v-else class="detail-kv">{{ ui.noExtraParams }}</div>
            </div>
            <div class="detail-section">
              <div class="detail-section-title">{{ ui.taskDesc }}</div>
              <div class="detail-kv">{{ templateDraft.description || ui.emptyDesc }}</div>
            </div>
          </div>
          <div class="template-editor-panel template-editor-help">
            <div class="card-head compact-head">
              <span>{{ ui.editorAdvice }}</span>
            </div>
            <div v-for="item in templateEditorAdvice" :key="item" class="mini-bullet">{{ item }}</div>
          </div>
        </div>
      </div>
      <template #footer>
        <div class="detail-actions">
          <el-button @click="templateCreateVisible = false">{{ ui.close }}</el-button>
          <el-button type="primary" :loading="creatingTemplate" @click="submitTemplateDraft">{{ templateDialogSubmitText }}</el-button>
        </div>
      </template>
    </el-dialog>
    <el-drawer v-model="templateDetailVisible" class="task-center-drawer" :title="ui.templateDetailTitle" size="42%" append-to-body>
      <template v-if="currentTemplate">
        <div class="detail-summary">
          <div class="detail-chip"><strong>{{ currentTemplate.name }}</strong></div>
          <div class="detail-chip">{{ templateExecutionKindLabel(currentTemplate) }}</div>
          <div class="detail-chip">{{ ui.executionMode }}: {{ executionModeLabel(currentTemplate.execution_mode, currentTemplate.execution_mode_display) }}</div>
          <div class="detail-chip">{{ ui.strategy }}: {{ executionStrategyLabel(currentTemplate.execution_strategy) }}</div>
          <div class="detail-chip">{{ ui.timeout }}: {{ currentTemplate.timeout_seconds }}</div>
          <div class="detail-chip">{{ ui.creator }}: {{ currentTemplate.created_by || '-' }}</div>
          <div class="detail-chip">{{ currentTemplate.is_builtin ? ui.builtinTemplate : ui.personalTemplate }}</div>
        </div>
        <div class="detail-desc">{{ currentTemplate.description || ui.emptyDesc }}</div>
        <div class="detail-section">
          <div class="detail-section-title">{{ ui.templatePayload }}</div>
          <pre v-if="currentTemplate.task_type === 'run_command'" class="detail-code-block">{{ currentTemplate.payload?.command || '-' }}</pre>
          <template v-else-if="currentTemplate.task_type === 'run_playbook'">
            <div class="detail-kv">{{ ui.playbookName }}: {{ currentTemplate.payload?.playbook_name || '-' }}</div>
            <pre class="detail-code-block template-code-block">{{ currentTemplate.payload?.playbook_content || '-' }}</pre>
          </template>
          <pre v-else-if="currentTemplate.task_type === 'k8s_pod_exec'" class="detail-code-block">{{ currentTemplate.payload?.command || '-' }}</pre>
          <div v-else class="detail-kv">{{ ui.noExtraParams }}</div>
        </div>
        <div v-if="Object.keys(currentTemplate.payload || {}).length" class="detail-section">
          <div class="detail-section-title">{{ ui.templatePayload }} JSON</div>
          <pre class="detail-code-block">{{ formatPayloadJson(currentTemplate.payload) }}</pre>
        </div>
        <div class="detail-kv">{{ ui.createdAt }}: {{ formatDateTime(currentTemplate.created_at) }}</div>
        <div class="detail-actions">
          <el-button @click="templateDetailVisible = false">{{ ui.close }}</el-button>
          <el-button v-if="!currentTemplate.is_builtin" @click="openTemplateEditDialog(currentTemplate)">{{ ui.editTemplate }}</el-button>
          <el-button type="primary" @click="applyTemplate(currentTemplate)">{{ ui.applyTemplate }}</el-button>
        </div>
      </template>
    </el-drawer>
    <el-drawer v-model="detailVisible" class="task-center-drawer" :title="ui.detailTitle" size="68%" append-to-body>
      <div v-loading="detailLoading" class="task-detail-shell">
        <template v-if="detailTask">
          <div class="detail-heading">
            <div class="detail-heading-main">
              <div class="detail-title-row">
                <strong class="detail-main-title">{{ detailTask.name }}</strong>
                <el-tag size="small" :type="taskStatusType(detailTask.status)">{{ detailTask.lifecycle_status_display || detailTask.status_display }}</el-tag>
              </div>
              <div class="detail-subline">
                <span>{{ detailTask.task_type_display }}</span>
                <span>{{ executionModeLabel(detailTask.execution_mode, detailTask.execution_mode_display) }}</span>
                <span>{{ ui.executor }}: {{ detailTask.created_by || '-' }}</span>
                <span>{{ formatDateTime(detailTask.created_at) }}</span>
              </div>
            </div>
            <div class="detail-summary compact">
              <div class="detail-chip">{{ detailTask.target_type_display || ui.hostResource }}</div>
              <div class="detail-chip">{{ ui.riskLevel }}: {{ detailTask.risk_level_display || '-' }}</div>
              <div class="detail-chip">{{ ui.successRate }}: {{ detailTask.success_rate }}%</div>
              <div class="detail-chip">{{ ui.targetCount }}: {{ detailTask.target_count || 0 }}</div>
            </div>
          </div>
          <div class="task-metric-grid compact">
            <div class="task-metric-card">
              <span class="task-metric-label">{{ ui.targetCount }}</span>
              <strong>{{ detailTask.target_count || 0 }}</strong>
            </div>
            <div class="task-metric-card success">
              <span class="task-metric-label">{{ ui.success }}</span>
              <strong>{{ detailTask.success_count || 0 }}</strong>
            </div>
            <div class="task-metric-card danger">
              <span class="task-metric-label">{{ ui.failed }}</span>
              <strong>{{ detailTask.failed_count || 0 }}</strong>
            </div>
            <div class="task-metric-card warning">
              <span class="task-metric-label">{{ ui.skipped }}</span>
              <strong>{{ detailTask.skipped_count || 0 }}</strong>
            </div>
          </div>
          <div class="detail-grid compact">
            <div class="detail-section">
              <div class="detail-section-title">{{ ui.summary }}</div>
              <div class="detail-kv">{{ detailTask.summary || detailTask.description || ui.emptyDesc }}</div>
              <div class="detail-kv compact-stack">
                <span>{{ ui.strategy }}: {{ executionStrategyLabel(detailTask.execution_strategy) }}</span>
                <span>{{ ui.timeout }}: {{ detailTask.timeout_seconds || 0 }}s</span>
                <span>{{ ui.triggerSource }}: {{ detailTask.trigger_source_display || '-' }}</span>
                <span>{{ ui.startedAt }}: {{ formatDateTime(detailTask.started_at) }}</span>
                <span>{{ ui.finishedAt }}: {{ formatDateTime(detailTask.finished_at) }}</span>
              </div>
              <div v-if="detailTask.cancel_requested" class="detail-kv danger-text">{{ ui.cancelRequestedBy }}: {{ detailTask.cancel_requested_by || '-' }} | {{ ui.cancelRequestedAt }}: {{ formatDateTime(detailTask.cancel_requested_at) }}</div>
            </div>
            <div class="detail-section">
              <div class="detail-section-title">{{ detailTask.target_type === 'k8s' ? ui.targetResources : ui.targetHosts }}</div>
              <div v-if="detailTask.target_snapshot?.length" class="target-list">
                <div v-for="host in detailTask.target_snapshot" :key="`${detailTask.id}-${host.id || host.hostname}`" class="target-list-item">
                  <strong>{{ targetSnapshotPrimaryName(host, detailTask.target_type) }}</strong>
                  <span>{{ targetSnapshotMeta(host, detailTask.target_type) }}</span>
                  <span v-if="host.namespace">{{ host.namespace }}</span>
                </div>
              </div>
              <div v-else class="detail-kv">{{ ui.emptyTargets }}</div>
            </div>
          </div>
          <div v-if="Object.keys(detailTask.payload || {}).length" class="detail-section">
            <div class="detail-section-title">{{ detailTask.task_type === 'run_playbook' ? ui.playbookContent : (detailTask.task_type === 'run_command' ? ui.command : `${ui.taskPayload} JSON`) }}</div>
            <template v-if="detailTask.task_type === 'run_playbook'">
              <div class="detail-kv">{{ ui.playbookName }}: {{ detailTask.payload?.playbook_name || '-' }}</div>
              <pre class="detail-code-block template-code-block yaml-code-block">{{ formatMultilineContent(detailTask.payload?.playbook_content) }}</pre>
            </template>
            <pre v-else-if="detailTask.task_type === 'run_command'" class="detail-code-block">{{ formatMultilineContent(detailTask.payload?.command) }}</pre>
            <pre v-else class="detail-code-block">{{ formatPayloadJson(detailTask.payload) }}</pre>
          </div>
          <div class="detail-section">
            <div class="detail-section-title">{{ ui.executionDetails }}</div>
            <div class="execution-progress-card">
              <div class="execution-progress-head">
                <strong>{{ ui.executionProgress }}</strong>
                <span>{{ executionProgressSummary }}</span>
              </div>
              <el-progress :percentage="executionProgressPercent" :status="executionProgressStatus" :stroke-width="8" />
            </div>
            <el-table :data="detailTask.executions || []" max-height="520" :empty-text="ui.emptyExecutions">
              <el-table-column :label="ui.targetResource" min-width="180">
                <template #default="{ row }">
                  <div class="execution-target-cell">
                    <strong>{{ executionTargetName(row) }}</strong>
                    <span v-if="executionTargetMeta(row)">{{ executionTargetMeta(row) }}</span>
                  </div>
                </template>
              </el-table-column>
              <el-table-column :label="ui.status" width="88">
                <template #default="{ row }"><el-tag size="small" :type="executionStatusType(row.status)">{{ row.status_display }}</el-tag></template>
              </el-table-column>
              <el-table-column :label="ui.duration" width="92">
                <template #default="{ row }">{{ formatExecutionDuration(row) }}</template>
              </el-table-column>
              <el-table-column :label="ui.output" min-width="560">
                <template #default="{ row }">
                  <div class="output-preview-card" @click="openExecutionOutput(row)">
                    <div class="output-preview-text">{{ previewExecutionOutput(row) }}</div>
                    <el-button link type="primary" size="small" class="output-preview-action">{{ ui.viewOutput }}</el-button>
                  </div>
                </template>
              </el-table-column>
            </el-table>
          </div>
        </template>
      </div>
    </el-drawer>
    <el-dialog v-model="outputDialogVisible" :title="outputDialogTitle" width="860px" append-to-body destroy-on-close align-center>
      <pre class="output-dialog-block">{{ outputDialogContent || '-' }}</pre>
    </el-dialog>
    <el-dialog v-model="k8sLogicVisible" :title="ui.k8sLogicTitle" width="640px" append-to-body destroy-on-close align-center>
      <div class="k8s-logic-panel">
        <div v-for="item in k8sLogicItems" :key="item.title" class="k8s-logic-item">
          <strong>{{ item.title }}</strong>
          <span>{{ item.desc }}</span>
        </div>
      </div>
      <template #footer>
        <el-button type="primary" @click="k8sLogicVisible = false">{{ ui.close }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>
<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowDown, Clock, Collection, Promotion, QuestionFilled, Search, VideoPlay } from '@element-plus/icons-vue'
import { useRouteTabState } from '@/composables/useRouteTabState'
import { normalizeTaskDraftTitle } from '@/utils/taskDraftTitle'
import {
  batchCancelHostTasks,
  cancelHostTask,
  createHostTask,
  createHostTaskTemplate,
  deleteHostTask,
  updateHostTaskTemplate,
  deleteHostTaskTemplate,
  executeHostTask,
  getHostTask,
  getHostTaskStats,
  getTaskResourceOptions,
  getHostTaskTemplates,
  getHostTasks,
  renameHostTask,
  rerunHostTask,
} from '@/api/modules/ops'
const route = useRoute()
const router = useRouter()
const TASK_DRAFT_STORAGE_KEY = 'sxdevops.task-center.prefill-draft'
const ui = {

  tip: '\u4efb\u52a1\u4e2d\u5fc3\u9002\u5408\u6279\u91cf\u5de1\u68c0\u3001\u7edf\u4e00\u5237\u65b0\u4e0e\u547d\u4ee4\u5206\u53d1\uff1b\u5f53\u524d\u4e3a\u4e32\u884c\u6267\u884c\uff0c\u5efa\u8bae\u5355\u6b21\u63a7\u5236\u5728 20 \u53f0\u4ee5\u5185\u3002',
  presets: '\u4efb\u52a1\u7c7b\u578b',
  quickStart: '\u5feb\u901f\u8d77\u6b65',
  dispatchAdvice: '\u4e0b\u53d1\u5efa\u8bae',
  templateLibrary: '\u6a21\u677f\u5e93',
  templateLibraryTip: '将常用巡检、变更和诊断编排沉淀为模板；任务执行类型只保留 Shell、Python、Ansible Playbook 和 K8s API。',
  commandLibrary: '\u5e38\u7528\u547d\u4ee4\u5e93',
  commandTip: '\u5efa\u8bae\u5148\u5728\u6d4b\u8bd5\u73af\u5883\u9a8c\u8bc1',
  libraryAdvice: '\u6a21\u677f\u6cbb\u7406\u5efa\u8bae',
  newTemplate: '\u65b0\u589e\u6a21\u677f',
  editTemplate: '\u7f16\u8f91',
  saveCurrentConfig: '\u4fdd\u5b58\u5f53\u524d\u914d\u7f6e',
  viewTemplate: '\u67e5\u770b\u8be6\u60c5',
  templateEditorTip: '选择基础执行类型后填写脚本或 Playbook 内容，具体巡检/变更动作通过模板名称和参数表达。',
  templateQuickFill: '\u5feb\u6377\u586b\u5145',
  editorBasicInfo: '\u57fa\u7840\u4fe1\u606f',
  editorExecution: '\u6267\u884c\u7b56\u7565',
  editorPayload: '\u6267\u884c\u5185\u5bb9',
  editorAdvice: '\u7f16\u6392\u5efa\u8bae',
  previewTemplate: '\u6a21\u677f\u9884\u89c8',
  templateCount: '\u6a21\u677f\u6570',
  templateSearchPlaceholder: '\u641c\u7d22\u6a21\u677f\u540d\u79f0 / \u8bf4\u660e',
  noTemplateMatch: '\u6682\u65e0\u5339\u914d\u6a21\u677f',
  createTemplateTitle: '\u65b0\u589e\u4efb\u52a1\u6a21\u677f',
  editTemplateTitle: '\u7f16\u8f91\u4efb\u52a1\u6a21\u677f',
  createTemplateSubmit: '\u521b\u5efa',
  updateTemplateSubmit: '\u4fdd\u5b58',
  templateDetailTitle: '\u6a21\u677f\u8be6\u60c5',
  templatePayload: '\u6a21\u677f\u53c2\u6570',
  serviceDetail: '\u670d\u52a1\u540d\u79f0',
  noExtraParams: '\u8be5\u6a21\u677f\u65e0\u9700\u989d\u5916\u53c2\u6570\u3002',
  creator: '\u521b\u5efa\u4eba',
  createdAt: '\u521b\u5efa\u65f6\u95f4',
  commandRequired: '请填写执行脚本',
  playbookRequired: '\u8bf7\u586b\u5199 Playbook \u5185\u5bb9',
  serviceRequired: '\u8bf7\u586b\u5199\u670d\u52a1\u540d\u79f0',
  templateCreated: '\u6a21\u677f\u5df2\u521b\u5efa',
  templateUpdated: '\u6a21\u677f\u5df2\u66f4\u65b0',
  close: '\u5173\u95ed',
  saveAsTemplate: '\u4fdd\u5b58\u4e3a\u6a21\u677f',
  builtinTemplate: '\u5185\u7f6e',
  personalTemplate: '\u6211\u7684',
  templateSource: '来源',
  applyTemplate: '\u5957\u7528',
  deleteTemplate: '\u5220\u9664',
  noTemplates: '\u6682\u65e0\u53ef\u7528\u6a21\u677f',
  createTask: '\u65b0\u5efa\u4efb\u52a1',
  k8sLogicButton: 'K8s 脚本执行逻辑',
  k8sLogicTitle: 'K8s 脚本执行逻辑',
  targetType: '目标类型',
  hostResource: '主机资源',
  k8sResource: 'K8s 资源',
  selectedTargets: '已选目标',
  unitTarget: '个',
  selectedHosts: '\u5df2\u9009',
  selectedTasks: '\u5df2\u9009',
  unitHost: '\u53f0',
  unitTask: '\u4e2a\u4efb\u52a1',
  taskName: '\u4efb\u52a1\u540d\u79f0',
  taskNamePlaceholder: '\u4f8b\u5982\uff1a\u751f\u4ea7\u4e3b\u673a\u6279\u91cf\u5de1\u68c0',
  taskType: '\u4efb\u52a1\u7c7b\u578b',
  executionType: '执行类型',
  taskDesc: '\u4efb\u52a1\u8bf4\u660e',
  taskDescPlaceholder: '\u5199\u660e\u8fd9\u6b21\u4e0b\u53d1\u76ee\u7684\u3001\u53d8\u66f4\u7a97\u53e3\u6216\u5de1\u68c0\u8303\u56f4',
  serviceName: '\u670d\u52a1\u540d\u79f0',
  serviceNamePlaceholder: '\u4f8b\u5982 nginx / docker / sshd',
  playbookName: 'Playbook \u540d\u79f0',
  playbookFileName: '文件名',
  playbookNamePlaceholder: '\u4f8b\u5982 deploy-app.yml',
  playbookContent: 'Playbook \u5185\u5bb9',
  playbookContentPlaceholder: '\u4f8b\u5982\uff1a- hosts: targets\n  gather_facts: false\n  tasks:\n    - name: check service\n      shell: systemctl status nginx',
  timeout: '\u8d85\u65f6(\u79d2)',
  script: '执行脚本',
  command: '\u6267\u884c\u547d\u4ee4',
  commandPlaceholder: '\u4f8b\u5982\uff1auptime && df -h && free -m',
  pythonPlaceholder: "例如：python3 - <<'PY'\nimport os\nprint(os.uname())\nPY",
  strategy: '\u6267\u884c\u7b56\u7565',
  executionMode: '\u6267\u884c\u65b9\u5f0f',
  sshModeLabel: 'SSH \u76f4\u8fde',
  ansibleModeLabel: 'Ansible \u5206\u53d1',
  modeHint: '\u65b9\u5f0f\u8bf4\u660e',
  sshMode: 'SSH \u76f4\u8fde\u6267\u884c\uff0c\u9002\u5408\u70b9\u72b6\u8bca\u65ad\u4e0e\u63a7\u5236\u7aef\u672a\u5b89\u88c5 Ansible \u7684\u573a\u666f\u3002',
  ansibleMode: 'Ansible \u7edf\u4e00\u5206\u53d1\uff0c\u9002\u5408\u6279\u91cf\u547d\u4ee4\u548c\u6279\u91cf\u5de1\u68c0\uff1b\u63a7\u5236\u7aef\u4e0d\u53ef\u7528\u65f6\u4f1a\u6309\u914d\u7f6e\u56de\u9000 SSH\u3002',
  playbookOnlyAnsible: 'Playbook \u4efb\u52a1\u4ec5\u652f\u6301 Ansible \u6267\u884c\uff0c\u4f1a\u81ea\u52a8\u9501\u5b9a\u4e3a Ansible \u5206\u53d1\u3002',
  k8sApiMode: '通过 Kubernetes API 执行，不需要主机脚本，适合 Pod 诊断、工作负载伸缩和 Service 变更。',
  continueOnError: '\u5931\u8d25\u7ee7\u7eed',
  stopOnError: '\u5931\u8d25\u5373\u505c',
  selectTargets: '选择执行资源',
  k8sTip: 'K8s 任务会通过集群 API 执行，适合 Pod 重启、集群级 kubectl 命令和工作负载伸缩。',
  searchHostPlaceholder: '搜索资源名称 / IP',
  searchK8sPlaceholder: '搜索集群名称 / 描述',
  businessLine: '系统',
  environment: '\u73af\u5883',
  status: '\u72b6\u6001',
  matchedHosts: '\u547d\u4e2d',
  matchedK8s: '命中',
  queryHosts: '查询资源',
  resetFilters: '\u91cd\u7f6e\u7b5b\u9009',
  selectCurrent: '\u5168\u9009\u5f53\u524d',
  clearSelection: '\u6e05\u7a7a\u9009\u62e9',
  onlineHosts: '\u5728\u7ebf',
  warningHosts: '\u544a\u8b66',
  offlineHosts: '\u79bb\u7ebf',
  activeClusters: '可用',
  inactiveClusters: '停用',
  selectedClusters: '已选',
  unitCluster: '个集群',
  hostName: '资源名称',
  ipAddress: 'IP \u5730\u5740',
  submitTip: '下发前请确认执行账号、维护窗口与目标资源范围。',
  executeNow: '\u7acb\u5373\u6267\u884c',
  history: '\u4efb\u52a1\u5386\u53f2',
  searchTaskPlaceholder: '\u641c\u7d22\u4efb\u52a1\u540d\u79f0 / \u6267\u884c\u4eba',
  result: '\u6267\u884c\u7ed3\u679c',
  type: '\u7c7b\u578b',
  executor: '\u6267\u884c\u4eba',
  targetCount: '\u76ee\u6807\u6570',
  successFailed: '\u6210\u529f/\u5931\u8d25',
  summary: '\u6267\u884c\u6458\u8981',
  finishedAt: '\u5b8c\u6210\u65f6\u95f4',
  actions: '\u64cd\u4f5c',
  detail: '\u8be6\u60c5',
  copyToDraft: '继续编辑',
  renameTask: '修改任务名',
  renameTaskTitle: '重命名任务',
  renameTaskPrompt: '请输入新的任务名称',
  renameTaskSuccess: '任务名称已更新',
  renameTaskFailed: '任务重命名失败',
  rerun: '\u91cd\u8dd1',
  cancelTask: '\u7ec8\u6b62',
  batchCancel: '\u6279\u91cf\u7ec8\u6b62',
  successRate: '\u6210\u529f\u7387',
  success: '\u6210\u529f',
  failed: '\u5931\u8d25',
  skipped: '\u8df3\u8fc7',
  detailTitle: '\u4efb\u52a1\u8be6\u60c5',
  emptyDesc: '\u6682\u65e0\u989d\u5916\u8bf4\u660e',
  host: '\u4e3b\u673a',
  duration: '\u8017\u65f6',
  output: '\u7ed3\u679c\u8f93\u51fa',
  executionOverview: '\u6267\u884c\u6982\u89c8',
  executionDetails: '执行明细',
  triggerSource: '\u89e6\u53d1\u6765\u6e90',
  riskLevel: '\u98ce\u9669',
  startTask: '\u6267\u884c',
  startedAt: '\u5f00\u59cb\u65f6\u95f4',
  targetHosts: '\u76ee\u6807\u4e3b\u673a',
  targetResources: '目标资源',
  targetResource: '目标资源',
  emptyTargets: '\u6682\u65e0\u76ee\u6807\u4e3b\u673a\u5feb\u7167',
  taskPayload: '\u4efb\u52a1\u53c2\u6570',
  cancelRequestedBy: '\u7ec8\u6b62\u53d1\u8d77\u4eba',
  cancelRequestedAt: '\u7ec8\u6b62\u7533\u8bf7\u65f6\u95f4',
  viewOutput: '查看输出',
  emptyHosts: '暂无匹配执行资源',
  emptyK8sTargets: '暂无匹配 K8s 集群',
  emptyTasks: '\u6682\u65e0\u4efb\u52a1\u8bb0\u5f55',
  emptyExecutions: '\u6682\u65e0\u6267\u884c\u660e\u7ec6',
  saveTemplateTitle: '\u4fdd\u5b58\u4e3a\u6a21\u677f',
  saveTemplatePrompt: '\u8bf7\u8f93\u5165\u6a21\u677f\u540d\u79f0',
  saveTemplateSuccess: '\u6a21\u677f\u5df2\u4fdd\u5b58',
  deleteTemplateConfirm: '\u786e\u8ba4\u5220\u9664\u8be5\u6a21\u677f\uff1f',
  deleteTemplateSuccess: '\u6a21\u677f\u5df2\u5220\u9664',
  deleteTask: '删除',
  deleteTaskConfirm: '确认删除该历史任务记录？删除后将同时移除执行明细。',
  deleteTaskSuccess: '任务记录已删除',
  templateApplySuccess: '\u5df2\u5957\u7528\u6a21\u677f',
  snippetApplySuccess: '\u5df2\u586b\u5165\u5e38\u7528\u547d\u4ee4',
  taskExecuted: '\u4efb\u52a1\u5df2\u521b\u5efa\uff0c\u6b63\u5728\u540e\u53f0\u6267\u884c',
  taskRerun: '\u4efb\u52a1\u5df2\u91cd\u8dd1\uff0c\u6b63\u5728\u540e\u53f0\u6267\u884c',
  cancelConfirm: '\u786e\u8ba4\u7ec8\u6b62\u8be5\u4efb\u52a1\uff1f',
  cancelBatchConfirm: '\u786e\u8ba4\u6279\u91cf\u7ec8\u6b62\u6240\u9009\u4efb\u52a1\uff1f',
  cancelSuccess: '\u5df2\u63d0\u4ea4\u7ec8\u6b62\u8bf7\u6c42',
  batchCancelSuccess: '\u6279\u91cf\u7ec8\u6b62\u8bf7\u6c42\u5df2\u63d0\u4ea4',
  loadTargetsFailed: '加载执行资源失败',
  loadTemplatesFailed: '\u52a0\u8f7d\u4efb\u52a1\u6a21\u677f\u5931\u8d25',
  loadTasksFailed: '\u52a0\u8f7d\u4efb\u52a1\u5386\u53f2\u5931\u8d25',
  loadTaskDetailFailed: '\u52a0\u8f7d\u4efb\u52a1\u8be6\u60c5\u5931\u8d25',
  saveTemplateFailed: '\u4fdd\u5b58\u4efb\u52a1\u6a21\u677f\u5931\u8d25',
  deleteTemplateFailed: '\u5220\u9664\u4efb\u52a1\u6a21\u677f\u5931\u8d25',
  deleteTaskFailed: '删除任务记录失败',
  taskNameRequired: '\u8bf7\u586b\u5199\u4efb\u52a1\u540d\u79f0',
  hostRequired: '请至少选择一个主机资源',
  k8sRequired: '请至少选择一个 K8s 集群',
  runCommandConfirm: '\u5c06\u6267\u884c\u6279\u91cf\u547d\u4ee4\uff0c\u8bf7\u786e\u8ba4\u547d\u4ee4\u5185\u5bb9\u548c\u7ef4\u62a4\u7a97\u53e3\u3002',
  overLimitConfirm: '\u76ee\u6807\u4e3b\u673a\u8d85\u8fc7 20 \u53f0\uff0c\u5efa\u8bae\u518d\u6b21\u786e\u8ba4\u5f71\u54cd\u8303\u56f4\u3002',
  confirmExecuteTitle: '\u786e\u8ba4\u6267\u884c\u4efb\u52a1',
  confirmExecute: '\u786e\u8ba4\u6267\u884c',
  executeTaskFailed: '\u4efb\u52a1\u6267\u884c\u5931\u8d25',
  rerunTaskFailed: '\u4efb\u52a1\u91cd\u8dd1\u5931\u8d25',
  cancelTaskFailed: '\u7ec8\u6b62\u4efb\u52a1\u5931\u8d25',
  batchCancelFailed: '\u6279\u91cf\u7ec8\u6b62\u5931\u8d25',
  cancel: '\u53d6\u6d88',
}
const innerTabs = [
  { key: 'history', label: '\u4efb\u52a1\u5386\u53f2', icon: Clock, desc: '\u67e5\u770b\u7ed3\u679c\u3001\u91cd\u8dd1\u4e0e\u7ec8\u6b62\u4efb\u52a1' },
  { key: 'dispatch', label: '\u4efb\u52a1\u4e0b\u53d1', icon: Promotion, desc: '\u9009\u62e9\u76ee\u6807\u4e3b\u673a\u5e76\u7acb\u5373\u6267\u884c' },
  { key: 'library', label: '\u6a21\u677f\u5e93', icon: Collection, desc: '维护可复用执行模板' },
]
const executionTypeOptions = [
  { label: 'Shell 脚本', value: 'shell', targetType: 'host', taskType: 'run_command', executionMode: 'ansible', desc: '在主机资源上执行 Shell 脚本。' },
  { label: 'Python 脚本', value: 'python', targetType: 'host', taskType: 'run_command', executionMode: 'ansible', desc: '通过 Python 解释器执行诊断、巡检或自动化脚本。' },
  { label: 'Ansible Playbook', value: 'playbook', targetType: 'host', taskType: 'run_playbook', executionMode: 'ansible', desc: '执行结构化 Playbook，适合固化编排流程。' },
  { label: 'K8s 脚本', value: 'k8s_command', targetType: 'k8s', taskType: 'k8s_pod_exec', executionMode: 'k8s_api', desc: '在目标集群执行 kubectl/Helm 任务，适合 K8s 资源变更。' },
]
const k8sLogicItems = [
  { title: '目标来源', desc: '选择 K8s 集群后，后端会读取该集群配置并为本次任务生成临时 kubeconfig。' },
  { title: 'API 直连', desc: '部分结构化操作会直接转成 Kubernetes API 调用，例如 Pod exec、Pod 删除重启、Service patch、Deployment/StatefulSet 扩缩容。' },
  { title: 'kubectl 任务', desc: '泛化 kubectl 命令由后端本地 kubectl 执行，并显式携带临时 kubeconfig 连接目标集群。' },
  { title: 'Helm 任务', desc: 'Helm Release 会走后端本地 Helm 客户端执行 upgrade --install，不会先转换成 manifest 再 apply。' },
  { title: '执行要求', desc: '真实集群需要后端执行环境安装 kubectl；Helm 部署还需要安装 helm 客户端。演示集群会返回模拟结果。' },
]
const targetTypeOptions = [
  { label: ui.hostResource, value: 'host' },
  { label: ui.k8sResource, value: 'k8s' },
]
const executionModeOptions = [
  { label: ui.sshModeLabel, value: 'ssh' },
  { label: ui.ansibleModeLabel, value: 'ansible' },
  { label: 'K8s API', value: 'k8s_api' },
]
const hostStatusOptions = [
  { label: '\u5728\u7ebf', value: 'online' },
  { label: '\u79bb\u7ebf', value: 'offline' },
  { label: '\u544a\u8b66', value: 'warning' },
]
const k8sStatusOptions = [
  { label: '可用', value: 'active' },
  { label: '停用', value: 'inactive' },
  { label: '异常', value: 'warning' },
]
const taskStatusOptions = [
  { label: '\u6392\u961f\u4e2d', value: 'pending' },
  { label: '\u6267\u884c\u4e2d', value: 'running' },
  { label: '\u5168\u90e8\u6210\u529f', value: 'success' },
  { label: '\u90e8\u5206\u6210\u529f', value: 'partial' },
  { label: '\u6267\u884c\u5931\u8d25', value: 'failed' },
  { label: '\u5df2\u7ec8\u6b62', value: 'canceled' },
]
const triggerSourceOptions = [
  { label: '\u624b\u52a8\u89e6\u53d1', value: 'manual' },
  { label: 'AIOps \u751f\u6210', value: 'aiops' },
  { label: '\u5b9a\u65f6\u89e6\u53d1', value: 'schedule' },
  { label: '\u4e8b\u4ef6\u4e2d\u5fc3\u89e6\u53d1', value: 'event_center' },
  { label: 'API \u89e6\u53d1', value: 'api' },
]
const riskLevelOptions = [
  { label: '\u4f4e', value: 'low' },
  { label: '\u4e2d', value: 'medium' },
  { label: '\u9ad8', value: 'high' },
  { label: '\u6781\u9ad8', value: 'critical' },
]
const templateEditorAdvice = ['\u6a21\u677f\u540d\u79f0\u5efa\u8bae\u5e26\u4e0a\u573a\u666f\u3001\u670d\u52a1\u6216\u7a97\u53e3\u4fe1\u606f\uff0c\u65b9\u4fbf\u641c\u7d22\u590d\u7528\u3002', '\u547d\u4ee4\u6a21\u677f\u9002\u5408\u505a\u5feb\u901f\u5de1\u68c0\uff1bPlaybook \u6a21\u677f\u66f4\u9002\u5408\u56fa\u5316\u68c0\u67e5\u6b65\u9aa4\u3002', 'Playbook \u5185\u5bb9\u5efa\u8bae\u4f18\u5148\u4fdd\u6301 gather_facts: false \u548c changed_when: false\uff0c\u51cf\u5c11\u5bf9\u76ee\u6807\u4e3b\u673a\u7684\u6253\u6270\u3002']
const playbookExample = '- hosts: targets\n  gather_facts: false\n  tasks:\n    - name: check app process\n      shell: ps -ef | grep myapp | grep -v grep\n      changed_when: false\n    - name: tail recent log\n      shell: journalctl -u myapp -n 50 --no-pager\n      changed_when: false'
const props = defineProps({ resourceTree: { type: Array, default: () => [] } })
const tabState = useRouteTabState({
  tabs: () => innerTabs.map(item => item.key),
  defaultTab: 'dispatch',
  queryKey: 'taskTab',
})
const activeTab = tabState.activeTab
const hostTableRef = ref(null)
const k8sTargetTableRef = ref(null)
const targetLoading = ref(false)
const taskLoading = ref(false)
const templateLoading = ref(false)
const submitting = ref(false)
const savingTemplate = ref(false)
const creatingTemplate = ref(false)
const templateCreateVisible = ref(false)
const templateEditorMode = ref('create')
const editingTemplateId = ref(null)
const lastTemplateDraftType = ref('check_connection')
const templateDetailVisible = ref(false)
const detailVisible = ref(false)
const detailLoading = ref(false)
const detailTask = ref(null)
const outputDialogVisible = ref(false)
const k8sLogicVisible = ref(false)
const outputDialogTitle = ref('')
const outputDialogContent = ref('')
const currentTemplate = ref(null)
const historyRefreshTimer = ref(null)
const detailRefreshTimer = ref(null)
const availableHosts = ref([])
const availableK8sTargets = ref([])
const selectedRows = ref([])
const selectedK8sRows = ref([])
const selectedTaskRows = ref([])
const prefillDraftTargetRefs = ref([])
const prefillDraftTargets = ref([])
const prefillSourceContext = ref(null)
const selectedTargetsExpanded = ref(false)
let syncingPrefillSelection = false
const tasks = ref([])
const templates = ref([])
const taskTotal = ref(0)
const taskPage = ref(1)
const openedRouteTaskId = ref('')
const taskStats = ref({ total: 0, running: 0, pending: 0, canceled: 0, success_rate: 0, aiops_pending: 0, high_risk: 0, by_source: {} })
const targetFilters = ref({ search: '', environment: '', system: '', status: '' })
const taskFilters = ref({ search: '', target_type: '', execution_kind: '', status: '', trigger_source: '', risk_level: '' })
const templateFilters = ref({ search: '', execution_kind: '' })
const taskForm = ref(defaultTaskForm())
const templateDraft = ref(defaultTemplateDraft())
const executionKind = ref('shell')
const templateExecutionKind = ref('shell')
const envNodes = computed(() => props.resourceTree.filter(item => item.group_type === 'environment'))
const currentSystemOptions = computed(() => (envNodes.value.find(item => item.id === targetFilters.value.environment)?.children || []))
const filteredTemplates = computed(() => {
  const keyword = (templateFilters.value.search || '').trim().toLowerCase()
  return templates.value.filter((item) => {
    const matchKeyword = !keyword || [item.name, item.description, item.created_by, item.task_type_display, item.execution_mode_display].some(value => String(value || '').toLowerCase().includes(keyword))
    const matchType = !templateFilters.value.execution_kind || detectExecutionKind(item) === templateFilters.value.execution_kind
    return matchKeyword && matchType
  })
})
const availableExecutionModeOptions = computed(() => {
  if (taskForm.value.target_type === 'k8s' || executionKind.value === 'k8s_command') {
    return executionModeOptions.filter(item => item.value === 'k8s_api')
  }
  return executionModeOptions.filter(item => item.value !== 'k8s_api')
})
const availableTemplateExecutionModeOptions = computed(() => {
  if (templateDraft.value.target_type === 'k8s' || templateExecutionKind.value === 'k8s_command') {
    return executionModeOptions.filter(item => item.value === 'k8s_api')
  }
  return executionModeOptions.filter(item => item.value !== 'k8s_api')
})
const templateDialogTitle = computed(() => (templateEditorMode.value === 'edit' ? ui.editTemplateTitle : ui.createTemplateTitle))
const templateDialogSubmitText = computed(() => (templateEditorMode.value === 'edit' ? ui.updateTemplateSubmit : ui.createTemplateSubmit))
const templateDraftTypeLabel = computed(() => executionKindLabel(templateExecutionKind.value))
const selectedResourceIds = computed(() => selectedRows.value.map(item => item.id))
const selectedHostIds = selectedResourceIds
const selectedK8sClusterIds = computed(() => selectedK8sRows.value.map(item => k8sRowClusterId(item)).filter(Boolean))
const selectedK8sSubmitRows = computed(() => selectedK8sRows.value.map(item => ({
  cluster_id: k8sRowClusterId(item),
  resource_id: k8sRowResourceId(item),
  task_resource_id: k8sRowResourceId(item),
  cluster_name: item.cluster_name || item.name || '',
  resource_name: item.name || '',
  environment_name: item.environment_name || item.environment_display || '',
  system_name: item.system_name || item.business_line || '',
})).filter(item => item.cluster_id))
const effectiveHostTargetRefs = computed(() => {
  if (selectedRows.value.length) {
    return selectedRows.value.map(item => ({ source: 'task_resource', id: item.id }))
  }
  return prefillDraftTargetRefs.value.filter(item => ['host', 'task_resource'].includes(item.source))
})
const selectedTargetCount = computed(() => taskForm.value.target_type === 'k8s' ? selectedK8sClusterIds.value.length : effectiveHostTargetRefs.value.length)
const hasPrefillDraft = computed(() => !!prefillSourceContext.value)
const prefillSourceLabel = computed(() => prefillSourceContext.value?.source === 'aiops' ? 'AIOps ' : '历史任务 ')
const currentExecutionKindLabel = computed(() => executionKindLabel(executionKind.value))
const scriptEditorTitle = computed(() => executionKind.value === 'python' ? 'Python 脚本' : 'Shell 脚本')
const scriptEditorLanguage = computed(() => executionKind.value === 'python' ? 'Python' : 'Shell')
const templateScriptEditorTitle = computed(() => templateExecutionKind.value === 'python' ? 'Python 脚本' : 'Shell 脚本')
const templateScriptEditorLanguage = computed(() => templateExecutionKind.value === 'python' ? 'Python' : 'Shell')
const selectedCancelableTaskIds = computed(() => selectedTaskRows.value.filter(canCancelTask).map(item => item.id))
const hasActiveHistoryTasks = computed(() => tasks.value.some(isTaskActive))
const detailTaskActive = computed(() => isTaskActive(detailTask.value))
const executionProgressStats = computed(() => {
  const task = detailTask.value || {}
  const executions = Array.isArray(task.executions) ? task.executions : []
  const total = Number(task.target_count || executions.length || 0)
  const success = Number(task.success_count || executions.filter(item => item.status === 'success').length || 0)
  const failed = Number(task.failed_count || executions.filter(item => item.status === 'failed').length || 0)
  const skipped = Number(task.skipped_count || executions.filter(item => item.status === 'skipped').length || 0)
  const running = executions.filter(item => item.status === 'running').length
  const finished = Math.min(success + failed + skipped, total || success + failed + skipped)
  return { total, success, failed, skipped, running, finished }
})
const executionProgressPercent = computed(() => {
  const total = executionProgressStats.value.total
  if (!total) return 0
  const value = Math.round((executionProgressStats.value.finished / total) * 100)
  return Math.min(Math.max(value, 0), 100)
})
const executionProgressStatus = computed(() => {
  if (!detailTask.value) return undefined
  if (detailTask.value.status === 'failed' || detailTask.value.status === 'canceled') return 'exception'
  if (['success', 'partial'].includes(detailTask.value.status)) return 'success'
  return undefined
})
const executionProgressSummary = computed(() => {
  const stats = executionProgressStats.value
  if (!stats.total) return '暂无进度'
  const runningText = stats.running ? `，执行中 ${stats.running}` : ''
  return `已完成 ${stats.finished}/${stats.total}，成功 ${stats.success}，失败 ${stats.failed}，跳过 ${stats.skipped}${runningText}`
})
const selectedHostPreviewItems = computed(() => {
  const rows = selectedRows.value.length ? selectedRows.value : matchedPrefillHostRows.value
  const fallback = rows.length ? rows : prefillDraftTargets.value
  return fallback.map((item, index) => ({
    key: `${item.source || 'target'}-${item.id || item.resource_id || item.host_id || index}`,
    name: item.name || item.hostname || item.resource_name || item.host_name || '-',
    meta: [item.ip_address || item.host_ip, item.environment_name || item.environment_display || item.environment].filter(Boolean).join(' / ') || '-',
  }))
})
const matchedPrefillHostRows = computed(() => {
  if (!prefillDraftTargetRefs.value.length || !availableHosts.value.length) return []
  return availableHosts.value.filter(row => prefillDraftTargetRefs.value.some(ref => hostRowMatchesTargetRef(row, ref)))
})
const selectedStats = computed(() => selectedRows.value.reduce((summary, item) => {
  if (item.status === 'online') summary.online += 1
  if (item.status === 'warning') summary.warning += 1
  if (item.status === 'offline') summary.offline += 1
  return summary
}, { online: 0, offline: 0, warning: 0 }))
const selectedK8sStats = computed(() => selectedK8sRows.value.reduce((summary, item) => {
  if (item.status === 'active') summary.active += 1
  if (item.status === 'warning') summary.warning += 1
  if (item.status === 'inactive') summary.inactive += 1
  return summary
}, { active: 0, inactive: 0, warning: 0 }))
const sourceCards = computed(() => {
  const bySource = taskStats.value.by_source || {}
  return [
    { key: 'all', label: '\u5168\u90e8\u4efb\u52a1', source: '', value: taskStats.value.total || 0, desc: '\u7edf\u4e00\u4efb\u52a1\u6c60', cardClass: '' },
    { key: 'manual', label: '\u4eba\u5de5\u521b\u5efa', source: 'manual', value: bySource.manual || 0, desc: '\u9875\u9762\u76f4\u63a5\u521b\u5efa', cardClass: 'task-source-card--danger' },
    { key: 'aiops', label: 'AIOps \u751f\u6210', source: 'aiops', value: bySource.aiops || 0, desc: '\u667a\u80fd\u52a9\u624b\u751f\u6210', cardClass: 'task-source-card--success' },
    { key: 'schedule', label: '\u8ba1\u5212\u4efb\u52a1', source: 'schedule', value: bySource.schedule || 0, desc: '\u5b9a\u65f6\u7f16\u6392\u89e6\u53d1', cardClass: 'task-source-card--warning' },
  ]
})
function defaultPayload() {
  return {
    command: '',
    script_kind: 'shell',
    service_name: '',
    namespace: 'default',
    patch: {},
    playbook_name: '',
    playbook_content: '',
    workload_type: 'deployment',
    replicas: 1,
  }
}
function defaultTaskForm() { return { name: '', target_type: 'host', task_type: 'run_command', description: '', execution_mode: 'ansible', execution_strategy: 'continue', timeout_seconds: 30, payload: buildPayloadByExecutionKind('shell') } }
function defaultTemplateDraft() { return { name: '', target_type: 'host', task_type: 'run_command', description: '', execution_mode: 'ansible', execution_strategy: 'continue', timeout_seconds: 30, payload: buildPayloadByExecutionKind('shell') } }
function buildPresetPayload(taskType) {
  if (taskType === 'run_command') return { ...defaultPayload(), command: 'uptime && df -h && free -m' }
  if (taskType === 'run_playbook') return { ...defaultPayload(), playbook_name: 'service-health.yml', playbook_content: playbookExample }
  if (taskType === 'service_status') return { ...defaultPayload(), command: buildServiceStatusScript('nginx'), service_name: 'nginx' }
  if (taskType === 'k8s_pod_exec') return { ...defaultPayload(), command: 'kubectl get deployment -A' }
  if (taskType === 'k8s_scale_workload') return { ...defaultPayload(), workload_type: 'deployment', replicas: 2 }
  return defaultPayload()
}
function buildPayloadByExecutionKind(kind) {
  if (kind === 'python') return { ...defaultPayload(), script_kind: 'python', command: "python3 - <<'PY'\nimport os\nprint(os.uname())\nPY" }
  if (kind === 'playbook') return buildPresetPayload('run_playbook')
  if (kind === 'k8s_command') return buildPresetPayload('k8s_pod_exec')
  return { ...defaultPayload(), script_kind: 'shell', command: 'uptime && df -h' }
}
function clearPrefillDraft() {
  prefillDraftTargetRefs.value = []
  prefillDraftTargets.value = []
  prefillSourceContext.value = null
  selectedTargetsExpanded.value = false
}
function handleSelectionChange(rows) {
  selectedRows.value = rows
  if (rows.length && !syncingPrefillSelection) {
    prefillDraftTargetRefs.value = []
    prefillDraftTargets.value = []
  }
}
function normalizeId(value) {
  return String(value ?? '').trim()
}
function hostRowMatchesTargetRef(row = {}, ref = {}) {
  const refSource = String(ref.source || '').trim()
  const refId = normalizeId(ref.id || ref.resource_id || ref.host_id)
  if (!refId) return false
  if (refSource === 'task_resource') {
    return [row.id, row.resource_id, row.task_resource_id].some(value => normalizeId(value) === refId)
  }
  if (refSource === 'host') {
    return [row.host_id, row.cmdb_host_id, row.id].some(value => normalizeId(value) === refId)
  }
  return [row.id, row.resource_id, row.task_resource_id, row.host_id, row.cmdb_host_id].some(value => normalizeId(value) === refId)
}
function hostRowMatchesTargetSnapshot(row = {}, target = {}) {
  const targetIds = [target.id, target.resource_id, target.task_resource_id, target.host_id, target.cmdb_host_id].map(normalizeId).filter(Boolean)
  const rowIds = [row.id, row.resource_id, row.task_resource_id, row.host_id, row.cmdb_host_id].map(normalizeId)
  if (targetIds.some(id => rowIds.includes(id))) return true
  const targetNames = [target.name, target.hostname, target.resource_name, target.host_name].map(value => String(value || '').trim()).filter(Boolean)
  const rowNames = [row.name, row.hostname, row.resource_name, row.host_name].map(value => String(value || '').trim())
  if (targetNames.some(name => rowNames.includes(name))) return true
  const targetIp = String(target.ip_address || target.host_ip || '').trim()
  return Boolean(targetIp && targetIp === String(row.ip_address || row.host_ip || '').trim())
}
async function syncPrefillHostSelection() {
  if (!prefillDraftTargetRefs.value.length && !prefillDraftTargets.value.length) return
  await nextTick()
  const matchedRows = availableHosts.value.filter(row =>
    prefillDraftTargetRefs.value.some(ref => hostRowMatchesTargetRef(row, ref))
    || prefillDraftTargets.value.some(target => hostRowMatchesTargetSnapshot(row, target))
  )
  if (!matchedRows.length) return
  syncingPrefillSelection = true
  hostTableRef.value?.clearSelection()
  matchedRows.forEach(row => hostTableRef.value?.toggleRowSelection(row, true))
  selectedRows.value = matchedRows
  syncingPrefillSelection = false
  selectedTargetsExpanded.value = true
}
function handleK8sSelectionChange(rows) { selectedK8sRows.value = rows }
function handleTaskHistorySelectionChange(rows) { selectedTaskRows.value = rows }
function executionStrategyLabel(strategy) { return strategy === 'stop_on_error' ? ui.stopOnError : ui.continueOnError }
function executionModeLabel(mode, display) { return display || executionModeOptions.find(item => item.value === mode)?.label || mode || '-' }
function executionModeHint(mode, taskType) {
  if (mode === 'k8s_api' || String(taskType || '').startsWith('k8s_')) return ui.k8sApiMode
  if (taskType === 'run_playbook') return ui.playbookOnlyAnsible
  return mode === 'ansible' ? ui.ansibleMode : ui.sshMode
}
function detectExecutionKind(source = {}) {
  const taskType = source.task_type || ''
  if (taskType.startsWith('k8s_') || source.target_type === 'k8s') return 'k8s_command'
  if (taskType === 'run_playbook') return 'playbook'
  if (taskType === 'run_command' && source.payload?.script_kind === 'python') return 'python'
  return 'shell'
}
function executionKindLabel(kind) {
  return executionTypeOptions.find(item => item.value === kind)?.label || kind || '-'
}
function templateExecutionKindLabel(template) {
  return executionKindLabel(detectExecutionKind(template))
}
function isPlainObject(value) {
  return !!value && typeof value === 'object' && !Array.isArray(value)
}
function commandTextFromValue(value) {
  if (value == null) return ''
  if (Array.isArray(value)) return value.map(commandTextFromValue).filter(Boolean).join('\n').trim()
  if (isPlainObject(value)) return extractCommandText(value)
  return String(value || '').replace(/\\r\\n/g, '\n').replace(/\\n/g, '\n').trim()
}
function extractCommandText(source = {}) {
  if (!isPlainObject(source)) return ''
  const aliasKeys = ['command', 'commands', 'cmd', 'script', 'script_content', 'script_text', 'script_body', 'shell', 'shell_script', 'shell_command', 'command_text']
  for (const key of aliasKeys) {
    const text = commandTextFromValue(source[key])
    if (text) return text
  }
  return ''
}
function normalizeServiceName(value) {
  return String(value || '').trim().replace(/^['"`]+|['"`]+$/g, '') || 'nginx'
}
function buildServiceStatusScript(serviceName = 'nginx') {
  const service = normalizeServiceName(serviceName)
  return `#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="${service}"

if [ "$(id -u)" -ne 0 ]; then
  SUDO="sudo"
else
  SUDO=""
fi

if ! command -v systemctl >/dev/null 2>&1; then
  echo "systemctl is not available on this host." >&2
  exit 1
fi

$SUDO systemctl status "$SERVICE_NAME" --no-pager`
}
function normalizeScriptTaskSource(source = {}) {
  const taskType = source.task_type || 'run_command'
  if (taskType !== 'service_status') return source
  const payload = isPlainObject(source.payload) ? source.payload : {}
  const serviceName = normalizeServiceName(payload.service_name || source.service_name)
  return {
    ...source,
    task_type: 'run_command',
    execution_mode: source.execution_mode || 'ansible',
    execution_strategy: source.execution_strategy || 'stop_on_error',
    payload: {
      ...payload,
      service_name: serviceName,
      script_kind: payload.script_kind || 'shell',
      script_purpose: payload.script_purpose || 'inspection',
      command: extractCommandText(payload) || buildServiceStatusScript(serviceName),
    },
  }
}
function clampTaskTimeout(value, fallback = 30) {
  const number = Number(value || fallback)
  if (!Number.isFinite(number)) return fallback
  return Math.min(Math.max(Math.round(number), 5), 120)
}
function taskRequestErrorMessage(error, fallback) {
  const data = error?.response?.data || {}
  const timeoutMessage = Array.isArray(data.timeout_seconds) ? data.timeout_seconds[0] : data.timeout_seconds
  if (timeoutMessage) return `超时时间需在 5-120 秒之间，已为你按 120 秒以内处理，请重新执行。`
  if (Array.isArray(data.non_field_errors) && data.non_field_errors[0]) return data.non_field_errors[0]
  if (data.detail) return data.detail
  const firstKey = Object.keys(data).find(key => data[key])
  if (firstKey) {
    const value = Array.isArray(data[firstKey]) ? data[firstKey][0] : data[firstKey]
    return value ? `${firstKey}: ${value}` : fallback
  }
  return fallback
}
function buildEditablePayload(payload = {}, executionKindValue = 'shell') {
  const patch = isPlainObject(payload.patch) ? payload.patch : {}
  const command = extractCommandText(payload)
  return {
    ...defaultPayload(),
    ...(payload || {}),
    ...(command ? { command } : {}),
    script_kind: payload?.script_kind || (executionKindValue === 'python' ? 'python' : 'shell'),
    namespace: payload?.namespace || 'default',
    patch,
  }
}
function sanitizePayload(payload = {}) {
  return payload
}
function normalizePayloadByType(taskType, source = {}) {
  if (taskType === 'run_command') return { command: extractCommandText(source), script_kind: source.script_kind === 'python' ? 'python' : 'shell' }
  if (taskType === 'run_playbook') return { playbook_name: (source.playbook_name || '').trim(), playbook_content: (source.playbook_content || '').trim() }
  if (taskType === 'service_status') return { command: extractCommandText(source) || buildServiceStatusScript(source.service_name), script_kind: 'shell', service_name: normalizeServiceName(source.service_name) }
  if (taskType === 'k8s_pod_exec') {
    const payload = { command: (source.command || '').trim() }
    ;['resource_kind', 'service_name', 'namespace', 'patch_type'].forEach((key) => {
      if (source[key]) payload[key] = source[key]
    })
    if (isPlainObject(source.patch)) payload.patch = source.patch
    return payload
  }
  if (taskType === 'k8s_scale_workload') return { workload_type: source.workload_type || 'deployment', replicas: Number(source.replicas || 0) }
  return {}
}
function k8sRowClusterId(item = {}) {
  const value = item.cluster || item.cluster_id
  if (value) return value
  const id = String(item.id || '')
  return id.startsWith('cluster:') ? id.slice(8) : id
}
function k8sRowResourceId(item = {}) {
  const id = item.task_resource_id || item.resource_id || item.id
  return Number.isInteger(Number(id)) ? Number(id) : undefined
}
function buildK8sSubmitTargets(payload = {}) {
  const kind = payload.resource_kind || payload.workload_type || (payload.service_name ? 'service' : 'cluster')
  const name = payload.service_name || payload.workload_name || payload.pod_name || ''
  const namespace = payload.namespace || (name ? 'default' : '')
  return selectedK8sSubmitRows.value.map(item => ({
    ...item,
    kind,
    namespace,
    name,
  }))
}
function validatePayloadByType(taskType, payload) {
  if (taskType === 'run_command' && !payload.command) return ElMessage.warning(ui.commandRequired), false
  if (taskType === 'run_playbook' && !payload.playbook_content) return ElMessage.warning(ui.playbookRequired), false
  if (taskType === 'service_status' && !(payload.command || payload.service_name)) return ElMessage.warning(ui.commandRequired), false
  if (taskType === 'k8s_pod_exec' && !payload.command) return ElMessage.warning(ui.commandRequired), false
  return true
}
function normalizePayload() { return normalizePayloadByType(taskForm.value.task_type, taskForm.value.payload || {}) }
function validateTaskPayload(payload) { return validatePayloadByType(taskForm.value.task_type, payload) }
function templatePayloadPreview(template) {
  const normalizedTemplate = normalizeScriptTaskSource(template)
  if (normalizedTemplate.task_type === 'run_command') return normalizedTemplate.payload?.command || ''
  if (normalizedTemplate.task_type === 'run_playbook') return normalizedTemplate.payload?.playbook_name || normalizedTemplate.payload?.playbook_content || ''
  if (normalizedTemplate.task_type === 'k8s_pod_exec') return normalizedTemplate.payload?.command || ''
  return ''
}
function templatePreviewLabel(template) {
  const normalizedTemplate = normalizeScriptTaskSource(template)
  if (normalizedTemplate.task_type === 'run_command') return ui.command
  if (normalizedTemplate.task_type === 'run_playbook') return ui.playbookContent
  return ui.serviceDetail
}
function formatPayloadJson(payload) { return JSON.stringify(payload || {}, null, 2) }
function formatMultilineContent(value) {
  return String(value || '-').replace(/\\n/g, '\n')
}
function escapeHtml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
}
function splitLineComment(line = '', shellMode = false) {
  let quote = ''
  let escaped = false
  for (let index = 0; index < line.length; index += 1) {
    const char = line[index]
    if (escaped) {
      escaped = false
      continue
    }
    if (char === '\\') {
      escaped = true
      continue
    }
    if (quote) {
      if (char === quote) quote = ''
      continue
    }
    if (char === '"' || char === "'") {
      quote = char
      continue
    }
    if (char === '#' && (!shellMode || index === 0 || /\s/.test(line[index - 1]))) {
      return [line.slice(0, index), line.slice(index)]
    }
  }
  return [line, '']
}
function highlightRawTokens(value = '', tokenPattern, resolveClass) {
  if (!tokenPattern) return escapeHtml(value)
  tokenPattern.lastIndex = 0
  let html = ''
  let offset = 0
  let match = tokenPattern.exec(value)
  while (match) {
    html += escapeHtml(value.slice(offset, match.index))
    const token = match[0]
    html += `<span class="${resolveClass(token)}">${escapeHtml(token)}</span>`
    offset = match.index + token.length
    match = tokenPattern.exec(value)
  }
  html += escapeHtml(value.slice(offset))
  return html
}
function highlightTextTokens(value = '', tokenPattern, resolveClass) {
  const stringPattern = /"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'/g
  let html = ''
  let offset = 0
  let match = stringPattern.exec(value)
  while (match) {
    html += highlightRawTokens(value.slice(offset, match.index), tokenPattern, resolveClass)
    html += `<span class="tok-string">${escapeHtml(match[0])}</span>`
    offset = match.index + match[0].length
    match = stringPattern.exec(value)
  }
  html += highlightRawTokens(value.slice(offset), tokenPattern, resolveClass)
  return html
}
function highlightShellCode(value = '') {
  const pattern = /\$\{?[A-Za-z_][A-Za-z0-9_]*\}?|\b(?:if|then|elif|else|fi|for|while|do|done|case|esac|function|return|exit|export|set|local)\b|\b(?:sudo|apt-get|dnf|yum|systemctl|command|echo|grep|awk|sed|curl|kubectl|docker|cat|test)\b|\b\d+(?:\.\d+)?\b/g
  return String(value || '').split('\n').map((line) => {
    const [code, comment] = splitLineComment(line, true)
    const codeHtml = highlightTextTokens(code, pattern, (token) => {
      if (token.startsWith('$')) return 'tok-variable'
      if (/^\d/.test(token)) return 'tok-number'
      if (/^(sudo|apt-get|dnf|yum|systemctl|command|echo|grep|awk|sed|curl|kubectl|docker|cat|test)$/.test(token)) return 'tok-command'
      return 'tok-keyword'
    })
    return comment ? `${codeHtml}<span class="tok-comment">${escapeHtml(comment)}</span>` : codeHtml
  }).join('\n')
}
function highlightPythonCode(value = '') {
  const pattern = /\b(?:def|class|if|elif|else|for|while|try|except|finally|with|as|import|from|return|yield|in|is|not|and|or|True|False|None|print)\b|\b\d+(?:\.\d+)?\b/g
  return String(value || '').split('\n').map((line) => {
    const [code, comment] = splitLineComment(line)
    const codeHtml = highlightTextTokens(code, pattern, token => (/^\d/.test(token) ? 'tok-number' : 'tok-keyword'))
    return comment ? `${codeHtml}<span class="tok-comment">${escapeHtml(comment)}</span>` : codeHtml
  }).join('\n')
}
function highlightYamlCode(value = '') {
  const pattern = /\b(?:true|false|null|yes|no|on|off)\b|\b\d+(?:\.\d+)?\b/gi
  return String(value || '').split('\n').map((line) => {
    const [code, comment] = splitLineComment(line)
    const keyMatch = code.match(/^(\s*-?\s*)([A-Za-z_][A-Za-z0-9_-]*)(\s*:)/)
    let codeHtml = ''
    if (keyMatch) {
      const headLength = keyMatch[0].length
      codeHtml = `${escapeHtml(keyMatch[1])}<span class="tok-keyword">${escapeHtml(keyMatch[2])}</span>${escapeHtml(keyMatch[3])}`
      codeHtml += highlightTextTokens(code.slice(headLength), pattern, token => (/^\d/.test(token) ? 'tok-number' : 'tok-bool'))
    } else {
      codeHtml = highlightTextTokens(code, pattern, token => (/^\d/.test(token) ? 'tok-number' : 'tok-bool'))
    }
    return comment ? `${codeHtml}<span class="tok-comment">${escapeHtml(comment)}</span>` : codeHtml
  }).join('\n')
}
function highlightScript(value = '', kind = 'shell') {
  if (kind === 'python') return highlightPythonCode(value)
  if (kind === 'playbook') return highlightYamlCode(value)
  if (kind === 'k8s') return highlightShellCode(value)
  return highlightShellCode(value || '')
}
function syncScriptEditorScroll(event) {
  const editor = event?.target
  const highlight = editor?.previousElementSibling
  if (!editor || !highlight) return
  highlight.scrollTop = editor.scrollTop
  highlight.scrollLeft = editor.scrollLeft
}
function executionTargetName(row) {
  return row?.target_name || row?.host_name || row?.host_ip || row?.target_id || '-'
}
function executionTargetMeta(row) {
  const normalizedKind = row?.target_kind === 'task_resource_host' ? '' : row?.target_kind
  const parts = [row?.host_ip, row?.target_namespace, normalizedKind].filter(Boolean)
  return parts.join(' / ')
}
function appendEnvironmentValue(list, value) {
  const text = String(value || '').trim()
  if (text && !list.includes(text)) list.push(text)
}
function appendEnvironmentItems(list, items) {
  if (!Array.isArray(items)) return
  items.forEach(item => {
    appendEnvironmentValue(list, item?.environment_name)
    appendEnvironmentValue(list, item?.environment_display)
    appendEnvironmentValue(list, item?.environment)
    appendEnvironmentValue(list, item?.env)
  })
}
function formatEnvironmentValues(values) {
  const items = values.filter(Boolean)
  if (!items.length) return '-'
  if (items.length === 1) return items[0]
  return `${items[0]} 等 ${items.length} 个`
}
function taskEnvironmentDisplay(task = {}) {
  const values = []
  const selectionFilters = task.selection_filters || {}
  const sourceContext = task.source_context || {}
  appendEnvironmentValue(values, task.environment_name)
  appendEnvironmentValue(values, task.environment_display)
  appendEnvironmentValue(values, task.environment)
  appendEnvironmentValue(values, selectionFilters.environment_name)
  appendEnvironmentValue(values, selectionFilters.resource_environment)
  appendEnvironmentValue(values, selectionFilters.environment)
  appendEnvironmentValue(values, sourceContext.environment_name)
  appendEnvironmentValue(values, sourceContext.environment)
  appendEnvironmentValue(values, sourceContext.resource_environment)
  appendEnvironmentValue(values, sourceContext.knowledge_environment)
  appendEnvironmentItems(values, task.target_snapshot)
  return formatEnvironmentValues(values)
}
function targetSnapshotPrimaryName(item = {}, targetType = 'host') {
  if (targetType === 'k8s') {
    if (item.kind && item.namespace && item.name) return `${item.kind}/${item.namespace}/${item.name}`
    if (item.namespace && item.name) return `${item.namespace}/${item.name}`
    return item.name || item.resource_name || item.cluster_name || '-'
  }
  return item.hostname || item.name || item.resource_name || '-'
}
function targetSnapshotMeta(item = {}, targetType = 'host') {
  if (targetType === 'k8s') return item.cluster_name || item.resource_name || '-'
  return item.ip_address || item.cluster_name || '-'
}
function buildTemplateDraft(source = {}) {
  const normalizedSource = normalizeScriptTaskSource(source)
  const taskType = normalizedSource.task_type || 'run_command'
  const targetType = normalizedSource.target_type || (taskType.startsWith('k8s_') ? 'k8s' : 'host')
  return {
    name: normalizedSource.name || '',
    target_type: targetType,
    task_type: taskType,
    description: normalizedSource.description || '',
    execution_mode: normalizedSource.execution_mode || (targetType === 'k8s' ? 'k8s_api' : (['run_command', 'run_playbook'].includes(taskType) ? 'ansible' : 'ssh')),
    execution_strategy: normalizedSource.execution_strategy || 'continue',
    timeout_seconds: clampTaskTimeout(normalizedSource.timeout_seconds, 15),
    payload: buildEditablePayload(normalizedSource.payload || {}, detectExecutionKind(normalizedSource)),
  }
}
function applyTemplate(template) {
  const normalizedTemplate = normalizeScriptTaskSource(template)
  executionKind.value = detectExecutionKind(normalizedTemplate)
  const detectedExecutionKind = detectExecutionKind(normalizedTemplate)
  taskForm.value = {
    name: normalizedTemplate.name,
    target_type: normalizedTemplate.target_type || (normalizedTemplate.task_type?.startsWith('k8s_') ? 'k8s' : 'host'),
    task_type: normalizedTemplate.task_type,
    description: normalizedTemplate.description || '',
    execution_mode: normalizedTemplate.execution_mode || (normalizedTemplate.task_type?.startsWith('k8s_') ? 'k8s_api' : (['run_command', 'run_playbook'].includes(normalizedTemplate.task_type) ? 'ansible' : 'ssh')),
    execution_strategy: normalizedTemplate.execution_strategy,
    timeout_seconds: clampTaskTimeout(normalizedTemplate.timeout_seconds),
    payload: buildEditablePayload(normalizedTemplate.payload || {}, detectedExecutionKind),
  }
  clearSelection()
  fetchTargets()
  activeTab.value = 'dispatch'
  templateDetailVisible.value = false
  ElMessage.success(ui.templateApplySuccess)
}
function canCancelTask(task) { return ['pending', 'running'].includes(task.status) && !task.cancel_requested }
function canExecuteTask(task) { return task.status === 'pending' && !task.cancel_requested }
function canDeleteTask(task) { return !['pending', 'running'].includes(task.status) }
function isTaskActive(task) { return ['pending', 'running'].includes(task?.status) }
function riskTagType(risk) { if (risk === 'critical' || risk === 'high') return 'danger'; if (risk === 'medium') return 'warning'; return 'success' }
function applySourceFilter(source, targetType = '') { taskFilters.value.trigger_source = source; taskFilters.value.target_type = targetType; taskPage.value = 1; activeTab.value = 'history'; fetchTasks() }
function handleEnvironmentChange() { targetFilters.value.system = '' }
async function applyExecutionKind(kind) {
  const option = executionTypeOptions.find(item => item.value === kind) || executionTypeOptions[0]
  const previousTargetType = taskForm.value.target_type
  executionKind.value = option.value
  taskForm.value.target_type = option.targetType
  taskForm.value.task_type = option.taskType
  taskForm.value.execution_mode = option.executionMode
  taskForm.value.name = option.label
  taskForm.value.description = option.desc
  taskForm.value.timeout_seconds = option.value === 'playbook' ? 60 : 30
  taskForm.value.execution_strategy = option.value === 'k8s_command' ? 'continue' : 'stop_on_error'
  taskForm.value.payload = buildPayloadByExecutionKind(option.value)
  if (previousTargetType !== option.targetType) clearSelection()
  await fetchTargets()
}
function handleTemplateExecutionKindChange(kind) {
  const option = executionTypeOptions.find(item => item.value === kind) || executionTypeOptions[0]
  templateExecutionKind.value = option.value
  templateDraft.value.task_type = option.taskType
  templateDraft.value.target_type = option.targetType
  templateDraft.value.execution_mode = option.executionMode
  templateDraft.value.timeout_seconds = option.value === 'playbook' ? 60 : 30
  templateDraft.value.execution_strategy = option.value === 'k8s_command' ? 'continue' : 'stop_on_error'
  templateDraft.value.payload = buildPayloadByExecutionKind(option.value)
  if (!templateDraft.value.name || executionTypeOptions.some(item => item.label === templateDraft.value.name)) {
    templateDraft.value.name = option.label
  }
  if (!templateDraft.value.description || executionTypeOptions.some(item => item.desc === templateDraft.value.description)) {
    templateDraft.value.description = option.desc
  }
  lastTemplateDraftType.value = option.taskType
}
function openTemplateCreateDialog() {
  templateEditorMode.value = 'create'
  editingTemplateId.value = null
  templateExecutionKind.value = 'shell'
  templateDraft.value = buildTemplateDraft({
    task_type: 'run_command',
    name: 'Shell 脚本',
    description: '在主机资源上执行 Shell 命令或脚本片段。',
    execution_mode: 'ansible',
    execution_strategy: 'stop_on_error',
    timeout_seconds: 30,
    payload: buildPayloadByExecutionKind('shell'),
  })
  lastTemplateDraftType.value = templateDraft.value.task_type
  templateCreateVisible.value = true
}
function openTemplateEditDialog(template) {
  templateEditorMode.value = 'edit'
  editingTemplateId.value = template.id
  const normalizedTemplate = normalizeScriptTaskSource(template)
  templateDraft.value = buildTemplateDraft(normalizedTemplate)
  templateExecutionKind.value = detectExecutionKind(normalizedTemplate)
  lastTemplateDraftType.value = templateDraft.value.task_type
  templateCreateVisible.value = true
}
function openTemplateDetail(template) {
  const normalizedTemplate = normalizeScriptTaskSource(template)
  currentTemplate.value = { ...normalizedTemplate, payload: buildEditablePayload(normalizedTemplate.payload || {}, detectExecutionKind(normalizedTemplate)) }
  templateDetailVisible.value = true
}
function resetTemplateFilters() { templateFilters.value = { search: '', execution_kind: '' } }
function taskStatusType(status) { if (status === 'success') return 'success'; if (status === 'partial') return 'warning'; if (status === 'failed' || status === 'canceled') return 'danger'; return 'info' }
function executionStatusType(status) { if (status === 'success') return 'success'; if (status === 'failed' || status === 'canceled') return 'danger'; if (status === 'running' || status === 'partial') return 'warning'; return 'info' }
function formatDateTime(value) { return value ? value.replace('T', ' ').slice(0, 19) : '-' }
function formatDuration(value) {
  const duration = Number(value || 0)
  if (!Number.isFinite(duration) || duration <= 0) return '0ms'
  if (duration < 1000) return `${duration}ms`
  if (duration < 60000) return `${(duration / 1000).toFixed(duration >= 10000 ? 0 : 1)}s`
  const minutes = Math.floor(duration / 60000)
  const seconds = Math.round((duration % 60000) / 1000)
  return seconds ? `${minutes}min ${seconds}s` : `${minutes}min`
}
function elapsedMsSince(value) {
  const timestamp = value ? new Date(value).getTime() : 0
  if (!Number.isFinite(timestamp) || timestamp <= 0) return 0
  return Math.max(Date.now() - timestamp, 0)
}
function formatExecutionDuration(row) {
  if (row?.status === 'running') return formatDuration(elapsedMsSince(row.started_at))
  return formatDuration(row?.duration_ms)
}
function executionOutputContent(row) {
  return row?.error_message || row?.output || '-'
}
function previewExecutionOutput(row) {
  const normalized = executionOutputContent(row).replace(/\s+/g, ' ').trim()
  if (!normalized) return '-'
  return normalized.length > 150 ? `${normalized.slice(0, 150)}...` : normalized
}
function openExecutionOutput(row) {
  outputDialogTitle.value = `${ui.output} · ${executionTargetName(row)}`
  outputDialogContent.value = executionOutputContent(row)
  outputDialogVisible.value = true
}
async function fetchHostTargets() {
  targetLoading.value = true
  try {
    const res = await getTaskResourceOptions({ ...targetFilters.value, resource_type: 'host' })
    availableHosts.value = Array.isArray(res) ? res : (res.results || [])
    await syncPrefillHostSelection()
  } catch (error) {
    ElMessage.error(ui.loadTargetsFailed)
  } finally {
    targetLoading.value = false
  }
}
async function fetchK8sTargets() {
  targetLoading.value = true
  try {
    const res = await getTaskResourceOptions({ ...targetFilters.value, resource_type: 'k8s' })
    availableK8sTargets.value = Array.isArray(res) ? res : (res.results || [])
  } catch (error) {
    ElMessage.error(ui.loadTargetsFailed)
  } finally {
    targetLoading.value = false
  }
}
async function fetchTargets() {
  if (taskForm.value.target_type === 'k8s') return fetchK8sTargets()
  return fetchHostTargets()
}
async function fetchStats() {
  try {
    const res = await getHostTaskStats()
    taskStats.value = {
      total: res?.total || 0,
      running: res?.running || 0,
      pending: res?.pending || 0,
      canceled: res?.canceled || 0,
      success_rate: res?.success_rate || 0,
      aiops_pending: res?.aiops_pending || 0,
      high_risk: res?.high_risk || 0,
      by_source: res?.by_source || {},
      by_target_type: res?.by_target_type || {},
    }
  } catch (error) {}
}
async function fetchTemplates() {
  templateLoading.value = true
  try {
    const res = await getHostTaskTemplates()
    templates.value = res.results || res || []
  } catch (error) {
    ElMessage.error(ui.loadTemplatesFailed)
  } finally {
    templateLoading.value = false
  }
}
async function fetchTasks() {
  taskLoading.value = true
  try {
    const taskTypeFilter = executionTypeOptions.find(item => item.value === taskFilters.value.execution_kind)?.taskType
    const res = await getHostTasks({
      page: taskPage.value,
      search: taskFilters.value.search || undefined,
      target_type: taskFilters.value.target_type || undefined,
      task_type: taskTypeFilter || undefined,
      status: taskFilters.value.status || undefined,
      trigger_source: taskFilters.value.trigger_source || undefined,
      risk_level: taskFilters.value.risk_level || undefined,
    })
    const rows = res.results || res || []
    tasks.value = rows.map(row => ({
      ...row,
      environment_display: taskEnvironmentDisplay(row),
    }))
    taskTotal.value = res.count || tasks.value.length
  } catch (error) {
    ElMessage.error(ui.loadTasksFailed)
  } finally {
    taskLoading.value = false
  }
}
function selectAllCurrent() {
  if (taskForm.value.target_type === 'k8s') {
    k8sTargetTableRef.value?.clearSelection()
    availableK8sTargets.value.forEach(row => k8sTargetTableRef.value?.toggleRowSelection(row, true))
    return
  }
  hostTableRef.value?.clearSelection()
  availableHosts.value.forEach(row => hostTableRef.value?.toggleRowSelection(row, true))
}
function clearSelection() {
  hostTableRef.value?.clearSelection()
  k8sTargetTableRef.value?.clearSelection()
  selectedRows.value = []
  selectedK8sRows.value = []
  clearPrefillDraft()
}
function resetTargetFilters() { targetFilters.value = { search: '', environment: '', system: '', status: '' }; clearSelection(); fetchTargets() }
function resetTaskFilters() { taskFilters.value = { search: '', target_type: '', execution_kind: '', status: '', trigger_source: '', risk_level: '' }; taskPage.value = 1; selectedTaskRows.value = []; fetchTasks() }
function buildPrefillDraftFromTask(task = {}) {
  const normalizedTask = normalizeScriptTaskSource(task)
  const taskType = normalizedTask.task_type || 'run_command'
  const targetType = normalizedTask.target_type || (taskType.startsWith('k8s_') ? 'k8s' : 'host')
  const targetSnapshot = Array.isArray(normalizedTask.target_snapshot) ? normalizedTask.target_snapshot : []
  const targetRefs = targetSnapshot
    .filter(item => item?.source === 'task_resource' || item?.id)
    .map(item => item?.source === 'task_resource'
      ? { source: 'task_resource', id: item.resource_id || item.id }
      : { source: 'host', id: item.id })
  const k8sTargets = targetType === 'k8s'
    ? targetSnapshot.map(item => ({
      cluster_id: item.cluster_id || item.id,
      kind: item.target_kind || item.kind || 'cluster',
      namespace: item.namespace || '',
      name: item.name || item.target_name || '',
      cluster_name: item.cluster_name || item.hostname || item.name || '',
    })).filter(item => item.cluster_id)
    : []
  return {
    name: normalizedTask.name || '',
    description: normalizedTask.description || '',
    target_type: targetType,
    task_type: taskType,
    execution_mode: normalizedTask.execution_mode || (targetType === 'k8s' ? 'k8s_api' : 'ansible'),
    execution_strategy: normalizedTask.execution_strategy || 'continue',
    timeout_seconds: clampTaskTimeout(normalizedTask.timeout_seconds),
    payload: { ...(normalizedTask.payload || {}) },
    target_refs: targetRefs,
    target_hosts: targetSnapshot,
    k8s_targets: k8sTargets,
    trigger_source: normalizedTask.trigger_source || 'manual',
    source_context: {
      ...(normalizedTask.source_context || {}),
      source: 'task_history',
      source_task_id: normalizedTask.id,
      source_task_name: normalizedTask.name || '',
      request_summary: normalizedTask.description || normalizedTask.summary || '',
    },
  }
}
async function applyTaskDraft(taskDraft, sourceLabel = '任务草稿') {
  if (!taskDraft?.task_type) return
  const scriptTaskDraft = normalizeScriptTaskSource(taskDraft)
  const normalizedTaskName = normalizeTaskDraftTitle(scriptTaskDraft)
  const detectedExecutionKind = detectExecutionKind(scriptTaskDraft)
  hostTableRef.value?.clearSelection()
  k8sTargetTableRef.value?.clearSelection()
  selectedRows.value = []
  selectedK8sRows.value = []
  executionKind.value = detectedExecutionKind
  taskForm.value = {
    name: normalizedTaskName || scriptTaskDraft.name || '',
    target_type: scriptTaskDraft.target_type || (scriptTaskDraft.task_type?.startsWith('k8s_') ? 'k8s' : 'host'),
    task_type: scriptTaskDraft.task_type,
    description: scriptTaskDraft.description || '',
    execution_mode: scriptTaskDraft.execution_mode || (scriptTaskDraft.task_type?.startsWith('k8s_') ? 'k8s_api' : (['run_command', 'run_playbook'].includes(scriptTaskDraft.task_type) ? 'ansible' : 'ssh')),
    execution_strategy: scriptTaskDraft.execution_strategy || 'continue',
    timeout_seconds: clampTaskTimeout(scriptTaskDraft.timeout_seconds),
    payload: buildEditablePayload(scriptTaskDraft.payload || {}, detectedExecutionKind),
  }
  prefillDraftTargetRefs.value = Array.isArray(scriptTaskDraft.target_refs) ? scriptTaskDraft.target_refs : []
  prefillDraftTargets.value = Array.isArray(scriptTaskDraft.target_hosts) ? scriptTaskDraft.target_hosts : []
  prefillSourceContext.value = scriptTaskDraft.source_context || null
  selectedTargetsExpanded.value = Boolean(prefillDraftTargetRefs.value.length || prefillDraftTargets.value.length)
  activeTab.value = 'dispatch'
  await fetchTargets()
  if (scriptTaskDraft.target_type === 'k8s' && Array.isArray(scriptTaskDraft.k8s_targets) && scriptTaskDraft.k8s_targets.length) {
    const clusterIds = new Set(scriptTaskDraft.k8s_targets.map(item => item.cluster_id))
    const resourceIds = new Set(scriptTaskDraft.k8s_targets.map(item => item.resource_id || item.task_resource_id).filter(Boolean))
    selectedK8sRows.value = availableK8sTargets.value.filter(item => clusterIds.has(item.cluster || item.cluster_id || item.id) || resourceIds.has(item.id))
    await nextTick()
    selectedK8sRows.value.forEach(row => k8sTargetTableRef.value?.toggleRowSelection(row, true))
  }
  ElMessage.success(`已载入${sourceLabel}，可继续编辑、执行或保存到模板库`)
}
async function hydratePrefillTaskDraft() {
  if (!route.query.aiopsDraft && !route.query.taskDraft) return
  const raw = sessionStorage.getItem(TASK_DRAFT_STORAGE_KEY)
  sessionStorage.removeItem(TASK_DRAFT_STORAGE_KEY)
  const nextQuery = { ...route.query }
  delete nextQuery.aiopsDraft
  delete nextQuery.taskDraft
  await router.replace({ path: route.path, query: nextQuery })
  if (!raw) return
  let draft = null
  try {
    draft = JSON.parse(raw)
  } catch (error) {
    return
  }
  await applyTaskDraft(draft, draft?.source_context?.source === 'aiops' ? 'AIOps 任务草稿' : '任务草稿')
}
async function submitTemplateDraft() {
  const payload = normalizePayloadByType(templateDraft.value.task_type, templateDraft.value.payload || {})
  if (!templateDraft.value.name) return ElMessage.warning(ui.taskNameRequired)
  if (!validatePayloadByType(templateDraft.value.task_type, payload)) return
  const submitPayload = {
    name: templateDraft.value.name,
    target_type: templateDraft.value.target_type,
    task_type: templateDraft.value.task_type,
    description: templateDraft.value.description,
    payload: sanitizePayload(payload),
    execution_mode: templateDraft.value.execution_mode,
    execution_strategy: templateDraft.value.execution_strategy,
    timeout_seconds: clampTaskTimeout(templateDraft.value.timeout_seconds),
  }
  creatingTemplate.value = true
  try {
    const saved = templateEditorMode.value === 'edit'
      ? await updateHostTaskTemplate(editingTemplateId.value, submitPayload)
      : await createHostTaskTemplate(submitPayload)
    ElMessage.success(templateEditorMode.value === 'edit' ? ui.templateUpdated : ui.templateCreated)
    templateCreateVisible.value = false
    currentTemplate.value = saved
    templateDetailVisible.value = true
    await fetchTemplates()
  } catch (error) {
    ElMessage.error(error?.response?.data?.payload || error?.response?.data?.detail || ui.saveTemplateFailed)
  } finally { creatingTemplate.value = false }
}
async function openDetail(task, options = {}) {
  if (!task?.id) return false
  const silent = Boolean(options.silent)
  detailVisible.value = true
  if (!silent) detailLoading.value = true
  detailTask.value = task
  try {
    detailTask.value = normalizeScriptTaskSource(await getHostTask(task.id))
    return true
  } catch (error) {
    detailVisible.value = false
    detailTask.value = null
    ElMessage.error(ui.loadTaskDetailFailed)
    return false
  } finally {
    if (!silent) detailLoading.value = false
  }
}

async function openRouteTaskDetail(taskId, force = false) {
  const normalizedTaskId = String(Array.isArray(taskId) ? taskId[0] : taskId || '').trim()
  if (!normalizedTaskId) return
  if (!force && openedRouteTaskId.value === normalizedTaskId && detailVisible.value) return
  openedRouteTaskId.value = normalizedTaskId
  activeTab.value = 'history'
  const nextTriggerSource = route.query.source === 'aiopsAudit' ? 'aiops' : taskFilters.value.trigger_source
  if (taskFilters.value.trigger_source !== nextTriggerSource) {
    taskFilters.value.trigger_source = nextTriggerSource
    taskPage.value = 1
    await fetchTasks()
  }
  const currentListTask = tasks.value.find(item => String(item.id) === normalizedTaskId)
  const opened = await openDetail(currentListTask || { id: normalizedTaskId })
  if (opened && !currentListTask && detailTask.value?.id && String(detailTask.value.id) === normalizedTaskId) {
    tasks.value = [detailTask.value, ...tasks.value]
  }
}

async function copyTaskToDraft(task) {
  const sourceTask = task?.executions ? task : await getHostTask(task.id)
  await applyTaskDraft(buildPrefillDraftFromTask(sourceTask), '历史任务草稿')
  detailVisible.value = false
}
async function saveTaskAsTemplate(task) {
  const sourceTask = task?.executions ? task : await getHostTask(task.id)
  const normalizedTask = normalizeScriptTaskSource(sourceTask)
  const payload = normalizePayloadByType(normalizedTask.task_type, normalizedTask.payload || {})
  if (!validatePayloadByType(normalizedTask.task_type, payload)) return
  let templateName = normalizedTask.name || ''
  try {
    const { value } = await ElMessageBox.prompt(ui.saveTemplatePrompt, ui.saveTemplateTitle, {
      confirmButtonText: ui.saveAsTemplate,
      cancelButtonText: ui.cancel,
      inputValue: templateName,
      inputValidator: value => !!String(value || '').trim(),
    })
    templateName = String(value || '').trim()
  } catch (error) {
    return
  }
  savingTemplate.value = true
  try {
    const created = await createHostTaskTemplate({
      name: templateName,
      target_type: normalizedTask.target_type || (normalizedTask.task_type?.startsWith('k8s_') ? 'k8s' : 'host'),
      task_type: normalizedTask.task_type,
      description: normalizedTask.description || '',
      payload: sanitizePayload(payload),
      execution_mode: normalizedTask.execution_mode,
      execution_strategy: normalizedTask.execution_strategy,
      timeout_seconds: clampTaskTimeout(normalizedTask.timeout_seconds),
    })
    ElMessage.success(ui.saveTemplateSuccess)
    await fetchTemplates()
    currentTemplate.value = created
    templateDetailVisible.value = true
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || ui.saveTemplateFailed)
  } finally {
    savingTemplate.value = false
  }
}
async function saveCurrentAsTemplate() {
  const payload = normalizePayload()
  if (!validateTaskPayload(payload)) return
  let templateName = taskForm.value.name || currentExecutionKindLabel.value || ''
  try {
    const { value } = await ElMessageBox.prompt(ui.saveTemplatePrompt, ui.saveTemplateTitle, { confirmButtonText: ui.saveAsTemplate, cancelButtonText: ui.cancel, inputValue: templateName, inputValidator: value => !!String(value || '').trim() })
    templateName = String(value || '').trim()
  } catch (error) { return }
  savingTemplate.value = true
  try {
    const created = await createHostTaskTemplate({ name: templateName, target_type: taskForm.value.target_type, task_type: taskForm.value.task_type, description: taskForm.value.description, payload: sanitizePayload(payload), execution_mode: taskForm.value.execution_mode, execution_strategy: taskForm.value.execution_strategy, timeout_seconds: clampTaskTimeout(taskForm.value.timeout_seconds) })
    ElMessage.success(ui.saveTemplateSuccess)
    await fetchTemplates()
    currentTemplate.value = created
    templateDetailVisible.value = true
    activeTab.value = 'library'
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || ui.saveTemplateFailed)
  } finally { savingTemplate.value = false }
}
function handleHistoryAction(command, row) {
  if (command === 'rename') return renameTask(row)
  if (command === 'copy') return copyTaskToDraft(row)
  if (command === 'template') return saveTaskAsTemplate(row)
  if (command === 'cancel') return handleCancelTask(row)
  if (command === 'delete') return removeTask(row)
}
function handleTemplateAction(command, row) {
  if (command === 'edit') return openTemplateEditDialog(row)
  if (command === 'delete') return removeTemplate(row)
}
async function removeTemplate(template) {
  try {
    await ElMessageBox.confirm(ui.deleteTemplateConfirm, ui.deleteTemplate, { type: 'warning', confirmButtonText: ui.deleteTemplate, cancelButtonText: ui.cancel })
  } catch (error) { return }
  try {
    await deleteHostTaskTemplate(template.id)
    ElMessage.success(ui.deleteTemplateSuccess)
    if (currentTemplate.value?.id === template.id) {
      currentTemplate.value = null
      templateDetailVisible.value = false
    }
    await fetchTemplates()
  } catch (error) { ElMessage.error(ui.deleteTemplateFailed) }
}
async function removeTask(task) {
  try {
    await ElMessageBox.confirm(ui.deleteTaskConfirm, ui.deleteTask, { type: 'warning', confirmButtonText: ui.deleteTask, cancelButtonText: ui.cancel })
  } catch (error) { return }
  try {
    await deleteHostTask(task.id)
    ElMessage.success(ui.deleteTaskSuccess)
    if (detailVisible.value && detailTask.value?.id === task.id) {
      detailVisible.value = false
      detailTask.value = null
    }
    selectedTaskRows.value = selectedTaskRows.value.filter(item => item.id !== task.id)
    await Promise.all([fetchStats(), fetchTasks()])
  } catch (error) { ElMessage.error(error?.response?.data?.detail || ui.deleteTaskFailed) }
}
async function renameTask(task) {
  let nextName = task?.name || ''
  try {
    const { value } = await ElMessageBox.prompt(ui.renameTaskPrompt, ui.renameTaskTitle, {
      confirmButtonText: ui.renameTask,
      cancelButtonText: ui.cancel,
      inputValue: nextName,
      inputValidator: value => !!String(value || '').trim(),
    })
    nextName = String(value || '').trim()
  } catch (error) {
    return
  }
  if (!nextName || nextName === task.name) return
  try {
    const updated = await renameHostTask(task.id, { name: nextName })
    ElMessage.success(ui.renameTaskSuccess)
    const index = tasks.value.findIndex(item => item.id === task.id)
    if (index >= 0) {
      tasks.value[index] = { ...tasks.value[index], ...updated, environment_display: taskEnvironmentDisplay(updated) }
    }
    if (detailTask.value?.id === task.id) {
      detailTask.value = { ...detailTask.value, ...updated, executions: detailTask.value.executions || updated.executions || [] }
    }
    await fetchTasks()
  } catch (error) {
    ElMessage.error(error?.response?.data?.name?.[0] || error?.response?.data?.detail || ui.renameTaskFailed)
  }
}
async function submitTask() {
  if (!taskForm.value.name) return ElMessage.warning(ui.taskNameRequired)
  if (taskForm.value.target_type === 'host' && !effectiveHostTargetRefs.value.length) return ElMessage.warning(ui.hostRequired)
  if (taskForm.value.target_type === 'k8s' && !selectedK8sClusterIds.value.length) return ElMessage.warning(ui.k8sRequired)
  const payload = normalizePayload()
  if (!validateTaskPayload(payload)) return
  const k8sTargetNames = selectedK8sRows.value.map(item => item.name).filter(Boolean)
  const targetSummary = taskForm.value.target_type === 'k8s'
    ? `K8s 集群：${k8sTargetNames.length ? `${k8sTargetNames.slice(0, 3).join('、')}${k8sTargetNames.length > 3 ? ` 等 ${k8sTargetNames.length} 个` : ''}` : `${selectedK8sClusterIds.value.length} 个`}`
    : `目标资源：${effectiveHostTargetRefs.value.length} 个`
  const confirmLines = [`\u4efb\u52a1\u540d\u79f0\uff1a${taskForm.value.name}`, targetSummary, `\u6267\u884c\u7c7b\u578b\uff1a${currentExecutionKindLabel.value}`, `\u6267\u884c\u65b9\u5f0f\uff1a${executionModeLabel(taskForm.value.execution_mode)}`]
  if (taskForm.value.task_type === 'run_command') confirmLines.push(ui.runCommandConfirm)
  if (effectiveHostTargetRefs.value.length > 20) confirmLines.push(ui.overLimitConfirm)
  try {
    await ElMessageBox.confirm(confirmLines.join('<br>'), ui.confirmExecuteTitle, { type: 'warning', dangerouslyUseHTMLString: true, confirmButtonText: ui.confirmExecute, cancelButtonText: ui.cancel })
  } catch (error) { return }
  submitting.value = true
  try {
    const draftHostIds = effectiveHostTargetRefs.value.filter(item => item.source === 'host').map(item => item.id)
    const draftResourceIds = effectiveHostTargetRefs.value.filter(item => item.source === 'task_resource').map(item => item.id)
    const submitPayload = {
      name: taskForm.value.name,
      target_type: taskForm.value.target_type,
      task_type: taskForm.value.task_type,
      description: taskForm.value.description,
      execution_mode: taskForm.value.execution_mode,
      execution_strategy: taskForm.value.execution_strategy,
      timeout_seconds: clampTaskTimeout(taskForm.value.timeout_seconds),
      selection_filters: {
        ...targetFilters.value,
        ...(hasPrefillDraft.value ? {
          source: prefillSourceContext.value?.source || 'manual',
          request_summary: prefillSourceContext.value?.request_summary || '',
          target_refs: effectiveHostTargetRefs.value,
          source_task_id: prefillSourceContext.value?.source_task_id || undefined,
        } : {}),
      },
      payload: sanitizePayload(payload),
      trigger_source: prefillSourceContext.value?.source === 'aiops' ? 'aiops' : 'manual',
      source_context: hasPrefillDraft.value ? { ...prefillSourceContext.value } : { source: 'manual' },
    }
    if (taskForm.value.target_type === 'k8s') {
      submitPayload.k8s_targets = buildK8sSubmitTargets(payload)
    } else {
      submitPayload.resource_ids = selectedRows.value.length ? selectedHostIds.value : draftResourceIds
      submitPayload.host_ids = selectedRows.value.length ? [] : draftHostIds
    }
    const task = await createHostTask(submitPayload)
    ElMessage.success(ui.taskExecuted)
    detailTask.value = task
    detailVisible.value = true
    applyExecutionKind('shell')
    clearSelection()
    activeTab.value = 'history'
    await Promise.all([fetchStats(), fetchTasks()])
  } catch (error) {
    ElMessage.error(taskRequestErrorMessage(error, ui.executeTaskFailed))
  } finally { submitting.value = false }
}
async function handleRerun(task) {
  try {
    const result = await rerunHostTask(task.id)
    ElMessage.success(ui.taskRerun)
    detailTask.value = result
    detailVisible.value = true
    await Promise.all([fetchStats(), fetchTasks()])
  } catch (error) { ElMessage.error(ui.rerunTaskFailed) }
}
async function handleExecuteTask(task) {
  try {
    await ElMessageBox.confirm(`确认执行任务「${task.name}」？`, ui.confirmExecuteTitle, { type: 'warning', confirmButtonText: ui.confirmExecute, cancelButtonText: ui.cancel })
  } catch (error) { return }
  try {
    const result = await executeHostTask(task.id)
    ElMessage.success(ui.taskExecuted)
    detailTask.value = result
    detailVisible.value = true
    await Promise.all([fetchStats(), fetchTasks()])
  } catch (error) { ElMessage.error(error?.response?.data?.detail || ui.executeTaskFailed) }
}
async function handleCancelTask(task) {
  try {
    await ElMessageBox.confirm(ui.cancelConfirm, ui.cancelTask, { type: 'warning', confirmButtonText: ui.cancelTask, cancelButtonText: ui.cancel })
  } catch (error) { return }
  try {
    await cancelHostTask(task.id)
    ElMessage.success(ui.cancelSuccess)
    await Promise.all([fetchStats(), fetchTasks()])
    if (detailVisible.value && detailTask.value?.id === task.id) await openDetail(task)
  } catch (error) { ElMessage.error(error?.response?.data?.detail || ui.cancelTaskFailed) }
}
async function handleBatchCancel() {
  if (!selectedCancelableTaskIds.value.length) return
  try {
    await ElMessageBox.confirm(ui.cancelBatchConfirm, ui.batchCancel, { type: 'warning', confirmButtonText: ui.batchCancel, cancelButtonText: ui.cancel })
  } catch (error) { return }
  try {
    const result = await batchCancelHostTasks({ ids: selectedCancelableTaskIds.value })
    ElMessage.success(result?.detail || ui.batchCancelSuccess)
    selectedTaskRows.value = []
    await Promise.all([fetchStats(), fetchTasks()])
  } catch (error) { ElMessage.error(error?.response?.data?.detail || ui.batchCancelFailed) }
}
function stopHistoryAutoRefresh() {
  if (!historyRefreshTimer.value) return
  clearInterval(historyRefreshTimer.value)
  historyRefreshTimer.value = null
}
function stopDetailAutoRefresh() {
  if (!detailRefreshTimer.value) return
  clearInterval(detailRefreshTimer.value)
  detailRefreshTimer.value = null
}
function syncHistoryAutoRefresh() {
  if (activeTab.value !== 'history' || !hasActiveHistoryTasks.value) {
    stopHistoryAutoRefresh()
    return
  }
  if (historyRefreshTimer.value) return
  historyRefreshTimer.value = setInterval(async () => {
    if (activeTab.value !== 'history') return
    await Promise.all([fetchStats(), fetchTasks()])
  }, 5000)
}
function syncDetailAutoRefresh() {
  if (!detailVisible.value || !detailTaskActive.value || !detailTask.value?.id) {
    stopDetailAutoRefresh()
    return
  }
  if (detailRefreshTimer.value) return
  detailRefreshTimer.value = setInterval(async () => {
    if (!detailVisible.value || !detailTask.value?.id) return
    await openDetail(detailTask.value, { silent: true })
    if (!detailTaskActive.value) {
      await Promise.all([fetchStats(), fetchTasks()])
    }
  }, 3000)
}
async function reloadAll() {
  await Promise.all([fetchStats(), fetchTasks(), fetchTemplates()])
}
onMounted(async () => {
  if (route.query.target === 'k8s') {
    await applyExecutionKind('k8s_command')
  } else {
    await applyExecutionKind('shell')
  }
  await reloadAll()
  await hydratePrefillTaskDraft()
  await openRouteTaskDetail(route.query.taskId, true)
  syncHistoryAutoRefresh()
  syncDetailAutoRefresh()
})
onBeforeUnmount(() => {
  stopHistoryAutoRefresh()
  stopDetailAutoRefresh()
})
watch([activeTab, hasActiveHistoryTasks], syncHistoryAutoRefresh)
watch([detailVisible, detailTaskActive], syncDetailAutoRefresh)
watch(() => route.query.aiopsDraft, async (value, previousValue) => {
  if (!value || value === previousValue) return
  await hydratePrefillTaskDraft()
})
watch(() => route.query.taskDraft, async (value, previousValue) => {
  if (!value || value === previousValue) return
  await hydratePrefillTaskDraft()
})
watch(() => route.query.taskId, async (value, previousValue) => {
  if (!value || value === previousValue) return
  await openRouteTaskDetail(value)
})
</script>
<style scoped>
.task-center-page {
  --tc-border: rgba(15, 23, 42, 0.08);
  --tc-border-strong: rgba(59, 130, 246, 0.18);
  --tc-bg-soft: linear-gradient(180deg, rgba(255, 255, 255, 0.98) 0%, rgba(248, 250, 252, 0.94) 100%);
  --tc-bg-panel: linear-gradient(180deg, #ffffff 0%, #f8fbfc 100%);
  --tc-bg-subtle: rgba(248, 250, 252, 0.92);
  --tc-shadow: 0 8px 24px rgba(15, 23, 42, 0.05);
  --tc-shadow-hover: 0 14px 30px rgba(15, 23, 42, 0.08);
  --tc-primary: #2563eb;
  --tc-primary-soft: rgba(37, 99, 235, 0.08);
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.task-inner-tabs {
  display: flex;
  width: 100%;
  align-self: stretch;
  margin-bottom: 0;
  padding: 3px;
  border: 1px solid rgba(148, 163, 184, 0.16);
  border-radius: 12px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.96), rgba(248, 250, 252, 0.9));
  box-shadow: 0 12px 26px rgba(15, 23, 42, 0.04);
}

.task-inner-tab-btn {
  min-height: 38px;
  padding: 0 18px;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: #4e5969;
  font-size: 13px;
  font-weight: 700;
  line-height: 1.2;
  gap: 6px;
}

.task-inner-tab-btn:hover {
  background: rgba(51, 112, 255, 0.06);
}

.task-inner-tab-btn.active {
  background: #e8f0ff;
  color: #245bdb;
  box-shadow: inset 0 0 0 1px rgba(51, 112, 255, 0.08);
}

.inner-tab-title {
  font-size: 13px;
  font-weight: 700;
  line-height: 1.1;
}

.task-source-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
  margin: 0;
}

.task-source-card {
  min-height: 68px;
  padding: 14px 16px;
  border: 1px solid rgba(15, 23, 42, 0.08);
  border-radius: 14px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.98) 0%, rgba(252, 253, 255, 0.94) 100%);
  display: flex;
  justify-content: center;
  align-items: center;
  cursor: pointer;
  text-align: left;
  box-shadow: 0 4px 14px rgba(15, 23, 42, 0.03);
  transition: 0.2s ease border-color, 0.2s ease box-shadow, 0.2s ease background;
}

.task-source-card__row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  width: 100%;
}

.task-source-card:hover {
  border-color: rgba(36, 91, 219, 0.16);
  box-shadow: 0 10px 20px rgba(36, 91, 219, 0.06);
}

.task-source-card.is-active {
  border-color: rgba(36, 91, 219, 0.26);
  background: linear-gradient(180deg, #f4f7ff 0%, #ffffff 100%);
  box-shadow:
    0 0 0 1px rgba(36, 91, 219, 0.08),
    0 12px 22px rgba(36, 91, 219, 0.08);
}

.task-source-card--warning {
  background: linear-gradient(180deg, #fffdfa 0%, #ffffff 100%);
}

.task-source-card--success {
  background: linear-gradient(180deg, #fbfffd 0%, #ffffff 100%);
}

.task-source-card--danger {
  background: linear-gradient(180deg, #fffafb 0%, #ffffff 100%);
}

.task-source-card span {
  color: #334155;
  font-size: 13px;
  font-weight: 600;
  line-height: 1;
}

.task-source-card strong {
  color: #1f2329;
  font-size: 24px;
  line-height: 1;
  font-weight: 600;
}

.k8s-cluster-tip {
  margin-bottom: 0;
}

.glass-card {
  background: var(--tc-bg-panel);
  border: 1px solid var(--tc-border);
  border-radius: 14px;
  box-shadow: var(--tc-shadow);
  padding: 14px;
}

.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 8px;
  font-weight: 600;
  color: #0f172a;
}

.card-title-with-action {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  flex-wrap: wrap;
}

.k8s-logic-button {
  min-height: 24px;
  padding: 0 7px;
  border-radius: 8px;
  font-size: 12px;
  font-weight: 500;
}

.k8s-logic-button :deep(.el-icon) {
  margin-right: 3px;
}

.compact-head {
  margin-bottom: 8px;
}

.composer-grid {
  display: grid;
  grid-template-columns: 248px minmax(0, 1fr);
  gap: 12px;
}

.library-grid {
  grid-template-columns: minmax(0, 1.18fr) minmax(320px, 0.82fr);
}

.side-stack {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.task-form-head-actions,
.history-actions {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.preset-grid,
.template-grid,
.snippet-grid {
  display: grid;
  gap: 8px;
}

.preset-card,
.snippet-card,
.template-card {
  padding: 12px;
  border: 1px solid var(--tc-border);
  border-radius: 12px;
  background: linear-gradient(180deg, #ffffff 0%, #fafcff 100%);
  box-shadow: 0 4px 14px rgba(15, 23, 42, 0.03);
  text-align: left;
  transition: transform 0.2s ease, box-shadow 0.2s ease, border-color 0.2s ease, background 0.2s ease;
}

.preset-card,
.snippet-card {
  cursor: pointer;
}

.preset-card:hover,
.snippet-card:hover,
.template-card:hover {
  border-color: var(--tc-border-strong);
  box-shadow: var(--tc-shadow-hover);
  background: linear-gradient(180deg, #ffffff 0%, #f8fbff 100%);
  transform: translateY(-1px);
}

.preset-card.active {
  border-color: rgba(37, 99, 235, 0.22);
  background: linear-gradient(180deg, #f8fbff 0%, #eef5ff 100%);
  box-shadow: 0 10px 24px rgba(37, 99, 235, 0.08);
}

.preset-title {
  color: #0f172a;
  font-weight: 600;
}

.preset-desc,
.template-desc,
.section-tip {
  margin-top: 4px;
  color: #64748b;
  font-size: 11px;
  line-height: 1.5;
}

.section-gap {
  margin-bottom: 10px;
}

.template-title-row,
.snippet-title-row,
.template-action-row,
.template-tag-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  flex-wrap: wrap;
}

.template-meta-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  flex-wrap: wrap;
  margin-top: 8px;
  color: #64748b;
  font-size: 12px;
}

.template-preview {
  margin-top: 10px;
  padding: 10px 12px;
  border-radius: 12px;
  background: rgba(15, 23, 42, 0.025);
  border: 1px dashed rgba(148, 163, 184, 0.24);
}

.template-preview-label {
  display: block;
  margin-bottom: 6px;
  color: #64748b;
  font-size: 12px;
}

.template-preview-code {
  display: block;
  color: #0f172a;
  font-size: 12px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-all;
}

.snippet-scene {
  color: #2563eb;
  font-size: 12px;
  background: rgba(59, 130, 246, 0.1);
  border-radius: 999px;
  padding: 2px 8px;
}

.snippet-command {
  display: block;
  margin-top: 8px;
  padding: 8px 10px;
  border-radius: 10px;
  background: #0f172a;
  color: #e2e8f0;
  font-size: 12px;
  white-space: pre-wrap;
  word-break: break-all;
}

.inline-empty {
  padding: 12px 4px;
  color: #94a3b8;
  font-size: 12px;
  text-align: center;
}

.mini-panel {
  padding: 14px;
  border-radius: 16px;
  background: rgba(248, 250, 252, 0.9);
  border: 1px solid rgba(148, 163, 184, 0.14);
}

.mini-panel-title {
  font-size: 13px;
  font-weight: 600;
  color: #0f172a;
  margin-bottom: 10px;
}

.mini-bullet {
  position: relative;
  padding-left: 14px;
  color: #64748b;
  font-size: 12px;
  line-height: 1.7;
}

.mini-bullet::before {
  content: '';
  position: absolute;
  left: 0;
  top: 8px;
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: #60a5fa;
}

.k8s-logic-panel {
  display: grid;
  gap: 10px;
}

.k8s-logic-item {
  padding: 12px 14px;
  border-radius: 12px;
  background: linear-gradient(180deg, #ffffff 0%, #f8fbff 100%);
  border: 1px solid rgba(148, 163, 184, 0.16);
}

.k8s-logic-item strong {
  display: block;
  margin-bottom: 5px;
  color: #0f172a;
  font-size: 13px;
  font-weight: 600;
}

.k8s-logic-item span {
  display: block;
  color: #64748b;
  font-size: 12px;
  line-height: 1.6;
}

.task-inline-tip {
  margin-bottom: 8px;
  padding: 7px 10px;
  border-radius: 12px;
  background: linear-gradient(90deg, rgba(37, 99, 235, 0.06) 0%, rgba(14, 165, 233, 0.03) 100%);
  border: 1px solid rgba(37, 99, 235, 0.1);
  color: #64748b;
  font-size: 11px;
  line-height: 1.45;
}

.task-form {
  margin-top: 2px;
}

.task-dispatch-form :deep(.el-form-item) {
  margin-bottom: 12px;
}

.form-row {
  display: flex;
  gap: 10px;
}

.form-col {
  flex: 1;
}

.form-col.wide {
  flex: 1 1 100%;
}

.toolbar {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 8px;
  margin-bottom: 8px;
  padding: 8px;
  border-radius: 12px;
  border: 1px solid rgba(148, 163, 184, 0.12);
  background: linear-gradient(180deg, rgba(248, 250, 252, 0.92) 0%, rgba(255, 255, 255, 0.96) 100%);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.9);
}

.toolbar-row {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.toolbar-row-main {
  flex-wrap: nowrap;
  overflow-x: auto;
  padding-bottom: 1px;
}

.toolbar-row-summary {
  align-items: stretch;
}

.toolbar-spacer {
  flex: 1 1 auto;
  min-width: 16px;
}

.toolbar :deep(.el-input__wrapper),
.toolbar :deep(.el-select__wrapper) {
  min-height: 28px;
  border-radius: 8px;
  box-shadow: 0 0 0 1px rgba(148, 163, 184, 0.12) inset;
  background: rgba(255, 255, 255, 0.94);
}

.toolbar :deep(.el-input__wrapper:hover),
.toolbar :deep(.el-select__wrapper:hover) {
  box-shadow: 0 0 0 1px rgba(59, 130, 246, 0.16) inset;
}

.toolbar :deep(.el-tag) {
  height: 26px;
  border-radius: 8px;
}

.toolbar-row-main :deep(.el-button),
.history-actions :deep(.el-button),
.task-form-head-actions :deep(.el-button),
.head-actions :deep(.el-button) {
  min-height: 26px;
  padding: 0 9px;
  border-radius: 8px;
  font-weight: 500;
}

.toolbar-row-main :deep(.el-button:not(.el-button--primary)),
.history-actions :deep(.el-button:not(.el-button--primary)),
.task-form-head-actions :deep(.el-button:not(.el-button--primary)),
.head-actions :deep(.el-button:not(.el-button--primary)) {
  border-color: rgba(148, 163, 184, 0.12);
  background: rgba(255, 255, 255, 0.9);
  color: #475569;
  box-shadow: none;
}

.toolbar-row-main :deep(.el-button:not(.is-link):hover),
.history-actions :deep(.el-button:not(.is-link):hover),
.task-form-head-actions :deep(.el-button:not(.is-link):hover),
.head-actions :deep(.el-button:not(.is-link):hover) {
  border-color: rgba(59, 130, 246, 0.18);
  color: #1d4ed8;
  background: #f8fbff;
}

.selection-strip {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  width: 100%;
}

.selection-pill {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 4px 9px;
  border-radius: 999px;
  background: rgba(59, 130, 246, 0.08);
  border: 1px solid rgba(59, 130, 246, 0.1);
  color: #2563eb;
  font-size: 11px;
}

.selection-pill-button {
  border: 1px solid rgba(59, 130, 246, 0.1);
  cursor: pointer;
}

.selection-pill-button:hover {
  background: rgba(59, 130, 246, 0.12);
}

.selection-pill-button {
  background: rgba(59, 130, 246, 0.08);
  font: inherit;
}

.selection-pill-button .el-icon {
  transition: transform 0.2s ease;
}

.selection-pill-button .el-icon.is-expanded {
  transform: rotate(180deg);
}

.selection-pill.success {
  background: rgba(16, 185, 129, 0.1);
  border-color: rgba(16, 185, 129, 0.12);
  color: #047857;
}

.selection-pill.warning {
  background: rgba(245, 158, 11, 0.1);
  border-color: rgba(245, 158, 11, 0.12);
  color: #b45309;
}

.selection-pill.danger {
  background: rgba(239, 68, 68, 0.1);
  border-color: rgba(239, 68, 68, 0.12);
  color: #b91c1c;
}

.selection-pill.info {
  background: rgba(14, 116, 144, 0.1);
  border-color: rgba(14, 116, 144, 0.14);
  color: #0f766e;
}

.selection-pill.muted {
  background: rgba(100, 116, 139, 0.08);
  border-color: rgba(100, 116, 139, 0.12);
  color: #475569;
}

.selected-target-panel {
  display: grid;
  grid-template-columns: 1fr;
  gap: 6px;
  width: 100%;
  margin-top: 8px;
}

.selected-target-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  min-width: 0;
  padding: 8px 12px;
  border-radius: 10px;
  border: 1px solid rgba(59, 130, 246, 0.1);
  background: linear-gradient(180deg, rgba(248, 251, 255, 0.96) 0%, rgba(255, 255, 255, 0.98) 100%);
}

.selected-target-item strong {
  flex: 1 1 auto;
  min-width: 0;
  color: #1e293b;
  font-size: 12px;
  font-weight: 700;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.selected-target-item span {
  flex: 0 1 auto;
  max-width: 55%;
  color: #64748b;
  font-size: 11px;
  text-align: right;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.submit-row {
  margin-top: 8px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
}

.submit-tip {
  color: #64748b;
  font-size: 11px;
}

.submit-actions {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.template-toolbar {
  margin-bottom: 6px;
}

.template-editor-topbar {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 6px;
}

.template-editor-presets {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.template-editor-label {
  color: #64748b;
  font-size: 11px;
}

.template-editor-chip {
  padding: 5px 9px;
  border: 1px solid rgba(59, 130, 246, 0.08);
  border-radius: 999px;
  background: rgba(59, 130, 246, 0.06);
  color: #2563eb;
  font-size: 11px;
  cursor: pointer;
  transition: 0.2s ease background, 0.2s ease transform;
}

.template-editor-chip:hover {
  background: rgba(59, 130, 246, 0.12);
  transform: translateY(-1px);
}

.template-editor-overview {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
  margin-bottom: 6px;
}

.template-overview-card {
  padding: 10px 12px;
  border-radius: 14px;
  background: linear-gradient(180deg, #ffffff 0%, #f7fbff 100%);
  border: 1px solid rgba(148, 163, 184, 0.14);
}

.template-overview-label {
  display: block;
  margin-bottom: 4px;
  color: #64748b;
  font-size: 11px;
}

.template-editor-layout {
  display: grid;
  grid-template-columns: minmax(0, 1.28fr) minmax(280px, 0.72fr);
  gap: 10px;
}

.template-editor-main {
  min-width: 0;
}

.template-editor-side {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.template-editor-panel {
  padding: 12px;
  border-radius: 16px;
  background: linear-gradient(180deg, #ffffff 0%, #f8fbff 100%);
  border: 1px solid rgba(148, 163, 184, 0.14);
}

.template-editor-section + .template-editor-section {
  margin-top: 6px;
}

.template-editor-section-title {
  margin-bottom: 6px;
  color: #0f172a;
  font-size: 12px;
  font-weight: 600;
}

.template-payload-stack {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.template-editor-help {
  background: linear-gradient(180deg, #f8fbff 0%, #f3f7fd 100%);
}

.template-editor-preview {
  align-self: start;
}

.template-code-block {
  margin-top: 6px;
  max-height: 280px;
  overflow: auto;
}

.history-card {
  min-width: 0;
}

.task-center-page > .history-card,
.task-center-page > .template-list-card {
  flex-grow: 1;
}

.history-head {
  margin-bottom: 6px;
}

.history-toolbar {
  margin: 6px 0;
}

.pagination-row {
  display: flex;
  justify-content: flex-end;
  margin-top: 8px;
}

.history-row-actions {
  display: flex;
  align-items: center;
  justify-content: flex-start;
  gap: 8px;
  flex-wrap: nowrap;
}

.history-row-actions :deep(.el-button) {
  margin-left: 0;
}

.history-name-cell {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.history-name-button {
  display: inline-flex;
  width: fit-content;
  max-width: 100%;
  padding: 0;
  border: none;
  background: transparent;
  cursor: pointer;
  text-align: left;
}

.history-name-button:hover strong {
  color: #2563eb;
}

.history-name-button:focus-visible {
  outline: 2px solid rgba(37, 99, 235, 0.22);
  outline-offset: 2px;
  border-radius: 8px;
}

.history-name-cell strong {
  color: #0f172a;
  font-size: 12px;
  line-height: 1.35;
  transition: color 0.2s ease;
}

.history-name-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  color: #94a3b8;
  font-size: 11px;
  line-height: 1.4;
}

.history-more-btn {
  color: #64748b;
  padding: 4px 8px;
  border-radius: 999px;
}

.task-center-page :deep(.history-more-btn.el-button:hover) {
  color: #2563eb;
  background: rgba(37, 99, 235, 0.08);
}

.task-detail-shell {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.detail-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
  flex-wrap: wrap;
}

.detail-heading-main {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.detail-title-row {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.detail-main-title {
  color: #0f172a;
  font-size: 15px;
  line-height: 1.3;
}

.detail-subline {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  color: #64748b;
  font-size: 11px;
}

.detail-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 0;
}

.detail-summary.compact {
  gap: 4px;
  justify-content: flex-end;
}

.detail-chip {
  padding: 4px 8px;
  border-radius: 999px;
  background: rgba(59, 130, 246, 0.08);
  border: 1px solid rgba(59, 130, 246, 0.12);
  color: #1e3a8a;
  font-size: 11px;
  line-height: 1.4;
}

.detail-desc {
  margin-bottom: 6px;
  color: #64748b;
  font-size: 12px;
}

.task-metric-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
}

.task-metric-grid.compact {
  gap: 5px;
}

.task-metric-card {
  padding: 8px 10px;
  border-radius: 14px;
  background: linear-gradient(180deg, #ffffff 0%, #f8fbff 100%);
  border: 1px solid rgba(148, 163, 184, 0.14);
}

.task-metric-card.success {
  background: linear-gradient(180deg, #f0fdf4 0%, #f7fee7 100%);
}

.task-metric-card.danger {
  background: linear-gradient(180deg, #fff1f2 0%, #fef2f2 100%);
}

.task-metric-card.warning {
  background: linear-gradient(180deg, #fffbeb 0%, #fefce8 100%);
}

.task-metric-label {
  display: block;
  margin-bottom: 4px;
  color: #64748b;
  font-size: 11px;
}

.detail-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 5px;
}

.detail-grid.compact {
  gap: 5px;
}

.detail-section {
  display: flex;
  flex-direction: column;
  gap: 3px;
  margin-bottom: 0;
  padding: 8px 10px;
  border-radius: 10px;
  background: rgba(248, 250, 252, 0.88);
  border: 1px solid rgba(148, 163, 184, 0.14);
}

.detail-section-title {
  margin-bottom: 0;
  color: #0f172a;
  font-size: 11px;
  font-weight: 600;
}

.detail-kv {
  color: #475569;
  font-size: 11px;
  line-height: 1.5;
}

.compact-stack {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 3px 8px;
}

.compact-kv {
  padding: 5px 0;
  min-height: 28px;
}

.detail-code-block {
  margin: 0;
  padding: 9px 10px;
  border-radius: 10px;
  background: #0f172a;
  color: #e2e8f0;
  font-size: 11px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
}

.yaml-code-block {
  max-height: 420px;
  overflow: auto;
  tab-size: 2;
}

.detail-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 4px;
  flex-wrap: wrap;
  margin-top: 4px;
}

.danger-text {
  color: #b91c1c;
}

.target-list {
  display: flex;
  flex-direction: column;
  gap: 0;
}

.target-list-item {
  display: grid;
  grid-template-columns: minmax(0, 1.2fr) minmax(120px, 0.9fr) minmax(80px, 0.7fr);
  gap: 10px;
  align-items: center;
  padding: 6px 0;
  border-bottom: 1px dashed rgba(148, 163, 184, 0.18);
}

.target-list-item:last-child {
  border-bottom: none;
  padding-bottom: 0;
}

.target-list-item:first-child {
  padding-top: 0;
}

.target-list-item strong {
  color: #0f172a;
  font-size: 12px;
}

.target-list-item span {
  color: #64748b;
  font-size: 11px;
}

.execution-target-cell {
  display: flex;
  flex-direction: column;
  gap: 1px;
  min-width: 0;
}

.execution-target-cell strong {
  color: #0f172a;
  font-size: 12px;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.execution-target-cell span {
  color: #64748b;
  font-size: 11px;
}

.execution-progress-card {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 10px;
  padding: 10px 12px;
  border-radius: 12px;
  border: 1px solid rgba(59, 130, 246, 0.1);
  background: linear-gradient(180deg, rgba(248, 251, 255, 0.96) 0%, rgba(255, 255, 255, 0.98) 100%);
}

.execution-progress-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  min-width: 0;
}

.execution-progress-head strong {
  color: #1f2937;
  font-size: 12px;
}

.execution-progress-head span {
  color: #64748b;
  font-size: 11px;
  text-align: right;
}

.output-preview-card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 9px 12px;
  border-radius: 12px;
  background: #0f172a;
  color: #e2e8f0;
  box-shadow: inset 0 0 0 1px rgba(148, 163, 184, 0.12);
  cursor: pointer;
}

.output-preview-card:hover {
  box-shadow: inset 0 0 0 1px rgba(96, 165, 250, 0.32);
}

.output-preview-text {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-family: Consolas, Monaco, monospace;
  font-size: 12px;
  line-height: 1.45;
}

.output-preview-action {
  flex: none;
}

.output-dialog-block {
  margin: 0;
  max-height: 62vh;
  overflow: auto;
  white-space: pre;
  word-break: normal;
  padding: 14px 16px;
  border-radius: 14px;
  background: #0f172a;
  color: #e2e8f0;
  font-family: Consolas, Monaco, monospace;
  font-size: 12px;
  line-height: 1.6;
}

.task-center-page :deep(.el-input__wrapper),
.task-center-page :deep(.el-textarea__inner),
.task-center-page :deep(.el-select__wrapper) {
  border-radius: 12px;
  box-shadow: 0 0 0 1px rgba(148, 163, 184, 0.16) inset;
  background: rgba(255, 255, 255, 0.92);
}

.task-center-page :deep(.el-input__wrapper:hover),
.task-center-page :deep(.el-select__wrapper:hover),
.task-center-page :deep(.el-textarea__inner:hover) {
  box-shadow: 0 0 0 1px rgba(59, 130, 246, 0.18) inset;
}

.task-center-page :deep(.el-input__wrapper.is-focus),
.task-center-page :deep(.el-select__wrapper.is-focused),
.task-center-page :deep(.el-textarea__inner:focus) {
  box-shadow: 0 0 0 1px rgba(37, 99, 235, 0.22) inset;
}

.script-editor-shell {
  width: 100%;
  overflow: hidden;
  border-radius: 10px;
  border: 1px solid rgba(148, 163, 184, 0.16);
  background: #0f172a;
}

.script-editor-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  min-height: 24px;
  padding: 3px 9px;
  background: rgba(15, 23, 42, 0.96);
  border-bottom: 1px solid rgba(226, 232, 240, 0.08);
  color: #cbd5e1;
  font-size: 10px;
  line-height: 1.2;
}

.script-editor-head strong {
  color: #93c5fd;
  font-size: 10px;
  letter-spacing: 0;
}

.script-editor-body {
  position: relative;
  min-height: 280px;
  max-height: 460px;
  overflow: hidden;
  background: #0f172a;
}

.script-editor-highlight,
.script-editor-textarea {
  box-sizing: border-box;
  width: 100%;
  min-height: 280px;
  max-height: 460px;
  margin: 0;
  padding: 12px 14px;
  overflow: auto;
  font-family: Consolas, Monaco, monospace;
  font-size: 12px;
  line-height: 1.65;
  white-space: pre;
  tab-size: 2;
}

.script-editor-highlight {
  position: absolute;
  inset: 0;
  color: #dbeafe;
  pointer-events: none;
}

.script-editor-textarea {
  position: relative;
  z-index: 1;
  display: block;
  resize: vertical;
  border: none;
  outline: none;
  box-shadow: none;
  background: transparent;
  color: transparent;
  caret-color: #f8fafc;
  -webkit-text-fill-color: transparent;
}

.script-editor-textarea::selection {
  background: rgba(96, 165, 250, 0.28);
  -webkit-text-fill-color: transparent;
}

.script-editor-textarea::placeholder {
  color: rgba(203, 213, 225, 0.45);
  -webkit-text-fill-color: rgba(203, 213, 225, 0.45);
}

.tok-comment { color: #64748b; }
.tok-string { color: #86efac; }
.tok-keyword { color: #93c5fd; font-weight: 700; }
.tok-command { color: #fbbf24; }
.tok-variable { color: #c4b5fd; }
.tok-number { color: #fdba74; }
.tok-bool { color: #f0abfc; font-weight: 700; }

.script-editor-body:focus-within {
  box-shadow: inset 0 0 0 1px rgba(96, 165, 250, 0.28);
}

.script-editor-shell--python .script-editor-head strong {
  color: #facc15;
}

.script-editor-shell--playbook .script-editor-head strong {
  color: #86efac;
}

.task-center-page :deep(.el-button) {
  border-radius: 10px;
}

.task-center-page :deep(.el-table) {
  --el-table-border-color: rgba(148, 163, 184, 0.16);
  --el-table-header-bg-color: #f8fafc;
  --el-table-row-hover-bg-color: #f8fbff;
  border: 1px solid rgba(148, 163, 184, 0.14);
  border-radius: 12px;
  overflow: hidden;
}

.task-center-page :deep(.el-table th.el-table__cell) {
  color: #475569;
  font-weight: 600;
  background: #f8fafc;
}

.task-center-page :deep(.el-drawer__header) {
  margin-bottom: 0;
  padding-bottom: 12px;
  border-bottom: 1px solid rgba(148, 163, 184, 0.14);
}

.task-center-page :deep(.task-center-drawer) {
  height: 100vh;
  max-height: 100vh;
}

.task-center-page :deep(.task-center-drawer .el-drawer__header) {
  padding: 14px 18px 10px;
}

.task-center-page :deep(.task-center-drawer .el-drawer__body) {
  min-height: calc(100vh - 56px);
  max-height: calc(100vh - 56px);
  overflow-y: auto;
  padding: 14px 16px 16px;
  background: #f8fafc;
}

@media (max-width: 1100px) {
  .composer-grid,
  .library-grid,
  .task-source-grid,
  .template-editor-layout,
  .template-editor-overview,
  .task-metric-grid,
  .detail-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 900px) {
  .detail-heading,
  .form-row,
  .submit-row,
  .template-title-row,
  .template-action-row {
    flex-direction: column;
    align-items: stretch;
  }

  .compact-stack {
    grid-template-columns: 1fr;
  }

  .target-list-item {
    grid-template-columns: 1fr;
    gap: 4px;
  }
}
</style>
