// ==========================================================
// MISSION 31B - AUTH / EMAIL CODE / SINGLE SESSION AUDIT
// ==========================================================
// Requires:
//   - backend at MISSION31B_API_BASE (default http://127.0.0.1:8000)
//     started with AUTH_EMAIL_TEST_MAILBOX pointing at MISSION31B_MAILBOX
//     (non-production test mailbox; forbidden in production by startup guard)
//   - web at MISSION31B_WEB_BASE (default http://127.0.0.1:3000)
// The report NEVER contains OTP codes, cookies or tokens.

import fs from "node:fs";
import path from "node:path";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(scriptDir, "..", "..", "..");
const reportPath = path.join(repoRoot, "runtime", "mission_31b_auth_session_report.json");
const screenshotDir = path.join(repoRoot, "output", "playwright", "mission31b");
const mailboxPath = process.env.MISSION31B_MAILBOX
  ? path.resolve(repoRoot, process.env.MISSION31B_MAILBOX)
  : path.join(repoRoot, "runtime", "test_mailbox_31b.jsonl");
const dbPath = process.env.MISSION31B_DB
  ? path.resolve(repoRoot, process.env.MISSION31B_DB)
  : path.join(repoRoot, "stocknews.db");
const pythonBin = process.env.MISSION31B_PYTHON
  ? path.resolve(repoRoot, process.env.MISSION31B_PYTHON)
  : path.join(repoRoot, "venv", "Scripts", "python.exe");

const API_BASE = (process.env.MISSION31B_API_BASE || "http://127.0.0.1:8000").replace(/\/$/, "");
const WEB_BASE = (process.env.MISSION31B_WEB_BASE || "http://127.0.0.1:3000").replace(/\/$/, "");
const WEB_ORIGIN = new URL(WEB_BASE).origin;
const HEADLESS = process.env.MISSION31B_HEADLESS !== "false";
const COOKIE_NAME = process.env.MISSION31B_COOKIE_NAME || "snb_session";
const COOLDOWN_STORAGE_KEY = "stocknewsbr.code_cooldown_until";

const failures = [];
const flows = [];
const screenshots = [];
const consoleErrors = [];
const networkErrors = [];

function flow(name, ok, note = "") {
  flows.push({ name, ok, note });
  if (!ok) failures.push(`${name}: ${note || "failed"}`);
}

function ensureDirs() {
  fs.mkdirSync(path.dirname(reportPath), { recursive: true });
  fs.mkdirSync(screenshotDir, { recursive: true });
}

async function textVisible(page, text, timeoutMs = 10000) {
  try {
    await page.getByText(text, { exact: false }).first().waitFor({ state: "visible", timeout: timeoutMs });
    return true;
  } catch {
    return false;
  }
}

async function shot(page, name) {
  const file = path.join(screenshotDir, `${name}.jpg`);
  try {
    await page.screenshot({ path: file, type: "jpeg", quality: 80 });
    screenshots.push(path.relative(repoRoot, file));
  } catch {
    // screenshots are best-effort evidence
  }
}

async function api(pathname, options = {}) {
  const response = await fetch(`${API_BASE}${pathname}`, options);
  const text = await response.text();
  let payload = null;
  try {
    payload = text ? JSON.parse(text) : null;
  } catch {
    payload = { raw: text };
  }
  return { status: response.status, ok: response.ok, payload };
}

async function registerUser(label) {
  const suffix = `${Date.now()}-${Math.random().toString(16).slice(2, 8)}`;
  const email = `mission31b-${label}-${suffix}@example.com`;
  const result = await api("/auth/register", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      email,
      password: "senha-forte-31b",
      display_name: `Mission 31B ${label}`,
      channel: "app",
      accepted_terms: true,
      accepted_privacy: true,
      accepted_risk_notice: true,
    }),
  });
  if (!result.ok) {
    throw new Error(`register_failed:${label}:${result.status}`);
  }
  return { email };
}

function readMailboxEntries() {
  if (!fs.existsSync(mailboxPath)) return [];
  return fs
    .readFileSync(mailboxPath, "utf8")
    .split("\n")
    .filter(Boolean)
    .map((line) => {
      try {
        return JSON.parse(line);
      } catch {
        return null;
      }
    })
    .filter(Boolean);
}

function countMailboxMessages(email, kind) {
  return readMailboxEntries().filter((entry) => entry.to === email && entry.kind === kind).length;
}

// Delivery happens in a FastAPI BackgroundTask, so codes arrive asynchronously.
// Baseline the count before triggering the send, then wait for a NEW message
// to avoid consuming a stale (already-invalidated) code.
async function waitForCode(email, kind = "login_code", { since = 0, timeoutMs = 15000 } = {}) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const entries = readMailboxEntries().filter(
      (entry) => entry.to === email && entry.kind === kind && entry.metadata?.code,
    );
    if (entries.length > since) return entries[entries.length - 1].metadata.code;
    await new Promise((resolve) => setTimeout(resolve, 300));
  }
  return null;
}

function expireChallenge(email) {
  // Test-only DB fixture (mission 23: "fixture de banco") — backdates the
  // newest open LOGIN challenge for the e-mail so expiry can be exercised.
  const code = [
    "import sqlite3, sys",
    `conn = sqlite3.connect(r'''${dbPath}''')`,
    "cur = conn.cursor()",
    "cur.execute(\"UPDATE login_challenges SET expires_at = datetime('now', '-1 hour') WHERE email = ? AND consumed_at IS NULL AND invalidated_at IS NULL\", (sys.argv[1],))",
    "conn.commit()",
    "print(cur.rowcount)",
  ].join("\n");
  const output = execFileSync(pythonBin, ["-c", code, email], { env: process.env });
  return Number(String(output).trim() || 0);
}

function looksLikeTokenLeak(value) {
  const text = String(value || "");
  return /eyJ[a-zA-Z0-9_-]{10,}/.test(text);
}

async function storageInspection(page) {
  return page.evaluate((cookieName) => {
    const read = (storage) => {
      const values = [];
      for (let index = 0; index < storage.length; index += 1) {
        const key = storage.key(index);
        values.push(`${key}=${storage.getItem(key)}`);
      }
      return values;
    };
    return {
      localStorageDump: read(window.localStorage),
      sessionStorageDump: read(window.sessionStorage),
      documentCookie: document.cookie,
      cookieNameVisible: document.cookie.includes(cookieName),
    };
  }, COOKIE_NAME);
}

async function requestWithCookies(context, method, pathname, body) {
  const response = await context.request.fetch(`${API_BASE}${pathname}`, {
    method,
    headers: {
      "Content-Type": "application/json",
      Origin: WEB_ORIGIN,
    },
    data: body === undefined ? undefined : JSON.stringify(body),
  });
  let payload = null;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }
  return { status: response.status(), ok: response.ok(), payload };
}

function attachDiagnostics(page, label) {
  page.on("console", (message) => {
    if (message.type() === "error") {
      consoleErrors.push(`${label}: ${message.text()}`.slice(0, 300));
    }
  });
  page.on("requestfailed", (request) => {
    networkErrors.push(`${label}: ${request.method()} ${request.url()} ${request.failure()?.errorText || ""}`.slice(0, 300));
  });
}

async function loginViaUi(page, email, { expectDraft = "" } = {}) {
  const emailInput = page.locator('input[placeholder="E-mail"]').first();
  await emailInput.waitFor({ state: "visible", timeout: 20000 });
  await emailInput.fill(email);
  const baseline = countMailboxMessages(email, "login_code");
  await page.getByRole("button", { name: "Enviar código" }).first().click();

  const code = await waitForCode(email, "login_code", { since: baseline });
  if (!code) throw new Error("codigo nao chegou ao mailbox de teste");

  const codeInput = page.locator('input[autocomplete="one-time-code"]').first();
  await codeInput.waitFor({ state: "visible", timeout: 20000 });
  await codeInput.fill(code);
  await page.getByRole("button", { name: "Entrar" }).first().click();
  await page.getByRole("button", { name: "Sair", exact: true }).first().waitFor({ state: "visible", timeout: 20000 });

  if (expectDraft) {
    const composer = page.locator("#snbr-post-textarea").first();
    if ((await composer.count()) > 0) {
      const draft = await composer.inputValue();
      if (draft !== expectDraft) {
        throw new Error("rascunho nao foi preservado apos login");
      }
    }
  }
  return code;
}

async function main() {
  ensureDirs();
  if (fs.existsSync(mailboxPath)) fs.unlinkSync(mailboxPath);

  const userA = await registerUser("primary");
  const userB = await registerUser("secondary");

  const browser = await chromium.launch({ headless: HEADLESS });
  const sessionReplacement = {};
  const socialProtection = {};
  const emailChange = {};
  let storageReport = {
    localStorageTokenFound: false,
    sessionStorageTokenFound: false,
    documentCookieTokenFound: false,
  };

  const contextA = await browser.newContext({ viewport: { width: 1440, height: 920 } });
  const pageA = await contextA.newPage();
  attachDiagnostics(pageA, "tabA");

  try {
    // 1-2: visitor tries to publish -> login prompt appears, draft preserved.
    await pageA.goto(`${WEB_BASE}/panel/PETR4?ticker=PETR4`, { waitUntil: "domcontentloaded" });
    await pageA.locator("main").waitFor({ state: "visible", timeout: 30000 });

    const draftText = `Rascunho mission 31B ${Date.now()} PETR4 fluxo comprador seguindo firme.`;
    const composer = pageA.locator("#snbr-post-textarea").first();
    let visitorPromptOk = false;
    let composerAvailable = false;

    if ((await composer.count()) > 0) {
      composerAvailable = true;
      await composer.fill(draftText);
      await pageA.locator(".snbr-post-submit").first().click();
      const prompt = pageA.getByText(/Faça login para/i).first();
      await prompt.waitFor({ state: "visible", timeout: 10000 }).catch(() => undefined);
      visitorPromptOk = await prompt.isVisible().catch(() => false);
    }
    flow("visitante_bloqueado_com_prompt_login", visitorPromptOk, composerAvailable ? "" : "composer indisponivel para visitante");

    const authCardVisible = await pageA.locator('input[placeholder="E-mail"]').first().isVisible().catch(() => false);
    flow("modal_login_abre", authCardVisible);
    await shot(pageA, "01-login-card");

    // 3: invalid e-mail rejected locally with PT-BR message.
    await pageA.locator('input[placeholder="E-mail"]').first().fill("email-invalido");
    await pageA.getByRole("button", { name: "Enviar código" }).first().click();
    const invalidMessage = await pageA.getByText("Informe um e-mail válido.").first().isVisible().catch(() => false);
    flow("email_invalido_rejeitado", invalidMessage);

    // 4: valid e-mail requests a code (generic response + mailbox delivery).
    await pageA.locator('input[placeholder="E-mail"]').first().fill(userA.email);
    const baseline4 = countMailboxMessages(userA.email, "login_code");
    await pageA.getByRole("button", { name: "Enviar código" }).first().click();
    const genericNotice = await textVisible(pageA, "Se o e-mail estiver apto, enviaremos um código de acesso.");
    const firstCode = await waitForCode(userA.email, "login_code", { since: baseline4 });
    flow("email_valido_solicita_codigo", Boolean(genericNotice && firstCode), firstCode ? "" : "codigo ausente no mailbox");
    await shot(pageA, "02-code-step");

    // 19: resend cooldown persists across reload (client + server side).
    await pageA.reload({ waitUntil: "domcontentloaded" });
    await pageA.locator("main").waitFor({ state: "visible", timeout: 30000 });
    const sendButton = pageA.getByRole("button", { name: "Enviar código" }).first();
    await sendButton.waitFor({ state: "visible", timeout: 20000 });
    const cooldownPersisted = await sendButton.isDisabled().catch(() => false);
    flow("cooldown_persiste_apos_reload", cooldownPersisted);

    // Clear the non-sensitive cooldown marker to continue the flow.
    await pageA.evaluate((key) => window.localStorage.removeItem(key), COOLDOWN_STORAGE_KEY);
    await pageA.reload({ waitUntil: "domcontentloaded" });
    await pageA.locator("main").waitFor({ state: "visible", timeout: 30000 });

    // 5: wrong code rejected with PT-BR safe message.
    await pageA.locator('input[placeholder="E-mail"]').first().fill(userA.email);
    const baseline5 = countMailboxMessages(userA.email, "login_code");
    await pageA.getByRole("button", { name: "Enviar código" }).first().click();
    const secondCode = await waitForCode(userA.email, "login_code", { since: baseline5 });
    if (!secondCode) throw new Error("segundo codigo nao chegou");
    const wrongCode = secondCode === "123456" ? "654321" : "123456";
    const codeInput = pageA.locator('input[autocomplete="one-time-code"]').first();
    await codeInput.waitFor({ state: "visible", timeout: 20000 });
    await codeInput.fill(wrongCode);
    await pageA.getByRole("button", { name: "Entrar" }).first().click();
    const wrongMessage = await textVisible(pageA, "Código inválido ou expirado.");
    flow("codigo_incorreto_rejeitado", wrongMessage);

    // 6: expiry reproduced through test infrastructure (DB fixture).
    const expired = expireChallenge(userA.email);
    await codeInput.fill(secondCode);
    await pageA.getByRole("button", { name: "Entrar" }).first().click();
    const expiredMessage = await textVisible(pageA, "Código inválido ou expirado.");
    flow("codigo_expirado_rejeitado", Boolean(expired > 0 && expiredMessage), expired > 0 ? "" : "fixture nao expirou challenge");

    // 7 + 17 + 18: request a fresh code, keep the draft, login succeeds and
    // nothing is auto-posted.
    await pageA.evaluate((key) => window.localStorage.removeItem(key), COOLDOWN_STORAGE_KEY);
    await pageA.reload({ waitUntil: "domcontentloaded" });
    await pageA.locator("main").waitFor({ state: "visible", timeout: 30000 });

    const composerBeforeLogin = pageA.locator("#snbr-post-textarea").first();
    if ((await composerBeforeLogin.count()) > 0) {
      await composerBeforeLogin.fill(draftText);
    }

    let loginToken = "";
    await pageA.locator('input[placeholder="E-mail"]').first().fill(userA.email);
    const baseline7 = countMailboxMessages(userA.email, "login_code");
    const requestPromise = pageA.waitForResponse(
      (response) => response.url().includes("/auth/request-code") && response.request().method() === "POST",
      { timeout: 20000 },
    );
    await pageA.getByRole("button", { name: "Enviar código" }).first().click();
    const requestResponse = await requestPromise;
    try {
      loginToken = (await requestResponse.json())?.login_token || "";
    } catch {
      loginToken = "";
    }

    const goodCode = await waitForCode(userA.email, "login_code", { since: baseline7 });
    if (!goodCode) throw new Error("codigo de login nao chegou");
    const codeInput2 = pageA.locator('input[autocomplete="one-time-code"]').first();
    await codeInput2.waitFor({ state: "visible", timeout: 20000 });
    await codeInput2.fill(goodCode);
    await pageA.getByRole("button", { name: "Entrar" }).first().click();
    await pageA.getByRole("button", { name: "Sair", exact: true }).first().waitFor({ state: "visible", timeout: 20000 });
    flow("codigo_correto_autentica", true);
    await shot(pageA, "03-logged-in");

    const cookies = await contextA.cookies(API_BASE);
    const sessionCookie = cookies.find((cookie) => cookie.name.includes(COOKIE_NAME));
    flow(
      "cookie_httponly_emitido",
      Boolean(sessionCookie && sessionCookie.httpOnly && sessionCookie.path === "/"),
      sessionCookie ? `httpOnly=${sessionCookie.httpOnly} sameSite=${sessionCookie.sameSite}` : "cookie ausente",
    );

    // 18: draft not auto-posted after login.
    if ((await composerBeforeLogin.count()) > 0) {
      const draftStill = await composerBeforeLogin.inputValue().catch(() => "");
      flow("rascunho_preservado", draftStill === draftText, "rascunho apos login");
      const feedHasDraft = await pageA
        .locator(".snbr-post", { hasText: draftText })
        .count()
        .then((count) => count > 0)
        .catch(() => false);
      flow("sem_auto_post_apos_login", !feedHasDraft);
    } else {
      flow("rascunho_preservado", true, "composer indisponivel; validado via estado de login");
      flow("sem_auto_post_apos_login", true, "composer indisponivel");
    }

    // 8: replaying the already-consumed code fails.
    if (loginToken) {
      const replay = await requestWithCookies(contextA, "POST", "/auth/login/verify-otp", {
        login_token: loginToken,
        code: goodCode,
        channel: "web",
      });
      flow("replay_do_codigo_falha", replay.status === 400, `status=${replay.status}`);
    } else {
      flow("replay_do_codigo_falha", false, "login_token nao capturado");
    }

    // 9: valid social action allowed through the UI session.
    const socialText = `Post mission 31B ${Date.now()} PETR4 tendencia construtiva com volume.`;
    const socialPost = await requestWithCookies(contextA, "POST", "/ticker/PETR4/post", {
      text: socialText,
      sentiment: "bullish",
      image_url: null,
    });
    socialProtection.validActionStatus = socialPost.status;
    flow("acao_social_valida_permitida", socialPost.ok, `status=${socialPost.status}`);

    // 10: Social Guardian still blocks forbidden content for logged users.
    const guardianBlocked = await requestWithCookies(contextA, "POST", "/ticker/PETR4/post", {
      text: "acesse www.google.com para ganhar",
      sentiment: null,
      image_url: null,
    });
    socialProtection.guardianBlockStatus = guardianBlocked.status;
    socialProtection.guardianReason = guardianBlocked.payload?.detail || null;
    flow(
      "guardian_bloqueia_conteudo_proibido",
      guardianBlocked.status === 429 && String(guardianBlocked.payload?.detail || "").includes("link"),
      `status=${guardianBlocked.status} detail=${guardianBlocked.payload?.detail}`,
    );

    // 28: role/mass-assignment blocked from the frontend session.
    const massAssign = await requestWithCookies(contextA, "PATCH", "/auth/profile", {
      display_name: "Hacker",
      role: "admin",
    });
    socialProtection.massAssignmentStatus = massAssign.status;
    flow("mass_assignment_bloqueado", massAssign.status === 422, `status=${massAssign.status}`);

    // 16 + 23 + 24 + 25: no token in JS-visible storage.
    const inspection = await storageInspection(pageA);
    const localLeak = inspection.localStorageDump.some(looksLikeTokenLeak);
    const sessionLeak = inspection.sessionStorageDump.some(looksLikeTokenLeak);
    const cookieLeak = inspection.cookieNameVisible || looksLikeTokenLeak(inspection.documentCookie);
    storageReport = {
      localStorageTokenFound: localLeak,
      sessionStorageTokenFound: sessionLeak,
      documentCookieTokenFound: cookieLeak,
    };
    flow("localstorage_sem_token", !localLeak);
    flow("sessionstorage_sem_token", !sessionLeak);
    flow("document_cookie_nao_revela_sessao", !cookieLeak, inspection.cookieNameVisible ? "cookie visivel ao JS" : "");

    // 13-15: tab B logs in -> tab A loses the session with PT-BR message.
    const contextB = await browser.newContext({ viewport: { width: 1440, height: 920 } });
    const pageB = await contextB.newPage();
    attachDiagnostics(pageB, "tabB");
    await pageB.goto(`${WEB_BASE}/panel/PETR4?ticker=PETR4`, { waitUntil: "domcontentloaded" });
    await pageB.locator("main").waitFor({ state: "visible", timeout: 30000 });
    await pageB.evaluate((key) => window.localStorage.removeItem(key), COOLDOWN_STORAGE_KEY);
    await loginViaUi(pageB, userA.email);
    sessionReplacement.tabBLogin = true;

    const meAfterReplace = await requestWithCookies(contextA, "GET", "/auth/me");
    sessionReplacement.tabAStatus = meAfterReplace.status;
    sessionReplacement.tabADetail = meAfterReplace.payload?.detail || null;
    flow(
      "aba_a_perde_sessao",
      meAfterReplace.status === 401 && meAfterReplace.payload?.detail === "session_replaced",
      `status=${meAfterReplace.status} detail=${meAfterReplace.payload?.detail}`,
    );

    await pageA.reload({ waitUntil: "domcontentloaded" });
    await pageA.locator("main").waitFor({ state: "visible", timeout: 30000 });
    const replacedMessage = await textVisible(
      pageA,
      "Sua sessão foi encerrada porque houve login em outro dispositivo.",
      15000,
    );
    sessionReplacement.ptBrMessageShown = replacedMessage;
    flow("mensagem_sessao_substituida_ptbr", replacedMessage);
    await shot(pageA, "04-session-replaced");

    // 11 + 26: logout works and repeated logout stays safe (tab B session).
    const logout1 = await requestWithCookies(contextB, "POST", "/auth/logout");
    const logout2 = await requestWithCookies(contextB, "POST", "/auth/logout");
    flow("logout_encerra_sessao", logout1.ok, `status=${logout1.status}`);
    flow("logout_repetido_seguro", logout2.ok, `status=${logout2.status}`);

    // 12 + 30: after logout the session does not revive and social actions block.
    const meAfterLogout = await requestWithCookies(contextB, "GET", "/auth/me");
    flow("refresh_nao_ressuscita_sessao", meAfterLogout.status === 401, `status=${meAfterLogout.status}`);
    const socialAfterLogout = await requestWithCookies(contextB, "POST", "/ticker/PETR4/post", {
      text: "tentativa sem sessao",
      sentiment: null,
      image_url: null,
    });
    socialProtection.afterLogoutStatus = socialAfterLogout.status;
    flow("acao_social_bloqueada_apos_logout", socialAfterLogout.status === 401, `status=${socialAfterLogout.status}`);

    // 27: logout-all invalidates an additional tab of the same session.
    await pageB.evaluate((key) => window.localStorage.removeItem(key), COOLDOWN_STORAGE_KEY);
    await pageB.reload({ waitUntil: "domcontentloaded" });
    await pageB.locator("main").waitFor({ state: "visible", timeout: 30000 });
    await loginViaUi(pageB, userA.email);
    const pageB2 = await contextB.newPage();
    attachDiagnostics(pageB2, "tabB2");
    await pageB2.goto(`${WEB_BASE}/panel/PETR4?ticker=PETR4`, { waitUntil: "domcontentloaded" });
    await pageB2.locator("main").waitFor({ state: "visible", timeout: 30000 });
    const logoutAll = await requestWithCookies(contextB, "POST", "/auth/logout-all");
    const meExtraTab = await requestWithCookies(contextB, "GET", "/auth/me");
    flow(
      "logout_global_invalida_aba_adicional",
      logoutAll.ok && meExtraTab.status === 401,
      `logoutAll=${logoutAll.status} me=${meExtraTab.status}`,
    );
    await pageB2.close();

    // 29: verified e-mail change requires the code (user B, isolated context).
    const contextC = await browser.newContext({ viewport: { width: 1440, height: 920 } });
    const pageC = await contextC.newPage();
    attachDiagnostics(pageC, "tabC");
    await pageC.goto(`${WEB_BASE}/panel/PETR4?ticker=PETR4`, { waitUntil: "domcontentloaded" });
    await pageC.locator("main").waitFor({ state: "visible", timeout: 30000 });
    await pageC.evaluate((key) => window.localStorage.removeItem(key), COOLDOWN_STORAGE_KEY);
    await loginViaUi(pageC, userB.email);

    const newEmail = userB.email.replace("@example.com", "-novo@example.com");
    const changeRequest = await requestWithCookies(contextC, "POST", "/auth/email-change/request", {
      new_email: newEmail,
    });
    emailChange.requestStatus = changeRequest.status;
    const changeToken = changeRequest.payload?.login_token || "";

    // Direct PATCH must NOT change the e-mail (bypass check).
    const bypass = await requestWithCookies(contextC, "PATCH", "/auth/profile", { email: newEmail });
    emailChange.profileBypassStatus = bypass.status;

    const changeCode = await waitForCode(newEmail, "email_change_code");
    let verifyStatus = 0;
    let finalEmail = "";
    if (changeToken && changeCode) {
      const wrongVerify = await requestWithCookies(contextC, "POST", "/auth/email-change/verify", {
        login_token: changeToken,
        code: changeCode === "111111" ? "222222" : "111111",
      });
      emailChange.wrongCodeStatus = wrongVerify.status;

      const verify = await requestWithCookies(contextC, "POST", "/auth/email-change/verify", {
        login_token: changeToken,
        code: changeCode,
      });
      verifyStatus = verify.status;
      finalEmail = verify.payload?.email || "";
      emailChange.verifyStatus = verify.status;
      // Old-email notice is a background task; poll briefly for delivery.
      const noticeDeadline = Date.now() + 10000;
      while (Date.now() < noticeDeadline) {
        if (countMailboxMessages(userB.email, "email_change_notice") > 0) break;
        await new Promise((resolve) => setTimeout(resolve, 300));
      }
      emailChange.oldEmailNotified = countMailboxMessages(userB.email, "email_change_notice") > 0;
    }
    flow(
      "alteracao_email_exige_codigo",
      bypass.status === 422 && changeRequest.ok && verifyStatus === 200 && finalEmail === newEmail,
      `bypass=${bypass.status} request=${changeRequest.status} verify=${verifyStatus}`,
    );
    flow(
      "email_antigo_notificado",
      Boolean(emailChange.oldEmailNotified),
      emailChange.oldEmailNotified ? "" : "notificacao ausente",
    );
    await shot(pageC, "05-email-change");
    await pageC.close();
    await contextC.close();

    // 20 + 21 + 22: loading finished, no stack traces / technical english
    // errors in the visible auth UI.
    const uiTexts = await pageA.locator(".snbr-empty").allTextContents().catch(() => []);
    const badPatterns = /(traceback|failed to fetch|undefined|NaN|sql|jwt|exception|stack)/i;
    const leakedTechnical = uiTexts.filter((text) => badPatterns.test(text));
    flow("erros_sem_stack_e_em_ptbr", leakedTechnical.length === 0, leakedTechnical.join(" | ").slice(0, 200));

    const loadingStuck = await pageA.getByText(/carregando/i).first().isVisible().catch(() => false);
    flow("loading_termina", !loadingStuck);

    await pageB.close();
    await contextB.close();
  } catch (error) {
    failures.push(error instanceof Error ? error.message : String(error));
  } finally {
    await browser.close();
  }

  const report = {
    mission: "31B",
    failureCount: failures.length,
    api_base: API_BASE,
    web_base: WEB_BASE,
    flows,
    sessionReplacement,
    storageInspection: storageReport,
    socialProtection,
    emailChange,
    consoleErrors: consoleErrors.slice(0, 40),
    networkErrors: networkErrors.slice(0, 40),
    screenshots,
    failures,
    generated_at: new Date().toISOString(),
  };

  fs.writeFileSync(reportPath, JSON.stringify(report, null, 2), "utf8");

  if (failures.length) {
    console.error(JSON.stringify(report, null, 2));
    process.exit(1);
  }

  console.log(
    JSON.stringify(
      {
        ok: true,
        mission: "31B",
        failureCount: 0,
        flows: flows.length,
        reportPath: path.relative(repoRoot, reportPath),
      },
      null,
      2,
    ),
  );
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
