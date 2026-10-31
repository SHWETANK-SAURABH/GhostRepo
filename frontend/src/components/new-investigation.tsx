"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CircleCheck,
  CircleX,
  FlaskConical,
  FolderGit2,
  Folder,
  Ghost,
  LoaderCircle,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { ConfirmButton } from "@/components/confirm-button";
import { EmptyState, ErrorState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { api, ApiError, errorMessage } from "@/lib/api";
import type { ValidationResult } from "@/lib/types";

export const pathSchema = z.object({
  path: z
    .string()
    .trim()
    .min(1, "Enter a repository path.")
    .max(4096, "That path is too long.")
    .refine((value) => !value.includes("\0"), "That path contains an invalid character."),
});

type FormValues = z.infer<typeof pathSchema>;

function ConfirmRepository({
  result,
  onStart,
  starting,
}: {
  result: ValidationResult;
  onStart: () => void;
  starting: boolean;
}) {
  return (
    <div className="flex flex-col gap-4 rounded-lg border border-primary/30 bg-primary/5 p-4">
      <div className="flex items-start gap-3">
        <CircleCheck className="mt-0.5 size-5 shrink-0 text-primary" aria-hidden />
        <div className="min-w-0">
          <p className="truncate font-mono font-medium">{result.name}</p>
          <p className="text-sm text-muted-foreground">{result.message}</p>
        </div>
      </div>
      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
        <dt className="text-muted-foreground">Path in workspace</dt>
        <dd className="truncate font-mono">{result.relative_path}</dd>
        <dt className="text-muted-foreground">Git history</dt>
        <dd>{result.is_git ? "Found" : "Not found"}</dd>
        <dt className="text-muted-foreground">README</dt>
        <dd>{result.has_readme ? "Found" : "Not found"}</dd>
        <dt className="text-muted-foreground">Root manifests</dt>
        <dd className="font-mono">{result.manifests.join(", ") || "None"}</dd>
      </dl>
      <p className="text-xs text-muted-foreground">
        GhostRepo only reads this repository. It does not run its code, install its dependencies or
        change its files.
      </p>
      <Button onClick={onStart} disabled={starting} className="ghost-glow self-start">
        {starting ? <LoaderCircle className="animate-spin" aria-hidden /> : <Ghost aria-hidden />}
        {starting ? "Starting…" : "Confirm and start investigation"}
      </Button>
    </div>
  );
}

export function NewInvestigation() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const candidates = useQuery({ queryKey: ["candidates"], queryFn: api.candidates });
  const {
    register,
    handleSubmit,
    setValue,
    formState: { errors },
  } = useForm<FormValues>({ resolver: zodResolver(pathSchema), defaultValues: { path: "" } });

  const validate = useMutation({ mutationFn: (path: string) => api.validateRepository(path) });

  const start = useMutation({
    mutationFn: (path: string) => api.startInvestigation(path),
    onSuccess: (investigation) => {
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      router.push(`/investigations/${investigation.id}`);
    },
    onError: (error) => {
      // The running investigation is what the person wants to see.
      const details = error instanceof ApiError ? error.details : null;
      const existing = (details as { investigation_id?: string } | null)?.investigation_id;
      if (existing) router.push(`/investigations/${existing}`);
    },
  });

  const demo = useMutation({
    mutationFn: api.createDemo,
    onSuccess: (candidate) => {
      queryClient.invalidateQueries({ queryKey: ["candidates"] });
      toast.success("Demo repository created. Its contents are synthetic.");
      choose(candidate.relative_path);
    },
    onError: (error) => toast.error(errorMessage(error)),
  });

  function choose(path: string) {
    setValue("path", path, { shouldValidate: true });
    start.reset();
    validate.mutate(path);
  }

  const result = validate.data;

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">New investigation</h1>
        <p className="mt-1 text-muted-foreground">
          Choose a repository inside your configured workspace.
        </p>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card className="min-w-0">
          <CardHeader>
            <CardTitle>Repositories in the workspace</CardTitle>
            <CardDescription>
              Only folders directly inside the workspace are listed.
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            {candidates.isPending && <Skeleton className="h-24" />}
            {candidates.isError && (
              <ErrorState error={candidates.error} onRetry={() => candidates.refetch()} />
            )}
            {candidates.data && !candidates.data.workspace_available && (
              <ErrorState error={new Error("The configured workspace root is not available.")} />
            )}
            {candidates.data?.workspace_available && candidates.data.candidates.length === 0 && (
              <EmptyState icon={Folder} title="The workspace is empty">
                Copy or clone a repository into the workspace, or create the demo below.
              </EmptyState>
            )}
            {candidates.data && candidates.data.candidates.length > 0 && (
              <ul className="flex flex-col gap-1">
                {candidates.data.candidates.map((item) => (
                  <li key={item.relative_path}>
                    <button
                      type="button"
                      onClick={() => choose(item.relative_path)}
                      className="flex w-full items-center gap-2.5 rounded-md border border-transparent px-3 py-2 text-left text-sm transition-colors hover:border-border hover:bg-muted/50 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
                    >
                      {item.is_git ? (
                        <FolderGit2 className="size-4 shrink-0 text-primary" aria-hidden />
                      ) : (
                        <Folder className="size-4 shrink-0 text-muted-foreground" aria-hidden />
                      )}
                      <span className="min-w-0 flex-1 truncate font-mono">{item.name}</span>
                      {item.is_demo && (
                        <span className="rounded border border-spectral/40 px-1.5 py-0.5 text-xs text-spectral">
                          Demo
                        </span>
                      )}
                    </button>
                  </li>
                ))}
              </ul>
            )}
            <ConfirmButton
              variant="outline"
              size="sm"
              className="self-start"
              disabled={demo.isPending}
              title="Create the demo repository?"
              description="This creates a synthetic sample named haunted-demo in your workspace, or rebuilds it if it exists. It is real analysis of fake data, and no other folder is touched."
              confirmLabel="Create demo"
              onConfirm={() => demo.mutate()}
            >
              <FlaskConical aria-hidden />
              {demo.isPending ? "Creating…" : "Create demo repository"}
            </ConfirmButton>
          </CardContent>
        </Card>

        <Card className="min-w-0">
          <CardHeader>
            <CardTitle>Enter a path</CardTitle>
            <CardDescription>Relative to the workspace, or an absolute path inside it.</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            <form
              noValidate
              className="flex flex-col gap-2"
              onSubmit={handleSubmit((values) => {
                start.reset();
                validate.mutate(values.path);
              })}
            >
              <Label htmlFor="path">Repository path</Label>
              <div className="flex flex-col gap-2 sm:flex-row">
                <Input
                  id="path"
                  className="font-mono"
                  placeholder="my-old-project"
                  autoComplete="off"
                  aria-invalid={Boolean(errors.path)}
                  aria-describedby={errors.path ? "path-error" : undefined}
                  {...register("path")}
                />
                <Button type="submit" variant="secondary" disabled={validate.isPending}>
                  {validate.isPending && <LoaderCircle className="animate-spin" aria-hidden />}
                  Validate
                </Button>
              </div>
              {errors.path && (
                <p id="path-error" role="alert" className="text-sm text-destructive">
                  {errors.path.message}
                </p>
              )}
            </form>

            {validate.isError && <ErrorState error={validate.error} />}
            {result && !result.valid && (
              <div
                role="alert"
                className="flex items-start gap-2 rounded-lg border border-destructive/40 bg-destructive/10 p-3 text-sm"
              >
                <CircleX className="mt-0.5 size-4 shrink-0 text-destructive" aria-hidden />
                {result.message}
              </div>
            )}
            {result?.valid && (
              <ConfirmRepository
                result={result}
                starting={start.isPending}
                onStart={() => start.mutate(result.relative_path ?? "")}
              />
            )}
            {start.isError && <ErrorState error={start.error} />}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
