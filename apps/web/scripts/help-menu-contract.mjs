import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const read = (file) => fs.readFileSync(path.join(root, file), "utf8");
const shell = read("components/workspace-shell.tsx");
const rail = read("components/workspace-rails.tsx");
const panel = read("components/workspace-sections.tsx");
const labels = [
  "1️⃣ Sobre a Empresa",
  "2️⃣ Principais Módulos da Plataforma",
  "3️⃣ Glossário: Painel de Análise Estratégica",
  "4️⃣ Glossário: Gráfico do Ativo",
  "5️⃣ Glossário: Modos de Uso da Plataforma",
  "6️⃣ Guia Rápido StockNewsBR",
  "7️⃣ Plataforma Web Trader Desk",
  "8️⃣ Aviso legal",
  "9️⃣ Por que escolher StockNewsBR?",
];
const ids = [
  "sobre-a-empresa",
  "principais-modulos",
  "glossario-painel-estrategico",
  "glossario-grafico-ativo",
  "glossario-modos-plataforma",
  "guia-rapido-stocknewsbr",
  "plataforma-web-trader-desk",
  "aviso-legal",
  "por-que-stocknewsbr",
];
const fail = (message) => { throw new Error(`Help menu contract: ${message}`); };

let previous = -1;
for (const label of labels) {
  const position = shell.indexOf(label);
  if (position <= previous) fail(`invalid order for ${label}`);
  previous = position;
}
for (const id of ids) {
  if ((shell.match(new RegExp(`id: "${id}"`, "g")) || []).length !== 2) fail(`missing PT/EN id ${id}`);
}
for (const obsolete of ["filosofia-oficial", "institucional-produto", "institucional-educacao", "Ajuda ao Trader"]) {
  if (shell.includes(obsolete)) fail(`obsolete reference ${obsolete}`);
}
if (!rail.includes("institutionalSections.map")) fail("rail must render all nine items");
if (rail.includes("slice(0, 8)")) fail("rail still limits the menu to eight items");
if (!rail.includes("onOpenInstitutionalSection(section.id)")) fail("rail buttons no longer open their matching id");
if (!panel.includes("<article id={section.id}")) fail("panel no longer renders section anchors");
if (!shell.includes("setSelectedInstitutionalSectionId(sectionId)") || !shell.includes("setEducationAnchor(sectionId)")) {
  fail("shared open handler no longer selects and anchors the requested section");
}

console.log(JSON.stringify({ ok: true, labels: labels.length, ids }, null, 2));
