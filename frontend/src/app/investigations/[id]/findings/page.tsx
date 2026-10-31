import { FindingsView } from "@/components/investigation/findings-view";

export default async function FindingsPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <FindingsView id={id} />;
}