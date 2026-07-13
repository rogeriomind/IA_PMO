import { useQuery } from '@tanstack/react-query'
import { Badge } from '../components/common/Badge'
import { Button } from '../components/common/Button'
import { Card } from '../components/common/Card'
import { PageHeader } from '../components/common/PageHeader'
import { PageState } from '../components/common/PageState'
import { useAuth } from '../hooks/useAuth'
import { useTenant } from '../hooks/useTenant'
import { auditService } from '../services/auditService'

type AuditRow = {
  id: string
  event: string
  actor: string
  createdAt: string
}

function TenantAwarePage({
  title,
  description,
  children,
}: {
  title: string
  description: string
  children: React.ReactNode
}) {
  const { activeTenant } = useTenant()
  if (!activeTenant) return <PageState state="loading" />
  if (activeTenant.status === 'suspended') return <PageState state="tenant-suspended" />

  return (
    <div>
      <PageHeader title={title} description={description} />
      {children}
    </div>
  )
}

export function ThreadsPage() {
  return (
    <TenantAwarePage title="Threads" description="Acompanhe threads abertas, encerradas e escaladas pelo agente.">
      <div className="grid gap-4 md:grid-cols-3">
        {['Abertas', 'Escaladas', 'Encerradas'].map((label, index) => (
          <Card key={label} className="p-5">
            <p className="text-sm font-semibold text-[#667085]">{label}</p>
            <p className="mt-2 text-3xl font-bold text-[#171A24]">{[42, 8, 190][index]}</p>
            <Badge tone={index === 1 ? 'yellow' : 'purple'}>{index === 1 ? 'requer atenção' : 'monitorado'}</Badge>
          </Card>
        ))}
      </div>
    </TenantAwarePage>
  )
}

export function EventsPage() {
  return (
    <TenantAwarePage title="Eventos" description="Linha do tempo de execuções, publicações e integrações.">
      <Card className="p-5">
        <div className="space-y-4">
          {['Nova conversa iniciada', 'Ação pendente criada', 'Integração executada', 'Configuração publicada'].map((event) => (
            <div key={event} className="flex items-center justify-between border-b border-[#E4E7EC] pb-3 last:border-0 last:pb-0">
              <span className="font-semibold text-[#171A24]">{event}</span>
              <span className="text-sm text-[#667085]">19/05/2026</span>
            </div>
          ))}
        </div>
      </Card>
    </TenantAwarePage>
  )
}

export function ReportsPage() {
  return (
    <TenantAwarePage title="Relatórios" description="Relatórios operacionais, custos, resolução e performance por canal.">
      <div className="grid gap-4 lg:grid-cols-2">
        {['Performance semanal', 'Custos por modelo', 'SLAs por canal', 'Ações por status'].map((report) => (
          <Card key={report} className="p-5">
            <h2 className="font-bold text-[#171A24]">{report}</h2>
            <p className="mt-2 text-sm text-[#667085]">Disponível para exportação CSV e revisão executiva.</p>
            <Button className="mt-4">Exportar</Button>
          </Card>
        ))}
      </div>
    </TenantAwarePage>
  )
}

export function AuditPage() {
  const { activeTenant, activeTenantId } = useTenant()
  const auditQuery = useQuery<AuditRow[]>({
    queryKey: ['audit', activeTenantId],
    queryFn: () => auditService.list(activeTenantId),
    enabled: Boolean(activeTenantId),
  })

  if (!activeTenant || auditQuery.isLoading) return <PageState state="loading" />
  if (activeTenant.status === 'suspended') return <PageState state="tenant-suspended" />
  if (auditQuery.isError) return <PageState state="error" onRetry={() => void auditQuery.refetch()} />

  return (
    <div>
      <PageHeader title="Auditoria" description="Trilha auditável de decisões, alterações e execuções." />
      <Card className="overflow-hidden">
        <table className="w-full text-left text-sm">
          <thead className="bg-[#F8F9FC] text-xs uppercase tracking-wide text-[#667085]">
            <tr>
              <th className="px-5 py-3">Evento</th>
              <th className="px-5 py-3">Autor</th>
              <th className="px-5 py-3">Criado em</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[#E4E7EC]">
            {auditQuery.data?.map((item) => (
              <tr key={item.id}>
                <td className="px-5 py-4 font-semibold text-[#171A24]">{item.event}</td>
                <td className="px-5 py-4 text-[#667085]">{item.actor}</td>
                <td className="px-5 py-4 text-[#667085]">{item.createdAt}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  )
}

export function UsersPage() {
  return (
    <TenantAwarePage title="Usuários" description="Papéis e acesso à operação administrativa por tenant.">
      <Card className="p-5">
        <div className="grid gap-4 md:grid-cols-3">
          {['Rogério Mind', 'Matheus Silva', 'Camila Torres'].map((name, index) => (
            <div key={name} className="rounded-lg border border-[#E4E7EC] p-4">
              <p className="font-bold text-[#171A24]">{name}</p>
              <p className="text-sm text-[#667085]">{['Administrador', 'Operador', 'Leitor'][index]}</p>
            </div>
          ))}
        </div>
      </Card>
    </TenantAwarePage>
  )
}

export function AdminPage() {
  const { user } = useAuth()

  if (user.role !== 'Administrador') return <PageState state="forbidden" />

  return (
    <TenantAwarePage title="Administrativo" description="Controles globais de governança do IA PMO.">
      <Card className="p-5">
        <h2 className="text-xl font-bold text-[#171A24]">Governança multi-tenant</h2>
        <p className="mt-2 text-sm text-[#667085]">Provisionamento, limites, políticas globais e health checks da plataforma.</p>
        <div className="mt-5 grid gap-4 md:grid-cols-3">
          <Badge tone="green">API administrativa ativa</Badge>
          <Badge tone="purple">3 tenants</Badge>
          <Badge tone="yellow">1 integração com alerta</Badge>
        </div>
      </Card>
    </TenantAwarePage>
  )
}
