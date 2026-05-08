# DadosBR

DadosBR é uma API HTTP e um servidor MCP para consultar, normalizar e servir dados gratuitos do mercado brasileiro.

O projeto está em versão alpha (`0.1.0a0`). A proposta é ser local-first, rastreável e útil para agentes, notebooks, pipelines e aplicações internas que precisam combinar fontes públicas brasileiras sem depender de APIs terceirizadas fechadas.

## O Que Tem Hoje

- API HTTP FastAPI com contrato OpenAPI e 71 paths.
- Servidor MCP com 73 ferramentas para agentes.
- Conectores para BCB, CVM, B3 COTAHIST, Tesouro Transparente, IBGE SIDRA, IPEADATA, Receita Federal CNPJ, MDIC Comex Stat e BNDES.
- Camadas derivadas para cadastro mestre de ativos, séries históricas, benchmarks, renda fixa, fundamentalistas, proventos, derivativos e curvas de juros.
- Cache local, fixtures de teste, respostas padronizadas e metadados de fonte em cada payload.

## Instalação

```powershell
python -m pip install -e ".[dev]"
```

Para enriquecimentos opcionais que usam `yfinance`:

```powershell
python -m pip install -e ".[dev,enriched]"
```

`yfinance` não é fonte oficial B3/CVM. Use apenas como enriquecimento validável.

## API HTTP

```powershell
dadosbr-api --host 127.0.0.1 --port 8000
```

Endpoints úteis para começar:

```powershell
curl "http://127.0.0.1:8000/health"
curl "http://127.0.0.1:8000/sources"
curl "http://127.0.0.1:8000/bcb/sgs/11?last=5"
curl "http://127.0.0.1:8000/cvm/funds/daily?limit=5"
curl "http://127.0.0.1:8000/benchmarks/selic/history?last=30"
```

OpenAPI local:

```text
http://127.0.0.1:8000/docs
http://127.0.0.1:8000/openapi.json
```

## MCP

```powershell
dadosbr-mcp
```

Exemplo genérico de configuração para clientes MCP que aceitam JSON:

```json
{
  "mcpServers": {
    "dadosbr": {
      "command": "python",
      "args": ["-m", "dadosbr.mcp.server"],
      "env": {
        "PYTHONPATH": "C:\\Users\\panze\\DadosBR\\src",
        "DADOSBR_CACHE_DIR": "C:\\Users\\panze\\DadosBR\\.dadosbr\\cache"
      }
    }
  }
}
```

Consulte [docs/mcp.md](docs/mcp.md) para grupos de ferramentas, paridade com a API e cuidados de segurança.

## Configuração

As variáveis principais estão em [.env.example](.env.example). O projeto não carrega `.env` automaticamente em todos os contextos; use o mecanismo do seu terminal, runner, IDE ou cliente MCP para injetar as variáveis.

Variáveis importantes:

| Variável | Uso |
| --- | --- |
| `DADOSBR_CACHE_DIR` | Diretório de cache HTTP e respostas parseadas. |
| `DADOSBR_CACHE_TTL_SECONDS` | TTL do cache HTTP fresco. Padrão: `3600`. |
| `DADOSBR_HTTP_CACHE_MAX_INLINE_BYTES` | Limite para corpo salvo inline no JSON do cache. |
| `DADOSBR_HTTP_CACHE_MAX_BODY_BYTES` | Limite máximo para persistir corpo no cache; acima disso o cache é ignorado. |
| `DADOSBR_MAX_STALE_SECONDS` | Idade máxima global para fallback stale. Padrão: `604800`. |
| `DADOSBR_STRICT_FRESH` | Quando `1`, falha em vez de devolver cache stale. |
| `DADOSBR_HTTP_RETRIES` | Tentativas HTTP para erros retryable. Padrão: `2`. |
| `DADOSBR_DATASET_DIR` | Diretório para datasets baixados e índices locais. |
| `DADOSBR_ALLOW_B3_DOWNLOAD` | Libera download automático do COTAHIST após aceite dos termos B3. Padrão: `0`. |
| `DADOSBR_B3_COTAHIST_FILE` | Usa um arquivo COTAHIST local em vez de baixar da B3. |
| `DADOSBR_ENABLE_LOCAL_FILE_ENDPOINTS` | Habilita API HTTP e tools MCP que recebem caminhos locais. Padrão: `0`. |
| `DADOSBR_LOCAL_DATA_DIR` | Raiz permitida para leitura de arquivos locais. |
| `DADOSBR_ENABLE_ADMIN_HTTP` | Habilita endpoints administrativos HTTP. Padrão: `0`. |
| `DADOSBR_ENABLE_ADMIN_MCP` | Habilita tools administrativas MCP. Padrão: `0`. |
| `DADOSBR_ADMIN_TOKEN` | Token obrigatório para admin HTTP ou MCP quando a superfície admin está habilitada. |
| `DADOSBR_CVM_COMPANY_REPORT_TIMEOUT_SECONDS` | Timeout para ZIPs anuais de companhias CVM. |
| `DADOSBR_YFINANCE_TIMEOUT_SECONDS` | Timeout das chamadas yfinance. Padrão: `30`. |
| `DADOSBR_YFINANCE_HISTORY_PERIOD` | Janela padrão yfinance quando não há datas. Padrão: `5y`. |
| `DADOSBR_RECEITA_CNPJ_FALLBACK_BASE_URLS` | Mirrors opcionais para a base pública CNPJ quando a origem oficial falhar. |
| `DADOSBR_COMEX_VERIFY_SSL` | Validação SSL do MDIC Comex. Use `0` apenas como fallback local temporário. |

## Fontes e Limites

DadosBR busca fontes gratuitas, oficiais ou claramente autorizadas. O software está sob licença MIT, mas os dados consultados continuam sujeitos aos termos de cada fonte.

Pontos de atenção:

- B3 COTAHIST exige respeito aos termos de Market Data; download automático é opt-in.
- Bases CNPJ, Comex e CVM podem ser grandes; use cache, filtros e índices locais.
- Em Windows com cadeia SSL incompleta, `certifi` é usado por padrão; `DADOSBR_COMEX_VERIFY_SSL=0` existe apenas para teste local controlado.
- ANBIMA Feed é normalizado apenas a partir de registros fornecidos pelo usuário com autorização própria.
- Indicadores derivados e ajustes via `yfinance` são enriquecimentos, não fonte oficial.
- O projeto não fornece recomendação de investimento.

Leia [DATA_LICENSE.md](DATA_LICENSE.md) e [docs/sources.md](docs/sources.md) antes de redistribuir dados.

## Documentação

- [docs/overview.md](docs/overview.md) - visão geral, arquitetura e limites da alpha.
- [docs/capabilities.md](docs/capabilities.md) - mapa de capacidades da API HTTP e do servidor MCP.
- [docs/configuration.md](docs/configuration.md) - variáveis de ambiente, cache, CNPJ, B3 e execução local.
- [docs/api-http.md](docs/api-http.md) - contrato HTTP, grupos de endpoints, paths e rotas sensíveis.
- [docs/sources.md](docs/sources.md) - fontes, licenças, restrições e rastreabilidade.
- [docs/mcp.md](docs/mcp.md) - servidor MCP e ferramentas para agentes.
- [docs/timeseries.md](docs/timeseries.md) - cotações, séries econômicas e armazenamento local.
- [docs/asset-master.md](docs/asset-master.md) - cadastro mestre de emissores, instrumentos e taxonomias.
- [docs/benchmarks.md](docs/benchmarks.md) - benchmarks, deflatores, calendário macro e comparação.
- [docs/fixed-income.md](docs/fixed-income.md) - Tesouro, debêntures, exposição de fundos e analytics.
- [docs/fundamentals.md](docs/fundamentals.md) - demonstrativos CVM, fatos, ratios e dividendos.
- [docs/corporate-actions.md](docs/corporate-actions.md) - proventos, eventos e histórico ajustado.
- [docs/derivatives-curves.md](docs/derivatives-curves.md) - derivativos, DI1, ANBIMA e curvas.
- [docs/data-quality.md](docs/data-quality.md) - estágios, flags, cache, qualidade e auditoria.
- [docs/deployment-hardening.md](docs/deployment-hardening.md) - cuidados para expor a API.
- [docs/alpha-roadmap.md](docs/alpha-roadmap.md) - prioridades da alpha.

## Receita Federal CNPJ

Consultas CNPJ dependem de índice SQLite local. Rode:

```powershell
dadosbr-admin cnpj status
dadosbr-admin cnpj sync --period latest --groups empresas,estabelecimentos,socios,simples,domains
```

Depois:

```powershell
curl "http://127.0.0.1:8000/cnpj/status"
curl "http://127.0.0.1:8000/cnpj/search?q=PETROBRAS&limit=5"
```

`POST /admin/cnpj/sync` fica desabilitado por padrão na API HTTP. Para uso local confiável:

```powershell
$env:DADOSBR_ENABLE_ADMIN_HTTP="1"
$env:DADOSBR_ADMIN_TOKEN="troque-este-token"
curl -X POST "http://127.0.0.1:8000/admin/cnpj/sync" -H "X-DadosBR-Admin-Token: troque-este-token"
```

No MCP, `admin_sync_cnpj` também fica desabilitada por padrão. Para teste local, use `DADOSBR_ENABLE_ADMIN_MCP=1` e informe `admin_token` na chamada da tool.

## Desenvolvimento

```powershell
python -m ruff check src tests scripts
python -m pytest -q
python -m compileall -q src
python scripts/export_openapi.py --check
python scripts/test_mcp_tools.py
```

Build local:

```powershell
python -m build
```

## Segurança

Por padrão, os recursos mais sensíveis ficam desligados:

- endpoints HTTP administrativos;
- tools MCP administrativas;
- leitura de caminhos locais;
- download automático B3;
- uploads grandes.

Não exponha uma instância pública com `DADOSBR_ENABLE_LOCAL_FILE_ENDPOINTS=1`, `DADOSBR_ENABLE_ADMIN_HTTP=1` ou `DADOSBR_ENABLE_ADMIN_MCP=1` sem isolamento, autenticação, rate limit e revisão de [SECURITY.md](SECURITY.md).

## Status

Este repositório ainda está em alpha. A prioridade é manter o contrato estável, documentar limitações e preservar rastreabilidade de fonte antes de expandir para dados com termos mais restritivos.
