import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(scriptDir, "..", "..", "..");
const reportPath = process.env.MISSION31A_REPORT_PATH
  ? path.resolve(repoRoot, process.env.MISSION31A_REPORT_PATH)
  : path.join(repoRoot, "runtime", "mission_31a_social_guardian_report.json");
const screenshotDir = path.join(repoRoot, "output", "playwright", "mission31a");
const moderationStorePath = process.env.MISSION31A_MODERATION_STORE_PATH
  ? path.resolve(repoRoot, process.env.MISSION31A_MODERATION_STORE_PATH)
  : path.join(repoRoot, "data", "moderation_state.json");

const API_BASE = (process.env.MISSION31A_API_BASE || "http://127.0.0.1:8000").replace(/\/$/, "");
const WEB_BASE = (process.env.MISSION31A_WEB_BASE || "http://127.0.0.1:3000").replace(/\/$/, "");
const HEADLESS = process.env.MISSION31A_HEADLESS !== "false";
const SESSION_COOKIE_NAME = process.env.MISSION31A_SESSION_COOKIE_NAME || process.env.SESSION_COOKIE_NAME || "snb_session";

function ensureDirs() {
  fs.mkdirSync(path.dirname(reportPath), { recursive: true });
  fs.mkdirSync(screenshotDir, { recursive: true });
}

function sanitize(value) {
  return String(value || "").replace(/[^a-z0-9_-]+/gi, "_").toLowerCase();
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

function authHeaders(token) {
  return {
    Authorization: `Bearer ${token}`,
    "Content-Type": "application/json",
  };
}

async function registerUser(label) {
  const suffix = `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  const email = `mission31a-${label}-${suffix}@example.com`;
  const result = await api("/auth/register", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      email,
      password: "123456",
      display_name: `Mission 31A ${label}`,
      channel: "web",
      accepted_terms: true,
      accepted_privacy: true,
      accepted_risk_notice: true,
    }),
  });
  if (!result.ok || !result.payload?.access_token) {
    throw new Error(`register_failed:${label}:${result.status}:${JSON.stringify(result.payload)}`);
  }
  return { email, token: result.payload.access_token };
}

async function createPost(token, text, ticker = "PETR4") {
  return api(`/ticker/${encodeURIComponent(ticker)}/post`, {
    method: "POST",
    headers: authHeaders(token),
    body: JSON.stringify({ text, sentiment: "bullish", image_url: null }),
  });
}

async function createComment(token, postId, text) {
  return api(`/post/${postId}/comment`, {
    method: "POST",
    headers: authHeaders(token),
    body: JSON.stringify({ text, image_url: null }),
  });
}

async function createRepost(token, postId, quoteText) {
  return api(`/post/${postId}/repost`, {
    method: "POST",
    headers: authHeaders(token),
    body: JSON.stringify({ quote_text: quoteText }),
  });
}

async function createChatMessage(token, text) {
  return api("/chat/PETR4/message", {
    method: "POST",
    headers: authHeaders(token),
    body: JSON.stringify({ text, image_url: null }),
  });
}

async function getFeed(token) {
  return api("/ticker/PETR4/feed?limit=100", {
    method: "GET",
    headers: { Authorization: `Bearer ${token}` },
  });
}

function readGuardianState() {
  if (!fs.existsSync(moderationStorePath)) return {};
  return JSON.parse(fs.readFileSync(moderationStorePath, "utf8"));
}

function assertBlocked(result, expectedReason, label, failures) {
  const detail = String(result.payload?.detail || result.payload?.reason || "");
  if (result.ok || result.status < 400) {
    failures.push(`${label}: conteudo proibido foi aceito`);
    return;
  }
  if (detail !== expectedReason) {
    failures.push(`${label}: motivo esperado ${expectedReason}, recebido ${detail || result.status}`);
  }
}

async function runApiAudit(authorToken, reporterToken) {
  const failures = [];
  const normalText = `Post normal Mission 31A ${Date.now()} PETR4 suporte, volume e fluxo alinhados.`;
  const normalPost = await createPost(authorToken, normalText);
  if (!normalPost.ok || !normalPost.payload?.id) {
    failures.push(`post normal falhou: ${normalPost.status}:${JSON.stringify(normalPost.payload)}`);
  }
  const postId = normalPost.payload?.id;

  const blockedCases = [
    ["post_link", () => createPost(authorToken, "www.google.com"), "link_detected"],
    ["post_https", () => createPost(authorToken, "https://google.com"), "link_detected"],
    ["post_domain_br", () => createPost(authorToken, "stocknewsbr.com.br"), "link_detected"],
    ["post_ai_domain", () => createPost(authorToken, "meusite.ai"), "link_detected"],
    ["post_email", () => createPost(authorToken, "abc@gmail.com"), "email_detected"],
    ["post_phone", () => createPost(authorToken, "11 99999-9999"), "phone_detected"],
    ["post_bet", () => createPost(authorToken, "bet365 e blaze"), "betting_detected"],
    ["gif_caption_link", () => createPost(authorToken, "GIF caption www.google.com"), "link_detected"],
    ["poll_comment_bet", () => createPost(authorToken, "[POLL PETR4] aposta no tigrinho"), "betting_detected"],
  ];

  for (const [label, runner, expectedReason] of blockedCases) {
    const result = await runner();
    assertBlocked(result, expectedReason, label, failures);
  }

  if (postId) {
    assertBlocked(await createComment(authorToken, postId, "teste@yahoo.com"), "email_detected", "comment_email", failures);
    assertBlocked(await createRepost(authorToken, postId, "aposta na betano"), "betting_detected", "repost_bet", failures);
    assertBlocked(await createChatMessage(authorToken, "chama no +55"), "phone_detected", "chat_phone", failures);
  }

  const feedAfterBlocks = await getFeed(authorToken);
  const feedTexts = (feedAfterBlocks.payload?.posts || []).map((post) => String(post.text || ""));
  for (const blockedText of ["www.google.com", "abc@gmail.com", "11 99999-9999", "bet365", "tigrinho"]) {
    if (feedTexts.some((text) => text.includes(blockedText))) {
      failures.push(`feed salvou texto proibido: ${blockedText}`);
    }
  }

  if (postId) {
    const report = await api("/report", {
      method: "POST",
      headers: authHeaders(reporterToken),
      body: JSON.stringify({ post_id: postId, reason: "spam", note: "playwright-api" }),
    });
    if (!report.ok || report.payload?.status !== "reported") {
      failures.push(`denuncia API falhou: ${report.status}:${JSON.stringify(report.payload)}`);
    }
  }

  return {
    normal_text: normalText,
    post_id: postId,
    feed_count: feedAfterBlocks.payload?.count ?? 0,
    failures,
  };
}

async function runBrowserAudit(reporter) {
  const browser = await chromium.launch({ headless: HEADLESS });
  const context = await browser.newContext({ viewport: { width: 1440, height: 920 } });
  await context.addCookies([
    {
      name: SESSION_COOKIE_NAME,
      value: reporter.token,
      url: new URL(API_BASE).origin,
      httpOnly: true,
      secure: API_BASE.startsWith("https://"),
      sameSite: "Lax",
    },
  ]);
  const page = await context.newPage();
  const browserPostText = `Post normal Mission 31A navegador ${Date.now()} PETR4 suporte, volume, fluxo e risco controlado.`;
  const result = {
    created_post_text: browserPostText,
    report_button_count: 0,
    reason_button_count: 0,
    dialog_visible: false,
    screenshot: "",
    failures: [],
  };

  try {
    await page.goto(`${WEB_BASE}/panel/PETR4?ticker=PETR4`, {
      waitUntil: "domcontentloaded",
    });
    await page.locator("main").waitFor({ state: "visible", timeout: 20000 });
    await page.getByText(reporter.email).first().waitFor({ state: "visible", timeout: 20000 });
    const composer = page.locator("#snbr-post-textarea").first();
    await composer.waitFor({ state: "visible", timeout: 20000 });
    await composer.fill(browserPostText);
    const postResponsePromise = page.waitForResponse((response) =>
      response.url().includes("/ticker/PETR4/post") && response.request().method() === "POST",
      { timeout: 20000 },
    );
    await page.locator(".snbr-post-submit").first().click();
    const postResponse = await postResponsePromise;
    if (!postResponse.ok()) {
      result.failures.push(`post normal no navegador falhou: ${postResponse.status()}`);
    }
    await page.locator(".snbr-post", { hasText: browserPostText }).first().waitFor({ state: "visible", timeout: 20000 });
    const post = page.locator(".snbr-post", { hasText: browserPostText }).first();
    const reportButton = post.locator("[data-social-report-button='true']").first();
    result.report_button_count = await post.locator("[data-social-report-button='true']").count();
    if (result.report_button_count < 1) {
      result.failures.push("botao Denunciar nao apareceu no post");
    } else {
      await reportButton.click();
      const dialog = page.locator("[data-social-report-dialog='true']").first();
      await dialog.waitFor({ state: "visible", timeout: 8000 });
      result.dialog_visible = await dialog.isVisible();
      result.reason_button_count = await dialog.locator("[data-report-reason]").count();
      if (result.reason_button_count < 6) {
        result.failures.push(`motivos insuficientes no dialog: ${result.reason_button_count}`);
      }
      await dialog.locator("[data-report-reason='spam']").click();
      result.screenshot = path.join(screenshotDir, `${sanitize("report-dialog")}.jpg`);
      await dialog.screenshot({ path: result.screenshot, type: "jpeg", quality: 82 });
      await dialog.locator("[data-social-report-submit='true']").click();
      await dialog.waitFor({ state: "hidden", timeout: 10000 }).catch(() => undefined);
    }
  } catch (error) {
    result.failures.push(error instanceof Error ? error.message : String(error));
  } finally {
    await browser.close();
  }

  return result;
}

async function main() {
  ensureDirs();
  const author = await registerUser("author");
  const reporter = await registerUser("reporter");
  const apiAudit = await runApiAudit(author.token, reporter.token);
  const browserAudit = await runBrowserAudit(reporter);
  const guardianState = readGuardianState();
  const auditActions = (guardianState.guardian_audit || []).map((item) => item.action);
  const scores = guardianState.guardian_scores || {};
  const failures = [...apiAudit.failures, ...browserAudit.failures];

  for (const action of ["post_created", "content_blocked", "post_reported", "user_reported"]) {
    if (!auditActions.includes(action)) failures.push(`auditoria sem evento obrigatorio: ${action}`);
  }
  if (!Object.keys(scores).length) failures.push("Social Guardian Score nao foi registrado");

  const report = {
    ok: failures.length === 0,
    mission: "31A",
    api_base: API_BASE,
    web_base: WEB_BASE,
    moderation_store: moderationStorePath,
    api_audit: apiAudit,
    browser_audit: browserAudit,
    audit_actions: auditActions.slice(-40),
    score_count: Object.keys(scores).length,
    failures,
    generated_at: new Date().toISOString(),
  };

  fs.writeFileSync(reportPath, JSON.stringify(report, null, 2), "utf8");
  if (!report.ok) {
    console.error(JSON.stringify(report, null, 2));
    process.exit(1);
  }
  console.log(JSON.stringify({
    ok: true,
    mission: "31A",
    reportPath,
    screenshot: browserAudit.screenshot,
    audit_events: auditActions.length,
    score_count: Object.keys(scores).length,
  }, null, 2));
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
