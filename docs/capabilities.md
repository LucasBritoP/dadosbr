# Capacidades DadosBR

Este documento mapeia o que o DadosBR entrega hoje pela API HTTP e pelo servidor MCP. Ele serve como uma visão de produto e também como guia rápido para agentes, notebooks, pipelines e aplicações que precisam consumir dados públicos do mercado brasileiro.

Status atual da alpha:

- API HTTP FastAPI com 71 paths públicos de dados, sem contar `/docs`, `/redoc` e `/openapi.json`.
- Servidor MCP com 73 ferramentas para agentes.
- Respostas padronizadas com `ok`, `source_id`, `source_url`, `license_name`, `source_mode`, `resilience`, `collected_at`, `observed_at`, `raw_sha256`, `limitations` e `records`.
- Fontes oficiais ou gratuitas quando disponíveis; enriquecimentos externos ficam identificados como tal.
- Operações administrativas, leitura de arquivos locais e download automático B3 ficam desligados por padrão.

## Quando Usar API ou MCP

| Superficie | Melhor para | Como consumir |
| --- | --- | --- |
| API HTTP | Aplicacoes, dashboards, notebooks, jobs, pipelines e integracoes entre serviços. | `dadosbr-api`, FastAPI, OpenAPI, `curl`, `httpx`, clientes REST. |
| MCP | Agentes que precisam escolher ferramentas, combinar fontes e explicar resultados com rastreabilidade. | `dadosbr-mcp`, clientes MCP compatíveis, Antigravity, Claude Desktop, Gemini CLI ou similares. |
| CLI admin | Rotinas locais de preparo de base, principalmente Receita Federal CNPJ. | `dadosbr-admin cnpj status` e `dadosbr-admin cnpj sync`. |

## Mapa de Capacidades

| Dominio | O que entrega | API HTTP | MCP |
| --- | --- | --- | --- |
| Fontes e metadados | Catálogo de fontes, licenças, frequência, notas e limitações. | `GET /sources`, `GET /sources/{source_id}` | `list_sources`, `get_source_metadata` |
| BCB macro | SGS, PTAX e expectativas Focus. | `GET /bcb/sgs/{series_id}`, `GET /bcb/ptax`, `GET /bcb/focus` | `get_bcb_sgs_series`, `get_bcb_ptax`, `get_bcb_focus` |
| IBGE e IPEA | Series SIDRA e IPEADATA em formato normalizado. | `GET /ibge/sidra`, `GET /ipea/series/{series_code}` | `get_ibge_sidra`, `get_ipeadata_series` |
| CVM companhias | DFP, ITR, FRE, FCA e IPE por ano, tipo de documento, companhia e demonstrativo. | `GET /cvm/company-reports` | `get_cvm_company_reports` |
| CVM fundos | Informe diario de fundos, carteira CDA e informes mensais FII. | `GET /cvm/funds/daily`, `GET /cvm/funds/portfolio`, `GET /cvm/fii/monthly` | `get_cvm_fund_daily_info`, `get_cvm_fund_portfolio`, `get_cvm_fii_monthly_report` |
| B3 COTAHIST | Cotacoes historicas EOD oficiais quando arquivo local/termos B3 estao configurados; parser de upload/texto. | `GET /b3/cotahist`, `POST /b3/cotahist/parse` | `get_b3_cotahist_quotes`, `parse_b3_cotahist_text` |
| Tesouro Transparente | Taxas e precos públicos do Tesouro Direto. | `GET /tesouro/rates` | `get_tesouro_rates` |
| Receita CNPJ | Indice local de empresas, estabelecimentos, socios/QSA, CNAE, Simples e busca. | `GET /cnpj/status`, `GET /cnpj/search`, `GET /cnpj/{cnpj}`, `GET /cnpj/{cnpj}/socios`, `POST /admin/cnpj/sync` | `get_cnpj_status`, `search_cnpj_companies`, `get_cnpj_company`, `get_cnpj_partners`, `admin_sync_cnpj` |
| MDIC Comex Stat | Importacao/exportacao por NCM, municipio, UF, pais e tabelas auxiliares. | `GET /comex/ncm`, `GET /comex/ncm/summary`, `GET /comex/municipality`, `GET /comex/tables/{table_name}` | `get_comex_ncm`, `summarize_comex_ncm`, `get_comex_municipality`, `get_comex_table` |
| BNDES | Operações de financiamento, renda variavel, debentures, fundos e catalogo CKAN. | `GET /bndes/operations`, `GET /bndes/variable-income`, `GET /bndes/datasets` | `get_bndes_operations`, `get_bndes_variable_income`, `list_bndes_datasets` |
| Cadastro mestre | Emissores, instrumentos B3, asset id unificado, CNAE e NCM. | `GET /assets/{asset_id}`, `GET /assets/search`, `GET /issuers/{cnpj}`, `GET /instruments/{ticker}`, `GET /taxonomies/cnae/{code}`, `GET /taxonomies/ncm/{code}` | `get_asset_master`, `search_asset_master`, `get_issuer_master`, `get_instrument_master`, `get_cnae_taxonomy`, `get_ncm_taxonomy` |
| Series temporais | Historico OHLCV de ativos, series economicas canonicas e store SQLite local. | `GET /assets/{asset_id}/history`, `GET /timeseries/economic/{provider}/{series_code}`, `POST /timeseries/store/assets/{asset_id}/history`, `GET /timeseries/store` | `get_asset_price_history`, `get_economic_timeseries`, `write_asset_history_to_store`, `read_timeseries_store` |
| Benchmarks | SELIC, CDI, IPCA, IBOV, IFIX, historico nominal/real e comparacao ativo vs benchmark. | `GET /benchmarks`, `GET /benchmarks/{benchmark_id}`, `GET /benchmarks/{benchmark_id}/history`, `GET /benchmarks/compare` | `list_benchmarks`, `get_benchmark_metadata`, `get_benchmark_history`, `get_real_benchmark_history`, `compare_asset_to_benchmark` |
| Calendario macro | Regras de frequência e divulgacao de indicadores macro. | `GET /macro/calendar` | `list_macro_calendar` |
| Renda fixa | Tesouro como instrumentos canonicos, debentures/credito privado, exposicao de fundos, fluxos e analytics. | `GET /fixed-income/tesouro`, `GET /fixed-income/debentures`, `GET /fixed-income/funds/exposure`, `GET /fixed-income/cashflows`, `GET /fixed-income/analytics`, `GET /fixed-income/curves/credit-spread` | `get_tesouro_fixed_income`, `get_private_credit_debentures`, `get_fund_fixed_income_exposure`, `get_fixed_income_cashflows`, `get_fixed_income_analytics`, `get_fixed_income_credit_spread_curve` |
| Fundamentalistas | Demonstrativos canonicos, fatos, ratios, comparacao entre companhias, calendario e dividendos. | `GET /fundamentals/calendar`, `GET /fundamentals/companies/{cvm_code}`, `GET /fundamentals/companies/{cvm_code}/statements`, `GET /fundamentals/companies/{cvm_code}/ratios`, `GET /fundamentals/companies/{ticker}/dividends`, `GET /fundamentals/compare` | `list_fundamentals_calendar`, `get_company_fundamentals`, `get_company_statement`, `get_company_ratios`, `get_company_dividends`, `compare_companies_fundamentals` |
| Proventos e eventos corporativos | Tipos de eventos, eventos por ticker, fatores acumulados e historico ajustado. | `GET /corporate-actions/types`, `GET /corporate-actions/{ticker}`, `GET /corporate-actions/{ticker}/adjustment-factors`, `GET /corporate-actions/{ticker}/adjusted-history` | `list_corporate_action_types`, `get_corporate_actions`, `get_corporate_action_factors`, `get_corporate_action_adjusted_history`, `normalize_corporate_actions` |
| Derivativos | Familias B3, normalizacao de futuros, parser CSV/texto e cadeia de opcoes. | `GET /derivatives/families`, `GET /derivatives/futures`, `POST /derivatives/futures/parse`, `POST /derivatives/futures/normalize`, `POST /derivatives/options/normalize` | `list_derivative_families`, `get_derivative_futures_from_file`, `parse_derivatives_futures_text`, `normalize_futures_quotes`, `normalize_options_chain` |
| Curvas de juros | Curva Tesouro, normalizacao generica, ANBIMA, DI via futuros, interpolacao, desconto e forwards. | `GET /curves/sources`, `GET /curves/tesouro`, `POST /curves/normalize`, `POST /curves/anbima/normalize`, `POST /curves/di-futures`, `POST /curves/interpolate`, `POST /curves/discount-factors`, `POST /curves/forward-rates` | `list_interest_curve_sources`, `get_tesouro_interest_curve`, `normalize_interest_curve_points`, `normalize_anbima_curve_rows`, `build_di_curve_from_futures`, `interpolate_interest_curve`, `calculate_discount_factors`, `calculate_forward_rates` |

## Capacidades por Tipo de Dado

### Dados brutos normalizados

O projeto busca dados nas fontes publicas, faz parsing e devolve registros normalizados sem esconder a origem.

Exemplos:

- `GET /bcb/sgs/11?last=5`
- `GET /cvm/funds/daily?limit=5`
- `GET /comex/ncm?flow=export&year=2026&limit=5`
- `GET /tesouro/rates?limit=5`

### Dados enriquecidos ou derivados

Algumas rotas combinam fontes ou calculam indicadores a partir de dados brutos.

Exemplos:

- `GET /fundamentals/companies/9512?year=2025`
- `GET /fundamentals/compare?cvm_codes=9512,4170&year=2025&metric=roe`
- `GET /benchmarks/compare?asset_id=B3:PETR4&benchmark_id=ibov&last=30`
- `GET /fixed-income/analytics?price=1000&settlement_date=2026-01-01&maturity_date=2028-01-01&principal=1000&annual_coupon_rate=0.1`
- `POST /curves/forward-rates`

### Dados locais e opt-in

Algumas capacidades dependem de arquivos locais, termos de uso ou processamento administrativo.

| Capacidade | Motivo do opt-in |
| --- | --- |
| B3 COTAHIST automático | Exige aceite dos termos de Market Data da B3; use `DADOSBR_ALLOW_B3_DOWNLOAD=1` apenas apos aceite. |
| Caminhos locais em API/MCP | Pode expor arquivos da maquina; exige `DADOSBR_ENABLE_LOCAL_FILE_ENDPOINTS=1` e `DADOSBR_LOCAL_DATA_DIR`. |
| Receita CNPJ sync HTTP/MCP | Baixa e indexa bases grandes; exige `DADOSBR_ENABLE_ADMIN_HTTP=1` ou `DADOSBR_ENABLE_ADMIN_MCP=1` e `DADOSBR_ADMIN_TOKEN`. |
| ANBIMA | O projeto normaliza linhas fornecidas pelo usuario, mas nao baixa feed restrito automaticamente. |

## Exemplos de Uso por Persona

### Agente MCP de analise

Um agente pode:

1. chamar `list_sources` para explicar fontes e licenças;
2. chamar `get_company_fundamentals` para montar um snapshot de companhia CVM;
3. chamar `get_company_dividends` e `get_corporate_actions` para eventos;
4. chamar `compare_asset_to_benchmark` para retorno relativo;
5. responder citando `source_id`, `source_url`, `source_mode` e `limitations`.

### Notebook de pesquisa

Um notebook pode:

1. consumir `GET /timeseries/economic/bcb_sgs/11?last=252`;
2. persistir historico de ativo com `POST /timeseries/store/assets/B3:PETR4/history`;
3. ler o store por `GET /timeseries/store`;
4. juntar com `GET /benchmarks/selic/history` e `GET /fundamentals/companies/9512/ratios`.

### Pipeline local de base mestre

Um job local pode:

1. rodar `dadosbr-admin cnpj sync --period latest`;
2. consultar `GET /cnpj/status`;
3. enriquecer tickers com `GET /instruments/{ticker}`;
4. resolver emissores por `GET /issuers/{cnpj}`;
5. salvar resultados com hash e metadados de fonte.

## Garantias de Resposta

Toda resposta de fonte segue a mesma ideia:

```json
{
  "ok": true,
  "source_id": "bcb_sgs",
  "source_url": "https://...",
  "license_name": "Dados Abertos BCB",
  "source_mode": "live",
  "resilience": {},
  "collected_at": "2026-05-08T00:00:00Z",
  "observed_at": "2026-05-07T00:00:00Z",
  "raw_sha256": "...",
  "limitations": [],
  "records": []
}
```

Modos comuns de `source_mode`:

| Valor | Significado |
| --- | --- |
| `live` | Fonte consultada diretamente. |
| `cache_hit` | Resposta veio de cache fresco. |
| `stale_cache` | Fallback seguro com cache antigo quando a fonte falhou. |
| `local_snapshot` | Arquivo local ou fixture configurada. |
| `error` | Falha estruturada com `error.code`, `error.message` e, quando aplicavel, `retryable`. |

## Limites Importantes

- DadosBR nao recomenda investimentos.
- O software esta sob MIT, mas os dados continuam sujeitos aos termos das fontes.
- CVM, Receita, B3, MDIC e BNDES podem oscilar, mudar layout ou ficar indisponíveis.
- Bases grandes devem ser consumidas com filtros, cache e indices locais.
- `yfinance` e Yahoo Chart sao enriquecimentos para dividendos/eventos quando usados; nao substituem fonte oficial.
- A alpha prioriza rastreabilidade e seguranca antes de cobertura comercial completa.

## Checklist de Prontidao da Alpha

Antes de publicar ou validar uma instalacao:

```powershell
python -m ruff check . --no-cache
python -m pytest -q
python -m compileall -q src scripts tests
python scripts/export_openapi.py
python scripts/test_mcp_tools.py
python scripts/test_api.py
```

Os testes de fogo atuais cobrem:

- 73 tools MCP executadas, com `admin_sync_cnpj` bloqueado por padrão como erro esperado.
- 73 chamadas HTTP na bateria de API, incluindo casos esperados de erro estruturado.
- Sync CNPJ administrativo habilitado com token e fixture local.
