"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { LoaderCircle, RefreshCw, Save } from "lucide-react";
import { useEffect, type ReactNode } from "react";
import { Controller, useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { describeRuntime, useOllamaStatus } from "@/components/runtime-status";
import { ErrorState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { api, errorMessage } from "@/lib/api";
import type { RuntimeSettings } from "@/lib/types";

export const settingsSchema = z.object({
  ollama_endpoint: z.string().trim().url("Enter a full URL, such as http://localhost:11434."),
  ollama_model: z
    .string()
    .trim()
    .regex(/^[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}$/, "Enter a valid model name, such as gemma3:4b."),
  ai_enabled: z.boolean(),
  workspace_root: z.string().trim().min(1, "Enter the workspace folder."),
  max_file_size_kb: z.coerce
    .number<string | number>()
    .int("Use a whole number.")
    .min(1, "Use at least 1 KB.")
    .max(50_000, "Use at most 50,000 KB."),
  excluded_dirs: z.string(),
  analysis_timeout_seconds: z.coerce
    .number<string | number>()
    .int("Use a whole number.")
    .min(5, "Use at least 5 seconds.")
    .max(3600, "Use at most 3,600 seconds."),
});

type FormInput = z.input<typeof settingsSchema>;
type FormValues = z.output<typeof settingsSchema>;

function toForm(settings: RuntimeSettings): FormValues {
  return {
    ollama_endpoint: settings.ollama_endpoint,
    ollama_model: settings.ollama_model,
    ai_enabled: settings.ai_enabled,
    workspace_root: settings.workspace_root,
    max_file_size_kb: Math.round(settings.max_file_size_bytes / 1000),
    excluded_dirs: settings.excluded_dirs.join(", "),
    analysis_timeout_seconds: settings.analysis_timeout_seconds,
  };
}

function fromForm(values: FormValues): RuntimeSettings {
  return {
    ollama_endpoint: values.ollama_endpoint,
    ollama_model: values.ollama_model,
    ai_enabled: values.ai_enabled,
    workspace_root: values.workspace_root,
    max_file_size_bytes: values.max_file_size_kb * 1000,
    excluded_dirs: values.excluded_dirs
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean),
    analysis_timeout_seconds: values.analysis_timeout_seconds,
  };
}

function Field({
  id,
  label,
  error,
  hint,
  children,
}: {
  id: string;
  label: string;
  error?: string;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <Label htmlFor={id}>{label}</Label>
      {children}
      {hint && !error && <p className="text-xs text-muted-foreground">{hint}</p>}
      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}
    </div>
  );
}

function RuntimeCard() {
  const status = useOllamaStatus();
  const models = useQuery({ queryKey: ["ollama-models"], queryFn: api.ollamaModels });
  const tone = describeRuntime(status.data, status.isError);
  const Icon = tone.icon;

  return (
    <Card className="min-w-0">
      <CardHeader>
        <CardTitle>Ollama runtime</CardTitle>
        <CardDescription>Ollama runs the model on this machine.</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-3 text-sm">
        <p className="flex items-center gap-2 font-medium">
          <Icon className={`size-4 ${tone.color}`} aria-hidden />
          {tone.label}
        </p>
        <p className="text-muted-foreground">{status.data?.message}</p>
        {status.data?.version && (
          <p className="font-mono text-xs text-muted-foreground">
            Ollama version {status.data.version}
          </p>
        )}
        <div>
          <h3 className="mb-1 text-xs font-medium tracking-wide text-muted-foreground uppercase">
            Installed models
          </h3>
          {models.data?.models.length ? (
            <ul className="flex flex-col gap-1">
              {models.data.models.map((model) => (
                <li key={model.name} className="flex flex-wrap items-baseline gap-x-2">
                  <span className="font-mono text-xs break-all">{model.name}</span>
                  {model.parameter_size && (
                    <span className="text-xs text-muted-foreground">
                      {model.parameter_size} parameters
                    </span>
                  )}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-muted-foreground">{models.data?.message ?? "Checking…"}</p>
          )}
        </div>
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="self-start"
          disabled={status.isFetching}
          onClick={() => {
            status.refetch();
            models.refetch();
          }}
        >
          <RefreshCw className={status.isFetching ? "animate-spin" : ""} aria-hidden />
          Check again
        </Button>
      </CardContent>
    </Card>
  );
}

export function SettingsView() {
  const queryClient = useQueryClient();
  const settings = useQuery({ queryKey: ["settings"], queryFn: api.settings });
  const form = useForm<FormInput, unknown, FormValues>({ resolver: zodResolver(settingsSchema) });
  const {
    register,
    handleSubmit,
    reset,
    control,
    formState: { errors, isDirty },
  } = form;

  useEffect(() => {
    if (settings.data) reset(toForm(settings.data));
  }, [settings.data, reset]);

  const save = useMutation({
    mutationFn: (values: FormValues) => api.saveSettings(fromForm(values)),
    onSuccess: (saved) => {
      queryClient.setQueryData(["settings"], saved);
      queryClient.invalidateQueries({ queryKey: ["ollama-status"] });
      queryClient.invalidateQueries({ queryKey: ["ollama-models"] });
      queryClient.invalidateQueries({ queryKey: ["candidates"] });
      toast.success("Settings saved.");
    },
    onError: (error) => toast.error(errorMessage(error)),
  });

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Settings</h1>
        <p className="mt-1 text-muted-foreground">Changes apply to new investigations.</p>
      </div>

      {settings.isError && (
        <ErrorState error={settings.error} onRetry={() => settings.refetch()} />
      )}
      {settings.isPending && <Skeleton className="h-96 rounded-xl" />}

      {settings.data && (
        <div className="grid gap-4 lg:grid-cols-3">
          <form
            noValidate
            onSubmit={handleSubmit((values) => save.mutate(values))}
            className="min-w-0 lg:col-span-2"
          >
            <Card>
              <CardContent className="flex flex-col gap-5">
                <div className="flex items-center justify-between gap-4">
                  <div>
                    <Label htmlFor="ai_enabled">Local AI analysis</Label>
                    <p className="text-xs text-muted-foreground">
                      When off, reports use deterministic analyzers only.
                    </p>
                  </div>
                  <Controller
                    name="ai_enabled"
                    control={control}
                    render={({ field }) => (
                      <Switch
                        id="ai_enabled"
                        checked={Boolean(field.value)}
                        onCheckedChange={field.onChange}
                      />
                    )}
                  />
                </div>
                <Field
                  id="ollama_endpoint"
                  label="Ollama endpoint"
                  error={errors.ollama_endpoint?.message}
                  hint="Must be a local host from the server's allowlist, so evidence stays on this machine."
                >
                  <Input id="ollama_endpoint" className="font-mono" {...register("ollama_endpoint")} />
                </Field>
                <Field id="ollama_model" label="Model" error={errors.ollama_model?.message}>
                  <Input id="ollama_model" className="font-mono" {...register("ollama_model")} />
                </Field>
                <Field
                  id="workspace_root"
                  label="Workspace root"
                  error={errors.workspace_root?.message}
                  hint="Only folders inside this one can be investigated. It cannot be a drive root or your home folder."
                >
                  <Input id="workspace_root" className="font-mono" {...register("workspace_root")} />
                </Field>
                <div className="grid gap-5 sm:grid-cols-2">
                  <Field
                    id="max_file_size_kb"
                    label="Maximum scan file size (KB)"
                    error={errors.max_file_size_kb?.message}
                  >
                    <Input
                      id="max_file_size_kb"
                      type="number"
                      inputMode="numeric"
                      {...register("max_file_size_kb")}
                    />
                  </Field>
                  <Field
                    id="analysis_timeout_seconds"
                    label="Analysis timeout (seconds)"
                    error={errors.analysis_timeout_seconds?.message}
                  >
                    <Input
                      id="analysis_timeout_seconds"
                      type="number"
                      inputMode="numeric"
                      {...register("analysis_timeout_seconds")}
                    />
                  </Field>
                </div>
                <Field
                  id="excluded_dirs"
                  label="Excluded directories"
                  error={errors.excluded_dirs?.message}
                  hint="Folder names separated by commas."
                >
                  <Textarea
                    id="excluded_dirs"
                    rows={3}
                    className="font-mono text-xs"
                    {...register("excluded_dirs")}
                  />
                </Field>
                {save.isError && <ErrorState error={save.error} />}
                <Button type="submit" className="self-start" disabled={save.isPending || !isDirty}>
                  {save.isPending ? (
                    <LoaderCircle className="animate-spin" aria-hidden />
                  ) : (
                    <Save aria-hidden />
                  )}
                  Save settings
                </Button>
              </CardContent>
            </Card>
          </form>
          <RuntimeCard />
        </div>
      )}
    </div>
  );
}
