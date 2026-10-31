"use client";

import { Check, GitBranch, Info, X } from "lucide-react";
import type { ReactNode } from "react";

import { AiPanel } from "@/components/investigation/ai-panel";
import { ProgressPanel } from "@/components/investigation/progress-panel";
import { isActive, useReport } from "@/components/investigation/use-report";
import { ErrorState } from "@/components/states";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { Profile, Report } from "@/lib/types";

function Facts({ rows }: { rows: [string, ReactNode][] }) {
  return (
    <dl className="grid grid-cols-[minmax(0,auto)_minmax(0,1fr)] gap-x-4 gap-y-1.5 text-sm">
      {rows.map(([label, value]) => (
        <div key={label} className="contents">
          <dt className="text-muted-foreground">{label}</dt>
          <dd className="min-w-0 break-words">{value}</dd>
        </div>
      ))}
    </dl>
  );
}

function Unavailable({ what }: { what: string }) {
  return <p className="text-sm text-muted-foreground">{what} is not available for this report.</p>;
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <Card className="min-w-0">
      <CardHeader>
        <CardTitle>{title}</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">{children}</CardContent>
    </Card>
  );
}

function HealthCard({ report }: { report: Report }) {
  const score = report.health.score;
  return (
    <Card size="sm">
      <CardContent className="flex items-center gap-4">
        <p className="font-mono text-4xl font-semibold tabular-nums">{score ?? "—"}</p>
        <div className="min-w-0 flex-1 text-sm">
          <p className="flex items-center gap-1.5 font-medium">
            Health indicator
            <Tooltip>
              <TooltipTrigger
                aria-label="How the health indicator is calculated"
                className="rounded text-muted-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
              >
                <Info className="size-3.5" aria-hidden />
              </TooltipTrigger>
              <TooltipContent className="max-w-xs">{report.health.note}</TooltipContent>
            </Tooltip>
          </p>
          <p className="text-muted-foreground">
            {report.investigation.verified_finding_count} verified findings
            {report.investigation.ai_finding_count > 0 &&
              `, ${report.investigation.ai_finding_count} AI-generated`}
          </p>
        </div>
      </CardContent>
    </Card>
  );
}

function RepositorySection({ data, report }: { data: Profile["repository"]; report: Report }) {
  if (!data) return <Unavailable what="Repository information" />;
  return (
    <>
      <Facts
        rows={[
          ["Primary language", data.primary_language ?? "Not detected"],
          ["Frameworks", report.investigation.repository.detected_frameworks.join(", ") || "None detected"],
          ["Build tools", data.build_tools.join(", ") || "None detected"],
          ["Files scanned", data.file_count],
        ]}
      />
      {data.languages.length > 0 && (
        <ul className="flex flex-col gap-1.5" aria-label="Languages by file size">
          {data.languages.slice(0, 6).map((language) => (
            <li
              key={language.name}
              className="grid grid-cols-[6rem_1fr_3rem] items-center gap-2 text-xs"
              title={`${language.name}: ${language.files} files`}
            >
              <span className="truncate">{language.name}</span>
              <span className="h-1.5 rounded-full bg-muted" aria-hidden>
                <span
                  className="block h-full rounded-full bg-primary"
                  style={{ width: `${language.share}%` }}
                />
              </span>
              <span className="text-right font-mono tabular-nums">{language.share}%</span>
            </li>
          ))}
        </ul>
      )}
      {data.entry_points.length > 0 && (
        <p className="text-sm">
          <span className="text-muted-foreground">Entry points: </span>
          <span className="font-mono text-xs break-all">{data.entry_points.join(", ")}</span>
        </p>
      )}
    </>
  );
}

const GIT_REASON: Record<string, string> = {
  no_git_metadata: "No Git metadata was found, so history is unknown.",
  unsafe_git_metadata: "The .git entry is a symlink or pointer file, so it was not followed.",
  git_refused: "Git could not read this repository's metadata.",
  git_failed: "Git could not be used.",
};

function GitSection({ data }: { data: Profile["git"] }) {
  if (!data) return <Unavailable what="Git history" />;
  if (!data.available) {
    return (
      <p className="text-sm text-muted-foreground">
        {GIT_REASON[data.reason ?? ""] ?? "Git history is not available."}
      </p>
    );
  }
  if (!data.latest_commit) {
    return <p className="text-sm text-muted-foreground">This repository has no commits yet.</p>;
  }
  return (
    <>
      <Facts
        rows={[
          [
            "Branch",
            <span key="branch" className="inline-flex items-center gap-1 font-mono">
              <GitBranch className="size-3.5" aria-hidden />
              {data.branch ?? "detached HEAD"}
            </span>,
          ],
          [
            "Latest commit",
            <span key="latest">
              <span className="font-mono text-xs">{data.latest_commit.hash}</span>{" "}
              {data.latest_commit.subject}
              <span className="block text-xs text-muted-foreground">
                {data.latest_commit.author}, {new Date(data.latest_commit.date).toLocaleDateString()}
              </span>
            </span>,
          ],
          ["Commits", `${data.commit_count}${data.shallow_clone ? " (shallow clone)" : ""}`],
          ["First commit", data.first_commit_date ? new Date(data.first_commit_date).toLocaleDateString() : "Unknown"],
          ["Days since last commit", data.days_since_last_commit],
          ["Contributors", data.contributor_count],
          [
            "Commits in last 30 / 90 / 365 days",
            `${data.activity?.last_30_days} / ${data.activity?.last_90_days} / ${data.activity?.last_365_days}`,
          ],
          ["Conventional commit subjects", `${data.message_patterns?.conventional_commit_share}%`],
        ]}
      />
      <p className="text-xs text-muted-foreground">
        These are observations. A quiet repository may be finished or stable, so age alone does not
        mean it is abandoned.
      </p>
    </>
  );
}

function DependencySection({ data }: { data: Profile["dependencies"] }) {
  if (!data) return <Unavailable what="Dependency information" />;
  return (
    <>
      <Facts
        rows={[
          ["Manifests", <span key="m" className="font-mono text-xs break-all">{data.manifests.join(", ") || "None found"}</span>],
          ["Ecosystems", data.ecosystems.join(", ") || "None"],
          ["Declared", `${data.dependency_count} (${data.direct_runtime_count} runtime, ${data.dev_count} development)`],
          ["Without a version constraint", data.pinning.unbounded ?? 0],
          ["Lockfiles", <span key="l" className="font-mono text-xs break-all">{data.lockfiles.join(", ") || "None found"}</span>],
          ["Malformed manifests", data.malformed_manifests.length],
        ]}
      />
      <p className="text-xs text-muted-foreground">{data.freshness_note}</p>
    </>
  );
}

function DocumentationSection({ data }: { data: Profile["documentation"] }) {
  if (!data) return <Unavailable what="Documentation information" />;
  return (
    <>
      <p className="text-sm">
        <span className="font-mono text-lg font-semibold tabular-nums">
          {data.completeness_score}%
        </span>{" "}
        <span className="text-muted-foreground">of observable criteria met</span>
      </p>
      <ul className="grid gap-1 text-sm sm:grid-cols-2">
        {Object.entries(data.criteria).map(([name, met]) => (
          <li key={name} className="flex items-start gap-1.5">
            {met ? (
              <Check className="mt-0.5 size-3.5 shrink-0 text-primary" aria-label="Met" />
            ) : (
              <X className="mt-0.5 size-3.5 shrink-0 text-muted-foreground" aria-label="Not met" />
            )}
            <span className={met ? "" : "text-muted-foreground"}>{name}</span>
          </li>
        ))}
      </ul>
    </>
  );
}

function TestSection({ data }: { data: Profile["tests"] }) {
  if (!data) return <Unavailable what="Test discovery" />;
  return (
    <>
      <Facts
        rows={[
          ["Test files", data.test_file_count],
          ["Source files", data.source_file_count],
          ["Test directories", <span key="d" className="font-mono text-xs break-all">{data.test_directories.join(", ") || "None found"}</span>],
          ["Tooling", data.frameworks.join(", ") || "None identified"],
        ]}
      />
      {data.commands.length > 0 && (
        <ul className="flex flex-col gap-1 text-sm">
          {data.commands.map((item) => (
            <li key={item.command} className="flex flex-wrap items-center gap-2">
              <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-xs">{item.command}</code>
              <span className="text-xs text-muted-foreground">{item.source}</span>
            </li>
          ))}
        </ul>
      )}
      <p className="text-xs text-muted-foreground">
        Tests were discovered, not run, so whether they pass is unknown.
      </p>
    </>
  );
}

export function AutopsyView({ id }: { id: string }) {
  const { data: report, isPending, isError, error, refetch } = useReport(id);

  if (isPending) return <Skeleton className="h-64 rounded-xl" />;
  if (isError) return <ErrorState error={error} onRetry={() => refetch()} />;

  const investigation = report.investigation;
  const showProgress =
    isActive(investigation) ||
    investigation.status === "failed" ||
    investigation.status === "interrupted" ||
    investigation.stages.some((stage) => stage.status === "failed" && stage.key !== "ai");
  const hasResults = Object.keys(report.profile).length > 0;

  return (
    <div className="flex flex-col gap-4">
      {showProgress && <ProgressPanel id={id} />}
      {investigation.status === "completed" && investigation.error_message && (
        <ErrorState error={new Error(investigation.error_message)} />
      )}
      {hasResults && (
        <>
          <div className="grid gap-4 lg:grid-cols-3">
            <div className="flex min-w-0 flex-col gap-4">
              <HealthCard report={report} />
              <Section title="Repository">
                <RepositorySection data={report.profile.repository} report={report} />
              </Section>
            </div>
            <div className="min-w-0 lg:col-span-2">
              <AiPanel report={report} />
            </div>
          </div>
          <div className="grid gap-4 lg:grid-cols-2">
            <Section title="Git history">
              <GitSection data={report.profile.git} />
            </Section>
            <Section title="Dependencies">
              <DependencySection data={report.profile.dependencies} />
            </Section>
            <Section title="Documentation">
              <DocumentationSection data={report.profile.documentation} />
            </Section>
            <Section title="Tests">
              <TestSection data={report.profile.tests} />
            </Section>
          </div>
        </>
      )}
    </div>
  );
}
