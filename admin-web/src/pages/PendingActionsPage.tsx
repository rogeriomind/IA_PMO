import { useQuery } from '@tanstack/react-query'
import { Badge } from '../components/common/Badge'
import { Button } from '../components/common/Button'
import { Card } from '../components/common/Card'
import { PageHeader } from '../components/common/PageHeader'
import { PageState } from '../components/common/PageState'
import { useTenant } from '../hooks/useTenant'
import { pendingActionService } from '../services/pendingActionService'
import type { Priority } from '../types'

const priorityTone: Record<Priority, 'red' | 'yellow' | 'green'> = {
  Alta: 'red',
  Média: 'yellow',
  Baixa: 'green',
}

export function PendingActionsPage() {
  const { activeTenant, activeTenantId } = useTenant()
  const pendingActionsQuery = useQuery({
    queryKey: ['pending-actions', activeTenantId],
    queryFn: () => pendingActionService.list(activeTenantId),
    enabled: Boolean(activeTenantId),
  })

  if (!activeTenant || pendingActionsQuery.isLoading) return <PageState state="loading" />
  if (activeTenant.status === 'suspended') return <PageState state="tenant-suspended" />
  if (pendingActionsQuery.isError) return <PageState state="error" onRetry={() => void pendingActionsQuery.refetch()} />

  const pendingActions = pendingActionsQuery.data ?? []

  return (
    <div>
      <PageHeader title="Ações Pendentes" description="Confirme, cancele ou acompanhe ações que dependem de decisão humana." />
      <Card className="overflow-hidden">
        <table className="w-full min-w-[760px] text-left text-sm">
          <thead className="bg-[#F8F9FC] text-xs uppercase tracking-wide text-[#667085]">
            <tr>
              <th className="px-5 py-3">Descrição</th>
              <th className="px-5 py-3">Thread</th>
              <th className="px-5 py-3">Criado em</th>
              <th className="px-5 py-3">Prioridade</th>
              <th className="px-5 py-3">Status</th>
              <th className="px-5 py-3">Ações</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[#E4E7EC]">
            {pendingActions.map((action) => (
              <tr key={action.id}>
                <td className="px-5 py-4 font-semibold text-[#171A24]">{action.description}</td>
                <td className="px-5 py-4 text-[#667085]">{action.thread}</td>
                <td className="px-5 py-4 text-[#667085]">{action.createdAt}</td>
                <td className="px-5 py-4">
                  <Badge tone={priorityTone[action.priority]}>{action.priority}</Badge>
                </td>
                <td className="px-5 py-4">
                  <Badge tone={action.status === 'Confirmada' ? 'green' : 'purple'}>{action.status}</Badge>
                </td>
                <td className="px-5 py-4">
                  <Button>Revisar</Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  )
}
