// ==========================================================
// MISSION 31B.1 - OFFICIAL ACCOUNTS / ANTI-IMPERSONATION AUDIT
// ==========================================================
// API-level audit (no browser). Exercises the anti-impersonation gate,
// payload hardening and the forge-proof badge flags against a running backend.
//
// Requires (optional):
//   - backend at MISSION31B1_API_BASE (default http://127.0.0.1:8000)
// If the backend is unreachable the audit degrades to SKIPPED (exit 0) so it
// never hard-fails a CI run that did not boot a server. The report NEVER
// contains tokens, cookies, passwords or OTP codes.

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(scriptDir, "..", "..", "..");
const runtimeDir = path.join(repoRoot, "runtime");
const reportPath = path.join(runtimeDir, "mission_31b1_official_accounts_report.json");
const API_BASE = (process.env.MISSION31B1_API_BASE || "http://127.0.0.1:8000").replace(/\/$/, "");

const checks = [];
const record = (name, ok, detail) => {
  checks.push({ name, status: ok === null ? "SKIPPED" : ok ? "PASS" : "FAIL", detail });
};

async function api(pathname, { token, ...options } = {}) {
  const headers = { "content-type": "application/json", ...(options.headers || {}) };
  if (token) headers["authorization"] = `Bearer ${token}`;
  const res = await fetch(`${API_BASE}${pathname}`, { ...options, headers });
  let body = null;
  try {
    body = await res.json();
  } catch {
    body = null;
  }
  return { status: res.status, body };
}

let counter = 0;
const uniqueEmail = () => {
  counter += 1;
  return `audit31b1_${Date.now()}_${counter}@example.com`;
};

function register(displayName, extra = {}) {
  return api("/auth/register", {
    method: "POST",
    body: JSON.stringify({
      email: uniqueEmail(),
      password: "auditpass123",
      display_name: displayName,
      accepted_terms: true,
      accepted_privacy: true,
      accepted_risk_notice: true,
      ...extra,
    }),
  });
}

async function main() {
  // Reachability probe: require the StockNewsBR backend to answer /auth/bootstrap
  // with 200. Anything else (connection error, or a foreign service returning
  // 404/5xx) degrades to SKIPPED so the audit never hard-fails without a server.
  let reachable = false;
  let probeDetail = "";
  try {
    const probe = await fetch(`${API_BASE}/auth/bootstrap`, { method: "GET" });
    reachable = probe.status === 200;
    probeDetail = `status=${probe.status}`;
  } catch (err) {
    probeDetail = String(err && err.message ? err.message : err);
  }
  if (!reachable) {
    const report = {
      mission: "31B.1",
      api_base: API_BASE,
      status: "SKIPPED_BACKEND_UNREACHABLE",
      detail: probeDetail,
      checks: [],
    };
    fs.mkdirSync(runtimeDir, { recursive: true });
    fs.writeFileSync(reportPath, JSON.stringify(report, null, 2));
    console.log(`[SKIP] StockNewsBR backend not answering at ${API_BASE} (${probeDetail}) -> ${reportPath}`);
    process.exit(0);
  }

  // 1) Anti-impersonation: reserved / official-looking identities are blocked (400).
  const reserved = [
    "stocknewsbr",
    "StockNewsBR Oficial",
    "StockNewsBR Suporte",
    "admin",
    "suporte",
    "Conta Oficial",
    "SтockNewsBR", // Cyrillic homoglyph
  ];
  for (const name of reserved) {
    const r = await register(name);
    record(`register blocks reserved '${name}'`, r.status === 400, `status=${r.status}`);
  }

  // 2) Clean registration succeeds.
  const clean = await register("Auditor Limpo");
  const cleanOk = clean.status === 200 && clean.body && typeof clean.body.access_token === "string";
  record("register clean identity succeeds", cleanOk, `status=${clean.status}`);
  const token = cleanOk ? clean.body.access_token : null;

  // 3) Register payload cannot escalate (official/role/is_bot ignored -> still 200).
  const escalated = await register("Auditor Payload", { official: true, role: "admin", is_bot: true });
  record("register ignores escalation payload", escalated.status === 200, `status=${escalated.status}`);

  // 4) Authenticated profile checks (best-effort; SKIPPED if bearer not accepted).
  if (token) {
    const me = await api("/auth/me", { token });
    if (me.status === 401) {
      record("profile checks (bearer auth)", null, "backend requires cookie session; covered by pytest");
    } else {
      record(
        "GET /me exposes forge-proof flags",
        me.body && "official" in me.body && "verified" in me.body && "role" in me.body && "is_bot" in me.body,
        `status=${me.status}`
      );
      record(
        "regular user badge is false",
        me.body && me.body.official === false && me.body.role === "user" && me.body.is_bot === false,
        `official=${me.body && me.body.official} role=${me.body && me.body.role}`
      );

      const p1 = await api("/auth/profile", { token, method: "PATCH", body: JSON.stringify({ official: true }) });
      record("PATCH /profile rejects official=true", p1.status === 422, `status=${p1.status}`);

      const p2 = await api("/auth/profile", { token, method: "PATCH", body: JSON.stringify({ role: "admin" }) });
      record("PATCH /profile rejects role=admin", p2.status === 422, `status=${p2.status}`);

      const p3 = await api("/auth/profile", {
        token,
        method: "PATCH",
        body: JSON.stringify({ display_name: "StockNewsBR Oficial" }),
      });
      record("PATCH /profile blocks impersonating display_name", p3.status === 400, `status=${p3.status}`);

      const p4 = await api("/auth/profile", {
        token,
        method: "PATCH",
        body: JSON.stringify({ display_name: "Nome Limpo Auditor" }),
      });
      const p4ok = p4.status === 200 && p4.body && p4.body.official === false;
      record("PATCH /profile allows clean display_name without badge", p4ok, `status=${p4.status}`);
    }
  } else {
    record("profile checks (bearer auth)", null, "no token from register; covered by pytest");
  }

  const passed = checks.filter((c) => c.status === "PASS").length;
  const failed = checks.filter((c) => c.status === "FAIL").length;
  const skipped = checks.filter((c) => c.status === "SKIPPED").length;

  const report = {
    mission: "31B.1",
    api_base: API_BASE,
    status: failed === 0 ? "PASS" : "FAIL",
    summary: { passed, failed, skipped, total: checks.length },
    checks,
  };
  fs.mkdirSync(runtimeDir, { recursive: true });
  fs.writeFileSync(reportPath, JSON.stringify(report, null, 2));

  for (const c of checks) console.log(`[${c.status}] ${c.name} (${c.detail})`);
  console.log(`\n31B.1 audit: ${passed} passed, ${failed} failed, ${skipped} skipped -> ${reportPath}`);
  process.exit(failed === 0 ? 0 : 1);
}

main().catch((err) => {
  console.error("audit error:", err);
  process.exit(1);
});
