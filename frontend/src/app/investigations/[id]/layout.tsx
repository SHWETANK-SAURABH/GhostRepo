import type { ReactNode } from "react";

import { InvestigationFrame } from "@/components/investigation/investigation-header";

export default async function InvestigationLayout({
  children,
  params,
}: {
  children: ReactNode;
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <InvestigationFrame id={id}>{children}</InvestigationFrame>;
}