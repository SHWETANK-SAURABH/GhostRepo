"use client";

import { useQuery } from "@tanstack/react-query";
import { CircleCheck, CircleSlash, CircleX, LoaderCircle, TriangleAlert } from "lucide-react";

import { api } from "@/lib/api";
import type { OllamaStatus } from "@/lib/types";

type Tone = { icon: typeof CircleCheck; color: string; label: string };

export function describeRuntime(status: OllamaStatus | undefined, failed: boolean): Tone {
  if (failed) return { icon: CircleX, color: "text-destructive", label: "Backend unreachable" };
  if (!status) return { icon: LoaderCircle, color: "text-muted-foreground", label: "Checking…" };
  if (!status.enabled)
    return { icon: CircleSlash, color: "text-muted-foreground", label: "AI disabled" };
  if (!status.reachable)
    return { icon: CircleX, color: "text-severity-high", label: "Ollama offline" };
  if (!status.model_available)
    return { icon: TriangleAlert, color: "text-severity-medium", label: "Model not installed" };
  return { icon: CircleCheck, color: "text-primary", label: "Local AI ready" };
}

export function useOllamaStatus() {
  return useQuery({
    queryKey: ["ollama-status"],
    queryFn: api.ollamaStatus,
    refetchInterval: 30_000,
  });
}

export function RuntimeBadge() {
  const { data, isError } = useOllamaStatus();
  const tone = describeRuntime(data, isError);
  const Icon = tone.icon;
  return (
    <div className="flex items-center gap-2 text-xs" role="status">
      <Icon className={`size-3.5 shrink-0 ${tone.color}`} aria-hidden />
      <span className="text-muted-foreground">{tone.label}</span>
    </div>
  );
}
