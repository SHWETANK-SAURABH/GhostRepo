"use client";

import { useQuery } from "@tanstack/react-query";
import { Circle, CircleCheck, CircleMinus, CircleX, LoaderCircle } from "lucide-react";

import { isActive } from "@/components/investigation/use-report";
import { ErrorState } from "@/components/states";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress as ProgressBar } from "@/components/ui/progress";
import { api } from "@/lib/api";
import type { Stage } from "@/lib/types";

const STAGE_ICON = {
  pending: { icon: Circle, className: "text-muted-foreground/50", label: "Pending" },
  running: { icon: LoaderCircle, className: "animate-spin text-primary", label: "Running" },
  completed: { icon: CircleCheck, className: "text-primary", label: "Done" },
  failed: { icon: CircleX, className: "text-destructive", label: "Failed" },
  skipped: { icon: CircleMinus, className: "text-muted-foreground", label: "Skipped" },
} as const;

export function StageList({ stages }: { stages: Stage[] }) {
  return (
    <ol className="flex flex-col gap-2.5">
      {stages.map((stage) => {
        const { icon: Icon, className, label } = STAGE_ICON[stage.status];
        return (
          <li key={stage.key} className="flex items-start gap-2.5 text-sm">
            <Icon className={`mt-0.5 size-4 shrink-0 ${className}`} aria-hidden />
            <div className="min-w-0 flex-1">
              <div className="flex items-baseline justify-between gap-2">
                <span className={stage.status === "pending" ? "text-muted-foreground" : ""}>
                  {stage.label}
                </span>
                <span className="text-xs text-muted-foreground">{label}</span>
              </div>
              {stage.message && (
                <p className="mt-0.5 text-xs text-muted-foreground">{stage.message}</p>
              )}
            </div>
          </li>
        );
      })}
    </ol>
  );
}

export function ProgressPanel({ id }: { id: string }) {
  const { data, isError, error, refetch } = useQuery({
    queryKey: ["progress", id],
    queryFn: () => api.progress(id),
    refetchInterval: (query) =>
      !query.state.data || isActive(query.state.data) ? 1000 : false,
  });

  if (isError) return <ErrorState error={error} onRetry={() => refetch()} />;
  const percent = data?.percent ?? 0;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Investigation progress</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <div className="flex items-center gap-3">
          <ProgressBar value={percent} aria-label="Investigation progress" className="flex-1" />
          <span className="font-mono text-sm tabular-nums">{percent}%</span>
        </div>
        {data && <StageList stages={data.stages} />}
        {data?.error_message && <ErrorState error={new Error(data.error_message)} />}
      </CardContent>
    </Card>
  );
}
