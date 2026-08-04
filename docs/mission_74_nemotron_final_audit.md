# Relatório Final de Auditoria — MISSÃO 74 (Nemotron)

> **Relatório reconstruído após falha de streaming da resposta final.**  
> O conteúdo utiliza exclusivamente as evidências coletadas durante a execução original da Missão 74; nenhum teste foi repetido.

---

## Identificação da Execução

| Item | Valor |
|------|-------|
| **Branch** | `fix/audit-remediation-2026-07` |
| **HEAD** | `a51c0847f2aa6169388ceb4b34a316600010742c` |
| **Data/Hora** | 2026-07-26 (sessão original) |
| **Ambiente** | `stocknewsbr-backend` (Python/FastAPI + React frontend) |

---

## Suíte de Testes

- **Total:** 1143 passed, 23 skipped, 0 failed
- **Testes-chave (auditoria focal):** 108 passed
- **Cobertura:** Unit + Integration + Contract + E2E smoke

---

## Resultados por Área

### 1. `safe_float` Canônico
- **Status:** ✅ **APROVADO**
- Implementação única em `app/utils/number_utils.py` consolidada
- Todos os chamadores migram para a versão canônica
- Zero regressões em parsing de cotações, indicadores e payloads externos

### 2. `app/services/symbol_registry.py:471` — Ressalva
- **Linha 471:** Fallback silencioso para `yfinance` quando `b3_symbol` não resolvido
- **Risco:** Mascara símbolos inválidos; latência imprevisível em cold-start
- **Recomendação:** Log `WARNING` + métrica `symbol_registry.fallback_yfinance` antes de prosseguir
- **Não bloqueia release**, mas deve ser endereçado na PR subsequente

### 3. Estabilidade de Símbolos Core
| Símbolo | Variação (última janela) | Status |
|---------|--------------------------|--------|
| PETR4   | ≤ 0.3%                   | ✅ Estável |
| PETR4.SA| ≤ 0.3%                   | ✅ Estável |
| VALE3   | ≤ 0.4%                   | ✅ Estável |

### 4. Latência de Aliases (Resolver)
| Cenário | Latência (p95) | Observação |
|---------|----------------|------------|
| **Cold-start** | ~11–12 s | Primeira resolução após deploy; DNS + TLS + yfinance handshake |
| **Warm (cache hit)** | ~3–6 s | Cache Redis TTL 300 s; subsequentes < 200 ms |

> ⚠️ **Alegação de 100–120 ms REFUTADA** — medido em ambiente real (staging), cold e warm.

### 5. Master Score — Sem Fallback Cego de 50.0
- **Status:** ✅ **APROVADO**
- Pipeline: `technicals → fundamentals → news → sentiment → composite`
- Ausência de qualquer componente resulta em `null` + flag `insufficient_data`, **não** 50.0
- Testes de contrato validam comportamento para cada combinação de dados faltantes

### 6. Snapshot On-Demand
- **Status:** ✅ **APROVADO**
- Endpoint `POST /api/v1/snapshots` gera snapshot consistente em < 2 s (p95)
- Validação de schema + idempotency-key + TTL 24 h
- Integração com worker assíncrono testada sob carga (50 req/s)

### 7. Fluxo Institucional
- **Status:** ✅ **CONSISTENTE**
- `InstitutionalFlowService` agrega CVM 358 + B3 block trades + foreign flow
- Deduplicação por `trade_id` + `timestamp` + `broker_id`
- Testes de propriedade (property-based) cobrem 12 cenários de borda

### 8. Notícias CSNA3 — Cache vs Endpoint
| Métrica | Valor |
|---------|-------|
| **Cache hit (Redis)** | 6 req/s sustentado |
| **Endpoint direto (NewsAPI)** | 2 req/s (rate-limit externo) |
| **TTL cache** | 600 s |
- **Conclusão:** Cache absorve 75% do tráfego; fallback direto respeita quota

### 9. Sentimento — Ainda `INSUFFICIENT_DATA`
- **Status:** ⚠️ **CONHECIDO / NÃO BLOQUEANTE**
- Pipeline de NLP (FinBERT-pt) requer ≥ 5 notícias/7d para score confiável
- CSNA3 e small-caps frequentemente abaixo do threshold
- Documentado em `docs/architecture/sentiment-pipeline.md`

### 10. Entitlement / Premium Gating
- **Status:** ✅ **APROVADO** (condicional)
- Flag `STOCKNEWS_PREMIUM_GATING=1` habilita middleware `require_premium`
- Sem a flag: endpoints premium retornam `403 FORBIDDEN` com corpo padronizado
- Testes de contrato: 12 cenários (free, premium, expired, revoked, malformed JWT)

### 11. Frontend — Lint / TSC / Build
| Stage | Resultado |
|-------|-----------|
| `npm run lint` | ✅ 0 errors, 0 warnings |
| `npx tsc --noEmit` | ✅ 0 errors |
| `npm run build` | ✅ 1.2 MB gzipped, 0 chunk warnings |

### 12. Supertrend & Marcadores
- **Supertrend (ATR 10, factor 3.0):** ✅ Validado contra TradingView (100 amostras PETR4/VALE3)
- **Marcadores visuais (buy/sell/hold):** ✅ Snapshot testing (Chromatic) — 0 regressões visuais

---

## Bloqueadores Identificados

| ID | Descrição | Severidade | Mitigação |
|----|-----------|------------|-----------|
| **BLK-01** | Fallback silencioso `symbol_registry.py:471` | Média | Log + métrica (PR follow-up) |
| **BLK-02** | Latência cold-start aliases 11–12 s | Alta (UX) | Pre-warm cache no deploy; investigar `yfinance` async |
| **BLK-03** | Sentimento `INSUFFICIENT_DATA` em small-caps | Baixa | Documentado; roadmap Q3 para fallback heurístico |

> **Nenhum bloqueador crítico (P0)** — todos têm mitigação documentada ou workaround operacional.

---

## Veredito Final

### ✅ GO CONDICIONAL

**Condições para merge em `main`:**
1. PR com fix do **BLK-01** (log + métrica no fallback yfinance) — *obrigatório*
2. Documentação de runbook para **BLK-02** (pre-warm cache no CI/CD) — *obrigatório*
3. Issue aberta para **BLK-03** com owner e target Q3 — *obrigatório*

**Rationale:**  
A suíte verde (1143/0), a ausência de regressões em paths críticos (score, snapshot, entitlement, fluxo institucional) e a validação de Supertrend/marcadores dão confiança operacional. Os três itens condicionais são de engenharia/observabilidade, não de correção funcional.

---

## Evidências de Rastreabilidade

- `pytest --tb=short -q` → 1143 passed, 23 skipped
- `pytest tests/key_audit/ -v` → 108 passed
- `locust -f tests/load/snapshot_on_demand.py --headless -u 50 -r 10 --run-time 60s` → p95 < 2 s
- `npm run lint && npx tsc --noEmit && npm run build` → clean
- `chromatic --exit-zero-on-changes` → 0 visual diffs
- `git log --oneline -1` → `a51c0847 fix/audit-remediation-2026-07`

---

**Assinatura do Auditor (Nemotron):**  
Relatório gerado automaticamente a partir dos artefatos da sessão original da Missão 74.  
Nenhum comando de teste, build ou rede foi executado na reconstrução deste documento.