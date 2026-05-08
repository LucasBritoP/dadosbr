# Proventos e Eventos Corporativos

Esta camada cria um schema canônico para proventos e eventos corporativos. Ela também calcula fatores de ajuste e aplica esses fatores em históricos OHLCV.

## Endpoints HTTP

```text
GET /corporate-actions/types
GET /corporate-actions/{ticker}
GET /corporate-actions/{ticker}/adjustment-factors
GET /corporate-actions/{ticker}/adjusted-history
```

## Tools MCP

```text
list_corporate_action_types
get_corporate_actions
get_corporate_action_factors
get_corporate_action_adjusted_history
normalize_corporate_actions
```

## Fontes

- Yahoo Finance Chart JSON como caminho rápido para dividendos e splits.
- yfinance opcional como fallback quando o Chart JSON falha.
- Registros externos ou manuais via normalização.
- B3 COTAHIST local para combinar histórico de preço com fatores.

Yahoo Finance/yfinance não são fontes oficiais B3/CVM. A busca automática usa timeout e cache local de 24 horas por padrão para evitar travamentos de agente MCP. A função `normalize_corporate_actions` permite acoplar uma fonte oficial estruturada no futuro sem trocar o schema.

## Tipos Suportados

- `dividend`
- `jcp`
- `amortization`
- `capital_reduction`
- `split`
- `reverse_split`
- `bonus`
- `subscription`
- `merger`
- `spin_off`

## Schema Canônico

Cada evento normalizado inclui:

- `action_id`
- `ticker`, `asset_id`, `isin`, `issuer_cnpj`, `cvm_code`
- `event_type`, `event_category`
- `declared_date`, `approval_date`, `record_date`, `ex_date`, `payment_date`
- `amount_per_share`, `currency`
- `ratio`, `subscription_price`, `reference_price`
- `price_adjustment_factor`, `share_adjustment_factor`
- `status`
- `source_id`, `source_url`, `document_id`
- `data_stage`, `quality_flags`

## Fatores de Ajuste

Eventos em dinheiro calculam fator de preço quando `reference_price` está disponível:

```text
(reference_price - amount_per_share) / reference_price
```

Splits usam:

```text
price_adjustment_factor = 1 / ratio
share_adjustment_factor = ratio
```

`GET /corporate-actions/{ticker}/adjustment-factors` retorna fatores acumulados de preço e quantidade.

## Histórico Ajustado

`GET /corporate-actions/{ticker}/adjusted-history` combina COTAHIST local com eventos disponíveis e adiciona:

- `adjusted_open`
- `adjusted_high`
- `adjusted_low`
- `adjusted_close`
- `adjusted_volume`
- `corporate_action_price_factor`
- `corporate_action_share_factor`
- `adjustment_event_count`
- `adjustment_action_ids`

## Limitações

- Yahoo Finance/yfinance não são fontes oficiais B3/CVM.
- Eventos em dinheiro precisam de `reference_price` para fator de preço.
- Subscrições, reorganizações e eventos complexos podem exigir regras específicas.
- Ainda falta fonte oficial estruturada de proventos/eventos com data-com, data-ex, pagamento, status e documento regulatório.
