/**
 * es-ES locale messages.
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
    add: 'Añadir', // TODO: native review
    apply: 'Aplicar', // TODO: native review
    approve: 'Aprobar', // TODO: native review
    archived: 'Archivado', // TODO: native review
    automatic: 'Automático', // TODO: native review
    backup: 'Copia de seguridad', // TODO: native review
    closed: 'Cerrado', // TODO: native review
    decline: 'Rechazar', // TODO: native review
    deleted: 'Eliminado', // TODO: native review
    description: 'Descripción', // TODO: native review
    draft: 'Borrador', // TODO: native review
    export: 'Exportar', // TODO: native review
    goTo: 'Ir a', // TODO: native review
    import: 'Importar', // TODO: native review
    inProgress: 'En curso', // TODO: native review
    label: 'Etiqueta', // TODO: native review
    language: 'Idioma', // TODO: native review
    notStarted: 'Sin iniciar', // TODO: native review
    operationFailed: 'Operación fallida', // TODO: native review
    paused: 'Pausado', // TODO: native review
    project: 'Proyecto', // TODO: native review
    question: 'Pregunta', // TODO: native review
    recommended: 'Recomendado', // TODO: native review
    start: 'Iniciar', // TODO: native review
    updatedAt: 'Actualizado el', // TODO: native review
    user: 'Usuario', // TODO: native review,
    add: 'Añadir', // TODO: native review
    apply: 'Aplicar', // TODO: native review
    approve: 'Aprobar', // TODO: native review
    archived: 'Archivado', // TODO: native review
    automatic: 'Automático', // TODO: native review
    backup: 'Copia de seguridad', // TODO: native review
    closed: 'Cerrado', // TODO: native review
    decline: 'Rechazar', // TODO: native review
    deleted: 'Eliminado', // TODO: native review
    description: 'Descripción', // TODO: native review
    draft: 'Borrador', // TODO: native review
    export: 'Exportar', // TODO: native review
    goTo: 'Ir a', // TODO: native review
    import: 'Importar', // TODO: native review
    inProgress: 'En curso', // TODO: native review
    label: 'Etiqueta', // TODO: native review
    language: 'Idioma', // TODO: native review
    notStarted: 'Sin iniciar', // TODO: native review
    operationFailed: 'Operación fallida', // TODO: native review
    paused: 'Pausado', // TODO: native review
    project: 'Proyecto', // TODO: native review
    question: 'Pregunta', // TODO: native review
    recommended: 'Recomendado', // TODO: native review
    start: 'Iniciar', // TODO: native review
    updatedAt: 'Actualizado el', // TODO: native review
    user: 'Usuario', // TODO: native review
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
    t000: 'Constructor de flujos',
    t001: 'Nuevo flujo',
    t002: 'módulos de capacidad para arrastrar y combinar',
    t003: 'Plantilla',
    t004: 'Última ejecución',
    t005: 'Completado',
    t006: 'Duración total',
    t007: 'Lienzo',
    t008: 'Comenzar desde plantilla',
    t009: 'Eliminar nodo',
    t010: 'Editar flujo',
    t011: 'Usar',
    t012: 'Ahora',
    t013: 'Requisito',
    t014: 'Conjunto de datos',
    t015: 'Recopilación',
    t016: 'Control de calidad',
    t017: 'Aceptación del solicitante',
    t018: 'Entrega',
    t019: 'Etiquetado',
    t020: 'Limpieza',
    t021: 'Evaluación',
    t022: 'Error al cargar el catálogo de capacidades',
    t023: 'Error al cargar la plantilla',
    t024: 'Plantilla cargada',
    t025: 'Lienzo vacío',
    t026: 'No es necesario guardar',
    t027: 'Ingrese el nombre del flujo',
    t028: 'Flujo guardado',
    t029: 'Error al guardar',
    t030: 'Ejecución completada',
    t031: 'Error de ejecución',
    t032: 'Error al cargar nodos',
    t033: 'Error al eliminar nodos',
  },




  dataFlowTracker: {
    apply: 'Aplicar', // TODO: native review
    clear: 'Limpiar', // TODO: native review
    domainEventsTitle: 'Eventos del dominio', // TODO: native review
    filterByProject: 'Filtrar por proyecto', // TODO: native review
    filterPlaceholder: 'Filtrar eventos…', // TODO: native review
    loadFailed: 'Error al cargar eventos', // TODO: native review
    noEvents: 'Sin eventos', // TODO: native review
    pageSubtitle: 'Línea de tiempo de eventos entre sistemas', // TODO: native review
    pageTitle: 'Rastreador de flujo de datos', // TODO: native review
    pipelineTitle: 'Resumen del pipeline', // TODO: native review
    refresh: 'Actualizar', // TODO: native review
    timelineTitle: 'Línea de tiempo de eventos', // TODO: native review
  },

  form: {
    category: 'Categoría', // TODO: native review
    creator: 'Creador', // TODO: native review
    dueDate: 'Fecha límite', // TODO: native review
    inputRate: 'Tasa de entrada', // TODO: native review
    placeholderName: 'Introducir nombre', // TODO: native review
    placeholderTitle: 'Introducir título', // TODO: native review
    sectionMember: 'Miembros', // TODO: native review
    title: 'Título', // TODO: native review
  },

  menu: {
    contextHistory: 'Recientes', // TODO: native review
    dropdownOptions: 'Opciones', // TODO: native review
    sidebarCleaningManagement: 'Gestión de limpieza', // TODO: native review
    sidebarWorkflow: 'Flujo de trabajo', // TODO: native review
    statusbarReady: 'Listo', // TODO: native review
    statusbarUnsaved: 'Sin guardar', // TODO: native review
    submenuData: 'Datos', // TODO: native review
    tabIncidents: 'Incidencias', // TODO: native review
    tabSchema: 'Esquema', // TODO: native review
  },

  multimodalAgentChat: {
    invoke: 'Invocar', // TODO: native review
  },

  userManagement: {
    createSuccess: 'Usuario creado', // TODO: native review
    roleAdmin: 'Administrador', // TODO: native review
  },

  projectCenter: {
    t000: 'Centro de proyectos', // TODO: native review
    t001: 'Proyecto sin título', // TODO: native review
    t002: 'Resumen del espacio de trabajo del proyecto', // TODO: native review
    t003: 'Buscar proyectos', // TODO: native review
    t004: 'Filtrar por estado', // TODO: native review
    t005: 'Filtrar por prioridad', // TODO: native review
    t006: 'Crear proyecto', // TODO: native review
    t007: 'Editar proyecto', // TODO: native review
  },

  requirementCenter: {
    t000: 'Centro de requisitos', // TODO: native review
    t001: 'Requisito sin título', // TODO: native review
    t002: 'Explorar y gestionar requisitos', // TODO: native review
    t003: 'Buscar requisitos', // TODO: native review
    t004: 'Filtrar por proyecto', // TODO: native review
    t005: 'Filtrar por estado', // TODO: native review
    t006: 'Crear requisito', // TODO: native review
    t007: 'Editar requisito', // TODO: native review
  },

  internalQC: {
    // TODO: native review (round 5 P3 P2 focused)
    t000: 'Control de calidad interno', // TODO: native review
    t001: 'Registro sin título', // TODO: native review
    t002: 'Banco de control de calidad', // TODO: native review
    t003: 'Buscar registros', // TODO: native review
    t004: 'Filtrar por revisor', // TODO: native review
    t005: 'Ejecutar QC', // TODO: native review
    t006: 'Guardar QC', // TODO: native review
    t007: 'Marcar como aprobado', // TODO: native review
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


  },