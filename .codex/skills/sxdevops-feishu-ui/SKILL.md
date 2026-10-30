---
name: sxdevops-feishu-ui
description: Use for new frontend pages, UI adjustments, and add/edit dialogs in this repository unless the user requests another style. Applies the Feishu minimal premium workbench style, the model-provider editor dialog pattern, and compatibility with light, charcoal, and blue-gray themes.
---

# SXDevOps Feishu UI

## Use When

- Building a new page under `frontend/src/views/`.
- Restyling or aligning an existing frontend page, embedded management panel, or console view.
- The user asks to "对齐 UI", "优化页面样式", "按当前项目风格来", or similar.
- The user does not explicitly ask for a different visual direction.

If the user explicitly asks for another style, follow the user.

## Source Of Truth

Use these pages before introducing any new UI pattern:

1. `frontend/src/views/Deployments.vue`
2. `frontend/src/views/TaskWorkbench.vue`
3. `frontend/src/components/cmdb/CmdbHostTaskCenter.vue`
4. `frontend/src/views/SqlAudit.vue`
5. `frontend/src/views/K8sManage.vue`
6. `frontend/src/views/ContainerManage.vue`

Read `references/ui-benchmarks.md` when you need the exact class patterns and spacing values.

For add/edit dialogs, use `frontend/src/components/aiops/ModelProviderDialog.vue` as the visual reference and read `references/dialog-editors.md`. Shared shell and section styles live in `frontend/src/assets/dialog-editor.css`.

## Default Style

- Overall tone: Feishu-like minimal premium workbench UI.
- Use theme-aware layered surfaces, restrained blue emphasis, soft borders, and low-noise shadows. Light uses white surfaces; both dark themes use their existing palettes.
- Prefer existing repo structures over inventing a new composition.
- Use `workbench-page-shell` for full pages when the page is console or management oriented.
- Do not use the old `page-header` pattern for new or restyled pages.
- Do not add hero buttons unless the user explicitly asks.
- Do not keep platform reminder strips by default.
- Do not duplicate stats inside list cards when the page already has a top stats row.
- Keep actions on the same row as the list title, not inside the hero.

## Three Color Themes — All UI

- **全站所有新增或修改的 UI 都必须适配浅色 (`light`)、炭灰 (`charcoal`)、深蓝灰 (`dark`)，不限于弹窗。** This applies equally when the user requests another visual style; theme compatibility is a separate requirement.
- Scope includes page backgrounds, sidebar/navigation, hero blocks, tabs, metric cards, toolbars, tables/lists, detail pages, forms, dialogs/drawers, menus, tooltips, notifications, empty/loading/error states, charts, topology diagrams, SVG icons, and code/log viewers.
- Actual theme state is `html[data-theme]`; both dark themes also have `html.dark`. Follow `frontend/src/theme/index.js`, `frontend/src/theme/palette.js`, and `frontend/src/assets/theme.css`. Do not treat `dark` as the only dark theme.
- Use shared theme tokens for surfaces, text, borders, emphasis, and statuses. Use `--text-secondary` for readable hints and existing Element Plus tokens for controls and states. The fixed colors in the layout benchmarks below describe the light appearance; reuse their themed implementation or provide equivalent theme-aware colors instead of applying the light colors unchanged to all themes.
- Check the entire affected UI in all three themes: layered backgrounds, body/secondary text, icons, links, placeholders, disabled controls, hover/focus/selected/error states, table headers/striping/fixed columns, chart labels/axes/legends/tooltips, and teleported content must remain distinguishable and readable. Preserve status meanings with text or icons as well as color.
- CSS color conversion does not cover every runtime color. For ECharts use the shared `frontend/src/lib/echarts.js` adapter. For inline styles, custom SVG/canvas, or other runtime-rendered visuals, reuse `resolveThemeColor` / `themePalette` where appropriate and respond to theme changes without requiring a reload. Inspect embedded HTML tooltips and image assets separately; never invert all images globally.
- Verify the actual affected page/components in a browser under each theme and switch between them to check existing rendered content updates. Restore the user's original theme afterward; UI work must not reset the saved theme preference or change the default light theme.

## Layout Rules

### Hero

- Use a top `hero panel`.
- Keep one title row: icon + `h2` + concise inline subtitle.
- Put the hero subtitle/description to the right of the title in the same row, using the `page-inline-desc` style from `AIOpsConfig.vue`; do not stack the description under the title on desktop.
- Reuse the same visual language as `Deployments.vue` and `TaskWorkbench.vue`:
  - panel padding `14px 16px`
  - hero radius follows `Deployments.vue`: component-local `.hero.panel { border-radius: 20px; }`
  - hero gradient `linear-gradient(135deg, #fbfdff 0%, #f7faff 52%, #f9fbfd 100%)`
  - hero border color `rgba(36,91,219,.09)`
  - header icon `42px * 42px`, pale blue background, blue foreground
- Hero bottom margin stays at `0`.
- For management pages that use top metrics, keep the page order as `hero -> stats cards -> tabs (if any) -> list/content`.
- Do not add stronger page-specific selectors such as `section.hero.panel... !important` for hero radius unless the benchmark page already does it; match the application release page's cascade and selector shape.
- If a page defines a generic `.panel` radius, still add the same final `.hero.panel { border-radius: 20px; }` rule used by `Deployments.vue`.

### Tabs

- Main tabs use the repo's blue pill workbench style.
- Prefer the button-based `neo-tabs theme-blue` pattern used by `frontend/src/components/cmdb/CmdbHostTaskCenter.vue`.
- Do not use Element Plus `el-tabs` for top-level workbench tabs unless the page needs native tab-pane behavior; if `el-tabs` is used, override it to visually match the same button dimensions below.
- Outer tabs shell:
  - `display: flex`
  - `width: 100%`
  - padding `3px`
  - gap `8px`
  - border radius `12px`
  - soft gray border
  - subtle workbench shadow `0 12px 26px rgba(15, 23, 42, 0.04)`
- Main tab button:
  - `min-height: 38px`
  - horizontal padding `0 18px`
  - border radius `8px`
  - icon size `15px`
  - gap `6px`
  - `13px` / `700` text, `line-height: 1.2`
  - translucent blue active state
- Secondary tabs should sit directly above the filter area with a tighter gap than a normal section break.
- Keep the tabs shell immediately below the stats row when both are present, not above it.
- Hard rule: the rendered vertical gap immediately above a top-level tabs shell and the rendered gap immediately below it must be exactly equal. The default is `6px` above and `6px` below, both produced by the same page-root `gap: 6px`.
- Do not use a tabs-specific non-zero `margin-top`, `margin-bottom`, negative margin, spacer, wrapper padding, or sibling offset to change only one side of the tabs. Because the global `.neo-tabs` rule currently contributes `margin-bottom: 8px`, every page using root-gap spacing must explicitly reset the top-level tabs and adjacent primary content margins to `0`; the page-root gap must be the single source of truth.
- Judge equality from a browser screenshot, including shadows. A downward tabs shadow that makes the lower gap look larger must be reduced or removed even when the box-model gaps are equal.
- Before finishing, inspect the rendered rectangles/computed styles and verify `tabs.top - previous.bottom === next.top - tabs.bottom === 6px`; checking only the authored `gap` declaration is insufficient.
- When a page has no metric row, use the order `hero -> tabs -> primary content` with the same compact rhythm. Do not preserve an empty stats slot or spacer after removing metrics.
- Active tabs should use `#e8f0ff` or `rgba(51, 112, 255, 0.1)` with `#245bdb` text and an inset pale blue border; do not use the global solid/gradient blue active style on workbench management pages.

### Stats Cards

- Default to `audit-grid`.
- Default metric card shape:
  - `audit-card audit-card--inline`
  - min-height `68px`
  - padding `14px 16px`
  - radius `14px`
  - soft border and subtle shadow
- Use clickable cards (`audit-card--action`) when cards switch tab, filter, or list state.
- Use tone variants only when they carry meaning:
  - base
  - `audit-card--success`
  - `audit-card--warning`
  - `audit-card--danger`
- Standard typography:
  - label `13px`, semibold
  - value `24px`
- If the page matches task history style, the card can place label and value on one row, but it must keep the same height, border, shadow, and active state language.

### List And Content Card

- List-driven pages should use one `workbench-card` to wrap title, filter bar, and table.
- Header row uses:
  - `section-toolbar`
  - `toolbar-head`
  - `toolbar-title`
  - `toolbar-desc`
- In `toolbar-head`, keep `toolbar-title` and `toolbar-desc` on the same baseline row with `inline-flex`, a small gap, and wrapping only when width is constrained; avoid putting the description as a second line on desktop.
- Filter row uses:
  - `workbench-toolbar workbench-toolbar--history`
- Keep filter bar visually inside the card with its own outer border treatment.
- Prefer one list card instead of a separate filter card plus another list card.
- On desktop, keep dense filter rows in a single line when the page's normal working width allows it; prefer narrower controls and horizontal overflow over wrapping to a second line.
- For module visibility or feature-switch management pages, keep the page as `hero -> single workbench-card -> table/list`; do not add stats cards unless the user asks. Required rows should use disabled switches plus a compact "required" tag, while configurable rows use the actual switch control.

### Buttons

- Keep buttons compact.
- Primary buttons are for create, confirm, or high-priority actions only.
- Refresh and secondary actions should use the lighter workbench button treatment.
- Buttons belong in section headers or filter rows, not the hero.

### Dialogs

- For Element Plus dialogs opened from management pages, especially create, edit, detail, and reset-password dialogs, set `append-to-body` by default so the modal is not clipped by nested cards, scroll containers, drawers, or page sub-windows.
- Add/edit forms default to the model-provider editor UI: `class="workbench-edit-dialog"`, `top="5vh"`, top-aligned labels, semantic sections, restrained tinted cards, a scrolling body, and footer actions outside the scrolling body. Read `references/dialog-editors.md` for the reusable markup and interaction requirements.
- Keep width appropriate to content: compact forms around 420–620px, normal forms 720–940px, always constrained to the viewport. Use two columns only where the fields fit; collapse to one column on narrow screens.
- Keep required fields visible; fold only optional advanced settings. Do not change existing validation, conditional fields, save events, permissions, or credential preservation while restyling.
- Keep terminals, log/detail viewers, topology canvases, and destructive confirmations in layouts suited to their purpose; the editor class is opt-in.

### Tables

- Use Element Plus tables with restrained density.
- Keep header tone soft and readable.
- Avoid oversized row padding.
- Match the information density of TaskWorkbench history and Deployments instead of older spacious pages.

### Vertical Rhythm

- Page root vertical gap: `6px`.
- Stats row and tabs block should not introduce extra top or bottom margins.
- Section title row to filter row spacing should stay tight.
- Use the TaskWorkbench history / Deployments rhythm as the default baseline for new pages.
- Avoid adding extra vertical wrappers between hero, stats, tabs, and the content card unless the page absolutely needs them.

## Execution Checklist

1. Open the benchmark pages before making layout decisions.
2. Reuse repo class names and structural patterns where possible.
3. Align hero, tabs, stats cards, filter bar, list card, buttons, and spacing to the benchmark pages.
4. Remove redundant reminders or duplicated stats unless the user asks to preserve them.
5. Run `cd frontend && npm run build`.
6. For pages with top-level tabs, verify the computed gaps above and below the tabs are both `6px` and visually equal in a browser screenshot.
7. If Chinese copy changed, confirm the file is still UTF-8 and readable.
8. For every UI change, inspect the affected page/components and interaction states in all three themes, including charts and teleported content when present. Verify live theme switching and restore the original selection.
9. For editor dialogs, also verify scrolling, footer visibility, validation, and narrow-screen layout. See `references/dialog-editors.md` for dialog-specific checks.

## References

- `references/ui-benchmarks.md`
- `references/dialog-editors.md`
