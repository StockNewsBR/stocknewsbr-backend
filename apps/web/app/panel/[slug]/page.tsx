import { WorkspaceShell } from "@/components/workspace-shell";

const PANEL_TAB_IDS = new Set([
  "grafico",
  "news",
  "busca",
  "flow",
  "liquidity",
  "trend",
  "momentum",
  "smart-money",
  "risk",
  "news-ia",
  "macro",
  "regime",
  "education",
]);

export default async function PanelPage({
  params
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const normalizedSlug = String(slug || "").trim();
  const focusedTab = PANEL_TAB_IDS.has(normalizedSlug) ? normalizedSlug : undefined;
  const initialTicker = focusedTab ? undefined : normalizedSlug;
  return <WorkspaceShell focusedTab={focusedTab} initialTicker={initialTicker} />;
}
