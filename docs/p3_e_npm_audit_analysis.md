# P3-E — npm Audit Analysis (H10 Release Hardening)

Source: `npm audit --json` inside `/home/dcima/stocknewsbr-h10/apps/web`,
captured to `/tmp/stocknewsbr-h10/npm-audit.json` (exit 0; vulnerabilities reported
in JSON, not audit tool error).

`npm audit fix --dry-run` output captured to `/tmp/stocknewsbr-h10/p3_e_npm_audit_fix_dryrun.json`.

## Audit metadata
- `auditReportVersion`: 2
- `metadata.vulnerabilities`:
  - info: 0
  - low: 0
  - moderate: 0
  - **high: 4**
  - critical: 0
  - total: 4

No moderate or critical advisories. All four are `high`.

## Vulnerability inventory

### 1. `brace-expansion`
- **Severity**: high
- **Direct?**: No — transitive (`node_modules/@typescript-eslint/typescript-estree/node_modules/brace-expansion` and one more under eslint chain)
- **Advisories (5 entries, 3 distinct CVEs)**:
  - GHSA-3jxr-9vmj-r5cp — DoS via exponential-time expansion of consecutive non-expanding `{}` groups — CVSS 5.3 (range `<1.1.16`)
  - GHSA-mh99-v99m-4gvg — DoS via unbounded expansion length causing OOM — CVSS 7.5 (ranges `<1.1.17` and `>=4.0.0 <5.0.8`)
  - GHSA-rgw5-rvv9-x895 — DoS via unbounded intermediate arrays, bypassing CVE-2026-14257 mitigation — CVSS 7.5 (ranges `<1.1.18` and `>=4.0.0 <5.0.9`)
- **Installed ranges**: `<=1.1.17 || 4.0.0 - 5.0.8`
- **Chain**: `eslint` (dev) → `@typescript-eslint/typescript-estree` → `brace-expansion`
- **Presence**: devDependencies only — used at lint time. Not bundled into the Next.js production output (`.next/` build, server chunks).
- **Real exploitability in our context**: ~none at runtime/production. An attacker would need to feed adversarial brace-expansion patterns into the developer's lint-time parser. Build artifacts are not exposed to user input.
- **Fix availability**: `npm audit fix` (no `--force`) — adds 51 packages, changes 2. Late-chain bump of `@typescript-eslint/typescript-estree` introduces many eslint-ecosystem transitive bumps. The lockfile delta is non-trivial (51 added).
- **Recommendation / decision**:
  - Per H10 mission: "Permitir somente patch/minor compatível, após provar: package-lock atualizado de forma controlada; npm ci verde; lint verde; tsc verde; build verde; start verde; sem regressões."
  - The fix touches 51 transitives in the eslint chain, all dev-only. While `--dry-run` says it's "non-breaking", the mission's bar ("sem regressões") requires us to additionally prove no divergence in the actual lint output (24 warnings baseline established in P3-D), the tsc output, and the Next.js build identity (chunk hashes). That re-baseline is high-effort and out of scope for the minimal-hardening H10 window.
  - **Documented as P3 backlog**. The runtime production bundle is not affected — no shipping risk introduced.
  - Mitigating factor: developers running `npm run lint` accept the (theoretical) risk of adversarial brace-expansion input — there is no vector via the canonical StockNewsBR lint inputs.

### 2. `next`
- **Severity**: high
- **Direct?**: Yes (`apps/web/package.json` declares `next: ^15.5.22`)
- **Installed**: 15.5.22 (transitively containing vulnerable `postcss`+`sharp`)
- **Advisories transit through postcss and sharp** (see below)
- **Range flagged vulnerable**: `9.3.4-canary.0 - 16.3.0-preview.10` (i.e. any modern Next version including 15.5.22 until 16.3.0 stable)
- **Fix availability**: `{ "name": "next", "version": "16.3.0", "isSemVerMajor": true }` — **Major upgrade Next 15 → 16 required**.
- **Real exploitability in our context**: indirect — comes from the postcss and sharp transitives (see below).
- **Decision**: **NOT FIXED in H10**. Per mission rules: "Não fazer upgrade major automático", "Atualização em massa de Next ou React" é proibida. Next 15 → 16 is a framework major that often changes routing semantics, Image component behavior, and RSC contracts — certainly outside H10 minimal-hardening scope.
- Documented as P3 backlog. Requires dedicated frontend migration mission.

### 3. `postcss`
- **Severity**: high (but one of the advisories is moderate)
- **Direct?**: No — transitive of `next`
- **Advisories (4 entries)**:
  - GHSA-qx2v-qp2m-jg93 — PostCSS XSS via Unescaped `</style>` in CSS Stringify Output — CVSS 6.1 (moderate; range `<8.5.10`)
  - GHSA-6g55-p6wh-862q — PostCSS Arbitrary file read / information disclosure via attacker-controlled sourceMappingURL in CSS comments — high
  - GHSA-r28c-9q8g-f849 — PostCSS Path Traversal in Previous Source Map Auto-Loading (sourceMappingURL) → Arbitrary `.map` File Disclosure — high
  - GHSA-fxqj-rqcc-2cmp — Incomplete fix of GHSA-6g55-p6wh-862q — arbitrary `.map` file read when `from` is unset — high
- **Installed range flagged vulnerable**: `<=8.5.22`
- **Chain**: `next` → `postcss` (Next's CSS pipeline depends on postcss at build-time and runtime)
- **Real exploitability in our context**:
  - The PostCSS XSS / file-read / path-traversal advisories require attacker-controlled CSS source. In StockNewsBR we author our own CSS — no third-party untrusted CSS is processed by Next's PostCSS pipeline (no user-styling plugins enabled, no style-string interpolation from untrusted input).
  - The `sourceMappingURL` disclosure would also require an attacker controlling a CSS comment in our build pipeline — not possible with the current build flow authored entirely in-app.
  - Production .map file disclosure ["Arbitrary .map File Disclosure"] is a build-time prerender artifact scenario, not user-facing.
- **Fix availability**: `{ "name": "next", "version": "16.3.0", "isSemVerMajor": true }` — major upgrade required.
- **Decision**: **NOT FIXED in H10**. Blocked by mission rule against major upgrades. **No production exposure** with our build pipeline.
- Documented as P3 backlog paired with the Next 16 migration.

### 4. `sharp`
- **Severity**: high
- **Direct?**: No — transitive of `next`
- **Advisory**: GHSA-f88m-g3jw-g9cj — sharp inherited vulnerabilities in libvips: CVE-2026-33327, CVE-2026-33328, CVE-2026-35590, CVE-2026-35591 (no CVSS score in the audit record)
- **Installed range flagged**: `<0.35.0`
- **Chain**: `next` (image optimization runtime) → `sharp`
- **Real exploitability in our context**:
  - `sharp` is used by Next.js's `next/image` optimization pipeline. In StockNewsBR's frontend we still use plain `<img>` (per P3-D lint inventory) — so the `next/image` runtime is not invoked at request time. `sharp` is bundled but inactive in our pipeline today.
  - The libvips CVEs require attacker-controlled input to the image optimizer endpoint. Because `next/image` is not used and we don't expose `/_next/image?url=...` for arbitrary remote images, the attack surface is essentially zero in H10.
- **Fix availability**: `{ "name": "next", "version": "16.3.0", "isSemVerMajor": true }` — major upgrade required.
- **Decision**: **NOT FIXED in H10**. Blocked by mission rule against major upgrades. Exploitability in our current pipeline is ~zero.
- Documented as P3 backlog paired with the Next 16 migration.

## Risk accepted by H10
- Zero critical or moderate advisories.
- All 4 high advisories are either (i) dev-only with no production exposure (`brace-expansion`), or (ii) infrastructure-dependency upgrades that require framework major bump (`next`+`postcss`+`sharp`), which is explicitly forbidden in H10 scope and is the natural subject of a dedicated frontend migration mission.
- The H10 frontend pipeline keeps passing gates: `npm ci` exit 0, `npm run lint` exit 0 (warnings-only), `npm run tsc` exit 0, `npm run build` exit 0, in-vivo `/` → 307 and `/site` → 200 verified.

## Fix action plan (out of H10 scope)
1. **`brace-expansion`** (low-risk but lockfile-heavy): plan a dedicated minimal PR that runs `npm audit fix` (no `--force`), then performs a full re-baseline comparing lint output, tsc output, Next build chunk hashes, and the runtime smoke (`/` → 307, `/site` → 200) before/after the lockfile bump. If any byte of the production `.next` chunks changes for reasons other than brace-expansion's chain, revert.
2. **`next` → 16.3.0** (with `postcss` and `sharp`): plan a Next 15 → 16 migration mission. Validate changes in:
   - App Router conventions
   - `next/image` (relevant if migrating any `<img>` from P3-D backlog)
   - RSC serialization contract
   - `next.config` shape (may deprecate `outputFileTracingRoot` semantics — reconfirm with Next 16)
   - Standalone output mode
   This migration would address 3 of 4 advisories simultaneously and could pair with the P3-D brand-image migration.

## Verdict
H10_P3_E_NPM_AUDIT_DOCUMENTED — 4 high vulnerabilities catalogued, 0 force-applied, 0 risky major upgrades. All advisories either dev-only or framework-major-gated. Mission rules (no `--force`, no major upgrade, no speculative dependency changes) honored. Lint, tsc, build and in-vivo smoke remain green. No production exposure introduced by leaving these advisories open in H10. Vulnerabilities parked as P3 backlog with explicit per-advisory rationale and a follow-up action plan.
