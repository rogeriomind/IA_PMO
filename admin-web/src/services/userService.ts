import { api, useMockApi } from '../lib/api'
import type { AuthUser } from '../types'

export const userService = {
  async me(): Promise<AuthUser> {
    if (useMockApi) {
      const role = window.localStorage.getItem('ia-pmo-role') as AuthUser['role'] | null
      return {
        name: 'Rogério Mind',
        role: role ?? 'Administrador',
        avatarUrl: 'https://i.pravatar.cc/80?img=12',
      }
    }

    const response = await api.get<AuthUser>('/admin/v1/me')
    return response.data
  },
}
