import { Suspense } from "react";

import { WorkspaceShell } from "@/components/workspace-shell";

export default function HomePage() {
  return (
    <Suspense fallback={null}>
      <WorkspaceShell />
    </Suspense>
  );
}
