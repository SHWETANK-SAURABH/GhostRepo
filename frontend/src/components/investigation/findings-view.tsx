"use client";

import { FileSearch, ShieldCheck, Sparkles } from "lucide-react";
import { useState } from "react";

import { AiLabel } from "@/components/investigation/ai-panel";
import { useReport } from "@/components/investigation/use-report";
import { SEVERITY_STYLE, SeverityBadge } from "@/components/severity";
import { EmptyState, ErrorState } from "@/components/states";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { SEVERITIES, type Evidence, type Finding, type Severity } from "@/lib/types";

function FindingCard({ finding, evidence }: { finding: Finding; evidence: Map<string, Evidence> }) {
  const cited = finding.evidence_references.map((key) => ({ key, item: evidence.get(key) }));
  return (
    <Card size="sm">
      <CardContent className="flex flex-col gap-2 text-sm">
        <div className="flex flex-wrap items-center gap-2">
          <SeverityBadge severity={finding.severity} />
          <span className="rounded-md bg-muted px-2 py-0.5 text-xs capitalize">
            {finding.category}
          </span>
          {finding.origin === "ai" && (
            <span className="rounded-md border border-spectral/40 px-2 py-0.5 text-xs text-spectral">
              {finding.is_hypothesis ? "Hypothesis" : "Evidence-linked interpretation"}
            </span>
          )}
        </div>
        <h3 className="font-medium break-words">{finding.title}</h3>
        <p className="break-words text-muted-foreground">{finding.description}</p>
        <p className="break-words">
          <span className="text-muted-foreground">Suggested action: </span>
          {finding.recommendation}
        </p>
        <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-0.5 text-xs text-muted-foreground">
          {finding.source_file && (
            <>
              <dt>Source</dt>
              <dd className="font-mono break-all text-foreground">{finding.source_file}</dd>
            </>
          )}
          <dt>Confidence</dt>
          <dd className="font-mono text-foreground">{Math.round(finding.confidence * 100)}%</dd>
          <dt>Detected by</dt>
          <dd className="font-mono break-all text-foreground">{finding.detection_method}</dd>
        </dl>
        <details className="text-xs">
          <summary className="cursor-pointer text-muted-foreground hover:text-foreground">
            Evidence ({cited.length})
          </summary>
          <ul className="mt-2 flex flex-col gap-1.5">
            {cited.map(({ key, item }) => (
              <li key={key} className="rounded bg-muted/60 p-2">
                <span className="font-mono text-primary">{key}</span>
                <span className="mt-0.5 block break-words">
                  {item?.description ?? "This evidence is not in the report."}
                </span>
              </li>
            ))}
          </ul>
        </details>
      </CardContent>
    </Card>
  );
}

export function FindingsView({ id }: { id: string }) {
  const { data: report, isPending, isError, error, refetch } = useReport(id);
  const [filter, setFilter] = useState<Severity | "all">("all");

  if (isPending) return <Skeleton className="h-64 rounded-xl" />;
  if (isError) return <ErrorState error={error} onRetry={() => refetch()} />;

  const evidence = new Map(report.evidence.map((item) => [item.key, item]));
  const matches = (finding: Finding) => filter === "all" || finding.severity === filter;
  const verified = report.verified_findings.filter(matches);
  const showAi = report.ai.status === "completed";
  const aiFindings = showAi ? report.ai.findings.filter(matches) : [];
  const all = [...report.verified_findings, ...(showAi ? report.ai.findings : [])];

  return (
    <div className="flex flex-col gap-6">
      <div role="group" aria-label="Filter by severity" className="flex flex-wrap gap-1.5">
        {(["all", ...SEVERITIES] as const).map((value) => {
          const count =
            value === "all" ? all.length : all.filter((item) => item.severity === value).length;
          const label = value === "all" ? "All" : SEVERITY_STYLE[value].label;
          return (
            <button
              key={value}
              type="button"
              aria-pressed={filter === value}
              onClick={() => setFilter(value)}
              className={`rounded-md border px-2.5 py-1 text-xs transition-colors focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none ${
                filter === value
                  ? "border-primary/50 bg-primary/10"
                  : "border-border text-muted-foreground hover:text-foreground"
              }`}
            >
              {label} <span className="font-mono tabular-nums">{count}</span>
            </button>
          );
        })}
      </div>

      <section aria-labelledby="verified-heading" className="flex flex-col gap-3">
        <div>
          <h2 id="verified-heading" className="flex items-center gap-2 font-medium">
            <ShieldCheck className="size-4 text-primary" aria-hidden />
            Verified findings
          </h2>
          <p className="text-sm text-muted-foreground">
            Produced by deterministic analyzers from files in the repository.
          </p>
        </div>
        {verified.length === 0 && (
          <EmptyState icon={FileSearch} title="No verified findings match this filter" />
        )}
        {verified.map((finding) => (
          <FindingCard key={finding.id} finding={finding} evidence={evidence} />
        ))}
      </section>

      <section aria-labelledby="ai-heading" className="flex flex-col gap-3">
        <div>
          <h2 id="ai-heading" className="flex flex-wrap items-center gap-2 font-medium">
            <Sparkles className="size-4 text-spectral" aria-hidden />
            AI-generated findings and hypotheses
            {showAi && <AiLabel model={report.ai.model} />}
          </h2>
          <p className="text-sm text-muted-foreground">
            Interpretation by a local model. Each one cites real evidence, but review it before
            relying on it.
          </p>
        </div>
        {!showAi && (
          <EmptyState icon={Sparkles} title="No AI results">
            AI analysis status: {report.ai.status}. See the Autopsy tab for details and to retry.
          </EmptyState>
        )}
        {showAi && aiFindings.length === 0 && (
          <EmptyState icon={Sparkles} title="No AI findings match this filter" />
        )}
        {aiFindings.map((finding) => (
          <FindingCard key={finding.id} finding={finding} evidence={evidence} />
        ))}
        {showAi && report.ai.rejected.length > 0 && (
          <details className="rounded-lg border border-border p-3 text-sm">
            <summary className="cursor-pointer text-muted-foreground">
              {report.ai.rejected.length} AI item(s) rejected during validation
            </summary>
            <ul className="mt-2 flex flex-col gap-1 text-xs">
              {report.ai.rejected.map((item, index) => (
                <li key={`${item.title}-${index}`} className="break-words">
                  <span className="font-medium">{item.title}:</span> {item.reason}
                </li>
              ))}
            </ul>
          </details>
        )}
      </section>
    </div>
  );
}
