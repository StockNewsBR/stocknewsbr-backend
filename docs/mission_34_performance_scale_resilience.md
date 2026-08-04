# Missão 34 — Performance, Escala e Resiliência

**Status:** `MISSION_SUSPENDED` (gates obrigatórios estruturalmente bloqueados neste ambiente; gates independentes concluídos com evidência; **PASS não declarado**)
**Branch:** `feat/github-workflow-ai-tools`
**BASE_COMMIT (M33 final):** `49ee466c55362a20a5605d084ce12518cbca8444`
**HEAD == origin:** `49ee466c` (working tree limpo no início)
**Ambiente:** Windows 11 + venv Python 3.11.9 (`venv/Scripts/python.exe`), Node v22.22.1. Repo: `C:\Users\dcima\stocknewsbr-backend`.

> Execução respeitou o bloqueio total de `git add`/`commit`/`push` e o modo read-only de Render/NVIDIA. Nenhuma regra financeira, fórmula, peso ou threshold foi tocado.

## Gate 0 — Estado do repositório: PASS
- Branch = `feat/github-workflow-ai-tools` ✓
- Working tree = CLEAN no início ✓
- HEAD local = HEAD remoto = `49ee466c` ✓
- M33 = PASS, commitada e pushada (`49ee466c feat(33): android go live hardening`) ✓
- BASE_COMMIT = commit final da M33 ✓

## Metodologia e ruído
- Benchmark backtest: seed fixa (34), warmup fora da medição, mediana de 3 execuções, sem rede, fail-fast por projeção quadrática (600 s). Digest SHA-256 do resultado completo para protocolo de equivalência.
- Suite backend: `python -m unittest discover tests`, 1 execução completa.

## Achado 34-01 — Backtest O(n²): CONFIRMADO (reproduzido)
Baseline (`runtime/mission_34/benchmarks/backtest_baseline.json`):

| barras | mediana | trades | events | digest |
|--------|---------|--------|--------|--------|
| 100    | 1.03 s  | 5      | 14     | 50cc24fa8d9d |
| 500    | 17.38 s | 21     | 62     | 73e480336436 |
| 1000   | 59.35 s | 44     | 108    | b13521db32e6 |

Crescimento: 2× barras → 3.4× tempo; 10× barras → 57× tempo ⇒ super-linear/quadrático confirmado.

**Causa-raiz** (`app/portfolio/backtest_engine.py:433-462`, `_collect_replay_events`): para cada prefixo `end_index ∈ [1..n]` chama `build_trend_breakout_payload(symbol, list(rows[:end_index]), ...)`. Cada chamada reconstrói o frame de indicadores pandas (EWM/rolling) sobre a fatia crescente ⇒ Σ O(k) = O(n²). Sub-item: `list(rows[:end_index])` faz cópia dupla redundante (`rows[:k]` já é cópia).

**Por que não é fix trivial de "chamar uma vez":** o engine deriva parâmetros **adaptativos** por tamanho de fatia — `_effective_indicator_settings(settings, len(frame))` e `_warmup_bars(len(df), ...)`. Logo `payload(rows[:k])` usa settings diferentes de `payload(rows[:n])` restrito aos primeiros k bars. Além disso `signal_counts` é acumulado por prefixo (cada evento é contado em todos os prefixos ≥ sua barra). Um colapso para O(n) exigiria um **engine incremental** com equivalência exata de digest, alto risco de regressão e mudança de semântica.

**Disposição:** fix asintótico exato = `PERFORMANCE_NOT_PROVEN` nesta passagem → follow-up controlado / `BUSINESS_DECISION_REQUIRED` (reescrita incremental do engine). Nenhuma otimização cega aplicada (conforme Seções 6, 10, 51). Como consequência, o **piloto DuckDB (15.1) permanece bloqueado** (dependência do fix do O(n²) não satisfeita).

## Auditoria estática de hot paths (Seções 11-34)
Agentes de auditoria paralela foram **bloqueados pelo limite de sessão** (reset 00:40 America/Sao_Paulo); auditoria refeita inline via grep/read com evidência.

- **34-02 N+1:** não confirmado nesta passagem (sem instrumentação de query executada). Requer profiling → parcial.
- **34-03 Event loop:** `app/engine/data/async_market_loader.py:18` envolve `yf.download` em `run_in_executor` ✓; `app/api/stripe_webhook.py:249` usa `run_in_threadpool` ✓. Ocorrências de `time.sleep` (`atomic_io`, `market_data_loader`, `scheduler`, `public_market_data_service`, `telegram_alert_engine`) estão em contexto **síncrono** (backoff/retry), não em `async def` direto. Sem bloqueio crítico de event loop confirmado.
- **34-04 Thread pools / concorrência:** múltiplos pools — `app/core/thread_pool.py:14` (singleton), `app/engine/parallel_signal_processor.py:66` e `app/engine/workers/multicore_scheduler.py:17` criam `ThreadPoolExecutor` **por chamada** (`with ...`), `MAX_WORKERS=min(32,cpu*2)` limitado e shutdown limpo. Churn menor por batch — **MEDIUM**, não crítico.
- **34-07/08 HTTP clients:** `requests.Session()` a nível de módulo em `app/core/api_timeout.py:15`, `app/core/telegram_timeout.py:18`, `app/telegram/telegram_alert_engine.py:80`; `httpx.AsyncClient` singleton em `app/telegram/bot.py:28`. **Reuso correto** (não por-request) ✓ — finding POSITIVO.
- **WebSocket (Seção 20):** `app/system/websocket_manager.py` já endurecido (M31F): `_max_connections=1000`, reserva de capacidade (`_pending_accepts`), accept timeout, rejeição de duplicados, purge de cliente morto, `RLock`, `gather(return_exceptions=True)`, `_safe_send` remove cliente com erro. **Sem bottleneck reproduzido** ⇒ refactor amplo de WS (Seção 20.1) = `FOLLOW_UP_NOT_EXECUTED_PERFORMANCE_NOT_PROVEN`. Micro-oportunidade: `broadcast` serializa a mensagem por-cliente (`send_json` N×) — poderia serializar 1×; MEDIUM.
- **Paginação/limites (Seção 31):** inconsistência real — endpoints com `limit` controlado pelo cliente **sem teto**: `routes_chat.py:51` (`limit:int=100`), `routes_social.py:15` (`=50`), `routes_moderation_admin.py:22,41` (`=100`), `routes_poll.py:19`, `routes_system.py:41,316`. Outros **clampam** corretamente via `safe_limit` (`routes_internal.py:34`, `routes_public_market_live.py:967`). Superfície de DoS/unbounded-pagination — **MEDIUM/HIGH**; correção (clamp uniforme) tocaria superfície de segurança ⇒ acionaria Codex Security.

## Testes
- **Suite backend completa:** `Ran 852 tests in 98.077s` — **OK**, exit 0. Zero failures, zero novos skips.
- **Web tsc/build, Playwright CLI/Interactive, Web Vitals (Chrome DevTools):** **NÃO executados** nesta passagem (limite de sessão/rate).
- **`$stocknewsbr-ai-regression`:** skill nativa ausente; mecanismo de digest before/after estabelecido no benchmark. Como nenhuma otimização foi aplicada, não há par antes/depois a comparar além do baseline.

## Gates bloqueados (registrados, sem PASS)
| Gate | Estado |
|------|--------|
| Render read-only | `TOOL_BLOCKED_RENDER` (sem acesso no ambiente) |
| NVIDIA / Nemotron | `TOOL_BLOCKED_NVIDIA` (sem acesso ao modelo) |
| Toxiproxy | Não instalado — cenários de falha (Seção 16) não executados |
| CodeRabbit | Autenticado (gitlab/dileno2010/stcoknewsbr1) — **não executado**: diff sem mudança de código de produção nesta passagem; obrigatório antes de qualquer PASS futuro |
| Playwright / Web Vitals / Chrome DevTools | Não executados (rate/session) |
| OpenTelemetry (42), PgBouncer/RLS (8.1), TimescaleDB (15.2), DuckDB (15.1) | Não alcançados (corretamente gated) |
| Codex Security | `NOT_APPLICABLE` — diff não toca código de produção/segurança |

## Segurança operacional / integridade
- `git add`/`commit`/`push`: **NÃO executados**.
- Alteração Render / deploy / migration: **NÃO**.
- Stress em produção ou provider real: **NÃO**.
- Score Mestre / pesos / thresholds / BUY-SELL-SHORT-COVER: **inalterados**.
- Tecnologia proibida (Kafka/K8s/ClickHouse/Elasticsearch/GraphQL/sharding/microserviços): **nenhuma introduzida**.

## Diff desta passagem
- `?? scripts/mission_34_benchmark_backtest.py` (novo, benchmark determinístico Seção 41)
- `docs/mission_34_performance_scale_resilience.md` (este relatório)
- `runtime/mission_34/**` (evidências — diretório gitignored)
- `git diff --check`: limpo. Nenhum arquivo de produção modificado.

## Conclusão (Rodada 1)
Gates independentes concluídos com evidência: Gate 0 PASS, inventário, reprodução+causa-raiz do O(n²), suite backend 852 OK, auditoria estática de hot paths. Gates obrigatórios Render/NVIDIA/Toxiproxy/Web-Vitals/CodeRabbit-run estão estruturalmente indisponíveis ou foram bloqueados pelo limite de sessão. **PASS não é declarado.** Próximos passos exigem: ambiente com Render/NVIDIA/Toxiproxy, reset do limite de sessão para a auditoria profunda + Playwright + Web Vitals, e decisão humana sobre o engine incremental do backtest antes de qualquer fix do O(n²).

---

# RODADA 2 — Continuação local (11/07/2026, mesma sessão)

**Regras atualizadas pelo usuário:** NVIDIA/Nemotron deixou de ser gate; Render deixou de ser gate (serviço não ativo/pago). Bloqueio de `git add`/`commit`/`push` mantido. Sem refactor amplo de WebSocket. Sem alteração financeira.

## RISK ACTION RECORD

```
Missão: 34 | Tier: 1
Ação: eliminar N+1 de I/O em get_posts (2N leituras+parses de moderation_state.json por request → 2)
Componente: app/social
Arquivos: app/social/moderation.py (+get_hidden_post_ids, +get_user_guardian_scores),
          app/social/posts.py (wiring em lote; _serialize_post ganha param opcional),
          tests/test_mission_34_performance_scale_resilience.py (novo)
Baseline: is_post_hidden ×300 = 0.2252–0.2742 s (estado sintético pequeno; produção pior)
Bottleneck confirmado: moderation.py:43 _load_state sem cache; posts.py chamava por post
  via _serialize_post→get_user_guardian_score e filtro is_post_hidden (2 loads/post, N≤500)
Impacto medido: get_hidden_post_ids(300) = 0.0007–0.0010 s (~270–320×); leituras por lote = 1 (teste conta)
Equivalência: testes de equivalência EXATA por id/uid em 20 estados aleatórios com seed
  (incl. None, ids inexistentes, duplicados, ações hide/remove/approve, auto_hidden misto)
Rollback: reverter os 2 arquivos (diff local, sem commit)
```

## Achado 34-02 (N+1) — CONFIRMADO e CORRIGIDO
Ver RISK ACTION RECORD acima. `is_post_hidden`/`get_user_guardian_score` por chamada permanecem intactos para os caminhos single-post (get_post/create_post) — compatibilidade total.

## Paginação (Seção 31) — RECLASSIFICADO: FALSE_POSITIVE
A rodada 1 apontou `limit` sem teto nas rotas. Verificação na camada de serviço provou clamps existentes: `get_posts` ≤500 (posts.py:114), `list_room_messages` ≤MAX_ROOM_MESSAGES, `get_review_queue`/`get_guardian_audit` ≤500, `get_poll_history`/`get_ai_worker_history` limitados pelo store em memória. **Nenhuma lista ilimitada confirmada; nenhuma edição necessária.**

## Backtest O(n²) — decisão desta rodada
Fix exato exige engine incremental (settings adaptativos por tamanho de prefixo) → mantém `BUSINESS_DECISION_REQUIRED`. Micro-fix da cópia (`list(rows[:end_index])`) teria ganho ~0,02% (sub-ruído) → **não aplicado** (regra Seção 51: sem benefício mensurável, não manter).

## Smoke Web (backend local + Next dev em 127.0.0.1:3000)
- Backend exige `SECRET_KEY` (hardening 31B) — subiu com chave efêmera de processo; instância já ativa na porta 8000 respondeu health 200.
- App renderiza: ticker tape com preços, página PETR4, gráfico com S/R, poll, social. **Console: zero erros.**
- **Notícias/IA:** sem quebra — estado vazio gracioso ("Sem notícia específica"), contadores IA presentes.
- **Requests duplicados — CONFIRMADO (dev):** 11 chamadas `GET /public/market/quotes` em ~1 s no load, universos sobrepostos (~330 símbolos-fetch para ~110 únicos ≈ 3× redundância) e **1 par byte-idêntico**. Causa: cada componente chama `getPublicQuotesChunked` com seu próprio universo; chunks (32) não se alinham entre universos → o cache por URL (TTL 8 s + single-flight, já existente em `lib/api.ts`) não deduplica sobreposição parcial. Par idêntico: suspeita Strict Mode dev / instância dupla de módulo — `NEEDS_REPRODUCTION` em build de produção.
- **Correção não aplicada** (consolidar universos exige quotes-store compartilhado = mudança de design; Seção 22 proíbe remover atualização legítima sem análise). Registrado como follow-up com evidência.

## Gates da Rodada 2
- Web TSC: **PASS** (exit 0).
- Web build: não executado (rate); TSC cobriu tipagem.
- Testes focados novos: **5/5 OK** (equivalência, contagem de I/O, evidência de timing).
- Suite backend completa + CodeRabbit (`-t uncommitted`): resultados na seção final abaixo.
- Playwright CLI formal: substituído por smoke interativo no browser pane (network+console evidenciados); cenários completos pendentes.
- Toxiproxy/OTel/PgBouncer/TimescaleDB/DuckDB: inalterados (bloqueados/gated como na rodada 1).

---

# RODADA 3 — Correção de workspace + fechamento no repo canônico `/home`

O trabalho da M34 havia sido executado no clone `/mnt/c/Users/dcima/stocknewsbr-backend`;
o repo canônico é `/home/dcima/stocknewsbr-backend`. Ambos estavam no mesmo
HEAD `49ee466c` (== origin), então o diff foi portado por cópia byte-idêntica
(verificada com `diff -q` nos 5 arquivos).

**Arquivos da M34 (diff completo):**
- `app/social/moderation.py` (+61) — helpers em lote `get_hidden_post_ids` / `get_user_guardian_scores`
- `app/social/posts.py` (+18/−4) — wiring em lote no `get_posts`
- `docs/mission_34_performance_scale_resilience.md` (novo)
- `scripts/mission_34_benchmark_backtest.py` (novo; `--reps` validado ≥1 após finding minor)
- `tests/test_mission_34_performance_scale_resilience.py` (novo, 5 testes)

**Gates executados no `/home` (Python canônico miniconda `ml` 3.11.15):**
- `git diff --check`: OK
- Teste focado M34: **5 passed** (0.10s)
- Suite completa: **856 passed, 1 skipped, 319 subtests, 55.34s**
- Web TSC (`npm --prefix apps/web run tsc`): **exit 0** (apps/web não tocado pela M34)
- CodeRabbit preliminar no /mnt/c: encerrado sem findings emitidos → `CODERABBIT_PRELIMINARY_FROM_MNTC` (descartado; conteúdo byte-idêntico coberto pelo final)
- **CodeRabbit final no /home (1ª passada):** 0 Critical / 0 Major / **1 Minor** (validar `--reps ≥ 1` no benchmark) → corrigido, sincronizado nos dois clones, sanity do script validado (`--reps 0` → erro argparse; run válido OK)
- **CodeRabbit final no /home (re-run pós-fix): 0 findings** → `CODERABBIT_FINAL_FROM_HOME = PASS` (5 arquivos revisados)
- Artefatos temporários removidos do /home: `data/moderation_state.json{,.lock}` (regenerados por teste), `runtime/mission_34/benchmarks/backtest_sanity.json`
- `git add`/`commit`/`push`: **NÃO executados**. Missão 35: **NÃO iniciada**.

## Status final da Missão 34

**PASS PARCIAL TÉCNICO (local).** Todos os gates executáveis neste ambiente passaram:
Gate 0, inventário, O(n²) reproduzido com causa-raiz e disposição (`BUSINESS_DECISION_REQUIRED`
para engine incremental), N+1 real corrigido com equivalência provada (~270×), paginação
reclassificada FALSE_POSITIVE, smoke Web com evidência de requests sobrepostos (follow-up),
suite completa, TSC, CodeRabbit final limpo. Permanecem fora do alcance deste ambiente
(registrados, não bloqueiam mais por decisão do usuário): Render (inativo/não pago),
NVIDIA/Nemotron (descontinuado), Toxiproxy, OpenTelemetry ponta-a-ponta, Web Vitals
formais em build de produção, Playwright CLI completo, PgBouncer/TimescaleDB/DuckDB.
