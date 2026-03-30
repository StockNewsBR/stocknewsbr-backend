import { WorkspaceShell } from "@/components/workspace-shell";

export default async function PanelPage({
  params
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  return <WorkspaceShell focusedTab={slug} />;
}
