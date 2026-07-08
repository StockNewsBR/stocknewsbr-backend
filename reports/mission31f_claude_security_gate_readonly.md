# Missão 31F — Claude Security Gate READ-ONLY (preparatório/independente)

**Data:** 2026-07-07
**Branch:** feat/github-workflow-ai-tools → main
**Diretório:** /mnt/c/Users/dcima/stocknewsbr-backend
**Executor:** **Claude Code** (auditoria multi-agente + verificação manual)
**Modo:** READ-ONLY — nenhum arquivo de código foi alterado.

> **Nota de vendor:** este é um gate de segurança **independente/preparatório executado pelo
> Claude Code**. Ele **NÃO** substitui o **Codex Security Deep Scan + Diff Scan oficial**, que
> permanece pendente. Por separação de vendor, o fechamento **oficial** da 31F só ocorre após o
> passe do Codex retornar 0 P0/P1.

## VEREDITO (Claude gate): ✅ PASS — pronto para fechamento TÉCNICO/LOCAL; fechamento OFICIAL pendente

Nenhum risco **P0/P1 real introduzido pela 31F** foi confirmado.
1 achado **P2 não-bloqueante** (leak de reserva de capacidade em cancelamento de WS) +
2 notas P2/P3 de hardening. Nenhum deles bloqueia o fechamento técnico da 31F.

O gate do Claude passa. Os itens P2/P3 abaixo são recomendações para o passe **oficial do Codex**
(dia 8), não condições de bloqueio.

### Status board
```
31F implementação local:            PASS
31F testes locais:                  PASS
31F CodeRabbit final clean:         PASS
31F Claude Security Gate READ-ONLY: PASS, 0 P0/P1
31F fechamento OFICIAL:             PENDENTE — Codex Security Deep Scan + Diff Scan
```

---

## 1. Preflight (evidência)

```
pwd: C:\Users\dcima\stocknewsbr-backend
git status: 17 modificados + 4 untracked canônicos (atomic_io.py, script .mjs, docs, teste 31F)
git diff --stat: 17 files changed, 1515 insertions(+), 843 deletions(-)
Artefatos $AUTO/ $BACKUP/ .m31f.bak-* : fora do diff (excluídos via .git/info/exclude)
```

Escopo auditado (canônico): app/core/atomic_io.py, app/cache/* (7), app/data/warm_data_pool.py,
app/services/{poll,push,ticker_room}_service.py, app/social/moderation.py,
app/system/{websocket_manager,room_websocket_manager}.py, app/telegram/telegram_alert_engine.py,
app/websocket/market_stream.py, tests da missão.

## 2. Método

- **Deep Scan:** 7 lentes de segurança em paralelo sobre o diff canônico.
- **Diff Scan:** cada finding submetido a verificação adversarial de 3 lentes independentes
  (correctness / provenance / severity), quórum ≥2 para sobreviver como bloqueador.
- **Nota de execução:** o orquestrador multi-agente atingiu o limite de sessão a meio caminho
  (3 de 7 finders concluídos por subagente; verificadores WS e crítico de completude falharam
  por rate limit até 22:20). As 4 lentes restantes (race-toctou, cache-poison-stale,
  cross-user-authz, silent-except-regression), a verificação do finding WS e o crítico de
  completude foram **concluídos manualmente** pelo executor com leitura linha a linha dos
  arquivos canônicos. Cobertura final: 7/7 lentes.

## 3. Resultado por lente

| Lente | P0/P1 introduzidos pela 31F | Observação |
|---|---|---|
| race-toctou | **0** | RMW sob lock; guards de identidade/mtime/epoch corretos |
| deadlock-lockorder | **0** | Ordering consistente por módulo; interprocess não-reentrante sem reentrada |
| atomicio-dataloss | **0** | O_EXCL+fsync+replace; fail-closed em JSON corrompido; falha vira DEGRADED (ruidoso) |
| cache-poison-stale | **0** | Sem poisoning de símbolo ausente; stale-reload bloqueado; memória preservada em falha |
| cross-user-authz | **0** | Estado por str(user_id); gate Telegram fail-closed (melhora de segurança) |
| websocket-broadcast | **0 P0/P1** | broadcast em snapshot; 1 achado **P2** (leak em CancelledError) |
| silent-except-regression | **0** | Telegram reserve/release correto; push atômico; except-pass pré-existente (P2, não da 31F) |

## 4. Achado P2 não-bloqueante (recomendado para o Codex dia 8)

### [P2] CancelledError vaza a reserva de pending-accept nos dois managers de WebSocket

- **Arquivos:** `app/system/websocket_manager.py:130` e `app/system/room_websocket_manager.py:137`
- **Mecanismo:** a 31F introduziu reserva de capacidade — `connect()` faz
  `_pending_accepts += 1` e `_pending_websockets.append(ws)` sob lock, depois
  `await asyncio.wait_for(websocket.accept(), timeout=ACCEPT_TIMEOUT_SECONDS)`. A limpeza
  (`_release_pending_locked`) está num handler `except Exception`. `asyncio.CancelledError` é
  `BaseException` (Py 3.8+), **não** `Exception` — se a task do endpoint ASGI for cancelada
  enquanto suspensa no `await accept()` (client some no handshake, shutdown, timeout de proxy),
  o `CancelledError` propaga para fora de `connect()` **sem** liberar a reserva. O slot em
  `_pending_accepts` e a referência em `_pending_websockets` vazam permanentemente (sem TTL).
- **Impacto:** com cancelamentos repetidos exatamente nessa janela, as reservas vazadas
  acumulam e a capacidade tende a `capacity_reached` permanente (limite global 1000 / por sala
  100). Degradação lenta de disponibilidade; **não** é perda de dados nem vazamento entre
  usuários. O caminho de *timeout* do `wait_for` está correto (levanta `TimeoutError`, capturado);
  só o cancelamento externo vaza.
- **Por que P2 e não P1:** requer cancelamento na janela curta de accept; cada leak custa 1 de
  1000/100; não se auto-cura mas não esgota rápido sob churn normal.
- **Introduzido pela 31F:** sim — o `connect()` pré-31F era só `await websocket.accept()`, sem
  estado de reserva para vazar.
- **Fix recomendado (para amanhã, fora deste gate read-only):** trocar `except Exception` por
  `except BaseException`, liberar a reserva e **re-levantar** `CancelledError` (nunca engolir
  cancelamento):
  ```python
  try:
      await asyncio.wait_for(websocket.accept(), timeout=ACCEPT_TIMEOUT_SECONDS)
  except BaseException as exc:
      with self._lock:
          self._release_pending_locked(websocket)   # (room_key, websocket) no room manager
      if isinstance(exc, asyncio.CancelledError):
          raise
      logger.warning(...)
      await _close_websocket(websocket, 1013, "accept_failed")
      return False
  ```
  Observação de escopo: mexer nos managers de WebSocket estava **proibido** nesta missão
  ("NÃO refatorar WebSocket") e este é um gate READ-ONLY, por isso o fix **não** foi aplicado —
  fica registrado para decisão no passe do Codex.

## 5. Notas P2/P3 adicionais (hardening, não-bloqueantes)

- **[P2] `os.replace` no Windows** (`app/core/atomic_io.py:139`): com um leitor mantendo o arquivo
  aberto sem delete-share, `os.replace` pode levantar `PermissionError`. Efeito: escrita marcada
  como falha → estado `DEGRADED` (ruidoso, sem perda silenciosa) e retry no ciclo seguinte. Já
  apontado pelo CodeRabbit como *minor*; recomenda-se retry curto no `nt`. Não é da lógica da 31F
  em si (comportamento de plataforma).
- **[P2, pré-existente] `except Exception: pass`** em
  `app/cache/snapshot_cache.py:_load_from_disk_if_needed`: silencia erro de leitura e retenta a
  cada `get()` com arquivo corrompido. Mantém o estado em memória (sem perda de dados). Não foi
  introduzido pela 31F; candidato a log rate-limited.
- **[P3] fsync de diretório ausente no Windows** (`atomic_io.py`, ramo `os.name != "nt"`): sem
  fsync do diretório no Windows, a durabilidade do rename não é forçada em queda de energia.
  Edge de durabilidade, não de segurança/lógica.

## 6. Verificações positivas de segurança introduzidas pela 31F

- **Gate Telegram fail-closed:** sem contrato `telegram_access` válido → bloqueado
  (`telegram_access_not_validated`); campos legados `telegram_linked`/`telegram_allowed` sozinhos
  **não** concedem acesso (coberto pelo novo teste). Redução de superfície.
- **Dedup determinístico do Telegram:** reserva de fingerprint sob lock antes do envio, com
  liberação em falha — sem envio duplicado nem supressão permanente sob concorrência.
- **IO atômico:** tmp exclusivo (`O_EXCL`, `0o600`) + fsync + `os.replace` — sem hijack de tmp
  previsível; corrupção de JSON falha fechado em vez de sobrescrever com default.
- **paper_trading_cache.update:** escrita fora do `_lock` com `_disk_write_lock` + guard de
  identidade — disco nunca fica mais antigo que a memória; update mais novo sempre reescreve por
  último.

## 7. Confirmações READ-ONLY

- Nenhum arquivo de código alterado (só este relatório foi criado em `reports/`).
- Não houve `git add`, `git commit`, `git push`.
- Não houve `git reset`, `git restore`, `git clean`, `git stash`.
- `$AUTO/`, `$BACKUP/`, `.fuse_hidden*`, `.m31f.bak-*`: não auditados como canônicos e não tocados.
- Score Mestre, Ranking, Signal Engine, BUY/SELL/SHORT/COVER, pesos e thresholds: não tocados.

## 8. Conclusão

**PASS (gate do Claude)** — a Missão 31F não introduziu risco P0/P1 de segurança/confiabilidade.
O único achado funcional (leak de reserva de WS em `CancelledError`) é P2 de disponibilidade de
degradação lenta, com fix pequeno e seguro já especificado.

A 31F está **pronta para fechamento técnico/local**, mas **NÃO oficialmente fechada** pelo
protocolo de vendor: o fechamento oficial exige o **Codex Security Deep Scan + Diff Scan** (dia 8).
Este relatório é evidência preparatória independente, não o passe oficial do Codex.

### Plano de fechamento (08/07)
1. Rodar Codex Security Deep Scan + Diff Scan oficiais, READ-ONLY.
2. Se vier 0 P0/P1 → declarar 31F **oficialmente fechada**.
3. Registrar o P2 do WebSocket como item separado — "31F follow-up P2 / WebSocket capacity
   reservation leak on CancelledError" — corrigido depois em micro-hotfix controlado ou dentro da
   próxima missão que toque WebSocket/realtime (respeita a cerca de escopo "não mexer em WebSocket").
