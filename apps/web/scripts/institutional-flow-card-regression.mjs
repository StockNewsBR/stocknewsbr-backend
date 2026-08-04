import assert from "node:assert/strict";
import fs from "node:fs";

const shell = fs.readFileSync(new URL("../components/workspace-shell.tsx", import.meta.url), "utf8");

assert.match(shell, /panel\.why\?\.find\(\(item\) => item\.tool === "flow"\)/);
assert.match(shell, /publicInsight\?\.strategic_panel,/);
assert.match(shell, /currentStrategicPanel\s*\?\s*strategicPanelDecisionCards\(currentStrategicPanel, appLocale\)\[4\]/);
assert.match(shell, /label: isEnglish \? "Institutional Flow" : "Fluxo Institucional"/);
assert.match(shell, /flowValue.*\|\| \(isEnglish \? "No read" : "Sem leitura"\)/);
assert.match(shell, /const \[scoreCard, directionCard, tradeCard, regimeCard, flowCard, liquidityCard, riskCard\] = essentialDecisionCards/);
assert.ok(shell.indexOf('label: isEnglish ? "Regime" : "Regime"') < shell.indexOf('label: isEnglish ? "Institutional Flow" : "Fluxo Institucional"'));

console.log("institutional flow card regression: ok");
