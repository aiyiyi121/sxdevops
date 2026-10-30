# Add / Edit Dialogs

The model-provider editor is the default visual pattern for editable modal forms. Start from `frontend/src/components/aiops/ModelProviderDialog.vue`; use `frontend/src/components/aiops/AgentAssetDialog.vue` when its form ownership and save/invalid events fit an AIOps asset editor. Other pages can retain their own forms, refs, rules, and handlers while sharing the opt-in CSS in `frontend/src/assets/dialog-editor.css` (loaded once in `main.js`).

## Shell and Fields

```vue
<el-dialog
  v-model="dialogVisible"
  :title="editingId ? '编辑连接' : '新增连接'"
  class="workbench-edit-dialog"
  width="min(760px, 94vw)"
  top="5vh"
  append-to-body
  destroy-on-close
  :close-on-click-modal="false"
>
  <el-form ref="formRef" :model="form" :rules="rules" label-position="top">
    <section class="workbench-editor-section">
      <div class="workbench-editor-heading">
        <span class="workbench-editor-step">01</span><h3>基础信息</h3>
      </div>
      <div class="workbench-editor-grid">
        <el-form-item label="名称" prop="name"><el-input v-model="form.name" /></el-form-item>
        <el-form-item label="类型" prop="type"><el-select v-model="form.type"><!-- options --></el-select></el-form-item>
        <el-form-item label="连接地址" prop="endpoint" class="workbench-editor-full">
          <el-input v-model="form.endpoint" />
        </el-form-item>
      </div>
    </section>
    <!-- Additional groups use sequential numbers and descriptive domain titles. -->
  </el-form>
  <template #footer>
    <el-button @click="dialogVisible = false">取消</el-button>
    <el-button type="primary" :loading="saving" @click="save">保存配置</el-button>
  </template>
</el-dialog>
```

- The shared shell supplies a 16px radius, 20px/24px padding (16px on narrow screens), a body that shrinks and scrolls within 90dvh, and a separated footer that stays visible. Do not copy competing body-height/padding rules into each page. The older global `.el-dialog` margin and body padding use `!important`; the opt-in shell already handles that conflict.
- Group related fields by purpose: account information, connection/authentication, resource scope, or execution policy. Use `workbench-editor-section--tinted` for secondary groups. Number groups from 01 in their displayed order. Tiny forms with one to three fields can omit group headings.
- `workbench-editor-grid` uses two equal columns with a 16px gutter and becomes one column at 640px. `workbench-editor-full` spans the row. Long URLs, scripts, descriptions, permission pickers, and dynamic condition builders should use the full row when space is limited. Preserve conditional chains inside one group.
- When an existing form root is itself a grid, add `workbench-editor-form--sectioned` to that root before inserting section wrappers; put the grid on each section's contents. Otherwise sections can become accidental half-width grid cells.
- Labels use 12px semibold text and a 6px gap to the control. Keep hints adjacent to the field and errors visible without colliding with the next row. Preserve meaningful units alongside numeric inputs.
- Use `el-collapse` with `workbench-editor-advanced` for optional advanced settings. Keep required fields and common switches visible. If validation can fail inside a collapsed section, expand it before scrolling to the invalid field.
- A footer hint such as “保存后生效” is appropriate only when that is the actual save behavior. Keep action labels accurate for drafts, submissions, approvals, and immediate execution.

## Interaction Preservation

Keep existing payloads, validation rules, conditional branches, disabled builtin fields, credential placeholders, and RBAC gates. Styling does not authorize rewriting any of them. Retain cancel/close behavior; for new complex editors follow the model-provider dirty-close confirmation and loading behavior. Prevent duplicate submits during saving. Do not introduce implicit connection requests when merely opening an editor.

Use `append-to-body` so forms escape nested scrolling cards. Keep footer buttons in `#footer`, outside the body. Avoid a second nested scroll container unless needed for a code editor or table. A long form must remain usable on a short viewport as well as a phone.

## Theme Tokens

The skill's **Three Color Themes — All UI** requirement applies to the entire frontend. This section only adds dialog-specific implementation details; it does not limit theme adaptation to dialogs.

The platform has three themes: `light` (浅色), `charcoal` (炭灰), and `dark` (深蓝灰). `html.dark` is present for both dark themes; use `html[data-theme="charcoal"]` only when a palette-specific difference is necessary. Do not treat `dark` as the sole dark mode.

| Purpose | Preferred tokens |
| --- | --- |
| Dialog and primary surface | `--el-bg-color`, `--el-fill-color-blank` |
| Secondary cards | `--el-fill-color-lighter` |
| Heading / field label | `--el-text-color-primary`, `--el-text-color-regular` |
| Hint / auxiliary text | `--text-secondary` with an Element Plus fallback |
| Border / separator | `--el-border-color-light`, `--el-border-color-lighter` |
| Step badge / selected emphasis | `--el-color-primary`, `--el-color-primary-light-9` |
| Error / warning / success | Corresponding Element Plus status tokens |

Reuse existing Element Plus themed controls. Do not erase their disabled, hover, focus, or error distinction. Teleported selects, date pickers, tooltips, upload previews, password icons, JSON editors, empty states, and collapsed summaries must also be readable. The build's legacy-color transformation is a compatibility fallback; use tokens directly in new code.

## Verification

- Run `npm run build` from `frontend/` and scan touched Chinese source files for invalid UTF-8, replacement characters, and mojibake.
- In a real browser inspect representative small, long, and dynamic forms in all three themes. Include a teleported dropdown, disabled/builtin field, and a validation error where available.
- Check a desktop viewport and a narrow viewport near 390px: no page/modal horizontal overflow, labels wrap, grouped fields become one column, and the footer remains visible while only the body scrolls.
- Check cancel/close and existing field validation without writing real credentials or creating production records for a visual check. Restore the user's original theme and reset temporary viewport overrides.
