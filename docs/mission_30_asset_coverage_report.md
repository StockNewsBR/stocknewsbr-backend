# Mission 30 Complement - Active List Coverage

Data da auditoria: 2026-06-19

## Universo ativo canonico

| Categoria | Total |
| --- | ---: |
| B3 | 68 |
| BDR | 12 |
| Crypto | 7 |
| USA | 26 |
| Todos | 113 |

Regra validada: `Todos = B3 + BDR + Crypto + USA`, com normalizacao canonica antes da contagem.

## Cobertura observada no cache local

Fonte: `runtime/cache/market_quotes.json` existente no ambiente local durante a auditoria.

| Metrica | Total |
| --- | ---: |
| Ativos cadastrados | 113 |
| Ativos com preco no cache runtime | 63 |
| Ativos sem preco no cache runtime | 50 |
| Ativos com erro de provider conhecido | 2 |
| Ativos com alias quebrado apos correcao | 0 |
| Ativos sem snapshot no cache runtime | 50 |
| Ativos duplicados apos canonicalizacao | 0 |
| Ativos renomeados tratados | 1 |

## Casos corrigidos

| Caso | Status |
| --- | --- |
| `ELET6` / `ELET6.SA` | Normaliza para `AXIA6` |
| `AXIA6` provider | Usa `AXIA6.SA` |
| `AXIA6` TradingView | Usa `BMFBOVESPA:AXIA6` |
| `ASAI3` | Mantido como B3 valido com provider `ASAI3.SA` |
| `AZUL4` | Removido de blocklist permanente e mantido como B3 valido |
| `B3SA3` | Mantido como B3 valido com provider `B3SA3.SA` |

## Observacao operacional

O cache runtime local ainda nao continha snapshot de `ASAI3`, `AZUL4`, `B3SA3` e `AXIA6` no momento da auditoria. A correcao remove os bloqueios e aliases errados, mas a precificacao real depende do proximo ciclo Provider -> Cache -> Snapshot. Enquanto nao houver preco/volume confirmados, o ativo permanece com fallback claro e nao fica elegivel para trade, bias operacional, push ou Telegram.
