# Missao 31C - Rabbit Critical Cleanup

## Status

Status operacional da Missao 31C: `PENDING_FINAL_CODERABBIT_RECHECK`.

Matriz de testes atual: `PASS_WITH_HISTORICAL_DEPENDENCIES_CLASSIFIED`.

CodeRabbit final limpo: `PENDING`.

Nenhum commit ou push foi executado.

Este relatorio ja inclui os ajustes feitos depois da ultima rodada do CodeRabbit. O status so pode virar `PASS` se a proxima revisao `coderabbit review --agent -t uncommitted -c AGENTS.md` concluir sem Critical/Major bloqueador e nenhuma alteracao nova for feita depois dela.

## Contrato Estabilizado

- `master_score_raw`: escala interna canonica `0..100`.
- `master_score` e `score` publico: escala de produto `0..10`.
- `master_score_source_scale`: origem explicita usada para derivar o display.
- Metadata explicita sempre vence.
- Compatibilidade legada sem metadata: valores `11..100` sao inferidos como raw `0..100`; valores `0..10` permanecem display `0..10`.
- Valor explicitamente marcado como `0_10` acima de `10` continua bloqueador.
- Push so emite raw quando a escala e explicita ou inferivel com seguranca pelo valor `11..100`.

## Arquivos Alterados

- `app/ai/ai_master_score.py`
- `app/ai/final_decision.py`
- `app/ai/trade_decision.py`
- `app/api/routes_public_market_live.py`
- `app/services/ranking.py`
- `app/services/score_display.py`
- `app/services/snapshot_contract.py`
- `app/services/workspace_service.py`
- `app/system/performance_intelligence.py`
- `app/system/push_dispatcher.py`
- `app/system/system_metrics.py`
- `app/telegram/telegram_alert_engine.py`
- `app/telegram/telegram_alert_formatter.py`
- `app/web/routes_radar.py`
- testes de contrato historico e regressao em `tests/`
- `tests/test_mission_31c_critical_cleanup.py`

## Correcoes Aplicadas

- Score Mestre foi centralizado em contrato raw/display unico.
- Ranking, Radar, Snapshot, Performance Intelligence, metricas, Telegram e Push consomem score display `0..10` sem promover raw invalido.
- Ranking normaliza payload legado `11..100` sem metadata como raw, mas rejeita valor invalido quando a escala explicita for `0_10`.
- Snapshot separa warning informativo de raw normalizado dos warnings bloqueadores de score invalido/clampado.
- Push preserva payload coerente para `master_score_raw` e nao inventa raw para valor `0..10` sem metadata.
- API publica e Workspace agora expoem `master_score` em `0..10`, preservam `master_score_raw` em `0..100` e propagam `master_score_source_scale`.
- `summarize_trade_decision` preserva `source_signal` real no caminho precomputado, permitindo bloquear conflito entre origem e decisao final.
- Auditoria ausente/invalida em `final_decision` preserva o fallback neutro historico; auditoria `0.0` explicita continua respeitada.

## Gate 31A-3

Runner oficial localizado: `python -m unittest tests.test_mission_31a3_coderabbit_triage -v`.

Execucao nesta maquina Windows: `venv\\Scripts\\python.exe -m unittest tests.test_mission_31a3_coderabbit_triage -v`.

Evidencia:

- `apps/web/package.json` nao possui `test:mission31a3`.
- `apps/web/scripts` nao possui script `mission-31a3`.
- A checagem de alias/script usa `apps/web` porque e ali que os scripts `mission*` do shell Next.js vivem; `app/web/` segue como superficie ativa da landing HTML/workspace, enquanto `app/Frontend/` cobre a area legada.
- A evidencia da branch aponta para `tests/test_mission_31a3_coderabbit_triage.py`, `docs/mission_31a3_coderabbit_triage_backlog.md` e logs `runtime/mission31a3_*`.

Resultado final: `PASS`, 8 testes.

## Scripts Historicos

Baseline usado para a 31C: `HEAD` pre-diff local `3e3d167c2190f8576e20019904f9bd23fd48b099`. O merge-base com `origin/main` nao e baseline valido para estes scripts porque naquele ponto os scripts mission ainda nao existiam.

Falhas historicas provadas contra o baseline `HEAD` e repetidas no diff atual:

- `test:mission25d`: FAIL. Falha: labels de suporte/resistencia removidos. Dono: Missao 31E.
- `test:mission28b`: FAIL. Falha: contador `Todos` nao agrega todas as categorias monitoradas. Dono: Missao 31G ou correcao previa de UI.
- `test:mission30e`: FAIL. Falhas: noticias antigas sem marcador e PETR4 sem URL original visivel. Dono: Missao 31D/31G.
- `test:mission30f`: FAIL. Falha: PETR4 noticia sem titulo/fonte/url/data/idade. Dono: Missao 31D/31G.
- `test:mission30f2`: FAIL. Falhas: suporte/resistencia ainda nao `card_only`, overlays customizados ainda presentes e noticia ELET6 pertencendo a AXIA6. Dono: Missao 31E e 31D/31G.

Scripts executados e nao bloqueadores da 31C depois da classificacao historica:

- `test:mission30`: PASS, 101 checks.
- `mission-30d-final-audit`: PASS na execucao isolada final, `failures: []`.
- `test:mission31a`: PASS.
- `test:mission31a2`: PASS, `failureCount = 0`.

Criterio formal aplicado nesta 31C: scripts mission historicos que falham igual no `HEAD` pre-31C, nao pertencem ao diff de cleanup da 31C e possuem missao proprietaria atribuida ficam registrados como dependencias externas, nao como bloqueadores da limpeza critica 31C.

## Testes

Backend:

- `venv\\Scripts\\python.exe -m unittest tests.test_mission_31c_critical_cleanup tests.test_ranking_service tests.test_market_pulse_actionable tests.test_mission_26_signal_outcome_audit tests.test_final_decision tests.test_institutional_priority tests.test_historical_confidence tests.test_operational_rules tests.test_institutional_conviction tests.test_institutional_radar tests.test_institutional_auditor tests.test_institutional_ranking tests.test_mission_28b2_regressions tests.test_mission_24c_go_live_runtime tests.test_strategic_panel tests.test_master_score_institutional tests.test_telegram_institutional -v` -> PASS, 153 testes.
- `venv\\Scripts\\python.exe -m unittest discover tests` -> PASS, 494 testes.
- `venv\\Scripts\\python.exe -m unittest tests.test_mission_31a3_coderabbit_triage -v` -> PASS, 8 testes.

Frontend:

- `npm --prefix apps/web run tsc` -> PASS.
- Scripts mission listados acima executados no diff atual.

Diff:

- `git diff --check` deve ser executado imediatamente antes do CodeRabbit final; warnings CRLF sao esperados pelo ambiente Git/Windows.

## CodeRabbit

- CLI: `coderabbit 0.6.4`.
- Auth agent: autenticado como `StockNewsBR`.
- Comando: `coderabbit review --agent -t uncommitted -c AGENTS.md`.
- Rodada CodeRabbit anterior encontrou 9 issues: 5 Major e 4 Minor; todas corrigidas.
- Rodada CodeRabbit intermediaria encontrou 16 issues: 5 Major e 11 Minor; todas corrigidas.
- Rodada CodeRabbit mais recente encontrou 18 issues: 12 Major e 6 Minor; todas corrigidas.
- Rodada CodeRabbit de recheck encontrou 13 issues: 6 Major e 7 Minor; todas corrigidas antes desta atualizacao.
- Majors corrigidos:
  - inferencia segura de escala ausente em Ranking para valores `11..100`;
  - preservacao de hint `0_100` em `score_display`;
  - Push sem raw inventado para `0..10` sem metadata;
  - fixture de prioridade Telegram com par raw/display valido;
  - cobertura de `source_signal` no caminho precomputado de `summarize_trade_decision`.
- Minors corrigidos:
  - doc de `app/web/`;
  - fixtures `market_pulse`;
  - helper `_row` em `test_final_decision`;
  - fixture de ranking no teste da Missao 26.
- Correcoes da rodada mais recente:
  - normalizacao antes de descartar candidatos em `score_display`;
  - inferencia sem metadata de qualquer valor `>10` como raw `0_100`, com invalidacao acima de `100` feita pelo normalizador;
  - ranking sem forcar `ranking_opportunity_score=8` como raw apenas por coincidir com `master_score_raw`;
  - Push preservando legacy score explicitamente `0_100` mesmo abaixo de `10`;
  - helpers historicos com par `master_score`/`master_score_raw` coerente quando `master_score_source_scale=0_10`;
  - cobertura `market_pulse` para escala `0_10` e mixed-scale;
  - propagacao de `master_score_source_scale` na canonicalizacao 28B.2.
- Correcoes da rodada final de majors/minors:
  - `resolve_master_score_display_value` ignora display invalido atual sem preservar warning obsoleto quando existe candidato valido;
  - Radar web ordena score legado `11..100` pela escala publica canonica;
  - Push trata `master_score_raw` como raw `0..100` independente da escala de display e converte score explicito `0_10` para raw quando seguro;
  - Ranking devolve `score_source_scale="0_10"` nos payloads normalizados e registra falhas de fallback por simbolo;
  - fixtures historicos normalizam `score` e `ranking_opportunity_score` quando suas escalas sao `0_10`;
  - API publica e Workspace ganharam cobertura de `master_score`, `master_score_raw` e `master_score_source_scale`;
  - Telegram ganhou cenario display-only `0_10`.
- Correcoes do recheck de 13 issues:
  - `score_source_scale` passou a ser preservado no merge de `apply_master_scores_by_ticker`;
  - hints invalidos de escala agora falham explicitamente em vez de cair em inferencia silenciosa;
  - `master_score`/`score` ja publicos em `0..10` nao sao renormalizados por hint `0_100` quando `master_score_raw` nao existe;
  - ranking calculado sem escala explicita nao cria `master_score_raw` para score display `0..10`;
  - Workspace canonicaliza tambem `master_score`, `master_scores`, `institutional_radar`, `institutional_ranking`, `operational_rules` e `final_decisions` vindos do snapshot;
  - testes reforcados para `market_snapshot`, Telegram, Strategic Panel, ranking eligibility e plural `master_scores`.
- A revisao final pos-relatorio ainda precisa concluir sem Critical/Major bloqueador para o status `PASS` ser valido.

## Historico De Assertions

- `tests/test_mission_28b_commercial_readiness.py`: nao enfraquecido; passou a exigir escala explicita e preserva raw `0..100`.
- `tests/test_mission_30_canonical_symbol_registry.py`: nao enfraquecido; mantem validacao de warning e separa debug de raw normalization.
- `tests/test_mission_31a3_coderabbit_triage.py`: nao enfraquecido; runner oficial continua com 8 testes e contrato explicito.
- `tests/test_ranking_service.py`: fortalecido com dedupe mixed-scale, compatibilidade legada `11..100`, rejeicao de score explicitamente invalido e contrato `0..10`.
- `tests/test_mission_31c_critical_cleanup.py`: novo contrato focado da 31C cobrindo ranking, snapshot, Push, Telegram, metricas e trade decision.

## Impacto

- Logica de trading: sem alteracao de pesos do Score Mestre e sem alteracao de regras BUY/SELL/SHORT/COVER.
- Snapshot/ranking/API/frontend/Telegram/Push: contrato de score ficou consistente entre raw interno `0..100` e display publico `0..10`.
- Providers externos: nenhum provider novo foi adicionado.
- Risco operacional: reduz falso score positivo, evita payload incoerente e bloqueia score publico explicitamente invalido.

## Pendencias Fora Da 31C

- 31E: suporte/resistencia, overlays e criterio `card_only`.
- 31D/31G: metadados/idade/URL de noticias e relacionamento ELET6/AXIA6.
- 31G ou correcao previa: contador `Todos`.
