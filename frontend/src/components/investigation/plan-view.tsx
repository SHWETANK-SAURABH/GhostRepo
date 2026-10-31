"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ListChecks, Sparkles } from "lucide-react";
import { toast } from "sonner";

import { useReport } from "@/components/investigation/use-report";
import { EmptyState, ErrorState } from "@/components/states";
import { Card, CardContent } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { api, errorMessage } from "@/lib/api";
import type { RecoveryTask, TaskStatus } from "@/lib/types";

const STATUS_LABEL: Record<TaskStatus, string> = {
  pending: "Pending",
  in_progress: "In progress",
  done: "Done",
  dismissed: "Dismissed",
};

const PRIORITY_CLASS: Record<RecoveryTask["priority"], string> = {
  high: "border-severity-high/50 text-severity-high",
  medium: "border-severity-medium/50 text-severity-medium",
  low: "border-severity-low/50 text-severity-low",
};

function TaskCard({ task, position, id }: { task: RecoveryTask; position: number; id: string }) {
  const queryClient = useQueryClient();
  const update = useMutation({
    mutationFn: (status: TaskStatus) => api.updateTask(id, task.id, status),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["report", id] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    },
    onError: (error) => toast.error(errorMessage(error)),
  });
  const closed = task.status === "done" || task.status === "dismissed";

  return (
    <Card size="sm" className={closed ? "opacity-70" : ""}>
      <CardContent className="flex flex-col gap-3 text-sm">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="flex min-w-0 flex-1 items-start gap-3">
            <span className="font-mono text-muted-foreground tabular-nums">{position}.</span>
            <div className="min-w-0">
              <h3 className="font-medium break-words">{task.title}</h3>
              <div className="mt-1 flex flex-wrap items-center gap-1.5">
                <span
                  className={`rounded-md border px-2 py-0.5 text-xs capitalize ${PRIORITY_CLASS[task.priority]}`}
                >
                  {task.priority} priority
                </span>
                {task.origin === "ai" && (
                  <span className="inline-flex items-center gap-1 rounded-md border border-spectral/40 px-2 py-0.5 text-xs text-spectral">
                    <Sparkles className="size-3" aria-hidden />
                    AI suggestion
                  </span>
                )}
              </div>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Label htmlFor={`status-${task.id}`} className="text-xs text-muted-foreground">
              Status
            </Label>
            <select
              id={`status-${task.id}`}
              value={task.status}
              disabled={update.isPending}
              onChange={(event) => update.mutate(event.target.value as TaskStatus)}
              className="h-8 rounded-md border border-input bg-card px-2 text-xs focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
            >
              {Object.entries(STATUS_LABEL).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </div>
        </div>

        <dl className="flex flex-col gap-2">
          <div>
            <dt className="text-xs text-muted-foreground">Problem</dt>
            <dd className="break-words">{task.description}</dd>
          </div>
          {task.why_it_matters && (
            <div>
              <dt className="text-xs text-muted-foreground">Why it matters</dt>
              <dd className="break-words">{task.why_it_matters}</dd>
            </div>
          )}
          {task.solution && (
            <div>
              <dt className="text-xs text-muted-foreground">Recommended solution</dt>
              <dd className="break-words">{task.solution}</dd>
            </div>
          )}
          {task.files.length > 0 && (
            <div>
              <dt className="text-xs text-muted-foreground">Files involved</dt>
              <dd className="font-mono text-xs break-all">{task.files.join(", ")}</dd>
            </div>
          )}
          {task.effort_estimate && (
            <div>
              <dt className="text-xs text-muted-foreground">
                Estimated effort (a rough estimate, not a measurement)
              </dt>
              <dd>{task.effort_estimate}</dd>
            </div>
          )}
          {task.verification_steps.length > 0 && (
            <div>
              <dt className="text-xs text-muted-foreground">How to verify</dt>
              <dd>
                <ul className="list-inside list-disc">
                  {task.verification_steps.map((step) => (
                    <li key={step}>{step}</li>
                  ))}
                </ul>
              </dd>
            </div>
          )}
        </dl>
      </CardContent>
    </Card>
  );
}

export function PlanView({ id }: { id: string }) {
  const { data: report, isPending, isError, error, refetch } = useReport(id);

  if (isPending) return <Skeleton className="h-64 rounded-xl" />;
  if (isError) return <ErrorState error={error} onRetry={() => refetch()} />;

  if (report.recovery_tasks.length === 0) {
    return (
      <EmptyState icon={ListChecks} title="No recovery tasks">
        Tasks appear once analysis finishes, for any finding that needs action.
      </EmptyState>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      <p className="text-sm text-muted-foreground">
        In priority order. GhostRepo only recommends these steps and does not carry them out.
      </p>
      {report.recovery_tasks.map((task, index) => (
        <TaskCard key={task.id} task={task} position={index + 1} id={id} />
      ))}
    </div>
  );
}
