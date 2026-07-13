import { api, useMockApi } from '../lib/api'
import { mockApi } from '../mocks/mockApi'
import type { PendingAction } from '../types'

export const pendingActionService = {
  async list(tenantId: string) {
    if (useMockApi) return mockApi.pendingActions(tenantId)
    const response = await api.get<PendingAction[]>('/admin/v1/pending-actions')
    return response.data
  },
}
