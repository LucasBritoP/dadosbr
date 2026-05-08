# Renda Fixa

Esta camada organiza dados públicos de renda fixa em formatos canônicos para API HTTP e MCP. Ela usa Tesouro Transparente, BNDES Dados Abertos, CVM Dados Abertos e benchmarks macro.

## Endpoints HTTP

```text
GET /fixed-income/tesouro
GET /fixed-income/debentures
GET /fixed-income/funds/exposure
GET /fixed-income/cashflows
GET /fixed-income/analytics
GET /fixed-income/curves/credit-spread
```

## Tools MCP

```text
get_tesouro_fixed_income
get_private_credit_debentures
get_fund_fixed_income_exposure
get_fixed_income_cashflows
get_fixed_income_analytics
get_fixed_income_credit_spread_curve
```

## Tesouro

`GET /fixed-income/tesouro` transforma taxas e preços do Tesouro Direto em instrumentos canônicos:

- `instrument_id`
- `asset_class=government_bond`
- `issuer_name=Tesouro Nacional`
- `bond_type`
- `indexer`: `SELIC`, `IPCA` ou `PRE`
- `rate_type`: `post_fixed`, `inflation_linked` ou `fixed_rate`
- `maturity_date`, `tenor_years`, `duration_bucket`
- `buy_rate`, `sell_rate`, `buy_price`, `sell_price`

## Crédito Privado

`GET /fixed-income/debentures` normaliza registros de debêntures encontrados nos dados abertos do BNDES:

- `instrument_id`
- `asset_class=debenture`
- `issuer_cnpj`, `issuer_name`
- `ticker`
- `year`
- `invested_value`
- `quantity_final`, quando a fonte pública traz quantidade em carteira
- `asset_type` e `sector`, quando disponíveis no CSV BNDES

Esses dados são posição/investimento público do BNDES. O CSV público atual de debêntures normalmente traz emissor, CNPJ, ano, tipo de ativo, setor e quantidade final, mas não traz indexador, vencimento, preço secundário, yield de mercado nem fluxo oficial completo do papel.

## Exposição de Fundos

`GET /fixed-income/funds/exposure` usa carteiras CVM e classifica holdings por heurística:

- `government_bond`
- `debenture`
- `cri`
- `cra`
- `cdb`
- `lci`
- `lca`
- `fidc`
- `financial_bill`
- `repo`

O retorno inclui total de mercado, total de renda fixa, participação de renda fixa e agrupamento por classe.

## Fluxos e Métricas

`GET /fixed-income/cashflows` gera fluxos simples de cupom fixo.

`GET /fixed-income/analytics` calcula:

- `yield_to_maturity`
- `macaulay_duration_years`
- `modified_duration_years`
- `present_value`

Esses cálculos são genéricos. Para instrumentos reais, a qualidade depende de termos oficiais de emissão, calendário, amortizações, indexador e datas de pagamento.

## Curva de Spread

`GET /fixed-income/curves/credit-spread` calcula spread em bps contra uma taxa de benchmark quando os instrumentos possuem `yield_rate`.

Como os dados públicos atuais do BNDES normalmente não trazem yield de mercado, essa curva pode retornar vazia até que fontes de precificação ou campos enriquecidos sejam adicionados.

## Limitações

- Sem preços de mercado secundário para debêntures, CRI, CRA, CDB, LCI/LCA.
- Sem fluxos oficiais completos por emissão.
- Sem rating, garantias, senioridade, coordenadores da oferta ou covenants.
- Sem cadastro público completo por ISIN/ticker para todos os títulos privados.
- Curvas ANBIMA/IMA/IDKA dependem de termos de uso e redistribuição.
