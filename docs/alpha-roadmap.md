# Roadmap Alpha

Este documento registra o estado público da alpha do DadosBR e os limites assumidos para evitar prometer dados, contratos ou automações que ainda não existem no código.

## Estado Entregue

- API HTTP com 71 paths verificados por OpenAPI.
- Servidor MCP com 73 tools verificadas em `src/dadosbr/mcp/server.py`.
- Registro de fontes consultável por HTTP e MCP.
- Resposta padronizada com `ok`, `source_id`, `source_url`, `license_name`, `collected_at`, `observed_at`, `raw_sha256`, `freshness`, `limitations`, `records` e `error`.
- Conectores para BCB SGS/PTAX/Focus, CVM, B3 COTAHIST, Tesouro Transparente, IBGE SIDRA, IPEADATA, Receita CNPJ, MDIC Comex Stat e BNDES.
- B3 COTAHIST com parser local, upload HTTP e download oficial somente por opt-in.
- Receita CNPJ com download por período, grupos selecionáveis, fallback de base URL e índice SQLite local.
- Camadas derivadas para cadastro mestre, séries históricas, benchmarks/macro, renda fixa, fundamentalistas, eventos corporativos, derivativos e curvas de juros.
- Hardening inicial para endpoints com caminho local, uploads e rotas admin HTTP.
- CLI admin para status e sync do índice CNPJ.
- CI com Ruff, pytest, compileall, smoke OpenAPI, smoke de entrypoints e build.

## Prioridades de Alpha

- Separar melhor a documentação pública por configuração, fontes, API/MCP, qualidade e deploy.
- Manter os avisos de licença e redistribuição próximos dos endpoints e camadas que usam cada fonte.
- Evoluir schemas públicos versionados para respostas mais críticas.
- Reduzir o tamanho de `src/dadosbr/api/app.py` e `src/dadosbr/mcp/server.py` com roteadores/grupos, sem quebrar contratos.
- Melhorar streaming e processamento incremental para fontes grandes, especialmente Receita CNPJ e uploads.
- Ampliar testes live opt-in por fonte oficial pequena.
- Formalizar limites de estabilidade: alpha pode quebrar contrato, beta deve exigir política de migração.

## Fora do Escopo Atual

- Dados B3 em tempo real, intraday, livro de ofertas ou posição por participante.
- Redistribuição hospedada de arquivos B3, ANBIMA ou dados sujeitos a termos específicos.
- Download automático de fontes restritas sem opt-in, credenciais e termos válidos do operador.
- Proventos/eventos corporativos oficiais B3/CVM automatizados de ponta a ponta.
- Ajustes históricos oficiais completos por evento corporativo em séries de preço.
- Relação completa e automática entre ticker B3 e CNPJ do emissor.
- Curvas ANBIMA autenticadas baixadas diretamente pelo projeto.
- Preço secundário, rating, garantias, covenants e fluxo oficial completo para crédito privado.
- Calendário macro com datas futuras oficiais dinâmicas e histórico de revisões por vintage.
- Autenticação/autorização própria para uma API pública multiusuário.

## Critérios Para Beta

- OpenAPI exportável e versionado como artefato de contrato.
- Modelos Pydantic públicos para os principais envelopes e registros.
- Política explícita de compatibilidade e breaking changes.
- Documentação de deploy com autenticação, rate limit e observabilidade definidos pelo operador.
- Testes de contrato e fixtures por domínio, cobrindo fontes oficiais e falhas esperadas.
- Caminho operacional claro para dados volumosos: download em chunks, índices locais e limpeza.
