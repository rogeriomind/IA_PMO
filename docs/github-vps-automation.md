# Fluxo GitHub com PR e deploy automatico na VPS

Este repositorio usa dois workflows do GitHub Actions:

- `CI`: roda em `pull_request` para `main` e em `push` para `main`.
- `Deploy VPS`: roda em `push` para `main` e em `workflow_dispatch`.

## Fluxo esperado

1. Criar uma branch para a alteracao.
2. Abrir Pull Request contra `main`.
3. Aguardar o workflow `CI`.
4. Fazer merge do PR.
5. O workflow `Deploy VPS` publica automaticamente na VPS.

## Secrets necessarios

Configurados em GitHub Actions Secrets:

```text
VPS_HOST
VPS_USER
VPS_PORT
VPS_SSH_KEY
VPS_APP_DIR
VPS_AGENT_PORT
```

Valores esperados para esta VPS:

```text
VPS_USER=root
VPS_PORT=22
VPS_APP_DIR=/opt/pmo-ai-agent-api
VPS_AGENT_PORT=8010
```

O valor de `VPS_SSH_KEY` deve ser uma chave privada com acesso SSH ao usuario configurado. O segredo nunca deve ser versionado.

## O que o deploy faz

1. Roda testes antes do deploy.
2. Cria um archive do commit em `main`.
3. Envia o archive para a VPS por SSH.
4. Confere se `/opt/shared/mcp/board_pmo.md` existe.
5. Cria backup de `/opt/pmo-ai-agent-api`.
6. Sincroniza o codigo preservando:
   - `.env`
   - `.env.txt`
   - `*.db`
   - `*.sqlite`
   - `*.sqlite3`
7. Executa:

```bash
docker compose build
docker compose up -d
```

8. Valida:

```bash
curl http://localhost:8010/health
curl http://localhost:8010/ready
```

## Rollback manual

Os backups ficam em:

```text
/opt/pmo-ai-agent-api-backup-YYYYMMDDHHMMSS.tar.gz
```

Para restaurar um backup:

```bash
cd /opt
mv pmo-ai-agent-api pmo-ai-agent-api-broken
tar -xzf /opt/pmo-ai-agent-api-backup-YYYYMMDDHHMMSS.tar.gz -C /opt
cd /opt/pmo-ai-agent-api
docker compose build
docker compose up -d
```

