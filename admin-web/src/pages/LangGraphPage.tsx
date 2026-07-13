import '@xyflow/react/dist/style.css'
import { useMutation, useQuery } from '@tanstack/react-query'
import {
  Background,
  Controls,
  MiniMap,
  ReactFlow,
  type Edge,
  type Node,
  type NodeMouseHandler,
} from '@xyflow/react'
import { Download, Maximize2, PanelRightOpen, Play, RotateCcw, X } from 'lucide-react'
import { useMemo, useState } from 'react'
import { Badge } from '../components/common/Badge'
import { Button } from '../components/common/Button'
import { Card } from '../components/common/Card'
import { PageHeader } from '../components/common/PageHeader'
import { PageState } from '../components/common/PageState'
import { useTenant } from '../hooks/useTenant'
import { langGraphService } from '../services/langGraphService'
import type { ExecutionStatus, LangGraphExecution, LangGraphNodeData, LangGraphNodeType } from '../types'

type FlowNode = Node<LangGraphNodeData>

const nodePositions: Record<string, { x: number; y: number }> = {
  start: { x: 0, y: 240 },
  tenant_context: { x: 260, y: 240 },
  memory: { x: 540, y: 240 },
  classify: { x: 820, y: 240 },
  intent: { x: 1100, y: 230 },
  extract_entities: { x: 1380, y: 0 },
  validate_fields: { x: 1640, y: 0 },
  resolve_owner: { x: 1900, y: 0 },
  prepare_action: { x: 2160, y: 0 },
  confirm: { x: 2420, y: 0 },
  create_task: { x: 2680, y: 0 },
  search_task: { x: 1380, y: 190 },
  select_task: { x: 1640, y: 190 },
  extract_changes: { x: 1900, y: 190 },
  update_task: { x: 2680, y: 190 },
  validate_status: { x: 1640, y: 380 },
  move_task: { x: 2680, y: 380 },
  board_search: { x: 1380, y: 560 },
  project_status: { x: 1380, y: 720 },
  blockers: { x: 1380, y: 880 },
  my_tasks: { x: 1380, y: 1040 },
  format_response: { x: 1900, y: 760 },
  answer: { x: 1380, y: 1200 },
  audit: { x: 2940, y: 540 },
  end: { x: 3220, y: 540 },
  error: { x: 2160, y: 380 },
}

const baseEdges: Edge[] = [
  { id: 'start-tenant', source: 'start', target: 'tenant_context' },
  { id: 'tenant-memory', source: 'tenant_context', target: 'memory' },
  { id: 'memory-classify', source: 'memory', target: 'classify' },
  { id: 'classify-intent', source: 'classify', target: 'intent' },
  { id: 'intent-extract', source: 'intent', target: 'extract_entities', label: 'Criar tarefa' },
  { id: 'extract-validate', source: 'extract_entities', target: 'validate_fields' },
  { id: 'validate-owner', source: 'validate_fields', target: 'resolve_owner' },
  { id: 'owner-prepare', source: 'resolve_owner', target: 'prepare_action' },
  { id: 'prepare-confirm', source: 'prepare_action', target: 'confirm' },
  { id: 'confirm-create', source: 'confirm', target: 'create_task' },
  { id: 'create-audit', source: 'create_task', target: 'audit' },
  { id: 'intent-search-update', source: 'intent', target: 'search_task', label: 'Atualizar tarefa' },
  { id: 'search-select', source: 'search_task', target: 'select_task' },
  { id: 'select-changes', source: 'select_task', target: 'extract_changes' },
  { id: 'changes-prepare', source: 'extract_changes', target: 'prepare_action' },
  { id: 'confirm-update', source: 'confirm', target: 'update_task' },
  { id: 'update-audit', source: 'update_task', target: 'audit' },
  { id: 'search-validate-status', source: 'search_task', target: 'validate_status', label: 'Mover tarefa' },
  { id: 'validate-status-confirm', source: 'validate_status', target: 'confirm' },
  { id: 'confirm-move', source: 'confirm', target: 'move_task' },
  { id: 'move-audit', source: 'move_task', target: 'audit' },
  { id: 'intent-board-search', source: 'intent', target: 'board_search', label: 'Consultar tarefas' },
  { id: 'board-search-format', source: 'board_search', target: 'format_response' },
  { id: 'intent-project-status', source: 'intent', target: 'project_status', label: 'Status do projeto' },
  { id: 'project-status-format', source: 'project_status', target: 'format_response' },
  { id: 'intent-blockers', source: 'intent', target: 'blockers', label: 'Bloqueios' },
  { id: 'blockers-format', source: 'blockers', target: 'format_response' },
  { id: 'intent-my-tasks', source: 'intent', target: 'my_tasks', label: 'Minhas tarefas' },
  { id: 'my-tasks-format', source: 'my_tasks', target: 'format_response' },
  { id: 'format-audit', source: 'format_response', target: 'audit' },
  { id: 'intent-answer', source: 'intent', target: 'answer', label: 'Dúvida ou conversa' },
  { id: 'answer-audit', source: 'answer', target: 'audit' },
  { id: 'audit-end', source: 'audit', target: 'end' },
  { id: 'error-audit', source: 'error', target: 'audit' },
  { id: 'validate-error', source: 'validate_status', target: 'error', label: 'Falha' },
]
const emptyPath: string[] = []

const nodeTypeStyles: Record<LangGraphNodeType, { border: string; background: string; color: string }> = {
  'start-end': { border: '#86EFAC', background: '#F0FDF4', color: '#16A34A' },
  llm: { border: '#D8C9FF', background: '#F2EDFF', color: '#6D3DF5' },
  mcp: { border: '#BFDBFE', background: '#EFF6FF', color: '#2563EB' },
  decision: { border: '#FDBA74', background: '#FFF7ED', color: '#D97706' },
  audit: { border: '#C4B5FD', background: '#EDE9FE', color: '#4C1D95' },
  human: { border: '#FDE68A', background: '#FFFBEB', color: '#D97706' },
  error: { border: '#FECACA', background: '#FEF2F2', color: '#DC2626' },
  context: { border: '#D0D5DD', background: '#F8F9FC', color: '#344054' },
}

const statusTone: Record<ExecutionStatus, 'neutral' | 'purple' | 'green' | 'yellow' | 'red' | 'blue'> = {
  'Não executado': 'neutral',
  Executando: 'blue',
  Sucesso: 'green',
  Falha: 'red',
  'Aguardando confirmação': 'yellow',
  Ignorado: 'purple',
}

function isPathEdge(path: string[], edge: Edge) {
  return path.some((nodeId, index) => nodeId === edge.source && path[index + 1] === edge.target)
}

function nodeKindLabel(kind: LangGraphNodeType) {
  const labels: Record<LangGraphNodeType, string> = {
    'start-end': 'Início/Fim',
    llm: 'Agente LLM',
    mcp: 'Ferramenta MCP',
    decision: 'Decisão',
    audit: 'Auditoria/Eventos',
    human: 'Confirmação humana',
    error: 'Erro',
    context: 'Contexto',
  }
  return labels[kind]
}

function NodePanel({ node, onClose }: { node: LangGraphNodeData; onClose: () => void }) {
  const rows = [
    ['Nome', node.label],
    ['Tipo', nodeKindLabel(node.nodeType)],
    ['Descrição', node.description],
    ['Modelo', node.model ?? 'N/A'],
    ['Prompt', node.prompt ?? 'N/A'],
    ['Temperatura', String(node.temperature ?? 'N/A')],
    ['Max tokens', String(node.maxTokens ?? 'N/A')],
    ['Ferramenta', node.tool ?? 'N/A'],
    ['Timeout', node.timeout ?? 'N/A'],
    ['Retries', String(node.retries ?? 'N/A')],
    ['Condições de entrada', node.entryConditions.join(', ')],
    ['Próximas rotas', node.nextRoutes.length ? node.nextRoutes.join(', ') : 'Definidas por arestas do grafo'],
    ['Últimas execuções', node.lastRuns.join(', ')],
    ['Taxa de sucesso', node.successRate],
    ['Tempo médio', node.averageTime],
    ['Custo médio', node.averageCost],
  ]

  return (
    <aside className="w-full border-l border-[#E4E7EC] bg-white p-5 xl:w-[360px]" aria-label="Painel do nó">
      <div className="mb-4 flex items-start justify-between gap-4">
        <div>
          <h2 className="text-lg font-bold text-[#171A24]">{node.label}</h2>
          <Badge tone={statusTone[node.status]}>{node.status}</Badge>
        </div>
        <button className="rounded-lg p-2 text-[#667085] hover:bg-[#F8F9FC]" type="button" onClick={onClose} aria-label="Fechar painel do nó">
          <X className="h-5 w-5" aria-hidden="true" />
        </button>
      </div>
      <dl className="space-y-4 text-sm">
        {rows.map(([label, value]) => (
          <div key={label}>
            <dt className="font-semibold text-[#667085]">{label}</dt>
            <dd className="mt-1 break-words font-semibold text-[#171A24]">{value}</dd>
          </div>
        ))}
      </dl>
    </aside>
  )
}

function TestDrawer({
  open,
  onClose,
  onRun,
  isRunning,
  result,
  tenantName,
}: {
  open: boolean
  onClose: () => void
  onRun: () => void
  isRunning: boolean
  result?: LangGraphExecution
  tenantName: string
}) {
  if (!open) return null

  return (
    <div className="fixed inset-0 z-50">
      <button className="absolute inset-0 bg-black/30" type="button" aria-label="Fechar modo teste" onClick={onClose} />
      <aside className="absolute inset-y-0 right-0 flex w-full max-w-xl flex-col bg-white shadow-xl" aria-label="Modo teste do LangGraph">
        <div className="flex items-center justify-between border-b border-[#E4E7EC] p-5">
          <div>
            <h2 className="text-xl font-bold text-[#171A24]">Executar teste</h2>
            <p className="text-sm text-[#667085]">Simula o fluxo sem escrita real.</p>
          </div>
          <button className="rounded-lg p-2 text-[#667085] hover:bg-[#F8F9FC]" type="button" onClick={onClose} aria-label="Fechar drawer">
            <X className="h-5 w-5" aria-hidden="true" />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-5">
          <div className="grid gap-4">
            {[
              ['Tenant', tenantName],
              ['Usuário', 'Rogério Mind'],
              ['Canal', 'WhatsApp'],
              ['Mensagem', 'Crie uma tarefa para atualizar o relatório de integração até amanhã.'],
              ['Projeto', 'Projeto Apollo'],
              ['Papéis', 'Administrador, Operador'],
            ].map(([label, value]) => (
              <label key={label} className="block">
                <span className="text-sm font-semibold text-[#344054]">{label}</span>
                {label === 'Mensagem' ? (
                  <textarea
                    className="mt-2 min-h-24 w-full rounded-lg border border-[#E4E7EC] px-3 py-2 text-sm focus:border-[#6D3DF5] focus:outline-none focus:ring-2 focus:ring-[#D8C9FF]"
                    defaultValue={value}
                  />
                ) : (
                  <input
                    className="mt-2 h-11 w-full rounded-lg border border-[#E4E7EC] px-3 text-sm focus:border-[#6D3DF5] focus:outline-none focus:ring-2 focus:ring-[#D8C9FF]"
                    defaultValue={value}
                  />
                )}
              </label>
            ))}
          </div>
          <Button className="mt-5 w-full" variant="primary" onClick={onRun} disabled={isRunning}>
            <Play className="h-4 w-4" aria-hidden="true" />
            Executar fluxo
          </Button>

          {result ? (
            <Card className="mt-5 p-5">
              <h3 className="text-lg font-bold text-[#171A24]">Resultado do teste</h3>
              <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2">
                <div>
                  <dt className="text-[#667085]">Caminho percorrido</dt>
                  <dd className="font-semibold text-[#171A24]">{result.path.join(' → ')}</dd>
                </div>
                <div>
                  <dt className="text-[#667085]">Intenção</dt>
                  <dd className="font-semibold text-[#171A24]">{result.intent}</dd>
                </div>
                <div>
                  <dt className="text-[#667085]">Confiança</dt>
                  <dd className="font-semibold text-[#171A24]">{Math.round(result.confidence * 100)}%</dd>
                </div>
                <div>
                  <dt className="text-[#667085]">Nós executados</dt>
                  <dd className="font-semibold text-[#171A24]">{result.nodesExecuted}</dd>
                </div>
                <div>
                  <dt className="text-[#667085]">MCP chamado</dt>
                  <dd className="font-semibold text-[#171A24]">{result.mcp}</dd>
                </div>
                <div>
                  <dt className="text-[#667085]">Resposta</dt>
                  <dd className="font-semibold text-[#171A24]">{result.response}</dd>
                </div>
                <div>
                  <dt className="text-[#667085]">Tokens</dt>
                  <dd className="font-semibold text-[#171A24]">{result.tokens}</dd>
                </div>
                <div>
                  <dt className="text-[#667085]">Custo</dt>
                  <dd className="font-semibold text-[#171A24]">{result.cost}</dd>
                </div>
                <div>
                  <dt className="text-[#667085]">Tempo total</dt>
                  <dd className="font-semibold text-[#171A24]">{result.durationMs} ms</dd>
                </div>
                <div>
                  <dt className="text-[#667085]">Erros</dt>
                  <dd className="font-semibold text-[#171A24]">{result.errors.length ? result.errors.join(', ') : 'Nenhum'}</dd>
                </div>
              </dl>
            </Card>
          ) : null}
        </div>
      </aside>
    </div>
  )
}

export function LangGraphPage() {
  const { activeTenant, activeTenantId } = useTenant()
  const [selectedNodeId, setSelectedNodeId] = useState<string>()
  const [selectedExecutionId, setSelectedExecutionId] = useState('exec-1')
  const [isTestOpen, setIsTestOpen] = useState(false)
  const [testResult, setTestResult] = useState<LangGraphExecution>()
  const [flowKey, setFlowKey] = useState(0)
  const [fullscreen, setFullscreen] = useState(false)

  const graphQuery = useQuery({
    queryKey: ['langgraph', activeTenantId],
    queryFn: () => langGraphService.getGraph(activeTenantId),
    enabled: Boolean(activeTenantId),
  })

  const runTestMutation = useMutation({
    mutationFn: () =>
      langGraphService.runTest(activeTenantId, {
        tenant: activeTenantId,
        user: 'Rogério Mind',
        channel: 'WhatsApp',
        message: 'Crie uma tarefa para atualizar o relatório de integração até amanhã.',
        project: 'Projeto Apollo',
        roles: 'Administrador, Operador',
      }),
    onSuccess: (execution) => {
      setTestResult(execution)
      setSelectedExecutionId(execution.id)
    },
  })

  const executions = useMemo(() => {
    const base = graphQuery.data?.executions ?? []
    return testResult ? [testResult, ...base] : base
  }, [graphQuery.data?.executions, testResult])

  const selectedExecution = executions.find((execution) => execution.id === selectedExecutionId) ?? executions[0]
  const activePath = selectedExecution?.path ?? emptyPath

  const nodes: FlowNode[] = useMemo(() => {
    const graphNodes = graphQuery.data?.nodes ?? {}
    return Object.entries(graphNodes).map(([id, data]) => {
      const style = nodeTypeStyles[data.nodeType]
      const active = activePath.includes(id)
      return {
        id,
        position: nodePositions[id] ?? { x: 0, y: 0 },
        data: {
          ...data,
          status: active ? selectedExecution?.status ?? data.status : data.status,
        },
        style: {
          width: 210,
          minHeight: 70,
          border: `2px solid ${active ? '#171A24' : style.border}`,
          borderRadius: 8,
          background: style.background,
          color: style.color,
          boxShadow: active ? '0 10px 30px rgba(23, 26, 36, 0.18)' : '0 4px 12px rgba(23, 26, 36, 0.08)',
          fontWeight: 700,
          fontSize: 13,
        },
      }
    })
  }, [activePath, graphQuery.data?.nodes, selectedExecution?.status])

  const edges = useMemo(
    () =>
      baseEdges.map((edge) => {
        const active = selectedExecution ? isPathEdge(activePath, edge) : false
        return {
          ...edge,
          animated: active && selectedExecution?.status === 'Executando',
          style: { stroke: active ? '#6D3DF5' : '#98A2B3', strokeWidth: active ? 3 : 2 },
          labelStyle: { fill: '#667085', fontWeight: 700, fontSize: 12 },
          labelBgStyle: { fill: '#FFFFFF', fillOpacity: 0.9 },
        }
      }),
    [activePath, selectedExecution],
  )

  const selectedNode = selectedNodeId ? graphQuery.data?.nodes[selectedNodeId] : undefined
  const handleNodeClick: NodeMouseHandler = (_event, node) => setSelectedNodeId(node.id)

  if (!activeTenant || graphQuery.isLoading) return <PageState state="loading" />
  if (activeTenant.status === 'suspended') return <PageState state="tenant-suspended" />
  if (graphQuery.isError) return <PageState state="error" onRetry={() => void graphQuery.refetch()} />

  return (
    <div className={fullscreen ? 'fixed inset-0 z-50 overflow-auto bg-[#F8F9FC] p-5' : ''}>
      <PageHeader
        eyebrow="3  Fluxo LangGraph"
        title="Fluxo LangGraph"
        description="Visualização do grafo de execução do agente IA PMO"
        actions={
          <>
            <select
              className="h-11 rounded-lg border border-[#E4E7EC] bg-white px-4 text-sm font-semibold text-[#171A24] focus:border-[#6D3DF5] focus:outline-none focus:ring-2 focus:ring-[#D8C9FF]"
              defaultValue="v2.3.1"
              aria-label="Versão ativa"
            >
              <option value="v2.3.1">Versão: v2.3.1</option>
              <option value="v2.2.9">Versão: v2.2.9</option>
            </select>
            <Button variant="primary" onClick={() => setIsTestOpen(true)}>
              <Play className="h-4 w-4" aria-hidden="true" />
              Executar Teste
            </Button>
            <select
              className="h-11 rounded-lg border border-[#E4E7EC] bg-white px-4 text-sm font-semibold text-[#171A24] focus:border-[#6D3DF5] focus:outline-none focus:ring-2 focus:ring-[#D8C9FF]"
              value={selectedExecutionId}
              onChange={(event) => setSelectedExecutionId(event.target.value)}
              aria-label="Ver execuções"
            >
              {executions.map((execution) => (
                <option key={execution.id} value={execution.id}>
                  {execution.label}
                </option>
              ))}
            </select>
            <Button
              onClick={() => {
                const blob = new Blob([JSON.stringify(graphQuery.data, null, 2)], { type: 'application/json' })
                const link = document.createElement('a')
                link.href = URL.createObjectURL(blob)
                link.download = 'ia-pmo-langgraph.json'
                link.click()
                URL.revokeObjectURL(link.href)
              }}
            >
              <Download className="h-4 w-4" aria-hidden="true" />
              Exportar
            </Button>
            <Button onClick={() => setFlowKey((current) => current + 1)}>
              <RotateCcw className="h-4 w-4" aria-hidden="true" />
              Centralizar
            </Button>
            <Button onClick={() => setFullscreen((current) => !current)} aria-label="Alternar fullscreen">
              <Maximize2 className="h-4 w-4" aria-hidden="true" />
              Fullscreen
            </Button>
          </>
        }
      />

      <div className="mb-4 flex flex-wrap items-center gap-2">
        {Object.entries(nodeTypeStyles).map(([type, style]) => (
          <span key={type} className="inline-flex items-center gap-2 rounded-full border bg-white px-3 py-1.5 text-xs font-semibold text-[#344054]">
            <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: style.color }} aria-hidden="true" />
            {nodeKindLabel(type as LangGraphNodeType)}
          </span>
        ))}
      </div>

      <Card className="overflow-hidden">
        <div className="flex min-h-[720px] flex-col xl:flex-row">
          <div className="min-h-[720px] flex-1 bg-white">
            <ReactFlow
              key={flowKey}
              nodes={nodes}
              edges={edges}
              onNodeClick={handleNodeClick}
              fitView
              minZoom={0.18}
              maxZoom={1.5}
              proOptions={{ hideAttribution: true }}
            >
              <Background color="#D0D5DD" gap={24} />
              <MiniMap pannable zoomable nodeStrokeWidth={3} />
              <Controls showInteractive={false} />
            </ReactFlow>
          </div>
          {selectedNode ? (
            <NodePanel node={selectedNode} onClose={() => setSelectedNodeId(undefined)} />
          ) : (
            <aside className="hidden w-[320px] border-l border-[#E4E7EC] bg-white p-5 xl:block">
              <div className="rounded-lg border border-dashed border-[#D0D5DD] p-5 text-sm text-[#667085]">
                <PanelRightOpen className="mb-3 h-5 w-5 text-[#6D3DF5]" aria-hidden="true" />
                Selecione um nó para ver parâmetros, condições, métricas e últimas execuções.
              </div>
            </aside>
          )}
        </div>
      </Card>

      {selectedExecution ? (
        <Card className="mt-4 p-5">
          <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
            <div>
              <h2 className="text-lg font-bold text-[#171A24]">{selectedExecution.label}</h2>
              <p className="text-sm text-[#667085]">
                Intenção {selectedExecution.intent} • confiança {Math.round(selectedExecution.confidence * 100)}% • {selectedExecution.nodesExecuted} nós
              </p>
            </div>
            <Badge tone={statusTone[selectedExecution.status]}>{selectedExecution.status}</Badge>
          </div>
        </Card>
      ) : null}

      <TestDrawer
        open={isTestOpen}
        onClose={() => setIsTestOpen(false)}
        onRun={() => runTestMutation.mutate()}
        isRunning={runTestMutation.isPending}
        result={testResult}
        tenantName={activeTenant.name}
      />
    </div>
  )
}
