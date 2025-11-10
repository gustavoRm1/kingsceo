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

## Comandos do bot

Todos os comandos administrativos devem ser executados em um chat privado com o bot e pelo menos um ID presente em `ADMIN_IDS`. O bot tambem pode ser controlado por um menu interativo: qualquer usuario pode enviar `/start` para exibir botoes como **Adicione-me a um grupo**, **Grupo** e **Canal**.

- `/start`  
  Exibe o menu interativo. Util para orientar usuarios e acessar explicacoes rapidas.

- `/setcategoria Nome da Categoria`  
  Cria uma categoria e gera um *slug* unico (usado nos demais comandos). Executar apenas uma vez por categoria.

- `/addmidia <slug> <tipo> [peso]`  
  Adiciona midia a uma categoria. Responda a mensagem que contem a midia ou envie a midia junto com o comando.  
  Tipos aceitos: `photo`, `video`, `document`, `animation`. O `peso` (padrao 1) define probabilidade relativa nas selecoes aleatorias.

- `/addcopy <slug> [peso]`  
  Salva um texto associado a categoria. O texto e lido da mensagem respondida ou dos argumentos restantes. `peso` controla a chance de envio (padrao 1).

- `/setbotao <slug> <label> <url> [peso]`  
  Registra um botao inline com texto e link (URL obrigatoriamente `http://` ou `https://`). `peso` define probabilidade em envio aleatorio.

- `/setboasvindas <slug> mode=<all|text|media|buttons|none>`  
  Configura a mensagem de boas-vindas de grupos/canais ligados a categoria. Responda a mensagem contendo o conteudo desejado (texto, midia e/ou botoes). Modos:
  - `all`: envia texto, midia e botoes quando disponiveis.
  - `text`: apenas texto.
  - `media`: apenas midia.
  - `buttons`: apenas botoes inline.
  - `none`: boas-vindas desativadas.

### Fluxo basico de configuracao

1. Execute `/setcategoria` para criar a categoria e anote o *slug* retornado.  
2. Use `/addmidia`, `/addcopy` e `/setbotao` para popular os conteudos.  
3. Configure as boas-vindas com `/setboasvindas`.  
4. Adicione o bot aos grupos/canais desejados e garanta permissao de administrador.  
5. Os envios aleatorios utilizarao o material cadastrado; falhas e failover sao informados ao admin via notificacoes e logs.

## Proximas etapas

- Implementar modelos e migracoes do banco
- Desenvolver comandos administrativos
- Configurar supervisor de bots e failover

## Scripts uteis

- `poetry run python scripts/bootstrap_db.py` — executa `alembic upgrade head`
- `poetry run python scripts/migrate_json.py data.json` — importa categorias/bots de um JSON

## Testes

- Rodar testes: `poetry run pytest`
