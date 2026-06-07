# Pipeline GPM — Planilha Principal

Pipeline de consolidação de dados que integra Google Sheets e Google Drive,
orquestrado por GitHub Actions. Lê dados de múltiplas planilhas de origem,
aplica fórmulas/normalizações e grava CSVs consolidados no Drive.

## Visão geral

O pipeline executa **três scripts em sequência** (ver `.github/workflows/pipeline.yml`):

| Ordem | Script | O que faz |
|-------|--------|-----------|
| 1 | `compilador_consulta_servicos_GPM.py` | Baixa CSVs de uma pasta do Drive, consolida com pandas, infere/normaliza datas por arquivo, gera `BANCO.csv` e atualiza a aba `BD_ConsultaServ`. |
| 2 | `bloco3_plan_principal.py` | Para cada planilha listada em `BD_Planilhas`, reaplica as fórmulas da aba `Plan_Principal` (via gspread), aguarda o cálculo, congela os valores e reaplica formatações. |
| 3 | `compilador_planilha_principal.py` | Consolida os CSVs da pasta + lê `Plan_Principal!B5:BX` das 11 planilhas de origem, normaliza números, remove duplicados, ordena por data e grava `COMPILADO.csv` no Drive. |

Entre os passos há esperas (`sleep`) para dar tempo ao Google Sheets de recalcular fórmulas.

### Módulo compartilhado

`common.py` centraliza o que era duplicado entre os scripts:

- `load_service_account_credentials(scopes)` — carrega as credenciais da service
  account a partir do secret `GOOGLE_CREDENTIALS_B64` ou de um arquivo local;
- `execute_with_retries(request, description)` — executa chamadas do
  `google-api-python-client` com retry e backoff exponencial para erros
  transitórios (429/5xx) e timeouts.

> O `bloco3_plan_principal.py` usa **gspread** (não o `google-api-python-client`),
> então mantém seu próprio helper de retry (`executar_com_retry`, baseado em
> callable), mas reaproveita o carregamento de credenciais do `common`.

## Credenciais

É necessária uma **service account** do Google Cloud com as APIs **Drive** e
**Sheets** habilitadas, e com acesso (compartilhamento) às planilhas/pastas
envolvidas. Os scripts aceitam a credencial de duas formas:

1. **`GOOGLE_CREDENTIALS_B64`** — o JSON da service account codificado em Base64.
   Usado no GitHub Actions (configurado como *secret* do repositório).
2. **Arquivo local** `service_account.json` (ou o caminho em
   `GOOGLE_APPLICATION_CREDENTIALS`) — para execução/teste local.

> ⚠️ Nunca faça commit de credenciais. O `.gitignore` já bloqueia `*.json`
> (exceto `.mcp.json`), `*.pem`, `*.key`, `secret*`, `token*` etc.

### Gerar o `GOOGLE_CREDENTIALS_B64`

```bash
# Linux / macOS
base64 -w0 service_account.json
```
```powershell
# Windows PowerShell
[Convert]::ToBase64String([IO.File]::ReadAllBytes("service_account.json"))
```

## Execução local

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate | Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt

# Coloque service_account.json na raiz (ou defina GOOGLE_APPLICATION_CREDENTIALS)
python compilador_consulta_servicos_GPM.py
python bloco3_plan_principal.py
python compilador_planilha_principal.py
```

## Configuração por variáveis de ambiente

Todos os IDs e nomes têm defaults de produção embutidos e podem ser
sobrescritos por variáveis de ambiente (útil para apontar para um ambiente de
teste sem editar código).

### `compilador_consulta_servicos_GPM.py`

| Variável | Default | Descrição |
|----------|---------|-----------|
| `CONSULTA_NEW_FOLDER_ID` | `1QHtqM…` | Pasta de origem dos CSVs no Drive. |
| `CONSULTA_FOLDER_ID` | `17Iobc…` | Pasta de destino do `BANCO.csv`. |
| `CONSULTA_OUTPUT_CSV_NAME` | `BANCO.csv` | Nome do CSV de saída. |
| `CONSULTA_SPREADSHEET_ID` | `189JPW…` | Planilha atualizada com os dados. |
| `CONSULTA_SHEET_NAME` | `BD_ConsultaServ` | Aba de destino. |
| `UPLOAD_BANCO_PARA_DRIVE` | `true` | Se `true`, também envia o CSV ao Drive. |
| `KEEP_COL_POS_1BASED` | `47,6,27,50,52,68,70` | Posições (1-based) das colunas mantidas, na ordem. |
| `KEEP_COLS_BY_NAME` | — | Alternativa por nome de cabeçalho (lista separada por vírgulas). Se definida, tem prioridade sobre as posições. |

> A seleção por posição loga, a cada execução, o cabeçalho real encontrado em
> cada posição, facilitando detectar mudanças na ordem das colunas de origem.

### `bloco3_plan_principal.py`

| Variável | Default | Descrição |
|----------|---------|-----------|
| `LISTA_PLANILHAS_SPREADSHEET_ID` | `1kMJed…` | Planilha com a lista de destinos. |
| `ABA_LISTA_PLANILHAS` | `BD_Planilhas` | Aba com nome/ID/valor BE das planilhas. |
| `CHUNK_SIZE` | `5000` | Linhas por bloco ao escrever fórmulas. |
| `CALC_WAIT_SECONDS` | `15` | Espera para o Sheets recalcular as fórmulas. |

### `compilador_planilha_principal.py`

| Variável | Default | Descrição |
|----------|---------|-----------|
| `FOLDER_ID` | `1f5Z0f…` | Pasta de origem dos CSVs. |
| `DEST_FOLDER_ID` | `1QvBJJ…` | Pasta de destino do `COMPILADO.csv`. |
| `DEST_CSV_NAME` | `COMPILADO.csv` | Nome do CSV consolidado. |
| `SOURCE_SPREADSHEET_IDS` | (11 IDs) | Lista separada por vírgulas das planilhas de origem. |
| `SOURCE_SHEET_NAME` | `Plan_Principal` | Aba lida nas planilhas de origem. |
| `SOURCE_RANGE_A1` | `B5:BX` | Intervalo lido. |
| `TIMESTAMP_SPREADSHEET_ID` | `1-_lTK…` | Planilha de controle do timestamp. |
| `TIMESTAMP_SHEET_NAME` | `BD_Config` | Aba do timestamp. |
| `TIMESTAMP_CELL` | `C6` | Célula do timestamp. |

Comum a todos (via `common.py`):

| Variável | Default | Descrição |
|----------|---------|-----------|
| `GOOGLE_CREDENTIALS_B64` | — | JSON da service account em Base64. |
| `GOOGLE_APPLICATION_CREDENTIALS` | `service_account.json` | Caminho da credencial local. |
| `API_TIMEOUT_SECONDS` | `300` | Timeout de socket das chamadas. |
| `API_MAX_RETRIES` | `5` | Máximo de tentativas com backoff. |

## CI (GitHub Actions)

Definido em `.github/workflows/pipeline.yml`:

- Disparo **manual** (`workflow_dispatch`). O agendamento por `cron` está
  comentado no momento.
- Input opcional **`wait_seconds`** (default `120`): espera entre as etapas
  para dar tempo de propagação no Drive/Sheets. Exposto como env
  `STEP_WAIT_SECONDS` nos passos de `sleep`.
- Requer o secret **`GOOGLE_CREDENTIALS_B64`** no repositório.
- Python 3.11; instala `requirements.txt`; executa os três scripts em ordem.
- Actions: `actions/checkout@v6` e `actions/setup-python@v6` (Node 24).

## Logging

Os scripts usam o módulo `logging` (configurado em `common.py` via
`setup_logging()`), com formato `data [NÍVEL] mensagem` em stdout. Falhas
transitórias e formatações que não puderam ser aplicadas saem como `WARNING`;
erros de processamento como `ERROR`.

## Dependências

Listadas em `requirements.txt` com versões fixadas (`==`) a partir de uma
execução bem-sucedida no CI. Para atualizar, rode o pipeline, confirme o
sucesso e refixe via `pip freeze`.
