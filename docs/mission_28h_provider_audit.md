# Missao 28H - Auditoria institucional dos providers e plugins

Data da auditoria: 2026-06-18

Escopo: auditoria institucional read-only dos plugins Quartr, Moody's, Binance, Alpaca, GitHub e CodeRabbit.

Resultado: relatorio documental. Nenhuma integracao em producao foi criada. Nenhuma logica operacional, Score Mestre, Ranking, Radar Institucional, Worker, Frontend, API ou banco foi alterado.

## Decisao executiva

O StockNewsBR deve usar imediatamente GitHub como base de governanca e rastreabilidade.

Binance deve ser o primeiro candidato futuro para uma frente crypto, porque respondeu melhor em candles, book, quotes e volume.

Alpaca deve ficar como candidato futuro para acoes EUA, ETFs e validacao secundaria de market data. Nao serve para B3.

Moody's deve ficar para pesquisa adicional e futura camada institucional de credito/risco, condicionada a reautenticacao.

Quartr tem alto valor para contexto corporativo e earnings, mas no ambiente atual exige Quartr Pro e nao esta pronto para uso.

CodeRabbit deve permanecer como ferramenta auxiliar de revisao quando houver CLI suportado/autenticado. Nesta sessao, o CLI nao rodou no Windows.

Nenhum plugin entra diretamente na API publica, no worker ou no caminho critico. Qualquer uso futuro deve seguir:

```text
Plugin
-> Pesquisa
-> Normalizacao
-> Cache
-> Snapshot
-> Engine
-> API
-> Web/App/Telegram
```

## Etapa 1 - Inventario completo

| Plugin | Categoria | O que faz | Dados fornecidos | Cobertura observada | Utilidade | Valor StockNewsBR | Complexidade | Risco operacional |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Quartr | Research/IR | Pesquisa empresas, eventos, documentos e conferencias | Earnings, transcripts, slides, reports, releases, IR, commentary | Tools disponiveis, mas acesso bloqueado por plano Pro | Contexto corporativo e earnings | ALTO futuro | MEDIA/ALTA | Custo/plano, licenca, latencia, cobertura por empresa |
| Moody's | Credit/entity intelligence | Pesquisa risco corporativo, ratings e estrutura empresarial | Ratings, outlook, ownership, subsidiaries, scorecard, credit drivers | Tools disponiveis, mas OAuth invalido | Risco institucional e explainability | ALTO futuro | ALTA | Auth, custo, cobertura, risco de misturar credito com trade intraday |
| Binance | Market data crypto | Dados de mercado spot/derivativos crypto | Candles, quotes, order book, 24h stats, volume | BTC/ETH/SOL/ADA/XRP/BNB responderam | Crypto ranking/radar | ALTO para crypto | MEDIA | Rate limit, simbolos, volatilidade, nao serve B3 |
| Alpaca | Market data EUA/ETF/crypto | Dados de acoes EUA, ETFs, opcoes e crypto | Quotes, snapshots, bars, assets, clock, crypto quotes/bars | EUA/ETF responderam em chamadas pequenas; B3 nao encontrada | EUA/ETF e auditoria de dados | MEDIO/ALTO | MEDIA | Feed IEX parcial, timeouts em lote, B3 ausente |
| GitHub | DevOps/governanca | Repo, branches, PRs, commits, reviews e status | PRs, branches, historico, status checks, arquivos | Repo e PRs acessiveis | Governanca e rastreabilidade | ALTO imediato | BAIXA/MEDIA | Branches antigas, PR aberto antigo, ausencia de workflows |
| CodeRabbit | Code review AI | Revisao automatica de diffs | Bugs, smells, seguranca, performance, cobertura | CLI nao instalado; instalador nao suporta MSYS Windows | Auxiliar de PR | MEDIO futuro | MEDIA | Dependencia de CLI/auth/SO; nao substitui teste de trading |

## Etapa 2 - Auditoria Quartr

Ferramentas Quartr disponiveis no ambiente:

- `search_companies`
- `get_company`
- `list_documents`
- `read_document`
- `get_document_summary`
- `search_documents`
- `list_conferences`
- `get_conference`
- `read_live_transcript`
- watchlist/tag/keyword tools, nao usados por serem mutacoes ou organizacionais

Empresas testadas:

- AAPL
- MSFT
- NVDA
- AMZN
- GOOGL
- META

Resultado do probe:

- Todas as chamadas `search_companies` falharam com `subscription_required`.
- Mensagem operacional: Quartr Pro subscription required.
- Plano atual retornado: `none`.
- Portanto, nao foi possivel validar documentos reais nesta sessao.

Cobertura esperada pelo schema:

- Earnings: SIM, via transcripts, reports e event documents.
- Conference Calls: SIM, via events/transcripts/live transcript.
- Transcricoes: SIM, via `read_document(eventId)` e transcript documents.
- Guidance: SIM, por busca em documentos/transcricoes, quando coberto.
- Investor Relations: SIM, via company profile/documents.
- Apresentacoes institucionais: SIM, via slides.
- Releases corporativos: SIM, via reports/press releases.
- Management commentary: SIM, via transcripts e summaries.

Impacto por modulo:

| Modulo | Quartr agrega valor? | Justificativa |
| --- | --- | --- |
| News IA | SIM | Transcricoes, releases e guidance melhoram contexto alem de headlines. |
| Explainability | SIM | Permite explicar motivo corporativo por tras de risco, guidance e resultado. |
| Radar Institucional | SIM | Eventos de earnings/calls podem virar contexto de atencao, nao sinal direto. |
| Auditor Institucional | SIM | Ajuda a checar se uma leitura tecnica conflita com comentario da gestao. |
| Workspace | SIM | Pode enriquecer cards institucionais e contexto de empresa. |

Limitacoes:

- Acesso bloqueado por plano Pro nesta sessao.
- Requer licenca/custo antes de qualquer uso real.
- Cobertura B3 precisa ser validada separadamente.
- Nao deve virar provider de sinal no caminho critico.

Recomendacao Quartr:

- Nao entra agora.
- Merece pesquisa adicional apos habilitar Quartr Pro.
- Prioridade futura: ALTA para Noticias IA, Explainability e Auditor Institucional.

## Etapa 3 - Auditoria Moody's

Ferramentas Moody's disponiveis no ambiente:

- `findEntity`
- `getEntityRatings`
- `getEntityBeneficiaryOwners`
- `getEntitySubsidiaries`
- `getEntityScorecard`
- `getEntityCreditOpinionSummary`
- `getEntityCreditOpinionOutlook`
- upgrade/downgrade factors
- earnings call search

Probe executado:

- Busca unica com AAPL, MSFT, NVDA, AMZN, GOOGL, META, Petrobras, Vale e Itau.
- Resultado: `UNAUTHORIZED`.
- Motivo: `oauth_token_invalid_grant`.
- Acao solicitada pelo plugin: `TRIGGER_REAUTHENTICATION`.

Cobertura esperada pelo schema:

- Ratings: SIM.
- Ownership: SIM.
- Credit Risk: SIM.
- Research/Credit Opinion: SIM.
- Filings: parcialmente, dependendo dos tools/documentos disponiveis na conta.
- Entity Intelligence: SIM.

Impacto por modulo:

| Modulo | Moody's agrega valor? | Justificativa |
| --- | --- | --- |
| Score Mestre | SIM como contexto futuro, NAO como alteracao agora | Rating/outlook podem enriquecer contexto de risco, mas nao devem alterar calculo sem missao propria. |
| Radar Institucional | SIM | Risco de credito, outlook e downgrade factors podem reduzir prioridade de setups frageis. |
| Auditor Institucional | SIM | Ownership, subsidiarias e ratings ajudam a auditar risco corporativo estrutural. |
| Explainability | SIM | Explica por que um ativo pode exigir cautela mesmo com setup tecnico positivo. |

Limitacoes:

- OAuth invalido nesta sessao.
- Pode haver empresas unrated ou cobertura incompleta.
- Custo/licenca provavelmente relevante em uso continuo.
- Dados de credito sao lentos/estruturais; nao substituem fluxo, book, liquidez e regime intraday.

Recomendacao Moody's:

- Nao entra agora por readiness.
- Fica como pesquisa adicional obrigatoria para Risk IA, Auditor Institucional e Explainability.
- Qualquer integracao futura deve ser cacheada e rotulada como contexto, nao gatilho operacional.

## Etapa 4 - Auditoria Binance

Ativos testados:

- BTCUSDT
- ETHUSDT
- SOLUSDT
- ADAUSDT
- XRPUSDT
- BNBUSDT

Testes executados:

- 24h ticker stats para os 6 pares.
- Candles 1m para os 6 pares.
- Best bid/ask para os 6 pares.
- Order book depth com 5 niveis para BTCUSDT e ETHUSDT.

Resultado resumido:

| Par | Candles | Quotes/bid-ask | Volume 24h | Order book |
| --- | --- | --- | --- | --- |
| BTCUSDT | OK | OK | OK | OK, depth 5 |
| ETHUSDT | OK | OK | OK | OK, depth 5 |
| SOLUSDT | OK | OK | OK | Best bid/ask OK |
| ADAUSDT | OK | OK | OK | Best bid/ask OK |
| XRPUSDT | OK | OK | OK | Best bid/ask OK |
| BNBUSDT | OK | OK | OK | Best bid/ask OK |

Snapshots:

- Binance nao expôs um endpoint chamado snapshot nesta lista de tools, mas `24h ticker + kline + book ticker + depth` compoe um snapshot operacional suficiente para pesquisa crypto.

Binance e o melhor provider crypto?

SIM, para o ambiente atual.

Justificativa:

- Respondeu com alta cobertura para os 6 ativos exigidos.
- Entregou candles, volume, bid/ask e order book.
- Tem granularidade melhor para microestrutura crypto do que Alpaca nesta sessao.

Comparacao Binance vs Alpaca em crypto:

| Criterio | Binance | Alpaca |
| --- | --- | --- |
| Cobertura dos 6 criptoativos | ALTA | Nao testada nos 6; BTC/USD OK |
| Candles | OK para todos testados | BTC/USD latest bar OK |
| Order book | OK para BTC/ETH depth; best bid/ask para todos | Order book maior deu timeout em rodada anterior; nao foi confiavel |
| Volume | 24h volume OK | BTC/USD volume muito menor/limitado |
| Latencia percebida | Algumas chamadas lentas, mas funcionais | Timeouts em lote e stock; chamadas pequenas funcionais |
| Melhor para crypto ranking/radar | SIM | NAO como principal |

Limitacoes:

- Binance nao deve ser usada para PETR4, VALE3, ITUB4, BBAS3, BOVA11, WIN ou DOL.
- Dados crypto devem ficar isolados de regras B3.
- Precisa de cache/rate-limit.
- Chamada em lote com `symbols` ja havia apresentado erro de parametro duplicado no wrapper em auditoria anterior; chamadas individuais sao mais seguras.

Recomendacao Binance:

- Entra no roadmap futuro somente para crypto.
- Nao entra em producao nesta missao.
- Prioridade: ALTA para crypto radar/ranking.

## Etapa 5 - Auditoria Alpaca

Ativos EUA/ETF testados:

- AAPL
- MSFT
- NVDA
- TSLA
- SPY
- QQQ

Ativos B3 testados:

- PETR4
- VALE3
- ITUB4

Testes executados:

- AAPL snapshot IEX: OK, com latest trade, latest quote, minute bar, daily bar e previous daily bar.
- MSFT snapshot IEX: OK, mas latest quote retornou ask 0, exigindo qualidade de quote.
- NVDA latest quote IEX: OK.
- TSLA snapshot IEX: OK.
- SPY snapshot IEX: OK, mas latest quote retornou ask 0, exigindo qualidade de quote.
- QQQ snapshot IEX: OK.
- SPY asset: OK, ETF ARCA ativo.
- AAPL asset: OK, equity NASDAQ ativo.
- Market clock: OK, mercado fechado em 2026-06-18 17:03:55 -04:00; next open 2026-06-22 09:30 -04:00.
- BTC/USD crypto quote/latest bar: OK.
- PETR4 asset: `asset not found`.
- VALE3 asset: `asset not found`.
- ITUB4 asset: `asset not found`.

Observacoes operacionais:

- Chamada grande de snapshots/quotes/bars em lote deu timeout.
- Chamadas menores funcionaram bem.
- Uma chamada `get_stock_latest_bar` aceitou schema publicado com `symbol`, mas backend reclamou `symbol_or_symbols`; ha inconsistencia de schema/handler a registrar.

Alpaca serve para:

| Mercado | SIM/NAO | Justificativa |
| --- | --- | --- |
| Acoes EUA | SIM | AAPL, MSFT, NVDA e TSLA retornaram snapshot/quote/bar em chamadas pequenas. |
| ETFs | SIM | SPY e QQQ retornaram snapshot; SPY asset ativo em ARCA. |
| Crypto | SIM, secundario | BTC/USD quote e bar funcionaram, mas Binance foi superior para crypto. |
| B3 | NAO | PETR4, VALE3 e ITUB4 retornaram asset not found. |

Recomendacao Alpaca:

- Futuro para EUA/ETFs.
- Pode servir como validador secundario de candles/volume.
- Nao usar para B3.
- Antes de integrar, tratar timeouts, schema mismatch e qualidade de feed IEX vs SIP.

## Etapa 6 - Auditoria GitHub

Repositorio:

- `StockNewsBR/stocknewsbr-backend`.
- Default branch: `main`.
- Visibilidade: publica.
- Permissoes da conexao: admin, maintain, pull, push e triage.

Branches encontradas:

- `main`.
- `feat/github-workflow`.
- `feat/github-workflow-ai-tools`.
- `feat/heatmap-service`.

Estado local:

- Branch ativa: `feat/github-workflow-ai-tools`.
- HEAD: `d367937d feat: mission 28B.3 post-hotfix certification`.
- Worktree ja estava sujo antes desta missao, com arquivos operacionais da Missao 29 e relatorio 28C untracked.

Pull requests:

- PR #1 merged: estrutura inicial/GitHub workflow.
- PR #3 merged: `feat/github-workflow-ai-tools`.
- PR #4 merged: `Feat/GitHub workflow ai tools`.
- PR #2 aberto: `feat/heatmap-service`, antigo, com titulo duplicado e comentario Codex sem major issues.

Status checks:

- Connector retornou lista vazia de statuses para `d367937d`.

Workflows:

- `.github/workflows` nao existe no checkout.
- Portanto, nao ha CI localmente versionado para validar tests/lint/build automaticamente.

GitHub esta bem organizado?

NAO completamente.

Pontos positivos:

- Repo remoto acessivel.
- PRs e branches rastreaveis.
- Historico de commits claro por missoes.
- Branch principal e branch de trabalho identificaveis.

Riscos de manutencao:

- PR #2 aberto desde marco de 2026 aparenta branch antiga/orfa.
- `feat/github-workflow` e `feat/heatmap-service` parecem historicas e devem ser revisadas/arquivadas ou fechadas.
- Ausencia de `.github/workflows` reduz governanca automatica.
- Sem status checks no HEAD auditado.
- Branch `main` local aparece divergente (`ahead 1, behind 2`) em relacao ao remoto.
- Worktree local contem alteracoes de outra missao; commits futuros precisam isolar escopo.

Relatorio GitHub:

- Branches orfas: PROVAVEL, principalmente `feat/github-workflow` e `feat/heatmap-service`.
- Workflows mortos: NAO encontrados; o risco real e ausencia de workflows versionados.
- Codigo abandonado: PROVAVEL no PR #2/heatmap-service.
- Riscos de manutencao: SIM, por PR antigo, ausencia de checks e branch local divergente.

Recomendacao GitHub:

- Entra agora como governanca.
- Fechar ou atualizar PR #2.
- Criar CI em missao futura propria.
- Proteger `main` com checks antes de qualquer go-live.

## Etapa 7 - Auditoria CodeRabbit

Objetivo solicitado:

- Executar review de leitura.
- Focar market providers, market services, snapshot cache, ranking, quotes e worker.
- Nao alterar codigo.

Resultado operacional:

- `coderabbit --version`: comando nao encontrado.
- `where.exe coderabbit`: nao encontrado.
- Instalador oficial via `curl -fsSL https://cli.coderabbit.ai/install.sh | sh` falhou inicialmente porque `sh` nao encontrava utilitarios Unix.
- Reexecucao com `C:\Users\dcima\.codex\tools\mingit-2.54.0\usr\bin` no PATH avancou, mas falhou com `Unsupported operating system: msys_nt-10.0-26200`.
- Portanto, CodeRabbit nao executou review real nesta sessao.

Conclusao CodeRabbit:

- Nao ha issues CodeRabbit a reportar porque o review nao rodou.
- Nao foi feito fallback fingindo que review manual era CodeRabbit.

Leitura local complementar, nao atribuida ao CodeRabbit:

Arquivos lidos/amostrados:

- `app/cache/snapshot_cache.py`
- `app/cache/market_data_cache.py`
- `app/services/ranking.py`
- `app/services/quote_service.py`
- `app/api/routes_public_market_live.py`
- `app/engine/market_snapshot_engine.py`
- `worker.py`

Riscos observados:

| Area | Risco | Severidade | Observacao |
| --- | --- | --- | --- |
| `app/services/ranking.py` | Uso de `pd.Series`/`pd.DataFrame` sem import visivel de pandas no trecho lido | MEDIO | Fallback de ranking por provider pode quebrar se executado; caminho padrao usa snapshot e pode mascarar o problema. |
| `app/services/ranking.py` | `except Exception: continue` no loop de fallback | MEDIO | Pode esconder erro por simbolo sem metrica detalhada. |
| `app/cache/market_data_cache.py` | Provider yfinance ainda existe fora do caminho HTTP | MEDIO | Esta protegido por `current_provider_call_source() == "http"`, mas qualquer uso futuro deve manter provider fora de endpoints. |
| `app/cache/snapshot_cache.py` | `except Exception: pass` em limpeza de runtime de teste | BAIXO | Aceitavel em cleanup, mas pode ocultar erro de higiene em teste. |
| `worker.py` | Muitas etapas isoladas em `try/except` | BAIXO/MEDIO | Bom para resiliencia, mas exige metricas/logs para nao criar falhas silenciosas. |
| Alpaca tool wrapper | Schema publicado divergiu do handler em `get_stock_latest_bar` | BAIXO/MEDIO | Risco de integracao se automatizar sem teste de contrato. |

Duplicacoes/oportunidades:

- Logica de alias para CME/B3 mini futures aparece em `quote_service.py` e `routes_public_market_live.py`; pode ser centralizada futuramente sem alterar comportamento.
- Ranking tem caminho legado de calculo tecnico por provider, mas arquitetura atual deve privilegiar snapshot. Manter esse fallback bem bloqueado e testado.
- Providers externos devem continuar atras de cache/worker, nunca em endpoint publico.

Recomendacao CodeRabbit:

- Nao entra agora como gate obrigatorio.
- Fica como auxiliar quando houver ambiente suportado/autenticado.
- Em Windows, considerar rodar CodeRabbit via WSL/Linux/CI em missao propria.

## Etapa 8 - Comparacao final

| Plugin | Valor estrategico | Valor operacional | Facilidade de uso | Cobertura | Potencial futuro | Risco |
| --- | --- | --- | --- | --- | --- | --- |
| Quartr | ALTO | BAIXO atual, ALTO futuro | BAIXA atual | Bloqueada por plano | ALTO | MEDIO/ALTO |
| Moody's | ALTO | BAIXO atual, ALTO futuro | BAIXA atual | Bloqueada por OAuth | ALTO | ALTO |
| Binance | ALTO para crypto | ALTO para crypto | MEDIA | ALTA nos 6 criptoativos | ALTO | MEDIO |
| Alpaca | MEDIO/ALTO | MEDIO/ALTO EUA/ETF | MEDIA | Boa EUA/ETF; nenhuma B3 | MEDIO/ALTO | MEDIO |
| GitHub | ALTO | ALTO | ALTA | Repo/PR/branch | ALTO | BAIXO/MEDIO |
| CodeRabbit | MEDIO | BAIXO atual | BAIXA atual no Windows | Bloqueada por CLI/SO | MEDIO | MEDIO |

## Etapa 9 - Ranking final dos plugins

1o GitHub.

Maior valor imediato, baixo risco e essencial para rastreabilidade, rollback, PRs e governanca.

2o Binance.

Melhor provider crypto testado, com candles, volume, bid/ask e order book funcionando nos ativos exigidos.

3o Alpaca.

Forte para acoes EUA e ETFs, util como validador secundario. Nao cobre B3.

4o Moody's.

Maior valor institucional futuro para credito, risco e explainability, mas bloqueado por OAuth nesta sessao.

5o Quartr.

Alto potencial para earnings/calls/guidance, mas bloqueado por plano Pro.

6o CodeRabbit.

Bom auxiliar futuro, mas nao operacional no Windows desta sessao.

## Etapa 10 - Decisao objetiva

O que entra no StockNewsBR agora:

- GitHub como governanca operacional.
- Nenhum provider de mercado externo entra em producao nesta missao.

O que nao entra:

- Binance para B3.
- Alpaca para B3.
- Quartr sem plano Pro.
- Moody's sem OAuth valido.
- CodeRabbit como gate obrigatorio sem CLI suportado/autenticado.

O que fica para futuro:

- Binance para modulo crypto/radar/ranking crypto.
- Alpaca para EUA/ETFs.
- Moody's para Risk IA, Auditor Institucional e Explainability.
- Quartr para Noticias IA, earnings, calls e workspace institucional.
- CodeRabbit em CI/WSL/Linux para revisao automatica.

O que merece pesquisa adicional:

- Quartr Pro e cobertura real de B3/US mega caps.
- Moody's reautenticado e cobertura por empresa B3.
- Alpaca SIP vs IEX e qualidade de quote.
- Binance rate limits, batch wrapper e normalizacao de simbolos.
- GitHub workflows/checks e branch cleanup.
- CodeRabbit em ambiente suportado.

## Criterios de sucesso

- Quartr auditado: SIM, com bloqueio de plano documentado.
- Moody's auditado: SIM, com bloqueio OAuth documentado.
- Binance auditada: SIM.
- Alpaca auditada: SIM.
- GitHub auditado: SIM.
- CodeRabbit auditado: SIM, com falha operacional documentada.
- Ranking final criado: SIM.
- Relatorio criado: SIM.
- Logica alterada: NAO.
- Endpoint alterado: NAO.
- Calculo alterado: NAO.
- Integracao criada: NAO.

## Validacao

- Probes read-only executados via plugins autorizados.
- Leitura local complementar executada sem edicao de codigo.
- `docs/mission_28h_provider_audit.md` criado como unico arquivo novo desta missao.
- `Select-String -Pattern '[ \t]+$'` no relatorio novo executado sem ocorrencias.
- `git ls-files --others --exclude-standard docs/mission_28h_provider_audit.md` confirmou o arquivo novo.
- `git status --short` confirmou que os demais arquivos modificados ja estavam no worktree antes desta auditoria.
- Testes funcionais/tsc nao foram executados porque a missao e documental e nao alterou codigo operacional.

## Riscos remanescentes

- Quartr precisa plano Pro antes de validar documentos reais.
- Moody's precisa reautenticacao OAuth.
- CodeRabbit precisa ambiente suportado/autenticado.
- Alpaca teve timeouts em lote e exige tratamento de qualidade.
- Binance precisa cache/rate-limit e isolamento de contratos crypto.
- GitHub precisa limpeza de branches/PR antigo e CI versionado.

## Commit sugerido

`docs: mission 28h institutional providers audit`
