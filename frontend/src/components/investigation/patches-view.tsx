"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CircleCheck, Download, FilePlus2, FilePen, GitCompare, LoaderCircle } from "lucide-react";
import { toast } from "sonner";

import { ConfirmButton } from "@/components/confirm-button";
import { EmptyState, ErrorState } from "@/components/states";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { api, errorMessage } from "@/lib/api";
import type { PatchProposal } from "@/lib/types";

function lineClass(line: string): string {
  if (line.startsWith("+++") || line.startsWith("---") || line.startsWith("diff ")) {
    return "text-muted-foreground";
  }
  if (line.startsWith("@@")) return "text-spectral";
  if (line.startsWith("+")) return "bg-primary/10 text-primary";
  if (line.startsWith("-")) return "bg-destructive/10 text-destructive";
  return "";
}

export function DiffPreview({ diff }: { diff: string }) {
  return (
    <pre
      tabIndex={0}
      aria-label="Proposed changes as a unified diff"
      className="max-h-[32rem] overflow-auto rounded-lg border border-border bg-background/60 p-3 font-mono text-xs leading-5"
    >
      {diff.split("\n").map((line, index) => (
        <span key={index} className={`block min-h-5 w-max min-w-full px-1 ${lineClass(line)}`}>
          {line}
        </span>
      ))}
    </pre>
  );
}

function Proposal({ patch, id }: { patch: PatchProposal; id: string }) {
  const queryClient = useQueryClient();
  const approve = useMutation({
    mutationFn: () => api.approvePatch(id, patch.id),
    onSuccess: (updated) => {
      queryClient.setQueryData(["patch", id], updated);
      toast.success("Approved. You can download the patch. Nothing has been applied.");
    },
    onError: (error) => toast.error(errorMessage(error)),
  });

  if (patch.files.length === 0) {
    return (
      <EmptyState icon={CircleCheck} title="Nothing to propose">
        {patch.message}
      </EmptyState>
    );
  }

  return (
    <Card>
      <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-3">
        <div className="min-w-0">
          <CardTitle>Proposed changes</CardTitle>
          <p className="mt-1 text-sm text-muted-foreground">{patch.message}</p>
        </div>
        {patch.status === "approved" ? (
          <a
            href={api.patchDownloadUrl(id, patch.id)}
            className={buttonVariants({ size: "sm" })}
          >
            <Download aria-hidden />
            Download patch
          </a>
        ) : (
          <ConfirmButton
            size="sm"
            disabled={approve.isPending}
            title="Approve this patch for download?"
            description="Confirm you have reviewed every change. GhostRepo will not apply the patch or change the repository. You decide if and when to apply it yourself."
            confirmLabel="I reviewed it, approve"
            onConfirm={() => approve.mutate()}
          >
            <CircleCheck aria-hidden />
            Approve patch
          </ConfirmButton>
        )}
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <ul className="flex flex-col gap-2">
          {patch.files.map((file) => {
            const Icon = file.change_type === "create" ? FilePlus2 : FilePen;
            return (
              <li key={file.path} className="flex items-start gap-2.5 text-sm">
                <Icon className="mt-0.5 size-4 shrink-0 text-primary" aria-hidden />
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-baseline gap-x-2">
                    <span className="font-mono break-all">{file.path}</span>
                    <span className="text-xs text-muted-foreground">
                      {file.change_type === "create" ? "new file" : "modified"}, +{file.additions}{" "}
                      −{file.deletions}
                    </span>
                  </div>
                  <p className="text-muted-foreground">{file.explanation}</p>
                </div>
              </li>
            );
          })}
        </ul>
        {patch.refused_paths.length > 0 && (
          <p className="text-sm text-muted-foreground">
            Refused by path validation: {patch.refused_paths.join(", ")}.
          </p>
        )}
        <DiffPreview diff={patch.diff} />
      </CardContent>
    </Card>
  );
}

export function PatchesView({ id }: { id: string }) {
  const queryClient = useQueryClient();
  const patch = useQuery({ queryKey: ["patch", id], queryFn: () => api.patch(id) });
  const generate = useMutation({
    mutationFn: () => api.generatePatch(id),
    onSuccess: (created) => queryClient.setQueryData(["patch", id], created),
    onError: (error) => toast.error(errorMessage(error)),
  });

  if (patch.isPending) return <Skeleton className="h-64 rounded-xl" />;
  if (patch.isError) return <ErrorState error={patch.error} onRetry={() => patch.refetch()} />;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-3">
        <Button onClick={() => generate.mutate()} disabled={generate.isPending}>
          {generate.isPending ? (
            <LoaderCircle className="animate-spin" aria-hidden />
          ) : (
            <GitCompare aria-hidden />
          )}
          {patch.data ? "Generate a new proposal" : "Generate patch proposal"}
        </Button>
        <p className="text-sm text-muted-foreground">
          Proposals are diffs only. GhostRepo never applies them to the repository.
        </p>
      </div>
      {patch.data ? (
        <Proposal patch={patch.data} id={id} />
      ) : (
        <EmptyState icon={GitCompare} title="No patch proposal yet">
          GhostRepo can propose missing project files. Generate a README draft first to include it
          when the repository has none.
        </EmptyState>
      )}
    </div>
  );
}
