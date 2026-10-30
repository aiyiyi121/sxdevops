<template>
  <div class="alerts-page workbench-page-shell">
    <section class="hero panel">
      <div class="hero-copy">
        <div class="hero-title-row">
          <span class="hero-icon">
            <el-icon><Bell /></el-icon>
          </span>
          <h2>&#x544A;&#x8B66;&#x4E2D;&#x5FC3;</h2>
          <p class="page-inline-desc">&#x7EDF;&#x4E00;&#x63A5;&#x6536;&#x591A;&#x6E90;&#x544A;&#x8B66;&#xFF0C;&#x652F;&#x6301;&#x805A;&#x5408;&#x3001;&#x6291;&#x5236;&#x3001;&#x5C4F;&#x853D;&#x3001;&#x8BA4;&#x9886;&#x3001;&#x5347;&#x7EA7;&#x4E0E;&#x901A;&#x77E5;&#x5206;&#x53D1;</p>
        </div>
      </div>
      <div class="hero-actions">
        <el-button size="small" :icon="Refresh" :loading="loading || configLoading" @click="refreshAll">&#x5237;&#x65B0;</el-button>
      </div>
    </section>

    <div class="audit-grid alert-top-stats">
      <button
        v-for="card in statCards"
        :key="card.key"
        type="button"
        class="audit-card audit-card--inline audit-card--action alert-summary-card"
        :class="[card.tone, { 'is-active': activeStatKey === card.key }]"
        @click="applyStatFilter(card)"
      >
        <div class="stat-label">{{ card.label }}</div>
        <div class="stat-value">{{ card.value }}</div>
      </button>
    </div>

    <div class="neo-tabs theme-blue alert-center-tabs">
      <button v-if="canViewAlerts" class="neo-tab-btn" :class="{ active: activeTab === 'events' }" @click="switchTab('events')">
        <el-icon style="margin-right: 4px;"><Bell /></el-icon>&#x544A;&#x8B66;&#x4E8B;&#x4EF6;
      </button>
      <button v-if="canViewConfig" class="neo-tab-btn" :class="{ active: activeTab === 'policies' }" @click="switchTab('policies')">
        <el-icon style="margin-right: 4px;"><Operation /></el-icon>&#x7B56;&#x7565;&#x7F16;&#x6392;
      </button>
      <button v-if="canViewConfig" class="neo-tab-btn" :class="{ active: activeTab === 'notify' }" @click="switchTab('notify')">
        <el-icon style="margin-right: 4px;"><Setting /></el-icon>&#x901A;&#x77E5;&#x914D;&#x7F6E;
      </button>
      <button v-if="canViewAlerts" class="neo-tab-btn" :class="{ active: activeTab === 'logs' }" @click="switchTab('logs')">
        <el-icon style="margin-right: 4px;"><Document /></el-icon>&#x901A;&#x77E5;&#x8BB0;&#x5F55;
      </button>
      <button v-if="canViewConfig" class="neo-tab-btn" :class="{ active: activeTab === 'integrations' }" @click="switchTab('integrations')">
        <el-icon style="margin-right: 4px;"><Connection /></el-icon>&#x544A;&#x8B66;&#x63A5;&#x5165;&#x6E90;
      </button>
    </div>

    <template v-if="activeTab === 'events' && canViewAlerts">
      <section class="panel workbench-fill-panel">
        <div class="toolbar">
          <el-select v-model="filters.status" size="small" clearable placeholder="&#x72B6;&#x6001;" @change="handleFilterChange">
            <el-option label="&#x6D3B;&#x8DC3;" value="active" />
            <el-option label="&#x5DF2;&#x6062;&#x590D;" value="resolved" />
            <el-option label="&#x5DF2;&#x5C4F;&#x853D;" value="muted" />
            <el-option label="&#x5DF2;&#x5173;&#x95ED;" value="closed" />
          </el-select>
          <el-select v-model="filters.source_type" size="small" clearable placeholder="&#x6765;&#x6E90;" @change="handleFilterChange">
            <el-option v-for="item in providerOptions" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
          <el-select v-model="filters.environment" size="small" clearable filterable allow-create default-first-option placeholder="&#x73AF;&#x5883;" @change="handleFilterChange">
            <el-option v-for="item in environmentOptions" :key="item" :label="item" :value="item" />
          </el-select>
          <el-select v-model="filters.level" size="small" clearable placeholder="&#x7EA7;&#x522B;" @change="handleFilterChange">
            <el-option label="&#x4E25;&#x91CD;" value="critical" />
            <el-option label="&#x8B66;&#x544A;" value="warning" />
            <el-option label="&#x4FE1;&#x606F;" value="info" />
          </el-select>
          <el-input
            v-model="filters.search"
            size="small"
            clearable
            placeholder="&#x641C;&#x7D22;&#x6807;&#x9898; / &#x6765;&#x6E90; / &#x670D;&#x52A1; / &#x8D44;&#x6E90;"
            :prefix-icon="Search"
            @input="handleFilterChange"
          />
          <el-segmented v-model="eventMode" size="small" :options="eventModeOptions" @change="refreshEvents" />
          <el-button size="small" :icon="Refresh" :loading="loading" @click="refreshEvents">&#x5237;&#x65B0;</el-button>
          <div class="toolbar-spacer" />
          <el-button
            v-if="canManageAlerts && eventMode === 'list'"
            size="small"
            type="danger"
            :disabled="!selectedAlerts.length"
            @click="handleBatchDelete"
          >
            &#x6279;&#x91CF;&#x5220;&#x9664;
          </el-button>
        </div>

        <div v-if="eventMode === 'group'" class="group-toolbar">
          <span class="toolbar-label">&#x5206;&#x7EC4;&#x7EF4;&#x5EA6;</span>
          <el-select v-model="groupBy" size="small" multiple collapse-tags collapse-tags-tooltip @change="fetchGroups">
            <el-option v-for="item in dimensionOptions" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
        </div>

        <el-table v-if="eventMode === 'list'" :data="alerts" stripe size="small" v-loading="loading" class="data-table" @selection-change="handleSelectionChange">
          <el-table-column type="selection" width="42" />
          <el-table-column prop="id" label="告警ID" width="70">
            <template #default="{ row }">
              <span class="alert-id-cell">{{ row.id }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="title" label="&#x544A;&#x8B66;&#x6807;&#x9898;" min-width="240">
            <template #default="{ row }">
              <button class="link-title" type="button" @click="openDetail(row)">{{ row.title }}</button>
              <div class="sub-line">{{ row.service || row.resource || row.source }}</div>
            </template>
          </el-table-column>
          <el-table-column prop="level" label="&#x7EA7;&#x522B;" width="80">
            <template #default="{ row }">
              <el-tag :type="levelType(row.level)" size="small">{{ row.level_display || levelText(row.level) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="status" label="&#x72B6;&#x6001;" width="80">
            <template #default="{ row }">
              <el-tag :type="statusType(row.status)" size="small">{{ row.status_display || statusText(row.status) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="source_type" label="&#x63A5;&#x5165;" width="120">
            <template #default="{ row }">{{ providerText(row.source_type) }}</template>
          </el-table-column>
          <el-table-column prop="environment" label="&#x73AF;&#x5883;" width="100" />
          <el-table-column prop="claimed_by" label="&#x8BA4;&#x9886;&#x4EBA;" width="120">
            <template #default="{ row }">
              <div class="claimant-cell" v-if="row.claimants?.length">
                <el-tag v-for="item in row.claimants" :key="item.id" size="small" class="mini-tag claimant-tag">{{ item.claimant }}</el-tag>
              </div>
              <span v-else>-</span>
            </template>
          </el-table-column>
          <el-table-column prop="occurrence_count" label="&#x6B21;&#x6570;" width="60" />
          <el-table-column prop="last_received_at" label="&#x6700;&#x8FD1;&#x63A5;&#x6536;" width="180">
            <template #default="{ row }">{{ formatTime(row.last_received_at || row.created_at) }}</template>
          </el-table-column>
          <el-table-column label="&#x64CD;&#x4F5C;" width="145" fixed="right">
            <template #default="{ row }">
              <div class="row-actions">
                <el-button v-if="canManageAlerts && !row.current_user_claimed" link type="success" size="small" @click="runAlertAction(row, 'claim')">&#x8BA4;&#x9886;</el-button>
                <el-button v-if="canManageAlerts" link type="warning" size="small" @click="openMuteDialog(row)">&#x5C4F;&#x853D;</el-button>
                <el-button link size="small" type="primary" @click="openDetail(row)">&#x8BE6;&#x60C5;</el-button>
              </div>
            </template>
          </el-table-column>
        </el-table>

        <el-table v-else :data="groups" stripe size="small" v-loading="loading" class="data-table">
          <el-table-column label="&#x5206;&#x7EC4;" min-width="280">
            <template #default="{ row }">
              <div class="group-key">{{ row.key }}</div>
              <div class="sub-line">{{ row.sample_title }}</div>
            </template>
          </el-table-column>
          <el-table-column prop="total" label="&#x603B;&#x6570;" width="80" />
          <el-table-column prop="critical" label="&#x4E25;&#x91CD;" width="80" />
          <el-table-column prop="warning" label="&#x8B66;&#x544A;" width="80" />
          <el-table-column prop="unacknowledged" label="&#x672A;&#x8BA4;&#x9886;" width="90" />
          <el-table-column prop="suppressed" label="&#x6291;&#x5236;" width="100" />
          <el-table-column prop="latest_at" label="&#x6700;&#x65B0;&#x65F6;&#x95F4;" width="170">
            <template #default="{ row }">{{ formatTime(row.latest_at) }}</template>
          </el-table-column>
          <el-table-column label="&#x64CD;&#x4F5C;" width="120">
            <template #default="{ row }">
              <el-button link size="small" type="primary" @click="openGroup(row)">&#x67E5;&#x770B;&#x660E;&#x7EC6;</el-button>
            </template>
          </el-table-column>
        </el-table>

        <div class="pager" v-if="eventMode === 'list'">
          <el-pagination
            small
            v-model:current-page="page"
            :page-size="20"
            :total="total"
            layout="total, prev, pager, next"
            @current-change="refreshEvents"
          />
        </div>
      </section>
    </template>

    <template v-if="activeTab === 'notify' && canViewConfig">
      <section class="panel workbench-fill-panel">
        <div class="neo-sub-tabs theme-blue alert-sub-tabs">
          <button class="neo-sub-tab-btn" :class="{ active: notifyTab === 'rules' }" @click="changeNotifyTab('rules')">&#x901A;&#x77E5;&#x89C4;&#x5219;</button>
          <button class="neo-sub-tab-btn" :class="{ active: notifyTab === 'channels' }" @click="changeNotifyTab('channels')">&#x901A;&#x77E5;&#x6E20;&#x9053;</button>
          <button class="neo-sub-tab-btn" :class="{ active: notifyTab === 'recipients' }" @click="changeNotifyTab('recipients')">&#x63A5;&#x6536;&#x5BF9;&#x8C61;</button>
        </div>

        <div v-show="notifyTab === 'rules'">
          <div class="section-head">
            <h3>&#x901A;&#x77E5;&#x89C4;&#x5219;</h3>
            <el-button v-if="canManageConfig" size="small" type="primary" :icon="Plus" @click="openNotificationRule()">&#x65B0;&#x589E;&#x89C4;&#x5219;</el-button>
          </div>
          <el-table :data="notificationRules" stripe size="small" v-loading="configLoading">
            <el-table-column prop="name" label="&#x89C4;&#x5219;&#x540D;&#x79F0;" min-width="180" />
            <el-table-column prop="min_level" label="&#x6700;&#x4F4E;&#x7EA7;&#x522B;" width="110">
              <template #default="{ row }">{{ levelText(row.min_level) || '&#x5168;&#x90E8;' }}</template>
            </el-table-column>
            <el-table-column label="&#x6E20;&#x9053;" min-width="180">
              <template #default="{ row }">
                <el-tag v-for="item in row.channels" :key="item.id" size="small" class="mini-tag">{{ item.channel_type_display || channelText(item.channel_type) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="&#x63A5;&#x6536;&#x7EC4;" min-width="180">
              <template #default="{ row }">{{ (row.recipient_groups || []).map((item) => item.name).join(', ') || '-' }}</template>
            </el-table-column>
            <el-table-column label="&#x72B6;&#x6001;" width="90">
              <template #default="{ row }">
                <el-tag :type="row.is_enabled ? 'success' : 'info'" size="small">{{ row.is_enabled ? '&#x542F;&#x7528;' : '&#x505C;&#x7528;' }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="&#x64CD;&#x4F5C;" width="150" fixed="right">
              <template #default="{ row }">
                <el-button v-if="canManageConfig" link size="small" @click="openNotificationRule(row)">&#x7F16;&#x8F91;</el-button>
                <el-popconfirm v-if="canManageConfig" title="&#x5220;&#x9664;&#x8BE5;&#x89C4;&#x5219;&#xFF1F;" @confirm="removeNotificationRule(row.id)">
                  <template #reference><el-button link type="danger" size="small">&#x5220;&#x9664;</el-button></template>
                </el-popconfirm>
              </template>
            </el-table-column>
          </el-table>
        </div>

        <div v-show="notifyTab === 'channels'">
          <div class="section-head">
            <h3>&#x901A;&#x77E5;&#x6E20;&#x9053;</h3>
            <el-button v-if="canManageConfig" size="small" type="primary" :icon="Plus" @click="openChannel()">&#x65B0;&#x589E;&#x6E20;&#x9053;</el-button>
          </div>
          <el-table :data="channels" stripe size="small" v-loading="configLoading">
            <el-table-column prop="name" label="&#x6E20;&#x9053;&#x540D;&#x79F0;" min-width="180" />
            <el-table-column prop="channel_type" label="&#x7C7B;&#x578B;" width="100">
              <template #default="{ row }">{{ row.channel_type_display || channelText(row.channel_type) }}</template>
            </el-table-column>
            <el-table-column prop="send_resolved" label="&#x6062;&#x590D;&#x901A;&#x77E5;" width="100">
              <template #default="{ row }">{{ row.send_resolved ? '&#x53D1;&#x9001;' : '&#x4E0D;&#x53D1;&#x9001;' }}</template>
            </el-table-column>
            <el-table-column prop="updated_at" label="&#x66F4;&#x65B0;&#x65F6;&#x95F4;" width="170">
              <template #default="{ row }">{{ formatTime(row.updated_at) }}</template>
            </el-table-column>
            <el-table-column label="&#x72B6;&#x6001;" width="90">
              <template #default="{ row }">
                <el-tag :type="row.is_enabled ? 'success' : 'info'" size="small">{{ row.is_enabled ? '&#x542F;&#x7528;' : '&#x505C;&#x7528;' }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="&#x64CD;&#x4F5C;" width="190" fixed="right">
              <template #default="{ row }">
                <el-button v-if="canNotifyAlerts" link type="success" size="small" @click="testChannel(row)">&#x6D4B;&#x8BD5;</el-button>
                <el-button v-if="canManageConfig" link size="small" @click="openChannel(row)">&#x7F16;&#x8F91;</el-button>
                <el-popconfirm v-if="canManageConfig" title="&#x5220;&#x9664;&#x8BE5;&#x6E20;&#x9053;&#xFF1F;" @confirm="removeChannel(row.id)">
                  <template #reference><el-button link type="danger" size="small">&#x5220;&#x9664;</el-button></template>
                </el-popconfirm>
              </template>
            </el-table-column>
          </el-table>
        </div>

        <div v-show="notifyTab === 'recipients'">
          <div class="split-grid">
            <div class="split-panel">
              <div class="section-head">
                <h3>&#x63A5;&#x6536;&#x4EBA;</h3>
                <el-button v-if="canManageConfig" size="small" type="primary" :icon="Plus" @click="openRecipient()">&#x65B0;&#x589E;&#x63A5;&#x6536;&#x4EBA;</el-button>
              </div>
              <el-table :data="recipients" stripe size="small" v-loading="configLoading">
                <el-table-column prop="name" label="&#x59D3;&#x540D;" min-width="120" />
                <el-table-column prop="phone" label="&#x624B;&#x673A;" min-width="130" />
                <el-table-column prop="email" label="&#x90AE;&#x7BB1;" min-width="170" />
                <el-table-column label="&#x64CD;&#x4F5C;" width="120">
                  <template #default="{ row }">
                    <el-button v-if="canManageConfig" link size="small" @click="openRecipient(row)">&#x7F16;&#x8F91;</el-button>
                    <el-popconfirm v-if="canManageConfig" title="&#x5220;&#x9664;&#x8BE5;&#x63A5;&#x6536;&#x4EBA;&#xFF1F;" @confirm="removeRecipient(row.id)">
                      <template #reference><el-button link type="danger" size="small">&#x5220;&#x9664;</el-button></template>
                    </el-popconfirm>
                  </template>
                </el-table-column>
              </el-table>
            </div>

            <div class="split-panel">
              <div class="section-head">
                <h3>&#x63A5;&#x6536;&#x7EC4;</h3>
                <el-button v-if="canManageConfig" size="small" type="primary" :icon="Plus" @click="openRecipientGroup()">&#x65B0;&#x589E;&#x63A5;&#x6536;&#x7EC4;</el-button>
              </div>
              <el-table :data="recipientGroups" stripe size="small" v-loading="configLoading">
                <el-table-column prop="name" label="&#x7EC4;&#x540D;" min-width="130" />
                <el-table-column label="&#x6210;&#x5458;" min-width="220">
                  <template #default="{ row }">{{ groupMembers(row) }}</template>
                </el-table-column>
                <el-table-column label="&#x64CD;&#x4F5C;" width="120">
                  <template #default="{ row }">
                    <el-button v-if="canManageConfig" link size="small" @click="openRecipientGroup(row)">&#x7F16;&#x8F91;</el-button>
                    <el-popconfirm v-if="canManageConfig" title="&#x5220;&#x9664;&#x8BE5;&#x63A5;&#x6536;&#x7EC4;&#xFF1F;" @confirm="removeRecipientGroup(row.id)">
                      <template #reference><el-button link type="danger" size="small">&#x5220;&#x9664;</el-button></template>
                    </el-popconfirm>
                  </template>
                </el-table-column>
              </el-table>
            </div>
          </div>
        </div>
      </section>
    </template>

    <template v-if="activeTab === 'policies' && canViewConfig">
      <section class="panel workbench-fill-panel">
        <div class="neo-sub-tabs theme-blue alert-sub-tabs">
          <button class="neo-sub-tab-btn" :class="{ active: policyTab === 'aggregation' }" @click="changePolicyTab('aggregation')">&#x805A;&#x5408;</button>
          <button class="neo-sub-tab-btn" :class="{ active: policyTab === 'inhibition' }" @click="changePolicyTab('inhibition')">&#x6291;&#x5236;</button>
          <button class="neo-sub-tab-btn" :class="{ active: policyTab === 'mute' }" @click="changePolicyTab('mute')">&#x5C4F;&#x853D;</button>
          <button class="neo-sub-tab-btn" :class="{ active: policyTab === 'escalation' }" @click="changePolicyTab('escalation')">&#x5347;&#x7EA7;</button>
        </div>

        <div v-show="policyTab === 'aggregation'">
          <PolicyTable title="&#x805A;&#x5408;&#x89C4;&#x5219;" :data="aggregationRules" :loading="configLoading" :can-manage="canManageConfig" @create="openAggregationRule()" @edit="openAggregationRule" @remove="removeAggregationRule" />
        </div>
        <div v-show="policyTab === 'inhibition'">
          <PolicyTable title="&#x6291;&#x5236;&#x89C4;&#x5219;" :data="inhibitionRules" :loading="configLoading" :can-manage="canManageConfig" @create="openInhibitionRule()" @edit="openInhibitionRule" @remove="removeInhibitionRule" />
        </div>
        <div v-show="policyTab === 'mute'">
          <PolicyTable title="&#x5C4F;&#x853D;&#x89C4;&#x5219;" :data="muteRules" :loading="configLoading" :can-manage="canManageConfig" @create="openMuteRule()" @edit="openMuteRule" @remove="removeMuteRule" />
        </div>
        <div v-show="policyTab === 'escalation'">
          <PolicyTable title="&#x5347;&#x7EA7;&#x7B56;&#x7565;" :data="escalationPolicies" :loading="configLoading" :can-manage="canManageConfig" @create="openEscalationPolicy()" @edit="openEscalationPolicy" @remove="removeEscalationPolicy" />
        </div>
      </section>
    </template>

    <template v-if="activeTab === 'integrations' && canViewConfig">
      <section class="panel workbench-fill-panel">
        <div class="section-head">
          <h3>Webhook &#x63A5;&#x5165;&#x6E90;</h3>
          <div class="section-actions">
            <el-button size="small" @click="integrationHelpVisible = true">&#x63A5;&#x5165;&#x5E2E;&#x52A9;</el-button>
            <el-button v-if="canManageConfig" size="small" type="primary" :icon="Plus" @click="openIntegration()">&#x65B0;&#x589E;&#x63A5;&#x5165;&#x6E90;</el-button>
          </div>
        </div>
        <el-table :data="integrations" stripe size="small" v-loading="configLoading">
          <el-table-column prop="name" label="&#x540D;&#x79F0;" min-width="150" />
          <el-table-column prop="provider" label="&#x7C7B;&#x578B;" width="130">
            <template #default="{ row }">{{ providerText(row.provider) }}</template>
          </el-table-column>
          <el-table-column prop="webhook_url" label="Webhook &#x5730;&#x5740;" min-width="520">
            <template #default="{ row }">
              <div class="webhook-url-cell" :title="displayIntegrationWebhook(row.webhook_url).full">
                <div class="mono webhook-url-line webhook-url-host">{{ displayIntegrationWebhook(row.webhook_url).host }}</div>
                <div class="mono webhook-url-line webhook-url-path">{{ displayIntegrationWebhook(row.webhook_url).path }}</div>
              </div>
            </template>
          </el-table-column>
          <el-table-column prop="last_received_at" label="&#x6700;&#x8FD1;&#x63A5;&#x6536;" width="150">
            <template #default="{ row }">{{ formatTime(row.last_received_at) }}</template>
          </el-table-column>
          <el-table-column label="&#x72B6;&#x6001;" width="80">
            <template #default="{ row }">
              <el-tag :type="row.is_enabled ? 'success' : 'info'" size="small">{{ row.is_enabled ? '&#x542F;&#x7528;' : '&#x505C;&#x7528;' }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="&#x64CD;&#x4F5C;" width="120" fixed="right">
            <template #default="{ row }">
              <el-button v-if="canManageConfig" link size="small" @click="openIntegration(row)">&#x7F16;&#x8F91;</el-button>
              <el-popconfirm v-if="canManageConfig" title="&#x5220;&#x9664;&#x8BE5;&#x63A5;&#x5165;&#x6E90;&#xFF1F;" @confirm="removeIntegration(row.id)">
                <template #reference><el-button link type="danger" size="small">&#x5220;&#x9664;</el-button></template>
              </el-popconfirm>
            </template>
          </el-table-column>
        </el-table>
      </section>
    </template>

    <el-dialog v-model="integrationHelpVisible" title="Webhook 接入帮助" width="860px">
      <div class="integration-help">
        <section class="integration-help-hero">
          <div class="integration-help-hero-title">{{ integrationHelpIntro.title }}</div>
          <div class="integration-help-hero-desc">{{ integrationHelpIntro.desc }}</div>
        </section>
        <section class="integration-help-card">
          <div class="integration-help-title">平台统一字段</div>
          <div class="integration-help-grid">
            <div v-for="item in integrationCommonFields" :key="item.field" class="integration-help-item">
              <div class="integration-help-field">{{ item.field }}</div>
              <div class="integration-help-desc">{{ item.desc }}</div>
            </div>
          </div>
        </section>
        <section v-for="guide in integrationFieldGuides" :key="guide.provider" class="integration-help-card">
          <div class="integration-help-head">
            <div class="integration-help-title">{{ guide.title }}</div>
            <div class="integration-help-note">{{ guide.note }}</div>
          </div>
          <div class="integration-help-grid">
            <div v-for="item in guide.fields" :key="`${guide.provider}-${item.field}`" class="integration-help-item">
              <div class="integration-help-field">{{ item.field }}</div>
              <div class="integration-help-desc">{{ item.desc }}</div>
            </div>
          </div>
          <div class="integration-sample-block">
            <div class="integration-sample-title">最小可用示例</div>
            <pre class="integration-sample-code">{{ guide.sample }}</pre>
          </div>
        </section>
      </div>
      <template #footer>
        <el-button @click="integrationHelpVisible = false">关闭</el-button>
      </template>
    </el-dialog>

    <template v-if="activeTab === 'logs' && canViewAlerts">
      <section class="panel workbench-fill-panel">
        <div class="section-head">
          <h3>&#x901A;&#x77E5;&#x8BB0;&#x5F55;</h3>
          <el-button size="small" :icon="Refresh" @click="fetchNotificationLogs">&#x5237;&#x65B0;</el-button>
        </div>
        <el-table :data="notificationLogs" stripe size="small" v-loading="configLoading">
          <el-table-column prop="created_at" label="&#x65F6;&#x95F4;" width="170">
            <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
          </el-table-column>
          <el-table-column prop="action" label="&#x52A8;&#x4F5C;" width="90" />
          <el-table-column prop="channel_name" label="&#x6E20;&#x9053;" width="140" />
          <el-table-column prop="rule_name" label="&#x89C4;&#x5219;" min-width="150" />
          <el-table-column prop="recipient_summary" label="&#x63A5;&#x6536;&#x5BF9;&#x8C61;" min-width="180" />
          <el-table-column prop="status" label="&#x72B6;&#x6001;" width="90">
            <template #default="{ row }">
              <el-tag :type="notifyStatusType(row.status)" size="small">{{ row.status_display || row.status }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="error_message" label="&#x9519;&#x8BEF;&#x4FE1;&#x606F;" min-width="220" show-overflow-tooltip />
        </el-table>
      </section>
    </template>

    <el-drawer v-model="detailVisible" class="alert-detail-drawer" size="640px" title="&#x544A;&#x8B66;&#x8BE6;&#x60C5;">
      <template v-if="selectedAlert">
        <div class="alert-detail-body">
          <div class="detail-head">
            <div class="detail-badges">
              <el-tag :type="levelType(selectedAlert.level)">{{ selectedAlert.level_display || levelText(selectedAlert.level) }}</el-tag>
              <el-tag :type="statusType(selectedAlert.status)">{{ selectedAlert.status_display || statusText(selectedAlert.status) }}</el-tag>
              <span class="detail-alert-id">告警ID：{{ selectedAlert.id }}</span>
            </div>
            <span class="detail-title">{{ selectedAlert.title }}</span>
            <span class="detail-fingerprint">告警指纹：{{ selectedAlert.fingerprint || '-' }}</span>
          </div>
          <section class="alert-detail-card">
            <el-descriptions class="alert-detail-summary" :column="1" size="small" border>
              <el-descriptions-item label="&#x6765;&#x6E90;">{{ providerText(selectedAlert.source_type) }} / {{ selectedAlert.source }}</el-descriptions-item>
              <el-descriptions-item label="&#x8D44;&#x6E90;">{{ selectedAlert.resource || selectedAlert.host_name || '-' }}</el-descriptions-item>
              <el-descriptions-item label="&#x670D;&#x52A1;">{{ selectedAlert.service || '-' }}</el-descriptions-item>
              <el-descriptions-item label="&#x73AF;&#x5883;">{{ selectedAlert.environment || '-' }}</el-descriptions-item>
              <el-descriptions-item label="&#x8BA4;&#x9886;&#x4EBA;">
                <div class="claimant-cell" v-if="selectedAlert.claimants?.length">
                  <el-tag v-for="item in selectedAlert.claimants" :key="item.id" size="small" class="mini-tag claimant-tag">{{ item.claimant }}</el-tag>
                </div>
                <span v-else>-</span>
              </el-descriptions-item>
              <el-descriptions-item label="&#x805A;&#x5408;&#x952E;">{{ selectedAlert.group_key || '-' }}</el-descriptions-item>
              <el-descriptions-item label="&#x63CF;&#x8FF0;">{{ selectedAlert.message }}</el-descriptions-item>
            </el-descriptions>
          </section>
          <div v-if="canManageAlerts || canNotifyAlerts" class="detail-actions">
            <el-button v-if="!selectedAlert.current_user_claimed" size="small" type="success" @click="runAlertAction(selectedAlert, 'claim')">&#x8BA4;&#x9886;</el-button>
            <el-button v-if="selectedAlert.current_user_claimed" size="small" @click="runAlertAction(selectedAlert, 'unclaim')">&#x53D6;&#x6D88;&#x8BA4;&#x9886;</el-button>
            <el-button v-if="canManageAlerts" size="small" type="warning" @click="openMuteDialog(selectedAlert)">&#x5C4F;&#x853D;</el-button>
            <el-button v-if="canNotifyAlerts" size="small" type="primary" @click="runAlertAction(selectedAlert, 'notify')">&#x53D1;&#x9001;&#x901A;&#x77E5;</el-button>
            <el-button v-if="canManageAlerts" size="small" @click="runAlertAction(selectedAlert, 'close')">&#x5173;&#x95ED;&#x544A;&#x8B66;</el-button>
          </div>
          <section class="alert-detail-card">
            <div class="detail-section-title">
              <h4>&#x6807;&#x7B7E;</h4>
              <span>{{ Object.keys(selectedAlert.labels || {}).length }} 项</span>
            </div>
            <div class="kv-list">
              <el-tag v-for="(value, key) in selectedAlert.labels" :key="key" size="small">{{ key }}={{ value }}</el-tag>
              <span v-if="!Object.keys(selectedAlert.labels || {}).length" class="detail-empty">暂无标签</span>
            </div>
          </section>
          <section class="alert-detail-card">
            <div class="detail-section-title">
              <h4>&#x5904;&#x7406;&#x8BB0;&#x5F55;</h4>
              <span>{{ (selectedAlert.actions || []).length }} 条</span>
            </div>
            <el-timeline class="alert-detail-timeline">
              <el-timeline-item v-for="item in selectedAlert.actions || []" :key="item.id" :timestamp="formatTime(item.created_at)">
                {{ item.actor || '\u7CFB\u7EDF' }} / {{ item.action_display || item.action }} / {{ item.note || '-' }}
              </el-timeline-item>
            </el-timeline>
            <span v-if="!(selectedAlert.actions || []).length" class="detail-empty">暂无处理记录</span>
          </section>
        </div>
      </template>
    </el-drawer>

    <el-dialog top="5vh" :close-on-click-modal="false" append-to-body class="workbench-edit-dialog" v-model="integrationDialog.visible" title="&#x63A5;&#x5165;&#x6E90;" width="620px">
      <el-form class="workbench-editor-form--sectioned" label-position="top" :model="integrationDialog.form" label-width="120px">
        <section class="workbench-editor-section">
          <div class="workbench-editor-heading"><span class="workbench-editor-step">01</span><h3>接入信息</h3></div>
          <div class="workbench-editor-grid">
            <el-form-item label="&#x540D;&#x79F0;"><el-input v-model="integrationDialog.form.name" /></el-form-item>
            <el-form-item label="&#x7C7B;&#x578B;">
              <el-select v-model="integrationDialog.form.provider">
                <el-option v-for="item in providerOptions" :key="item.value" :label="item.label" :value="item.value" />
              </el-select>
            </el-form-item>
          </div>
        </section>
        <section class="workbench-editor-section workbench-editor-section--tinted">
          <div class="workbench-editor-heading"><span class="workbench-editor-step">02</span><h3>标签与状态</h3></div>
          <div>
            <el-form-item label="&#x9ED8;&#x8BA4;&#x6807;&#x7B7E;">
              <MatcherEditor v-model="integrationDialog.form.default_label_rows" mode="equals" />
            </el-form-item>
            <el-form-item label="&#x542F;&#x7528;"><el-switch v-model="integrationDialog.form.is_enabled" /></el-form-item>
            <el-form-item class="workbench-editor-full" label="&#x8BF4;&#x660E;"><el-input v-model="integrationDialog.form.description" type="textarea" :rows="2" /></el-form-item>
          </div>
        </section>
      </el-form>
      <template #footer>
        <el-button @click="integrationDialog.visible = false">&#x53D6;&#x6D88;</el-button>
        <el-button type="primary" @click="saveIntegration">&#x4FDD;&#x5B58;</el-button>
      </template>
    </el-dialog>

    <el-dialog top="5vh" :close-on-click-modal="false" append-to-body class="workbench-edit-dialog" v-model="channelDialog.visible" title="&#x901A;&#x77E5;&#x6E20;&#x9053;" width="700px">
      <el-form class="workbench-editor-form--sectioned" label-position="top" :model="channelDialog.form" label-width="130px">
        <section class="workbench-editor-section">
          <div class="workbench-editor-heading"><span class="workbench-editor-step">01</span><h3>渠道信息</h3></div>
          <div class="workbench-editor-grid">
            <el-form-item label="&#x540D;&#x79F0;"><el-input v-model="channelDialog.form.name" /></el-form-item>
            <el-form-item label="&#x7C7B;&#x578B;">
              <el-select v-model="channelDialog.form.channel_type">
                <el-option v-for="item in channelOptions" :key="item.value" :label="item.label" :value="item.value" />
              </el-select>
            </el-form-item>
          </div>
        </section>
        <section class="workbench-editor-section workbench-editor-section--tinted">
          <div class="workbench-editor-heading"><span class="workbench-editor-step">02</span><h3>通知接入</h3></div>
          <div>
            <el-form-item label="Webhook &#x5730;&#x5740;"><el-input v-model="channelDialog.form.webhook_url" /></el-form-item>
            <el-form-item label="&#x8BBF;&#x95EE;&#x4EE4;&#x724C;"><el-input v-model="channelDialog.form.access_token" show-password /></el-form-item>
            <el-form-item label="&#x9ED8;&#x8BA4;&#x63A5;&#x6536;&#x5730;&#x5740;"><el-input v-model="channelDialog.form.to" placeholder="&#x591A;&#x4E2A;&#x63A5;&#x6536;&#x5730;&#x5740;&#x6216;&#x624B;&#x673A;&#x53F7;&#xFF0C;&#x4F7F;&#x7528;&#x82F1;&#x6587;&#x9017;&#x53F7;&#x5206;&#x9694;" /></el-form-item>
          </div>
        </section>
        <section class="workbench-editor-section workbench-editor-section--tinted">
          <div class="workbench-editor-heading"><span class="workbench-editor-step">03</span><h3>消息模板与通知设置</h3></div>
          <div class="workbench-editor-grid">
            <el-form-item label="&#x6807;&#x9898;&#x6A21;&#x677F;"><el-input v-model="channelDialog.form.template_title" /></el-form-item>
            <el-form-item label="&#x5185;&#x5BB9;&#x6A21;&#x677F;"><el-input v-model="channelDialog.form.template_body" type="textarea" :rows="4" /></el-form-item>
            <el-form-item label="&#x6062;&#x590D;&#x901A;&#x77E5;"><el-switch v-model="channelDialog.form.send_resolved" /></el-form-item>
            <el-form-item label="&#x542F;&#x7528;"><el-switch v-model="channelDialog.form.is_enabled" /></el-form-item>
          </div>
        </section>
      </el-form>
      <template #footer>
        <el-button @click="channelDialog.visible = false">&#x53D6;&#x6D88;</el-button>
        <el-button type="primary" @click="saveChannel">&#x4FDD;&#x5B58;</el-button>
      </template>
    </el-dialog>

    <el-dialog top="5vh" :close-on-click-modal="false" append-to-body class="workbench-edit-dialog" v-model="recipientDialog.visible" title="&#x63A5;&#x6536;&#x4EBA;" width="620px">
      <el-form class="workbench-editor-form--sectioned" label-position="top" :model="recipientDialog.form" label-width="120px">
        <section class="workbench-editor-section">
          <div class="workbench-editor-heading"><span class="workbench-editor-step">01</span><h3>联系人信息</h3></div>
          <div class="workbench-editor-grid">
            <el-form-item label="&#x59D3;&#x540D;"><el-input v-model="recipientDialog.form.name" /></el-form-item>
            <el-form-item label="&#x624B;&#x673A;&#x53F7;"><el-input v-model="recipientDialog.form.phone" /></el-form-item>
            <el-form-item label="&#x90AE;&#x7BB1;"><el-input v-model="recipientDialog.form.email" /></el-form-item>
          </div>
        </section>
        <section class="workbench-editor-section workbench-editor-section--tinted">
          <div class="workbench-editor-heading"><span class="workbench-editor-step">02</span><h3>平台账号与状态</h3></div>
          <div class="workbench-editor-grid">
            <el-form-item label="&#x9489;&#x9489; ID"><el-input v-model="recipientDialog.form.dingtalk_user_id" /></el-form-item>
            <el-form-item label="&#x98DE;&#x4E66; ID"><el-input v-model="recipientDialog.form.feishu_user_id" /></el-form-item>
            <el-form-item label="&#x4F01;&#x5FAE; ID"><el-input v-model="recipientDialog.form.wecom_user_id" /></el-form-item>
            <el-form-item label="&#x542F;&#x7528;"><el-switch v-model="recipientDialog.form.is_enabled" /></el-form-item>
          </div>
        </section>
      </el-form>
      <template #footer>
        <el-button @click="recipientDialog.visible = false">&#x53D6;&#x6D88;</el-button>
        <el-button type="primary" @click="saveRecipient">&#x4FDD;&#x5B58;</el-button>
      </template>
    </el-dialog>

    <el-dialog top="5vh" :close-on-click-modal="false" append-to-body class="workbench-edit-dialog" v-model="recipientGroupDialog.visible" title="&#x63A5;&#x6536;&#x7EC4;" width="620px">
      <el-form class="workbench-editor-form--sectioned" label-position="top" :model="recipientGroupDialog.form" label-width="120px">
        <section class="workbench-editor-section">
          <div class="workbench-editor-heading"><span class="workbench-editor-step">01</span><h3>接收组信息</h3></div>
          <div>
            <el-form-item label="&#x7EC4;&#x540D;"><el-input v-model="recipientGroupDialog.form.name" /></el-form-item>
          </div>
        </section>
        <section class="workbench-editor-section workbench-editor-section--tinted">
          <div class="workbench-editor-heading"><span class="workbench-editor-step">02</span><h3>接收对象与状态</h3></div>
          <div>
            <el-form-item label="&#x63A5;&#x6536;&#x4EBA;">
              <el-select v-model="recipientGroupDialog.form.recipient_ids" multiple filterable>
                <el-option v-for="item in recipients" :key="item.id" :label="item.name" :value="item.id" />
              </el-select>
            </el-form-item>
            <el-form-item label="&#x5E73;&#x53F0;&#x7528;&#x6237;">
              <el-select v-model="recipientGroupDialog.form.user_ids" multiple filterable>
                <el-option v-for="item in users" :key="item.id" :label="item.display_name || item.username" :value="item.id" />
              </el-select>
            </el-form-item>
            <el-form-item label="&#x542F;&#x7528;"><el-switch v-model="recipientGroupDialog.form.is_enabled" /></el-form-item>
            <el-form-item class="workbench-editor-full" label="&#x8BF4;&#x660E;"><el-input v-model="recipientGroupDialog.form.description" type="textarea" :rows="2" /></el-form-item>
          </div>
        </section>
      </el-form>
      <template #footer>
        <el-button @click="recipientGroupDialog.visible = false">&#x53D6;&#x6D88;</el-button>
        <el-button type="primary" @click="saveRecipientGroup">&#x4FDD;&#x5B58;</el-button>
      </template>
    </el-dialog>

    <el-dialog top="5vh" :close-on-click-modal="false" append-to-body class="workbench-edit-dialog" v-model="notificationRuleDialog.visible" title="&#x901A;&#x77E5;&#x89C4;&#x5219;" width="760px">
      <el-form class="workbench-editor-form--sectioned" label-position="top" :model="notificationRuleDialog.form" label-width="130px">
        <section class="workbench-editor-section">
          <div class="workbench-editor-heading"><span class="workbench-editor-step">01</span><h3>匹配范围</h3></div>
          <div>
            <el-form-item label="&#x540D;&#x79F0;"><el-input v-model="notificationRuleDialog.form.name" /></el-form-item>
            <el-form-item label="&#x5339;&#x914D;&#x6761;&#x4EF6;"><MatcherEditor v-model="notificationRuleDialog.form.matchers" /></el-form-item>
            <el-form-item label="&#x6700;&#x4F4E;&#x7EA7;&#x522B;">
              <el-select v-model="notificationRuleDialog.form.min_level" clearable>
                <el-option label="&#x4E25;&#x91CD;" value="critical" />
                <el-option label="&#x8B66;&#x544A;" value="warning" />
                <el-option label="&#x4FE1;&#x606F;" value="info" />
              </el-select>
            </el-form-item>
          </div>
        </section>
        <section class="workbench-editor-section workbench-editor-section--tinted">
          <div class="workbench-editor-heading"><span class="workbench-editor-step">02</span><h3>通知对象</h3></div>
          <div>
            <el-form-item label="&#x901A;&#x77E5;&#x6E20;&#x9053;">
              <el-select v-model="notificationRuleDialog.form.channel_ids" multiple>
                <el-option v-for="item in channels" :key="item.id" :label="`${item.name} / ${channelText(item.channel_type)}`" :value="item.id" />
              </el-select>
            </el-form-item>
            <el-form-item label="&#x63A5;&#x6536;&#x7EC4;">
              <el-select v-model="notificationRuleDialog.form.recipient_group_ids" multiple>
                <el-option v-for="item in recipientGroups" :key="item.id" :label="item.name" :value="item.id" />
              </el-select>
            </el-form-item>
            <el-form-item label="&#x63A5;&#x6536;&#x4EBA;">
              <el-select v-model="notificationRuleDialog.form.recipient_ids" multiple>
                <el-option v-for="item in recipients" :key="item.id" :label="item.name" :value="item.id" />
              </el-select>
            </el-form-item>
          </div>
        </section>
        <section class="workbench-editor-section workbench-editor-section--tinted">
          <div class="workbench-editor-heading"><span class="workbench-editor-step">03</span><h3>聚合与通知策略</h3></div>
          <div class="workbench-editor-grid">
            <el-form-item label="&#x805A;&#x5408;&#x89C4;&#x5219;">
              <el-select v-model="notificationRuleDialog.form.aggregation_rule" clearable>
                <el-option v-for="item in aggregationRules" :key="item.id" :label="item.name" :value="item.id" />
              </el-select>
            </el-form-item>
            <el-form-item label="&#x5347;&#x7EA7;&#x7B56;&#x7565;">
              <el-select v-model="notificationRuleDialog.form.escalation_policy" clearable>
                <el-option v-for="item in escalationPolicies" :key="item.id" :label="item.name" :value="item.id" />
              </el-select>
            </el-form-item>
            <el-form-item label="&#x901A;&#x77E5;&#x65F6;&#x673A;">
              <el-checkbox v-model="notificationRuleDialog.form.notify_on_fire">&#x89E6;&#x53D1;</el-checkbox>
              <el-checkbox v-model="notificationRuleDialog.form.notify_on_resolved">&#x6062;&#x590D;</el-checkbox>
              <el-checkbox v-model="notificationRuleDialog.form.notify_on_escalation">&#x5347;&#x7EA7;</el-checkbox>
            </el-form-item>
            <el-form-item label="&#x542F;&#x7528;"><el-switch v-model="notificationRuleDialog.form.is_enabled" /></el-form-item>
            <el-form-item class="workbench-editor-full" label="&#x8BF4;&#x660E;"><el-input v-model="notificationRuleDialog.form.description" type="textarea" :rows="2" /></el-form-item>
          </div>
        </section>
      </el-form>
      <template #footer>
        <el-button @click="notificationRuleDialog.visible = false">&#x53D6;&#x6D88;</el-button>
        <el-button type="primary" @click="saveNotificationRule">&#x4FDD;&#x5B58;</el-button>
      </template>
    </el-dialog>

    <el-dialog top="5vh" :close-on-click-modal="false" append-to-body class="workbench-edit-dialog" v-model="policyDialog.visible" :title="policyDialog.title" width="760px">
      <el-form class="workbench-editor-form--sectioned" label-position="top" :model="policyDialog.form" label-width="130px">
        <section class="workbench-editor-section">
          <div class="workbench-editor-heading"><span class="workbench-editor-step">01</span><h3>策略信息</h3></div>
          <div>
            <el-form-item label="&#x540D;&#x79F0;"><el-input v-model="policyDialog.form.name" /></el-form-item>
            <el-form-item v-if="policyDialog.kind !== 'inhibition'" label="&#x5339;&#x914D;&#x6761;&#x4EF6;"><MatcherEditor v-model="policyDialog.form.matchers" /></el-form-item>
          </div>
        </section>

        <section class="workbench-editor-section workbench-editor-section--tinted">
          <div class="workbench-editor-heading"><span class="workbench-editor-step">02</span><h3>规则与状态</h3></div>
          <div>
            <template v-if="policyDialog.kind === 'aggregation'">
              <el-form-item label="&#x5206;&#x7EC4;&#x7EF4;&#x5EA6;">
                <el-select v-model="policyDialog.form.group_by" multiple>
                  <el-option v-for="item in dimensionOptions" :key="item.value" :label="item.label" :value="item.value" />
                </el-select>
              </el-form-item>
              <el-form-item label="&#x805A;&#x5408;&#x7A97;&#x53E3;"><el-input-number v-model="policyDialog.form.window_minutes" :min="1" /> &#x5206;&#x949F;</el-form-item>
              <el-form-item label="&#x91CD;&#x590D;&#x95F4;&#x9694;"><el-input-number v-model="policyDialog.form.repeat_interval_minutes" :min="1" /> &#x5206;&#x949F;</el-form-item>
            </template>

            <template v-if="policyDialog.kind === 'inhibition'">
              <el-form-item label="&#x6765;&#x6E90;&#x5339;&#x914D;"><MatcherEditor v-model="policyDialog.form.source_matchers" /></el-form-item>
              <el-form-item label="&#x76EE;&#x6807;&#x5339;&#x914D;"><MatcherEditor v-model="policyDialog.form.target_matchers" /></el-form-item>
              <el-form-item label="&#x76F8;&#x7B49;&#x6807;&#x7B7E;">
                <el-select v-model="policyDialog.form.equal_labels" multiple allow-create filterable>
                  <el-option v-for="item in dimensionOptions" :key="item.value" :label="item.label" :value="item.value" />
                </el-select>
              </el-form-item>
              <el-form-item label="&#x6301;&#x7EED;&#x65F6;&#x95F4;"><el-input-number v-model="policyDialog.form.duration_minutes" :min="1" /> &#x5206;&#x949F;</el-form-item>
            </template>

            <template v-if="policyDialog.kind === 'mute'">
              <el-form-item label="&#x65F6;&#x95F4;&#x8303;&#x56F4;">
                <el-date-picker
              v-model="policyDialog.form.range"
              type="datetimerange"
              value-format="YYYY-MM-DDTHH:mm:ssZ"
              start-placeholder="&#x5F00;&#x59CB;&#x65F6;&#x95F4;"
              end-placeholder="&#x7ED3;&#x675F;&#x65F6;&#x95F4;"
            />
              </el-form-item>
              <el-form-item class="workbench-editor-full" label="&#x539F;&#x56E0;"><el-input v-model="policyDialog.form.reason" /></el-form-item>
            </template>

            <template v-if="policyDialog.kind === 'escalation'">
              <el-form-item label="&#x91CD;&#x590D;&#x95F4;&#x9694;"><el-input-number v-model="policyDialog.form.repeat_interval_minutes" :min="1" /> &#x5206;&#x949F;</el-form-item>
              <el-form-item label="&#x5347;&#x7EA7;&#x5C42;&#x7EA7;">
                <div class="level-editor">
                  <div v-for="(item, index) in policyDialog.form.levels" :key="index" class="level-row">
                    <el-input-number v-model="item.after_minutes" :min="0" size="small" />
                    <el-input v-model="item.name" size="small" placeholder="&#x5C42;&#x7EA7;&#x540D;&#x79F0;" />
                    <el-select v-model="item.channel_ids" multiple size="small" placeholder="&#x901A;&#x77E5;&#x6E20;&#x9053;">
                      <el-option v-for="channel in channels" :key="channel.id" :label="channel.name" :value="channel.id" />
                    </el-select>
                    <el-button link type="danger" :icon="Delete" @click="policyDialog.form.levels.splice(index, 1)" />
                  </div>
                  <el-button size="small" :icon="Plus" @click="policyDialog.form.levels.push({ name: '', after_minutes: 30, channel_ids: [] })">&#x65B0;&#x589E;&#x5C42;&#x7EA7;</el-button>
                </div>
              </el-form-item>
            </template>

            <el-form-item label="&#x542F;&#x7528;"><el-switch v-model="policyDialog.form.is_enabled" /></el-form-item>
            <el-form-item class="workbench-editor-full" label="&#x8BF4;&#x660E;"><el-input v-model="policyDialog.form.description" type="textarea" :rows="2" /></el-form-item>
          </div>
        </section>
      </el-form>
      <template #footer>
        <el-button @click="policyDialog.visible = false">&#x53D6;&#x6D88;</el-button>
        <el-button type="primary" @click="savePolicy">&#x4FDD;&#x5B58;</el-button>
      </template>
    </el-dialog>

    <el-dialog top="5vh" :close-on-click-modal="false" append-to-body class="workbench-edit-dialog" v-model="muteDialog.visible" title="&#x5C4F;&#x853D;&#x544A;&#x8B66;" width="420px">
      <el-form label-position="top" :model="muteDialog.form" label-width="96px">
        <el-form-item label="&#x5C4F;&#x853D;&#x65F6;&#x957F;">
          <el-input-number v-model="muteDialog.form.minutes" :min="1" :max="10080" />
          <span class="field-suffix">&#x5206;&#x949F;</span>
        </el-form-item>
        <el-form-item label="&#x5FEB;&#x6377;&#x9009;&#x62E9;">
          <div class="mute-presets">
            <el-button size="small" @click="muteDialog.form.minutes = 30">30m</el-button>
            <el-button size="small" @click="muteDialog.form.minutes = 60">1h</el-button>
            <el-button size="small" @click="muteDialog.form.minutes = 180">3h</el-button>
            <el-button size="small" @click="muteDialog.form.minutes = 1440">1d</el-button>
            <el-button size="small" @click="muteDialog.form.minutes = 10080">7d</el-button>
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="muteDialog.visible = false">&#x53D6;&#x6D88;</el-button>
        <el-button type="primary" @click="submitMuteDialog">&#x786E;&#x8BA4;&#x5C4F;&#x853D;</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, defineComponent, h, onMounted, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { Bell, Connection, Delete, Document, Operation, Plus, Refresh, Search, Setting } from '@element-plus/icons-vue'
import { ElButton, ElInput, ElMessage, ElMessageBox, ElOption, ElPopconfirm, ElSelect, ElTable, ElTableColumn, ElTag } from 'element-plus'
import {
  claimAlert,
  closeAlert,
  createAlertAggregationRule,
  createAlertEscalationPolicy,
  createAlertInhibitionRule,
  createAlertIntegration,
  createAlertMuteRule,
  createAlertNotificationChannel,
  createAlertNotificationRule,
  createAlertRecipient,
  createAlertRecipientGroup,
  deleteAlert,
  deleteAlertAggregationRule,
  deleteAlertEscalationPolicy,
  deleteAlertInhibitionRule,
  deleteAlertIntegration,
  deleteAlertMuteRule,
  deleteAlertNotificationChannel,
  deleteAlertNotificationRule,
  deleteAlertRecipient,
  deleteAlertRecipientGroup,
  escalateAlert,
  getAlertAggregationRules,
  getAlertEscalationPolicies,
  getAlertGroups,
  getAlertInhibitionRules,
  getAlertIntegrations,
  getAlertMuteRules,
  getAlertNotificationChannels,
  getAlertNotificationLogs,
  getAlertNotificationRules,
  getAlertRecipientGroups,
  getAlertRecipients,
  getAlerts,
  getAlertSummary,
  getUsers,
  muteAlert,
  notifyAlert,
  reopenAlert,
  testAlertNotificationChannel,
  unclaimAlert,
  updateAlertAggregationRule,
  updateAlertEscalationPolicy,
  updateAlertInhibitionRule,
  updateAlertIntegration,
  updateAlertMuteRule,
  updateAlertNotificationChannel,
  updateAlertNotificationRule,
  updateAlertRecipient,
  updateAlertRecipientGroup,
} from '@/api/modules/ops'
import { useAuthStore } from '@/stores/auth'

function clone(value) {
  return JSON.parse(JSON.stringify(value || []))
}

function listOf(response) {
  return Array.isArray(response) ? response : (response?.results || [])
}

function splitText(value) {
  return String(value || '').split(',').map((item) => item.trim()).filter(Boolean)
}

function matchersToObject(rows) {
  const data = {}
  for (const row of rows || []) {
    if (row.key) data[row.key] = row.value
  }
  return data
}

function matcherRowsFromObject(obj) {
  return Object.entries(obj || {}).map(([key, value]) => ({ key, op: '==', value }))
}

const MatcherEditor = defineComponent({
  name: 'MatcherEditor',
  props: {
    modelValue: { type: Array, default: () => [] },
    mode: { type: String, default: 'matcher' },
  },
  emits: ['update:modelValue'],
  setup(props, { emit }) {
    const ops = ['==', '!=', '=~', '!~', 'in', 'not in', 'contains']
    function update(index, key, value) {
      const rows = clone(props.modelValue)
      rows[index] = { ...rows[index], [key]: value }
      emit('update:modelValue', rows)
    }
    function remove(index) {
      const rows = clone(props.modelValue)
      rows.splice(index, 1)
      emit('update:modelValue', rows)
    }
    function add() {
      emit('update:modelValue', [...props.modelValue, { key: '', op: '==', value: '' }])
    }
    return () => h('div', { class: 'matcher-editor' }, [
      ...props.modelValue.map((row, index) => h('div', { class: 'matcher-row', key: index }, [
        h(ElInput, { modelValue: row.key, size: 'small', placeholder: '\u5B57\u6BB5\u6216\u6807\u7B7E', onInput: (value) => update(index, 'key', value) }),
        props.mode === 'equals'
          ? null
          : h(ElSelect, { modelValue: row.op || '==', size: 'small', onChange: (value) => update(index, 'op', value) }, () => ops.map((op) => h(ElOption, { key: op, label: op, value: op }))),
        h(ElInput, { modelValue: row.value, size: 'small', placeholder: '\u5339\u914D\u503C', onInput: (value) => update(index, 'value', value) }),
        h(ElButton, { link: true, type: 'danger', icon: Delete, onClick: () => remove(index) }),
      ])),
      h(ElButton, { size: 'small', icon: Plus, onClick: add }, () => '\u65B0\u589E\u5339\u914D'),
    ])
  },
})

const PolicyTable = defineComponent({
  name: 'PolicyTable',
  props: {
    title: { type: String, required: true },
    data: { type: Array, default: () => [] },
    loading: { type: Boolean, default: false },
    canManage: { type: Boolean, default: false },
  },
  emits: ['create', 'edit', 'remove'],
  setup(props, { emit }) {
    return () => h('div', [
      h('div', {
        class: 'section-head',
        style: {
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: '8px',
          marginBottom: '8px',
          minHeight: '30px',
          width: '100%',
          flexWrap: 'nowrap',
        },
      }, [
        h('h3', {
          style: {
            margin: '0',
            fontSize: '15px',
            fontWeight: '700',
            lineHeight: '1.3',
            flex: '0 1 auto',
          },
        }, props.title),
        props.canManage ? h(ElButton, {
          size: 'small',
          type: 'primary',
          icon: Plus,
          onClick: () => emit('create'),
          style: {
            marginLeft: 'auto',
            flex: '0 0 auto',
          },
        }, () => '\u65B0\u589E\u7B56\u7565') : null,
      ]),
      h(ElTable, { data: props.data, stripe: true, size: 'small', loading: props.loading }, () => [
        h(ElTableColumn, { prop: 'name', label: '\u540D\u79F0', minWidth: 180 }),
        h(ElTableColumn, { prop: 'description', label: '\u8BF4\u660E', minWidth: 220, showOverflowTooltip: true }),
        h(ElTableColumn, { label: '\u72B6\u6001', width: 90 }, {
          default: ({ row }) => h(ElTag, { type: row.is_enabled ? 'success' : 'info', size: 'small' }, () => (row.is_enabled ? '\u542F\u7528' : '\u505C\u7528')),
        }),
        h(ElTableColumn, { prop: 'updated_at', label: '\u66F4\u65B0\u65F6\u95F4', width: 170 }, {
          default: ({ row }) => formatTime(row.updated_at),
        }),
        h(ElTableColumn, { label: '\u64CD\u4F5C', width: 140, fixed: 'right' }, {
          default: ({ row }) => h('div', { class: 'row-actions' }, [
            props.canManage ? h(ElButton, { link: true, size: 'small', onClick: () => emit('edit', row) }, () => '\u7F16\u8F91') : null,
            props.canManage ? h(ElPopconfirm, { title: '\u786E\u8BA4\u5220\u9664\u8BE5\u7B56\u7565\uFF1F', onConfirm: () => emit('remove', row.id) }, {
              reference: () => h(ElButton, { link: true, type: 'danger', size: 'small' }, () => '\u5220\u9664'),
            }) : null,
          ]),
        }),
      ]),
    ])
  },
})

const route = useRoute()
const authStore = useAuthStore()

const activeTab = ref('events')
const notifyTab = ref('rules')
const policyTab = ref('aggregation')
const eventMode = ref('list')
const eventModeOptions = [
  { label: '\u5217\u8868', value: 'list' },
  { label: '\u5206\u7EC4', value: 'group' },
]

const providerOptions = [
  { label: 'Alertmanager', value: 'prometheus' },
  { label: 'Zabbix', value: 'zabbix' },
  { label: 'Nightingale', value: 'nightingale' },
  { label: '\u963F\u91CC\u4E91\u76D1\u63A7', value: 'aliyun' },
  { label: '\u901A\u7528 Webhook', value: 'generic' },
]

const channelOptions = [
  { label: '\u77ED\u4FE1', value: 'sms' },
  { label: '\u8BED\u97F3', value: 'voice' },
  { label: '\u90AE\u4EF6', value: 'email' },
  { label: '\u9489\u9489', value: 'dingtalk' },
  { label: '\u98DE\u4E66', value: 'feishu' },
  { label: '\u4F01\u5FAE', value: 'wecom' },
]

const dimensionOptions = [
  { label: '\u6765\u6E90\u7C7B\u578B', value: 'source_type' },
  { label: '\u73AF\u5883', value: 'environment' },
  { label: '\u670D\u52A1', value: 'service' },
  { label: '\u96C6\u7FA4', value: 'cluster' },
  { label: '\u547D\u540D\u7A7A\u95F4', value: 'namespace' },
  { label: '业务线', value: 'business_line' },
  { label: '\u8D44\u6E90\u7C7B\u578B', value: 'resource_type' },
  { label: '\u8D44\u6E90', value: 'resource' },
  { label: '\u7EA7\u522B', value: 'level' },
  { label: '\u5730\u57DF', value: 'region' },
  { label: '\u6807\u7B7E alertname', value: 'label.alertname' },
  { label: '\u6807\u7B7E team', value: 'label.team' },
]

const filters = reactive({
  search: '',
  level: '',
  status: '',
  claimed: '',
  source_type: '',
  environment: '',
})

const loading = ref(false)
const configLoading = ref(false)
const alerts = ref([])
const selectedAlerts = ref([])
const groups = ref([])
const summary = ref({})
const total = ref(0)
const page = ref(1)
const groupBy = ref(['source_type', 'environment', 'service'])
const integrations = ref([])
const channels = ref([])
const recipients = ref([])
const recipientGroups = ref([])
const users = ref([])
const notificationRules = ref([])
const aggregationRules = ref([])
const inhibitionRules = ref([])
const muteRules = ref([])
const escalationPolicies = ref([])
const notificationLogs = ref([])
const selectedAlert = ref(null)
const detailVisible = ref(false)
const integrationHelpVisible = ref(false)

const canViewAlerts = computed(() => authStore.hasPermission('ops.alert.view'))
const canManageAlerts = computed(() => authStore.hasPermission('ops.alert.manage'))
const canNotifyAlerts = computed(() => authStore.hasPermission('ops.alert.notify'))
const canViewConfig = computed(() => authStore.hasPermission('ops.alert.config.view'))
const canManageConfig = computed(() => authStore.hasPermission('ops.alert.config.manage'))

const statCards = computed(() => [
  { key: 'all', label: '\u5168\u90E8\u544A\u8B66', value: summary.value.total || 0, tone: 'base-card', filter: { status: '', level: '', claimed: '' } },
  { key: 'active', label: '\u6D3B\u8DC3\u544A\u8B66', value: summary.value.active || 0, tone: 'info-card', filter: { status: 'active', level: '', claimed: '' } },
  { key: 'critical', label: '\u4E25\u91CD\u544A\u8B66', value: summary.value.critical || 0, tone: 'danger-card', filter: { status: '', level: 'critical', claimed: '' } },
  { key: 'muted', label: '\u5DF2\u5C4F\u853D\u544A\u8B66', value: summary.value.muted || 0, tone: 'warning-card', filter: { status: 'muted', level: '', claimed: '' } },
])

const activeStatKey = computed(() => {
  const current = {
    status: filters.status || '',
    level: filters.level || '',
    claimed: filters.claimed || '',
  }
  return statCards.value.find((card) => (
    card.filter.status === current.status
    && card.filter.level === current.level
    && card.filter.claimed === current.claimed
  ))?.key || ''
})

const integrationHelpIntro = {
  title: '说明平台如何从各类 webhook payload 中提取告警字段',
  desc: '下面按接入源分别说明标题、描述、服务、环境、资源、指纹、聚合键等字段的取值优先级，并附上最小可用示例，便于对照你自己的 webhook payload 调整。',
}

const integrationCommonFields = [
  { field: '标题', desc: '告警列表标题和详情标题。不同来源会按各自优先级取规则名、summary、告警名等字段。' },
  { field: '描述', desc: '对应详情里的“描述”字段。平台会优先取各来源的 description / message / 正文字段，取不到时回退到标题。' },
  { field: '级别', desc: '统一归一成 critical / warning / info。通常来自 severity、level、priority、warnLevel 等字段。' },
  { field: '状态', desc: '统一归一成 active / resolved / muted / closed。Webhook 接入时通常只负责 active / resolved。' },
  { field: '服务', desc: '用于聚合和检索。通常优先取 labels.app，其次 job_name、service 或来源自己的业务字段。' },
  { field: '环境', desc: '通常来自 env / environment；也支持在接入源里配置默认标签补齐。' },
  { field: '资源', desc: '用于定位具体实例。常见取值包括 instance、pod、host、target_ident、instanceId。' },
  { field: '告警指纹', desc: '事件去重键。优先使用来源自带 fingerprint/hash/triggerid 等；没有时平台按稳定字段计算。' },
  { field: '聚合键', desc: '用于分组展示和通知聚合。Prometheus 优先取 Alertmanager 的 groupKey，其他来源优先取各自分组字段。' },
]

const integrationFieldGuides = [
  {
    provider: 'prometheus',
    title: 'Alertmanager / Prometheus',
    note: '适合直接接 Alertmanager webhook。',
    fields: [
      { field: '标题', desc: '优先 annotations.summary，其次 labels.alertname，再回退到 title。' },
      { field: '描述', desc: '优先 annotations.description，其次 annotations.message，再其次 item.message；都没有时回退标题。' },
      { field: '来源', desc: '优先 labels.job，其次 labels.alertname，默认显示 Alertmanager。' },
      { field: '服务', desc: '优先 labels.app，其次 labels.job_name，再其次 labels.service，最后回退 labels.job。' },
      { field: '环境', desc: '优先 labels.env，其次 labels.environment。' },
      { field: '资源', desc: '优先 labels.instance，其次 pod、node、host、job。' },
      { field: '告警指纹', desc: '使用 alerts[].fingerprint；平台会再基于 provider 做一次哈希后落库。' },
      { field: '聚合键', desc: '优先使用 webhook 顶层 groupKey；没有时才按平台聚合规则生成。' },
    ],
    sample: `{
  "status": "firing",
  "groupKey": "{alertname=\\"HighErrorRate\\",service=\\"order-api\\"}",
  "alerts": [
    {
      "status": "firing",
      "fingerprint": "2f8aa6b2d2a4",
      "labels": {
        "alertname": "HighErrorRate",
        "severity": "critical",
        "app": "order-api",
        "env": "prod",
        "instance": "10.0.1.10:8080"
      },
      "annotations": {
        "summary": "订单服务错误率升高",
        "description": "5xx 比例超过阈值"
      },
      "startsAt": "2026-05-17T12:30:00+08:00"
    }
  ]
}`,
  },
  {
    provider: 'nightingale',
    title: '夜莺',
    note: '兼容 events / alerts / data 多种结构。',
    fields: [
      { field: '标题', desc: '优先 rule_name，其次 title，再其次 annotations.summary。' },
      { field: '描述', desc: '优先 rule_note，其次 trigger_value，再其次 annotations.description；都没有时回退标题。' },
      { field: '来源', desc: '优先 cluster，其次 datasource_name、cate。' },
      { field: '服务', desc: '优先 tags 里的 app / job_name / service，最后回退 rule_prod。' },
      { field: '资源', desc: '优先 target_ident，其次 target、ident、instance、host。' },
      { field: '告警指纹', desc: '优先 hash。' },
      { field: '聚合键', desc: '优先 group_name，其次 group_id。' },
    ],
    sample: `{
  "events": [
    {
      "rule_name": "CPU 使用率过高",
      "rule_note": "持续 5 分钟超过 90%",
      "severity": "2",
      "status": "firing",
      "hash": "9ec7b8d1",
      "group_name": "order-api-prod",
      "target_ident": "10.0.1.10",
      "cluster": "prod-cluster",
      "tags_map": {
        "app": "order-api",
        "env": "prod",
        "instance": "10.0.1.10"
      },
      "trigger_time": 1778992200
    }
  ]
}`,
  },
  {
    provider: 'zabbix',
    title: 'Zabbix',
    note: '兼容常见自定义 webhook payload。',
    fields: [
      { field: '标题', desc: '优先 trigger_name，其次 event_name、subject、name。' },
      { field: '描述', desc: '优先 message，其次 body，再其次 trigger_description；都没有时回退标题。' },
      { field: '来源', desc: '优先 source，默认显示 Zabbix。' },
      { field: '服务', desc: '优先 tags 里的 app / job_name / service，最后回退 application。' },
      { field: '资源', desc: '优先 host / hostname / host_name；如果有 hosts 数组，会回退取第一个 host。' },
      { field: '告警指纹', desc: '优先 triggerid，其次 trigger_id，再其次 eventid。' },
      { field: '聚合键', desc: '优先 hostgroup，其次 host_group，再其次 tags.group。' },
    ],
    sample: `{
  "alerts": [
    {
      "trigger_name": "磁盘使用率过高",
      "message": "/data 使用率超过 85%",
      "severity": "high",
      "status": "PROBLEM",
      "source": "Zabbix",
      "triggerid": "28731",
      "host": "db-prod-01",
      "hostgroup": "database-prod",
      "tags": "app=order-db,env=prod,cluster=prod-cluster",
      "event_time": 1778992200
    }
  ]
}`,
  },
  {
    provider: 'aliyun',
    title: '阿里云监控',
    note: '适合接云监控告警 webhook。',
    fields: [
      { field: '标题', desc: '优先 alertName，其次 ruleName、name。' },
      { field: '描述', desc: '优先 message，其次 content，再其次 curValue；都没有时回退标题。' },
      { field: '来源', desc: '优先 namespace，其次 product，默认显示 Aliyun CloudMonitor。' },
      { field: '服务', desc: '优先 dimensions 中的标签映射，最后回退 product / namespace。' },
      { field: '环境', desc: '优先 item.env，其次 dimensions.env。' },
      { field: '资源', desc: '优先 instanceName，其次 instanceId、dimensions.instanceId、dimensions.userId。' },
      { field: '告警指纹', desc: '平台用 ruleId + resource + metricName 组合生成。' },
      { field: '聚合键', desc: '优先 groupId，其次 contactGroups。' },
    ],
    sample: `{
  "alerts": [
    {
      "alertName": "ECS CPU 使用率高",
      "message": "CPU 持续 5 分钟超过 90%",
      "level": "critical",
      "alertState": "ALARM",
      "namespace": "acs_ecs_dashboard",
      "product": "ECS",
      "ruleId": "rule-001",
      "metricName": "CPUUtilization",
      "instanceName": "ecs-prod-01",
      "instanceId": "i-xxxxxx",
      "groupId": "prod-ecs",
      "dimensions": {
        "env": "prod",
        "cluster": "prod-cluster"
      },
      "timestamp": 1778992200
    }
  ]
}`,
  },
  {
    provider: 'generic',
    title: '通用 Webhook',
    note: '字段名越贴近平台统一字段，接入越省事。',
    fields: [
      { field: '标题', desc: '优先 title，其次 name、alertname、labels.alertname。' },
      { field: '描述', desc: '优先 message，其次 description，再其次 annotations.description；都没有时回退标题。' },
      { field: '级别', desc: '优先 level，其次 severity、labels.severity。' },
      { field: '服务', desc: '优先 labels.app，其次 labels.job_name、labels.service，最后回退 payload.service。' },
      { field: '环境', desc: '优先 environment、env，再看 labels.environment、labels.env。' },
      { field: '资源', desc: '优先 resource、instance，再看 labels.instance、labels.host。' },
      { field: '告警指纹', desc: '优先 payload.fingerprint；没有时平台自动计算。' },
      { field: '聚合键', desc: '优先 payload.group_key；没有时平台按聚合规则生成。' },
    ],
    sample: `{
  "title": "订单服务错误率升高",
  "message": "5xx 比例超过阈值",
  "level": "critical",
  "status": "firing",
  "source": "custom-monitor",
  "fingerprint": "custom-order-error-rate",
  "group_key": "service=order-api|env=prod",
  "service": "order-api",
  "environment": "prod",
  "resource": "10.0.1.10:8080",
  "labels": {
    "alertname": "HighErrorRate",
    "team": "trade"
  }
}`,
  },
]

const environmentOptions = computed(() => {
  const values = new Set()
  for (const item of alerts.value || []) {
    const env = String(item?.environment || '').trim()
    if (env) values.add(env)
  }
  const selected = String(filters.environment || '').trim()
  if (selected) values.add(selected)
  return Array.from(values).sort((a, b) => a.localeCompare(b, 'zh-CN'))
})

const integrationDialog = reactive({ visible: false, form: emptyIntegration() })
const muteDialog = reactive({ visible: false, target: null, form: { minutes: 60 } })
const channelDialog = reactive({ visible: false, form: emptyChannel() })
const recipientDialog = reactive({ visible: false, form: emptyRecipient() })
const recipientGroupDialog = reactive({ visible: false, form: emptyRecipientGroup() })
const notificationRuleDialog = reactive({ visible: false, form: emptyNotificationRule() })
const policyDialog = reactive({ visible: false, kind: 'aggregation', title: '', form: emptyAggregationRule() })

function levelType(level) {
  return { critical: 'danger', warning: 'warning', info: 'info' }[level] || 'info'
}

function levelText(level) {
  return { critical: '\u4E25\u91CD', warning: '\u8B66\u544A', info: '\u4FE1\u606F' }[level] || ''
}

function statusType(status) {
  return { active: 'danger', resolved: 'success', muted: 'warning', closed: 'info' }[status] || 'info'
}

function statusText(status) {
  return { active: '\u6D3B\u8DC3', resolved: '\u5DF2\u6062\u590D', muted: '\u5DF2\u5C4F\u853D', closed: '\u5DF2\u5173\u95ED' }[status] || status
}

function providerText(value) {
  return providerOptions.find((item) => item.value === value)?.label || value || '-'
}

function channelText(value) {
  return channelOptions.find((item) => item.value === value)?.label || value || '-'
}

function notifyStatusType(value) {
  return { success: 'success', skipped: 'info', error: 'danger' }[value] || 'info'
}

function formatTime(value) {
  return value ? new Date(value).toLocaleString('zh-CN', { hour12: false }) : '-'
}

function displayIntegrationWebhook(value) {
  const raw = String(value || '').trim()
  if (!raw) return { host: '-', path: '', full: '-' }
  const placeholderHost = '<\u544A\u8B66\u4E2D\u5FC3IP:PORT>'
  if (raw.startsWith('/')) {
    return {
      host: `http://${placeholderHost}`,
      path: raw,
      full: `http://${placeholderHost}${raw}`,
    }
  }
  try {
    const parsed = new URL(raw)
    const host = `${parsed.protocol}//${placeholderHost}`
    const path = `${parsed.pathname}${parsed.search}${parsed.hash}` || '/'
    return { host, path, full: `${host}${path}` }
  } catch {
    const masked = raw.replace(/^https?:\/\/[^/]+/i, `http://${placeholderHost}`)
    const matched = masked.match(/^(https?:\/\/[^/]+)(.*)$/i)
    if (matched) {
      return {
        host: matched[1],
        path: matched[2] || '/',
        full: masked,
      }
    }
    return { host: `http://${placeholderHost}`, path: masked, full: masked }
  }
}

function groupMembers(row) {
  const names = (row.recipients || []).map((item) => item.name)
  const platformUsers = (row.users || []).map((item) => item.display_name || item.username)
  return [...names, ...platformUsers].join('\u3001') || '-'
}

function buildAlertParams() {
  const params = { page: page.value }
  if (filters.search) params.search = filters.search
  if (filters.level) params.level = filters.level
  if (filters.status) params.status = filters.status
  if (filters.claimed) params.claimed = filters.claimed
  if (filters.source_type) params.source_type = filters.source_type
  if (filters.environment) params.environment = filters.environment
  return params
}

async function fetchAlerts() {
  loading.value = true
  try {
    const response = await getAlerts(buildAlertParams())
    alerts.value = listOf(response)
    selectedAlerts.value = []
    total.value = response?.count || alerts.value.length
  } finally {
    loading.value = false
  }
}

async function fetchSummary() {
  summary.value = await getAlertSummary(buildAlertParams())
}

async function fetchGroups() {
  if (eventMode.value !== 'group') return
  loading.value = true
  try {
    groups.value = await getAlertGroups({ ...buildAlertParams(), group_by: groupBy.value.join(',') })
  } finally {
    loading.value = false
  }
}

async function refreshEvents() {
  const tasks = [fetchSummary()]
  if (eventMode.value === 'group') tasks.push(fetchGroups())
  else tasks.push(fetchAlerts())
  await Promise.all(tasks)
}

function handleFilterChange() {
  page.value = 1
  refreshEvents()
}

async function applyStatFilter(card) {
  const shouldClear = activeStatKey.value === card.key
  filters.status = shouldClear ? '' : card.filter.status
  filters.level = shouldClear ? '' : card.filter.level
  filters.claimed = shouldClear ? '' : card.filter.claimed
  activeTab.value = 'events'
  eventMode.value = 'list'
  page.value = 1
  await refreshEvents()
}

function openGroup(row) {
  eventMode.value = 'list'
  filters.search = row.sample_title || ''
  page.value = 1
  refreshEvents()
}

function openDetail(row) {
  selectedAlert.value = row
  detailVisible.value = true
}

function handleSelectionChange(rows) {
  selectedAlerts.value = rows || []
}

async function runAlertAction(row, action) {
  const actionMap = {
    claim: () => claimAlert(row.id),
    unclaim: () => unclaimAlert(row.id),
    mute: () => muteAlert(row.id, { minutes: 60 }),
    escalate: () => escalateAlert(row.id),
    close: () => closeAlert(row.id),
    reopen: () => reopenAlert(row.id),
    notify: () => notifyAlert(row.id, { action: row.status === 'resolved' ? 'resolved' : 'fire' }),
  }
  await actionMap[action]?.()
  ElMessage.success('\u64CD\u4F5C\u5DF2\u63D0\u4EA4')
  detailVisible.value = false
  await refreshAll()
}

function openMuteDialog(row) {
  muteDialog.target = row
  muteDialog.form.minutes = 60
  muteDialog.visible = true
}

async function submitMuteDialog() {
  if (!muteDialog.target?.id) return
  await muteAlert(muteDialog.target.id, { minutes: Number(muteDialog.form.minutes || 60) })
  muteDialog.visible = false
  ElMessage.success('\u64CD\u4F5C\u5DF2\u63D0\u4EA4')
  detailVisible.value = false
  await refreshAll()
}

async function handleRowCommand(command, row) {
  if (command === 'delete') {
    await deleteAlert(row.id)
    ElMessage.success('\u544A\u8B66\u5DF2\u5220\u9664')
    await refreshAll()
    return
  }
  await runAlertAction(row, command)
}

async function handleBatchDelete() {
  if (!selectedAlerts.value.length) return
  await ElMessageBox.confirm(`确认删除已选中的 ${selectedAlerts.value.length} 条告警？`, '批量删除', {
    type: 'warning',
    confirmButtonText: '删除',
    cancelButtonText: '取消',
  })
  await Promise.all(selectedAlerts.value.map((item) => deleteAlert(item.id)))
  selectedAlerts.value = []
  ElMessage.success('\u5DF2\u5220\u9664\u9009\u4E2D\u544A\u8B66')
  await refreshAll()
}

function ensureTabAccess() {
  const tabs = []
  if (canViewAlerts.value) tabs.push('events', 'logs')
  if (canViewConfig.value) tabs.push('notify', 'policies', 'integrations')
  if (!tabs.includes(activeTab.value)) activeTab.value = tabs[0] || 'events'
}

async function switchTab(tab) {
  activeTab.value = tab
  await refreshAll()
}

async function changeNotifyTab(tab) {
  notifyTab.value = tab
  await loadNotifyTab()
}

async function changePolicyTab(tab) {
  policyTab.value = tab
  await loadPolicyTab()
}

async function loadNotifyTab() {
  if (!canViewConfig.value) return
  configLoading.value = true
  try {
    if (notifyTab.value === 'rules') {
      const [rules, channelList, recipientList, groupList, aggregationList, escalationList] = await Promise.all([
        getAlertNotificationRules(),
        getAlertNotificationChannels(),
        getAlertRecipients(),
        getAlertRecipientGroups(),
        getAlertAggregationRules(),
        getAlertEscalationPolicies(),
      ])
      notificationRules.value = listOf(rules)
      channels.value = listOf(channelList)
      recipients.value = listOf(recipientList)
      recipientGroups.value = listOf(groupList)
      aggregationRules.value = listOf(aggregationList)
      escalationPolicies.value = listOf(escalationList)
    } else if (notifyTab.value === 'channels') {
      channels.value = listOf(await getAlertNotificationChannels())
    } else {
      const [recipientList, groupList, userList] = await Promise.all([
        getAlertRecipients(),
        getAlertRecipientGroups(),
        getUsers(),
      ])
      recipients.value = listOf(recipientList)
      recipientGroups.value = listOf(groupList)
      users.value = listOf(userList)
    }
  } finally {
    configLoading.value = false
  }
}

async function loadPolicyTab() {
  if (!canViewConfig.value) return
  configLoading.value = true
  try {
    if (policyTab.value === 'aggregation') {
      aggregationRules.value = listOf(await getAlertAggregationRules())
    } else if (policyTab.value === 'inhibition') {
      inhibitionRules.value = listOf(await getAlertInhibitionRules())
    } else if (policyTab.value === 'mute') {
      muteRules.value = listOf(await getAlertMuteRules())
    } else {
      const [policyList, channelList] = await Promise.all([
        getAlertEscalationPolicies(),
        getAlertNotificationChannels(),
      ])
      escalationPolicies.value = listOf(policyList)
      channels.value = listOf(channelList)
    }
  } finally {
    configLoading.value = false
  }
}

async function fetchIntegrations() {
  configLoading.value = true
  try {
    integrations.value = listOf(await getAlertIntegrations())
  } finally {
    configLoading.value = false
  }
}

async function fetchNotificationLogs() {
  configLoading.value = true
  try {
    notificationLogs.value = listOf(await getAlertNotificationLogs())
  } finally {
    configLoading.value = false
  }
}

async function refreshAll() {
  ensureTabAccess()
  if (activeTab.value === 'events' && canViewAlerts.value) await refreshEvents()
  if (activeTab.value === 'notify' && canViewConfig.value) await loadNotifyTab()
  if (activeTab.value === 'policies' && canViewConfig.value) await loadPolicyTab()
  if (activeTab.value === 'integrations' && canViewConfig.value) await fetchIntegrations()
  if (activeTab.value === 'logs' && canViewAlerts.value) await fetchNotificationLogs()
}

function emptyIntegration() {
  return { id: null, name: '', provider: 'prometheus', default_label_rows: [], is_enabled: true, description: '' }
}

function openIntegration(row = null) {
  integrationDialog.form = row ? { ...row, default_label_rows: matcherRowsFromObject(row.default_labels) } : emptyIntegration()
  integrationDialog.visible = true
}

async function saveIntegration() {
  const data = { ...integrationDialog.form, default_labels: matchersToObject(integrationDialog.form.default_label_rows) }
  if (data.id) await updateAlertIntegration(data.id, data)
  else await createAlertIntegration(data)
  integrationDialog.visible = false
  ElMessage.success('\u63A5\u5165\u6E90\u5DF2\u4FDD\u5B58')
  await fetchIntegrations()
}

async function removeIntegration(id) {
  await deleteAlertIntegration(id)
  ElMessage.success('\u63A5\u5165\u6E90\u5DF2\u5220\u9664')
  await fetchIntegrations()
}

function emptyChannel() {
  return { id: null, name: '', channel_type: 'dingtalk', webhook_url: '', access_token: '', to: '', template_title: '', template_body: '', send_resolved: true, is_enabled: true, timeout_seconds: 8 }
}

function openChannel(row = null) {
  if (row) {
    const config = row.config || {}
    const configTo = config.to || config.phones || []
    channelDialog.form = {
      ...emptyChannel(),
      ...row,
      webhook_url: config.webhook_url || config.url || '',
      access_token: config.access_token || config.token || '',
      to: Array.isArray(configTo) ? configTo.join(',') : String(configTo || ''),
    }
  } else {
    channelDialog.form = emptyChannel()
  }
  channelDialog.visible = true
}

async function saveChannel() {
  const data = { ...channelDialog.form }
  const recipientsText = splitText(data.to)
  data.config = {
    ...(data.webhook_url ? { webhook_url: data.webhook_url } : {}),
    ...(data.access_token ? { access_token: data.access_token } : {}),
    ...(data.channel_type === 'email' ? { to: recipientsText } : {}),
    ...((data.channel_type === 'sms' || data.channel_type === 'voice') ? { phones: recipientsText } : {}),
  }
  if (data.id) await updateAlertNotificationChannel(data.id, data)
  else await createAlertNotificationChannel(data)
  channelDialog.visible = false
  ElMessage.success('\u901A\u77E5\u6E20\u9053\u5DF2\u4FDD\u5B58')
  await loadNotifyTab()
}

async function removeChannel(id) {
  await deleteAlertNotificationChannel(id)
  ElMessage.success('\u901A\u77E5\u6E20\u9053\u5DF2\u5220\u9664')
  await loadNotifyTab()
}

async function testChannel(row) {
  await testAlertNotificationChannel(row.id)
  ElMessage.success('\u6D4B\u8BD5\u8BF7\u6C42\u5DF2\u63D0\u4EA4')
  await fetchNotificationLogs()
}

function emptyRecipient() {
  return { id: null, name: '', phone: '', email: '', dingtalk_user_id: '', feishu_user_id: '', wecom_user_id: '', is_enabled: true }
}

function openRecipient(row = null) {
  recipientDialog.form = row ? { ...emptyRecipient(), ...row } : emptyRecipient()
  recipientDialog.visible = true
}

async function saveRecipient() {
  const data = { ...recipientDialog.form }
  if (data.id) await updateAlertRecipient(data.id, data)
  else await createAlertRecipient(data)
  recipientDialog.visible = false
  ElMessage.success('\u63A5\u6536\u4EBA\u5DF2\u4FDD\u5B58')
  await loadNotifyTab()
}

async function removeRecipient(id) {
  await deleteAlertRecipient(id)
  ElMessage.success('\u63A5\u6536\u4EBA\u5DF2\u5220\u9664')
  await loadNotifyTab()
}

function emptyRecipientGroup() {
  return { id: null, name: '', recipient_ids: [], user_ids: [], is_enabled: true, description: '' }
}

function openRecipientGroup(row = null) {
  recipientGroupDialog.form = row
    ? {
        ...emptyRecipientGroup(),
        ...row,
        recipient_ids: (row.recipients || []).map((item) => item.id),
        user_ids: (row.users || []).map((item) => item.id),
      }
    : emptyRecipientGroup()
  recipientGroupDialog.visible = true
}

async function saveRecipientGroup() {
  const data = { ...recipientGroupDialog.form }
  if (data.id) await updateAlertRecipientGroup(data.id, data)
  else await createAlertRecipientGroup(data)
  recipientGroupDialog.visible = false
  ElMessage.success('\u63A5\u6536\u7EC4\u5DF2\u4FDD\u5B58')
  await loadNotifyTab()
}

async function removeRecipientGroup(id) {
  await deleteAlertRecipientGroup(id)
  ElMessage.success('\u63A5\u6536\u7EC4\u5DF2\u5220\u9664')
  await loadNotifyTab()
}

function emptyNotificationRule() {
  return {
    id: null,
    name: '',
    matchers: [],
    min_level: '',
    channel_ids: [],
    recipient_ids: [],
    recipient_group_ids: [],
    aggregation_rule: null,
    escalation_policy: null,
    notify_on_fire: true,
    notify_on_resolved: true,
    notify_on_escalation: true,
    is_enabled: true,
    description: '',
  }
}

function openNotificationRule(row = null) {
  notificationRuleDialog.form = row
    ? {
        ...emptyNotificationRule(),
        ...row,
        channel_ids: (row.channels || []).map((item) => item.id),
        recipient_ids: (row.recipients || []).map((item) => item.id),
        recipient_group_ids: (row.recipient_groups || []).map((item) => item.id),
        matchers: clone(row.matchers || []),
      }
    : emptyNotificationRule()
  notificationRuleDialog.visible = true
}

async function saveNotificationRule() {
  const data = { ...notificationRuleDialog.form }
  if (data.id) await updateAlertNotificationRule(data.id, data)
  else await createAlertNotificationRule(data)
  notificationRuleDialog.visible = false
  ElMessage.success('\u901A\u77E5\u89C4\u5219\u5DF2\u4FDD\u5B58')
  await loadNotifyTab()
}

async function removeNotificationRule(id) {
  await deleteAlertNotificationRule(id)
  ElMessage.success('\u901A\u77E5\u89C4\u5219\u5DF2\u5220\u9664')
  await loadNotifyTab()
}

function emptyAggregationRule() {
  return { id: null, name: '', matchers: [], group_by: ['source_type', 'environment', 'service'], window_minutes: 5, repeat_interval_minutes: 30, is_enabled: true, description: '' }
}

function emptyInhibitionRule() {
  return { id: null, name: '', source_matchers: [], target_matchers: [], equal_labels: ['service', 'resource'], duration_minutes: 60, is_enabled: true, description: '' }
}

function emptyMuteRule() {
  return { id: null, name: '', matchers: [], range: [], starts_at: null, ends_at: null, reason: '', is_enabled: true, description: '' }
}

function emptyEscalationPolicy() {
  return { id: null, name: '', matchers: [], levels: [{ name: '\u4E00\u7EA7\u5347\u7EA7', after_minutes: 30, channel_ids: [] }], repeat_interval_minutes: 30, is_enabled: true, description: '' }
}

function openAggregationRule(row = null) {
  policyDialog.kind = 'aggregation'
  policyDialog.title = '\u805A\u5408\u89C4\u5219'
  policyDialog.form = row ? { ...emptyAggregationRule(), ...row, matchers: clone(row.matchers), group_by: clone(row.group_by) } : emptyAggregationRule()
  policyDialog.visible = true
}

function openInhibitionRule(row = null) {
  policyDialog.kind = 'inhibition'
  policyDialog.title = '\u6291\u5236\u89C4\u5219'
  policyDialog.form = row ? { ...emptyInhibitionRule(), ...row, source_matchers: clone(row.source_matchers), target_matchers: clone(row.target_matchers), equal_labels: clone(row.equal_labels) } : emptyInhibitionRule()
  policyDialog.visible = true
}

function openMuteRule(row = null) {
  policyDialog.kind = 'mute'
  policyDialog.title = '\u5C4F\u853D\u89C4\u5219'
  policyDialog.form = row ? { ...emptyMuteRule(), ...row, matchers: clone(row.matchers), range: row.starts_at && row.ends_at ? [row.starts_at, row.ends_at] : [] } : emptyMuteRule()
  policyDialog.visible = true
}

function openEscalationPolicy(row = null) {
  policyDialog.kind = 'escalation'
  policyDialog.title = '\u5347\u7EA7\u7B56\u7565'
  policyDialog.form = row ? { ...emptyEscalationPolicy(), ...row, matchers: clone(row.matchers), levels: clone(row.levels || []) } : emptyEscalationPolicy()
  policyDialog.visible = true
}

async function savePolicy() {
  const data = { ...policyDialog.form }
  if (policyDialog.kind === 'mute') {
    data.starts_at = data.range?.[0] || null
    data.ends_at = data.range?.[1] || null
  }
  const actionMap = {
    aggregation: [createAlertAggregationRule, updateAlertAggregationRule, loadPolicyTab],
    inhibition: [createAlertInhibitionRule, updateAlertInhibitionRule, loadPolicyTab],
    mute: [createAlertMuteRule, updateAlertMuteRule, loadPolicyTab],
    escalation: [createAlertEscalationPolicy, updateAlertEscalationPolicy, loadPolicyTab],
  }
  const [createFn, updateFn, refreshFn] = actionMap[policyDialog.kind]
  if (data.id) await updateFn(data.id, data)
  else await createFn(data)
  policyDialog.visible = false
  ElMessage.success('\u7B56\u7565\u5DF2\u4FDD\u5B58')
  await refreshFn()
}

async function removeAggregationRule(id) {
  await deleteAlertAggregationRule(id)
  ElMessage.success('\u805A\u5408\u89C4\u5219\u5DF2\u5220\u9664')
  await loadPolicyTab()
}

async function removeInhibitionRule(id) {
  await deleteAlertInhibitionRule(id)
  ElMessage.success('\u6291\u5236\u89C4\u5219\u5DF2\u5220\u9664')
  await loadPolicyTab()
}

async function removeMuteRule(id) {
  await deleteAlertMuteRule(id)
  ElMessage.success('\u5C4F\u853D\u89C4\u5219\u5DF2\u5220\u9664')
  await loadPolicyTab()
}

async function removeEscalationPolicy(id) {
  await deleteAlertEscalationPolicy(id)
  ElMessage.success('\u5347\u7EA7\u7B56\u7565\u5DF2\u5220\u9664')
  await loadPolicyTab()
}

function applyRouteFilters() {
  filters.search = typeof route.query.search === 'string' ? route.query.search.trim() : ''
  filters.level = typeof route.query.level === 'string' ? route.query.level.trim() : ''
  if (route.query.claimed === '0' || route.query.ack === '0') filters.claimed = '0'
  else if (route.query.claimed === '1' || route.query.ack === '1') filters.claimed = '1'
  else filters.claimed = ''
}

watch(
  () => [route.query.search || '', route.query.level || '', route.query.claimed || '', route.query.ack || ''].join('|'),
  async () => {
    applyRouteFilters()
    page.value = 1
    await refreshAll()
  },
)

onMounted(async () => {
  applyRouteFilters()
  users.value = listOf(await getUsers())
  await refreshAll()
})
</script>

<style scoped>
.alerts-page {
  --alert-primary: #3370ff;
  --alert-bg: #f7f8fa;
  --alert-panel: #ffffff;
  --alert-border-soft: #eff0f2;
  --alert-text: #1f2329;
  --alert-muted: #646a73;
  --alert-subtle: #8f959e;
  --alert-shadow: 0 8px 24px rgba(31, 35, 41, 0.06);
  background: linear-gradient(180deg, rgba(247, 248, 250, 0.94), rgba(255, 255, 255, 0) 180px), var(--alert-bg);
  color: var(--alert-text);
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-height: 100%;
}

.hero,
.hero-title-row,
.hero-actions,
.toolbar,
.row-actions,
.group-toolbar,
.section-head,
.detail-actions,
.matcher-row,
.level-row,
.claimant-cell {
  align-items: center;
  display: flex;
  gap: 4px;
}

.claimant-cell {
  flex-wrap: wrap;
}

.claimant-tag {
  margin: 0;
}

.hero.panel {
  background: linear-gradient(180deg, #ffffff 0%, #fffdf8 100%);
  border: 1px solid var(--alert-border-soft);
  border-radius: 12px;
  box-shadow: 0 6px 16px rgba(15, 23, 42, 0.04);
  justify-content: space-between;
  padding: 12px 14px;
}

.hero-copy {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.hero-title-row {
  align-items: center;
  gap: 10px;
}

.hero-title-row h2 {
  color: #0f172a;
  font-size: 23px;
  font-weight: 700;
  line-height: 1.1;
  margin: 0;
}

.page-inline-desc {
  color: #64748b;
  font-size: 13px;
  line-height: 1.45;
  margin: 0;
  flex: 0 1 auto;
  transform: translateY(1px);
}

.hero-icon {
  align-items: center;
  background: linear-gradient(135deg, #0f766e, #0ea5e9);
  border-radius: 16px;
  color: #fff;
  display: inline-flex;
  height: 40px;
  justify-content: center;
  width: 40px;
}

.hero-actions .el-button {
  border-radius: 10px;
  font-weight: 500;
  min-height: 32px;
  padding: 0 14px;
}

.panel {
  background: var(--alert-panel);
  border: 1px solid var(--alert-border-soft);
  border-radius: 16px;
  box-shadow: var(--alert-shadow);
  padding: 12px 14px;
}

.alert-center-tabs .neo-tab-btn {
  min-height: 36px;
  padding: 0 18px;
}

.alert-center-tabs.theme-blue .neo-tab-btn.active {
  color: #245bdb;
  background: rgba(51, 112, 255, 0.1);
  box-shadow: inset 0 0 0 1px rgba(51, 112, 255, 0.08);
}

.alert-center-tabs {
  margin: 0;
}

.alert-sub-tabs {
  flex-wrap: wrap;
  margin-bottom: 8px;
}

.alert-sub-tabs .neo-sub-tab-btn {
  min-height: 30px;
  padding: 0 14px;
}

.alert-top-stats {
  display: grid;
  gap: 8px;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  margin-bottom: 0;
}

.alert-summary-card {
  justify-content: center;
  min-height: 68px;
  padding: 14px 16px;
}

.alert-summary-card.audit-card--action:hover {
  border-color: rgba(36, 91, 219, 0.16);
  box-shadow: 0 10px 20px rgba(36, 91, 219, 0.06);
}

.alert-summary-card.audit-card--action.is-active {
  border-color: rgba(36, 91, 219, 0.24);
  background: linear-gradient(180deg, #f4f7ff 0%, #ffffff 100%);
  box-shadow: 0 0 0 1px rgba(36, 91, 219, 0.05), 0 12px 22px rgba(36, 91, 219, 0.08);
}

.alert-summary-card .stat-label {
  color: #334155;
  font-size: 13px;
  font-weight: 600;
}

.alert-summary-card .stat-value {
  color: #1f2329;
  font-size: 24px;
}

.toolbar,
.group-toolbar {
  background: #fbfcff;
  border: 1px solid var(--alert-border-soft);
  border-radius: 12px;
  margin-bottom: 8px;
  padding: 8px 10px;
}

.toolbar {
  flex-wrap: wrap;
}

.toolbar-spacer {
  flex: 1 1 auto;
}

.section-actions {
  align-items: center;
  display: flex;
  gap: 8px;
}

.toolbar .el-input {
  width: 280px;
}

.toolbar .el-select {
  width: 120px;
}

.group-toolbar .el-select {
  min-width: 420px;
}

.toolbar-label {
  color: var(--alert-muted);
  font-size: 12px;
  font-weight: 600;
}

.data-table {
  width: 100%;
}

.link-title {
  background: transparent;
  border: 0;
  color: var(--alert-text);
  cursor: pointer;
  font-weight: 600;
  padding: 0;
  text-align: left;
}

.link-title:hover {
  color: var(--alert-primary);
}

.alert-id-cell {
  color: var(--alert-text);
  font-size: 12px;
  font-weight: 500;
  line-height: 1.4;
}

.sub-line {
  color: var(--alert-subtle);
  margin-top: 3px;
}

.group-key {
  font-family: "JetBrains Mono", "SFMono-Regular", Consolas, monospace;
  font-weight: 600;
}

.pager {
  display: flex;
  justify-content: flex-end;
  padding-top: 8px;
}

.section-head {
  justify-content: space-between;
  margin-bottom: 8px;
  min-height: 30px;
}

.section-head h3 {
  font-size: 15px;
  font-weight: 700;
  margin: 0;
}

.split-grid {
  display: grid;
  gap: 8px;
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.split-panel {
  background: #fbfcff;
  border: 1px solid var(--alert-border-soft);
  border-radius: 14px;
  padding: 10px 12px;
}

.mini-tag {
  margin: 0 4px 4px 0;
}

.separator {
  color: #cbd5e1;
  margin: 0 6px;
}

.mono {
  color: var(--alert-muted);
  font-family: "JetBrains Mono", "SFMono-Regular", Consolas, monospace;
}

.webhook-url-cell {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.webhook-url-line {
  line-height: 1.45;
  white-space: normal;
}

.webhook-url-host {
  color: #334155;
  white-space: nowrap;
}

.webhook-url-path {
  word-break: break-all;
}

.integration-help {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.integration-help-hero {
  background: linear-gradient(180deg, #f8fbff 0%, #fdfefe 100%);
  border: 1px solid rgba(51, 112, 255, 0.14);
  border-radius: 12px;
  padding: 12px 14px;
}

.integration-help-hero-title {
  color: var(--alert-text);
  font-size: 14px;
  font-weight: 700;
  line-height: 1.3;
}

.integration-help-hero-desc {
  color: #64748b;
  font-size: 12px;
  line-height: 1.65;
  margin-top: 4px;
}

.integration-help-card {
  background: #fbfcff;
  border: 1px solid var(--alert-border-soft);
  border-radius: 12px;
  padding: 12px;
}

.integration-help-head {
  margin-bottom: 8px;
}

.integration-help-title {
  color: var(--alert-text);
  font-size: 14px;
  font-weight: 700;
  line-height: 1.3;
}

.integration-help-note {
  color: var(--alert-subtle);
  font-size: 12px;
  line-height: 1.5;
  margin-top: 3px;
}

.integration-help-grid {
  display: grid;
  gap: 8px;
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.integration-help-item {
  background: #fff;
  border: 1px solid #edf0f5;
  border-radius: 10px;
  padding: 10px;
}

.integration-help-field {
  color: #1f2937;
  font-size: 12px;
  font-weight: 700;
  line-height: 1.2;
  margin-bottom: 4px;
}

.integration-help-desc {
  color: #475569;
  font-size: 12px;
  line-height: 1.65;
}

.integration-sample-block {
  margin-top: 10px;
}

.integration-sample-title {
  color: #1f2937;
  font-size: 12px;
  font-weight: 700;
  line-height: 1.2;
  margin-bottom: 6px;
}

.integration-sample-code {
  background: #0f172a;
  border-radius: 10px;
  color: #e2e8f0;
  font-family: "JetBrains Mono", "SFMono-Regular", Consolas, monospace;
  font-size: 11px;
  line-height: 1.6;
  margin: 0;
  overflow-x: auto;
  overflow-y: hidden;
  padding: 10px 12px;
  white-space: pre-wrap;
  word-break: break-word;
}

.alert-detail-body {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.detail-head {
  align-items: flex-start;
  background: linear-gradient(135deg, #ffffff 0%, #f6faff 100%);
  border: 1px solid rgba(51, 112, 255, 0.16);
  border-radius: 10px;
  box-shadow: 0 8px 20px rgba(31, 35, 41, 0.05);
  display: flex;
  flex-direction: column;
  gap: 7px;
  margin: 0;
  padding: 10px 12px;
}

.detail-badges {
  align-items: center;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.detail-alert-id {
  border: 1px solid rgba(148, 163, 184, 0.24);
  border-radius: 999px;
  color: #475569;
  font-size: 12px;
  font-weight: 500;
  line-height: 22px;
  padding: 0 9px;
}

.detail-title {
  color: var(--alert-text);
  font-size: 14px;
  font-weight: 700;
  line-height: 1.45;
}

.detail-fingerprint {
  color: var(--alert-subtle);
  font-family: "JetBrains Mono", "SFMono-Regular", Consolas, monospace;
  font-size: 11px;
  line-height: 1.45;
  word-break: break-all;
}

.alert-detail-card {
  background: #fff;
  border: 1px solid var(--alert-border-soft);
  border-radius: 10px;
  box-shadow: 0 6px 14px rgba(15, 23, 42, 0.035);
  padding: 8px;
}

.alert-detail-summary {
  overflow: hidden;
  border-radius: 8px;
}

.alert-detail-summary :deep(.el-descriptions__table) {
  border-radius: 8px;
}

.alert-detail-summary :deep(.el-descriptions__cell) {
  border-color: #edf0f5;
}

.alert-detail-summary :deep(.el-descriptions__label) {
  background: #f8fafc;
  box-sizing: border-box;
  color: #64748b;
  font-size: 12px;
  font-weight: 600;
  min-width: 64px;
  padding: 6px 8px;
  text-align: left;
  white-space: nowrap;
  width: 64px;
  word-break: keep-all;
}

.alert-detail-summary :deep(.el-descriptions__content) {
  color: #334155;
  font-size: 12px;
  line-height: 1.45;
  padding: 6px 8px;
  word-break: break-word;
}

.detail-actions {
  background: #fff;
  border: 1px solid var(--alert-border-soft);
  border-radius: 10px;
  box-shadow: 0 6px 14px rgba(15, 23, 42, 0.035);
  flex-wrap: wrap;
  gap: 6px;
  margin: 0;
  padding: 8px;
}

.detail-actions :deep(.el-button) {
  margin-left: 0;
}

.detail-section-title {
  align-items: center;
  display: flex;
  justify-content: space-between;
  margin-bottom: 7px;
}

.detail-section-title h4 {
  color: var(--alert-text);
  font-size: 13px;
  font-weight: 700;
  line-height: 1;
  margin: 0;
}

.detail-section-title span,
.detail-empty {
  color: var(--alert-muted);
  font-size: 12px;
}

.field-suffix {
  color: var(--alert-muted);
  margin-left: 8px;
}

.mute-presets {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.kv-list {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  margin-bottom: 0;
}

.alert-detail-timeline {
  margin-top: 2px;
  padding-left: 2px;
}

.alert-detail-timeline :deep(.el-timeline-item) {
  padding-bottom: 10px;
}

.alert-detail-timeline :deep(.el-timeline-item__timestamp) {
  color: #8f959e;
  font-size: 11px;
  line-height: 1.3;
}

.alert-detail-timeline :deep(.el-timeline-item__content) {
  color: #334155;
  font-size: 12px;
  line-height: 1.45;
}

.matcher-editor,
.level-editor {
  display: flex;
  flex-direction: column;
  gap: 6px;
  width: 100%;
}

.matcher-row,
.level-row {
  flex-wrap: nowrap;
  width: 100%;
}

.matcher-row .el-input {
  flex: 1;
}

.matcher-row .el-select {
  width: 110px;
}

.level-row {
  background: #fbfcff;
  border: 1px solid var(--alert-border-soft);
  border-radius: 12px;
  padding: 7px 8px;
}

.level-row .el-input {
  width: 150px;
}

.level-row .el-select {
  min-width: 220px;
}

.alerts-page :deep(.el-input__wrapper),
.alerts-page :deep(.el-select__wrapper) {
  background: #fff;
  border-radius: 10px;
  box-shadow: 0 0 0 1px var(--alert-border-soft) inset;
}

.alerts-page :deep(.el-drawer__header) {
  margin-bottom: 8px;
}

.alerts-page :deep(.el-drawer__body) {
  padding-top: 8px;
}

.alerts-page :deep(.alert-detail-drawer .el-drawer__header) {
  border-bottom: 1px solid #edf0f5;
  margin-bottom: 0;
  padding: 14px 18px 10px;
}

.alerts-page :deep(.alert-detail-drawer .el-drawer__body) {
  background: #f7f8fa;
  padding: 10px 14px 14px;
}

.alerts-page :deep(.el-button--primary) {
  --el-button-bg-color: var(--alert-primary);
  --el-button-border-color: var(--alert-primary);
  --el-button-hover-bg-color: #2b63db;
  --el-button-hover-border-color: #2b63db;
  border-radius: 10px;
}

.alerts-page :deep(.el-button:not(.is-link)) {
  border-radius: 10px;
}

.alerts-page :deep(.el-segmented) {
  --el-segmented-item-selected-bg-color: #ffffff;
  --el-segmented-item-selected-color: var(--alert-primary);
  background: #f2f3f5;
  border-radius: 10px;
  padding: 2px;
}

.alerts-page :deep(.el-table) {
  --el-table-border-color: var(--alert-border-soft);
  --el-table-header-bg-color: #fbfcff;
  --el-table-header-text-color: var(--alert-muted);
  --el-table-row-hover-bg-color: #f7faff;
  border-radius: 12px;
  color: var(--alert-text);
  overflow: hidden;
}

.alerts-page :deep(.el-tag) {
  border-radius: 999px;
  font-weight: 500;
}

.alerts-page :deep(.el-dialog),
.alerts-page :deep(.el-drawer) {
  border-radius: 10px;
}

@media (max-width: 1100px) {
  .alert-top-stats,
  .split-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .integration-help-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 760px) {
  .hero.panel,
  .hero-title-row,
  .matcher-row,
  .level-row {
    align-items: stretch;
    flex-direction: column;
  }

  .page-inline-desc {
    flex-basis: 100%;
    padding-left: 54px;
  }

  .alert-top-stats,
  .split-grid {
    grid-template-columns: 1fr;
  }

  .toolbar .el-input,
  .toolbar .el-select,
  .group-toolbar .el-select,
  .level-row .el-input,
  .level-row .el-select,
  .matcher-row .el-select {
    min-width: 0;
    width: 100%;
  }
}
</style>
