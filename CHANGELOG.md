# Changelog

Todas as mudanças relevantes do DadosBR serão documentadas aqui.

O formato segue a ideia de Keep a Changelog. O projeto usa SemVer enquanto possível, com versões alpha enquanto o contrato ainda está amadurecendo.

## [Unreleased]

### Changed

- Documentação pública reorganizada em português-BR para preparar a publicação alpha no GitHub.
- README reduzido para porta de entrada do projeto, com links para docs detalhados.
- Política de dados, contribuição e segurança reescritas com foco em compliance de fontes públicas brasileiras.

## [0.1.0a0] - 2026-05-06

### Added

- API HTTP FastAPI para dados gratuitos do mercado brasileiro.
- Servidor MCP para agentes, com paridade funcional com os endpoints de dados da API.
- Conectores BCB, CVM, B3 COTAHIST, Tesouro Transparente, IBGE SIDRA, IPEADATA, Receita CNPJ, MDIC Comex Stat e BNDES.
- Camadas derivadas para cadastro mestre, séries históricas, benchmarks, renda fixa, fundamentalistas, proventos e eventos corporativos, derivativos e curvas de juros.
- Índice SQLite local para Receita Federal CNPJ.
- Cache HTTP e cache de respostas parseadas.
- Segurança local-first para endpoints administrativos, caminhos locais e upload.
- Testes offline com fixtures sintéticas.
- CI com Ruff, Pytest, compileall, OpenAPI smoke e build de pacote.

### Security

- Download automático B3 desabilitado por padrão.
- Endpoints admin HTTP desabilitados por padrão.
- Endpoints com caminhos locais desabilitados por padrão.
