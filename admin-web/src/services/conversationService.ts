import { api, useMockApi } from '../lib/api'
import { mockApi } from '../mocks/mockApi'
import type { Conversation } from '../types'

export const conversationService = {
  async list(tenantId: string) {
    if (useMockApi) return mockApi.conversations(tenantId)
    const response = await api.get<Conversation[]>('/admin/v1/conversations')
    return response.data
  },
  async get(tenantId: string, threadId: string) {
    if (useMockApi) return mockApi.conversation(tenantId, threadId)
    const response = await api.get<Conversation>(`/admin/v1/conversations/${threadId}`)
    return response.data
  },
}
