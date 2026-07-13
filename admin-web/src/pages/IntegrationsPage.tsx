import { useMutation, useQuery } from '@tanstack/react-query'
import { CheckCircle2, PlugZap } from 'lucide-react'
import { Badge } from '../components/common/Badge'
import { Button } from '../components/common/Button'
import { Card } from '../components/common/Card'
import { PageHeader } from '../components/common/PageHeader'
import { PageState } from '../components/common/PageState'
import { useTenant } from '../hooks/useTenant'
import { integrationService } from '../services/integrationService'
import type { IntegrationStatus } from '../types'

const statusTone: Record<IntegrationStatus, 'green' | 'yellow' | 'red' | 'neutral'> = {
  Conectado: 'green',
  Desconectado: 'neutral',
  Erro: 'red',
  'Em configuração': 'yellow',
}

export function IntegrationsPage() {
  const { activeTenant, activeTenantId } = useTenant()
  const integrationsQuery = useQuery({
    queryKey: ['integrations', activeTenantId],
    queryFn: () => integrationService.list(activeTenantId),
    enabled: Boolean(activeTenantId),
  })
  const testMutation = useMutation({
    mutationFn: (id: string) => integrationService.test(activeTenantId, id),
  })

  if (!activeTenant || integrationsQuery.isLoading) return <PageState state="loading" />
  if (activeTenant.status === 'suspended') return <PageState state="tenant-suspended" />
  if (integrationsQuery.isError) return <PageState state="error" onRetry={() => void integrationsQuery.refetch()} />

  const integrations = integrationsQuery.data ?? []
  const unavailable = integrations.find((integration) => integration.status === 'Erro')

  return (
    <div>
      <PageHeader title="Integrações" description="Status operacional das conexões administrativas e MCP." />
      {unavailable ? (
        <div className="mb-4">
          <PageState state="integration-unavailable" />
        </div>
      ) : null}
      <div className="grid gap-4 lg:grid-cols-2 xl:grid-cols-3">
        {integrations.map((integration) => (
          <Card key={integration.id} className="p-5">
            <div className="flex items-start justify-between gap-4">
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-[#F2EDFF] text-[#6D3DF5]">
                  {integration.status === 'Conectado' ? <CheckCircle2 className="h-5 w-5" aria-hidden="true" /> : <PlugZap className="h-5 w-5" aria-hidden="true" />}
                </div>
                <div>
                  <h2 className="font-bold text-[#171A24]">{integration.name}</h2>
                  <p className="text-sm text-[#667085]">ID: {integration.id}</p>
                </div>
              </div>
              <Badge tone={statusTone[integration.status]}>{integration.status}</Badge>
            </div>
            <dl className="mt-5 grid gap-3 text-sm">
              <div>
                <dt className="text-[#667085]">Última verificação</dt>
                <dd className="font-semibold text-[#171A24]">{integration.lastCheck}</dd>
              </div>
              <div>
                <dt className="text-[#667085]">Latência</dt>
                <dd className="font-semibold text-[#171A24]">{integration.latency}</dd>
              </div>
              {integration.recentError ? (
                <div>
                  <dt className="text-[#667085]">Erro recente</dt>
                  <dd className="font-semibold text-[#DC2626]">{integration.recentError}</dd>
                </div>
              ) : null}
            </dl>
            <Button className="mt-5" onClick={() => testMutation.mutate(integration.id)} disabled={testMutation.isPending}>
              Testar
            </Button>
          </Card>
        ))}
      </div>
    </div>
  )
}
