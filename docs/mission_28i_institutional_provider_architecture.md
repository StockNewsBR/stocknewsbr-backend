# Missao 28I - Arquitetura de providers institucionais

Data da arquitetura: 2026-06-18

Escopo: consolidacao documental da arquitetura futura para Quartr, Moody's, Binance, Alpaca, GitHub e CodeRabbit.

Resultado: decisao arquitetural. Nenhum provider foi integrado em producao, nenhum endpoint foi criado e nenhuma logica operacional foi alterada.

## Resumo executivo

O Snapshot Interno permanece como fonte unica do produto.

Nenhum provider externo pode entrar no caminho critico. A API publica, o frontend, Telegram, Push e a engine de sinais nao podem chamar providers externos ao vivo.

Fluxo permitido:

```text
Provider externo
-> Connector
-> Normalizer
-> Provider Cache
-> Snapshot Interno
-> Engine / Auditor
-> API / Web / App / Telegram / Push
```

Decisao principal:

- Entra agora: GitHub como governanca e esta documentacao de arquitetura.
- Entra futuramente: Binance para crypto, Alpaca para EUA/ETFs, Quartr para earnings/IR e Moody's para risco institucional.
- Fica como auxiliar: CodeRabbit para revisao automatica, quando houver CLI suportado/autenticado.
- Nao entra: qualquer chamada direta de provider em API publica, frontend, Telegram, Push ou engine de sinal.

## Status das missoes anteriores

### Missao 28C

Arquivo lido: `docs/mission_28c_institutional_plugin_audit.md`

Status registrado:

- GitHub auditado e classificado como maior valor imediato.
- Binance auditada e funcional para BTC/ETH/SOL/ADA/XRP/BNB.
- Alpaca auditada para EUA/ETFs e sem cobertura B3 para PETR4.
- Moody's tentou rodar, mas exigiu reautenticacao OAuth.
- CodeRabbit tentou rodar, mas CLI nao estava instalado/autenticado.
- Nenhuma integracao em producao foi criada.

### Missao 28H

Arquivo lido: `docs/mission_28h_provider_audit.md`

Status registrado:

- Binance funcionou muito bem para crypto.
- Alpaca funcionou para acoes EUA e ETFs.
- Alpaca nao possui cobertura real B3 para PETR4, VALE3 e ITUB4.
- Quartr ficou bloqueado por `subscription_required`.
- Moody's ficou bloqueado por OAuth/`UNAUTHORIZED`.
- CodeRabbit nao rodou no Windows/MSYS.
- GitHub funcionou como governanca.
- Nenhuma integracao em producao foi criada.

## Ranking final dos providers

Ranking por readiness e valor imediato, conforme 28C/28H:

1. GitHub
2. Binance
3. Alpaca
4. Moody's
5. Quartr
6. CodeRabbit

Ranking por valor estrategico futuro, quando credenciais e cache existirem:

1. Quartr
2. Moody's
3. Binance
4. Alpaca
5. GitHub
6. CodeRabbit

Leitura final:

- GitHub tem maior valor imediato.
- Quartr e Moody's tem maior valor institucional futuro.
- Binance e o melhor provider crypto testado.
- Alpaca e o melhor candidato para EUA/ETFs.
- CodeRabbit e ferramenta auxiliar, nao provider de mercado.

## Papel de cada provider

### Quartr

Tipo: Institutional / IR / Earnings.

Status atual: instalado, mas 28H registrou bloqueio por plano Quartr Pro / `subscription_required`.

Papel futuro:

- Earnings calls.
- Conference calls.
- Transcripts.
- Guidance.
- Investor Relations.
- Apresentacoes corporativas.
- Releases corporativos.
- Management commentary.

Pode enriquecer:

- News IA.
- Fundamental IA futura.
- Explainability.
- Auditor Institucional.
- Risk IA.
- Score Mestre como contexto.

Nao pode:

- Gerar BUY/SELL/SHORT/COVER.
- Virar dependencia para sinal.
- Ser chamado pela API publica.
- Ser chamado pelo frontend.
- Substituir snapshot interno.

### Moody's

Tipo: Institutional Risk / Credit / Ownership.

Status atual: instalado, mas 28C/28H registraram OAuth invalido e `UNAUTHORIZED`.

Papel futuro:

- Ratings.
- Risco corporativo.
- Credito.
- Outlook.
- Ownership.
- Entity intelligence.
- Filings.
- Research.

Pode enriquecer:

- Risk IA.
- Auditor Institucional.
- Explainability.
- Score Mestre como contexto.
- Decisao de `NAO OPERAR AGORA`, quando risco critico confirmado estiver normalizado no snapshot.

Nao pode:

- Gerar sinal sozinho.
- Substituir Auditor Institucional.
- Ser chamado em tempo real pela API.
- Sobrescrever Score Mestre.
- Forcar `READY`.

### Binance

Tipo: Crypto Market Data.

Status atual: funcionando para BTC/ETH/SOL/ADA/XRP/BNB nas auditorias.

Papel futuro:

- Crypto Radar.
- Crypto Ranking.
- Crypto Alerts.
- BTCUSD.
- ETHUSD.
- SOLUSD.
- XRPUSD.
- ADAUSD.
- BNBUSD.

Pode enriquecer:

- Area crypto.
- Candles crypto.
- Volume crypto.
- Order book crypto.
- Volatilidade crypto.
- Liquidez crypto.

Nao pode:

- Ser fallback para PETR4.
- Ser fallback para VALE3.
- Ser fallback para ITUB4.
- Ser fallback para BBAS3.
- Ser fallback para BOVA11.
- Ser usado em WIN/DOL.
- Substituir provider B3.
- Contaminar regras de acoes B3.

### Alpaca

Tipo: US Market Data / ETF / Secondary Crypto.

Status atual: funcionando para AAPL/MSFT/NVDA/TSLA/SPY/QQQ em chamadas pequenas; nao cobre B3 diretamente.

Papel futuro:

- Acoes EUA.
- ETFs.
- SPY.
- QQQ.
- AAPL.
- MSFT.
- NVDA.
- TSLA.
- Validacao de candles EUA.
- Expansao internacional.

Pode enriquecer:

- USA workspace.
- USA radar futuro.
- ETF monitoring.
- Market data lab.
- Validacao secundaria de candles e volume.

Nao pode:

- Substituir dados B3.
- Ser provider principal do produto BR.
- Ser fallback para PETR4/VALE3/ITUB4.
- Ser chamado direto pela API publica.
- Inferir execucao B3 por ADR/ETF correlato.

### GitHub

Tipo: Governance / Change Control.

Papel atual:

- Historico.
- Branches.
- Commits.
- Pull Requests.
- Rollback.
- Auditoria.
- Rastreabilidade de missoes.

Pode enriquecer:

- Governanca de codigo.
- Revisao institucional.
- Rastreabilidade.
- Qualidade de release.
- Controle de escopo e rollback.

Nao e:

- Provider de mercado.
- Provider de dados financeiros.
- Fonte de sinais.
- Dependencia operacional do produto em runtime.

### CodeRabbit

Tipo: Code Review / Static Review.

Status atual: 28H registrou indisponibilidade no Windows/MSYS.

Papel futuro:

- Revisao automatica.
- Bugs silenciosos.
- Payload quebrado.
- Duplicacao.
- Qualidade.
- Risco de regressao em PRs.

Nao e:

- Provider de mercado.
- Dependencia operacional.
- Fonte de dados.
- Gate unico de aprovacao.
- Substituto de teste de trading.

## Arquitetura oficial

```text
Provider Layer
  |-- QuartrConnector
  |-- MoodysConnector
  |-- BinanceConnector
  |-- AlpacaConnector
  |-- GitHub governance tools
  `-- CodeRabbit review tools

Normalization Layer
  |-- SymbolNormalizer
  |-- EventNormalizer
  |-- MarketDataNormalizer
  |-- RiskDataNormalizer
  `-- ProviderQualityNormalizer

Cache Layer
  |-- provider_event_cache
  |-- provider_market_cache
  |-- provider_risk_cache
  |-- provider_transcript_cache
  `-- provider_health_cache

Snapshot Layer
  |-- context_quartr
  |-- context_moodys
  |-- context_binance
  |-- context_alpaca
  |-- enrichment_status
  `-- provider_quality_flags

Engine Layer
  |-- Score Mestre
  |-- Auditor Institucional
  |-- Decision Envelope
  `-- Explainability

Delivery Layer
  |-- API
  |-- Web
  |-- App
  |-- Telegram
  `-- Push
```

Regras oficiais:

- Provider Layer nunca entrega direto para Delivery Layer.
- Normalization Layer converte simbolos, eventos, dados de mercado, risco e qualidade.
- Cache Layer absorve latencia, rate limit, erro e indisponibilidade.
- Snapshot Layer e a unica superficie consumida por engine/API/UI.
- Engine Layer pode usar contexto de provider apenas como enriquecimento auditavel.
- Delivery Layer nunca sabe credencial, endpoint ou payload bruto de provider.

## Schemas futuros

Estes schemas sao propostas documentais. Nenhuma tabela real foi criada nesta missao.

### ProviderEvent

Campos:

- `provider`
- `source_type`
- `symbol`
- `canonical_symbol`
- `asset_class`
- `market`
- `timestamp`
- `title`
- `summary`
- `sentiment`
- `relevance`
- `confidence`
- `raw_payload_ref`
- `quality_flags`

Uso:

- Quartr events.
- Earnings releases.
- Corporate events.
- IR documents.
- News IA context.

### ProviderMarketData

Campos:

- `provider`
- `symbol`
- `canonical_symbol`
- `asset_class`
- `timeframe`
- `open`
- `high`
- `low`
- `close`
- `price`
- `volume`
- `bid`
- `ask`
- `spread`
- `timestamp`
- `latency_ms`
- `quality_flags`

Uso:

- Binance crypto candles/book.
- Alpaca EUA/ETF quotes/bars.
- Validacao secundaria de mercado.

### ProviderRiskData

Campos:

- `provider`
- `symbol`
- `canonical_symbol`
- `rating`
- `outlook`
- `credit_risk`
- `sector_risk`
- `ownership_signal`
- `entity_quality`
- `timestamp`
- `confidence`
- `quality_flags`

Uso:

- Moody's ratings.
- Credit risk.
- Ownership/contexto societario.
- Auditor Institucional e Risk IA.

### ProviderTranscriptData

Campos:

- `provider`
- `symbol`
- `canonical_symbol`
- `event_type`
- `quarter`
- `fiscal_year`
- `event_date`
- `title`
- `summary`
- `management_tone`
- `guidance_change`
- `risk_mentions`
- `transcript_ref`
- `confidence`
- `quality_flags`

Uso:

- Quartr transcripts.
- Earnings calls.
- Guidance commentary.
- Explainability.

### ProviderHealth

Campos:

- `provider`
- `status`
- `last_success_at`
- `last_error_at`
- `latency_ms`
- `error_count`
- `rate_limit_remaining`
- `is_available`
- `is_stale`

Uso:

- Health administrativo.
- Provider fallback.
- Decisao de degradacao.
- Alertas internos, nao alertas premium de trade.

## Cache e TTL sugeridos

| Provider | Dado | TTL sugerido |
| --- | --- | --- |
| Binance | Crypto candles | 30s a 60s |
| Binance | Order book | 5s a 15s |
| Binance | Ticker 24h | 60s |
| Alpaca | US quotes | 30s a 60s |
| Alpaca | US bars | 60s a 5min |
| Alpaca | Market clock | 5min |
| Quartr | Earnings/transcripts | 6h a 24h |
| Quartr | Guidance/IR | 6h a 24h |
| Moody's | Ratings/credit | 24h a 7 dias |
| Moody's | Ownership/research | 24h a 7 dias |
| GitHub | PR/branch/status metadata | 5min a 30min para painel interno |
| CodeRabbit | Review result | Por commit/PR, imutavel salvo novo diff |

Regra de TTL:

- Quanto mais operacional e volatel, menor TTL.
- Quanto mais institucional e estrutural, maior TTL.
- Todo cache deve carregar `last_success_at`, `last_error_at`, `is_stale` e `quality_flags`.

## Fallback

Ordem oficial:

1. Usar snapshot atual valido.
2. Usar ultimo snapshot valido.
3. Rodar analise degradada sem provider premium.
4. Se dado critico faltar, retornar `NAO OPERAR AGORA`.

Nunca:

- Inventar preco.
- Inventar volume.
- Inventar noticia.
- Gerar sinal com provider falhando.
- Gerar alerta premium com dado invalido.
- Promover ativo por dado stale sem aviso.
- Trocar provider B3 por Binance ou Alpaca.

Estados recomendados:

- `provider_available`
- `provider_unavailable`
- `provider_stale`
- `provider_partial`
- `provider_unauthorized`
- `provider_subscription_required`
- `provider_timeout`
- `provider_rate_limited`
- `premium_context_unavailable`

## Decision Envelope

Como providers podem afetar o Decision Envelope no futuro:

Permitido:

- Adicionar `warnings`.
- Adicionar `context`.
- Adicionar `quality_flags`.
- Adicionar `blockers` se provider indicar risco critico confirmado e normalizado.
- Enriquecer `human_message`.
- Explicar degradacao por provider indisponivel.

Proibido:

- Provider decidir `action` sozinho.
- Provider sobrescrever BUY/SELL/SHORT/COVER.
- Provider sobrescrever Score Mestre.
- Provider forcar `READY`.
- Provider remover bloqueio do Auditor Institucional.
- Provider transformar dado institucional lento em gatilho intraday.

Exemplos futuros permitidos:

- Moody's com downgrade/outlook critico pode adicionar warning ou blocker contextual.
- Quartr com guidance negativo pode enriquecer `human_message` e Explainability.
- Binance com book crypto degradado pode adicionar warning de liquidez crypto.
- Alpaca com quote parcial ou ask 0 pode adicionar quality flag e impedir promocao de ativo EUA.

## Impacto por modulo

| Provider | News IA | Risk IA | Macro IA | Score Context | Auditor | Explainability | Ranking | Push | Telegram |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Quartr | ALTO | MEDIO | MEDIO | MEDIO | ALTO | ALTO | BAIXO | BAIXO | BAIXO |
| Moody's | BAIXO | ALTO | MEDIO | MEDIO | ALTO | ALTO | BAIXO | BAIXO | BAIXO |
| Binance | BAIXO | MEDIO | BAIXO | MEDIO para crypto | MEDIO para crypto | MEDIO | ALTO para crypto | MEDIO futuro | MEDIO futuro |
| Alpaca | BAIXO | MEDIO | MEDIO | MEDIO para EUA | MEDIO | MEDIO | MEDIO para EUA/ETF | BAIXO | BAIXO |
| GitHub | NENHUM | NENHUM | NENHUM | NENHUM | MEDIO governanca | MEDIO governanca | NENHUM | NENHUM | NENHUM |
| CodeRabbit | NENHUM | NENHUM | NENHUM | NENHUM | MEDIO qualidade | MEDIO qualidade | NENHUM | NENHUM | NENHUM |

Observacao:

- Ranking/Push/Telegram so podem consumir provider indiretamente via Snapshot Interno.
- GitHub e CodeRabbit impactam governanca de produto, nao decisao de mercado.

## O que entra agora

Entra agora:

- GitHub como governanca.
- Documentacao de arquitetura 28I.
- Regra formal de que providers externos nao entram no caminho critico.

Nao entra agora:

- Integracao operacional Binance.
- Integracao operacional Alpaca.
- Integracao operacional Quartr.
- Integracao operacional Moody's.
- CodeRabbit como gate obrigatorio.
- Qualquer nova rota publica.
- Qualquer novo worker.
- Qualquer chamada de provider em API, frontend, Telegram, Push ou engine de sinal.

Entra futuramente:

- Binance para Crypto Radar/Ranking.
- Alpaca para USA/ETF.
- Quartr para Earnings/IR.
- Moody's para Risk/Institutional.
- CodeRabbit em CI/WSL/Linux, se suportado.

## Plano por fases

### Fase 0 - Agora

- Documentacao e decisao arquitetural.
- Nenhuma integracao.
- Nenhuma mudanca operacional.
- Manter Snapshot Interno como fonte unica.

### Fase 1 - Provider Health

- Monitorar disponibilidade dos plugins.
- Registrar auth, plano, latencia, rate limit e ultimo sucesso.
- Nao alimentar produto ainda.

### Fase 2 - Cache Offline

- Ingestao offline sem afetar producao.
- Persistir payload bruto por referencia, nao no snapshot direto.
- Validar normalizacao, qualidade e stale.

### Fase 3 - Snapshot Enrichment

- Adicionar campos opcionais no snapshot.
- Campos devem ser nullable/degradaveis.
- Frontend/API devem funcionar sem provider.

### Fase 4 - Explainability

- Usar providers para explicar, nao decidir.
- Priorizar Quartr/Moody's como contexto humano e auditoria.
- Registrar warnings e incerteza.

### Fase 5 - Alerts Premium

- Somente depois de validacao.
- Alertas premium nao podem depender de provider ao vivo.
- Se provider falhar, usar snapshot ou nao alertar.

### Fase 6 - Score Context

- Somente depois de auditoria final.
- Providers podem influenciar contexto, warnings e blockers.
- Nenhum provider sobrescreve Score Mestre ou action.

## Riscos

- Custo de licenca.
- OAuth/reautenticacao.
- Plano insuficiente.
- Rate limit.
- Latencia.
- Provider down.
- Divergencia de preco.
- Dados stale.
- Cobertura parcial.
- Excesso de confianca.
- Confusao do usuario entre dado premium e decisao operacional.
- Dependencia operacional indevida.
- Quebra de payload.
- Inconsistencia de simbolos.
- Mistura de B3, EUA e crypto.
- Provider institucional lento usado como gatilho intraday.
- Alertas premium emitidos com dado invalido.

Mitigacoes:

- Provider quality flags obrigatorios.
- Cache obrigatorio.
- Fallback obrigatorio.
- Snapshot como unica fonte de consumo.
- Campos opcionais e degradaveis.
- Testes de provider indisponivel antes de go-live.
- Separar contexto institucional de decisao operacional.

## Criterios para futura implementacao

Antes de qualquer integracao real, exigir:

- Credencial valida.
- Plano/licenca valido.
- Teste de latencia.
- Teste de fallback.
- Teste de cache.
- Teste de stale.
- Teste de payload antigo.
- Teste de payload parcial.
- Teste de Decision Envelope.
- Teste de API sem provider.
- Teste de frontend sem provider.
- Teste de Telegram/Push sem provider.
- Teste de rate limit.
- Teste de provider offline.
- Teste de simbolo nao suportado.
- Teste de B3 nao contaminado por Binance/Alpaca.
- Teste de ausencia de credencial em runtime publico.

Gate minimo:

- Se qualquer teste critico falhar, provider nao entra em producao.
- Se provider for premium e indisponivel, produto deve continuar funcional em modo degradado.
- Se dado critico faltar, decisao operacional deve ser `NAO OPERAR AGORA` ou manter leitura sem alerta.

## Conclusao final

Missao 28I define a arquitetura futura sem implementar provider real.

A arquitetura aprovada preserva:

- Snapshot Interno como fonte unica.
- Providers externos fora do caminho critico.
- Score Mestre sem alteracao.
- Ranking sem alteracao.
- Radar Institucional sem alteracao.
- Auditor Institucional sem alteracao.
- Decision Envelope sem alteracao operacional.
- Worker, frontend, APIs, Telegram, Push e banco sem alteracao.

Decisao final:

- GitHub entra agora como governanca.
- Binance entra futuramente para crypto, com cache e snapshot.
- Alpaca entra futuramente para EUA/ETF, com qualidade de feed explicita.
- Quartr entra futuramente para earnings/IR, condicionado a Quartr Pro.
- Moody's entra futuramente para risco institucional, condicionado a OAuth valido.
- CodeRabbit fica como ferramenta auxiliar de review, condicionado a ambiente suportado.

Commit sugerido:

`docs: define institutional provider architecture`

## Validacao executada

- `git status --short` executado.
- `git diff --check -- docs/mission_28i_institutional_provider_architecture.md` executado sem erro.
- `Select-String -LiteralPath 'docs\mission_28i_institutional_provider_architecture.md' -Pattern '[ \t]+$'` executado sem ocorrencias.
- `git ls-files --others --exclude-standard docs/mission_28i_institutional_provider_architecture.md` confirmou o arquivo novo.
- Testes funcionais nao foram executados porque a missao e documental e alterou apenas este relatorio.
