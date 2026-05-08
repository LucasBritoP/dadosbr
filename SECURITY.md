# Política de Segurança

## Versões Suportadas

| Versão | Suporte |
| --- | --- |
| `0.1.x` alpha | Melhor esforço |

## Reportando Vulnerabilidades

Use GitHub Security Advisory quando estiver habilitado no repositório. Se não estiver, entre em contato com os mantenedores antes de publicar detalhes.

Inclua:

- versão afetada;
- endpoint, comando, tool MCP ou módulo afetado;
- passos mínimos para reproduzir;
- impacto esperado;
- logs ou respostas relevantes, sem credenciais;
- sistema operacional e versão do Python quando for problema local.

## Modelo de Ameaça da Alpha

DadosBR é local-first. A configuração padrão assume uso local ou em rede confiável. Antes de expor API ou MCP a usuários externos, revise autenticação, proxy, limites de corpo, rate limit e permissões de arquivo.

Recursos sensíveis ficam desligados por padrão:

- `DADOSBR_ENABLE_ADMIN_HTTP=0`
- `DADOSBR_ENABLE_LOCAL_FILE_ENDPOINTS=0`
- `DADOSBR_ALLOW_B3_DOWNLOAD=0`

## API HTTP

Antes de publicar a API:

- mantenha `DADOSBR_ENABLE_LOCAL_FILE_ENDPOINTS=0`, salvo em ambiente isolado;
- mantenha `DADOSBR_ENABLE_ADMIN_HTTP=0`; se habilitar admin HTTP, configure `DADOSBR_ADMIN_TOKEN`;
- defina `DADOSBR_MAX_UPLOAD_BYTES` com limite compatível com seu proxy;
- use TLS no proxy;
- aplique rate limit;
- bloqueie acesso direto a diretórios de cache e datasets;
- revise [docs/deployment-hardening.md](docs/deployment-hardening.md).

## MCP

O servidor MCP roda com as permissões do processo local. Não conecte o servidor a agentes ou clientes não confiáveis quando:

- `DADOSBR_ENABLE_LOCAL_FILE_ENDPOINTS=1`;
- `DADOSBR_LOCAL_DATA_DIR` aponta para diretórios amplos;
- existem `.env`, tokens, chaves SSH ou bases restritas no workspace;
- ferramentas admin estão habilitadas.

Tools MCP que recebem caminhos locais seguem a mesma trava de arquivos locais da API HTTP: `DADOSBR_ENABLE_LOCAL_FILE_ENDPOINTS=1` e raiz limitada por `DADOSBR_LOCAL_DATA_DIR`.

## Dados e Segredos

Não commite nem reporte publicamente:

- tokens, cookies, headers privados ou credenciais;
- arquivos `.env`;
- credenciais ou payloads restritos ANBIMA/B3;
- bases baixadas grandes;
- SQLite local com dados gerados;
- caches HTTP.

## Arquivos Locais

Endpoints que aceitam caminhos locais validam se o arquivo está dentro de `DADOSBR_LOCAL_DATA_DIR`, mas isso não substitui isolamento operacional. Para testes permissivos, use um ambiente local descartável.

## Aviso Financeiro

Este projeto não presta consultoria financeira. Problemas de qualidade de dados, cálculo ou defasagem temporal devem ser tratados como risco operacional do usuário.
