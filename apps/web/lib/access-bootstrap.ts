/**
 * Canonical bootstrap contract for entitlement + workspace-mode preference.
 *
 * The race this replaces: three independent effects owned the same state.
 * On the first commit the persistence effect wrote `advancedMode` (still its
 * `false` initial value) straight to storage, so the user's saved "pro"
 * preference was destroyed BEFORE the mount effect could act on it. A later
 * restore then re-read storage and only ever saw the clobbered "simple". Any
 * remount made it permanent, which is why Pro landed on 4-6 of 9 pages.
 *
 * The rules here are deliberately boring: while access is pending nothing is
 * written and nothing is destroyed; the saved preference is applied exactly
 * once when entitlement is confirmed; a denial is fail-closed and is the only
 * path that persists "simple" on the user's behalf.
 *
 * Server-side auth stays the authority. Storage carries a *visual preference*,
 * never an entitlement — `preferPro` alone can never produce `advancedMode`.
 */

export type AccessBootstrapState = "ACCESS_PENDING" | "ACCESS_ALLOWED" | "ACCESS_DENIED";

export type AccessProbe = {
  /** True once the access request settled, whether it succeeded or failed. */
  resolved: boolean;
  /** Server-confirmed entitlement for Pro mode. */
  proAllowed: boolean;
};

export function resolveAccessBootstrap(probe: AccessProbe): AccessBootstrapState {
  if (!probe.resolved) return "ACCESS_PENDING";
  return probe.proAllowed ? "ACCESS_ALLOWED" : "ACCESS_DENIED";
}

export type ModeBootstrapInput = {
  state: AccessBootstrapState;
  /** Whether the one-shot restore already ran. */
  bootstrapped: boolean;
  /** Saved visual preference captured at mount. */
  preferPro: boolean;
  /** Current mode, so a denial only writes when it actually revokes something. */
  advancedMode?: boolean;
};

export type ModeBootstrapDecision = {
  /** Desired advancedMode, or null to leave it untouched. */
  advancedMode: boolean | null;
  /** Value to persist, or null to write nothing. */
  persist: "pro" | "simple" | null;
  /** Whether the bootstrap is complete after this decision. */
  bootstrapped: boolean;
};

/**
 * Single decision point. Idempotent: calling it again with the resulting
 * `bootstrapped` value yields no further writes, so a duplicated effect
 * invocation (React Strict Mode) cannot change the outcome.
 */
export function nextModeBootstrap(input: ModeBootstrapInput): ModeBootstrapDecision {
  if (input.state === "ACCESS_PENDING") {
    // Never assume the user chose basic just because entitlement is in flight.
    return { advancedMode: null, persist: null, bootstrapped: false };
  }

  if (input.state === "ACCESS_DENIED") {
    // Fail closed. "simple" is persisted on the first confirmed denial and on a
    // real revocation — never repeatedly on every re-render.
    const revoking = !input.bootstrapped || input.advancedMode === true;
    return { advancedMode: false, persist: revoking ? "simple" : null, bootstrapped: true };
  }

  if (!input.bootstrapped) {
    return {
      advancedMode: input.preferPro,
      persist: null, // the post-bootstrap persistence effect owns the write
      bootstrapped: true,
    };
  }

  return { advancedMode: null, persist: null, bootstrapped: true };
}

/**
 * Post-bootstrap persistence. A change is only written once the bootstrap has
 * completed, so hydration, symbol changes and re-renders can never rewrite the
 * saved preference.
 */
export function shouldPersistModeChange(bootstrapped: boolean): boolean {
  return bootstrapped;
}
