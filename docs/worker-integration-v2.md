# Integracao do Worker com a API V2

## Endpoint Principal

```http
POST /v2/agent/events
Authorization: Bearer ${AGENT_API_TOKEN}
Content-Type: application/json
```

O worker deve manter o mesmo `thread_id` para a conversa inteira. O `event_id` precisa ser estavel para replay da fila ou do Telegram.

## Envelope

```json
{
  "event_id": "telegram:update:123456",
  "request_id": "req-123",
  "correlation_id": "corr-123",
  "thread_id": "tenant:telegram:123456",
  "tenant_id": "default",
  "channel": "telegram",
  "message_type": "text",
  "user": {
    "id": "123456",
    "name": "Rogerio",
    "username": "rogerio"
  },
  "content": {
    "text": "Quero atualizar uma tarefa",
    "callback_data": null
  },
  "metadata": {
    "chat_id": "123456",
    "message_id": "987",
    "project_id": "pmo",
    "timezone": "America/Sao_Paulo"
  }
}
```

Tipos aceitos: `welcome`, `text`, `menu_selection`, `task_selection`, `confirmation`, `cancel`, `back`, `reset`.

## Resposta e Renderizacao

A API devolve UI neutra. O worker converte `ui.options[*].callback_data` para botoes do Telegram.

```json
{
  "status": "waiting_user_input",
  "flow": "main_menu",
  "step": "waiting_menu_selection",
  "message": "Ola, Rogerio! O que voce deseja fazer?",
  "ui": {
    "type": "inline_keyboard",
    "options": [
      {"id": "menu_status", "label": "Status", "callback_data": "menu:status"}
    ]
  }
}
```

## Replay

Se o worker reenviar o mesmo `event_id`, a API retorna a resposta persistida e adiciona `data.replay = true`.

## Exemplo Completo: Menu

1. Worker envia `welcome`.
2. API retorna `main_menu` com callbacks `menu:status`, `menu:create`, `menu:update`, `menu:questions`.
3. Usuario toca em `menu:update`.
4. Worker envia `message_type=menu_selection` e `content.callback_data=menu:update`.

## Exemplo Completo: Criacao

```json
{
  "message_type": "text",
  "content": {
    "text": "Criar atividade Revisar callbacks para hoje, prioridade alta. Precisamos validar os botoes.",
    "callback_data": null
  }
}
```

Resposta esperada:

- `status = awaiting_confirmation`
- `requires_confirmation = true`
- `confirmation.id` preenchido
- UI com `confirmation:approve:{id}`, `confirmation:edit:{id}`, `confirmation:reject:{id}`

O worker deve enviar a aprovacao assim:

```json
{
  "message_type": "confirmation",
  "content": {
    "text": null,
    "callback_data": "confirmation:approve:CONFIRMATION_ID"
  }
}
```

## Exemplo Completo: Atualizacao

1. `menu:update`
2. `update:list_tasks`
3. `update:task:2`
4. Texto: `Mude a data para amanha e adicione comentario aguardando retorno do CRM`
5. API retorna pending action com duas operacoes: `board_update_task` e `board_add_comment`.
6. Worker envia `confirmation:approve:{id}`.

## Tratamento de Status

- `waiting_user_input`: renderizar mensagem e botoes.
- `awaiting_confirmation`: renderizar botoes de confirmacao.
- `completed`: mostrar resultado.
- `validation_error`: pedir nova entrada.
- `conflict`: aguardar e tentar depois, se apropriado.
- `degraded`: mostrar resultado parcial.
- `error`: mostrar mensagem segura da API.
