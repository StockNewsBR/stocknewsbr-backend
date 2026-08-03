/**
 * Access bootstrap contract — regression tests for the Pro-mode race.
 *
 * The defect: three effects owned the same state and the persistence effect ran
 * first, writing `advancedMode`'s initial `false` to storage and destroying the
 * saved "pro" preference before anything could read it. Pro then landed on only
 * 4-6 of 9 pages depending on effect/commit interleaving.
 *
 * These assert the canonical decision, not copy or aria attributes.
 *
 * Run: npm run test:access-bootstrap
 */
import {
  nextModeBootstrap,
  resolveAccessBootstrap,
  shouldPersistModeChange,
} from "../lib/access-bootstrap.ts";
import type { AccessBootstrapState } from "../lib/access-bootstrap.ts";

const failures: string[] = [];
let checks = 0;

function check(id: string, actual: unknown, expected: unknown) {
  checks += 1;
  const ok = JSON.stringify(actual) === JSON.stringify(expected);
  if (!ok) failures.push(`${id}: expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
  console.log(`${ok ? "PASS" : "FAIL"}  ${id}`);
}

const PENDING: AccessBootstrapState = "ACCESS_PENDING";
const ALLOWED: AccessBootstrapState = "ACCESS_ALLOWED";
const DENIED: AccessBootstrapState = "ACCESS_DENIED";

// A. Pending must not touch the saved preference in any way.
const a = nextModeBootstrap({ state: PENDING, bootstrapped: false, preferPro: true });
check("A pending writes nothing", a.persist, null);
check("A pending leaves mode untouched", a.advancedMode, null);
check("A pending does not complete bootstrap", a.bootstrapped, false);

// B. Saved pro + entitlement confirmed -> Pro, with no click involved.
check(
  "B storage=pro + allowed -> advancedMode=true",
  nextModeBootstrap({ state: ALLOWED, bootstrapped: false, preferPro: true }).advancedMode,
  true,
);

// C. Saved simple + allowed -> stays basic.
check(
  "C storage=simple + allowed -> advancedMode=false",
  nextModeBootstrap({ state: ALLOWED, bootstrapped: false, preferPro: false }).advancedMode,
  false,
);

// D. Denial is fail-closed and is the only path that persists "simple" for the user.
const d = nextModeBootstrap({ state: DENIED, bootstrapped: false, preferPro: true });
check("D denied -> advancedMode=false", d.advancedMode, false);
check("D denied persists simple", d.persist, "simple");

// E. Entitlement arriving before hydration still yields Pro (bootstrap is
//    independent of market-data hydration).
check(
  "E allowed before hydration -> Pro",
  nextModeBootstrap({ state: ALLOWED, bootstrapped: false, preferPro: true }).advancedMode,
  true,
);

// F. Hydration first, access later: the pending pass must preserve the
//    preference so the later allowed pass can still restore it.
const fPending = nextModeBootstrap({ state: PENDING, bootstrapped: false, preferPro: true });
const fAllowed = nextModeBootstrap({ state: ALLOWED, bootstrapped: fPending.bootstrapped, preferPro: true });
check("F preference survives the pending pass", fPending.persist, null);
check("F Pro restored once access arrives", fAllowed.advancedMode, true);

// G. Symbol change after bootstrap must not re-decide the mode.
check(
  "G symbol change leaves mode untouched",
  nextModeBootstrap({ state: ALLOWED, bootstrapped: true, preferPro: true }).advancedMode,
  null,
);

// H. Plain re-render must not re-decide either.
check(
  "H rerender leaves mode untouched",
  nextModeBootstrap({ state: ALLOWED, bootstrapped: true, preferPro: false }).advancedMode,
  null,
);

// I. React Strict Mode double invocation must be idempotent.
const i1 = nextModeBootstrap({ state: ALLOWED, bootstrapped: false, preferPro: true });
const i2 = nextModeBootstrap({ state: ALLOWED, bootstrapped: i1.bootstrapped, preferPro: true });
check("I first pass restores", i1.advancedMode, true);
check("I second pass is a no-op", i2.advancedMode, null);
check("I second pass writes nothing", i2.persist, null);

// J/K. Post-bootstrap the user owns the value; pre-bootstrap nothing persists.
check("J user change persists after bootstrap", shouldPersistModeChange(true), true);
check("K nothing persists before bootstrap", shouldPersistModeChange(false), false);
// Entitlement, never storage, decides Pro: a denied state forces false even
// when the saved preference says pro.
check(
  "K preference alone cannot grant Pro",
  nextModeBootstrap({ state: DENIED, bootstrapped: true, preferPro: true }).advancedMode,
  false,
);

// L. allowed -> denied revokes immediately. Revocation means Pro was active,
// so that is the state under test; a denial with Pro already off must not
// rewrite storage on every re-render.
const l = nextModeBootstrap({ state: DENIED, bootstrapped: true, preferPro: true, advancedMode: true });
check("L revocation is immediate", l.advancedMode, false);
check("L revocation persists simple", l.persist, "simple");
check(
  "L denial with Pro already off does not rewrite storage",
  nextModeBootstrap({ state: DENIED, bootstrapped: true, preferPro: true, advancedMode: false }).persist,
  null,
);

// State resolution itself.
check("resolve: unsettled -> PENDING", resolveAccessBootstrap({ resolved: false, proAllowed: true }), PENDING);
check("resolve: settled + entitled -> ALLOWED", resolveAccessBootstrap({ resolved: true, proAllowed: true }), ALLOWED);
check("resolve: settled + not entitled -> DENIED", resolveAccessBootstrap({ resolved: true, proAllowed: false }), DENIED);

console.log(JSON.stringify({ checks, failureCount: failures.length, failures }, null, 2));
if (failures.length > 0) process.exit(1);
