/**
 * Shared ephemeral authentication fixture for the Playwright audit suites.
 *
 * One auth contract for every suite: a short-lived JWT minted at runtime against
 * a synthetic user, verified against a hard TTL ceiling, applied per browser
 * context, and revoked when the suite ends. No literal token ever lives in a
 * committable file, and the token is never passed as a process argument, logged,
 * or written to a report.
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { execFileSync } from "node:child_process";

const moduleDir = path.dirname(fileURLToPath(import.meta.url));
export const REPO_ROOT = path.resolve(moduleDir, "..", "..", "..", "..");

// Interpreter resolved from the repo root or active conda/venv — never searched blindly on the system PATH.
export const PYTHON_PATH = process.env.PYTHON_PATH || 
  (process.env.CONDA_PREFIX ? path.join(process.env.CONDA_PREFIX, "bin", "python") : 
  (process.env.VIRTUAL_ENV ? path.join(process.env.VIRTUAL_ENV, "bin", "python") : 
  path.resolve(REPO_ROOT, "venv", "bin", "python")));
export const TOKEN_TTL_MAX_SECONDS = 600;

const TOKEN_SCRIPT = `
import json, sys, os, uuid, datetime
sys.path.insert(0, os.getcwd())
os.environ['ACCESS_TOKEN_EXPIRE_MINUTES'] = '10'

from app.database import SessionLocal
from app.models import User, UserSession
from app.security import create_access_token

db = SessionLocal()
try:
    if not db.query(User).filter_by(id=1).first():
        db.add(User(id=1, email='mission-audit@stocknewsbr.local', is_active=True))
        db.commit()
    sid = str(uuid.uuid4())
    db.add(UserSession(
        user_id=1,
        session_id=sid,
        expires_at=datetime.datetime.utcnow() + datetime.timedelta(minutes=10),
    ))
    db.commit()
    print(json.dumps({'token': create_access_token({'sub': '1', 'sid': sid}), 'sid': sid}))
finally:
    db.close()
`;

const SESSION_CLEANUP_SCRIPT = `
import json, sys, os
sys.path.insert(0, os.getcwd())
from app.database import SessionLocal
from app.models import UserSession

sid = sys.stdin.read().strip()
db = SessionLocal()
try:
    db.query(UserSession).filter_by(session_id=sid).delete()
    db.commit()
    print(json.dumps({'remaining': db.query(UserSession).filter_by(session_id=sid).count()}))
finally:
    db.close()
`;

const SESSION_COUNT_SCRIPT = `
import json, sys, os
sys.path.insert(0, os.getcwd())
from app.database import SessionLocal
from app.models import UserSession

db = SessionLocal()
try:
    print(json.dumps({'count': db.query(UserSession).count()}))
finally:
    db.close()
`;

const SYNTHETIC_SESSION_CLEANUP_SCRIPT = `
import json, sys, os
sys.path.insert(0, os.getcwd())
from app.database import SessionLocal
from app.models import User, UserSession

prefixes = json.loads(sys.stdin.read() or '[]')
db = SessionLocal()
try:
    user_ids = {
        row[0]
        for prefix in prefixes
        for row in db.query(User.id).filter(User.email.like(str(prefix) + '%')).all()
    }
    if user_ids:
        db.query(UserSession).filter(UserSession.user_id.in_(user_ids)).delete(synchronize_session=False)
        db.commit()
    remaining = db.query(UserSession).filter(UserSession.user_id.in_(user_ids)).count() if user_ids else 0
    print(json.dumps({'remaining': remaining}))
finally:
    db.close()
`;

// shell=false + explicit argv: nothing sensitive reaches a process argument.
function runPython(script, input) {
  return execFileSync(PYTHON_PATH, ["-c", script], {
    cwd: REPO_ROOT,
    encoding: "utf8",
    shell: false,
    input: input ?? "",
    env: {
      ...process.env,
      PYTHONPATH: REPO_ROOT,
      ACCESS_TOKEN_EXPIRE_MINUTES: "10",
      PYTHONDONTWRITEBYTECODE: "1",
    },
  }).trim();
}

export function decodeJwtPayload(token) {
  const segment = String(token || "").split(".")[1];
  if (!segment) throw new Error("malformed token");
  const base64 = segment.replace(/-/g, "+").replace(/_/g, "/");
  return JSON.parse(Buffer.from(base64, "base64").toString("utf8"));
}

/**
 * Mints an ephemeral session. Fails closed: a missing interpreter, a failed
 * generation, or a TTL above the ceiling aborts the run rather than degrading.
 */
export function generateEphemeralSession() {
  if (!fs.existsSync(PYTHON_PATH)) {
    throw new Error(`Ephemeral auth unavailable: expected interpreter at ${PYTHON_PATH}`);
  }
  let parsed;
  try {
    parsed = JSON.parse(runPython(TOKEN_SCRIPT));
  } catch (error) {
    throw new Error(`Failed to generate ephemeral token: ${String(error?.message || error).slice(0, 200)}`);
  }
  if (!parsed?.token || !parsed?.sid) {
    throw new Error("Ephemeral auth returned an incomplete session payload");
  }
  // TTL is verified on the issued token itself, so the ceiling never depends on
  // Python import order honouring ACCESS_TOKEN_EXPIRE_MINUTES.
  let ttlSeconds;
  try {
    const payload = decodeJwtPayload(parsed.token);
    ttlSeconds = Number(payload.exp) - Number(payload.iat);
  } catch (error) {
    throw new Error(`Could not read token expiry: ${String(error?.message || error).slice(0, 120)}`);
  }
  if (!Number.isFinite(ttlSeconds) || ttlSeconds <= 0 || ttlSeconds > TOKEN_TTL_MAX_SECONDS) {
    throw new Error(`Ephemeral token TTL ${ttlSeconds}s exceeds the ${TOKEN_TTL_MAX_SECONDS}s ceiling`);
  }
  return { token: parsed.token, sid: parsed.sid, ttlSeconds };
}

/** Removes the ephemeral session row. Returns remaining rows (0 when clean). */
export function revokeEphemeralSession(sid) {
  try {
    const result = JSON.parse(runPython(SESSION_CLEANUP_SCRIPT, sid));
    return Number(result?.remaining ?? -1);
  } catch (error) {
    console.error("Failed to revoke ephemeral session:", String(error?.message || error).slice(0, 120));
    return -1;
  }
}

export function sessionIdFromToken(token) {
  const sid = decodeJwtPayload(token).sid;
  if (!sid) throw new Error("token has no session id");
  return String(sid);
}

export function revokeTokenSession(token) {
  return revokeEphemeralSession(sessionIdFromToken(token));
}

export function countSessions() {
  return Number(JSON.parse(runPython(SESSION_COUNT_SCRIPT))?.count ?? -1);
}

export function cleanupSyntheticSessions(prefixes) {
  const values = Array.isArray(prefixes) ? prefixes : [prefixes];
  return Number(JSON.parse(runPython(SYNTHETIC_SESSION_CLEANUP_SCRIPT, JSON.stringify(values)))?.remaining ?? -1);
}

/**
 * Applies auth to a browser context before any page exists, so it is in place
 * before React mounts. Scoped to the context — never inherited across scenarios.
 */
export async function applyEphemeralAuth(context, token, options = {}) {
  await context.addCookies([
    {
      name: "snb_session",
      value: token,
      domain: options.cookieDomain || "127.0.0.1",
      path: "/",
      httpOnly: true,
      sameSite: "Lax",
    },
  ]);
  await context.addInitScript((value) => {
    try {
      window.localStorage.setItem("stocknewsbr.auth_token", value);
      window.localStorage.setItem("stocknewsbr.workspace_mode", "pro");
      // Test-only probe: count what the app persists for the mode preference,
      // so a regression that clobbers it during bootstrap is visible as data.
      const counters = { pro: 0, simple: 0 };
      window.__snbrModePersistCounters = counters;
      const nativeSetItem = window.localStorage.setItem.bind(window.localStorage);
      window.localStorage.setItem = (key, val) => {
        if (key === "stocknewsbr.workspace_mode") {
          if (val === "pro") counters.pro += 1;
          else if (val === "simple") counters.simple += 1;
        }
        return nativeSetItem(key, val);
      };
    } catch {}
  }, token);
  await context.route("**/*auth/access*", (route) =>
    route
      .fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          user_id: 1,
          email: "mission-audit@stocknewsbr.local",
          display_name: "Mission Audit",
          plan: "premium",
          plan_status: "active",
          is_active: true,
          access_web: true,
          access_app: true,
        }),
      })
      .catch(() => undefined),
  );
}

/**
 * Deterministic Pro mode.
 *
 * Waits on the canonical entitlement state, not on timing. With a stored "pro"
 * preference the authority restores Pro on its own, so `clicks` staying 0 is an
 * assertion about the product, not a convenience.
 */
export async function enableProMode(page, options = {}) {
  const timeout = options.timeoutMs ?? 20000;
  const toggle = page.locator(".snbr-mode-toggle").first();

  // 1. Wait for a terminal entitlement state (ALLOWED or DENIED).
  await page
    .waitForFunction(
      () => {
        const a = window.__snbrAccess;
        return Boolean(a) && (a.state === "ALLOWED" || a.state === "DENIED");
      },
      undefined,
      { timeout },
    )
    .catch(() => undefined);

  // 2. The authority applies the stored preference by itself.
  await page
    .waitForFunction(
      () => document.querySelector(".snbr-mode-toggle")?.getAttribute("aria-pressed") === "true",
      undefined,
      { timeout: 8000 },
    )
    .catch(() => undefined);

  const restored = (await toggle.getAttribute("aria-pressed").catch(() => null)) === "true";
  let clicks = 0;

  // 3. Exactly one click, and only if the stored preference was not pro.
  if (!restored && (await toggle.getAttribute("aria-disabled").catch(() => null)) === "false") {
    clicks = 1;
    await toggle.evaluate((element) => {
      if (element instanceof HTMLElement) element.click();
    }).catch(() => undefined);
    await page
      .waitForFunction(
        () => document.querySelector(".snbr-mode-toggle")?.getAttribute("aria-pressed") === "true",
        undefined,
        { timeout: 5000 },
      )
      .catch(() => undefined);
  }

  const access = await page.evaluate(() => window.__snbrAccess || {}).catch(() => ({}));
  const persist = await page.evaluate(() => window.__snbrModePersistCounters || { pro: 0, simple: 0 }).catch(() => ({ pro: 0, simple: 0 }));
  return {
    ok: (await toggle.getAttribute("aria-pressed").catch(() => null)) === "true",
    accessState: access.state ?? null,
    ACCESS_LOGICAL_REQUEST_COUNT: access.logicalRequests ?? 0,
    ACCESS_NETWORK_REQUEST_COUNT: access.networkRequests ?? 0,
    ACCESS_ALLOWED_COUNT: access.allowed ?? 0,
    ACCESS_DENIED_COUNT: access.denied ?? 0,
    ACCESS_TRANSIENT_ERROR_COUNT: access.transientError ?? 0,
    ACCESS_STALE_RESPONSE_IGNORED_COUNT: access.staleIgnored ?? 0,
    ACCESS_ABORT_COUNT: access.aborts ?? 0,
    restored,
    clicks,
    persistPro: persist.pro || 0,
    persistSimple: persist.simple || 0,
  };
}
