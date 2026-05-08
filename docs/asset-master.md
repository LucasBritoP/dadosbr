# Cadastro Mestre de Ativos

O cadastro mestre cria identificadores e registros canônicos para emissores, instrumentos, fundos, títulos públicos e taxonomias. Ele é uma camada derivada: não substitui as bases originais e deve preservar referências de fonte em `source_refs`.

## Fontes Usadas

- Receita Federal CNPJ: emissores e CNAE, via índice SQLite local.
- B3 COTAHIST: instrumentos listados, quando há arquivo local ou download opt-in autorizado.
- CVM Dados Abertos: fundos, quando registros são fornecidos ao snapshot.
- Tesouro Transparente: títulos públicos.
- MDIC Comex Stat: NCM.

## Identificadores Canônicos

| Tipo | Formato |
| --- | --- |
| Emissor | `BR_CNPJ:{cnpj}` |
| Instrumento B3 | `B3:{ticker}` |
| Fundo CVM | `CVM_FUND:{cnpj}` |
| Título público | `TESOURO:{tipo}:{vencimento}` |

## Endpoints HTTP

```text
GET /assets/search
GET /assets/{asset_id}
GET /issuers/{cnpj}
GET /instruments/{ticker}
GET /taxonomies/cnae/{code}
GET /taxonomies/ncm/{code}
```

Parâmetros importantes:

- `q`: termo de busca em `/assets/search`.
- `type`: filtro `all`, `issuer` ou `instrument`.
- `issuer_cnpj`: filtro por emissor em `/assets/search`.
- `db_path`: índice SQLite CNPJ alternativo.
- `b3_file_path`: arquivo COTAHIST local.

`db_path` e `b3_file_path` são validados por política de caminho local na API HTTP. Veja [deployment-hardening.md](deployment-hardening.md).

## Tools MCP

```text
get_asset_master
search_asset_master
get_issuer_master
get_instrument_master
get_cnae_taxonomy
get_ncm_taxonomy
```

## Campos Normalizados

Emissores:

- `asset_id`, `issuer_id`, `asset_type`, `issuer_type`
- `cnpj`, `legal_name`, `trading_name`, `uf`
- `registration_status`, `main_cnae`, `source_refs`

Instrumentos B3:

- `asset_id`, `instrument_id`, `asset_type`
- `ticker`, `exchange`, `isin`, `market_type`
- `short_name`, `specification`, `currency`
- `last_observed_at`, `last_close_price`, `source_refs`

Taxonomias:

- CNAE: `code`, `description`
- NCM: `code`, `description`

## Fluxo de Uso

1. Construa o índice CNPJ local se precisar de emissores ou CNAE.
2. Informe um COTAHIST local autorizado se precisar de instrumentos B3 offline.
3. Use `/assets/search` para descoberta e `/assets/{asset_id}` para buscar um registro canônico.

## Limitações

- A relação automática ticker B3 -> CNPJ do emissor ainda depende de fonte oficial adicional.
- O cadastro mestre não calcula histórico ajustado por eventos corporativos.
- CNAE e NCM são taxonomias de apoio; não indicam exposição econômica direta sem regra de negócio adicional.
- Dados de CNPJ dependem da atualização e cobertura do índice SQLite local.
