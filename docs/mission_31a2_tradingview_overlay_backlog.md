# Missao 31A-2.1 - Backlog Tecnico: TradingView Overlay

## Contexto

A auditoria da Missao 31A-2.1 confirmou que o problema visual do grafico envolve duas frentes diferentes:

- dados operacionais e painel estrategico, tratados no hotfix atual;
- overlays visuais do TradingView, que precisam de uma missao propria para evitar mexer em leitura de trade junto com UX de grafico.

## Problema Observado

As linhas de suporte e resistencia e a zona visual do grafico precisam continuar ancoradas ao preco real, nao a coordenadas fixas de tela. Quando o grafico muda timeframe, zoom ou pan, qualquer overlay customizado deve acompanhar a escala do TradingView.

## Regra Para Missao Futura

Nao desenhar overlays operacionais com HTML/CSS fixo sobre o grafico quando o objetivo for representar preco. Qualquer suporte, resistencia, VWAP ou faixa operacional deve ser:

- baseado em preco real;
- recalculado por timeframe;
- sincronizado com zoom/pan;
- removido se nao houver dado confiavel.

## Risco

Uma correcao apressada nesta missao poderia misturar contrato de dados, painel estrategico e renderizacao do grafico. Isso aumentaria o risco de regressao visual e de sinal operacional incoerente.

## Proxima Acao Recomendada

Criar uma missao dedicada para validar:

- `apps/web/components/ticker-chart.tsx`;
- renderizadores de suporte/resistencia;
- VWAP e medias;
- zonas de liquidez/operacionais;
- testes Playwright com PETR4, VALE3, AAPL, CRM e F em 1m, 30m e 1h.

## Status

Backlog documentado. Nenhuma regra de Score Mestre, Ranking, Engine, Worker, Telegram ou Push foi alterada por este item.
