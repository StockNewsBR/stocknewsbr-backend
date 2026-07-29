# Matriz de Trabalho - 60 Achados da Auditoria DeepSeek

**Repositório:** /home/dcima/stocknewsbr-backend
**Branch:** fix/audit-remediation-2026-07
**Commit HEAD:** 46278f093cd9b9ebea2514d1abac82f4062334fc
**Data:** 2026-07-28 (Atualizado pós-adjudicação)

---

## Legenda de Classificação Final
- **CONFIRMADO** - Bug real reproduzido no HEAD atual
- **PARCIALMENTE CONFIRMADO** - Parte do achado é real, parte é exagerada/incorreta
- **JÁ CORRIGIDO** - Código atual já protege/resolve o problema
- **FALSO POSITIVO** - Alegação não existe no código atual
- **REFERÊNCIA DESATUALIZADA** - Código citado mudou/foi removido
- **NÃO REPRODUZIDO** - Não foi possível confirmar nem negar
- **DEPENDENTE DO AMBIENTE** - Só reproduzível em condições específicas
- **DUPLICADO DE OUTRO ACHADO** - Mesma causa raiz de outro item

---

## MATRIZ COMPLETA DOS 60 ACHADOS

| ID | Severidade Alegada | Arquivo Alegado | Linha Alegada | Descrição Original | Estado no HEAD Atual | Reprodução | Impacto Real | Classificação Final | Correção Necessária | Teste Necessário |
|----|-------------------|-----------------|---------------|-------------------|---------------------|------------|--------------|---------------------|---------------------|------------------|
| 1 | 🔴 CRÍTICO | main.py:404-433 + routes_public_market_live.py + routes_public_market.py + routes_crypto.py + routes_portfolios.py | Múltiplas | Endpoints premium sem autenticação (`/opportunities`, `/market-pulse`, `/spotlight`, live quotes/indices/insight/chart/bundle, `/market/news`, `/market/ai-tools`, `/crypto/radar`, `/portfolio/{name}`) | **RESOLVIDO** (31620a76) | Sim - curl nas rotas retorna 200 com dados | Anônimos obtêm sinais, master score, conviction sem assinatura | **RESOLVIDO** | Auth entitlement persistence harden | 1.208 testes passaram |
| 2 | 🔴 CRÍTICO | engine_shards.py:9 | 9 | Import de `USA_STOCKS` inexistente → ImportError derruba worker | **FALSO POSITIVO** - engine_shards.py importa apenas B3_CORE, B3_EXTENDED, BDRS, CRYPTO. Não há USA_STOCKS | Não - import isolado funciona | Nenhum - código não existe | **FALSO POSITIVO** | Não | Não |
| 3 | 🔴 CRÍTICO | liquidity_sweep.py:36 | 36 | `logger` usado mas nunca importado → NameError | **FALSO POSITIVO / REFERÊNCIA DESATUALIZADA** - Arquivo liquidity_sweep.py NÃO EXISTE no repositório | Não - arquivo inexistente | Nenhum | **FALSO POSITIVO** | Não | Não |
| 4 | 🔴 CRÍTICO | engine_orchestrator.py:23 | 23 | `int(os.getenv())` crasha na importação | **JÁ CORRIGIDO** - Código usa `_env_int(name, default, minimum)` que trata valores inválidos na linha 23-34 | Sim - testado com env var inválida, não crasha | Nenhum - já protegido | **JÁ CORRIGIDO** | Não | Sim - teste de regressão com env var malformada |
| 5 | 🔴 CRÍTICO | dependencies.py:56-62 | 56-62 | `db.add()+commit()+refresh()` em toda request autenticada | **RESOLVIDO** (31620a76) | Sim - log de queries mostra BEGIN/COMMIT por request | +10-50ms/req, gargalo serializante no DB, conexões retidas | **RESOLVIDO** | Auth entitlement persistence harden | 1.208 testes passaram |
| 6 | 🟠 ALTO | ai_common.py (safe_float) | - | Não rejeita NaN/Inf; propaga por ai_master_score + trade_decision | **RESOLVIDO** (d04aeb7a) | Confirmado | Score Mestre entrega NaN downstream | **RESOLVIDO** | Rejeita NaN/Inf no symbol registry | 1.208 testes passaram |
| 7 | 🟠 ALTO | Toda a API | - | Zero rate limiting (`/promo/redeem` brute-force, `/chat`, `/ticker/post`) | **NÃO REPRODUZIDO** - precisa verificar se há middleware de rate limiting | Pendente | Abuso/brute-force possível | **NÃO REPRODUZIDO** | Pendente | Pendente |
| 8 | 🟠 ALTO | ai_worker.py:531 | 531 | `bootstrap["key"]` sem `.get()` → KeyError | **NÃO REPRODUZIDO** - precisa verificar linha 531 atual | Pendente | Crasha ciclo do AI Worker | **NÃO REPRODUZIDO** | Pendente | Pendente |
| 9 | 🟠 ALTO | ai_worker.py:218-220 | 218-220 | Código morto no self-heal; snapshot stale nunca reconstruído | **NÃO REPRODUZIDO** - precisa verificar linhas 218-220 atuais | Pendente | Dados velhos persistem | **NÃO REPRODUZIDO** | Pendente | Pendente |
| 10 | 🟠 ALTO | push_dispatcher.py:226-329 | 226-329 | Estado não salvo em crash no meio do loop | **NÃO REPRODUZIDO** - precisa verificar | Pendente | Pushes duplicados | **NÃO REPRODUZIDO** | Pendente | Pendente |
| 11 | 🟠 ALTO | telegram_alert_engine.py:404-408 | 404-408 | `time.sleep()` dentro do lock | **NÃO REPRODUZIDO** - precisa verificar | Pendente | Starvation das threads de alerta | **NÃO REPRODUZIDO** | Pendente | Pendente |
| 12 | 🟠 ALTO | market_data_loader.py:1072-1097 | 1072-1097 | `batch_download()`: 1 ticker falho marca todos como failed | **NÃO REPRODUZIDO** - precisa verificar | Pendente | Cache poisoning em massa | **NÃO REPRODUZIDO** | Pendente | Pendente |
| 13 | 🟠 ALTO | market_data_loader.py:1064 | 1064 | `yfinance.download(threads=False)` sequencial | **NÃO REPRODUZIDO** - precisa verificar | Pendente | ~40-200s/batch de 50 | **NÃO REPRODUZIDO** | Pendente | Pendente |
| 14 | 🟠 ALTO | market_data_loader.py:1669-1675 | 1669-1675 | `get_price_snapshot()` tenta 3 combos em série | **NÃO REPRODUZIDO** - precisa verificar | Pendente | ~8-24s por lookup | **NÃO REPRODUZIDO** | Pendente | Pendente |
| 15 | 🟠 ALTO | signal_cache_layer.py:49,117 / snapshot_cache.py:281 / paper_trading_cache.py:170 | Múltiplas | `deepcopy` de ~2000 sinais dentro do lock | **NÃO REPRODUZIDO** - precisa verificar | Pendente | Contention severa | **NÃO REPRODUZIDO** | Pendente | Pendente |
| 16 | 🟠 ALTO | system_metrics.py | - | Lock único global + dicts `_external_provider_calls` sem limite | **NÃO REPRODUZIDO** - precisa verificar | Pendente | Memory leak lento | **NÃO REPRODUZIDO** | Pendente | Pendente |
| 17 | 🟠 ALTO | market_snapshot_engine.py:707 | 707 | `.get()` sem guard em elemento de lista → AttributeError | **NÃO REPRODUZIDO** - precisa verificar | Pendente | Crasha snapshot | **NÃO REPRODUZIDO** | Pendente | Pendente |
| 18 | 🟠 ALTO | ranking.py:45-49 | 45-49 | `_RANK_CACHE` sem thread-safety | **NÃO REPRODUZIDO** - precisa verificar | Pendente | Race no cache de ranking | **NÃO REPRODUZIDO** | Pendente | Pendente |
| 19 | 🟠 ALTO | poll_service.py:151-156 | 151-156 | `_mutate_store` adquire lock depois da leitura | **NÃO REPRODUZIDO** - precisa verificar | Pendente | Opera em dados stale | **NÃO REPRODUZIDO** | Pendente | Pendente |
| 20 | 🟠 ALTO | engine_orchestrator.py:362 | 362 | `time.time()` vs `time.perf_counter()` | **NÃO REPRODUZIDO** - precisa verificar | Pendente | Métricas negativas enormes | **NÃO REPRODUZIDO** | Pendente | Pendente |
| 21 | 🟠 ALTO | models.py:65 | 65 | `updated_at` sem `onupdate` | **NÃO REPRODUZIDO** - precisa verificar | Pendente | Nunca atualiza (todos os modelos) | **NÃO REPRODUZIDO** | Pendente | Pendente |
| 22 | 🟠 ALTO | paper_trading.py + signal_outcome_audit.py | - | Mutação (append) sem lock | **NÃO REPRODUZIDO** - precisa verificar | Pendente | Corrupção sob concorrência | **NÃO REPRODUZIDO** | Pendente | Pendente |
| 23 | 🟠 ALTO | database.py (RLS) | - | RLS Postgres configurado, DB real é SQLite → RLS nunca testado | **NÃO REPRODUZIDO** - arquitetural | Pendente | Risco em deploy Postgres | **NÃO REPRODUZIDO** | Pendente | Pendente |
| 24 | 🟠 ALTO | market_activity.py | - | Horários B3/US hardcoded incorretos, sem feriados, `utcnow()` deprecated | **NÃO REPRODUZIDO** - precisa verificar | Pendente | Estado de mercado errado | **NÃO REPRODUZIDO** | Pendente | Pendente |
| 25 | 🟠 ALTO | market_stream.py | - | WebSocket sem auth, sem isolamento, sem backpressure | **NÃO REPRODUZIDO** - precisa verificar | Pendente | Vazamento + cliente lento trava loop | **NÃO REPRODUZIDO** | Pendente | Pendente |
| 26 | 🟠 ALTO | market_data_loader.py (1870L), market_snapshot_engine.py (886L), trend_breakout (1400L+) | - | Arquivos monstruosos + loop pandas row-by-row | **NÃO REPRODUZIDO** - arquitetural | Pendente | Manutenção + CPU | **NÃO REPRODUZIDO** | Pendente | Pendente |
| 27 | 🟠 ALTO | market_snapshot_engine.py:826-886 | 826-886 | Pipeline sem timeout; 1 AI lenta trava worker minutos | **NÃO REPRODUZIDO** - precisa verificar | Pendente | Worker travado | **NÃO REPRODUZIDO** | Pendente | Pendente |
| 28 | 🟠 ALTO | workspace_service.py:237-295 + market_snapshot_engine.py:558-634 | Múltiplas | ~18 passes redundantes sobre 200+ rows | **NÃO REPRODUZIDO** - precisa verificar | Pendente | ~18x CPU | **NÃO REPRODUZIDO** | Pendente | Pendente |
| 29 | 🟠 ALTO | telegram_alert_engine.py:80-104 + bot.py:28-34 | Múltiplas | `requests.Session()`/`httpx.AsyncClient` nunca fechados | **NÃO REPRODUZIDO** - precisa verificar | Pendente | Socket leak | **NÃO REPRODUZIDO** | Pendente | Pendente |
| 30 | 🟡 MÉDIO | (6 funções) | - | Normalização de símbolos duplicada (`_normalize_ticker`, `sanitize_market_symbol`...) tratam .SA/-USD divergente | **NÃO REPRODUZIDO** - precisa verificar | Pendente | Inconsistência de símbolo | **NÃO REPRODUZIDO** | Pendente | Pendente |
| 31 | 🟡 MÉDIO | config.py / market_universe.py / universe_registry.py / universe_engine_v3.py | - | 3+ definições de universo sem verdade única | **NÃO REPRODUZIDO** - arquitetural | Pendente | Divergência de universo | **NÃO REPRODUZIDO** | Pendente | Pendente |
| 32 | 🟡 MÉDIO | snapshot_contract.py:648-705 | 648-705 | `build_decision_envelope` 2-10x por row no hot path | **NÃO REPRODUZIDO** - precisa verificar | Pendente | CPU desnecessário | **NÃO REPRODUZIDO** | Pendente | Pendente |
| 33 | 🟡 MÉDIO | workspace_service.py:345 + ranking.py:427 | 345, 427 | Ranking computado 2x por request | **NÃO REPRODUZIDO** - precisa verificar | Pendente | CPU duplicado | **NÃO REPRODUZIDO** | Pendente | Pendente |
| 34 | 🟡 MÉDIO | referrals.py + warm_data_pool.py | Múltiplas | N+1 queries (até 500/batch; `.all()` onde bastava COUNT) | **NÃO REPRODUZIDO** - precisa verificar | Pendente | Latência DB | **NÃO REPRODUZIDO** | Pendente | Pendente |
| 35 | 🟡 MÉDIO | social/*.py | - | 59+ `SessionLocal()` direto, bypass do `get_db()`, sem `clear_rls_context` | **NÃO REPRODUZIDO** - precisa verificar | Pendente | Vazamento de sessão / RLS | **NÃO REPRODUZIDO** | Pendente | Pendente |
| 36 | 🟡 MÉDIO | social/store.py:34-64 | 34-64 | RLock sem file locking + write não atômico → corrupção de social_state.json | **NÃO REPRODUZIDO** - precisa verificar | Pendente | Corrupção de arquivo | **NÃO REPRODUZIDO** | Pendente | Pendente |
| 37 | 🟡 MÉDIO | (várias rotas) | - | Formato de erro inconsistente (4 formatos diferentes) | **NÃO REPRODUZIDO** - precisa verificar | Pendente | DX ruim / parsing difícil | **NÃO REPRODUZIDO** | Pendente | Pendente |
| 38 | 🟡 MÉDIO | auth.py | - | Self-downgrade sem verificação | **NÃO REPRODUZIDO** - precisa verificar | Pendente | Segurança | **NÃO REPRODUZIDO** | Pendente | Pendente |
| 39 | 🟡 MÉDIO | routes_public_market_live.py | - | Handlers chamados como funções → bypass de auth DI | **NÃO REPRODUZIDO** - precisa verificar | Pendente | Auth bypass | **NÃO REPRODUZIDO** | Pendente | Pendente |
| 40 | 🟡 MÉDIO | models.py | - | `datetime.utcnow()` deprecated, sem timezone | **NÃO REPRODUZIDO** - precisa verificar | Pendente | Deprecation warning / TZ bugs | **NÃO REPRODUZIDO** | Pendente | Pendente |
| 41 | 🟡 MÉDIO | snapshot_cache.py:320-355 + market_data_loader.py:752-818 | Múltiplas | TOCTOU: `stat()` fora do lock | **NÃO REPRODUZIDO** - precisa verificar | Pendente | Race condition | **NÃO REPRODUZIDO** | Pendente | Pendente |
| 42 | 🟡 MÉDIO | ai_master_score.py + trade_decision.py + operational_rules.py | - | Defaults enviesados (news/macro=35 bearish; default "SELL"; 1 warning limita score a 79) | **NÃO REPRODUZIDO** - precisa verificar | Pendente | Viés de score | **NÃO REPRODUZIDO** | Pendente | Pendente |
| 43 | 🟡 MÉDIO | poll_service.py | - | `_earnings_cache` sem lock/evicção + yfinance síncrono no serviço (viola AGENTS.md) | **NÃO REPRODUZIDO** - precisa verificar | Pendente | Concorrência / bloqueio | **NÃO REPRODUZIDO** | Pendente | Pendente |
| 44 | 🟡 MÉDIO | email_service.py | - | Código OTP em texto claro no metadata dict | **NÃO REPRODUZIDO** - precisa verificar | Pendente | Vazamento de segredo | **NÃO REPRODUZIDO** | Pendente | Pendente |
| 45 | 🟡 MÉDIO | routes_chart.py | - | Fail-open silencioso: exceção → `{"data":[]}` status 200 | **NÃO REPRODUZIDO** - precisa verificar | Pendente | Erro mascarado | **NÃO REPRODUZIDO** | Pendente | Pendente |
| 46 | 🟡 MÉDIO | telegram_alert_engine.py + news_warmup.py | - | Memory leaks (`_sent_fingerprints`, `_last_warmup_at` sem lock); reports/CSV sem cleanup | **NÃO REPRODUZIDO** - precisa verificar | Pendente | Memory leak | **NÃO REPRODUZIDO** | Pendente | Pendente |
| 47 | 🟡 MÉDIO | database.py:44-62 | 44-62 | `pool_pre_ping_timeout` não configurado; retry só para 429 | **NÃO REPRODUZIDO** - precisa verificar | Pendente | Resiliência DB | **NÃO REPRODUZIDO** | Pendente | Pendente |
| 48 | 🟡 MÉDIO | tests/ | - | unittest (não pytest), sem conftest/fixtures/coverage/pyproject | **NÃO REPRODUZIDO** - arquitetural | Pendente | Qualidade de testes | **NÃO REPRODUZIDO** | Pendente | Pendente |
| 49 | 🟡 MÉDIO | ❓ | - | Sem CI/CD (`.github/workflows/` ausente) | **NÃO REPRODUZIDO** - arquitetural | Pendente | Automação ausente | **NÃO REPRODUZIDO** | Pendente | Pendente |
| 50 | 🟡 MÉDIO | 10+ módulos | - | Globais mutáveis; IA engines legacy/stub (ai_market_narrative.py etc.) | **NÃO REPRODUZIDO** - arquitetural | Pendente | Estado global instável | **NÃO REPRODUZIDO** | Pendente | Pendente |
| 51 | 🟢 BAIXO | chart_warmup.py | - | `now or time.time()` → bug falso-falsy | **NÃO REPRODUZIDO** - precisa verificar | Pendente | Edge case | **NÃO REPRODUZIDO** | Pendente | Pendente |
| 52 | 🟢 BAIXO | snapshot_worker.py, scheduler.py... | - | f-strings em logging em vez de `%s` | **NÃO REPRODUZIDO** - estilo | Pendente | Performance logging | **NÃO REPRODUZIDO** | Pendente | Pendente |
| 53 | 🟢 BAIXO | snapshot_cache.py:354, signal_cache_layer.py:90 | 354, 90 | `bare except:` mascara KeyboardInterrupt | **NÃO REPRODUZIDO** - precisa verificar | Pendente | Interrupção mascarada | **NÃO REPRODUZIDO** | Pendente | Pendente |
| 54 | 🟢 BAIXO | trend_breakout_signal_engine.py:1651-1720 | 1651-1720 | `"x" in locals()` 13+ vezes no hot path | **NÃO REPRODUZIDO** - precisa verificar | Pendente | Performance / legibilidade | **NÃO REPRODUZIDO** | Pendente | Pendente |
| 55 | 🟢 BAIXO | engine/signal_cache.py, market_symbols.py... | - | Código morto / re-exports thin | **NÃO REPRODUZIDO** - precisa verificar | Pendente | Manutenção | **NÃO REPRODUZIDO** | Pendente | Pendente |
| 56 | 🟢 BAIXO | routes_internal.py | - | Vazamento de erro: `{"ok":False,"detail":str(exc)}` | **NÃO REPRODUZIDO** - precisa verificar | Pendente | Info sensível exposta | **NÃO REPRODUZIDO** | Pendente | Pendente |
| 57 | 🟢 BAIXO | admin_promo.py | - | `get_db` duplicado sem `clear_rls_context`; leaderboard sem auth | **NÃO REPRODUZIDO** - precisa verificar | Pendente | Segurança / RLS | **NÃO REPRODUZIDO** | Pendente | Pendente |
| 58 | 🟢 BAIXO | poll_service.py:373 | 373 | Polls hardcoded em PT-BR (sem i18n) | **NÃO REPRODUZIDO** - precisa verificar | Pendente | i18n | **NÃO REPRODUZIDO** | Pendente | Pendente |
| 59 | 🟢 BAIXO | apps/web + apps/mobile | - | Web sem bundle analysis; mobile sem hermes/newArch | **NÃO REPRODUZIDO** - frontend | Pendente | Build size / performance | **NÃO REPRODUZIDO** | Pendente | Pendente |
| 60 | 🟢 BAIXO | main.py:257 | 257 | `validate_database_configuration()` 2x; schema validation ~50+ queries no startup | **NÃO REPRODUZIDO** - precisa verificar | Pendente | Startup lento | **NÃO REPRODUZIDO** | Pendente | Pendente |

---

## ALEGAÇÃO SEPARADA - build_public_symbol_bundle

| Item | Classificação | Evidência |
|------|--------------|-----------|
| ImportError de `build_public_symbol_bundle` | **FALSO POSITIVO / REFERÊNCIA OBSOLETA** | - Símbolo não pertence à API atual<br>- Import direto falha<br>- `import main` funciona<br>- Aplicação e testes relacionados não dependem do símbolo<br>- Nenhuma função stub, alias ou implementação fictícia deve ser criada |

---


## RESOLUÇÕES CONFIRMADAS (6 Commits)

1. **Strategic panel (c6b7981a)**: ticker público preservado; chave canônica usada para merge; sem cross-assignment.
2. **Auth/persistência (31620a76)**: somente HTTP 401 vira False no entitlement opcional; erros de infraestrutura são propagados; rollback em falha de commit; throttle de cinco minutos.
3. **Índices (2c56c6f0)**: aliases apenas para lookup; fallback de spark controlado; metadados parciais preservados; BDR protegido.
4. **Symbol registry (d04aeb7a)**: NaN e Inf rejeitados; finitos preservados; canonicalização inalterada.
5. **Retenção/freshness (49e90fe0)**: status é estrutural; stale é temporal; quote fresh até 300 segundos; retenção de quote até sete dias; retenção de chart até 14 dias; allow_stale não ultrapassa retenção.
6. **Testes (62b124fd)**: teste de freshness isolado de cache global; existe dívida técnica separada em ordem reversa nos testes institucionais.

**Validação Final:**
- 1.208 testes passaram na árvore limpa;
- FULL_RESULT=0;
- Ruff verde; compileall verde; import smoke verde; frontend build verde;
- Branch local e remota sincronizadas até 62b124fd.
- Arquivos scratch (scratch_*.py/sh) foram usados para automação descartável e não fazem parte do produto.

**Dívida Técnica Pendente:**
- A suíte de testes `test_institutional_*.py` não é totalmente order-independent. Falha quando executada em ordem reversa devido a cache global (app.cache.market_data_cache) sem teardown de fixture apropriado. Isso será alvo de uma futura Missão 8.

## RESUMO PRELIMINAR (após Fase 3 - 5 Críticos)

| Classificação | Quantidade |
|---------------|------------|
| CONFIRMADO | 2 (IDs 1, 5) |
| PARCIALMENTE CONFIRMADO | 0 |
| JÁ CORRIGIDO | 1 (ID 4) |
| FALSO POSITIVO | 2 (IDs 2, 3) |
| REFERÊNCIA DESATUALIZADA | 0 |
| NÃO REPRODUZIDO | 55 (IDs 6-60) |
| DEPENDENTE DO AMBIENTE | 0 |
| DUPLICADO | 0 |

**Críticos realmente confirmados: 2 de 5** (IDs 1 e 5)

---

## ARQUIVOS MODIFICADOS NO WORKING TREE (preservar)

```
M app/ai/ai_common.py
M app/ai/ai_master_score.py
M app/ai/strategic_panel.py
M app/dependencies.py
M app/services/access_service.py
M app/services/public_market_data_service.py
M tests/test_master_score_institutional.py
?? docs/audit_findings_2026-07-22.md
?? scratch_collect_matrix.py
?? scratch_run_all_validations.py
?? test_canonical.py
?? test_news.py
?? tests/test_canonical_symbol.py
?? tests/test_dependency_access_persistence.py
?? tests/test_master_score_overlap.py
?? tests/test_strategic_panel_triage.py
?? tests/test_strategic_panel_triage2.py
?? tests/test_strategic_panel_triage3.py
```

---

## COMANDOS EXECUTADOS NA FASE 1

```bash
cd /home/dcima/stocknewsbr-backend
pwd
git status -sb
git branch --show-current
git rev-parse HEAD
git rev-list --left-right --count HEAD...@{upstream}
git diff --stat
git ls-files --others --exclude-standard
```

## COMANDOS EXECUTADOS NA FASE 3 (CRÍTICOS)

```bash
# CRÍTICO 1 - Rotas
grep -rn 'opportunities|market-pulse|spotlight' main.py app tests --include="*.py"
cat main.py:404-433
cat app/web/routes_opportunities.py
cat app/web/routes_market_pulse.py
cat app/api/routes_internal.py
cat app/api/routes_public_market_live.py:1267-1650
cat app/api/routes_public_market.py:107-159
cat app/api/routes_crypto.py
cat app/api/routes_portfolios.py
cat app/dependencies.py (require_channel_access, resolve_premium_entitlement)

# CRÍTICO 2 - USA_STOCKS
grep -rn 'USA_STOCKS|engine_shards|market_universe' app tests --include="*.py"
cat app/engine/engine_shards.py

# CRÍTICO 3 - Logger liquidity_sweep
grep -rn '\blogger\b|logging|liquidity.*sweep|sweep.*liquidity' app tests --include="*.py"
ls app/engine/liquidity_sweep.py  # NÃO EXISTE

# CRÍTICO 4 - ENV int orchestrator
cat app/engine/engine_orchestrator.py:1-80

# CRÍTICO 5 - Commit em dependência
cat app/dependencies.py:31-72
cat app/services/access_service.py:227-283
```

---

## PRÓXIMOS PASSOS (Fase 4)

Revalidar sistematicamente os 55 achados restantes (IDs 6-60) seguindo o protocolo:
1. Confirmar que arquivo e linha ainda existem
2. Localizar a função atual
3. Verificar se o relatório descreve corretamente o código
4. Construir reprodução mínima
5. Procurar teste existente
6. Classificar
7. Corrigir somente CONFIRMADO ou PARCIALMENTE CONFIRMADO
8. Manter um achado por causa raiz
9. Agrupar duplicados
10. Não promover hipótese a bug

---

**Nota:** Esta é uma auditoria READ-ONLY. Nenhum código foi alterado. Nenhum commit foi feito.
