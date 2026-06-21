# =====================================================
# STOCKNEWSBR_V4_MASTER_ROADMAP
# =====================================================


STOCKNEWSBR V4 — MASTER PRODUCT ROADMAP
PARTE 2/3 — MOTOR INSTITUCIONAL, SCORE MESTRE E DIFERENCIAIS PREMIUM
MISSÃO 8 — ENGINE DE MERCADO / MARKET PULSE
Objetivo

Corrigir a leitura institucional do mercado.

Problema Atual

Hoje sinais bloqueados podem contaminar a percepção do mercado.

Exemplo:

Score alto
Sem preço real
Sem volume
Decision Ready = False

Mesmo assim aparece como bullish.

Isso é incorreto.

Implementar

Separar:

Candidatos
bullish_candidates
bearish_candidates
Acionáveis
actionable_bullish
actionable_bearish
Bloqueados
blocked_signals
watchlist_candidates
Regras

Sinal bloqueado:

NÃO conta como oportunidade operacional
NÃO entra no ranking
NÃO vira alerta
Critério de Aceite

Market Pulse deve separar claramente:

interesse
oportunidade
operação
MISSÃO 9 — AUDITORIA DAS 9 IAs
Objetivo

Auditar todas as IAs antes de reescrever.

Não alterar código ainda

Somente auditoria.

Auditar
Flow IA
entradas
saídas
score
Liquidity IA
sweep
stops
liquidez
Trend IA
tendência
Momentum IA
aceleração
Smart Money IA
acumulação
Risk IA
risco
News IA
notícias
Macro IA
macroeconomia
Regime IA
contexto
Procurar
redundâncias
conflitos
textos iguais
scores iguais
funções sobrepostas
Critério

Cada IA deve justificar sua existência.

MISSÃO 10 — DIFERENCIAÇÃO DAS 9 IAs
Objetivo

Dar identidade única para cada IA.

FLOW IA

Responsável por:

fluxo institucional
agressão
pressão compradora
pressão vendedora
LIQUIDITY IA

Responsável por:

sweep
stops
armadilhas
liquidez alvo
TREND IA

Responsável por:

tendência
direção predominante
estrutura
MOMENTUM IA

Responsável por:

aceleração
exaustão
força
SMART MONEY IA
Nome interno

Smart Money IA

Nome visual

🏦 Atuação Institucional

Mostrar:

Acumulando
Distribuindo
Neutro
Defesa Institucional
Possível Manipulação
RISK IA

Responsável por:

risco operacional
risco de entrada
risco de stop
NEWS IA

Responsável por:

impacto das notícias
MACRO IA

Responsável por:

juros
dólar
NQ
ES
exterior
REGIME IA

Responsável por:

tendência
lateralização
volatilidade
Critério

Nenhuma IA deve parecer cópia da outra.

MISSÃO 11 — AUDITOR INSTITUCIONAL
Objetivo

Criar camada obrigatória entre IAs e Score Mestre.

Campos
conflict_detected
conflict_level
auditor_score
auditor_summary
blocked_by_auditor
Níveis
none
low
medium
high
critical
Exemplo

Flow:

BUY

Liquidity:

SELL

Resultado:

⚠️ conflito detectado

Critério

Score Mestre nunca ignora conflito crítico.

MISSÃO 12 — SCORE MESTRE
Objetivo

Transformar o Score Mestre no centro do produto.

O Score Mestre NÃO É
mais uma IA
mais uma aba
mais um score
O Score Mestre É

O sistema operacional do StockNewsBR.

Entradas
Snapshot
9 IAs
Auditor
Data Quality
Decision Ready
Saídas
direção
convicção
risco
decisão final
plano operacional
NOVA FEATURE
POR QUÊ?

Ao lado do Score Mestre.

Exemplo:

Score Mestre: 84

Por quê?

Flow +12
Liquidez +8
Trend +10
Momentum +6
Smart Money +10
Risk -5
News -3
Macro +2
Regime +15

Resumo:

Convicção elevada devido a fluxo institucional comprador e regime favorável.

Critério

Usuário deve entender de onde veio o score.

NOVA FEATURE
O QUE MUDARIA MINHA OPINIÃO?

Exemplo

Viés Comprador

O que invalida?

perda da VWAP
fluxo vendedor dominante
liquidez abaixo da região crítica
falso rompimento confirmado
Critério

Toda tese deve ter:

gatilho
invalidação
cenário contrário
MISSÃO 13 — PAINEL DE ANÁLISE ESTRATÉGICA
Objetivo

Traduzir inteligência institucional para linguagem simples.

O painel deve responder
Comprar?
Vender?
Esperar?
Qual risco?
Por quê?
O que invalida?
Próximo gatilho?
Estrutura
Cenário Atual
Convicção
Risco
Por quê?
O que mudaria minha opinião?
Próximo gatilho
Critério

Usuário entende tudo sem abrir 10 abas.

MISSÃO 14 — BDR EM REAIS
Objetivo

Garantir que BDR nunca apareça em dólar.

Validar
AAPL34
GOGL34
TSLA34
META34
MSFT34
AMZO34
Regras
somente BRL
bloquear USD
bloquear proxy USA
Critério

BDR sempre em reais.

MISSÃO 15 — NOTÍCIAS POR TICKER
Objetivo

Corrigir notícias.

Problemas
duplicadas
ticker errado
inglês sem necessidade
Implementar
dedupe
ticker relevance
separação macro/ticker
Critério

Notícia correta para ativo correto.

MISSÃO 16 — TRADINGVIEW WIDGET
Objetivo

Usar TradingView como gráfico principal.

TradingView

Responsável apenas por:

gráfico
candles
visualização
NÃO RESPONSÁVEL
Score Mestre
Alertas
Ranking
Radar
Critério

TradingView pode falhar.

Sistema continua funcionando.

MISSÃO 17 — RADAR INSTITUCIONAL
Objetivo

Detectar o que pode acontecer antes do movimento.

Não é IA

É feature premium.

Detectar
compressão
absorção
acumulação
distribuição
liquidez
squeeze
NOVA FEATURE
O QUE ESTÁ PRESTES A ACONTECER?

Exemplo

Radar:

Building

Provável:

rompimento comprador

Gatilho:

37,80

Risco:

volume insuficiente

Estados
inactive
watching
building
trigger_near
triggered
invalidated
Critério

Radar prepara.

Não dispara trade sozinho.

MISSÃO 18 — RANKING DE OPORTUNIDADES
Objetivo

Mostrar as melhores oportunidades do mercado.

Entrada
Score Mestre
Auditor
Radar
Snapshot
Confiança Histórica
Exemplo
PETR4
VALE3
WIN
NOVA FEATURE
POR QUE ESTÁ NO RANKING?

PETR4

fluxo comprador
radar building
regime favorável
liquidez acima da resistência
Critério

Todo ativo deve justificar sua posição.

FIM DA PARTE 2/3

Próxima parte:

Missão 19–27
Confiança Histórica
Placar das IAs
Frontend Comercial
Mercado Agora
Modo 2 Cliques
Rede Social Inteligente
Histórico de Acerto
Métricas
Segurança
Definição Oficial de Produto 10/10
Critério de Aprovação para Produção

Essa última parte fecha a versão definitiva do documento.



Depois Parte 3 com Missões 19–27 + Produto 10/10.
STOCKNEWSBR V4 — MASTER PRODUCT ROADMAP
PARTE 3/3 — DIFERENCIAIS COMERCIAIS, LANÇAMENTO E PRODUTO 10/10
MISSÃO 19 — CONFIANÇA HISTÓRICA
Objetivo

Transformar o Score Mestre em algo comprovável.

Hoje:

Score 84

não significa muito.

Depois:

Score 84

Confiança Histórica: 72%

Amostra: 41 sinais

Aí vira produto profissional.

Calcular

Por:

ticker
horário
regime
direção
IA
Score Mestre
Radar
Campos
historical_confidence
sample_size
ticker_win_rate
regime_win_rate
time_window_win_rate
confidence_quality
Exemplo

PETR4

Convicção Atual: 84

Confiança Histórica: 72%

Melhor horário:

10h–11h

Melhor regime:

Tendencial

Regras

Não mostrar estatística com amostra pequena como verdade.

Mostrar:

⚠️ Amostra limitada

quando necessário.

Critério

Usuário entende:

Convicção Atual
Histórico Real

separadamente.

MISSÃO 20 — PLACAR DAS IAs
Objetivo

Mostrar transparência.

Exemplo

Últimos 30 dias

Flow IA: 72%

Liquidity IA: 68%

Trend IA: 64%

Smart Money IA: 75%

Risk IA:

Bloqueou 31% dos sinais ruins

Medir
acerto
falso positivo
falso negativo
contribuição ao Score Mestre
Critério

Cada IA tem histórico próprio.

MISSÃO 21 — FRONTEND COMERCIAL
Objetivo

Transformar o produto em algo vendável.

NOVA FEATURE
MERCADO AGORA

Sempre no topo.

Exemplo

Mercado Agora

Regime: Tendencial
Fluxo: Comprador
Risco: Médio
Volatilidade: Normal

Atualizado por snapshot.

Hierarquia Visual Oficial
Mercado Agora
Score Mestre
Radar Institucional
Ranking de Oportunidades
Painel Estratégico
TradingView Widget
Notícias
Comunidade
Auditor
IAs Especialistas
Modo Simples

Mostrar:

Mercado Agora
Score Mestre
Radar
Ranking
Plano Operacional
Modo PRO

Mostrar:

Auditor
IAs
Histórico
Macro
Liquidez
Confiança Histórica
NOVA FEATURE
MODO 2 CLIQUES

Fluxo:

Usuário entra

↓

Top Oportunidades

PETR4
VALE3
WIN

↓

Clique

↓

Abre:

TradingView
Score Mestre
Radar
Painel Estratégico
Notícias
Critério

Máximo 2 cliques.

MISSÃO 22 — PERFIL DE TRADER
Objetivo

Adaptar a plataforma ao usuário.

Perfis
Scalper

Maior peso:

Flow
Momentum
Liquidez
Day Trader

Equilíbrio.

Swing Trader

Maior peso:

Tendência
Macro
Notícias
Ajustar
Alertas
Ranking
Radar
Painel
Critério

Experiência personalizada.

MISSÃO 23 — REDE SOCIAL INTELIGENTE
Objetivo

Criar comunidade sem virar bagunça.

NÃO CRIAR

Facebook de traders.

Criar

Discussão por ativo.

Exemplos:

PETR4
VALE3
WIN
NQ
Funcionalidades
comentários
curtidas
votação
sentimento
Integração

Comparar:

Comunidade

vs

Score Mestre

Exemplo

Comunidade:

Compradora

Score Mestre:

Neutro

Resultado:

⚠️ Divergência relevante

MISSÃO 24 — HISTÓRICO DE ACERTO
Objetivo

Registrar tudo.

Salvar
ticker
direção
score
auditor
radar
resultado
timestamp
Medir
acerto
erro
pnl estimado
mfe
mae
Critério

Todo sinal deve ser auditável.

MISSÃO 25 — TESTES DE PRODUÇÃO
Objetivo

Validar lançamento.

Testar
Snapshot
TradingView
BDR
Notícias
Radar
Ranking
Score Mestre
Auditor
Telegram
Push
Cache
Worker
Critério

Build verde.

Testes verdes.

Sem regressões.

MISSÃO 26 — MÉTRICAS E OBSERVABILIDADE
Objetivo

Saber exatamente quando algo quebra.

Medir
p50
p95
p99
cache hit ratio
worker duration
provider errors
stale snapshots
alerts blocked
alerts sent
auditor blocks
radar triggers
ranking generation
Logs Obrigatórios
erro provider
erro ticker
conflito institucional
alerta bloqueado
cache sobrescrevendo dado bom
BDR inválido
notícia duplicada
Critério

Problemas detectáveis imediatamente.

MISSÃO 27 — SEGURANÇA E DISCLAIMER
Objetivo

Reduzir risco comercial e jurídico.

Implementar
aviso de risco
disclaimer
transparência
histórico auditável
Linguagem Permitida
cenário favorece
viés comprador
viés vendedor
risco elevado
aguardar confirmação
Linguagem Proibida
lucro garantido
compra certa
sinal infalível
certeza de alta
certeza de queda
Critério

Produto profissional.

REGRA GLOBAL DO PRODUTO
PROIBIDO
criar novas IAs
criar dashboards redundantes
criar heatmaps desnecessários
criar scores genéricos
adicionar indicadores apenas para parecer sofisticado
O QUE MAIS VENDE ASSINATURA
1 — SCORE MESTRE

Responde:

👉 O que fazer?

2 — RANKING DE OPORTUNIDADES

Responde:

👉 Onde olhar?

3 — RADAR INSTITUCIONAL

Responde:

👉 O que está prestes a acontecer?

DEFINIÇÃO OFICIAL DE PRODUTO 10/10

O StockNewsBR será considerado 10/10 quando:

✅ Snapshot Único validado

✅ Yahoo fora das rotas públicas

✅ Worker robusto

✅ Data Quality funcionando

✅ Decision Ready funcionando

✅ Auditor Institucional funcionando

✅ Score Mestre funcionando

✅ Botão "Por Quê?" funcionando

✅ "O que Mudaria Minha Opinião?" funcionando

✅ BDR sempre em reais

✅ Notícias corretas por ticker

✅ TradingView estável

✅ Radar Institucional funcionando

✅ Ranking de Oportunidades funcionando

✅ Confiança Histórica funcionando

✅ Placar das IAs funcionando

✅ Frontend comercial funcionando

✅ Mercado Agora funcionando

✅ Modo 2 Cliques funcionando

✅ Perfil de Trader funcionando

✅ Rede Social por Ativo funcionando

✅ Histórico de Acerto funcionando

✅ Métricas funcionando

✅ Segurança e Disclaimer funcionando

✅ 30–90 dias de histórico auditado

✅ Usuário entende o cenário em menos de 10 segundos

CRITÉRIO DE APROVAÇÃO PARA PRODUÇÃO

Liberar lançamento apenas quando:

Todas as missões críticas concluídas
Testes verdes
Build verde
Sem provider externo em rotas públicas
Sem BUY/SELL com dado inválido
Sem conflito ignorado pelo Auditor
Ranking funcionando
Radar funcionando
Score Mestre funcionando
Homologação real concluída
RESUMO EXECUTIVO FINAL

A arquitetura final do StockNewsBR é:

9 IAs Especialistas
↓
Auditor Institucional
↓
Score Mestre
↓
Radar Institucional
↓
Ranking de Oportunidades
↓
Painel Estratégico
↓
Telegram / Push
↓
Usuário

O gráfico TradingView é visualização.

A decisão operacional vem do:

Score Mestre + Auditor + Decision Ready

A missão principal do produto é:

Transformar complexidade institucional em decisão simples.

Essa é a versão V4 consolidada das missões.