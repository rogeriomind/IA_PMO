import { useQuery } from '@tanstack/react-query'
import clsx from 'clsx'
import { Check, MessageSquareText, Paperclip, Search, Send, Smartphone, X } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { Badge } from '../components/common/Badge'
import { Button } from '../components/common/Button'
import { Card } from '../components/common/Card'
import { PageHeader } from '../components/common/PageHeader'
import { PageState } from '../components/common/PageState'
import { useTenant } from '../hooks/useTenant'
import { conversationService } from '../services/conversationService'
import type { ActionStatus, Channel, Conversation, Message } from '../types'

const channelColors: Record<Channel, string> = {
  WhatsApp: 'text-[#16A34A] bg-green-50 border-green-200',
  Telegram: 'text-[#2563EB] bg-blue-50 border-blue-200',
  'Web Chat': 'text-[#6D3DF5] bg-[#F2EDFF] border-[#D8C9FF]',
  Email: 'text-[#D97706] bg-amber-50 border-amber-200',
}
const emptyConversations: Conversation[] = []

function ChannelPill({ channel }: { channel: Channel }) {
  return (
    <span className={clsx('inline-flex items-center gap-1 rounded-full border px-2 py-1 text-xs font-bold', channelColors[channel])}>
      <Smartphone className="h-3.5 w-3.5" aria-hidden="true" />
      {channel}
    </span>
  )
}

function ActionCard({
  message,
  status,
  onConfirm,
  onCancel,
}: {
  message: Message
  status?: ActionStatus
  onConfirm: () => void
  onCancel: () => void
}) {
  if (!message.action) return null

  const actionStatus = status ?? message.action.status

  return (
    <div className="mt-3 rounded-lg border border-[#E4E7EC] bg-white p-4 shadow-sm">
      <div className="mb-3 flex items-start justify-between gap-3">
        <div>
          <p className="font-bold text-[#171A24]">{message.action.title}</p>
          <p className="text-sm text-[#667085]">ID: {message.action.id}</p>
        </div>
        <Badge tone={actionStatus === 'Confirmada' ? 'green' : actionStatus === 'Cancelada' ? 'red' : 'yellow'}>{actionStatus}</Badge>
      </div>
      <dl className="grid gap-2 text-sm sm:grid-cols-2">
        <div>
          <dt className="text-[#667085]">Prioridade</dt>
          <dd className="font-semibold text-[#171A24]">{message.action.priority}</dd>
        </div>
        <div>
          <dt className="text-[#667085]">Prazo</dt>
          <dd className="font-semibold text-[#171A24]">{message.action.deadline}</dd>
        </div>
        <div>
          <dt className="text-[#667085]">Responsável</dt>
          <dd className="font-semibold text-[#171A24]">{message.action.owner}</dd>
        </div>
        <div>
          <dt className="text-[#667085]">Status</dt>
          <dd className="font-semibold text-[#171A24]">{actionStatus}</dd>
        </div>
      </dl>
      {actionStatus === 'Aguardando confirmação' ? (
        <div className="mt-4 flex flex-wrap gap-2">
          <Button variant="primary" onClick={onConfirm}>
            <Check className="h-4 w-4" aria-hidden="true" />
            Confirmar
          </Button>
          <Button variant="danger" onClick={onCancel}>
            <X className="h-4 w-4" aria-hidden="true" />
            Cancelar
          </Button>
        </div>
      ) : null}
    </div>
  )
}

function MessageBubble({
  message,
  actionStatus,
  onConfirm,
  onCancel,
}: {
  message: Message
  actionStatus?: ActionStatus
  onConfirm: () => void
  onCancel: () => void
}) {
  const isUser = message.author === 'user'

  return (
    <div className={clsx('flex', isUser ? 'justify-end' : 'justify-start')}>
      <div
        className={clsx(
          'max-w-[780px] rounded-lg border px-5 py-4 text-sm shadow-sm',
          isUser ? 'border-[#D8C9FF] bg-[#F2EDFF] text-[#3B247A]' : 'border-[#E4E7EC] bg-white text-[#171A24]',
        )}
      >
        <p className="leading-6">{message.body}</p>
        {message.structured ? (
          <ul className="mt-3 space-y-2">
            {message.structured.map((item) => (
              <li key={item.label} className="flex gap-2">
                <span aria-hidden="true">•</span>
                <span>
                  <strong>{item.label}:</strong> {item.value}
                </span>
              </li>
            ))}
          </ul>
        ) : null}
        <ActionCard message={message} status={actionStatus} onConfirm={onConfirm} onCancel={onCancel} />
        <div className="mt-2 flex justify-end gap-1 text-xs text-[#667085]">
          <span>{message.createdAt}</span>
          {message.deliveryStatus ? <span>{message.deliveryStatus}</span> : null}
        </div>
      </div>
    </div>
  )
}

function DetailsPanel({ conversation }: { conversation: Conversation }) {
  return (
    <Card className="h-full p-5">
      <h2 className="text-xl font-bold text-[#171A24]">Detalhes da Conversa</h2>
      <dl className="mt-6 space-y-5 text-sm">
        {[
          ['Thread ID', conversation.threadId],
          ['Tenant', conversation.tenantId],
          ['Canal', conversation.channel],
          ['Usuário', conversation.user],
          ['Projeto', conversation.project],
          ['Início', conversation.startedAt],
          ['Última atividade', conversation.lastActivity],
          ['Status', conversation.status],
          ['Ações pendentes', String(conversation.pendingActions)],
          ['Custo estimado', conversation.estimatedCost],
          ['Tokens consumidos', conversation.tokens.toLocaleString('pt-BR')],
        ].map(([label, value]) => (
          <div key={label}>
            <dt className="font-semibold text-[#667085]">{label}</dt>
            <dd className="mt-1 font-bold text-[#171A24]">{value}</dd>
          </div>
        ))}
      </dl>
      <div className="mt-5">
        <p className="mb-2 text-sm font-semibold text-[#667085]">Tags</p>
        <div className="flex flex-wrap gap-2">
          {conversation.tags.map((tag) => (
            <Badge key={tag} tone="purple">
              {tag}
            </Badge>
          ))}
        </div>
      </div>
      <Button className="mt-6 w-full">Ver detalhes</Button>
    </Card>
  )
}

export function ConversationsPage() {
  const { activeTenant, activeTenantId } = useTenant()
  const params = useParams()
  const navigate = useNavigate()
  const [query, setQuery] = useState('')
  const [channelFilter, setChannelFilter] = useState<'Todos' | Channel>('Todos')
  const [statusFilter, setStatusFilter] = useState<'Todos' | 'Ativa' | 'Pendente' | 'Encerrada'>('Todos')
  const [mineOnly, setMineOnly] = useState(false)
  const [messageText, setMessageText] = useState('')
  const [actionStatusById, setActionStatusById] = useState<Record<string, ActionStatus>>({})

  const conversationsQuery = useQuery({
    queryKey: ['conversations', activeTenantId],
    queryFn: () => conversationService.list(activeTenantId),
    enabled: Boolean(activeTenantId),
  })

  const conversations = conversationsQuery.data ?? emptyConversations
  const filteredConversations = useMemo(
    () =>
      conversations.filter((conversation) => {
        const matchesQuery =
          conversation.title.toLowerCase().includes(query.toLowerCase()) ||
          conversation.lastMessage.toLowerCase().includes(query.toLowerCase())
        const matchesChannel = channelFilter === 'Todos' || conversation.channel === channelFilter
        const matchesStatus = statusFilter === 'Todos' || conversation.status === statusFilter
        const matchesMine = !mineOnly || conversation.isMine
        return matchesQuery && matchesChannel && matchesStatus && matchesMine
      }),
    [channelFilter, conversations, mineOnly, query, statusFilter],
  )

  const selectedConversation =
    filteredConversations.find((conversation) => conversation.threadId === params.threadId) ?? filteredConversations[0]

  if (!activeTenant || conversationsQuery.isLoading) return <PageState state="loading" />
  if (activeTenant.status === 'suspended') return <PageState state="tenant-suspended" />
  if (conversationsQuery.isError) return <PageState state="error" onRetry={() => void conversationsQuery.refetch()} />
  if (!selectedConversation) return <PageState state="empty" />

  return (
    <div>
      <PageHeader eyebrow="2  Conversas" title="Conversas" />
      <div className="grid min-h-[calc(100vh-160px)] gap-4 xl:grid-cols-[360px_minmax(0,1fr)_320px]">
        <Card className="overflow-hidden">
          <div className="border-b border-[#E4E7EC] p-5">
            <h2 className="text-xl font-bold text-[#171A24]">Conversas</h2>
            <label className="relative mt-4 block">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[#667085]" aria-hidden="true" />
              <input
                className="h-11 w-full rounded-lg border border-[#E4E7EC] bg-white pl-10 pr-3 text-sm focus:border-[#6D3DF5] focus:outline-none focus:ring-2 focus:ring-[#D8C9FF]"
                placeholder="Buscar conversas..."
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                aria-label="Buscar conversas"
              />
            </label>
            <div className="mt-4 grid grid-cols-2 gap-2">
              <select
                className="rounded-lg border border-[#E4E7EC] bg-white px-3 py-2 text-sm font-semibold"
                value={channelFilter}
                onChange={(event) => setChannelFilter(event.target.value as 'Todos' | Channel)}
                aria-label="Filtrar por canal"
              >
                <option>Todos</option>
                <option>WhatsApp</option>
                <option>Telegram</option>
                <option>Web Chat</option>
                <option>Email</option>
              </select>
              <select
                className="rounded-lg border border-[#E4E7EC] bg-white px-3 py-2 text-sm font-semibold"
                value={statusFilter}
                onChange={(event) => setStatusFilter(event.target.value as 'Todos' | 'Ativa' | 'Pendente' | 'Encerrada')}
                aria-label="Filtrar por status"
              >
                <option>Todos</option>
                <option>Ativa</option>
                <option>Pendente</option>
                <option>Encerrada</option>
              </select>
            </div>
            <label className="mt-3 flex items-center gap-2 text-sm font-semibold text-[#344054]">
              <input
                className="h-4 w-4 rounded border-[#D0D5DD] text-[#6D3DF5] focus:ring-[#6D3DF5]"
                type="checkbox"
                checked={mineOnly}
                onChange={(event) => setMineOnly(event.target.checked)}
              />
              Minhas
            </label>
          </div>
          <div className="max-h-[720px] overflow-y-auto p-3">
            {filteredConversations.map((conversation) => (
              <button
                key={conversation.threadId}
                type="button"
                className={clsx(
                  'mb-2 w-full rounded-lg border p-4 text-left transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#6D3DF5]',
                  selectedConversation.threadId === conversation.threadId
                    ? 'border-[#D8C9FF] bg-[#F2EDFF]'
                    : 'border-transparent bg-white hover:border-[#E4E7EC] hover:bg-[#F8F9FC]',
                )}
                onClick={() => navigate(`/conversations/${conversation.threadId}`)}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="flex items-center gap-3">
                    <MessageSquareText className="h-5 w-5 text-[#6D3DF5]" aria-hidden="true" />
                    <p className="font-bold text-[#171A24]">{conversation.title}</p>
                  </div>
                  <span className="text-xs font-semibold text-[#667085]">{conversation.lastActivity.slice(-5)}</span>
                </div>
                <p className="mt-2 line-clamp-2 text-sm text-[#667085]">{conversation.lastMessage}</p>
                <div className="mt-3 flex items-center justify-between">
                  <ChannelPill channel={conversation.channel} />
                  {conversation.unreadCount ? (
                    <span className="flex h-6 min-w-6 items-center justify-center rounded-full bg-[#6D3DF5] px-2 text-xs font-bold text-white">
                      {conversation.unreadCount}
                    </span>
                  ) : null}
                </div>
              </button>
            ))}
          </div>
        </Card>

        <Card className="flex min-h-[680px] flex-col overflow-hidden">
          <div className="flex items-center justify-between gap-4 border-b border-[#E4E7EC] p-5">
            <div className="flex items-center gap-3">
              <ChannelPill channel={selectedConversation.channel} />
              <div>
                <h2 className="font-bold text-[#171A24]">{selectedConversation.title}</h2>
                <p className="text-sm text-[#667085]">ID: {selectedConversation.threadId}</p>
              </div>
            </div>
            <Button>Mais ações</Button>
          </div>
          <div className="flex-1 space-y-5 overflow-y-auto bg-[#FCFCFD] p-5">
            {selectedConversation.messages.map((message) => {
              const actionId = message.action?.id
              return (
                <MessageBubble
                  key={message.id}
                  message={message}
                  actionStatus={actionId ? actionStatusById[actionId] : undefined}
                  onConfirm={() => actionId && setActionStatusById((current) => ({ ...current, [actionId]: 'Confirmada' }))}
                  onCancel={() => actionId && setActionStatusById((current) => ({ ...current, [actionId]: 'Cancelada' }))}
                />
              )
            })}
          </div>
          <form
            className="flex items-center gap-3 border-t border-[#E4E7EC] bg-white p-4"
            onSubmit={(event) => {
              event.preventDefault()
              setMessageText('')
            }}
          >
            <Button type="button" aria-label="Anexar arquivo">
              <Paperclip className="h-4 w-4" aria-hidden="true" />
            </Button>
            <label className="sr-only" htmlFor="conversation-message">
              Mensagem
            </label>
            <input
              id="conversation-message"
              className="h-11 flex-1 rounded-lg border border-[#E4E7EC] px-4 text-sm focus:border-[#6D3DF5] focus:outline-none focus:ring-2 focus:ring-[#D8C9FF]"
              value={messageText}
              onChange={(event) => setMessageText(event.target.value)}
              placeholder="Escreva uma mensagem..."
            />
            <Button type="submit" variant="primary" disabled={!messageText.trim()} aria-label="Enviar mensagem">
              <Send className="h-4 w-4" aria-hidden="true" />
            </Button>
          </form>
        </Card>

        <DetailsPanel conversation={selectedConversation} />
      </div>
    </div>
  )
}
