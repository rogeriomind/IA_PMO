import { api, useMockApi } from '../lib/api'
import { mockApi } from '../mocks/mockApi'
import type { LangGraphExecution, LangGraphNodeData } from '../types'

export type LangGraphPayload = {
  nodes: Record<string, LangGraphNodeData>
  executions: LangGraphExecution[]
}

export type LangGraphTestInput = {
  tenant: string
  user: string
  channel: string
  message: string
  project: string
  roles: string
}

export const langGraphService = {
  async getGraph(_tenantId: string) {
    if (useMockApi) return mockApi.langGraph()
    const response = await api.get<LangGraphPayload>('/admin/v1/langgraph')
    return response.data
  },
  async getExecutions(_tenantId: string) {
    if (useMockApi) return mockApi.langGraphExecutions()
    const response = await api.get<LangGraphExecution[]>('/admin/v1/langgraph/executions')
    return response.data
  },
  async runTest(_tenantId: string, input: LangGraphTestInput) {
    if (useMockApi) return mockApi.runLangGraphTest()
    const response = await api.post<LangGraphExecution>('/admin/v1/langgraph/test', input)
    return response.data
  },
}
