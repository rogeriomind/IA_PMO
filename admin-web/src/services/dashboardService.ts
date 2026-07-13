import { api, useMockApi } from '../lib/api'
import { mockApi } from '../mocks/mockApi'
import type { DashboardData } from '../types'

export const dashboardService = {
  async getDashboard(tenantId: string) {
    if (useMockApi) return mockApi.dashboard(tenantId)
    const response = await api.get<DashboardData>('/admin/v1/dashboard')
    return response.data
  },
}
