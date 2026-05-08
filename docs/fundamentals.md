# Fundamentalistas

Esta camada transforma demonstrativos CVM em fatos financeiros, indicadores, TTM, valuation e comparações simples. Ela é derivada: os dados primários continuam sendo os arquivos oficiais da CVM.

## Endpoints HTTP

```text
GET /fundamentals/companies/{cvm_code}
GET /fundamentals/companies/{cvm_code}/statements
GET /fundamentals/companies/{cvm_code}/ratios
GET /fundamentals/companies/{ticker}/dividends
GET /fundamentals/compare
GET /fundamentals/calendar
```

## Tools MCP

```text
get_company_fundamentals
get_company_statement
get_company_ratios
get_company_dividends
compare_companies_fundamentals
list_fundamentals_calendar
```

## Fontes

- CVM Dados Abertos: DFP, ITR, FRE, FCA e IPE.
- B3 COTAHIST local, quando usado para `last_price`.
- yfinance opcional para dividendos/JCP e enriquecimentos de mercado.

## Contas Canônicas

O mapeamento inicial cobre:

- `revenue`
- `gross_profit`
- `ebit`
- `net_income`
- `total_assets`
- `current_assets`
- `cash_and_equivalents`
- `current_liabilities`
- `non_current_liabilities`
- `equity`
- `gross_debt`
- `net_debt`
- `operating_cash_flow`
- `investing_cash_flow`
- `financing_cash_flow`

## Indicadores

`GET /fundamentals/companies/{cvm_code}/ratios` calcula:

- `gross_margin`
- `ebit_margin`
- `net_margin`
- `roe`
- `roa`
- `debt_to_equity`
- `eps`
- `book_value_per_share`
- `market_cap`
- `enterprise_value`
- `price_to_earnings`
- `price_to_book`
- `ev_to_ebit`
- `ev_to_ebitda`

Para múltiplos de mercado, informe `market_cap` diretamente ou combine `ticker`, `b3_file_path` e `shares_outstanding`.

## TTM e Comparação

TTM soma os últimos quatro períodos disponíveis por conta canônica. A qualidade depende da comparabilidade dos períodos CVM carregados.

Comparação:

```text
GET /fundamentals/compare?cvm_codes=9512,4170&year=2026&metric=roe
```

A rota ranqueia empresas pelo indicador informado.

## Dividendos

```text
GET /fundamentals/companies/{ticker}/dividends
```

Esta rota usa enriquecimento opcional do Yahoo Finance: primeiro tenta o endpoint JSON de chart, que é mais leve, e mantém yfinance como fallback. Ela não substitui uma fonte oficial CVM/B3 de eventos corporativos.

Quando `start_date`/`end_date` não são informados, dividendos usam `DADOSBR_YFINANCE_DIVIDEND_PERIOD` (`2y` por padrão), menor que a janela geral `DADOSBR_YFINANCE_HISTORY_PERIOD`. A chamada também respeita `DADOSBR_YFINANCE_TIMEOUT_SECONDS` e mantém cache local por `DADOSBR_YFINANCE_DIVIDEND_CACHE_TTL_SECONDS` (`86400` segundos por padrão). Isso evita travamento em tickers com histórico longo e acelera consultas repetidas.

## Limitações

- O mapeamento de contas CVM é heurístico e deve ser validado por setor.
- Bancos, seguradoras e utilities podem exigir mapeamentos próprios.
- ROE/ROA/margens vêm dos demonstrativos CVM; P/E, P/B, EV e market cap dependem de parâmetros ou enriquecimento externo.
- Dividendos/JCP oficiais ainda precisam de fonte de eventos corporativos com termos compatíveis.
- Calendário descreve famílias de documentos e frequência, não datas futuras oficiais dinâmicas.
