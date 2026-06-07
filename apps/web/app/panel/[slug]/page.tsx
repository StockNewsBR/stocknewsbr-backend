import { WorkspaceShell } from "@/components/workspace-shell";

const PANEL_TAB_IDS = new Set([
  "grafico",
  "news",
  "busca",
  "heat-map",
  "radar",
  "breakout-probability",
  "volatility-squeeze",
  "institutional-flow",
  "smart-money",
  "accumulation",
  "liquidity-sweep",
  "liquidity-map",
  "market-regime",
  "master-score",
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
