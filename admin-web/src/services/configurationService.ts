import { api, useMockApi } from '../lib/api'
import { mockApi } from '../mocks/mockApi'
import type { Configuration } from '../types'

export const configurationService = {
  async get(tenantId: string) {
    if (useMockApi) return mockApi.configuration(tenantId)
    const response = await api.get<Configuration>('/admin/v1/configuration')
    return response.data
  },
  async save(tenantId: string, configuration: Configuration) {
    if (useMockApi) return mockApi.saveConfiguration(tenantId, configuration)
    const response = await api.put<Configuration>('/admin/v1/configuration', configuration)
    return response.data
  },
  async publish(tenantId: string, configuration: Configuration) {
    if (useMockApi) return mockApi.publishConfiguration(tenantId, configuration)
    const response = await api.post('/admin/v1/configuration/publish', configuration)
    return response.data
  },
}
