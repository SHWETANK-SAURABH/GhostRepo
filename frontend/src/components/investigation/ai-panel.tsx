"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { LoaderCircle, RefreshCw, Sparkles, TriangleAlert } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api, errorMessage } from "@/lib/api";
import type { Report } from "@/lib/types";

const STATE_TEXT: Record<string, string> = {
  pending: "AI analysis has not started.",
  queued: "AI analysis is queued.",
  running: "The local model is analyzing the evidence. This can take a few minutes.",
  disabled: "AI is disabled in Settings. These results come from deterministic analyzers only.",
  skipped: "AI analysis was skipped because the investigation did not finish.",
};

export function AiLabel({ model }: { model?: string | null }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-md border border-spectral/40 px-2 py-0.5 text-xs text-spectral">
      <Sparkles className="size-3" aria-hidden />
      AI-generated{model ? ` · ${model}` : ""}
    </span>
  );
}

export function AiPanel({ report }: { report: Report }) {
  const queryClient = useQueryClient();
  const id = report.investigation.id;
  const { ai } = report;
  const canRetry =
    report.investigation.status === "completed" && !["queued", "running"].includes(ai.status);

  const retry = useMutation({
    mutationFn: () => api.reanalyze(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["report", id] });
      queryClient.invalidateQueries({ queryKey: ["progress", id] });
      toast.success("AI analysis started. Deterministic findings are unchanged.");
    },
    onError: (error) => toast.error(errorMessage(error)),
  });

  const failed = ai.status === "failed" || ai.status === "unavailable";

  return (
    <Card>
      <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2">
        <CardTitle>Ghost Analyst</CardTitle>
        {ai.status === "completed" && <AiLabel model={ai.model} />}
      </CardHeader>
      <CardContent className="flex flex-col gap-3 text-sm">
        {failed && (
          <div
            role="alert"
            className="flex items-start gap-2 rounded-lg border border-severity-high/40 bg-severity-high/10 p-3"
          >
            <TriangleAlert className="mt-0.5 size-4 shrink-0 text-severity-high" aria-hidden />
            <div>
              <p className="font-medium">AI analysis did not complete.</p>
              <p className="text-muted-foreground">
                {ai.error} Deterministic findings below are unaffected.
              </p>
            </div>
          </div>
        )}
        {STATE_TEXT[ai.status] && (
          <p className="flex items-center gap-2 text-muted-foreground">
            {(ai.status === "running" || ai.status === "queued") && (
              <LoaderCircle className="size-4 animate-spin" aria-hidden />
            )}
            {STATE_TEXT[ai.status]}
          </p>
        )}
        {ai.status === "completed" && (
          <>
            <p>{ai.summary}</p>
            <div>
              <h3 className="mb-1 text-xs font-medium tracking-wide text-muted-foreground uppercase">
                Health assessment
              </h3>
              <p>{ai.health_assessment}</p>
            </div>
          </>
        )}
        {canRetry && (
          <Button
            variant="outline"
            size="sm"
            className="self-start"
            disabled={retry.isPending}
            onClick={() => retry.mutate()}
          >
            <RefreshCw aria-hidden />
            {ai.status === "completed" ? "Run AI analysis again" : "Retry AI analysis"}
          </Button>
        )}
      </CardContent>
    </Card>
  );
}
