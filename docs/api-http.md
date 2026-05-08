# API HTTP

A API HTTP é implementada em `src/dadosbr/api/app.py` com FastAPI. A superfície verificada por `scripts/export_openapi.py --check` possui 71 paths OpenAPI.

## Execução

```powershell
python -m pip install -e ".[dev]"
dadosbr-api --host 127.0.0.1 --port 8000
```

Healthcheck:

```powershell
Invoke-RestMethod "http://127.0.0.1:8000/health"
```

## Contrato de Resposta

As rotas de dados retornam a estrutura comum definida em `dadosbr.core.models.DataResponse`:

```json
{
  "ok": true,
  "source_id": "bcb_sgs",
  "source_url": "https://api.bcb.gov.br/dados/serie/...",
  "license_name": "Dados Abertos BCB",
  "source_mode": "live",
  "resilience": {
    "cache_status": "miss"
  },
  "collected_at": "2026-05-06T00:00:00Z",
  "observed_at": "2026-05-05T00:00:00Z",
  "raw_sha256": "...",
  "freshness": "fresh",
  "limitations": [],
  "records": []
}
```

Falhas mantêm HTTP 200 quando vêm da fonte e `ok=false` no corpo, exceto bloqueios de política local/admin, que retornam HTTP 403.

`source_mode` informa se o dado veio de `live`, `cache_hit`, `stale_cache`, `local_snapshot`, `fallback_source` ou `error`. Quando houver fallback, `resilience` traz detalhes como idade do cache, arquivo local usado ou fonte alternativa.

## Grupos de Endpoints

| Grupo | Paths | Finalidade |
| --- | ---: | --- |
| `/health` | 1 | Liveness simples da API. |
| `/sources` | 2 | Registro de fontes, licenças e limitações. |
| `/bcb` | 3 | SGS, PTAX e Focus. |
| `/cvm` | 4 | Companhias, fundos, carteiras e FIIs. |
| `/b3` | 2 | COTAHIST por arquivo/download opt-in e parser de upload. |
| `/tesouro` | 1 | Taxas e preços do Tesouro Direto. |
| `/ibge` | 1 | SIDRA. |
| `/ipea` | 1 | IPEADATA. |
| `/cnpj` | 4 | Consulta ao índice SQLite local da Receita Federal. |
| `/admin` | 1 | Sync HTTP do índice CNPJ, bloqueado por padrão. |
| `/comex` | 4 | MDIC Comex Stat por NCM, município e tabelas. |
| `/bndes` | 3 | Operações, renda variável e catálogo CKAN. |
| `/assets`, `/issuers`, `/instruments`, `/taxonomies` | 7 | Cadastro mestre e taxonomias CNAE/NCM. |
| `/timeseries` | 3 | Séries econômicas e store SQLite local. |
| `/benchmarks`, `/macro` | 5 | Benchmarks, deflatores, comparação e calendário macro. |
| `/fixed-income` | 6 | Tesouro, debêntures, exposição de fundos, fluxos, analytics e spreads. |
| `/fundamentals` | 6 | Demonstrativos, fatos, ratios, dividendos e comparação. |
| `/corporate-actions` | 4 | Proventos, eventos, fatores e histórico ajustado. |
| `/derivatives` | 5 | Famílias, futuros, parser e normalização de opções. |
| `/curves` | 8 | Fontes de curva, Tesouro, ANBIMA, DI1, interpolação, fatores e forwards. |

## Lista de Paths

```text
POST /admin/cnpj/sync
GET /assets/search
GET /assets/{asset_id}
GET /assets/{asset_id}/history
GET /b3/cotahist
POST /b3/cotahist/parse
GET /bcb/focus
GET /bcb/ptax
GET /bcb/sgs/{series_id}
GET /benchmarks
GET /benchmarks/compare
GET /benchmarks/{benchmark_id}
GET /benchmarks/{benchmark_id}/history
GET /bndes/datasets
GET /bndes/operations
GET /bndes/variable-income
GET /cnpj/search
GET /cnpj/status
GET /cnpj/{cnpj}
GET /cnpj/{cnpj}/socios
GET /comex/municipality
GET /comex/ncm
GET /comex/ncm/summary
GET /comex/tables/{table_name}
GET /corporate-actions/types
GET /corporate-actions/{ticker}
GET /corporate-actions/{ticker}/adjusted-history
GET /corporate-actions/{ticker}/adjustment-factors
POST /curves/anbima/normalize
POST /curves/di-futures
POST /curves/discount-factors
POST /curves/forward-rates
POST /curves/interpolate
POST /curves/normalize
GET /curves/sources
GET /curves/tesouro
GET /cvm/company-reports
GET /cvm/fii/monthly
GET /cvm/funds/daily
GET /cvm/funds/portfolio
GET /derivatives/families
GET /derivatives/futures
POST /derivatives/futures/normalize
POST /derivatives/futures/parse
POST /derivatives/options/normalize
GET /fixed-income/analytics
GET /fixed-income/cashflows
GET /fixed-income/curves/credit-spread
GET /fixed-income/debentures
GET /fixed-income/funds/exposure
GET /fixed-income/tesouro
GET /fundamentals/calendar
GET /fundamentals/companies/{cvm_code}
GET /fundamentals/companies/{cvm_code}/ratios
GET /fundamentals/companies/{cvm_code}/statements
GET /fundamentals/companies/{ticker}/dividends
GET /fundamentals/compare
GET /health
GET /ibge/sidra
GET /instruments/{ticker}
GET /ipea/series/{series_code}
GET /issuers/{cnpj}
GET /macro/calendar
GET /sources
GET /sources/{source_id}
GET /taxonomies/cnae/{code}
GET /taxonomies/ncm/{code}
GET /tesouro/rates
GET /timeseries/economic/{provider}/{series_code}
GET /timeseries/store
POST /timeseries/store/assets/{asset_id}/history
```

## Rotas Sensíveis

Rotas com caminhos locais passam por `validate_optional_local_path`:

- `b3_file_path`
- `file_path`
- `db_path`

Elas ficam bloqueadas por padrão e exigem `DADOSBR_ENABLE_LOCAL_FILE_ENDPOINTS=1`. Mesmo habilitadas, só aceitam caminhos dentro de `DADOSBR_LOCAL_DATA_DIR`.

Uploads passam por `DADOSBR_MAX_UPLOAD_BYTES`, com padrão de 50 MiB. `/admin/cnpj/sync` fica bloqueada por padrão e exige `DADOSBR_ENABLE_ADMIN_HTTP=1` e `DADOSBR_ADMIN_TOKEN` não vazio; o header `X-DadosBR-Admin-Token` precisa corresponder ao token configurado.

## Exemplos

BCB SGS:

```powershell
Invoke-RestMethod "http://127.0.0.1:8000/bcb/sgs/11?last=5"
```

Consulta CNPJ depois do sync local:

```powershell
Invoke-RestMethod "http://127.0.0.1:8000/cnpj/status"
```

Histórico de ativo com arquivo COTAHIST local autorizado:

```powershell
$env:DADOSBR_ENABLE_LOCAL_FILE_ENDPOINTS="1"
$env:DADOSBR_LOCAL_DATA_DIR="C:\dadosbr-data"
Invoke-RestMethod "http://127.0.0.1:8000/assets/B3:PETR4/history?b3_file_path=C:\dadosbr-data\COTAHIST_A2026.TXT&limit=10"
```
