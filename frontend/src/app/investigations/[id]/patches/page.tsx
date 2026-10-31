import { PatchesView } from "@/components/investigation/patches-view";

export default async function PatchesPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <PatchesView id={id} />;
}