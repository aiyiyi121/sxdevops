# UI Benchmarks

Use this file when you need the exact repo pattern to copy instead of inventing a new one.

## Primary Reference Pages

### `frontend/src/views/Deployments.vue`

Use this page as the main benchmark for:

- hero block
- top metric cards
- section toolbar
- bordered filter bar inside the content card
- compact list header actions
- page-level 6px vertical rhythm

Key patterns:

- `release-page workbench-page-shell`
- `hero panel`
- `release-hero-title-row release-hero-title-inline`
- `audit-grid`
- `audit-card audit-card--inline audit-card--action`
- `workbench-card`
- `section-toolbar`
- `workbench-toolbar workbench-toolbar--history`

Key values:

- page gap `6px`
- panel padding `14px 16px`
- hero radius `20px`
- hero icon `42px`
- stats card min-height `68px`
- stats grid gap `10px`

### `frontend/src/views/TaskWorkbench.vue`

Use this page as the benchmark for:

- task workbench hero style
- the exact hero tone you should keep for new console pages

Key patterns:

- `task-page-shell workbench-page-shell`
- `task-hero-panel`
- `release-hero-title-row`
- same hero border, radius, and spacing language as Deployments

### `frontend/src/components/cmdb/CmdbHostTaskCenter.vue`

Use this component as the benchmark for task-history-style content areas:

- inner tabs
- one-line stats cards
- task/history density
- compact toolbar rhythm
- compact table-driven control surfaces

Key patterns:

- `task-inner-tabs`
- `task-inner-tab-btn`
- `audit-grid task-source-grid`
- `task-source-card`
- `history-card`
- `.toolbar`, `.toolbar-left`, `.toolbar-right`

Key values:

- inner tab shell padding `3px`
- inner tab shell gap `8px`
- inner tab height `38px`
- inner tab padding `0 18px`
- inner tab border radius `8px`
- inner tab text `13px` / `700`
- inner tab icon size `15px`
- active inner tab background `#e8f0ff`, text `#245bdb`, inset pale blue border
- history stats grid `repeat(4, minmax(0, 1fr))`
- one-line stats cards with label left / value right
- card min-height `68px`

### `frontend/src/views/SqlAudit.vue`

Use this page when the stats cards need to drive tab switching or filtering.

Key patterns:

- `.sql-audit-overview .audit-card--action`
- active card outer ring and pale blue background

Use this page to copy the interaction feel of clickable stats cards.

## Secondary Reference Pages

### `frontend/src/views/K8sManage.vue`

Use this page for:

- infrastructure management page structure
- main tabs shell
- context selector placement
- right-aligned environment / namespace selectors

### `frontend/src/views/ContainerManage.vue`

Use this page for:

- Docker page structure aligned to K8s
- host / cluster style context selector dropdowns
- disconnected empty-state pattern

## Default Adoption Rules

- New management pages should look like a close sibling of Deployments or TaskWorkbench history, not a new visual system.
- If the page is list-heavy, start from Deployments.
- If the page is task- or history-heavy, start from TaskWorkbench + CmdbHostTaskCenter.
- If stats cards control state, borrow the SqlAudit card interaction pattern.
- If the page manages cluster, namespace, host, or environment context, borrow K8s/ContainerManage selector placement.

## Explicit Do Nots

- Do not use the old `page-header`.
- Do not put action buttons in the hero unless the user asks.
- Do not add platform reminder bars by default.
- Do not duplicate stats inside lower cards when top stats already exist.
- Do not split filter area and list into unrelated stacked cards when one workbench card is enough.
