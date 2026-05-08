# Visão Geral

DadosBR é uma API HTTP e um servidor MCP para consumir, normalizar e auditar dados gratuitos do mercado brasileiro em fluxos locais, agentes e integrações de pesquisa.

O projeto está em alpha (`0.1.0a0`) e é local-first: ele prioriza uso em máquina confiável, cache local, arquivos autorizados pelo operador e rastreabilidade de fonte. Ele não é uma redistribuição hospedada de market data B3, ANBIMA ou de agregadores de terceiros.

## Superfície Atual

Validação feita a partir de `src/dadosbr/api/app.py`, `src/dadosbr/mcp/server.py` e `scripts/export_openapi.py`:

| Interface | Estado verificado | Observação |
| --- | ---: | --- |
| API HTTP | 71 paths OpenAPI | Inclui saúde, fontes, conectores, camadas derivadas e admin CNPJ. |
| MCP | 73 tools | Mantém paridade funcional com as rotas de dados e adiciona conveniências MCP. |
| CLI admin | `dadosbr-admin` | Hoje cobre status e sync do índice local de CNPJ. |
| Pacote Python | `dadosbr-api`, `dadosbr-mcp`, `dadosbr-admin` | Entry points declarados em `pyproject.toml`. |

## Como Ler a Documentação

- [configuration.md](configuration.md): variáveis de ambiente, dependências opcionais, cache e diretórios locais.
- [sources.md](sources.md): fontes oficiais, camadas derivadas, licenças e restrições de uso.
- [api-http.md](api-http.md): grupos de endpoints, contrato de resposta e cuidados de uso HTTP.
- [mcp.md](mcp.md): execução do servidor MCP e lista de tools por domínio.
- [data-quality.md](data-quality.md): resposta padronizada, freshness, erros, flags e auditoria.
- [deployment-hardening.md](deployment-hardening.md): recomendações para expor a API fora de uma máquina confiável.
- Guias de domínio: [timeseries.md](timeseries.md), [asset-master.md](asset-master.md), [benchmarks.md](benchmarks.md), [fixed-income.md](fixed-income.md), [fundamentals.md](fundamentals.md), [corporate-actions.md](corporate-actions.md) e [derivatives-curves.md](derivatives-curves.md).

## Arquitetura em Camadas

```text
Clientes HTTP / agentes MCP / CLI
        |
        v
FastAPI app, FastMCP server e comandos admin
        |
        v
Camadas derivadas: cadastro mestre, séries, benchmarks, renda fixa,
fundamentalistas, eventos corporativos, derivativos e curvas
        |
        v
Conectores: BCB, CVM, B3 COTAHIST, Tesouro, IBGE, IPEA,
Receita CNPJ, MDIC Comex Stat e BNDES
        |
        v
Cache local, arquivos autorizados e índice SQLite local
```

Os conectores retornam dados próximos da fonte, enquanto as camadas derivadas criam identificadores canônicos, séries comparáveis, métricas e normalizações para uso por aplicações e agentes.

## Princípios de Produto

- Preferir fontes oficiais quando elas estão disponíveis e têm termos compatíveis.
- Marcar enriquecimentos opcionais, como yfinance, como não oficiais.
- Evitar download automático de fonte restrita ou sensível sem opt-in explícito.
- Preservar `source_id`, `source_url`, `license_name`, `raw_sha256`, `limitations` e `quality_flags`.
- Manter segurança local por padrão: caminhos de arquivo e rotas admin HTTP ficam bloqueados até configuração explícita.

## Limites da Alpha

- Não há dados B3 intraday, livro de ofertas, tempo real, margem ou posição por participante.
- O download oficial de B3 COTAHIST só roda com `DADOSBR_ALLOW_B3_DOWNLOAD=1` ou com arquivo local informado.
- yfinance é dependência opcional e não é fonte oficial B3/CVM.
- Receita CNPJ depende de download e índice SQLite local antes das consultas.
- Curvas ANBIMA são normalizadas a partir de dados fornecidos pelo operador; o projeto não embute credenciais ANBIMA.
- API pública hospedada exige hardening adicional descrito em [deployment-hardening.md](deployment-hardening.md).
