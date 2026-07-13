import { useQuery } from '@tanstack/react-query'
import { AlertTriangle, CheckCircle2, MessageSquarePlus, RefreshCcw, Settings2, Zap } from 'lucide-react'
import {
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { Badge } from '../components/common/Badge'
import { Button } from '../components/common/Button'
import { Card } from '../components/common/Card'
import { PageHeader } from '../components/common/PageHeader'
import { PageState } from '../components/common/PageState'
import { useTenant } from '../hooks/useTenant'
import { dashboardService } from '../services/dashboardService'
import type { DashboardEvent, Kpi, Priority } from '../types'

const priorityTone: Record<Priority, 'red' | 'yellow' | 'green'> = {
  Alta: 'red',
  Média: 'yellow',
  Baixa: 'green',
}

function EventIcon({ kind }: { kind: DashboardEvent['kind'] }) {
  const classes = 'h-4 w-4'
  if (kind === 'conversation') return <MessageSquarePlus className={classes} aria-hidden="true" />
  if (kind === 'action') return <Zap className={classes} aria-hidden="true" />
  if (kind === 'integration') return <CheckCircle2 className={classes} aria-hidden="true" />
  if (kind === 'configuration') return <Settings2 className={classes} aria-hidden="true" />
  return <AlertTriangle className={classes} aria-hidden="true" />
}

function KpiCard({ kpi }: { kpi: Kpi }) {
  const data = kpi.sparkline.map((value, index) => ({ index, value }))

  return (
    <Card className="p-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-sm font-semibold text-[#667085]">{kpi.title}</p>
          <p className="mt-2 text-3xl font-bold text-[#171A24]">{kpi.value}</p>
          <p className={kpi.positive ? 'mt-2 text-sm font-semibold text-[#16A34A]' : 'mt-2 text-sm font-semibold text-[#DC2626]'}>
            {kpi.comparison}
          </p>
        </div>
      </div>
      <div className="mt-4 h-16">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data}>
            <Line type="monotone" dataKey="value" stroke={kpi.positive ? '#6D3DF5' : '#D97706'} strokeWidth={3} dot={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </Card>
  )
}

export function DashboardPage() {
  const { tenants, activeTenant, activeTenantId, setActiveTenantId } = useTenant()
  const dashboardQuery = useQuery({
    queryKey: ['dashboard', activeTenantId],
    queryFn: () => dashboardService.getDashboard(activeTenantId),
    enabled: Boolean(activeTenantId),
  })

  if (!activeTenant || dashboardQuery.isLoading) return <PageState state="loading" />
  if (activeTenant.status === 'suspended') return <PageState state="tenant-suspended" />
  if (dashboardQuery.isError) return <PageState state="error" onRetry={() => void dashboardQuery.refetch()} />

  const dashboard = dashboardQuery.data
  if (!dashboard || dashboard.kpis.length === 0) return <PageState state="empty" />

  return (
    <div>
      <PageHeader
        eyebrow="1  Visão Geral"
        title="Olá, Rogério! 👋"
        description="Veja o que está acontecendo com a IA PMO hoje."
        actions={
          <>
            <label className="sr-only" htmlFor="dashboard-tenant">
              Empresa
            </label>
            <select
              id="dashboard-tenant"
              className="h-11 rounded-lg border border-[#E4E7EC] bg-white px-4 text-sm font-semibold text-[#171A24] focus:border-[#6D3DF5] focus:outline-none focus:ring-2 focus:ring-[#D8C9FF]"
              value={activeTenantId}
              onChange={(event) => setActiveTenantId(event.target.value)}
            >
              {tenants.map((tenant) => (
                <option key={tenant.id} value={tenant.id}>
                  {tenant.name}
                </option>
              ))}
            </select>
            <select
              className="h-11 rounded-lg border border-[#E4E7EC] bg-white px-4 text-sm font-semibold text-[#171A24] focus:border-[#6D3DF5] focus:outline-none focus:ring-2 focus:ring-[#D8C9FF]"
              defaultValue="7d"
              aria-label="Período"
            >
              <option value="7d">13/05/2026 - 19/05/2026</option>
              <option value="30d">Últimos 30 dias</option>
            </select>
            <Button aria-label="Atualizar dashboard" onClick={() => void dashboardQuery.refetch()}>
              <RefreshCcw className="h-4 w-4" aria-hidden="true" />
            </Button>
          </>
        }
      />

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {dashboard.kpis.map((kpi) => (
          <KpiCard key={kpi.id} kpi={kpi} />
        ))}
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-[minmax(0,1.7fr)_minmax(360px,0.8fr)]">
        <Card className="p-5">
          <div className="mb-5 flex items-center justify-between gap-4">
            <h2 className="text-xl font-bold text-[#171A24]">Conversas por Dia</h2>
            <select
              className="h-10 rounded-lg border border-[#E4E7EC] bg-white px-3 text-sm font-semibold text-[#667085] focus:border-[#6D3DF5] focus:outline-none focus:ring-2 focus:ring-[#D8C9FF]"
              defaultValue="7d"
              aria-label="Intervalo do gráfico"
            >
              <option value="7d">Últimos 7 dias</option>
              <option value="15d">Últimos 15 dias</option>
            </select>
          </div>
          <div className="h-[280px]">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={dashboard.conversationsByDay} margin={{ left: -20, right: 12, top: 10, bottom: 0 }}>
                <CartesianGrid stroke="#E4E7EC" vertical={false} />
                <XAxis dataKey="day" tickLine={false} axisLine={false} tick={{ fill: '#667085', fontSize: 12 }} />
                <YAxis tickLine={false} axisLine={false} tick={{ fill: '#667085', fontSize: 12 }} />
                <Tooltip contentStyle={{ borderRadius: 8, borderColor: '#E4E7EC' }} />
                <Line type="monotone" dataKey="conversas" name="Conversas" stroke="#6D3DF5" strokeWidth={3} dot={{ r: 4 }} activeDot={{ r: 6 }} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </Card>

        <Card className="p-5">
          <h2 className="text-xl font-bold text-[#171A24]">Eventos Recentes</h2>
          <div className="mt-5 space-y-4">
            {dashboard.events.map((event) => (
              <div key={event.id} className="flex items-start gap-3">
                <div className="mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-[#F2EDFF] text-[#6D3DF5]">
                  <EventIcon kind={event.kind} />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="font-semibold text-[#171A24]">{event.title}</p>
                  <p className="text-sm text-[#667085]">{event.description}</p>
                </div>
                <span className="text-xs font-semibold text-[#667085]">{event.occurredAt}</span>
              </div>
            ))}
          </div>
        </Card>
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-[minmax(0,1.7fr)_minmax(360px,0.8fr)]">
        <Card className="overflow-hidden">
          <div className="flex items-center justify-between border-b border-[#E4E7EC] p-5">
            <h2 className="text-xl font-bold text-[#171A24]">Ações Pendentes</h2>
            <Button>Ver todas</Button>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[720px] text-left text-sm">
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
                {dashboard.pendingActions.map((action) => (
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
                      <Button>Detalhes</Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>

        <Card className="p-5">
          <h2 className="text-xl font-bold text-[#171A24]">Top Plataformas</h2>
          <div className="mt-4 grid gap-4 sm:grid-cols-[180px_minmax(0,1fr)] xl:grid-cols-1 2xl:grid-cols-[180px_minmax(0,1fr)]">
            <div className="h-[180px]">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie data={dashboard.platforms} innerRadius={54} outerRadius={80} dataKey="value" paddingAngle={2}>
                    {dashboard.platforms.map((platform) => (
                      <Cell key={platform.name} fill={platform.color} />
                    ))}
                  </Pie>
                  <Tooltip contentStyle={{ borderRadius: 8, borderColor: '#E4E7EC' }} />
                </PieChart>
              </ResponsiveContainer>
            </div>
            <div className="space-y-3">
              {dashboard.platforms.map((platform) => (
                <div key={platform.name} className="flex items-center justify-between gap-3 text-sm">
                  <span className="flex items-center gap-2 font-semibold text-[#344054]">
                    <span className="h-3 w-3 rounded-full" style={{ backgroundColor: platform.color }} aria-hidden="true" />
                    {platform.name}
                  </span>
                  <span className="font-bold text-[#171A24]">{platform.value}%</span>
                </div>
              ))}
            </div>
          </div>
        </Card>
      </div>
    </div>
  )
}
