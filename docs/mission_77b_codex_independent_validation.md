# MISSÃO 77B — VALIDAÇÃO INDEPENDENTE E READ-ONLY DO RELATÓRIO 77A

**Data da validação:** 2026-07-26  
**Repositório:** `/home/dcima/stocknewsbr-backend`  
**Documento auditado:** `docs/mission_77a_opus_pre_codex_review.md`  
**Veredito para futura implementação:** **GO PARCIAL**

## 1. Escopo, procedência e limitações

Esta validação tratou a Missão 77A apenas como uma lista de alegações a testar. Nenhuma conclusão da 77A foi adotada como fonte de verdade.

### 1.1 Inconsistências documentais da Missão 77A

1. `docs/mission_77a_opus_pre_codex_review.md:1-4` informa que o relatório final foi produzido pelo **DeepSeek V4 Flash Free**.
2. O cabeçalho, em `docs/mission_77a_opus_pre_codex_review.md:7`, ainda declara **“Modelo: Opus 4.6”**.
3. A seção de GO, em `docs/mission_77a_opus_pre_codex_review.md:447-454`, marca correções e testes como concluídos com `[x]`, embora o próprio documento declare, em `:475`, que nenhuma correção foi implementada.
4. A frase de `:471`, “Nenhum ... working tree foi alterado”, não pode descrever o repositório inteiro: a working tree já estava extensamente alterada antes desta auditoria.
5. Há duas afirmações diferentes que não podem ser confundidas:
   - **arquivo alterado/criado por uma ação específica**;
   - **estado completo da working tree**, que inclui alterações preexistentes e possivelmente concorrentes.

O arquivo da Missão 77A não foi editado.

### 1.2 Limitação de integridade desta execução

Nenhum arquivo rastreado, código, teste, configuração ou dependência foi alterado por esta auditoria. Nenhum `git add`, `git commit`, `git push`, restore, clean ou reset foi executado.

Entretanto, uma chamada direta à função `public_market_insight("JPM"/"LCID")`, usada inicialmente como leitura, acionou `request_symbol_hydration` e escreveu estado `PENDING` no arquivo ignorado `runtime/cache/symbol_analysis.json`. A origem é o fluxo `public_market_insight` → hydration, com persistência em `app/system/symbol_hydration.py:_store` (`:103-114`). O arquivo não foi restaurado nem sobrescrito, para não descartar estado preexistente ou concorrente.

Consequências:

- a afirmação literal “100% nenhum estado runtime foi alterado” **não pode ser feita**;
- a comparação Git continua mostrando somente o relatório 77B como novo resultado versionável desta missão;
- o incidente também demonstra que chamar diretamente essa função de rota não é uma operação read-only.

## 2. Estado inicial do repositório

### 2.1 Comandos e resultados

```text
$ pwd
/home/dcima/stocknewsbr-backend

$ git branch --show-current
fix/audit-remediation-2026-07

$ git rev-parse HEAD
a51c0847f2aa6169388ceb4b34a316600010742c
```

```text
$ git status --short
 M app/ai/ai_common.py
 M app/ai/ai_master_score.py
 M app/ai/feature_hub.py
 M app/api/api_market_radar_v2.py
 M app/api/routes_public_market_live.py
 M app/dependencies.py
 M app/engine/engine_orchestrator.py
 M app/engine/engine_shards.py
 D app/market/liquidity_sweep.py
 M app/market/market_data_loader.py
 M app/services/public_ai_tools_service.py
 M app/services/public_news_service.py
 M app/services/snapshot_contract.py
 M app/social/posts.py
 M app/system/chart_warmup.py
 M app/system/market_stream.py
 M app/system/news_warmup.py
 M app/system/quote_warmup.py
 M app/system/scheduler.py
 M app/system/snapshot_worker.py
 M app/system/stream_router.py
 M app/system/stream_worker.py
 M app/system/symbol_hydration.py
 M app/system/system_monitor.py
 M app/system/websocket_manager.py
 M app/web/routes_chart.py
 M app/web/routes_dashboard.py
 M app/web/routes_market_pulse.py
 M app/web/routes_opportunities.py
 M app/web/routes_radar.py
 M app/web/routes_search.py
 M app/web/routes_terminal.py
 M app/web/routes_watchlist.py
 M apps/web/app/globals.css
 M apps/web/components/ticker-chart.tsx
 M apps/web/components/workspace-rails.tsx
 M apps/web/components/workspace-sections.tsx
 M apps/web/components/workspace-shell.tsx
 M apps/web/lib/types.ts
 M apps/web/package.json
 M apps/web/tsconfig.tsbuildinfo
 M tests/test_mission_24c_go_live_runtime.py
 M tests/test_mission_28b2_regressions.py
 M tests/test_mission_30_canonical_symbol_registry.py
 M tests/test_on_demand_hydration.py
 M tests/test_operational_rules.py
 M tests/test_public_market_routes.py
 M tests/test_single_snapshot_source.py
 M tests/test_strategic_panel.py
?? app/ai/conclusion_generator.py
?? docs/mission_70_data_chain_audit.md
?? docs/mission_70_fix_execution.md
?? docs/mission_71_remaining_errors_audit.md
?? docs/mission_72_consolidated_fixes.md
?? docs/mission_72_gemini31_execution.md
?? docs/mission_72_gemini36_validation.md
?? docs/mission_73_final_independent_review.md
?? docs/mission_74_nemotron_final_audit.md
?? docs/mission_75_laguna_adversarial_audit.md
?? docs/mission_76_north_mechanical_verification.md
?? docs/mission_77a_opus_pre_codex_review.md
?? scratch_collect_matrix.py
?? scratch_run_all_validations.py
?? test_news.py
?? tests/test_mission_70_ai_tools_freshness.py
?? tests/test_premium_gating.py
?? tests/test_safe_float.py
```

```text
$ git diff --stat
 app/ai/ai_common.py                                | 203 +++++-----
 app/ai/ai_master_score.py                          |  32 +-
 app/ai/feature_hub.py                              |  48 ++-
 app/api/api_market_radar_v2.py                     | 442 ++++++++++-----------
 app/api/routes_public_market_live.py               | 193 ++++++---
 app/dependencies.py                                | 128 +++---
 app/engine/engine_orchestrator.py                  | 186 +++++----
 app/engine/engine_shards.py                        |   2 -
 app/market/liquidity_sweep.py                      |  39 --
 app/market/market_data_loader.py                   |  21 +-
 app/services/public_ai_tools_service.py            | 119 +++++-
 app/services/public_news_service.py                |  10 +-
 app/services/snapshot_contract.py                  |   8 +-
 app/social/posts.py                                |   2 +-
 app/system/chart_warmup.py                         |   2 +-
 app/system/market_stream.py                        |  82 ++--
 app/system/news_warmup.py                          |   2 +-
 app/system/quote_warmup.py                         |   4 +-
 app/system/scheduler.py                            | 240 +++++------
 app/system/snapshot_worker.py                      | 234 +++++------
 app/system/stream_router.py                        | 118 +++---
 app/system/stream_worker.py                        | 152 +++----
 app/system/symbol_hydration.py                     |  14 +-
 app/system/system_monitor.py                       | 310 +++++++--------
 app/system/websocket_manager.py                    |   4 +-
 app/web/routes_chart.py                            |  80 ++--
 app/web/routes_dashboard.py                        |  82 ++--
 app/web/routes_market_pulse.py                     |  58 +--
 app/web/routes_opportunities.py                    |  58 +--
 app/web/routes_radar.py                            |  66 +--
 app/web/routes_search.py                           | 158 ++++----
 app/web/routes_terminal.py                         | 102 ++---
 app/web/routes_watchlist.py                        | 164 ++++----
 apps/web/app/globals.css                           | 396 +++++++++++++++++-
 apps/web/components/ticker-chart.tsx               |  10 +-
 apps/web/components/workspace-rails.tsx            |   2 +
 apps/web/components/workspace-sections.tsx         |   4 +-
 apps/web/components/workspace-shell.tsx            | 428 +++++++++++++++++++-
 apps/web/lib/types.ts                              |   1 +
 apps/web/package.json                              |   3 -
 apps/web/tsconfig.tsbuildinfo                      |   2 +-
 tests/test_mission_24c_go_live_runtime.py          |  10 +-
 tests/test_mission_28b2_regressions.py             |   9 +-
 tests/test_mission_30_canonical_symbol_registry.py |   4 +-
 tests/test_on_demand_hydration.py                  |   2 +-
 tests/test_operational_rules.py                    |   2 +-
 tests/test_public_market_routes.py                 |   3 +-
 tests/test_single_snapshot_source.py               |  11 +-
 tests/test_strategic_panel.py                      |   2 +-
 49 files changed, 2650 insertions(+), 1602 deletions(-)
```

```text
$ git ls-files --others --exclude-standard
app/ai/conclusion_generator.py
docs/mission_70_data_chain_audit.md
docs/mission_70_fix_execution.md
docs/mission_71_remaining_errors_audit.md
docs/mission_72_consolidated_fixes.md
docs/mission_72_gemini31_execution.md
docs/mission_72_gemini36_validation.md
docs/mission_73_final_independent_review.md
docs/mission_74_nemotron_final_audit.md
docs/mission_75_laguna_adversarial_audit.md
docs/mission_76_north_mechanical_verification.md
docs/mission_77a_opus_pre_codex_review.md
scratch_collect_matrix.py
scratch_run_all_validations.py
test_news.py
tests/test_mission_70_ai_tools_freshness.py
tests/test_premium_gating.py
tests/test_safe_float.py
```

## 3. Metodologia

1. Leitura integral da Missão 77A.
2. Consulta read-only do grafo existente `graphify-out/graph.json` apenas como índice de símbolos; as conclusões abaixo foram confirmadas no código atual.
3. Rastreamento por função, não apenas por nome de arquivo.
4. Leitura dos caches atuais sem reescrevê-los intencionalmente.
5. Reproduções puras via stdin e testes focalizados existentes.
6. Reprodução real do Yahoo/yfinance para AXIA/ELET/PETR, com cache do yfinance redirecionado para `/tmp`.
7. Separação entre:
   - evidência observada agora;
   - contrato expresso em código/testes;
   - hipótese não demonstrada.

As linhas citadas são as linhas da working tree auditada, não necessariamente as de `HEAD`.

## 4. Evidência por achado

### 4.1 P0-01 — AXIA3/ELET3/ELET6/AXIA6/PETR4

**Classificação da alegação “AXIA3 retorna PETR4”: REFUTADO no código, cache e provedor atuais.**

#### Cadeia atual

| Etapa | Arquivo/função/linhas | Resultado |
|---|---|---|
| Entrada/canonical | `app/services/symbol_registry.py:canonical_symbol_or_none`, `:292-324` | consulta `_ALIAS_TO_CANONICAL` |
| Alias | `_CURATED_ALIASES`, `:102-139`, especialmente `:114` | AXIA6/ELET3/ELET6 convergem para AXIA3 |
| Provider registry | `provider_symbol`, `:423-437` | AXIA3 → `AXIA3.SA`; PETR4 → `PETR4.SA` |
| Provider loader | `app/market/market_data_loader.py:_normalize_symbol`, `:536-573` | AXIA/ELET → `AXIA3.SA` por `_BDR_PROVIDER_SYMBOLS` `:418-449` |
| Cache loader | `_cache_key`, `:608-610`; `_cache_price_payload`, `:982-1003` | grupo AXIA usa chave `AXIA3`; PETR4 usa `PETR4` |
| Proxy | `_proxy_symbol_for`, `:634-637` | `None` para AXIA3, AXIA6, ELET3, ELET6 e PETR4 |
| Validação de identidade | `_payload_matches_requested_symbol`, `:246-294`; `_cache_price_payload`, `:986-989` | payload incompatível é rejeitado |
| Hydration | `app/system/symbol_hydration.py:_symbol/_key`, `:45-50` | grupo AXIA compartilha `AXIA3:1D`; PETR4 usa `PETR4:1D` |
| Bundle público | `app/api/routes_public_market_live.py:_normalize_public_symbol`, `:86-94`; `_symbol_aliases`, `:254-277`; `public_market_bundle`, `:1491-1612` | usa o canonical e candidates validados |

#### Reprodução do contrato

```text
AXIA3 -> canonical AXIA3; provider AXIA3.SA; loader cache AXIA3; proxy None
ELET3 -> canonical AXIA3; provider AXIA3.SA; loader cache AXIA3; proxy None
ELET6 -> canonical AXIA3; provider AXIA3.SA; loader cache AXIA3; proxy None
AXIA6 -> canonical AXIA3; provider AXIA3.SA; loader cache AXIA3; proxy None
PETR4 -> canonical PETR4; provider PETR4.SA; loader cache PETR4; proxy None
```

O cache atual `runtime/cache/market_quotes.json`, lido antes de qualquer chamada que enfileirasse hydration, continha identidades e preços distintos:

```text
AXIA3: price=50.26, volume=8,780,300, provider_symbol=AXIA3.SA
PETR4: price=42.21, volume=28,690,300, provider_symbol=PETR4.SA
```

#### Reprodução concreta do yfinance

Comando: script stdin usando `yf.Ticker(...).history(period="5d", interval="1d")`, com `yf.set_tz_cache_location("/tmp/mission77b-yfinance-cache")`.

Primeira tentativa no sandbox: falhou por resolução de rede/DNS e não produziu evidência de mercado. A repetição com rede autorizada produziu:

```text
AXIA3.SA 5 rows; 2026-07-24 close=50.2599983215332 volume=8874100
ELET3.SA EMPTY; Yahoo 404 quote not found
ELET6.SA EMPTY; Yahoo 404 quote not found
PETR4.SA 5 rows; 2026-07-24 close=42.209999084472656 volume=29151600
```

**Fato:** yfinance retornou AXIA3, não PETR4, para `AXIA3.SA`.  
**Fato:** não existe proxy AXIA→PETR4 no loader atual.  
**Hipótese não demonstrada pela 77A:** um fallback do yfinance teria devolvido PETR4. A reprodução contradiz essa hipótese.

O agrupamento AXIA3/AXIA6/ELET3/ELET6 é deliberado no contrato atual e confirmado por testes. Se as classes precisarem permanecer independentes, isso é uma decisão de produto/dados mestre diferente; não é prova de contaminação com PETR4.

#### Testes focalizados

```text
tests/test_mission_30_canonical_symbol_registry.py::
  Mission30CanonicalSymbolRegistryTests::
  test_axia_current_codes_replace_legacy_elet_aliases
1 passed in 0.91s

tests/test_market_data_loader.py::
  MarketDataLoaderTests::
  test_legacy_aliases_keep_canonical_snapshot_and_cache_identity
1 passed, 11 subtests passed in 0.58s

tests/test_mission_31e_market_symbols_data_integrity.py::
  Mission31EMarketSymbolsDataIntegrityTests::
  test_cached_identity_contract_rejects_wrong_symbol_aliases
1 passed in 0.78s
```

Três tentativas anteriores usaram nomes de classe inexistentes e terminaram com exit 4/“no tests ran”; não foram contadas como testes executados.

### 4.2 P0-02 — `public_market_insight` e premium gating

**Classificação: CONFIRMADO, condicionado ao gating estar ligado.**

#### Decorador e dependências

- Router: `app/api/routes_public_market_live.py:58`, prefixo `/public`.
- Decorador: `@router.get("/market/insight/{symbol}")`, `:1275`.
- Função: `public_market_insight`, `:1276`.
- Dependências da rota observadas por introspecção FastAPI: `[]`.
- Rota efetiva: `GET /public/market/insight/{symbol}`.

A função retorna diretamente `_snapshot_master_context`, que expõe, entre outros, `master_score`, `strategic_panel` e `institutional_flow` (`:348-436`).

O bundle:

- `public_market_bundle`, `:1491`;
- `is_premium: bool = Depends(resolve_premium_entitlement)`, `:1498`;
- `_gate_bundle_for_entitlement`, `:1453-1487`;
- aplicação do gate ao final, `:1612`.

O entitlement está em `app/dependencies.py:resolve_premium_entitlement`, `:66-85`.

#### Estado default

`_PREMIUM_GATING_ENABLED`, `app/api/routes_public_market_live.py:1450`, usa `STOCKNEWS_PREMIUM_GATING` e fica **OFF** quando a variável está ausente/vazia. Em `:1462`, gate OFF torna a função de gating um no-op.

Logo:

- **ausência da dependency:** fato, sempre;
- **gating desativado por configuração:** comportamento default atual;
- **vazamento efetivo/bypass:** reproduzido quando o gating está ON, porque o bundle anonimizado é redigido e o endpoint direto não.

#### Reprodução

Com `STOCKNEWS_PREMIUM_GATING=1`, fontes de cache substituídas por dados determinísticos:

```text
route=/public/market/insight/{symbol}
methods=GET
dependencies=[]
direct insight:
  master_score=8.2
  strategic_panel.recommended_action=COMPRAR
  institutional_flow=BUY
anonymous bundle:
  master_score redacted
  strategic_panel redacted
  ai_tools.status=PREMIUM_LOCKED
```

Teste:

```text
$ STOCKNEWS_PREMIUM_GATING=1 python -m pytest -q -p no:cacheprovider tests/test_premium_gating.py
4 passed in 0.87s
```

Os testes usam patches/mocks para isolar entitlement e payload. Eles validam a política/gating, não um provedor real.

### 4.3 P1-01 — cache “perpetua PETR4 sob AXIA3”

**Classificação: REFUTADO como alegação causal atual.**

`app/system/symbol_hydration.py:_key` (`:49-50`) usa canonical, mas PETR4 e AXIA3 têm canonicals diferentes. O loader também usa chaves diferentes e valida identidade antes de persistir (`app/market/market_data_loader.py:_cache_price_payload`, `:982-1003`).

O cache compartilha corretamente os aliases que o contrato declarou equivalentes dentro do grupo AXIA; ele não compartilha a chave PETR4. Como a contaminação upstream não foi reproduzida e o cache observado possuía valores distintos, não há erro PETR4 que o cache esteja perpetuando.

**Possibilidade residual:** um payload já corrompido em uma versão anterior poderia ter sido persistido historicamente. Não há evidência atual que identifique quando ou onde isso ocorreu.

### 4.4 P1-02 — liquidez

**Classificação: PARCIALMENTE CONFIRMADO.**

- Sintoma `INSUFFICIENT_DATA/missing_liquidity_geometry`: confirmado.
- Causa “lower/upper não são produzidos”: refutada.

#### Cadeia

1. `app/ai/ai_liquidity_map.py:_score_row`, `:8-90`:
   - `upper_liquidity = high + 25% do range`, `:21`;
   - `lower_liquidity = low - 25% do range`, `:22`;
   - ambos entram em `metrics`, `:74-79`.
2. `app/ai/ai_specialists.py:_compose_liquidity`, `:206-262`:
   - lê os campos em `:223-227`;
   - preserva em `metrics`, `:250-258`.
3. `app/api/routes_public_market_live.py:_ai_metric_component`, `:460-517`:
   - valida `low < high` e preço, `:483-488`;
   - só define lado se toda a faixa estiver acima (`low > price`) ou abaixo (`high < price`), `:489`;
   - exige lado, `as_of` e `source`, `:490`;
   - caso contrário retorna `INSUFFICIENT_DATA`, `:491-499`.

Reprodução pura:

```text
price=100, high=105, low=95
liquidity_map: lower=92.5, upper=107.5
official liquidity: lower=92.5, upper=107.5
public component:
  status=INSUFFICIENT_DATA
  side=None
  reason=missing_liquidity_geometry
```

O produtor cria uma **faixa que envolve o preço**. O consumidor aceita apenas uma **zona inteiramente de um lado do preço**. A falha começa no limite contratual entre esses dois significados, não por falta dos campos.

`app/market/liquidity_sweep.py` está removido na working tree, mas o arquivo de `HEAD` era um detector pandas independente e não possuía consumidores atuais. Módulos alternativos ativos:

- `app/ai/ai_liquidity_map.py`;
- `app/ai/ai_liquidity_sweep.py`;
- `app/ai/ai_specialists.py`;
- `app/engine/scanners/liquidity_scanner.py`;
- detector local em `app/api/api_market_radar_v2.py`.

A remoção de `app/market/liquidity_sweep.py` não explica o contrato oficial observado.

Teste:

```text
$ python -m pytest -q -p no:cacheprovider tests/test_on_demand_hydration.py
21 passed in 0.77s
```

Limitação: os casos READY desse teste usam geometria artificial inteiramente acima/abaixo do preço; não validam que o produtor real gere essa geometria.

**Conclusão:** relaxar a validação e inventar um lado para uma faixa envolvente fabricaria dado operacional. Até o contrato ser definido, manter `INSUFFICIENT_DATA` é mais correto que publicar BUY_SIDE/SELL_SIDE falso.

### 4.5 P1-03 — JPM e LCID

**Classificação: PARCIALMENTE CONFIRMADO.**

Antes da chamada incidental de hydration, `public_market_insight` produziu leituras distintas:

```text
JPM:  score=4.9, RSI=49.2673, trend_bias=neutro
LCID: score=4.8, RSI=47.0697, trend_bias=neutro
ambos: master_score ausente; strategic_panel_summary ausente
```

Portanto, os payloads e scores não são idênticos.

Depois da chamada, `runtime/cache/symbol_analysis.json` registrou ambos como `PENDING/hydrating`, sem `analysis`/painel, com `updated_at` distintos. Isso confirma ausência momentânea de hydration, mas a observação foi influenciada pela própria chamada e não deve ser tratada como fotografia inicial.

Frontend atual:

- painel somente do insight do símbolo: `apps/web/components/workspace-shell.tsx:9392-9396`;
- operational view do bundle: `:9453-9456`;
- conclusão: LLM do painel primeiro, `:10662-10664`;
- depois fallback por `symbolOperationalView`, `:10665-10675`;
- só depois painel genérico, `:10677-10679`.

O fallback operacional atual não é a cadeia da linha 3800 citada pela 77A. `symbolContextStrategicSections` (`:5609-5666`) inclui o símbolo e deriva o texto de bias/blocks; `symbolContextStrategicBasis` (`:5669-5696`) inclui score e volume próprios. Se os dois ativos têm o mesmo conjunto de componentes ausentes e mesmo bias, várias frases ficam iguais por construção, mas cenário/basis continuam individualizados.

O cache da conclusão em `app/ai/conclusion_generator.py:_cache_key` (`:42-50`) inclui o símbolo uppercased como primeiro elemento. Não há evidência de colisão JPM/LCID.

**Causa confirmada da similaridade:** mesmo estado de autorização (`WAIT`), mesmo bias neutro e mesmos componentes ausentes alimentam o fallback operacional.  
**Não confirmado:** backend idêntico, cache de conclusão compartilhado ou fallback antigo da linha 3800.

Não há setor no contrato usado pelo fallback. Textos específicos por setor, como os propostos pela 77A, inventariam contexto.

### 4.6 P1-04 — timestamps

**Classificação: PARCIALMENTE CONFIRMADO.**

#### Mapa semântico atual

| Campo | Produtor/consumidor | Semântica observada |
|---|---|---|
| `detected_at` | `app/ai/ai_common.py:423-424,498` | alias de `deal_timestamp`; um `detected_at` de entrada isolado não é preferido por `deal_timestamp` |
| `found_at` | `ai_common.py:495`; `deal_timestamp`, `:102-112` | primeiro instante do finding quando fornecido |
| `first_seen_at` | `ai_common.py:496` | hoje é alias de `found_at` no produtor |
| `updated_at` | `ai_common.py:425-432,499` | confirmação/reprocessamento, limitado para não ficar depois do market time |
| `last_confirmed_at` | `ai_common.py:500` | alias de `updated_at` no produtor base |
| `as_of` | `ai_common.py:433,501` | timestamp dos dados/análise quando fornecido; fallback no market time |
| `market_data_updated_at` | `ai_common.py:423,481` | timestamp escolhido por `market_timestamp` |
| `evaluated_at` | `app/services/public_ai_tools_service.py:371,381` | relógio da avaliação de freshness |
| `source_as_of` | `public_ai_tools_service.py:380` | preserva o `as_of` antes da avaliação |
| `quote_time` | payload de quote | instante do provedor/candle; o serviço de quote também o alia a timestamps de mercado |
| `hydration.updated_at` | `app/system/symbol_hydration.py:_store`, `:103-114` | momento de escrita/mudança do estado do worker |

Reprodução:

```text
Somente market_data_updated_at:
  detected_at=found_at=first_seen_at=updated_at=last_confirmed_at=
  as_of=market_data_updated_at=2026-07-24T20:00:00Z

Com found_at=19:00, last_confirmed_at=19:30, as_of=19:45,
market_data_updated_at=20:00:
  detected_at=found_at=first_seen_at=19:00
  updated_at=last_confirmed_at=19:30
  as_of=19:45
  market_data_updated_at=20:00
```

Logo, os campos parecem todos iguais quando o input só possui um timestamp, mas podem representar eventos diferentes quando o produtor fornece dados distintos.

Achado adicional: `deal_timestamp` não lista a chave de entrada `detected_at`; ela aparece em `market_timestamp` depois de vários campos de mercado. Um `detected_at` isolado pode ser substituído por `market_data_updated_at`. Isso é uma ambiguidade real e deve ser coberta por contrato.

Consumidores frontend:

- `resolveAiAlertTimestamp`, `workspace-shell.tsx:1767-1784`, prefere found/first/detected;
- `resolveAiFindingTimestamp`, `:1787-1804`, prefere last_confirmed/updated/as_of;
- merge de alertas, `:10270-10317`, conserva detecção estável e atualiza confirmação;
- UI exibe “Detectado”, “Atualizado” e “Dados até” separadamente, `:11696-11715`.

Portanto, remoção/deduplicação imediata quebraria semânticas e consumidores. Não foi comprovado que um merge backend “sobrescreva updated_at múltiplas vezes”; o frontend atualiza deliberadamente o evento de confirmação.

Testes:

```text
$ python -m pytest -q -p no:cacheprovider \
    tests/test_ai_common_payload.py \
    tests/test_market_snapshot_ai_tools.py \
    tests/test_mission_70_ai_tools_freshness.py
18 passed in 8.61s
```

Os testes validam aliases, clamp e freshness; parte deles usa fixtures/mocks e não reproduz relógios reais concorrentes.

### 4.7 P1-05 — Master Score e consensus ratio

**Classificação: PARCIALMENTE CONFIRMADO.**

`OFFICIAL_AI_TOOLS`, `app/ai/ai_master_score.py:29-39`, contém 9 ferramentas:

```text
flow, liquidity, trend, momentum, smart_money, risk, news, macro, regime
```

- `_direction_from_text` trata `risk` como `NEUTRAL` (`:196-219`).
- `_weighted_direction_score` exclui `risk` (`:331-347`).
- `_consensus` conta todas as nove e divide por nove (`:369-387`).

Reprodução:

```text
8 ferramentas direcionais BULLISH + risk NEUTRAL:
  aligned=8, neutral=1, total=9, ratio=0.8889

9 ferramentas NEUTRAL:
  aligned=9, neutral=9, total=9, ratio=1.0
```

A afirmação “risk nunca incrementa aligned” é falsa no caso de direção mestre neutra. Para direção bullish/bearish, existe teto aritmético de 8/9.

O contrato esperado não está definido de forma suficiente para concluir que dividir por 9 seja necessariamente incorreto:

- consenso de todas as ferramentas: 9 é coerente;
- consenso direcional: risk deveria sair do denominador;
- cobertura total: deveria considerar disponibilidade, não apenas direção;
- consenso apenas entre ferramentas disponíveis: denominador deveria ser dinâmico.

Como `ratio` alimenta confidence e score (`:402-413`, `:462-465`) e o frontend/testes exibem contagens sobre total 9, trocar para `-1` sem migração alteraria score e confiança. A recomendação da 77A “dividir por 8” não está comprovada pelo contrato.

Teste:

```text
$ python -m pytest -q -p no:cacheprovider tests/test_master_score_institutional.py
14 passed in 7.95s
```

Os testes confirmam o contrato atual; não provam que ele é o contrato de produto desejado.

### 4.8 `_context_available`

**Classificação da alegação “mínimo de 5 tools alinhadas”: REFUTADO.**

`CORE_CONTEXT_TOOLS`, `STRUCTURE_TOOLS` e `INSTITUTIONAL_TOOLS` se sobrepõem (`app/ai/ai_master_score.py:65-67`). `_context_available` (`:324-328`) exige contagens por conjunto, não cinco ferramentas distintas.

Reprodução:

```text
trend=BULLISH, flow=BULLISH, liquidity=BULLISH; demais NEUTRAL
core=3, structure=1, institutional=2
_context_available(..., BULLISH) = True
```

Três ferramentas distintas podem satisfazer o guard. Isso não prova que a lógica esteja errada; apenas refuta a descrição da 77A.

### 4.9 `safe_float`

**Classificação: COMPORTAMENTO ESPERADO, com ressalva de contrato.**

`app/ai/ai_common.py:safe_float`, `:22-31`, retorna o default para `None`, string vazia, erro, NaN ou infinito. Os chamadores críticos em `_pseudo_tool_rows_from_feature_row`, `app/ai/ai_master_score.py:156-180`, checam ausência e usam default numérico.

Teste:

```text
$ python -m pytest -q -p no:cacheprovider tests/test_safe_float.py
1 passed, 3 subtests passed in 0.02s
```

O arquivo contém um teste parametrizado com três subtests, não “12 casos” como afirma a 77A. Não foi observada propagação de `None` nos chamadores críticos auditados. A anotação `-> Any` permite defaults não numéricos e continua frágil, mas isso não é falha reproduzida.

### 4.10 Sentimento e `impact`

**Classificação: PARCIALMENTE CONFIRMADO.**

Origem:

- `app/services/news_service.py:_impact_hint_balance`, `:984-1020`;
- `_impact_from_keywords`, `:1044-1051`;
- `_normalize_raw_item`, `:1549-1587`;
- item normalizado recebe `impact`, `:1629`.

Valores produzidos: `bullish`, `bearish` ou `neutral`. Portanto, o pipeline real possui uma classificação léxica upstream; não é apenas um campo externo não analisado.

Agregação no bundle, `app/api/routes_public_market_live.py:_market_metrics_contract`, `:753-815`:

```text
sem notícias:
  INSUFFICIENT_DATA / no_fresh_sentiment_source

1 notícia fresca sem chave impact:
  READY / neutral / bull=0 / bear=0 / total=1

1 notícia fresca impact=neutral:
  READY / neutral / bull=0 / bear=0 / total=1

1 bullish + 1 bearish:
  READY / mixed / bull=1 / bear=1 / total=2
```

O payload atual não diferencia notícia realmente classificada como neutra de notícia sem classificação. Logo:

- `READY + neutral` pode representar dado real;
- também pode representar ausência da chave `impact` em um item legado/mocado;
- converter todo caso bull=0/bear=0 em `INSUFFICIENT_DATA`, como sugere a 77A, quebraria neutralidade verdadeira.

Teste do produtor:

```text
$ python -m pytest -q -p no:cacheprovider tests/test_news_service.py
18 passed in 0.04s
```

### 4.11 Notícias e locale

**Classificação: COMPORTAMENTO ESPERADO pelo contrato atual.**

- detector: `app/services/public_news_service.py:_public_news_language`, `:199-203`;
- `_ARTICLE_TEXT_FIELDS`, `:289-292`;
- `_translate_english_news_text`, `:295-360`;
- `_normalize_public_news_item`, `:363-378`.

O código preserva deliberadamente título/headline como publicado. Summary/card_summary também preservam a frase do publisher se a tradução léxica seria parcial; `language/content_locale` informa essa condição. O título inglês em UI pt-BR não é uma falha acidental no fluxo atual, embora possa contrariar uma expectativa futura de produto.

Teste:

```text
$ python -m pytest -q -p no:cacheprovider tests/test_public_news_service.py
12 passed in 0.06s
```

As alegações quantitativas históricas “CSNA3 10→6→2” e seu conteúdo ao vivo não foram reproduzidas, pois dependeriam do feed externo e de um instante anterior. Classificação desse número: **INCONCLUSIVO**.

### 4.12 Painel das IAs

**Classificação: PARCIALMENTE CONFIRMADO.**

- `_scoped_tools`, `app/services/public_ai_tools_service.py:240-293`, filtra símbolo/tool/timeframe, exige linha displayable e limita por `AI_ALERT_MAX_ROWS_PER_TOOL`.
- `_payload_from_snapshot`, `:354-416`, separa `active_tools` e `historical_tools` e acrescenta `source_as_of`, `evaluated_at` e freshness.
- `build_public_ai_tools_payload`, `:419-528`, tenta hydration on-demand do símbolo antes do snapshot global, especialmente `:450-485`.

Isso refuta a causa absoluta “small-cap fora do top-N necessariamente gera painel vazio” no código atual: existe um caminho on-demand específico para esse caso. O resultado ainda pode ser PENDING/INSUFFICIENT_DATA se o provider não entregar candles/volume.

O frontend usa `tools` ativos para a aba selecionada (`workspace-shell.tsx:9540-9565`) e trata stale/terminal states separadamente (`:10376-10416`). Não foi comprovado que misture `historical_tools` com ativos na lista atual.

Múltiplas rows por tool são permitidas e limitadas; “repetitivo” é uma avaliação de UX, não um defeito técnico demonstrado.

Teste:

```text
$ python -m pytest -q -p no:cacheprovider tests/test_mission_68_public_ai_tools.py
17 passed, 10 subtests passed in 0.73s
```

Os testes usam snapshots/hydration mockados; validam scoping, freshness e fallback, não disponibilidade real de cada símbolo.

### 4.13 Gauge de volume

**Classificação da alegação “número e rótulo usam contratos diferentes”: REFUTADO.**

Backend:

- `volume_vs_daily_average`, `routes_public_market_live.py:755-763`;
- `intraday_rvol`, `:767`;
- alias `rvol = intraday_rvol`, `:812-814`.

Frontend:

- número `dailyVolumeRatio`: `assetMetrics.volume_vs_daily_average.ratio`, `workspace-shell.tsx:10544`;
- rótulo: derivado do mesmo `dailyVolumeRatio`, `:10545-10551`;
- título: “Volume atual / média diária”, `:12075`;
- valor mostrado: `${dailyVolumeRatio}×`, `:12079`;
- nota: “Dado informativo”, `:12080`.

O gauge não apresenta esse número como RVOL intraday. Número, título e rótulo usam o mesmo contrato diário informacional.

Existe, porém, uma regressão independente de escala do ponteiro:

```text
$ node apps/web/scripts/mission-68-functional-recovery.mjs
46 PASS
1 FAIL: daily volume ratio is separate from intraday RVOL
exit 1
```

O script espera `dailyVolumeRatio * 100`; o componente atual usa `* 50` (`:12077`). O campo está correto, mas teste e escala visual divergiram. Não há evidência suficiente para decidir se o teste ou a implementação contém a escala desejada.

### 4.14 Premium gating default OFF

**Classificação: COMPORTAMENTO ESPERADO/configuração atual.**

Default OFF está explícito em `routes_public_market_live.py:1450`. Isso não corrige a ausência de dependency no insight; apenas significa que, por padrão, não existe fronteira premium ativa a contornar. Antes de ligar a flag, o endpoint direto precisa aplicar a mesma política do bundle.

### 4.15 LLM/template e cache da conclusão

**Classificação: COMPORTAMENTO ESPERADO.**

`app/ai/conclusion_generator.py` documenta fallback para template (`:1-11`) e `_cache_key` inclui símbolo, tendência, sinal, veredito, RSI e variação (`:42-50`). Não há prova de cache cruzado entre ativos. Como o arquivo é não rastreado e preexistente, esta auditoria não atribui sua autoria à Missão 77A.

### 4.16 META34/M1TA34

**Classificação: COMPORTAMENTO ESPERADO pelo contrato atual.**

O registry e o loader convergem META34/M1TA34 em provider `M1TA34.SA` (`symbol_registry.py:138`; `market_data_loader.py:441-444`). Preço/cache compartilhado decorre desse alias deliberado. Não foi feita consulta externa específica nesta missão.

## 5. Matriz final

| ID | Alegação da M77A | Classificação | Evidência | Causa confirmada | Prioridade real | Mudança recomendada |
|---|---|---|---|---|---|---|
| P0-01 | AXIA3/ELET/AXIA retornam PETR4 por yfinance/proxy | REFUTADO | provider real AXIA3=50.26 e PETR4=42.21; proxies `None`; caches/chaves distintos | nenhuma contaminação atual encontrada | nenhuma correção | adicionar apenas teste de identidade/regressão; não mudar alias/provider sem nova reprodução |
| P0-02 | insight público contorna gating | CONFIRMADO | rota sem dependency; bundle redigido com gate ON; direto expõe premium | política aplicada só no bundle | P0 antes de habilitar gate; P1 latente enquanto OFF | aplicar uma função comum de gating/entitlement ao insight e bundle |
| P1-01 | cache perpetua PETR4 sob AXIA3 | REFUTADO | key AXIA3 distinta de PETR4; identity mismatch rejeitado | grupo AXIA compartilha apenas o canonical declarado | nenhuma correção | manter; teste contra payload PETR4 sob AXIA |
| P1-02 | liquidez falha porque lower/upper não são produzidos | PARCIALMENTE CONFIRMADO | lower/upper 92.5/107.5 produzidos; consumidor rejeita faixa envolvendo preço | incompatibilidade envelope vs zona one-sided | P1 contrato | definir semântica; corrigir produtor ou representar envelope; não relaxar inventando side |
| P1-03 | JPM/LCID têm backend/cache idêntico e mesmo fallback antigo | PARCIALMENTE CONFIRMADO | scores/RSI distintos; cache key da LLM inclui ticker; textos convergem quando blocks/bias coincidem | ausência de hydration + fallback operacional comum | P2 | melhorar disponibilidade/hydration; não inventar setor |
| P1-04 | timestamps são todos redundantes/sobrescritos | PARCIALMENTE CONFIRMADO | aliases iguais no produtor base, mas divergência reproduzida e consumidores distintos | defaults colapsam eventos quando input é pobre | P1/P2 contrato | documentar eventos, preservar campos; testar `detected_at` de entrada; não remover antes de migrar consumidores |
| P1-05 | consensus deve ser `aligned/8` | PARCIALMENTE CONFIRMADO | 8/9 para direção, 9/9 para neutral; risk excluído do peso, não da contagem | semântica de ratio ambígua | P1 produto | definir consenso vs cobertura; só então alterar denominador e recalibrar score |
| S-01 | sem `impact` equivale a neutral real | PARCIALMENTE CONFIRMADO | missing e neutral geram payload idêntico | agregador não conta classified/missing | P1/P2 | expor contagens neutral/classified/missing; insufficient apenas se nenhum item classificado |
| N-01 | título inglês em pt-BR é bug de tradução | COMPORTAMENTO ESPERADO | título e texto do publisher preservados explicitamente | contrato “as published” | produto | mudar só se houver requisito de tradução integral e tradutor confiável |
| N-02 | CSNA3 10→6→2 é redução legítima observada | INCONCLUSIVO | não reproduzido contra o feed daquele instante | dado histórico da 77A | baixa | teste determinístico de relevância/dedup/freshness |
| AI-01 | top-N global necessariamente deixa símbolo sem painel | REFUTADO no código atual | hydration on-demand ocorre antes do snapshot global | indisponibilidade pode vir do provider/hydration terminal | P1 operacional se recorrente | medir statuses on-demand; não ampliar top-N sem dados |
| AI-02 | painel mistura histórico com ativo | REFUTADO no backend atual | `active_tools` e `historical_tools` separados; testes passam | não encontrado | baixa | teste frontend explícito; nenhuma correção agora |
| VOL-01 | gauge mostra daily ratio rotulado como RVOL | REFUTADO | título, valor e label usam `volume_vs_daily_average` | contrato diário informacional consistente | nenhuma correção de campo | manter separação |
| VOL-02 | gauge está coerente com teste visual | REFUTADO | teste espera ×100; código usa ×50 | escala visual não especificada | P2 | decidir escala e alinhar teste/código |
| FP-01 | `safe_float(None)` propaga e quebra score | REFUTADO | guardas + teste finito/NaN/Inf | default controlado nos chamadores auditados | baixa | nenhuma mudança funcional |
| FP-02 | `_context_available` exige 5 tools distintas | REFUTADO | trend+flow+liquidity já satisfaz | sobreposição de conjuntos | P1 apenas se requisito era 5 | documentar/ajustar só após confirmar regra de produto |
| CFG-01 | premium gating OFF é bug | COMPORTAMENTO ESPERADO | default explícito OFF | rollout incompleto/intencional | alta antes de ligar | manter OFF até insight e UI estarem prontos |
| LLM-01 | conclusão cacheada colide JPM/LCID | REFUTADO | `_cache_key` inclui símbolo | não encontrado | nenhuma | manter teste de chave |

## 6. Testes e reproduções realmente executados

Todos os pytest foram executados com `PYTHONDONTWRITEBYTECODE=1`, `XDG_CACHE_HOME=/tmp/mission77b-xdg` e `-p no:cacheprovider`, salvo quando o comando mostrado não precisava desses controles.

| Hipótese | Comando/artefato | Resultado real | Limitação |
|---|---|---|---|
| alias/provider/cache AXIA | três node IDs específicos, seção 4.1 | 3 testes, 11 subtests, todos passaram | mocks validam contrato, não cotação externa |
| yfinance não devolve PETR4 para AXIA3 | script stdin com `history(5d,1d)` | AXIA3 50.26; PETR4 42.21; ELET3/ELET6 404 | fotografia do provider em 2026-07-26 |
| gating do bundle | `tests/test_premium_gating.py` | 4 passed | payloads mockados |
| master score | `tests/test_master_score_institutional.py` | 14 passed | contrato atual, não intenção do produto |
| liquidez/hydration | `tests/test_on_demand_hydration.py` | 21 passed | geometria READY artificial |
| news impact | `tests/test_news_service.py` | 18 passed | feeds mockados |
| timestamps/freshness | três arquivos, seção 4.6 | 18 passed | relógios/fixtures controlados |
| safe_float | `tests/test_safe_float.py` | 1 passed, 3 subtests | cobre função canônica |
| locale/public news | `tests/test_public_news_service.py` | 12 passed | feeds mockados |
| painel IA | `tests/test_mission_68_public_ai_tools.py` | 17 passed, 10 subtests | hydration mockada |
| gauge frontend | `node apps/web/scripts/mission-68-functional-recovery.mjs` | 46 pass, 1 fail, exit 1 | teste textual de contrato |

Tentativas não contadas como sucesso:

1. yfinance dentro do sandbox: falha de DNS/rede.
2. Três pytest com nomes de classe incorretos: exit 4, nenhum teste executado; repetidos com node IDs corretos.
3. `tests/test_public_market_routes.py` completo: ficou sem saída por mais de dois minutos e foi interrompido apenas o processo iniciado por esta auditoria; exit 130, nenhum “passed” alegado.
4. Primeiro script puro: `ImportError` por nome incorreto `run_ai_liquidity_map`.
5. Segundo script puro: produziu os resultados de consensus/context antes de falhar por argumentos obrigatórios ausentes em `build_payload`; a reprodução foi corrigida e repetida integralmente.

## 7. Plano mínimo para futura implementação

### 7.1 Bloqueadores comprovados

#### I1 — Uniformizar o gating do insight

- **Arquivos mínimos:** `app/api/routes_public_market_live.py`; teste em `tests/test_premium_gating.py`.
- **Mudança:** aplicar o mesmo entitlement/redaction aos dados premium do insight direto e do bundle, preferencialmente reutilizando a função existente.
- **Testes:** anônimo/basic/premium com flag ON; comportamento explícito com flag OFF; acesso HTTP direto ao insight e bundle.
- **Risco:** alto — segurança/receita e compatibilidade do frontend.
- **Dependências:** definir quais campos do insight são públicos.
- **Ordem:** primeiro contrato/redaction, depois teste HTTP, só depois considerar habilitar a flag.

### 7.2 Bugs reais não bloqueadores

#### I2 — Distinguir sentimento neutro de não classificado

- **Arquivos mínimos:** `app/api/routes_public_market_live.py`; testes de market metrics/news.
- **Mudança:** contar `neutral`, `missing_impact` e `classified_total`; manter READY neutral quando há `impact=neutral`; usar insufficient quando nenhum item possui classificação.
- **Risco:** médio — muda cards e decisões dependentes de sentiment.
- **Dependências:** garantir que todo produtor preserve `impact`.
- **Ordem:** contrato/testes do produtor, agregador, frontend.

#### I3 — Resolver a escala visual do gauge

- **Arquivos mínimos:** ou `apps/web/components/workspace-shell.tsx` ou `apps/web/scripts/mission-68-functional-recovery.mjs`, não ambos sem decisão.
- **Mudança:** definir o mapeamento do ratio diário para 0–100 e alinhar a asserção.
- **Risco:** baixo; apenas visual se displayValue permanecer ratio real.
- **Dependências:** decisão UX para 0.5×, 1× e ≥2×.

#### I4 — Clarificar timestamps sem remover campos

- **Arquivos mínimos:** `app/ai/ai_common.py`, testes de payload; eventualmente frontend somente se rótulos mudarem.
- **Mudança:** definir precedência de um `detected_at` de entrada e documentar evento de cada campo; manter aliases compatíveis durante migração.
- **Risco:** médio/alto — ordenação, freshness e deduplicação de alertas.
- **Dependências:** inventário de consumidores já iniciado na seção 4.6.

### 7.3 Limitações de provider/contrato

#### I5 — Liquidez

- **Arquivos mínimos após decisão:** `app/ai/ai_liquidity_map.py`, `app/ai/ai_specialists.py` e/ou `app/api/routes_public_market_live.py`; testes produtor→consumidor.
- **Decisão necessária:** a métrica é envelope ao redor do preço ou zona operacional one-sided?
- **Risco:** alto — fabricar lado gera sinal falso.
- **Ordem segura:** especificar exemplos de SELL_SIDE/BUY_SIDE/envelope; teste end-to-end; alterar produtor ou adicionar representação não direcional; manter insufficient até lá.

#### I6 — Hydration JPM/LCID e outros símbolos

- **Arquivos mínimos:** primeiro nenhum; instrumentar/testar `app/system/symbol_hydration.py` com caches em `/tmp`.
- **Mudança futura:** somente se for reproduzido provider candles/volume insuficiente.
- **Risco:** médio — chamadas externas e latência.
- **Dependências:** provider real e orçamento de retry.
- **Proibição:** não gerar copy setorial sem setor no contrato.

#### I7 — Consensus ratio

- **Arquivos mínimos após decisão:** `app/ai/ai_master_score.py`, testes institucionais e contratos frontend.
- **Decisão necessária:** consenso total, consenso direcional, cobertura ou consenso entre disponíveis.
- **Risco:** alto — altera score/confidence/conviction.
- **Ordem:** contrato esperado; fixtures de 0–9 tools; recalibração; migração. Não aplicar `len(...)-1` isoladamente.

### 7.4 Comportamentos esperados — nenhuma implementação agora

- aliases AXIA/ELET conforme contrato atual;
- provider/cache distintos de PETR4;
- título de notícia como publicado;
- premium gate default OFF;
- fallback LLM para template;
- cache da conclusão contendo ticker;
- separação `volume_vs_daily_average` de `intraday_rvol/rvol`;
- separação backend de tools ativos/históricos.

### 7.5 Alegações refutadas — não corrigir

- AXIA3 atual retornando PETR4 por yfinance/proxy;
- cache PETR4 compartilhado com AXIA3;
- ausência de `lower_liquidity`/`upper_liquidity`;
- mínimo de cinco ferramentas distintas em `_context_available`;
- cache de conclusão JPM/LCID sem ticker;
- gauge lendo RVOL com rótulo de média diária;
- necessidade automática de excluir risk por `-1`.

### 7.6 Itens que exigem mais evidência

- origem histórica do payload `proxy_market`/PETR4 relatado pela 77A;
- redução CSNA3 10→6→2 no feed daquele instante;
- requisito de tradução integral de headlines;
- número ideal de rows por tool no painel;
- escala pretendida do ponteiro de volume;
- contrato de produto do consensus ratio;
- se classes AXIA3/AXIA6/ELET3/ELET6 devem continuar convergindo no futuro.

## 8. Veredito

### GO PARCIAL

Há base para uma futura missão de implementação limitada a:

1. fechar o bypass do insight antes de ativar o premium gating;
2. corrigir a distinção entre sentimento neutro e item sem classificação;
3. resolver a divergência documentada da escala do gauge;
4. especificar timestamps e liquidez antes de qualquer mudança estrutural.

Não há base para:

- alterar aliases/provider AXIA por causa de PETR4;
- “corrigir” cache AXIA/PETR4;
- relaxar a geometria de liquidez;
- dividir consensus por 8 sem contrato;
- remover timestamps consumidos;
- inventar texto setorial para JPM/LCID.

O relatório 77A superestimou seis “blockers”: um bypass condicional foi confirmado; a contaminação AXIA/PETR4 foi refutada; liquidez, JPM/LCID, timestamps e consensus possuem sintomas ou ambiguidades reais, mas causas/recomendações da 77A não foram confirmadas integralmente.

## 9. Confirmação de alterações e comparação Git

### Estado esperado após criar este relatório

Comparado ao estado inicial, a única diferença Git atribuível à Missão 77B deve ser:

```text
?? docs/mission_77b_codex_independent_validation.md
```

Todos os demais caminhos modificados, removidos e não rastreados já estavam presentes no estado inicial e não foram limpos, restaurados ou atribuídos à Missão 77A/77B.

### Declaração precisa

- código alterado pela Missão 77B: **nenhum**;
- testes alterados pela Missão 77B: **nenhum**;
- configurações/dependências alteradas: **nenhuma**;
- commit/push/add: **nenhum**;
- arquivo versionável criado: **somente este relatório**;
- estado runtime ignorado alterado incidentalmente: **`runtime/cache/symbol_analysis.json`**, por enqueue de hydration de JPM/LCID; não restaurado.

### Resultado final executado

```text
$ pwd
/home/dcima/stocknewsbr-backend

$ git branch --show-current
fix/audit-remediation-2026-07

$ git rev-parse HEAD
a51c0847f2aa6169388ceb4b34a316600010742c
```

Comparação mecânica:

- `git status --short`: todas as entradas iniciais permaneceram; única entrada adicional:

```text
?? docs/mission_77b_codex_independent_validation.md
```

- `git diff --stat`: resultado final idêntico ao inicial:

```text
49 files changed, 2650 insertions(+), 1602 deletions(-)
```

O relatório não aparece em `git diff --stat` porque é não rastreado.

- `git ls-files --others --exclude-standard`: resultado inicial acrescido somente de:

```text
docs/mission_77b_codex_independent_validation.md
```

Nenhuma entrada inicial desapareceu ou mudou de status na comparação Git. A ressalva do cache runtime ignorado permanece fora dessa comparação.
