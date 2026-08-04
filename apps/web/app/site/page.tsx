import { Suspense } from "react";

import { WorkspaceShell } from "@/components/workspace-shell";

export default function SitePage() {
  return (
    <Suspense fallback={<div role="status" aria-live="polite">Carregando...</div>}>
      <WorkspaceShell />
    </Suspense>
  );
}
