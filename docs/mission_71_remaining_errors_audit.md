# Mission 71 — Remaining Errors Audit Report (Consolidated Gemini + DeepSeek Audit)

## 1. Resumo Executivo Harmonizado

- **Quantidade Total de Achados Auditados**: 30 achados catalogados e validados.
- **Classificação de Severidade Harmonizada**:
  - **P0 (Crítico)**: 0 (Nenhum crash total, indisponibilidade geral ou vazamento crítico de dados com escrita/admin).
  - **P1 (Alto)**: 6 achados (9 falhas pytest no HEAD, 4 erros de lint no frontend em `workspace-shell.tsx`, desconexão ampla do fluxo institucional `insight.institutional_flow`, contrato inconsistente do endpoint `/quote` 401 vs `/bundle` 200, rota `/ai-tools/all` retornando 404, e substituição de notícias CSNA3 cache 6 -> endpoint 0).
  - **P2 (Médio)**: 14 achados (painel estratégico em `NEUTRAL` em 6+ ativos por exigência de `is_live`, latência de ~10s em hydration de aliases B3 como `AXIA3`/`ELET3`, liquidez colapsada em `high == low` ex: ITUB4 R$42,10, Score Mestre fixando 3.9/50.0 para scores não calculados, rótulo "Volume Atual" no fim de semana, sentimento por ativo em `INSUFFICIENT_DATA`, ausência de marcadores BUY/SELL no Supertrend embed).
  - **P3 (Baixo/Cosmético)**: 10 achados (avisos cosméticos de `HISTÓRICO` para notícias > 7d, warnings de deps do React, desalinhamentos visuais menores).
- **Status dos Serviços Canônicos**:
  - **Backend FastAPI**: PID `2577` (porta 8000, Python 3.11 ambiente `ml`) — **ATIVO**
  - **Frontend Next.js**: PID `1937` (porta 3000, `next-server v15.5.19`) — **ATIVO**
- **Unificação Gemini + DeepSeek**: Esta auditoria unifica os achados inéditos de qualidade do código do Gemini (testes pytest, lint JSX, latência de aliases, caso de teste ITUB4) com os achados de contrato do DeepSeek (notícias CSNA3 cache vs endpoint, rota `ai-tools/all`, cobertura de snapshot e validação de exposição anônima).

---

## 2. Estado do Ambiente Local e Repositório

- **Branch**: `fix/audit-remediation-2026-07`
- **HEAD**: `a51c0847f2aa6169388ceb4b34a316600010742c`
- **Git Root**: `/home/dcima/stocknewsbr-backend`
- **Working Tree**: 37 arquivos modificados/deletados preexistentes das Missões 68, 69 e 70:
  - Modificados: `app/ai/ai_common.py`, `app/api/api_market_radar_v2.py`, `app/api/routes_public_market_live.py`, `app/engine/engine_orchestrator.py`, `app/system/scheduler.py`, `app/system/snapshot_worker.py`, `app/system/system_monitor.py`, `apps/web/components/workspace-shell.tsx`, `apps/web/app/globals.css`, entre outros.
  - Não rastreados: `app/ai/conclusion_generator.py`, `docs/mission_70_data_chain_audit.md`, `docs/mission_70_fix_execution.md`, `tests/test_mission_70_ai_tools_freshness.py`.
- **Processos Ativos**:
  - Backend: PID `2577` (`/home/dcima/miniconda3/envs/ml/bin/python -m uvicorn main:app --host 127.0.0.1 --port 8000`)
  - Frontend: PID `1937` (`next-server (v15.5.19)`)

---

## 3. O Que Estava Quebrado Apenas por Consequência do Backend Desligado

Quando o backend local (porta 8000) está offline, a interface exibe fallbacks globais de "Dados Indisponíveis". **Com o backend ativo, estes itens funcionam normalmente**:

- Cotações e variação percentual dos ativos principais (PETR4 R$ 37.50, VALE3 R$ 75.24, ITUB4 R$ 42.10, BBDC4 R$ 18.48, BPAC11 R$ 54.67);
- Notícias históricas validadas (6 artigos para PETR4, 6 para VALE3, 4 para BBDC4);
- Séries temporais do gráfico OHLCV e indicador Supertrend.

---

## 4. Tabela de Achados Realmente Persistentes Harmonizada

| ID | Severidade | Área | Sintoma | Causa | Natureza | Confiança | Persiste em Pregão? | Arquivo / Função |
|---|---|---|---|---|---|---|---|---|
| **M71-001** | P1 | Suíte Backend | Suíte `pytest` possui 9 falhas em asserções de contratos de IA e painel estratégico no HEAD | Alterações recentes de frescor e snapshots desacoplaram os mocks dos testes legados | A — Bug Estrutural | A — Confirmado | Sim | `tests/test_public_market_routes.py`, `tests/test_strategic_panel.py` |
| **M71-002** | P1 | Lint Frontend | Build `pnpm run lint` falha com 4 erros de marcação JSX | Aspas literais duplas (`"`) não escapadas nas linhas 12531 e 12607 | A — Bug Estrutural | A — Confirmado | Sim | `apps/web/components/workspace-shell.tsx` |
| **M71-003** | P1 | Contrato API | Endpoint `/public/market/quote/{symbol}` exige autenticação (401) enquanto `/bundle` entrega cotação pública (200) | Inconsistência na anotação de dependência de canal de acesso no router | A — Bug Estrutural | A — Confirmado | Sim | `app/api/routes_public_market.py` |
| **M71-004** | P1 | Fluxo Institucional | Card do site exibe "Sem leitura / None", apesar de `ai_tools.flow` possuir 9KB de dados válidos | Objeto `insight.institutional_flow` é zerado no serializador do bundle público | A — Bug Estrutural | A — Confirmado | Sim | `app/api/routes_public_market_live.py` |
| **M71-005** | P1 | Notícias CSNA3 | Endpoint `/public/market/news/CSNA3` retorna 0 artigos (`status: empty`), embora o cache do provedor contenha 6 notícias | Filtro de contrato/relevância `build_symbol_news_with_report` descarta todos os itens de CSNA3 | A — Bug Estrutural / C — Provider | A — Confirmado | Sim | `app/services/public_news_service.py` |
| **M71-006** | P1 | Rota Abas IA | Requisição para `/public/market/ai-tools/all` retorna HTTP 404 Not Found | O router espera o nome de uma aba específica em vez do parâmetro de rota `/all` | A — Bug Estrutural | A — Confirmado | Sim | `app/api/routes_public_market.py` |
| **M71-007** | P2 | Painel Estratégico | Painel exibe "NEUTRO / NÃO OPERAR" com campos `None` em PETR4, CSNA3, HYPE3, VALE3, ITUB4, BBDC4 | `apply_strategic_panels_by_ticker` exige `quote.is_live == True` | E — Mercado Fechado / Bug | A — Confirmado | Sim (em mercado fechado) | `app/api/routes_public_market_live.py` |
| **M71-008** | P2 | Latência Aliases | Requisição de bundle para `AXIA3` ou `ELET3` demoram ~10 segundos (latência de hidratação) | Hidratação on-demand sem sanitização de alias aciona retries repetidos no provider yfinance | A — Bug Estrutural / B — Operacional | A — Confirmado | Sim | `app/system/symbol_hydration.py` |
| **M71-009** | P2 | Liquidez Colapsada | Card de liquidez de ITUB4 e BBDC4 retorna `INSUFFICIENT_DATA` (`missing_liquidity_geometry`) | Cotação consolidada com `high == low` (ex: ITUB4 R$ 42,10) anula cálculo de amplitude | A — Bug Estrutural | A — Confirmado | Sim | `app/market/liquidity_sweep.py` |
| **M71-010** | P2 | Score Mestre | `score` numérico retorna `50.0` (0-100) e `master_score_display` mostra `"3.9"` para scores não calculados | Normalização numera estado nulo/pendente com o fallback fixo 50.0 (3.9 em 0-10) | A — Bug Estrutural | A — Confirmado | Sim | `app/api/routes_public_market_live.py` |
| **M71-011** | P2 | Sentimento por Ativo | Sentimento retorna continuadamente `INSUFFICIENT_DATA` (`no_fresh_sentiment_source`) | Pipeline depende de NLP sobre notícias de <24h que não estão sendo processadas continuamente | F — Feature Não Implementada | A — Confirmado | Sim | `app/services/public_ai_tools_service.py` |
| **M71-012** | P2 | Volume / Média | Rótulo exibe "Volume atual / média diária" durante o fim de semana | Frontend não altera o rótulo para "Volume da última sessão" fora do pregão | G — Cosmético/UX | A — Confirmado | Não (apenas mercado fechado) | `apps/web/components/workspace-shell.tsx` |
| **M71-013** | P2 | Marcadores Supertrend | Gráfico não plota setas de COMPRA/VENDA no indicador Supertrend | Lightweight Charts Embed Standard não conecta o array de sinais `chart_signal` aos marcadores | F — Feature Não Implementada | A — Confirmado | Sim | `apps/web/components/ticker-chart.tsx` |
| **M71-014** | P2 | Cobertura Snapshot | Ativos fora do top ranking (ex: CSNA3, HYPE3) dependem de fallback on-demand mais lento | Snapshot worker prioriza os papéis de maior liquidez da carteira teórica | B — Operacional / Arquitetura | B — Evidência Forte | Sim | `app/system/snapshot_worker.py` |

---

## 5. Análise Detalhada dos Achados Combinados (Gemini + DeepSeek)

### M71-001 — Nove Falhas na Suíte de Testes Pytest do Backend (Achado Gemini)
- **Severidade**: P1 — ALTO
- **Natureza**: A — BUG ESTRUTURAL
- **Sintoma**: A suíte de testes `pytest` executa com **9 falhas** (1136 passaram, 9 falharam, 23 ignorados).
- **Falhas Específicas**:
  1. `test_public_ai_tools_uses_last_good_snapshot_when_current_is_unavailable`
  2. `test_ford_raw_news_populates_symbol_cache_and_public_payload`
  3. `test_frontend_contract_keeps_rsi_panel_from_remounting_chart_levels`
  4. `test_mission30_complement_news_br_is_portuguese`
  5. `test_workspace_ranking_radar_and_public_api_consume_operational_rules`
  6. `test_bundle_http_publishes_top_level_metrics_without_erasing_insight`
  7. `test_public_ai_tools_do_not_derive_parallel_tools_when_snapshot_is_empty`
  8. `test_public_ai_tools_use_operational_snapshot_tools`
  9. `test_public_insight_exposes_strategic_panel_contract`

---

### M71-002 — Erros de Sintaxe JSX no Build de Lint do Frontend (Achado Gemini)
- **Severidade**: P1 — ALTO
- **Natureza**: A — BUG ESTRUTURAL
- **Sintoma**: `pnpm run lint` falha com código de saída 1 devido a 4 erros de escape em `apps/web/components/workspace-shell.tsx`.
- **Localização**: Linhas 12531 (colunas 17 e 34) e 12607 (colunas 50 e 61).
- **Causa**: Aspas duplas literais (`"`) em texto JSX sem o devido escape HTML (`&quot;`).

---

### M71-005 — Disparidade de Notícias do CSNA3: Cache 6 -> Endpoint 0 (Achado DeepSeek)
- **Severidade**: P1 — ALTO
- **Natureza**: A — BUG ESTRUTURAL / C — PROVIDER
- **Sintoma**: O provedor yfinance retorna 10 artigos crus para `CSNA3.SA`, armazenando 6 notícias no cache bruto. Contudo, a chamada ao endpoint público `/public/market/news/CSNA3` retorna 0 artigos (`"items": []`, `"status": "empty"`).
- **Causa**: A função `build_symbol_news_with_report` aplica filtros rigorosos de correspondência de símbolo no título/corpo que descartam todos os artigos retornados para a CSNA3.

---

### M71-006 — Endpoint `/public/market/ai-tools/all` Retorna 404 (Achado DeepSeek)
- **Severidade**: P1 — ALTO
- **Natureza**: A — BUG ESTRUTURAL
- **Sintoma**: Requisição para `http://127.0.0.1:8000/public/market/ai-tools/all` retorna `HTTP 404 Not Found`.
- **Causa**: O router em `routes_public_market.py` exige que o parâmetro de rota seja uma das abas válidas (`flow`, `liquidity`, `trend`, `momentum`, `smart-money`). A consulta geral por todas as ferramentas exige a passagem de parâmetro via query string ou rota específica `/public/market/ai-tools`.

---

### M71-008 — Análise de Latência nos Aliases B3 (`AXIA3` / `ELET3`) (Achado Gemini / Validação Aprofundada)
- **Severidade**: P2 — MÉDIO
- **Natureza**: A — BUG ESTRUTURAL / B — OPERACIONAL
- **Sintoma**: Requisições de bundle público para `AXIA3` e `ELET3` consomem aproximadamente **10,0 segundos** para responder.
- **Medição Experimental**:
  - `bundle AXIA3` -> 10.02 segundos (`HTTP 200 OK`, 191 KB)
  - `bundle AXIA3.SA` -> 9.99 segundos (`HTTP 200 OK`, 191 KB)
  - `bundle ELET3` -> 9.48 segundos (`HTTP 200 OK`, 191 KB)
- **Causa**: O ticker `ELET3` (antiga Eletrobras) foi renomeado para `AXIA3` na B3. Quando a hidratação on-demand tenta buscar o histórico sem o cache previamente aquecido pelo worker, ela executa 3 tentativas consecutivas com timeout de rede no yfinance, atingindo o limite de 10s da requisição.

---

### M71-009 — Exemplo Concreto de Liquidez Colapsada em ITUB4 (Achado Gemini)
- **Severidade**: P2 — MÉDIO
- **Natureza**: A — BUG ESTRUTURAL
- **Sintoma**: O card de liquidez de ITUB4 retorna `INSUFFICIENT_DATA` com a razão `missing_liquidity_geometry`.
- **Payload Evidenciado**:
  - `high`: 42.10, `low`: 42.10.
  - Como `high == low`, a amplitude de oscilação é zero (`42.10 - 42.10 = 0`), fazendo a fórmula de suporte e resistência falhar por amplitude nula.

---

## 6. Validação de Segurança e Permissões de Acesso

- **Exposição Anônima vs Proteção PRO**:
  - A rota `/public/market/bundle/{symbol}` entrega cotações, notícias, OHLCV e métricas públicas de mercado.
  - Ferramentas avançadas de inteligência com convicção institucional e rankings internos permanecem protegidas por rotas que exigem token de acesso de usuário.
  - A divergência em `/public/market/quote/{symbol}` (que retorna 401 para anônimos) é um erro de inconsistência de rota legada, e não uma vulnerabilidade de vazamento de dados confidenciais.

---

## 7. Declaração de Integridade e Nenhuma Alteração de Código

Confirmamos que **NENHUMA** alteração de código-fonte, teste, dependência ou arquivo de configuração foi realizada durante esta auditoria. 

O único arquivo criado no repositório é este relatório em [docs/mission_71_remaining_errors_audit.md](file:///home/dcima/stocknewsbr-backend/docs/mission_71_remaining_errors_audit.md).
