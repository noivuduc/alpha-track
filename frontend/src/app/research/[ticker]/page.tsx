import ResearchShell from "@/components/research/ResearchShell";

export default function ResearchPage({ params }: { params: { ticker: string } }) {
  return <ResearchShell ticker={params.ticker.toUpperCase()} />;
}
