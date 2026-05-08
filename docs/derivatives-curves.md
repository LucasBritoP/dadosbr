# Derivativos e Curvas de Juros

Esta camada adiciona uma superfície canônica para derivativos listados B3 e curvas de juros usadas por agentes e aplicações quantitativas. Ela não substitui as fontes originais; cada registro carrega `source_id`, `data_stage` e `quality_flags`.

## Derivativos

Famílias cobertas no catálogo alpha:

| Família | Tipo | Uso |
| --- | --- | --- |
| `DI1` | futuro | curva DI x Pré |
| `DAP` | futuro | cupom IPCA |
| `DOL` | futuro | dólar comercial |
| `WDO` | futuro | mini dólar |
| `IND` | futuro | Ibovespa |
| `WIN` | futuro | mini Ibovespa |
| `equity_options` | opção | opções listadas sobre ações/units |

Endpoints:

```text
GET /derivatives/families
GET /derivatives/futures
POST /derivatives/futures/parse
POST /derivatives/futures/normalize
POST /derivatives/options/normalize
```

Tools MCP:

```text
list_derivative_families
normalize_futures_quotes
get_derivative_futures_from_file
parse_derivatives_futures_text
normalize_options_chain
```

Campos principais de futuros:

- `contract_id`, `symbol`, `instrument_type`, `contract_family`
- `underlying_asset`, `asset_class`
- `maturity_code`, `maturity_month`, `maturity_year`, `maturity_date`
- `observed_at`, `business_days`, `calendar_days`
- `open_price`, `high_price`, `low_price`, `close_price`
- `settlement_price`, `previous_settlement_price`, `settlement_variation`, `settlement_rate`
- `quantity_traded`, `financial_volume`, `volume`, `open_interest`
- `price_unit`, `source_id`, `data_stage`, `quality_flags`

O parser CSV aceita aliases comuns como `Codigo Instrumento`, `Data Pregao`, `Preco Ajuste Atual`, `Preco Ajuste Anterior`, `Quantidade Negociada` e `Contratos em Aberto`.

## Curvas de Juros

Fontes lógicas:

| Curva | Origem | Observação |
| --- | --- | --- |
| `tesouro_direto` | Tesouro Transparente | curva derivada de taxas ofertadas |
| `anbima_prefixado` | ANBIMA Feed | ETTJ prefixada normalizada |
| `anbima_ipca` | ANBIMA Feed | ETTJ real/IPCA normalizada |
| `anbima_inflacao_implicita` | ANBIMA Feed | inflação implícita |
| `b3_di_pre` | B3 DI1 | curva DI x Pré derivada de PU de ajuste |

Endpoints:

```text
GET /curves/sources
GET /curves/tesouro
POST /curves/normalize
POST /curves/anbima/normalize
POST /curves/di-futures
POST /curves/interpolate
POST /curves/discount-factors
POST /curves/forward-rates
```

Tools MCP:

```text
list_interest_curve_sources
get_tesouro_interest_curve
normalize_interest_curve_points
normalize_anbima_curve_rows
build_di_curve_from_futures
interpolate_interest_curve
calculate_discount_factors
calculate_forward_rates
```

Para DI1, a curva usa:

```text
annual_rate = (100000 / settlement_price) ** (252 / business_days) - 1
discount_factor = settlement_price / 100000
```

Para ANBIMA, envie linhas com campos do Feed, por exemplo:

```json
[
  {
    "data_referencia": "2026-05-05",
    "vertice_du": 252,
    "taxa_prefixadas": "10,25",
    "taxa_ipca": "5,50",
    "taxa_implicita": "4,50"
  }
]
```

O retorno inclui `annual_rate` em decimal, `annual_rate_pct` em percentual anual, `discount_factor`, `zero_price_per_100`, tenor e flags de qualidade.

## Segurança e Licença

- Arquivos locais de derivativos exigem `DADOSBR_ENABLE_LOCAL_FILE_ENDPOINTS=1` na API HTTP.
- Uploads respeitam `DADOSBR_MAX_UPLOAD_BYTES`.
- Dados B3 e ANBIMA têm termos próprios; o projeto normaliza dados autorizados pelo operador.

## Limitações

- Sem tempo real, livro de ofertas ou intraday B3.
- Sem cliente autenticado ANBIMA.
- A camada aceita arquivos/exports locais e registros autorizados; não embute credenciais B3/ANBIMA.
- Volatilidade oficial, margem, garantias e posições por participante seguem fora da alpha.
- Layouts oficiais específicos podem exigir novos aliases, mas o schema canônico já está definido.
