import fs from "node:fs";
import path from "node:path";
import { chromium } from "playwright";

const baseUrl = process.env.SNBR_WEB_URL || "http://127.0.0.1:3000";
const repoRoot = path.resolve(process.cwd(), "..", "..");
const runtimeDir = path.join(repoRoot, "runtime", "etapa7");
const tickers = ["F", "PETR4", "BTCUSD", "META34"];
const aiTabs = [
  { id: "heat-map", name: /IA Mapa de Calor|IA Mapa|AI Heat Map/i },
  { id: "radar", name: /IA Radar|AI Radar/i },
  { id: "breakout-probability", name: /IA Probabilidade de Breakout|IA Breakout|AI Breakout/i },
  { id: "volatility-squeeze", name: /IA Compress[aã]o|IA Squeeze|AI Volatility Squeeze|AI Squeeze/i },
  { id: "institutional-flow", name: /IA Fluxo Institucional|IA Fluxo|AI Institutional Flow|AI Flow/i },
  { id: "smart-money", name: /IA Dinheiro Inteligente|IA Smart|AI Smart/i },
  { id: "accumulation", name: /IA Acumula[cç][aã]o|AI Accumulation/i },
  { id: "liquidity-sweep", name: /IA Varredura de Liquidez|IA Varredura|AI Liquidity Sweep|AI Sweep/i },
  { id: "liquidity-map", name: /IA Liquidity Map|AI Liquidity Map/i },
  { id: "market-regime", name: /IA Regime de Mercado|IA Regime|AI Market Regime|AI Regime/i },
  { id: "master-score", name: /IA Score Mestre|Score Mestre|AI Master Score|Master Score/i },
];

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

async function pageText(page) {
  return (await page.locator("body").innerText()).replace(/\s+/g, " ").trim();
}

async function waitForPanel(page) {
  await page.waitForLoadState("domcontentloaded");
  await page.locator("main").waitFor({ timeout: 30_000 });
  await page.waitForTimeout(700);
}

fs.mkdirSync(runtimeDir, { recursive: true });

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1366, height: 768 } });
const consoleErrors = [];
page.on("console", (message) => {
  if (message.type() === "error") consoleErrors.push(message.text());
});

const result = {
  baseUrl,
  tickers: [],
  aiTabs: [],
  screenshots: [],
  consoleErrors,
};

try {
  await page.goto(`${baseUrl}/panel/F`, { waitUntil: "domcontentloaded", timeout: 45_000 });
  await waitForPanel(page);

  const localeSwitch = page.locator(".snbr-locale-switch");
  await localeSwitch.getByRole("button", { name: /^BR$/i }).click();
  let text = await pageText(page);
  assert(text.includes("IA Grafico/ Rede Social") || text.includes("IA Gráfico/ Rede Social"), "top tab BR deve mostrar IA Grafico/ Rede Social");
  assert(text.includes("WIN") && text.includes("WDO"), "lista B3 deve conter futuros WIN/WDO");
  assert(text.includes("NQ") && text.includes("MES") && text.includes("MYM"), "lista USA deve conter futuros CME principais");

  const lightShot = path.join(runtimeDir, "panel-F-light.png");
  await page.screenshot({ path: lightShot, fullPage: true });
  result.screenshots.push(lightShot);

  await page.locator(".snbr-theme-toggle").click();
  await page.waitForTimeout(300);
  const darkShot = path.join(runtimeDir, "panel-F-dark.png");
  await page.screenshot({ path: darkShot, fullPage: true });
  result.screenshots.push(darkShot);
  await page.locator(".snbr-theme-toggle").click();

  await localeSwitch.getByRole("button", { name: /^USA$/i }).click();
  text = await pageText(page);
  assert(text.includes("AI Chart / Social"), "USA deve traduzir top tab IA Grafico");
  assert(text.includes("International account: USA subscription"), "USA deve mostrar aviso de assinatura internacional");
  assert(text.includes("$49/month") && text.includes("$500 upfront"), "USA deve expor precos em USD");
  assert(text.includes("Asset Search") && text.includes("My Active List"), "USA deve traduzir rail e lista ativa");

  const forbiddenUsShellTerms = [
    "Painel do ativo",
    "ativo",
    "ativos",
    "Preço",
    "sem preço",
    "Leituras da IA",
    "Score IA",
    "Leitura principal",
    "Invalidação",
    "Métricas da lente",
    "Liberar Tela",
    "Sobre a empresa",
    "Descrição do produto",
    "Educação financeira",
    "Aviso legal",
    "Termos de uso",
    "Política de privacidade",
    "Contato / empresa",
    "Abrir",
    "Excluir",
    "Para trader:",
    "Ajuda",
    "Gráfico",
    "tendência semanal",
    "tendência",
    "Sem discussões",
    "LEITURA ATUAL",
    "DIRECAO OPERACIONAL",
    "CONFIRMACAO NECESSARIA",
    "INVALIDACAO",
    "RISCO",
    "buydor",
    "buydora",
    "posicao",
    "baixo",
    "médio",
    "medio",
    "alto:",
    "filtros principais",
    "Observar;",
    "sem ordem operacional",
    "Virada de",
    "confirmacao",
    "Ignorar se",
    "antes de virar",
  ];
  for (const term of forbiddenUsShellTerms) {
    assert(!text.includes(term), `USA nao deve mostrar texto PT no shell: ${term}`);
  }

  await page.getByRole("tab", { name: /AI Heat Map/i }).click();
  await page.waitForTimeout(700);
  text = await pageText(page);
  assert(text.includes("Asset Panel") && text.includes("AI Reads"), "USA deve traduzir painel de IA");
  assert(!text.includes("Painel do ativo") && !text.includes("Leituras da IA"), "USA nao deve manter labels PT na aba IA");

  await page.getByRole("tab", { name: /Help/i }).click();
  await page.waitForTimeout(700);
  text = await pageText(page);
  assert(text.includes("Trader Help") && text.includes("About the company"), "USA deve traduzir Ajuda institucional");
  assert(!text.includes("Sobre a empresa") && !text.includes("Descrição do produto"), "USA nao deve manter Ajuda institucional em PT");

  await page.getByRole("tab", { name: /AI Chart \/ Social/i }).click();
  await page.waitForTimeout(500);
  const usaShot = path.join(runtimeDir, "panel-F-usa.png");
  await page.screenshot({ path: usaShot, fullPage: true });
  result.screenshots.push(usaShot);

  await page.goto(`${baseUrl}/panel/PETR4`, { waitUntil: "domcontentloaded", timeout: 45_000 });
  await waitForPanel(page);
  await page.waitForTimeout(700);
  text = await pageText(page);
  assert(text.includes("AI Chart / Social") && text.includes("Asset Search") && text.includes("no price"), "PETR4 em USA deve permanecer em ingles");
  for (const term of forbiddenUsShellTerms) {
    assert(!text.includes(term), `PETR4 USA nao deve mostrar texto PT no shell/news/poll/social: ${term}`);
  }

  await localeSwitch.getByRole("button", { name: /^BR$/i }).click();

  for (const ticker of tickers) {
    await page.goto(`${baseUrl}/panel/${encodeURIComponent(ticker)}`, { waitUntil: "domcontentloaded", timeout: 45_000 });
    await waitForPanel(page);
    text = await pageText(page);
    assert(text.includes(ticker), `painel deve carregar ticker ${ticker}`);
    result.tickers.push({ ticker, ok: true });
  }

  await page.goto(`${baseUrl}/panel/F`, { waitUntil: "domcontentloaded", timeout: 45_000 });
  await waitForPanel(page);
  const petrButton = page.getByRole("button", { name: /PETR4/ }).first();
  await petrButton.click();
  await page.waitForTimeout(900);
  text = await pageText(page);
  assert(text.includes("PETR4"), "troca de ticker via UI deve carregar PETR4");

  const tabTexts = new Map();
  for (const tab of aiTabs) {
    await page.getByRole("tab", { name: tab.name }).click();
    await page.waitForTimeout(900);
    const panel = page.locator(`#panel-${tab.id}`);
    const panelText = await panel.innerText({ timeout: 10_000 });
    const normalized = panelText.replace(/\s+/g, " ").trim();
    assert(/Encontrado:|Found:/i.test(normalized), `${tab.id} precisa exibir horario real`);
    assert(/Score/i.test(normalized), `${tab.id} precisa exibir Score`);
    assert(/Trigger/i.test(normalized), `${tab.id} precisa exibir Trigger`);
    assert(/Invalid|Invalida/i.test(normalized), `${tab.id} precisa exibir invalidacao`);
    tabTexts.set(tab.id, normalized.slice(0, 1200));
    result.aiTabs.push({ id: tab.id, ok: true });
  }

  const uniqueTabBodies = new Set(tabTexts.values());
  assert(uniqueTabBodies.size >= Math.max(6, aiTabs.length - 2), "abas IA parecem clonadas demais no smoke");

  const jsonPath = path.join(runtimeDir, "smoke-etapa7-result.json");
  fs.writeFileSync(jsonPath, JSON.stringify(result, null, 2), "utf-8");
  console.log(JSON.stringify({ ok: true, result: jsonPath, screenshots: result.screenshots }, null, 2));
} finally {
  await browser.close();
}
