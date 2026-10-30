---
name: sxdevops-rbac-feature-integration
description: Use when adding or changing any SXDevOps feature that needs permission codes, backend enforcement, route guards, menu visibility, page action gating, WebSocket access, or built-in role updates.
---

# SXDevOps RBAC Integration

## When To Use

- New backend APIs, viewsets, custom actions, or approval / execute flows.
- New frontend routes, menu entries, buttons, dialogs, or operation columns.
- Any WebSocket or other non-HTTP entry point.
- Any feature that needs a permission code or built-in role update.

## Default Rule

1. Enforce on the backend first.
2. Mirror the same permission on the frontend.
3. Update built-in roles only when the feature should be pre-granted.
4. Add audit hooks for write or execute actions when they matter operationally.

## Canonical Files

- `backend/rbac/registry.py`
- `backend/rbac/permissions.py`
- `backend/rbac/views.py`
- `frontend/src/router/index.js`
- `frontend/src/layout/AppLayout.vue`
- `frontend/src/stores/auth.js`
- `frontend/src/utils/permission.js`
- `backend/ops/ssh_consumer.py`
- `frontend/src/views/Users.vue`

## Workflow

### 1. Register The Permission

- Add a module-scoped code in `backend/rbac/registry.py`.
- Prefer namespaces that already exist in this repo, such as `ops.*`, `cmdb.*`, `sqlaudit.*`, `aiops.*`, and `eventwall.*`.
- Prefer suffixes like `view`, `manage`, `submit`, `review`, `approve`, `execute`, `query`, and `terminal`.
- Update `BUILTIN_ROLES` only when a built-in role should inherit the new access.

### 2. Protect The Backend

- Use `RBACPermissionMixin` for viewsets.
- Map every action explicitly in `rbac_permissions`.
- Use `build_rbac_permission(...)` for function views.
- For WebSocket or other non-HTTP entry points, authenticate the token and call `user_has_permissions(...)` before accepting.

### 3. Keep Audit Fields Server-Side

- Write `submitter`, `reviewer`, `deployer`, `applicant`, and similar fields from `request.user.username`.
- Do not trust the frontend for identity-sensitive audit fields.

### 4. Wire The Frontend

- Add `meta.permission` for a single gate.
- Add `meta.anyPermissions` when one page has multiple permission slices.
- Hide menu entries and buttons with `hasPermission(...)` or `hasAnyPermission(...)`.
- Keep route and menu gating in sync.

### 5. Add Audit Hooks When Needed

- Prefer `EventWallModelViewSetMixin` for CRUD resources that should emit audit events.
- Use `record_event(...)` for custom actions with meaningful state changes.
- Never place raw passwords, tokens, kubeconfig, or certificate bodies into audit payloads.

## Validation

- `cd backend && python manage.py test`
- `cd frontend && npm run build`

## Reference

See `references/rbac-patterns.md` for repo-specific examples and permission naming patterns.
