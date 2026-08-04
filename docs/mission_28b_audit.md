# Missao 28B - Auditoria final de consistencia, UX e prontidao comercial

## Noticias vs Noticias IA

Conclusao: nao sao o mesmo modulo.

- Aba Noticias: consome `activeNews.items`, ou seja, noticias reais do ativo vindas do payload de noticias, deduplicadas e ordenadas por horario original da fonte.
- Aba Noticias IA: consome `workspace.ai_tools.news` ou `publicAiTools.tools.news`, ou seja, leitura institucional da noticia como contexto operacional.
- Existe overlap de assunto, mas nao duplicacao funcional: uma aba mostra a noticia original; a outra mostra a interpretacao contextual da IA.
- Valor em manter ambas: sim, desde que os nomes fiquem claros. A UI agora diferencia "Noticias" de "Noticias IA".

## Tendencia IA vs Momento IA

Conclusao: existe overlap parcial, mas as lentes sao diferentes.

- Tendencia IA: usa direcao predominante, estrutura de mercado, tendencia e contexto de continuidade.
- Momento IA: usa aceleracao, forca, exaustao, breakout/radar/heat map e intensidade do movimento.
- Overlap estimado: menor que 70%, porque uma lente responde "qual estrutura domina" e a outra responde "qual a intensidade/agora".
- Valor em manter ambas: sim, como lentes separadas.

## Auditoria das IAs

- Fluxo IA: ATIVA. Le fluxo institucional, agressao e pressao compradora/vendedora.
- Liquidez IA: ATIVA. Le zonas, varreduras, armadilhas e invalidacao.
- Tendencia IA: ATIVA. Le direcao predominante e estrutura.
- Momento IA: ATIVA. Le aceleracao, forca e exaustao.
- Smart Money IA: ATIVA. Le acumulacao, absorcao e atuacao institucional.
- Risco IA: ATIVA. Le risco operacional, bloqueios e Can Trade.
- Noticias IA: ATIVA. Le noticia como contexto, relevancia e status do provedor.
- Macro IA: ATIVA. Separa macro real de contexto derivado de noticia.
- Regime IA: ATIVA. Classifica tendencia, lateralidade e volatilidade.

## Consistencia visual

- CRITICO: Score Mestre acima de 10 quebrava confianca visual. Corrigido com contrato de display 0-10 e warning interno.
- ALTO: Modo Basico vazava cards premium. Corrigido com bloqueio visual "Disponivel no Plano Pro".
- ALTO: timestamps de IA podiam parecer horario de abertura da pagina. Corrigido com Detectado/Publicado/Visualizado separados.
- MEDIO: Volume Snapshot e RSI Snapshot tinham explicacoes longas sem valor operacional. Removidas.
- MEDIO: suporte/resistencia repetiam labels nas linhas e nos chips. Corrigido mantendo texto no topo e linha visual sem label.
- BAIXO: nomes PT-BR misturavam ingles em menus. Corrigido nas superficies principais e legadas.

## Escopo preservado

Nenhuma regra BUY/SELL/SHORT/COVER foi alterada. Nenhuma decisao operacional, Ranking, Auditor, Paper Trading, Signal Outcome Audit, Performance Intelligence ou Explainability teve regra de decisao modificada; as mudancas sao de UX, contrato de display e auditoria.
