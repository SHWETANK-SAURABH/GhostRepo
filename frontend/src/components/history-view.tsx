"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowRight, History } from "lucide-react";
import Link from "next/link";

import { EmptyState, ErrorState } from "@/components/states";
import { StatusBadge } from "@/components/status-badge";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";

const AI_LABEL: Record<string, string> = {
  completed: "AI completed",
  failed: "AI failed",
  unavailable: "AI unavailable",
  disabled: "AI disabled",
  skipped: "AI skipped",
  running: "AI running",
  queued: "AI queued",
  pending: "AI pending",
};

export function HistoryView() {
  const { data, isPending, isError, error, refetch } = useQuery({
    queryKey: ["investigations"],
    queryFn: () => api.investigations(100),
  });

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Investigation history</h1>
        <p className="mt-1 text-muted-foreground">
          {data
            ? `${data.total} investigation${data.total === 1 ? "" : "s"} stored locally.`
            : "Stored locally."}
        </p>
      </div>
      {isPending && <Skeleton className="h-48 rounded-xl" />}
      {isError && <ErrorState error={error} onRetry={() => refetch()} />}
      {data && data.items.length === 0 && (
        <EmptyState icon={History} title="No investigations yet">
          Investigations you run will appear here.
        </EmptyState>
      )}
      {data && data.items.length > 0 && (
        <Card>
          <CardContent>
            <ul className="flex flex-col divide-y divide-border">
              {data.items.map((item) => (
                <li key={item.id}>
                  <Link
                    href={`/investigations/${item.id}`}
                    className="-mx-2 flex items-center gap-3 rounded-md px-2 py-3 transition-colors hover:bg-muted/50"
                  >
                    <span className="min-w-0 flex-1">
                      <span className="block truncate font-mono text-sm">
                        {item.repository.name}
                      </span>
                      <span className="text-xs text-muted-foreground">
                        {new Date(item.created_at).toLocaleString()} ·{" "}
                        {item.verified_finding_count} verified findings ·{" "}
                        {AI_LABEL[item.ai_status] ?? item.ai_status}
                        {item.health_score !== null && ` · health ${item.health_score}`}
                      </span>
                    </span>
                    <StatusBadge status={item.status} />
                    <ArrowRight className="size-4 text-muted-foreground" aria-hidden />
                  </Link>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
