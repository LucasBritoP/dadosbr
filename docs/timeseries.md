# Séries Históricas e Cotações

Esta camada transforma fontes oficiais e opcionais em registros canônicos de série temporal. Ela separa dado bruto, normalizado, ajustado e persistido em SQLite local.

## Fontes

- B3 COTAHIST para OHLCV diário de ativos listados.
- BCB SGS, IPEADATA e IBGE SIDRA para séries econômicas.
- yfinance opcional para `adjusted_close`; não é fonte oficial B3.

## Endpoints HTTP

```text
GET /assets/{asset_id}/history
GET /timeseries/economic/{provider}/{series_code}
GET /timeseries/store
POST /timeseries/store/assets/{asset_id}/history
```

## Tools MCP

```text
get_asset_price_history
get_economic_timeseries
read_timeseries_store
write_asset_history_to_store
```

## Histórico de Ativos

Parâmetros principais de `/assets/{asset_id}/history`:

- `asset_id`: identificador canônico, por exemplo `B3:PETR4`.
- `start_date` e `end_date`: filtros `YYYY-MM-DD`.
- `adjusted`: quando `true`, tenta enriquecer com `adjusted_close` via yfinance.
- `b3_file_path`: arquivo COTAHIST local.
- `limit`: limite de registros.
- `store`: grava o resultado no SQLite local.
- `db_path`: caminho alternativo para o SQLite de séries.

Campos canônicos de preço:

- `series_id`, `asset_id`, `data_kind`, `frequency`, `observed_at`
- `open`, `high`, `low`, `close`, `adjusted_close`
- `volume`, `financial_volume`, `currency`, `isin`
- `simple_return`, `cumulative_return`
- `adjusted_return`, `adjusted_cumulative_return`
- `data_stage`, `is_adjusted`, `adjustment_method`, `quality_flags`

## Séries Econômicas

Provedores aceitos:

- `bcb_sgs`
- `ipeadata`
- `ibge_sidra`

Campos canônicos:

- `series_id`, `asset_id`, `data_kind`, `frequency`
- `observed_at`, `value`, `source_id`
- `data_stage`, `quality_flags`

## Store Local

O SQLite padrão fica em `.dadosbr/datasets/timeseries/timeseries.sqlite`.

Leitura:

```text
GET /timeseries/store
```

Gravação:

```text
POST /timeseries/store/assets/{asset_id}/history
```

A chave primária usa `series_id`, `asset_id` e `observed_at`; chamadas repetidas fazem upsert.

## Ajustes e Retornos

`adjusted_close` usa yfinance quando `adjusted=true`. O campo `adjustment_method` recebe `yfinance_adj_close` quando o enriquecimento foi aplicado.

Para ajuste oficial rastreável ainda é necessário conectar uma fonte estruturada de proventos, splits, grupamentos, bonificações e datas ex.

## Limitações

- B3 COTAHIST é fim de dia e não cobre intraday ou tempo real.
- Download B3 automático exige `DADOSBR_ALLOW_B3_DOWNLOAD=1`.
- yfinance é opcional, pode faltar e não substitui fonte oficial.
- `db_path` e `b3_file_path` são bloqueados por padrão na API HTTP.
