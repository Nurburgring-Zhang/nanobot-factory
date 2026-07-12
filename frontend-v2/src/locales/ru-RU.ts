/**
 * ru-RU locale messages.
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
    add: 'Добавить', // TODO: native review
    apply: 'Применить', // TODO: native review
    approve: 'Одобрить', // TODO: native review
    archived: 'В архиве', // TODO: native review
    automatic: 'Автоматически', // TODO: native review
    backup: 'Резервная копия', // TODO: native review
    closed: 'Закрыто', // TODO: native review
    decline: 'Отклонить', // TODO: native review
    deleted: 'Удалено', // TODO: native review
    description: 'Описание', // TODO: native review
    draft: 'Черновик', // TODO: native review
    export: 'Экспорт', // TODO: native review
    goTo: 'Перейти', // TODO: native review
    import: 'Импорт', // TODO: native review
    inProgress: 'В процессе', // TODO: native review
    label: 'Метка', // TODO: native review
    language: 'Язык', // TODO: native review
    notStarted: 'Не начато', // TODO: native review
    operationFailed: 'Операция не выполнена', // TODO: native review
    paused: 'Приостановлено', // TODO: native review
    project: 'Проект', // TODO: native review
    question: 'Вопрос', // TODO: native review
    recommended: 'Рекомендуется', // TODO: native review
    start: 'Запустить', // TODO: native review
    updatedAt: 'Обновлено', // TODO: native review
    user: 'Пользователь', // TODO: native review,
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
    t000: 'Конструктор рабочих процессов',
    t001: 'Новый процесс',
    t002: 'модулей для перетаскивания',
    t003: 'Шаблон',
    t004: 'Последний запуск',
    t005: 'Завершено',
    t006: 'Общее время',
    t007: 'Холст',
    t008: 'Начать с шаблона',
    t009: 'Удалить узел',
    t010: 'Редактировать процесс',
    t011: 'Использовать',
    t012: 'Сейчас',
    t013: 'Требование',
    t014: 'Набор данных',
    t015: 'Сбор',
    t016: 'Контроль качества',
    t017: 'Приёмка заказчиком',
    t018: 'Доставка',
    t019: 'Разметка',
    t020: 'Очистка',
    t021: 'Оценка',
    t022: 'Не удалось загрузить каталог возможностей',
    t023: 'Не удалось загрузить шаблон',
    t024: 'Шаблон загружен',
    t025: 'Холст пуст',
    t026: 'Сохранение не требуется',
    t027: 'Введите имя рабочего процесса',
    t028: 'Рабочий процесс сохранён',
    t029: 'Не удалось сохранить',
    t030: 'Выполнение завершено',
    t031: 'Сбой выполнения',
    t032: 'Не удалось загрузить узлы',
    t033: 'Не удалось удалить узлы',
  },




  dataFlowTracker: {
    apply: 'Применить', // TODO: native review
    clear: 'Очистить', // TODO: native review
    domainEventsTitle: 'События домена', // TODO: native review
    filterByProject: 'Фильтр по проекту', // TODO: native review
    filterPlaceholder: 'Фильтр событий…', // TODO: native review
    loadFailed: 'Не удалось загрузить события', // TODO: native review
    noEvents: 'Нет событий', // TODO: native review
    pageSubtitle: 'Лента событий между системами в реальном времени', // TODO: native review
    pageTitle: 'Трекер потоков данных', // TODO: native review
    pipelineTitle: 'Обзор конвейера', // TODO: native review
    refresh: 'Обновить', // TODO: native review
    timelineTitle: 'Временная шкала событий', // TODO: native review
  },

  form: {
    category: 'Категория', // TODO: native review
    creator: 'Создатель', // TODO: native review
    dueDate: 'Срок', // TODO: native review
    inputRate: 'Скорость ввода', // TODO: native review
    placeholderName: 'Введите имя', // TODO: native review
    placeholderTitle: 'Введите заголовок', // TODO: native review
    sectionMember: 'Участники', // TODO: native review
    title: 'Заголовок', // TODO: native review
  },

  menu: {
    contextHistory: 'Недавние', // TODO: native review
    dropdownOptions: 'Параметры', // TODO: native review
    sidebarCleaningManagement: 'Управление очисткой', // TODO: native review
    sidebarWorkflow: 'Рабочий процесс', // TODO: native review
    statusbarReady: 'Готово', // TODO: native review
    statusbarUnsaved: 'Не сохранено', // TODO: native review
    submenuData: 'Данные', // TODO: native review
    tabIncidents: 'Инциденты', // TODO: native review
    tabSchema: 'Схема', // TODO: native review
  },

  multimodalAgentChat: {
    invoke: 'Вызвать', // TODO: native review
  },

  userManagement: {
    createSuccess: 'Пользователь создан', // TODO: native review
    roleAdmin: 'Администратор', // TODO: native review
  },

  projectCenter: {
    t000: 'Центр проектов', // TODO: native review
    t001: 'Безымянный проект', // TODO: native review
    t002: 'Обзор рабочего пространства проекта', // TODO: native review
    t003: 'Поиск проектов', // TODO: native review
    t004: 'Фильтр по статусу', // TODO: native review
    t005: 'Фильтр по приоритету', // TODO: native review
    t006: 'Создать проект', // TODO: native review
    t007: 'Изменить проект', // TODO: native review
  },

  requirementCenter: {
    t000: 'Центр требований', // TODO: native review
    t001: 'Безымянное требование', // TODO: native review
    t002: 'Просмотр и управление требованиями', // TODO: native review
    t003: 'Поиск требований', // TODO: native review
    t004: 'Фильтр по проекту', // TODO: native review
    t005: 'Фильтр по статусу', // TODO: native review
    t006: 'Создать требование', // TODO: native review
    t007: 'Изменить требование', // TODO: native review
  },

  internalQC: {
    // TODO: native review (round 5 P3 P2 focused)
    t000: 'Внутренний контроль качества', // TODO: native review
    t001: 'Безымянная запись', // TODO: native review
    t002: 'Рабочее место контроля качества', // TODO: native review
    t003: 'Поиск записей', // TODO: native review
    t004: 'Фильтр по рецензенту', // TODO: native review
    t005: 'Запустить QC', // TODO: native review
    t006: 'Сохранить QC', // TODO: native review
    t007: 'Отметить как пройденное', // TODO: native review
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
