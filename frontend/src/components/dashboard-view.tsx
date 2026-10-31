"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowRight, FileSearch, Ghost, HeartPulse, ListChecks, ShieldCheck } from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";

import { describeRuntime, useOllamaStatus } from "@/components/runtime-status";
import { SEVERITY_STYLE } from "@/components/severity";
import { EmptyState, ErrorState } from "@/components/states";
import { StatusBadge } from "@/components/status-badge";
import { buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { SEVERITIES, type DashboardSummary } from "@/lib/types";

function StatTile({
  label,
  value,
  note,
  icon,
}: {
  label: string;
  value: ReactNode;
  note: string;
  icon: ReactNode;
}) {
  return (
    <Card size="sm">
      <CardContent className="flex flex-col gap-1">
        <div className="flex items-center justify-between gap-2 text-xs text-muted-foreground">
          {label}
          {icon}
        </div>
        <p className="font-mono text-3xl font-semibold tabular-nums">{value}</p>
        <p className="text-xs text-muted-foreground">{note}</p>
      </CardContent>
    </Card>
  );
}

function SeveritySummary({ summary }: { summary: DashboardSummary }) {
  const largest = Math.max(1, ...Object.values(summary.severity_counts));
  return (
    <ul className="flex flex-col gap-2.5">
      {SEVERITIES.map((severity) => {
        const style = SEVERITY_STYLE[severity];
        const Icon = style.icon;
        const count = summary.severity_counts[severity] ?? 0;
        return (
          <li
            key={severity}
            className="grid grid-cols-[7.5rem_1fr_2rem] items-center gap-2 text-sm"
            title={`${style.label}: ${count} verified`}
          >
            <span className="flex items-center gap-1.5 text-muted-foreground">
              <Icon className={`size-3.5 ${style.text}`} aria-hidden />
              {style.label}
            </span>
            <span className="h-1.5 rounded-full bg-muted" aria-hidden>
              <span
                className={`block h-full rounded-full ${style.bar}`}
                style={{ width: `${(count / largest) * 100}%` }}
              />
            </span>
            <span className="text-right font-mono tabular-nums">{count}</span>
          </li>
        );
      })}
    </ul>
  );
}

function RuntimeCard() {
  const { data, isError } = useOllamaStatus();
  const tone = describeRuntime(data, isError);
  const Icon = tone.icon;
  return (
    <Card>
      <CardHeader>
        <CardTitle>AI runtime</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-2 text-sm">
        <p className="flex items-center gap-2 font-medium">
          <Icon className={`size-4 ${tone.color}`} aria-hidden />
          {tone.label}
        </p>
        <p className="text-muted-foreground">
          {isError ? "Start the backend to check the runtime." : data?.message}
        </p>
        {data && (
          <dl className="mt-1 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 font-mono text-xs">
            <dt className="text-muted-foreground">model</dt>
            <dd className="truncate">{data.model}</dd>
            {data.version && (
              <>
                <dt className="text-muted-foreground">ollama</dt>
                <dd>{data.version}</dd>
              </>
            )}
          </dl>
        )}
        <p className="mt-1 text-xs text-muted-foreground">
          Verified findings do not need a model. They appear with or without Ollama.
        </p>
      </CardContent>
    </Card>
  );
}

export function DashboardView() {
  const { data, isPending, isError, error, refetch } = useQuery({
    queryKey: ["dashboard"],
    queryFn: api.dashboard,
  });

  return (
    <div className="flex flex-col gap-6">
      <section className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight md:text-3xl">
            Welcome to the investigation room
          </h1>
          <p className="mt-1 text-muted-foreground">
            Every abandoned repository has a story. Let&apos;s bring it back to life.
          </p>
        </div>
        <Link
          href="/investigations/new"
          className={`${buttonVariants({ size: "lg" })} ghost-glow shrink-0`}
        >
          <Ghost aria-hidden />
          Summon Ghost — Inspect Repository
        </Link>
      </section>

      {isError && <ErrorState error={error} onRetry={() => refetch()} />}

      {isPending && (
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4" aria-label="Loading summary">
          {[0, 1, 2, 3].map((item) => (
            <Skeleton key={item} className="h-28 rounded-xl" />
          ))}
        </div>
      )}

      {data && (
        <section className="grid grid-cols-2 gap-3 lg:grid-cols-4" aria-label="Summary">
          <StatTile
            label="Investigations"
            value={data.investigations}
            note="All time"
            icon={<FileSearch className="size-4" aria-hidden />}
          />
          <StatTile
            label="Verified findings"
            value={data.verified_findings}
            note="From deterministic analyzers"
            icon={<ShieldCheck className="size-4" aria-hidden />}
          />
          <StatTile
            label="Recovery suggestions"
            value={data.pending_recovery_tasks}
            note="Pending"
            icon={<ListChecks className="size-4" aria-hidden />}
          />
          <StatTile
            label="Repository health"
            value={data.average_health_score ?? "—"}
            note={data.average_health_score === null ? "No score yet" : "Average indicator, 0–100"}
            icon={<HeartPulse className="size-4" aria-hidden />}
          />
        </section>
      )}

      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="min-w-0 lg:col-span-2">
          <CardHeader>
            <CardTitle>Recent investigations</CardTitle>
          </CardHeader>
          <CardContent>
            {data && data.recent.length === 0 && (
              <EmptyState icon={Ghost} title="No investigations yet">
                Summon the ghost to inspect a repository in your workspace.
              </EmptyState>
            )}
            {isPending && <Skeleton className="h-32" />}
            {data && data.recent.length > 0 && (
              <ul className="flex flex-col divide-y divide-border">
                {data.recent.map((item) => (
                  <li key={item.id}>
                    <Link
                      href={`/investigations/${item.id}`}
                      className="-mx-2 flex items-center gap-3 rounded-md px-2 py-3 transition-colors hover:bg-muted/50"
                    >
                      <span className="min-w-0 flex-1">
                        <span className="block truncate font-mono text-sm">
                          {item.repository_name}
                        </span>
                        <span className="text-xs text-muted-foreground">
                          {new Date(item.created_at).toLocaleString()} · {item.finding_count}{" "}
                          findings
                          {item.health_score !== null && ` · health ${item.health_score}`}
                        </span>
                      </span>
                      <StatusBadge status={item.status} />
                      <ArrowRight className="size-4 text-muted-foreground" aria-hidden />
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>

        <div className="flex min-w-0 flex-col gap-4">
          <RuntimeCard />
          <Card>
            <CardHeader>
              <CardTitle>Verified findings by severity</CardTitle>
            </CardHeader>
            <CardContent>
              {data ? <SeveritySummary summary={data} /> : <Skeleton className="h-32" />}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
