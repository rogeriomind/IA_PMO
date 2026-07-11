# Migracao da V1 para a V2

## Diferencas Principais

| Area | V1 | V2 |
| --- | --- | --- |
| Entrada | `/v1/agent/messages` e `/v1/agent/confirmations` | `/v2/agent/events` |
| Estado | request orientado a intent | conversa orientada a fluxo/step |
| UI | mensagem simples | UI neutra com opcoes estruturadas |
| Confirmacao | endpoint separado | subgrafo central via evento `confirmation` |
| Replay | limitado | `event_id` persistido em `agent_events` |
| Selecao de tarefas | texto/ID | mapa temporario numero -> `task_id` |
| Persistencia | pending actions + auditoria | threads, drafts, mapas, eventos, pending actions |

## Flags

```env
LEGACY_ENDPOINTS_ENABLED=false
V1_ENDPOINTS_ENABLED=true
V2_ENDPOINTS_ENABLED=true
```

Em desenvolvimento, os endpoints legados podem continuar ativos. Em producao, mantenha `LEGACY_ENDPOINTS_ENABLED=false` por padrao.

## Passos Recomendados

1. Subir PostgreSQL e aplicar migrations.
2. Configurar `AGENT_API_TOKEN`.
3. Ajustar o worker para montar o envelope v2.
4. Manter o mesmo `thread_id` por usuario/canal/tenant.
5. Converter botoes do Telegram a partir de `ui.options`.
6. Enviar callbacks como `message_type=menu_selection`, `task_selection` ou `confirmation`.
7. Tratar replay por `event_id`.
8. Migrar gradualmente comandos da v1 para a v2.
9. Desativar v1 depois de validar operacao e observabilidade.

## Aplicar Migrations

```bash
alembic upgrade head
```

O Compose local ja inclui PostgreSQL com volume persistente:

```bash
docker compose up -d postgres
docker compose up -d pmo-ai-agent-api
```

Redis para locks distribuidos:

```bash
docker compose --profile redis up -d redis
```

## Exemplo V1

```json
{
  "thread_id": "default:telegram:123",
  "message": "Minhas tarefas",
  "channel": "telegram",
  "metadata": {"project_id": "pmo"}
}
```

## Exemplo V2 Equivalente

```json
{
  "event_id": "telegram:update:123",
  "request_id": "req-123",
  "correlation_id": "corr-123",
  "thread_id": "default:telegram:123",
  "tenant_id": "default",
  "channel": "telegram",
  "message_type": "text",
  "user": {"id": "123", "name": "Rogerio", "username": "rogerio"},
  "content": {"text": "Minhas tarefas", "callback_data": null},
  "metadata": {"chat_id": "123", "message_id": "10", "project_id": "pmo", "timezone": "America/Sao_Paulo"}
}
```

## Confirmacao

Na v1, o worker chamava `/v1/agent/confirmations`. Na v2, ele envia outro evento:

```json
{
  "message_type": "confirmation",
  "content": {
    "text": null,
    "callback_data": "confirmation:approve:CONFIRMATION_ID"
  }
}
```

## Desativacao Final

Quando o worker estiver 100% na v2:

```env
LEGACY_ENDPOINTS_ENABLED=false
V1_ENDPOINTS_ENABLED=false
V2_ENDPOINTS_ENABLED=true
```

Depois disso, remova chamadas antigas do worker e monitore:

- `agent_events_total`
- `agent_confirmations_total`
- `agent_errors_total`
- auditoria em `agent_tool_execution_audit`
