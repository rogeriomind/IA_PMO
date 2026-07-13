import { api, useMockApi } from '../lib/api'

export const auditService = {
  async list(_tenantId: string) {
    if (useMockApi) {
      return [
        { id: 'aud-1', event: 'Configuração publicada', actor: 'Rogério Mind', createdAt: '19/05/2026 10:31' },
        { id: 'aud-2', event: 'Fluxo testado', actor: 'Matheus Silva', createdAt: '19/05/2026 09:12' },
      ]
    }

    const response = await api.get('/admin/v1/audit')
    return response.data
  },
}
