# MCP

O servidor MCP expõe fontes e camadas derivadas do DadosBR para agentes. A superfície verificada em `src/dadosbr/mcp/server.py` possui 73 tools.

## Execução

```powershell
python -m pip install -e ".[dev]"
dadosbr-mcp
```

Para ferramentas que usam yfinance, instale também:

```powershell
python -m pip install -e ".[dev,enriched]"
```

## Configuração de Cliente

Use o executável `dadosbr-mcp` como servidor MCP stdio. Em clientes que aceitam comando e argumentos, configure:

```json
{
  "command": "dadosbr-mcp",
  "args": []
}
```

As variáveis de ambiente são as mesmas da API HTTP. Veja [configuration.md](configuration.md).

## Teste de Fogo

Para validar a superficie MCP inteira antes de publicar ou trocar a configuracao de um agente:

```powershell
python scripts/test_mcp_tools.py
```

O script cria uma area temporaria com fixtures locais para B3, Tesouro, Comex, Receita/CNPJ e derivativos, chama as 73 tools por stdio com timeouts isolados e grava um relatorio em `.dadosbr/reports/`. A tool administrativa `admin_sync_cnpj` deve retornar erro esperado com `admin_mcp_disabled` na configuracao segura padrao.

## Grupos de Tools

| Grupo | Tools | Exemplos |
| --- | ---: | --- |
| Fontes e metadados | 2 | `list_sources`, `get_source_metadata` |
| BCB | 3 | `get_bcb_sgs_series`, `get_bcb_ptax`, `get_bcb_focus` |
| CVM | 4 | `get_cvm_company_reports`, `get_cvm_fund_daily_info` |
| B3 COTAHIST | 2 | `get_b3_cotahist_quotes`, `parse_b3_cotahist_text` |
| Tesouro, IBGE e IPEA | 3 | `get_tesouro_rates`, `get_ibge_sidra`, `get_ipeadata_series` |
| Receita, Comex e BNDES | 12 | `get_cnpj_company`, `get_comex_ncm`, `get_bndes_operations`, `admin_sync_cnpj` |
| Cadastro mestre | 6 | `search_asset_master`, `get_instrument_master` |
| Séries históricas | 4 | `get_asset_price_history`, `read_timeseries_store` |
| Benchmarks e macro | 7 | `get_benchmark_history`, `compare_asset_to_benchmark` |
| Renda fixa | 6 | `get_tesouro_fixed_income`, `get_fixed_income_analytics` |
| Fundamentalistas | 6 | `get_company_fundamentals`, `get_company_ratios` |
| Proventos e eventos | 5 | `get_corporate_actions`, `normalize_corporate_actions` |
| Derivativos | 5 | `normalize_futures_quotes`, `parse_derivatives_futures_text` |
| Curvas de juros | 8 | `normalize_interest_curve_points`, `calculate_forward_rates` |

## Lista de Tools

```text
list_sources
get_source_metadata
get_bcb_sgs_series
get_bcb_ptax
get_bcb_focus
get_cvm_company_reports
get_cvm_fund_daily_info
get_cvm_fund_portfolio
get_cvm_fii_monthly_report
get_b3_cotahist_quotes
parse_b3_cotahist_text
get_tesouro_rates
get_ibge_sidra
get_ipeadata_series
get_cnpj_status
get_cnpj_company
search_cnpj_companies
get_cnpj_partners
admin_sync_cnpj
get_comex_ncm
summarize_comex_ncm
get_comex_municipality
get_comex_table
get_bndes_operations
get_bndes_variable_income
list_bndes_datasets
get_asset_master
search_asset_master
get_issuer_master
get_instrument_master
get_cnae_taxonomy
get_ncm_taxonomy
get_asset_price_history
get_economic_timeseries
read_timeseries_store
write_asset_history_to_store
list_benchmarks
get_benchmark_metadata
get_benchmark_history
get_real_benchmark_history
compare_asset_to_benchmark
get_yield_curve
list_macro_calendar
get_tesouro_fixed_income
get_private_credit_debentures
get_fund_fixed_income_exposure
get_fixed_income_cashflows
get_fixed_income_analytics
get_fixed_income_credit_spread_curve
get_company_fundamentals
get_company_statement
get_company_ratios
get_company_dividends
compare_companies_fundamentals
list_fundamentals_calendar
list_corporate_action_types
get_corporate_actions
get_corporate_action_factors
get_corporate_action_adjusted_history
normalize_corporate_actions
list_derivative_families
normalize_futures_quotes
get_derivative_futures_from_file
parse_derivatives_futures_text
normalize_options_chain
list_interest_curve_sources
get_tesouro_interest_curve
normalize_interest_curve_points
normalize_anbima_curve_rows
build_di_curve_from_futures
interpolate_interest_curve
calculate_discount_factors
calculate_forward_rates
```

## Paridade Com HTTP

- Rotas HTTP de upload (`/b3/cotahist/parse` e `/derivatives/futures/parse`) aparecem no MCP como payload textual JSON: `parse_b3_cotahist_text` e `parse_derivatives_futures_text`.
- `get_real_benchmark_history`, `get_yield_curve` e `normalize_corporate_actions` são conveniências MCP sem rota HTTP dedicada.
- `/health` é infraestrutura HTTP e não tem tool MCP equivalente.
- Respostas de dados incluem `source_mode` e `resilience`, iguais à API HTTP, para indicar cache hit, cache stale, snapshot local ou fonte fallback.
- `admin_sync_cnpj` roda no ambiente local do operador. Ela não usa header HTTP; exige `DADOSBR_ENABLE_ADMIN_MCP=1`, `DADOSBR_ADMIN_TOKEN` configurado e argumento `admin_token` válido.

## Segurança

O MCP executa com permissões do processo local. Não exponha um servidor MCP DadosBR para usuários não confiáveis.

Cuidados principais:

- Mantenha arquivos locais em um diretório de dados dedicado.
- Tools que recebem `file_path`, `b3_file_path` ou `db_path` exigem `DADOSBR_ENABLE_LOCAL_FILE_ENDPOINTS=1` e só aceitam caminhos dentro de `DADOSBR_LOCAL_DATA_DIR`.
- Mantenha `DADOSBR_ENABLE_ADMIN_MCP=0` por padrão. Para sync local via agente, habilite temporariamente e passe `admin_token` apenas em ambiente confiável.
- Não coloque credenciais ou bases restritas no workspace do código.
- Use `DADOSBR_MAX_UPLOAD_BYTES` para limitar textos grandes enviados a parsers MCP.
- Revise termos de B3, ANBIMA e yfinance antes de usar, armazenar ou redistribuir resultados.
