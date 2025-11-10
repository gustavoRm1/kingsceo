# KingsCEO Bot Platform

Sistema multi-bot para Telegram com gerenciamento de categorias, conteudos e failover.

## Requisitos

- Python 3.11+
- PostgreSQL 14+
- Poetry 1.8+

## Setup Rapido

1. Instale dependencias:
   ```powershell
   poetry install
   ```
2. Crie um arquivo `.env` baseado no `.env.example`.
3. Execute migracoes Alembic:
   ```powershell
   poetry run alembic upgrade head
   ```
4. Inicie um bot especifico:
   ```powershell
   poetry run kingsceo-bot --bot main
   ```

## Estrutura principal

- `app/core`: configuracao, logging, utilidades
- `app/domain`: regras de negocio
- `app/infrastructure`: banco de dados, cache, criptografia
- `app/bots`: runners, heartbeat e registro de bots
- `app/commands`: comandos administrativos
- `app/scheduling`: agendamento de envios
- `scripts`: bootstrap de dados e migracoes legadas
- `docker`: arquivos para containerizacao

## Proximas etapas

- Implementar modelos e migracoes do banco
- Desenvolver comandos administrativos
- Configurar supervisor de bots e failover

## Scripts uteis

- `poetry run python scripts/bootstrap_db.py` — executa `alembic upgrade head`
- `poetry run python scripts/migrate_json.py data.json` — importa categorias/bots de um JSON

## Testes

- Rodar testes: `poetry run pytest`
