import { createContext } from 'react'
import type { Tenant } from '../types'

export type TenantContextValue = {
  tenants: Tenant[]
  activeTenant?: Tenant
  activeTenantId: string
  setActiveTenantId: (tenantId: string) => void
  isLoading: boolean
}

export const TenantContext = createContext<TenantContextValue | undefined>(undefined)
