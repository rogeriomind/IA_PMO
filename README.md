# pmo-ai-agent-api

API FastAPI separada para receber mensagens ja tratadas pelo worker PMO, classificar intencao com LangGraph usando DeepSeek via API OpenAI-compatible, consultar ou preparar acoes no MCP do Board PMO, registrar observabilidade no Langfuse e devolver uma resposta pronta para o worker enviar ao usuario.

## Arquitetura

Fluxo esperado:

```text
Worker atual
  -> POST /agent/invoke
  -> LangGraph: load_context -> classify_intent -> route_by_intent
  -> leitura: MCP read tool -> generate_response
  -> escrita: extract_entities -> validate_required_fields -> prepare_pending_action -> ask_confirmation
  -> POST /agent/confirm
  -> load_pending_action -> execute_mcp_write_tool -> generate_response
```

Toda acao de escrita cria antes um registro em `pending_actions`. O MCP so e chamado para escrita depois de `confirmed=true` em `/agent/confirm`.

## MCP Board PMO

O arquivo `/opt/shared/mcp/board_pmo.md` e a fonte de verdade das tools do board. O container monta `/opt/shared/mcp` como volume somente leitura e o servico carrega `MCP_BOARD_DOC_PATH` no startup.

Wrappers internos disponiveis:

- `search_tasks`
- `get_task`
- `create_task`
- `update_task`
- `move_task`
- `add_comment`
- `get_project_status`
- `list_blockers`
- `list_my_tasks`

Eles chamam somente tools encontradas no markdown ou mapeadas explicitamente por `MCP_TOOL_MAP_JSON`. Se uma tool estiver ausente, a API retorna uma limitacao clara e nao executa fallback destrutivo.

Exemplo de `MCP_TOOL_MAP_JSON`, se os nomes reais no markdown forem diferentes:

```json
{"create_task":"board_create_card","get_project_status":"board_project_status"}
```

## Configuracao

Crie um `.env` a partir de `.env.example` e preencha os valores reais sem commitar secrets.

Variaveis principais:

```env
AI_PROVIDER=deepseek
DEEPSEEK_API_KEY=
DEEPSEEK_MODEL=deepseek-v4-flash
DEEPSEEK_BASE_URL=https://api.deepseek.com
LLM_VALIDATE_MODEL_ON_HEALTH=true
DATABASE_URL=
MCP_BOARD_URL=docker compose -f /opt/board_pmo/docker-compose.yml exec -T api node apps/api/dist/mcp/server.js
MCP_BOARD_TRANSPORT=stdio
LANGFUSE_ENABLED=true
LANGFUSE_PUBLIC_KEY=
LANGFUSE_SECRET_KEY=
LANGFUSE_HOST=
AGENT_API_PORT=8010
```

O provedor padrao e `deepseek`. A implementacao usa `langchain-openai` porque a DeepSeek expoe um endpoint compativel com o formato OpenAI.

O MCP do board documentado em `/opt/shared/mcp/board_pmo.md` usa transporte `stdio` executando o servidor dentro do container `api` do projeto `/opt/board_pmo`. Por isso o compose monta `/var/run/docker.sock` e `/opt/board_pmo` no container da API.

Se `DATABASE_URL` estiver vazio, o servico usa SQLite local apenas para desenvolvimento. Em producao, use Postgres.

O `/health` valida a disponibilidade do modelo por padrao. Para desativar essa chamada externa em probes muito frequentes:

```env
LLM_VALIDATE_MODEL_ON_HEALTH=false
```

## Rodar local

```bash
cd pmo-ai-agent-api
python -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --host 0.0.0.0 --port 8010
```

No PowerShell:

```powershell
cd D:\IA_pmo\pmo-ai-agent-api
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
uvicorn app.main:app --host 0.0.0.0 --port 8010
```

## Rodar na VPS com Docker Compose

```bash
cd pmo-ai-agent-api
cp .env.example .env
# edite .env com os valores reais
docker compose build
docker compose up -d
```

O compose assume que a rede `board_pmo_default` ja existe:

```bash
docker network ls | grep board_pmo_default
```

Se nao existir, crie ou ajuste o nome da rede no `docker-compose.yml`:

```bash
docker network create board_pmo_default
```

## Testar health

```bash
curl http://localhost:8010/health
```

Resposta esperada:

```json
{
  "status": "ok",
  "service": "pmo-ai-agent-api",
  "model": "deepseek-v4-flash",
  "langfuse_enabled": true,
  "mcp_loaded": true,
  "checks": {
    "llm_provider": "deepseek",
    "llm_configured": true
  }
}
```

## Testar /agent/invoke

```bash
curl -X POST http://localhost:8010/agent/invoke \
  -H "Content-Type: application/json" \
  -d '{
    "conversation_id": "whatsapp_5511999999999",
    "user_id": "5511999999999",
    "channel": "whatsapp",
    "message": "Cria uma tarefa para ajustar integracao Telegram com prioridade alta",
    "metadata": {"project_id": "pmo-agent"}
  }'
```

Para escrita, a resposta deve vir com `requires_confirmation=true` e `pending_action_id`.

## Testar /agent/confirm

```bash
curl -X POST http://localhost:8010/agent/confirm \
  -H "Content-Type: application/json" \
  -d '{
    "conversation_id": "whatsapp_5511999999999",
    "user_id": "5511999999999",
    "pending_action_id": "UUID_RETORNADO_NO_INVOKE",
    "confirmed": true
  }'
```

Com `confirmed=false`, a acao pendente e cancelada e nada e alterado no board.

## Integracao futura com o worker

Configure no worker:

```env
PMO_AGENT_API_URL=http://pmo-ai-agent-api:8010
```

Depois do debounce/fila/worker tratar a mensagem, envie o payload para `POST /agent/invoke`. Se a resposta pedir confirmacao, o worker deve armazenar ou repassar o `pending_action_id` e chamar `POST /agent/confirm` quando o usuario confirmar.

## Langfuse

Quando `LANGFUSE_ENABLED=true` e as chaves estiverem configuradas, cada `/agent/invoke` e `/agent/confirm` cria um trace com:

- `session_id`: `conversation_id`
- `user_id`: `user_id`
- metadata: `intent`, `confidence`, `channel`, `project_id`
- spans por node do LangGraph e chamada MCP quando possivel

Payloads sao sanitizados para mascarar tokens, Authorization, cookies, senhas e secrets.

## Testes

```bash
cd pmo-ai-agent-api
pip install -e ".[dev]"
pytest
```
