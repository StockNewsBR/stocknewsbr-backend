/**
 * Decision matrix contract — permanent regression tests for the canonical
 * no-data state (lib/decision-state.ts).
 *
 * These assert the CANONICAL field, not the localized copy. The panel used to
 * decide domain state by string-comparing "AGUARDAR DADOS REAIS", which was
 * rewritten in transit and never emitted by the symbol-context path at all.
 *
 * Run: npm run test:decision-matrix
 */
import {
  noDataDecisionCopy,
  normalizeOperationalSide,
  resolveNoDataReason,
  resolveStrategicSide,
  shouldSkipTradeAlignment,
  sideBlocksOperationalValues,
} from "../lib/decision-state.ts";
import type { StrategicDecisionSide } from "../lib/decision-state.ts";

const failures: string[] = [];
let checks = 0;

function check(id: string, actual: unknown, expected: unknown) {
  checks += 1;
  const ok = Object.is(actual, expected);
  if (!ok) failures.push(`${id}: expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
  console.log(`${ok ? "PASS" : "FAIL"}  ${id}`);
}

/** Side the cards would return if the gate let them through. */
const cardsSay = (side: StrategicDecisionSide) => () => side;

// A. core_data=false with a truthy symbol-context decision -> no_data wins.
check(
  "A core_data=false + symbolOperationalView truthy -> no_data",
  resolveStrategicSide({
    reasonCode: resolveNoDataReason({ hasCoreData: false, score: 7.4 }),
    hasCoreData: false,
    executionReady: true,
    resolveSide: cardsSay("buy"),
  }),
  "no_data",
);

// B. core_data=false + executionReady=false -> no_data, never wait.
check(
  "B core_data=false + executionReady=false -> no_data (not wait)",
  resolveStrategicSide({
    reasonCode: resolveNoDataReason({ hasCoreData: false, score: null }),
    hasCoreData: false,
    executionReady: false,
    resolveSide: cardsSay("wait"),
  }),
  "no_data",
);

// C. Complete data -> the normal card read is honoured.
check(
  "C core_data=true + score + missing_fields=[] -> normal decision",
  resolveStrategicSide({
    reasonCode: resolveNoDataReason({ hasCoreData: true, score: 8.1 }),
    hasCoreData: true,
    executionReady: true,
    resolveSide: cardsSay("buy"),
  }),
  "buy",
);

// D. An absent OPTIONAL field must not block a healthy asset. The canonical
// predicate deliberately ignores missing_fields entirely.
check(
  "D core_data=true + optional field missing -> not blocked",
  resolveNoDataReason({ hasCoreData: true, score: 6.2 }),
  null,
);

// E. no_data must suppress stale price/volume/VWAP/targets in the UI.
check("E no_data blocks stale operational values", sideBlocksOperationalValues("no_data"), true);
check("E buy does not block operational values", sideBlocksOperationalValues("buy"), false);

// F/G. Copy is DERIVED from the canonical state, never the reverse.
check("F pt-BR copy", noDataDecisionCopy("pt-BR"), "AGUARDAR DADOS REAIS");
check("G en-US copy", noDataDecisionCopy("en-US"), "WAIT FOR REAL DATA");

// H. An unknown/malformed side may stand aside, never become an operation.
check("H unknown side -> wait", normalizeOperationalSide("TOTALMENTE_DESCONHECIDO"), "wait");
check("H undefined side -> wait", normalizeOperationalSide(undefined), "wait");
check(
  "H unknown side never reaches buy/sell through the gate",
  resolveStrategicSide({
    reasonCode: null,
    hasCoreData: true,
    executionReady: true,
    resolveSide: () => "???" as unknown as StrategicDecisionSide,
  }),
  "wait",
);

// I. Trade alignment must preserve a canonical no-data decision untouched.
check("I alignment skipped for no_data", shouldSkipTradeAlignment("NO_CORE_DATA"), true);
check("I alignment applied for normal decision", shouldSkipTradeAlignment(null), false);

// J. A symbol-context decision cannot outrank the core-data gate.
check(
  "J symbolOperationalView cannot escape the gate",
  resolveStrategicSide({
    reasonCode: "NO_CORE_DATA",
    hasCoreData: true, // context claims data is fine
    executionReady: true,
    resolveSide: cardsSay("sell"),
  }),
  "no_data",
);

// Score is the documented essential field — null score is a no-data state.
check("score=null -> NO_CORE_DATA", resolveNoDataReason({ hasCoreData: true, score: null }), "NO_CORE_DATA");
check("score=NaN -> NO_CORE_DATA", resolveNoDataReason({ hasCoreData: true, score: NaN }), "NO_CORE_DATA");

console.log(JSON.stringify({ checks, failureCount: failures.length, failures }, null, 2));
if (failures.length > 0) process.exit(1);
