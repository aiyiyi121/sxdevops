# RBAC Patterns

Use these repo patterns as the default reference when wiring permissions.

## Permission Namespaces In This Repo

- `ops.*` for host, task, deployment, docker, k8s, logs, observability, and alert features
- `cmdb.*` for CMDB resources, topology, cost, and requests
- `sqlaudit.*` for SQL audit data sources, orders, and queries
- `aiops.*` for AI assistant, knowledge, config, audit, and task generation
- `eventwall.*` for event wall and event source management
- `rbac.*` for user, role, group, permission, and audit administration

## Existing Permission Shapes

- `ops.host.view`, `ops.host.manage`, `ops.host.terminal`, `ops.host.execute`
- `ops.task.execute`, `ops.task.resource.view`, `ops.task.resource.manage`
- `ops.deployment.view`, `ops.deployment.manage`, `ops.deployment.approve`
- `ops.k8s.view`, `ops.k8s.manage`, `ops.k8s.exec`
- `ops.docker.view`, `ops.docker.manage`
- `ops.log.query`, `ops.log.datasource.view`, `ops.log.datasource.manage`
- `ops.observability.system_posture.view`, `ops.observability.system_posture.manage`
- `sqlaudit.datasource.view`, `sqlaudit.datasource.manage`
- `sqlaudit.order.view`, `sqlaudit.order.submit`, `sqlaudit.order.review`, `sqlaudit.order.execute`
- `sqlaudit.query.view`, `sqlaudit.query.execute`
- `aiops.chat.view`, `aiops.chat.analyze`, `aiops.task.generate`, `aiops.task.execute`
- `aiops.config.view`, `aiops.config.manage`
- `eventwall.view`, `eventwall.source.view`, `eventwall.source.manage`

## Backend Entry Points To Inspect

- `backend/rbac/registry.py` for permission definitions and built-in role bundles
- `backend/rbac/permissions.py` for `RBACPermissionMixin` and `build_rbac_permission`
- `backend/ops/views.py` for host, task, deployment, ticket, and alert examples
- `backend/ops/docker_views.py` for Docker-specific permission mapping
- `backend/ops/k8s_views.py` for K8s viewset gating
- `backend/sqlaudit/views.py` for order and query actions
- `backend/aiops/views.py` for assistant and config gating
- `backend/ops/ssh_consumer.py` for token-authenticated WebSocket permission checks

## Frontend Entry Points To Inspect

- `frontend/src/router/index.js` for `meta.permission` and `meta.anyPermissions`
- `frontend/src/layout/AppLayout.vue` for menu visibility checks
- `frontend/src/stores/auth.js` for `hasPermission` and `hasAnyPermission`
- `frontend/src/utils/permission.js` for helper wrappers
- `frontend/src/views/Users.vue` for user, role, and group surfaces

## Practical Rules

- If the action mutates state, enforce backend permission first.
- If the action is a page entry, add a matching route guard.
- If the action is a menu item, mirror the same permission in the sidebar.
- If the action is sensitive or write-heavy, consider operation audit hooks.
- If a built-in role should see it by default, update `BUILTIN_ROLES` alongside the permission definition.
