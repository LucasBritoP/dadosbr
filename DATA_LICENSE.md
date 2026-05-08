# Política de Dados, Licenças e Atribuição

O código do DadosBR é distribuído sob a licença MIT. Essa licença cobre o software deste repositório, não os dados obtidos das fontes externas.

Cada usuário é responsável por cumprir os termos de uso, licença, limites de acesso e regras de redistribuição da fonte consultada.

## Como o DadosBR Ajuda na Auditoria

As respostas do projeto buscam preservar metadados de rastreabilidade:

- `source_id`
- `source_url`
- `license_name`
- `collected_at`
- `observed_at`
- `raw_sha256`
- `limitations`
- `quality_flags`

Esses campos ajudam a auditar origem e transformação, mas não transferem direitos de redistribuição.

## Fontes e Observações

| Fonte | Uso no DadosBR | Observações |
| --- | --- | --- |
| Banco Central do Brasil | SGS, PTAX, Focus | Dados públicos do BCB. Cite a fonte em redistribuições. |
| CVM Dados Abertos | Companhias, fundos, FIIs, documentos IPE/DFP/ITR/FRE/FCA | Ver termos do portal de dados CVM. Arquivos podem ser grandes. |
| B3 COTAHIST | Histórico D-1 e parse local | Respeite termos de Market Data B3. Download automático é opt-in. |
| Tesouro Transparente | Taxas e preços do Tesouro Direto | Dados públicos do Tesouro. |
| IBGE SIDRA | Séries socioeconômicas | Dados públicos do IBGE. |
| IPEADATA | Séries econômicas, regionais e sociais | Uso público com citação da fonte. |
| Receita Federal CNPJ | Base pública CNPJ e tabelas auxiliares | Volumes grandes; consultas dependem de índice local. |
| MDIC Comex Stat | Comércio exterior por NCM, município e tabelas auxiliares | Bases CSV grandes; use filtros e streaming. |
| BNDES Dados Abertos | Operações, debêntures, fundos e renda variável | Ver licença específica de cada dataset CKAN. |
| ANBIMA Feed | Normalização de curvas fornecidas pelo usuário | O DadosBR não embute credenciais nem redistribui dados restritos. |
| yfinance | Enriquecimento opcional de séries, ajustes, dividendos e índices | Não é fonte oficial B3/CVM. Use conforme termos do provedor. |

## Regras Para o Repositório

- Não commitar bases oficiais, ZIPs, SQLite gerado, caches ou dados baixados.
- Não commitar credenciais, tokens, cookies, headers privados ou arquivos `.env`.
- Fixtures de teste devem ser pequenas, sintéticas e suficientes para validar parser/contrato.
- Ao adicionar fonte, documente URL, licença/termos, frequência, campos, limitações e riscos.
- Ao adicionar camada derivada, indique se o dado é bruto, normalizado, derivado ou enriquecido.

## B3 e Market Data

O DadosBR mantém `DADOSBR_ALLOW_B3_DOWNLOAD=0` por padrão. O usuário só deve habilitar `DADOSBR_ALLOW_B3_DOWNLOAD=1` depois de aceitar e respeitar os termos aplicáveis da B3.

Para testes e pipelines internos, prefira `DADOSBR_B3_COTAHIST_FILE` apontando para arquivo COTAHIST local obtido de forma autorizada.

## Aviso

DadosBR não fornece recomendação de investimento, consultoria financeira, garantia de completude ou garantia de atualização dos dados. Valide dados, licenças e cálculos antes de uso profissional.
