# Benchmarks e Indicadores Macro

Esta camada organiza benchmarks em aliases estáveis para agentes e aplicações. Ela usa fontes oficiais quando disponíveis e marca enriquecimentos opcionais quando a fonte não é oficial.

## Catálogo Inicial

| Alias | Fonte | Código/símbolo | Tipo | Frequência | Oficial |
| --- | --- | --- | --- | --- | --- |
| `selic` | BCB SGS | `11` | juros | diária | sim |
| `cdi` | BCB SGS | `12` | juros | diária | sim |
| `ipca` | BCB SGS | `433` | inflação | mensal | sim |
| `igpm` | BCB SGS | `189` | inflação | mensal | sim |
| `ptax_usd` | BCB SGS | `1` | câmbio | diária | sim |
| `ibov` | yfinance opcional | `^BVSP` | índice de mercado | diária | não |
| `ifix` | yfinance opcional | `IFIX.SA` | índice de mercado | diária | não |

## Endpoints HTTP

```text
GET /benchmarks
GET /benchmarks/{benchmark_id}
GET /benchmarks/{benchmark_id}/history
GET /benchmarks/compare
GET /macro/calendar
```

## Tools MCP

```text
list_benchmarks
get_benchmark_metadata
get_benchmark_history
get_real_benchmark_history
compare_asset_to_benchmark
get_yield_curve
list_macro_calendar
```

## Histórico

`GET /benchmarks/{benchmark_id}/history` retorna registros com:

- `benchmark_id`, `series_id`, `name`
- `data_kind`, `frequency`, `observed_at`, `value`, `unit`
- `source_id`, `provider`, `official`
- `period_factor`, `accumulated_factor`
- `simple_return`, `cumulative_return`
- `revision_policy`, `quality_flags`

Para séries percentuais como SELIC, CDI, IPCA e IGP-M, `period_factor` e `accumulated_factor` ajudam a compor a série. Para índices de mercado, `simple_return` e `cumulative_return` usam variação do nível do índice.

## Série Real Deflacionada

Use:

```text
GET /benchmarks/{benchmark_id}/history?real=true&deflator=ipca
```

O retorno adiciona:

- `deflator_id`
- `deflator_factor`
- `real_value`
- `data_stage=deflated`

## Comparação Ativo vs Benchmark

Exemplo:

```text
GET /benchmarks/compare?asset_id=B3:PETR4&benchmark_id=ibov
```

O retorno alinha datas e calcula:

- `asset_return`
- `benchmark_return`
- `excess_return`

Use `b3_file_path` para comparar com COTAHIST local autorizado e `adjusted=true` para usar retorno ajustado quando houver `adjusted_close`.

## Curva Tesouro e Calendário Macro

A curva derivada de títulos do Tesouro Direto fica no domínio de curvas:

```text
GET /curves/tesouro
```

No MCP:

- `get_tesouro_interest_curve`: curva normalizada.
- `get_yield_curve`: atalho para pontos brutos de vencimento e taxa.

`GET /macro/calendar` retorna regras e frequências de divulgação; a alpha ainda não calcula datas futuras oficiais dinamicamente.

## Limitações

- IBOV/IFIX usam yfinance opcional por enquanto, não redistribuição oficial B3.
- Calendário macro atual descreve regras/frequências, não datas oficiais futuras.
- Revisões são marcadas via `revision_policy`; ainda não há versionamento histórico por vintage.
- IMA/IDKA/curvas ANBIMA completas não são baixadas automaticamente.
