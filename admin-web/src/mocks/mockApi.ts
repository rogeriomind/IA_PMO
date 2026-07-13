import {
  configurationByTenant,
  conversationsByTenant,
  dashboardByTenant,
  integrations,
  langGraphExecutions,
  langGraphNodes,
  tenants,
} from './data'
import type { Configuration, LangGraphExecution } from '../types'

const clone = <T>(value: T): T => structuredClone(value)

const delay = async <T>(value: T) => Promise.resolve(clone(value))

export const mockApi = {
  tenants: () => delay(tenants),
  tenant: (tenantId: string) => delay(tenants.find((tenant) => tenant.id === tenantId) ?? tenants[0]),
  dashboard: (tenantId: string) => delay(dashboardByTenant[tenantId] ?? dashboardByTenant['acme-corp']),
  pendingActions: (tenantId: string) => delay(dashboardByTenant[tenantId]?.pendingActions ?? []),
  conversations: (tenantId: string) => delay(conversationsByTenant[tenantId] ?? []),
  conversation: async (tenantId: string, threadId: string) => {
    const conversations = conversationsByTenant[tenantId] ?? []
    return delay(conversations.find((conversation) => conversation.threadId === threadId) ?? conversations[0])
  },
  langGraph: () => delay({ nodes: langGraphNodes, executions: langGraphExecutions }),
  langGraphExecutions: () => delay(langGraphExecutions),
  runLangGraphTest: async (): Promise<LangGraphExecution> =>
    delay({
      id: `exec-test-${Date.now()}`,
      label: 'Teste manual de fluxo',
      status: 'Sucesso',
      path: ['start', 'tenant_context', 'memory', 'classify', 'intent', 'extract_entities', 'validate_fields', 'resolve_owner', 'prepare_action', 'confirm', 'create_task', 'audit', 'end'],
      intent: 'criar_tarefa',
      confidence: 0.93,
      nodesExecuted: 13,
      mcp: 'board_create_task',
      response: 'Fluxo executado em modo teste. Nenhuma escrita real foi enviada.',
      tokens: 2110,
      cost: 'US$ 0.05',
      durationMs: 1840,
      errors: [],
    }),
  configuration: (tenantId: string) => delay(configurationByTenant[tenantId] ?? configurationByTenant['acme-corp']),
  saveConfiguration: (_tenantId: string, configuration: Configuration) => delay(configuration),
  publishConfiguration: (_tenantId: string, configuration: Configuration) =>
    delay({ version: 'v2.3.2', publishedAt: '19/05/2026 11:05', configuration }),
  integrations: () => delay(integrations),
}
