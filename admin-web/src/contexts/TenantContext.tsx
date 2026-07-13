import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo, useState } from 'react'
import { setApiTenantId } from '../lib/api'
import { tenantService } from '../services/tenantService'
import { TenantContext } from './TenantContextValue'

const defaultTenantId = 'pmo-vps'
const tenantStorageKey = 'ia-pmo-active-tenant'

export function TenantProvider({ children }: { children: React.ReactNode }) {
  const queryClient = useQueryClient()
  const [activeTenantId, setTenantIdState] = useState(() => window.localStorage.getItem(tenantStorageKey) ?? defaultTenantId)
  const { data: tenants = [], isLoading } = useQuery({
    queryKey: ['tenants'],
    queryFn: tenantService.list,
  })

  const activeTenant = useMemo(
    () => tenants.find((tenant) => tenant.id === activeTenantId) ?? tenants[0],
    [activeTenantId, tenants],
  )

  useEffect(() => {
    if (tenants.length > 0 && !tenants.some((tenant) => tenant.id === activeTenantId)) {
      setTenantIdState(tenants[0].id)
    }
  }, [activeTenantId, tenants])

  useEffect(() => {
    setApiTenantId(activeTenantId)
    window.localStorage.setItem(tenantStorageKey, activeTenantId)
  }, [activeTenantId])

  const value = useMemo(
    () => ({
      tenants,
      activeTenant,
      activeTenantId,
      isLoading,
      setActiveTenantId: (tenantId: string) => {
        setTenantIdState(tenantId)
        setApiTenantId(tenantId)
        window.localStorage.setItem(tenantStorageKey, tenantId)
        void queryClient.invalidateQueries({ predicate: (query) => query.queryKey[0] !== 'tenants' })
      },
    }),
    [activeTenant, activeTenantId, isLoading, queryClient, tenants],
  )

  return <TenantContext.Provider value={value}>{children}</TenantContext.Provider>
}
