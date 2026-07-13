# Contrato de API Administrativa

O front consome somente `VITE_API_BASE_URL`, com valor padrão `/api`. Em produção, `/api` deve ser roteado para o backend FastAPI.

## Headers

- `Authorization`
- `X-Tenant-ID`
- `X-Request-ID`
- `X-Correlation-ID`

## Endpoints esperados

- `GET /admin/v1/tenants`
- `GET /admin/v1/tenants/:tenantId`
- `GET /admin/v1/me`
- `GET /admin/v1/dashboard`
- `GET /admin/v1/conversations`
- `GET /admin/v1/conversations/:threadId`
- `GET /admin/v1/pending-actions`
- `GET /admin/v1/langgraph`
- `GET /admin/v1/langgraph/executions`
- `POST /admin/v1/langgraph/test`
- `GET /admin/v1/integrations`
- `POST /admin/v1/integrations/:id/test`
- `GET /admin/v1/configuration`
- `PUT /admin/v1/configuration`
- `POST /admin/v1/configuration/publish`
- `GET /admin/v1/audit`

## Segurança

- Exigir papel `admin` ou `agent.admin` no backend para os endpoints administrativos.
- Usar `X-Tenant-ID` para preparar multi-tenant sem colocar tenant na URL operacional.
- Retornar dados sanitizados, sem API keys, passwords, tokens completos ou credenciais MCP/Langfuse.
- Retornar estruturas vazias válidas quando uma fonte ainda não existir.

## Modo mock

Use `VITE_USE_MOCK_API=true` para testes ou desenvolvimento isolado. O fluxo normal em produção usa `VITE_USE_MOCK_API=false`.
