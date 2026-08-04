# Missao 28C - Pesquisa institucional multifonte

Data da auditoria: 2026-06-18

Escopo oficial: auditoria institucional dos plugins GitHub, CodeRabbit, Moody's, Binance e Alpaca.

Resultado: relatorio documental. Nenhuma integracao de producao foi criada, nenhuma regra operacional foi alterada e nenhum plugin foi conectado ao caminho critico.

## Sumario executivo

GitHub gera o maior valor imediato para o StockNewsBR porque melhora governanca, rastreabilidade, rollback, revisao e controle de mudancas sem tocar na logica de trading.

Binance gera o maior valor imediato para uma futura frente crypto, pois entregou candles, volume, estatisticas 24h e book de BTC/ETH/SOL/ADA/XRP/BNB via chamadas de leitura. Nao serve para B3, WIN, DOL ou acoes brasileiras.

Moody's gera a maior vantagem competitiva institucional futura para Risk IA, Auditor Institucional e Explainability, porque seus campos de rating, outlook, ownership, subsidiarias, scorecard e drivers de credito podem enriquecer contexto. Nesta auditoria, a conexao exigiu reautenticacao OAuth e nao retornou dados de entidade.

Alpaca tem valor futuro alto para expansao EUA/ETFs e validacao secundaria de candles, OHLC e volume. Confirmou snapshots para AAPL, MSFT, NVDA, TSLA, SPY e QQQ, alem de asset ativo para AAPL. Nao serve para B3: PETR4 retornou asset not found.

CodeRabbit e util para revisao automatica, bugs, code smells, seguranca e performance, mas o CLI nao estava instalado/autenticado nesta sessao. Deve ficar atras de GitHub na prioridade imediata.

## Evidencias coletadas

- GitHub app: repositorio `StockNewsBR/stocknewsbr-backend`, publico, default branch `main`, permissoes admin/push/pull/triage disponiveis.
- Git local: branch ativa `feat/github-workflow-ai-tools`, HEAD `d367937d feat: mission 28B.3 post-hotfix certification`.
- Branches remotas/localizadas: `main`, `feat/github-workflow`, `feat/github-workflow-ai-tools`, `feat/heatmap-service`.
- Pull requests: PR #1, #3 e #4 merged; PR #2 aberto em `feat/heatmap-service`.
- GitHub status checks: commit `d367937d` sem statuses retornados pelo connector.
- `gh pr list`: nao executavel porque `gh` nao esta instalado no PATH desta sessao.
- CodeRabbit skill disponivel, mas `coderabbit --version` e `coderabbit auth status --agent` falharam porque o comando nao esta instalado no PATH.
- Moody's tools disponiveis por schema: entity search, ratings, beneficial owners, subsidiaries, scorecard, credit opinion summary, outlook e upgrade/downgrade factors.
- Moody's live probe: `findEntity` para Petrobras, Vale, Itau Unibanco e Banco do Brasil falhou por `UNAUTHORIZED`, com acao solicitada `TRIGGER_REAUTHENTICATION`.
- Binance live probe: BTCUSDT retornou candles 1m, book depth com 5 niveis e estatisticas 24h.
- Binance live probe: BTCUSDT, ETHUSDT, SOLUSDT, ADAUSDT, XRPUSDT e BNBUSDT retornaram estatisticas 24h e best bid/ask em chamadas individuais.
- Binance limitacao observada: chamadas em lote com `symbols` retornaram erro de parametro duplicado no wrapper; chamadas individuais funcionaram.
- Alpaca live probe: snapshots IEX para AAPL, MSFT, NVDA, TSLA, SPY e QQQ retornaram latest trade, latest quote, minute bar, daily bar e previous daily bar.
- Alpaca live probe: AAPL asset ativo em NASDAQ; PETR4 retornou `asset not found`.
- Alpaca crypto: snapshot/book em lote deram timeout; probes menores retornaram BTC/USD quote, latest bar e 3 daily bars.

## GitHub

Beneficios:

- ALTO para qualidade, porque centraliza PRs, branch discipline, historico e revisao antes de merge.
- ALTO para auditoria, porque cada mudanca fica vinculada a commit, PR, autor, data e diff.
- ALTO para rastreabilidade, porque permite mapear missoes, testes, status e rollback por SHA.
- ALTO para rollback, porque commits e branches criam pontos seguros de retorno.
- ALTO para controle de mudancas, principalmente em areas criticas como scanner, signals, snapshot e workspace.

Riscos:

- Branches longas podem divergir de `main` e misturar missoes.
- PR aberto antigo (#2) pode confundir historico se reaproveitado sem contexto.
- Ausencia de status checks no commit auditado reduz evidencia automatica de CI.
- `gh` nao esta disponivel no PATH, entao parte do fluxo local depende do connector ou do git local.

Impacto:

- Qualidade: ALTO.
- Auditoria: ALTO.
- Rastreabilidade: ALTO.
- Rollback: ALTO.
- Controle de mudancas: ALTO.

Recomendacao:

- Usar imediatamente como camada obrigatoria de governanca.
- Criar PR por missao ou por hotfix logico.
- Exigir evidencias de validacao no corpo do PR antes de merge.
- Nao aceitar mudancas de trading sem diff pequeno, testes e resumo do impacto operacional.

Classificacao final: ALTO.

## CodeRabbit

Beneficios:

- Pode revisar diffs, apontar bugs, code smells, riscos de seguranca, problemas de performance e cobertura.
- Pode ajudar em regressao de arquitetura quando a mudanca toca contratos compartilhados.
- Pode complementar GitHub como revisao automatica antes de merge.
- Pode gerar valor em arquivos criticos com muita superficie de edge case, como snapshot, worker, APIs internas e motores de decisao.

Riscos:

- Nesta sessao, o CLI `coderabbit` nao estava instalado no PATH, entao nenhuma revisao real foi executada.
- Revisor automatico pode gerar falso positivo ou falso negativo; nao substitui validacao de trading.
- Pode nao entender o contrato institucional completo se o contexto da missao nao estiver no PR.
- Pode identificar sintomas sem capturar conflitos de sinal, regime, liquidez ou fluxo institucional.

Capacidade esperada:

- Bugs de producao: MEDIO/ALTO, melhor quando o diff e pequeno e testavel.
- Problemas de arquitetura: MEDIO, depende de contexto e de instrucoes do repo.
- Problemas de cache: MEDIO, bom para inconsistencias obvias, limitado para ciclos reais do worker.
- Problemas de concorrencia: MEDIO, util para locks/estado compartilhado, mas precisa de teste dedicado.
- Problemas de API: ALTO para contrato, validacao e tratamento de erro.
- Seguranca: MEDIO/ALTO para padroes comuns; nao substitui auditoria dedicada.
- Performance: MEDIO, bom para hotspots obvios, limitado sem perfilamento.
- Cobertura: MEDIO, consegue sugerir lacunas, mas nao garante adequacao de cenarios de trading.

Impacto:

- Qualidade de PR: ALTO apos instalacao e autenticacao.
- Auditoria institucional: MEDIO.
- Controle de regressao: MEDIO/ALTO.
- Valor imediato nesta sessao: BAIXO, porque o CLI nao estava operacional.

Recomendacao:

- Ficar como segundo passo depois de GitHub.
- Instalar/autenticar o CLI somente em missao propria de governanca, sem alterar codigo de producao.
- Usar em PRs que toquem areas criticas, mas manter testes e validacao institucional como criterio final.

Classificacao final: MEDIO, com potencial ALTO apos setup.

## Moody's

Beneficios:

- ALTO para Risk IA: rating, outlook, drivers de credito, downgrade/upgrade factors e scorecard podem explicar risco estrutural que preco intraday nao mostra.
- ALTO para Auditor Institucional: ownership, subsidiarias e estrutura empresarial podem alertar sobre complexidade societaria, risco de grupo, controladores e exposicoes indiretas.
- ALTO para Explainability: permite explicar por que uma oportunidade tem risco corporativo maior mesmo quando o setup tecnico parece forte.
- MEDIO/ALTO para Score Mestre como contexto futuro, desde que nao altere regra de score sem missao especifica.

Campos que poderiam enriquecer contexto:

- Long term rating e historico de rating.
- Outlook atual e rationale de outlook.
- Rating drivers, upgrade factors e downgrade factors.
- Scorecard/metodologia e fatores quantitativos/qualitativos.
- Beneficial owners, ownership direto/total e estrutura de controle.
- Subsidiarias, tamanho do grupo e complexidade societaria.
- Setor, classificacoes, pais, matriz e identificadores corporativos.
- ESG/risco qualitativo, se disponivel no conector.

Riscos:

- Plugin exigiu reautenticacao OAuth; dados reais nao foram retornados nesta rodada.
- Nem toda empresa pode ter rating ou cobertura suficiente.
- Dados de credito nao devem virar gatilho operacional intraday sozinho.
- Pode reduzir clareza se misturado diretamente ao Score Mestre sem separacao entre contexto e decisao.
- Campos ausentes precisam aparecer como ausencia de cobertura, nunca como inferencia.

Impacto:

- Risk IA: ALTO.
- Auditor Institucional: ALTO.
- Explainability: ALTO.
- Score Mestre: MEDIO como contexto futuro, sem alterar score agora.
- Ranking operacional imediato: BAIXO ate haver cache/snapshot normalizado.

Recomendacao:

- Ficar para depois de GitHub e Binance, mas como maior vantagem competitiva institucional futura.
- Antes de integrar, resolver OAuth e criar pesquisa offline/cacheada.
- Nunca chamar Moody's diretamente de endpoint publico.
- Usar como enriquecimento contextual normalizado no snapshot, nao como regra isolada de trade.

Classificacao final: ALTO em valor estrategico; readiness atual BAIXO ate reautenticacao.

## Binance

Beneficios:

- ALTO para modulo crypto: fornece candles, OHLC, volume, estatisticas 24h, book, best bid/ask e liquidez de pares crypto.
- ALTO para crypto ranking: pode alimentar volume, range, volatilidade, spread e atividade por par.
- ALTO para crypto radar: pode detectar rompimento, suporte, volume, profundidade e deterioracao de liquidez.
- Boa granularidade para candles 1m e book depth.

Evidencia por ativos auditados:

- BTCUSDT: 24h stats, best bid/ask, candles 1m e book depth funcionaram.
- ETHUSDT: 24h stats e best bid/ask funcionaram.
- SOLUSDT: 24h stats e best bid/ask funcionaram.
- ADAUSDT: 24h stats e best bid/ask funcionaram.
- XRPUSDT: 24h stats e best bid/ask funcionaram.
- BNBUSDT: 24h stats e best bid/ask funcionaram.

Limitacoes:

- Chamada em lote com `symbols` retornou erro de parametro duplicado no wrapper; usar chamadas individuais ou corrigir wrapper em missao futura.
- Nao cobre mercado B3.
- Nao deve ser usada para PETR4, VALE3, ITUB4, BBAS3, BOVA11, WIN ou DOL.
- Latencia variou por chamada individual; precisa de cache e rate-limit antes de qualquer uso de produto.
- Dados crypto podem ter microestrutura diferente de acoes B3 e nao devem contaminar regras de equity.

Confirmacao obrigatoria:

- Binance nao deve ser usada para PETR4.
- Binance nao deve ser usada para VALE3.
- Binance nao deve ser usada para ITUB4.
- Binance nao deve ser usada para BBAS3.
- Binance nao deve ser usada para BOVA11.
- Binance nao deve ser usada para WIN.
- Binance nao deve ser usada para DOL.

Impacto:

- Modulo crypto: ALTO.
- Crypto ranking: ALTO.
- Crypto radar: ALTO.
- B3 equities/futuros: NENHUM.

Recomendacao:

- Usar depois do relatorio 28C como primeiro provider candidato para uma futura trilha crypto.
- Integrar apenas via pesquisa/cache/snapshot.
- Isolar contratos crypto dos contratos B3 para evitar mistura de regime, liquidez e horarios.
- Tratar o erro de batch antes de qualquer worker real.

Classificacao final: ALTO para crypto; NENHUM para B3.

## Alpaca

Beneficios:

- ALTO para expansao EUA: snapshots de AAPL, MSFT, NVDA, TSLA, SPY e QQQ retornaram trade, quote, minute bar, daily bar e previous daily bar.
- ALTO para ETFs EUA: SPY e QQQ retornaram snapshots e barras.
- MEDIO/ALTO para auditoria de market data: pode comparar OHLC, volume, trade_count, VWAP e quote com outras fontes.
- MEDIO/ALTO para validacao de candles e volume em EUA.
- MEDIO para crypto: retornou BTC/USD quote, latest bar e daily bars, mas snapshot/book em lote deram timeout.

Evidencia por ativos auditados:

- AAPL, MSFT, NVDA, TSLA, SPY, QQQ: snapshots retornaram 6 registros via feed IEX.
- AAPL: barras diarias retornaram 4 registros nos ultimos 5 dias de calendario.
- AAPL asset: ativo NASDAQ, `us_equity`, status active, tradable, shortable e fractionable.
- PETR4 asset: `asset not found`.
- BTC/USD: quote, latest bar e daily bars funcionaram em probes menores.

Serve para B3?

NAO.

Justificativa:

- PETR4 retornou `asset not found`.
- O plugin e orientado a acoes/ETFs EUA, opcoes e crypto, com feeds como IEX/SIP/delayed SIP/OTC/overnight.
- Mesmo quando houver ADR/BDR correlato, isso nao substitui PETR4, VALE3, ITUB4, BBAS3, BOVA11, WIN ou DOL.

Riscos:

- Feed IEX pode ter cobertura/quote parcial e diferir de SIP completo.
- Alguns quotes retornaram ask 0 em MSFT/SPY, entao validacao de qualidade e obrigatoria.
- Crypto snapshot/book maior pode dar timeout.
- Dados EUA nao devem ser usados para inferir execucao B3.

Impacto:

- Expansao EUA: ALTO.
- Auditoria de market data: MEDIO/ALTO.
- Validacao de candles: ALTO para EUA.
- Validacao de volume: MEDIO/ALTO para EUA.
- B3: NENHUM.

Recomendacao:

- Usar depois de GitHub/Binance quando a expansao EUA for prioritaria.
- Comecar com snapshots e barras cacheados, nunca com chamada direta em endpoint publico.
- Marcar feed e qualidade explicitamente (`iex`, `sip`, `delayed_sip`, `crypto_us`) para evitar confusao operacional.

Classificacao final: MEDIO/ALTO.

## Comparacao final

Ranking oficial da Missao 28C:

1o lugar: GitHub.

Motivo: maior valor imediato para governanca, auditoria, PRs, rollback e rastreabilidade com risco operacional baixo.

2o lugar: Binance.

Motivo: melhor evidencia live para um futuro modulo crypto, com candles, volume, book e 24h stats funcionais.

3o lugar: Moody's.

Motivo: maior vantagem competitiva futura em risco institucional e explicabilidade, mas depende de reautenticacao e cache.

4o lugar: Alpaca.

Motivo: bom para EUA/ETFs e validacao secundaria, sem serventia para B3.

5o lugar: CodeRabbit.

Motivo: bom complemento de qualidade, mas nesta sessao ficou limitado pela ausencia do CLI/autenticacao.

Maior valor imediato: GitHub.

Maior valor futuro: Moody's.

Primeiro plugin para futura integracao de dados: Binance, se a proxima trilha for crypto; Moody's, se a proxima trilha for risco institucional; Alpaca, se a proxima trilha for EUA/ETFs.

## Impacto por modulo

| Modulo | GitHub | CodeRabbit | Moody's | Binance | Alpaca |
| --- | --- | --- | --- | --- | --- |
| Noticias IA | MEDIO | BAIXO | MEDIO | BAIXO | BAIXO |
| Macro IA | BAIXO | BAIXO | ALTO | BAIXO | MEDIO |
| Risk IA | MEDIO | MEDIO | ALTO | MEDIO | MEDIO |
| Auditor Institucional | ALTO | MEDIO | ALTO | MEDIO | MEDIO |
| Explainability | MEDIO | MEDIO | ALTO | MEDIO | MEDIO |
| Ranking | MEDIO | MEDIO | BAIXO | ALTO para crypto | MEDIO para EUA |
| Telegram | MEDIO | BAIXO | BAIXO | BAIXO | BAIXO |
| Push | MEDIO | BAIXO | BAIXO | BAIXO | BAIXO |
| Android | MEDIO | BAIXO | BAIXO | MEDIO para crypto | MEDIO para EUA |
| Community | MEDIO | BAIXO | BAIXO | BAIXO | BAIXO |

Observacao: impacto em Ranking, Telegram, Push, Android e Community e indireto e futuro. Nenhum plugin deve alterar sinais, notificacoes ou UI nesta missao.

## Arquitetura futura recomendada

Fluxo obrigatorio:

```text
Plugin
↓
Pesquisa
↓
Normalizacao
↓
Cache
↓
Snapshot
↓
Engine
↓
API
↓
Web/App/Telegram
```

Regra de arquitetura:

- Nenhum plugin pode entrar diretamente na API publica.
- Nenhum endpoint HTTP deve chamar provider externo de mercado no caminho critico.
- Toda pesquisa deve ser read-only, normalizada, cacheada, versionada e propagada via snapshot.
- Dados externos devem carregar `source`, `timestamp`, `quality`, `coverage`, `latency` e `staleness`.
- Campos ausentes devem ser tratados como ausencia explicita, nao como fallback inventado.

## O que usar agora

- GitHub para governanca de missao, PR, rollback, trilha de auditoria e separacao de escopo.
- Relatorios `docs/` para registrar pesquisas institucionais sem mexer na producao.

## O que usar depois

- Binance para uma missao futura de crypto, com cache/snapshot e contrato separado de B3.
- Moody's para risco institucional, depois de reautenticacao e desenho de contrato de contexto.
- Alpaca para expansao EUA/ETF, com qualidade de feed explicita.
- CodeRabbit para revisao automatica quando o CLI estiver instalado e autenticado.

## O que nao vale a pena agora

- Integrar qualquer provider diretamente no worker/API sem missao propria.
- Usar Binance para B3.
- Usar Alpaca para PETR4/VALE3/ITUB4/BBAS3/BOVA11/WIN/DOL.
- Alterar Score Mestre com Moody's antes de ter cache, snapshot e contrato de explainability.
- Rodar CodeRabbit como criterio unico de aprovacao.

## Maior vantagem competitiva

Moody's e o plugin com maior vantagem competitiva futura para o StockNewsBR, porque pode transformar Risk IA, Auditor Institucional e Explainability em leitura mais institucional, com rating, outlook, ownership e estrutura de credito.

GitHub e o plugin com maior valor imediato, porque melhora governanca sem aumentar risco de trading.

## Criterio de aprovacao

- Todos os plugins autorizados foram auditados: SIM.
- Beneficios documentados: SIM.
- Limitacoes documentadas: SIM.
- Impacto documentado: SIM.
- Ranking final criado: SIM.
- Integracao em producao criada: NAO.
- Regra operacional alterada: NAO.
- Score Mestre, Ranking, Worker, Snapshot Engine, Decision Envelope, Telegram, Push, Frontend e Banco de Dados alterados: NAO.

## Validacao

- Auditoria documental baseada em probes read-only e estado local/remoto.
- Nenhum teste funcional de trading foi necessario, pois nao houve mudanca de codigo operacional.
- `git diff --check -- docs/mission_28c_institutional_plugin_audit.md` executado sem erro.
- `Select-String -Pattern '[ \t]+$'` no relatorio novo executado sem ocorrencias.
- `git status --short` confirmou que a unica alteracao nova da Missao 28C e `docs/mission_28c_institutional_plugin_audit.md`; os demais arquivos modificados ja estavam no worktree antes desta auditoria.

## Riscos remanescentes

- Moody's precisa de reautenticacao para confirmar campos reais por entidade.
- CodeRabbit precisa de CLI instalado e autenticado para medir achados reais.
- Binance precisa correcao/contorno para chamada batch antes de uso automatizado.
- Alpaca precisa regra de qualidade para quotes parciais, feed IEX vs SIP e timeouts crypto.
- Esta missao nao aprova lancamento de produto e nao altera a regra absoluta de nao lancar antes da Missao 35.
