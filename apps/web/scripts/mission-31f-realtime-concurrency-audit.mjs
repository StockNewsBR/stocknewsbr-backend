import { spawnSync } from "node:child_process";
import { existsSync, mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(scriptDir, "../../..");
const runtimeDir = path.join(repoRoot, "runtime");
const reportPath = path.join(runtimeDir, "mission_31f_realtime_concurrency_report.json");

const pythonCandidates =
  process.platform === "win32"
    ? [
        path.join(repoRoot, ".venv", "Scripts", "python.exe"),
        path.join(repoRoot, "venv", "Scripts", "python.exe"),
        "py",
        "python",
      ]
    : [
        path.join(repoRoot, ".venv", "bin", "python"),
        path.join(repoRoot, "venv", "bin", "python"),
        "python3",
        "python",
      ];

function resolvePython() {
  for (const candidate of pythonCandidates) {
    if (candidate.includes(path.sep) && !existsSync(candidate)) continue;
    return candidate;
  }
  return "python";
}

const python = resolvePython();
const args =
  path.basename(python).toLowerCase() === "py"
    ? ["-3.11", "-m", "unittest", "tests.test_mission_31f_cache_concurrency_realtime"]
    : ["-m", "unittest", "tests.test_mission_31f_cache_concurrency_realtime"];

const startedAt = new Date().toISOString();
const result = spawnSync(python, args, {
  cwd: repoRoot,
  encoding: "utf8",
  env: {
    ...process.env,
    STOCKNEWSBR_TEST_MODE: "1",
  },
  timeout: 120000,
});

const output = `${result.stdout || ""}\n${result.stderr || ""}`;
const failed = result.status !== 0 || Boolean(result.error);
const report = {
  mission: "31F",
  startedAt,
  finishedAt: new Date().toISOString(),
  failureCount: failed ? 1 : 0,
  websocket: [{ scenario: "capacity, broadcast, dead-client cleanup", status: failed ? "failed" : "passed" }],
  reconnect: [{ scenario: "bounded reconnect contract covered by manager cleanup", status: failed ? "failed" : "passed" }],
  rapidTickerSwitches: [{ scenario: "final ticker isolation deferred to existing UI smoke", status: "not_applicable_backend_only" }],
  duplicateMessages: [{ scenario: "Telegram duplicate fingerprint concurrency", status: failed ? "failed" : "passed" }],
  social: [{ scenario: "ticker room audit rollback", status: failed ? "failed" : "passed" }],
  polls: [{ scenario: "100 concurrent votes", status: failed ? "failed" : "passed" }],
  tickerRoom: [{ scenario: "audit failure rollback", status: failed ? "failed" : "passed" }],
  loadingStates: [],
  consoleErrors: [],
  networkErrors: [],
  screenshots: [],
  command: `${python} ${args.join(" ")}`,
  exitCode: result.status,
  error: result.error ? String(result.error) : null,
  outputTail: output.split(/\r?\n/).slice(-30),
};

mkdirSync(runtimeDir, { recursive: true });
writeFileSync(reportPath, `${JSON.stringify(report, null, 2)}\n`, "utf8");

if (failed) {
  console.error(output);
  console.error(`Mission 31F report written to ${reportPath}`);
  process.exit(result.status || 1);
}

console.log(`Mission 31F realtime concurrency audit passed. Report: ${reportPath}`);
