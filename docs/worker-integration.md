# Integracao do worker com a PMO Agent API

Este documento descreve como o worker deve consumir a Agent API sem conhecer LangGraph, MCP ou regras internas do agente.

## Responsabilidades do worker

O worker deve:

- Consumir mensagens da fila.
- Recuperar metadados autenticados do usuario, tenant e canal.
- Gerar ou reutilizar `request_id`.
- Gerar ou reutilizar `correlation_id`.
- Definir um `thread_id` estavel por conversa.
- Chamar `POST /v1/agent/messages`.
- Interpretar `completed`, `awaiting_confirmation`, `rejected` e `error`.
- Enviar a resposta ao canal de origem.
- Persistir confirmacoes pendentes.
- Chamar `POST /v1/agent/confirmations` quando houver confirmacao explicita.
- Nao chamar MCP tools diretamente.

## Variaveis de ambiente do worker

```env
PMO_AGENT_API_URL=http://agent-api:8010
PMO_AGENT_API_TOKEN=
PMO_AGENT_TIMEOUT_SECONDS=30
PMO_AGENT_MAX_RETRIES=2
PMO_AGENT_VERIFY_SSL=true
```

Entre containers, nao use `localhost`. Use o nome do servico Docker ou DNS interno.

## Thread ID

O `thread_id` deve ser deterministico e estavel:

```text
{tenant_id}:{channel}:{conversation_id}
```

Exemplos:

```text
porto:telegram:123456
porto:whatsapp:5511999999999
porto:web:user-789
```

## Enviar mensagem

```http
POST /v1/agent/messages
Content-Type: application/json
Authorization: Bearer <token>
X-Request-ID: <request_id>
X-Correlation-ID: <correlation_id>
X-Tenant-ID: porto
X-User-ID: user-123
X-User-Roles: board.read,board.write,board.manage
```

Payload:

```json
{
  "thread_id": "porto:telegram:123456",
  "message": "Mostre minhas tarefas atrasadas",
  "channel": "telegram",
  "metadata": {
    "message_id": "987654",
    "chat_id": "123456",
    "source": "worker",
    "received_at": "2026-07-10T22:00:00-03:00"
  }
}
```

Resposta concluida:

```json
{
  "request_id": "request-uuid",
  "thread_id": "porto:telegram:123456",
  "status": "completed",
  "intent": "user.my_tasks",
  "message": "Encontrei suas tarefas...",
  "data": {}
}
```

Resposta aguardando confirmacao:

```json
{
  "request_id": "request-uuid",
  "thread_id": "porto:telegram:123456",
  "status": "awaiting_confirmation",
  "intent": "task.move",
  "message": "Vou mover a tarefa TASK-123 para DONE. Confirma?",
  "data": {},
  "confirmation": {
    "confirmation_id": "confirmation-uuid",
    "action": "board_move_task",
    "preview": {
      "tool": "board_move_task",
      "intent": "task.move",
      "arguments": {
        "task_id": "TASK-123",
        "status": "DONE"
      }
    }
  }
}
```

## Confirmar ou rejeitar

Confirmacao:

```http
POST /v1/agent/confirmations
Content-Type: application/json
Authorization: Bearer <token>
X-Request-ID: <request_id>
X-Correlation-ID: <correlation_id>
X-Tenant-ID: porto
X-User-ID: user-123
X-User-Roles: board.read,board.manage
```

```json
{
  "thread_id": "porto:telegram:123456",
  "confirmation_id": "confirmation-uuid",
  "approved": true,
  "message": "confirmo"
}
```

Rejeicao:

```json
{
  "thread_id": "porto:telegram:123456",
  "confirmation_id": "confirmation-uuid",
  "approved": false,
  "message": "nao"
}
```

O worker deve aceitar apenas respostas explicitas do usuario. A Agent API tambem valida mensagens ambiguas e nao executa a escrita nesses casos.

## Status esperados

| Status | Acao do worker |
| --- | --- |
| `completed` | Enviar resposta ao usuario e finalizar a mensagem. |
| `awaiting_confirmation` | Persistir `confirmation_id`, enviar pergunta ao usuario e aguardar nova mensagem. |
| `rejected` | Informar que nenhuma alteracao foi realizada. |
| `error` | Aplicar politica de erro, retry ou dead-letter conforme o codigo retornado. |

## Politica de retry

O worker pode repetir chamadas de mensagem para:

- HTTP 408, 429, 502, 503, 504.
- Timeout de conexao.
- Falha temporaria de rede ou DNS.

Nao repetir automaticamente:

- HTTP 400, 401, 403, 404, 409 permanente, 422.
- Confirmacoes de escrita sem garantia de idempotencia.

Durante retry da mesma mensagem, reutilize:

- `request_id`
- `correlation_id`
- `thread_id`

## Health e readiness

Use:

```http
GET /health
GET /ready
```

`/health` indica processo ativo. `/ready` indica dependencias principais e registry carregados.

O worker nao deve chamar health antes de cada mensagem. Use health check da infraestrutura.

## Docker e rede

Mesma rede Docker:

```yaml
networks:
  pmo-network:
    external: true
```

Worker:

```yaml
services:
  worker:
    environment:
      PMO_AGENT_API_URL: http://pmo-ai-agent-api:8010
    networks:
      - pmo-network
```

Agent API:

```yaml
services:
  pmo-ai-agent-api:
    networks:
      - pmo-network
```

## Exemplo manual

```bash
curl -X POST "${PMO_AGENT_API_URL}/v1/agent/messages" \
  -H "Authorization: Bearer ${PMO_AGENT_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -H "X-Request-ID: test-request-001" \
  -H "X-Correlation-ID: test-correlation-001" \
  -H "X-Tenant-ID: porto" \
  -H "X-User-ID: user-123" \
  -H "X-User-Roles: board.read" \
  -d '{
    "thread_id": "porto:telegram:123456",
    "message": "Mostre minhas tarefas",
    "channel": "telegram",
    "metadata": {
      "message_id": "test-message-001",
      "source": "manual-test"
    }
  }'
```

## Cliente Python

Use o exemplo em `examples/worker/pmo_agent_client.py`.

Fluxo de processamento:

1. O worker recebe a mensagem da fila.
2. Monta `thread_id`.
3. Chama `PMOAgentClient.send_message`.
4. Se `awaiting_confirmation`, persiste `confirmation_id`.
5. Ao receber confirmacao explicita do usuario, chama `PMOAgentClient.confirm_action`.

Veja `examples/worker/process_message.py` para um exemplo completo com stubs.

