/**
 * 简体中文文案 (zh-CN)
 * 集中管理 30+ 核心 key, 覆盖 nav/menu/buttons/errors
 * 命名规范: domain.subkey, 支持点分路径与 fallback
 */
window.I18N_ZH_CN = {
  // ===== nav 导航 =====
  'nav.dashboard':     '仪表盘',
  'nav.assets':        '资产管理',
  'nav.requirements':  '需求管理',
  'nav.tasks':         '任务管理',
  'nav.datasets':      '数据集',
  'nav.eval':          '模型评测',
  'nav.stats':         '统计看板',
  'nav.governance':    '数据治理',
  'nav.users':         '用户管理',
  'nav.brand':         '智影数据工场',
  'nav.projects':      '项目管理',
  'nav.canvas':        '画布',
  'nav.quality':       '质量中心',

  // ===== common 通用 =====
  'common.search':     '搜索',
  'common.create':     '创建',
  'common.delete':     '删除',
  'common.edit':       '编辑',
  'common.confirm':    '确认',
  'common.cancel':     '取消',
  'common.save':       '保存',
  'common.submit':     '提交',
  'common.refresh':    '刷新',
  'common.loading':    '加载中...',
  'common.empty':      '暂无数据',
  'common.yes':        '是',
  'common.no':         '否',
  'common.all':        '全部',

  // ===== buttons 操作 =====
  'btn.create_user':     '创建用户',
  'btn.create_asset':    '新增资产',
  'btn.create_requirement':'新建需求',
  'btn.create_task':     '创建任务',
  'btn.create_dataset':  '新建数据集',
  'btn.create_eval':     '创建评测',
  'btn.preview':         '预览',
  'btn.assign':          '分配',
  'btn.review':          '审核',
  'btn.export':          '导出',
  'btn.approve':         '通过',
  'btn.reject':          '驳回',
  'btn.decompose':       '拆解',
  'btn.backup':          '创建备份',
  'btn.lineage':         '查询血缘',
  'btn.badcase':         '查看 BadCase',

  // ===== errors 错误 =====
  'error.network':       '网络错误,请重试',
  'error.unauthorized':  '未授权,请重新登录',
  'error.forbidden':     '权限不足,无法访问',
  'error.not_found':     '资源不存在',
  'error.server':        '服务器错误',
  'error.validation':    '输入参数有误',
  'error.empty_query':   '查询条件不能为空',
  'error.role_required': '此操作需要管理员权限',

  // ===== user & role =====
  'user.online':         '服务在线',
  'user.offline':        '服务离线',
  'user.role_admin':     '系统管理员',
  'user.role_prod_lead': '生产负责人',
  'user.role_qc_lead':   '质检负责人',
  'user.role_annotator': '标注员',
  'user.role_reviewer':  '复核员',
  'user.role_viewer':    '查看者',
  'user.switch_role':    '切换角色',
  'user.switch_lang':    '语言',

  // ===== stats 统计 =====
  'stats.total_users':   '总用户',
  'stats.total_assets':  '总资产',
  'stats.total_datasets':'数据集',
  'stats.total_tasks':   '总任务',
  'stats.completed':     '已完成',
  'stats.storage':       '存储占用',
  'stats.approval_rate': '整体通过率',

  // ===== table column =====
  'col.name':       '名称',
  'col.type':       '类型',
  'col.status':     '状态',
  'col.priority':   '优先级',
  'col.assignee':   '负责人',
  'col.score':      '评分',
  'col.tags':       '标签',
  'col.created_at': '创建时间',
  'col.action':     '操作',
  'col.id':         'ID',
  'col.size':       '大小',
  'col.role':       '角色',

  // ===== P1-C-W1 period / dashboard =====
  'period.today':   '今日',
  'period.week':    '本周',
  'period.month':   '本月',
  'stats.production_count':    '今日生产',
  'stats.avg_quality_score':   '质量评分',
  'stats.tasks_pending':       '待处理任务',
  'stats.daily_active_users':  '日活用户',
  'stats.audit_actions':       '操作审计',
  'stats.current_user':        '当前用户',
  'stats.assets_projects':     '资产 / 项目',
  'dashboard.recent_tasks':    '最近任务',
  'dashboard.recent_tasks_empty': '暂无任务 — 后端 /api/tasks/recent 返回空',
  'dashboard.notifications':   '通知中心',
  'dashboard.notifications_empty': '暂无新通知',

  // ===== P1-C-W1 canvas =====
  'btn.load':       '加载',
  'btn.save':       '保存',
  'btn.render':     '渲染',
  'btn.export':     '导出',
  'btn.upload':     '上传',
  'btn.download':   '下载',
  'btn.tag':        '标签',
  'btn.audit':      '审计',
  'btn.members':    '成员',
  'btn.load_template': '加载模板',
  'canvas.saved_at': '保存时间',
  'canvas.render_task': '渲染任务',
  'canvas.loading':  '画布加载中...',
  'canvas.empty_title': '画布为空',
  'canvas.empty_desc': '点击上方"加载模板"选择起点, 或从节点库拖入节点',
  'canvas.full_editor': '画布编辑器 (R6.5 阶段接 R7 节点库)',

  // ===== P1-C-W1 assets / projects / users =====
  'assets.empty_desc':  '暂无资产 — 点击"上传"创建第一批',
  'projects.empty_desc': '暂无项目 — 点击"创建"开始',
  'projects.no_members': '该项目暂无成员',
  'users.empty_desc':   '暂无用户 — 点击"创建"开始',
  'users.no_audit':     '暂无审计记录',

  // ===== 403 page =====
  '403.title':      '403 无权限访问',
  '403.message':    '您当前的角色无权访问此页面',
  '403.back':       '返回首页',

  // ===== a11y =====
  'a11y.skip':          '跳到主内容',
  'a11y.lang_zh':       '简体中文',
  'a11y.lang_en':       'English',
};
