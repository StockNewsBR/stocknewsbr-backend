/**
 * Canonical authority for the "no operational data" domain state.
 *
 * Why this module exists: the strategic panel used to decide domain state by
 * comparing `operationalDecision.action` against localized copy
 * ("AGUARDAR DADOS REAIS" / "WAIT FOR REAL DATA"). That is a presentation
 * string — it is rewritten in transit by alignment helpers and is never emitted
 * at all by the symbol-context path, so the check silently failed open.
 *
 * Domain state is decided here, from canonical fields only. Localized copy is
 * derived from the state, never the other way around.
 */

export type StrategicDecisionSide = "buy" | "sell" | "wait" | "exit" | "no_data";

/** Canonical reason a decision carries no operational read. */
export type OperationalReasonCode = "NO_CORE_DATA";

/**
 * Canonical quote field ids that must be present for an operational read.
 * These are backend field ids, never translated labels.
 */
export const CORE_QUOTE_FIELD_IDS = ["price", "volume"] as const;

/**
 * Canonical analysis field ids required before any buy/sell side is emitted.
 * `score` is essential: confidence is derived from it, so a null score cannot
 * produce an honest operational conviction. This is the documented contract —
 * it must not be re-derived from an accidental card position.
 */
export const ESSENTIAL_ANALYSIS_FIELD_IDS = ["score"] as const;

export type CoreDataProbe = {
  /** Canonical backend `core_data` flag, already combined with price/volume presence. */
  hasCoreData: boolean;
  /** Canonical Master Score, or null when the backend did not confirm one. */
  score: number | null;
};

/**
 * The single completeness predicate. Returns the canonical reason code when the
 * symbol has no operational read, or null when a normal decision may proceed.
 *
 * Deliberately does NOT consider `missing_fields`: an optional field being
 * absent must never block an otherwise healthy asset. Only the canonical core
 * data flag and the essential score gate the decision.
 */
export function resolveNoDataReason(probe: CoreDataProbe): OperationalReasonCode | null {
  if (probe.hasCoreData === false) return "NO_CORE_DATA";
  if (probe.score == null || !Number.isFinite(probe.score)) return "NO_CORE_DATA";
  return null;
}

/** True when the canonical state is "no operational data". */
export function isNoDataReason(reasonCode: OperationalReasonCode | null | undefined): boolean {
  return reasonCode === "NO_CORE_DATA";
}

/**
 * Presentation copy for the canonical no-data state. This is the ONLY place the
 * localized strings are produced — they are derived from the state, and are
 * never read back as a logical authority.
 */
export function noDataDecisionCopy(locale: string): string {
  return locale === "en-US" ? "WAIT FOR REAL DATA" : "AGUARDAR DADOS REAIS";
}

/**
 * Degrades any unrecognized side to `wait`. An unknown or malformed decision may
 * stand aside, but it must never be promoted into a buy/sell operation.
 */
export function normalizeOperationalSide(side: unknown): StrategicDecisionSide {
  return side === "buy" || side === "sell" || side === "exit" || side === "no_data" || side === "wait"
    ? side
    : "wait";
}

export type StrategicSideInput = {
  /** Canonical reason code carried by the operational decision. */
  reasonCode: OperationalReasonCode | null | undefined;
  /** Canonical core-data flag observed by the panel itself. */
  hasCoreData: boolean;
  /** False when execution components are not confirmed yet. */
  executionReady?: boolean;
  /** Lazy fallback that reads the decision cards. Only called when data is complete. */
  resolveSide: () => StrategicDecisionSide;
};

/**
 * Resolves the strategic side with a fixed, documented priority:
 *
 *   1. no_data  — canonical reason code OR core data absent
 *   2. wait     — execution components not confirmed
 *   3. cards    — the normal buy/sell/exit/wait read
 *
 * `no_data` outranks `wait` so a missing snapshot can never be presented as a
 * confirmable setup, and it outranks any symbol-context decision so a truthy
 * context cannot escape the core-data gate.
 */
export function resolveStrategicSide(input: StrategicSideInput): StrategicDecisionSide {
  if (isNoDataReason(input.reasonCode) || input.hasCoreData === false) return "no_data";
  if (input.executionReady === false) return "wait";
  return normalizeOperationalSide(input.resolveSide());
}

/**
 * Guard for alignment helpers: a decision in the canonical no-data state must
 * pass through untouched. Alignment rewrites presentation copy, and rewriting
 * the action of a no-data decision is what previously turned it back into a
 * plain "wait".
 */
export function shouldSkipTradeAlignment(reasonCode: OperationalReasonCode | null | undefined): boolean {
  return isNoDataReason(reasonCode);
}

/**
 * True when the side carries no operational read and therefore must not render
 * stale price, volume, VWAP, targets, entries or invalidation levels.
 */
export function sideBlocksOperationalValues(side: StrategicDecisionSide): boolean {
  return side === "no_data";
}
