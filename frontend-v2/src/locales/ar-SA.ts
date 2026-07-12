/**
 * ar-SA locale messages.
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
    add: 'إضافة', // TODO: native review
    apply: 'تطبيق', // TODO: native review
    approve: 'موافقة', // TODO: native review
    archived: 'مؤرشف', // TODO: native review
    automatic: 'تلقائي', // TODO: native review
    backup: 'نسخ احتياطي', // TODO: native review
    closed: 'مغلق', // TODO: native review
    decline: 'رفض', // TODO: native review
    deleted: 'محذوف', // TODO: native review
    description: 'الوصف', // TODO: native review
    draft: 'مسودة', // TODO: native review
    export: 'تصدير', // TODO: native review
    goTo: 'انتقال إلى', // TODO: native review
    import: 'استيراد', // TODO: native review
    inProgress: 'قيد التنفيذ', // TODO: native review
    label: 'تسمية', // TODO: native review
    language: 'اللغة', // TODO: native review
    notStarted: 'لم تبدأ', // TODO: native review
    operationFailed: 'فشلت العملية', // TODO: native review
    paused: 'متوقف مؤقتاً', // TODO: native review
    project: 'المشروع', // TODO: native review
    question: 'سؤال', // TODO: native review
    recommended: 'موصى به', // TODO: native review
    start: 'بدء', // TODO: native review
    updatedAt: 'تم التحديث في', // TODO: native review
    user: 'المستخدم', // TODO: native review,
    add: 'إضافة', // TODO: native review
    apply: 'تطبيق', // TODO: native review
    approve: 'موافقة', // TODO: native review
    archived: 'مؤرشف', // TODO: native review
    automatic: 'تلقائي', // TODO: native review
    backup: 'نسخ احتياطي', // TODO: native review
    closed: 'مغلق', // TODO: native review
    decline: 'رفض', // TODO: native review
    deleted: 'محذوف', // TODO: native review
    description: 'الوصف', // TODO: native review
    draft: 'مسودة', // TODO: native review
    export: 'تصدير', // TODO: native review
    goTo: 'انتقال إلى', // TODO: native review
    import: 'استيراد', // TODO: native review
    inProgress: 'قيد التنفيذ', // TODO: native review
    label: 'تسمية', // TODO: native review
    language: 'اللغة', // TODO: native review
    notStarted: 'لم تبدأ', // TODO: native review
    operationFailed: 'فشلت العملية', // TODO: native review
    paused: 'متوقف مؤقتاً', // TODO: native review
    project: 'المشروع', // TODO: native review
    question: 'سؤال', // TODO: native review
    recommended: 'موصى به', // TODO: native review
    start: 'بدء', // TODO: native review
    updatedAt: 'تم التحديث في', // TODO: native review
    user: 'المستخدم', // TODO: native review
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
    t000: 'منشئ سير العمل',
    t001: 'سير عمل جديد',
    t002: 'وحدات قابلة للسحب والدمج',
    t003: 'قالب',
    t004: 'آخر تشغيل',
    t005: 'مكتمل',
    t006: 'الوقت الكلي',
    t007: 'اللوحة',
    t008: 'البدء من قالب',
    t009: 'حذف عقدة',
    t010: 'تحرير سير العمل',
    t011: 'استخدام',
    t012: 'الآن',
    t013: 'متطلب',
    t014: 'مجموعة بيانات',
    t015: 'جمع',
    t016: 'فحص الجودة',
    t017: 'قبول العميل',
    t018: 'تسليم',
    t019: 'وسم',
    t020: 'تنظيف',
    t021: 'تقييم',
    t022: 'فشل تحميل كتالوج القدرات',
    t023: 'فشل تحميل القالب',
    t024: 'تم تحميل القالب',
    t025: 'اللوحة فارغة',
    t026: 'لا حاجة للحفظ',
    t027: 'الرجاء إدخال اسم سير العمل',
    t028: 'تم حفظ سير العمل',
    t029: 'فشل الحفظ',
    t030: 'اكتمل التنفيذ',
    t031: 'فشل التنفيذ',
    t032: 'فشل تحميل العقد',
    t033: 'فشل حذف العقد',
  },




  dataFlowTracker: {
    apply: 'تطبيق', // TODO: native review
    clear: 'مسح', // TODO: native review
    domainEventsTitle: 'أحداث النطاق', // TODO: native review
    filterByProject: 'تصفية حسب المشروع', // TODO: native review
    filterPlaceholder: 'تصفية الأحداث…', // TODO: native review
    loadFailed: 'فشل تحميل الأحداث', // TODO: native review
    noEvents: 'لا توجد أحداث', // TODO: native review
    pageSubtitle: 'خط زمني للأحداث بين الأنظمة في الوقت الفعلي', // TODO: native review
    pageTitle: 'متتبع تدفق البيانات', // TODO: native review
    pipelineTitle: 'نظرة عامة على خط المعالجة', // TODO: native review
    refresh: 'تحديث', // TODO: native review
    timelineTitle: 'الخط الزمني للأحداث', // TODO: native review
  },

  form: {
    category: 'الفئة', // TODO: native review
    creator: 'المنشئ', // TODO: native review
    dueDate: 'تاريخ الاستحقاق', // TODO: native review
    inputRate: 'معدل الإدخال', // TODO: native review
    placeholderName: 'أدخل الاسم', // TODO: native review
    placeholderTitle: 'أدخل العنوان', // TODO: native review
    sectionMember: 'الأعضاء', // TODO: native review
    title: 'العنوان', // TODO: native review
  },

  menu: {
    contextHistory: 'حديثاً', // TODO: native review
    dropdownOptions: 'خيارات', // TODO: native review
    sidebarCleaningManagement: 'إدارة التنظيف', // TODO: native review
    sidebarWorkflow: 'سير العمل', // TODO: native review
    statusbarReady: 'جاهز', // TODO: native review
    statusbarUnsaved: 'غير محفوظ', // TODO: native review
    submenuData: 'البيانات', // TODO: native review
    tabIncidents: 'الحوادث', // TODO: native review
    tabSchema: 'المخطط', // TODO: native review
  },

  multimodalAgentChat: {
    invoke: 'استدعاء', // TODO: native review
  },

  userManagement: {
    createSuccess: 'تم إنشاء المستخدم', // TODO: native review
    roleAdmin: 'مسؤول', // TODO: native review
  },

  projectCenter: {
    t000: 'مركز المشاريع', // TODO: native review
    t001: 'مشروع بدون عنوان', // TODO: native review
    t002: 'نظرة عامة على مساحة عمل المشروع', // TODO: native review
    t003: 'البحث في المشاريع', // TODO: native review
    t004: 'تصفية حسب الحالة', // TODO: native review
    t005: 'تصفية حسب الأولوية', // TODO: native review
    t006: 'إنشاء مشروع', // TODO: native review
    t007: 'تعديل المشروع', // TODO: native review
  },

  requirementCenter: {
    t000: 'مركز المتطلبات', // TODO: native review
    t001: 'متطلب بدون عنوان', // TODO: native review
    t002: 'تصفح وإدارة المتطلبات', // TODO: native review
    t003: 'البحث في المتطلبات', // TODO: native review
    t004: 'تصفية حسب المشروع', // TODO: native review
    t005: 'تصفية حسب الحالة', // TODO: native review
    t006: 'إنشاء متطلب', // TODO: native review
    t007: 'تعديل المتطلب', // TODO: native review
  },

  internalQC: {
    t000: 'مراقبة الجودة الداخلية', // TODO: native review
    t001: 'سجل بدون عنوان', // TODO: native review
    t002: 'ورشة مراقبة الجودة', // TODO: native review
    t003: 'البحث في السجلات', // TODO: native review
    t004: 'تصفية حسب المراجع', // TODO: native review
    t005: 'تشغيل فحص الجودة', // TODO: native review
    t006: 'حفظ فحص الجودة', // TODO: native review
    t007: 'وضع علامة اجتياز', // TODO: native review
    t040: 'حجم العينة',
    t041: 'مستوى الثقة',
    t042: 'هامش الخطأ',
    t043: 'اتفاق المقيّمين',
    t044: 'درجة Kappa',
    t045: 'حد الاختلاف',
    t046: 'قاعدة التحكيم',
    t047: 'تناوب المراجعين',
    t048: 'مراجعة عمياء',
    t049: 'الوقت المستغرق',
    t050: 'دقة التعليق التوضيحي',
    t051: 'معدل التغطية',
    t052: 'الحالات الحدّية',
    t053: 'أنماط الأخطاء',
    t054: 'اتجاهات الجودة',
    t055: 'جلسة المعايرة',
    t056: 'المعيار الذهبي',
    t057: 'اختبار مخفي',
    t058: 'سجل التدقيق',
    t059: 'ملاحظات المراجعين'


  },