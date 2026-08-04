# Missao 31B.0 - Security Dependencies Hardening

## Status final

Status: `TOOL_BLOCKED`

Motivo: o hardening local foi aplicado e validado, incluindo a correcao do finding confirmado pelo Codex Security para o fallback publico `CHANGE_THIS_SECRET`. Os gates locais de backend, Web e Mobile fecharam, e o Codex Security diff scan pos-correcao concluiu com 0 findings. O unico gate obrigatorio ainda bloqueado e o CodeRabbit final: a CLI `coderabbit` nao esta disponivel no Windows atual e o instalador oficial `curl ... | sh` nao consegue executar porque `sh` nao existe no ambiente. Pela regra da missao, isso impede declarar `PASS` ate esse gate fechar.

## Repositorio

- Branch: `feat/github-workflow-ai-tools`
- `BASE_COMMIT`: `7ec5e100b73c97953e88a2f57e41e879187c3d48`
- HEAD local inicial: `7ec5e100b73c97953e88a2f57e41e879187c3d48`
- HEAD remoto inicial: `7ec5e100b73c97953e88a2f57e41e879187c3d48`
- 31C: commit sincronizado e usado como base.
- Working tree inicial: continha o diff aberto da 31B.0.
- Commit/push nesta missao: nao executados por esta sessao. Foi encontrado posteriormente um commit ja sincronizado em `b61cf9906fbac07d350eb1b51ee5afaea07594c2`.
- Working tree final desta sessao: sujo apenas com ajustes da 31B.0 em `.env.example`, `app/core/settings.py`, `app/security.py`, `main.py`, `tests/test_mission_31b0_security_dependencies.py` e este documento.

## Ambiente

- Python do projeto: `.\\venv\\Scripts\\python.exe` (`3.11.9`)
- pip: `26.1.2`
- Node: `v26.4.0`
- npm: `11.17.0`
- Package manager Web: npm com `apps/web/package-lock.json`
- Package manager Mobile: npm com `apps/mobile/package-lock.json`

## Manifests e lockfiles

- `requirements.txt`
- `apps/web/package.json`
- `apps/web/package-lock.json`
- `apps/mobile/package.json`
- `apps/mobile/package-lock.json`

Nao ha `.github` versionado no checkout atual, portanto nao foram encontrados workflows, Dependabot ou code-scanning config locais para alterar nesta missao.

## Baseline

Historico conhecido:

- Python: 16 vulnerabilidades em 6 pacotes.
- Web: 1 HIGH, 1 MODERATE.
- Mobile: 1 CRITICAL, 5 HIGH, 25 MODERATE, 1 LOW.
- Bandit: 55 findings, 5 HIGH, 3 MEDIUM, 47 LOW.

Atual antes das alteracoes:

- Python: 16 vulnerabilidades.
- Web: 2 vulnerabilidades, sendo 1 HIGH e 1 MODERATE.
- Mobile: 32 vulnerabilidades, sendo 1 CRITICAL, 5 HIGH, 25 MODERATE e 1 LOW.
- Bandit: salvo em `runtime/mission_31b0/before/bandit.json`.

Depois:

- Python: 0 vulnerabilidades no `pip-audit`.
- Web: 0 vulnerabilidades no `npm audit`.
- Mobile: 12 MODERATE, 0 HIGH, 0 CRITICAL.
- Bandit: 5 HIGH, 3 MEDIUM, 36 LOW, sem correcao nesta missao por escopo.

## Upgrades aplicados

- `python-jose[cryptography]`: `3.3.0` -> `3.5.0`
- `python-multipart`: `0.0.9` -> `0.0.31`
- `python-dotenv`: `1.0.1` -> `1.2.2`
- `requests`: `2.32.5` -> `2.33.0`
- `yfinance`: `1.2.0` -> `1.2.1`
- `curl-cffi`: pinado em `0.15.0`
- `next`: `^15.2.0` -> `^15.5.19`
- `postcss`: override `8.5.10` no Web
- `react-native`: `0.79.6` -> `0.79.7`
- Mobile overrides: `@babel/core`, `@expo/metro-config/postcss`, `@xmldom/xmldom`, `node-forge`, `react-devtools-core/shell-quote`, `tar`, `undici`

Nao houve upgrade major automatico.

## JWT

`python-jose` foi mantido e atualizado, sem troca para PyJWT. A politica continua em `HS256`.

Mudanca de compatibilidade: `create_access_token()` grava `sub` como string no JWT, conforme exigido pelo `python-jose 3.5.0`; `decode_access_token_payload()` segue retornando `payload["sub"]` como `int`, preservando o contrato interno existente. O decode tambem rejeita `sub` assinado com formato nao canonico, como `00123`, ` 123`, `+123`, nulo, booleano ou nao numerico.

Correcao de seguranca: o fallback publico `CHANGE_THIS_SECRET` foi removido de `app/security.py`. A fonte unica do segredo de JWT agora fica em `app/core/settings.py` por `get_secret_key()`, que falha fechado quando `SECRET_KEY` esta ausente, vazio, menor que 32 caracteres, igual a placeholders conhecidos (`CHANGE_THIS_SECRET`, `change_this_in_production` e o placeholder de `.env.example`) ou trivial/repetitivo demais para uso operacional. `settings.SECRET_KEY`, assinatura e verificacao de JWT passam pela mesma fonte validada. `main.py` chama `validate_runtime_security_settings()` no lifespan antes do bootstrap de banco/workers.

Testes cobrem token valido com `sub`/`sid`, `sub=0`, token expirado, assinatura invalida, claim `sub` ausente, token malformado, `alg=none`, `sub` assinado nao canonico, startup sem `SECRET_KEY`, assinatura/verificacao sem segredo, rejeicao do segredo publico antigo, comprimento minimo/triviais de `SECRET_KEY`, ordem de `load_dotenv()` antes da leitura final de `ENV`/`SECRET_KEY` e preservacao da politica atual de `sid`.

## Multipart

`python-multipart` foi atualizado para `0.0.31`.

Testes cobrem form/upload valido, form vazio, `multipart/form-data` sem boundary, content-type incorreto e multipart truncado retornando 4xx sem 500 inesperado.

## Next.js e Web

`next` foi atualizado para `^15.5.19` e `postcss` ficou em `8.5.10` por override. `npm ci`, `npm audit`, `npm audit --omit=dev`, `npm ls`, `tsc` e `next build` passaram.

Regressoes Web existentes executadas:

- `test:mission30`: passou.
- `test:mission25d`: falhou em contrato historico de labels de suporte/resistencia.
- `test:mission28b`: falhou em contrato historico do contador de Todos.

Essas duas falhas ja eram fora do escopo de dependencia e nao foram corrigidas aqui para nao misturar missoes.

## Mobile

`shell-quote` foi resolvido para `1.9.0` via override em `react-devtools-core`; a cadeia e de tooling/dev, nao bundle operacional do app.

`npm ci`, `npm ls`, `typecheck`, `smoke:mobile` e `export:android` passaram. O audit mobile reduziu de 32 para 12 vulnerabilidades, sem CRITICAL e sem HIGH. As 12 MODERATE residuais exigem major de Expo/React Native ou missao proprietaria.

Moderates residuais registrados no ledger:

- `31B0-DEP-020` - `@expo/cli` - transitive - fix sugerido por audit envolve major/downgrade de `expo`
- `31B0-DEP-021` - `@expo/config` - transitive - fix sugerido por audit envolve major/downgrade de `expo`
- `31B0-DEP-022` - `@expo/config-plugins` - transitive - fix sugerido por audit envolve major/downgrade de `expo`
- `31B0-DEP-023` - `@expo/metro-config` - transitive - fix sugerido por audit envolve major/downgrade de `expo`
- `31B0-DEP-024` - `@expo/prebuild-config` - transitive - depende da cadeia `@expo/config`/`@expo/config-plugins`
- `31B0-DEP-033` - `expo` - direct - requer missao dedicada de plataforma
- `31B0-DEP-034` - `expo-asset` - transitive - depende de `expo-constants`
- `31B0-DEP-035` - `expo-constants` - direct - fix sugerido por audit e major
- `31B0-DEP-036` - `expo-linking` - direct - fix sugerido por audit e major
- `31B0-DEP-037` - `js-yaml` - transitive - preso a cadeia Expo/React Native
- `31B0-DEP-048` - `uuid` - transitive - preso a cadeia `xcode`/Expo
- `31B0-DEP-050` - `xcode` - transitive - preso a cadeia Expo

## Bandit

Bandit final preserva findings existentes:

- HIGH: 5
- MEDIUM: 3
- LOW: 36

Decisao: `SECURITY_BACKLOG`. Esta missao nao alterou logica de producao para silenciar Bandit.

Artefato Bandit final: `runtime/mission_31b0/after/bandit.json`

SHA256 Bandit final: `209431D521330D46B2D38FB84E90CC818EC957A4A647A841AE924F6DCF0CC625`

Backlog recomendado: abrir missao proprietaria de Bandit HIGH, candidata `31B.1` se a sequencia de seguranca continuar antes de `31D`, ou backlog formal da 31D se a prioridade for Root App/API/integridade financeira.

## Codex Security

- `security-scan` standard anterior: encontrou 1 finding confirmado/reportavel, severidade oficial `Medium`, para `CHANGE_THIS_SECRET` como fallback de JWT quando `SECRET_KEY` esta ausente.
- Tratamento 31B.0: o finding foi promovido a bloqueador operacional da missao porque permite falsificacao de identidade em deploy mal configurado.
- Correcao aplicada: fonte unica validada, fail-closed em startup, assinatura e verificacao, e testes focados de regressao.
- `security-diff-scan` pos-correcao: concluido com 0 findings reportaveis. O scan revisou o working tree corrigido contra `b61cf9906fbac07d350eb1b51ee5afaea07594c2`, com o `snapshotDigest` canonico do workspace. O caminho absoluto do artefato nao foi registrado neste relatorio para nao persistir path pessoal.

## CodeRabbit

Primeira revisao encontrou um Major em `data/moderation_state.json`, arquivo nao versionado gerado por teste com estado local. O artefato foi removido. A revisao seguinte apontou um Minor no teste JWT; o teste foi ajustado para validar explicitamente `sub` string no token bruto e `sub` int no contrato publico decodificado.

Rodadas posteriores encontraram Majors no contrato de `sub` do JWT. A emissao agora falha cedo quando `sub` esta ausente, nulo, booleano, nao numerico ou numerico nao canonico. Os minors de cobertura adicional foram aplicados no teste focado. A revisao final apos esses ajustes ficou presa em `summarizing` e foi encerrada por timeout para nao deixar processo em background.

Rodada mais recente apontou dois Majors adicionais: comprimento minimo/valores triviais de `SECRET_KEY`, e ordem de `load_dotenv()` antes da leitura final de `ENV`. Ambos foram corrigidos em `app/core/settings.py` com testes de regressao.

Rodada final apos a ultima alteracao: `coderabbit --version` falhou porque `coderabbit` nao esta no PATH. `Get-Command sh` e os caminhos esperados do Git Bash nao existem, e a tentativa `curl.exe -fsSL https://cli.coderabbit.ai/install.sh | sh` falhou por ausencia de `sh`. Resultado: `TOOL_BLOCKED`.

## Evidencias

- Ledger: `runtime/mission_31b0/dependency_ledger.json`
- Relatorio JSON: `runtime/mission_31b0/security_dependency_report.json`
- Baseline antes: `runtime/mission_31b0/before/`
- Evidencias depois: `runtime/mission_31b0/after/`
- Logs de testes: `runtime/mission_31b0/tests/`
- CodeRabbit: `runtime/mission_31b0/security/`
- Codex Security standard scan anterior: artefato local temporario da ferramenta; caminho absoluto removido deste relatorio para nao registrar path pessoal.

SHA256 ledger: `0E617C5FD739BC170B3B5EC2B05D1A3075F20A05E04403163BA905C0AA36DD68`

SHA256 relatorio JSON: `1712A17DC331DE68E0E2A45F3DF399D9A1705335F7D625323FC95E020DAB4D88`

## Impacto no produto

- Trading: sem alteracao em BUY, SELL, SHORT, COVER, WATCH, HOLD, NO_TRADE, Score Mestre, pesos, thresholds, Ranking ou Decision Envelope.
- Snapshot/cache/API/frontend/Telegram/Push: sem mudanca de contrato operacional.
- Auth: sem nova feature; apenas compatibilidade de tipo do claim `sub` para a versao segura de JWT.
- Runtime auth: deploy sem `SECRET_KEY` valido agora falha fechado em vez de aceitar segredo publico conhecido.

## Riscos residuais

- CodeRabbit final obrigatorio esta bloqueado por indisponibilidade/instalacao da CLI no Windows atual.
- Mobile mantem 12 MODERATE que pedem major de Expo/React Native ou uma missao dedicada.
- Bandit permanece como backlog de seguranca existente.
- `git diff --check` padrao neste repo reporta CRLF como trailing whitespace nas linhas alteradas de arquivos CRLF; nao foi tratado como mudanca funcional.
