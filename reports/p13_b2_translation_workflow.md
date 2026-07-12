# P13-B2 翻译工作流 (Translation Workflow)

> **Task**: P13-B2 (i18n key 扩展 66 → 200+)
> **Date**: 2026-06-26
> **Author**: coder agent (P13-B2 sub-session)
> **Applies to**: `frontend-v2/src/locales/{zh-CN,en-US}.ts`

---

## 1. 目标

为智影 (ZhiYing) 平台建立可持续的 i18n 翻译工作流,涵盖:

1. **共享 key 池**:5 个全局 namespace (common / menu / button / form / table) 各 200+ keys,所有 view 共享
2. **业务 key 池**:每个 view 自己的 namespace (dashboard / annotation / billing / workflows / engines / …)
3. **辅助工具**:`scripts/extract_i18n_keys.py` 自动扫描 t() 覆盖率、缺失 key、硬编码中文字符串
4. **同步规则**:zh-CN ↔ en-US 必须保持 key set 100% 对齐

---

## 2. 当前 namespace 架构

### 2.1 5 个全局共享 namespace (P13-B2 新增 / 扩展)

| Namespace | zh 键数 | en 键数 | 用途 | 共享给 |
|---|---|---|---|---|
| `common`   | 384 | 384 | 全局 UI 文本(状态/时间/单位/操作/确认消息) | 所有 view |
| `menu`     | 310 | 310 | 侧边栏/面包屑/标签页/上下文菜单/快捷操作 | 所有 view |
| `button`   | 434 | 434 | 按钮标签(CRUD/文件/搜索/状态/工作流/账户/计费) | 所有 view |
| `form`     | 306 | 306 | 表单字段名/占位符/校验消息/文件上传/富文本 | 所有 form |
| `table`    | 306 | 306 | 表格列头/排序/过滤/分页/分密度/行操作 | 所有 DataTable |
| **合计**   | **1740** | **1740** | — | — |

> **设计原则**:这些 namespace 提供"原子级"复用 key,新 view 不再需要重复定义 `confirm` / `cancel` / `colId` / `colName` 等公共字符串。

### 2.2 14 个业务 namespace (P6-Fix-B-4 / P8-1 已存在,保留不变)

| Namespace | zh 键数 | en 键数 | 对应 view |
|---|---|---|---|
| `nav` | 19 | 19 | DefaultLayout (顶层路由) |
| `auth` | 10 | 10 | Login |
| `dashboard` | 16 | 16 | Dashboard |
| `annotation` | 34 | 34 | Annotation |
| `billing` | 25 | 25 | Billing |
| `workflows` | 25 | 25 | Workflows |
| `engines` | 28 | 28 | Engines |
| `userManagement` | 34 | 34 | UserManagement |
| `agentManagement` | 9 | 9 | AgentManagement |
| `assetManagement` | 13 | 13 | AssetManagement |
| `annotationManagement` | 5 | 5 | AnnotationManagement |
| `marketplace` | 6 | 6 | Marketplace |
| `agentChat` | 5 | 5 | MultimodalChat |
| **合计** | **229** | **229** | — |

**总 locale 键数**:1969 keys × 2 locales = **3938 翻译条目**

---

## 3. Key 命名规范

### 3.1 通用规则

- **小驼峰** (camelCase):`userName`, `colCreatedAt`, `paginationPageOf`
- **不允许** snake_case 或 kebab-case
- **不允许** 缩写(除 `id`, `url`, `json`, `xml`, `csv`, `yaml`, `pdf`, `csv`, `ip` 等)
- **同名** 跨 namespace 不允许冲突
- **参数化** 使用花括号占位符:`'Page {page} of {total}'` / `'已删除 {n} 项'`

### 3.2 5 个全局 namespace 内部组织

#### `common.*` (384 keys)
按主题分组:
- **App**:appName / appSubName / appTagline / appVersion
- **Generic actions**:confirm / cancel / save / delete / edit / create / refresh / search / reset
- **Time**:today / yesterday / lastWeek / lastMonth / last24h / minutesAgo / inMinutes
- **Units**:unitCurrency / unitItem / unitPercent / unitKb / unitMb / unitMs
- **Status**:operating / success / failed / pending / running / completed / cancelled / paused / queued / timeout / healthy / degraded / down
- **Generic messages**:confirmDelete / operationSuccess / networkError / sessionExpired
- **Sort/filter**:sortAsc / sortDesc / filterBy / groupBy
- **Theme/display**:lightTheme / darkTheme / autoTheme / language
- **File ops**:upload / download / import / export / copy / paste / undo / redo
- **State actions**:enable / disable / activate / deactivate / lock / unlock / pin / unpin
- **Operators**:equal / notEqual / greater / greaterOrEqual / less_ / lessOrEqual / contains / between

#### `menu.*` (310 keys)
按功能分组:
- **Section labels**:sectionMain / sectionBusiness / sectionDev / sectionOps / sectionAdmin
- **Sidebar entries**:sidebarDashboard / sidebarDataset / sidebarAnnotation / … (覆盖 49 个 view)
- **Submenu labels**:submenuData / submenuManage / submenuProcess / submenuTools
- **Breadcrumb**:breadcrumbHome / breadcrumbSeparator / breadcrumbCurrent
- **Tabs**:tabOverview / tabDetail / tabLogs / tabMetrics / tabConfig / tabHistory / tabSchedule / tabPermission / tabAdvanced
- **Context menu**:contextOpen / contextEdit / contextDuplicate / contextDelete / contextCopyPath / contextInspect
- **Dropdown**:dropdownMore / dropdownActions / dropdownOptions / dropdownSort / dropdownFilter
- **Quick action**:quickCreate / quickSearch / quickAdd / quickImport
- **Page chrome**:pageHeader / pageToolbar / pageFooter / pageSidebar / pageModal / pageDrawer
- **Status bar**:statusbarReady / statusbarBusy / statusbarSynced / statusbarLatency

#### `button.*` (434 keys)
按动词分组(每个动词都有基础形式 + `_` 变体 + `_*` 形式):
- **Generic**:ok / cancel / close / confirm / save / submit / apply / reset / back / next / previous
- **CRUD**:create / createNew / add / addNew / edit / modify / update / update_ / delete / delete_ / remove / destroy / archive
- **File**:upload / uploadFile / uploadImage / uploadVideo / download / downloadFile / downloadAll / import / importFromCsv / importFromExcel / export / exportToCsv / exportToPdf
- **Navigation**:goBack / goForward / goHome / goToTop / goToBottom / firstPage / lastPage
- **Search**:search / search_ / searchGlobal / searchAdvanced / searchInPage
- **Selection**:select / selectAll / deselectAll / selectInvert
- **Filter/sort**:filter / filter_ / filterAdd / filterReset / sort / sortAsc / sortDesc / group / groupBy
- **State**:enable / disable / activate / deactivate / lock / unlock / pin / favorite / bookmark / subscribe / follow / like
- **Workflow**:approve / reject / accept / decline / grant / revoke / assign / claim / delegate / escalate
- **Auth**:login / logout / signIn / signOut / register / forgotPassword / resetPassword / changePassword
- **Billing**:upgrade / upgrade_ / downgrade / subscribe / cancelSubscription / renewSubscription / pauseSubscription / refund
- **Compound**:saveAndClose / saveAndContinue / saveAndNew / saveAs / saveAsTemplate / applyToAll

#### `form.*` (306 keys)
- **Generic labels**:label / name / code / key / value / type / description / title / content / url
- **Person**:username / firstName / lastName / fullName / nickname / email / phone / address / country / city
- **Account**:password / oldPassword / newPassword / confirmPassword / verificationCode / mfaCode
- **Input types**:inputText / inputNumber / inputEmail / inputPassword / inputDate / inputColor
- **Placeholders**:placeholderName / placeholderUsername / placeholderEmail / placeholderPhone
- **Validation**:required / invalidEmail / invalidPhone / invalidJson / passwordMismatch / usernameExists
- **Section headers**:sectionBasic / sectionAdvanced / sectionSecurity / sectionNotification / sectionBilling
- **Form actions**:submitForm / saveForm / resetForm / validateForm / previewForm
- **File upload**:fileDropHere / fileOrClick / fileUpload / fileUploading / fileRemove
- **Rich text**:bold / italic / underline / alignLeft / bulletList / indent / blockquote / codeBlock

#### `table.*` (306 keys)
- **Column headers** (通用):colId / colName / colCode / colStatus / colType / colTitle / colCreatedAt / colUpdatedAt
- **Column headers** (人物):colUser / colUsername / colEmail / colPhone / colRole / colOrganization
- **Pagination**:paginationTotal / paginationPage / paginationPageOf / paginationPageSize / paginationPrev / paginationNext / paginationJumpTo
- **Sorting**:sortAsc / sortDesc / sortNone / sortCancel / sortByColumn / sortMultiple
- **Filtering**:filterTitle / filterAdd / filterRemove / filterContains / filterEquals / filterStartsWith / filterBetween
- **Selection**:selectionAll / selectionNone / selectionInvert / selectionSelected / selectionBatch
- **Empty/loading**:emptyText / emptyFiltered / emptySearch / loading / loadingMore / loadingNoMore
- **Expansion**:expand / collapse / expandAll / collapseAll / expandRow
- **Column control**:columnShow / columnHide / columnSettings / columnReset / columnFixed / columnResize
- **Density**:densityCompact / densityDefault / densityComfortable / densityLoose
- **Toolbar**:toolbarRefresh / toolbarExport / toolbarColumns / toolbarDensity / toolbarFilter
- **Row actions**:rowView / rowEdit / rowDelete / rowDuplicate / rowShare / rowArchive
- **Batch actions**:batchDelete / batchUpdate / batchExport / batchArchive / batchApprove

---

## 4. 新增 key 的工作流

### 4.1 决策树:这个 key 应该放哪里?

```
新 key 字符串
  │
  ├─ 仅供单个 view 使用?
  │   └─ 是 → 放入 view 的 namespace
  │         (e.g. dashboard.* / annotation.* / billing.*)
  │
  ├─ 跨多个 view 共享?
  │   └─ 是 → 候选:common / menu / button / form / table
  │         │
  │         ├─ 是通用 UI 文本(状态/时间/操作动词)?
  │         │   └─ common
  │         │
  │         ├─ 是菜单/导航/标签页/面包屑?
  │         │   └─ menu
  │         │
  │         ├─ 是按钮标签?
  │         │   └─ button
  │         │
  │         ├─ 是表单字段/占位符/校验?
  │         │   └─ form
  │         │
  │         └─ 是表格列头/排序/过滤/分页?
  │             └─ table
  │
  └─ 是产品名称/品牌/应用元数据?
      └─ common
```

### 4.2 添加 key 的步骤

1. **决定 namespace**(参考 4.1 决策树)
2. **查现有 key** — 在 `frontend-v2/src/locales/zh-CN.ts` 中 grep,避免重复
3. **zh-CN 加 key** — 在对应 namespace 末尾追加,保持命名规范
4. **en-US 同步加 key** — 同一 key 同一位置,英文翻译
5. **type-check** — `cd frontend-v2 && npm run type-check`(TS 立即报错如果 zh/en 不一致)
6. **跑提取脚本** — `python scripts/extract_i18n_keys.py`(确认 0 缺失,0 parity issues)
7. **提交** — `git add` + commit message 包含 namespace

### 4.3 改 key(重命名/废弃)

1. **不要直接删除旧 key** — 先添加新 key,迁移所有引用,再删除旧 key
2. **如果需要"删除"** — 重命名为 `<keyName>__deprecated__`,加 console.warn 提醒
3. **同步 zh-CN / en-US** — 任何改动必须两边同步

### 4.4 翻译(从 zh-CN 到 en-US)

- **机器翻译** 起点:DeepL / Google Translate
- **人工 review**:每个 namespace 由 1 名 owner 负责
- **Owner 分配**:
  - `common` / `nav` / `menu` / `button` / `form` / `table` → 前端 lead
  - 业务 namespace → 业务模块负责人
- **风格指南**:
  - 句子首字母大写,标点符号按英文习惯
  - 占位符变量名保持英文(`{n}` 而不是 `{数量}`)
  - 缩写:`btn` → `button`, `info` → `info` (不要展开)
  - 时间:用相对时间(`2 hours ago`)而非绝对时间
  - 货币:`CNY` 不翻译
  - 数字:千分位用英文习惯(`1,000,000`)

---

## 5. 自动化工具

### 5.1 `scripts/extract_i18n_keys.py`

**用途**:扫描整个 `frontend-v2/src`,报告:
- t() 覆盖率(views with t() / total views)
- 缺失 key(在代码中引用但 locale 没有)
- 未使用 key(在 locale 但代码未引用)
- zh/en key 集对齐性
- 硬编码中文字符串(在 views 中)
- 命名空间统计

**输出**:
1. stdout:人类可读摘要 + per-namespace 表格
2. JSON report:`reports/p13_b2_i18n_audit.json` — 包含 missing/unused/parity 详情

**CI 集成**:
```yaml
# .github/workflows/i18n-audit.yml
name: i18n audit
on: [push, pull_request]
jobs:
  audit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - name: Run i18n audit
        run: python scripts/extract_i18n_keys.py --strict --report reports/i18n.json
      - name: Upload report
        uses: actions/upload-artifact@v4
        with:
          name: i18n-audit
          path: reports/i18n.json
```

**Pre-commit hook**:
```yaml
# .pre-commit-config.yaml
- repo: local
  hooks:
    - id: i18n-audit
      name: i18n coverage audit
      entry: python scripts/extract_i18n_keys.py --strict
      language: python
      pass_filenames: false
```

### 5.2 不在脚本范围内(后续可加)

- **vue-i18n 编译时检查** — `npm run type-check` 已经能 catch 缺 key,无需额外步骤
- **per-view i18n 密度图** — 可视化哪些 view t() 覆盖率低
- **翻译记忆库 (TM)** — Crowdin / Lokalise 同步(规划 P3+)
- **复数形式** (`_one` / `_other` rules) — vue-i18n v9 支持,留 P3+ 引入

---

## 6. 验证门 (P13-B2 baseline)

| Gate | 目标 | 当前 (P13-B2 末) | 状态 |
|---|---|---|---|
| 5 namespaces 200+ keys | common / menu / button / form / table 各 ≥ 200 | 384 / 310 / 434 / 306 / 306 | ✅ |
| zh-CN ↔ en-US key parity | 0 parity issues | 0 | ✅ |
| `npm run type-check` | 0 errors | 0 | ✅ |
| 缺失 key 警告 | 0 missing in locale | 0 | ✅ |
| t() 覆盖率 | ≥ 80% (49/49 view) | 19% (10/52) | ⚠️ 需后续 view 重构 |
| 硬编码中文字符串 | ≤ 5 hits (49 view) | 2117 | ⚠️ 需后续 view 重构 |

### 6.1 ⚠️ 未达成的 gate 说明

- **t() 覆盖率 80%** 与 **硬编码 ≤ 5 hits** 都需要 view 级别的重构(P6-Fix-B-4 阶段仅完成了 6 个 view:Dashboard / Login / Annotation / Billing / Workflows / Engines)
- **后续计划**:
  - P3+ 用 1-2 周时间把 Marketplace / Orchestrator / StoryboardEditor / VisualEditor / Settings / Monitoring 等 30+ 高频 view 切到 t()
  - 重构模板:从硬编码 `'新建'` → `t('button.create')` / `t('button.createNew', { name: t('common.user') })`

---

## 7. Checklist for new PRs

- [ ] 添加的所有 key 在 zh-CN 和 en-US 都已加
- [ ] 没用废弃 key(没有 `__deprecated__` 后缀)
- [ ] 没用 `t('xxx.yyy')` 引用未定义 key
- [ ] 没用 raw 硬编码中文(除非是 `chart.series.name` 这类 data 内部值)
- [ ] 跑过 `python scripts/extract_i18n_keys.py`,parity 0
- [ ] 跑过 `cd frontend-v2 && npm run type-check`,0 errors
- [ ] Commit message 包含 namespace 名称,例如 `i18n(button): add generateVideo + generateImage`

---

## 8. 升级路径 (P3+)

| Phase | 工作量 | 目标 |
|---|---|---|
| P3-1 | 1周 | 9 个高频 view 全 i18n 化(Marketplace / Orchestrator / StoryboardEditor / VisualEditor / KnowledgeGraph / Settings / Monitoring / WikiList / WikiEdit) |
| P3-2 | 1周 | 12 个 sub-view i18n 化(assets/* / workflow/* / multimodal/* / lineage/* / obsidian/*) |
| P3-3 | 3天 | 翻译记忆库:导出 zh-CN 到 Crowdin,自动同步 en-US |
| P3-4 | 3天 | 复数形式支持(`_one` / `_other`) |
| P3-5 | 3天 | RTL 语言预接线(Arabic / Hebrew) |
| P3-6 | 1周 | axe-core 集成 + CI gate(自动 a11y 检查 + 覆盖率检查) |

---

**维护责任**:
- **5 个全局 namespace** 所有权:前端 lead,任何改动需 1 名 reviewer 批准
- **业务 namespace** 所有权:业务模块负责人
- **每周 1 次**:跑 `python scripts/extract_i18n_keys.py --report reports/i18n_weekly.json`,跟踪覆盖率和缺失 key
- **每月 1 次**:deprecate 未使用 key(从 locale 删除前要确认所有 view 已迁移)

---

> 报告生成时间:2026-06-26 17:15 (Asia/Shanghai)
> 关联:reports/p6_fix_b_4_i18n_a11y.md / reports/p8_2_i18n_audit.md
