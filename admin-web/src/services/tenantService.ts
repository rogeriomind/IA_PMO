import { api, useMockApi } from '../lib/api'
import { mockApi } from '../mocks/mockApi'
import type { Tenant } from '../types'

export const tenantService = {
  async list() {
    if (useMockApi) return mockApi.tenants()
    const response = await api.get<Tenant[]>('/admin/v1/tenants')
    return response.data
  },
  async get(tenantId: string) {
    if (useMockApi) return mockApi.tenant(tenantId)
    const response = await api.get<Tenant>(`/admin/v1/tenants/${tenantId}`)
    return response.data
  },
}
