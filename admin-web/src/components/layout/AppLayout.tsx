import { Menu } from 'lucide-react'
import { useState } from 'react'
import { Outlet } from 'react-router-dom'
import { useTenant } from '../../hooks/useTenant'
import { Sidebar } from '../navigation/Sidebar'

export function AppLayout() {
  const [collapsed, setCollapsed] = useState(false)
  const [mobileOpen, setMobileOpen] = useState(false)
  const { activeTenant } = useTenant()

  return (
    <div className="min-h-screen bg-[#F8F9FC] text-[#171A24]">
      <div className="fixed inset-y-0 left-0 z-40 hidden lg:block">
        <Sidebar collapsed={collapsed} onToggle={() => setCollapsed((current) => !current)} />
      </div>

      {mobileOpen ? (
        <div className="fixed inset-0 z-50 lg:hidden">
          <button className="absolute inset-0 bg-black/30" type="button" aria-label="Fechar navegação" onClick={() => setMobileOpen(false)} />
          <div className="absolute inset-y-0 left-0">
            <Sidebar collapsed={false} onToggle={() => undefined} mobile onClose={() => setMobileOpen(false)} />
          </div>
        </div>
      ) : null}

      <div className={collapsed ? 'lg:pl-[88px]' : 'lg:pl-[280px]'}>
        <header className="sticky top-0 z-30 flex h-16 items-center justify-between border-b border-[#E4E7EC] bg-white/95 px-4 backdrop-blur lg:hidden">
          <button className="rounded-lg p-2 text-[#344054] hover:bg-[#F8F9FC]" type="button" onClick={() => setMobileOpen(true)} aria-label="Abrir menu">
            <Menu className="h-6 w-6" aria-hidden="true" />
          </button>
          <span className="font-bold text-[#171A24]">IA PMO</span>
          <span className="h-10 w-10" aria-hidden="true" />
        </header>

        {activeTenant?.status === 'suspended' ? (
          <div className="border-b border-amber-200 bg-amber-50 px-5 py-3 text-sm font-semibold text-[#D97706]">
            Tenant suspenso: operações de escrita, integrações e testes estão bloqueados para {activeTenant.name}.
          </div>
        ) : null}

        <main className="mx-auto min-h-screen w-full max-w-[1600px] px-4 py-6 md:px-6 lg:px-8">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
