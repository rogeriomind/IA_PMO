import { useMutation, useQuery } from '@tanstack/react-query'
import clsx from 'clsx'
import { Eye, FileClock, GitCompare, RotateCcw, Save, Send, TestTube2, Trash2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { Badge } from '../components/common/Badge'
import { Button } from '../components/common/Button'
import { Card } from '../components/common/Card'
import { PageHeader } from '../components/common/PageHeader'
import { PageState } from '../components/common/PageState'
import { useTenant } from '../hooks/useTenant'
import { configurationService } from '../services/configurationService'
import type { Configuration, IntegrationStatus } from '../types'

const tabs = [
  'Empresa',
  'Identidade',
  'Modelo',
  'System Prompt',
  'Políticas',
  'Ferramentas',
  'Canais',
  'Integrações',
  'Observabilidade',
  'Parâmetros',
  'Segurança',
] as const

type SettingsTab = (typeof tabs)[number]
type PublishState = 'Alterações não salvas' | 'Rascunho salvo' | 'Configuração publicada' | 'Erro ao publicar'

const configurationSchema = z
  .object({
    company: z.object({
      name: z.string().min(2),
      legalName: z.string().min(2),
      document: z.string().min(4),
      slug: z.string().min(2),
      status: z.enum(['active', 'suspended']),
      language: z.string().min(2),
      timezone: z.string().min(2),
      environment: z.string().min(2),
    }),
    identity: z.object({
      primaryColor: z.string().min(4),
      secondaryColor: z.string().min(4),
      assistantName: z.string().min(2),
      tone: z.string().min(2),
      welcomeMessage: z.string().min(5),
    }),
    model: z.object({
      provider: z.enum(['DeepSeek', 'OpenAI']),
      model: z.string().min(2),
      temperature: z.coerce.number().min(0).max(2),
      topP: z.coerce.number().min(0).max(1),
      maxTokens: z.coerce.number().min(1),
      thinkingEnabled: z.boolean(),
      confidenceThreshold: z.coerce.number().min(0).max(1),
    }),
    systemPrompt: z.string().trim().min(1, 'O system prompt não pode ficar vazio.'),
  })
  .passthrough()

const inputClass =
  'mt-2 h-11 w-full rounded-lg border border-[#E4E7EC] bg-white px-3 text-sm text-[#171A24] focus:border-[#6D3DF5] focus:outline-none focus:ring-2 focus:ring-[#D8C9FF]'
const textareaClass =
  'mt-2 min-h-32 w-full rounded-lg border border-[#E4E7EC] bg-white px-3 py-2 text-sm text-[#171A24] focus:border-[#6D3DF5] focus:outline-none focus:ring-2 focus:ring-[#D8C9FF]'

const statusTone: Record<IntegrationStatus, 'green' | 'yellow' | 'red' | 'neutral'> = {
  Conectado: 'green',
  Desconectado: 'neutral',
  Erro: 'red',
  'Em configuração': 'yellow',
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="text-sm font-semibold text-[#344054]">{label}</span>
      {children}
    </label>
  )
}

function ToggleField({ label, checked, onChange }: { label: string; checked: boolean; onChange: (value: boolean) => void }) {
  return (
    <label className="flex items-center justify-between gap-4 rounded-lg border border-[#E4E7EC] bg-white p-4 text-sm font-semibold text-[#344054]">
      <span>{label}</span>
      <input
        className="h-5 w-5 rounded border-[#D0D5DD] text-[#6D3DF5] focus:ring-[#6D3DF5]"
        type="checkbox"
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
      />
    </label>
  )
}

function PublishModal({
  open,
  onClose,
  onConfirm,
  justification,
  setJustification,
  isPublishing,
}: {
  open: boolean
  onClose: () => void
  onConfirm: () => void
  justification: string
  setJustification: (value: string) => void
  isPublishing: boolean
}) {
  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4">
      <div className="w-full max-w-2xl rounded-lg bg-white shadow-xl">
        <div className="border-b border-[#E4E7EC] p-5">
          <h2 className="text-xl font-bold text-[#171A24]">Publicar configuração</h2>
          <p className="text-sm text-[#667085]">Revise o impacto antes de promover o rascunho.</p>
        </div>
        <div className="space-y-4 p-5 text-sm">
          <dl className="grid gap-3 sm:grid-cols-2">
            <div>
              <dt className="text-[#667085]">Itens alterados</dt>
              <dd className="font-semibold text-[#171A24]">Modelo, System Prompt, Políticas</dd>
            </div>
            <div>
              <dt className="text-[#667085]">Versão atual</dt>
              <dd className="font-semibold text-[#171A24]">v2.3.1</dd>
            </div>
            <div>
              <dt className="text-[#667085]">Nova versão</dt>
              <dd className="font-semibold text-[#171A24]">v2.3.2</dd>
            </div>
            <div>
              <dt className="text-[#667085]">Impacto</dt>
              <dd className="font-semibold text-[#171A24]">Afeta classificação, confirmação e chamadas MCP.</dd>
            </div>
            <div>
              <dt className="text-[#667085]">Autor</dt>
              <dd className="font-semibold text-[#171A24]">Rogério Mind</dd>
            </div>
          </dl>
          <label className="block">
            <span className="font-semibold text-[#344054]">Justificativa</span>
            <textarea
              className={textareaClass}
              value={justification}
              onChange={(event) => setJustification(event.target.value)}
              placeholder="Descreva por que esta publicação é necessária."
            />
          </label>
        </div>
        <div className="flex flex-wrap justify-end gap-3 border-t border-[#E4E7EC] p-5">
          <Button onClick={onClose}>Cancelar</Button>
          <Button variant="primary" onClick={onConfirm} disabled={!justification.trim() || isPublishing}>
            Publicar configuração
          </Button>
        </div>
      </div>
    </div>
  )
}

export function SettingsPage() {
  const { activeTenant, activeTenantId } = useTenant()
  const [activeTab, setActiveTab] = useState<SettingsTab>('Empresa')
  const [publishState, setPublishState] = useState<PublishState>('Configuração publicada')
  const [promptError, setPromptError] = useState('')
  const [publishModalOpen, setPublishModalOpen] = useState(false)
  const [justification, setJustification] = useState('')

  const configurationQuery = useQuery({
    queryKey: ['configuration', activeTenantId],
    queryFn: () => configurationService.get(activeTenantId),
    enabled: Boolean(activeTenantId),
  })

  const form = useForm<Configuration>()
  const { register, handleSubmit, reset, watch, setValue, getValues } = form
  const values = watch()

  useEffect(() => {
    if (configurationQuery.data) {
      reset(configurationQuery.data)
      setPublishState('Configuração publicada')
    }
  }, [configurationQuery.data, reset])

  const saveMutation = useMutation({
    mutationFn: (configuration: Configuration) => configurationService.save(activeTenantId, configuration),
    onSuccess: (configuration) => {
      reset(configuration)
      setPublishState('Rascunho salvo')
    },
  })

  const publishMutation = useMutation({
    mutationFn: (configuration: Configuration) => configurationService.publish(activeTenantId, configuration),
    onSuccess: () => {
      setPublishState('Configuração publicada')
      setPublishModalOpen(false)
      setJustification('')
    },
    onError: () => setPublishState('Erro ao publicar'),
  })

  if (!activeTenant || configurationQuery.isLoading) return <PageState state="loading" />
  if (activeTenant.status === 'suspended') return <PageState state="tenant-suspended" />
  if (configurationQuery.isError) return <PageState state="error" onRetry={() => void configurationQuery.refetch()} />
  if (!configurationQuery.data || !values.company) return <PageState state="empty" />

  const onSave = (configuration: Configuration) => {
    const parsed = configurationSchema.safeParse(configuration)
    if (!parsed.success) {
      setPromptError(parsed.error.issues[0]?.message ?? 'Revise os campos obrigatórios.')
      return
    }
    setPromptError('')
    saveMutation.mutate(configuration)
  }

  const onPublish = () => {
    const configuration = getValues()
    const parsed = configurationSchema.safeParse(configuration)
    if (!parsed.success) {
      setPromptError(parsed.error.issues[0]?.message ?? 'Revise os campos obrigatórios.')
      setPublishModalOpen(false)
      return
    }
    setPromptError('')
    publishMutation.mutate(configuration)
  }

  const renderTab = () => {
    if (activeTab === 'Empresa') {
      return (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <Field label="Nome"><input className={inputClass} {...register('company.name')} /></Field>
          <Field label="Razão social"><input className={inputClass} {...register('company.legalName')} /></Field>
          <Field label="Documento"><input className={inputClass} {...register('company.document')} /></Field>
          <Field label="Slug"><input className={inputClass} {...register('company.slug')} /></Field>
          <Field label="Status">
            <select className={inputClass} {...register('company.status')}>
              <option value="active">Ativo</option>
              <option value="suspended">Suspenso</option>
            </select>
          </Field>
          <Field label="Idioma"><input className={inputClass} {...register('company.language')} /></Field>
          <Field label="Fuso horário"><input className={inputClass} {...register('company.timezone')} /></Field>
          <Field label="Ambiente"><input className={inputClass} {...register('company.environment')} /></Field>
        </div>
      )
    }

    if (activeTab === 'Identidade') {
      return (
        <div className="grid gap-4 md:grid-cols-2">
          <Card className="p-4">
            <p className="text-sm font-semibold text-[#344054]">Logo</p>
            <div className="mt-3 flex h-24 items-center justify-center rounded-lg border border-dashed border-[#D0D5DD] text-sm text-[#667085]">
              Upload preparado pela API administrativa
            </div>
          </Card>
          <Card className="p-4">
            <p className="text-sm font-semibold text-[#344054]">Favicon</p>
            <div className="mt-3 flex h-24 items-center justify-center rounded-lg border border-dashed border-[#D0D5DD] text-sm text-[#667085]">
              Arquivo mascarado e versionado
            </div>
          </Card>
          <Field label="Cor principal"><input className={inputClass} type="color" {...register('identity.primaryColor')} /></Field>
          <Field label="Cor secundária"><input className={inputClass} type="color" {...register('identity.secondaryColor')} /></Field>
          <Field label="Nome do assistente"><input className={inputClass} {...register('identity.assistantName')} /></Field>
          <Field label="Tom de voz"><input className={inputClass} {...register('identity.tone')} /></Field>
          <div className="md:col-span-2">
            <Field label="Mensagem de boas-vindas"><textarea className={textareaClass} {...register('identity.welcomeMessage')} /></Field>
          </div>
        </div>
      )
    }

    if (activeTab === 'Modelo') {
      return (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          <Field label="Provedor">
            <select className={inputClass} {...register('model.provider')}>
              <option>DeepSeek</option>
              <option>OpenAI</option>
            </select>
          </Field>
          <Field label="Modelo"><input className={inputClass} {...register('model.model')} /></Field>
          <Field label="Temperatura"><input className={inputClass} type="number" step="0.1" {...register('model.temperature', { valueAsNumber: true })} /></Field>
          <Field label="Top P"><input className={inputClass} type="number" step="0.1" {...register('model.topP', { valueAsNumber: true })} /></Field>
          <Field label="Max tokens"><input className={inputClass} type="number" {...register('model.maxTokens', { valueAsNumber: true })} /></Field>
          <Field label="Confidence threshold">
            <input className={inputClass} type="number" step="0.01" {...register('model.confidenceThreshold', { valueAsNumber: true })} />
          </Field>
          <ToggleField label="Thinking habilitado" checked={values.model.thinkingEnabled} onChange={(value) => setValue('model.thinkingEnabled', value, { shouldDirty: true })} />
          <div className="flex items-end">
            <Button type="button">
              <TestTube2 className="h-4 w-4" aria-hidden="true" />
              Testar modelo
            </Button>
          </div>
        </div>
      )
    }

    if (activeTab === 'System Prompt') {
      const prompt = values.systemPrompt ?? ''
      return (
        <div>
          <Field label="System Prompt">
            <textarea className={clsx(textareaClass, 'min-h-[320px] font-mono')} {...register('systemPrompt')} onChange={(event) => {
              register('systemPrompt').onChange(event)
              setPublishState('Alterações não salvas')
            }} />
          </Field>
          <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
            <p className="text-sm font-semibold text-[#667085]">{prompt.length} caracteres</p>
            <div className="flex flex-wrap gap-2">
              <Button type="button" onClick={() => reset(configurationQuery.data)}>
                <RotateCcw className="h-4 w-4" aria-hidden="true" />
                Restaurar versão
              </Button>
              <Button type="button"><GitCompare className="h-4 w-4" aria-hidden="true" />Visualizar diff</Button>
              <Button type="button"><FileClock className="h-4 w-4" aria-hidden="true" />Histórico</Button>
              <Button type="button"><Eye className="h-4 w-4" aria-hidden="true" />Testar prompt</Button>
            </div>
          </div>
          {promptError ? <p className="mt-2 text-sm font-semibold text-[#DC2626]">{promptError}</p> : null}
        </div>
      )
    }

    if (activeTab === 'Políticas') {
      return (
        <div className="grid gap-4 lg:grid-cols-2">
          <ToggleField label="Exigir confirmação para escrita" checked={values.policies.requireConfirmation} onChange={(value) => setValue('policies.requireConfirmation', value, { shouldDirty: true })} />
          <ToggleField label="Permitir criação" checked={values.policies.allowCreate} onChange={(value) => setValue('policies.allowCreate', value, { shouldDirty: true })} />
          <ToggleField label="Permitir atualização" checked={values.policies.allowUpdate} onChange={(value) => setValue('policies.allowUpdate', value, { shouldDirty: true })} />
          <ToggleField label="Permitir movimentação" checked={values.policies.allowMove} onChange={(value) => setValue('policies.allowMove', value, { shouldDirty: true })} />
          <ToggleField label="Permitir comentários" checked={values.policies.allowComments} onChange={(value) => setValue('policies.allowComments', value, { shouldDirty: true })} />
          <Field label="Limite máximo de ações"><input className={inputClass} type="number" {...register('policies.maxActions', { valueAsNumber: true })} /></Field>
          <Field label="Tempo de expiração da confirmação"><input className={inputClass} type="number" {...register('policies.confirmationExpiration', { valueAsNumber: true })} /></Field>
          <Field label="Retenção de memória"><input className={inputClass} type="number" {...register('policies.memoryRetention', { valueAsNumber: true })} /></Field>
          <Field label="Limite de opções"><input className={inputClass} type="number" {...register('policies.optionLimit', { valueAsNumber: true })} /></Field>
          <div className="lg:col-span-2">
            <p className="mb-2 text-sm font-semibold text-[#344054]">Intenções permitidas</p>
            <div className="flex flex-wrap gap-2">{values.policies.allowedIntents.map((intent) => <Badge key={intent} tone="purple">{intent}</Badge>)}</div>
          </div>
        </div>
      )
    }

    if (activeTab === 'Ferramentas') {
      return (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[860px] text-left text-sm">
            <thead className="bg-[#F8F9FC] text-xs uppercase tracking-wide text-[#667085]">
              <tr>
                <th className="px-4 py-3">Ferramenta</th>
                <th className="px-4 py-3">Ativa</th>
                <th className="px-4 py-3">Tipo</th>
                <th className="px-4 py-3">Exige confirmação</th>
                <th className="px-4 py-3">Papéis permitidos</th>
                <th className="px-4 py-3">Timeout</th>
                <th className="px-4 py-3">Retries</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#E4E7EC]">
              {values.tools.map((tool, index) => (
                <tr key={tool.name}>
                  <td className="px-4 py-3 font-semibold text-[#171A24]">{tool.name}</td>
                  <td className="px-4 py-3"><input type="checkbox" {...register(`tools.${index}.enabled`)} /></td>
                  <td className="px-4 py-3"><Badge tone={tool.type === 'write' ? 'yellow' : 'blue'}>{tool.type}</Badge></td>
                  <td className="px-4 py-3"><input type="checkbox" {...register(`tools.${index}.requiresConfirmation`)} /></td>
                  <td className="px-4 py-3 text-[#667085]">{tool.roles.join(', ')}</td>
                  <td className="px-4 py-3"><input className="w-20 rounded border border-[#E4E7EC] px-2 py-1" type="number" {...register(`tools.${index}.timeout`, { valueAsNumber: true })} /></td>
                  <td className="px-4 py-3"><input className="w-20 rounded border border-[#E4E7EC] px-2 py-1" type="number" {...register(`tools.${index}.retries`, { valueAsNumber: true })} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )
    }

    if (activeTab === 'Canais') {
      return (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          {values.channels.map((channel) => (
            <Card key={channel.name} className="p-4">
              <div className="flex items-center justify-between gap-3">
                <h3 className="font-bold text-[#171A24]">{channel.name}</h3>
                <Badge tone={statusTone[channel.status]}>{channel.status}</Badge>
              </div>
              <p className="mt-3 text-sm text-[#667085]">Token: {channel.tokenPreview}</p>
              <Button className="mt-4 w-full" type="button">Testar conexão</Button>
            </Card>
          ))}
        </div>
      )
    }

    if (activeTab === 'Integrações') {
      return (
        <div className="grid gap-4 lg:grid-cols-2">
          {values.integrations.map((integration) => (
            <Card key={integration.id} className="p-4">
              <div className="flex items-center justify-between gap-3">
                <h3 className="font-bold text-[#171A24]">{integration.name}</h3>
                <Badge tone={statusTone[integration.status]}>{integration.status}</Badge>
              </div>
              <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2">
                <div><dt className="text-[#667085]">Última verificação</dt><dd className="font-semibold text-[#171A24]">{integration.lastCheck}</dd></div>
                <div><dt className="text-[#667085]">Latência</dt><dd className="font-semibold text-[#171A24]">{integration.latency}</dd></div>
              </dl>
              {integration.recentError ? <p className="mt-3 text-sm font-semibold text-[#DC2626]">{integration.recentError}</p> : null}
              <Button className="mt-4" type="button">Testar</Button>
            </Card>
          ))}
        </div>
      )
    }

    if (activeTab === 'Observabilidade') {
      return (
        <div className="grid gap-4 lg:grid-cols-2">
          <ToggleField label="Langfuse ativo" checked={values.observability.langfuseEnabled} onChange={(value) => setValue('observability.langfuseEnabled', value, { shouldDirty: true })} />
          <Field label="Sampling rate"><input className={inputClass} type="number" step="0.05" {...register('observability.samplingRate', { valueAsNumber: true })} /></Field>
          <ToggleField label="Registrar prompts" checked={values.observability.logPrompts} onChange={(value) => setValue('observability.logPrompts', value, { shouldDirty: true })} />
          <ToggleField label="Registrar respostas" checked={values.observability.logResponses} onChange={(value) => setValue('observability.logResponses', value, { shouldDirty: true })} />
          <ToggleField label="Registrar custo" checked={values.observability.logCost} onChange={(value) => setValue('observability.logCost', value, { shouldDirty: true })} />
          <Field label="Retenção"><input className={inputClass} type="number" {...register('observability.retentionDays', { valueAsNumber: true })} /></Field>
          <ToggleField label="Mascaramento de dados" checked={values.observability.dataMasking} onChange={(value) => setValue('observability.dataMasking', value, { shouldDirty: true })} />
        </div>
      )
    }

    if (activeTab === 'Parâmetros') {
      const fields = [
        ['Debounce', 'parameters.debounce'],
        ['Rate limit', 'parameters.rateLimit'],
        ['Janela do rate limit', 'parameters.rateLimitWindow'],
        ['Retries', 'parameters.retries'],
        ['Queue lock', 'parameters.queueLock'],
        ['Worker sleep', 'parameters.workerSleep'],
        ['TTL de sessão', 'parameters.sessionTtl'],
        ['TTL de ações pendentes', 'parameters.pendingActionTtl'],
        ['TTL de seleção', 'parameters.selectionTtl'],
      ] as const

      return (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {fields.map(([label, path]) => (
            <Field key={path} label={label}>
              <input className={inputClass} type="number" {...register(path, { valueAsNumber: true })} />
            </Field>
          ))}
        </div>
      )
    }

    return (
      <div className="grid gap-4 lg:grid-cols-2">
        <Card className="p-4">
          <h3 className="font-bold text-[#171A24]">Papéis</h3>
          <div className="mt-3 flex flex-wrap gap-2">{values.security.roles.map((role) => <Badge key={role} tone="purple">{role}</Badge>)}</div>
        </Card>
        <Card className="p-4">
          <h3 className="font-bold text-[#171A24]">Tokens internos</h3>
          <ul className="mt-3 space-y-2 text-sm font-semibold text-[#344054]">{values.security.internalTokens.map((token) => <li key={token}>{token}</li>)}</ul>
        </Card>
        <Card className="p-4">
          <h3 className="font-bold text-[#171A24]">Secrets</h3>
          <ul className="mt-3 space-y-2 text-sm font-semibold text-[#344054]">{values.security.secrets.map((secret) => <li key={secret}>{secret}</li>)}</ul>
        </Card>
        <Card className="p-4">
          <dl className="grid gap-3 text-sm">
            <div><dt className="text-[#667085]">Última rotação</dt><dd className="font-semibold text-[#171A24]">{values.security.lastRotation}</dd></div>
            <div><dt className="text-[#667085]">Sessões ativas</dt><dd className="font-semibold text-[#171A24]">{values.security.activeSessions}</dd></div>
            <div><dt className="text-[#667085]">IP allowlist</dt><dd className="font-semibold text-[#171A24]">{values.security.ipAllowlist.join(', ')}</dd></div>
          </dl>
          <ToggleField label="Auditoria" checked={values.security.auditEnabled} onChange={(value) => setValue('security.auditEnabled', value, { shouldDirty: true })} />
        </Card>
      </div>
    )
  }

  return (
    <form
      className="pb-24"
      onChange={() => setPublishState('Alterações não salvas')}
      onSubmit={handleSubmit(onSave)}
    >
      <PageHeader
        eyebrow="4  Configurações"
        title="Configurações"
        description="Controle a identidade, políticas, ferramentas e observabilidade do tenant."
        actions={<Badge tone={publishState === 'Erro ao publicar' ? 'red' : publishState === 'Configuração publicada' ? 'green' : 'yellow'}>{publishState}</Badge>}
      />

      <Card className="overflow-hidden">
        <div className="flex gap-1 overflow-x-auto border-b border-[#E4E7EC] bg-[#F8F9FC] p-2">
          {tabs.map((tab) => (
            <button
              key={tab}
              type="button"
              className={clsx(
                'whitespace-nowrap rounded-lg px-4 py-2 text-sm font-semibold transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#6D3DF5]',
                activeTab === tab ? 'bg-[#6D3DF5] text-white shadow-sm' : 'text-[#667085] hover:bg-white hover:text-[#171A24]',
              )}
              onClick={() => setActiveTab(tab)}
            >
              {tab}
            </button>
          ))}
        </div>
        <div className="p-5">{renderTab()}</div>
      </Card>

      <div className="fixed bottom-0 left-0 right-0 z-30 border-t border-[#E4E7EC] bg-white/95 p-4 backdrop-blur lg:left-[280px]">
        <div className="mx-auto flex max-w-[1600px] flex-wrap items-center justify-between gap-3">
          <p className="text-sm font-semibold text-[#667085]">{publishState}</p>
          <div className="flex flex-wrap gap-2">
            <Button type="button" variant="danger" onClick={() => reset(configurationQuery.data)}>
              <Trash2 className="h-4 w-4" aria-hidden="true" />
              Descartar alterações
            </Button>
            <Button type="submit" disabled={saveMutation.isPending}>
              <Save className="h-4 w-4" aria-hidden="true" />
              Salvar rascunho
            </Button>
            <Button type="button" variant="primary" onClick={() => setPublishModalOpen(true)}>
              <Send className="h-4 w-4" aria-hidden="true" />
              Publicar configuração
            </Button>
          </div>
        </div>
      </div>

      <PublishModal
        open={publishModalOpen}
        onClose={() => setPublishModalOpen(false)}
        onConfirm={onPublish}
        justification={justification}
        setJustification={setJustification}
        isPublishing={publishMutation.isPending}
      />
    </form>
  )
}
