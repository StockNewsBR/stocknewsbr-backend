# Missao 31B.0 - Security Dependencies Hardening

## Status final

Status: `TOOL_BLOCKED`

Motivo: o hardening local foi aplicado e validado, mas o Codex Security obrigatorio nao concluiu. As duas tentativas do `open_codex_security_workspace` falharam com `Transport closed`, tanto no scan completo quanto no diff scan. Pela regra da missao, isso impede declarar `PASS`.

## Repositorio

- Branch: `feat/github-workflow-ai-tools`
- `BASE_COMMIT`: `7ec5e100b73c97953e88a2f57e41e879187c3d48`
- HEAD local inicial: `7ec5e100b73c97953e88a2f57e41e879187c3d48`
- HEAD remoto inicial: `7ec5e100b73c97953e88a2f57e41e879187c3d48`
- 31C: commit sincronizado e usado como base.
- Working tree inicial: limpo.
- Commit/push nesta missao: nao executados.

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

Mudanca de compatibilidade: `create_access_token()` grava `sub` como string no JWT, conforme exigido pelo `python-jose 3.5.0`; `decode_access_token_payload()` segue retornando `payload["sub"]` como `int`, preservando o contrato interno existente.

Testes cobrem token valido com `sub`/`sid`, token expirado, assinatura invalida, claim `sub` ausente, token malformado e `alg=none`.

## Multipart

`python-multipart` foi atualizado para `0.0.31`.

Testes cobrem form/upload valido, form vazio, content-type incorreto e multipart truncado retornando 4xx sem 500 inesperado.

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

- `security-scan`: `TOOL_BLOCKED` (`Transport closed`)
- `security-diff-scan`: `TOOL_BLOCKED` (`Transport closed`)

## CodeRabbit

Primeira revisao encontrou um Major em `data/moderation_state.json`, arquivo nao versionado gerado por teste com estado local. O artefato foi removido. A revisao seguinte apontou um Minor no teste JWT; o teste foi ajustado para validar explicitamente `sub` string no token bruto e `sub` int no contrato publico decodificado.

Rodadas posteriores encontraram Majors no contrato de `sub` do JWT. A emissao agora falha cedo quando `sub` esta ausente, nulo, booleano, nao numerico ou numerico nao canonico. A ultima revisao concluiu com exit code 0 e apenas Minors de cobertura adicional, sem Critical/Major aberto.

## Evidencias

- Ledger: `runtime/mission_31b0/dependency_ledger.json`
- Relatorio JSON: `runtime/mission_31b0/security_dependency_report.json`
- Baseline antes: `runtime/mission_31b0/before/`
- Evidencias depois: `runtime/mission_31b0/after/`
- Logs de testes: `runtime/mission_31b0/tests/`
- CodeRabbit: `runtime/mission_31b0/security/`

SHA256 ledger: `0E617C5FD739BC170B3B5EC2B05D1A3075F20A05E04403163BA905C0AA36DD68`

SHA256 relatorio JSON: `1712A17DC331DE68E0E2A45F3DF399D9A1705335F7D625323FC95E020DAB4D88`

## Impacto no produto

- Trading: sem alteracao em BUY, SELL, SHORT, COVER, WATCH, HOLD, NO_TRADE, Score Mestre, pesos, thresholds, Ranking ou Decision Envelope.
- Snapshot/cache/API/frontend/Telegram/Push: sem mudanca de contrato operacional.
- Auth: sem nova feature; apenas compatibilidade de tipo do claim `sub` para a versao segura de JWT.

## Riscos residuais

- Codex Security obrigatorio nao concluiu, portanto a missao fica bloqueada por ferramenta.
- Mobile mantem 12 MODERATE que pedem major de Expo/React Native ou uma missao dedicada.
- Bandit permanece como backlog de seguranca existente.
- `git diff --check` padrao neste repo reporta CRLF como trailing whitespace nas linhas alteradas de arquivos CRLF; nao foi tratado como mudanca funcional.
