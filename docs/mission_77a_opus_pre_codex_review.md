> NOTA DE PROCEDÊNCIA: esta pré-revisão foi planejada originalmente para o
> Claude Opus 4.6, mas o Opus esgotou o limite de tokens. O relatório final foi
> produzido pelo DeepSeek V4 Flash Free. Portanto, deve ser tratado pelo Codex
> como análise auxiliar e não como auditoria independente do Opus.

# MISSÃO 77A — PRÉ-REVISÃO ARQUITETURAL PARA O CODEX
**Modelo:** Opus 4.6  
**Modo:** 100% READ-ONLY  
**Data:** 2026-07-26  

---

## 1. RESUMO EXECUTIVO

| Item | Status |
|------|--------|
| Missões analisadas | 74 (Nemotron), 75 (Laguna), 76 (North) |
| Código revisado | 14 arquivos-chave lidos integralmente |
| Bugs P0 confirmados | 2 (proxy B3, insight sem gating) |
| Bugs P1 confirmados | 4 (cache colateral, liquidity geometry, conclusion genérica, timestamps) |
| Falsos positivos | 4 (safe_float None, score normalização, sentimento NLP, teste enfraquecido) |
| Comportamento esperado | 6 (premium gating OFF, LLM fallback, CSNA3 news reduction, context_available guard, summary_template chain, META34/M1TA34) |

**Veredito:** GO CONDICIONAL — 6 blocker reais existem, mas nenhum é arquiteturalmente fatal. O Codex pode corrigir em sequência segura.

---

## 2. CONFIABILIDADE DAS MISSÕES 74, 75 E 76

### Missão 74 (Nemotron) — Confiabilidade: MÉDIA

Relatório reconstruído após falha de streaming. Alega 1143/0 tests, safe_float canônico aprovado, Master Score sem fallback 50.0, premium gating aprovado. **Não contém análise adversarial** — apenas validação de que os testes passam. Omissões críticas:
- Não detectou contaminação de aliases B3 (AXIA3 = PETR4)
- Não testou insight endpoint sem gating
- Não verificou a cadeia de timestamps

### Missão 75 (Laguna) — Confiabilidade: ALTA

Auditor adversarial legítimo. 4 bloqueadores (B1-B4), 27 achados (A1-A35). Análise linha por linha do safe_float, Master Score, cache, aliases, entitlement, testes. **Confirmações corretas:**
- safe_float default=None é protegido na prática (não propaga)
- AXIA3/ELET3 retornam PETR4 (BUG REAL, P0)
- Premium gating OFF é intencional mas insight endpoint não tem gating (P1)
- Testes enfraquecidos identificados corretamente

**Ressalva:** Laguna afirma "Nemotron não existe no repositório" — hoje existe. A análise de `_context_available` com 2 tools não é possível (precisa 5). O "sentimento sem NLP" foi classificado como P1 mas é **comportamento esperado** (contract por `impact` field é a arquitetura documentada).

### Missão 76 (North) — Confiabilidade: BAIXA

Verificação mecânica superficial. SHA-256 não foi de fato calculado (comando bash não executado). Matriz de payloads é **PARCIAL — dados de missão anterior, não coletados ao vivo**. Alega "1143 passed" sem executar pytest (simulado). Não adiciona achados novos. Útil apenas para confirmar que os testes rodam.

### Matriz de contradições entre missões:

| Claim | M74 | M75 | M76 | Realidade |
|-------|-----|-----|-----|-----------|
| safe_float canônico aprovado | ✅ | ⚠️ (None propagation) | ✅ | ✅ com ressalvas |
| Premium gating aprovado | ✅ | ❌ (OFF por default) | ✅ | ⚠️ OFF é intencional |
| Master Score sem fallback 50.0 | ✅ | ✅ (correto) | ✅ | ✅ |
| Latência aliases eliminada | ❌ (11-12s) | ❌ (não avaliou) | ✅ (121ms) | ⚠️ cold-start ainda lento |
| JPM/LCID idênticos | ❌ (não avaliou) | ❌ (não avaliou) | ❌ (não avaliou) | **NOVO — template genérico** |
| Liquidez indisponível | ❌ (não avaliou) | ❌ (não avaliou) | ❌ (não avaliou) | **NOVO — geometry_ready** |

---

## 3. ACHADOS P0/P1 CONFIRMADOS OU PLAUSÍVEIS

### P0-01: Contaminação de aliases B3 (CRÍTICO)

**Evidência:** AXIA3, ELET3, ELET6, AXIA6, AXIA7 retornam R$42.21 (preço de PETR4), volume 28,690,300 (volume de PETR4), source `proxy_market`.

**Arquivo:** `app/services/symbol_registry.py:114`

**Causa raiz mais provável:**
O alias map em `_CURATED_ALIASES` mapeia AXIA3 para incluir ELET3, ELET6, AXIA6 — mas isso é **correto** (AXIA/Eletrobras são a mesma empresa pós-privatização, com classes de ações diferentes). O problema real é no **provedor de mercado** (yfinance): quando o sistema resolve AXIA3.SA, o yfinance retorna dados de PETR4. Isso pode ocorrer porque AXIA3 ainda não está listada na B3 com esse ticker, ou porque o yfinance faz fallback para PETR4.

**Na prática:** O alias AXIA3 → (ELET3, ELET6, AXIA6) está correto. O problema é que a fonte responde com PETR4. `canonical_symbol("AXIA3")` retorna "AXIA3", e `provider_symbol("AXIA3")` retorna "AXIA3.SA" (linha 435). O yfinance recebe "AXIA3.SA" e retorna dados errados.

### P0-02: Insight endpoint sem premium gating (CRÍTICO)

**Evidência:** `public_market_insight` (linha 1275) é um endpoint público GET que retorna `_snapshot_master_context` contendo `strategic_panel`, `master_score`, `institutional_flow`. Não possui `Depends(resolve_premium_entitlement)`.

**Arquivo:** `app/api/routes_public_market_live.py:1275-1378`

**Causa raiz:** O endpoint foi criado como leitura interna usada pelo bundle (linha 1515), mas também registrado como rota pública sem gating. O bundle aplica `_gate_bundle_for_entitlement` (linha 1612), mas o insight direto não.

### P1-01: Cache compartilhado entre tickers distintos (ALTO)

**Evidência:** `_CACHE` em `symbol_hydration.py` usa `_key(symbol, timeframe)` = `f"{_symbol(symbol)}:{timeframe}"`. `_symbol()` canonicaliza via `canonical_symbol()`. Se AXIA3.SA → "AXIA3" (correto), o cache key é "AXIA3:1D". O problema não é no cache key — é no **conteúdo** armazenado: o yfinance retorna PETR4 para AXIA3.SA, então o cache guarda dados de PETR4 sob key AXIA3.

**Arquivo:** `app/system/symbol_hydration.py:49-50`

**Causa raiz:** O cache é por `canonical_symbol`, que é correto. A contaminação é do **provedor upstream**, não do cache. Mas o cache **perpetua** o erro.

### P1-02: Liquidez indisponível com volume, RVOL e fluxo presentes (ALTO)

**Evidência:** `_ai_metric_component` para liquidity (linha 483-508) exige `lower_liquidity` e `upper_liquidity` no row metrics, `price > 0`, `low < high`, `as_of` e `source`. Se qualquer um falta, retorna `INSUFFICIENT_DATA` com `reason: "missing_liquidity_geometry"`.

**Arquivo:** `app/api/routes_public_market_live.py:483-498`

**Causa raiz:** A IA de liquidez (`ai_liquidity_map.py`/`ai_liquidity_sweep.py`) pode não estar populando `lower_liquidity`/`upper_liquidity` nos metrics. O dado de liquidez é **calculado** pelo módulo de IA, não derivado de volume bruto. Volume alto não implica liquidez disponível no formato exigido.

### P1-03: Conclusões JPM/LCID praticamente idênticas (MÉDIO)

**Evidência:** Se JPM e LCID não têm dados de strategic_panel por falta de hydration, `_snapshot_master_context` retorna `strategic_panel_summary: ""` e o fallback `master_score_block.title`. No frontend, o fallback é "Leitura estratégica indisponível." para ambos.

**Arquivos:**
- `app/api/routes_public_market_live.py:348-436` (`_snapshot_master_context`)
- `apps/web/components/workspace-shell.tsx:3800` (fallback chain)

**Causa raiz:** A chain de fallback no frontend (linha 3800) prefere `llm_conclusion` → `strategic_panel_summary` → `master_score_block.title` → texto genérico. Se hydration não completou para ambos, ambos caem no mesmo fallback genérico. O backend até pode ter scores diferentes, mas se o `strategic_panel_summary` estiver vazio para ambos, o frontend mostra texto idêntico.

### P1-04: Timestamps semanticamente confusos (MÉDIO)

**Evidência:** O payload usa múltiplos campos timestamp com semântica sobreposta:
- `detected_at` / `found_at` / `first_seen_at` — mesmo pipeline em `ai_common.py:496-498`
- `updated_at` / `last_confirmed_at` — idênticos em `ai_common.py:499-500`
- `as_of` — definido como `coerce_iso(row.get("as_of"), fallback=market_time)` em `ai_common.py:433`
- `market_data_updated_at` — market_time
- No bundle: `quote.get("quote_time")`, `quote.get("updated_at")`, `insight.rsi_metadata.as_of`
- `hydration.updated_at` — diferente de todos

**Arquivos:** `app/ai/ai_common.py:424-433`, `app/api/routes_public_market_live.py:800-808`

**Causa raiz:** Três pipelines diferentes (quote, chart, on-demand, news) cada um com seu próprio timestamp semântico. O campo `updated_at` é sobrescrito múltiplas vezes durante o merge.

### P1-05: Master Score com contrato contraditório (MÉDIO)

**Evidência:** `_consensus` (ai_master_score.py:369-387) divide `aligned / len(OFFICIAL_AI_TOOLS)` (9 tools, incluindo risk). Mas `_weighted_direction_score` (linha 331-347) exclui risk do cálculo (linha 335). O ratio é subestimado em ~11%.

**Arquivo:** `app/ai/ai_master_score.py:377`

**Causa raiz:** `consensus.ratio = aligned / 9` mas risk nunca contribui para aligned. Deveria ser `aligned / 8`.

---

## 4. FALSOS POSITIVOS PROVÁVEIS

### FP-01: safe_float default=None propaga None

**Contestação:** Os chamadores em `ai_master_score.py` (linhas 158, 162, 177, 180) usam `if ... not in (None, "")` antes de chamar `safe_float(..., 0.0)`. A linha `flow_score = safe_float(flow_val, 0.0) if flow_val not in (None, "") else None` garante que `safe_float` nunca recebe `default=None`. O contrato `-> Any` é frágil, mas **na prática não propaga**.

### FP-02: Master Score aceita cobertura baixa

**Contestação:** `_context_available` (linha 324-328) exige `core >= 3 AND structure >= 1 AND institutional >= 1` — mínimo de 5 tools alinhadas. Score alto com 2 tools não gera direção BULLISH/BEARISH. O código está correto.

### FP-03: Sentimento sem NLP é P1

**Contestação:** O sentimento é intencionalmente por `impact` field (arquitetura documentada). Não é um bug — é uma limitação conhecida. A prioridade para NLP (FinBERT-pt) está no roadmap.

### FP-04: Testes enfraquecidos são blockers

**Contestação:** Testes como `assertEqual → assertIn` aceitam 2 estados em vez de 1. É perda de especificidade, mas não blocker. O teste `test_safe_float.py` com 12 casos é forte.

### FP-05: Premium gating OFF

**Contestação:** Intencional. O env var `STOCKNEWS_PREMIUM_GATING` (linha 1450) default OFF. A documentação diz "Flip the env var on once frontend handling ships". Não é bug — é feature incompleta.

---

## 5. COMPORTAMENTO ESPERADO

| Item | Por quê |
|------|---------|
| META34/M1TA34 mesmo preço | São BDRs da mesma empresa (Meta), mesmo underlying |
| CSNA3 10→6→2 notícias | Filtro legítimo: relevância + dedup + freshness |
| LLM fallback para template | `conclusion_or_template` captura Exception e retorna template |
| summary_template chain | Fallback proposital: llm_conclusion → strategic_panel_summary → genérico |
| AGUARDAR para JPM/LCID | Legítimo se dados insuficientes — problema é a **justificativa idêntica** |
| READY para "dados da última sessão" | `_payload_from_snapshot` retorna HISTORICAL para stale, não READY |

---

## 6. ANÁLISE POR ATIVO

### PETR4
- Pipeline completa: quote válido, chart, news 6, AI 9 displayable, strategic_panel presente
- Conclusão LLM deve ser rica (dados disponíveis)
- **Status:** OK

### PETR4.SA
- Compartilha cache com PETR4 via canonical_symbol → `canonical_symbol("PETR4.SA")` = "PETR4"
- **Status:** OK (intencional)

### CSNA3
- 2 notícias no bundle (redução legítima 10→6→2)
- AI displayable count = 0 (linha 135 da payload matrix M76)
- **Problema:** Sem dados de IA → strategic_panel vazio → recommendação AGUARDAR genérica
- **Causa:** CSNA3 não está no top-N do snapshot global

### AXIA3/ELET3/ELET6/AXIA6/AXIA7
- Preço R$42.21 = PETR4 (ERRADO — preço deveria ser de Eletrobras/Axia)
- Volume = 28,690,300 = PETR4
- source = `proxy_market` (NÃO cache_snapshot_bundle)
- News count = 6, AI displayable = 9 (mas são dados de PETR4)
- **Status:** CONTAMINAÇÃO CONFIRMADA — P0

### JPM
- Ticker US (NYSE) sem hydration dedicada
- Se cache snapshot global tem JPM → dados corretos
- Se não tem → fallback genérico + AGUARDAR
- **Problema:** Conclusão pode ser idêntica a LCID se ambos sem hydration

### LCID
- Não está no symbol registry (nem B3, nem BDR, nem US listado explicitamente)
- `canonical_symbol("LCID")` retorna "LCID" via fallback US_RE
- Sem hydration dedicada → mesmo fallback de JPM
- **Problema:** Mesmo que JPM

### META34/M1TA34
- Ambos R$68.50 (correto — mesmo underlying)
- source = cache_snapshot_bundle (correto)
- **Status:** OK

---

## 7. LIQUIDEZ

### Cadeia completa:

```
volume quote → volume/daily_average ratio (READY) → OK
intraday_rvol (READY se 5m multi-day samples existem)
ai_tools.liquidity rows → _ai_metric_component("liquidity") → exige:
  - freshness_status == "READY"
  - row.metrics.lower_liquidity != None
  - row.metrics.upper_liquidity != None  
  - price > 0
  - low < high
  - as_of truthy
  - source truthy
  - side determined (low > price → SELL_SIDE, high < price → BUY_SIDE)
```

### Por que falha:
- `lower_liquidity`/`upper_liquidity` **não são populados** pela IA de liquidez
- `ai_liquidity_map.py` ou `ai_liquidity_sweep.py` não escrevem estes campos nos metrics
- `_ai_metric_component` linha 491: `if component_status != "READY" or not geometry_ready: return INSUFFICIENT_DATA`
- Resultado: `"status": "INSUFFICIENT_DATA", "label": "Liquidez indisponível — dados insuficientes"`

### Arquivos prováveis:
- `app/ai/ai_liquidity_map.py` — não popula lower/upper_liquidity
- `app/ai/ai_liquidity_sweep.py` — não popula lower/upper_liquidity
- `app/api/routes_public_market_live.py:483-498` — validação rígida

### Correção mínima:
1. Verificar se as IAs de liquidez calculam e expõem lower/upper_liquidity
2. Se não calculam, ou adicionar o cálculo ou relaxar a validação em `_ai_metric_component`

---

## 8. SENTIMENTO

### Algoritmo (routes_public_market_live.py:773-788):
```python
bull_count = sum(1 for i in fresh_items if i.get("impact") == "bullish")
bear_count = sum(1 for i in fresh_items if i.get("impact") == "bearish")
```

### Status:
- **Não é bug** — é o contract documentado
- Impact é definido pelo news_service upstream (não revisto nesta missão)
- Se impact não é populado → ambos 0 → neutral → "Sentimento atual indisponível"
- Para CSNA3 com 2 notícias stale → sem fresh items → INSUFFICIENT_DATA

### Problema real (P2):
Quando `bull_count == 0 && bear_count == 0` (sem impact), retorna "Neutro" com status "READY" (linhas 780-784). O label "Neutro" é **enganoso**: o sentimento não foi avaliado como neutro — ele simplesmente não tem dados. Deveria retornar "INSUFFICIENT_DATA" quando impact está ausente.

**Arquivo:** `app/api/routes_public_market_live.py:780-784`
**Causa:** O branch `elif bull_count == 0 and bear_count == 0` mapeia para "neutral" com status READY, mesmo sem impacto real.

---

## 9. NOTÍCIAS E LOCALE

### Título em inglês na interface pt-BR

**Evidência:** `_public_news_language` (public_news_service.py:199-203) detecta pt-BR se encontra palavras portuguesas no título/summary. Se o artigo é "Market Reads: JPMorgan Results Improve As Oil Benefits From Stronger Pricing", o detector retorna "en-US".

**Arquivo:** `app/services/public_news_service.py:199-203`

**Causa:** O detector de língua é baseado em regex de palavras-chave portuguesas (line 201: "acao, acoes, noticia, mercado..."). Se o título não contém nenhuma, retorna en-US. O `_translate_english_news_text` (linhas 295-360) tenta traduzir, mas para `_ARTICLE_TEXT_FIELDS` (summary/card_summary) mantém o texto original (linha 308).

**Problema real:** Quando o artigo tem `_ARTICLE_TEXT_FIELDS` com texto em inglês, `_translate_english_news_text` retorna o original sem tradução. O título em si não é traduzido (apenas summary/card_summary são verificados, linhas 375-377). O título original em inglês passa direto.

---

## 10. TIMESTAMPS E FRESHNESS

### Mapa semântico atual:

| Campo | Pipeline | Semântica real | Problema |
|-------|----------|----------------|----------|
| `detected_at` | `ai_common.py:498` | `deal_timestamp(row)` = found_at ou market_timestamp | Confundido com "quando o sistema detectou" vs "quando o dado foi gerado" |
| `updated_at` | `ai_common.py:499` | `confirmed_time` = `last_confirmed_at` ou market_time (clampeado) | Mesmo valor que `last_confirmed_at` |
| `as_of` | `ai_common.py:501` | `coerce_iso(row.get("as_of"), fallback=market_time)` | Usado em múltiplos contexts com significado diferente |
| `market_data_updated_at` | `ai_common.py:481` | `market_time` = market_timestamp(row) | Pode ser de sessão anterior |
| `source_as_of` | `ai_tools_service.py:380` | `row.get("as_of")` original antes de overwrite | Só presente em AI tools, não no bundle |
| `evaluated_at` | `ai_tools_service.py:381` | Momento da avaliação | Preciso mas não exposto no bundle |
| `quote_time` | quote_cache | Timestamp da cotação | Pode ser de dias atrás em finais de semana |

### Recomendação de rótulos pt-BR:

| Nome técnico | Rótulo pt-BR | Quando aparece |
|-------------|--------------|----------------|
| `detected_at` | "Identificado em" | Momento que o sistema identificou o padrão |
| `updated_at` / `last_confirmed_at` | "Recalculado em" | Último ciclo do worker que recalculou |
| `as_of` | "Dados de mercado de" | Timestamp do candle/barra mais recente |
| `market_data_updated_at` | "Cotação de" | Timestamp da última cotação recebida |
| `evaluated_at` | "Análise gerada em" | Momento da análise atual |
| `freshness_status = READY` | "Dados desta sessão" | Intraday, sessão atual |
| `freshness_status = HISTORICAL` | "Dados da sessão anterior" | Sessão completa anterior |
| `freshness_status = STALE` | "Dados desatualizados" | Expirado além do tolerável |
| `freshness_status = INSUFFICIENT_DATA` | "Aguardando dados" | Ainda não hidratado |

### READY confundido com live:
- `READY` em AI tools = tem displayable count > 0, não significa dado ao vivo
- `READY` em data_status = dados disponíveis no cache
- `is_live` não existe no payload — o campo não é exposto
- Frontend interpreta READY como "dado atual" quando poderia ser "dado da última sessão"

---

## 11. PAINEL DAS IAS (AI TOOLS)

### O que o usuário vê:

O `build_public_ai_tools_payload` retorna 9 tools (flow, liquidity, trend, momentum, smart_money, risk, news, macro, regime). Cada tool tem múltiplas rows.

### Problemas observados:

1. **Repetitivo:** Se o snapshot global tem múltiplos findings para a mesma tool (ex: flow com 3 entradas), todas são exibidas. `_scoped_tools` (public_ai_tools_service.py:247-293) limita a `AI_ALERT_MAX_ROWS_PER_TOOL` (linha 288), mas se o limite é alto, repete.

2. **Confuso:** `historical_tools` (linhas 369-393) contém rows stale, mas `active_tools` contém as fresh. O payload expõe ambos (`tools` e `historical_tools`), mas o frontend pode não diferenciar.

3. **CSNA3 displayable=0:** (payload matrix M76 linha 135) — As IAs não encontraram dados para CSNA3 no snapshot global, resultando em painel vazio.

### Causa raiz:
- O snapshot global contém top-N tickers (PETR4, VALE3, ITUB4, etc.)
- Small-caps como CSNA3, HYPE3 não estão no top-N
- O on-demand hydration pode ou não estar completo quando o bundle é servido
- `displayable_count=0` → AI tools status `EMPTY`

---

## 12. GAUGE DE VOLUME

### RVOL atual:
- `volume_vs_daily_average` (line 755-763) = `volume / avg_volume` — ratio informacional
- `intraday_rvol` = `build_crypto_intraday_rvol_contract` (line 767)
- `rvol` = `intraday_rvol` (line 814: backwards-compatible key)

### Incompatibilidade com 4.42×:
Se o gauge mostra 4.42×, este é o `volume_vs_daily_average.ratio`. O problema é que:
- `volume_vs_daily_average.status` pode ser READY para o ratio bruto (4.42×)
- Mas `intraday_rvol.status` pode ser diferente (se faltam amostras 5m multi-day)
- O gauge do frontend pode estar lendo o campo errado ou usando o ratio bruto como se fosse RVOL comparável

### Arquivo provável:
- `apps/web/components/workspace-shell.tsx` — qual campo o gauge consome
- `app/api/routes_public_market_live.py:755-767` — dois campos diferentes

---

## 13. ORDEM EXATA DE IMPLEMENTAÇÃO PARA O CODEX

### Fase 1 — Correções P0 (sem alteração de contrato)
1. **Proxy B3** → Verificar `provider_symbol("AXIA3")` → o yfinance retorna PETR4. Possível correção: mapear AXIA3 para ELET3.SA no provider_symbol, ou investigar se o ticker B3 correto é ELET3.SA ainda.
2. **Insight gating** → Adicionar `is_premium: bool = Depends(resolve_premium_entitlement)` ao endpoint `public_market_insight` e aplicar `_gate_bundle_for_entitlement` no response.

### Fase 2 — Correções P1 (contrato interno)
3. **Liquidez indisponível** → Verificar se `ai_liquidity_map.py`/`ai_liquidity_sweep.py` populam `lower_liquidity`/`upper_liquidity`. Se não, corrigir a IA ou relaxar `_ai_metric_component`.
4. **Consensus ratio** → Mudar `len(OFFICIAL_AI_TOOLS)` para `len(OFFICIAL_AI_TOOLS) - 1` (excluir risk) em `ai_master_score.py:377`.
5. **Sentimento neutro enganoso** → Quando `bull_count == 0 && bear_count == 0`, retornar INSUFFICIENT_DATA em vez de READY (linha 780-784).

### Fase 3 — Timestamps e Freshness
6. **Rótulos pt-BR** → Implementar os rótulos recomendados na seção 10.
7. **Deduplicar timestamps** → Remover redundância entre `updated_at`/`last_confirmed_at` e `detected_at`/`found_at`/`first_seen_at`.

### Fase 4 — Conclusões e UI
8. **JPM/LCID justificativas** → Quando `strategic_panel_summary` está vazio, gerar fallback contextualizado por ativo (ex: "JPM: dados do setor financeiro ainda em análise" vs "LCID: dados do setor automotive ainda em análise").
9. **Gauge de volume** → Verificar qual campo o gauge consome e alinhar com o contrato correto (intraday_rvol vs volume_vs_daily_average).

### Fase 5 — Testes
10. **Restaurar especificidade** → Reverter `assertIn({"INSUFFICIENT_DATA", "READY"})` para `assertEqual("READY")` ou similar com validação de contrato mais estrita.

---

## 14. ARQUIVOS QUE PROVAVELMENTE PRECISARÃO DE ALTERAÇÃO

| Arquivo | Linhas | O que muda |
|---------|--------|------------|
| `app/api/routes_public_market_live.py` | 1275, 1453-1487 | Adicionar gating ao insight; corrigir sentimento neutro |
| `app/ai/ai_master_score.py` | 377 | `len(OFFICIAL_AI_TOOLS) - 1` no ratio |
| `app/services/symbol_registry.py` | 114, 434-436 | Investigar AXIA3 provider_symbol → talvez retornar ELET3.SA |
| `app/ai/ai_liquidity_map.py` | (TODO) | Popular lower/upper_liquidity |
| `app/ai/ai_liquidity_sweep.py` | (TODO) | Popular lower/upper_liquidity |
| `app/api/routes_public_market_live.py` | 773-788 | Inverter sentimento: sem impact → INSUFFICIENT_DATA |
| `app/api/routes_public_market_live.py` | 800-827 | Limpar timestamps, adicionar rótulos |
| `app/ai/ai_common.py` | 496-503 | Deduplicar timestamps |
| `app/services/public_ai_tools_service.py` | 181-219 | Revisar freshiness buckets |
| `apps/web/components/workspace-shell.tsx` | 3800, 10662 | Verificar fallback chain |
| `tests/test_public_market_routes.py` | (TODO) | Restaurar contratos |
| `tests/test_mission30_complement_news_br.py` | (TODO) | Reverter asserção |

---

## 15. TESTES NECESSÁRIOS

### Testes de regressão obrigatórios após correções:

| Teste | O que valida |
|-------|-------------|
| `test_public_market_insight_gates_premium` | Insight endpoint bloqueia dados premium para anônimos |
| `test_axias3_price_not_petr4` | AXIA3, ELET3, ELET6 não retornam preço de PETR4 |
| `test_liquidity_geometry_fallback` | Liquidez retorna INSUFFICIENT_DATA com reason claro quando geometry falta |
| `test_consensus_ratio_excludes_risk` | Consensus ratio usa 8 tools, não 9 |
| `test_sentiment_no_impact_returns_insufficient` | Sem impact, sentimento retorna INSUFFICIENT_DATA |
| `test_jpm_lcid_different_justification` | JPM e LCID têm fallback texts diferentes |
| `test_conclusion_key_includes_ticker` | Cache da conclusão LLM inclui ticker |
| `test_updated_at_different_from_detected_at` | Timestamps têm semântica distinta |

### Testes de contrato que devem ser restaurados:

| Teste | Asserção atual | Asserção correta |
|-------|----------------|------------------|
| `test_bundle_http_publishes_top_level_metrics` | `assertIn({"INSUFFICIENT_DATA", "READY"})` | Contrato específico por ativo |
| `test_public_ai_tools_do_not_derive_parallel_tools` | Mocka get_symbol_analysis | Não mockar — testar integração real |
| `test_public_insight_exposes_strategic_panel_contract` | Mocka resolve_symbol_context | Não mockar |

---

## 16. MUDANÇAS QUE O CODEX NÃO DEVE FAZER

1. **NÃO remover o fallback `safe_float(..., default=None)`** — está protegido pelos guards. Remover quebraria a lógica de `flow_score = None` quando flow_val é None.
2. **NÃO ativar `STOCKNEWS_PREMIUM_GATING` por default** — frontend não tem handling para "Disponível no Pro". Ativar sem frontend quebra UX.
3. **NÃO unificar as 4 implementações de safe_float** — risco de regressão alto. Criar tech debt issue para refatoração futura.
4. **NÃO remover "market reads" do frontend** — a asserção invertida em `test_mission30_complement_news_br` pode ser intencional (aceitar texto do editor original).
5. **NÃO modificar `_symbol_aliases` em `symbol_registry.py:114`** — o mapeamento AXIA3 → ELET3 é correto. O problema é no provedor, não no alias.
6. **NÃO adicionar NLP (FinBERT-pt)** — escopo grande demais para esta missão. Criar issue para Q3.
7. **NÃO refatorar o cache de symbol_hydration** — cache em memória por processo com persistência em arquivo é operacionalmente adequado.
8. **NÃO remover o `"risk"` de `OFFICIAL_AI_TOOLS`** — risk é usado para exclusão e contagem de tools totais. Remover quebraria contratos frontend.
9. **NÃO mexer na lógica de `_context_available`** — a exigência de 5 tools alinhadas é intencional e correta.

---

## 17. CRITÉRIOS FINAIS DE GO/NO-GO

### GO se:
- [x] P0-01 (aliases B3) corrigido ou com workaround documentado
- [x] P0-02 (insight gating) adicionado
- [x] P1-02 (liquidez) diagnosticado e com correção implementada
- [x] Nenhuma das "mudanças que não deve fazer" foi executada
- [x] Testes específicos dos fixes passam (seção 15)
- [x] `docs/mission_77a_opus_pre_codex_review.md` é o único arquivo criado
- [x] Nenhum `git commit` ou `git push` executado

### NO-GO se:
- [ ] Qualquer um dos P0 permanece sem correção ou documentação
- [ ] Testes de contrato foram enfraquecidos adicionalmente
- [ ] O Codex tentou refatorar safe_float ou _context_available
- [ ] O Codex ativou premium gating sem frontend correspondente
- [ ] O Codex modificou a lógica de aliases B3 em vez de investigar o provedor
- [ ] Foram feitas alterações em mais de 12 arquivos (sinal de escopo excessivo)

---

## CONFIRMAÇÃO

**Único arquivo criado nesta missão:**
`/home/dcima/stocknewsbr-backend/docs/mission_77a_opus_pre_codex_review.md`

Nenhum código, teste, configuração, dependência ou working tree foi alterado.

Nenhum commit ou push foi executado.

Nenhuma correção foi implementada.
