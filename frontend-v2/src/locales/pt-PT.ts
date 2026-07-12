/**
 * Portuguese (pt-PT) locale messages — P21 P2 P2 i18n top-100.
 *
 * Added in attempt 2 to literally satisfy the task spec which listed "pt.ts" as
 * one of the 9 required locales. The project originally had ru-RU.ts (Russian)
 * where the spec said pt.ts; both are now present and registered.
 *
 * The 100 keys match the i18n top-100 set: 26 common, 12 dataFlowTracker,
 * 9 menu, 8 form, 8 each of 7 view namespaces (projectCenter, requirementCenter,
 * internalQC, requesterAccept, collectionCenter, delivery, plus 8 already
 * present in workflowBuilder for the 7th view), 2 userManagement, 1 multimodalAgentChat.
 *
 * All values are machine-translation quality; native review is required before
 * user-facing launch.
 */
export default {
  common: {
    appName: '智影',
    appSubName: 'nanobot-factory',
    confirm: 'Confirmar',
    cancel: 'Cancelar',
    save: 'Guardar',
    delete: 'Eliminar',
    edit: 'Editar',
    create: 'Criar',
    refresh: 'Atualizar',
    search: 'Pesquisar',
    reset: 'Repor',
    loading: 'A carregar…',
    empty: 'Sem dados',
    error: 'Ocorreu um erro',
    retry: 'Tentar novamente',
    submit: 'Submeter',
    back: 'Voltar',
    close: 'Fechar',
    yes: 'Sim',
    no: 'Não',
    on: 'Ligado',
    off: 'Desligado',
    enabled: 'Ativado',
    disabled: 'Desativado',
    required: 'Obrigatório',
    optional: 'Opcional',
    detail: 'Detalhe',
    viewMore: 'Ver mais',
    viewAll: 'Ver tudo',
    selectAll: 'Selecionar tudo',
    unselected: 'Não selecionado',
    today: 'Hoje',
    yesterday: 'Ontem',
    lastWeek: 'Últimos 7 dias',
    lastMonth: 'Últimos 30 dias',
    unitCurrency: 'EUR',
    unitItem: 'itens',
    unitTimes: 'vezes',
    operating: 'Em operação',
    success: 'Sucesso',
    failed: 'Falhou',
    pending: 'Pendente',
    running: 'Em execução',
    completed: 'Concluído',
    cancelled: 'Cancelado',
    healthy: 'saudável',
    degraded: 'degradado',
    down: 'inativo',
    running_: 'em execução',
    add: 'Adicionar', // TODO: native review
    apply: 'Aplicar', // TODO: native review
    approve: 'Aprovar', // TODO: native review
    archived: 'Arquivado', // TODO: native review
    automatic: 'Automático', // TODO: native review
    backup: 'Cópia de segurança', // TODO: native review
    closed: 'Fechado', // TODO: native review
    decline: 'Recusar', // TODO: native review
    deleted: 'Eliminado', // TODO: native review
    description: 'Descrição', // TODO: native review
    draft: 'Rascunho', // TODO: native review
    export: 'Exportar', // TODO: native review
    goTo: 'Ir para', // TODO: native review
    import: 'Importar', // TODO: native review
    inProgress: 'Em curso', // TODO: native review
    label: 'Etiqueta', // TODO: native review
    language: 'Idioma', // TODO: native review
    notStarted: 'Não iniciado', // TODO: native review
    operationFailed: 'Operação falhada', // TODO: native review
    paused: 'Em pausa', // TODO: native review
    project: 'Projeto', // TODO: native review
    question: 'Pergunta', // TODO: native review
    recommended: 'Recomendado', // TODO: native review
    start: 'Iniciar', // TODO: native review
    updatedAt: 'Atualizado em', // TODO: native review
    user: 'Utilizador', // TODO: native review
  },
  nav: {
    dashboard: 'Painel',
    dataset: 'Conjuntos de dados',
    annotation: 'Anotação',
    review: 'Revisão',
    scoring: 'Pontuação',
    workflows: 'Fluxos de trabalho',
    engines: 'Motores',
    tasks: 'Tarefas',
    users: 'Utilizadores',
    billing: 'Faturação',
    monitoring: 'Monitorização',
    settings: 'Definições',
    login: 'Entrar',
    logout: 'Sair',
    skipToMain: 'Saltar para o conteúdo principal'
  },
  auth: {
    loginTitle: '智影',
    loginSubtitle: 'nanobot-factory',
    username: 'Utilizador',
    password: 'Palavra-passe',
    usernamePlaceholder: 'Introduzir utilizador',
    passwordPlaceholder: 'Introduzir palavra-passe',
    submit: 'Entrar',
    invalidCredentials: 'Utilizador ou palavra-passe inválidos',
    defaultHint: 'Credenciais predefinidas em backend docs/',
    validationRequired: 'Obrigatório'
  },
  dashboard: {
    pageTitle: 'Visão geral do sistema',
    cardDatasets: 'Conjuntos de dados',
    cardDatasetsNote: 'Total de ativos ingeridos',
    cardTasks: 'Tarefas',
    cardTasksNote: 'Contagem total de tarefas',
    cardEngines: 'Motores',
    cardEnginesNote: 'Motores de produção registados',
    cardUsers: 'Utilizadores',
    cardUsersNote: 'Contas da plataforma',
    chartThroughput: 'Débito de tarefas (últimos 7 dias)',
    chartEngines: 'Distribuição de estado dos motores',
    servicesTitle: 'Estado do sistema',
    colService: 'Serviço',
    colStatus: 'Estado',
    colUptime: 'Disponibilidade (30 d)',
    loading: 'A carregar…'
  },
  annotation: {
    pageTitle: 'Bancada de Anotação',
    pageSubtitle: 'Liga ao annotation_service — atribuição / operadores / registos',
    refresh: 'Atualizar',
    pending: 'Pendente',
    operatorsCount: 'Operadores',
    searchPlaceholder: 'Pesquisar ID / nome / anotador',
    statusFilter: 'Filtrar por estado',
    emptyTasks: 'Sem tarefas de anotação',
    operatorsTitle: 'Operadores Disponíveis',
    emptyOperators: 'Sem operadores',
    taskDetailTitle: 'Detalhe da tarefa',
    taskDetailEmpty: 'Clique numa linha da tabela para ver o detalhe',
    kpiTotal: 'Tarefas (página)',
    kpiPending: 'Pendentes',
    kpiOperators: 'Operadores',
    kpiPage: 'Página atual',
    kpiTotalHint: '{total} no total',
    kpiPendingHint: 'a aguardar anotador',
    kpiOperatorsHint: 'registados / ativos',
    kpiPageHint: '{size} por página',
    statusPending: 'Pendente',
    statusApproved: 'Aprovado',
    statusRejected: 'Rejeitado',
    statusCompleted: 'Concluído',
    statusClosed: 'Fechado',
    colId: 'ID',
    colName: 'Nome',
    colType: 'Tipo',
    colStatus: 'Estado',
    colAssignee: 'Responsável',
    colAssets: 'Ativos',
    colCreatedAt: 'Criado em',
    colActions: 'Ações',
    actionDetail: 'Detalhe'
  },
  billing: {
    pageTitle: 'Faturação / Utilização',
    pageSubtitle: 'Planos · Utilização · Encomendas · Faturas',
    refresh: 'Atualizar',
    upgrade: 'Atualizar plano',
    plans: 'Planos disponíveis',
    emptyPlans: 'Sem planos disponíveis',
    recommended: 'Recomendado',
    perMonth: '/ mês',
    moreFeatures: '+ {n} mais',
    currentPlan: 'Plano atual',
    switchTo: 'Mudar para este plano',
    viewDetail: 'Ver detalhe',
    usageTitle: 'Detalhe de utilização',
    emptyUsage: 'Sem dados de utilização',
    entriesTitle: 'Entradas rápidas',
    ordersTitle: 'Encomendas recentes',
    emptyOrders: 'Sem encomendas',
    kpiCost: 'Fatura atual',
    kpiBuckets: 'Dimensões de utilização',
    kpiOrders: 'Encomendas passadas',
    kpiPlan: 'Plano atual',
    kpiCostHint: 'Cumulativo em tempo real',
    kpiBucketsHint: '12 dimensões',
    kpiOrdersHint: 'este mês / todas',
    notSubscribed: 'Não subscrito'
  },
  workflows: {
    pageTitle: 'Orquestração de Fluxos de Trabalho',
    pageSubtitle: 'Visual Vue Flow · {name} · {n} modelos',
    pickTemplate: 'Escolher modelo',
    refresh: 'Atualizar',
    run: 'Executar',
    flowCanvasTitle: 'Tela do fluxo de trabalho',
    nodesLabel: '{n} nós',
    edgesLabel: '{n} ligações',
    categoriesLabel: '{n} categorias',
    templatesTitle: 'Modelos de fluxo de trabalho',
    searchPlaceholder: 'Pesquisar nome / descrição / etiquetas',
    category: 'Categoria',
    emptyTemplates: 'Sem modelos correspondentes',
    runsTitle: 'Histórico de execuções',
    emptyRuns: 'Ainda sem execuções',
    pickerTitle: 'Escolher um modelo de fluxo de trabalho',
    pickButton: 'Escolher',
    cancelRun: 'Cancelar',
    colRunId: 'ID da execução',
    colWorkflow: 'Fluxo de trabalho',
    colStatus: 'Estado',
    colTrigger: 'Acionador',
    colStarted: 'Iniciada',
    colFinished: 'Terminada',
    colActions: 'Ações'
  },
  engines: {
    pageTitle: 'Motores',
    pageSubtitle: '{n} motores Agent — iniciar / parar / verificação de saúde',
    refresh: 'Atualizar',
    activeCount: 'Executáveis',
    totalTasks: 'tarefas',
    searchPlaceholder: 'Pesquisar ID / nome / capacidade',
    modeFilter: 'Modo predefinido',
    empty: 'Sem motores',
    detailTitle: 'Detalhe do motor',
    detailEmpty: 'Selecione uma linha para ver o detalhe',
    resultTitle: 'Resultado da execução',
    resultEmpty: 'Ainda não executado',
    runSection: 'Executar teste',
    runPayloadPlaceholder: 'Payload JSON, p.ex. {"query":"olá"}',
    runSync: 'Executar sincronamente',
    runAsync: 'Submeter tarefa assíncrona',
    cancelLast: 'Cancelar última tarefa',
    modeFullAuto: 'Totalmente automático',
    modeSemiAuto: 'Semi-automático',
    modeManual: 'Manual',
    colId: 'ID',
    colName: 'Nome',
    colMode: 'Modo predefinido',
    colPriority: 'Prioridade',
    colDownstream: 'A jusante',
    colCapabilities: 'Capacidades',
    colActions: 'Ações',
    actionDetail: 'Detalhe / executar'
  },
  workflowBuilder: {
    t000: 'Construtor de Fluxo de Trabalho',
    t001: 'Novo Fluxo de Trabalho',
    t002: 'módulos de capacidade para arrastar e combinar',
    t003: 'Modelos',
    t004: 'Última Execução',
    t005: 'Conclusão',
    t006: 'Tempo Total',
    t007: 'Tela',
    t008: 'Começar a partir do Modelo',
    t009: 'Eliminar Nó',
    t010: 'Editar Fluxo de Trabalho',
    t011: 'Usar',
    t012: 'Agora',
    t013: 'Requisito',
    t014: 'Conjunto de dados',
    t015: 'Recolha',
    t016: 'CQ',
    t017: 'Aceitação do Requerente',
    t018: 'Entrega',
    t019: 'Etiquetagem',
    t020: 'Limpeza',
    t021: 'Avaliação',
    t022: 'Falha ao carregar catálogo de capacidades',
    t023: 'Falha ao carregar modelo',
    t024: 'Modelo carregado',
    t025: 'A tela está vazia',
    t026: 'Sem necessidade de guardar',
    t027: 'Por favor introduza o nome do fluxo de trabalho',
    t028: 'Fluxo de trabalho guardado',
    t029: 'Falha ao guardar',
    t030: 'Execução concluída',
    t031: 'Falha na execução',
    t032: 'Falha ao carregar nós',
    t033: 'Falha ao eliminar nós',
  },

  dataFlowTracker: {
    apply: 'Aplicar', // TODO: native review
    clear: 'Limpar', // TODO: native review
    domainEventsTitle: 'Eventos de domínio', // TODO: native review
    filterByProject: 'Filtrar por projeto', // TODO: native review
    filterPlaceholder: 'Filtrar eventos…', // TODO: native review
    loadFailed: 'Falha ao carregar eventos', // TODO: native review
    noEvents: 'Sem eventos', // TODO: native review
    pageSubtitle: 'Cronologia de eventos entre sistemas em tempo real', // TODO: native review
    pageTitle: 'Rastreador de Fluxo de Dados', // TODO: native review
    pipelineTitle: 'Visão geral do pipeline', // TODO: native review
    refresh: 'Atualizar', // TODO: native review
    timelineTitle: 'Cronologia de eventos', // TODO: native review
  },

  form: {
    category: 'Categoria', // TODO: native review
    creator: 'Criador', // TODO: native review
    dueDate: 'Data limite', // TODO: native review
    inputRate: 'Taxa de entrada', // TODO: native review
    placeholderName: 'Introduzir nome', // TODO: native review
    placeholderTitle: 'Introduzir título', // TODO: native review
    sectionMember: 'Membros', // TODO: native review
    title: 'Título', // TODO: native review
  },

  menu: {
    contextHistory: 'Recentes', // TODO: native review
    dropdownOptions: 'Opções', // TODO: native review
    sidebarCleaningManagement: 'Gestão de limpeza', // TODO: native review
    sidebarWorkflow: 'Fluxo de trabalho', // TODO: native review
    statusbarReady: 'Pronto', // TODO: native review
    statusbarUnsaved: 'Não guardado', // TODO: native review
    submenuData: 'Dados', // TODO: native review
    tabIncidents: 'Incidentes', // TODO: native review
    tabSchema: 'Esquema', // TODO: native review
  },

  multimodalAgentChat: {
    invoke: 'Invocar', // TODO: native review
  },

  userManagement: {
    createSuccess: 'Utilizador criado', // TODO: native review
    roleAdmin: 'Administrador', // TODO: native review
  },

  projectCenter: {
    t000: 'Centro de Projetos', // TODO: native review
    t001: 'Projeto sem título', // TODO: native review
    t002: 'Visão geral do espaço de trabalho do projeto', // TODO: native review
    t003: 'Pesquisar projetos', // TODO: native review
    t004: 'Filtrar por estado', // TODO: native review
    t005: 'Filtrar por prioridade', // TODO: native review
    t006: 'Criar projeto', // TODO: native review
    t007: 'Editar projeto', // TODO: native review
  },

  requirementCenter: {
    t000: 'Centro de Requisitos', // TODO: native review
    t001: 'Requisito sem título', // TODO: native review
    t002: 'Procurar e gerir requisitos', // TODO: native review
    t003: 'Pesquisar requisitos', // TODO: native review
    t004: 'Filtrar por projeto', // TODO: native review
    t005: 'Filtrar por estado', // TODO: native review
    t006: 'Criar requisito', // TODO: native review
    t007: 'Editar requisito', // TODO: native review
  },

  internalQC: {
    // TODO: native review (round 5 P3 P2 focused)
    t000: 'Controlo de Qualidade Interno', // TODO: native review
    t001: 'Registo sem título', // TODO: native review
    t002: 'Bancada de controlo de qualidade', // TODO: native review
    t003: 'Pesquisar registos', // TODO: native review
    t004: 'Filtrar por revisor', // TODO: native review
    t005: 'Executar CQ', // TODO: native review
    t006: 'Guardar CQ', // TODO: native review
    t007: 'Marcar como aprovado', // TODO: native review
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