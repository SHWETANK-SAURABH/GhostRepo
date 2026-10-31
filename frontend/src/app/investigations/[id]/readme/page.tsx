import { ReadmeView } from "@/components/investigation/readme-view";

export default async function ReadmePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <ReadmeView id={id} />;
}