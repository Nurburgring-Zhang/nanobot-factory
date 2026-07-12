/**
 * Simplified Chinese (zh-CN) locale messages — P6-4 P1 baseline.
 *
 * Naming convention: dot-separated namespaces; group by feature module.
 *   common.*   — global UI chrome (buttons, headers, status)
 *   nav.*      — sidebar / route titles
 *   auth.*     — login form
 *   dashboard.* — Dashboard view
 *   annotation.* — Annotation view
 *   billing.*  — Billing view
 *   workflows.* — Workflows view
 *   engines.*  — Engines view
 *
 * Keep keys stable across locales; en-US is the source of truth for additions.
 */
export default {
  common: {
    appName: '智影',
    appSubName: 'nanobot-factory',
    confirm: '确认',
    cancel: '取消',
    save: '保存',
    delete: '删除',
    edit: '编辑',
    create: '新建',
    refresh: '刷新',
    search: '搜索',
    reset: '重置',
    loading: '加载中…',
    empty: '暂无数据',
    error: '出错了',
    retry: '重试',
    submit: '提交',
    back: '返回',
    close: '关闭',
    yes: '是',
    no: '否',
    on: '开',
    off: '关',
    enabled: '启用',
    disabled: '禁用',
    required: '必填',
    optional: '可选',
    detail: '详情',
    viewMore: '查看更多',
    viewAll: '查看全部',
    selectAll: '全选',
    unselected: '未选择',
    today: '今天',
    yesterday: '昨天',
    lastWeek: '近 7 天',
    lastMonth: '近 30 天',
    unitCurrency: '元',
    unitItem: '个',
    unitTimes: '次',
    operating: '操作中',
    success: '成功',
    failed: '失败',
    pending: '待处理',
    running: '运行中',
    completed: '已完成',
    cancelled: '已取消',
    healthy: '健康',
    degraded: '降级',
    down: '宕机',
    running_: '运行中',
    add: '添加', // TODO: native review
    apply: '应用', // TODO: native review
    approve: '通过', // TODO: native review
    archived: '已归档', // TODO: native review
    automatic: '自动', // TODO: native review
    backup: '备份', // TODO: native review
    closed: '已关闭', // TODO: native review
    decline: '拒绝', // TODO: native review
    deleted: '已删除', // TODO: native review
    description: '描述', // TODO: native review
    draft: '草稿', // TODO: native review
    export: '导出', // TODO: native review
    goTo: '前往', // TODO: native review
    import: '导入', // TODO: native review
    inProgress: '进行中', // TODO: native review
    label: '标签', // TODO: native review
    language: '语言', // TODO: native review
    notStarted: '未开始', // TODO: native review
    operationFailed: '操作失败', // TODO: native review
    paused: '已暂停', // TODO: native review
    project: '项目', // TODO: native review
    question: '问题', // TODO: native review
    recommended: '推荐', // TODO: native review
    start: '开始', // TODO: native review
    updatedAt: '更新时间', // TODO: native review
    user: '用户', // TODO: native review
  },
  nav: {
    dashboard: '仪表盘',
    dataset: '数据集',
    annotation: '标注',
    review: '审核',
    scoring: '评分',
    workflows: '工作流',
    engines: '引擎',
    tasks: '任务',
    users: '用户',
    billing: '计费',
    monitoring: '监控',
    settings: '设置',
    login: '登录',
    logout: '退出登录',
    skipToMain: '跳转到主内容'
  },
  auth: {
    loginTitle: '智影',
    loginSubtitle: 'nanobot-factory',
    username: '账号',
    password: '密码',
    usernamePlaceholder: '请输入账号',
    passwordPlaceholder: '请输入密码',
    submit: '登录',
    invalidCredentials: '账号或密码不正确',
    defaultHint: '默认账号可在后端 docs/ 中查阅',
    validationRequired: '必填项'
  },
  dashboard: {
    pageTitle: '系统概览',
    cardDatasets: '数据集',
    cardDatasetsNote: '累计入库数据资产',
    cardTasks: '任务',
    cardTasksNote: '历史任务总数',
    cardEngines: '引擎',
    cardEnginesNote: '已注册生产引擎',
    cardUsers: '用户',
    cardUsersNote: '平台账户数',
    chartThroughput: '任务吞吐（近 7 天）',
    chartEngines: '引擎状态分布',
    servicesTitle: '系统状态',
    colService: '服务',
    colStatus: '状态',
    colUptime: '可用率（30 天）',
    loading: '加载中…'
  },
  annotation: {
    pageTitle: '标注工作台',
    pageSubtitle: '对接 annotation_service — 任务分配 / 操作员 / 标注记录',
    refresh: '刷新',
    pending: '待处理',
    operatorsCount: '操作员',
    searchPlaceholder: '搜索任务 ID / 名称 / 标注员',
    statusFilter: '按状态过滤',
    emptyTasks: '暂无标注任务',
    operatorsTitle: '可用操作员（Annotation Operators）',
    emptyOperators: '暂无操作员',
    taskDetailTitle: '任务详情',
    taskDetailEmpty: '点击表格行查看任务详情',
    kpiTotal: '本页任务',
    kpiPending: '待处理',
    kpiOperators: '可用操作员',
    kpiPage: '当前页',
    kpiTotalHint: '共 {total} 条',
    kpiPendingHint: '需标注员跟进',
    kpiOperatorsHint: '已注册 / 活跃',
    kpiPageHint: '每页 {size} 条',
    statusPending: '待处理',
    statusApproved: '已通过',
    statusRejected: '已驳回',
    statusCompleted: '已完成',
    statusClosed: '已关闭',
    colId: 'ID',
    colName: '名称',
    colType: '类型',
    colStatus: '状态',
    colAssignee: '标注员',
    colAssets: '资产',
    colCreatedAt: '创建时间',
    colActions: '操作',
    actionDetail: '详情'
  },
  billing: {
    pageTitle: '计费 / 用量',
    pageSubtitle: '套餐 · 用量 · 订单 · 发票',
    refresh: '刷新',
    upgrade: '升级套餐',
    plans: '可用套餐',
    emptyPlans: '暂无可用套餐',
    recommended: '推荐',
    perMonth: '/ 月',
    moreFeatures: '+ {n} 更多',
    currentPlan: '当前套餐',
    switchTo: '切换到此套餐',
    viewDetail: '查看详情',
    usageTitle: '用量明细',
    emptyUsage: '暂无用量数据',
    entriesTitle: '业务入口',
    ordersTitle: '近期订单',
    emptyOrders: '暂无订单',
    kpiCost: '本期账单',
    kpiBuckets: '用量维度',
    kpiOrders: '历史订单',
    kpiPlan: '当前套餐',
    kpiCostHint: '实时累计',
    kpiBucketsHint: '12 维度监控',
    kpiOrdersHint: '本月 / 历史',
    notSubscribed: '未订阅'
  },
  workflows: {
    pageTitle: '工作流编排',
    pageSubtitle: 'Vue Flow 可视化 · {name} · {n} 模板',
    pickTemplate: '选模板',
    refresh: '刷新',
    run: '运行',
    flowCanvasTitle: '工作流画布',
    nodesLabel: '{n} 节点',
    edgesLabel: '{n} 连线',
    categoriesLabel: '{n} 类别',
    templatesTitle: '工作流模板',
    searchPlaceholder: '搜索模板名称 / 描述 / 标签',
    category: '类别',
    emptyTemplates: '无匹配模板',
    runsTitle: '运行历史',
    emptyRuns: '尚无运行',
    pickerTitle: '选择工作流模板',
    pickButton: '选用',
    cancelRun: '取消',
    colRunId: '运行 ID',
    colWorkflow: '工作流',
    colStatus: '状态',
    colTrigger: '触发器',
    colStarted: '开始',
    colFinished: '结束',
    colActions: '操作'
  },
  engines: {
    pageTitle: '引擎管理',
    pageSubtitle: '{n} 个 Agent 引擎 — 启动 / 停止 / 健康检查',
    refresh: '刷新',
    activeCount: '可运行',
    totalTasks: '任务',
    searchPlaceholder: '搜索引擎 ID / 名称 / 能力',
    modeFilter: '默认模式',
    empty: '暂无引擎',
    detailTitle: '引擎详情',
    detailEmpty: '选择左侧表格行查看详情',
    resultTitle: '运行结果',
    resultEmpty: '尚未运行',
    runSection: '运行测试',
    runPayloadPlaceholder: 'JSON 输入 payload，例如 {"query":"hello"}',
    runSync: '同步运行',
    runAsync: '提交异步任务',
    cancelLast: '取消最近任务',
    modeFullAuto: '全自动',
    modeSemiAuto: '半自动',
    modeManual: '手动',
    colId: 'ID',
    colName: '名称',
    colMode: '默认模式',
    colPriority: '优先级',
    colDownstream: '下游服务',
    colCapabilities: '能力',
    colActions: '操作',
    actionDetail: '详情 / 运行'
  },

  workflowBuilder: {
    t000: '工作流搭建器',
    t001: '新工作流',
    t002: '个能力模块拖拽组合',
    t003: '模板',
    t004: '上次运行',
    t005: '完成率',
    t006: '总耗时',
    t007: '画布',
    t008: '从模板开始',
    t009: '删除节点',
    t010: '编辑工作流',
    t011: '使用',
    t012: '现在',
    t013: '需求',
    t014: '数据包',
    t015: '采集',
    t016: '质检',
    t017: '需求方验收',
    t018: '交付',
    t019: '打标',
    t020: '清洗',
    t021: '评测',
    t022: '加载能力目录失败',
    t023: '加载模板失败',
    t024: '已加载模板',
    t025: '画布为空',
    t026: '无需保存',
    t027: '请填写工作流名称',
    t028: '已保存工作流',
    t029: '保存失败',
    t030: '运行完成',
    t031: '运行失败',
    t032: '加载节点失败',
    t033: '删除节点失败',
  },

  dataFlowTracker: {
    apply: '应用', // TODO: native review
    clear: '清空', // TODO: native review
    domainEventsTitle: '领域事件', // TODO: native review
    filterByProject: '按项目筛选', // TODO: native review
    filterPlaceholder: '筛选事件…', // TODO: native review
    loadFailed: '加载事件失败', // TODO: native review
    noEvents: '暂无事件', // TODO: native review
    pageSubtitle: '跨系统事件实时时间线', // TODO: native review
    pageTitle: '数据流转追踪', // TODO: native review
    pipelineTitle: '流水线总览', // TODO: native review
    refresh: '刷新', // TODO: native review
    timelineTitle: '事件时间线', // TODO: native review
  },

  form: {
    category: '类别', // TODO: native review
    creator: '创建者', // TODO: native review
    dueDate: '截止日期', // TODO: native review
    inputRate: '输入速率', // TODO: native review
    placeholderName: '请输入名称', // TODO: native review
    placeholderTitle: '请输入标题', // TODO: native review
    sectionMember: '成员', // TODO: native review
    title: '标题', // TODO: native review
  },

  menu: {
    contextHistory: '最近访问', // TODO: native review
    dropdownOptions: '选项', // TODO: native review
    sidebarCleaningManagement: '清洗管理', // TODO: native review
    sidebarWorkflow: '工作流', // TODO: native review
    statusbarReady: '就绪', // TODO: native review
    statusbarUnsaved: '未保存', // TODO: native review
    submenuData: '数据', // TODO: native review
    tabIncidents: '事件', // TODO: native review
    tabSchema: '数据模型', // TODO: native review
  },

  multimodalAgentChat: {
    invoke: '调用', // TODO: native review
  },

  userManagement: {
    createSuccess: '用户已创建', // TODO: native review
    roleAdmin: '管理员', // TODO: native review
  },

  projectCenter: {
    t000: '项目中心', // TODO: native review
    t001: '未命名项目', // TODO: native review
    t002: '项目工作区总览', // TODO: native review
    t003: '搜索项目', // TODO: native review
    t004: '按状态筛选', // TODO: native review
    t005: '按优先级筛选', // TODO: native review
    t006: '新建项目', // TODO: native review
    t007: '编辑项目', // TODO: native review
  },

  requirementCenter: {
    t000: '需求中心', // TODO: native review
    t001: '未命名需求', // TODO: native review
    t002: '浏览并管理需求', // TODO: native review
    t003: '搜索需求', // TODO: native review
    t004: '按项目筛选', // TODO: native review
    t005: '按状态筛选', // TODO: native review
    t006: '新建需求', // TODO: native review
    t007: '编辑需求', // TODO: native review
  },

  internalQC: {
    t000: '内部质检', // TODO: native review
    t001: '未命名记录', // TODO: native review
    t002: '质检工作台', // TODO: native review
    t003: '搜索记录', // TODO: native review
    t004: '按审核员筛选', // TODO: native review
    t005: '执行质检', // TODO: native review
    t006: '保存质检', // TODO: native review
    t007: '标记通过', // TODO: native review
    t040: '样本量',
    t041: '置信水平',
    t042: '误差范围',
    t043: '评分者一致性',
    t044: 'Kappa 分数',
    t045: '分歧阈值',
    t046: '裁决规则',
    t047: '审核员轮换',
    t048: '盲审',
    t049: '耗时',
    t050: '标注准确率',
    t051: '覆盖率',
    t052: '边缘案例',
    t053: '错误模式',
    t054: '质量趋势',
    t055: '校准会议',
    t056: '黄金标准',
    t057: '隐藏测试',
    t058: '审计跟踪',
    t059: '审核员反馈'


  }
};
