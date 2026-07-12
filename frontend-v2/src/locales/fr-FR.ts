/**
 * fr-FR locale messages.
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
    add: 'Ajouter', // TODO: native review
    apply: 'Appliquer', // TODO: native review
    approve: 'Approuver', // TODO: native review
    archived: 'Archivé', // TODO: native review
    automatic: 'Automatique', // TODO: native review
    backup: 'Sauvegarder', // TODO: native review
    closed: 'Fermé', // TODO: native review
    decline: 'Refuser', // TODO: native review
    deleted: 'Supprimé', // TODO: native review
    description: 'Description', // TODO: native review
    draft: 'Brouillon', // TODO: native review
    export: 'Exporter', // TODO: native review
    goTo: 'Aller à', // TODO: native review
    import: 'Importer', // TODO: native review
    inProgress: 'En cours', // TODO: native review
    label: 'Étiquette', // TODO: native review
    language: 'Langue', // TODO: native review
    notStarted: 'Non démarré', // TODO: native review
    operationFailed: 'Échec de l\'opération', // TODO: native review
    paused: 'En pause', // TODO: native review
    project: 'Projet', // TODO: native review
    question: 'Question', // TODO: native review
    recommended: 'Recommandé', // TODO: native review
    start: 'Démarrer', // TODO: native review
    updatedAt: 'Mis à jour le', // TODO: native review
    user: 'Utilisateur', // TODO: native review,
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
    t000: 'Constructeur de flux',
    t001: 'Nouveau flux',
    t002: 'modules de capacité à glisser-déposer',
    t003: 'Modèle',
    t004: 'Dernière exécution',
    t005: 'Terminé',
    t006: 'Durée totale',
    t007: 'Canevas',
    t008: 'Démarrer à partir d\'un modèle',
    t009: 'Supprimer le nœud',
    t010: 'Modifier le flux',
    t011: 'Utiliser',
    t012: 'Maintenant',
    t013: 'Exigence',
    t014: 'Jeu de données',
    t015: 'Collecte',
    t016: 'Contrôle qualité',
    t017: 'Acceptation client',
    t018: 'Livraison',
    t019: 'Étiquetage',
    t020: 'Nettoyage',
    t021: 'Évaluation',
    t022: 'Échec du chargement du catalogue de capacités',
    t023: 'Échec du chargement du modèle',
    t024: 'Modèle chargé',
    t025: 'Canevas vide',
    t026: 'Aucune sauvegarde nécessaire',
    t027: 'Veuillez saisir un nom de flux',
    t028: 'Flux enregistré',
    t029: 'Échec de l\'enregistrement',
    t030: 'Exécution terminée',
    t031: 'Échec de l\'exécution',
    t032: 'Échec du chargement des nœuds',
    t033: 'Échec de la suppression des nœuds',
  },




  dataFlowTracker: {
    apply: 'Appliquer', // TODO: native review
    clear: 'Effacer', // TODO: native review
    domainEventsTitle: 'Événements du domaine', // TODO: native review
    filterByProject: 'Filtrer par projet', // TODO: native review
    filterPlaceholder: 'Filtrer les événements…', // TODO: native review
    loadFailed: 'Échec du chargement des événements', // TODO: native review
    noEvents: 'Aucun événement', // TODO: native review
    pageSubtitle: 'Chronologie des événements inter-systèmes', // TODO: native review
    pageTitle: 'Suivi du flux de données', // TODO: native review
    pipelineTitle: 'Aperçu du pipeline', // TODO: native review
    refresh: 'Actualiser', // TODO: native review
    timelineTitle: 'Chronologie des événements', // TODO: native review
  },

  form: {
    category: 'Catégorie', // TODO: native review
    creator: 'Créateur', // TODO: native review
    dueDate: 'Date d\'échéance', // TODO: native review
    inputRate: 'Débit d\'entrée', // TODO: native review
    placeholderName: 'Saisir le nom', // TODO: native review
    placeholderTitle: 'Saisir le titre', // TODO: native review
    sectionMember: 'Membres', // TODO: native review
    title: 'Titre', // TODO: native review
  },

  menu: {
    contextHistory: 'Récents', // TODO: native review
    dropdownOptions: 'Options', // TODO: native review
    sidebarCleaningManagement: 'Gestion du nettoyage', // TODO: native review
    sidebarWorkflow: 'Flux de travail', // TODO: native review
    statusbarReady: 'Prêt', // TODO: native review
    statusbarUnsaved: 'Non enregistré', // TODO: native review
    submenuData: 'Données', // TODO: native review
    tabIncidents: 'Incidents', // TODO: native review
    tabSchema: 'Schéma', // TODO: native review
  },

  multimodalAgentChat: {
    invoke: 'Invoquer', // TODO: native review
  },

  userManagement: {
    createSuccess: 'Utilisateur créé', // TODO: native review
    roleAdmin: 'Administrateur', // TODO: native review
  },

  projectCenter: {
    t000: 'Centre de projets', // TODO: native review
    t001: 'Projet sans titre', // TODO: native review
    t002: 'Vue d\'ensemble de l\'espace de travail', // TODO: native review
    t003: 'Rechercher des projets', // TODO: native review
    t004: 'Filtrer par statut', // TODO: native review
    t005: 'Filtrer par priorité', // TODO: native review
    t006: 'Créer un projet', // TODO: native review
    t007: 'Modifier le projet', // TODO: native review
  },

  requirementCenter: {
    t000: 'Centre des exigences', // TODO: native review
    t001: 'Exigence sans titre', // TODO: native review
    t002: 'Parcourir et gérer les exigences', // TODO: native review
    t003: 'Rechercher des exigences', // TODO: native review
    t004: 'Filtrer par projet', // TODO: native review
    t005: 'Filtrer par statut', // TODO: native review
    t006: 'Créer une exigence', // TODO: native review
    t007: 'Modifier l\'exigence', // TODO: native review
  },

  internalQC: {
    // TODO: native review (round 5 P3 P2 focused)
    t000: 'Contrôle qualité interne', // TODO: native review
    t001: 'Enregistrement sans titre', // TODO: native review
    t002: 'Atelier de contrôle qualité', // TODO: native review
    t003: 'Rechercher des enregistrements', // TODO: native review
    t004: 'Filtrer par réviseur', // TODO: native review
    t005: 'Exécuter le CQ', // TODO: native review
    t006: 'Enregistrer le CQ', // TODO: native review
    t007: 'Marquer comme réussi', // TODO: native review
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
