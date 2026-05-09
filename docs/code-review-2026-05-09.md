# Revisão rápida da base (2026-05-09)

## 1) Tarefa de correção de erro de digitação
- **Problema encontrado:** o texto de capacidades públicas usa palavras sem acentuação em português (ex.: `visao`, `tambem`, `rapido`, `aplicacoes`, `publicos`), o que reduz a qualidade editorial da documentação.
- **Evidência:** `docs/capabilities.md` linha 3 e linha 7.
- **Tarefa sugerida:** padronizar ortografia/acentuação em toda a página (e, opcionalmente, em toda a pasta `docs/`) com uma revisão editorial leve.

## 2) Tarefa de correção de bug
- **Problema encontrado:** a lógica de cache stale trata `DADOSBR_MAX_STALE_SECONDS <= 0` como **permitir stale sempre** (`return True`), o que é contraintuitivo para configuração operacional (em muitos sistemas, `0` significa “não permitir” ou “expiração imediata”).
- **Evidência:** em `_stale_age_allowed`, quando `limit <= 0`, retorna `True`.
- **Tarefa sugerida:** ajustar semântica para que `0` desabilite stale por idade (ou documentar explicitamente que `0` significa ilimitado e adicionar flag separada para desabilitar). Atualizar testes para refletir o comportamento escolhido.

## 3) Tarefa de ajuste de comentário/documentação
- **Problema encontrado:** o `DEFAULT_USER_AGENT` aponta para `https://github.com/` sem o repositório do projeto, prejudicando rastreabilidade e suporte quando provedores de dados inspecionam tráfego.
- **Evidência:** constante `DEFAULT_USER_AGENT` em `src/dadosbr/core/http.py`.
- **Tarefa sugerida:** corrigir para URL real do projeto e refletir isso na documentação de operação/rede (ex.: seção de comportamento HTTP e identificação de cliente).

## 4) Tarefa de melhoria de teste
- **Problema encontrado:** cobertura de integração live do BCB valida apenas cenário feliz mínimo (`series_id=11`, `last=1`) e não verifica metadados de resiliência/cache nem cenários de falha transitória.
- **Evidência:** `tests/integration/test_live_bcb.py` contém um único teste curto.
- **Tarefa sugerida:** adicionar testes live opcionais para:
  1. validar presença/estrutura de `source_mode`, `resilience` e `limitations`;
  2. validar comportamento com parâmetro inválido (erro bem formatado);
  3. validar fallback de stale em ambiente controlado (com mock/fake do fetcher em teste unitário complementar).
