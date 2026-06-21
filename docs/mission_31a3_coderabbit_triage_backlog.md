# Mission 31A-3 CodeRabbit Triage Backlog

Scope: registro tecnico dos achados P2/P3 nao corrigidos nesta missao. Nenhuma logica operacional foi alterada por este arquivo.

## P2 - Concorrencia

| Arquivo | Achado | Severidade | Acao recomendada |
| --- | --- | --- | --- |
| `app/social/store.py` | Confirmar que todas as leituras e mutacoes continuem passando por `read_social_state`/`mutate_social_state`, com escrita atomica mantida. | Medium | Criar teste de concorrencia com multiplas mutacoes simultaneas no store social. |
| `app/social/moderation.py` | O lock protege load/save, mas fluxos load -> mutate -> save precisam de auditoria dedicada para evitar lost update em alto volume. | High | Consolidar operacoes compostas em helper atomico na proxima missao social. |
| `app/services/ticker_room_service.py` | `_load_store()` e `_save_store()` sao protegidos individualmente, mas `append_room_message` faz ciclo load/mutate/save fora de uma unica secao critica. | High | Encapsular append completo sob lock unico e cobrir com teste multithread. |
| `app/services/poll_service.py` | `get_weekly_poll` cria/atualiza poll em blocos separados e pode duplicar trabalho ou sobrescrever migracoes sob concorrencia. | Critical | Refatorar `get_weekly_poll` para operacao atomica de read/create/migrate/save. |

## P3 - Baixo Risco

| Item | Registro |
| --- | --- |
| `not-found.tsx` | Revisar somente em futura rodada de UX/Next; sem impacto operacional nesta missao. |
| `app/social/comments.py` | Possivel N+1/listagem ineficiente; manter para backlog de performance social. |
| `display_name` cosmetico | Padronizacao visual apenas; sem impacto de seguranca/trading. |

## Nota sobre Score Mestre

Foi encontrada evidencia de escala interna 0..100 em `app/ai/ai_master_score.py`, onde `score` e `master_score_raw` sao calculados e preservados nessa escala antes da camada de display 0..10. Por isso, a Missao 31A-3 manteve a conversao existente de display e corrigiu apenas a exposicao indevida de `score_raw` invalido em blocos aninhados.
