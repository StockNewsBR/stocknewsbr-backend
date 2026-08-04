/**
 * Canonical lifecycle for an AI lens panel (symbol + tool).
 *
 * The defect this removes: the expiry deadline was recreated whenever its
 * anchor changed. The backend flips between LOADING / PENDING / REFRESHING
 * while it polls, and `currentAiKey` can momentarily read empty during a tab
 * switch — each of those recreated the deadline, so the nominal ceiling could
 * never elapse and the panel sat on "Calculando análise…" indefinitely. It
 * showed up as ~0.7% of tab measurements, concentrated on `momentum` (the
 * slowest lens, so the one most likely to still be loading when re-anchored).
 *
 * The rule enforced here is deliberately blunt: a deadline for a key is created
 * ONCE and can never be restarted. It is only removed when the panel reaches a
 * terminal state or the key is explicitly invalidated (symbol change, unmount).
 * Re-renders, status oscillation and Strict Mode's double invocation are all
 * no-ops by construction rather than by timing luck.
 */

export type AiPanelState =
  | "IDLE"
  | "LOADING"
  | "READY"
  | "EMPTY"
  | "EXPIRED"
  | "ERROR"
  | "LOCKED"
  | "UNSUPPORTED";

/** Backend statuses that mean "still working". None of them is terminal. */
export const AI_LOADING_STATUSES = ["LOADING", "PENDING", "REFRESHING"] as const;

export function isAiLoadingStatus(status: string): boolean {
  return (AI_LOADING_STATUSES as readonly string[]).includes(String(status || "").toUpperCase());
}

export type DeadlineRegistry = {
  /** Creates the deadline once; every later call returns the original. */
  ensure(key: string, now: number): number;
  /** True once the original deadline has elapsed. */
  isExpired(key: string, now: number): boolean;
  /** Milliseconds left on the ORIGINAL deadline (never extended). */
  remaining(key: string, now: number): number;
  /** Terminal state reached, or key invalidated. */
  clear(key: string): void;
  /** Drops every deadline whose key belongs to `prefix` (e.g. a symbol). */
  clearPrefix(prefix: string): void;
  clearAll(): void;
  size(): number;
};

export function createDeadlineRegistry(timeoutMs: number): DeadlineRegistry {
  const deadlines = new Map<string, number>();
  return {
    ensure(key, now) {
      const existing = deadlines.get(key);
      // The single most important line in this file: an existing deadline is
      // returned untouched, so nothing can extend it.
      if (existing != null) return existing;
      const at = now + timeoutMs;
      deadlines.set(key, at);
      return at;
    },
    isExpired(key, now) {
      const at = deadlines.get(key);
      return at != null && now >= at;
    },
    remaining(key, now) {
      const at = deadlines.get(key);
      if (at == null) return timeoutMs;
      return Math.max(0, at - now);
    },
    clear(key) {
      deadlines.delete(key);
    },
    clearPrefix(prefix) {
      for (const key of Array.from(deadlines.keys())) {
        if (key.startsWith(prefix)) deadlines.delete(key);
      }
    },
    clearAll() {
      deadlines.clear();
    },
    size() {
      return deadlines.size;
    },
  };
}

export function aiPanelKey(symbol: string, tool: string): string {
  return `${String(symbol || "").toUpperCase()}|${String(tool || "")}`;
}

export type AiPanelInput = {
  /** Normalized backend status for this lens. */
  status: string;
  /** True when the entitlement gate has locked the lens. */
  locked: boolean;
  /** True when the lens published at least one current finding. */
  hasFindings: boolean;
  /** True when the deadline for this key has elapsed. */
  timedOut: boolean;
};

/**
 * Resolves the canonical panel state. A late payload still wins over an expired
 * deadline: EXPIRED only applies while the lens is genuinely still loading, so
 * a result that arrives after the ceiling is shown rather than discarded.
 */
export function resolveAiPanelState(input: AiPanelInput): AiPanelState {
  if (input.locked) return "LOCKED";
  const status = String(input.status || "").toUpperCase();
  if (status === "UNSUPPORTED") return "UNSUPPORTED";
  if (status === "ERROR" || status === "PROVIDER_ERROR") return "ERROR";
  if (input.hasFindings) return "READY";
  if (isAiLoadingStatus(status)) return input.timedOut ? "EXPIRED" : "LOADING";
  if (status === "" || status === "IDLE") return "IDLE";
  return "EMPTY";
}

/** A state the UI can present as a final answer. LOADING never qualifies. */
export function isTerminalAiPanelState(state: AiPanelState): boolean {
  return state !== "LOADING" && state !== "IDLE";
}
