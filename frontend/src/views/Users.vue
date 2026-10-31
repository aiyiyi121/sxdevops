<template>
  <div class="fade-in users-page workbench-page-shell">
    <section class="hero panel">
      <div class="release-hero-copy">
        <div class="release-hero-title-row">
          <span class="release-header-icon"><el-icon><User /></el-icon></span>
          <h2>用户管理</h2>
          <p class="page-inline-desc">统一维护用户、用户组、角色与权限字典，支持内置权限同步与账号治理。</p>
        </div>
      </div>
    </section>

    <div class="neo-tabs theme-blue users-tabs">
      <button
        v-if="canViewUsers"
        type="button"
        class="neo-tab-btn"
        :class="{ active: activeTab === 'users' }"
        @click="switchTab('users')"
      >
        <el-icon><User /></el-icon>
        用户
      </button>
      <button
        v-if="canViewGroups"
        type="button"
        class="neo-tab-btn"
        :class="{ active: activeTab === 'groups' }"
        @click="switchTab('groups')"
      >
        <el-icon><UserFilled /></el-icon>
        用户组
      </button>
      <button
        v-if="canViewRoles"
        type="button"
        class="neo-tab-btn"
        :class="{ active: activeTab === 'roles' }"
        @click="switchTab('roles')"
      >
        <el-icon><Avatar /></el-icon>
        角色
      </button>
      <button
        v-if="canViewPermissions"
        type="button"
        class="neo-tab-btn"
        :class="{ active: activeTab === 'permissions' }"
        @click="switchTab('permissions')"
      >
        <el-icon><Grid /></el-icon>
        权限字典
      </button>
    </div>

    <div class="workbench-card users-content-card">
      <div class="section-toolbar">
        <div class="toolbar-head">
          <span class="toolbar-title">{{ sectionTitle }}</span>
          <span class="toolbar-desc">{{ sectionDesc }}</span>
        </div>
        <div class="workbench-card-actions">
          <el-button v-if="canSync" class="filter-refresh-btn" @click="handleSyncPermissions">
            <el-icon><RefreshRight /></el-icon>
            同步内置权限
          </el-button>
          <el-button v-if="activeTab === 'users' && canManageUsers" type="primary" @click="openUserDialog()">
            <el-icon><Plus /></el-icon>
            新增用户
          </el-button>
          <el-button v-if="activeTab === 'roles' && canManageRoles" type="primary" @click="openRoleDialog()">
            <el-icon><Plus /></el-icon>
            新增角色
          </el-button>
          <el-button v-if="activeTab === 'groups' && canManageGroups" type="primary" @click="openGroupDialog()">
            <el-icon><Plus /></el-icon>
            新增用户组
          </el-button>
        </div>
      </div>

      <div class="workbench-toolbar workbench-toolbar--history users-toolbar">
        <div class="workbench-toolbar-left">
          <template v-if="activeTab === 'users'">
            <el-input v-model="userSearch" placeholder="搜索用户名 / 邮箱" clearable class="users-search" @input="searchUsers" />
          </template>
          <template v-else-if="activeTab === 'roles'">
            <el-input v-model="roleSearch" placeholder="搜索角色编码 / 名称" clearable style="width: 260px" @input="fetchRoles" />
          </template>
          <template v-else-if="activeTab === 'groups'">
            <el-input v-model="groupSearch" placeholder="搜索用户组编码 / 名称" clearable style="width: 260px" @input="fetchGroups" />
          </template>
          <template v-else>
            <el-input v-model="permissionSearch" placeholder="搜索权限编码 / 名称" clearable style="width: 280px" @input="applyPermissionFilter" />
          </template>
        </div>
        <div class="workbench-toolbar-right">
          <el-button class="filter-refresh-btn" @click="handleRefreshCurrentTab">
            <el-icon><RefreshRight /></el-icon>
            刷新
          </el-button>
        </div>
      </div>

      <template v-if="activeTab === 'users' && canViewUsers">
        <el-table :data="users" stripe v-loading="loading.users" style="width: 100%">
          <el-table-column prop="username" label="用户名" min-width="130" />
          <el-table-column label="姓名" min-width="120">
            <template #default="{ row }">{{ row.display_name || row.username }}</template>
          </el-table-column>
          <el-table-column prop="email" label="邮箱" min-width="180" />
          <el-table-column label="用户组" min-width="130">
            <template #default="{ row }">
              <el-tag v-for="group in row.user_groups" :key="group.id" size="small" type="info" class="tag-gap">{{ group.name }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="角色" min-width="150">
            <template #default="{ row }">
              <el-tag v-for="role in row.roles" :key="role.id" size="small" class="tag-gap">{{ role.name }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="82">
            <template #default="{ row }">
              <el-tag :type="row.is_active ? 'success' : 'danger'" size="small">{{ row.is_active ? '启用' : '禁用' }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="系统身份" width="108">
            <template #default="{ row }">
              <el-tag :type="row.is_superuser ? 'danger' : row.is_staff ? 'warning' : 'info'" size="small">
                {{ row.is_superuser ? '超级管理员' : row.is_staff ? '管理员' : '普通用户' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="加入时间" width="150">
            <template #default="{ row }">{{ formatTime(row.date_joined) }}</template>
          </el-table-column>
          <el-table-column label="操作" :width="canManageUsers ? 300 : 70" fixed="right" class-name="users-actions-column">
            <template #default="{ row }">
              <el-button link type="primary" @click="permissionUser = row">权限</el-button>
              <template v-if="canManageUsers">
              <el-button link type="primary" :disabled="!row.can_manage && !authStore.isPreview" @click="openUserDialog(row)">编辑</el-button>
              <el-button link type="primary" :disabled="(!row.can_manage && !authStore.isPreview) || row.is_superuser" @click="k8sAccessDialog?.open(row)">K8s 授权</el-button>
              <el-button link type="warning" :disabled="!row.can_manage && !authStore.isPreview" @click="openPasswordDialog(row)">重置密码</el-button>
              <el-popconfirm title="删除后账号及其聊天将不可恢复，确定删除？" @confirm="handleDeleteUser(row.id)">
                <template #reference>
                  <el-button link type="danger" :disabled="!row.can_remove && !authStore.isPreview">删除</el-button>
                </template>
              </el-popconfirm>
              </template>
            </template>
          </el-table-column>
        </el-table>
        <div class="pagination-row">
          <el-pagination
            v-model:current-page="userPage"
            :page-size="20"
            :total="userTotal"
            layout="total, prev, pager, next"
            @current-change="fetchUsers"
          />
        </div>
      </template>

      <template v-else-if="activeTab === 'roles' && canViewRoles">
        <el-table :data="roles" stripe v-loading="loading.roles" style="width: 100%">
          <el-table-column prop="code" label="角色编码" width="160" />
          <el-table-column prop="name" label="角色名称" min-width="160" />
          <el-table-column prop="description" label="说明" min-width="220" />
          <el-table-column label="权限数" width="100">
            <template #default="{ row }">{{ row.permissions.length }}</template>
          </el-table-column>
          <el-table-column label="内置" width="90">
            <template #default="{ row }">
              <el-tag :type="row.is_builtin ? 'warning' : 'info'" size="small">{{ row.is_builtin ? '是' : '否' }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" :width="canManageRoles ? 190 : 70" fixed="right">
            <template #default="{ row }">
              <el-button link type="primary" @click="openRoleDialog(row)">{{ row.can_manage ? '编辑' : '查看' }}</el-button>
              <el-button v-if="canManageRoles" link type="primary" @click="copyRole(row)">复制</el-button>
              <el-popconfirm v-if="canManageRoles" title="确定删除该角色吗？" @confirm="handleDeleteRole(row.id)">
                <template #reference>
                  <el-button link type="danger" :disabled="!row.can_manage">删除</el-button>
                </template>
              </el-popconfirm>
            </template>
          </el-table-column>
        </el-table>
      </template>

      <template v-else-if="activeTab === 'groups' && canViewGroups">
        <el-table :data="groups" stripe v-loading="loading.groups" style="width: 100%">
          <el-table-column prop="code" label="用户组编码" width="160" />
          <el-table-column prop="name" label="用户组名称" min-width="160" />
          <el-table-column prop="description" label="说明" min-width="220" />
          <el-table-column label="角色" min-width="220">
            <template #default="{ row }">
              <el-tag v-for="role in row.roles" :key="role.id" size="small" class="tag-gap">{{ role.name }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="成员数" width="90">
            <template #default="{ row }">{{ row.users.length }}</template>
          </el-table-column>
          <el-table-column v-if="canManageGroups" label="操作" width="140" fixed="right">
            <template #default="{ row }">
              <el-button link type="primary" :disabled="!row.can_manage && !authStore.isPreview" @click="openGroupDialog(row)">编辑</el-button>
              <el-popconfirm title="确定删除该用户组吗？" @confirm="handleDeleteGroup(row.id)">
                <template #reference>
                  <el-button link type="danger" :disabled="row.is_builtin || !row.can_manage">删除</el-button>
                </template>
              </el-popconfirm>
            </template>
          </el-table-column>
        </el-table>
      </template>

      <template v-else-if="activeTab === 'permissions' && canViewPermissions">
        <el-table :data="filteredPermissions" stripe v-loading="loading.permissions" style="width: 100%">
          <el-table-column prop="category" label="模块" width="120" />
          <el-table-column prop="name" label="权限名称" min-width="180" />
          <el-table-column prop="code" label="权限编码" min-width="220" />
          <el-table-column prop="description" label="说明" min-width="260" />
        </el-table>
      </template>
    </div>

    <K8sUserAccessDialog ref="k8sAccessDialog" />
    <el-dialog top="5vh" :close-on-click-modal="false" class="workbench-edit-dialog" v-model="userDialogVisible" :title="editingUserId ? '编辑用户' : '新增用户'" width="min(720px, 94vw)" destroy-on-close append-to-body>
      <el-form ref="userFormRef" :rules="userRules" :disabled="saving.user" class="workbench-editor-form--sectioned" label-position="top" :model="userForm" label-width="90px" @submit.prevent>
        <section class="workbench-editor-section">
          <div class="workbench-editor-heading"><span class="workbench-editor-step">01</span><h3>账号信息</h3></div>
          <div>
            <div class="workbench-editor-grid">
              <el-form-item label="用户名" prop="username">
                <el-input v-model="userForm.username" :disabled="!!editingUserId" />
              </el-form-item>
              <el-form-item label="邮箱" prop="email">
                <el-input v-model="userForm.email" />
              </el-form-item>
              <el-form-item label="名">
                <el-input v-model="userForm.first_name" />
              </el-form-item>
              <el-form-item label="姓">
                <el-input v-model="userForm.last_name" />
              </el-form-item>
              <el-form-item label="密码" prop="password">
                <el-input v-model="userForm.password" type="password" show-password autocomplete="new-password" :placeholder="editingUserId ? '留空则不修改' : '请输入密码'" />
              </el-form-item>
              <el-form-item label="启用">
                <el-switch v-model="userForm.is_active" :disabled="editingUserId === authStore.currentUser?.id || (editingUserId && !users.find(item => item.id === editingUserId)?.can_remove)" />
                <span class="field-hint">停用或修改密码后，原登录凭据立即失效。</span>
              </el-form-item>
            </div>
          </div>
        </section>
        <section class="workbench-editor-section workbench-editor-section--tinted">
          <div class="workbench-editor-heading"><span class="workbench-editor-step">02</span><h3>成员与角色</h3></div>
          <div>
            <el-form-item label="用户组">
              <el-select v-model="userForm.group_ids" multiple filterable style="width:100%">
                <el-option v-for="group in assignmentOptions.groups" :key="group.id" :label="group.name" :value="group.id" />
              </el-select>
            </el-form-item>
            <el-form-item label="角色">
              <el-select v-model="userForm.role_ids" multiple filterable style="width:100%">
                <el-option v-for="role in assignmentOptions.roles" :key="role.id" :label="role.name" :value="role.id" />
              </el-select>
            </el-form-item>
          </div>
        </section>
      </el-form>
      <template #footer>
        <el-button @click="userDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving.user" @click="handleSaveUser">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog top="5vh" :close-on-click-modal="false" class="workbench-edit-dialog" v-model="roleDialogVisible" :title="currentRoleReadOnly ? (currentRoleBuiltin ? '查看内置角色' : '查看角色') : editingRoleId ? '编辑角色' : '新增角色'" width="min(760px, 94vw)" destroy-on-close append-to-body>
      <el-form ref="roleFormRef" :rules="roleRules" :disabled="saving.role || currentRoleReadOnly" class="workbench-editor-form--sectioned" label-position="top" :model="roleForm" label-width="90px" @submit.prevent>
        <section class="workbench-editor-section">
          <div class="workbench-editor-heading"><span class="workbench-editor-step">01</span><h3>角色信息</h3></div>
          <div class="workbench-editor-grid">
            <el-form-item label="角色编码" prop="code">
              <el-input v-model="roleForm.code" :disabled="currentRoleReadOnly || saving.role" />
            </el-form-item>
            <el-form-item label="角色名称" prop="name">
              <el-input v-model="roleForm.name" />
            </el-form-item>
            <el-form-item class="workbench-editor-full" label="说明">
              <el-input v-model="roleForm.description" type="textarea" :rows="3" />
            </el-form-item>
          </div>
        </section>
        <section class="workbench-editor-section workbench-editor-section--tinted">
          <div class="workbench-editor-heading"><span class="workbench-editor-step">02</span><h3>权限范围</h3></div>
          <div>
            <el-form-item label="权限">
              <div v-if="currentRoleReadOnly" class="permission-code-list">
                <code v-for="permission in rolePermissionOptions" :key="permission.id">{{ permission.name }} · {{ permission.code }}</code>
              </div>
              <el-select v-else v-model="roleForm.permission_ids" multiple filterable collapse-tags style="width:100%">
                <el-option v-for="permission in rolePermissionOptions" :key="permission.id" :label="`${permission.name} (${permission.code})`" :value="permission.id" />
              </el-select>
            </el-form-item>
          </div>
        </section>
      </el-form>
      <template #footer>
        <el-button @click="roleDialogVisible = false">取消</el-button>
        <el-button v-if="!currentRoleReadOnly" type="primary" :loading="saving.role" @click="handleSaveRole">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog top="5vh" :close-on-click-modal="false" class="workbench-edit-dialog" v-model="groupDialogVisible" :title="editingGroupId ? '编辑用户组' : '新增用户组'" width="min(760px, 94vw)" destroy-on-close append-to-body>
      <el-form ref="groupFormRef" :rules="groupRules" :disabled="saving.group" class="workbench-editor-form--sectioned" label-position="top" :model="groupForm" label-width="90px" @submit.prevent>
        <section class="workbench-editor-section">
          <div class="workbench-editor-heading"><span class="workbench-editor-step">01</span><h3>用户组信息</h3></div>
          <div class="workbench-editor-grid">
            <el-form-item label="用户组编码" prop="code">
              <el-input v-model="groupForm.code" :disabled="currentGroupBuiltin" />
            </el-form-item>
            <el-form-item label="用户组名称" prop="name">
              <el-input v-model="groupForm.name" />
            </el-form-item>
            <el-form-item class="workbench-editor-full" label="说明">
              <el-input v-model="groupForm.description" type="textarea" :rows="3" />
            </el-form-item>
          </div>
        </section>
        <section class="workbench-editor-section workbench-editor-section--tinted">
          <div class="workbench-editor-heading"><span class="workbench-editor-step">02</span><h3>角色与成员</h3></div>
          <div>
            <el-form-item label="角色">
              <el-select v-model="groupForm.role_ids" multiple filterable style="width:100%">
                <el-option v-for="role in assignmentOptions.roles" :key="role.id" :label="role.name" :value="role.id" />
              </el-select>
            </el-form-item>
            <el-form-item label="成员">
              <el-select v-model="groupForm.user_ids" multiple filterable remote :remote-method="fetchUserOptions" :loading="loading.userOptions" style="width:100%" placeholder="输入用户名搜索成员">
                <el-option v-for="user in userOptions" v-show="!memberSearch || user.username.toLowerCase().includes(memberSearch.toLowerCase())" :key="user.id" :label="user.username" :value="user.id" />
              </el-select>
            </el-form-item>
          </div>
        </section>
      </el-form>
      <template #footer>
        <el-button @click="groupDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving.group" @click="handleSaveGroup">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog top="5vh" :close-on-click-modal="false"
      v-model="passwordDialogVisible"
      title="重置密码"
      width="min(420px, 94vw)"
      destroy-on-close
      append-to-body
      class="workbench-edit-dialog password-reset-dialog"
    >
      <el-form ref="passwordFormRef" :rules="passwordRules" :disabled="saving.password" label-position="top" :model="passwordForm" label-width="90px" @submit.prevent>
        <el-form-item label="新密码" prop="password">
          <el-input v-model="passwordForm.password" type="password" show-password autocomplete="new-password" />
        </el-form-item>
        <p class="field-hint">重置后该用户需要重新登录。</p>
      </el-form>
      <template #footer>
        <el-button @click="passwordDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving.password" @click="handleResetPassword">确认</el-button>
      </template>
    </el-dialog>

    <el-dialog :model-value="!!permissionUser" @close="permissionUser = null" :title="`权限详情 · ${permissionUser?.username || ''}`" width="min(760px, 94vw)" class="workbench-edit-dialog" top="5vh" append-to-body destroy-on-close>
      <template v-if="permissionUser">
        <section class="workbench-editor-section">
          <div class="workbench-editor-heading"><h3>授权来源</h3></div>
          <p class="field-hint">{{ permissionUser.is_superuser ? '超级管理员拥有所有已启用功能的权限。' : '有效权限取直接角色与用户组角色的并集；K8s 还受集群范围约束。' }}</p>
          <div class="permission-tags"><el-tag v-for="role in permissionUser.roles" :key="role.id">角色 · {{ role.name }}</el-tag><el-tag v-for="group in permissionUser.user_groups" :key="group.id" type="info">用户组 · {{ group.name }}</el-tag></div>
        </section>
        <section class="workbench-editor-section workbench-editor-section--tinted">
          <div class="workbench-editor-heading"><h3>当前有效权限 · {{ permissionUser.effective_permissions.length }}</h3></div>
          <div v-if="permissionUser.effective_permissions.length" class="permission-code-list"><code v-for="code in permissionUser.effective_permissions" :key="code">{{ code }}</code></div>
          <el-empty v-else description="暂无有效权限" :image-size="56" />
        </section>
      </template>
      <template #footer><el-button @click="permissionUser = null">关闭</el-button></template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import K8sUserAccessDialog from '@/components/k8s/K8sUserAccessDialog.vue'
import { ElMessage } from 'element-plus'
import { Avatar, Grid, Plus, RefreshRight, User, UserFilled } from '@element-plus/icons-vue'
import {
  createGroup,
  createRole,
  createUser,
  deleteGroup,
  deleteRole,
  deleteUser,
  getGroups,
  getPermissions,
  getRoles,
  getUsers,
  getAssignmentOptions,
  getUserOptions,
  resetUserPassword,
  syncPermissions,
  updateGroup,
  updateRole,
  updateUser,
} from '@/api/modules/rbac'
import { useAuthStore } from '@/stores/auth'
import { useRouteTabState } from '@/composables/useRouteTabState'

const authStore = useAuthStore()
const router = useRouter()
const k8sAccessDialog = ref(null)
const permissionUser = ref(null)
const assignmentOptions = ref({ roles: [], groups: [], permissions: [] })
const userFormRef = ref(null)
const roleFormRef = ref(null)
const groupFormRef = ref(null)
const passwordFormRef = ref(null)
const required = message => ({ required: true, message, trigger: 'blur' })
const userRules = {
  username: [required('请输入用户名')],
  email: [{ type: 'email', message: '请输入有效邮箱', trigger: 'blur' }],
  password: [{ validator: (_rule, value, callback) => {
    if (!editingUserId.value && !value) return callback(new Error('请输入初始密码'))
    if (value && value.length < 8) return callback(new Error('密码至少 8 个字符'))
    callback()
  }, trigger: 'blur' }],
}
const roleRules = { code: [required('请输入角色编码')], name: [required('请输入角色名称')] }
const groupRules = { code: [required('请输入用户组编码')], name: [required('请输入用户组名称')] }
const passwordRules = { password: [required('请输入新密码'), { min: 8, message: '密码至少 8 个字符', trigger: 'blur' }] }

const canViewUsers = computed(() => authStore.hasPermission('rbac.user.view'))
const canManageUsers = computed(() => authStore.hasPermission('rbac.user.manage'))
const canViewRoles = computed(() => authStore.hasPermission('rbac.role.view'))
const canManageRoles = computed(() => authStore.hasPermission('rbac.role.manage'))
const canViewGroups = computed(() => authStore.hasPermission('rbac.group.view'))
const canManageGroups = computed(() => authStore.hasPermission('rbac.group.manage'))
const canViewPermissions = computed(() => authStore.hasPermission('rbac.permission.view'))
const canSync = computed(() => authStore.hasPermission('rbac.permission.sync'))

const availableTabs = computed(() => [
  canViewUsers.value && 'users',
  canViewGroups.value && 'groups',
  canViewRoles.value && 'roles',
  canViewPermissions.value && 'permissions',
].filter(Boolean))

const activeTabState = useRouteTabState({
  tabs: () => availableTabs.value,
  defaultTab: 'users',
})
const activeTab = activeTabState.activeTab
const switchTab = activeTabState.switchTab

const loading = ref({ users: false, roles: false, groups: false, permissions: false, userOptions: false })
const saving = ref({ user: false, role: false, group: false, password: false })

const users = ref([])
const userOptions = ref([])
const memberSearch = ref('')
const userSearch = ref('')
const userPage = ref(1)
const userTotal = ref(0)

const roles = ref([])
const roleSearch = ref('')

const groups = ref([])
const groupSearch = ref('')

const permissions = ref([])
const permissionSearch = ref('')
const filteredPermissions = ref([])

const userDialogVisible = ref(false)
const editingUserId = ref(null)
const userForm = ref({})

const roleDialogVisible = ref(false)
const editingRoleId = ref(null)
const roleForm = ref({})
const currentRoleBuiltin = computed(() => roles.value.find(item => item.id === editingRoleId.value)?.is_builtin || false)
const currentRoleReadOnly = computed(() => Boolean(!authStore.isPreview && editingRoleId.value && !roles.value.find(item => item.id === editingRoleId.value)?.can_manage))
const rolePermissionOptions = computed(() => currentRoleReadOnly.value
  ? roles.value.find(item => item.id === editingRoleId.value)?.permissions || []
  : assignmentOptions.value.permissions)

const groupDialogVisible = ref(false)
const editingGroupId = ref(null)
const groupForm = ref({})
const currentGroupBuiltin = computed(() => groups.value.find(item => item.id === editingGroupId.value)?.is_builtin || false)

const passwordDialogVisible = ref(false)
const passwordUserId = ref(null)
const passwordForm = ref({ password: '' })

const sectionTitle = computed(() => ({
  users: '用户列表',
  groups: '用户组列表',
  roles: '角色列表',
  permissions: '权限字典',
}[activeTab.value] || '用户管理'))

const sectionDesc = computed(() => ({
  users: '维护账号启停与授权，支持编辑、重置密码和删除操作。',
  groups: '维护用户组及成员映射，便于批量授权和治理。',
  roles: '维护角色及其权限集合，支持和内置权限同步。',
  permissions: '查看内置权限字典，辅助角色和用户组配置。',
}[activeTab.value] || '管理平台身份体系。'))

function formatTime(value) {
  return value ? new Date(value).toLocaleString('zh-CN') : '-'
}

function resetUserForm() {
  userForm.value = {
    username: '',
    email: '',
    first_name: '',
    last_name: '',
    password: '',
    is_active: true,
    role_ids: [],
    group_ids: [],
  }
}

function resetRoleForm() {
  roleForm.value = {
    code: '',
    name: '',
    description: '',
    permission_ids: [],
  }
}

function resetGroupForm() {
  groupForm.value = {
    code: '',
    name: '',
    description: '',
    role_ids: [],
    user_ids: [],
  }
}

let userRequest = 0
let searchTimer
function searchUsers() {
  userPage.value = 1
  clearTimeout(searchTimer)
  searchTimer = setTimeout(fetchUsers, 250)
}

async function fetchUsers() {
  if (!canViewUsers.value) return
  const requestId = ++userRequest
  loading.value.users = true
  try {
    const params = { page: userPage.value }
    if (userSearch.value) params.search = userSearch.value
    const res = await getUsers(params)
    if (requestId !== userRequest) return
    users.value = res.results || []
    userTotal.value = res.count || users.value.length
  } finally {
    if (requestId === userRequest) loading.value.users = false
  }
}

let optionsRequest = 0
async function fetchUserOptions(search = '') {
  if (!canManageGroups.value) return
  memberSearch.value = typeof search === 'string' ? search : ''
  const requestId = ++optionsRequest
  loading.value.userOptions = true
  try {
    const res = await getUserOptions({ page_size: 100, search: memberSearch.value })
    if (requestId !== optionsRequest) return
    const selected = userOptions.value.filter(user => groupForm.value.user_ids?.includes(user.id))
    userOptions.value = [...new Map([...selected, ...(res.results || [])].map(user => [user.id, user])).values()]
  } finally {
    if (requestId === optionsRequest) loading.value.userOptions = false
  }
}

async function fetchAssignmentOptions() {
  if (!canManageUsers.value && !canManageGroups.value && !canManageRoles.value) return
  assignmentOptions.value = await getAssignmentOptions()
}

async function fetchRoles() {
  if (!canViewRoles.value) return
  loading.value.roles = true
  try {
    const params = roleSearch.value ? { search: roleSearch.value } : {}
    roles.value = await getRoles(params)
  } finally {
    loading.value.roles = false
  }
}

async function fetchGroups() {
  if (!canViewGroups.value) return
  loading.value.groups = true
  try {
    const params = groupSearch.value ? { search: groupSearch.value } : {}
    groups.value = await getGroups(params)
  } finally {
    loading.value.groups = false
  }
}

async function fetchPermissions() {
  if (!canViewPermissions.value) return
  loading.value.permissions = true
  try {
    permissions.value = await getPermissions()
    applyPermissionFilter()
  } finally {
    loading.value.permissions = false
  }
}

function applyPermissionFilter() {
  const keyword = permissionSearch.value.trim().toLowerCase()
  filteredPermissions.value = permissions.value.filter((item) => {
    if (!keyword) return true
    return [item.name, item.code, item.description, item.category]
      .filter(Boolean)
      .some(value => value.toLowerCase().includes(keyword))
  })
}

async function openUserDialog(row) {
  if (!canManageUsers.value || (row && !row.can_manage && !authStore.isPreview)) return
  await fetchAssignmentOptions()
  resetUserForm()
  editingUserId.value = row?.id || null
  if (row) {
    userForm.value = {
      username: row.username,
      email: row.email,
      first_name: row.first_name || '',
      last_name: row.last_name || '',
      password: '',
      is_active: row.is_active,
      role_ids: row.roles.map(item => item.id),
      group_ids: row.user_groups.map(item => item.id),
    }
  }
  userDialogVisible.value = true
}

async function openRoleDialog(row) {
  if (row ? !canViewRoles.value : !canManageRoles.value) return
  if (!row || row.can_manage || authStore.isPreview) await fetchAssignmentOptions()
  resetRoleForm()
  editingRoleId.value = row?.id || null
  if (row) {
    roleForm.value = {
      code: row.code,
      name: row.name,
      description: row.description,
      permission_ids: row.permissions.map(item => item.id),
    }
  }
  roleDialogVisible.value = true
}

async function copyRole(row) {
  await openRoleDialog()
  const allowed = new Set(assignmentOptions.value.permissions.map(item => item.id))
  roleForm.value = { code: '', name: `${row.name}副本`, description: row.description,
    permission_ids: row.permissions.filter(item => allowed.has(item.id)).map(item => item.id) }
}

async function openGroupDialog(row) {
  if (!canManageGroups.value || (row && !row.can_manage && !authStore.isPreview)) return
  await fetchAssignmentOptions()
  resetGroupForm()
  editingGroupId.value = row?.id || null
  if (row) {
    groupForm.value = {
      code: row.code,
      name: row.name,
      description: row.description,
      role_ids: row.roles.map(item => item.id),
      user_ids: row.users.map(item => item.id),
    }
  }
  userOptions.value = row?.users || []
  await fetchUserOptions()
  groupDialogVisible.value = true
}

function openPasswordDialog(row) {
  if (!canManageUsers.value || (!row.can_manage && !authStore.isPreview)) return
  passwordUserId.value = row.id
  passwordForm.value = { password: '' }
  passwordDialogVisible.value = true
}

async function handleSaveUser() {
  if (saving.value.user || !canManageUsers.value || !await userFormRef.value?.validate().catch(() => false)) return
  saving.value.user = true
  try {
    const payload = { ...userForm.value }
    if (!payload.password) delete payload.password
    if (editingUserId.value) {
      await updateUser(editingUserId.value, payload)
      ElMessage.success('用户已更新')
    } else {
      await createUser(payload)
      ElMessage.success('用户已创建')
    }
    userDialogVisible.value = false
    if (editingUserId.value === authStore.currentUser?.id && payload.password) {
      authStore.clearSession()
      await router.replace('/login')
      return
    }
    await authStore.reloadProfile({ silent: true })
    await Promise.all([fetchUsers(), fetchUserOptions()])
  } finally {
    saving.value.user = false
  }
}

async function handleSaveRole() {
  if (saving.value.role || currentRoleReadOnly.value || !canManageRoles.value || !await roleFormRef.value?.validate().catch(() => false)) return
  saving.value.role = true
  try {
    if (editingRoleId.value) {
      await updateRole(editingRoleId.value, roleForm.value)
      ElMessage.success('角色已更新')
    } else {
      await createRole(roleForm.value)
      ElMessage.success('角色已创建')
    }
    roleDialogVisible.value = false
    await authStore.reloadProfile({ silent: true })
    await Promise.all([fetchRoles(), fetchUsers()])
  } finally {
    saving.value.role = false
  }
}

async function handleSaveGroup() {
  if (saving.value.group || !canManageGroups.value || !await groupFormRef.value?.validate().catch(() => false)) return
  saving.value.group = true
  try {
    if (editingGroupId.value) {
      await updateGroup(editingGroupId.value, groupForm.value)
      ElMessage.success('用户组已更新')
    } else {
      await createGroup(groupForm.value)
      ElMessage.success('用户组已创建')
    }
    groupDialogVisible.value = false
    await authStore.reloadProfile({ silent: true })
    await Promise.all([fetchGroups(), fetchUsers(), fetchUserOptions()])
  } finally {
    saving.value.group = false
  }
}

async function handleResetPassword() {
  if (saving.value.password || !canManageUsers.value || !await passwordFormRef.value?.validate().catch(() => false)) return
  saving.value.password = true
  try {
    await resetUserPassword(passwordUserId.value, passwordForm.value.password)
    ElMessage.success('密码已重置')
    passwordDialogVisible.value = false
    if (passwordUserId.value === authStore.currentUser?.id) {
      authStore.clearSession()
      await router.replace('/login')
    }
  } finally {
    saving.value.password = false
  }
}

async function handleDeleteUser(id) {
  await deleteUser(id)
  ElMessage.success('用户已删除')
  if (users.value.length === 1 && userPage.value > 1) userPage.value -= 1
  await Promise.all([fetchUsers(), fetchUserOptions()])
}

async function handleDeleteRole(id) {
  await deleteRole(id)
  ElMessage.success('角色已删除')
  await authStore.reloadProfile({ silent: true })
  await Promise.all([fetchRoles(), fetchUsers()])
}

async function handleDeleteGroup(id) {
  await deleteGroup(id)
  ElMessage.success('用户组已删除')
  await authStore.reloadProfile({ silent: true })
  await Promise.all([fetchGroups(), fetchUsers(), fetchUserOptions()])
}

async function handleSyncPermissions() {
  await syncPermissions()
  await authStore.reloadProfile({ silent: true })
  await Promise.all([fetchPermissions(), fetchRoles()])
  ElMessage.success('权限与内置角色已同步')
}

async function handleRefreshCurrentTab() {
  if (activeTab.value === 'users') {
    await fetchUsers()
    await fetchUserOptions()
  } else if (activeTab.value === 'roles') {
    await fetchRoles()
  } else if (activeTab.value === 'groups') {
    await fetchGroups()
  } else {
    await fetchPermissions()
  }
}

onMounted(async () => {
  const tasks = []
  if (canViewUsers.value) tasks.push(fetchUsers())
  if (canViewRoles.value) tasks.push(fetchRoles())
  if (canViewGroups.value) tasks.push(fetchGroups())
  if (canViewPermissions.value) tasks.push(fetchPermissions())
  await Promise.all(tasks)
})
onUnmounted(() => clearTimeout(searchTimer))
</script>

<style scoped>
.users-page {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.users-page.workbench-page-shell {
  gap: 6px;
}

.panel {
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 18px;
  box-shadow: 0 8px 24px rgba(15,23,42,.04);
  padding: 14px 16px;
}

.hero {
  margin-bottom: 0;
  background: linear-gradient(135deg, var(--el-bg-color) 0%, var(--el-fill-color-lighter) 100%);
  border-color: var(--el-border-color-lighter);
}

.release-hero-title-row {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.release-hero-title-row h2 {
  color: var(--el-text-color-primary);
  font-size: 23px;
  margin: 0;
}

.release-header-icon {
  width: 42px;
  height: 42px;
  border-radius: 14px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
  border: 1px solid var(--el-color-primary-light-8);
  box-shadow: inset 0 1px 0 rgba(255,255,255,.8);
}

.page-inline-desc {
  color: var(--text-secondary, var(--el-text-color-secondary));
  font-size: 13px;
  line-height: 1.45;
  margin: 0;
  flex: 0 1 auto;
}

.users-tabs {
  width: 100%;
  padding: 3px;
  gap: 8px;
  margin: 0;
  box-shadow: none;
  overflow-x: auto;
}

.users-tabs.theme-blue .neo-tab-btn.active {
  color: var(--el-color-primary);
  background: var(--el-color-primary-light-9) !important;
  box-shadow: inset 0 0 0 1px var(--el-color-primary-light-8) !important;
}

.users-tabs .neo-tab-btn {
  min-height: 38px;
  padding: 0 18px;
  font-size: 13px;
  font-weight: 700;
  line-height: 1.2;
  flex-shrink: 0;
}

.users-content-card {
  display: flex;
  flex-direction: column;
  min-width: 0;
  margin: 0;
}

.toolbar-head { display: inline-flex; align-items: baseline; gap: 8px; flex-wrap: wrap; }
.users-search { width: 260px; max-width: 100%; }
.field-hint { color: var(--text-secondary, var(--el-text-color-secondary)); font-size: 12px; line-height: 1.6; margin: 4px 0 0; }
.permission-tags { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px; }
.permission-code-list { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 6px 12px; }
.permission-code-list code { overflow-wrap: anywhere; color: var(--el-text-color-regular); font-size: 12px; }

.users-toolbar {
  margin-top: 0;
}

.tag-gap {
  margin-right: 6px;
}

.pagination-row {
  display: flex;
  justify-content: flex-end;
  margin-top: 8px;
}

:deep(.users-actions-column .cell) {
  display: flex;
  align-items: center;
  gap: 6px;
  white-space: nowrap;
}

:deep(.users-actions-column .el-button) {
  margin-left: 0;
  padding: 0;
}

@media (max-width: 900px) {
  .release-hero-title-row {
    align-items: flex-start;
  }
}

@media (max-width: 640px) {
  .section-toolbar { align-items: flex-start; flex-direction: column; gap: 8px; }
  .workbench-card-actions { flex-wrap: wrap; }
  .permission-code-list { grid-template-columns: 1fr; }
}

.hero.panel { border-radius: 20px; }
</style>
