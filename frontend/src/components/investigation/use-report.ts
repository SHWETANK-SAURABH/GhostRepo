"use client";

import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";
import type { Investigation } from "@/lib/types";

export function isActive(investigation: Pick<Investigation, "status" | "ai_status"> | undefined) {
  if (!investigation) return false;
  return (
    investigation.status === "queued" ||
    investigation.status === "running" ||
    investigation.ai_status === "queued" ||
    investigation.ai_status === "running"
  );
}

export function useReport(id: string) {
  return useQuery({
    queryKey: ["report", id],
    queryFn: () => api.report(id),
    refetchInterval: (query) => (isActive(query.state.data?.investigation) ? 1500 : false),
  });
}
