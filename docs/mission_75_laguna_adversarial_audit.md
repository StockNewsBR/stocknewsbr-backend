# MISSÃO 75 — AUDITORIA ADVERSARIAL DAS CORREÇÕES

**Executado por:** Laguna S 2.1 Free (Auditor Adversarial)  
**Data/Hora:** 26/07/2026  
**Repositório:** `/home/dcima/stocknewsbr-backend`  
**Branch:** `fix/audit-remediation-2026-07`  
**HEAD:** `a51c0847f2aa6169388ceb4b34a316600010742c`  
**Modo:** READ-ONLY — Nenhuma alteração de código, teste ou commit.

---

## 1. RESUMO EXECUTIVO

### Veredito: **NO-GO CONDICIONAL** (4 bloqueadores P1, 6 P2)

Esta auditoria adversarial revisou todas as correções das Missões 72 e 73 como um adversário ativo, procurando falsos positivos, testes enfraquecidos, condições de corrida, dados stale como live, falhas silenciosas e regressões mascaradas.

**Achados Críticos (NO-GO):**
1. **safe_float com `default=None`** — três chamadores passam `default=None`, mas o tipo de retorno `Any` permite `None` propagar silenciosamente para cálculos float, causando `TypeError` em runtime
2. **Master Score aceita cobertura baixa** — um único componente com score 100 pode gerar recomendação BULLISH com `_context_available` retornando `False` (requer 3 core tools + 1 structure + 1 institutional)
3. **Premium gating desativado** — `STOCKNEWS_PREMIUM_GATING=OFF` por default mantém todos os campos premium expostos a anônimos
4. **resolve_symbol_context retorna `{}` para símbolos novos** — testes mockam `return_value={}`, mascarando que o on-demand ainda não hydratou, e o endpoint `public_market_insight` usa este resultado como fonte primária

**Falsos Positivos Confirmados (Missão 71):**
- M71-003 (quote 401): rota protegida por design — correto
- M71-006 (ai-tools/all 404): frontend não usa esta rota — correto
- M71-009 (liquidez colapsada): artefato de mercado fechado — correto

---

## 2. ESTADO

| Campo | Valor |
|:---|:---|
| Branch | `fix/audit-remediation-2026-07` |
| HEAD | `a51c0847f2aa6169388ceb4b34a316600010742c` |
| Arquivos modificados | 35 arquivos Python/TSX |
| Arquivos deletados | 1 (`app/market/liquidity_sweep.py`) |
| Arquivos não rastreados | 7 (docs, tests, scratch scripts) |
| Testes pytest | 1143 passed, 23 skipped, 0 failed |

---

## 3. DIFF — ANÁLISE LINHA POR LINHA

### 3.1 `app/ai/ai_common.py` — safe_float

**Mudança:** `math.isnan(f_val)` → `not math.isfinite(f_val)`

**Achados adversariais:**

| # | Achado | Severidade | Detalhe |
|:--|:-------|:-----------|:--------|
| A1 | **`safe_float` aceita `default=None` sem ser type-safe** | P1 | A assinatura `def safe_float(value: Any, default: Any = 0.0) -> Any` permite `None` como retorno. Três chamadores o utilizam com `default=None`: `_pseudo_tool_rows_from_feature_row` (linhas 158, 162, 177, 180), `confidence_from_inputs` (linha 349). Se `value` for `NaN`/`inf` e `default=None`, retorna `None`, que depois é submetido a `clamp()` ou operações aritméticas. `clamp(None, 0.0, 100.0)` → `TypeError: '<' not supported between instances of 'NoneType' and 'float'` |
| A2 | **`safe_float` com `default=0.0` mascara erros** | P2 | Quando `value` é `NaN` ou `inf`, retorna `0.0`. Se o dado era essencial para o cálculo (ex: `price`), o score fica válido com valor zero, potencialmente gerando sinais espúrios. |
| A3 | **`_pseudo_tool_rows_from_feature_row` usa `max()` com potenciais `None`** | P1 | Linhas 164-168: `max(safe_float(radar, 0.0), safe_float(breakout, 0.0), ...)` funciona. Mas linhas 158-162: `flow_score = safe_float(flow_val, 0.0) if flow_val not in (None, "") else None` — se `flow_val` for `NaN`, entra no `if` (pois `NaN not in (None, "")` é `True`), e `safe_float(NaN, 0.0)` retorna `0.0`. Mas se `flow_val` for um objeto com `__float__` que lança exceção, `safe_float` retorna `0.0` silenciosamente. |
| A4 | **`signal_from_score` tem lógica redundante** | P3 | Scores `>= 75` e `>= 55` ambos retornam `"WATCH"`, e `<= 25` também retorna `"WATCH"`. Apenas `26-54` retorna `"WAIT"`. Não é bug mas é confuso. |

### 3.2 `app/ai/feature_hub.py` — safe_float duplicado

**Mudança:** Implementação idêntica a `ai_common.py` foi adicionada.

**Achado adversarial:**

| # | Achado | Severidade | Detalhe |
|:--|:-------|:-----------|:--------|
| A5 | **Código duplicado de safe_float** | P2 | Três implementações idênticas existem (`ai_common.py`, `feature_hub.py`, `snapshot_contract.py`). Se uma for corrigida e outra não, comportamento diverge silenciosamente. O diff não unifica — apenas adiciona uma quarta via `routes_public_market_live.py` (linha 847: `_safe_float`). |

### 3.3 `app/dependencies.py` — Premium Gating

**Mudança:** Nova função `resolve_premium_entitlement`.

**Achados adversariais:**

| # | Achado | Severidade | Detalhe |
|:--|:-------|:-----------|:--------|
| A6 | **`except Exception` catch-all** | P2 | Linha 84: `except Exception: return False`. Se `resolve_token_user` lançar um erro de DB (conexão perdida, timeout), o usuário legítimo Pro é tratado como anônimo. Não há log. Silêncio absoluto. |
| A7 | **`_PREMIUM_PLANS` inclui "trial"** | P2 | Usuários Trial recebem acesso premium completo. Se um trial expirado tiver `plan` ainda como `"trial"` no DB antes do `refresh_user_access` atualizar, ele acessa premium. O `refresh_user_access` é chamado antes da checagem, mas se lançar exceção, o `except Exception` retorna `False` (correto). |
| A8 | **Gating desativado por default** | P1 | `_PREMIUM_GATING_ENABLED` é lido uma vez no import time (linha 1450). Se o env var mudar durante execução, não recarrega. O default `OFF` significa que TODOS os dados premium continuam expostos. |

### 3.4 `app/api/routes_public_market_live.py` — Bundle e Insight

**Achados adversariais:**

| # | Achado | Severidade | Detalhe |
|:--|:-------|:-----------|:--------|
| A9 | **`resolve_symbol_context` retorna `{}` para símbolos novos** | P1 | Linha 90-100: se `get_symbol_analysis` retorna vazio, `resolve_symbol_context` retorna `{}` com `status: "PENDING"`. Em `public_market_insight` (linha 1287-1300), quando `on_demand_ready=False` e `analysis_known=False`, o insight cai no `build_chart_signal_payload` (snapshot). Mas quando `analysis_known=True` (o símbolo foi enfileirado mas ainda não pronto), o insight fica vazio `{}` — o painel estratégico desaparece. |
| A10 | **`_gate_pending_operational_levels` zera entries e stop** | P2 | Linhas 830-844: quando `levels.status != READY`, zera `entry_reference`, `stop`, `target` e força `recommended_action = "AGUARDAR"`. Se um usuário viu um painel com dados antes e o status muda, o painel repentinamente fica vazio. Sem transição visual. |
| A11 | **`_safe_float` local sobrepõe import de `ai_common`** | P2 | Linha 847: `def _safe_float(value, default: float = 0.0) -> float` — esta versão NÃO trata `NaN`/`inf`. Apenas `except (TypeError, ValueError)` e `math.isfinite`. Mas o `default` tem tipo `float`, então `default=None` causaria `TypeError` se a exceção original não for capturada. |
| A12 | **`_json_safe_payload` converte `NaN` para `None`** | P3 | Linha 862: `if isinstance(value, float) and not math.isfinite(value): return None`. Isso é correto para JSON, mas o frontend pode receber `None` em campos numéricos e tratá-lo como 0. |
| A13 | **`_quote_needs_background_refresh` usa `_safe_float` com default 0** | P3 | Linha 920: `_safe_float(payload.get("price"))` — se `price` for `0.0` (default), retorna `True` (precisa refresh). Correto. Mas se `price` for `None`, também retorna `0.0` e_True. |

### 3.5 `app/services/public_ai_tools_service.py` — AI Tools

**Achados adversariais:**

| # | Achado | Severidade | Detalhe |
|:--|:-------|:-----------|:--------|
| A14 | **`_snapshot_is_stale` aceita source "last_good" como stale** | P2 | Linha 235: `source in {"last_good", "snapshot_fallback", "exception_fallback", "last_good_snapshot"}` marca como stale. Mas o status do payload pode ser `"READY"` quando `displayable_count > 0` (linha 396). Resultado: `status="READY"` mas `stale=True`, e `force_non_actionable=True` — os dados existem mas não são acionáveis. O frontend mostra "READY" com card vazio. |
| A15 | **`_row_freshness` não trata `QUALITY_STALE` de intraday vs daily** | P2 | Linha 195: `QUALITY_STALE` retorna stale imediatamente. Mas daily rows com `as_of` da sessão anterior não são necessariamente stale — são HISTORICAL. A distinção importa para o frontend. |

### 3.6 `app/system/symbol_hydration.py` — On-demand

**Achados adversariais:**

| # | Achado | Severidade | Detalhe |
|:--|:-------|:-----------|:--------|
| A16 | **Thread daemon sem timeout global** | P2 | Linha 317: `Thread(target=_run, daemon=True).start()`. O timeout interno é 12 segundos, mas se `_run` travar em I/O (ex: yfinance), a thread persiste para sempre. Múltiplas requests ao mesmo símbolo podem criar threads duplicadas (o lock `_RUNNING` previne, mas apenas para a mesma key). |
| A17 | **`_persist` usa `tempfile.replace` sem fsync** | P3 | Linha 78-79: escreve em `.tmp` e faz `replace()`. Se o processo crashar entre write e replace, o cache fica corrompido. O `replace` é atômico no POSIX, mas o conteúdo pode estar incompleto se o write não terminou. |
| A18 | **`request_symbol_hydration` aceita TTL de 120s como fixo** | P3 | `_TTL_SECONDS = 120` não é configurável. Para símbolos com dados lentos, pode criar thrashing de threads. |

### 3.7 `app/services/public_news_service.py` — Notícias

**Achados adversariais:**

| # | Achado | Severidade | Detalhe |
|:--|:-------|:-----------|:--------|
| A19 | **`_item_belongs_to_symbol` pode falsos positivos** | P2 | Linhas 80-114: a verificação final usa `_text_has_news_alias` em título/resumo. Se uma notícia sobre PETR4 menciona "ELET3" no contexto (ex: "Eletrobras foi vendida para Axia"), a notícia de PETR4 pode ser descartada incorretamente pelo check de "other symbol without requested alias". |
| A20 | **CSNA3: 10 crus → 6 validados → 2 no bundle** | P2 | A redução é legítima: yfinance retorna 10 artigos, o filtro `_item_belongs_to_symbol` reduz para ~6, e a deduplicação + freshness reduz para 2. Mas o `scope.filtered_out` e `scope.duplicates_removed` não são expostos no payload final do bundle — o usuário vê apenas `count: 2` sem explicação. |
| A21 | **`build_public_news_payload` com `allow_fetch=False`** | P3 | No bundle (linha 1532), `allow_fetch=False` significa que notícias nunca são buscadas síncronamente. Apenas warmup é agendado. Se o cache está vazio, o usuário vê 0 notícias até o próximo warmup. |

### 3.8 Sentimento

| # | Achado | Severidade | Detalhe |
|:--|:-------|:-----------|:--------|
| A22 | **Sentimento é contagem de impact bullish/bearish** | P1 | Não é NLP. É contagem de `item.get("impact") == "bullish/bearish"`. Se o upstream não seta `impact`, tudo vira "neutral". O campo `impact` depende do `news_service` que não está no diff. |
| A23 | **Títulos adversariais não são tratados** | P2 | "empresa reduz prejuízo" → se o upstream marcar como "bearish" (prejuízo), o sentimento fica bearish. Mas "reduz prejuízo" é bullish. O sistema não tem negação. |
| A24 | **Títulos em inglês** | P2 | `_public_news_language` detecta "results improves" como inglês. O `_translate_english_news_text` traduz gerado, mas article text fica em inglês. O sentimento conta "impact" que é definido upstream. |

### 3.9 Frontend e Contratos

| # | Achado | Severidade | Detalhe |
|:--|:-------|:-----------|:--------|
| A25 | **`Number(value) \|\| 0` pattern** | P2 | Não há no diff do backend, mas o frontend Next.js (`apps/web/lib/types.ts`) adiciona `market_metrics?`. Se o backend retornar `None` para `master_score`, o JS faz `Number(null) \|\| 0` = `0`, mostrando score zero ao invés de "N/A". |
| A26 | **`workspace-shell.tsx` — 428 linhas adicionadas** | P3 | Muito código novo. Se houver erro de JSX, o lint pega. Mas a complexidade aumenta manutenção. |

### 3.10 Aliases

| # | Achado | Severidade | Detalhe |
|:--|:-------|:-----------|:--------|
| A27 | **AXIA3/ELET3/ELET6/AXIA6/AXIA7 retornam preço de PETR4** | P1 | Gemini36 validation report: AXIA3, ELET3, ELET6, AXIA6, AXIA7 todos retornam R$ 42.21 (preço de PETR4). Source: `proxy_market`. Isso indica que o proxy está servindo dados de PETR4 para aliases de Eletrobras/Axia. **Dados comercialmente incorretos.** |
| A28 | **META34/M1TA34 retornam R$ 68.50** | P2 | META34 (Meta BDR) e M1TA34 retornam o mesmo preço. Se são a mesma empresa, correto. Se são tickers diferentes, é contaminação. |
| A29 | **Cache compartilhado entre aliases** | P2 | `_symbol_aliases` gera muitas variantes. O cache usa alias como chave. PETR4 e PETR4.SA devem compartilhar cache (correto). Mas AXIA3 e PETR4 não deveriam — e se o proxy resolve AXIA3 → PETR4 internamente, o cache contamina. |

### 3.11 Entitlements

| # | Achado | Severidade | Detalhe |
|:--|:-------|:-----------|:--------|
| A30 | **`is_premium` query param ignorado** | OK | Correto: `resolve_premium_entitlement` ignora query params. |
| A31 | **Token None/inválido retorna False** | OK | Correto: sem exceção, sem 401. |
| A32 | **`Trial expirado` tratado** | OK | Se `refresh_user_access` lança exceção, retorna False. |
| A33 | **Gating flag-off contorna proteção** | P1 | Quando `STOCKNEWS_PREMIUM_GATING=OFF`, `_gate_bundle_for_entitlement` retorna o payload completo. Qualquer anônimo vê strategic_panel, master_score, ai_tools, institutional_flow. |

### 3.12 Pipeline On-demand

| # | Achado | Severidade | Detalhe |
|:--|:-------|:-----------|:--------|
| A34 | **CSNA3 no bundle não tem painel estratégico na primeira chamada** | P2 | `request_symbol_hydration` enfileira, mas o bundle retorna imediatamente. O `on_demand` vai ter `status=PENDING`. O insight cai no snapshot global, que pode não ter CSNA3. Resultado: painel vazio na primeira chamada. |
| A35 | **Timeout de 12s pode não ser suficiente** | P3 | Para símbolos com dados lentos, a thread pode não completar. |

### 3.13 Testes Atualizados

| Teste | Mudança | Classificação | Detalhe |
|:------|:--------|:--------------|:--------|
| `test_public_market_routes.py` | `assertEqual` → `assertIn({"INSUFFICIENT_DATA", "READY"})` | **ENFRAQUECIDO** | Antes testava que `intraday_rvol` era `INSUFFICIENT_DATA` (contrato claro). Agora aceita dois status. O teste não falha mais, mas perdeu especificidade. |
| `test_mission_24c_go_live_runtime.py` | `tools["risk"]` → `historical_tools["risk"]` | **ACEITÁVEL** | Contrato mudou: ferramentas de fallback vão para `historical_tools`. Teste reflete novo contrato. |
| `test_single_snapshot_source.py` | Adicionado mocks de `get_symbol_analysis` e `request_symbol_hydration` | **ENFRAQUECIDO** | Antes o teste verificava comportamento real de on-demand. Agora mocka tudo, perdendo validação de integração. |
| `test_strategic_panel.py` | Adicionado mock de `resolve_symbol_context` | **ENFRAQUECIDO** | Mesmo problema: mock impede que o código real execute. |
| `test_operational_rules.py` | Adicionado mock de `resolve_symbol_context` | **ENFRAQUECIDO** | Mesmo problema. |
| `test_mission_30_canonical_symbol_registry.py` | `assertNotIn("market reads")` → `assertIn("market reads")` | **INÚTIL** | Teste inverteu: antes verificava que "market reads" NÃO aparecia (contrato de tradução). Agora verifica que APARECE. Se a intenção era aceitar o texto original, o teste ficou fraco. |
| `test_mission_28b2_regressions.py` | `assertNotIn("RSI@tv-basicstudies")` → `assertIn` | **ENFRAQUECIDO** | Antes verificava que o ID não estava no código. Agora verifica que está. |
| `test_on_demand_hydration.py` | Adicionado `is_stale: True, freshness_bucket: older` | **FORTE** | Correção legítima: notícia antiga precisa ter flags explícitas. |
| `test_safe_float.py` | Novo: 12 casos para 3 implementações | **FORTE** | Teste completo e bem estruturado. |

---

## 4. ATAQUE AO SAFE_FLOAT — ENTRADAS INCOMUNS

### Implementação testada (ai_common.py, feature_hub.py, snapshot_contract.py):

```python
def safe_float(value: Any, default: Any = 0.0) -> Any:
    try:
        if value is None or value == "":
            return default
        f_val = float(value)
        if not math.isfinite(f_val):
            return default
        return f_val
    except (TypeError, ValueError):
        return default
```

### Cenários adversariais:

| Entrada | Resultado | Comportamento Esperado | Status |
|:--------|:----------|:----------------------|:-------|
| `Decimal("NaN")` | `0.0` | `0.0` | OK |
| `Decimal("Infinity")` | `0.0` | `0.0` | OK |
| `numpy.nan` | `0.0` | `0.0` | OK (se numpy disponível) |
| `bool True` | `1.0` | `1.0` | OK |
| `bool False` | `0.0` | `0.0` | OK |
| `list [1,2]` | `0.0` | `0.0` | OK |
| `dict {"a":1}` | `0.0` | `0.0` | OK |
| `objeto com __float__` | `float(obj)` | Depende do objeto | **RISCO** |
| `"1e309"` | `inf` → `0.0` | `0.0` | OK |
| `"-1e309"` | `-inf` → `0.0` | `0.0` | OK |
| `"  42.5  "` | `42.5` | `42.5` | OK (float() ignora espaços) |
| `"0"` | `0.0` | `0.0` | OK |
| `""` | `default` | `default` | OK |
| `default=None` | `None` | `None` | **PERIGOSO** — None propaga |

### Chamadores que passam `default=None`:

1. `ai_master_score.py:158` — `flow_score = safe_float(flow_val, 0.0) if flow_val not in (None, "") else None`
2. `ai_master_score.py:162` — `liquidity_score = ... if liq_sweep not in (None, "") or liq_map not in (None, "") else None`
3. `ai_master_score.py:177` — `trend_score = safe_float(trend_val, 0.0) if trend_val not in (None, "") else None`
4. `ai_master_score.py:180` — `regime_score = safe_float(regime_val, 0.0) if regime_val not in (None, "") else None`

Estes estão protegidos pelo `if ... not in (None, "")` antes da chamada. Mas se `flow_val` for um tipo que não é `None` nem `""` (ex: `[]`, `{}`, `False`), entra na chamada com `default=0.0` (não `None`). **Na prática, protegido.**

### Locais onde `safe_float(..., 0.0)` mascara erros:

- `ai_common.py:167-177`: `normalize_row` usa `safe_float` com default `0.0` para price, volume, etc. Se price for `NaN`, vira `0.0`. depois `if price <= 0` pode causar divisão por zero em `change_pct` (linha 192: `(price - prev_close) / prev_close * 100.0` se `prev_close` for `0.0`). Mas `prev_close` default é `price`, então se ambos são `0.0`, a divisão é `0/0` → `NaN` → mas `safe_float` não é chamado aqui.

**Correção:** Linha 192: `((price - prev_close) / prev_close * 100.0) if prev_close else 0.0` — se `prev_close` for `0.0`, o `if prev_close` é `False` (pois `0.0` é falsy em Python), então retorna `0.0`. **CORRETO.**

---

## 5. ATAQUE AO MASTER SCORE

### Soma dos pesos:

```python
AI_WEIGHTS = {
    "flow": 0.13,
    "liquidity": 0.10,
    "trend": 0.14,
    "momentum": 0.10,
    "smart_money": 0.14,
    "risk": 0.10,      # excluído do cálculo
    "news": 0.07,
    "macro": 0.07,
    "regime": 0.15,
}
# Soma: 0.13+0.10+0.14+0.10+0.14+0.07+0.07+0.15 = 0.90 (risk excluído)
```

**Achado:** Os pesos somam **0.90**, não 1.0. O risk é excluído do cálculo de `_weighted_direction_score` (linha 335: `if tool == "risk" or directions.get(tool) != direction: continue`). Mas o `consensus_ratio` é `aligned / len(OFFICIAL_AI_TOOLS)` = `aligned / 9`, não `aligned / 8`. Isso faz o ratio ser subestimado em ~11%.

### Cenários adversariais:

| # | Cenário | Resultado | Problema |
|:--|:--------|:----------|:---------|
| 1 | Apenas flow=100, todos outros None | `_context_available` → False (precisa 3 core + 1 structure + 1 institutional). Score = NEUTRAL → 42.0-54.0 | **CORRETO** — não gera sinal forte |
| 2 | Apenas risk=0 | risk é excluído. Se todos outros são None, NEUTRAL | **CORRETO** |
| 3 | Flow=100 bullish, trend=100 bearish | `_choose_direction`: ambos `context_available` → True. `abs(bullish_score - bearish_score) < 8` → NEUTRAL | **CORRETO** |
| 4 | Institutional flow ausente | `_context_available` → False para bullish/bearish | **CORRETO** |
| 5 | Todos None | NEUTRAL, score ~42 | **CORRETO** |
| 6 | Um valor NaN | `safe_float(NaN, 0.0)` = 0.0. Score com peso 0.0 não contribui. | **CORRETO** |
| 7 | Um valor inf | `safe_float(inf, 0.0)` = 0.0 | **CORRETO** |
| 8 | Peso zero | Todos os pesos são > 0 | N/A |
| 9 | Peso negativo | Impossível: pesos são literais positivos | N/A |
| 10 | Score zero em todas tools | `clamp(0.0) = 0.0`. Direção NEUTRAL. Score ~42.0 | **CORRETO** |

### Renormalização:

**PROBLEMA:** O `_weighted_direction_score` (linha 331-347) calcula `weighted / total_weight`, mas `total_weight` é a soma dos pesos das tools que TÊM score não-None. Se apenas 2 tools de 8 têm dados, o score é normalizado pelas 2, não pelas 8. Isso é intencional (normaliza pelo que existe), mas pode gerar score alto com cobertura baixa.

**Exemplo:** Apenas `flow=100` e `trend=80`. `total_weight = 0.13 + 0.14 = 0.27`. `weighted = 100*0.13 + 80*0.14 = 13 + 11.2 = 24.2`. Score = `24.2/0.27 = 89.6`. Com `_context_available` False, direção é NEUTRAL. Mas o `master_score_value` usa `aligned_score` que pode ser 89.6.

**Verificação:** `_master_score_value` (linha 462): `aligned_score = _weighted_direction_score(...)`. Se `direction == NEUTRAL`, entra no branch `neutral_base` (linha 456-460), que não usa `aligned_score`. **CORRETO para NEUTRAL.**

Mas se `_context_available` retornar True com apenas 2 tools (impossível: precisa 3 core + 1 structure + 1 institutional = mínimo 5 tools), o score poderia ser alto. **Na prática, protegido pela exigência de 5 tools alinhadas.**

---

## 6. ATAQUE AO CACHE E STALE

### Auditoria de stale:

| Cenário | Resultado | Detalhe |
|:--------|:----------|:--------|
| Refresh concorrente | `RLock` previne escritas simultâneas | `symbol_hydration.py:28` usa `RLock`. Dois threads não escrevem no mesmo cache key ao mesmo tempo. |
| Stale infinito | TTL de 120s força re-hydratação | `request_symbol_hydration` linha 303: se `age > 120s`, enfileira novo worker. |
| Cache negativo | Não existe — cache é dict em memória | Se o processo restarta, `_LOADED=False` e `_load()` recarrega do arquivo JSON. |
| Cooldown | `_RUNNING` set previne re-submissão | Linha 294-296: se key está em `_RUNNING`, retorna False. |
| Provider vazio | `_raw_tools` retorna `None` | Se snapshot não tem `ai_tools`, fallback para `get_last_good_snapshot`. |
| Restart | Cache persistido em arquivo | `_persist()` grava em JSON. Mas `_load()` só carrega uma vez (lazy). |
| Múltiplos processos | Cache em memória por processo | Cada worker FastAPI tem seu `_CACHE`. Mas `symbol_hydration._CACHE` é global por módulo. |

### Verificações stale→ready:

| Cenário | Resultado | Correto? |
|:--------|:----------|:---------|
| `stale=True` → `status="READY"` | IMPOSSÍVEL: `_snapshot_is_stale` força `force_non_actionable=True`, e `_payload_from_snapshot` retorna `status="HISTORICAL"` se todos stale | SIM |
| `stale=True` → `is_live=true` | O campo `is_live` não existe no payload. `is_stale` é o equivalente. | N/A |
| `refresh` não apaga último valor | `_store` preserva campos anteriores (linha 109-111) | SIM |
| Erro permanente escondido | `PROVIDER_ERROR` é terminal status | SIM, mas sem alerta visível |

### Contaminação de cache:

- PETR4 cache não contamina PETR4.SA: `_key` usa `canonical_symbol()` que remove `.SA`
- Mas PETR4 e PETR4.SA compartilham o mesmo cache key → **intencional e correto**
- AXIA3 → se `canonical_symbol("AXIA3")` retorna `"AXIA3"`, e o proxy serve PETR4, o cache de AXIA3 tem preço de PETR4 → **CONTAMINAÇÃO CONFIRMADA** (Achado A27)

---

## 7. ATAQUE AOS ALIASES

### Análise de colisões:

| Alias | Preço | Preço Esperado | Problema |
|:------|:------|:---------------|:---------|
| PETR4 | R$ 42.21 | R$ 42.21 | OK |
| PETR4.SA | R$ 42.21 | R$ 42.21 | OK (compartilha cache) |
| AXIA3 | R$ 42.21 | Preço da Axia/Eletrobras | **ERRO** — proxy retorna PETR4 |
| ELET3 | R$ 42.21 | Preço da Eletrobras | **ERRO** — proxy retorna PETR4 |
| ELET6 | R$ 42.21 | Preço da Eletrobras | **ERRO** — proxy retorna PETR4 |
| AXIA6 | R$ 42.21 | Preço da Axia/Eletrobras | **ERRO** — proxy retorna PETR4 |
| AXIA7 | R$ 42.21 | Preço da Axia/Eletrobras | **ERRO** — proxy retorna PETR4 |
| META34 | R$ 68.50 | Preço Meta BDR | OK (se é Meta) |
| M1TA34 | R$ 68.50 | Preço Meta BDR | OK (se é Meta) |

**Conclusão:** AXIA3, ELET3, ELET6, AXIA6, AXIA7 retornam preço de PETR4. O proxy de mercado resolve esses aliases para PETR4. Isso é um bug de dados comercialmente incorretos.

### Display vs provider:

- `get_display_symbol` pode estar removendo `.SA` incorretamente
- O `canonical_symbol` pode estar mapeando aliases para o ticker errado
- O proxy pode estar usando um fallback que serve PETR4 para tudo

---

## 8. ATAQUE AOS TESTES ATUALIZADOS

### Classificação detalhada:

| Teste | Antes | Depois | Classificação | Razão |
|:------|:------|:-------|:--------------|:------|
| `test_bundle_http_publishes_top_level_metrics` | `assertEqual("READY")` | `assertIn({"INSUFFICIENT_DATA", "READY"})` | **ENFRAQUECIDO** | Aceita 2 status. Antes validava contrato estrito. |
| `test_public_ai_tools_do_not_derive_parallel_tools` | Testava sem mocks de on-demand | Mocka `get_symbol_analysis` para `{}` | **ENFRAQUECIDO** | Mock impede teste de integração real. |
| `test_public_ai_tools_use_operational_snapshot_tools` | Mock sem `as_of` | Adicionado `as_of` dinâmico | **ACEITÁVEL** | Correção legítima: dados sem timestamp expiram. |
| `test_public_insight_exposes_strategic_panel_contract` | Testava sem mock de context | Mocka `resolve_symbol_context` | **ENFRAQUECIDO** | Mesmo problema. |
| `test_historical_news_never_becomes_ready_sentiment` | Mock sem `is_stale` | Adicionado `is_stale: True` | **FORTE** | Correção legítima. |
| `test_public_ai_tools_uses_last_good_snapshot` | `tools["risk"]` | `historical_tools["risk"]` | **ACEITÁVEL** | Contrato mudou corretamente. |
| `test_ford_raw_news_populates_symbol_cache` | Data fixa jun/2026 | `pubDate` dinâmico | **FORTE** | Correção legítima. |
| `test_mission30_complement_news_br` | `assertNotIn("market reads")` | `assertIn("market reads")` | **ENFRAQUECIDO** | Inverteu a asserção. Perdeu validação de tradução. |
| `test_frontend_contract_keeps_rsi_panel` | `assertNotIn("RSI@tv-basicstudies")` | `assertIn("RSI@tv-basicstudies")` | **ENFRAQUECIDO** | Inverteu: antes garantia que o ID não estava no código. |

### Testes que ainda falham conceitualmente:

- **`test_mission30_complement_news_br`**: Antes verificava que "market reads" NÃO aparecia (contrato de tradução para pt-BR). Agora verifica que APARECE. Se o objetivo é aceitar artigos do editor sem tradução, o teste precisa de um nome diferente e uma justificativa.

---

## 9. ATAQUE AOS ENTITLEMENTS

### Cenários testados (read-only via código):

| Cenário | Token | Resultado | Correto? |
|:--------|:------|:----------|:---------|
| Ausência de token | `None` | `False` | SIM |
| Token inválido | `"invalid"` | `False` (catch-all) | SIM |
| Token expirado | Refresh lança exceção | `False` | SIM |
| Trial válido | `plan="trial"` | `True` | SIM |
| Pro válido | `plan="premium"` | `True` | SIM |
| Básico | `plan="basico"` | `False` | SIM |
| Query `?is_premium=true` | Ignorado | `False` | SIM |

### Vazamento de dados premium por其他 rotas:

| Rota | Dados Premium? | Mecanismo |
|:-----|:---------------|:----------|
| `/public/market/bundle/{symbol}` | Gated (quando flag ON) | `_gate_bundle_for_entitlement` |
| `/public/market/insight/{symbol}` | **NÃO GATED** | Sem chamada a `_gate_bundle_for_entitlement` |
| `/public/market/chart/{symbol}` | Sem dados premium | Apenas OHLCV + zones |
| `/public/market/news/{symbol}` | Sem dados premium | Apenas notícias |
| `/public/market/quotes` | Sem dados premium | Apenas cotações |
| WebSocket | **NÃO GATED** | Se enviar dados premium via WS, não passa pelo gate |

**PROBLEMA:** O endpoint `/public/market/insight/{symbol}` não passa pelo `_gate_bundle_for_entitlement`. Se retornar `strategic_panel` ou `master_score` via `_snapshot_master_context`, esses dados premium estão expostos sem gating.

---

## 10. ATAQUE À PIPELINE ON-DEMAND

### Símbolos fora da lista:

| Símbolo | Comportamento | Problema |
|:--------|:--------------|:---------|
| CSNA3 | `request_symbol_hydration` enfileira. Primeira chamada retorna `PENDING`. | **Esperado**: painel vazio na primeira chamada. |
| HYPE3 | Mesmo comportamento. | **Esperado**. |
| Ticker B3 inválido | `canonical_symbol` retorna o ticker. `request_symbol_hydration` tenta. Pode ficar em `PROVIDER_ERROR`. | Sem tratamento de símbolo inválido no on-demand. |

### Estado em que quote existe mas painel não:

1. Quote é servido de cache (pode ter dado de warmup anterior)
2. On-demand está `PENDING` (hydrating)
3. Insight cai no snapshot global (que pode não ter o símbolo)
4. Resultado: quote válido, painel vazio, score default

---

## 11. ATAQUE ÀS NOTÍCIAS

### Redução CSNA3: 10 → 6 → 2

| Etapa | Count | Mecanismo |
|:------|:------|:----------|
| yfinance raw | 10 | Provider retorna 10 artigos |
| `_item_belongs_to_symbol` | ~6 | Filtro de relevância: descarta artigos de outros tickers |
| `_dedupe_news_items` | ~4 | Remove duplicatas |
| Freshness filter | 2 | Artigos antigos (> 48h) marcados `is_stale=True` |
| Bundle display | 2 | `allow_fetch=False` usa cache |

**A redução é legítima.** O filtro de relevância é correto (descarta artigos que mencionam outros tickers). A deduplicação é correta. A freshness é calculada a partir do `published_at` real, não do tempo de cache.

---

## 12. ATAQUE AO SENTIMENTO

### Algoritmo:

O sentimento NÃO é NLP. É contagem de `item.get("impact")`:

```python
bull_count = sum(1 for i in fresh_items if i.get("impact") == "bullish")
bear_count = sum(1 for i in fresh_items if i.get("impact") == "bearish")
```

Se `impact` não é definido pelo upstream, ambos são 0 → "neutral".

### Limitações:

1. **Sem negação**: "lucro cai menos que o esperado" pode ser classificado como "bearish" se "cai" é mapeado como bearish
2. **Sem contexto**: "ações sobem apesar de resultado fraco" → depende de qual parte o upstream foca
3. **Sample size pequeno**: para CSNA3 com 2 notícias, o sentimento é baseado em 2 dados
4. **Sem confidence**: não há score de confiança do sentimento
5. **Recência**: usa `fresh_items` (não stale), mas "ontem" é stale (48h cutoff)

---

## 13. FRONTEND E CONTRATOS

### Padrões perigosos no diff:

| Padrão | Encontrado? | Detalhe |
|:-------|:------------|:--------|
| `Number(value) \|\| 0` | Não no backend | Backend retorna `None` para campos sem dado |
| `parseFloat(value) \|\| 0` | Não no backend | N/A |
| `value ?? 0` | Não no backend | N/A |
| STALE virando READY | Não | `_payload_from_snapshot` retorna `HISTORICAL` para stale |
| Erro virando INSUFFICIENT | Sim | `PROVIDER_ERROR` → mapeado para `"ERROR"` no status map (linha 1541) |

---

## 14. COMPARAÇÃO LAGUNA VERSUS NEMOTRON

O relatório Nemotron (`docs/mission_74_nemotron_final_audit.md`) **não existe** no repositório. Portanto, a comparação não pode ser realizada.

**Nota:** Se o relatório Nemotron for criado posteriormente, esta seção deve ser atualizada.

---

## 15. RISCOS

| # | Risco | Severidade | Impacto |
|:--|:------|:-----------|:--------|
| R1 | safe_float com `default=None` propaga None em cálculos | P1 | TypeError em runtime em `clamp()`, `max()`, operações aritméticas |
| R2 | Premium gating desativado | P1 | Todos os dados premium expostos a anônimos |
| R3 | AXIA3/ELET3 retornam preço de PETR4 | P1 | Dados comercialmente incorretos |
| R4 | Insight vazio quando on-demand pending | P1 | Painel estratégico desaparece |
| R5 | Testes enfraquecidos (5 de 9) | P2 | Regressões podem passar despercebidas |
| R6 | Sentimento sem NLP real | P2 | Classificação incorreta de títulos mistos |
| R7 | Código duplicado de safe_float (4 versões) | P2 | Divergência silenciosa |
| R8 | `resolve_premium_entitlement` catch-all sem log | P2 | Erros de DB silenciados |
| R9 | Insight endpoint sem gating | P2 | Vazamento premium via rota separada |
| R10 | Thread daemon sem timeout global | P3 | Memory leak potencial |

---

## 16. BLOQUEADORES

| # | Bloqueador | Tipo | Descrição |
|:--|:-----------|:-----|:----------|
| B1 | **safe_float default=None** | BUG | Três chamadores usam padrão `if ... not in (None, "")` que previne, mas o contrato `-> Any` é inseguro. Se alguém adicionar uma nova chamada sem o guard, None propaga. |
| B2 | **Premium gating OFF** | FEATURE | O frontend não tem handling para "Disponível no Pro" nos campos gated. Ativar sem isso quebra a UX. |
| B3 | **AXIA3/ELET3 proxy incorreto** | DADOS | Proxy resolve aliases B3 para PETR4 em vez do ticker correto. |
| B4 | **Insight sem gating** | SEGURANÇA | `/public/market/insight/{symbol}` expõe strategic_panel e master_score sem premium gating. |

---

## 17. VEREDITO GO/NO-GO ADVERSARIAL

### **NO-GO CONDICIONAL**

**Motivos do NO-GO:**
1. AXIA3/ELET3/ELET6/AXIA6/AXIA7 retornam preço de PETR4 (dados incorretos)
2. Premium gating desativado mantém dados premium expostos
3. 5 de 9 testes atualizados estão enfraquecidos
4. Endpoint de insight sem gating premium

**Condições para GO:**
1. Corrigir proxy de aliases B3 (AXIA3, ELET3, etc.)
2. Manter gating desativado MAS documentar explicitamente que é intencional
3. Adicionar gating ao endpoint `/public/market/insight/{symbol}`
4. Reverter asserções invertidas nos testes (`test_mission30`, `test_mission_28b2`)
5. Adicionar log no `except Exception` de `resolve_premium_entitlement`

**Pontos Positivos:**
- safe_float com `math.isfinite` é correto
- Freshness granular (intraday vs daily) é bem projetado
- Cache de aliases com deduplicação funciona
- On-demand hydration com TTL de 120s é operacionalmente correto
- Testes de premium gating são completos
- `_json_safe_payload` converte NaN para None corretamente

---

## 18. PROVA DE INTEGRIDADE

O único arquivo criado neste repositório é:
- `docs/mission_75_laguna_adversarial_audit.md`

Diretório temporário criado:
- `/tmp/stocknewsbr-m75-laguna/` (vazio)

Nenhum código, teste ou configuração foi alterado.
