import ResearchShell from "@/components/research/ResearchShell";

export default async function ResearchPage({ params }: { params: Promise<{ ticker: string }> }) {
  const { ticker } = await params;
  return <ResearchShell ticker={ticker.toUpperCase()} />;
}
