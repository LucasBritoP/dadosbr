# Hardening Para Deploy

DadosBR é seguro por padrão para uso local-first, mas uma API HTTP exposta na internet precisa de controles adicionais do operador. Este documento cobre o que o código já bloqueia e o que deve existir fora da aplicação.

## Padrão Seguro

Valores recomendados para uma instância pública:

```text
DADOSBR_ENABLE_LOCAL_FILE_ENDPOINTS=0
DADOSBR_ENABLE_ADMIN_HTTP=0
DADOSBR_ENABLE_ADMIN_MCP=0
DADOSBR_ALLOW_B3_DOWNLOAD=0
DADOSBR_MAX_UPLOAD_BYTES=10485760
DADOSBR_HTTP_CACHE_MAX_BODY_BYTES=104857600
DADOSBR_STRICT_FRESH=0
DADOSBR_MAX_STALE_SECONDS=604800
```

Com isso:

- Endpoints que recebem `file_path`, `b3_file_path` ou `db_path` retornam HTTP 403.
- `/admin/cnpj/sync` retorna HTTP 403.
- `admin_sync_cnpj` no MCP retorna erro estruturado `admin_mcp_disabled`.
- Download automático de COTAHIST B3 fica bloqueado.
- Uploads ficam limitados a 10 MiB no processo Python.

Defina também limite de corpo no proxy ou gateway, porque `DADOSBR_MAX_UPLOAD_BYTES` só protege depois que a requisição chegou à aplicação.

## Uso Local Confiável

Para usar arquivos locais em uma máquina confiável:

```powershell
$env:DADOSBR_ENABLE_LOCAL_FILE_ENDPOINTS="1"
$env:DADOSBR_LOCAL_DATA_DIR="C:\dadosbr-data"
```

Somente caminhos resolvidos dentro de `DADOSBR_LOCAL_DATA_DIR` são aceitos.

Para admin HTTP local:

```powershell
$env:DADOSBR_ENABLE_ADMIN_HTTP="1"
$env:DADOSBR_ADMIN_TOKEN="troque-este-token"
```

Use:

```text
X-DadosBR-Admin-Token: troque-este-token
```

Se `DADOSBR_ADMIN_TOKEN` ficar vazio, o código bloqueia admin mesmo quando `DADOSBR_ENABLE_ADMIN_HTTP=1`.

Para admin MCP local, habilite `DADOSBR_ENABLE_ADMIN_MCP=1` e envie o mesmo token no argumento `admin_token` da tool. Mantenha essa flag desligada em ambientes compartilhados ou públicos.

## Superfícies Sensíveis

- `POST /admin/cnpj/sync`: baixa e indexa arquivos grandes da Receita Federal.
- `admin_sync_cnpj` no MCP: baixa e indexa arquivos grandes da Receita Federal no processo do agente.
- `GET /derivatives/futures`: aceita `file_path`.
- Rotas com `b3_file_path`: leem COTAHIST local.
- Rotas com `db_path`: leem ou gravam SQLite local.
- `POST /b3/cotahist/parse`: recebe arquivo enviado.
- `POST /derivatives/futures/parse`: recebe arquivo enviado.
- Tools MCP com payload textual grande: `parse_b3_cotahist_text` e `parse_derivatives_futures_text`.

## Resiliência

- `DADOSBR_HTTP_RETRIES` controla retentativas curtas para falhas retryable.
- `DADOSBR_MAX_STALE_SECONDS` limita por quanto tempo um cache expirado pode ser usado quando a fonte cai.
- `DADOSBR_STRICT_FRESH=1` ou `DADOSBR_DISABLE_STALE_CACHE=1` força falha em vez de fallback stale.
- `DADOSBR_HTTP_CACHE_MAX_BODY_BYTES` evita cachear respostas grandes demais; payloads intermediários usam sidecar `.body` com metadado JSON escrito atomicamente.
- Respostas retornam `source_mode` e `resilience`; monitore `stale_cache`, `local_snapshot` e `fallback_source` em produção.

## Checklist Para API Pública

- Rodar atrás de proxy com TLS.
- Definir autenticação/autorização no gateway ou serviço chamador.
- Aplicar rate limit por IP/chave.
- Definir limite de corpo no proxy e em `DADOSBR_MAX_UPLOAD_BYTES`.
- Manter rotas admin desabilitadas; rode syncs via CLI ou job interno.
- Manter tools MCP administrativas desabilitadas, salvo em agente local confiável com token.
- Manter leitura de arquivo local desabilitada para usuários externos.
- Separar diretório de dados, cache e código.
- Limitar disco do cache e diretórios de datasets.
- Registrar logs estruturados com status, latência, path e `source_id`.
- Monitorar erro, latência, uso de disco, memória e chamadas a fontes externas.
- Revisar termos de cada fonte antes de persistir, redistribuir ou expor resultados.

## CNPJ em Produção

Prefira rodar o sync fora do processo HTTP:

```powershell
dadosbr-admin cnpj sync --period latest --groups empresas,estabelecimentos,socios,simples,domains --dataset-dir C:\dadosbr-data\datasets
```

Depois a API pode consultar o SQLite já construído por caminho configurado dentro de uma raiz de dados permitida. Em uma API pública, exponha consultas de CNPJ sem aceitar `db_path` arbitrário de usuário.

## B3 e ANBIMA

- Não habilite `DADOSBR_ALLOW_B3_DOWNLOAD=1` em ambiente público sem revisar termos e finalidade.
- Não hospede arquivos COTAHIST ou derivados se seus direitos de redistribuição não estiverem claros.
- Curvas ANBIMA dependem de dados fornecidos pelo operador; o projeto não gerencia autenticação nem redistribuição ANBIMA.

## MCP

O servidor MCP roda com permissões locais do processo. Não exponha MCP para usuários externos sem isolamento, porque tools podem processar textos grandes e acessar caminhos que o operador informar. Tools MCP que recebem `file_path`, `b3_file_path` ou `db_path` seguem `DADOSBR_ENABLE_LOCAL_FILE_ENDPOINTS` e `DADOSBR_LOCAL_DATA_DIR`. Tools MCP administrativas exigem `DADOSBR_ENABLE_ADMIN_MCP=1`, `DADOSBR_ADMIN_TOKEN` não vazio e argumento `admin_token` válido.

## Rollback

O repositório não contém pipeline de deploy ou rollback de produção. Use o mecanismo da sua plataforma:

1. Mantenha versão/tag do pacote ou imagem.
2. Reimplante a versão anterior.
3. Restaure variáveis de ambiente e volumes de dados compatíveis.
4. Rode `/health` e uma consulta pequena de fonte antes de liberar tráfego.
