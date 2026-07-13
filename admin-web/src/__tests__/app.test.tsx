import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from '../App'

vi.mock('@xyflow/react', () => ({
  ReactFlow: ({
    nodes,
    onNodeClick,
    children,
  }: {
    nodes: Array<{ id: string; data: { label: string } }>
    onNodeClick?: (event: unknown, node: { id: string; data: { label: string } }) => void
    children: React.ReactNode
  }) => (
    <div data-testid="react-flow">
      {nodes.map((node) => (
        <button key={node.id} type="button" onClick={(event) => onNodeClick?.(event, node)}>
          {node.data.label}
        </button>
      ))}
      {children}
    </div>
  ),
  Background: () => <div data-testid="flow-background" />,
  Controls: () => <div data-testid="flow-controls" />,
  MiniMap: () => <div data-testid="flow-minimap" />,
}))

function renderAt(path: string) {
  window.history.pushState({}, '', path)
  return render(<App />)
}

afterEach(() => {
  cleanup()
  window.localStorage.clear()
  window.sessionStorage.clear()
  vi.clearAllMocks()
})

describe('IA PMO admin-web', () => {
  it('troca o tenant ativo e recarrega métricas', async () => {
    const user = userEvent.setup()
    window.localStorage.setItem('ia-pmo-active-tenant', 'acme-corp')
    renderAt('/dashboard')

    expect(await screen.findByText('128')).toBeInTheDocument()
    await user.selectOptions(screen.getByLabelText('Empresa'), 'porto-seguro')

    expect(await screen.findByText('86')).toBeInTheDocument()
  })

  it('carrega o dashboard em modo mock', async () => {
    renderAt('/dashboard')

    expect(await screen.findByText('Olá, Rogério! 👋')).toBeInTheDocument()
    expect(screen.getByText('Taxa de Resolução')).toBeInTheDocument()
    expect(screen.getByText('Eventos Recentes')).toBeInTheDocument()
  })

  it('renderiza a lista e o detalhe de conversas', async () => {
    renderAt('/conversations')

    expect(await screen.findAllByText('Projeto Apollo')).not.toHaveLength(0)
    expect(screen.getByText('Aqui está o status atualizado das entregas do projeto Apollo:')).toBeInTheDocument()
    expect(screen.getByText('Detalhes da Conversa')).toBeInTheDocument()
  })

  it('confirma uma ação criada pelo agente', async () => {
    const user = userEvent.setup()
    renderAt('/conversations')

    await screen.findByText('Atualizar relatório de integração')
    await user.click(screen.getByRole('button', { name: /confirmar/i }))

    expect(await screen.findAllByText('Confirmada')).not.toHaveLength(0)
  })

  it('cancela uma ação criada pelo agente', async () => {
    const user = userEvent.setup()
    renderAt('/conversations')

    await screen.findByText('Atualizar relatório de integração')
    await user.click(screen.getByRole('button', { name: /cancelar/i }))

    expect(await screen.findAllByText('Cancelada')).not.toHaveLength(0)
  })

  it('renderiza o React Flow do LangGraph', async () => {
    renderAt('/langgraph')

    expect(await screen.findByTestId('react-flow')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'START' })).toBeInTheDocument()
  })

  it('abre o painel lateral ao selecionar um nó', async () => {
    const user = userEvent.setup()
    renderAt('/langgraph')

    await user.click(await screen.findByRole('button', { name: 'Classificar Intenção' }))

    const panel = screen.getByLabelText('Painel do nó')
    expect(panel).toBeInTheDocument()
    expect(within(panel).getByText('Agente LLM')).toBeInTheDocument()
  })

  it('executa um teste de fluxo e mostra o resultado', async () => {
    const user = userEvent.setup()
    renderAt('/langgraph')

    await user.click(await screen.findByRole('button', { name: /executar teste/i }))
    await user.click(screen.getByRole('button', { name: /executar fluxo/i }))

    expect(await screen.findByText('Resultado do teste')).toBeInTheDocument()
    expect(screen.getAllByText('board_create_task')).not.toHaveLength(0)
  })

  it('edita configuração e salva rascunho', async () => {
    const user = userEvent.setup()
    renderAt('/settings')

    await user.click(await screen.findByRole('button', { name: 'System Prompt' }))
    await user.clear(screen.getByLabelText('System Prompt'))
    await user.type(screen.getByLabelText('System Prompt'), 'Prompt atualizado para teste.')
    await user.click(screen.getByRole('button', { name: /salvar rascunho/i }))

    expect(await screen.findAllByText('Rascunho salvo')).not.toHaveLength(0)
  })

  it('publica configuração com justificativa', async () => {
    const user = userEvent.setup()
    renderAt('/settings')

    expect(await screen.findAllByText('Configuração publicada')).not.toHaveLength(0)
    await user.click(screen.getAllByRole('button', { name: /publicar configuração/i })[0])
    await user.type(screen.getByPlaceholderText('Descreva por que esta publicação é necessária.'), 'Ajuste validado pelo time de PMO.')
    const modal = screen.getByText('Revise o impacto antes de promover o rascunho.').closest('div')?.parentElement
    expect(modal).not.toBeNull()
    await user.click(within(modal as HTMLElement).getByRole('button', { name: /publicar configuração/i }))

    await waitFor(() => expect(screen.queryByText('Revise o impacto antes de promover o rascunho.')).not.toBeInTheDocument())
  })

  it('bloqueia rota administrativa por papel', async () => {
    window.localStorage.setItem('ia-pmo-role', 'Leitor')
    renderAt('/admin')

    expect(await screen.findByText('Acesso bloqueado por papel')).toBeInTheDocument()
  })

  it('mascara secrets e tokens internos', async () => {
    const user = userEvent.setup()
    renderAt('/settings')

    await user.click(await screen.findByRole('button', { name: 'Segurança' }))

    expect(screen.getByText('OPENAI_API_KEY=sk-****-a71')).toBeInTheDocument()
    expect(screen.queryByText(/sk-live/i)).not.toBeInTheDocument()
  })

  it('mostra erro de integração indisponível', async () => {
    renderAt('/integrations')

    expect(await screen.findByText('Integração indisponível')).toBeInTheDocument()
    expect(screen.getByText(/conexão recusada/i)).toBeInTheDocument()
  })

  it('exibe estado de tenant suspenso', async () => {
    const user = userEvent.setup()
    renderAt('/dashboard')

    await screen.findByText('128')
    await user.selectOptions(screen.getByLabelText('Empresa'), 'empresa-demo')

    expect(await screen.findByText('Tenant suspenso')).toBeInTheDocument()
  })

  it('abre drawer mobile de navegação', async () => {
    const user = userEvent.setup()
    renderAt('/dashboard')

    await user.click(await screen.findByLabelText('Abrir menu'))

    expect(screen.getByLabelText('Fechar menu')).toBeInTheDocument()
  })
})
