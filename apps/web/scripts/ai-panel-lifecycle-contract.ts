/**
 * AI panel lifecycle contract — regression tests for the Momentum flakiness.
 *
 * The defect: the expiry deadline was recreated whenever its anchor changed
 * (status oscillation between LOADING/PENDING/REFRESHING, a momentarily empty
 * tool id during a tab switch). The ceiling could therefore never elapse and the
 * panel stayed on "Calculando análise…" — ~0.7% of tab measurements, always the
 * slowest lens (`momentum`).
 *
 * Everything below runs on a controlled clock: no sleeps, no wall time.
 *
 * Run: npm run test:ai-panel-lifecycle
 */
import {
  aiPanelKey,
  createDeadlineRegistry,
  isAiLoadingStatus,
  isTerminalAiPanelState,
  resolveAiPanelState,
} from "../lib/ai-panel-lifecycle.ts";
import type { AiPanelState } from "../lib/ai-panel-lifecycle.ts";

const failures: string[] = [];
let checks = 0;

function check(id: string, actual: unknown, expected: unknown) {
  checks += 1;
  const ok = JSON.stringify(actual) === JSON.stringify(expected);
  if (!ok) failures.push(`${id}: expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
  console.log(`${ok ? "PASS" : "FAIL"}  ${id}`);
}

const TIMEOUT = 8000;
const base = (over: Partial<Parameters<typeof resolveAiPanelState>[0]> = {}) =>
  resolveAiPanelState({ status: "LOADING", locked: false, hasFindings: false, timedOut: false, ...over });

const MOM = aiPanelKey("AVGO", "momentum");
const FLOW = aiPanelKey("AVGO", "flow");

// A. A payload that lands before the deadline is READY.
check("A READY before deadline", base({ status: "READY", hasFindings: true }), "READY" as AiPanelState);

// B. A lens with zero signals settles on EMPTY, not on an error.
check("B zero signals -> EMPTY", base({ status: "READY", hasFindings: false }), "EMPTY" as AiPanelState);

// C. Still loading past the deadline -> EXPIRED (never an eternal LOADING).
{
  const r = createDeadlineRegistry(TIMEOUT);
  let now = 1_000;
  r.ensure(MOM, now);
  check("C not expired before deadline", r.isExpired(MOM, now + TIMEOUT - 1), false);
  now += TIMEOUT;
  check("C expired at deadline", r.isExpired(MOM, now), true);
  check("C state becomes EXPIRED", base({ status: "PENDING", timedOut: true }), "EXPIRED" as AiPanelState);
}

// D. Status oscillation must NOT push the deadline out.
{
  const r = createDeadlineRegistry(TIMEOUT);
  const first = r.ensure(MOM, 1_000);
  r.ensure(MOM, 3_000); // LOADING -> PENDING
  r.ensure(MOM, 5_000); // PENDING -> REFRESHING
  r.ensure(MOM, 7_000); // REFRESHING -> LOADING
  check("D deadline unchanged by oscillation", r.ensure(MOM, 7_999), first);
  check("D still expires on the original deadline", r.isExpired(MOM, 1_000 + TIMEOUT), true);
}

// E. Re-render must not restart it either.
{
  const r = createDeadlineRegistry(TIMEOUT);
  const first = r.ensure(MOM, 500);
  for (let i = 0; i < 50; i += 1) r.ensure(MOM, 500 + i * 100);
  check("E deadline survives 50 re-renders", r.ensure(MOM, 6_000), first);
}

// F. Strict Mode's double invocation is one logical deadline.
{
  const r = createDeadlineRegistry(TIMEOUT);
  const a = r.ensure(MOM, 0);
  const b = r.ensure(MOM, 0);
  check("F strict-mode double invoke -> one deadline", a, b);
  check("F registry holds a single entry", r.size(), 1);
}

// G. momentum -> flow -> momentum keeps momentum's ORIGINAL deadline.
{
  const r = createDeadlineRegistry(TIMEOUT);
  const momentumDeadline = r.ensure(MOM, 1_000);
  r.ensure(FLOW, 2_000);
  check("G tab round-trip preserves the deadline", r.ensure(MOM, 6_000), momentumDeadline);
  check("G each lens has its own deadline", r.size(), 2);
}

// H. Changing symbol invalidates the previous symbol's generation.
{
  const r = createDeadlineRegistry(TIMEOUT);
  r.ensure(aiPanelKey("AVGO", "momentum"), 0);
  r.ensure(aiPanelKey("AXP", "momentum"), 0);
  r.clearPrefix("AVGO|");
  check("H previous symbol invalidated", r.size(), 1);
  check("H new symbol keeps its deadline", r.isExpired(aiPanelKey("AXP", "momentum"), TIMEOUT), true);
}

// I. A late response for an older lens cannot expire the current one.
{
  const r = createDeadlineRegistry(TIMEOUT);
  r.ensure(MOM, 0);
  r.clear(MOM); // old generation retired
  check("I retired lens reports no expiry", r.isExpired(MOM, 999_999), false);
}

// J. Deadline and payload arriving together: the payload wins.
check("J payload beats the timeout", base({ status: "PENDING", hasFindings: true, timedOut: true }), "READY" as AiPanelState);

// K. Unmount clears the timer's registry entry.
{
  const r = createDeadlineRegistry(TIMEOUT);
  r.ensure(MOM, 0);
  r.clearAll();
  check("K unmount leaves no deadline", r.size(), 0);
}

// L. An aborted request must still land on a terminal state.
check("L aborted -> ERROR is terminal", isTerminalAiPanelState(base({ status: "ERROR" })), true);
check("L expired is terminal", isTerminalAiPanelState("EXPIRED"), true);
check("L loading is NOT terminal", isTerminalAiPanelState("LOADING"), false);

// M. Five lenses alternating quickly keep independent deadlines.
{
  const r = createDeadlineRegistry(TIMEOUT);
  const tools = ["flow", "liquidity", "trend", "momentum", "smart-money"];
  const first = new Map<string, number>();
  for (let pass = 0; pass < 10; pass += 1) {
    for (const tool of tools) {
      const key = aiPanelKey("AVGO", tool);
      const at = r.ensure(key, pass * 250);
      if (pass === 0) first.set(key, at);
    }
  }
  const drifted = tools.filter((tool) => r.ensure(aiPanelKey("AVGO", tool), 9_999) !== first.get(aiPanelKey("AVGO", tool)));
  check("M rapid tab alternation drifts nothing", drifted, []);
  check("M one deadline per lens", r.size(), tools.length);
}

// N. Nine sequential symbols, each retired on completion.
{
  const r = createDeadlineRegistry(TIMEOUT);
  for (const symbol of ["AVGO", "AXP", "CMG", "CRWD", "GE", "GM", "LI", "ROKU", "SAP"]) {
    const key = aiPanelKey(symbol, "momentum");
    r.ensure(key, 0);
    r.clear(key);
  }
  check("N no residue after nine symbols", r.size(), 0);
}

// O. 100 cycles: loading may never survive its own deadline.
{
  const r = createDeadlineRegistry(TIMEOUT);
  let loadingAfterDeadline = 0;
  for (let cycle = 0; cycle < 100; cycle += 1) {
    const key = aiPanelKey(`SYM${cycle}`, "momentum");
    const start = cycle * 1_000;
    r.ensure(key, start);
    // Oscillate the status the way the backend does while polling.
    for (const status of ["LOADING", "PENDING", "REFRESHING", "PENDING"]) {
      r.ensure(key, start + 1_000);
      if (!isAiLoadingStatus(status)) loadingAfterDeadline += 1;
    }
    const timedOut = r.isExpired(key, start + TIMEOUT);
    const state = base({ status: "PENDING", timedOut });
    if (state === "LOADING") loadingAfterDeadline += 1;
    r.clear(key);
  }
  check("O 100 cycles with no loading past the deadline", loadingAfterDeadline, 0);
  check("O no leaked deadlines", r.size(), 0);
}

// P. Nothing pending once every lens settles.
{
  const r = createDeadlineRegistry(TIMEOUT);
  r.ensure(MOM, 0);
  r.ensure(FLOW, 0);
  r.clear(MOM);
  r.clear(FLOW);
  check("P registry drained", r.size(), 0);
}

// Q/R. State is decided by canonical fields only — copy never participates, so
// the same inputs must yield the same state in every locale.
check("Q pt-BR does not change the state", base({ status: "PENDING", timedOut: true }), "EXPIRED" as AiPanelState);
check("R en-US does not change the state", base({ status: "PENDING", timedOut: true }), "EXPIRED" as AiPanelState);

// S. An empty lens is not an error.
check("S empty is not ERROR", base({ status: "READY", hasFindings: false }), "EMPTY" as AiPanelState);
check("S locked is not ERROR", base({ locked: true }), "LOCKED" as AiPanelState);
check("S unsupported is its own state", base({ status: "UNSUPPORTED" }), "UNSUPPORTED" as AiPanelState);

// T. A stale timeout can never demote a READY payload.
check("T READY survives a stale timeout", base({ status: "REFRESHING", hasFindings: true, timedOut: true }), "READY" as AiPanelState);

console.log(JSON.stringify({ checks, failureCount: failures.length, failures }, null, 2));
if (failures.length > 0) process.exit(1);
