# Qualidade, Auditoria e Erros

O DadosBR usa um envelope comum para tornar cada consulta rastreável e comparável entre fontes. A estrutura está em `dadosbr.core.models.DataResponse` e é preenchida por `make_success` e `make_failure`.

## Resposta Padrão

Campos comuns:

- `ok`: sucesso lógico da consulta.
- `source_id`: fonte lógica registrada.
- `source_url`: origem primária, arquivo local ou URI `local://`.
- `license_name`: licença ou termos conhecidos da fonte.
- `source_mode`: modo de obtenção: `live`, `cache_hit`, `stale_cache`, `local_snapshot`, `fallback_source` ou `error`.
- `resilience`: metadados de retry/cache/fallback, como `cache_status`, idade do cache, arquivo local ou fonte alternativa.
- `collected_at`: instante de coleta/processamento.
- `observed_at`: data mais recente observada nos registros, quando disponível.
- `raw_sha256`: hash do payload bruto ou dos registros normalizados.
- `freshness`: `fresh`, `stale`, `old`, `no_data`, `error` ou `unknown`.
- `limitations`: limitações específicas da consulta.
- `records`: registros retornados.
- `error`: erro estruturado quando `ok=false`.

## Fallbacks Seguros

Chamadas HTTP retryable usam retentativas curtas. Quando uma fonte falha e há cache expirado dentro da política configurada, a resposta pode voltar com `source_mode=stale_cache`, `resilience.stale=true` e uma limitação explícita. Use `DADOSBR_STRICT_FRESH=1` ou `DADOSBR_DISABLE_STALE_CACHE=1` para exigir dado fresco.

Fontes com snapshot local, como COTAHIST, Tesouro, Comex e índices CNPJ, retornam `source_mode=local_snapshot`. Mirrors configurados para Receita CNPJ aparecem como `fallback_source`.

## Erros Estruturados

`error` contém:

- `code`
- `message`
- `source_id`
- `source_url`
- `retryable`
- `details`

Exemplos de códigos usados no código:

| Código | Situação típica |
| --- | --- |
| `source_unavailable` | Fonte indisponível, download bloqueado ou sem dados. |
| `network_error` | Falha de rede. |
| `timeout` | Timeout de requisição. |
| `http_error` | Status HTTP >= 400 vindo da fonte. |
| `parse_error` | Payload ou arquivo não pôde ser parseado. |
| `validation_error` | Parâmetro inválido. |
| `not_found` | Fonte, benchmark ou entidade desconhecida. |
| `index_missing` | Índice SQLite local ausente. |
| `dependency_missing` | Extra opcional, como yfinance, não instalado. |
| `local_file_access_disabled` | Endpoint de caminho local bloqueado por configuração. |
| `local_file_outside_allowed_root` | Caminho local fora de `DADOSBR_LOCAL_DATA_DIR`. |
| `admin_http_disabled` | Rota admin HTTP bloqueada por padrão. |
| `admin_mcp_disabled` | Tool admin MCP bloqueada por padrão. |
| `admin_token_required` | Superfície admin habilitada sem `DADOSBR_ADMIN_TOKEN`. |
| `admin_token_invalid` | Header ou argumento admin ausente/incorreto. |
| `upload_too_large` | Upload excede `DADOSBR_MAX_UPLOAD_BYTES`. |

## Estágios de Dado

- `raw`: dado bruto ou quase bruto da fonte.
- `normalized`: campos convertidos para nomes, tipos e datas canônicas.
- `classified`: registro classificado por heurística.
- `derived`: calculado a partir de uma ou mais fontes.
- `deflated`: série ajustada por deflator.
- `adjusted`: série enriquecida com preço ajustado.
- `enriched`: dado complementado por fonte opcional.

## Flags de Qualidade

Flags observadas nos módulos atuais:

- `missing_value`
- `missing_close`
- `missing_adjusted_close`
- `missing_observed_at`
- `missing_tenor`
- `missing_annual_rate`
- `missing_settlement_price`
- `missing_strike_price`
- `unknown_contract_family`
- `unknown_option_type`
- `revision_possible`
- `approximate_business_days`
- `offered_rate_curve`

Novos módulos devem documentar flags próprias no guia de domínio correspondente e manter a lista em português quando a flag afetar decisão de usuário.

## Convenções

- Datas de dia usam ISO `YYYY-MM-DD`.
- Datetimes usam ISO 8601.
- Taxas em decimal usam `0.10` para 10%.
- Taxas percentuais usam campo com sufixo `_pct`, por exemplo `10.0`.
- Valores monetários preservam moeda quando a fonte permite.
- Campos derivados devem carregar `data_stage=derived` ou estágio mais específico.
- Enriquecimentos não oficiais devem aparecer em `limitations`, `source_id`, `provider` ou `quality_flags`.

## Cache e Freshness

O cache HTTP em disco usa:

- `DADOSBR_CACHE_DIR`, padrão `.dadosbr/cache`.
- `DADOSBR_CACHE_TTL_SECONDS`, padrão `3600`.
- `DADOSBR_HTTP_CACHE_MAX_INLINE_BYTES`, limite para corpo salvo inline no JSON.
- `DADOSBR_HTTP_CACHE_MAX_BODY_BYTES`, limite máximo para persistir corpo no cache.
- `DADOSBR_DISABLE_HTTP_CACHE=1` para bypass.

O cabeçalho interno `x-dadosbr-cache` é registrado como `hit`, `miss`, `stale`, `skip` ou `disabled` pelos conectores que usam `http_get_bytes_cached`. Corpos acima do limite inline usam sidecar `.body`; corpos acima do limite máximo não são cacheados e retornam `x-dadosbr-cache-skip-reason=body_too_large`.

`freshness` é calculado a partir de `observed_at` e `collected_at`; consultas sem registros ou sem data observável podem retornar `no_data` ou `unknown` conforme o caso.

## Reprodutibilidade

Use fixtures locais quando precisar repetir uma análise:

- `DADOSBR_B3_COTAHIST_FILE`
- `DADOSBR_TESOURO_PACKAGE_FILE`
- `DADOSBR_TESOURO_RATES_CSV_FILE`
- `DADOSBR_COMEX_DATA_DIR`
- `--dataset-dir` e `--db-path` no `dadosbr-admin cnpj sync`

Registre também a versão do pacote, parâmetros da consulta e `raw_sha256` retornado.

## Validação Recomendada

Antes de publicar mudanças de contrato:

```powershell
python -m ruff check src tests scripts
python -m pytest -q
python scripts/export_openapi.py --check
```

Testes live são opt-in e usam o marcador `live`; eles só devem rodar quando `DADOSBR_RUN_LIVE_TESTS=1` estiver configurado.
