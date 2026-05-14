import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const repoRoot = path.resolve(root, "..", "..");
const requireDevice = process.env.REQUIRE_MOBILE_DEVICE === "1";

const checks = [];

function addCheck(name, ok, detail = "") {
  checks.push({ name, ok: Boolean(ok), detail });
}

function read(relPath) {
  return readFileSync(path.join(root, relPath), "utf8");
}

function json(relPath) {
  return JSON.parse(read(relPath));
}

function run(command, args, cwd = root) {
  const useCmdShim = process.platform === "win32" && command === "npx";
  const executable = useCmdShim ? process.env.ComSpec || "cmd.exe" : command;
  const commandArgs = useCmdShim ? ["/d", "/s", "/c", ["npx", ...args].join(" ")] : args;
  const result = spawnSync(executable, commandArgs, {
    cwd,
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
  });
  return {
    ok: result.status === 0,
    status: result.status,
    stdout: result.stdout || "",
    stderr: result.stderr || result.error?.message || "",
  };
}

function candidateAndroidSdkPaths() {
  const candidates = [];
  for (const key of ["ANDROID_HOME", "ANDROID_SDK_ROOT"]) {
    if (process.env[key]) {
      candidates.push(process.env[key]);
    }
  }
  if (process.env.LOCALAPPDATA) {
    candidates.push(path.join(process.env.LOCALAPPDATA, "Android", "Sdk"));
  }
  return [...new Set(candidates)];
}

function findAdb() {
  for (const sdkPath of candidateAndroidSdkPaths()) {
    const candidate = path.join(sdkPath, "platform-tools", process.platform === "win32" ? "adb.exe" : "adb");
    if (existsSync(candidate)) {
      return candidate;
    }
  }
  return "adb";
}

const requiredFiles = [
  "app/index.tsx",
  "app/(tabs)/index.tsx",
  "app/(tabs)/profile.tsx",
  "app/ticker/[symbol].tsx",
  "components/mobile-price-chart.tsx",
  "lib/api.ts",
  "lib/session.tsx",
  "eas.json",
];

for (const relPath of requiredFiles) {
  addCheck(`file:${relPath}`, existsSync(path.join(root, relPath)));
}

const appJson = json("app.json");
const easJson = json("eas.json");
const tickerScreen = read("app/ticker/[symbol].tsx");
const chartComponent = read("components/mobile-price-chart.tsx");
const api = read("lib/api.ts");
const loginScreen = read("app/index.tsx");
const profileScreen = read("app/(tabs)/profile.tsx");

addCheck("android package", appJson.expo?.android?.package === "com.stocknewsbr.mobile", appJson.expo?.android?.package);
addCheck("android versionCode", Number.isInteger(appJson.expo?.android?.versionCode) && appJson.expo.android.versionCode >= 1);
addCheck("google play app bundle profile", easJson.build?.production?.android?.buildType === "app-bundle");
addCheck("google play submit internal track", easJson.submit?.production?.android?.track === "internal");
addCheck("billing products configured", Boolean(appJson.expo?.extra?.billingProducts?.brMonthly && appJson.expo?.extra?.billingProducts?.usaMonthly));

addCheck("ticker route opens asset", tickerScreen.includes("Painel mobile do ativo") && tickerScreen.includes("router.back()"));
addCheck("ticker ranges", ["1D", "1W", "1M", "3M", "1Y"].every((range) => tickerScreen.includes(`"${range}"`)));
addCheck("ticker chart uses active range", tickerScreen.includes("getChart(token, ticker, activeRange)"));
addCheck("mobile chart renders candles", chartComponent.includes("mobile-price-chart") && chartComponent.includes("candleSlot") && chartComponent.includes("Grafico indisponivel"));
addCheck("chart marker risk contract", chartComponent.includes("Trigger:") && chartComponent.includes("Invalidacao:") && chartComponent.includes("Risco:"));
addCheck("billing pricing api", api.includes("getBillingPricing") && api.includes("/billing/pricing"));
addCheck("login plan BR USA", loginScreen.includes("Trial BR") && loginScreen.includes("USA mensal") && loginScreen.includes("refund"));
addCheck("profile plan and google play", profileScreen.includes("Google Play") && profileScreen.includes("BR mensal") && profileScreen.includes("USA anual"));

const expoConfig = run("npx", ["expo", "config", "--type", "public"]);
addCheck("expo config", expoConfig.ok, expoConfig.ok ? "ok" : `${expoConfig.stderr}\n${expoConfig.stdout}`.trim());

const adb = findAdb();
const adbDevices = run(adb, ["devices"]);
const deviceLines = adbDevices.stdout
  .split(/\r?\n/)
  .map((line) => line.trim())
  .filter((line) => /\tdevice$/.test(line));
addCheck(
  "android emulator/device visible",
  deviceLines.length > 0 || !requireDevice,
  deviceLines.length ? deviceLines.join(", ") : "no device connected",
);

if (deviceLines.length > 0) {
  const boot = run(adb, ["shell", "getprop", "sys.boot_completed"]);
  addCheck("android emulator booted", boot.stdout.trim() === "1", boot.stdout.trim() || boot.stderr.trim());
}

const failed = checks.filter((check) => !check.ok);
const report = {
  status: failed.length ? "failed" : "ok",
  root,
  repoRoot,
  requireDevice,
  checks,
};

console.log(JSON.stringify(report, null, 2));

if (failed.length) {
  process.exit(1);
}
