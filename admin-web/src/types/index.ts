export type TenantStatus = 'active' | 'suspended'

export type Tenant = {
  id: string
  name: string
  slug: string
  status: TenantStatus
  environment: 'production' | 'staging' | 'demo'
  brandColor: string
}

export type AuthUser = {
  name: string
  role: 'Administrador' | 'Operador' | 'Leitor'
  avatarUrl: string
}

export type Channel = 'WhatsApp' | 'Telegram' | 'Web Chat' | 'Email'
export type Priority = 'Alta' | 'Média' | 'Baixa'
export type ActionStatus = 'Aguardando confirmação' | 'Confirmada' | 'Cancelada'

export type Kpi = {
  id: string
  title: string
  value: string
  comparison: string
  positive: boolean
  sparkline: number[]
}

export type DashboardEvent = {
  id: string
  kind: 'conversation' | 'action' | 'integration' | 'error' | 'configuration'
  title: string
  description: string
  occurredAt: string
}

export type PendingAction = {
  id: string
  description: string
  thread: string
  createdAt: string
  priority: Priority
  status: ActionStatus
}

export type PlatformMetric = {
  name: Channel
  value: number
  color: string
}

export type DashboardData = {
  kpis: Kpi[]
  conversationsByDay: Array<{ day: string; conversas: number }>
  events: DashboardEvent[]
  pendingActions: PendingAction[]
  platforms: PlatformMetric[]
}

export type ActionCard = {
  id: string
  title: string
  priority: Priority
  deadline: string
  owner: string
  status: ActionStatus
}

export type Message = {
  id: string
  author: 'user' | 'agent'
  body: string
  createdAt: string
  deliveryStatus?: 'enviado' | 'entregue' | 'lido'
  structured?: Array<{ label: string; value: string; tone?: 'success' | 'warning' | 'danger' }>
  action?: ActionCard
}

export type Conversation = {
  threadId: string
  tenantId: string
  title: string
  channel: Channel
  status: 'Ativa' | 'Pendente' | 'Encerrada'
  user: string
  project: string
  startedAt: string
  lastActivity: string
  tags: string[]
  pendingActions: number
  estimatedCost: string
  tokens: number
  isMine: boolean
  unreadCount: number
  lastMessage: string
  messages: Message[]
}

export type LangGraphNodeType =
  | 'start-end'
  | 'llm'
  | 'mcp'
  | 'decision'
  | 'audit'
  | 'human'
  | 'error'
  | 'context'

export type ExecutionStatus =
  | 'Não executado'
  | 'Executando'
  | 'Sucesso'
  | 'Falha'
  | 'Aguardando confirmação'
  | 'Ignorado'

export type LangGraphNodeData = {
  label: string
  nodeType: LangGraphNodeType
  description: string
  model?: string
  prompt?: string
  temperature?: number
  maxTokens?: number
  tool?: string
  timeout?: string
  retries?: number
  entryConditions: string[]
  nextRoutes: string[]
  lastRuns: string[]
  successRate: string
  averageTime: string
  averageCost: string
  status: ExecutionStatus
}

export type LangGraphExecution = {
  id: string
  label: string
  status: ExecutionStatus
  path: string[]
  intent: string
  confidence: number
  nodesExecuted: number
  mcp: string
  response: string
  tokens: number
  cost: string
  durationMs: number
  errors: string[]
}

export type IntegrationStatus = 'Conectado' | 'Desconectado' | 'Erro' | 'Em configuração'

export type Integration = {
  id: string
  name: string
  status: IntegrationStatus
  lastCheck: string
  latency: string
  recentError?: string
}

export type ToolPolicy = {
  name: string
  enabled: boolean
  type: 'read' | 'write'
  requiresConfirmation: boolean
  roles: string[]
  timeout: number
  retries: number
}

export type ChannelConfiguration = {
  name: Channel
  status: IntegrationStatus
  tokenPreview: string
}

export type Configuration = {
  company: {
    name: string
    legalName: string
    document: string
    slug: string
    status: TenantStatus
    language: string
    timezone: string
    environment: string
  }
  identity: {
    primaryColor: string
    secondaryColor: string
    assistantName: string
    tone: string
    welcomeMessage: string
  }
  model: {
    provider: 'DeepSeek' | 'OpenAI'
    model: string
    temperature: number
    topP: number
    maxTokens: number
    thinkingEnabled: boolean
    confidenceThreshold: number
  }
  systemPrompt: string
  policies: {
    requireConfirmation: boolean
    allowCreate: boolean
    allowUpdate: boolean
    allowMove: boolean
    allowComments: boolean
    maxActions: number
    confirmationExpiration: number
    memoryRetention: number
    optionLimit: number
    allowedIntents: string[]
  }
  tools: ToolPolicy[]
  channels: ChannelConfiguration[]
  integrations: Integration[]
  observability: {
    langfuseEnabled: boolean
    samplingRate: number
    logPrompts: boolean
    logResponses: boolean
    logCost: boolean
    retentionDays: number
    dataMasking: boolean
  }
  parameters: {
    debounce: number
    rateLimit: number
    rateLimitWindow: number
    retries: number
    queueLock: number
    workerSleep: number
    sessionTtl: number
    pendingActionTtl: number
    selectionTtl: number
  }
  security: {
    roles: string[]
    internalTokens: string[]
    secrets: string[]
    lastRotation: string
    activeSessions: number
    ipAllowlist: string[]
    auditEnabled: boolean
  }
}

export type AppViewState =
  | 'loading'
  | 'empty'
  | 'error'
  | 'success'
  | 'unauthorized'
  | 'forbidden'
  | 'tenant-suspended'
  | 'integration-unavailable'
