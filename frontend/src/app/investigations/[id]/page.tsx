import { AutopsyView } from "@/components/investigation/autopsy-view";

export default async function AutopsyPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <AutopsyView id={id} />;
}