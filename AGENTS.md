# Repository Guidelines

## Project Structure & Module Organization
This repo is split into `backend/` and `frontend/`. `backend/` is a Django project with shared settings in `backend/sxdevops/` and domain apps in `backend/ops/`, `backend/cmdb/`, `backend/marketplace/`, and `backend/sqlaudit/`. `frontend/src/` contains the Vue app: page views in `frontend/src/views/`, shared layout in `frontend/src/layout/`, API wrappers in `frontend/src/api/`, router config in `frontend/src/router/`, and Pinia stores in `frontend/src/stores/`. Reference docs belong in `docs/`. Treat `frontend/dist/`, `frontend/node_modules/`, `backend/__pycache__/`, and `db.sqlite3` as generated artifacts.

## Build, Test, and Development Commands
- `cd backend && pip install -r requirements.txt` installs Python dependencies.
- `cd backend && python manage.py migrate` applies local database migrations.
- `cd backend && python manage.py seed_data` loads demo data for dashboards and CRUD pages.
- `cd backend && python -m daphne -b 0.0.0.0 -p 8000 sxdevops.asgi:application` runs the ASGI backend with WebSocket support.
- `cd backend && python manage.py test` runs Django test suites in each app's `tests.py`.
- `cd frontend && npm install` installs the Vite/Vue toolchain.
- `cd frontend && npm run dev` starts the UI on `http://localhost:3000`.
- `cd frontend && npm run build` creates a production bundle; use `npm run preview` for a local smoke test.

## Coding Style & Naming Conventions
Follow existing conventions: Python uses 4-space indentation, snake_case modules, and app-local helpers. Vue components in `frontend/src/views/` and `frontend/src/layout/` use PascalCase filenames such as `NginxManage.vue`; API and store modules use lower-case filenames such as `request.js` and `app.js`. No formatter or linter is committed, so match the surrounding file and remove unused imports.

## Frontend Page Header Convention
For new management or console-style pages, default to the same top structure already used by `MultiCloudManage`, `Deployments`, `MiddlewareManage`, `NginxManage`, `K8sManage`, and `ContainerManage`:

- Use a top `hero` section with the main title on the first row only.
- Do not add a second explanatory text row under the title unless the user explicitly asks for it.
- Follow the `hero + stats cards + compact alert strip + tabs/content` pattern.
- Reuse the `release-stat-card` visual style for the top metric cards instead of older icon-box summary cards.
- Keep a compact runtime hint strip near the top when the page has operational hints, warnings, or current-context reminders.
- If the page has context filters such as environment, cluster, namespace, or domain, place them in a compact toolbar below the tabs or in the top control area, not in an old-style `page-header`.

## Frontend UI Skill Default
- For any new frontend page or UI adjustment in this repo, default to the project skill at `.codex/skills/sxdevops-feishu-ui/SKILL.md` unless the user explicitly asks for a different style.
- The default style is Feishu minimal premium workbench UI.
- Primary source pages are `frontend/src/views/TaskWorkbench.vue`, `frontend/src/components/cmdb/CmdbHostTaskCenter.vue`, and `frontend/src/views/Deployments.vue`.
- Align hero, tabs, stats cards, list card, buttons, filter bar, and page vertical spacing to those source pages.
- Default vertical rhythm is the compact workbench rhythm used by task history and Deployments.
- Do not add hero buttons, platform reminder strips, old `page-header` blocks, or duplicated inner stats unless the user explicitly asks.

## RBAC Skill Default
- For any feature that adds or changes permissions, route guards, menu visibility, page actions, or WebSocket access, default to `.codex/skills/sxdevops-rbac-feature-integration/SKILL.md`.
- Use the repo's existing `backend/rbac/*`, `frontend/src/router/index.js`, `frontend/src/layout/AppLayout.vue`, and `frontend/src/stores/auth.js` patterns as the first reference.
- Backend RBAC enforcement comes first; frontend hiding is a mirror, not a substitute.

## Chinese Encoding Guardrails
- Any source file that contains Chinese text must be saved as `UTF-8`.
- Do not round-trip source text through `GBK`, `ANSI`, or editor auto-detected legacy encodings.
- Preserve readable Chinese in comments, labels, tooltips, alerts, backend responses, and operation logs.
- If a task touches Chinese text, run a quick mojibake scan before finishing and also check for any replacement-character artifacts.
- Do not paste terminal output back into source files when terminal encoding is uncertain. Prefer direct file edits and then reopen the file to verify the saved text.
- For UI or API changes involving Chinese, validate the affected page or build output and fix any newly introduced mojibake before closing the task.

## Testing Guidelines
Backend tests use Django's built-in `TestCase`; add coverage in the nearest app-level `tests.py` or a `test_*.py` module. Name tests by behavior, for example `test_refresh_info_marks_host_offline_on_ssh_failure`. Frontend has no automated test suite yet, so every UI change should at minimum pass `npm run build` and a manual browser check.

## Commit & Pull Request Guidelines
Use the commit style already in history: `feat: ...`, `feat(scope): ...`, `style(scope): ...`, `docs: ...`. Keep subjects imperative and scoped to one change. PRs should describe the user-visible impact, list touched areas, include validation steps, and attach screenshots for UI updates.

## README Screenshot Workflow
When the user asks to update `README.md` for product presentation, treat README updates as including screenshot refresh by default unless the user explicitly says text-only.

- Capture real product screenshots from the running demo instead of using placeholders when the demo is available.
- Prefer the four README showcase pages already used in this repo: dashboard, CMDB, logs, and IaC orchestration.
- Save screenshot assets under `docs/screenshots/` and keep README image references aligned with the latest `.png` files.
- For README-facing screenshots, add lightweight presentation polish when helpful, such as consistent framing, title bars, and highlight annotations for key areas.
- After replacing screenshots, also update `docs/screenshots/README.md` if the asset format, naming, or usage notes change.
- If a page needs live data to look complete, use the local demo account and trigger a representative query or action before capturing the screenshot.

## Security & Configuration Tips
`backend/sxdevops/settings.py` is configured for local development (`DEBUG = True`, open CORS, SQLite). Do not commit production secrets, real credentials, or environment-specific hostnames. If you change backend Python code while using Daphne, restart the server manually because hot reload is not enabled.
