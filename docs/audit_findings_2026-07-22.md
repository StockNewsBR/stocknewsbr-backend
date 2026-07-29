# StockNewsBR — Lista Consolidada de Achados (Auditoria 22/07/2026)

Fonte: 3 auditorias externas (DeepSeek/Nemotron "6 agentes", "5 explore tasks/V36",
"Data/Connection/Speed"). Deduplicadas para 60 achados únicos.

> ⚠️ **Estas são alegações NÃO verificadas por padrão.** Spot-check dos 5 críticos
> encontrou **3 falsos positivos / referências desatualizadas** (linha errada, código
> já protegido, arquivo sem o problema alegado). **Verificar cada item antes de agir.**
> Coluna STATUS: `VERIF` = confirmado no código · `FALSO` = falso positivo/stale ·
> `?` = não verificado ainda.

Legenda severidade: 🔴 CRÍTICO · 🟠 ALTO · 🟡 MÉDIO · 🔵 BAIXO

---

## 🔴 CRÍTICOS

| # | STATUS | Arquivo:Linha | Problema | Impacto |
|---|---|---|---|---|
| 1 | **RESOLVIDO** (31620a76) | main.py:404-433 + routes_public_market_live.py:1199-1510 + routes_public_market.py:140,148 + routes_crypto.py + routes_portfolios.py | Endpoints premium sem autenticação (`/opportunities`, `/market-pulse`, `/spotlight`, live quotes/indices/insight/chart/bundle, `/market/news`, `/market/ai-tools`, `/crypto/radar`, `/portfolio/{name}`) | Anônimos obtêm sinais/master score/conviction sem assinatura |
| 2 | **FALSO** | engine_shards.py:9 | Import de `USA_STOCKS` inexistente → ImportError derruba worker | Linha 9 = `CRYPTO`; `market_universe.py` não tem `USA_STOCKS`. Referência errada/velha |
| 3 | **FALSO** | liquidity_sweep.py:36 | `logger` usado mas nunca importado → NameError | Nenhum `logger.` no arquivo. Sem base |
| 4 | **FALSO** | engine_orchestrator.py:23 | `int(os.getenv())` crasha na importação | Já usa `_env_int(name, default, minimum)`. Já protegido |
| 5 | **RESOLVIDO** (31620a76) | dependencies.py:56-62 | `db.add()+commit()+refresh()` em toda request autenticada | +10-50ms/req, gargalo serializante no DB |

## 🟠 ALTOS

| # | STATUS | Arquivo:Linha | Problema | Impacto |
|---|---|---|---|---|
| 6 | **RESOLVIDO** (d04aeb7a) | ai_common.py (safe_float) | Não rejeita NaN/Inf; propaga por ai_master_score + trade_decision | Score Mestre entrega NaN downstream |
| 7 | ? | Toda a API | Zero rate limiting (`/promo/redeem` brute-force, `/chat`, `/ticker/post`) | Abuso/brute-force |
| 8 | ? | ai_worker.py:531 | `bootstrap["key"]` sem `.get()` → KeyError | Crasha ciclo do AI Worker |
| 9 | ? | ai_worker.py:218-220 | Código morto no self-heal; snapshot stale nunca reconstruído | Dados velhos persistem |
| 10 | ? | push_dispatcher.py:226-329 | Estado não salvo em crash no meio do loop | Pushes duplicados |
| 11 | ? | telegram_alert_engine.py:404-408 | `time.sleep()` dentro do lock | Starvation das threads de alerta |
| 12 | ? | market_data_loader.py:1072-1097 | `batch_download()`: 1 ticker falho marca todos como failed | Cache poisoning em massa |
| 13 | ? | market_data_loader.py:1064 | `yfinance.download(threads=False)` sequencial | ~40-200s/batch de 50 |
| 14 | ? | market_data_loader.py:1669-1675 | `get_price_snapshot()` tenta 3 combos em série | ~8-24s por lookup |
| 15 | ? | signal_cache_layer.py:49,117 / snapshot_cache.py:281 / paper_trading_cache.py:170 | `deepcopy` de ~2000 sinais dentro do lock | Contention severa |
| 16 | ? | system_metrics.py | Lock único global + dicts `_external_provider_calls` sem limite | Memory leak lento |
| 17 | ? | market_snapshot_engine.py:707 | `.get()` sem guard em elemento de lista → AttributeError | Crasha snapshot |
| 18 | ? | ranking.py:45-49 | `_RANK_CACHE` sem thread-safety | Race no cache de ranking |
| 19 | ? | poll_service.py:151-156 | `_mutate_store` adquire lock depois da leitura | Opera em dados stale |
| 20 | ? | engine_orchestrator.py:362 | `time.time()` vs `time.perf_counter()` | Métricas negativas enormes |
| 21 | ? | models.py:65 | `updated_at` sem `onupdate` | Nunca atualiza (todos os modelos) |
| 22 | ? | paper_trading.py + signal_outcome_audit.py | Mutação (append) sem lock | Corrupção sob concorrência |
| 23 | ? | database.py (RLS) | RLS Postgres configurado, DB real é SQLite → RLS nunca testado | Risco em deploy Postgres |
| 24 | ? | market_activity.py | Horários B3/US hardcoded incorretos, sem feriados, `utcnow()` deprecated | Estado de mercado errado |
| 25 | ? | market_stream.py | WebSocket sem auth, sem isolamento, sem backpressure | Vazamento + cliente lento trava loop |
| 26 | ? | market_data_loader.py (1870L), market_snapshot_engine.py (886L), trend_breakout (1400L+) | Arquivos monstruosos + loop pandas row-by-row | Manutenção + CPU |
| 27 | ? | market_snapshot_engine.py:826-886 | Pipeline sem timeout; 1 AI lenta trava worker minutos | Worker travado |
| 28 | ? | workspace_service.py:237-295 + market_snapshot_engine.py:558-634 | ~18 passes redundantes sobre 200+ rows | ~18x CPU |
| 29 | ? | telegram_alert_engine.py:80-104 + bot.py:28-34 | `requests.Session()`/`httpx.AsyncClient` nunca fechados | Socket leak |

## 🟡 MÉDIOS

| # | STATUS | Arquivo | Problema |
|---|---|---|---|
| 30 | **RESOLVIDO** (c6b7981a) | (6 funções) | Normalização de símbolos duplicada (`_normalize_ticker`, `sanitize_market_symbol`...) tratam .SA/-USD divergente |
| 31 | ? | config.py / market_universe.py / universe_registry.py / universe_engine_v3.py | 3+ definições de universo sem verdade única |
| 32 | ? | snapshot_contract.py:648-705 | `build_decision_envelope` 2-10x por row no hot path |
| 33 | ? | workspace_service.py:345 + ranking.py:427 | Ranking computado 2x por request |
| 34 | ? | referrals.py:294-322,135-144,163-170 + warm_data_pool.py:59-92 | N+1 queries (até 500/batch; `.all()` onde bastava COUNT) |
| 35 | ? | social/*.py | 59+ `SessionLocal()` direto, bypass do `get_db()`, sem `clear_rls_context` |
| 36 | ? | social/store.py:34-64 | RLock sem file locking + write não atômico → corrupção de social_state.json |
| 37 | ? | (várias rotas) | Formato de erro inconsistente (4 formatos diferentes) |
| 38 | ? | auth.py | Self-downgrade sem verificação |
| 39 | ? | routes_public_market_live.py | Handlers chamados como funções → bypass de auth DI |
| 40 | ? | models.py | `datetime.utcnow()` deprecated, sem timezone |
| 41 | ? | snapshot_cache.py:320-355 + market_data_loader.py:752-818 | TOCTOU: `stat()` fora do lock |
| 42 | ? | ai_master_score.py + trade_decision.py + operational_rules.py | Defaults enviesados (news/macro=35 bearish; default "SELL"; 1 warning limita score a 79) |
| 43 | ? | poll_service.py | `_earnings_cache` sem lock/evicção + yfinance síncrono no serviço (viola AGENTS.md) |
| 44 | ? | email_service.py | Código OTP em texto claro no metadata dict |
| 45 | ? | routes_chart.py | Fail-open silencioso: exceção → `{"data":[]}` status 200 |
| 46 | ? | telegram_alert_engine.py + news_warmup.py | Memory leaks (`_sent_fingerprints`, `_last_warmup_at` sem lock); reports/CSV sem cleanup |
| 47 | ? | database.py:44-62 | `pool_pre_ping_timeout` não configurado; retry só para 429 |
| 48 | ? | tests/ | unittest (não pytest), sem conftest/fixtures/coverage/pyproject |
| 49 | ? | — | Sem CI/CD (`.github/workflows/` ausente) |
| 50 | ? | 10+ módulos | Globais mutáveis; IA engines legacy/stub (ai_market_narrative.py etc.) |

## 🔵 BAIXOS

| # | STATUS | Arquivo | Problema |
|---|---|---|---|
| 51 | ? | chart_warmup.py | `now or time.time()` → bug falso-falsy |
| 52 | ? | snapshot_worker.py, scheduler.py... | f-strings em logging em vez de `%s` |
| 53 | ? | snapshot_cache.py:354, signal_cache_layer.py:90 | `bare except:` mascara KeyboardInterrupt |
| 54 | ? | trend_breakout_signal_engine.py:1651-1720 | `"x" in locals()` 13+ vezes no hot path |
| 55 | ? | engine/signal_cache.py, market_symbols.py... | Código morto / re-exports thin |
| 56 | ? | routes_internal.py | Vazamento de erro: `{"ok":False,"detail":str(exc)}` |
| 57 | ? | admin_promo.py | `get_db` duplicado sem `clear_rls_context`; leaderboard sem auth |
| 58 | ? | poll_service.py:373 | Polls hardcoded em PT-BR (sem i18n) |
| 59 | ? | apps/web + apps/mobile | Web sem bundle analysis; mobile sem hermes/newArch |
| 60 | ? | main.py:257 | `validate_database_configuration()` 2x; schema validation ~50+ queries no startup |

---

## ✅ Positivos confirmados (pelas auditorias, não são bugs)
CSRF (SameSite + Origin); Stripe webhook com assinatura; internal token `compare_digest`;
JWT allowlist HS256; validação de schema de produção; `.env` não carregado em produção.

## 🎯 Top 5 por ganho/esforço (SE confirmados)
1. #1 + #5 — auth nos endpoints premium + remover `commit()` por request (cache TTL 60s)
2. #6 — `safe_float` com `math.isfinite()` (parar NaN de propagar)
3. #15 — `deepcopy()` fora dos locks
4. #28 + #32 + #33 — fundir passes do pipeline + memoizar `build_decision_envelope`
5. #13 + #14 — `yfinance.download(threads=True)` + fallback paralelo


---
## VALIDAÇÃO FINAL PÓS-AUDITORIA
- **c6b7981a**: Strategic panel (ticker público preservado, chave canônica, sem cross-assignment).
- **31620a76**: Auth/persistência (401 vira False, throttle 5min, rollback em falha).
- **2c56c6f0**: Índices (aliases para lookup, fallback de spark controlado, BDR protegido).
- **d04aeb7a**: Symbol registry (NaN/Inf rejeitados, finitos preservados).
- **49e90fe0**: Retenção/freshness (status estrutural, stale temporal).
- **62b124fd**: Testes (freshness isolado).
- **Testes**: 1.208 testes passaram (FULL_RESULT=0).
- **Dívida Técnica**: `test_institutional_*.py` vaza cache em ordem reversa.

## Próximo passo original
Rodar UMA verificação em lote (read-only) confirmando file:line de cada item antes de
qualquer correção — dado que 3/5 críticos já eram falsos, a lista real de trabalho
pode ser bem menor que 60.
