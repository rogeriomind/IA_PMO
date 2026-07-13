import clsx from 'clsx'
import {
  Activity,
  BarChart3,
  BellDot,
  ChevronLeft,
  ChevronRight,
  ClipboardList,
  Database,
  FileText,
  GitBranch,
  Home,
  MessageSquareText,
  Settings,
  ShieldCheck,
  Sparkles,
  Users,
  X,
  type LucideIcon,
} from 'lucide-react'
import { NavLink } from 'react-router-dom'
import { useAuth } from '../../hooks/useAuth'
import { useTenant } from '../../hooks/useTenant'

type MenuItem = {
  label: string
  to: string
  icon: LucideIcon
  badge?: string
}

const menuItems: MenuItem[] = [
  { label: 'Visão Geral', to: '/dashboard', icon: Home },
  { label: 'Conversas', to: '/conversations', icon: MessageSquareText },
  { label: 'Ações Pendentes', to: '/pending-actions', icon: ClipboardList, badge: '12' },
  { label: 'Threads', to: '/threads', icon: GitBranch },
  { label: 'Fluxo LangGraph', to: '/langgraph', icon: Activity },
  { label: 'Integrações', to: '/integrations', icon: Database },
  { label: 'Eventos', to: '/events', icon: BellDot },
  { label: 'Relatórios', to: '/reports', icon: FileText },
  { label: 'Configurações', to: '/settings', icon: Settings },
  { label: 'Auditoria', to: '/audit', icon: ShieldCheck },
  { label: 'Usuários', to: '/users', icon: Users },
  { label: 'Administrativo', to: '/admin', icon: BarChart3 },
]

export function Sidebar({
  collapsed,
  onToggle,
  mobile,
  onClose,
}: {
  collapsed: boolean
  onToggle: () => void
  mobile?: boolean
  onClose?: () => void
}) {
  const { tenants, activeTenantId, setActiveTenantId } = useTenant()
  const { user } = useAuth()

  return (
    <aside
      className={clsx(
        'flex h-full flex-col border-r border-[#E4E7EC] bg-white transition-all',
        collapsed && !mobile ? 'w-[88px]' : 'w-[280px]',
      )}
      aria-label="Navegação principal"
    >
      <div className="flex h-20 items-center justify-between px-6">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-[#6D3DF5] text-white shadow-sm">
            <Sparkles className="h-5 w-5" aria-hidden="true" />
          </div>
          {!collapsed || mobile ? <span className="text-2xl font-bold text-[#171A24]">IA PMO</span> : null}
        </div>
        {mobile ? (
          <button className="rounded-lg p-2 text-[#667085] hover:bg-[#F8F9FC]" type="button" onClick={onClose} aria-label="Fechar menu">
            <X className="h-5 w-5" aria-hidden="true" />
          </button>
        ) : (
          <button className="rounded-lg p-2 text-[#667085] hover:bg-[#F8F9FC]" type="button" onClick={onToggle} aria-label="Recolher menu">
            {collapsed ? <ChevronRight className="h-5 w-5" aria-hidden="true" /> : <ChevronLeft className="h-5 w-5" aria-hidden="true" />}
          </button>
        )}
      </div>

      <nav className="flex-1 space-y-1 overflow-y-auto px-4 pb-4">
        {menuItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            onClick={onClose}
            className={({ isActive }) =>
              clsx(
                'flex min-h-11 items-center gap-3 rounded-lg px-3 text-sm font-semibold transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#6D3DF5]',
                isActive ? 'bg-[#6D3DF5] text-white shadow-sm' : 'text-[#344054] hover:bg-[#F8F9FC] hover:text-[#171A24]',
                collapsed && !mobile ? 'justify-center' : 'justify-between',
              )
            }
          >
            {({ isActive }) => (
              <>
                <span className="flex items-center gap-3">
                  <item.icon className="h-5 w-5 shrink-0" aria-hidden="true" />
                  {!collapsed || mobile ? <span>{item.label}</span> : <span className="sr-only">{item.label}</span>}
                </span>
                {item.badge && (!collapsed || mobile) ? (
                  <span className={clsx('rounded-full px-2 py-0.5 text-xs font-bold', isActive ? 'bg-white/20 text-white' : 'bg-[#6D3DF5] text-white')}>
                    {item.badge}
                  </span>
                ) : null}
              </>
            )}
          </NavLink>
        ))}
      </nav>

      <div className="space-y-3 border-t border-[#E4E7EC] p-4">
        {!collapsed || mobile ? (
          <label className="block">
            <span className="text-xs font-semibold uppercase tracking-wide text-[#667085]">Empresa Atual</span>
            <select
              className="mt-2 w-full rounded-lg border border-[#E4E7EC] bg-white px-3 py-2 text-sm font-semibold text-[#171A24] focus:border-[#6D3DF5] focus:outline-none focus:ring-2 focus:ring-[#D8C9FF]"
              value={activeTenantId}
              onChange={(event) => setActiveTenantId(event.target.value)}
              aria-label="Selecionar empresa"
            >
              {tenants.map((tenant) => (
                <option key={tenant.id} value={tenant.id}>
                  {tenant.name}
                </option>
              ))}
            </select>
          </label>
        ) : null}

        <div className={clsx('flex items-center gap-3 rounded-lg border border-[#E4E7EC] bg-[#F8F9FC] p-3', collapsed && !mobile ? 'justify-center' : '')}>
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-[#171A24] text-sm font-bold text-white">RM</div>
          {!collapsed || mobile ? (
            <div className="min-w-0">
              <p className="truncate text-sm font-bold text-[#171A24]">{user.name}</p>
              <p className="truncate text-xs text-[#667085]">{user.role}</p>
            </div>
          ) : null}
        </div>
      </div>
    </aside>
  )
}
