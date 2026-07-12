/**
 * ja-JP locale messages.
 * P20-N recovery: rebuilt from zh-CN baseline + workflowBuilder block.
 * Per task spec, English fallback used for keys not yet translated.
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
    add: '追加', // TODO: native review
    apply: '適用', // TODO: native review
    approve: '承認', // TODO: native review
    archived: 'アーカイブ済み', // TODO: native review
    automatic: '自動', // TODO: native review
    backup: 'バックアップ', // TODO: native review
    closed: '終了', // TODO: native review
    decline: '拒否', // TODO: native review
    deleted: '削除済み', // TODO: native review
    description: '説明', // TODO: native review
    draft: '下書き', // TODO: native review
    export: 'エクスポート', // TODO: native review
    goTo: '移動', // TODO: native review
    import: 'インポート', // TODO: native review
    inProgress: '進行中', // TODO: native review
    label: 'ラベル', // TODO: native review
    language: '言語', // TODO: native review
    notStarted: '未開始', // TODO: native review
    operationFailed: '操作に失敗しました', // TODO: native review
    paused: '一時停止', // TODO: native review
    project: 'プロジェクト', // TODO: native review
    question: '質問', // TODO: native review
    recommended: 'おすすめ', // TODO: native review
    start: '開始', // TODO: native review
    updatedAt: '更新日時', // TODO: native review
    user: 'ユーザー', // TODO: native review,
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
    t000: 'ワークフロービルダー',
    t001: '新規ワークフロー',
    t002: '個の能力モジュールをドラッグして組み合わせ',
    t003: 'テンプレート',
    t004: '最終実行',
    t005: '完了',
    t006: '合計時間',
    t007: 'キャンバス',
    t008: 'テンプレートから開始',
    t009: 'ノード削除',
    t010: 'ワークフロー編集',
    t011: '使用',
    t012: '今',
    t013: '要件',
    t014: 'データセット',
    t015: '収集',
    t016: '品質検査',
    t017: '依頼者検収',
    t018: '納品',
    t019: 'ラベリング',
    t020: 'クリーニング',
    t021: '評価',
    t022: '能力目録の読み込みに失敗しました',
    t023: 'テンプレートの読み込みに失敗しました',
    t024: 'テンプレートを読み込みました',
    t025: 'キャンバスが空です',
    t026: '保存不要',
    t027: 'ワークフロー名を入力してください',
    t028: 'ワークフローを保存しました',
    t029: '保存に失敗しました',
    t030: '実行完了',
    t031: '実行失敗',
    t032: 'ノードの読み込みに失敗しました',
    t033: 'ノードの削除に失敗しました',
  },




  dataFlowTracker: {
    apply: '適用', // TODO: native review
    clear: 'クリア', // TODO: native review
    domainEventsTitle: 'ドメインイベント', // TODO: native review
    filterByProject: 'プロジェクトで絞り込み', // TODO: native review
    filterPlaceholder: 'イベントを絞り込み…', // TODO: native review
    loadFailed: 'イベントの読み込みに失敗しました', // TODO: native review
    noEvents: 'イベントなし', // TODO: native review
    pageSubtitle: 'システム横断のリアルタイムイベント', // TODO: native review
    pageTitle: 'データフロー追跡', // TODO: native review
    pipelineTitle: 'パイプライン概要', // TODO: native review
    refresh: '更新', // TODO: native review
    timelineTitle: 'イベントタイムライン', // TODO: native review
  },

  form: {
    category: 'カテゴリ', // TODO: native review
    creator: '作成者', // TODO: native review
    dueDate: '期限', // TODO: native review
    inputRate: '入力レート', // TODO: native review
    placeholderName: '名前を入力', // TODO: native review
    placeholderTitle: 'タイトルを入力', // TODO: native review
    sectionMember: 'メンバー', // TODO: native review
    title: 'タイトル', // TODO: native review
  },

  menu: {
    contextHistory: '最近', // TODO: native review
    dropdownOptions: 'オプション', // TODO: native review
    sidebarCleaningManagement: 'クリーニング管理', // TODO: native review
    sidebarWorkflow: 'ワークフロー', // TODO: native review
    statusbarReady: '準備完了', // TODO: native review
    statusbarUnsaved: '未保存', // TODO: native review
    submenuData: 'データ', // TODO: native review
    tabIncidents: 'インシデント', // TODO: native review
    tabSchema: 'スキーマ', // TODO: native review
  },

  multimodalAgentChat: {
    invoke: '呼び出し', // TODO: native review
  },

  userManagement: {
    createSuccess: 'ユーザーを作成しました', // TODO: native review
    roleAdmin: '管理者', // TODO: native review
  },

  projectCenter: {
    t000: 'プロジェクトセンター', // TODO: native review
    t001: '無題のプロジェクト', // TODO: native review
    t002: 'プロジェクトワークスペース概要', // TODO: native review
    t003: 'プロジェクトを検索', // TODO: native review
    t004: 'ステータスで絞り込み', // TODO: native review
    t005: '優先度で絞り込み', // TODO: native review
    t006: 'プロジェクト作成', // TODO: native review
    t007: 'プロジェクト編集', // TODO: native review
  },

  requirementCenter: {
    t000: '要件センター', // TODO: native review
    t001: '無題の要件', // TODO: native review
    t002: '要件の閲覧と管理', // TODO: native review
    t003: '要件を検索', // TODO: native review
    t004: 'プロジェクトで絞り込み', // TODO: native review
    t005: 'ステータスで絞り込み', // TODO: native review
    t006: '要件作成', // TODO: native review
    t007: '要件編集', // TODO: native review
  },

  internalQC: {
    // TODO: native review (round 5 P3 P2 focused)
    t000: '内部品質検査', // TODO: native review
    t001: '無題のレコード', // TODO: native review
    t002: '品質検査ワークベンチ', // TODO: native review
    t003: 'レコード検索', // TODO: native review
    t004: 'レビュアーで絞り込み', // TODO: native review
    t005: 'QC実行', // TODO: native review
    t006: 'QC保存', // TODO: native review
    t007: '合格として記録', // TODO: native review
    t040: 'Sample size',
    t041: 'Confidence level',
    t042: 'Margin of error',
    t043: 'Inter-rater agreement',
    t044: 'Kappa score',
    t045: 'Disagreement threshold',
    t046: 'Adjudication rule',
    t047: 'Reviewer rotation',
    t048: 'Blind review',
    t049: 'Time spent',
    t050: 'Annotation accuracy',
    t051: 'Coverage rate',
    t052: 'Edge cases',
    t053: 'Error patterns',
    t054: 'Quality trends',
    t055: 'Calibration session',
    t056: 'Gold standard',
    t057: 'Hidden test',
    t058: 'Audit trail',
    t059: 'Reviewer feedback'


  }
};
