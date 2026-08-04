/**
 * Canonical entitlement authority.
 *
 * What this replaces: `access` had several owners. The bootstrap effect fetched
 * it once, and a second effect re-fetched it inside
 * `Promise.all([getAccess, getWorkspace, getWorkspaceTickerBundle,
 * getPublicMarketBundle])` — so entitlement only committed if four unrelated
 * market-data requests all resolved. When a chart/news bundle was starved or
 * aborted (routine under the browser's per-origin connection limit) the `.then`
 * never ran, `setAccess` never fired, and a premium user silently stayed in
 * Modo Básico. Whether a page got Pro depended on which requests happened to
 * win the connection pool that run — the 4-6/9 flapping.
 *
 * Rules enforced here:
 *   - one logical request per token (single-flight, shared promise);
 *   - a stale response can never overwrite a newer one (generation guard);
 *   - only an explicit 401/403 (or a denying payload) is DENIED;
 *   - transport failures are TRANSIENT_ERROR and never revoke a preference;
 *   - entitlement never depends on market data resolving.
 */

export type AccessState = "UNINITIALIZED" | "PENDING" | "ALLOWED" | "DENIED" | "TRANSIENT_ERROR";

/** Minimal shape this module needs; the app's UserAccess satisfies it. */
export type AccessPayloadLike = {
  plan?: string | null;
  plan_status?: string | null;
} | null;

export const PRO_PLANS = ["trial", "premium", "enterprise"] as const;
export const DEAD_PLAN_STATUSES = ["expired", "inactive", "cancelled", "canceled", "trial_expired"] as const;

/** Server-confirmed entitlement. Storage can never substitute for this. */
export function isProEntitled(access: AccessPayloadLike): boolean {
  if (!access) return false;
  const plan = String(access.plan || "").toLowerCase();
  const status = String(access.plan_status || "").toLowerCase();
  return (PRO_PLANS as readonly string[]).includes(plan) && !(DEAD_PLAN_STATUSES as readonly string[]).includes(status);
}

export type AccessOutcome =
  | { kind: "response"; payload: AccessPayloadLike }
  | { kind: "error"; status?: number };

/**
 * A 200 that does not grant Pro is a real, confirmed answer (DENIED).
 * A 401/403 is a confirmed denial. Everything else — 5xx, timeout, aborted
 * connection, malformed body — is transport noise and must not revoke anything.
 */
export function classifyAccessOutcome(outcome: AccessOutcome): AccessState {
  if (outcome.kind === "response") {
    if (outcome.payload == null || typeof outcome.payload !== "object") {
      // Fail closed without pretending the server denied us.
      return "TRANSIENT_ERROR";
    }
    return isProEntitled(outcome.payload) ? "ALLOWED" : "DENIED";
  }
  if (outcome.status === 401 || outcome.status === 403) return "DENIED";
  return "TRANSIENT_ERROR";
}

/** Retry is only ever justified for transport failures. */
export function isRetryableAccessState(state: AccessState): boolean {
  return state === "TRANSIENT_ERROR";
}

/** A settled state the UI can act on. PENDING/UNINITIALIZED are not terminal. */
export function isTerminalAccessState(state: AccessState): boolean {
  return state === "ALLOWED" || state === "DENIED";
}

/**
 * A response from an older generation (previous token, unmounted page) must
 * never overwrite a newer one.
 */
export function isStaleAccessResponse(responseGeneration: number, currentGeneration: number): boolean {
  return responseGeneration !== currentGeneration;
}

export type AccessCounters = {
  logicalRequests: number;
  networkRequests: number;
  allowed: number;
  denied: number;
  transientError: number;
  staleIgnored: number;
  aborts: number;
};

export function createAccessCounters(): AccessCounters {
  return { logicalRequests: 0, networkRequests: 0, allowed: 0, denied: 0, transientError: 0, staleIgnored: 0, aborts: 0 };
}

type Flight<T> = { key: string; promise: Promise<T> };

/**
 * Single-flight: concurrent consumers of the same key share one promise, so
 * re-renders, symbol switches, tab switches and Strict Mode's double effect
 * cannot multiply the logical request.
 */
export function createSingleFlight<T>() {
  let current: Flight<T> | null = null;
  return {
    run(key: string, factory: () => Promise<T>): Promise<T> {
      if (current && current.key === key) return current.promise;
      const promise = factory().finally(() => {
        if (current && current.key === key && current.promise === promise) current = null;
      });
      current = { key, promise };
      return promise;
    },
    /** Drops the shared flight so a new key starts fresh. */
    reset() {
      current = null;
    },
    get activeKey() {
      return current?.key ?? null;
    },
  };
}

/**
 * Derives the visual mode. Entitlement gates Pro; storage only expresses a
 * preference. A pending or transient state must never destroy that preference.
 */
export function resolveAdvancedMode(input: {
  state: AccessState;
  preferPro: boolean;
  current: boolean;
}): { advancedMode: boolean | null; persist: "pro" | "simple" | null } {
  switch (input.state) {
    case "UNINITIALIZED":
    case "PENDING":
    case "TRANSIENT_ERROR":
      // Hold. Never write, never revoke, never grant.
      return { advancedMode: null, persist: null };
    case "DENIED":
      return { advancedMode: false, persist: input.current ? "simple" : null };
    case "ALLOWED":
      return { advancedMode: input.preferPro, persist: null };
  }
}
