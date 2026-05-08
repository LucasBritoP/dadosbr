# Fontes, Licenças e Camadas

O DadosBR separa fonte primária, normalização derivada e enriquecimento opcional. Cada resposta deve preservar `source_id`, `source_url`, `license_name` e `limitations` para deixar claro de onde o dado veio e quais termos se aplicam.

## Fontes Registradas

Os metadados abaixo vêm de `src/dadosbr/core/registry.py`.

| `source_id` | Fonte | Base | Licença/termos | Frequência |
| --- | --- | --- | --- | --- |
| `bcb_sgs` | Banco Central SGS | `https://api.bcb.gov.br/dados/serie/` | Dados Abertos BCB | diária |
| `bcb_ptax` | Banco Central PTAX | `https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/odata/` | Dados Abertos BCB | diária |
| `bcb_focus` | Banco Central Focus | `https://olinda.bcb.gov.br/olinda/servico/Expectativas/versao/v1/odata/` | Dados Abertos BCB | semanal |
| `cvm_dados_abertos` | CVM Dados Abertos | `https://dados.cvm.gov.br/` | ODbL | diária |
| `b3_cotahist` | B3 COTAHIST Histórico | `https://bvmf.bmfbovespa.com.br/InstDados/SerHist/` | Termos B3 Market Data | diária |
| `b3_derivatives` | B3 Derivativos Históricos | `https://www.b3.com.br/pt_br/market-data-e-indices/servicos-de-dados/market-data/historico/` | Termos B3 Market Data | diária |
| `anbima_curves` | ANBIMA Feed - Curvas | `https://api.anbima.com.br/feed/precos-indices/v1/titulos-publicos/curvas-juros` | Termos ANBIMA Feed | diária |
| `tesouro_transparente` | Tesouro Transparente | `https://www.tesourotransparente.gov.br/ckan/` | ODbL | diária |
| `ibge_sidra` | IBGE SIDRA | `https://apisidra.ibge.gov.br/values/` | Dados Abertos IBGE | mensal |
| `ipeadata` | IPEADATA | `http://www.ipeadata.gov.br/api/odata4/` | Uso público com citação | diária |
| `receita_cnpj` | Receita Federal CNPJ | `https://arquivos.receitafederal.gov.br/dados/cnpj/dados_abertos_cnpj/` | Dados Abertos Receita Federal | mensal |
| `mdic_comex_stat` | MDIC Comex Stat | `https://balanca.economia.gov.br/balanca/bd/comexstat-bd/` | Dados Abertos MDIC | mensal |
| `bndes_dados_abertos` | BNDES Dados Abertos | `https://dadosabertos.bndes.gov.br/api/3/action/` | ODbL | mensal |

## Camadas Derivadas

| `source_id` | Camada | Origem principal | Observação |
| --- | --- | --- | --- |
| `asset_master` | Cadastro mestre | B3, CVM, Receita, Tesouro, MDIC e BNDES | Cria identificadores canônicos e `source_refs`. |
| `timeseries` | Séries históricas | B3 COTAHIST, BCB, IPEA, IBGE e yfinance opcional | `adjusted_close` via yfinance não é ajuste oficial B3. |
| `benchmarks` | Benchmarks e macro | BCB SGS, Tesouro, séries canônicas e yfinance opcional | IBOV/IFIX por yfinance não são redistribuição oficial B3. |
| `fixed_income` | Renda fixa | Tesouro, BNDES, CVM e benchmarks | Crédito privado público não inclui mercado secundário completo. |
| `fundamentals` | Fundamentalistas | CVM, COTAHIST local e yfinance opcional | Mapeamento de contas é heurístico. |
| `corporate_actions` | Proventos e eventos | yfinance opcional, registros externos/manuais e COTAHIST | Fonte oficial B3/CVM estruturada ainda não está automatizada. |
| `derivatives` | Derivativos | B3 Derivativos e arquivos/exports locais autorizados | Sem tempo real, intraday, margem ou posição por participante. |
| `interest_curves` | Curvas de juros | Tesouro, DI1/B3 e registros ANBIMA fornecidos | O projeto não embute credenciais ANBIMA. |

## B3 COTAHIST

O conector `b3_cotahist` usa esta ordem:

1. `DADOSBR_B3_COTAHIST_FILE`, quando definido.
2. Download oficial da B3 somente quando `DADOSBR_ALLOW_B3_DOWNLOAD=1`.
3. Caso contrário, retorna `ok=false` com erro `source_unavailable`.

Essa trava é intencional. O operador precisa revisar os termos aplicáveis antes de baixar, hospedar ou redistribuir dados B3.

## Receita CNPJ

O conector descobre o período mais recente no índice público da Receita, baixa grupos selecionados e constrói um SQLite local. A base primária é `DADOSBR_RECEITA_CNPJ_BASE_URL`; bases alternativas podem ser configuradas em `DADOSBR_RECEITA_CNPJ_FALLBACK_BASE_URLS`.

Consultas como `/cnpj/search`, `/cnpj/{cnpj}` e `/cnpj/{cnpj}/socios` dependem desse índice. Sem o banco, o retorno é `ok=false` com erro `index_missing`.

## yfinance

yfinance aparece somente como enriquecimento opcional:

- `adjusted_close` em séries de ativos.
- Dividendos/JCP em fundamentalistas.
- Proventos/eventos corporativos automáticos.
- IBOV/IFIX em benchmarks.

Ele exige o extra `enriched` e não é fonte oficial B3/CVM. Resultados devem ser tratados como conveniência validável, não como base oficial regulatória.

## ANBIMA e Curvas

O código normaliza registros ANBIMA já fornecidos pelo operador. Ele não faz autenticação, não baixa o feed com credenciais e não redistribui a fonte. Use apenas dados para os quais você possui autorização compatível.

## Redistribuição

A licença MIT do código não altera termos das fontes. Antes de publicar, revender, redistribuir ou hospedar dados obtidos por DadosBR, revise:

- Licença do código no `LICENSE`.
- Política de dados do projeto em `DATA_LICENSE.md`.
- Termos específicos de B3, ANBIMA, yfinance e demais fontes externas.
