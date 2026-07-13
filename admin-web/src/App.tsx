import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AppLayout } from './components/layout/AppLayout'
import { AuthProvider } from './contexts/AuthContext'
import { TenantProvider } from './contexts/TenantContext'
import { ConversationsPage } from './pages/ConversationsPage'
import { DashboardPage } from './pages/DashboardPage'
import { IntegrationsPage } from './pages/IntegrationsPage'
import { LangGraphPage } from './pages/LangGraphPage'
import { PendingActionsPage } from './pages/PendingActionsPage'
import { SettingsPage } from './pages/SettingsPage'
import { AdminPage, AuditPage, EventsPage, ReportsPage, ThreadsPage, UsersPage } from './pages/SimplePages'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
})

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <TenantProvider>
          <AuthProvider>
            <Routes>
              <Route element={<AppLayout />}>
                <Route index element={<Navigate to="/dashboard" replace />} />
                <Route path="/dashboard" element={<DashboardPage />} />
                <Route path="/conversations" element={<ConversationsPage />} />
                <Route path="/conversations/:threadId" element={<ConversationsPage />} />
                <Route path="/pending-actions" element={<PendingActionsPage />} />
                <Route path="/threads" element={<ThreadsPage />} />
                <Route path="/langgraph" element={<LangGraphPage />} />
                <Route path="/integrations" element={<IntegrationsPage />} />
                <Route path="/events" element={<EventsPage />} />
                <Route path="/reports" element={<ReportsPage />} />
                <Route path="/settings" element={<SettingsPage />} />
                <Route path="/audit" element={<AuditPage />} />
                <Route path="/users" element={<UsersPage />} />
                <Route path="/admin" element={<AdminPage />} />
                <Route path="*" element={<Navigate to="/dashboard" replace />} />
              </Route>
            </Routes>
          </AuthProvider>
        </TenantProvider>
      </BrowserRouter>
    </QueryClientProvider>
  )
}

export default App
