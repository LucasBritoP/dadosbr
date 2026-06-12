# Configuração

Este guia lista a configuração verificada em `.env.example`, `pyproject.toml` e nos módulos de segurança, cache e conectores.

## Dependências

Requisitos do pacote:

- Python `>=3.11`.
- Dependências base: FastAPI, Uvicorn, Pydantic, certifi e MCP.
- Dependências de desenvolvimento: pytest, Ruff, httpx e build.
- Enriquecimento opcional: `yfinance`, instalado com o extra `enriched`.

```powershell
python -m pip install -e ".[dev]"
python -m pip install -e ".[dev,enriched]"
```

Use o extra `enriched` somente quando precisar de `adjusted_close`, dividendos ou índices de mercado via yfinance. Esses dados não são oficiais B3/CVM.

## Variáveis de Ambiente

| Variável | Obrigatória | Padrão em `.env.example` | Uso |
| --- | --- | --- | --- |
| `DADOSBR_CACHE_DIR` | Não | `.dadosbr/cache` | Raiz do cache HTTP em disco. |
| `DADOSBR_CACHE_TTL_SECONDS` | Não | `3600` | TTL do cache HTTP, em segundos. |
| `DADOSBR_HTTP_CACHE_MAX_INLINE_BYTES` | Não | `1048576` | Tamanho máximo salvo inline em JSON antes de usar sidecar `.body`. |
| `DADOSBR_HTTP_CACHE_MAX_BODY_BYTES` | Não | `104857600` | Tamanho máximo de corpo HTTP cacheável; acima disso a resposta vem com `x-dadosbr-cache=skip`. |
| `DADOSBR_DISABLE_HTTP_CACHE` | Não | `0` | Desativa cache quando valor é `1`, `true`, `yes` ou `on`. |
| `DADOSBR_DISABLE_STALE_CACHE` | Não | `0` | Desativa fallback para cache expirado quando a fonte falha. |
| `DADOSBR_STRICT_FRESH` | Não | `0` | Força falha em vez de usar cache stale. |
| `DADOSBR_MAX_STALE_SECONDS` | Não | `604800` | Idade máxima global para cache stale; `0` desativa o uso de cache stale. |
| `DADOSBR_HTTP_RETRIES` | Não | `2` | Número máximo de tentativas por chamada HTTP retryable. |
| `DADOSBR_HTTP_RETRY_BACKOFF_SECONDS` | Não | `0.25` | Backoff base entre retentativas HTTP. |
| `DADOSBR_CA_BUNDLE` | Não | vazio | Caminho para bundle CA customizado; também são aceitos `REQUESTS_CA_BUNDLE` e `SSL_CERT_FILE`. |
| `DADOSBR_CSV_FIELD_SIZE_LIMIT` | Não | `104857600` | Limite de campo CSV usado por leitores de CSV. |
| `DADOSBR_ALLOW_B3_DOWNLOAD` | Não | `0` | Libera download automático de COTAHIST B3 quando configurado como `1`. |
| `DADOSBR_B3_COTAHIST_FILE` | Não | vazio | Arquivo COTAHIST local usado antes de qualquer download. |
| `DADOSBR_ENABLE_LOCAL_FILE_ENDPOINTS` | Não | `0` | Libera API HTTP e tools MCP que recebem `file_path`, `b3_file_path` ou `db_path`. |
| `DADOSBR_LOCAL_DATA_DIR` | Não | `.dadosbr` | Raiz permitida para caminhos locais quando endpoints de arquivo estão habilitados. |
| `DADOSBR_MAX_UPLOAD_BYTES` | Não | `52428800` | Tamanho máximo de uploads HTTP e payloads textuais MCP convertidos para bytes. |
| `DADOSBR_ENABLE_ADMIN_HTTP` | Não | `0` | Libera rotas HTTP `/admin/*` em ambiente confiável. |
| `DADOSBR_ENABLE_ADMIN_MCP` | Não | `0` | Libera tools MCP administrativas, como `admin_sync_cnpj`, em ambiente confiável. |
| `DADOSBR_ADMIN_TOKEN` | Condicional | vazio | Token obrigatório para admin HTTP ou MCP quando a superfície admin correspondente está habilitada. |
| `DADOSBR_CVM_COMPANY_REPORT_TIMEOUT_SECONDS` | Não | `10` | Timeout usado em consultas de relatórios de companhias CVM. |
| `DADOSBR_YFINANCE_TIMEOUT_SECONDS` | Não | `30` | Timeout usado em enriquecimentos yfinance. |
| `DADOSBR_YFINANCE_HISTORY_PERIOD` | Não | `5y` | Período padrão yfinance quando `start_date`/`end_date` não são informados. |
| `DADOSBR_YFINANCE_DIVIDEND_PERIOD` | Não | `2y` | Janela padrão específica para dividendos yfinance. |
| `DADOSBR_YFINANCE_DIVIDEND_CACHE_TTL_SECONDS` | Não | `86400` | TTL do cache local de dividendos yfinance. |
| `DADOSBR_YFINANCE_ACTION_PERIOD` | Não | `2y` | Janela padrão para eventos corporativos via Yahoo Chart/yfinance. |
| `DADOSBR_YFINANCE_ACTION_CACHE_TTL_SECONDS` | Não | `86400` | TTL do cache local de eventos corporativos enriquecidos. |
| `DADOSBR_RECEITA_CNPJ_BASE_URL` | Não | URL oficial Receita | Base primária para dados públicos CNPJ. |
| `DADOSBR_RECEITA_CNPJ_FALLBACK_BASE_URLS` | Não | vazio | Bases alternativas separadas por vírgula ou ponto e vírgula. |
| `DADOSBR_TESOURO_PACKAGE_FILE` | Não | vazio | Fixture local do package CKAN do Tesouro. |
| `DADOSBR_TESOURO_RATES_CSV_FILE` | Não | vazio | CSV local de taxas do Tesouro Direto. |
| `DADOSBR_COMEX_DATA_DIR` | Não | vazio | Diretório local para CSVs MDIC Comex Stat. |
| `DADOSBR_COMEX_VERIFY_SSL` | Não | `1` | Valida SSL nas URLs MDIC Comex; `0` desativa apenas como fallback local temporário. |

Nenhuma variável é obrigatória para importar o pacote ou iniciar a API. Algumas funcionalidades retornam erro estruturado quando dependem de arquivo, índice local, extra opcional ou opt-in não configurado.

## Configuração Local Recomendada

Para uso local com arquivos autorizados:

```powershell
$env:DADOSBR_ENABLE_LOCAL_FILE_ENDPOINTS="1"
$env:DADOSBR_LOCAL_DATA_DIR="C:\dadosbr-data"
```

Somente caminhos resolvidos dentro de `DADOSBR_LOCAL_DATA_DIR` são aceitos. Caminhos fora dessa raiz retornam HTTP 403 com código `local_file_outside_allowed_root`.

Para admin HTTP local:

```powershell
$env:DADOSBR_ENABLE_ADMIN_HTTP="1"
$env:DADOSBR_ADMIN_TOKEN="<TOKEN>"
```

Envie o token no header:

```text
X-DadosBR-Admin-Token: <TOKEN>
```

Para admin MCP local:

```powershell
$env:DADOSBR_ENABLE_ADMIN_MCP="1"
$env:DADOSBR_ADMIN_TOKEN="<TOKEN>"
```

Informe o mesmo valor no argumento `admin_token` da tool administrativa. O MCP não reutiliza headers HTTP.

## CNPJ Receita Federal

As consultas CNPJ dependem de um índice SQLite local. O comando admin baixa os ZIPs públicos da Receita e reconstrói o índice:

```powershell
dadosbr-admin cnpj sync --period latest --groups empresas,estabelecimentos,socios,simples,domains
dadosbr-admin cnpj status
```

O caminho padrão do banco é `.dadosbr/datasets/receita_cnpj/index/cnpj.sqlite`. Use `--dataset-dir` e `--db-path` para separar downloads, banco e código.

O conector tenta `DADOSBR_RECEITA_CNPJ_BASE_URL` primeiro e depois cada URL de `DADOSBR_RECEITA_CNPJ_FALLBACK_BASE_URLS`, preservando os erros por fonte no retorno quando todas falham.

O download dos ZIPs é feito em streaming para arquivo temporário com rename atômico; o indexador processa o CSV dentro do ZIP linha a linha para reduzir pressão de memória na base completa.

## B3 COTAHIST

O fluxo mais seguro e reprodutível é usar arquivo local:

```powershell
$env:DADOSBR_B3_COTAHIST_FILE="C:\dadosbr-data\COTAHIST_A2026.TXT"
```

Download automático da URL oficial da B3 continua bloqueado por padrão. Habilite somente em ambiente autorizado:

```powershell
$env:DADOSBR_ALLOW_B3_DOWNLOAD="1"
```

O projeto também reconhece o legado `PREVER_AGENT_ALLOW_B3_PUBLIC_DOWNLOAD=1`, mas a variável atual documentada é `DADOSBR_ALLOW_B3_DOWNLOAD`.

## Cache e Fixtures Locais

BCB, Tesouro, Comex e outros conectores usam cache HTTP em disco quando disponível. Para uma execução sem cache:

```powershell
$env:DADOSBR_DISABLE_HTTP_CACHE="1"
```

Payloads pequenos são salvos inline no JSON do cache. Payloads maiores que `DADOSBR_HTTP_CACHE_MAX_INLINE_BYTES` usam sidecar `.body`; payloads acima de `DADOSBR_HTTP_CACHE_MAX_BODY_BYTES` não são cacheados.

Para testes reprodutíveis ou operação offline parcial, use as variáveis de fixture:

- `DADOSBR_TESOURO_PACKAGE_FILE`
- `DADOSBR_TESOURO_RATES_CSV_FILE`
- `DADOSBR_COMEX_DATA_DIR`
- `DADOSBR_B3_COTAHIST_FILE`

## MDIC Comex e SSL

O cliente HTTP usa `certifi` por padrão, além de respeitar `DADOSBR_CA_BUNDLE`, `REQUESTS_CA_BUNDLE` e `SSL_CERT_FILE`.

Se o servidor MDIC falhar em uma instalação Windows específica por cadeia de certificados, prefira configurar um bundle CA válido. Para teste local controlado, o conector Comex aceita:

```powershell
$env:DADOSBR_COMEX_VERIFY_SSL="0"
```

Não use essa configuração em produção ou em ambiente que processe dados não confiáveis.

## Execução

API HTTP:

```powershell
dadosbr-api --host 127.0.0.1 --port 8000
```

Servidor MCP:

```powershell
dadosbr-mcp
```

Validação local:

```powershell
python -m ruff check src tests scripts
python -m pytest -q
python scripts/export_openapi.py --check
```
