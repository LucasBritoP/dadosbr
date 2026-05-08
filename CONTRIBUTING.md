# Contribuindo

Obrigado por considerar contribuir com o DadosBR. O projeto está em alpha e prioriza qualidade de contrato, rastreabilidade de fonte e respeito aos termos de dados.

## Ambiente Local

```powershell
python -m pip install -e ".[dev]"
python -m pip install -e ".[dev,enriched]"  # opcional, para yfinance
```

Validação mínima:

```powershell
python -m ruff check src tests scripts
python -m pytest -q
python -m compileall -q src
python scripts/export_openapi.py --check
```

## Princípios Técnicos

- Conectores de fonte primária ficam em `src/dadosbr/connectors`.
- Camadas derivadas ficam fora dos conectores e devem preservar `source_refs` ou metadados equivalentes quando possível.
- Respostas públicas devem usar `make_success` e `make_failure`.
- Preserve `source_id`, `source_url`, `license_name`, `raw_sha256`, `limitations`, `quality_flags` e campos de estágio quando aplicável.
- Não commite caches, ZIPs, bases oficiais grandes, SQLite gerado, tokens, cookies ou `.env`.
- Mudanças em API, MCP, schema ou fonte exigem atualização de documentação.

## Adicionando Uma Fonte

Inclua na proposta:

- URL oficial ou origem autorizada.
- Licença, termos de uso e restrições de redistribuição.
- Frequência de atualização e disponibilidade histórica.
- Campos principais e identificadores.
- Exemplo pequeno ou fixture sintética.
- Estratégia de cache, streaming ou índice local para arquivos grandes.
- Riscos conhecidos: SSL, layout instável, autenticação, rate limit ou termos de Market Data.

## Testes

Use fixtures pequenas e determinísticas para a suíte padrão. Testes que chamam fontes reais devem ser marcados como `live` e depender de `DADOSBR_RUN_LIVE_TESTS=1`.

Boas práticas:

- Escreva teste para bug antes da correção.
- Prefira fixtures sintéticas a dados baixados reais.
- Para parsers, cubra encoding, campos vazios, limites de tamanho e aliases de layout.
- Para endpoints, teste comportamento de segurança: admin desligado, caminhos locais bloqueados e validação de upload.

## Pull Requests

Antes de abrir PR:

```powershell
python -m ruff check src tests scripts
python -m pytest -q
python -m compileall -q src
python scripts/export_openapi.py --check
python -m build
```

Inclua no PR:

- Resumo do problema e da solução.
- Fontes afetadas.
- Endpoints HTTP e tools MCP afetadas.
- Testes executados.
- Limitações ou riscos residuais.

## Compliance

Não contorne termos de fonte. Em especial:

- B3 COTAHIST continua opt-in via `DADOSBR_ALLOW_B3_DOWNLOAD=1`.
- ANBIMA Feed não deve ter credenciais, tokens ou dados restritos commitados.
- `yfinance` é enriquecimento opcional e não substitui fonte oficial.
- Bases públicas grandes devem ser baixadas pelo usuário no ambiente local.
