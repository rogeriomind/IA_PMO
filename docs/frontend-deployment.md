# Deploy do Frontend Administrativo

O `admin-web` e uma aplicacao React/Vite independente, empacotada com Node.js 22 e Nginx 1.27. O browser chama apenas `/api`; chamadas para DeepSeek, OpenAI, Telegram, WhatsApp, MCP, Langfuse, Redis e PostgreSQL devem passar pelo backend FastAPI.

## Containers

- `pmo-ai-agent-api`: backend FastAPI/LangGraph, porta interna `8010`.
- `ia-pmo-admin-web`: frontend React/Nginx, porta interna `80`.
- Redes: `pmo_internal` para comunicacao interna e `board_pmo_default` externa mantida no backend para integracao com o Board PMO.

## Build local

```bash
cd admin-web
npm ci
npm run lint
npm run typecheck
npm run test
npm run build
```

## Docker Compose

```bash
docker compose -f docker-compose.prod.yml up -d --build pmo-ai-agent-api ia-pmo-admin-web
docker compose -f docker-compose.prod.yml ps
```

Healthchecks:

```bash
docker compose -f docker-compose.prod.yml exec -T pmo-ai-agent-api \
  python -c "import urllib.request; urllib.request.urlopen('http://localhost:8010/health')"
docker compose -f docker-compose.prod.yml exec -T ia-pmo-admin-web wget -qO- http://localhost/health
```

## Reverse proxy

Dominio esperado:

```text
https://pmo.productpulse.com.br/      -> ia-pmo-admin-web:80
https://pmo.productpulse.com.br/api/* -> pmo-ai-agent-api:8010
```

Exemplo Caddy:

```caddyfile
pmo.productpulse.com.br {
    handle /api/* {
        uri strip_prefix /api
        reverse_proxy pmo-ai-agent-api:8010
    }

    handle {
        reverse_proxy ia-pmo-admin-web:80
    }
}
```

Se o FastAPI for publicado com prefixo `/api`, remova `uri strip_prefix /api`.

## GitHub Actions

O workflow `CI` valida Python e frontend. O workflow `Deploy VPS` preserva `.env`, nao recria volumes e executa build do backend e do frontend.

## Rollback

Volte a imagem/tag ou commit anterior e recrie somente o servico afetado:

```bash
docker compose -f docker-compose.prod.yml up -d --build ia-pmo-admin-web
```

Nunca use `docker compose down -v` em rollback, para nao apagar bancos ou filas.
