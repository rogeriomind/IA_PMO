import { AlertCircle, Ban, DatabaseZap, Loader2, Lock, SearchX, ShieldAlert } from 'lucide-react'
import { Button } from './Button'

const stateCopy = {
  loading: {
    icon: Loader2,
    title: 'Carregando dados',
    description: 'Buscando informações atualizadas para o tenant ativo.',
  },
  empty: {
    icon: SearchX,
    title: 'Sem dados para exibir',
    description: 'Não encontramos registros para os filtros atuais.',
  },
  error: {
    icon: AlertCircle,
    title: 'Erro ao carregar',
    description: 'A API administrativa não respondeu como esperado.',
  },
  unauthorized: {
    icon: Lock,
    title: 'Sessão expirada',
    description: 'Entre novamente para continuar operando o IA PMO.',
  },
  forbidden: {
    icon: ShieldAlert,
    title: 'Acesso bloqueado por papel',
    description: 'Seu papel atual não permite acessar esta área.',
  },
  'tenant-suspended': {
    icon: Ban,
    title: 'Tenant suspenso',
    description: 'A operação está bloqueada até a reativação da empresa.',
  },
  'integration-unavailable': {
    icon: DatabaseZap,
    title: 'Integração indisponível',
    description: 'Uma dependência externa está com erro ou timeout.',
  },
}

type PageStateKind = keyof typeof stateCopy

export function PageState({
  state,
  onRetry,
}: {
  state: PageStateKind
  onRetry?: () => void
}) {
  const copy = stateCopy[state]
  const Icon = copy.icon

  return (
    <div className="flex min-h-[320px] items-center justify-center rounded-lg border border-dashed border-[#D0D5DD] bg-white p-8 text-center">
      <div className="max-w-md">
        <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-[#F2EDFF] text-[#6D3DF5]">
          <Icon className={state === 'loading' ? 'h-5 w-5 animate-spin' : 'h-5 w-5'} aria-hidden="true" />
        </div>
        <h2 className="text-lg font-bold text-[#171A24]">{copy.title}</h2>
        <p className="mt-2 text-sm text-[#667085]">{copy.description}</p>
        {onRetry ? (
          <Button className="mt-5" onClick={onRetry}>
            Tentar novamente
          </Button>
        ) : null}
      </div>
    </div>
  )
}
