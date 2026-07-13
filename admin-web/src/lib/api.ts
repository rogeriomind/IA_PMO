import axios from 'axios'

const DEFAULT_TENANT_ID = 'pmo-vps'
const tenantStorageKey = 'ia-pmo-active-tenant'

let activeTenantId =
  typeof window === 'undefined'
    ? DEFAULT_TENANT_ID
    : window.localStorage.getItem(tenantStorageKey) ?? DEFAULT_TENANT_ID

export const useMockApi = import.meta.env.MODE === 'test' || import.meta.env.VITE_USE_MOCK_API === 'true'

export function setApiTenantId(tenantId: string) {
  activeTenantId = tenantId
}

function requestId() {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return crypto.randomUUID()
  }

  return `req-${Date.now()}-${Math.random().toString(16).slice(2)}`
}

export const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? '/api',
  timeout: 20_000,
})

api.interceptors.request.use((config) => {
  const token = typeof window === 'undefined' ? undefined : window.sessionStorage.getItem('ia-pmo-token')
  const correlationId =
    typeof window === 'undefined'
      ? requestId()
      : window.sessionStorage.getItem('ia-pmo-correlation-id') ?? requestId()

  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  } else if (useMockApi) {
    config.headers.Authorization = 'Bearer mock-admin-session'
  }
  config.headers['X-Tenant-ID'] = activeTenantId
  config.headers['X-Request-ID'] = requestId()
  config.headers['X-Correlation-ID'] = correlationId

  return config
})
