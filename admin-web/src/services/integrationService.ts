import { api, useMockApi } from '../lib/api'
import { mockApi } from '../mocks/mockApi'
import type { Integration } from '../types'

export const integrationService = {
  async list(_tenantId: string) {
    if (useMockApi) return mockApi.integrations()
    const response = await api.get<Integration[]>('/admin/v1/integrations')
    return response.data
  },
  async test(_tenantId: string, id: string) {
    if (useMockApi) return { id, ok: id !== 'redis' }
    const response = await api.post(`/admin/v1/integrations/${id}/test`)
    return response.data
  },
}
