import fs from "node:fs";
import ts from "typescript";

process.env.TZ = "America/Sao_Paulo";
const source = fs.readFileSync(new URL("../lib/social-time.ts", import.meta.url), "utf8");
const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText;
const { formatSocialTimestamp } = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString("base64")}`);

const sameDay = formatSocialTimestamp("2026-07-18T13:25:00Z", "pt-BR", new Date("2026-07-18T15:00:00Z"));
const previousDay = formatSocialTimestamp("2026-07-17T13:25:00Z", "pt-BR", new Date("2026-07-18T15:00:00Z"));
const previousDayEn = formatSocialTimestamp("2026-07-17T13:25:00Z", "en-US", new Date("2026-07-18T15:00:00Z"));
const epoch = formatSocialTimestamp(1784381100, "pt-BR", new Date("2026-07-18T15:00:00Z"));
if (sameDay.label !== "10:25 AM") throw new Error(`unexpected same-day timestamp: ${sameDay.label}`);
if (previousDay.label !== "17/07/2026 · 10:25 AM") throw new Error(`unexpected previous-day timestamp: ${previousDay.label}`);
if (previousDayEn.label !== "07/17/2026 · 10:25 AM") throw new Error(`unexpected English timestamp: ${previousDayEn.label}`);
if (epoch.label !== sameDay.label || epoch.dateTime !== sameDay.dateTime) throw new Error("epoch and created_at must remain stable after reload");
if (!sameDay.title.includes("2026") || sameDay.dateTime !== "2026-07-18T13:25:00.000Z") throw new Error("timestamp metadata is incomplete");
if (formatSocialTimestamp("invalid", "pt-BR").label !== "horário indisponível") throw new Error("invalid timestamp must be neutral");
console.log("social-time-regression: ok");
